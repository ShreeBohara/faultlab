"""Reviewer's independent monitor (not part of the repo). Loaded by every Python process whose PYTHONPATH
includes this directory (pytest and any Python child it starts). It never blocks anything; it only records:
  * every socket.connect / socket.getaddrinfo audit event (address or host), and
  * every attempt to open a file whose basename is '.env' (path only; the file is NOT read by this hook).
Lines are appended to $NETMON_LOG as JSON. Loopback/UNIX addresses are recorded too and classified later."""
import os, sys, json, threading
_LOG = os.environ.get('NETMON_LOG')
_guard = threading.local()


def _write(kind, detail):
    if getattr(_guard, 'busy', False):
        return
    _guard.busy = True
    try:
        fd = os.open(_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (json.dumps({'pid': os.getpid(), 'kind': kind, 'detail': detail}) + '\n').encode())
        finally:
            os.close(fd)
    except Exception:
        pass
    finally:
        _guard.busy = False


def _hook(event, args):
    if getattr(_guard, 'busy', False):
        return
    if event == 'socket.connect':
        try:
            family = args[0].family
        except Exception:
            family = None
        _write('connect', {'family': str(family), 'address': repr(args[1])[:200]})
    elif event == 'socket.getaddrinfo':
        _write('getaddrinfo', {'host': repr(args[0])[:200], 'port': repr(args[1])[:20]})
    elif event == 'open' and args and isinstance(args[0], (str, bytes)):
        p = args[0] if isinstance(args[0], str) else args[0].decode(errors='replace')
        if os.path.basename(p) == '.env':
            _write('env_open_attempt', {'path': p})


if _LOG:
    sys.addaudithook(_hook)
