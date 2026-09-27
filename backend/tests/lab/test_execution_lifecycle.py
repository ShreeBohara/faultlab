"""Offline failure injection retains durable attempts and releases local admission."""
import asyncio
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import CampaignRequest, Episode, RegressionExecution, EpisodeBudget, Usage, new_id
from app.lab.coordinator import LabCoordinator
from app.lab.evaluation import PairedEvaluator, queue_evaluation
from app.lab.regression_executions import execute_regression
from test_evaluation import setup, cases
from test_evidence import episode
from test_regression_bundle import compile_fixture


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def persist_runner(coordinator, runner):
    original = runner.run

    async def run(campaign, recipe, policy, **kwargs):
        trial = await original(campaign, recipe, policy, **kwargs)
        purpose = kwargs.get('purpose', 'promotion')
        saved = Episode(campaign_id=campaign.campaign_id, episode_id=trial.episode_id,
            origin='faultlab_evaluation', split='promotion' if purpose == 'promotion' else 'development',
            arm=trial.arm, source_mode='offline_fixture', experiment_purpose=purpose,
            trial_index=trial.trial_index, study_id=kwargs.get('study_id', campaign.campaign_id),
            evidence_context_id=campaign.campaign_id, execution_epoch=campaign.execution_epoch,
            world_id=trial.world_id, task_id=new_id('task'), scenario_hash=trial.scenario_hash,
            policy_hash=trial.policy_hash, policy_version=policy.version, model=campaign.model,
            configuration_hash=campaign.configuration_hash, lifecycle=trial.lifecycle, usage=trial.usage)
        coordinator.store.put_record('episodes', trial.episode_id, saved)
        coordinator.store.put_record('trials', trial.episode_id, trial, immutable=True)
        return trial

    runner.run = run


@pytest.mark.anyio
@pytest.mark.parametrize('cancel', [False, True])
async def test_evaluator_keeps_saved_attempt_when_next_execution_throws_or_is_cancelled(tmp_path, cancel):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    persist_runner(c, runner)
    original = runner.run
    waiting = asyncio.Event()
    count = 0

    async def run(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            waiting.set()
            if cancel:
                await asyncio.Event().wait()
            raise RuntimeError('SECRET_FAILURE_TEXT')
        ledger.consume_call(reservation=kwargs['reservation'])
        return await original(*args, **kwargs)

    runner.run = run
    task = asyncio.create_task(PairedEvaluator(c.store, runner, ledger).run(
        campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation'))
    await waiting.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await task
    batch = c.store.list_records('evaluations')[0]
    assert batch['decision'] == 'INCOMPLETE' and len(batch['trials']) == 1
    trial = batch['trials'][0]
    assert c.store.get_record('trials', trial['episode_id']) == trial
    assert c.store.get_record('episodes', trial['episode_id'])['world_id'] == trial['world_id']
    assert batch['usage']['http_attempts'] == trial['usage']['http_attempts']
    assert not batch['trial_pairs'] and ledger.used_calls == 1 and ledger.reserved_calls == 1064
    assert 'SECRET_FAILURE_TEXT' not in str(c.store.list_records('evaluation_errors'))
    await c.close()


@pytest.mark.anyio
async def test_evaluation_request_is_durable_before_startup_failure(tmp_path, monkeypatch):
    c, campaign, _, _, runner = setup(tmp_path)
    c.runner = runner
    monkeypatch.setattr(Settings, 'require_live', lambda self: None)

    async def fail(_):
        raise RuntimeError('SECRET_STARTUP_TEXT')

    c._get_runner = fail
    request = SimpleNamespace(campaign_id=campaign.campaign_id, policy_versions=['policy-v0'], purpose='comparison')
    queued = await queue_evaluation(c, request)
    saved = c.store.get_record('evaluation_requests', queued['request_id'])
    assert saved['status'] == 'QUEUED' and saved['batch_id']
    await c.tasks[queued['request_id']]
    saved = c.store.get_record('evaluation_requests', queued['request_id'])
    assert saved['status'] == 'INCOMPLETE' and saved['error']['code'] == 'EXECUTION_ERROR'
    assert 'SECRET_STARTUP_TEXT' not in str(saved) and c.active_id is None
    await c.close()


@pytest.mark.anyio
async def test_queued_evaluation_cancellation_keeps_batch_and_stopped_campaign(tmp_path, monkeypatch):
    c, campaign, ledger, _, runner = setup(tmp_path)
    c.runner = runner
    c.ledgers[campaign.campaign_id] = ledger
    persist_runner(c, runner)
    monkeypatch.setattr(Settings, 'require_live', lambda self: None)
    original = runner.run
    waiting = asyncio.Event()
    calls = 0

    async def run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            waiting.set()
            await asyncio.Event().wait()
        return await original(*args, **kwargs)

    runner.run = run
    queued = await queue_evaluation(c, SimpleNamespace(campaign_id=campaign.campaign_id,
        policy_versions=['policy-v0'], purpose='comparison'))
    await waiting.wait()
    await c.stop(campaign.campaign_id)
    c.tasks[queued['request_id']].cancel()
    with pytest.raises(asyncio.CancelledError):
        await c.tasks[queued['request_id']]
    request = c.store.get_record('evaluation_requests', queued['request_id'])
    assert request['status'] == 'INTERRUPTED'
    batch = c.store.get_record('evaluations', request['batch_id'])
    assert batch['decision'] == 'INCOMPLETE' and len(batch['trials']) == 1
    assert c.get(campaign.campaign_id).state == 'STOPPED' and c.active_id is None
    assert ledger.reserved_calls == 1064
    await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('cancel_cleanup', [False, True])
async def test_cleanup_failure_or_cancellation_closes_other_resources_and_releases_owner(tmp_path, cancel_cleanup):
    c, campaign, _, _, _ = setup(tmp_path)
    c.active_id = campaign.campaign_id
    c.transition(campaign.campaign_id, 'COMPLETED', 'Original result')
    before = c.store.get_record('campaigns', campaign.campaign_id)
    closed = []
    waiting = asyncio.Event()

    class Resource:
        def __init__(self, name): self.name = name
        async def close(self):
            closed.append(self.name)
            if self.name == 'world_client':
                waiting.set()
                if cancel_cleanup: await asyncio.Event().wait()
                raise RuntimeError('SECRET_CLOSE_TEXT')

    runner = SimpleNamespace(**{name: Resource(name) for name in ('world_client', 'provider', 'telemetry_worker')})
    task = asyncio.create_task(c.finish_activity(campaign.campaign_id, runner, owned=True, activity_id='cleanup-fixture'))
    await waiting.wait()
    if cancel_cleanup:
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    else:
        await task
    assert closed == ['world_client', 'provider', 'telemetry_worker'] and c.active_id is None
    assert c.store.get_record('campaigns', campaign.campaign_id) == before
    errors = c.store.get_record('resource_cleanup_errors', 'cleanup-fixture')
    assert len(errors['errors']) == 1 and 'SECRET_CLOSE_TEXT' not in str(errors)
    await c.close()


@pytest.mark.anyio
async def test_error_after_stop_cannot_overwrite_stop_result(tmp_path):
    c, campaign, ledger, _, runner = setup(tmp_path)
    c.active_id = campaign.campaign_id
    c.ledgers[campaign.campaign_id] = ledger
    entered = asyncio.Event(); release = asyncio.Event()

    async def fail(*args, **kwargs):
        entered.set(); await release.wait()
        raise RuntimeError('SECRET_EXECUTION_TEXT')

    runner.run = fail
    c.runner = runner
    task = asyncio.create_task(c._execute(campaign.campaign_id, False))
    await entered.wait()
    await c.stop(campaign.campaign_id)
    before = c.store.get_record('campaigns', campaign.campaign_id)
    release.set(); await task
    assert c.store.get_record('campaigns', campaign.campaign_id) == before
    assert c.store.get_record('execution_errors', campaign.campaign_id)['code'] == 'EXECUTION_ERROR'
    assert c.active_id is None
    await c.close()


@pytest.mark.anyio
async def test_regression_startup_cancellation_durably_finishes_record_and_reservation(tmp_path, monkeypatch):
    c, _, bundle = compile_fixture(tmp_path)
    campaign = c.store.list_records('campaigns')[0]
    from app.integrations.registry import AgentRegistry
    registration = AgentRegistry(c.store).get(c.store.get_record('campaign_registrations', campaign['campaign_id'])['registration_id'])
    from dataclasses import replace
    c.settings = replace(c.settings, wandb_model=registration.model)
    monkeypatch.setattr(Settings, 'require_live', lambda self: None)
    c.runner = object()
    waiting = asyncio.Event()

    async def start(_):
        waiting.set(); await asyncio.Event().wait()

    c._get_runner = start
    regression = c.store.list_records('regressions')[0]
    record = await execute_regression(c, regression['regression_id'], SimpleNamespace(
        policy_version='policy-v0', agent_registration_id=registration.registration_id,
        execute_live=True, execution_profile_id='sandbox-v1'))
    await waiting.wait()
    c.tasks[record.execution_id].cancel()
    with pytest.raises(asyncio.CancelledError): await c.tasks[record.execution_id]
    saved = c.store.get_record('regression_executions', record.execution_id)
    assert saved['status'] == 'INCOMPLETE' and 'interrupted' in saved['stop_reason']
    assert c.active_id is None and c.ledgers[campaign['campaign_id']].reserved_calls == 1064
    assert not c.store.list_records('episodes')
    await c.close()


@pytest.mark.anyio
async def test_restart_recovers_pending_requests_and_regression_worlds_without_replay(tmp_path):
    c, campaign, ledger, _, _ = setup(tmp_path)
    regression_id = 'execution-interrupted'
    e = episode(c, campaign, study=regression_id)
    e.lifecycle = 'RUNNING'; e.usage = Usage(model_calls=1, http_attempts=2)
    c.store.put_record('episodes', e.episode_id, e)
    record = RegressionExecution(execution_id=regression_id, bundle_id='bundle-fixture', manifest_hash='a'*64,
        registration_id='orders-v1', profile_id='sandbox-v1', mode='FRESH_SANDBOX', explicit_action=True,
        policy_hash=c.policies.baseline().policy_hash, configuration_hash=campaign.configuration_hash,
        declared_budget=EpisodeBudget(), usage=Usage(), episode_ids=[], world_ids=[], status='RUNNING')
    c.store.put_record('regression_executions', regression_id, record)
    ledger.reserve('regression:'+regression_id, 24)
    ledger.reserve('promotion:pending-batch', 48)
    ledger.consume_call(reservation='regression:'+regression_id)
    c.store.put_record('evaluation_requests', 'pending-request', {'request_id':'pending-request',
        'campaign_id':campaign.campaign_id, 'batch_id':'pending-batch', 'status':'RUNNING'})
    c.store.close()
    restarted = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    saved = restarted.store.get_record('regression_executions', regression_id)
    assert saved['status'] == 'INCOMPLETE' and saved['episode_ids'] == [e.episode_id]
    assert saved['world_ids'] == [e.world_id] and saved['usage']['http_attempts'] == 2
    assert restarted.store.get_record('episodes', e.episode_id)['lifecycle'] == 'INTERRUPTED'
    assert restarted.store.get_record('evaluation_requests', 'pending-request')['status'] == 'INTERRUPTED'
    budget = restarted.store.get_record('budgets', campaign.campaign_id)
    assert budget['used_calls'] == 1 and sum(r['calls'] for r in budget['reservations'].values()) == 1064
    assert restarted.tasks == {} and restarted.active_id is None
    await restarted.close()


@pytest.mark.anyio
async def test_restart_closes_only_interrupted_main_loop_work_and_preserves_charges(tmp_path):
    from app.lab.budgets import CampaignLedger

    c, campaign, ledger, candidate, _ = setup(tmp_path)
    c.transition(campaign.campaign_id, 'CHALLENGING')
    qualification = {'campaign_id':campaign.campaign_id, 'qualification_ref':'qualification-interrupted',
        'candidate_version':candidate.version, 'decision':'PROPOSED', 'stage':'CHALLENGE',
        'source_validation_ref':'source-batch-preserved'}
    c.store.put_record('candidate_qualifications', qualification['qualification_ref'], qualification)
    for prefix in ('candidate:', 'reproduce:', 'reduce:', 'intervention:', 'pair-retry:', 'promotion:'):
        ledger.reserve(prefix+'interrupted', 24)
    ledger.reserve('owner-reserved-unknown', 7)
    ledger.consume_call(reservation='candidate:interrupted')

    closed = c.create(CampaignRequest(task_text='Closed history', order_id='order-closed', mode='baseline'))
    c.transition(closed.campaign_id, 'NO_CHANGE', 'Historical original reason')
    closed_ledger = CampaignLedger(c.store, closed.campaign_id)
    closed_ledger.reserve('candidate:historical', 24)
    closed_qualification = {'campaign_id':closed.campaign_id, 'qualification_ref':'qualification-historical',
        'candidate_version':'historical-version', 'decision':'PROPOSED'}
    c.store.put_record('candidate_qualifications', closed_qualification['qualification_ref'], closed_qualification)
    historical = c.store.get_record('campaigns', closed.campaign_id)
    historical_budget = c.store.get_record('budgets', closed.campaign_id)
    c.store.close()

    restarted = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    saved = restarted.store.get_record('candidate_qualifications', qualification['qualification_ref'])
    assert saved['decision'] == 'INCOMPLETE' and saved['source_validation_ref'] == 'source-batch-preserved'
    assert restarted.policies.get(candidate.version).decision == 'INCOMPLETE'
    assert restarted.get(campaign.campaign_id).state == 'STOPPED'
    assert restarted.store.get_pointer('active-policy:'+campaign.campaign_id) == 'policy-v0'
    budget = restarted.store.get_record('budgets', campaign.campaign_id)
    assert budget['used_calls'] == 1 and budget['unknown_cost_calls'] == 1
    assert set(budget['reservations']) == {'final_audit', 'portability', 'selection_comparison', 'owner-reserved-unknown'}
    assert restarted.store.get_record('campaigns', closed.campaign_id) == historical
    assert restarted.store.get_record('budgets', closed.campaign_id) == historical_budget
    assert restarted.store.get_record('candidate_qualifications', closed_qualification['qualification_ref']) == closed_qualification
    assert restarted.tasks == {} and restarted.active_id is None
    await restarted.close()
