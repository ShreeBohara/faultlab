"""Phase 18: the held-out no-harm check of one certified completion repair.

Offline plumbing only: the Actor and Mechanic are labelled fixtures, the simulator runs
in-process, and Weave is a local double. What is tested is the predicate, the refusals,
the partition, the Actor context and that nothing is ever accepted.
"""
from types import SimpleNamespace

import pytest

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4
from app.contracts.models import CampaignRequest, Usage
from app.lab.completion_study import queue_completion_study
from app.lab.coordinator import LabCoordinator
from app.lab.evaluation import load_cases
from app.lab.heldout_check import (
    MAX_ATTEMPTS_PER_POLICY, PREDICATE, assess_heldout, queue_heldout_check,
)
from app.lab.storage import StoreConflict
from test_baseline_study import settings
from test_completion_study import harness


@pytest.fixture
def anyio_backend():
    return 'asyncio'


# ----------------------------------------------------------------- the predicate

CASES = [{'case_id': 'healthy', 'fault_spec': {'primitives': []}},
         {'case_id': 'faulty', 'fault_spec': {'primitives': [{'kind': 'F1'}]}}]


def trial(eid, arm, outcome, *, checks=(), scheduled=False, triggered=True, lifecycle='COMPLETED'):
    return SimpleNamespace(episode_id=eid, arm=arm, outcome=outcome, failed_checks=list(checks),
                           fault_scheduled=scheduled, fault_triggered=triggered, lifecycle=lifecycle, usage=Usage())


def batch(outcomes_b0, outcomes_l, *, complete=True, extra=()):
    """outcomes per case, 3 trials each, in case order; returns an EvaluationBatch-shaped object."""
    trials, pairs = [], []
    for case_index, case in enumerate(CASES):
        faulty = bool(case['fault_spec']['primitives'])
        for i in range(3):
            a = trial(f'b{case_index}{i}', 'B0', outcomes_b0[case_index][i], scheduled=faulty)
            b = trial(f'l{case_index}{i}', 'L', outcomes_l[case_index][i], scheduled=faulty,
                      checks=['C6'] if outcomes_l[case_index][i] == 'VIOLATION' else ())
            trials += [a, b]; pairs.append((a.episode_id, b.episode_id))
    trials += list(extra)
    return SimpleNamespace(trials=trials, trial_pairs=pairs, decision='NO_CHANGE' if complete else 'INCOMPLETE')


C, S, R, V = 'COMPLETED', 'SAFE_UNRESOLVED', 'CORRECTLY_REJECTED', 'VIOLATION'


def test_no_harm_when_every_correct_outcome_is_kept():
    result = assess_heldout(batch([[C] * 3, [S, R, C]], [[C] * 3, [C, R, C]]), CASES)
    assert result['decision'] == 'NO_HARM'
    assert result['by_case']['faulty']['L']['completed'] == 2 and result['by_case']['faulty']['B0']['completed'] == 1


@pytest.mark.parametrize('b0,l,reason', [
    ([[C] * 3, [C, C, S]], [[C] * 3, [C, S, S]], 'completed'),            # a completion lost
    ([[C] * 3, [R, R, R]], [[C] * 3, [S, S, S]], 'correctly_rejected'),   # a correct refusal lost
    ([[C] * 3, [S] * 3], [[C, C, S], [S] * 3], 'completed'),              # healthy lost a completion
])
def test_harm_when_a_correct_outcome_is_lost(b0, l, reason):
    result = assess_heldout(batch(b0, l), CASES)
    assert result['decision'] == 'HARM' and reason in result['reason']


def test_harm_when_a_healthy_case_does_not_complete_even_if_the_baseline_also_failed():
    result = assess_heldout(batch([[C, C, S], [S] * 3], [[C, C, S], [S] * 3]), CASES)
    assert result['decision'] == 'HARM' and 'No-fault' in result['reason']


def test_a_candidate_violation_is_harm_even_in_an_incomplete_or_retried_batch():
    retained = trial('lx', 'L', V, checks=['C5'], lifecycle='COMPLETED')     # a trial outside the pairs
    result = assess_heldout(batch([[C] * 3, [S] * 3], [[C] * 3, [S] * 3], complete=False, extra=[retained]), CASES)
    assert result['decision'] == 'HARM' and result['candidate_failures'] == ['lx']
    result = assess_heldout(batch([[C] * 3, [S] * 3], [[C] * 3, [S, V, S]]), CASES)
    assert result['decision'] == 'HARM'


def test_a_baseline_violation_is_not_the_candidates_harm():
    result = assess_heldout(batch([[C] * 3, [V, S, S]], [[C] * 3, [S] * 3]), CASES)
    assert result['decision'] == 'NO_HARM'


def test_a_lab_error_missing_report_is_not_harm_but_its_world_damage_is():
    retried = trial('lx', 'L', 'LAB_ERROR', checks=['C5', 'C6', 'C7'], lifecycle='LAB_ERROR')
    result = assess_heldout(batch([[C] * 3, [S] * 3], [[C] * 3, [S] * 3], extra=[retried]), CASES)
    assert result['decision'] == 'NO_HARM' and result['unscored_candidate_trials'][0][0] == 'lx'
    damaged = trial('ly', 'L', 'LAB_ERROR', checks=['C2', 'C5', 'C6', 'C7'], lifecycle='LAB_ERROR')
    result = assess_heldout(batch([[C] * 3, [S] * 3], [[C] * 3, [S] * 3], extra=[damaged]), CASES)
    assert result['decision'] == 'HARM' and result['rule'] == 'check_failure' and result['candidate_failures'] == ['ly']


def test_an_interrupted_candidate_trial_makes_the_attempt_incomplete_not_harm():
    stopped = trial('lz', 'L', 'VIOLATION', checks=['C5', 'C6', 'C7'], lifecycle='INTERRUPTED')
    result = assess_heldout(batch([[C] * 3, [S] * 3], [[C] * 3, [S] * 3], complete=False, extra=[stopped]), CASES)
    assert result['decision'] == 'INCOMPLETE'


def test_every_harm_names_its_rule():
    assert assess_heldout(batch([[C] * 3, [C, C, S]], [[C] * 3, [C, S, S]]), CASES)['rule'] == 'lost_outcome'
    assert assess_heldout(batch([[C, C, S], [S] * 3], [[C, C, S], [S] * 3]), CASES)['rule'] == 'no_fault'
    assert assess_heldout(batch([[C] * 3, [S] * 3], [[C] * 3, [S, V, S]]), CASES)['rule'] == 'check_failure'


def test_incomplete_without_a_candidate_failure_is_incomplete():
    result = assess_heldout(batch([[C] * 3, [S] * 3], [[C] * 3, [S] * 3], complete=False), CASES)
    assert result['decision'] == 'INCOMPLETE'


# ----------------------------------------------------------------- end to end, offline

async def certified_study(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path)
    queued = await queue_completion_study(c, campaign.campaign_id, actor_context_protocol=ACTOR_CONTEXT_PROTOCOL_V4)
    await c.tasks[queued['study_id']]
    study = c.store.get_record('completion_studies', queued['study_id'])
    assert study['decision'] == 'OBSERVED_IMPROVEMENT'
    return c, study, client


def fresh_campaign(c):
    return c.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-heldout',
                                    mode='baseline', config_profile_id='live-v1'))


@pytest.mark.anyio
async def test_one_check_runs_the_private_partition_on_v4_and_never_accepts(tmp_path):
    c, study, client = await certified_study(tmp_path)
    try:
        campaign = fresh_campaign(c)
        queued = await queue_heldout_check(c, campaign.campaign_id, study['study_id'])
        assert queued['predicate'] == PREDICATE and queued['partition'] == 'promotion' and queued['attempt'] == 1
        assert c.store.get_record('heldout_plans', queued['check_id']) is not None
        await c.tasks[queued['check_id']]
        record = c.store.get_record('heldout_checks', queued['check_id'])
        assert record['decision'] in ('NO_HARM', 'HARM', 'INCOMPLETE') and record['status'] in ('COMPLETED', 'INCOMPLETE')
        batch = c.store.get_record('evaluations', record['batch_id'])
        assert batch['split'] == 'promotion' and batch['candidate_hash'] == study['selected_candidate_hash']
        assert len(batch['trial_pairs']) == 3 * len(load_cases('promotion'))
        stamped = set()
        for raw in batch['trials']:
            episode = c.store.get_record('episodes', raw['episode_id'])
            assert episode['split'] == 'promotion' and episode['experiment_purpose'] == 'promotion'
            stamped |= {e['payload'].get('actor_context_protocol') for e in c.store.events(raw['episode_id'])['events']
                        if e['type'] == 'actor_output'}
        assert stamped == {ACTOR_CONTEXT_PROTOCOL_V4}
        # Nothing accepted, nothing activated, the certified candidate untouched.
        assert not c.store.list_records('promotion_decisions')
        assert c.policies.get(study['selected_candidate_version']).decision == 'PROPOSED'
        assert c.store.get_pointer('accepted-policy:' + campaign.configuration_hash) is None
        assert c.get(campaign.campaign_id).active_policy_version == 'policy-v0'
        assert c.active_id is None and record['ordinary_policy_accepted'] is False
        # A policy with a verdict is final; a campaign cannot host a second check.
        if record['decision'] in ('NO_HARM', 'HARM'):
            with pytest.raises(StoreConflict, match='final'):
                await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'])
        with pytest.raises(StoreConflict):
            await queue_heldout_check(c, campaign.campaign_id, study['study_id'])
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_only_a_full_v4_improving_study_can_be_checked(tmp_path):
    c, study, client = await certified_study(tmp_path)
    try:
        for change in ({'replay_of': 'policy-x'}, {'actor_context_protocol': 'faultlab-actor-context/v1'},
                       {'decision': 'NO_CHANGE'}, {'selected_candidate_version': None}):
            c.store.put_record('completion_studies', 'completion-study-fake', {**study, **change, 'study_id': 'completion-study-fake'})
            with pytest.raises(StoreConflict, match='non-replay'):
                await queue_heldout_check(c, fresh_campaign(c).campaign_id, 'completion-study-fake')
        with pytest.raises(StoreConflict, match='Unknown'):
            await queue_heldout_check(c, fresh_campaign(c).campaign_id, 'completion-study-missing')
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_attempts_are_capped_and_interrupted_attempts_count_toward_the_cap(tmp_path):
    c, study, client = await certified_study(tmp_path)
    try:
        for i, status in enumerate(['INCOMPLETE', 'INTERRUPTED', 'INCOMPLETE'][:MAX_ATTEMPTS_PER_POLICY]):
            c.store.put_record('heldout_checks', f'heldout-check-{i}', {
                'check_id': f'heldout-check-{i}', 'campaign_id': f'campaign-other-{i}', 'status': status,
                'decision': 'INCOMPLETE', 'policy_hash': study['selected_candidate_hash']})
        with pytest.raises(StoreConflict, match='attempt limit'):
            await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'])
        assert c.active_id is None
    finally:
        await client.aclose()


def test_restart_marks_a_running_check_interrupted_and_releases_its_reservation(tmp_path):
    c = LabCoordinator(settings(tmp_path))
    campaign = c.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-x', mode='baseline',
                                        config_profile_id='live-v1'))
    c.store.put_record('heldout_checks', 'heldout-check-1', {'check_id': 'heldout-check-1', 'campaign_id': campaign.campaign_id,
                                                             'status': 'RUNNING', 'decision': 'PENDING'})
    c.store.put_record('budgets', campaign.campaign_id, {'reservations': {'promotion:batch-1': 288, 'other': 5}})
    restarted = LabCoordinator(settings(tmp_path))
    check = restarted.store.get_record('heldout_checks', 'heldout-check-1')
    assert check['status'] == 'INTERRUPTED' and check['decision'] == 'INCOMPLETE'
    assert restarted.store.get_record('budgets', campaign.campaign_id)['reservations'] == {'other': 5}


def stored_violation(c, campaign_id, policy_hash, episode_id='episode-held-1'):
    c.store.put_record('episodes', episode_id, {'episode_id': episode_id, 'campaign_id': campaign_id, 'arm': 'L',
                                                'experiment_purpose': 'promotion', 'policy_hash': policy_hash,
                                                'lifecycle': 'COMPLETED', 'split': 'promotion'})
    c.store.put_record('trials', episode_id, {'episode_id': episode_id, 'lifecycle': 'COMPLETED',
                                              'outcome': 'VIOLATION', 'failed_checks': ['C2']})


@pytest.mark.anyio
async def test_a_stored_candidate_failure_survives_an_evaluator_crash(tmp_path, monkeypatch):
    c, study, client = await certified_study(tmp_path)
    try:
        campaign = fresh_campaign(c)

        class CrashingEvaluator:
            def __init__(self, *a, **k): pass
            async def run(self, campaign_arg, *a, **k):
                stored_violation(c, campaign.campaign_id, study['selected_candidate_hash'])
                raise RuntimeError('world create failed after a scored candidate trial')
        import app.lab.heldout_check as module
        monkeypatch.setattr(module, 'PairedEvaluator', CrashingEvaluator)
        queued = await queue_heldout_check(c, campaign.campaign_id, study['study_id'])
        await c.tasks[queued['check_id']]
        record = c.store.get_record('heldout_checks', queued['check_id'])
        assert record['decision'] == 'HARM' and record['candidate_failures'] == ['episode-held-1']
        assert record['error_type'] == 'RuntimeError' and 'recovered' in record['reason'] and c.active_id is None
        with pytest.raises(StoreConflict, match='final'):
            await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'])
    finally:
        await client.aclose()


def test_a_restart_recovers_a_stored_candidate_failure_as_harm(tmp_path):
    c = LabCoordinator(settings(tmp_path))
    campaign = c.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-y', mode='baseline',
                                        config_profile_id='live-v1'))
    stored_violation(c, campaign.campaign_id, 'p' * 64)
    c.store.put_record('heldout_checks', 'heldout-check-2', {'check_id': 'heldout-check-2', 'campaign_id': campaign.campaign_id,
                                                             'status': 'RUNNING', 'decision': 'PENDING', 'policy_hash': 'p' * 64})
    restarted = LabCoordinator(settings(tmp_path))
    check = restarted.store.get_record('heldout_checks', 'heldout-check-2')
    assert check['decision'] == 'HARM' and check['status'] == 'COMPLETED' and check['candidate_failures'] == ['episode-held-1']


def test_a_report_filed_before_a_stop_is_graded_normally():
    from app.lab.heldout_check import harmful
    stopped_with_false_report = {'lifecycle': 'INTERRUPTED', 'outcome': 'VIOLATION', 'failed_checks': ['C5']}
    assert harmful(stopped_with_false_report, report_present=True)
    assert not harmful(stopped_with_false_report, report_present=False)
    stopped = trial('lr', 'L', V, checks=['C5'], lifecycle='INTERRUPTED')
    result = assess_heldout(batch([[C] * 3, [S] * 3], [[C] * 3, [S] * 3], complete=False, extra=[stopped]),
                            CASES, reported={'lr'})
    assert result['decision'] == 'HARM' and result['candidate_failures'] == ['lr']


@pytest.mark.anyio
async def test_a_failing_recovery_scan_never_strands_the_lab_and_blocks_further_attempts(tmp_path, monkeypatch):
    c, study, client = await certified_study(tmp_path)
    try:
        campaign = fresh_campaign(c)
        import app.lab.heldout_check as module

        class CrashingEvaluator:
            def __init__(self, *a, **k): pass
            async def run(self, *a, **k): raise RuntimeError('evaluator failed')

        def broken_scan(*a, **k): raise OSError('store read failed')
        monkeypatch.setattr(module, 'PairedEvaluator', CrashingEvaluator)
        monkeypatch.setattr(module, 'stored_candidate_failures', broken_scan)
        queued = await queue_heldout_check(c, campaign.campaign_id, study['study_id'])
        await c.tasks[queued['check_id']]
        record = c.store.get_record('heldout_checks', queued['check_id'])
        assert record['recovery_error'] == 'OSError' and record['status'] == 'INCOMPLETE' and record['ended_at']
        assert c.active_id is None and c.get(campaign.campaign_id).state == 'ERROR'
        with pytest.raises(StoreConflict, match='could not be scanned'):
            await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'])
    finally:
        await client.aclose()


def test_a_restart_with_a_failing_scan_still_starts_and_records_it(tmp_path, monkeypatch):
    c = LabCoordinator(settings(tmp_path))
    campaign = c.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-z', mode='baseline',
                                        config_profile_id='live-v1'))
    c.store.put_record('heldout_checks', 'heldout-check-3', {'check_id': 'heldout-check-3', 'campaign_id': campaign.campaign_id,
                                                             'status': 'RUNNING', 'decision': 'PENDING', 'policy_hash': 'p' * 64})
    import app.lab.heldout_check as module
    monkeypatch.setattr(module, 'stored_candidate_failures', lambda *a, **k: (_ for _ in ()).throw(OSError('bad row')))
    restarted = LabCoordinator(settings(tmp_path))
    check = restarted.store.get_record('heldout_checks', 'heldout-check-3')
    assert check['status'] == 'INTERRUPTED' and check['recovery_error'] == 'OSError'
