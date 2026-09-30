"""Reviewer guard ($0): import first in every reviewer script run from faultlab/backend.

* disables python-dotenv and imports the test suite's conftest (its audit hook refuses any open of the real .env);
* refuses every outbound socket that is not loopback or a Unix socket, and counts refusals;
* prints the counts at exit (stderr).
"""
import atexit
import ipaddress
import os
import socket
import sys
from pathlib import Path

BACKEND = Path.cwd()
assert BACKEND.name == 'backend', 'run from faultlab/backend'
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'tests' / 'lab')]
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
import conftest  # noqa: E402,F401

REFUSED, LOOPBACK = [], []
_connect, _connect_ex, _create = socket.socket.connect, socket.socket.connect_ex, socket.create_connection


def _loopback(address):
    host = address[0] if isinstance(address, tuple) else address
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == 'localhost'


def _check(family, address):
    if family == socket.AF_UNIX:
        return
    if _loopback(address):
        LOOPBACK.append(address); return
    REFUSED.append(address)
    raise PermissionError(f'reviewer guard: outbound connection refused: {address!r}')


def connect(sock, address):
    _check(sock.family, address); return _connect(sock, address)


def connect_ex(sock, address):
    _check(sock.family, address); return _connect_ex(sock, address)


def create_connection(address, *args, **kwargs):
    _check(socket.AF_INET, address); return _create(address, *args, **kwargs)


socket.socket.connect, socket.socket.connect_ex, socket.create_connection = connect, connect_ex, create_connection


@atexit.register
def _report():
    print(f'[reviewer guard] refused outbound connections: {len(REFUSED)}; loopback: {len(LOOPBACK)}', file=sys.stderr)
