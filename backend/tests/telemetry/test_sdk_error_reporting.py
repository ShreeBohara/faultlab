"""Offline processes never contact third-party SDK crash telemetry, including at exit.

Weave 0.53.x builds a Sentry client when it is first imported unless
WANDB_ERROR_REPORTING is false, then posts a session from an atexit handler. The
per-test socket guard in conftest.py is gone by then, so these checks run fresh
interpreters under an independent guard that records (and blocks) every
non-loopback lookup or connection until the interpreter has fully exited.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

GUARD = r'''
import ipaddress, json, socket, sys
RECORD = sys.argv[1]
attempts = []
def _local(host):
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False
def _blocked(kind, target):
    attempts.append([kind, repr(target)])
    with open(RECORD, "w") as handle:
        json.dump(attempts, handle)
    raise OSError("network-silence guard: outbound socket blocked")
_gai, _create = socket.getaddrinfo, socket.create_connection
_connect, _connect_ex = socket.socket.connect, socket.socket.connect_ex
def _guarded_gai(host, *args, **kwargs):
    if not _local(host):
        _blocked("getaddrinfo", host)
    return _gai(host, *args, **kwargs)
def _guarded_create(address, *args, **kwargs):
    if not _local(address[0]):
        _blocked("create_connection", address)
    return _create(address, *args, **kwargs)
def _guarded_connect(sock, address):
    if sock.family != socket.AF_UNIX and not _local(address[0]):
        _blocked("connect", address)
    return _connect(sock, address)
def _guarded_connect_ex(sock, address):
    if sock.family != socket.AF_UNIX and not _local(address[0]):
        _blocked("connect_ex", address)
    return _connect_ex(sock, address)
socket.getaddrinfo, socket.create_connection = _guarded_gai, _guarded_create
socket.socket.connect, socket.socket.connect_ex = _guarded_connect, _guarded_connect_ex
with open(RECORD, "w") as handle:
    json.dump(attempts, handle)
'''

FAULTLAB_FIRST = r'''
import app
import weave
from weave.telemetry import trace_sentry
print("SENTRY_DISABLED" if trace_sentry.global_trace_sentry._disabled else "SENTRY_ENABLED")
'''

OFFLINE_STARTUP = r'''
import asyncio, sys
import httpx
from app.config import Settings
from app.main import create_app
application = create_app(settings=Settings(faultlab_artifact_dir=sys.argv[2]))
async def main():
    # The backend answers only local host names (app.main.LOCAL_HOSTS).
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1:8000") as client:
        for path in ("/api/health", "/api/config/status", "/api/readiness", "/api/bundle-imports"):
            assert (await client.get(path)).status_code == 200, path
asyncio.run(main())
# A later in-process SDK import (for example a live telemetry helper) stays silent.
import weave
from weave.telemetry import trace_sentry
assert trace_sentry.global_trace_sentry._disabled
print("STARTUP_OK")
'''

SDK_ONLY = r'''
import weave
from weave.telemetry import trace_sentry
print("SENTRY_DISABLED" if trace_sentry.global_trace_sentry._disabled else "SENTRY_ENABLED")
'''


def run_guarded(tmp_path, body, *, reporting=None, extra=()):
    record = tmp_path / 'attempts.json'
    environment = {'PATH': os.environ.get('PATH', ''), 'HOME': str(tmp_path / 'home'),
                   'PYTHONPATH': str(BACKEND), 'PYTHONDONTWRITEBYTECODE': '1'}
    if reporting is not None:
        environment['WANDB_ERROR_REPORTING'] = reporting
    (tmp_path / 'home').mkdir(exist_ok=True)
    completed = subprocess.run([sys.executable, '-c', GUARD + body, str(record), *extra],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=120)
    # Read only after the interpreter (and every atexit handler) has finished.
    attempts = json.loads(record.read_text())
    return completed, attempts


@pytest.mark.parametrize('reporting', [None, 'true'])
def test_faultlab_import_disables_sdk_crash_telemetry_before_weave_even_if_inherited(tmp_path, reporting):
    completed, attempts = run_guarded(tmp_path, FAULTLAB_FIRST, reporting=reporting)
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert 'SENTRY_DISABLED' in completed.stdout
    assert attempts == []


def test_offline_startup_and_later_sdk_import_open_no_outbound_socket_through_exit(tmp_path):
    data = tmp_path / 'store'
    completed, attempts = run_guarded(tmp_path, OFFLINE_STARTUP, extra=(str(data),))
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert 'STARTUP_OK' in completed.stdout and attempts == []


def test_guard_observes_the_unpatched_sdk_exit_upload(tmp_path):
    """Control: without FaultLab's setting, the installed SDK really tries to report."""
    pytest.importorskip('sentry_sdk')
    completed, attempts = run_guarded(tmp_path, SDK_ONLY)
    assert completed.returncode == 0, completed.stderr[-2000:]
    if 'SENTRY_ENABLED' not in completed.stdout:
        pytest.skip('Installed Weave no longer enables Sentry by default')
    assert attempts and any('sentry.io' in target for _, target in attempts)


def test_this_test_process_cannot_report_at_exit():
    assert os.environ['WANDB_ERROR_REPORTING'] == 'false'
    from weave.telemetry import trace_sentry
    assert trace_sentry.global_trace_sentry._disabled
