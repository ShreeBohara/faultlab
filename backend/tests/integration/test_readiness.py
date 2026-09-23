import asyncio
import json
import socket
from unittest.mock import patch
import pytest

from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts.models import CampaignRequest
from app.lab.coordinator import LabCoordinator
from app.lab.readiness import execution_failure
from app.main import create_app
from app.providers.runtime import RuntimeProvider


def request_body():
    return {'task_text': 'Upgrade and confirm', 'order_id': 'order-ready',
            'mode': 'baseline', 'config_profile_id': 'offline-v1'}


@pytest.mark.localhost_http
def test_readiness_checks_control_without_provider_calls_or_world_creation(tmp_path, simulator_server):
    url, _ = simulator_server
    settings = Settings(faultlab_artifact_dir=str(tmp_path/'lab'),
                        faultlab_simulator_url=url, faultlab_control_token='integration-control')
    with patch.object(RuntimeProvider, 'complete', side_effect=AssertionError('Unexpected provider call')):
        with TestClient(create_app(settings=settings)) as client:
            result = client.get('/api/readiness')
            assert result.status_code == 200
            value = result.json()
            assert value['ready'] and value['simulator']['code'] == 'READY'
            assert value['provider_calls'] == 0 and value['provider_access'] == 'not_checked'
            assert not value['live_configuration']['ready']
    assert not list((tmp_path/'worlds').glob('*.sqlite3'))


@pytest.mark.localhost_http
def test_bad_control_access_prevents_start_and_budget_reservation(tmp_path, simulator_server):
    url, _ = simulator_server
    coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),
        faultlab_simulator_url=url, faultlab_control_token='wrong-secret-control'))
    with TestClient(create_app(coordinator=coordinator)) as client:
        readiness = client.get('/api/readiness').json()
        assert not readiness['ready']
        assert readiness['simulator']['code'] == 'SIMULATOR_CONTROL_DENIED'
        campaign = client.post('/api/campaigns', json=request_body()).json()
        response = client.post(f'/api/campaigns/{campaign["campaign_id"]}/start', json={})
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'SERVICE_NOT_READY'
        assert 'wrong-secret-control' not in response.text
        assert coordinator.get(campaign['campaign_id']).state == 'IDLE'
        assert coordinator.store.get_record('budgets', campaign['campaign_id']) is None
        assert coordinator.active_id is None


@pytest.mark.localhost_http
def test_unavailable_simulator_is_explained_before_execution(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        url = f'http://127.0.0.1:{listener.getsockname()[1]}'
        settings = Settings(faultlab_artifact_dir=str(tmp_path), faultlab_simulator_url=url,
                            faultlab_control_token='test-control')
        with TestClient(create_app(settings=settings)) as client:
            value = client.get('/api/readiness').json()
            assert value['simulator']['code'] == 'SIMULATOR_UNAVAILABLE'
            assert value['provider_calls'] == 0


def test_execution_error_records_safe_cause_without_raw_exception_text(tmp_path):
    class BrokenRunner:
        async def run(self, *args, **kwargs):
            raise ValueError('Authorization Bearer secret-value private URL database dump')

    async def run():
        c = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)), runner=BrokenRunner())
        campaign = c.create(CampaignRequest(**request_body()))
        await c.start(campaign.campaign_id)
        await c.tasks[campaign.campaign_id]
        result = c.get(campaign.campaign_id)
        error = c.store.get_record('execution_errors', campaign.campaign_id)
        assert result.state == 'ERROR'
        assert error['error_class'] == 'ValueError'
        assert error['locations']
        assert 'secret-value' not in json.dumps(error)
        assert 'secret-value' not in result.terminal_reason
        assert c.active_id is None
        await c.close()
    asyncio.run(run())


def test_safe_error_metadata_never_serializes_sdk_response():
    import httpx
    request = httpx.Request('GET', 'http://127.0.0.1/private?api_key=secret')
    response = httpx.Response(403, request=request, text='secret raw body')
    error = httpx.HTTPStatusError('secret', request=request, response=response)
    result = execution_failure(error)
    assert result['http_status'] == 403
    assert result['code'] == 'LOCAL_HTTP_ERROR'
    assert 'secret' not in json.dumps(result)


def test_inference_only_execution_does_not_dispatch_existing_aria_automation(tmp_path):
    class Bridge:
        async def publish_campaign(self, *args, **kwargs):
            raise AssertionError('Aria must remain outside this bounded experiment')
    async def run():
        c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path), faultlab_aria_publish_enabled=False))
        campaign=c.create(CampaignRequest(**request_body()))
        c.store.put_record('aria_setup',c.settings.project_path,{'automation_id':'existing-automation'})
        result=await c._publish_completion(campaign.campaign_id,bridge=Bridge())
        assert result['state']=='publication_disabled'
        assert c.get(campaign.campaign_id).aria_status=='PENDING'
        assert c.store.list_records('aria_publish_intents')==[]
        assert c.store.get_record('campaign_provenance',campaign.campaign_id)['aria_publication_enabled'] is False
        await c.close()
    asyncio.run(run())
