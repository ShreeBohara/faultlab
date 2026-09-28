"""Operator CLIs cannot bypass the backend owner or mutate saved-only reads."""
import asyncio
from dataclasses import replace
import hashlib
import errno
import json
from pathlib import Path
import subprocess
import sys

import pytest
import httpx

from app.cli import freeze, regressions, sponsors, stores, studies
from app.config import Settings
from app.integrations.registry import AgentRegistry
from app.lab.coordinator import LabCoordinator
from app.lab.ownership import CoordinatorLease, StoreInUse
from app.lab.storage import ReadOnlyStore
from test_regression_execution import build_bundle


@pytest.fixture
def fixture_store(tmp_path):
    settings = Settings(faultlab_artifact_dir=str(tmp_path / 'lab'), wandb_model='deepseek-ai/DeepSeek-V3.1')
    owner = LabCoordinator(settings)
    directory = tmp_path / 'bundle'
    campaign, bundle = build_bundle(owner, directory)
    try:
        yield settings, owner, directory, campaign, bundle
    finally:
        asyncio.run(owner.close())


def snapshot(store):
    return list(store.db.execute('SELECT kind,id,payload,immutable FROM records ORDER BY rowid')), list(store.db.execute('SELECT * FROM pointers'))


def test_owner_blocks_before_cli_opens_sqlite(tmp_path, monkeypatch):
    path = tmp_path / 'lab.sqlite3'
    with CoordinatorLease.acquire(path):
        monkeypatch.setattr(stores, 'LabStore', lambda *_: pytest.fail('Blocked CLI opened SQLite'))
        with pytest.raises(StoreInUse):
            with stores.owned_store(path):
                pytest.fail('Blocked CLI admitted')
    assert not path.exists()


@pytest.mark.parametrize('failure', ['constructor', 'body', 'close'])
def test_cli_lease_is_released_after_every_failure(tmp_path, monkeypatch, failure):
    path = tmp_path / 'lab.sqlite3'
    if failure == 'constructor':
        def fail(*_): raise RuntimeError('constructor failed')
        monkeypatch.setattr(stores, 'LabStore', fail)
    with pytest.raises(RuntimeError):
        with stores.owned_store(path) as store:
            if failure == 'close':
                store.on_close(lambda: (_ for _ in ()).throw(RuntimeError('close failed')))
            else:
                raise RuntimeError('body failed')
    with CoordinatorLease.acquire(path):
        pass


def test_explicit_store_close_releases_cli_lease(tmp_path):
    path = tmp_path / 'lab.sqlite3'
    with stores.owned_store(path) as store:
        store.close()
        with CoordinatorLease.acquire(path):
            pass


def test_archive_write_denied_without_creating_parent_or_lease(tmp_path):
    settings = Settings(faultlab_artifact_dir=str(tmp_path / 'missing'), faultlab_read_only=True)
    with pytest.raises(ReadOnlyStore):
        with stores.writable_store(settings): pass
    assert not (tmp_path / 'missing').exists()


@pytest.mark.parametrize('module,args', [
    ('regressions', ['register', '--agent', 'reference']),
    ('regressions', ['export', '--counterexample', 'missing', '--output', 'unused']),
    ('freeze', ['--campaign', 'missing']),
])
def test_real_cli_subprocess_cannot_write_backend_store(fixture_store, module, args):
    settings, owner, *_ = fixture_store
    before = snapshot(owner.store)
    source = '''
import sys
from app.config import Settings
Settings.from_env = classmethod(lambda cls: Settings(faultlab_artifact_dir=sys.argv[1]))
module = __import__('app.cli.' + sys.argv[2], fromlist=['main'])
# Select a deliberately absent loopback listener; never contact a user's backend.
import socket
from app.cli import client
with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0))
    client.BASE_URL = 'http://127.0.0.1:' + str(probe.getsockname()[1])
sys.argv = [sys.argv[2], *sys.argv[3:]]
raise SystemExit(module.main())
'''
    # Freeze Settings before argv is replaced; no real .env is read by the child.
    source = source.replace("Settings.from_env =", "directory = sys.argv[1]\nSettings.from_env =").replace('faultlab_artifact_dir=sys.argv[1]', 'faultlab_artifact_dir=directory')
    result = subprocess.run([sys.executable, '-c', source, str(settings.artifact_path), module, *args],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert 'owns this store' in result.stdout + result.stderr
    assert snapshot(owner.store) == before


def test_sponsor_registration_is_also_leased(fixture_store, tmp_path, monkeypatch, capsys):
    settings, owner, *_ = fixture_store
    settings = replace(settings, wandb_entity='test-team', wandb_project='test-project')
    from app.telemetry.aria_bridge import ARIA_PROMPT, RUN_NAME_FILTER
    record = {'project': settings.project_path, 'automation_id': 'actual-observation',
              'team_confirmed': True, 'smart_features_enabled': True, 'ask_aria_observed': True,
              'event': 'Finished', 'run_name_filter': RUN_NAME_FILTER, 'action': 'Trigger ARIA',
              'prompt': ARIA_PROMPT, 'configuration_url': 'https://wandb.ai/test-team/test-project',
              'recorder': 'test', 'observed_at': '2026-09-27T00:00:00Z'}
    path = tmp_path / 'observed.json'; path.write_text(json.dumps(record))
    monkeypatch.setattr(Settings, 'from_env', lambda: settings)
    monkeypatch.setattr(sys, 'argv', ['sponsors', 'register-automation', '--record', str(path)])
    before = snapshot(owner.store)
    with pytest.raises(SystemExit) as caught: sponsors.main()
    assert caught.value.code == 2 and 'owns this store' in capsys.readouterr().err
    assert snapshot(owner.store) == before


@pytest.mark.parametrize('registered', [False, True])
def test_validate_playback_and_saved_export_are_read_only_while_backend_owns(fixture_store, tmp_path, monkeypatch, capsys, registered):
    settings, owner, directory, campaign, _ = fixture_store
    registration = AgentRegistry(owner.store).register_reference(
        owner.store.get_record('configurations', campaign.configuration_hash), internal_smoke=True)
    before = snapshot(owner.store)
    monkeypatch.setattr(Settings, 'from_env', lambda: replace(settings, faultlab_read_only=True))
    for command in ('validate', 'playback'):
        args = ['regressions', command, '--bundle', str(directory)]
        if registered: args += ['--agent', registration.registration_id]
        monkeypatch.setattr(sys, 'argv', args)
        assert regressions.main() == 0
        value = json.loads(capsys.readouterr().out)
        assert value.get('execution', value)['usage']['model_calls'] == 0
    regression = owner.store.list_records('regressions')[0]
    output = tmp_path / 'exported'
    monkeypatch.setattr(sys, 'argv', ['regressions', 'export', '--regression', regression['regression_id'], '--output', str(output)])
    assert regressions.main() == 0
    assert json.loads(capsys.readouterr().out)['execution_performed'] is False
    assert (output / 'manifest.json').is_file()
    assert snapshot(owner.store) == before


def test_validate_without_registration_does_not_create_store(fixture_store, tmp_path, monkeypatch, capsys):
    _, _, directory, *_ = fixture_store
    settings = Settings(faultlab_artifact_dir=str(tmp_path / 'absent'))
    monkeypatch.setattr(Settings, 'from_env', lambda: settings)
    monkeypatch.setattr(sys, 'argv', ['regressions', 'validate', '--bundle', str(directory)])
    assert regressions.main() == 0
    assert not settings.artifact_path.exists()


def test_closed_archive_reads_leave_database_hash_unchanged(fixture_store, monkeypatch, capsys):
    settings, owner, directory, campaign, _ = fixture_store
    registration = AgentRegistry(owner.store).register_reference(
        owner.store.get_record('configurations', campaign.configuration_hash), internal_smoke=True)
    owner.store.close()
    path = settings.artifact_path / 'lab.sqlite3'
    before = hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
    monkeypatch.setattr(Settings, 'from_env', lambda: replace(settings, faultlab_read_only=True))
    monkeypatch.setattr(sys, 'argv', ['regressions', 'playback', '--bundle', str(directory), '--agent', registration.registration_id])
    assert regressions.main() == 0
    assert (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) == before


def test_execute_and_portability_only_send_expected_store_to_owner(fixture_store, monkeypatch, capsys):
    settings, owner, directory, campaign, _ = fixture_store
    monkeypatch.setattr(Settings, 'from_env', lambda: settings)
    calls = []
    def send(method, route, body):
        assert method == 'POST'
        assert body['expected_store_identity'] == owner.config_status()['data_store']['identity']
        calls.append(route)
        return {'status': 'QUEUED'}
    monkeypatch.setattr(regressions, 'request', send)
    monkeypatch.setattr(studies, 'request', send)
    monkeypatch.setattr(stores, 'LabStore', lambda *_: pytest.fail('HTTP path opened writable SQLite'))
    monkeypatch.setattr(stores, 'ReadOnlyLabStore', lambda *_: pytest.fail('HTTP path opened local SQLite'))
    before = snapshot(owner.store)
    monkeypatch.setattr(sys, 'argv', ['regressions', 'execute', '--bundle', str(directory), '--agent', 'registered-agent', '--profile', 'sandbox-v1', '--execute-live'])
    assert regressions.main() == 0
    monkeypatch.setattr(sys, 'argv', ['studies', 'portability', '--campaign', campaign.campaign_id, '--agent', 'registered-agent', '--execute-live'])
    assert studies.main() == 0
    assert calls == ['/api/regressions/import-and-execute', f'/api/campaigns/{campaign.campaign_id}/freeze-and-portability']
    assert snapshot(owner.store) == before


def test_registration_uses_running_backend_without_local_store(fixture_store, monkeypatch):
    settings, owner, *_ = fixture_store
    def send(method, route, body):
        assert method == 'POST' and route == '/api/agent-registrations'
        assert body == {'expected_store_identity': owner.config_status()['data_store']['identity'], 'agent': 'reference'}
        return {'registration_id': 'backend-owned'}
    monkeypatch.setattr(regressions, 'request', send)
    monkeypatch.setattr(stores, 'LabStore', lambda *_: pytest.fail('Remote registration opened SQLite'))
    assert regressions.register_remote_or_offline(settings, 'reference') == {'registration_id': 'backend-owned'}


@pytest.mark.parametrize('failure', ['http', 'timeout', 'reset', 'ambiguous_connect'])
def test_registration_never_falls_back_after_backend_or_transport_failure(tmp_path, monkeypatch, failure):
    settings = Settings(faultlab_artifact_dir=str(tmp_path / 'absent'))
    def fail(*_):
        if failure == 'http': raise RuntimeError('HTTP 409: configured store differs')
        if failure == 'timeout': raise httpx.ReadTimeout('No response')
        if failure == 'reset':
            try: raise ConnectionResetError(errno.ECONNRESET, 'Reset')
            except OSError as error: raise httpx.ConnectError('Reset') from error
        raise httpx.ConnectError('Unknown transport failure')
    monkeypatch.setattr(regressions, 'request', fail)
    monkeypatch.setattr(stores, 'LabStore', lambda *_: pytest.fail('Failed remote request opened SQLite'))
    with pytest.raises((RuntimeError, httpx.HTTPError)):
        regressions.register_remote_or_offline(settings, 'reference')
    assert not settings.artifact_path.exists()


def test_registration_falls_back_only_for_actual_refusal_and_releases_lease(tmp_path, monkeypatch):
    settings = Settings(faultlab_artifact_dir=str(tmp_path / 'offline'))
    def refused(*_):
        try: raise ConnectionRefusedError(errno.ECONNREFUSED, 'Refused')
        except OSError as error: raise httpx.ConnectError('Refused') from error
    monkeypatch.setattr(regressions, 'request', refused)
    result = regressions.register_remote_or_offline(settings, 'reference')
    with CoordinatorLease.acquire(settings.artifact_path / 'lab.sqlite3'):
        with stores.saved_store(settings) as reader:
            assert reader.get_record('agent_registrations', result['registration_id']) == result
