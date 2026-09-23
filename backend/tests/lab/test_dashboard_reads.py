"""Phase 19: dashboard read endpoints must not parse every campaign's records.

The dashboard polls /matrix and /experiments once a second. Both ran on the event loop
and parsed every episode and evidence bundle in the store (~0.9s and ~1.3s at 4,794
episodes), freezing the lab most of each second. The freeze is what let a re-send's
connect time out unsent (see tests/adapters/test_connect_freeze.py).
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.lab.api import create_router
from app.lab.storage import LabStore


@pytest.fixture
def store(tmp_path):
    return LabStore(tmp_path / 'lab.sqlite3')


def episode(eid, campaign, split='development', purpose='development_validation'):
    return {'episode_id': eid, 'campaign_id': campaign, 'study_id': campaign, 'split': split, 'experiment_purpose': purpose,
            'lifecycle': 'COMPLETED', 'arm': 'L', 'policy_hash': 'p' * 64, 'scenario_hash': 's' * 64, 'source_mode': 'live',
            'usage': {'ticks': 1}, 'verdict': {'outcome': 'COMPLETED', 'fault_executions': []}}


# Real ids are random hex, so storage order and id order disagree. Insert in an order
# that is neither sorted nor reverse-sorted, so a query ordered by id instead of rowid
# fails these tests.
IDS = ['episode-7f', 'episode-1c', 'episode-e2', 'episode-03', 'episode-9a', 'episode-5d', 'episode-b4', 'episode-0e', 'episode-c8']


def seed(store):
    # Interleave three campaigns so row order is a real check.
    for n in range(9):
        campaign = ('campaign-a', 'campaign-b', 'campaign-c')[n % 3]
        eid = IDS[n]
        store.put_record('episodes', eid, episode(eid, campaign, split='promotion' if n == 6 else 'development'))
        store.put_record('evidence', eid, {'episode_id': eid, 'source': 'local_only', 'root_call_id': None, 'child_call_ids': [], 'source_project': None})
        store.put_record('ingestions', eid, {'episode_id': eid, 'state': 'VERIFIED'})


def test_campaign_episodes_are_exactly_the_python_filter_in_the_same_order(store):
    seed(store)
    for campaign in ('campaign-a', 'campaign-b', 'campaign-c', 'campaign-none'):
        expected = [v for v in store.list_records('episodes') if v.get('campaign_id') == campaign]
        assert store.list_campaign_episodes(campaign) == expected


def test_campaign_episodes_follow_the_payload_not_a_stale_registry_row(store):
    seed(store)
    # put_record keeps the FIRST campaign in the registry; the payload guard must still
    # drop an episode whose payload now names another campaign.
    moved = {**store.get_record('episodes', IDS[0]), 'campaign_id': 'campaign-b'}
    store.db.execute("UPDATE records SET payload=? WHERE kind='episodes' AND id=?", (__import__('json').dumps(moved), IDS[0]))
    assert IDS[0] not in [v['episode_id'] for v in store.list_campaign_episodes('campaign-a')]


def test_get_records_keeps_storage_order_and_ignores_duplicates_and_missing_ids(store):
    # Ids inserted in a scrambled order, so id order and storage order disagree.
    ids = [f'episode-{(n * 7919) % 1203:04d}' for n in range(1203)]
    for eid in ids: store.put_record('evidence', eid, {'episode_id': eid})
    wanted = ids[::-2]
    # A duplicate that falls in a DIFFERENT 500-id chunk from its original, and a missing id.
    wanted = wanted + [wanted[0], 'episode-missing']
    got = store.get_records('evidence', wanted)
    expected = [eid for eid in ids if eid in set(wanted)]
    assert [v['episode_id'] for v in got] == expected


@pytest.fixture
def api(store):
    seed(store)
    coordinator = SimpleNamespace(store=store, get=lambda id: {'campaign_id': id})
    app = FastAPI(); app.include_router(create_router(coordinator))
    calls = []
    original = store.list_records
    def spy(kind):
        calls.append(kind); return original(kind)
    store.list_records = spy
    return TestClient(app), calls


def test_matrix_reads_only_its_own_campaign(api):
    client, calls = api
    matrix = client.get('/api/campaigns/campaign-a/matrix').json()
    assert [cell['episode_id'] for cell in matrix['cells']] == [IDS[0], IDS[3], IDS[6]]
    assert 'episodes' not in calls


def test_experiments_reads_only_its_own_development_evidence(api):
    client, calls = api
    body = client.get('/api/campaigns/campaign-a/experiments').json()
    # IDS[6] is campaign-a's promotion episode: excluded exactly as before.
    assert [e['episode_id'] for e in body['evidence']] == [IDS[0], IDS[3]]
    assert [e['episode_id'] for e in body['ingestions']] == [IDS[0], IDS[3]]
    assert not {'episodes', 'evidence', 'ingestions'} & set(calls)
