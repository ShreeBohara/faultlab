"""Evidence waits: the declared automatic telemetry-only retry, 'needs operator', and a truthful stop.

Live campaign a2fbffe3 waited about four hours in WAITING_EVIDENCE after one Weave TRANSPORT failure,
until a manual Retry evidence sync verified all six pending episodes in 30 s; a later stop during a
second wait was saved as EXECUTION_ERROR / UnexpectedError.

Here the real coordinator runs a planned Learn campaign through _execute with the real learning loop,
evidence wait, retry-evidence job, ledger and plan. Fakes: Weave (the evidence reader and the retry
job's telemetry services), the Actor runner, and the Explorer, reproduction, diagnosis and Mechanic
stages. No provider, simulator port, W&B or model call is made. The wait's clock runs 1000 times
faster, so the plan keeps the real 30 s / 120 s / 300 s delays while the test takes a second or two.
"""
import asyncio
from types import SimpleNamespace
import time

import httpx
import pytest
from pydantic import ValidationError

from app.contracts.models import (CampaignRequest, CandidatePolicy, Counterexample, ExplorerOutput, MechanicCandidate,
                                  MechanicNoChange, canonical_json, content_hash)
from app.lab import evidence_wait
from app.lab.budgets import BudgetExhausted, CampaignLedger
from app.lab.coordinator import LabCoordinator
from app.lab.discovery_protocol import DISCOVERY_V1
from app.lab.evidence import WaitingEvidence
from app.lab.exports import development_recording
from app.lab.run_plans import EvidenceRetryPlan, EvidenceRetryPlanV3, prepare_run_plan, read_run_plan, validate_run_plan
from app.lab.operator_actions import register_agent
from app.lab.storage import StoreConflict
from app.main import create_app
from test_counterexample_loop import RECIPE
from test_discovery_v2_flow import learn_campaign, owner, request  # noqa: F401  (fixture)
from test_evaluation import FakeRunner


def verified_record(episode_id):
    return {'episode_id': episode_id, 'source': 'weave_verified', 'root_call_id': 'fake-root-' + episode_id[-6:],
            'child_call_ids': [], 'source_project': 'fake-entity/fake-project', 'findings': []}


class FakeWeave:
    """In-memory Weave: the campaign's evidence reads and the retry job's telemetry services.

    The first read of every episode ``fail_when`` selects fails with TRANSPORT, and keeps failing until a
    retry re-sends it. The first ``broken_retries`` per-episode retries fail too (a persistent outage).
    """
    def __init__(self, owner, campaign_id, fail_when, *, broken_retries=0):
        self.owner, self.store, self.campaign_id = owner, owner.store, campaign_id
        self.fail_when, self.broken_retries = fail_when, broken_retries
        self.failed, self.cleared = [], set()
        self.reads, self.retried, self.jobs, self.closed = [], [], 0, 0
        self.retry_kwargs = []  # which keyword arguments each re-send received (automatic jobs get stopped=)
        self.hold_job = None   # an asyncio.Event: while set to an unset event, a retry job stays RUNNING
        self.snapshots = []    # (moment, counts) proving nothing else runs during a wait

    async def get(self, episode_id, context, **kwargs):
        self.reads.append(episode_id)
        saved = self.store.get_record('evidence', episode_id)
        if saved and saved['source'] == 'weave_verified':
            return SimpleNamespace(episode_id=episode_id, source='weave_verified', report=None, findings=[], observations=[])
        episode = self.store.get_record('episodes', episode_id)
        if self.fail_when(episode) and episode_id not in self.cleared:
            self.failed.append(episode_id)
            self.snapshots.append(('failed_read', self.counts()))
            self.store.put_record('ingestions', episode_id, {'episode_id': episode_id, 'state': 'RETRYABLE_ERROR',
                                                             'status': 'weave_pending', 'error_code': 'TRANSPORT'})
            raise WaitingEvidence('TRANSPORT')
        self.store.put_record('evidence', episode_id, verified_record(episode_id))
        return SimpleNamespace(episode_id=episode_id, source='weave_verified', report=None, findings=[], observations=[])

    async def services(self):
        weave = self; self.jobs += 1
        class Worker:
            async def start(self):
                if weave.hold_job is not None: await weave.hold_job.wait()
            async def close(self): weave.closed += 1
        class RetryGateway:
            async def retry(self, episode_id, **kwargs):
                weave.retried.append(episode_id)
                weave.retry_kwargs.append(sorted(kwargs))
                weave.snapshots.append(('retry', weave.counts()))
                if weave.broken_retries:
                    weave.broken_retries -= 1
                    raise RuntimeError('fake Weave outage')
                weave.cleared.add(episode_id)
                weave.store.put_record('evidence', episode_id, verified_record(episode_id))
                return SimpleNamespace(source='weave_verified')
        return Worker(), RetryGateway(), object()

    def counts(self):
        return self.owner.stage_counts()


def candidate():
    return CandidatePolicy.model_validate_json(canonical_json({'parent_version': 'policy-v0', 'rules': [
        {'hook': 'before_confirmation', 'when': 'always', 'steps': [{'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}]}))


def harness(owner, monkeypatch, fail_when, *, planned=True, broken_retries=0, mode='tie', candidate_fails=True):
    """A Learn campaign whose stages are doubles, except the evidence path, ledger, plan and coordinator."""
    import app.lab.learning as learning
    monkeypatch.setattr(evidence_wait, 'clock', lambda: time.monotonic() * 1000)  # 30 s declared = 30 ms here
    monkeypatch.setattr(evidence_wait, 'POLL_SECONDS', 0.005)
    campaign = (learn_campaign(owner, DISCOVERY_V1) if planned else
                owner.create(CampaignRequest(task_text='Upgrade', order_id='order-1', mode='learn', config_profile_id='live-v1')))
    ident = campaign.campaign_id
    owner.ledgers[ident] = ledger = CampaignLedger(owner.store, ident, owner.get(ident).caps)
    weave = FakeWeave(owner, ident, fail_when, broken_retries=broken_retries)
    owner.evidence_gateway = weave; owner._evidence_retry_services = weave.services
    runner = FakeRunner(mode); runner.provider = object(); original = runner.run
    calls = {'explorer': 0, 'mechanic': 0}
    owner.stage_counts = lambda: {'actor_episodes': len(runner.calls), 'used_model_calls': ledger.used_calls, **calls}

    async def persisted(current, recipe, policy, **kwargs):
        trial = await original(current, recipe, policy, **kwargs)
        purpose = kwargs.get('purpose') or 'discovery'
        if candidate_fails and purpose == 'source_validation' and kwargs['arm'] == 'L':
            trial.failed_checks = ['C3']; trial.outcome = 'VIOLATION'
        owner.store.put_record('trials', trial.episode_id, trial)
        owner.store.put_record('episodes', trial.episode_id, {
            'episode_id': trial.episode_id, 'campaign_id': current.campaign_id, 'configuration_hash': current.configuration_hash,
            'policy_hash': policy.policy_hash, 'scenario_hash': trial.scenario_hash, 'split': 'development', 'source_mode': 'live',
            'lifecycle': trial.lifecycle, 'arm': kwargs['arm'], 'experiment_purpose': purpose, 'study_id': current.campaign_id,
            'evidence_context_id': current.campaign_id, 'selector_id': None,
            'verdict': {'fault_executions': [{'triggered': True, 'reason': None} for _ in recipe.primitives]}})
        return trial
    runner.run = persisted

    class Explorer:
        def __init__(self, *args): pass
        async def select(self, context, **kwargs):
            calls['explorer'] += 1
            ref = f'selection-{calls["explorer"]}'
            output = ExplorerOutput(fault_spec=RECIPE, hypothesis='Offline selection fixture')
            owner.store.put_record('selections', ref, {'output': output.model_dump(mode='json')})
            return ref, output
    class Reproducer:
        def __init__(self, *args): pass
        async def source(self, campaign, source, recipe, policy, **kwargs):
            return Counterexample(counterexample_id='counter-' + source.episode_id[-8:], campaign_id=campaign.campaign_id,
                                  agent_registration_id='orders-v1', source_episode_id=source.episode_id, target_invariant='C3',
                                  scenario_hash=content_hash(recipe), configuration_hash=campaign.configuration_hash,
                                  report_ref=source.episode_id, verdict_ref='verdict-fixture', reproduced=True,
                                  target_violation_count=3, valid_count=3, attempted_count=3), [source]
        async def reduce(self, *args, **kwargs):
            return SimpleNamespace(result=SimpleNamespace(status='NO_REDUCTION', model_dump=lambda **_: {'status': 'NO_REDUCTION'}),
                                   retained_recipe=RECIPE, trials=[])
    class Diagnosis:
        def __init__(self, *args): pass
        async def run(self, *args, **kwargs):
            return (SimpleNamespace(kind='POLICY_GAP', model_dump=lambda **_: {'kind': 'POLICY_GAP', 'provenance': 'offline_double'}),
                    SimpleNamespace(trials=[]))
    class Mechanic:
        def __init__(self, *args): pass
        async def propose(self, context, **kwargs):
            calls['mechanic'] += 1
            proposal = (MechanicCandidate(candidate=candidate(), explanation='Offline fixture proposal') if calls['mechanic'] == 1
                        else MechanicNoChange(no_change_reason='No further supported repair'))
            return f'mechanic-{calls["mechanic"]}', proposal, [proposal.model_dump_json()]
    async def export(*args, **kwargs): pass
    for name, value in [('Explorer', Explorer), ('Reproducer', Reproducer), ('Diagnostician', Diagnosis),
                        ('Mechanic', Mechanic), ('export_incident', export)]:
        monkeypatch.setattr(learning, name, value)
    owner.runner = runner; owner.active_id = ident
    return campaign, weave, runner, ledger


def purpose_is(purpose, *, first_only=False):
    seen = []
    def select(episode):
        if not episode or episode['experiment_purpose'] != purpose: return False
        if first_only:
            if not seen: seen.append(episode['episode_id'])
            return episode['episode_id'] == seen[0]
        return True
    return select


async def until(predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, 'condition not reached'
        await asyncio.sleep(0.005)


def waits(owner, ident):
    return sorted((w for w in owner.store.list_records('evidence_waits') if w['campaign_id'] == ident), key=lambda w: w['started_at'])


def retries(owner, ident):
    return sorted((r for r in owner.store.list_records('evidence_retries') if r['campaign_id'] == ident), key=lambda r: r['requested_at'])


async def api_get(owner, path):
    transport = httpx.ASGITransport(app=create_app(coordinator=owner))
    async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1') as client:
        response = await client.get(path)
        return response.status_code, response.json()


def assert_nothing_ran_during_waits(weave):
    """Every retry saw exactly the Actor episodes, model calls and stage calls of the failed read before it."""
    last = None
    for moment, counts in weave.snapshots:
        if moment == 'failed_read': last = counts
        else: assert counts == last, (moment, counts, last)


# ------------------------------------------------------------------------------------------ plan
def test_learn_plans_declare_the_rule_and_other_plans_do_not(owner):
    campaign = learn_campaign(owner, DISCOVERY_V1)
    plan = read_run_plan(owner.store, campaign.campaign_id)['plan']
    assert plan['evidence_retry'] == evidence_wait.declaration()
    assert plan['evidence_retry']['delays_seconds'] == [30, 120, 300] and plan['evidence_retry']['automatic_retries_per_wait'] == 3
    # Rule v3 (September 30) in every new Learn plan: the same per-wait rule, at most 24 per campaign (v2 plans keep 6).
    assert plan['evidence_retry']['protocol'] == 'faultlab-evidence-retry/v3' and plan['evidence_retry']['automatic_retries_per_campaign'] == 24
    assert plan['evidence_retry']['repeats_model_requests'] is False and plan['evidence_retry']['charged_model_calls'] == 0
    assert 'telemetry-only' in plan['evidence_retry']['rule'] and 'needs operator' in plan['evidence_retry']['rule']
    assert evidence_wait.campaign_rule(owner.store, owner.get(campaign.campaign_id)) == evidence_wait.declaration()
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) == plan
    registration = register_agent(owner.store, owner.settings, 'reference')
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-5'))
    assert 'evidence_retry' not in baseline.plan
    saved = owner.create(baseline.campaign_request, run_plan=baseline)
    assert read_run_plan(owner.store, saved.campaign_id)['plan']['evidence_retry'] is None


def test_declaration_is_exact_and_a_different_installed_rule_refuses_the_saved_plan(owner, monkeypatch):
    # Rule v2 (plans saved before v3) and rule v3 (every new Learn plan) are each exact; neither accepts the other's cap.
    EvidenceRetryPlan.model_validate(evidence_wait.declaration_v2())
    EvidenceRetryPlanV3.model_validate(evidence_wait.declaration())
    for model, rule, other_cap in ((EvidenceRetryPlan, evidence_wait.declaration_v2(), 24), (EvidenceRetryPlanV3, evidence_wait.declaration(), 6)):
        for change in ({'automatic_retries_per_wait': 4}, {'delays_seconds': [30, 120]}, {'delays_seconds': [10, 120, 300]},
                       {'repeats_model_requests': True}, {'repeats_business_actions': True}, {'charged_model_calls': 1},
                       {'telemetry_only': False}, {'after_last_retry': 'STOP'}, {'protocol': 'faultlab-evidence-retry/v4'},
                       {'automatic_retries_per_campaign': 7}, {'automatic_retries_per_campaign': None},
                       {'automatic_retries_per_campaign': other_cap}):
            with pytest.raises(ValidationError):
                model.model_validate({**rule, **change})
    campaign = learn_campaign(owner, DISCOVERY_V1)
    from app.lab import run_plans
    monkeypatch.setattr(run_plans, 'evidence_retry_declaration', lambda: {**evidence_wait.declaration(), 'rule': 'another rule'})
    with pytest.raises(StoreConflict, match='automatic evidence retry rule differs'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))


# ------------------------------------------------------------------------------------------ transient failure
@pytest.mark.parametrize('failing', ['discovery', 'source_validation'])
def test_a_transient_weave_failure_is_retried_automatically_and_the_campaign_resumes(owner, monkeypatch, failing):
    # source_validation: the discovery source fails C3, the candidate is proposed, and all six of its source-validation
    # episodes fail their first Weave read (as in a2fbffe3); the candidate is then rejected on its own violations.
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is(failing, first_only=failing == 'discovery'),
                                              mode='tie' if failing == 'discovery' else 'gain')
    ident = campaign.campaign_id
    states = []
    original_transition = owner.transition
    def transition(ident_, state, reason=None):
        states.append(state); return original_transition(ident_, state, reason)
    owner.transition = transition
    asyncio.run(owner._execute(ident, True))
    final = owner.get(ident)
    assert final.state == 'NO_CHANGE', final.terminal_reason
    assert 'WAITING_EVIDENCE' in states
    wait, = waits(owner, ident)
    assert wait['status'] == 'RESOLVED' and wait['resolution'] == 'VERIFIED' and wait['ended_at']
    assert wait['message'] == 'Weave evidence verified after automatic telemetry retry 1 of 3; resumed.'
    attempt, = wait['automatic_attempts']
    retry, = retries(owner, ident)
    assert retry['trigger'] == 'automatic' and retry['automatic'] == {'evidence_wait_id': wait['wait_id'], 'attempt': 1, 'attempts_max': 3}
    assert attempt['request_id'] == retry['request_id'] and attempt['status'] == 'COMPLETED'
    expected = 1 if failing == 'discovery' else 6   # like a2fbffe3: one retry verified the whole pending batch at once
    assert attempt['verified'] == expected and attempt['still_pending'] == 0
    assert weave.retried[0] == wait['episode_id']                                 # blocked episode retried first
    assert [o['status'] for o in retry['outcomes'].values()] == ['VERIFIED'] * expected
    # Only the blocked episode's read failed: the one retry re-sent the whole pending batch before the loop read it.
    assert weave.failed == [wait['episode_id']] and len(wait['pending_episode_ids']) == expected
    assert sorted(weave.retried) == sorted(wait['pending_episode_ids'])
    assert weave.jobs == 1 and weave.closed == 1
    assert_nothing_ran_during_waits(weave)
    assert not owner.store.list_records('execution_errors')
    if failing == 'source_validation':
        qualification, = owner.store.list_records('candidate_qualifications')
        assert qualification['decision'] == 'REJECTED' and 'interruption_reason' not in qualification


# ------------------------------------------------------------------------------------------ persistent failure
def test_persistent_failure_makes_three_bounded_attempts_then_needs_operator_and_a_manual_retry_still_works(owner, monkeypatch):
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('discovery', first_only=True), broken_retries=10**6)
    ident = campaign.campaign_id

    async def scenario():
        task = asyncio.create_task(owner._execute(ident, True))
        await until(lambda: (waits(owner, ident) or [{}])[-1].get('status') == 'NEEDS_OPERATOR')
        wait = waits(owner, ident)[-1]
        await asyncio.sleep(0.5)          # 500 declared seconds later: still no fourth attempt
        automatic = retries(owner, ident)
        assert [r['automatic']['attempt'] for r in automatic] == [1, 2, 3] and all(r['trigger'] == 'automatic' for r in automatic)
        assert all(r['status'] == 'COMPLETED' and set(o['status'] for o in r['outcomes'].values()) == {'PENDING'} for r in automatic)
        wait = waits(owner, ident)[-1]
        assert wait['status'] == 'NEEDS_OPERATOR' and [a['attempt'] for a in wait['automatic_attempts']] == [1, 2, 3]
        assert all(a['status'] == 'COMPLETED' and a['verified'] == 0 for a in wait['automatic_attempts'])
        assert wait['failed_reads'] == 4 and wait['next_automatic_retry_at'] is None
        current = owner.get(ident)
        assert current.state == 'WAITING_EVIDENCE' and current.terminal_reason.startswith('Needs operator:')
        assert 'after 3 automatic telemetry retries' in current.terminal_reason and 'TRANSPORT' in current.terminal_reason
        status, body = await api_get(owner, f'/api/campaigns/{ident}/evidence-wait')
        assert status == 200 and body['status'] == 'NEEDS_OPERATOR' and body['needs_operator'] is True
        assert body['declared'] == evidence_wait.declaration() and body['current']['wait_id'] == wait['wait_id']
        assert body['message'] == current.terminal_reason and body['automatic_retries_total'] == 3
        # The operator's manual retry still works and resumes the campaign.
        weave.broken_retries = 0
        manual = await owner.retry_evidence(ident)
        assert manual['trigger'] == 'manual' and 'automatic' not in manual
        await task
        return manual

    manual = asyncio.run(scenario())
    final = owner.get(ident)
    assert final.state == 'NO_CHANGE', final.terminal_reason
    wait, = waits(owner, ident)
    assert wait['status'] == 'RESOLVED' and wait['message'] == 'Weave evidence verified after a manual evidence retry; resumed.'
    assert wait['manual_retry_request_ids'] == [manual['request_id']] and len(wait['automatic_attempts']) == 3
    assert [r['trigger'] for r in retries(owner, ident)] == ['automatic'] * 3 + ['manual']
    assert weave.jobs == 4 and weave.closed == 4
    assert_nothing_ran_during_waits(weave)


def test_a_campaign_without_the_declaration_keeps_manual_retry_only(owner, monkeypatch):
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('discovery', first_only=True), planned=False)
    ident = campaign.campaign_id

    async def scenario():
        task = asyncio.create_task(owner._execute(ident, True))
        await until(lambda: (waits(owner, ident) or [{}])[-1].get('status') == 'MANUAL_RETRY_ONLY')
        await asyncio.sleep(0.5)          # 500 declared seconds: nothing automatic happens
        assert not retries(owner, ident) and weave.jobs == 0
        status, body = await api_get(owner, f'/api/campaigns/{ident}/evidence-wait')
        assert body['status'] == 'MANUAL_RETRY_ONLY' and body['declared'] is None and 'Not declared' in body['declared_note']
        assert 'declares no automatic evidence retry' in owner.get(ident).terminal_reason
        await owner.retry_evidence(ident, [waits(owner, ident)[-1]['episode_id']])
        await task
    asyncio.run(scenario())
    assert owner.get(ident).state == 'NO_CHANGE'
    assert [r['trigger'] for r in retries(owner, ident)] == ['manual']


# ------------------------------------------------------------------------------------------ stop during a wait
@pytest.mark.parametrize('moment', ['retry_scheduled', 'retry_running', 'needs_operator'])
def test_stop_during_an_evidence_wait_ends_stopped_with_a_plain_reason_not_an_error(owner, monkeypatch, moment):
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('source_validation'), broken_retries=10**6,
                                              mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    if moment == 'retry_scheduled':
        # Slow the wait's clock back to real time, so retry 1 is still 30 s away when Stop arrives.
        monkeypatch.setattr(evidence_wait, 'clock', time.monotonic)

    async def scenario():
        if moment == 'retry_running': weave.hold_job = asyncio.Event()
        task = asyncio.create_task(owner._execute(ident, True))
        target = {'retry_scheduled': 'AUTOMATIC_RETRY_SCHEDULED', 'retry_running': 'AUTOMATIC_RETRY_RUNNING',
                  'needs_operator': 'NEEDS_OPERATOR'}[moment]
        await until(lambda: (waits(owner, ident) or [{}])[-1].get('status') == target)
        assert owner.get(ident).state == 'WAITING_EVIDENCE'
        qualification, = owner.store.list_records('candidate_qualifications')
        assert qualification['decision'] == 'PROPOSED' and qualification['stage'] == 'SOURCE_VALIDATION'
        before = owner.stage_counts()
        await owner.stop(ident)           # what the dashboard Stop button and a watcher's POST /stop both do
        await task
        assert owner.stage_counts() == before  # the stop replays nothing
        if weave.hold_job is not None:
            weave.hold_job.set()
            await asyncio.gather(*[t for t in owner.tasks.values() if not t.done()])
    asyncio.run(scenario())

    final = owner.get(ident)
    assert final.state == 'STOPPED' and final.stop_requested
    assert final.terminal_reason.startswith('Stopped during an evidence wait: Stop was requested while 6 episodes waited '
                                            'for verified Weave evidence (last ingestion result: TRANSPORT;')
    made = {'retry_scheduled': 0, 'retry_running': 1, 'needs_operator': 3}[moment]
    assert f'{made} of 3 automatic telemetry retries made' in final.terminal_reason
    assert ('needs operator' in final.terminal_reason) == (moment == 'needs_operator')
    assert 'nothing is replayed' in final.terminal_reason and 'UnexpectedError' not in final.terminal_reason
    assert not owner.store.list_records('execution_errors')
    qualification, = owner.store.list_records('candidate_qualifications')
    assert qualification['decision'] == 'INCOMPLETE' and 'error' not in qualification
    assert qualification['interruption_reason'] == evidence_wait.STOPPED_WAIT_REASON
    assert qualification['interruption_reason'].startswith('Stopped during evidence wait')
    wait, = waits(owner, ident)
    assert qualification['interruption'] == {'kind': 'STOPPED_DURING_EVIDENCE_WAIT', 'evidence_wait_id': wait['wait_id'],
                                             'waiting_for_episode_ids': wait['pending_episode_ids'], 'evidence_verified_before_stop': False,
                                             'automatic_retries_made': made, 'stage_before_wait': 'CANDIDATE_VALIDATION'}
    assert owner.policies.get(qualification['candidate_version']).decision == 'INCOMPLETE'
    assert wait['status'] == 'STOPPED' and wait['resolution'] == 'STOPPED' and wait['message'] == final.terminal_reason
    assert len(wait['automatic_attempts']) == made
    if moment == 'retry_running':
        assert wait['automatic_attempts'][0]['status'] == 'RUNNING_AT_STOP'
        assert retries(owner, ident)[0]['status'] == 'COMPLETED'   # the telemetry job itself finished afterwards
    assert_nothing_ran_during_waits(weave)
    status, body = asyncio.run(api_get(owner, f'/api/campaigns/{ident}/evidence-wait'))
    assert body['status'] == 'NOT_WAITING' and body['current'] is None and body['waits'][0]['status'] == 'STOPPED'


def test_a_stop_while_reading_evidence_before_any_wait_is_also_a_stop_not_an_error(owner, monkeypatch):
    campaign, weave, runner, ledger = harness(owner, monkeypatch, lambda episode: False, mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    read = weave.get
    async def stopped_during_read(episode_id, context, **kwargs):
        if (owner.store.get_record('episodes', episode_id) or {}).get('experiment_purpose') == 'source_validation':
            await owner.stop(ident)
            raise WaitingEvidence('STOPPED')   # what the Weave reader returns when a stop cuts its read short
        return await read(episode_id, context, **kwargs)
    weave.get = stopped_during_read
    asyncio.run(owner._execute(ident, True))
    final = owner.get(ident)
    assert final.state == 'STOPPED' and not owner.store.list_records('execution_errors')
    assert final.terminal_reason == 'External stop requested while reading Weave evidence; remote effects are retained'
    assert not waits(owner, ident)   # a read cut short by the stop is not an evidence wait
    qualification, = owner.store.list_records('candidate_qualifications')
    assert qualification['decision'] == 'INCOMPLETE' and 'error' not in qualification and 'interruption' not in qualification
    assert qualification['interruption_reason'] == 'External stop interrupted qualification; saved attempts are not replayed'


def test_a_stop_just_after_the_evidence_was_verified_keeps_the_wait_resolved(owner, monkeypatch):
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('discovery', first_only=True))
    ident = campaign.campaign_id
    read = weave.get
    async def stop_during_the_successful_reread(episode_id, context, **kwargs):
        bundle = await read(episode_id, context, **kwargs)
        if weave.retried and episode_id == weave.failed[0]:
            await owner.stop(ident)             # arrives while the verified bundle is being returned
        return bundle
    weave.get = stop_during_the_successful_reread
    asyncio.run(owner._execute(ident, True))
    final = owner.get(ident)
    assert final.state == 'STOPPED'
    assert final.terminal_reason == 'External stop requested while reading Weave evidence; remote effects are retained'
    wait, = waits(owner, ident)
    assert wait['status'] == 'RESOLVED' and wait['resolution'] == 'VERIFIED'   # not rewritten as a stop


# ------------------------------------------------------------------------------------------ restart and recording
def test_restart_closes_an_open_wait_and_the_recording_keeps_waits_and_retries(owner, monkeypatch):
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('discovery', first_only=True), broken_retries=10**6)
    ident = campaign.campaign_id

    async def scenario():
        task = asyncio.create_task(owner._execute(ident, True))
        await until(lambda: len(retries(owner, ident)) == 1 and retries(owner, ident)[0]['status'] == 'COMPLETED'
                    and waits(owner, ident)[-1]['status'] == 'AUTOMATIC_RETRY_SCHEDULED')
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(scenario())
    wait, = waits(owner, ident)
    assert wait['status'] == 'INTERRUPTED' and wait['error_class'] == 'CancelledError'
    # A crash leaves an open wait and a waiting campaign; the next coordinator on the store closes both.
    wait.update(status='NEEDS_OPERATOR', ended_at=None, resolution=None); owner.store.put_record('evidence_waits', wait['wait_id'], wait)
    crashed = owner.get(ident); crashed.state = 'WAITING_EVIDENCE'; crashed.stop_requested = False; owner.save(crashed)
    asyncio.run(owner.close())
    restarted = LabCoordinator(owner.settings)
    try:
        again, = [w for w in restarted.store.list_records('evidence_waits') if w['campaign_id'] == ident]
        assert again['status'] == 'INTERRUPTED' and again['ended_at'] and 'restart' in again['message']
        assert restarted.get(ident).state == 'STOPPED'
        status, body = asyncio.run(api_get(restarted, f'/api/campaigns/{ident}/evidence-wait'))
        assert body['status'] == 'NOT_WAITING' and body['current'] is None
        with restarted.store.transaction() as db:   # the fake runner's minimal episode rows are not exportable episodes
            db.execute("DELETE FROM records WHERE kind='episodes' AND json_extract(payload,'$.campaign_id')=?", (ident,))
        recording = development_recording(restarted.store, ident)
        assert [w['wait_id'] for w in recording['evidence_waits']] == [wait['wait_id']]
        assert [r['trigger'] for r in recording['evidence_retries']] == ['automatic']
        assert recording['run_plan']['plan']['evidence_retry'] == evidence_wait.declaration()
    finally:
        asyncio.run(restarted.close())


def test_the_evidence_wait_endpoint_for_a_campaign_that_never_waited(owner):
    campaign = learn_campaign(owner, DISCOVERY_V1)
    status, body = asyncio.run(api_get(owner, f'/api/campaigns/{campaign.campaign_id}/evidence-wait'))
    assert status == 200 and body == {
        'schema_version': 'faultlab-evidence-wait/v1', 'campaign_id': campaign.campaign_id, 'campaign_state': 'IDLE',
        'declared': evidence_wait.declaration(), 'declared_note': None, 'status': 'NOT_WAITING', 'needs_operator': False,
        'message': 'This campaign is not waiting for evidence.', 'current': None, 'waits': [], 'waits_total': 0,
        'automatic_retries_total': 0}
    status, body = asyncio.run(api_get(owner, '/api/campaigns/campaign-unknown/evidence-wait'))
    assert status == 404


# ------------------------------------------------------------------------------------------ review fixes (fixer, 2026-09-29)
# Each test below reproduces one reviewer probe (artifacts/product-dependability-2026-09-29/review-builder-a/) and
# checks the corrected behaviour.
STOP_REASON = 'External stop requested; remote effects are retained'   # what LabCoordinator.stop saves


def stop_after(owner, runner, ident, purpose, count):
    """Stop the campaign as soon as the count-th episode of ``purpose`` has finished (before any evidence read)."""
    run, seen = runner.run, []
    async def stopping(current, recipe, policy, **kwargs):
        trial = await run(current, recipe, policy, **kwargs)
        if kwargs.get('purpose') == purpose:
            seen.append(trial.episode_id)
            if len(seen) == count: await owner.stop(ident)
        return trial
    runner.run = stopping
    return seen


def run_and_settle(owner, ident, seconds=60):
    """Run the campaign, then let any evidence retry job still running finish (asyncio.run would cancel it).
    A regression that leaves the campaign waiting fails after ``seconds`` instead of hanging the suite."""
    async def scenario():
        await owner._execute(ident, True)
        await asyncio.gather(*[t for t in owner.tasks.values() if not t.done()])
    asyncio.run(asyncio.wait_for(scenario(), seconds))


@pytest.mark.parametrize('purpose', ['source_validation', 'challenge'])
def test_a_stop_during_episodes_keeps_the_stops_own_reason(owner, monkeypatch, purpose):
    # Probe 01: no evidence was read and nothing waited, yet the reason said "while reading Weave evidence".
    campaign, weave, runner, ledger = harness(owner, monkeypatch, lambda episode: False, mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    seen = stop_after(owner, runner, ident, purpose, 2)
    read_purposes, get = [], weave.get
    async def counting(episode_id, context, **kwargs):
        read_purposes.append((owner.store.get_record('episodes', episode_id) or {}).get('experiment_purpose'))
        return await get(episode_id, context, **kwargs)
    weave.get = counting
    run_and_settle(owner, ident)
    final = owner.get(ident)
    assert len(seen) == 2 and purpose not in read_purposes and not waits(owner, ident)
    assert final.state == 'STOPPED' and final.terminal_reason == STOP_REASON
    assert not owner.store.list_records('execution_errors')
    qualification, = owner.store.list_records('candidate_qualifications')
    assert qualification['decision'] == 'INCOMPLETE' and 'error' not in qualification and 'interruption' not in qualification
    assert qualification['interruption_reason'] == 'External stop interrupted qualification; saved attempts are not replayed'


def test_budget_exhausted_mid_qualification_is_a_budget_interruption_not_an_execution_error(owner, monkeypatch):
    # Probe 02: the qualification was saved INCOMPLETE with error EXECUTION_ERROR / UnexpectedError.
    import app.lab.learning as learning
    campaign, weave, runner, ledger = harness(owner, monkeypatch, lambda episode: False, mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    class ExhaustedChallenger:
        def __init__(self, *args, **kwargs): pass
        async def run(self, *args, **kwargs): raise BudgetExhausted('Model budget exhausted')
    monkeypatch.setattr(learning, 'Challenger', ExhaustedChallenger)
    run_and_settle(owner, ident)
    final = owner.get(ident)
    assert final.state == 'NO_CHANGE' and final.terminal_reason == 'Model budget exhausted'
    assert not owner.store.list_records('execution_errors')
    qualification, = owner.store.list_records('candidate_qualifications')
    assert qualification['decision'] == 'INCOMPLETE' and 'error' not in qualification
    assert qualification['interruption'] == {'kind': 'BUDGET_EXHAUSTED', 'reason': 'Model budget exhausted'}
    assert qualification['interruption_reason'] == 'Budget exhausted before qualification completed; saved attempts are not replayed'
    assert owner.policies.get(qualification['candidate_version']).decision == 'INCOMPLETE'


@pytest.mark.parametrize('stopped_by', ['stop', 'ledger_only'])
def test_a_stop_first_noticed_by_a_model_call_charge_keeps_the_stops_reason(owner, monkeypatch, stopped_by):
    # Probe 09: an empty StopRequested from CampaignLedger.consume_call replaced the reason with "Budget or stop boundary".
    import app.lab.learning as learning
    campaign, weave, runner, ledger = harness(owner, monkeypatch, lambda episode: False, mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    class StoppedDuringDiagnosis:
        def __init__(self, *args): pass
        async def run(self, *args, **kwargs):
            if stopped_by == 'stop': await owner.stop(ident)   # the dashboard Stop and a watcher's POST /stop do this
            else: ledger.stopped = True                        # no Stop request: the old wording is kept for this case
            ledger.consume_call(role='mechanic')               # raises StopRequested() with no message
    monkeypatch.setattr(learning, 'Diagnostician', StoppedDuringDiagnosis)
    run_and_settle(owner, ident)
    final = owner.get(ident)
    assert not owner.store.list_records('execution_errors')
    if stopped_by == 'stop':
        assert final.state == 'STOPPED' and final.terminal_reason == STOP_REASON
    else:
        assert final.state == 'NO_CHANGE' and final.terminal_reason == 'Budget or stop boundary'


def test_a_stop_just_after_a_retry_verified_everything_says_the_evidence_was_verified(owner, monkeypatch):
    # Probe 10: the reason said "1 episode waited for verified Weave evidence" although none was still unverified.
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('source_validation'), mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    services = weave.services
    async def stop_once_all_are_verified():
        worker, gateway, publisher = await services()
        class StopAfterLast:
            async def retry(self, episode_id, **kwargs):
                result = await gateway.retry(episode_id)
                pending = waits(owner, ident)[-1]['pending_episode_ids']
                if all((owner.store.get_record('evidence', e) or {}).get('source') == 'weave_verified' for e in pending):
                    await owner.stop(ident)             # lands in the job's last moment, before the campaign re-reads
                return result
        return worker, StopAfterLast(), publisher
    owner._evidence_retry_services = stop_once_all_are_verified
    run_and_settle(owner, ident)
    final = owner.get(ident)
    wait, = waits(owner, ident)
    qualification, = owner.store.list_records('candidate_qualifications')
    assert final.state == 'STOPPED' and wait['status'] == 'STOPPED' and wait['message'] == final.terminal_reason
    assert final.terminal_reason.startswith('Stopped during an evidence wait: the evidence this wait needed was verified '
                                            'just before the Stop, but the campaign had not read it again yet (1 of 3 '
                                            'automatic telemetry retries made).')
    assert 'waited for verified Weave evidence' not in final.terminal_reason
    assert qualification['interruption']['waiting_for_episode_ids'] == []
    assert qualification['interruption']['evidence_verified_before_stop'] is True
    assert qualification['decision'] == 'INCOMPLETE' and 'error' not in qualification


def test_an_automatic_retry_waiting_for_the_lock_is_not_started_after_a_stop(owner, monkeypatch):
    # Probe 03: retry_evidence never checked for a stop, so a job could be created after the Stop.
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('discovery', first_only=True), broken_retries=10**6)
    ident = campaign.campaign_id
    async def scenario():
        task = asyncio.create_task(owner._execute(ident, True))
        await until(lambda: (waits(owner, ident) or [{}])[-1].get('status') == 'AUTOMATIC_RETRY_SCHEDULED')
        await owner.lock.acquire()                 # e.g. a Create or Start request holding the scheduler lock
        await asyncio.sleep(0.1)                   # retry 1 (30 declared s) falls due and waits for the lock
        assert not retries(owner, ident)
        await owner.stop(ident)
        owner.lock.release()
        await task
        await asyncio.gather(*[t for t in owner.tasks.values() if not t.done()])
    asyncio.run(scenario())
    final = owner.get(ident)
    wait, = waits(owner, ident)
    assert final.state == 'STOPPED' and not retries(owner, ident) and weave.jobs == 0
    assert wait['automatic_attempts'] == [] and wait['status'] == 'STOPPED'
    assert '0 of 3 automatic telemetry retries made' in final.terminal_reason


def test_a_running_automatic_retry_job_ends_at_its_next_step_after_a_stop(owner, monkeypatch):
    # Probe 03 (second part): a job running at Stop was not given stopped= and ran on for up to 60 s.
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('source_validation'), mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    async def services():
        weave.jobs += 1
        class Worker:
            async def start(self): pass
            async def close(self): weave.closed += 1
        class StopDuringFirstResend:
            async def retry(self, episode_id, **kwargs):
                weave.retried.append(episode_id); weave.retry_kwargs.append(sorted(kwargs))
                assert kwargs['stopped']() is False
                await owner.stop(ident)
                assert kwargs['stopped']() is True     # the gateway can now cut its upload and read short
                raise RuntimeError('fake Weave read cut short by the stop')
        return Worker(), StopDuringFirstResend(), object()
    owner._evidence_retry_services = services
    run_and_settle(owner, ident)
    retry, = retries(owner, ident)
    wait, = waits(owner, ident)
    assert retry['trigger'] == 'automatic' and retry['status'] == 'COMPLETED'
    assert len(weave.retried) == 1 and weave.retry_kwargs == [['stopped']]
    assert weave.retried[0] == wait['episode_id']                 # the blocked episode was the one re-sent
    reasons = [outcome.get('reason') for outcome in retry['outcomes'].values()]
    assert reasons.count('Saved evidence synchronization is unavailable') == 1
    assert reasons.count('Campaign stopped before this episode was re-sent') == len(wait['pending_episode_ids']) - 1
    assert owner.get(ident).state == 'STOPPED' and wait['automatic_attempts'][0]['status'] == 'COMPLETED'


def test_the_campaign_limit_ends_automatic_retries_for_a_flaky_batch(owner, monkeypatch):
    # Probe 06: the limit was per wait only, so a flaky six-episode batch took 18 automatic retries and 45 declared
    # minutes and never showed "needs operator". Rule v2 also allows at most 6 automatic retries per campaign. Every new
    # Learn plan now declares rule v3 (24 per campaign; tests/lab/test_evidence_retry_v3.py); a plan saved under rule v2
    # still starts and keeps its cap of 6, which is what this campaign's plan declares.
    from app.lab import run_plans
    monkeypatch.setattr(run_plans, 'evidence_retry_declaration', evidence_wait.declaration_v2)  # a plan saved before v3
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('source_validation'), mode='gain', candidate_fails=False)
    monkeypatch.setattr(run_plans, 'evidence_retry_declaration', evidence_wait.declaration)      # today's installed rule
    assert read_run_plan(owner.store, campaign.campaign_id)['plan']['evidence_retry'] == evidence_wait.declaration_v2()
    ident = campaign.campaign_id
    first_listed = {}
    async def services():
        weave.jobs += 1
        class Worker:
            async def start(self): pass
            async def close(self): weave.closed += 1
        class OnlyTheBlockedEpisodeOnItsThirdTry:
            first = True
            async def retry(self, episode_id, **kwargs):
                weave.retried.append(episode_id); weave.snapshots.append(('retry', weave.counts()))
                is_first, self.first = self.first, False
                if is_first:
                    first_listed[episode_id] = first_listed.get(episode_id, 0) + 1
                    if first_listed[episode_id] >= 3:
                        weave.cleared.add(episode_id)
                        owner.store.put_record('evidence', episode_id, verified_record(episode_id))
                        return SimpleNamespace(source='weave_verified')
                raise RuntimeError('fake partial outage')
        return Worker(), OnlyTheBlockedEpisodeOnItsThirdTry(), object()
    owner._evidence_retry_services = services
    async def scenario():
        task = asyncio.create_task(owner._execute(ident, True))
        await until(lambda: (waits(owner, ident) or [{}])[-1].get('status') == 'NEEDS_OPERATOR', seconds=30)
        await asyncio.sleep(0.5)                   # 500 declared seconds later: still no seventh automatic retry
        observed = (waits(owner, ident), owner.get(ident).terminal_reason,
                    (await api_get(owner, f'/api/campaigns/{ident}/evidence-wait'))[1], len(retries(owner, ident)))
        await owner.stop(ident); await task
        return observed
    all_waits, reason, body, made = asyncio.run(scenario())
    assert [len(w['automatic_attempts']) for w in all_waits] == [3, 3, 0]
    assert [w['status'] for w in all_waits] == ['RESOLVED', 'RESOLVED', 'NEEDS_OPERATOR']
    assert all_waits[2]['limit_reached'] == 'PER_CAMPAIGN' and all_waits[2]['automatic_retries_campaign_max'] == 6
    assert made == 6 and [r['trigger'] for r in retries(owner, ident)] == ['automatic'] * 6
    assert reason.startswith('Needs operator: Weave evidence for 4 episodes is still unverified and this campaign has used all 6 '
                             'of its automatic telemetry retries (0 of 3 in this wait)')
    assert body['needs_operator'] is True and body['automatic_retries_total'] == 6 and body['message'] == reason
    declared_seconds = sum(sum(w['delays_seconds'][:len(w['automatic_attempts'])]) for w in all_waits)
    assert declared_seconds == 2 * 450                                  # was 6 * 450 under the per-wait limit alone
    assert_nothing_ran_during_waits(weave)
    assert owner.get(ident).state == 'STOPPED'


def test_the_needs_operator_retry_sends_the_waits_episodes_blocked_first_and_skips_verified_ones(owner, monkeypatch):
    # Probe 11: the notice posted {}, so the job re-sent every campaign episode in id order under one 60 s deadline.
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is('source_validation'), broken_retries=10**6,
                                              mode='gain', candidate_fails=False)
    ident = campaign.campaign_id
    async def scenario():
        task = asyncio.create_task(owner._execute(ident, True))
        await until(lambda: (waits(owner, ident) or [{}])[-1].get('status') == 'NEEDS_OPERATOR')
        wait = waits(owner, ident)[-1]
        automatic = len(weave.retried)
        weave.broken_retries = 0
        verified = wait['pending_episode_ids'][-1]      # verified meanwhile, e.g. by an earlier partial retry
        owner.store.put_record('evidence', verified, verified_record(verified))
        transport = httpx.ASGITransport(app=create_app(coordinator=owner))
        async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1') as client:
            # What the dashboard notice now sends: the current wait's pending_episode_ids.
            response = await client.post(f'/api/campaigns/{ident}/retry-evidence', json={'episode_ids': wait['pending_episode_ids']})
        await asyncio.wait_for(task, 60)
        await asyncio.gather(*[t for t in owner.tasks.values() if not t.done()])
        return wait, response, weave.retried[automatic:], weave.retry_kwargs[automatic:]
    wait, response, manual_order, manual_kwargs = asyncio.run(scenario())
    assert response.status_code == 202 and response.json()['trigger'] == 'manual'
    job = owner.store.get_record('evidence_retries', response.json()['request_id'])
    campaign_episodes = [e for e in owner.store.list_records('episodes') if e['campaign_id'] == ident]
    assert len(campaign_episodes) > len(wait['pending_episode_ids'])       # the campaign has more episodes than the wait
    assert sorted(job['episode_ids']) == sorted(wait['pending_episode_ids'])  # only the wait's own episodes
    assert manual_order == wait['pending_episode_ids'][:-1]                  # given order, blocked episode first
    assert manual_order[0] == wait['episode_id']
    assert job['outcomes'][wait['pending_episode_ids'][-1]] == {'status': 'VERIFIED', 'already_verified': True}
    assert manual_kwargs == [[]] * len(manual_order)                         # an operator's retry is not tied to Stop
    assert owner.get(ident).state == 'NO_CHANGE'


def test_a_plan_saved_under_the_first_rule_still_reads_and_start_refuses_it(owner, monkeypatch):
    # Rule v1 (per-wait limit only) was built and reviewed offline and never run live.
    from app.lab import run_plans
    v1 = {key: value for key, value in evidence_wait.declaration().items() if key != 'automatic_retries_per_campaign'}
    v1.update(protocol='faultlab-evidence-retry/v1', rule='At most 3 automatic retries per wait (the first rule).')
    monkeypatch.setattr(run_plans, 'evidence_retry_declaration', lambda: dict(v1))
    campaign = learn_campaign(owner, DISCOVERY_V1)
    monkeypatch.setattr(run_plans, 'evidence_retry_declaration', evidence_wait.declaration)
    saved = read_run_plan(owner.store, campaign.campaign_id)
    assert saved['status'] == 'PLANNED' and saved['plan']['evidence_retry'] == v1
    with pytest.raises(StoreConflict, match='automatic evidence retry rule differs'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    status, body = asyncio.run(api_get(owner, f'/api/campaigns/{campaign.campaign_id}/evidence-wait'))
    assert status == 200 and body['declared'] == v1
    for bad in ({**v1, 'automatic_retries_per_campaign': 6}, {**evidence_wait.declaration(), 'protocol': 'faultlab-evidence-retry/v1'}):
        with pytest.raises(ValidationError):
            run_plans.SavedRunPlan.model_validate({**saved['plan'], 'evidence_retry': bad})
