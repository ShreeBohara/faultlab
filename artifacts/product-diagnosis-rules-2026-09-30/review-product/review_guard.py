"""Product-review guard ($0): import first in every review script run from faultlab/backend.

* sets PYTHON_DOTENV_DISABLED and installs the backend test suite's own audit hook that refuses any open of the project's
  real .env before a byte is read (tests/conftest.py _refuse_real_env, loaded without pytest fixtures);
* refuses every non-loopback socket connection AND every DNS lookup of a non-local name, and counts both;
* prints the counts at exit (stderr).
"""
import atexit
import ipaddress
import os
import socket
import sys
from pathlib import Path

sys.dont_write_bytecode = True
BACKEND = Path(__file__).resolve().parents[3] / 'backend'
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['WANDB_ERROR_REPORTING'] = 'false'
os.environ['WANDB_MODE'] = 'disabled'
_REAL_ENV = str(BACKEND.parent / '.env')


def _refuse_real_env(event, args):
    if event != 'open' or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    try:
        path = os.fsdecode(os.fspath(args[0]))
    except TypeError:
        return
    if os.path.basename(path) == '.env' and os.path.abspath(path) == _REAL_ENV:
        raise PermissionError('review guard: the project .env must not be read')


sys.addaudithook(_refuse_real_env)
for p in (str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'tests' / 'lab')):
    if p not in sys.path:
        sys.path.insert(0, p)

REFUSED, LOOPBACK = [], []
_connect, _connect_ex, _create, _gai = socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo


def _local(host):
    if isinstance(host, bytes):
        host = host.decode()
    if host in ('localhost', None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def _check(address):
    host = address[0] if isinstance(address, tuple) else address
    if _local(host):
        LOOPBACK.append(address)
        return
    REFUSED.append(address)
    raise PermissionError(f'review guard: outbound connection refused: {address!r}')


def connect(sock, address):
    if sock.family != socket.AF_UNIX:
        _check(address)
    return _connect(sock, address)


def connect_ex(sock, address):
    if sock.family != socket.AF_UNIX:
        _check(address)
    return _connect_ex(sock, address)


def create_connection(address, *args, **kwargs):
    _check(address)
    return _create(address, *args, **kwargs)


def getaddrinfo(host, *args, **kwargs):
    if not _local(host):
        REFUSED.append(('dns', host))
        raise PermissionError(f'review guard: DNS lookup refused: {host!r}')
    return _gai(host, *args, **kwargs)


socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo = connect, connect_ex, create_connection, getaddrinfo
atexit.register(lambda: print(f'[review guard] refused outbound connections/DNS lookups: {len(REFUSED)}; loopback connects: {len(LOOPBACK)}',
                              file=sys.stderr))
