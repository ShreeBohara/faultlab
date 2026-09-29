"""Native adapter v2 registers through the same API and CLI paths as v1, chosen explicitly; offline, no provider."""
import sys

from fastapi.testclient import TestClient
import pytest

from app.cli import regressions
from app.main import create_app
from test_cli_store_ownership import fixture_store, snapshot  # noqa: F401  (fixture_store is a fixture)


def test_api_registers_v2_only_when_chosen_and_keeps_v1_separate(fixture_store):
    settings, owner, *_ = fixture_store
    identity = owner.config_status()['data_store']['identity']
    with TestClient(create_app(coordinator=owner)) as client:
        before = snapshot(owner.store)
        response = client.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents-v3'})
        assert response.status_code == 422 and snapshot(owner.store) == before
        v2 = client.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents-v2'})
        v1 = client.post('/api/agent-registrations', json={'expected_store_identity': identity, 'agent': 'smolagents'})
        assert v2.status_code == v1.status_code == 201, (v2.text, v1.text)
        v2, v1 = v2.json(), v1.json()
        assert v2['adapter_entrypoint_id'] == 'smolagents-toolcalling-v2' and v1['adapter_entrypoint_id'] == 'smolagents-toolcalling-v1'
        assert v2['registration_id'] != v1['registration_id'] and v2['configuration_hash'] != v1['configuration_hash']
        assert v2['model'] == v1['model'] == settings.wandb_model
        listed = {row['registration_id']: row for row in client.get('/api/agent-registrations').json()}
        assert listed[v2['registration_id']] == v2 and listed[v1['registration_id']] == v1
        assert owner.store.list_records('episodes') == []


@pytest.mark.parametrize('agent', ['reference', 'smolagents', 'smolagents-v2'])
def test_cli_register_accepts_the_explicit_adapter_choice(monkeypatch, capsys, agent):
    seen = []
    monkeypatch.setattr(regressions.Settings, 'from_env', classmethod(lambda cls, **_: object()))
    monkeypatch.setattr(regressions, 'register_remote_or_offline', lambda settings, chosen: seen.append(chosen) or {'agent': chosen})
    monkeypatch.setattr(sys, 'argv', ['regressions', 'register', '--agent', agent])
    assert regressions.main() == 0 and seen == [agent]


def test_cli_register_refuses_an_unknown_adapter(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['regressions', 'register', '--agent', 'smolagents-v3'])
    with pytest.raises(SystemExit):
        regressions.main()
