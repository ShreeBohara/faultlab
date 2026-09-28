"""Saved navigation is bounded, passive and cannot block the scheduler."""
import asyncio
import threading
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts.models import CampaignRequest
from app.lab.coordinator import LabCoordinator
from app.main import create_app
from app.providers.runtime import RuntimeProvider


def campaign(coordinator, label):
    return coordinator.create(CampaignRequest(
        task_text=label, order_id='order-history', mode='baseline',
        config_profile_id='offline-v1'))


def test_history_empty_and_invalid_cursors(tmp_path):
    with TestClient(create_app(settings=Settings(faultlab_artifact_dir=str(tmp_path)))) as client:
        assert client.get('/api/campaigns').json() == {
            'campaigns': [], 'next_before': None, 'has_more': False}
        for query in ('limit=0', 'limit=101', 'before=0', 'before=-1',
                      'before=hello', 'before=9223372036854775808'):
            assert client.get('/api/campaigns?' + query).status_code == 422


def test_history_cursor_survives_new_runs_and_updates_without_reexecution(tmp_path):
    c = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    original = [campaign(c, f'Historical run {i}') for i in range(4)]
    c.store.put_record('budgets', original[-1].campaign_id, {
        'reservations': {'remaining': {'calls': 3}}, 'used_calls': 7,
        'measured_input_tokens': 13, 'measured_output_tokens': 17,
        'actual_cost_dollars': .25})
    with patch.object(RuntimeProvider, 'complete', side_effect=AssertionError('No paid calls')):
        with TestClient(create_app(coordinator=c)) as client:
            # The reader must not scan every record or touch worlds/providers.
            with patch.object(c.store, 'list_records', side_effect=AssertionError('Unbounded scan')):
                first = client.get('/api/campaigns?limit=2').json()
                assert [r['campaign_id'] for r in first['campaigns']] == [r.campaign_id for r in original[::-1][:2]]
                assert first['has_more'] and first['next_before'] > 0
                assert first['campaigns'][0]['usage']['model_calls'] == 7
                assert first['campaigns'][0]['usage']['cost_dollars'] == .25
                assert first['campaigns'][0]['reserved_calls'] == 3
            new = campaign(c, 'New run between pages')
            c.transition(original[0].campaign_id, 'COMPLETED', 'Saved result')
            before = list(c.store.db.iterdump())
            second = client.get(f'/api/campaigns?limit=2&before={first["next_before"]}').json()
            assert [r['campaign_id'] for r in second['campaigns']] == [original[1].campaign_id, original[0].campaign_id]
            assert second['campaigns'][-1]['state'] == 'COMPLETED'
            assert second['next_before'] is None and not second['has_more']
            assert list(c.store.db.iterdump()) == before
            assert not c.tasks and c.active_id is None
            assert client.get('/api/campaigns?limit=1').json()['campaigns'][0]['campaign_id'] == new.campaign_id


def test_evidence_read_does_not_hold_scheduler_event_loop(tmp_path):
    """A deliberately slow saved-record reader must not block a Stop request."""
    async def verify():
        c = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
        saved = campaign(c, 'Active local fixture')
        c.active_id = saved.campaign_id
        c.transition(saved.campaign_id, 'RUNNING')
        entered = threading.Event()
        release = threading.Event()
        from app.lab.storage import ReadOnlyLabStore
        original = ReadOnlyLabStore.list_campaign_episodes

        def slow_reader(store, id):
            entered.set()
            assert release.wait(3), 'Read must be released by scheduler while it runs'
            return original(store, id)

        try:
            with patch.object(ReadOnlyLabStore, 'list_campaign_episodes', slow_reader):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=c)), base_url='http://test') as client:
                    read = asyncio.create_task(client.get(f'/api/campaigns/{saved.campaign_id}/matrix'))
                    assert await asyncio.to_thread(entered.wait, 2)
                    try:
                        response = await asyncio.wait_for(client.post(f'/api/campaigns/{saved.campaign_id}/stop', json={}), .5)
                        assert response.status_code == 202
                        assert response.json()['state'] == 'STOPPED'
                    finally:
                        release.set()
                    assert (await read).status_code == 200
        finally:
            release.set()
            c.active_id = None
            await c.close()
    asyncio.run(verify())


def test_execution_history_is_bundle_scoped_and_passive(tmp_path):
    from app.contracts.models import RegressionExecution, EpisodeBudget, Usage, content_hash
    c = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    c.store.put_record('regressions', 'regression-selected', {'bundle_id': 'bundle-selected'})
    c.store.put_record('regressions', 'regression-empty', {'bundle_id': 'bundle-empty'})
    for index in range(5):
        execution = RegressionExecution(
            execution_id=f'execution-{index}', bundle_id='bundle-foreign' if index == 3 else 'bundle-selected',
            manifest_hash=content_hash('fixture'), registration_id='agent-fixture',
            profile_id='sandbox-v1', mode='FRESH_SANDBOX', explicit_action=True,
            policy_hash=content_hash('policy'), configuration_hash=content_hash('configuration'),
            declared_budget=EpisodeBudget(), usage=Usage(), episode_ids=[], world_ids=[],
            status='INCOMPLETE', stop_reason='Offline interrupted execution fixture')
        c.store.put_record('regression_executions', execution.execution_id, execution)
    before = list(c.store.db.iterdump())
    with TestClient(create_app(coordinator=c)) as client:
        with patch.object(c.store, 'list_records', side_effect=AssertionError('Unbounded scan')):
            page = client.get('/api/regressions/regression-selected/executions?limit=2').json()
            assert [e['execution_id'] for e in page['executions']] == ['execution-4', 'execution-2']
            assert page['has_more']
            older = client.get(f'/api/regressions/regression-selected/executions?limit=2&before={page["next_before"]}').json()
            assert [e['execution_id'] for e in older['executions']] == ['execution-1', 'execution-0']
            assert not older['has_more'] and older['next_before'] is None
            assert client.get('/api/regressions/regression-empty/executions').json()['executions'] == []
            assert client.get('/api/regressions/missing/executions').status_code == 404
            assert client.get('/api/regressions/regression-selected/executions?before=-1').status_code == 422
        assert list(c.store.db.iterdump()) == before
        assert not c.tasks and c.active_id is None
