"""New campaign defaults are frozen; explicit studies and historical snapshots keep their choices."""
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.adapters.business_tools import WorldClient
from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V1 as V1, ACTOR_CONTEXT_PROTOCOL_V4 as V4
from app.config import Settings
from app.contracts.models import Campaign, CampaignBudget, CampaignRequest, FaultSpec, canonical_json, content_hash
from app.lab import completion_study
from app.lab.configuration import frozen_configuration, resolve_actor_context_protocol
from app.lab.coordinator import LabCoordinator
from app.lab.policies import PolicyRepository
from app.lab.runner import EpisodeRunner
from app.lab.storage import LabStore, StoreConflict
from app.providers.runtime import RuntimeGeneration
from app.simulator.main import create_app
from test_baseline_study import settings


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def test_new_configuration_freezes_the_selected_context_as_semantic_identity():
    current = Settings()
    v4 = frozen_configuration(current, CampaignBudget(), 'offline-v1')
    v1 = frozen_configuration(replace(current, faultlab_actor_context_protocol=V1),
                              CampaignBudget(), 'offline-v1')
    assert current.faultlab_actor_context_protocol == V4
    assert v4['actor_context_protocol'] == V4 and v1['actor_context_protocol'] == V1
    assert content_hash(v4) != content_hash(v1)
    assert {key: value for key, value in v4.items() if key != 'actor_context_protocol'} == {
        key: value for key, value in v1.items() if key != 'actor_context_protocol'}
    with pytest.raises(ValueError, match='Unknown actor context protocol'):
        frozen_configuration(replace(current, faultlab_actor_context_protocol='invented'),
                             CampaignBudget(), 'offline-v1')


@pytest.mark.parametrize('frozen,explicit,expected', [
    ({}, None, V1),
    ({}, V4, V4),
    ({'actor_context_protocol': V4}, None, V4),
    ({'actor_context_protocol': V4}, V1, V1),
    ({'actor_context_protocol': V1}, None, V1),
    ({'actor_context_protocol': V1}, V4, V4),
])
def test_protocol_selection_never_applies_a_new_default_to_an_old_snapshot(frozen, explicit, expected):
    assert resolve_actor_context_protocol(frozen, explicit) == expected


@pytest.mark.anyio
@pytest.mark.parametrize('frozen_choice,explicit,expected', [
    (V4, None, V4), (V4, V1, V1), (V1, None, V1),
    ('missing', None, V1), ('missing', V4, V4),
])
async def test_runner_passes_the_frozen_or_explicit_choice_into_real_actor_requests(
        tmp_path, frozen_choice, explicit, expected):
    # A minimal saved snapshot isolates the runner's compatibility path. Normal API
    # admission still refuses an old campaign whose complete runtime identity changed.
    frozen = {'models': {'actor': 'openai/gpt-oss-120b'}}
    if frozen_choice != 'missing':
        frozen['actor_context_protocol'] = frozen_choice
    store = LabStore(tmp_path / 'lab.sqlite3')
    identity = content_hash(frozen)
    store.put_record('configurations', identity, frozen, immutable=True)
    campaign = Campaign(campaign_id='campaign-context', mode='baseline',
        task_text='Upgrade and confirm', order_id='order-1', config_profile_id='live-v1',
        model='openai/gpt-oss-120b', configuration_hash=identity)
    requests = []

    class Provider:
        async def complete(self, messages, **kwargs):
            turn = json.loads(messages[-1]['content']); requests.append(turn)
            action = ({'kind': 'tool', 'tool': 'get_order', 'arguments': {}} if len(requests) == 1 else
                {'kind': 'report', 'report': {'upgrade_outcome': 'NOT_STARTED',
                    'notification_outcome': 'NOT_STARTED', 'overall': 'SAFE_UNRESOLVED',
                    'evidence_ids': [turn['observations'][0]['evidence_id']],
                    'next_action': {'kind': 'ESCALATE'}}})
            return RuntimeGeneration(canonical_json(action), 'openai/gpt-oss-120b')

    simulator = create_app(database_dir=tmp_path / 'worlds', control_token='test')
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator),
                               base_url='http://127.0.0.1:8001')
    try:
        runner = EpisodeRunner(store, WorldClient('http://127.0.0.1:8001', 'test', client=client), Provider())
        trial = await runner.run(campaign, FaultSpec(seed=1, primitives=[]),
            PolicyRepository(store).baseline(), source_mode='offline_fixture', actor_context_protocol=explicit)
        assert trial.outcome == 'SAFE_UNRESOLVED' and not trial.failed_checks
        events = store.events(trial.episode_id)['events']
        observed = next(event['evidence_id'] for event in events if event['type'] == 'observation_delivered')
        outputs = [event['payload'] for event in events if event['type'] == 'actor_output']
        assert {output['actor_context_protocol'] for output in outputs} == {expected}
        assert requests[-1]['observations'][0]['evidence_id'] == ('obs-1' if expected == V4 else observed)
        assert store.get_record('episodes', trial.episode_id)['report']['evidence_ids'] == [observed]
        assert store.get_record('configurations', identity) == frozen
    finally:
        await client.aclose()
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('frozen_choice,explicit', [
    ('invented', None), (None, None), ('', None), (V4, 'invented'), (V4, ''),
])
async def test_runner_rejects_unknown_context_before_creating_a_world_or_record(frozen_choice, explicit):
    store = LabStore(':memory:')
    frozen = {'actor_context_protocol': frozen_choice}
    identity = content_hash(frozen)
    store.put_record('configurations', identity, frozen, immutable=True)
    world = SimpleNamespace(create=AsyncMock())
    runner = EpisodeRunner(store, world)
    campaign = Campaign(campaign_id='campaign-invalid-context', mode='baseline',
        task_text='Upgrade and confirm', order_id='order-1', config_profile_id='live-v1',
        model='openai/gpt-oss-120b', configuration_hash=identity)
    try:
        with pytest.raises(ValueError, match='Unknown actor context protocol'):
            await runner.run(campaign, None, None, actor_context_protocol=explicit)
        world.create.assert_not_called()
        assert not store.list_records('episodes') and not store.list_records('private_episode_inputs')
    finally:
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('selected,explicit,expected', [(V4, None, V4), (V4, V1, V1), (V1, None, V1)])
async def test_completion_queue_saves_campaign_choice_and_respects_explicit_study_arm(
        tmp_path, monkeypatch, selected, explicit, expected):
    coordinator = LabCoordinator(replace(settings(tmp_path), faultlab_actor_context_protocol=selected))
    campaign = coordinator.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-1',
                                                 mode='baseline', config_profile_id='live-v1'))
    execute = AsyncMock()
    monkeypatch.setattr(completion_study, '_execute', execute)
    monkeypatch.setattr(coordinator, 'require_simulator', AsyncMock())
    try:
        queued = await completion_study.queue_completion_study(coordinator, campaign.campaign_id,
                                                              actor_context_protocol=explicit)
        await coordinator.tasks[queued['study_id']]
        frozen = coordinator.store.get_record('configurations', campaign.configuration_hash)
        assert frozen['actor_context_protocol'] == selected
        assert campaign.configuration_hash == content_hash(frozen)
        assert queued['actor_context_protocol'] == expected
        assert coordinator.store.get_record('completion_plans', queued['study_id'])['actor_context_protocol'] == expected
        assert execute.await_args.args[3]['actor_context_protocol'] == expected
    finally:
        await coordinator.close()


@pytest.mark.anyio
async def test_completion_rejects_an_unknown_explicit_protocol_without_admission(tmp_path):
    coordinator = LabCoordinator(settings(tmp_path))
    campaign = coordinator.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-1',
                                                 mode='baseline', config_profile_id='live-v1'))
    try:
        with pytest.raises(StoreConflict, match='Unknown actor context protocol'):
            await completion_study.queue_completion_study(coordinator, campaign.campaign_id,
                                                         actor_context_protocol='invented')
        assert not coordinator.store.list_records('completion_studies')
        assert not coordinator.store.list_records('completion_plans')
        assert coordinator.active_id is None and not coordinator.ledgers
        assert coordinator.get(campaign.campaign_id).state == 'IDLE'
    finally:
        await coordinator.close()
