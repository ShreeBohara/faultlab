"""Passive archives and slow SQL readers cannot mutate or stall active work."""
import asyncio
from dataclasses import replace
import hashlib
import sqlite3
import threading
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts.models import CampaignRequest
from app.lab.coordinator import LabCoordinator
from app.lab.storage import LabStore, ReadOnlyLabStore, ReadOnlyStore
from app.main import create_app


def create_campaign(owner):
    return owner.create(CampaignRequest(task_text='Saved task', order_id='order-archive',
                                       mode='baseline', config_profile_id='offline-v1'))


def test_reader_never_creates_missing_database_or_parent(tmp_path):
    path = tmp_path / 'absent' / 'lab.sqlite3'
    with pytest.raises(sqlite3.OperationalError):
        ReadOnlyLabStore(path)
    assert not path.parent.exists()


def test_read_only_store_preserves_snapshot_and_rejects_all_writes(tmp_path):
    writer = LabStore(tmp_path / 'lab.sqlite3')
    writer.put_record('items', 'one', {'value': 1})
    reader = ReadOnlyLabStore(writer.path)
    try:
        reader.begin_snapshot()
        assert reader.get_record('items', 'one') == {'value': 1}
        writer.put_record('items', 'one', {'value': 2})
        assert reader.get_record('items', 'one') == {'value': 1}
        with pytest.raises(ReadOnlyStore):
            reader.put_record('items', 'two', {})
        with pytest.raises(sqlite3.OperationalError):
            reader.db.execute('DELETE FROM records')
    finally:
        reader.close()
        writer.close()
    reopened = ReadOnlyLabStore(writer.path)
    assert reopened.get_record('items', 'one') == {'value': 2}
    reopened.close()


def test_store_close_releases_every_registered_resource_even_if_callback_fails(tmp_path):
    store = LabStore(tmp_path / 'lab.sqlite3')
    called = []
    store.on_close(lambda: called.append('lease'))
    def broken():
        called.append('broken')
        raise RuntimeError('fixture cleanup failure')
    store.on_close(broken)
    with pytest.raises(RuntimeError):
        store.close()
    assert called == ['broken', 'lease']
    store.close()
    store.on_close(lambda: called.append('late'))
    assert called == ['broken', 'lease', 'late']
    with pytest.raises(sqlite3.ProgrammingError):
        store.db.execute('SELECT 1')


def test_archive_reads_running_records_without_recovery_and_rejects_mutations(tmp_path):
    settings = Settings(faultlab_artifact_dir=str(tmp_path))
    owner = LabCoordinator(settings)
    campaign = create_campaign(owner)
    owner.transition(campaign.campaign_id, 'RUNNING')
    owner.store.put_record('episodes', 'episode-unfinished', {
        'episode_id': 'episode-unfinished', 'campaign_id': campaign.campaign_id,
        'split': 'development', 'lifecycle': 'RUNNING'})
    asyncio.run(owner.close())
    path = tmp_path / 'lab.sqlite3'
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    archived = replace(settings, faultlab_read_only=True)
    with patch('app.lab.coordinator.LabCoordinator', side_effect=AssertionError('No recovery owner')):
        with TestClient(create_app(settings=archived)) as client:
            status = client.get('/api/config/status').json()
            assert status['data_store']['read_only'] and not status['live_enabled']
            assert status['active_campaign_id'] is None
            assert client.get(f'/api/campaigns/{campaign.campaign_id}').json()['state'] == 'RUNNING'
            assert client.get('/api/episodes/episode-unfinished').json()['lifecycle'] == 'RUNNING'
            readiness = client.get('/api/readiness').json()
            assert readiness['simulator']['code'] == 'READ_ONLY_ARCHIVE'
            assert readiness['provider_calls'] == 0
            for route, body in [
                ('/api/campaigns', {'task_text': 'No mutation', 'order_id': 'order-archive',
                                    'mode': 'baseline', 'config_profile_id': 'offline-v1'}),
                (f'/api/campaigns/{campaign.campaign_id}/start', {}),
                (f'/api/campaigns/{campaign.campaign_id}/stop', {}),
                (f'/api/campaigns/{campaign.campaign_id}/retry-evidence', {}),
                ('/api/reset-demo', {}),
            ]:
                response = client.post(route, json=body)
                assert response.status_code == 409
                assert response.json()['error']['code'] == 'READ_ONLY_ARCHIVE'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_slow_sql_read_has_its_own_lock_and_stop_commits_while_it_waits(tmp_path):
    async def check():
        owner = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
        campaign = create_campaign(owner)
        owner.active_id = campaign.campaign_id
        owner.transition(campaign.campaign_id, 'RUNNING')
        entered, release = threading.Event(), threading.Event()
        original = ReadOnlyLabStore.list_campaign_episodes
        def slow_sql(reader, ident):
            def hold():
                entered.set()
                assert release.wait(3), 'Stop must remain responsive while SQL is blocked'
                return 1
            with reader.lock:
                reader.db.create_function('hold_reader', 0, hold)
                reader.db.execute("SELECT hold_reader() FROM records WHERE kind='campaigns' LIMIT 1").fetchone()
            return original(reader, ident)
        try:
            with patch.object(ReadOnlyLabStore, 'list_campaign_episodes', slow_sql):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as client:
                    read = asyncio.create_task(client.get(f'/api/campaigns/{campaign.campaign_id}/matrix'))
                    assert await asyncio.to_thread(entered.wait, 2)
                    try:
                        stop = await asyncio.wait_for(client.post(f'/api/campaigns/{campaign.campaign_id}/stop', json={}), .5)
                        assert stop.status_code == 202 and stop.json()['state'] == 'STOPPED'
                        assert owner.get(campaign.campaign_id).state == 'STOPPED'
                    finally:
                        release.set()
                    assert (await read).status_code == 200
        finally:
            release.set()
            owner.active_id = None
            await owner.close()
    asyncio.run(check())
