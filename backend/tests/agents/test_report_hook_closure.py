"""Finalizing a real model answer cannot reopen work or bypass receipt guards."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.adapters.business_tools import WorldClient
from app.adapters.journal import Journal, allocate_intent
from app.agents.actor import Actor, ActorReportError
from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4
from app.config import Settings
from app.contracts.models import (CampaignRequest, CandidatePolicy, EpisodeBudget,
                                  FaultSpec, RecoveryPolicy, canonical_json)
from app.lab.budgets import BudgetExhausted, EpisodeMeter, StopRequested
from app.lab.coordinator import LabCoordinator
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.runner import EpisodeRunner
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration
from app.simulator.main import create_app


@pytest.fixture
def anyio_backend(): return 'asyncio'


HONEST = {'upgrade_outcome': 'UNKNOWN', 'notification_outcome': 'NOT_STARTED',
          'overall': 'SAFE_UNRESOLVED', 'evidence_ids': [], 'next_action': {'kind': 'ESCALATE'}}
IO_STEPS = [{'op': 'read_current_operation'}, {'op': 'read_notification_operation'},
            {'op': 'read_order'}, {'op': 'wait_ticks', 'ticks': 1},
            {'op': 'retry_original_request', 'service': 'orders'}]


def context_for(tmp_path, steps, *, report=None, hook='before_final_report', closed=True):
    store = LabStore(tmp_path / 'lab.sqlite3')
    store.put_record('episodes', 'episode-test', {'campaign_id': 'campaign-test'})
    journal = Journal(store, 'episode-test', allocate_intent('order-test', 'Upgrade and confirm'))
    broker = SimpleNamespace(journal=journal, meter=EpisodeMeter(), logical_calls=[])
    broker.meter.business_closed = closed
    effects = []

    async def call(*args, **kwargs):
        broker.meter.http_attempt()
        effects.append((args, kwargs))

    async def wait(ticks):
        broker.meter.wait(ticks)
        effects.append(('wait', ticks))

    broker.call = call
    broker.wait_ticks = wait
    broker.retry_original = call
    policy = RecoveryPolicy.model_validate_json(canonical_json({
        'parent_version': 'policy-v0', 'rules': [{'hook': hook, 'when': 'always', 'steps': steps}]}))
    requests = []
    raw = canonical_json({'kind': 'report', 'report': report or HONEST})

    class Provider:
        async def complete(self, messages, **kwargs):
            requests.append((messages, kwargs))
            return RuntimeGeneration(raw, 'openai/gpt-oss-120b')

    context = SimpleNamespace(broker=broker, interpreter=PolicyInterpreter(policy, broker),
                              provider=Provider(), metadata={'model_id': 'openai/gpt-oss-120b'},
                              actor_context_protocol=ACTOR_CONTEXT_PROTOCOL_V4)
    return context, requests, effects, raw, store


@pytest.mark.anyio
@pytest.mark.parametrize('step', IO_STEPS)
@pytest.mark.parametrize('service', ['orders', 'notifications'])
@pytest.mark.parametrize('guard_first', [False, True])
async def test_closed_final_hook_skips_io_but_keeps_guards_and_step_charges(tmp_path, step, service, guard_first):
    guard = {'op': 'require_receipt', 'service': service, 'status': 'SUCCEEDED'}
    steps = [guard, step] if guard_first else [step, guard]
    context, requests, effects, raw, store = context_for(tmp_path, steps)
    try:
        report = await Actor()(context.broker.journal.intent, context)
        assert report.model_dump(mode='json') == HONEST
        assert len(requests) == context.broker.meter.usage.actor_calls == 1
        assert requests[0][1]['response_contract'] == 'actor_final_report'
        assert effects == [] and context.broker.meter.business_closed
        usage = context.broker.meter.usage
        assert (usage.http_attempts, usage.ticks, usage.wait_cycles, usage.policy_steps) == (0, 0, 0, 2)
        events = store.events('episode-test')['events']
        skipped = [e['payload'] for e in events if e['type'] == 'policy_step' and e['payload']['op'] == step['op']]
        assert skipped == [{'hook': 'before_final_report', 'op': step['op'],
                            'executed': False, 'skip_reason': 'BUSINESS_CALLS_CLOSED'}]
        assert [e['payload']['raw'] for e in events if e['type'] == 'actor_output'] == [raw]
        assert len([e for e in events if e['type'] == 'report_submitted']) == 1
    finally:
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('service,field', [('orders', 'upgrade_outcome'), ('notifications', 'notification_outcome')])
@pytest.mark.parametrize('guard_first', [False, True])
async def test_closed_final_hook_cannot_bypass_success_guard_or_gain_a_ninth_turn(tmp_path, service, field, guard_first):
    guard = {'op': 'require_receipt', 'service': service, 'status': 'SUCCEEDED'}
    read = {'op': 'read_current_operation'}
    context, requests, effects, raw, store = context_for(
        tmp_path, [guard, read] if guard_first else [read, guard], report={**HONEST, field: 'SUCCEEDED'})
    try:
        with pytest.raises(ActorReportError, match='blocked by policy on the final available turn'):
            await Actor()(context.broker.journal.intent, context)
        assert len(requests) == context.broker.meter.usage.actor_calls == 8
        assert effects == []
        events = store.events('episode-test')['events']
        assert not any(e['type'] == 'report_submitted' for e in events)
        blocked = [e['payload'] for e in events if e['type'] == 'report_hook_blocked']
        assert len(blocked) == 8 and blocked[-1]['actor_turn'] == 8
        assert f'RECEIPT_REQUIRED:{service}' in blocked[-1]['reasons']
        assert all(e['payload']['raw'] == raw for e in events if e['type'] == 'actor_output')
    finally:
        store.close()


@pytest.mark.anyio
async def test_false_condition_stays_skipped_and_charged_without_closed_io_reason(tmp_path):
    context, _, effects, _, store = context_for(tmp_path, [{'op': 'read_order', 'only_if': 'upgrade_succeeded'}])
    try:
        await Actor()(context.broker.journal.intent, context)
        step = next(e['payload'] for e in store.events('episode-test')['events'] if e['type'] == 'policy_step')
        assert step == {'hook': 'before_final_report', 'op': 'read_order', 'executed': False}
        assert context.broker.meter.usage.policy_steps == 1 and effects == []
    finally:
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('hook,closed', [('before_final_report', False), ('before_confirmation', True)])
async def test_open_report_hooks_and_closed_nonreport_hooks_keep_existing_behavior(tmp_path, hook, closed):
    context, _, effects, _, store = context_for(tmp_path, [{'op': 'read_order'}], hook=hook, closed=closed)
    try:
        if closed:
            with pytest.raises(BudgetExhausted, match='Business calls closed'):
                await context.interpreter.invoke(hook, 'proposal-test')
            assert effects == []
        else:
            await Actor()(context.broker.journal.intent, context)
            assert len(effects) == context.broker.meter.usage.http_attempts == 1
    finally:
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('limit', ['policy_steps', 'deadline'])
async def test_remaining_hook_budget_failures_name_the_hook_and_preserve_the_answer(tmp_path, limit):
    context, requests, effects, raw, store = context_for(tmp_path, [{'op': 'read_order'}])
    meter = context.broker.meter
    if limit == 'policy_steps':
        meter.caps = EpisodeBudget(policy_steps=0)
    else:
        now = [0.0]
        meter.clock = lambda: now[0]
        meter.started = 0.0
        provider = context.provider

        class Expiring:
            async def complete(self, *args, **kwargs):
                answer = await provider.complete(*args, **kwargs)
                now[0] = meter.caps.wall_seconds
                return answer
        context.provider = Expiring()
    try:
        with pytest.raises(ActorReportError, match='before_final_report hook exhausted its limit'):
            await Actor()(context.broker.journal.intent, context)
        assert len(requests) == 1 and effects == []
        events = store.events('episode-test')['events']
        assert not any(e['type'] == 'report_submitted' for e in events)
        failure = next(e['payload'] for e in events if e['type'] == 'report_hook_failed')
        assert failure['reason'] == ('policy_steps exhausted' if limit == 'policy_steps' else 'Episode deadline exhausted')
        assert failure['actor_turn'] == 1 and failure['original_answer_retained']
        assert next(e['payload']['raw'] for e in events if e['type'] == 'actor_output') == raw
    finally:
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('error', [StopRequested, asyncio.CancelledError])
async def test_report_finalization_never_swallows_stop_or_cancellation(tmp_path, error):
    context, _, _, raw, store = context_for(tmp_path, [{'op': 'read_order'}])

    async def interrupted(*args): raise error()
    context.interpreter.invoke = interrupted
    try:
        with pytest.raises(error):
            await Actor()(context.broker.journal.intent, context)
        events = store.events('episode-test')['events']
        assert next(e['payload']['raw'] for e in events if e['type'] == 'actor_output') == raw
        assert not any(e['type'] in ('report_submitted', 'report_hook_failed') for e in events)
    finally:
        store.close()


@pytest.mark.anyio
async def test_saved_development_failure_finishes_original_report_in_a_fresh_world(tmp_path):
    """Captured policy/answers, real broker/referee/world, no provider generation."""
    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/report_hook_closed_business.json').read_text())
    sim = create_app(database_dir=tmp_path / 'worlds', control_token='test')
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=sim), base_url='http://127.0.0.1:8001')
    coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path / 'lab'), wandb_model='openai/gpt-oss-120b'))
    campaign = coordinator.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-1', mode='baseline', config_profile_id='live-v1'))
    candidate = CandidatePolicy.model_validate_json(canonical_json(fixture['policy']))
    policy = coordinator.policies.proposal(candidate, parent='policy-v0', raw=canonical_json(fixture['policy']), episode_ids=[])
    requests = []
    raw_outputs = []

    class RecordedAnswers:
        async def complete(self, messages, **kwargs):
            intent = json.loads(messages[1]['content'])['task']
            raw = fixture['outputs'][len(requests)].replace(fixture['original_upgrade_operation_id'], intent['upgrade_operation_id'])
            requests.append((messages, kwargs)); raw_outputs.append(raw)
            return RuntimeGeneration(raw, campaign.model)

    try:
        trial = await EpisodeRunner(coordinator.store, WorldClient('http://127.0.0.1:8001', 'test', client=client), RecordedAnswers()).run(
            campaign, FaultSpec.model_validate_json(canonical_json(fixture['recipe'])), policy,
            purpose='completion_study', arm='L', source_mode='offline_fixture', actor_context_protocol=ACTOR_CONTEXT_PROTOCOL_V4)
        episode = coordinator.store.get_record('episodes', trial.episode_id)
        events = coordinator.store.events(trial.episode_id)['events']
        assert trial.outcome == 'SAFE_UNRESOLVED' and trial.failed_checks == []
        assert len(requests) == trial.usage.actor_calls == 3
        assert trial.usage.http_attempts == 6 and trial.usage.ticks == 7
        assert trial.usage.policy_steps == 10
        assert episode['verdict']['upgrade_effects'] == episode['verdict']['notification_effects'] == 0
        submitted = next(e['payload'] for e in events if e['type'] == 'report_submitted')
        assert submitted['emitted_report'] == json.loads(raw_outputs[-1])['report']
        assert [e['payload']['raw'] for e in events if e['type'] == 'actor_output'] == raw_outputs
        assert len(episode['report']['evidence_ids']) == 6
        assert any(e['type'] == 'policy_step' and e['payload'].get('skip_reason') == 'BUSINESS_CALLS_CLOSED' for e in events)
        assert coordinator.store.get_record('campaigns', campaign.campaign_id)['active_policy_version'] == 'policy-v0'
    finally:
        await client.aclose()
        await coordinator.close()
