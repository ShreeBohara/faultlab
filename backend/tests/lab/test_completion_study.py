"""Offline plumbing evidence, never model-performance or remote-service evidence.

The Actor deliberately keeps polling UNKNOWN notifications; the Mechanic returns
a handwritten fixture. Real episode execution, simulator state and C1–C8 remain
in use. ASGI does not model a real socket timeout, which live manual checks cover.
"""
import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import httpx
import pytest

from app.adapters.business_tools import WorldClient
from app.contracts.models import CampaignRequest, TrialResult, Usage, canonical_json, content_hash
from app.lab.budgets import BudgetExhausted, CampaignLedger
from app.lab.completion_study import (
    MODEL_CALL_RESERVATION, SCHEMA, assess_pairs, case_manifest, planned_slots,
    queue_completion_study,
)
from app.lab.coordinator import LabCoordinator
from app.lab.evidence import EvidenceContext, EvidenceDenied, EvidenceGateway, WaitingEvidence
from app.lab.runner import EpisodeRunner
from app.lab.storage import StoreConflict
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError
from app.simulator.main import create_app
from app.config import Settings
from app.telemetry.evaluations import EvaluationPublisher
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.tracing import TraceRecorder
from test_baseline_study import BaselineFixtureProvider, StudyRemoteDouble, settings


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def fixture_candidate(parent='policy-v0', *, useful=True):
    steps = [{'op': 'read_notification_operation'}]
    if useful:
        steps.append({'op': 'retry_original_request', 'service': 'notifications',
                      'only_if': 'notification_outcome_uncertain'})
    return {'candidate': {'scope': 'orders.upgrade_then_confirm/v1',
            'parent_version': parent, 'rules': [{'hook': 'after_notification_response',
            'when': 'notification_outcome_uncertain', 'steps': steps}]},
            'explanation': 'Handwritten offline fixture, not a learned result.'}


class CompletionFixtureProvider(BaselineFixtureProvider):
    def __init__(self, *, useful=True, broken_actor=False, invalid_mechanic=False, recover_baseline=False):
        super().__init__()
        self.useful = useful
        self.broken_actor = broken_actor
        self.invalid_mechanic = invalid_mechanic
        self.recover_baseline = recover_baseline
        self.mechanic_inputs = []
        self.dispatch_roles = []

    async def complete(self, messages, **kwargs):
        role = kwargs.get('role', 'actor')
        self.dispatch_roles.append(role)
        if role == 'mechanic':
            self.calls += 1
            context = json.loads(messages[1]['content'])
            self.mechanic_inputs.append(deepcopy(context))
            output = '{}' if self.invalid_mechanic else canonical_json(
                fixture_candidate(context['parent_version'], useful=self.useful))
            return RuntimeGeneration(output, 'openai/gpt-oss-120b',
                input_tokens=100, output_tokens=30, cost_usd=.0001)
        if self.broken_actor:
            self.calls += 1
            raise RuntimeProviderError('Offline provider failure', code='HTTP_ERROR')
        history = json.loads(messages[-1]['content'])
        results = [o['result'] for o in history['observations']]
        attempted = any(r['tool'] == 'send_confirmation' for r in results)
        has_receipt = any(isinstance(r.get('data'), dict)
            and r['data'].get('service') == 'notifications' and r['data'].get('receipt')
            for r in results)
        if attempted and not has_receipt and not history['final_report_required'] and not self.recover_baseline:
            self.calls += 1
            return RuntimeGeneration(canonical_json({'kind': 'tool',
                'tool': 'get_operation_status', 'arguments': {'service': 'notifications'}}),
                'openai/gpt-oss-120b', input_tokens=100, output_tokens=30, cost_usd=.0001)
        return await super().complete(messages, **kwargs)


async def harness(tmp_path, provider=None):
    coordinator = LabCoordinator(settings(tmp_path))
    campaign = coordinator.create(CampaignRequest(task_text='Upgrade and confirm',
        order_id='order-completion', mode='baseline', config_profile_id='live-v1'))
    simulator = create_app(database_dir=tmp_path/'worlds', control_token='offline-test', settings=Settings())
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator),
                              base_url='http://127.0.0.1:8001')
    provider = provider or CompletionFixtureProvider()
    remote = StudyRemoteDouble()
    outbox = TelemetryOutbox(coordinator.store)
    trace = TraceRecorder(remote, outbox)
    coordinator.runner = EpisodeRunner(coordinator.store,
        WorldClient('http://127.0.0.1:8001', 'offline-test', client=client), provider, trace=trace)
    coordinator.evidence_gateway = EvidenceGateway(coordinator.store, 'entity/project',
        trace=trace, worker=remote)
    coordinator.evaluation_publisher = EvaluationPublisher(remote, outbox)
    return coordinator, campaign, provider, remote, client


async def finish(coordinator, campaign):
    queued = await queue_completion_study(coordinator, campaign.campaign_id)
    await coordinator.tasks[queued['study_id']]
    return coordinator.store.get_record('completion_studies', queued['study_id'])


@pytest.mark.anyio
async def test_real_runner_recovers_with_exact_identity_without_acceptance_or_validation_feedback(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        queued = await queue_completion_study(c, campaign.campaign_id)
        assert queued['status'] == 'QUEUED' and provider.calls == 0
        assert len(queued['slots']) == 60 and len({s['episode_id'] for s in queued['slots']}) == 60
        assert MODEL_CALL_RESERVATION == 484
        assert c.ledgers[campaign.campaign_id].reserved_calls == 1064 + 484
        planned = c.store.get_record('completion_plans', queued['study_id'])
        assert all(s['status'] == 'NOT_ATTEMPTED' for s in planned['slots'])
        await c.tasks[queued['study_id']]
        result = c.store.get_record('completion_studies', queued['study_id'])
        assert result['decision'] == 'OBSERVED_IMPROVEMENT', result
        assert result['status'] == 'COMPLETED' and result['ordinary_policy_accepted'] is False
        assert len(result['trial_rows']) == 54
        assert len({r['trial']['world_id'] for r in result['trial_rows']}) == 54
        assert len({r['trial']['episode_id'] for r in result['trial_rows']}) == 54
        assert set(result['evidence'].values()) == {'weave_verified'} and len(result['evidence']) == 54
        assert provider.calls == result['charged_model_calls'] <= 484
        assert result['usage']['model_calls'] == provider.calls
        assert result['usage']['input_tokens'] == provider.calls * 100
        assert result['usage']['output_tokens'] == provider.calls * 30
        assert result['usage']['cost_dollars'] == pytest.approx(provider.calls * .0001)
        assert result['conservative_charge_bound'] == pytest.approx(
            c.ledgers[campaign.campaign_id].used_dollar_upper_bound)
        assert len(provider.mechanic_inputs) == 1
        assert sum(s['status'] == 'NOT_ATTEMPTED' for s in result['slots']) == 6
        assert c.store.get_record('completion_plans', queued['study_id']) == planned
        assert c.get(campaign.campaign_id).active_policy_version == 'policy-v0'
        assert c.store.get_pointer('active-policy:' + campaign.campaign_id) == 'policy-v0'
        assert c.store.get_pointer('accepted-policy:' + campaign.configuration_hash) is None
        assert not c.store.list_records('promotion_decisions')
        assert all(p.decision != 'ACCEPTED' for p in c.policies.list())
        assert c.policies.get(result['selected_candidate_version']).decision == 'PROPOSED'
        assert c.active_id is None and c.ledgers[campaign.campaign_id].reserved_calls == 1064

        observed = result['validation_assessment']['by_case']
        assert observed['notification-2']['B0']['safe_unresolved'] == 3
        assert observed['notification-2']['L']['completed'] == 3
        assert observed['notification-3']['L']['completed'] == 3
        assert observed['notification-18']['L']['safe_unresolved'] == 3
        assert observed['terminal-upgrade-rejection']['L']['correctly_rejected'] == 3
        assert all(v['L']['violations'] == 0 for v in observed.values())

        control_ids = {r['trial']['episode_id'] for r in result['trial_rows'] if r['stage'] == 'controls'}
        validation_ids = {r['trial']['episode_id'] for r in result['trial_rows'] if r['stage'] == 'validation'}
        supplied = provider.mechanic_inputs[0]
        assert supplied['objective'] == SCHEMA
        assert {e['episode_id'] for e in supplied['development_evidence']['episodes']} == control_ids
        # The adjudicated outcome is bound to each episode row, and it is exactly the
        # value the grouped observed_outcomes already carried - no new disclosure.
        assert supplied['development_evidence']['format'] == 'faultlab-compact-evidence/v2-task-outcome'
        control_outcomes = {r['trial']['episode_id']: r['trial']['outcome']
                            for r in result['trial_rows'] if r['stage'] == 'controls'}
        assert {e['episode_id']: e['task_outcome'] for e in supplied['development_evidence']['episodes']} == control_outcomes
        assert set(control_outcomes.values()) >= {'SAFE_UNRESOLVED', 'COMPLETED'}
        grouped = {o['outcome'] for o in supplied['observed_outcomes']}
        assert set(control_outcomes.values()) <= grouped
        assert not validation_ids.intersection(canonical_json(supplied).split('"'))
        assert 'validation_assessment' not in supplied and 'manifest' not in supplied
        for row in result['trial_rows']:
            trial = row['trial']; episode = c.store.get_record('episodes', trial['episode_id'])
            assert episode['study_id'] == episode['evidence_context_id'] == result['study_id']
            assert episode['report'] is not None and episode['split'] == 'development'
            assert episode['experiment_purpose'] == 'completion_study'
            assert episode['origin'] == 'faultlab_evaluation'
            assert trial['usage']['actor_calls'] <= 8 and trial['usage']['http_attempts'] <= 18
            assert trial['usage']['ticks'] <= 20 and trial['usage']['policy_steps'] <= 32
            with pytest.raises(EvidenceDenied):
                c.evidence_gateway.authorize(trial['episode_id'], EvidenceContext(
                    campaign.campaign_id, campaign.campaign_id, campaign.campaign_id))
            if row['stage'] != 'validation' or row['case_id'] != 'notification-2' or trial['arm'] != 'L':
                continue
            # Compare real journal, physical effects and the original report.
            eid = trial['episode_id']
            intent = c.store.get_record('private_episode_inputs', eid)['intent']
            journal = c.store.get_record('journals', eid + ':' + intent['notification_operation_id'])
            assert len(journal['attempt_ids']) == 3
            request = json.loads(journal['original_request'])
            assert request['operation_id'] == intent['notification_operation_id']
            assert request['idempotency_key'] == intent['notification_idempotency_key']
            assert content_hash(request) == journal['payload_hash']
            snapshot = c.store.get_record('private_snapshots', eid)['horizon']
            assert len(snapshot['notifications']) == 1
            effect = snapshot['notifications'][0]
            assert effect['operation_id'] == request['operation_id']
            assert effect['payload_hash'] == journal['payload_hash']
            assert episode['report']['overall'] == 'COMPLETED'
            calls = [r for r in c.store.list_records('tool_calls') if r['episode_id'] == eid]
            assert any(r['tool'] == 'send_confirmation' and r['caller'] == 'policy'
                       and r['hook'] == 'after_notification_response' for r in calls)
        assert remote.operations[0] == 'evaluation_init'
        from app.lab.exports import development_recording
        exported = development_recording(c.store, campaign.campaign_id)
        assert exported['completion_studies'] == [result]
        assert len(exported['episodes']) == 54
        assert 'private_snapshots' not in exported and 'private_episode_inputs' not in exported
        partial = development_recording(c.store, campaign.campaign_id,
                                        episode_ids=[next(iter(control_ids))])
        assert partial['completion_studies'] == [] and len(partial['episodes']) == 1
        with pytest.raises(StoreConflict):
            await queue_completion_study(c, campaign.campaign_id)
    finally:
        await client.aclose()
        await c.close()


def pair_rows(cases):
    rows = []
    for case in cases:
        for index in range(3):
            for arm in ('B0', 'L'):
                suffix = f"{case['case_id']}-{index}-{arm}"
                outcome = case['expected_outcome']
                if arm == 'B0' and case['case_id'] == 'notification-2':
                    outcome = 'SAFE_UNRESOLVED'
                trial = TrialResult(episode_id='episode-' + suffix, world_id='world-' + suffix,
                    scenario_hash=content_hash(case['fault_spec']), policy_hash=('a' if arm == 'B0' else 'b')*64,
                    arm=arm, trial_index=index, lifecycle='COMPLETED', outcome=outcome,
                    failed_checks=[], fault_scheduled=bool(case['fault_spec']['primitives']),
                    fault_triggered=bool(case['fault_spec']['primitives']), usage=Usage())
                rows.append({'case_id': case['case_id'], 'trial': trial})
    return rows


@pytest.mark.parametrize('corruption', ['missing', 'extra', 'duplicate_identity', 'wrong_scenario',
    'wrong_policy', 'wrong_index', 'untriggered', 'masked_fault', 'lab_error'])
def test_exact_pair_gate_rejects_incomplete_or_mismatched_evidence(corruption):
    cases = case_manifest()['cases']; rows = pair_rows(cases)
    idx = next(i for i, r in enumerate(rows) if r['case_id'] == 'notification-2' and r['trial'].arm == 'L')
    if corruption == 'missing': rows.pop(idx)
    elif corruption == 'extra': rows.append(deepcopy(rows[idx]))
    else:
        changes = {'duplicate_identity': {'world_id': rows[0]['trial'].world_id},
            'wrong_scenario': {'scenario_hash': 'c'*64}, 'wrong_policy': {'policy_hash': 'c'*64},
            'wrong_index': {'trial_index': 2}, 'untriggered': {'fault_triggered': False},
            'masked_fault': {'fault_scheduled': False, 'fault_triggered': False},
            'lab_error': {'lifecycle': 'LAB_ERROR', 'outcome': 'LAB_ERROR'}}[corruption]
        rows[idx]['trial'] = rows[idx]['trial'].model_copy(update=changes)
    assert assess_pairs(rows, cases, 'a'*64, 'b'*64, validation=True)['decision'] == 'INCOMPLETE'


@pytest.mark.parametrize('case_id,outcome,checks', [('notification-2', 'SAFE_UNRESOLVED', []),
    ('healthy', 'SAFE_UNRESOLVED', []), ('terminal-upgrade-rejection', 'SAFE_UNRESOLVED', []),
    ('notification-3', 'VIOLATION', ['C6'])])
def test_no_favorable_aggregate_hides_candidate_error_or_case_regression(case_id, outcome, checks):
    cases = case_manifest()['cases']; rows = pair_rows(cases)
    row = next(r for r in rows if r['case_id'] == case_id and r['trial'].arm == 'L')
    row['trial'] = row['trial'].model_copy(update={'outcome': outcome, 'failed_checks': checks})
    assert assess_pairs(rows, cases, 'a'*64, 'b'*64, validation=True)['decision'] == 'NO_CHANGE'


@pytest.mark.anyio
@pytest.mark.parametrize('variant,expected_trials,expected_requests', [('duplicate', 12, 2), ('invalid', 6, 4), ('no_gap', 6, 0)])
async def test_proposal_caps_duplicate_no_retest_and_no_gap_stops(tmp_path, variant, expected_trials, expected_requests):
    provider = CompletionFixtureProvider(useful=variant != 'duplicate', invalid_mechanic=variant == 'invalid',
                                         recover_baseline=variant == 'no_gap')
    c, campaign, provider, _, client = await harness(tmp_path, provider)
    try:
        result = await finish(c, campaign)
        assert result['status'] == 'COMPLETED' and result['decision'] == 'NO_CHANGE', result
        assert len(result['trial_rows']) == expected_trials
        assert len(provider.mechanic_inputs) == expected_requests
        assert not any(r['stage'] == 'validation' for r in result['trial_rows'])
        if variant == 'duplicate':
            assert result['candidates'][1]['decision'] == 'DUPLICATE'
            assert all(s['status'] == 'NOT_ATTEMPTED' for s in result['slots'] if s['stage'] == 'candidate-2')
            assert len(provider.mechanic_inputs[-1]['development_evidence']['episodes']) == 12
        assert c.get(campaign.campaign_id).active_policy_version == 'policy-v0'
    finally:
        await client.aclose(); await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('failure', ['provider', 'untriggered', 'evidence'])
async def test_failed_attempt_retained_without_replacement_and_reservation_released(tmp_path, failure):
    c, campaign, provider, _, client = await harness(tmp_path, CompletionFixtureProvider(broken_actor=failure == 'provider'))
    try:
        if failure == 'untriggered':
            run = c.runner.run
            async def untriggered(*args, **kwargs):
                return (await run(*args, **kwargs)).model_copy(update={'fault_triggered': False})
            c.runner.run = untriggered
        if failure == 'evidence':
            c.evidence_gateway.get = AsyncMock(side_effect=WaitingEvidence('offline missing trace'))
        result = await finish(c, campaign)
        if failure == 'untriggered':
            # Declared change: an uninformative trial is retained, never replaced,
            # and never aborts the batch. Every control still ran; the gap is then
            # judged on the valid controls only, and here none of them are valid.
            assert len(result['trial_rows']) == len(c.store.list_records('episodes')) == 6
            assert all(s['status'] == 'COMPLETED' for s in result['slots'][:6])
            # Only the fault-bearing source controls become uninformative; the
            # healthy controls schedule no fault, so they stay valid.
            assert len(result['retained_invalid_slots']) == 3
            assert result['control_assessment']['valid_source'] == 0
            assert result['control_assessment']['valid_healthy'] == 3
            assert result['status'] == 'COMPLETED' and result['decision'] == 'NO_CHANGE'
            assert 'valid controls' in result['reason']
            assert c.get(campaign.campaign_id).state == 'COMPLETED'
        else:
            assert result['status'] == result['decision'] == 'INCOMPLETE'
            assert len(result['trial_rows']) == len(c.store.list_records('episodes')) == 1
            assert len([s for s in result['slots'] if s['status'] != 'NOT_ATTEMPTED']) == 1
            assert c.get(campaign.campaign_id).state == 'ERROR'
        # No proposal is ever requested when the declared controls do not hold.
        assert not provider.mechanic_inputs
        assert c.active_id is None and c.ledgers[campaign.campaign_id].reserved_calls == 1064
        with pytest.raises(StoreConflict): await queue_completion_study(c, campaign.campaign_id)
    finally:
        await client.aclose(); await c.close()


@pytest.mark.anyio
async def test_cancelled_inflight_mechanic_charge_retained_without_followup_or_acceptance(tmp_path):
    class WaitingMechanic(CompletionFixtureProvider):
        def __init__(self):
            super().__init__(); self.started = asyncio.Event()
        async def complete(self, messages, **kwargs):
            if kwargs.get('role') == 'mechanic':
                self.calls += 1; self.started.set()
                await asyncio.Future()
            return await super().complete(messages, **kwargs)
    provider = WaitingMechanic()
    c, campaign, _, _, client = await harness(tmp_path, provider)
    try:
        queued = await queue_completion_study(c, campaign.campaign_id)
        await asyncio.wait_for(provider.started.wait(), 10)
        await c.stop(campaign.campaign_id)
        c.tasks[queued['study_id']].cancel()
        await c.tasks[queued['study_id']]
        result = c.store.get_record('completion_studies', queued['study_id'])
        assert result['status'] == 'INTERRUPTED' and result['decision'] == 'INCOMPLETE'
        assert len(result['trial_rows']) == 6 and len(c.store.list_records('episodes')) == 6
        assert result['charged_model_calls'] == result['usage']['model_calls'] == provider.calls
        assert result['usage']['input_tokens'] == (provider.calls - 1) * 100
        assert result['usage']['cost_dollars'] is None
        assert c.ledgers[campaign.campaign_id].unknown_token_calls == 1
        assert c.ledgers[campaign.campaign_id].unknown_cost_calls == 1
        assert c.ledgers[campaign.campaign_id].reserved_calls == 1064 and c.active_id is None
        assert len(c.policies.list()) == 1 and not result['candidates']
        assert c.get(campaign.campaign_id).active_policy_version == 'policy-v0'
    finally:
        await client.aclose(); await c.close()


@pytest.mark.anyio
async def test_read_only_api_explicit_execution_gate_and_stop_before_dispatch(tmp_path):
    from app.main import create_app as backend_app
    c = LabCoordinator(settings(tmp_path)); campaign = c.create(CampaignRequest(task_text='Upgrade',
        order_id='order-1', mode='baseline', config_profile_id='live-v1'))
    called = []
    async def forbidden(*args):
        called.append('runner'); raise AssertionError('Dispatch after stop')
    c._get_runner = forbidden; c.require_simulator = AsyncMock()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app(coordinator=c)),
                                base_url='http://127.0.0.1:8000') as client:
        path = f'/api/campaigns/{campaign.campaign_id}/completion-study'
        for body in ({}, {'execute_live': False}, {'execute_live': True, 'unknown': 'value'}):
            assert (await client.post(path, json=body)).status_code == 422
        assert not called and not c.store.list_records('completion_studies')
        assert (await client.get(f'/api/campaigns/{campaign.campaign_id}/completion-studies')).json() == []
        queued = await queue_completion_study(c, campaign.campaign_id)
        await c.stop(campaign.campaign_id); await c.tasks[queued['study_id']]
        result = (await client.get('/api/completion-studies/' + queued['study_id'])).json()
        assert result['status'] == 'INTERRUPTED' and result['decision'] == 'INCOMPLETE'
        assert not result['trial_rows'] and not called
        for _ in range(2):
            assert (await client.get('/api/completion-studies/' + queued['study_id'])).json() == result
        assert not c.store.list_records('episodes') and not called
        assert (await client.get('/api/completion-studies/missing')).status_code == 404
    await c.close()


@pytest.mark.anyio
async def test_active_budget_and_changed_configuration_reject_before_work(tmp_path):
    c = LabCoordinator(settings(tmp_path)); campaign = c.create(CampaignRequest(task_text='Upgrade',
        order_id='order-1', mode='baseline', config_profile_id='live-v1'))
    c.require_simulator = AsyncMock(); c.active_id = 'other'
    with pytest.raises(StoreConflict): await queue_completion_study(c, campaign.campaign_id)
    c.active_id = None
    ledger = CampaignLedger(c.store, campaign.campaign_id, campaign.caps,
                           dollar_bounds=c.settings.model_call_dollar_bounds)
    c.ledgers[campaign.campaign_id] = ledger
    ledger.reserve('other-batch', campaign.caps.model_calls - 1064 - 100)
    with pytest.raises(BudgetExhausted): await queue_completion_study(c, campaign.campaign_id)
    ledger.release('other-batch')
    c.validate_core_configuration = lambda campaign: (_ for _ in ()).throw(StoreConflict('changed source'))
    with pytest.raises(StoreConflict): await queue_completion_study(c, campaign.campaign_id)
    assert not c.store.list_records('completion_plans') and not c.store.list_records('completion_studies')
    assert c.active_id is None and not c.tasks and not c.store.list_records('episodes')
    await c.close()


@pytest.mark.anyio
async def test_restart_preserves_attempted_slots_and_never_replays(tmp_path):
    configured = settings(tmp_path); c = LabCoordinator(configured)
    campaign = c.create(CampaignRequest(task_text='Upgrade', order_id='order-1', mode='baseline',
                                        config_profile_id='live-v1'))
    slots = planned_slots(case_manifest()); slots[0]['status'] = 'COMPLETED'; slots[1]['status'] = 'RUNNING'
    saved = {'study_id': 'completion-study-restart', 'campaign_id': campaign.campaign_id,
             'status': 'RUNNING', 'decision': 'PENDING', 'slots': slots, 'trial_rows': []}
    c.store.put_record('completion_studies', saved['study_id'], saved)
    c.transition(campaign.campaign_id, 'RUNNING'); c.store.close()
    restarted = LabCoordinator(configured)
    try:
        result = restarted.store.get_record('completion_studies', saved['study_id'])
        assert result['status'] == 'INTERRUPTED' and result['decision'] == 'INCOMPLETE'
        assert [s['status'] for s in result['slots'][:3]] == ['COMPLETED', 'INTERRUPTED', 'NOT_ATTEMPTED']
        assert not restarted.tasks and not restarted.store.list_records('episodes')
        assert restarted.get(campaign.campaign_id).state == 'STOPPED'
        assert restarted.store.get_pointer('active-policy:' + campaign.campaign_id) == 'policy-v0'
        with pytest.raises(StoreConflict): await queue_completion_study(restarted, campaign.campaign_id)
    finally:
        await restarted.close()


@pytest.mark.parametrize('mode', ['unconfirmed', 'status', 'execute'])
def test_cli_completion_is_explicit_and_saved_status_only_reads(monkeypatch, mode):
    from app.cli import client
    calls = []
    def request(method, path, body=None):
        calls.append((method, path, body))
        return {'study_id': 'completion-study-test', 'status': 'COMPLETED'}
    monkeypatch.setattr(client, 'request', request)
    monkeypatch.setattr(client, 'print_json', lambda value: None)
    args = ['faultlab', 'completion-study']
    args += ['--status', 'completion-study-test'] if mode == 'status' else ['--campaign', 'campaign-test']
    if mode == 'execute': args += ['--execute-live']
    monkeypatch.setattr('sys.argv', args)
    if mode == 'unconfirmed':
        with pytest.raises(SystemExit): client.main()
        assert calls == []
    else:
        assert client.main() == 0
        expected = ('GET', '/api/completion-studies/completion-study-test', None) if mode == 'status' else (
            'POST', '/api/campaigns/campaign-test/completion-study', {'execute_live': True})
        assert calls == [expected]


@pytest.mark.anyio
async def test_search_projection_and_export_preserve_original_and_admitted_selection_without_calls(tmp_path):
    from app.main import create_app as backend_app
    from app.lab.exports import development_recording
    c = LabCoordinator(settings(tmp_path)); campaign = c.create(CampaignRequest(task_text='Upgrade',
        order_id='order-1', mode='baseline', config_profile_id='live-v1'))
    context = {'campaign_id': campaign.campaign_id, 'configuration_hash': campaign.configuration_hash,
        'policy_hash': c.policies.baseline().policy_hash, 'selection_index': 2, 'development_history': []}
    row = {'selection_id': 'selection-admitted', 'context': context, 'challenge': False,
        'model_id': campaign.model, 'raw': 'Original proposal remains distinct', 'valid': True,
        'error': None, 'provenance': 'model', 'output': {'hypothesis': 'original'},
        'selected_output': None, 'search_decision': {'status': 'SKIPPED_DUPLICATE'},
        'usage': {'model_calls': 1, 'input_tokens': 100, 'output_tokens': 20}}
    c.store.put_record('selections', row['selection_id'], row, immutable=True)
    for name, extra in [('challenge', {}), ('foreign', {'campaign_id': 'another-campaign'}),
                        ('study', {'study_id': 'separate-study'}), ('old_config', {'configuration_hash': '0'*64})]:
        changed = {**row, 'selection_id': 'selection-' + name, 'context': {**context, **extra}}
        if name == 'challenge': changed['challenge'] = True
        c.store.put_record('selections', changed['selection_id'], changed, immutable=True)
    c._get_runner = AsyncMock(side_effect=AssertionError('Read request dispatched'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app(coordinator=c)),
                                base_url='http://127.0.0.1:8000') as client:
        response = await client.get(f'/api/campaigns/{campaign.campaign_id}/search-attempts')
        assert response.status_code == 200
        projected = response.json()
        assert len(projected) == 1 and projected[0]['selection_ref'] == row['selection_id']
        assert projected[0]['raw_response'] == row['raw']
        assert projected[0]['output'] == row['output'] and projected[0]['selected_output'] is None
        assert projected[0]['search_decision'] == row['search_decision']
    exported = development_recording(c.store, campaign.campaign_id)
    admitted = next(s for s in exported['selections'] if s['selection_id'] == row['selection_id'])
    assert admitted['raw'] == row['raw'] and admitted['output'] == row['output']
    assert admitted['selected_output'] is None and admitted['search_decision'] == row['search_decision']
    assert not any(s['selection_id'] == 'selection-foreign' for s in exported['selections'])
    assert not c._get_runner.called and not c.store.list_records('episodes')
    await c.close()


@pytest.mark.anyio
async def test_one_uninformative_control_does_not_abort_the_batch_or_relax_qualification(tmp_path):
    """The Phase 3 B2 failure mode, and the gate that must survive the fix."""
    c, campaign, provider, _, client = await harness(tmp_path)
    try:
        run = c.runner.run
        spoiled = {'done': False}
        async def one_untriggered(*args, **kwargs):
            trial = await run(*args, **kwargs)
            # Spoil exactly the third source control, as Phase 3 B2's fifth trial was.
            if not spoiled['done'] and kwargs.get('trial_index') == 2 and trial.fault_scheduled:
                spoiled['done'] = True
                return trial.model_copy(update={'fault_triggered': False})
            return trial
        c.runner.run = one_untriggered
        result = await finish(c, campaign)
        # The batch ran on past the spoiled control and still reached a proposal.
        assert len(result['retained_invalid_slots']) == 1
        assert result['control_assessment']['valid_source'] == 2
        assert result['control_assessment']['source_completions'] == 0
        assert len(result['trial_rows']) > 6 and provider.mechanic_inputs
        # And the acceptance gate is untouched: exact valid pairs are still required.
        source = next(case for case in result['manifest']['cases']
                      if case['case_id'] == result['manifest']['source_case_id'])
        rows = [{'case_id': r['case_id'], 'trial': TrialResult.model_validate(r['trial'])}
                for r in result['trial_rows'] if r['stage'] == 'candidate-1']
        assert assess_pairs(rows, [source], result['incumbent_hash'],
                            result['candidates'][0]['policy_hash'])['decision'] == 'SOURCE_QUALIFIED'
        spoilt = [dict(r, trial=TrialResult.model_validate(r['trial']).model_copy(
            update={'fault_triggered': False})) if i == 0 else
            {'case_id': r['case_id'], 'trial': TrialResult.model_validate(r['trial'])}
            for i, r in enumerate(r2 for r2 in result['trial_rows'] if r2['stage'] == 'candidate-1')]
        assert assess_pairs(spoilt, [source], result['incumbent_hash'],
                            result['candidates'][0]['policy_hash'])['decision'] == 'INCOMPLETE'
    finally:
        await client.aclose(); await c.close()


@pytest.mark.anyio
async def test_declared_control_protocol_restores_the_preserved_presentation(tmp_path):
    """The Phase 9 concurrent control must reproduce the Phase 5/6 evidence exactly,
    in EVERY proposal slot, not just the first."""
    from app.lab.diagnosis import COMPACT_EVIDENCE_V1
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        queued = await queue_completion_study(c, campaign.campaign_id,
                                              evidence_protocol=COMPACT_EVIDENCE_V1)
        assert queued['evidence_protocol'] == COMPACT_EVIDENCE_V1
        await c.tasks[queued['study_id']]
        assert provider.mechanic_inputs, 'the study must have reached a proposal'
        for index, supplied in enumerate(provider.mechanic_inputs):
            evidence = supplied['development_evidence']
            assert evidence['format'] == COMPACT_EVIDENCE_V1, f'slot {index + 1} switched presentation'
            assert all('task_outcome' not in e for e in evidence['episodes'])
            assert 'task_outcome' not in evidence['interpretation']
            # The control still receives the grouped outcomes it always received, so the
            # arms differ only in where the verdict appears, not in whether it is supplied.
            assert {g['outcome'] for g in supplied['observed_outcomes']}
        assert c.store.get_record('completion_studies',
                                  queued['study_id'])['evidence_protocol'] == COMPACT_EVIDENCE_V1
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_default_treatment_protocol_holds_in_every_proposal_slot(tmp_path):
    """Slot 2 builds its evidence from controls PLUS feedback rows; a presentation that
    silently reverted there would corrupt the arm without failing any other test."""
    from app.lab.diagnosis import COMPACT_EVIDENCE_V2
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        queued = await queue_completion_study(c, campaign.campaign_id)
        assert queued['evidence_protocol'] == COMPACT_EVIDENCE_V2
        await c.tasks[queued['study_id']]
        assert len(provider.mechanic_inputs) >= 1
        for index, supplied in enumerate(provider.mechanic_inputs):
            evidence = supplied['development_evidence']
            assert evidence['format'] == COMPACT_EVIDENCE_V2, f'slot {index + 1} switched presentation'
            assert all('task_outcome' in e for e in evidence['episodes'])
            grouped = {g['outcome'] for g in supplied['observed_outcomes']}
            per_episode = {e['task_outcome'] for e in evidence['episodes']}
            # Presentation, not disclosure: every per-episode value was already grouped.
            assert per_episode <= grouped
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_unknown_protocol_is_refused_before_any_state_or_reservation_is_taken(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        ledger_before = c.ledgers.get(campaign.campaign_id)
        reserved_before = dict(ledger_before.reservations) if ledger_before else {}
        with pytest.raises(StoreConflict):
            await queue_completion_study(c, campaign.campaign_id,
                                         evidence_protocol='faultlab-compact-evidence/v3-invented')
        ledger_after = c.ledgers.get(campaign.campaign_id)
        assert (dict(ledger_after.reservations) if ledger_after else {}) == reserved_before
        assert not c.store.list_records('completion_studies')
        assert not c.store.list_records('completion_plans')
        assert c.active_id is None
        assert c.get(campaign.campaign_id).state == 'IDLE'
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_http_route_carries_the_declared_protocol_end_to_end(tmp_path):
    """The paid runner reaches the study through this route and nothing else."""
    from app.lab.diagnosis import COMPACT_EVIDENCE_V1, COMPACT_EVIDENCE_V2
    from fastapi import FastAPI
    from app.lab.api import create_router
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        app = FastAPI(); app.include_router(create_router(lambda: c))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://lab') as http:
            response = await http.post(f'/api/campaigns/{campaign.campaign_id}/completion-study',
                                       json={'execute_live': True,
                                             'evidence_protocol': COMPACT_EVIDENCE_V1})
            assert response.status_code == 202, response.text
            body = response.json()
            assert body['evidence_protocol'] == COMPACT_EVIDENCE_V1
            await c.tasks[body['study_id']]
            assert provider.mechanic_inputs[0]['development_evidence']['format'] == COMPACT_EVIDENCE_V1
            status = await http.get(f"/api/completion-studies/{body['study_id']}")
            assert status.json()['evidence_protocol'] == COMPACT_EVIDENCE_V1
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_http_route_rejects_an_unknown_protocol_without_starting_work(tmp_path):
    from fastapi import FastAPI
    from app.lab.api import create_router
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        app = FastAPI(); app.include_router(create_router(lambda: c))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://lab') as http:
            response = await http.post(f'/api/campaigns/{campaign.campaign_id}/completion-study',
                                       json={'execute_live': True,
                                             'evidence_protocol': 'faultlab-compact-evidence/v9'})
            assert response.status_code >= 400
            assert not c.store.list_records('completion_studies')
            assert c.active_id is None
    finally:
        await client.aclose()


def test_primary_read_out_classifies_every_candidate_shape_as_declared():
    """The Phase 9 primary read-out, checked against every state a candidate can hold.

    A refusal and an invalid output are draws that do not contain the step; treating them
    as 'no draw' would resample a real Mechanic answer. Only an absent or unresolved
    candidate yields no draw.
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / 'scripts/experiments'))
    from run_replication import first_proposal_draw
    step = {'rules': [{'hook': 'after_notification_response', 'steps': [
        {'op': 'retry_original_request', 'service': 'notifications'}]}]}
    wrong_service = {'rules': [{'hook': 'after_upgrade_response', 'steps': [
        {'op': 'retry_original_request', 'service': 'orders'}]}]}
    assert first_proposal_draw({'candidates': []}) is None
    assert first_proposal_draw({'candidates': [{'decision': 'PROPOSED', 'raw_outputs': ['x']}]}) is None
    assert first_proposal_draw({'candidates': [{'decision': 'NO_CHANGE', 'reason': 'declines'}]}) is False
    assert first_proposal_draw({'candidates': [{'decision': 'REJECTED', 'reason': 'invalid'}]}) is False
    assert first_proposal_draw({'candidates': [{'content': {'rules': []}}]}) is False
    assert first_proposal_draw({'candidates': [{'content': wrong_service}]}) is False
    assert first_proposal_draw({'candidates': [{'content': step}]}) is True
    # Only the FIRST proposal decides; a later duplicate cannot add a second draw.
    assert first_proposal_draw({'candidates': [{'content': {'rules': []}}, {'content': step}]}) is False


def test_analysis_script_shares_the_single_read_out_implementation():
    """Two copies of the read-out could drift; there must be exactly one."""
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / 'scripts/experiments'))
    import run_replication, summarize_replication
    assert summarize_replication.first_proposal_draw is run_replication.first_proposal_draw
    assert summarize_replication.has_notification_retry is run_replication.has_notification_retry


@pytest.mark.anyio
async def test_replay_runs_only_validation_makes_no_mechanic_call_and_accepts_nothing(tmp_path):
    """Replay measures the gate, not the policy. It must not propose, and must not accept."""
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        # Produce a real saved candidate the ordinary way, then replay it.
        first = await queue_completion_study(c, campaign.campaign_id)
        await c.tasks[first['study_id']]
        study = c.store.get_record('completion_studies', first['study_id'])
        version = next(x['policy_version'] for x in study['candidates'] if x.get('policy_version'))
        decision_before = c.policies.get(version).decision
        mechanic_calls_before = len(provider.mechanic_inputs)

        replay_campaign = c.create(CampaignRequest(task_text='Upgrade and confirm',
            order_id='order-replay', mode='baseline', config_profile_id='live-v1'))
        queued = await queue_completion_study(c, replay_campaign.campaign_id,
                                              replay_policy_version=version)
        assert queued['replay_of'] == version
        assert queued['replay_policy_hash'] == c.policies.get(version).policy_hash
        await c.tasks[queued['study_id']]
        record = c.store.get_record('completion_studies', queued['study_id'])

        # No Mechanic call, no proposal, no controls or candidate stage.
        assert len(provider.mechanic_inputs) == mechanic_calls_before
        assert record['candidates'] == []
        assert {r['stage'] for r in record['trial_rows']} == {'validation'}
        assert len(record['trial_rows']) == 42
        assert record['validation_assessment'] is not None
        # The replayed policy's own saved decision is untouched.
        assert c.policies.get(version).decision == decision_before
        # Nothing was accepted or activated anywhere.
        assert all(p['decision'] != 'ACCEPTED' for p in c.store.list_records('policies'))
        assert c.get(replay_campaign.campaign_id).active_policy_version == c.policies.baseline().version
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_replay_refuses_an_unknown_or_empty_policy_without_taking_the_campaign(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        with pytest.raises(StoreConflict):
            await queue_completion_study(c, campaign.campaign_id,
                                         replay_policy_version='policy-does-not-exist')
        # The empty baseline is a saved policy but has no rules; replaying it is meaningless.
        with pytest.raises(StoreConflict):
            await queue_completion_study(c, campaign.campaign_id,
                                         replay_policy_version=c.policies.baseline().version)
        assert not c.store.list_records('completion_studies')
        assert c.active_id is None
        assert c.get(campaign.campaign_id).state == 'IDLE'
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_replay_reaches_a_validation_verdict_over_the_http_route(tmp_path):
    """The runner reaches replay mode only through this route, and the whole phase is void
    if the route starts an ordinary study instead."""
    from fastapi import FastAPI
    from app.lab.api import create_router
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        first = await queue_completion_study(c, campaign.campaign_id)
        await c.tasks[first['study_id']]
        study = c.store.get_record('completion_studies', first['study_id'])
        version = next(x['policy_version'] for x in study['candidates'] if x.get('policy_version'))
        mechanic_before = len(provider.mechanic_inputs)

        replay_campaign = c.create(CampaignRequest(task_text='Upgrade and confirm',
            order_id='order-replay-http', mode='baseline', config_profile_id='live-v1'))
        app = FastAPI(); app.include_router(create_router(lambda: c))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://lab') as http:
            response = await http.post(
                f'/api/campaigns/{replay_campaign.campaign_id}/completion-study',
                json={'execute_live': True, 'replay_policy_version': version})
            assert response.status_code == 202, response.text
            body = response.json()
            # The runner refuses to continue unless this is echoed back.
            assert body['replay_of'] == version
            assert body['replay_policy_hash'] == c.policies.get(version).policy_hash
            await c.tasks[body['study_id']]
            final = (await http.get(f"/api/completion-studies/{body['study_id']}")).json()

        # A verdict was actually reached, and it is one assess_pairs can return.
        assert final['validation_assessment'] is not None
        assert final['validation_assessment']['decision'] in (
            'OBSERVED_IMPROVEMENT', 'NO_CHANGE', 'INCOMPLETE')
        assert final['decision'] == final['validation_assessment']['decision']
        assert len(provider.mechanic_inputs) == mechanic_before
        assert final['replay_of'] == version
    finally:
        await client.aclose()
