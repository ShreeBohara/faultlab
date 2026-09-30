"""Fixer guard ($0): import before anything else in a fixer script run from faultlab/backend.

* installs the test suite's own audit hook that refuses any open of the project's real .env (tests/conftest.py);
* refuses every outbound socket connection that is not loopback or a Unix socket, and counts refusals;
* prints the counts at exit (stderr), so a script's log shows 0 refused connections.
"""
import atexit
import ipaddress
import os
import socket
import sys
from pathlib import Path

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests')]
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
import conftest  # noqa: E402,F401  (refuses the real .env before any byte is read)

REFUSED = []
LOOPBACK = []
_connect, _connect_ex, _create = socket.socket.connect, socket.socket.connect_ex, socket.create_connection


def _loopback(address):
    host = address[0] if isinstance(address, tuple) else address
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ('localhost',)


def _guard(sock, address):
    if sock.family == socket.AF_UNIX:
        return True
    if _loopback(address):
        LOOPBACK.append(address)
        return True
    REFUSED.append(address)
    raise PermissionError(f'fixer guard: outbound connection refused: {address!r}')


def connect(sock, address):
    _guard(sock, address)
    return _connect(sock, address)


def connect_ex(sock, address):
    _guard(sock, address)
    return _connect_ex(sock, address)


def create_connection(address, *args, **kwargs):
    if not _loopback(address):
        REFUSED.append(address)
        raise PermissionError(f'fixer guard: outbound connection refused: {address!r}')
    LOOPBACK.append(address)
    return _create(address, *args, **kwargs)


socket.socket.connect, socket.socket.connect_ex, socket.create_connection = connect, connect_ex, create_connection
atexit.register(lambda: print(f'[fixer guard] refused outbound connections: {len(REFUSED)}; loopback connects: {len(LOOPBACK)}',
                              file=sys.stderr))
