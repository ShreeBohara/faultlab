"""Follow-up stage guard ($0): import before anything else in a script run from faultlab/backend.

Adapted from fixer/guard.py:
* installs the test suite's own audit hook that refuses any open of the project's real .env (tests/conftest.py);
* refuses every outbound socket connection that is not loopback or a Unix socket, and every DNS lookup of a non-local
  name; counts refusals;
* refuses (audit hook) any open of artifacts/heldout2/, audit/promotion.json or audit/final-audit*.json, which this
  stage may not read (backend/app/referee/checks.py is not refused: the product's own identity code imports it to
  compute scorer_hash, which the rules allow; no script of this stage opens it directly);
* prints the counts at exit (stderr).
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

REFUSED, LOOPBACK, LOOKUPS, PROTECTED = [], [], [], []
_connect, _connect_ex, _create, _getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo
ROOT = str(Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'))


def _protected(path):
    text = os.path.abspath(os.fspath(path)) if isinstance(path, (str, bytes, os.PathLike)) and not isinstance(path, bytes) else ''
    if not text:
        return False
    rel = text[len(ROOT) + 1:] if text.startswith(ROOT + os.sep) else None
    return rel is not None and (rel.startswith('artifacts/heldout2/') or rel == 'audit/promotion.json'
                                or (rel.startswith('audit/final-audit') and rel.endswith('.json')))


def _audit(event, args):
    if event == 'open' and args and _protected(args[0]):
        PROTECTED.append(str(args[0]))
        raise PermissionError(f'follow-up guard: protected path refused: {args[0]!r}')


sys.addaudithook(_audit)


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
    raise PermissionError(f'follow-up guard: outbound connection refused: {address!r}')


def connect(sock, address):
    _guard(sock, address)
    return _connect(sock, address)


def connect_ex(sock, address):
    _guard(sock, address)
    return _connect_ex(sock, address)


def create_connection(address, *args, **kwargs):
    if not _loopback(address):
        REFUSED.append(address)
        raise PermissionError(f'follow-up guard: outbound connection refused: {address!r}')
    LOOPBACK.append(address)
    return _create(address, *args, **kwargs)


def getaddrinfo(host, *args, **kwargs):
    if host not in (None, 'localhost') and not _loopback((host,)):
        LOOKUPS.append(host)
        raise PermissionError(f'follow-up guard: DNS lookup refused: {host!r}')
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo = connect, connect_ex, create_connection, getaddrinfo
atexit.register(lambda: print(f'[follow-up guard] refused outbound connections: {len(REFUSED)}; refused lookups: {len(LOOKUPS)}; '
                              f'refused protected opens: {len(PROTECTED)}; loopback connects: {len(LOOPBACK)}', file=sys.stderr))
