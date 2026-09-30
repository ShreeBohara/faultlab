"""Verifier guard ($0). Import first in any verifier Python script.

* Audit hook: refuses (before any byte is read) every open of a file named .env or .env.* (except .env.example),
  of audit/promotion.json, audit/final-audit*.json and anything under artifacts/heldout2/, in ANY tree.
  (checks.py is not blocked: the repo's own identity / gate_freeze code hashes it; nothing here prints it.)
* Refuses every non-loopback, non-Unix socket connect and every non-loopback name lookup; counts them.
* At exit prints one line to stderr: refused connects, refused lookups, refused protected opens.
"""
import atexit, ipaddress, os, socket, sys

REFUSED_NET, REFUSED_DNS, REFUSED_OPEN = [], [], []


def _protected(path):
    try:
        p = os.path.abspath(os.fsdecode(path))
    except Exception:
        return False
    base = os.path.basename(p)
    if base == '.env' or (base.startswith('.env.') and base != '.env.example'):
        return True
    if p.endswith('/audit/promotion.json') or ('/audit/final-audit' in p and p.endswith('.json')):
        return True
    return '/artifacts/heldout2/' in p or p.endswith('/artifacts/heldout2')


def _hook(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)) and _protected(args[0]):
        REFUSED_OPEN.append(os.fsdecode(args[0]))
        raise PermissionError(f'verifier guard: protected path refused: {args[0]!r}')


sys.addaudithook(_hook)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['WANDB_MODE'] = 'disabled'
os.environ['WANDB_ERROR_REPORTING'] = 'false'


def _loop(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ('localhost',)


_c, _cx, _cc, _gai = socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo


def _check(sock, address):
    if sock.family == socket.AF_UNIX:
        return
    host = address[0] if isinstance(address, tuple) else address
    if not _loop(host):
        REFUSED_NET.append(repr(address))
        raise PermissionError(f'verifier guard: outbound connect refused: {address!r}')


def connect(sock, address):
    _check(sock, address); return _c(sock, address)


def connect_ex(sock, address):
    _check(sock, address); return _cx(sock, address)


def create_connection(address, *a, **k):
    if not _loop(address[0]):
        REFUSED_NET.append(repr(address)); raise PermissionError(f'verifier guard: outbound connect refused: {address!r}')
    return _cc(address, *a, **k)


def getaddrinfo(host, *a, **k):
    if host is not None and not _loop(host if isinstance(host, str) else host.decode()):
        REFUSED_DNS.append(repr(host)); raise socket.gaierror(f'verifier guard: lookup refused: {host!r}')
    return _gai(host, *a, **k)


socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo = connect, connect_ex, create_connection, getaddrinfo
atexit.register(lambda: print(f'[verifier guard] refused outbound connects: {len(REFUSED_NET)}; refused lookups: {len(REFUSED_DNS)}; '
                              f'refused protected opens: {len(REFUSED_OPEN)}', file=sys.stderr))
