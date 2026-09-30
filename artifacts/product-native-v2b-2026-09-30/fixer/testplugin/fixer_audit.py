"""Fixer's pytest plugin (copied from the integrity reviewer's review_audit.py): an audit hook, installed before any test module is imported, that
logs (a) every non-loopback socket connect / getaddrinfo attempt and (b) every open of a file named .env
(path only, never content) to REVIEW_AUDIT_LOG. It blocks nothing itself; the suite's own guards still apply."""
import os, sys, json
LOG = os.environ.get('REVIEW_AUDIT_LOG')
_seen = {'socket_connect_nonlocal': 0, 'socket_connect_local': 0, 'getaddrinfo_nonlocal': 0, 'getaddrinfo_local': 0,
         'dotenv_opens': 0, 'unix_connect': 0}
_LOCAL = ('127.0.0.1', '::1', 'localhost', 'testserver', 'test', 'lab', '0.0.0.0')
def _write(kind, detail):
    if LOG:
        with open(LOG, 'a') as fh:
            fh.write(json.dumps({'kind': kind, 'detail': detail}) + '\n')
def _hook(event, args):
    try:
        if event == 'socket.connect':
            addr = args[1]
            if isinstance(addr, (tuple, list)):
                host = str(addr[0])
                key = 'socket_connect_local' if host in _LOCAL or host.startswith('127.') else 'socket_connect_nonlocal'
                _seen[key] += 1
                _write(key, repr(addr) + ' test=' + os.environ.get('PYTEST_CURRENT_TEST', '?'))
            else:
                _seen['unix_connect'] += 1
        elif event == 'socket.getaddrinfo':
            host = str(args[0])
            key = 'getaddrinfo_local' if host in _LOCAL or host.startswith('127.') else 'getaddrinfo_nonlocal'
            _seen[key] += 1
            if key.endswith('nonlocal'): _write(key, host)
        elif event == 'open':
            path = args[0]
            if isinstance(path, (str, bytes, os.PathLike)):
                p = os.fsdecode(path)
                if os.path.basename(p) == '.env':
                    _seen['dotenv_opens'] += 1; _write('dotenv_open_attempt', p + ' test=' + os.environ.get('PYTEST_CURRENT_TEST', '?'))
    except Exception:
        pass
sys.addaudithook(_hook)
def pytest_sessionfinish(session, exitstatus):
    _write('summary', dict(_seen))
