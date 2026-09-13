"""Offline integrated reference; fixture provenance never passes remote acceptance."""
import time
from fastapi.testclient import TestClient
import pytest
from app.config import Settings
from app.main import create_app

pytestmark=pytest.mark.localhost_http


def wait_campaign(client,id):
    deadline=time.monotonic()+6
    while time.monotonic()<deadline:
        data=client.get(f'/api/campaigns/{id}').json()
        if data.get('state') in ('COMPLETED','ERROR','STOPPED','NO_CHANGE'):return data
        time.sleep(.02)
    pytest.fail('offline campaign did not complete')


def test_fresh_reference_real_http_and_read_only_history(tmp_path,simulator_server):
    url,world_app=simulator_server
    settings=Settings(faultlab_artifact_dir=str(tmp_path/'lab'),faultlab_simulator_url=url,faultlab_control_token='integration-control')
    with TestClient(create_app(settings=settings)) as client:
        response=client.post('/api/campaigns',json={'mode':'baseline','task_text':'Upgrade to express and confirm truthfully.','order_id':'order-integration','config_profile_id':'offline-v1'})
        assert response.status_code==201,response.text
        id=response.json()['campaign_id']
        assert response.json()['state']=='IDLE'
        assert not list((tmp_path/'worlds').glob('*.sqlite3'))
        assert client.post(f'/api/campaigns/{id}/start',json={}).status_code==202
        campaign=wait_campaign(client,id)
        assert campaign['state']=='COMPLETED',campaign
        episode_id=campaign['latest_episode_id']
        episode=client.get(f'/api/episodes/{episode_id}').json()
        assert episode['lifecycle']=='COMPLETED',episode
        assert episode['arm']=='B1' and episode['source_mode']=='offline_fixture'
        assert episode['verdict']['outcome']=='COMPLETED',episode
        assert episode['report']['upgrade_outcome']==episode['report']['notification_outcome']=='SUCCEEDED'
        assert episode['usage']['model_calls']==0
        snapshot=world_app.state.store.snapshot(episode['world_id']).model_dump(mode='json')
        for _ in range(3):
            assert client.get(f'/api/episodes/{episode_id}').status_code==200
            assert client.get(f'/api/episodes/{episode_id}/events?after=0').status_code==200
            assert client.get(f'/api/campaigns/{id}/matrix').status_code==200
        assert world_app.state.store.snapshot(episode['world_id']).model_dump(mode='json')==snapshot
        assert campaign['telemetry_status']=='local_recorded'
        assert client.post(f'/api/campaigns/{id}/retry-evidence',json={}).status_code==202
        assert len(list(world_app.state.store.directory.glob('*.sqlite3')))==1


def test_live_start_is_blocked_before_world_or_provider_call(tmp_path,simulator_server):
    url,world_app=simulator_server
    with TestClient(create_app(settings=Settings(faultlab_artifact_dir=str(tmp_path/'lab'),faultlab_simulator_url=url))) as client:
        data=client.post('/api/campaigns',json={'mode':'baseline','task_text':'Test','order_id':'order-one','config_profile_id':'live-v1'}).json()
        response=client.post(f'/api/campaigns/{data["campaign_id"]}/start',json={})
        assert response.status_code==503,response.text
        assert list(world_app.state.store.directory.glob('*.sqlite3'))==[]
