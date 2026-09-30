"""Reviewer guard, loaded as a pytest plugin (-p rguard) or imported first by a script. $0, offline.

* refuses every outbound socket connection that is not loopback or a Unix socket, and every DNS lookup of a non-local name;
* refuses (audit hook) any open of a .env file (other than .env.example), of artifacts/heldout2/, audit/promotion.json
  and audit/final-audit*.json (backend/app/referee/checks.py is not refused: the product imports it when tests run; no
  script of this review opens it directly);
* refuses any open for writing under /Users/shree/FaultLab_Runs or the real repo (except this review folder), after
  resolving symlinks, so a scratch tree that links to real artifacts can never write through the link;
* refuses sqlite3.connect to a saved store unless it is a file: URI with mode=ro;
* prints counts at exit (stderr).
"""
import atexit
import ipaddress
import os
import socket
import sys

REFUSED, LOOKUPS, PROTECTED, LOOPBACK = [], [], [], []
_connect, _connect_ex, _create, _getaddrinfo = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection,
                                                socket.getaddrinfo)


REAL = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
REVIEW = REAL + '/artifacts/product-diagnosis-rules-2026-09-30/followup-review'
RUNS = '/Users/shree/FaultLab_Runs'


def _is_protected(text):
    base = os.path.basename(text)
    real_env = base.startswith('.env') and base != '.env.example' and (text.startswith(REAL + '/') or text.startswith(RUNS + '/'))
    return (real_env or '/artifacts/heldout2/' in text or text.endswith('/artifacts/heldout2')
            or text.endswith('/audit/promotion.json') or ('/audit/final-audit' in text and text.endswith('.json')))


def _audit(event, args):
    if event == 'sqlite3.connect' and args:
        database = os.fspath(args[0]) if isinstance(args[0], (str, os.PathLike)) else ''
        if RUNS + '/' in database or RUNS + '/' in os.path.realpath(database.split('?')[0].removeprefix('file:') or '.'):
            if not (database.startswith('file:') and 'mode=ro' in database):
                PROTECTED.append('SQLITE-RW ' + database)
                raise PermissionError(f'reviewer guard: saved store opened without mode=ro: {database!r}')
        return
    if event != 'open' or not args:
        return
    path = args[0]
    if not isinstance(path, (str, os.PathLike)):
        return
    text = os.path.realpath(os.path.abspath(os.fspath(path)))
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 else 0
    writing = ((isinstance(mode, str) and any(c in mode for c in 'wax+'))
               or (isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND))))
    if _is_protected(text):
        PROTECTED.append(text)
        raise PermissionError(f'reviewer guard: protected path refused: {text!r}')
    if writing and (text.startswith(RUNS + '/') or (text.startswith(REAL + '/') and not text.startswith(REVIEW + '/'))):
        PROTECTED.append('WRITE ' + text)
        raise PermissionError(f'reviewer guard: write refused (saved stores / real repo are read-only here): {text!r}')


sys.addaudithook(_audit)


def _loopback(address):
    host = address[0] if isinstance(address, tuple) else address
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ('localhost',)


def _guard(sock, address):
    if sock.family == socket.AF_UNIX:
        return
    if _loopback(address):
        LOOPBACK.append(address)
        return
    REFUSED.append(address)
    raise PermissionError(f'reviewer guard: outbound connection refused: {address!r}')


def connect(sock, address):
    _guard(sock, address)
    return _connect(sock, address)


def connect_ex(sock, address):
    _guard(sock, address)
    return _connect_ex(sock, address)


def create_connection(address, *args, **kwargs):
    if not _loopback(address):
        REFUSED.append(address)
        raise PermissionError(f'reviewer guard: outbound connection refused: {address!r}')
    LOOPBACK.append(address)
    return _create(address, *args, **kwargs)


def getaddrinfo(host, *args, **kwargs):
    if host not in (None, 'localhost') and not _loopback((host,)):
        LOOKUPS.append(host)
        raise PermissionError(f'reviewer guard: DNS lookup refused: {host!r}')
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo = (connect, connect_ex,
                                                                                                create_connection, getaddrinfo)
atexit.register(lambda: print(f'[reviewer guard] refused outbound: {len(REFUSED)}; refused lookups: {len(LOOKUPS)}; '
                              f'refused protected opens: {len(PROTECTED)}; loopback connects: {len(LOOPBACK)}'
                              + (f'; refused: {PROTECTED[:10]}' if PROTECTED else ''), file=sys.stderr))
