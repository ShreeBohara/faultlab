"""New-run admissibility guard; historical no-harm predicates stay unchanged."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.lab.coordinator import LabCoordinator
from app.lab.heldout_check import (
    PREDICATE, WORLD_INTEGRITY_PROTOCOL, _execute, heldout_integrity_findings,
    queue_heldout_check, stored_candidate_failures, world_integrity_assessment,
)
from test_evaluation import setup
from test_heldout_check import CASES, C, S, batch, trial


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def fixture(tmp_path, *, arm='L', marker=True, other_harm=None):
    c, campaign, ledger, candidate, _ = setup(tmp_path)
    invalid = trial('invalid-clock', arm, 'LAB_ERROR', checks=['C5', 'C6', 'C8'], lifecycle='LAB_ERROR')
    extras = [invalid]
    if other_harm:
        extras.append(trial('actual-world-harm', 'L', 'LAB_ERROR', checks=['C3'], lifecycle=other_harm))
    evaluated = batch([[C] * 3, [S] * 3], [[C] * 3, [S] * 3], extra=extras)
    evaluated.batch_id = 'batch-world-integrity'
    baseline = c.policies.baseline()
    record = {'check_id': 'check-world-integrity', 'campaign_id': campaign.campaign_id,
              'policy_hash': candidate.policy_hash, 'incumbent_hash': baseline.policy_hash,
              'predicate': PREDICATE, 'status': 'RUNNING', 'decision': 'PENDING', 'assessment': None}
    if marker:
        record['world_integrity_protocol'] = WORLD_INTEGRITY_PROTOCOL
    for t in evaluated.trials:
        t.policy_hash = candidate.policy_hash if t.arm == 'L' else baseline.policy_hash
        t.world_id = 'world-' + t.episode_id
        c.store.put_record('episodes', t.episode_id, {
            'episode_id': t.episode_id, 'campaign_id': campaign.campaign_id, 'world_id': t.world_id,
            'arm': t.arm, 'policy_hash': t.policy_hash, 'experiment_purpose': 'promotion',
            'lifecycle': t.lifecycle, 'report': None if t.episode_id == 'actual-world-harm' else {'overall': 'COMPLETED'},
        })
        c.store.put_record('trials', t.episode_id, {
            'episode_id': t.episode_id, 'lifecycle': t.lifecycle, 'outcome': t.outcome,
            'failed_checks': t.failed_checks,
        }, immutable=True)
    integrity = {'schema_version': WORLD_INTEGRITY_PROTOCOL, 'status': 'INVALID',
                 'issues': ['DECISION_TICK_MISMATCH', 'HTTP_ADMISSION_COUNT_MISMATCH',
                            'HTTP_ADMISSION_IDENTITY_MISMATCH'],
                 'lab_ticks': 4, 'decision_tick': 3, 'horizon_tick': 8,
                 'charged_http_attempts': 4, 'admitted_http_attempts': 3}
    c.store.put_record('private_world_integrity', invalid.episode_id, integrity, immutable=True)
    c.store.put_record('heldout_checks', record['check_id'], record)
    return c, campaign, ledger, baseline, candidate, record, evaluated


@pytest.mark.parametrize('marker', [False, True])
def test_only_explicit_new_plan_uses_trusted_verifier_findings(tmp_path, marker):
    c, _, _, _, candidate, record, _ = fixture(tmp_path, marker=marker)
    try:
        findings = heldout_integrity_findings(c.store, record)
        assert bool(findings) is marker
        excluded = {f['episode_id'] for f in findings}
        failures = stored_candidate_failures(c.store, record['campaign_id'], candidate.policy_hash,
                                             excluded_episode_ids=excluded)
        assert failures == ([] if marker else ['invalid-clock'])
        # The old default still applies the exact old harmful predicate.
        assert stored_candidate_failures(c.store, record['campaign_id'], candidate.policy_hash) == ['invalid-clock']
        changed = {**record, 'world_integrity_protocol': 'unknown-future-version'}
        assert heldout_integrity_findings(c.store, changed) == []
    finally:
        c.store.close()


def test_findings_require_this_campaign_arm_policy_and_known_verifier(tmp_path):
    c, _, _, _, _, record, _ = fixture(tmp_path)
    try:
        assert heldout_integrity_findings(c.store, record)[0]['episode_id'] == 'invalid-clock'
        for changed in ({'campaign_id': 'another'}, {'policy_hash': 'wrong'}):
            assert heldout_integrity_findings(c.store, {**record, **changed}) == []
        episode = c.store.get_record('episodes', 'invalid-clock')
        c.store.put_record('episodes', 'invalid-clock', {**episode, 'experiment_purpose': 'completion_study'})
        assert heldout_integrity_findings(c.store, record) == []
    finally:
        c.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('arm,marker,expected', [('L', True, 'INCOMPLETE'), ('B0', True, 'INCOMPLETE'),
                                              ('L', False, 'HARM'), ('B0', False, 'NO_HARM')])
async def test_finalization_keeps_broken_clock_out_of_new_causal_decision(tmp_path, monkeypatch, arm, marker, expected):
    c, campaign, ledger, baseline, candidate, record, evaluated = fixture(tmp_path, arm=arm, marker=marker)
    before = deepcopy([c.store.get_record('trials', t.episode_id) for t in evaluated.trials])

    async def get_runner(live):
        return SimpleNamespace(), False

    async def evaluate(*args, **kwargs):
        return evaluated

    monkeypatch.setattr(c, '_get_runner', get_runner)
    monkeypatch.setattr('app.lab.heldout_check.PairedEvaluator.run', evaluate)
    c.active_id = campaign.campaign_id
    try:
        await _execute(c, campaign, baseline, candidate, CASES, record, ledger)
        saved = c.store.get_record('heldout_checks', record['check_id'])
        assert saved['decision'] == expected
        assert saved['status'] == ('INCOMPLETE' if expected == 'INCOMPLETE' else 'COMPLETED')
        assert c.active_id is None
        assert before == [c.store.get_record('trials', t.episode_id) for t in evaluated.trials]
        if marker:
            assert saved['assessment']['rule'] == 'world_integrity'
            assert saved['assessment']['candidate_failures'] == []
            assert saved['world_integrity_findings'][0]['arm'] == arm
            assert saved['diagnostic_legacy_assessment']['decision'] == ('HARM' if arm == 'L' else 'NO_HARM')
        else:
            assert 'world_integrity_findings' not in saved and 'diagnostic_legacy_assessment' not in saved
    finally:
        await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('lifecycle', ['LAB_ERROR', 'INTERRUPTED'])
async def test_true_world_harm_on_another_trial_still_counts(tmp_path, monkeypatch, lifecycle):
    c, campaign, ledger, baseline, candidate, record, evaluated = fixture(tmp_path, other_harm=lifecycle)

    async def get_runner(live):
        return SimpleNamespace(), False

    async def evaluate(*args, **kwargs):
        return evaluated

    monkeypatch.setattr(c, '_get_runner', get_runner)
    monkeypatch.setattr('app.lab.heldout_check.PairedEvaluator.run', evaluate)
    try:
        await _execute(c, campaign, baseline, candidate, CASES, record, ledger)
        saved = c.store.get_record('heldout_checks', record['check_id'])
        assert saved['decision'] == 'HARM' and saved['status'] == 'COMPLETED'
        assert saved['candidate_failures'] == ['actual-world-harm']
        assert saved['assessment']['candidate_failures'] == ['actual-world-harm']
        assert saved['world_integrity_findings'][0]['episode_id'] == 'invalid-clock'
    finally:
        await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('broken_reader', ['heldout_integrity_findings', 'stored_candidate_failures'])
@pytest.mark.parametrize('arm', ['B0', 'L'])
async def test_new_plan_fails_closed_if_integrity_or_failure_scan_cannot_finish(tmp_path, monkeypatch, broken_reader, arm):
    c, campaign, ledger, baseline, candidate, record, evaluated = fixture(tmp_path, arm=arm)

    async def get_runner(live):
        return SimpleNamespace(), False

    async def evaluate(*args, **kwargs):
        return evaluated

    def broken(*args, **kwargs):
        raise OSError('offline read failure')

    monkeypatch.setattr(c, '_get_runner', get_runner)
    monkeypatch.setattr('app.lab.heldout_check.PairedEvaluator.run', evaluate)
    monkeypatch.setattr('app.lab.heldout_check.' + broken_reader, broken)
    try:
        await _execute(c, campaign, baseline, candidate, CASES, record, ledger)
        saved = c.store.get_record('heldout_checks', record['check_id'])
        assert saved['decision'] == saved['status'] == 'INCOMPLETE'
        assert saved['recovery_error'] == 'OSError'
        assert saved['assessment']['rule'] == 'world_integrity_unavailable'
        assert saved['diagnostic_legacy_assessment']['decision'] == ('HARM' if arm == 'L' else 'NO_HARM')
    finally:
        await c.close()


@pytest.mark.parametrize('marker,other_harm,expected', [(True, None, 'INCOMPLETE'),
    (False, None, 'HARM'), (True, 'INTERRUPTED', 'HARM')])
def test_restart_uses_same_guard_without_replaying_or_weakening_world_harm(tmp_path, marker, other_harm, expected):
    c, _, _, _, _, record, _ = fixture(tmp_path, marker=marker, other_harm=other_harm)
    settings = c.settings
    c.store.close()
    restarted = LabCoordinator(settings)
    try:
        saved = restarted.store.get_record('heldout_checks', record['check_id'])
        assert saved['decision'] == expected
        assert saved['status'] == ('INTERRUPTED' if expected == 'INCOMPLETE' else 'COMPLETED')
        assert not restarted.tasks and restarted.active_id is None
        if marker:
            assert saved['world_integrity_findings'][0]['episode_id'] == 'invalid-clock'
            assert saved['candidate_failures'] == ([] if expected == 'INCOMPLETE' else ['actual-world-harm'])
    finally:
        restarted.store.close()


@pytest.mark.parametrize('previous_decision', ['HARM', 'NO_HARM'])
def test_restart_scan_failure_keeps_previous_conclusion_diagnostic_only(tmp_path, monkeypatch, previous_decision):
    c, _, _, _, _, record, _ = fixture(tmp_path)
    prior = {'decision': previous_decision, 'rule': 'saved-diagnostic'}
    record['assessment'] = prior
    c.store.put_record('heldout_checks', record['check_id'], record)
    settings = c.settings
    c.store.close()

    def broken(*args, **kwargs):
        raise OSError('offline integrity read failure')

    monkeypatch.setattr('app.lab.heldout_check.heldout_integrity_findings', broken)
    restarted = LabCoordinator(settings)
    try:
        saved = restarted.store.get_record('heldout_checks', record['check_id'])
        assert saved['decision'] == saved['assessment']['decision'] == 'INCOMPLETE'
        assert saved['status'] == 'INTERRUPTED'
        assert saved['assessment']['rule'] == 'world_integrity_unavailable'
        assert saved['diagnostic_legacy_assessment'] == prior
        assert saved['recovery_error'] == 'OSError'
        assert not restarted.tasks
    finally:
        restarted.store.close()


def test_guard_does_not_mutate_legacy_assessment_or_its_finding_input():
    legacy = {'decision': 'HARM', 'candidate_failures': ['invalid'], 'by_case': {'healthy': {}}}
    findings = [{'episode_id': 'invalid', 'issues': ['DECISION_TICK_MISMATCH']}]
    before = deepcopy((legacy, findings))
    assert world_integrity_assessment(legacy, findings, [])['decision'] == 'INCOMPLETE'
    assert (legacy, findings) == before


@pytest.mark.anyio
async def test_new_plan_freezes_guard_protocol_before_execution(tmp_path, monkeypatch):
    from test_heldout_check import SYNTHETIC_PROMOTION, certified_study, fresh_campaign
    import app.lab.heldout_check as module

    monkeypatch.setattr(module, 'load_cases', lambda name: deepcopy(SYNTHETIC_PROMOTION))
    c, study, client = await certified_study(tmp_path)
    try:
        campaign = fresh_campaign(c)
        queued = await queue_heldout_check(c, campaign.campaign_id, study['study_id'])
        assert queued['world_integrity_protocol'] == WORLD_INTEGRITY_PROTOCOL
        frozen = c.store.get_record('heldout_plans', queued['check_id'])
        assert frozen['world_integrity_protocol'] == WORLD_INTEGRITY_PROTOCOL
        assert frozen['status'] == 'QUEUED'
        await c.tasks[queued['check_id']]
        assert c.store.get_record('heldout_plans', queued['check_id']) == frozen
    finally:
        await client.aclose()
        await c.close()
