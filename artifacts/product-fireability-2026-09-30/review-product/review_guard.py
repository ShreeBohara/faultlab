"""Product reviewer guard ($0, offline). Import FIRST in every review script (run with cwd = a backend/ directory).

* Refuses, before any byte is read, every open of a file named `.env` (any tree), and of anything under
  artifacts/heldout2/ or audit/final-audit*. (backend/app/referee/checks.py is never opened by these scripts; the
  product imports it as a module, which is how the test suite runs too.)
* Counts every open of audit/promotion.json by product code (plan creation hashes that manifest through
  app.referee.manifests.load_manifest, exactly as the test suite does); the review scripts never print its content,
  and the learning-loop promotion stage is blocked separately (review_harness.block_promotion).
* Refuses every outbound socket that is not loopback or a Unix socket, and counts refusals.
* Prints the counts at exit (stderr).
"""
import atexit
import ipaddress
import os
import socket
import sys
from pathlib import Path

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['WANDB_ERROR_REPORTING'] = 'false'
os.environ.setdefault('FAULTLAB_ALLOWED_HOSTS', 'test,testserver,lab')

REFUSED_SOCKETS = []
LOOPBACK = []
REFUSED_OPENS = []
PROMOTION_MANIFEST_OPENS = []


def _audit(event, args):
    if event != 'open' or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    try:
        path = os.path.abspath(os.fsdecode(os.fspath(args[0])))
    except TypeError:
        return
    base = os.path.basename(path)
    if base == '.env' or '/artifacts/heldout2/' in path or '/audit/final-audit' in path:
        REFUSED_OPENS.append(path)
        raise PermissionError(f'review guard: refused open of a protected file: {base}')
    if path.endswith('/audit/promotion.json'):
        PROMOTION_MANIFEST_OPENS.append(path)


sys.addaudithook(_audit)

_connect, _connect_ex, _create = socket.socket.connect, socket.socket.connect_ex, socket.create_connection


def _loopback(address):
    host = address[0] if isinstance(address, tuple) else address
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ('localhost',)


def _check(sock, address):
    if sock.family == socket.AF_UNIX:
        return
    if _loopback(address):
        LOOPBACK.append(address)
        return
    REFUSED_SOCKETS.append(address)
    raise PermissionError(f'review guard: outbound connection refused: {address!r}')


def connect(sock, address):
    _check(sock, address)
    return _connect(sock, address)


def connect_ex(sock, address):
    _check(sock, address)
    return _connect_ex(sock, address)


def create_connection(address, *args, **kwargs):
    if not _loopback(address):
        REFUSED_SOCKETS.append(address)
        raise PermissionError(f'review guard: outbound connection refused: {address!r}')
    LOOPBACK.append(address)
    return _create(address, *args, **kwargs)


socket.socket.connect, socket.socket.connect_ex, socket.create_connection = connect, connect_ex, create_connection


def counts():
    return {'refused_outbound_connections': len(REFUSED_SOCKETS), 'loopback_connections': len(LOOPBACK),
            'refused_protected_file_opens': len(REFUSED_OPENS),
            'promotion_manifest_opens_by_product_code': len(PROMOTION_MANIFEST_OPENS)}


@atexit.register
def _report():
    print(f'review guard: {counts()}', file=sys.stderr)
