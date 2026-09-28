"""Phase 18: the held-out no-harm check of one certified completion repair.

Offline plumbing only: the Actor and Mechanic are labelled fixtures, the simulator runs
in-process, and Weave is a local double. What is tested is the predicate, the refusals,
the partition, the Actor context and that nothing is ever accepted.

Synthetic fixtures only (Phase 22 review round 1): an autouse fixture replaces the promotion
partition with SYNTHETIC_PROMOTION everywhere, so no test here loads audit/promotion.json.
"""
from types import SimpleNamespace

import pytest

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4
from app.contracts.models import CampaignRequest, FaultSpec, Usage
from app.lab.completion_study import queue_completion_study
from app.lab.coordinator import LabCoordinator
from app.lab.heldout_check import (
    MAX_ATTEMPTS_PER_POLICY, PREDICATE, assess_heldout, queue_heldout_check,
)
from app.lab.storage import StoreConflict
from test_baseline_study import settings
from test_completion_study import harness


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def synthetic_spec(primitives, seed):
    return FaultSpec.model_validate({'seed': seed, 'primitives': primitives}).model_dump(mode='json')


# Stands in for the private promotion partition in every test: a no-fault case and one delayed
# upgrade success, in the case shape PairedEvaluator reads (case_id, fixture_id, fault_spec).
SYNTHETIC_PROMOTION = [
    {'case_id': 'synthetic-promotion-1', 'fixture_id': 'standard-v1', 'fault_spec': synthetic_spec([], 800)},
    {'case_id': 'synthetic-promotion-2', 'fixture_id': 'standard-v1', 'fault_spec': synthetic_spec([{
        'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
        'parameters': {'completion_delay_ticks': 2, 'terminal_status': 'SUCCEEDED', 'failure_code': None}}], 801)},
]


@pytest.fixture(autouse=True)
def synthetic_promotion_partition(monkeypatch):
    """No test loads the real promotion partition: both held-out loaders return the synthetic
    one, and the referee loader refuses 'promotion' from the real audit directory outright."""
    import app.lab.evaluation as evaluation
    import app.lab.heldout_check as heldout
    import app.referee.manifests as manifests
    real_cases, real_manifest = evaluation.load_cases, manifests.load_manifest

    def load_cases(name):
        if name == 'promotion':
            return [dict(case) for case in SYNTHETIC_PROMOTION]
        return real_cases(name)

    def load_manifest(name, *, directory=None):
        if name == 'promotion' and directory is None:
            raise AssertionError('a test tried to load the real promotion partition')
        return real_manifest(name, directory=directory)
    monkeypatch.setattr(evaluation, 'load_cases', load_cases)
    monkeypatch.setattr(heldout, 'load_cases', load_cases)
    monkeypatch.setattr(manifests, 'load_manifest', load_manifest)


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
        assert len(batch['trial_pairs']) == 3 * len(SYNTHETIC_PROMOTION)
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
    c.store.close()
    restarted = LabCoordinator(settings(tmp_path))
    try:
        check = restarted.store.get_record('heldout_checks', 'heldout-check-1')
        assert check['status'] == 'INTERRUPTED' and check['decision'] == 'INCOMPLETE'
        assert restarted.store.get_record('budgets', campaign.campaign_id)['reservations'] == {'other': 5}
    finally:
        restarted.store.close()


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
    c.store.close()
    restarted = LabCoordinator(settings(tmp_path))
    try:
        check = restarted.store.get_record('heldout_checks', 'heldout-check-2')
        assert check['decision'] == 'HARM' and check['status'] == 'COMPLETED' and check['candidate_failures'] == ['episode-held-1']
    finally:
        restarted.store.close()


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
    c.store.close()
    restarted = LabCoordinator(settings(tmp_path))
    try:
        check = restarted.store.get_record('heldout_checks', 'heldout-check-3')
        assert check['status'] == 'INTERRUPTED' and check['recovery_error'] == 'OSError'
    finally:
        restarted.store.close()


# ================================================================= Phase 22: predicate v2
#
# Synthetic fixtures only: no test here reads the promotion partition or any sealed
# partition. The novelty scope is replaced by a synthetic identity set wherever it is used.

import importlib.util
import json
import pathlib
from fractions import Fraction

import app.lab.heldout_check as module
from app.contracts.models import FaultSpec, content_hash
from app.lab.challenge import schedule_identity
from app.lab.heldout_check import (
    FAULT_REPLICAS, PREDICATE_V2, assess_heldout_v2, check_plan, fisher_one_sided_less, load_partition,
    position_trials, replica_layout, rule3_v2,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]


# ----------------------------------------------------------------- v1 on Phase 18's counts

# PHASE18_RESULTS.md, "Every candidate trial, by case (by fault kind)". Case names are the
# fault kinds, not the private case ids; the order here is not the partition's.
PHASE18 = [
    ('no-fault', False, [C, C, S], [C, C, C]),
    ('delayed-confirmation', True, [C, C, C], [C, C, V]),
    ('delayed-upgrade-success', True, [C, C, C], [C, C, C]),
    ('delayed-refusal', True, [R, R, R], [R, R, R]),
    ('stale-history', True, [C, C, C], [C, C, S]),
    ('transient-upgrade', True, [C, S, S], [S, S, S]),
]
PHASE18_CASES = [{'case_id': name, 'fault_spec': {'primitives': [{'kind': 'F'}] if faulty else []}}
                 for name, faulty, _, _ in PHASE18]


def phase18_batch(drift_fixed=False):
    trials, pairs = [], []
    for name, faulty, b0, l in PHASE18:
        for i in range(3):
            outcome = C if drift_fixed and l[i] == V else l[i]
            a = trial(f'b-{name}-{i}', 'B0', b0[i], scheduled=faulty)
            b = trial(f'l-{name}-{i}', 'L', outcome, scheduled=faulty,
                      checks=['C5', 'C6', 'C8'] if outcome == V else ())
            trials += [a, b]; pairs.append((a.episode_id, b.episode_id))
    return SimpleNamespace(trials=trials, trial_pairs=pairs, decision='NO_CHANGE')


def test_v1_is_unchanged_on_phase18s_per_case_counts():
    result = assess_heldout(phase18_batch(), PHASE18_CASES)
    assert (result['decision'], result['rule']) == ('HARM', 'check_failure')
    assert result['candidate_failures'] == ['l-delayed-confirmation-2']
    counts = {name: (arms['L']['completed'], arms['B0']['completed'], arms['L']['correctly_rejected'])
              for name, arms in result['by_case'].items()}
    assert counts == {'no-fault': (3, 2, 0), 'delayed-confirmation': (2, 3, 0), 'delayed-upgrade-success': (3, 3, 0),
                      'delayed-refusal': (0, 0, 3), 'stale-history': (2, 3, 0), 'transient-upgrade': (0, 1, 0)}


def test_v1_without_the_drifted_episode_is_still_harm_by_lost_outcome():
    """PHASE19 correction: the defect decided which rule fired first, not the verdict."""
    result = assess_heldout(phase18_batch(drift_fixed=True), PHASE18_CASES)
    assert (result['decision'], result['rule'], result['case_id']) == ('HARM', 'lost_outcome', 'stale-history')
    no_stale = [c for c in PHASE18_CASES if c['case_id'] != 'stale-history']
    batch = phase18_batch(drift_fixed=True)
    batch.trial_pairs = batch.trial_pairs[:12] + batch.trial_pairs[15:]
    result = assess_heldout(batch, no_stale)
    assert (result['decision'], result['rule'], result['case_id']) == ('HARM', 'lost_outcome', 'transient-upgrade')


# ----------------------------------------------------------------- Fisher, pure python

@pytest.mark.parametrize('l,nl,b,nb,expected', [
    (1, 4, 3, 4, Fraction(17, 70)),            # Fisher's tea-tasting table, one-sided
    (0, 13, 5, 13, Fraction(1287, 65780)),     # Phase 13's 5 of 13 vs 0 of 13, one tail (two-sided 0.039)
    (0, 15, 5, 15, Fraction(3003, 142506)),
    (0, 15, 3, 15, Fraction(455, 4060)),       # 0.112: the OR-branch's cell
    (0, 15, 4, 15, Fraction(1365, 27405)),     # 0.0498: the first Fisher cell at L = 0
    (1, 15, 6, 15, Fraction(81510, 2035800)),  # 0.0400
    (1, 15, 5, 15, Fraction(50050, 593775)),   # 0.0843
    (3, 3, 3, 3, Fraction(1)), (0, 15, 0, 15, Fraction(1)),
])
def test_fisher_one_sided_matches_known_values(l, nl, b, nb, expected):
    assert fisher_one_sided_less(l, nl, b, nb) == expected


def test_fisher_rejects_counts_outside_their_range():
    for args in ((4, 3, 0, 3), (-1, 3, 0, 3), (0, 3, 1.0, 3)):
        with pytest.raises(ValueError):
            fisher_one_sided_less(*args)


def calibration():
    spec = importlib.util.spec_from_file_location('phase20_null_calibration',
                                                  ROOT / 'scripts/experiments/phase20_null_calibration.py')
    loaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(loaded)
    return loaded


def test_rule3_v2_agrees_with_the_phase20_calibration_on_every_cell():
    cal = calibration()
    for b in range(16):
        for l in range(16):
            assert rule3_v2(l, 15, b, 15)['harm'] == cal.harm_v2(b, l), (b, l)


def test_rule3_v2_reproduces_the_programs_design_figures():
    """Program table (design_tradeoff2.out): q = 0.33, v2 null false alarm 0.020, power 0.92 on a full loss."""
    cal = calibration()
    harm = lambda b, l, n: rule3_v2(l, n, b, n)['harm']  # noqa: E731
    assert round(cal.rule3(15, 0.33, 0.33, harm), 3) == 0.020
    assert round(cal.rule3(15, 0.33, 0.0, harm), 3) == 0.917
    # v1 at n = 3, the same scenario (Appendix B): 0.331 and 0.699.
    assert (round(cal.rule3(3, 0.33, 0.33, cal.harm_v1), 3), round(cal.rule3(3, 0.33, 0.0, cal.harm_v1), 3)) == (0.331, 0.699)


# ----------------------------------------------------------------- the v2 predicate

V2_CASES = [{'case_id': 'healthy', 'fault_spec': {'primitives': []}},
            {'case_id': 'fault', 'fault_spec': {'primitives': [{'kind': 'F4'}]}},
            {'case_id': 'refusal', 'fault_spec': {'primitives': [{'kind': 'F2'}]}}]


def t2(eid, arm, outcome, index, *, checks=(), scheduled=True, lifecycle='COMPLETED'):
    return SimpleNamespace(episode_id=eid, arm=arm, outcome=outcome, failed_checks=list(checks), trial_index=index,
                           fault_scheduled=scheduled, fault_triggered=True, lifecycle=lifecycle, usage=Usage())


def arm(done=0, n=15, key=C, other=S):
    return [key] * done + [other] * (n - done)


def v2_batch(outcomes, *, cases=V2_CASES, complete=True, retained=None):
    """outcomes {case_id: (B0 list, L list)} in replica order; the batch in execution order.
    retained {(position, index): [trials]} are lab-error trials run before that position's clean pair."""
    trials, pairs = [], []
    faulty = {c['case_id']: bool(c['fault_spec']['primitives']) for c in cases}
    for position, (case_id, replica) in enumerate(replica_layout(cases)):
        for index in range(3):
            k = replica * 3 + index
            b0, l = outcomes[case_id][0][k], outcomes[case_id][1][k]
            trials += (retained or {}).get((position, index), [])
            a = t2(f'b-{case_id}-{replica}-{index}', 'B0', b0, index, scheduled=faulty[case_id])
            b = t2(f'l-{case_id}-{replica}-{index}', 'L', l, index, scheduled=faulty[case_id],
                   checks=['C6'] if l == V else ())
            trials += [a, b]; pairs.append((a.episode_id, b.episode_id))
    return SimpleNamespace(trials=trials, trial_pairs=pairs, decision='NO_CHANGE' if complete else 'INCOMPLETE')


def clean(**changes):
    outcomes = {'healthy': (arm(3, 3), arm(3, 3)), 'fault': (arm(9), arm(9)),
                'refusal': (arm(15, key=R), arm(15, key=R))}
    outcomes.update(changes)
    return outcomes


def test_the_layout_runs_every_first_replica_first_and_sizes_heldout2_at_78_pairs():
    layout = replica_layout(V2_CASES)
    assert layout[:3] == [('healthy', 0), ('fault', 0), ('refusal', 0)]
    assert layout[3:] == [(case, r) for r in range(1, FAULT_REPLICAS) for case in ('fault', 'refusal')]
    assert [p for p in layout if p[0] == 'fault'] == [('fault', r) for r in range(5)]
    assert [p for p in layout if p[0] == 'healthy'] == [('healthy', 0)]
    heldout2 = [{'case_id': 'none', 'fault_spec': {'primitives': []}}] + [
        {'case_id': f'k{i}', 'fault_spec': {'primitives': [{'kind': 'F'}]}} for i in range(5)]
    assert len(replica_layout(heldout2)) * 3 == 78


def test_v2_no_harm_stores_pooled_and_per_replica_counts():
    result = assess_heldout_v2(v2_batch(clean()), V2_CASES)
    assert result['decision'] == 'NO_HARM' and result['predicate'] == PREDICATE_V2
    assert result['by_case']['fault']['L']['attempted'] == 15 and result['by_case']['healthy']['L']['attempted'] == 3
    assert len(result['by_case_replica']['fault']) == 5 and len(result['by_case_replica']['healthy']) == 1
    assert result['rule3']['fault']['completed']['n_L'] == 15 and set(result['rule3']) == {'fault', 'refusal'}
    assert result['rule4'] == {'healthy': {'L_completed': 3, 'n_L': 3, 'harm': False}}


def test_v2_fisher_branch_fires():
    result = assess_heldout_v2(v2_batch(clean(fault=(arm(6), arm(1)))), V2_CASES)
    assert (result['decision'], result['rule'], result['case_id']) == ('HARM', 'lost_outcome', 'fault')
    test = result['rule3']['fault']['completed']
    assert test['fisher'] and not test['zero_floor'] and Fraction(test['p_exact']) == Fraction(81510, 2035800)


def test_v2_or_branch_fires_where_fisher_cannot():
    result = assess_heldout_v2(v2_batch(clean(fault=(arm(3), arm(0)))), V2_CASES)
    test = result['rule3']['fault']['completed']
    assert result['decision'] == 'HARM' and result['rule'] == 'lost_outcome'
    assert not test['fisher'] and test['zero_floor'] and test['p_value'] > 0.1


@pytest.mark.parametrize('b0,l', [(5, 1), (2, 0), (9, 7), (0, 0)])
def test_v2_does_not_fire_below_its_threshold(b0, l):
    result = assess_heldout_v2(v2_batch(clean(fault=(arm(b0), arm(l)))), V2_CASES)
    assert result['decision'] == 'NO_HARM' and not result['rule3']['fault']['completed']['harm']


def test_v2_boundary_cell_is_compared_exactly():
    result = assess_heldout_v2(v2_batch(clean(fault=(arm(4), arm(0)))), V2_CASES)
    test = result['rule3']['fault']['completed']
    assert test['fisher'] and test['zero_floor'] and Fraction(test['p_exact']) == Fraction(1365, 27405)


def test_v2_applies_rule3_to_correct_refusals():
    result = assess_heldout_v2(v2_batch(clean(refusal=(arm(3, key=R), arm(0, key=R)))), V2_CASES)
    assert (result['decision'], result['rule'], result['case_id']) == ('HARM', 'lost_outcome', 'refusal')
    assert result['harm_findings'] == [{'rule': 'lost_outcome', 'case_id': 'refusal', 'key': 'correctly_rejected'}]


def test_v2_rule4_is_unchanged_three_of_three():
    result = assess_heldout_v2(v2_batch(clean(healthy=(arm(2, 3), arm(2, 3)))), V2_CASES)
    assert (result['decision'], result['rule'], result['case_id']) == ('HARM', 'no_fault', 'healthy')


def test_v2_lists_every_rule_that_fires_and_names_the_first():
    result = assess_heldout_v2(v2_batch(clean(healthy=(arm(3, 3), arm(2, 3)), fault=(arm(6), arm(0)),
                                              refusal=(arm(15, key=R), arm(0, key=R)))), V2_CASES)
    assert [(f['rule'], f['case_id']) for f in result['harm_findings']] == [
        ('no_fault', 'healthy'), ('lost_outcome', 'fault'), ('lost_outcome', 'refusal')]
    assert result['rule'] == 'no_fault'


def test_v2_decides_and_v1_on_the_first_replica_is_descriptive_only():
    # First replica: L 2 of 3 vs B0 3 of 3 (v1 would say HARM). Pooled: L 13 vs B0 14 (v2: no harm).
    fault = ([C] * 3 + arm(11, 12), [C, C, S] + arm(11, 12))
    result = assess_heldout_v2(v2_batch(clean(fault=fault)), V2_CASES)
    assert result['decision'] == 'NO_HARM'
    v1 = result['v1_first_replica']
    assert v1['descriptive_only'] and v1['predicate'] == PREDICATE and v1['attribution'] == 'execution_order'
    assert (v1['decision'], v1['rule'], v1['case_id']) == ('HARM', 'lost_outcome', 'fault')
    assert v1['by_case']['fault']['L']['attempted'] == 3


def test_v2_rule1_covers_retained_trials_in_any_replica_and_attribution_is_by_execution_order():
    damaged = t2('lx', 'L', 'LAB_ERROR', 1, checks=['C2', 'C5', 'C6', 'C7'], lifecycle='LAB_ERROR')
    partner = t2('bx', 'B0', C, 1)
    later = v2_batch(clean(), retained={(4, 1): [partner, damaged]})      # position 4 = fault replica 1
    result = assess_heldout_v2(later, V2_CASES)
    assert (result['decision'], result['rule'], result['candidate_failures']) == ('HARM', 'check_failure', ['lx'])
    assert result['v1_first_replica']['decision'] == 'NO_HARM'
    first = v2_batch(clean(), retained={(1, 1): [partner, damaged]})      # position 1 = fault replica 0
    assert assess_heldout_v2(first, V2_CASES)['v1_first_replica']['rule'] == 'check_failure'
    assert position_trials(first, len(replica_layout(V2_CASES)))[1][2:4] == [partner, damaged]


def test_v2_incomplete_unless_every_pair_is_valid_and_a_candidate_failure_is_still_harm():
    assert assess_heldout_v2(v2_batch(clean(), complete=False), V2_CASES)['decision'] == 'INCOMPLETE'
    result = assess_heldout_v2(v2_batch(clean(fault=(arm(9), arm(9)[:14] + [V])), complete=False), V2_CASES)
    assert (result['decision'], result['rule']) == ('HARM', 'check_failure')


def test_v2_refuses_a_layout_whose_first_positions_are_not_the_first_replicas():
    layout = replica_layout(V2_CASES)
    with pytest.raises(ValueError):
        assess_heldout_v2(v2_batch(clean()), V2_CASES, layout=layout[1:] + layout[:1])


# ----------------------------------------------------------------- the sealed partition

def spec(primitives, seed):
    return FaultSpec.model_validate({'seed': seed, 'primitives': primitives}).model_dump(mode='json')


SYNTHETIC = [
    {'case_id': 'syn-1', 'fixture_id': 'standard-v1', 'fault_spec': spec([], 900)},
    {'case_id': 'syn-2', 'fixture_id': 'standard-v1', 'fault_spec': spec([{
        'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
        'parameters': {'completion_delay_ticks': 3, 'terminal_status': 'SUCCEEDED', 'failure_code': None}}], 901)},
]


@pytest.fixture
def sealed(tmp_path, monkeypatch):
    """A synthetic partition inside a synthetic application root; the novelty scope is synthetic too."""
    monkeypatch.setattr(module, 'APP_ROOT', tmp_path)
    monkeypatch.setattr(module, 'excluded_identities', lambda: frozenset({'x' * 64}))
    def write(cases=SYNTHETIC, name='sealed', raw=None):
        directory = tmp_path / name; directory.mkdir(exist_ok=True)
        (directory / module.PARTITION_FILE_V2).write_text(raw if raw is not None else json.dumps({'cases': cases}))
        return name, content_hash(cases)
    return write


def test_a_partition_loads_only_under_its_pinned_manifest_hash(sealed):
    name, digest = sealed()
    assert load_partition(name, digest) == SYNTHETIC
    with pytest.raises(StoreConflict, match='pinned manifest hash'):
        load_partition(name, 'f' * 64)
    tampered = json.loads(json.dumps(SYNTHETIC)); tampered[1]['fault_spec']['primitives'][0]['parameters']['completion_delay_ticks'] = 4
    name2, _ = sealed(tampered, name='tampered')
    with pytest.raises(StoreConflict, match='pinned manifest hash'):
        load_partition(name2, digest)


@pytest.mark.parametrize('cases,message', [
    ([SYNTHETIC[0]], 'exactly one no-fault'),
    ([SYNTHETIC[1]], 'exactly one no-fault'),
    ([SYNTHETIC[0], SYNTHETIC[0] | {'case_id': 'syn-3'}, SYNTHETIC[1]], 'exactly one no-fault'),
    ([SYNTHETIC[0], SYNTHETIC[1] | {'case_id': 'syn-1'}], 'unique'),
    ([SYNTHETIC[0], {'case_id': 'bad', 'fault_spec': {'primitives': [{'kind': 'F9'}]}}], 'not a valid fault schedule'),
])
def test_a_malformed_partition_is_refused_even_under_its_own_hash(sealed, cases, message):
    name, digest = sealed(cases)
    with pytest.raises(StoreConflict, match=message):
        load_partition(name, digest)


def test_a_missing_unreadable_or_outside_partition_is_refused(sealed, tmp_path):
    with pytest.raises(StoreConflict, match='no sealed partition file'):
        load_partition('absent', 'a' * 64)
    name, _ = sealed(raw='{not json', name='garbled')
    with pytest.raises(StoreConflict, match='cannot be read'):
        load_partition(name, 'a' * 64)
    with pytest.raises(StoreConflict, match='inside the application root'):
        load_partition(str(tmp_path.parent), 'a' * 64)
    with pytest.raises(StoreConflict, match='inside the application root'):
        load_partition('../elsewhere', 'a' * 64)


def test_the_novelty_rule_refuses_a_case_the_excluded_partitions_contain(sealed, monkeypatch):
    name, digest = sealed()
    identity = schedule_identity(FaultSpec.model_validate(SYNTHETIC[1]['fault_spec']))
    monkeypatch.setattr(module, 'excluded_identities', lambda: frozenset({identity}))
    with pytest.raises(StoreConflict, match='novelty'):
        load_partition(name, digest)
    # Seeds are metadata: a re-seeded copy of an excluded schedule is the same identity.
    reseeded = json.loads(json.dumps(SYNTHETIC)); reseeded[1]['fault_spec']['seed'] = 12345
    name2, digest2 = sealed(reseeded, name='reseeded')
    with pytest.raises(StoreConflict, match='novelty'):
        load_partition(name2, digest2)


def test_check_plan_default_is_exactly_the_phase18_check(monkeypatch):
    synthetic_promotion = [dict(case) for case in SYNTHETIC]
    monkeypatch.setattr(module, 'load_cases', lambda name: synthetic_promotion if name == 'promotion' else None)
    plan = check_plan()
    assert (plan['predicate'], plan['partition'], plan['extra']) == (PREDICATE, 'promotion', {})
    assert plan['cases'] is synthetic_promotion and plan['manifest_hash'] == content_hash(synthetic_promotion)
    assert check_plan(predicate=PREDICATE)['predicate'] == PREDICATE


@pytest.mark.parametrize('kwargs,message', [
    ({'predicate': 'faultlab-heldout-no-harm/v2'}, 'needs a sealed partition'),
    ({'predicate': 'faultlab-heldout-no-harm/v9'}, 'needs a sealed partition'),
    ({'partition_dir': 'sealed'}, 'both'),
    ({'manifest_hash': 'a' * 64}, 'both'),
    ({'partition_dir': 'sealed', 'manifest_hash': 'a' * 64, 'predicate': 'faultlab-heldout-no-harm/v1'}, 'only by predicate v2'),
])
def test_check_plan_refuses_undeclared_combinations(kwargs, message):
    with pytest.raises(ValueError, match=message):
        check_plan(**kwargs)


def test_check_plan_v2_records_partition_predicate_pin_and_layout(sealed):
    name, digest = sealed()
    plan = check_plan(name, digest)
    extra = plan['extra']
    assert (plan['predicate'], plan['partition'], plan['manifest_hash']) == (PREDICATE_V2, 'heldout-2', digest)
    assert extra['schema_version'] == 'faultlab-heldout-check/v2' and extra['partition_dir'] == name
    assert extra['layout'] == [['syn-1', 0], ['syn-2', 0], ['syn-2', 1], ['syn-2', 2], ['syn-2', 3], ['syn-2', 4]]
    assert (extra['planned_pairs'], extra['planned_episodes']) == (18, 36)
    assert extra['evaluated_manifest_hash'] == content_hash([SYNTHETIC[0]] + [SYNTHETIC[1]] * 5)


def test_the_request_model_keeps_the_phase18_body_and_pins_the_hash_shape():
    from app.lab.api import HeldoutCheckRequest
    old = HeldoutCheckRequest(execute_live=True, certified_study_id='completion-study-1')
    assert (old.partition_dir, old.manifest_hash, old.predicate) == (None, None, None)
    with pytest.raises(Exception):
        HeldoutCheckRequest(execute_live=True, certified_study_id='s', manifest_hash='not-a-hash')
    with pytest.raises(Exception):
        HeldoutCheckRequest(execute_live=True, certified_study_id='s', partition='heldout-2')


def test_the_route_passes_the_partition_through_and_keeps_the_phase18_call(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.lab.api import create_router
    calls = []

    async def fake_queue(coordinator, campaign_id, study_id, **kwargs):
        calls.append((campaign_id, study_id, kwargs)); return {'check_id': 'heldout-check-x'}
    monkeypatch.setattr(module, 'queue_heldout_check', fake_queue)
    app = FastAPI(); app.include_router(create_router(lambda: object()))
    client = TestClient(app)
    assert client.post('/api/campaigns/c1/heldout-check', json={'execute_live': True, 'certified_study_id': 's1'}).status_code == 202
    body = {'execute_live': True, 'certified_study_id': 's1', 'partition_dir': 'sealed', 'manifest_hash': 'a' * 64,
            'predicate': PREDICATE_V2}
    assert client.post('/api/campaigns/c1/heldout-check', json=body).status_code == 202
    assert calls == [('c1', 's1', {'partition_dir': None, 'manifest_hash': None, 'predicate': None}),
                     ('c1', 's1', {'partition_dir': 'sealed', 'manifest_hash': 'a' * 64, 'predicate': PREDICATE_V2})]
    assert client.post('/api/campaigns/c1/heldout-check', json={**body, 'manifest_hash': 'A' * 64}).status_code == 422
    assert len(calls) == 2


# ----------------------------------------------------------------- v2 end to end, offline

PHASE18_RECORD_KEYS = {'schema_version', 'check_id', 'campaign_id', 'status', 'decision', 'reason', 'predicate',
                       'certified_study_id', 'policy_version', 'policy_hash', 'incumbent_hash',
                       'actor_context_protocol', 'partition', 'manifest_hash', 'configuration_hash', 'attempt',
                       'ordinary_policy_accepted', 'batch_id', 'assessment', 'created_at'}


@pytest.mark.anyio
async def test_one_v2_check_runs_the_sealed_partition_replicated_on_v4_and_never_accepts(tmp_path, monkeypatch):
    c, study, client = await certified_study(tmp_path)
    try:
        monkeypatch.setattr(module, 'APP_ROOT', tmp_path)
        monkeypatch.setattr(module, 'excluded_identities', lambda: frozenset())
        (tmp_path / 'sealed').mkdir()
        (tmp_path / 'sealed' / module.PARTITION_FILE_V2).write_text(json.dumps({'cases': SYNTHETIC}))
        campaign = fresh_campaign(c)
        queued = await queue_heldout_check(c, campaign.campaign_id, study['study_id'], partition_dir='sealed',
                                           manifest_hash=content_hash(SYNTHETIC))
        plan = c.store.get_record('heldout_plans', queued['check_id'])
        assert (plan['predicate'], plan['partition'], plan['manifest_hash']) == (PREDICATE_V2, 'heldout-2', content_hash(SYNTHETIC))
        assert plan['schema_version'] == 'faultlab-heldout-check/v2' and plan['planned_pairs'] == 18
        await c.tasks[queued['check_id']]
        record = c.store.get_record('heldout_checks', queued['check_id'])
        assert record['predicate'] == PREDICATE_V2 and record['partition'] == 'heldout-2'
        assert record['decision'] in ('NO_HARM', 'HARM', 'INCOMPLETE') and record['status'] in ('COMPLETED', 'INCOMPLETE')
        assert record['assessment']['predicate'] == PREDICATE_V2 and record['assessment']['v1_first_replica']['descriptive_only']
        batch = c.store.get_record('evaluations', record['batch_id'])
        assert batch['split'] == 'promotion' and batch['candidate_hash'] == study['selected_candidate_hash']
        assert len(batch['trial_pairs']) == 18 and batch['manifest_hash'] == record['evaluated_manifest_hash']
        stamped = set()
        for raw in batch['trials']:
            episode = c.store.get_record('episodes', raw['episode_id'])
            assert episode['split'] == 'promotion' and episode['experiment_purpose'] == 'promotion'
            stamped |= {e['payload'].get('actor_context_protocol') for e in c.store.events(raw['episode_id'])['events']
                        if e['type'] == 'actor_output'}
        assert stamped == {ACTOR_CONTEXT_PROTOCOL_V4}
        assert not c.store.list_records('promotion_decisions')
        assert c.policies.get(study['selected_candidate_version']).decision == 'PROPOSED'
        assert c.store.get_pointer('accepted-policy:' + campaign.configuration_hash) is None
        assert c.active_id is None and record['ordinary_policy_accepted'] is False
        if record['decision'] in ('NO_HARM', 'HARM'):
            # A verdict under v2 is final under every predicate.
            with pytest.raises(StoreConflict, match='final'):
                await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'])
            with pytest.raises(StoreConflict, match='final'):
                await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'], partition_dir='sealed',
                                          manifest_hash=content_hash(SYNTHETIC))
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_the_default_request_is_still_the_phase18_check_with_its_exact_record(tmp_path, monkeypatch):
    c, study, client = await certified_study(tmp_path)
    try:
        synthetic_promotion = [dict(case) for case in SYNTHETIC]
        monkeypatch.setattr(module, 'load_cases', lambda name: synthetic_promotion)

        class Refusing:
            def __init__(self, *a, **k): pass
            async def run(self, campaign_arg, cases, *a, **k):
                assert cases is synthetic_promotion and k['actor_context_protocol'] == ACTOR_CONTEXT_PROTOCOL_V4
                raise RuntimeError('stop before any call')
        monkeypatch.setattr(module, 'PairedEvaluator', Refusing)
        queued = await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'])
        assert set(queued) == PHASE18_RECORD_KEYS | {'world_integrity_protocol'} and queued['schema_version'] == 'faultlab-heldout-check/v1'
        assert queued['world_integrity_protocol'] == module.WORLD_INTEGRITY_PROTOCOL
        assert (queued['predicate'], queued['partition'], queued['manifest_hash']) == (
            PREDICATE, 'promotion', content_hash(synthetic_promotion))
        await c.tasks[queued['check_id']]
        assert c.store.get_record('heldout_checks', queued['check_id'])['decision'] == 'INCOMPLETE'
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_a_phase18_verdict_blocks_a_v2_check_and_attempts_count_across_partitions(tmp_path, sealed):
    c, study, client = await certified_study(tmp_path)
    try:
        name, digest = sealed()
        c.store.put_record('heldout_checks', 'heldout-check-v1', {
            'check_id': 'heldout-check-v1', 'campaign_id': 'campaign-old', 'status': 'COMPLETED', 'decision': 'HARM',
            'predicate': PREDICATE, 'partition': 'promotion', 'policy_hash': study['selected_candidate_hash']})
        with pytest.raises(StoreConflict, match='final'):
            await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'], partition_dir=name,
                                      manifest_hash=digest)
        c.store.put_record('heldout_checks', 'heldout-check-v1', {
            'check_id': 'heldout-check-v1', 'campaign_id': 'campaign-old', 'status': 'INCOMPLETE',
            'decision': 'INCOMPLETE', 'policy_hash': study['selected_candidate_hash']})
        for i in range(MAX_ATTEMPTS_PER_POLICY - 1):
            c.store.put_record('heldout_checks', f'heldout-check-v2-{i}', {
                'check_id': f'heldout-check-v2-{i}', 'campaign_id': f'campaign-v2-{i}', 'status': 'INCOMPLETE',
                'decision': 'INCOMPLETE', 'predicate': PREDICATE_V2, 'policy_hash': study['selected_candidate_hash']})
        with pytest.raises(StoreConflict, match='attempt limit'):
            await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'], partition_dir=name,
                                      manifest_hash=digest)
        assert c.active_id is None
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_a_partition_refusal_starts_nothing(tmp_path, sealed):
    c, study, client = await certified_study(tmp_path)
    try:
        name, _ = sealed()
        campaign = fresh_campaign(c)
        with pytest.raises(StoreConflict, match='pinned manifest hash'):
            await queue_heldout_check(c, campaign.campaign_id, study['study_id'], partition_dir=name,
                                      manifest_hash='e' * 64)
        assert not c.store.list_records('heldout_checks') and c.active_id is None
        assert c.get(campaign.campaign_id).state == 'IDLE'
    finally:
        await client.aclose()


# ----------------------------------------------------------------- review round 1: no promotion oracle

def test_the_check_time_novelty_scope_is_the_public_completion_manifest_only(monkeypatch):
    """Review round 1: comparing the private promotion partition at check time let any API caller
    ask, through the refusal message, whether a schedule is in it. Only 7ab9368e is compared here."""
    from app.lab.completion_study import case_manifest
    monkeypatch.setattr(module, 'load_cases', lambda name: (_ for _ in ()).throw(AssertionError(name)))
    expected = {schedule_identity(FaultSpec.model_validate(case['fault_spec'])) for case in case_manifest()['cases']
                if case['fault_spec']['primitives']}
    assert module.excluded_identities() == frozenset(expected)


def promotion_probe_partitions(tmp_path):
    """Two sealed partitions that differ only in whether their fault case repeats a (synthetic)
    promotion schedule. Neither schedule is in 7ab9368e."""
    named = [SYNTHETIC[0], {**SYNTHETIC[1], 'fault_spec': SYNTHETIC_PROMOTION[1]['fault_spec']}]
    other = [SYNTHETIC[0], SYNTHETIC[1]]
    promoted = schedule_identity(FaultSpec.model_validate(SYNTHETIC_PROMOTION[1]['fault_spec']))
    assert schedule_identity(FaultSpec.model_validate(named[1]['fault_spec'])) == promoted
    assert schedule_identity(FaultSpec.model_validate(other[1]['fault_spec'])) != promoted
    found = []
    for name, cases in (('named', named), ('other', other)):
        (tmp_path / name).mkdir()
        (tmp_path / name / module.PARTITION_FILE_V2).write_text(json.dumps({'cases': cases}))
        found.append((name, content_hash(cases)))
    return found


def answer(error):
    from app.lab.api import error_response
    body = json.loads(error_response(error).body)['error']
    return error_response(error).status_code, body['code'], body['message']


@pytest.mark.anyio
async def test_a_partition_naming_a_promotion_schedule_gets_the_same_answer_as_one_that_does_not(tmp_path, monkeypatch):
    c, study, client = await certified_study(tmp_path)
    try:
        monkeypatch.setattr(module, 'APP_ROOT', tmp_path)
        requested = []
        loader = module.load_cases
        monkeypatch.setattr(module, 'load_cases', lambda name: requested.append(name) or loader(name))
        partitions = promotion_probe_partitions(tmp_path)
        # The plan itself: both load, so no refusal can tell them apart.
        assert [check_plan(name, digest)['partition'] for name, digest in partitions] == ['heldout-2', 'heldout-2']
        # An unknown campaign, and then a policy whose verdict is final: the same answer for both.
        answers = []
        for name, digest in partitions:
            with pytest.raises(KeyError) as missing:
                await queue_heldout_check(c, 'campaign-missing', study['study_id'], partition_dir=name, manifest_hash=digest)
            answers.append(answer(missing.value))
        assert answers[0] == answers[1] == (404, 'NOT_FOUND', 'Unknown record')
        c.store.put_record('heldout_checks', 'heldout-check-final', {
            'check_id': 'heldout-check-final', 'campaign_id': 'campaign-old', 'status': 'COMPLETED', 'decision': 'HARM',
            'predicate': PREDICATE, 'partition': 'promotion', 'policy_hash': study['selected_candidate_hash']})
        answers = []
        for name, digest in partitions:
            with pytest.raises(StoreConflict) as final:
                await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'], partition_dir=name,
                                          manifest_hash=digest)
            answers.append(answer(final.value))
        assert answers[0] == answers[1] and 'final' in answers[0][2]
        assert 'promotion' not in requested and c.active_id is None
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_a_sealed_partition_serves_exactly_one_policy(tmp_path, sealed):
    """PHASE22_EXPERIMENT.md section 7.5, enforced in the backend (review round 1)."""
    c, study, client = await certified_study(tmp_path)
    try:
        name, digest = sealed()
        c.store.put_record('heldout_checks', 'heldout-check-other', {
            'check_id': 'heldout-check-other', 'campaign_id': 'campaign-other', 'status': 'INCOMPLETE',
            'decision': 'INCOMPLETE', 'predicate': PREDICATE_V2, 'partition': 'heldout-2', 'manifest_hash': digest,
            'policy_hash': 'f' * 64})
        campaign = fresh_campaign(c)
        with pytest.raises(StoreConflict, match='another policy'):
            await queue_heldout_check(c, campaign.campaign_id, study['study_id'], partition_dir=name, manifest_hash=digest)
        assert c.active_id is None and c.get(campaign.campaign_id).state == 'IDLE'
        # The same policy's earlier attempt on the partition is not a second policy: it only counts.
        c.store.put_record('heldout_checks', 'heldout-check-other', {
            'check_id': 'heldout-check-other', 'campaign_id': 'campaign-other', 'status': 'INCOMPLETE',
            'decision': 'INCOMPLETE', 'predicate': PREDICATE_V2, 'partition': 'heldout-2', 'manifest_hash': digest,
            'policy_hash': study['selected_candidate_hash']})
        for i in range(MAX_ATTEMPTS_PER_POLICY - 1):
            c.store.put_record('heldout_checks', f'heldout-check-same-{i}', {
                'check_id': f'heldout-check-same-{i}', 'campaign_id': f'campaign-same-{i}', 'status': 'INCOMPLETE',
                'decision': 'INCOMPLETE', 'predicate': PREDICATE_V2, 'manifest_hash': digest,
                'policy_hash': study['selected_candidate_hash']})
        with pytest.raises(StoreConflict, match='attempt limit'):
            await queue_heldout_check(c, campaign.campaign_id, study['study_id'], partition_dir=name, manifest_hash=digest)
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_the_one_policy_rule_never_touches_the_v1_request(tmp_path, monkeypatch):
    """A v2 record naming another policy leaves the Phase 18 request exactly as it was."""
    c, study, client = await certified_study(tmp_path)
    try:
        c.store.put_record('heldout_checks', 'heldout-check-other', {
            'check_id': 'heldout-check-other', 'campaign_id': 'campaign-other', 'status': 'INCOMPLETE',
            'decision': 'INCOMPLETE', 'predicate': PREDICATE_V2, 'manifest_hash': content_hash(SYNTHETIC_PROMOTION),
            'policy_hash': 'f' * 64})

        class Refusing:
            def __init__(self, *a, **k): pass
            async def run(self, *a, **k): raise RuntimeError('stop before any call')
        monkeypatch.setattr(module, 'PairedEvaluator', Refusing)
        queued = await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'])
        assert set(queued) == PHASE18_RECORD_KEYS | {'world_integrity_protocol'} and queued['predicate'] == PREDICATE
        assert queued['world_integrity_protocol'] == module.WORLD_INTEGRITY_PROTOCOL
        await c.tasks[queued['check_id']]
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_the_one_policy_guard_admits_the_same_policys_next_attempt_and_ignores_other_partitions(
        tmp_path, sealed, monkeypatch):
    """Review round 2: the routed policy's INCOMPLETE first attempt on heldout-2 must not block its
    second (a guard that refused any record with the same manifest_hash would end Phase 24 with a $0
    409 on every resume), and a record of another policy on ANOTHER partition must not refuse."""
    c, study, client = await certified_study(tmp_path)
    try:
        name, digest = sealed()
        c.store.put_record('heldout_checks', 'heldout-check-elsewhere', {
            'check_id': 'heldout-check-elsewhere', 'campaign_id': 'campaign-elsewhere', 'status': 'INCOMPLETE',
            'decision': 'INCOMPLETE', 'predicate': PREDICATE_V2, 'partition': 'heldout-2', 'manifest_hash': 'e' * 64,
            'policy_hash': 'f' * 64})

        class Refusing:
            def __init__(self, *a, **k): pass
            async def run(self, *a, **k): raise RuntimeError('stop before any call')
        monkeypatch.setattr(module, 'PairedEvaluator', Refusing)
        first = await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'], partition_dir=name,
                                          manifest_hash=digest)
        assert (first['attempt'], first['predicate'], first['manifest_hash']) == (1, PREDICATE_V2, digest)
        await c.tasks[first['check_id']]
        assert c.store.get_record('heldout_checks', first['check_id'])['decision'] == 'INCOMPLETE'
        second = await queue_heldout_check(c, fresh_campaign(c).campaign_id, study['study_id'], partition_dir=name,
                                           manifest_hash=digest)
        assert (second['attempt'], second['policy_hash'], second['manifest_hash']) == (
            2, study['selected_candidate_hash'], digest)
        await c.tasks[second['check_id']]
        assert c.active_id is None
    finally:
        await client.aclose()
