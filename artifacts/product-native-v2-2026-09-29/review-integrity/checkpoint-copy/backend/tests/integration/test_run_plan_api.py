"""Setup reads cannot acquire ownership; creation and execution remain separate."""
import asyncio
from dataclasses import replace
import hashlib
import threading
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.contracts.models import CampaignRequest
from app.lab.coordinator import LabCoordinator
from app.main import create_app


def request_for(options):
    return {
        'expected_store_identity': options['data_store']['identity'],
        'expected_setup_hash': options['setup_hash'],
        'task_definition_id': 'orders.upgrade_then_confirm/v1',
        'mode': 'baseline', 'config_profile_id': 'offline-v1',
        'task_text': 'Upgrade the authorized order, then confirm truthfully.',
        'order_id': 'order-planned-api', 'development_case_id': 'dev-1',
    }


def test_setup_reads_do_not_create_directory_owner_or_provider(tmp_path):
    directory=tmp_path/'missing-workspace'
    settings=Settings(faultlab_artifact_dir=str(directory))
    with patch('app.lab.coordinator.LabCoordinator', side_effect=AssertionError('No writer during preview')):
        with patch('app.providers.runtime.RuntimeProvider', side_effect=AssertionError('No provider during preview')):
            with TestClient(create_app(settings=settings)) as client:
                response=client.get('/api/run-options')
                assert response.status_code == 200, response.text
                options=response.json()
                assert options['provider_calls'] == 0
                assert {row['case_id'] for row in options['development']['cases']} == {f'dev-{i}' for i in range(1,7)}
                assert {row['agent'] for row in options['agents']} == {'reference','smolagents'}
                assert all(row['provider_access']=='not_checked' and not row['behavior_verified'] for row in options['agents'])
    assert not directory.exists()


@pytest.mark.parametrize('archive',[False,True])
def test_setup_inspection_does_not_recover_or_change_another_owners_work(tmp_path,archive):
    settings=Settings(faultlab_artifact_dir=str(tmp_path))
    owner=LabCoordinator(settings)
    campaign=owner.create(CampaignRequest(task_text='Saved task',order_id='order-running',mode='baseline'))
    owner.transition(campaign.campaign_id,'RUNNING')
    before=owner.store.list_records('campaigns')
    before_registrations=owner.store.list_records('agent_registrations')
    path=tmp_path/'lab.sqlite3'
    fingerprint=(hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns)
    try:
        with patch('app.lab.coordinator.LabCoordinator',side_effect=AssertionError('No second owner')):
            with TestClient(create_app(settings=replace(settings,faultlab_read_only=archive))) as client:
                response=client.get('/api/run-options')
                assert response.status_code == 200,response.text
                assert response.json()['data_store']['read_only'] is archive
        assert owner.store.list_records('campaigns') == before
        assert owner.store.list_records('agent_registrations') == before_registrations
        assert (hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns) == fingerprint
    finally:
        asyncio.run(owner.close())


@pytest.mark.parametrize('bad_field,bad_value,status',[
    ('expected_store_identity','0'*64,409),('expected_setup_hash','0'*64,409),
    ('task_definition_id','arbitrary-code',422),('development_case_id','promotion-1',422),
])
def test_invalid_selection_is_refused_before_lazy_writer_creation(tmp_path,bad_field,bad_value,status):
    directory=tmp_path/'not-created'
    settings=Settings(faultlab_artifact_dir=str(directory))
    with patch('app.lab.coordinator.LabCoordinator',side_effect=AssertionError('Invalid request constructed owner')):
        with TestClient(create_app(settings=settings)) as client:
            options=client.get('/api/run-options').json()
            body=request_for(options);body[bad_field]=bad_value
            response=client.post('/api/planned-campaigns',json=body)
            assert response.status_code == status,response.text
    assert not directory.exists()


@pytest.mark.parametrize('existing_store', [False, True])
@pytest.mark.parametrize('mode', ['baseline', 'compare'])
def test_invalid_live_selection_cannot_initialize_or_recover_store(tmp_path, existing_store, mode):
    from app.lab.operator_actions import register_agent
    from app.lab.storage import ReadOnlyLabStore

    directory = tmp_path / 'selected-store'
    settings = Settings(faultlab_artifact_dir=str(directory), wandb_model='deepseek-ai/DeepSeek-V3.1')
    registration_id = 'registration-not-saved'
    campaign_id = None
    if existing_store:
        owner = LabCoordinator(settings)
        try:
            saved = owner.create(CampaignRequest(task_text='Unfinished saved task', order_id='order-unfinished', mode='baseline'))
            owner.transition(saved.campaign_id, 'RUNNING')
            campaign_id = saved.campaign_id
            registered = register_agent(owner.store, settings, 'reference')
            # The compare case has a current registration but no accepted policy;
            # baseline independently exercises an arbitrary registration ID.
            if mode == 'compare':
                registration_id = registered.registration_id
        finally:
            asyncio.run(owner.close())
    path = directory / 'lab.sqlite3'
    fingerprint = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) if existing_store else None

    with patch('app.lab.coordinator.LabCoordinator', side_effect=AssertionError('Invalid live selection initialized owner')) as constructor:
        with TestClient(create_app(settings=settings)) as client:
            options = client.get('/api/run-options').json()
            if existing_store and mode == 'compare':
                row = next(row for row in options['agents'] if row['agent'] == 'reference')
                assert row['registered'] and row['registration_id'] == registration_id
                assert not row['compare_available']
            body = {**request_for(options), 'mode': mode, 'config_profile_id': 'live-v1',
                    'agent_registration_id': registration_id}
            if mode == 'compare':
                body.pop('development_case_id')
            response = client.post('/api/planned-campaigns', json=body)
            assert response.status_code == 409, response.text
            assert response.json()['error']['code'] == 'CONFLICT'
        constructor.assert_not_called()
    if existing_store:
        assert (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) == fingerprint
        snapshot = ReadOnlyLabStore(path)
        try:
            assert snapshot.get_record('campaigns', campaign_id)['state'] == 'RUNNING'
        finally:
            snapshot.close()
    else:
        assert not directory.exists()


def test_create_freezes_plan_without_starting_and_export_keeps_plan(tmp_path):
    settings=Settings(faultlab_artifact_dir=str(tmp_path))
    with patch('app.providers.runtime.RuntimeProvider',side_effect=AssertionError('Create must not execute')):
        with TestClient(create_app(settings=settings)) as client:
            options=client.get('/api/run-options').json()
            response=client.post('/api/planned-campaigns',json=request_for(options))
            assert response.status_code == 201,response.text
            campaign=response.json()
            assert campaign['state']=='IDLE' and campaign['latest_episode_id'] is None
            plan=client.get(f"/api/campaigns/{campaign['campaign_id']}/plan")
            assert plan.status_code==200,plan.text
            assert plan.json()['status']=='PLANNED'
            recording=client.get(f"/api/campaigns/{campaign['campaign_id']}/recording")
            assert recording.status_code==200,recording.text
            data=recording.json()
            assert data['campaign']==campaign
            assert data['run_plan']==plan.json()
            assert data['configuration'] and data['agent_registration']
            assert data['episodes']==[]
            assert client.get(f"/api/campaigns/{campaign['campaign_id']}").json()==campaign


def test_slow_setup_inspection_does_not_block_active_campaign_stop(tmp_path,monkeypatch):
    from app.lab import run_plans
    async def check():
        owner=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
        campaign=owner.create(CampaignRequest(task_text='Active task',order_id='order-active',mode='baseline'))
        owner.active_id=campaign.campaign_id
        owner.transition(campaign.campaign_id,'RUNNING')
        body=request_for(run_plans.build_run_options(owner.settings,owner.store))
        entered,release=threading.Event(),threading.Event()
        original=run_plans.build_run_options
        def slow(*args,**kwargs):
            entered.set()
            assert release.wait(3),'Stop must remain responsive during source inspection'
            return original(*args,**kwargs)
        monkeypatch.setattr(run_plans,'build_run_options',slow)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)),base_url='http://test') as client:
                creation=asyncio.create_task(client.post('/api/planned-campaigns',json=body))
                assert await asyncio.to_thread(entered.wait,2)
                try:
                    stop=await asyncio.wait_for(client.post(f'/api/campaigns/{campaign.campaign_id}/stop',json={}),.5)
                    assert stop.status_code==202 and stop.json()['state']=='STOPPED'
                finally:
                    release.set()
                created=await creation
                assert created.status_code==201,created.text
                assert created.json()['state']=='IDLE'
                assert owner.store.list_records('episodes')==[]
        finally:
            release.set()
            owner.active_id=None
            await owner.close()
    asyncio.run(check())
