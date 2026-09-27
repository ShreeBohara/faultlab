"""Offline gate regressions: infrastructure retries never erase agent mistakes."""
import pytest

from app.contracts.models import ChallengeResult, content_hash
from app.lab.challenge import Challenger
from app.lab.evaluation import PairedEvaluator, observed_candidate_violations, paired_complete
from app.lab.learning import source_validation_assessment
from app.lab.promotion import promotion_decision
from test_challenge import FixedFixtureExplorer
from test_evaluation import cases, setup


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def fail_first_pair(runner, *, candidate_violation=True):
    """First incumbent has a lab error; its candidate still receives a fixed score."""
    original = runner.run
    attempts = []

    async def run(*args, **kwargs):
        trial = await original(*args, **kwargs)
        if not attempts:
            trial.lifecycle = 'LAB_ERROR'
            trial.outcome = 'LAB_ERROR'
            trial.failed_checks = []
        elif len(attempts) == 1 and candidate_violation:
            trial.outcome = 'VIOLATION'
            trial.failed_checks = ['C3']
        attempts.append(trial)
        return trial

    runner.run = run
    return attempts


def passed_challenge(source):
    return ChallengeResult(
        challenge_id='offline-passed-challenge', candidate_hash=source.candidate_hash,
        incumbent_hash=source.incumbent_hash, source_validation_ref=source.batch_id,
        schedule_hashes=[content_hash(i) for i in range(4)], selection_refs=['offline-selection'],
        novel_schedule_hashes=[content_hash(1)],
        trial_pairs=[(f'incumbent-{i}', f'candidate-{i}') for i in range(12)],
        failed_checks=[], status='PASSED_OBSERVED', stopping_reason='Offline gate fixture',
    )


@pytest.mark.anyio
async def test_source_rejects_candidate_violation_from_replaced_pair(tmp_path):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    attempts = fail_first_pair(runner)
    batch = await PairedEvaluator(c.store, runner, ledger).run(
        campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation',
    )
    assessment = source_validation_assessment(batch, 'C3')
    assert paired_complete(batch, 3) and len(batch.trials) == 8
    assert attempts[1].episode_id not in {eid for pair in batch.trial_pairs for eid in pair}
    assert assessment['classification'] == 'CANDIDATE_FAILED'
    assert assessment['decision'] == 'REJECTED'
    assert assessment['candidate_violation_episode_ids'] == [attempts[1].episode_id]
    assert assessment['qualification_candidate_violation_episode_ids'] == []
    assert c.store.get_record('evaluations', batch.batch_id)['trials'][1]['outcome'] == 'VIOLATION'
    await c.close()


@pytest.mark.anyio
async def test_challenge_returns_replaced_pair_failure_as_counterexample(tmp_path):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    attempts = fail_first_pair(runner)
    ledger.reserve('candidate', 538)
    challenge = await Challenger(c.store, FixedFixtureExplorer(), evaluator).run(
        campaign, c.policies.baseline(), candidate, source, reservation='candidate',
    )
    assert challenge.status == 'COUNTEREXAMPLE_FOUND' and challenge.failed_checks == ['C3']
    assert len(challenge.schedule_hashes) == 1 and len(attempts) == 8
    counterexample = c.store.get_record('challenge_counterexamples', candidate.version)
    assert attempts[1].episode_id in counterexample['trial_ids']
    assert c.store.get_pointer(f'active-policy:{campaign.campaign_id}') == 'policy-v0'
    await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('stage', ['source_validation', 'promotion'])
async def test_promotion_vetoes_retained_failure_in_either_required_batch(tmp_path, stage):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    evaluator = PairedEvaluator(c.store, runner, ledger)
    if stage == 'source_validation':
        fail_first_pair(runner)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    if stage == 'promotion':
        fail_first_pair(runner)
    promotion = await evaluator.run(campaign, cases(6), c.policies.baseline(), candidate)
    assert paired_complete(source, 3) and paired_complete(promotion, 18)
    decision, reason = promotion_decision(source, passed_challenge(source), promotion, target_invariant='C3')
    assert decision == 'REJECTED' and 'retained scored attempt' in reason
    await c.close()


@pytest.mark.anyio
async def test_infrastructure_retry_alone_does_not_invent_candidate_failure(tmp_path):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    fail_first_pair(runner, candidate_violation=False)
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    promotion = await evaluator.run(campaign, cases(6), c.policies.baseline(), candidate)
    assert source_validation_assessment(source, 'C3')['classification'] == 'PASSED'
    assert promotion_decision(source, passed_challenge(source), promotion, target_invariant='C3')[0] == 'ACCEPTED'
    assert len(source.trials) == 8 and sum(t.lifecycle == 'LAB_ERROR' for t in source.trials) == 1
    await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('lifecycle,outcome', [('LAB_ERROR', 'LAB_ERROR'), ('INTERRUPTED', 'VIOLATION')])
async def test_incomplete_or_infrastructure_trial_is_not_a_scored_agent_failure(tmp_path, lifecycle, outcome):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    promotion = await evaluator.run(campaign, cases(6), c.policies.baseline(), candidate)
    trial = next(t for t in source.trials if t.arm == 'L')
    trial.lifecycle = lifecycle
    trial.outcome = outcome
    trial.failed_checks = ['C5']  # Partial diagnostics must not become a valid score.
    assert not observed_candidate_violations(source)
    assert source_validation_assessment(source, 'C3')['classification'] == 'INCOMPLETE_PAIRS'
    assert promotion_decision(source, passed_challenge(source), promotion, target_invariant='C3')[0] == 'INCOMPLETE'
    await c.close()


@pytest.mark.anyio
async def test_untriggered_scored_violation_cannot_be_erased_by_coverage_status(tmp_path):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    batch = await PairedEvaluator(c.store, runner, ledger).run(
        campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation',
    )
    trial = next(t for t in batch.trials if t.arm == 'L')
    trial.fault_scheduled = True
    trial.fault_triggered = False
    trial.outcome = 'VIOLATION'
    trial.failed_checks = ['C3']
    assert not paired_complete(batch, 3)
    assert observed_candidate_violations(batch) == [trial]
    assessment = source_validation_assessment(batch, 'C3')
    assert assessment['classification'] == 'INCOMPLETE_PAIRS'
    assert assessment['candidate_violation_episode_ids'] == [trial.episode_id]
    await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('stage', ['source_validation', 'challenge'])
async def test_full_loop_never_promotes_after_failure_in_replaced_pair(tmp_path, monkeypatch, stage):
    from app.lab.learning import run_learning_cycle
    from test_learning_qualification import candidate as fixture_candidate, loop

    c, campaign, runner, contexts, _ = loop(tmp_path, monkeypatch, [fixture_candidate(), None])
    original = runner.run
    attempts = []

    async def run(*args, **kwargs):
        trial = await original(*args, **kwargs)
        if kwargs.get('purpose') == stage:
            if not attempts:
                trial.lifecycle = 'LAB_ERROR'; trial.outcome = 'LAB_ERROR'; trial.failed_checks = []
            elif len(attempts) == 1:
                trial.outcome = 'VIOLATION'; trial.failed_checks = ['C3']
            attempts.append(trial)
            c.store.put_record('trials', trial.episode_id, trial)
        return trial

    runner.run = run
    await run_learning_cycle(c, campaign, runner)
    assert c.get(campaign.campaign_id).state == 'NO_CHANGE'
    assert c.get(campaign.campaign_id).active_policy_version == 'policy-v0'
    assert c.policies.list()[1].decision == 'REJECTED'
    assert not c.store.list_records('promotion_decisions')
    if stage == 'source_validation':
        feedback = contexts[1]['source_validation_feedback'][0]
        assert feedback['candidate_violation_episode_ids'] == [attempts[1].episode_id]
    else:
        feedback = contexts[1]['challenge_counterexamples'][0]
        assert feedback['status'] == 'COUNTEREXAMPLE_FOUND'
        assert any(attempts[1].episode_id in row['episode_ids'] and row['failed_checks'] == ['C3']
                   for row in feedback['trial_outcomes'])
    await c.close()
