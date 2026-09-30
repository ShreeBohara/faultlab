"""Product reviewer's guard ($0). Import first in any review script run from faultlab/backend.

* loads the test suite's conftest (its audit hook refuses any open of the project's real .env; dotenv disabled);
* refuses every outbound socket connection and name lookup that is not loopback or a Unix socket;
* prints the refusal count at exit (stderr).
"""
import atexit
import os
import socket
import sys
from pathlib import Path

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'tests' / 'lab')]
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
import conftest  # noqa: E402,F401

REFUSED = []
LOOPBACK = {'127.0.0.1', '::1', 'localhost'}
_connect, _connect_ex, _getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo


def _ok(sock, address):
    return sock.family == socket.AF_UNIX or (isinstance(address, tuple) and address[0] in LOOPBACK)


def connect(sock, address):
    if not _ok(sock, address):
        REFUSED.append(repr(address)); raise PermissionError(f'review guard refused {address!r}')
    return _connect(sock, address)


def connect_ex(sock, address):
    if not _ok(sock, address):
        REFUSED.append(repr(address)); raise PermissionError(f'review guard refused {address!r}')
    return _connect_ex(sock, address)


def getaddrinfo(host, *args, **kwargs):
    name = host.decode() if isinstance(host, bytes) else host
    if host is not None and name not in LOOPBACK:
        REFUSED.append(repr(host)); raise OSError(f'review guard refused name lookup {host!r}')
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
atexit.register(lambda: print(f'[review guard] refused outbound connections/lookups: {len(REFUSED)}', file=sys.stderr))
