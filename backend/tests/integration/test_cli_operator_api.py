"""Bounded CLI uploads are validated before the owning backend admits work."""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.cli.regressions import current_configuration
from app.integrations.registry import AgentRegistry
from app.lab import operator_actions
from app.lab.ownership import CoordinatorLease, StoreInUse
from app.main import create_app
from test_cli_store_ownership import fixture_store, snapshot


def upload(owner, directory, campaign):
    manifest = json.loads((directory / 'manifest.json').read_text())
    registration = AgentRegistry(owner.store).register_reference(
        current_configuration(owner.settings), internal_smoke=True)
    return {'expected_store_identity': owner.config_status()['data_store']['identity'],
            'manifest': (directory / 'manifest.json').read_text(),
            'files': {entry['path']: (directory / entry['path']).read_text() for entry in manifest['files']},
            'agent_registration_id': registration.registration_id,
            'execution_profile_id': 'sandbox-v1', 'execute_live': True}


@pytest.mark.parametrize('mutation,code', [
    ('store', 409), ('extra_file', 422), ('oversize_file', 422), ('oversize_total', 422),
    ('manifest', 422), ('tampered', 422), ('no_live', 422), ('registration', 422),
])
def test_bad_import_never_creates_campaign_or_import(fixture_store, monkeypatch, mutation, code):
    _, owner, directory, campaign, _ = fixture_store
    body = upload(owner, directory, campaign)
    before = snapshot(owner.store)
    monkeypatch.setattr(Settings, 'require_live', lambda *_: None)
    if mutation == 'store': body['expected_store_identity'] = '0' * 64
    if mutation == 'extra_file': body['files']['../../PRIVATE'] = 'no'
    if mutation == 'oversize_file': body['files']['policy.json'] = 'x' * (operator_actions.MAX_BUNDLE_FILE + 1)
    if mutation == 'oversize_total':
        for name in ('policy.json', 'configuration.json', 'trials.json'):
            body['files'][name] = 'x' * (6 * 1024 * 1024)
    if mutation == 'manifest': body['manifest'] = '{"PRIVATE_CANARY":"invalid"}'
    if mutation == 'tampered': body['files']['policy.json'] += 'PRIVATE_CANARY'
    if mutation == 'no_live': body['execute_live'] = False
    if mutation == 'registration': body['agent_registration_id'] = 'PRIVATE_CANARY'
    with TestClient(create_app(coordinator=owner)) as client:
        response = client.post('/api/regressions/import-and-execute', json=body)
        assert response.status_code == code, response.text
        assert 'PRIVATE_CANARY' not in response.text
        assert snapshot(owner.store) == before
        assert owner.active_id is None


def test_upload_transport_bound_and_duplicate_keys_rejected(fixture_store):
    _, owner, directory, campaign, _ = fixture_store
    body = upload(owner, directory, campaign)
    before = snapshot(owner.store)
    with TestClient(create_app(coordinator=owner)) as client:
        response = client.post('/api/regressions/import-and-execute', content='{}',
            headers={'content-length': str(operator_actions.MAX_UPLOAD_BYTES + 1)})
        assert response.status_code == 422
        raw = json.dumps(body)
        response = client.post('/api/regressions/import-and-execute', content=raw[:-1] + ',"execute_live":true}')
        assert response.status_code == 422
        assert snapshot(owner.store) == before


def test_chunked_body_is_bounded_before_decoding(monkeypatch):
    monkeypatch.setattr(operator_actions, 'MAX_UPLOAD_BYTES', 12)
    chunks = []
    class Request:
        headers = {}
        async def stream(self):
            for chunk in (b'x' * 8, b'x' * 8, b'never consumed'):
                chunks.append(chunk)
                yield chunk
    with pytest.raises(ValueError, match='transport bound'):
        asyncio.run(operator_actions.read_import_request(Request()))
    assert len(chunks) == 2


def test_full_upload_imports_under_owner_and_queues_exact_policy(fixture_store, monkeypatch):
    _, owner, directory, campaign, bundle = fixture_store
    body = upload(owner, directory, campaign)
    monkeypatch.setattr(Settings, 'require_live', lambda *_: None)
    calls = []
    async def queue(coordinator, regression_id, request):
        with pytest.raises(StoreInUse):
            CoordinatorLease.acquire(coordinator.store.path)
        case = coordinator.store.get_record('regressions', regression_id)
        calls.append((case, request))
        assert case['bundle_id'] == bundle.bundle_id
        assert case['campaign_id'] != campaign.campaign_id
        assert coordinator.get(case['campaign_id']).active_policy_version == 'policy-v0'
        assert request.policy_version == 'policy-v0' and request.execute_live is True
        return {'status': 'PENDING', 'regression_id': regression_id}
    monkeypatch.setattr('app.lab.regression_executions.execute_regression', queue)
    with TestClient(create_app(coordinator=owner)) as client:
        response = client.post('/api/regressions/import-and-execute', json=body)
        assert response.status_code == 202, response.text
        assert len(calls) == 1
        assert owner.store.get_record('bundle_imports', bundle.bundle_id)['source_evidence_verified_locally'] is False
        assert owner.store.get_record('bundle_files', bundle.bundle_id) == body['files']
        assert owner.store.list_records('episodes') == []


def test_store_mismatch_precedes_live_settings_and_registration(fixture_store, monkeypatch):
    _, owner, directory, campaign, _ = fixture_store
    body = upload(owner, directory, campaign)
    body['expected_store_identity'] = '0' * 64
    monkeypatch.setattr(Settings, 'require_live', lambda *_: pytest.fail('Mismatch reached admission'))
    with TestClient(create_app(coordinator=owner)) as client:
        assert client.post('/api/regressions/import-and-execute', json=body).status_code == 409
        port = {key: body[key] for key in ('expected_store_identity', 'agent_registration_id', 'execute_live')}
        assert client.post(f'/api/campaigns/{campaign.campaign_id}/freeze-and-portability', json=port).status_code == 409


def test_archive_rejects_both_remote_operator_actions(fixture_store):
    settings, owner, directory, campaign, _ = fixture_store
    body = upload(owner, directory, campaign)
    before = snapshot(owner.store)
    with TestClient(create_app(settings=replace(settings, faultlab_read_only=True))) as client:
        response = client.post('/api/regressions/import-and-execute', json=body)
        assert response.status_code == 409 and response.json()['error']['code'] == 'READ_ONLY_ARCHIVE'
        port = {key: body[key] for key in ('expected_store_identity', 'agent_registration_id', 'execute_live')}
        assert client.post(f'/api/campaigns/{campaign.campaign_id}/freeze-and-portability', json=port).status_code == 409
        assert snapshot(owner.store) == before


def test_portability_freeze_is_owned_then_queue_has_saved_record(fixture_store, monkeypatch):
    settings, owner, directory, campaign, _ = fixture_store
    body = upload(owner, directory, campaign)
    target = operator_actions.register_agent(owner.store, settings, 'smolagents')
    body['agent_registration_id'] = target.registration_id
    port = {key: body[key] for key in ('expected_store_identity', 'agent_registration_id', 'execute_live')}
    owner.store.put_record('audit_freezes', campaign.campaign_id, {
        'learned_arm_available': True,
        'path': str(settings.artifact_path / 'campaigns' / campaign.campaign_id / 'audit' / 'freeze.json')})
    monkeypatch.setattr(Settings, 'require_live', lambda *_: None)
    observed = []
    def freeze(directory, registration):
        with pytest.raises(StoreInUse): CoordinatorLease.acquire(owner.store.path)
        observed.append('freeze')
        return {'registration': {'registration_id': registration.registration_id}, 'freeze_hash': 'a' * 64}
    async def queue(coordinator, ident, request):
        assert coordinator.store.get_record('external_freezes', ident)['freeze_hash'] == 'a' * 64
        observed.append('queue')
        return {'status': 'QUEUED'}
    monkeypatch.setattr('app.referee.freeze.freeze_external', freeze)
    monkeypatch.setattr('app.lab.portability.queue_portability', queue)
    with TestClient(create_app(coordinator=owner)) as client:
        route = f'/api/campaigns/{campaign.campaign_id}/freeze-and-portability'
        assert client.post(route, json=port).status_code == 202
        assert client.post(route, json=port).status_code == 202
        assert observed == ['freeze', 'queue', 'queue']


def test_matrix_keeps_full_coverage_counts_and_separates_partial_from_none(fixture_store):
    _, owner, _, campaign, _ = fixture_store
    for index, triggers in enumerate(([], [True], [False], [True, False])):
        owner.store.put_record('episodes', f'projection-{index}', {
            'episode_id': f'projection-{index}', 'campaign_id': campaign.campaign_id,
            'experiment_purpose': 'discovery', 'study_id': campaign.campaign_id,
            'scenario_hash': str(index) * 64, 'arm': 'B0', 'policy_hash': 'a' * 64,
            'lifecycle': 'COMPLETED', 'source_mode': 'offline_fixture', 'usage': {},
            'verdict': {'outcome': 'COMPLETED', 'fault_executions': [{'triggered': value} for value in triggers]}})
    with TestClient(create_app(coordinator=owner)) as client:
        result = client.get(f'/api/campaigns/{campaign.campaign_id}/matrix').json()
        assert result['counts']['triggered'] == 1
        assert result['counts']['untriggered'] == 2
        assert result['counts']['partially_triggered'] == 1
        assert result['counts']['none_triggered'] == 1
        assert [(row['fault_count'], row['triggered_fault_count']) for row in result['cells']] == [(0, 0), (1, 1), (1, 0), (2, 1)]


def test_backend_registration_is_server_authoritative_and_read_only_safe(fixture_store):
    settings, owner, *_ = fixture_store
    body = {'expected_store_identity': owner.config_status()['data_store']['identity'], 'agent': 'reference'}
    with TestClient(create_app(settings=replace(settings, faultlab_read_only=True))) as archive:
        response = archive.post('/api/agent-registrations', json=body)
        assert response.status_code == 409 and response.json()['error']['code'] == 'READ_ONLY_ARCHIVE'
    with TestClient(create_app(coordinator=owner)) as client:
        before = snapshot(owner.store)
        for invalid in ({**body, 'expected_store_identity': '0' * 64}, {**body, 'agent': 'arbitrary-code'},
                        {**body, 'settings': {'wandb_model': 'PRIVATE_CANARY'}}, {**body, 'model': 'PRIVATE_CANARY'}):
            response = client.post('/api/agent-registrations', json=invalid)
            assert response.status_code in (409, 422)
            assert 'PRIVATE_CANARY' not in response.text
            assert snapshot(owner.store) == before
        response = client.post('/api/agent-registrations', json=body)
        assert response.status_code == 201, response.text
        registration = response.json()
        assert registration['model'] == settings.wandb_model
        assert owner.store.get_record('agent_registrations', registration['registration_id']) == registration
        assert owner.store.list_records('episodes') == []


def test_registration_rejects_an_active_execution_before_writing(fixture_store):
    _, owner, _, campaign, _ = fixture_store
    owner.active_id = campaign.campaign_id
    body = {'expected_store_identity': owner.config_status()['data_store']['identity'], 'agent': 'reference'}
    with TestClient(create_app(coordinator=owner)) as client:
        before = snapshot(owner.store)
        response = client.post('/api/agent-registrations', json=body)
        assert response.status_code == 409
        assert snapshot(owner.store) == before
        owner.active_id = None
