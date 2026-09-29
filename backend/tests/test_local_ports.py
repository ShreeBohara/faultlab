"""Port settings and the offline check runner (no services, sockets or provider calls).

FAULTLAB_SIMULATOR_PORT, FAULTLAB_BACKEND_PORT and FAULTLAB_DASHBOARD_PORT select the local ports; unset
means 8001, 8000 and 5173 exactly as before. The shell scripts run here against a stub interpreter and a
stub npm in a scratch copy of the repository layout, so nothing real starts.
"""
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import time

import httpx
import pytest

from app import local
from app.cli import client
from app.ports import DEFAULT_PORTS, PortSettingError, configured_port, local_url

ROOT = Path(__file__).resolve().parents[2]
PORT_NAMES = ('FAULTLAB_SIMULATOR_PORT', 'FAULTLAB_BACKEND_PORT', 'FAULTLAB_DASHBOARD_PORT')
BAD_VALUES = ('0', '65536', '08000', 'abc', ' 8000', '80 00', '-1', '8000.5', '١٢٣')


@pytest.fixture
def no_port_settings(monkeypatch):
    for name in (*PORT_NAMES, 'FAULTLAB_SIMULATOR_URL'):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------- the shared rule (Python)

def test_defaults_are_the_documented_ports():
    assert DEFAULT_PORTS == {'FAULTLAB_SIMULATOR_PORT': 8001, 'FAULTLAB_BACKEND_PORT': 8000,
                             'FAULTLAB_DASHBOARD_PORT': 5173}
    assert {name: configured_port(name, {}) for name in PORT_NAMES} == DEFAULT_PORTS
    assert configured_port('FAULTLAB_BACKEND_PORT', {'FAULTLAB_BACKEND_PORT': ''}) == 8000
    assert local_url('FAULTLAB_BACKEND_PORT', {}) == 'http://127.0.0.1:8000'


def test_one_setting_per_service():
    environ = {'FAULTLAB_SIMULATOR_PORT': '18001', 'FAULTLAB_BACKEND_PORT': '18000', 'FAULTLAB_DASHBOARD_PORT': '65535'}
    assert [configured_port(name, environ) for name in PORT_NAMES] == [18001, 18000, 65535]
    with pytest.raises(KeyError):
        configured_port('PORT', environ)


@pytest.mark.parametrize('value', BAD_VALUES)
def test_a_value_that_is_not_a_port_is_refused_with_its_name(value):
    with pytest.raises(PortSettingError, match='FAULTLAB_BACKEND_PORT must be a whole port number from 1 to 65535'):
        configured_port('FAULTLAB_BACKEND_PORT', {'FAULTLAB_BACKEND_PORT': value})


# ---------------------------------------------------------------- the paired launcher

def test_default_launch_plan_is_unchanged(tmp_path, no_port_settings, monkeypatch):
    monkeypatch.setattr(local.shutil, 'which', lambda name: '/stub/npm')
    path, environment, commands = local.launch_plan(tmp_path / 'data')
    assert environment['FAULTLAB_SIMULATOR_URL'] == 'http://127.0.0.1:8001'
    # The exact commands the launcher used before ports became settings.
    assert commands == [
        ('simulator', [sys.executable, '-m', 'uvicorn', 'app.simulator.main:app', '--host', '127.0.0.1',
                       '--port', '8001', '--timeout-keep-alive', '75'], local.ROOT / 'backend', 8001),
        ('backend', [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000',
                     '--no-access-log'], local.ROOT / 'backend', 8000),
        ('dashboard', ['/stub/npm', 'run', 'dev'], local.ROOT / 'frontend', 5173)]


def test_launch_plan_uses_the_three_settings_and_tells_the_dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(local.shutil, 'which', lambda name: '/stub/npm')
    for name, value in zip(PORT_NAMES, ('18001', '18000', '15173')):
        monkeypatch.setenv(name, value)
    monkeypatch.setenv('FAULTLAB_SIMULATOR_URL', 'http://127.0.0.1:8001')     # e.g. from a copied template
    _, environment, commands = local.launch_plan(tmp_path / 'data')
    assert [(name, port, command[command.index('--port') + 1] if '--port' in command else None)
            for name, command, _, port in commands] == [
        ('simulator', 18001, '18001'), ('backend', 18000, '18000'), ('dashboard', 15173, None)]
    assert environment['FAULTLAB_SIMULATOR_URL'] == 'http://127.0.0.1:18001'
    assert (environment['FAULTLAB_BACKEND_PORT'], environment['FAULTLAB_DASHBOARD_PORT']) == ('18000', '15173')


def test_launcher_refuses_a_bad_or_repeated_port_before_starting_anything(tmp_path, monkeypatch, capsys,
                                                                               no_port_settings):
    monkeypatch.setattr(local, 'supervise', lambda *a: pytest.fail('nothing may start'))
    monkeypatch.setenv('FAULTLAB_BACKEND_PORT', 'abc')
    with pytest.raises(SystemExit) as exit_info:
        local.main(['--data-dir', str(tmp_path / 'data'), '--no-frontend'])
    assert exit_info.value.code == 2 and 'FAULTLAB_BACKEND_PORT must be a whole port number' in capsys.readouterr().err
    monkeypatch.setenv('FAULTLAB_BACKEND_PORT', '18001')
    monkeypatch.setenv('FAULTLAB_SIMULATOR_PORT', '18001')
    with pytest.raises(SystemExit):
        local.main(['--data-dir', str(tmp_path / 'data'), '--no-frontend'])
    assert 'must be three different ports' in capsys.readouterr().err
    assert not (tmp_path / 'data').exists()


def test_launcher_prints_the_selected_addresses(tmp_path, monkeypatch, capsys, no_port_settings):
    monkeypatch.setattr(local, 'check_ports', lambda commands: None)
    monkeypatch.setattr(local, 'supervise', lambda commands, environment: 0)
    monkeypatch.setattr(local.shutil, 'which', lambda name: '/stub/npm')
    assert local.main(['--data-dir', str(tmp_path / 'data')]) == 0
    assert 'Dashboard: http://127.0.0.1:5173\n' in capsys.readouterr().out
    monkeypatch.setenv('FAULTLAB_DASHBOARD_PORT', '15173')
    monkeypatch.setenv('FAULTLAB_BACKEND_PORT', '18000')
    assert local.main(['--data-dir', str(tmp_path / 'data')]) == 0
    assert 'Dashboard: http://127.0.0.1:15173\n' in capsys.readouterr().out
    assert local.main(['--data-dir', str(tmp_path / 'data'), '--no-frontend']) == 0
    assert 'API: http://127.0.0.1:18000\n' in capsys.readouterr().out


# ---------------------------------------------------------------- the CLI client (run-demo, export-evidence, ...)

class RecordingClient:
    seen = []

    def __init__(self, *, base_url, timeout, trust_env):
        RecordingClient.seen.append(base_url)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, path, json=None):
        return httpx.Response(200, json={'ok': True}, request=httpx.Request(method, 'http://127.0.0.1' + path))


def test_cli_client_addresses_the_backend_port(monkeypatch, no_port_settings):
    RecordingClient.seen = []
    monkeypatch.setattr(client.httpx, 'Client', RecordingClient)
    assert client.request('GET', '/api/health') == {'ok': True}
    monkeypatch.setenv('FAULTLAB_BACKEND_PORT', '18000')
    client.request('GET', '/api/health')
    monkeypatch.setattr(client, 'BASE_URL', 'http://127.0.0.1:9')           # an explicit URL still wins
    client.request('GET', '/api/health')
    assert RecordingClient.seen == ['http://127.0.0.1:8000', 'http://127.0.0.1:18000', 'http://127.0.0.1:9']


class RefusingClient(RecordingClient):
    def request(self, method, path, json=None):
        raise httpx.ConnectError('connection refused', request=httpx.Request(method, 'http://127.0.0.1' + path))


@pytest.mark.parametrize('port,named', [(None, 'http://127.0.0.1:8000 (FAULTLAB_BACKEND_PORT unset, so the default port 8000)'),
                                        ('18000', 'http://127.0.0.1:18000 (FAULTLAB_BACKEND_PORT=18000)')])
def test_cli_names_the_address_it_tried_when_no_backend_answers(monkeypatch, capsys, no_port_settings, port, named):
    # Review: the old message named neither the address nor the setting, so a terminal without the setting failed
    # (or reached another checkout's backend on 8000) with no hint why.
    monkeypatch.setattr(client.httpx, 'Client', RefusingClient)
    if port: monkeypatch.setenv('FAULTLAB_BACKEND_PORT', port)
    monkeypatch.setattr(sys, 'argv', ['client', 'status', '--campaign', 'campaign-x'])
    assert client.main() == 1
    err = capsys.readouterr().err
    assert err == (f'No FaultLab backend answered at {named}. Start one with scripts/start-local.sh, or export '
                   'FAULTLAB_BACKEND_PORT to match the backend you started.\n')


@pytest.mark.parametrize('argv,changes', [(['stop', '--campaign', 'campaign-x'], True), (['status', '--campaign', 'campaign-x'], False),
                                          (['baseline-study', '--status', 'baseline-study-x'], False)])
def test_cli_says_which_backend_it_will_change_before_it_changes_anything(monkeypatch, capsys, no_port_settings, argv, changes):
    RecordingClient.seen = []
    monkeypatch.setattr(client.httpx, 'Client', RecordingClient)
    monkeypatch.setenv('FAULTLAB_BACKEND_PORT', '18000')
    monkeypatch.setattr(sys, 'argv', ['client', *argv])
    assert client.main() == 0
    err = capsys.readouterr().err
    assert err == ('Using the FaultLab backend at http://127.0.0.1:18000.\n' if changes else '')
    assert RecordingClient.seen == ['http://127.0.0.1:18000']


def test_cli_reports_a_bad_backend_port_without_a_request(monkeypatch, capsys):
    monkeypatch.setattr(client.httpx, 'Client', lambda **_: pytest.fail('no request may be sent'))
    monkeypatch.setenv('FAULTLAB_BACKEND_PORT', 'eight thousand')
    monkeypatch.setattr(sys, 'argv', ['client', 'status', '--campaign', 'campaign-x'])
    assert client.main() == 1
    assert 'FAULTLAB_BACKEND_PORT must be a whole port number' in capsys.readouterr().err


# ---------------------------------------------------------------- shell scripts, against stubs

STUB_PYTHON = '''#!/bin/bash
{ printf 'argv:'; printf ' %s' "$@"; printf '\\n'; printf 'cwd: %s\\n' "$PWD"
  printf 'FAULTLAB_SIMULATOR_URL=%s\\n' "${FAULTLAB_SIMULATOR_URL-<unset>}"; } >> "$STUB_LOG"
exit "${STUB_PYTHON_EXIT:-0}"
'''
# A backend stage that runs until Ctrl+C and then exits 2, as pytest does.
STUB_PYTHON_UNTIL_INTERRUPTED = '''#!/bin/bash
trap 'printf "pytest interrupted\\n" >> "$STUB_LOG"; exit 2' INT
printf 'pytest running\\n' >> "$STUB_LOG"
: > "$STUB_READY"
while :; do sleep 0.05; done
'''
STUB_NPM = '''#!/bin/bash
printf 'npm %s in %s\\n' "$*" "$(basename "$PWD")" >> "$STUB_LOG"
case "$*" in "run build") exit "${STUB_BUILD_EXIT:-0}" ;; esac
exit 0
'''


def _executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def stub_repo(tmp_path):
    """A scratch repository layout: the real scripts, a stub .venv interpreter and a stub npm on PATH."""
    repo = tmp_path / 'repo'
    for name in ('test.sh', 'start-simulator.sh', 'start-backend.sh', 'start-live-backend.sh', 'lib/ports.sh'):
        (repo / 'scripts' / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'scripts' / name, repo / 'scripts' / name)
    (repo / 'backend').mkdir()
    (repo / 'frontend').mkdir()
    _executable(repo / '.venv/bin/python', STUB_PYTHON)
    _executable(tmp_path / 'bin/npm', STUB_NPM)
    log = tmp_path / 'stub.log'
    environment = {key: value for key, value in os.environ.items()
                   if key not in (*PORT_NAMES, 'FAULTLAB_SIMULATOR_URL', 'FAULTLAB_LIVE_ENABLED',
                                  'FAULTLAB_CONFIRMED_ENTITY', 'WANDB_ENTITY')}
    environment.update(PATH=f'{tmp_path / "bin"}:/usr/bin:/bin', STUB_LOG=str(log))

    def run(script, *args, **extra):
        result = subprocess.run(['bash', str(repo / 'scripts' / script), *args], env={**environment, **extra},
                                capture_output=True, text=True, timeout=30)
        return result, (log.read_text() if log.exists() else '')
    run.repo = repo
    run.log = log
    run.environment = environment
    return run


# The argv each start script ran before ports became settings (checkpoint backup/part2-2026-09-22).
CHECKPOINT_ARGV = {
    'start-simulator.sh': 'argv: -m uvicorn app.simulator.main:app --host 127.0.0.1 --port 8001 --timeout-keep-alive 75',
    'start-backend.sh': 'argv: -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload',
    'start-live-backend.sh': 'argv: -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
}


@pytest.mark.parametrize('script', sorted(CHECKPOINT_ARGV))
def test_start_scripts_run_the_same_command_when_no_port_is_set(stub_repo, script):
    result, log = stub_repo(script)
    assert result.returncode == 0, result.stderr
    assert log.splitlines() == [CHECKPOINT_ARGV[script], f'cwd: {stub_repo.repo / "backend"}',
                                'FAULTLAB_SIMULATOR_URL=<unset>']


def test_start_scripts_use_the_port_settings(stub_repo):
    ports = {'FAULTLAB_SIMULATOR_PORT': '18001', 'FAULTLAB_BACKEND_PORT': '18000'}
    stub_repo('start-simulator.sh', **ports)
    stub_repo('start-backend.sh', **ports)
    _, log = stub_repo('start-live-backend.sh', **ports, FAULTLAB_SIMULATOR_URL='http://127.0.0.1:19001')
    lines = log.splitlines()
    assert lines[0].endswith('--port 18001 --timeout-keep-alive 75')
    assert lines[3].endswith('--port 18000 --reload') and lines[5] == 'FAULTLAB_SIMULATOR_URL=http://127.0.0.1:18001'
    # An explicit simulator URL in the process environment still wins.
    assert lines[6].endswith('--port 18000') and lines[8] == 'FAULTLAB_SIMULATOR_URL=http://127.0.0.1:19001'


@pytest.mark.parametrize('script,name', [('start-simulator.sh', 'FAULTLAB_SIMULATOR_PORT'),
                                         ('start-backend.sh', 'FAULTLAB_BACKEND_PORT'),
                                         ('start-backend.sh', 'FAULTLAB_SIMULATOR_PORT'),
                                         ('start-live-backend.sh', 'FAULTLAB_BACKEND_PORT')])
@pytest.mark.parametrize('value', ['0', '65536', '08000', 'abc', '-1'])
def test_start_scripts_refuse_a_bad_port_before_starting(stub_repo, script, name, value):
    result, log = stub_repo(script, **{name: value})
    assert result.returncode == 2 and log == ''
    assert f'{name} must be a whole port number from 1 to 65535' in result.stderr


def test_test_script_runs_every_stage_and_fails_if_any_failed(stub_repo):
    result, log = stub_repo('test.sh', STUB_PYTHON_EXIT='1', STUB_BUILD_EXIT='3')
    assert result.returncode == 1
    assert [line.split()[0] if line.startswith('argv') else line for line in log.splitlines()
            if not line.startswith(('cwd', 'FAULTLAB'))] == [
        'argv:', 'npm test in frontend', 'npm run build in frontend', 'npm run test:browser in frontend']
    assert 'argv: -m pytest' in log
    summary = result.stdout.split('Offline check summary:\n', 1)[1]
    lines = [line.split(' (')[0].split() for line in summary.splitlines() if line.startswith('  ')]
    assert lines == [['FAILED', 'backend'], ['PASSED', 'frontend'], ['FAILED', 'build'], ['PASSED', 'browser']]
    assert '(exit 1,' in summary and '(exit 3,' in summary


def test_test_script_passes_when_every_stage_passes_and_runs_named_stages_only(stub_repo):
    result, log = stub_repo('test.sh')
    assert result.returncode == 0 and 'At least one stage failed' not in result.stdout
    assert result.stdout.count('PASSED') == 4
    stub_repo.log.unlink()
    result, log = stub_repo('test.sh', 'build', 'browser')
    assert result.returncode == 0
    assert log.splitlines() == ['npm run build in frontend', 'npm run test:browser in frontend']
    result, _ = stub_repo('test.sh', 'backend', 'lint')
    assert result.returncode == 2 and 'Unknown stage lint' in result.stderr


def test_test_script_stops_at_once_on_ctrl_c(stub_repo, tmp_path):
    # Review: without set -e, a Ctrl+C that pytest turns into exit 2 let the frontend, build and browser stages run
    # (the browser stage starts its own dashboard). Ctrl+C sends SIGINT to the whole foreground process group.
    _executable(stub_repo.repo / '.venv/bin/python', STUB_PYTHON_UNTIL_INTERRUPTED)
    ready = tmp_path / 'backend-stage-running'
    process = subprocess.Popen(['bash', str(stub_repo.repo / 'scripts' / 'test.sh')], env={**stub_repo.environment, 'STUB_READY': str(ready)},
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while not ready.exists():
            assert process.poll() is None and time.monotonic() < deadline, 'the backend stage did not start'
            time.sleep(0.02)
        os.killpg(process.pid, signal.SIGINT)
        out, err = process.communicate(timeout=20)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL); process.communicate()
    assert process.returncode == 130
    assert err.endswith('Interrupted; later stages not run.\n')
    assert stub_repo.log.read_text() == 'pytest running\npytest interrupted\n'   # no npm stage started
    assert 'Offline check summary' not in out
