"""Independent verifier guard (product dependability, 2026-09-29). Loaded into every Python process that inherits
PYTHONPATH=<this folder>, as a sys.addaudithook audit hook (below any monkeypatch a test may install).

* socket connect / sendto / name lookup: non-loopback targets are LOGGED and REFUSED (PermissionError).
  Loopback and unix-socket connects are counted and written once per process at exit.
* Opens of the project's real .env: LOGGED. REFUSED here unless the backend test conftest (backend/tests/conftest.py)
  has registered its own audit hook in this process, in which case that hook refuses it with its own message (a test
  asserts that message). Revision 2: registration is seen through the 'sys.addaudithook' audit event (the caller's
  file), because pytest can later replace sys.modules['conftest'] with another directory's conftest.
  So in no process can the real .env be read.
* Opens of protected files (audit/promotion.json, final-audit, heldout2, backend/app/referee/checks.py) are
  counted per path, so the verifier can say which process read them (the product hashes checks.py; nothing here
  prints any content).
"""
import atexit
import ipaddress
import json
import os
import sys

_ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
_ENV = os.path.realpath(os.path.join(_ROOT, '.env'))
_LOG = os.environ.get('VERIFY_GUARD_LOG')
_NAMES = {'localhost', 'localhost.localdomain', '', 'ip6-localhost', 'ip6-loopback'}
_counts = {'loopback_connect': 0, 'local_lookup': 0, 'unix_connect': 0, 'refused_outside': 0, 'env_open': 0}
_protected_counts = {}
_busy = False
_conftest_hook = False  # sticky: audit hooks cannot be removed once added


def _log(kind, detail):
    if not _LOG:
        return
    try:
        with open(_LOG, 'a') as fh:
            fh.write(json.dumps({'kind': kind, 'detail': str(detail) if kind == 'process_summary' else str(detail)[:300], 'pid': os.getpid(),
                                 'argv': ' '.join(sys.argv[:3])[:200]}) + '\n')
    except Exception:
        pass


def _local(host):
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode(errors='replace')
    host = str(host).strip('[]')
    if host.lower() in _NAMES or host.lower().endswith('.localhost'):
        return True
    try:
        ip = ipaddress.ip_address(host.split('%')[0])
    except ValueError:
        return False
    mapped = getattr(ip, 'ipv4_mapped', None)
    if mapped is not None:
        ip = mapped
    return ip.is_loopback or ip.is_unspecified


def _protected(path):
    return (path.endswith('/audit/promotion.json') or 'final-audit' in path or '/heldout2' in path
            or path.endswith('/backend/app/referee/checks.py'))


def _conftest_guard_loaded():
    return _conftest_hook


def _hook(event, args):
    global _busy, _conftest_hook
    if _busy:
        return
    if event == 'sys.addaudithook':
        frame = sys._getframe(1)
        while frame is not None:
            if frame.f_code.co_filename.replace('\\', '/').endswith('backend/tests/conftest.py'):
                _conftest_hook = True
                _log('conftest_audit_hook_seen', frame.f_code.co_filename)
                break
            frame = frame.f_back
        return
    if event == 'open':
        p = args[0]
        if isinstance(p, int):
            return
        _busy = True
        try:
            try:
                rp = os.path.realpath(os.fsdecode(p))
            except Exception:
                return
            if rp == _ENV:
                _counts['env_open'] += 1
                handled = _conftest_guard_loaded()
                _log('env_open', rp + (' (conftest hook refuses)' if handled else ' (REFUSED by verifier guard)'))
                if not handled:
                    raise PermissionError('verify guard: .env open refused')
            elif _protected(rp):
                if rp not in _protected_counts:
                    _log('protected_open_first', rp)
                _protected_counts[rp] = _protected_counts.get(rp, 0) + 1
        finally:
            _busy = False
    elif event in ('socket.connect', 'socket.sendto', 'socket.sendmsg'):
        addr = args[1] if len(args) > 1 else None
        if isinstance(addr, tuple) and addr:
            if not _local(addr[0]):
                _counts['refused_outside'] += 1
                _log('REFUSED_' + event, addr)
                raise PermissionError('verify guard: outside connect refused')
            _counts['loopback_connect'] += 1
        else:
            _counts['unix_connect'] += 1
    elif event in ('socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.gethostbyname_ex'):
        if not _local(args[0]):
            _counts['refused_outside'] += 1
            _log('REFUSED_lookup', args[0])
            raise PermissionError('verify guard: outside lookup refused')
        _counts['local_lookup'] += 1


def _summary():
    _log('process_summary', json.dumps({**_counts, 'protected': _protected_counts}))


sys.addaudithook(_hook)
atexit.register(_summary)
_log('guard_loaded', sys.executable)
