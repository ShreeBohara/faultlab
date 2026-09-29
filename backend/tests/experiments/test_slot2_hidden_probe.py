"""Offline checks of the Phase 29 slot-2 hidden-prior probe. No provider call, no .env read, no store write."""
import asyncio
from collections import Counter
import dataclasses
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
import pathlib
import random
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('slot2_hidden_probe', ROOT / 'scripts/experiments/slot2_hidden_probe.py')
probe = importlib.util.module_from_spec(SPEC)
sys.modules['slot2_hidden_probe'] = probe
SPEC.loader.exec_module(probe)
s2 = probe.s2

from app.contracts.models import content_hash  # noqa: E402
from app.providers.runtime import RuntimeProvider, RuntimeProviderError  # noqa: E402

STORE = ROOT / 'artifacts/lab.sqlite3'

# The Phase 17 settings file lives under the git-ignored artifacts/ folder, so a fresh clone does not have it.
# Tests that read it skip there with this reason (as test_run_dev_probe.py and test_run_gap_probe.py already
# do); where the file exists they run unchanged.
PHASE17_SETTINGS_ABSENT = not (ROOT / probe.DECLARED_SETTINGS).is_file()
NO_PHASE17_SETTINGS = ('needs the Phase 17 settings file (artifacts/phase16-2026-09-22/settings-phase17.json; '
                       'git-ignored, so a fresh clone does not have it)')
needs_phase17_settings = pytest.mark.skipif(PHASE17_SETTINGS_ABSENT, reason=NO_PHASE17_SETTINGS)


@pytest.fixture(autouse=True)
def no_real_process_list(monkeypatch):
    """No test reads the machine's real process list; the process guard is tested with injected rows."""
    monkeypatch.setattr(probe, 'process_list', lambda: [])


def _policy(rules, explanation='A bounded recovery policy.'):
    return json.dumps({'candidate': {'scope': 'orders.upgrade_then_confirm/v1', 'parent_version': 'policy-v0',
                                     'rules': rules}, 'explanation': explanation})


STEP_RULE = {'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
             'steps': [{'op': 'retry_original_request', 'service': 'notifications'}]}
READ_RULE = {'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
             'steps': [{'op': 'read_notification_operation'},
                       {'op': 'require_receipt', 'service': 'notifications', 'status': 'SUCCEEDED'}]}
DEFER_RULE = {'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain',
              'steps': [{'op': 'defer_unresolved'}]}
STEP = _policy([STEP_RULE])
NO_STEP = _policy([READ_RULE])
STEP_AND_DEFER = _policy([STEP_RULE, DEFER_RULE])
NO_CHANGE = json.dumps({'no_change_reason': 'nothing supported'})


def _hash(raw):
    return content_hash(s2.parse_policy(raw).candidate)


REFERENCE = {'slot1_policy_hash': _hash(NO_STEP), 'slot1_raw_sha256': s2.sha256_text(NO_STEP),
             'slot1_rules_text_sha256': s2.sha256_text(s2.rules_text(NO_STEP)),
             'slot1_step_fires': False, 'slot1_harmful': False,
             'historical_raw_sha256': s2.sha256_text(NO_STEP), 'historical_policy_hash': _hash(NO_STEP),
             'historical_class': 'CANDIDATE', 'historical_duplicate_of_slot1': True, 'historical_attempts': 1}
HIDDEN_REFERENCE = {**REFERENCE, 'phase25_n_raw_sha256': s2.sha256_text(STEP), 'phase25_n_policy_hash': _hash(STEP)}
# The plan's already-proposed record (review round 2) for the fake draws: the fake slot-1 policy was proposed; STEP is
# novel unless a test says otherwise.
KNOWN = {'policy_hashes': sorted({_hash(NO_STEP), 'f' * 64}), 'certified_policy_hashes': []}


def _distinct(i):
    return _policy([READ_RULE, {'hook': 'before_final_report', 'when': 'always',
                                'steps': [{'op': 'wait_ticks', 'ticks': 1 + i % 4}]}])


def _rows(arm, pattern, prompts=26, repeats=3, missing=0, missing_if=None, reference=None):
    """Draw rows for one arm; pattern(prompt, repeat) returns a raw output. The first `missing` rows, and any row
    where missing_if(prompt, repeat) holds, are missing."""
    rows = []
    for p in range(prompts):
        for r in range(repeats):
            ref = reference(p) if reference else (REFERENCE if arm == 'C' else HIDDEN_REFERENCE)
            request = {'request_id': f'{arm}{p}-{r}', 'prompt_id': f'p{p}', 'arm': arm, 'repeat': r,
                       'population': 'slot2', 'reference': ref}
            received = len(rows) >= missing and not (missing_if and missing_if(p, r))
            raw = pattern(p, r)
            rows.append({'request': request, 'received': received,
                         'result': {'status': 'ok', 'raw': raw} if received else None,
                         'c': s2.classify_response(raw, ref) if received else None})
    return rows


def _saved(*row_sets):
    requests, results = [], []
    for rows in row_sets:
        for row in rows:
            requests.append(row['request'])
            if row['received']:
                results.append({'request_id': row['request']['request_id'], 'status': 'ok', 'raw': row['result']['raw'],
                                'attempts': [{'attempt': 1}]})
    return requests, results


CONTROL = lambda p, r: NO_STEP if p % 4 else _distinct(p)  # noqa: E731
GOOD = lambda p, r: STEP if p % 3 == 0 else _distinct(p + r)  # noqa: E731
GAIN = f'working_share_gain_at_least_{probe._label(probe.WORKING_SHARE_GAIN_MIN)}'
WORKING_SIGN = 'working_sign_test_p_below_0.025'


# ---------------------------------------------------------------- pins and declared constants

def test_the_phase25_harness_is_imported_pinned_and_a_changed_one_refuses(monkeypatch):
    assert probe.phase25_harness_problem() is None
    assert probe.PHASE25_HARNESS_SHA256 == probe.sha256_file(probe.PHASE25_HARNESS)
    monkeypatch.setattr(probe, 'PHASE25_HARNESS_SHA256', '0' * 64)
    assert 'not the pinned Phase 25 harness' in probe.phase25_harness_problem()
    with pytest.raises(probe.PlanningError, match='not the pinned Phase 25 harness'):
        probe.build_plan()
    with pytest.raises(probe.PlanningError, match='not the pinned Phase 25 harness'):
        probe.run_live(SimpleNamespace(out='artifacts/phase29-x/live'), {}, {})


def test_the_code_that_ran_is_the_pinned_code_and_a_changed_file_refuses_at_import(tmp_path, monkeypatch):
    """Review round 1: the Phase 25 bytes are hashed BEFORE any of them run, and exactly those bytes are executed.
    A copy of this harness beside a changed slot2_probe.py refuses at import, and the changed code never runs."""
    assert hashlib.sha256(probe._PHASE25_SOURCE).hexdigest() == probe.PHASE25_HARNESS_SHA256
    assert s2.__file__ == str(probe.PHASE25_HARNESS) and s2.ROOT == ROOT
    assert s2.__name__ == 'faultlab_phase29_slot2_probe' and s2.__name__ not in sys.modules
    monkeypatch.setattr(sys, 'path', list(sys.path))
    experiments = tmp_path / 'scripts/experiments'
    experiments.mkdir(parents=True)
    (experiments / 'slot2_hidden_probe.py').write_bytes((ROOT / 'scripts/experiments/slot2_hidden_probe.py').read_bytes())
    original = probe.PHASE25_HARNESS.read_bytes()

    def load(name):
        spec = importlib.util.spec_from_file_location(name, experiments / 'slot2_hidden_probe.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    (experiments / 'slot2_probe.py').write_bytes(original)
    copy = load('slot2_hidden_probe_copy_unchanged')
    assert copy.s2.__file__ == str(experiments / 'slot2_probe.py') and copy.phase25_harness_problem() is None
    sentinel = tmp_path / 'the-changed-file-ran'
    (experiments / 'slot2_probe.py').write_bytes(
        f'import pathlib\npathlib.Path({str(sentinel)!r}).write_text("ran")\n'.encode() + original)
    with pytest.raises(ImportError, match='not the pinned Phase 25 harness'):
        load('slot2_hidden_probe_copy_changed')
    assert not sentinel.exists()
    # A file edited after import is caught before any plan or send.
    (experiments / 'slot2_probe.py').write_bytes(original + b'\n# edited later\n')
    assert 'not the pinned Phase 25 harness' in copy.phase25_harness_problem()


def test_the_declared_design_constants():
    """Written out, not read from the harness: the protocol quotes these numbers."""
    assert probe.ARMS == ('C', 'N', 'NT') and probe.TREATED_ARMS == ('N', 'NT') and probe.REPEATS == 3
    assert probe.ARM_TEMPERATURE == {'C': 0, 'N': 0, 'NT': 0.4}
    assert probe.HARD_SPEND_CAP == 15.0 and probe.PER_REQUEST_DOLLAR_BOUND == s2.PER_REQUEST_DOLLAR_BOUND == 0.04984
    assert probe.DECLARED_CONFIGURATION_HASH == '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba'
    assert probe.WORKING_SHARE_GAIN_MIN == 3 and probe.WORKING_SHARE_GAIN_MIN_ROUND1 == 1
    assert (probe.POSITIVE_ALPHA, probe.GUARD_ALPHA, probe.FALSE_ALARM_TARGET) == (0.025, 0.05, 0.025)
    assert (probe.DISTINCT_MIN, probe.DISTINCT_GAIN_MIN, probe.INVALID_MARGIN, probe.HARMFUL_FIRING_SHARE_MAX) == (
        Fraction(7, 10), Fraction(3, 10), Fraction(1, 10), Fraction(1, 2))
    assert probe.COMPLETE_MIN == Fraction(95, 100)


# ---------------------------------------------------------------- the real store (read-only)

def _tree_is_the_declared_configuration():
    try:
        settings = probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)
        return probe.configuration_pins(settings)['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    except Exception:
        return False


needs_store = pytest.mark.skipif(not STORE.exists() or not _tree_is_the_declared_configuration(),
                                 reason='needs the local lab store and the tree Phase 29 is pinned to')


@pytest.fixture(scope='module')
def real_plan():
    if not STORE.exists() or not _tree_is_the_declared_configuration():
        pytest.skip('needs the local lab store and the tree Phase 29 is pinned to')
    return probe.build_plan()


@pytest.fixture(scope='module')
def dry_settings():
    if PHASE17_SETTINGS_ABSENT:
        pytest.skip(NO_PHASE17_SETTINGS)
    return probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)


@needs_store
def test_the_plan_is_phase25s_census_with_three_arms_and_every_slot_verifies(real_plan):
    plan, prompts = real_plan
    assert plan['populations']['by_phase'] == {'phase17': 5, 'phase23': 21}
    assert plan['populations']['verification_failures'] == [] and plan['populations']['slot2_prompts'] == 26
    assert plan['verification']['slots_checked'] == plan['verification']['slots_verified'] == 52
    assert len(plan['verification']['rule']) == 12 and plan['populations']['excluded_in_scope'] == {'no_slot2_proposal': 13}
    assert len(plan['populations']['prompts_whose_slot1_policy_fires']) == 2
    assert plan['counts'] == {'by_population_and_arm': {'slot2/C': 78, 'slot2/N': 78, 'slot2/NT': 78},
                              'total_requests': 234, 'distinct_prompts': 52} and len(prompts) == 52
    assert plan['cost']['planned_upper_bound'] == pytest.approx(11.66256)
    assert plan['cost']['max_attempts_under_cap'] == 300 and plan['cost']['retry_headroom_attempts'] == 66
    assert plan['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    assert plan['phase25_harness_sha256'] == probe.PHASE25_HARNESS_SHA256
    assert plan['precheck'] == {'slot2_prompts': 26, **{key: 26 for key in (
        'N_differs_from_C_only_by_an_empty_candidate_history', 'N_user_message_holds_no_prior_candidate',
        'NT_differs_from_N_only_in_temperature', 'C_request_is_phase25_C_request',
        'N_request_is_phase25_N_request')}, 'passed': True}
    assert plan['thresholds']['working_share_gain_min'] == '3' and plan['thresholds']['nt_temperature'] == 0.4
    assert plan['investigation']['auditor_validation']['agreement'] == 40
    # Review round 1: one source case for all 26 prompts; every slot 1 ran there and none source-qualified.
    facts = plan['populations']['census_facts']
    assert list(facts['source_fault_spec_content_hashes'].values()) == [26]
    assert facts['slot1_decisions'] == {'INCOMPLETE': 3, 'NO_CHANGE': 23}
    assert (facts['slot1_ran_on_the_source_case'], facts['slot1_source_qualified'], facts['slot1_policies']) == (26, 0, 22)
    assert len(probe.census_slot1_policies(plan['requests'])) == 22
    # Review round 2: every policy the 39 in-scope v4 studies proposed, in either slot, on the same source case; the
    # four certified policies among them, read from the pinned run manifests.
    proposed = plan['populations']['already_proposed']
    assert (proposed['studies'], proposed['studies_with_a_proposal'], len(proposed['policy_hashes'])) == (39, 33, 35)
    assert proposed['proposals_with_a_policy_by_slot'] == {'slot1': 33, 'slot2': 26}
    assert proposed['source_fault_spec_content_hashes_of_the_studies_with_a_proposal'] == {
        next(iter(facts['source_fault_spec_content_hashes'])): 33}
    assert proposed['certified_policy_hashes'] == sorted(probe.CERTIFIED_POLICY_HASHES)
    assert set(proposed['certified_policy_hashes']) <= set(proposed['policy_hashes'])
    assert probe.census_slot1_policies(plan['requests']) <= set(proposed['policy_hashes'])


@needs_store
def test_the_arms_are_exactly_the_declared_change_and_phase25s_own_requests(real_plan):
    plan, prompts = real_plan
    phase25 = json.loads((ROOT / probe.PHASE25_LIVE_PLAN).read_text())
    earlier = {(r['prompt_id'], r['arm']): r for r in phase25['requests'] if r['repeat'] == 0}
    by_prompt = {}
    for request in plan['requests']:
        by_prompt.setdefault(request['prompt_id'], {}).setdefault(request['arm'], set()).add(
            (request['messages_hash'], request['request_hash'], request['temperature']))
    assert len(by_prompt) == 26
    for prompt_id, arms in by_prompt.items():
        assert all(len(v) == 1 for v in arms.values()), 'every repeat of an arm is the same request'
        (c_messages, c_request, c_temp), = arms['C']
        (n_messages, n_request, n_temp), = arms['N']
        (t_messages, t_request, t_temp), = arms['NT']
        assert (c_temp, n_temp, t_temp) == (0, 0, 0.4)
        assert n_messages == t_messages != c_messages and len({c_request, n_request, t_request}) == 3
        assert (c_messages, c_request) == (earlier[(prompt_id, 'C')]['messages_hash'], earlier[(prompt_id, 'C')]['request_hash'])
        assert (n_messages, n_request) == (earlier[(prompt_id, 'N')]['messages_hash'], earlier[(prompt_id, 'N')]['request_hash'])
        body = s2.request_body(prompts[n_messages]['messages'], 0.4)
        assert s2.request_digest(body) == t_request
        assert json.loads(prompts[n_messages]['messages'][1]['content'])['candidate_history'] == []
        assert prompts[n_messages]['arm_context'] == 'prior_candidate_hidden' and prompts[c_messages]['arm_context'] == 'stored'


@needs_store
def test_every_hidden_prompt_is_what_the_real_mechanic_sends(real_plan):
    """The hidden-arm prompt equals the messages the real Mechanic.propose_completion sends for the slot-2 context
    with an empty candidate_history (captured with a fake provider), for all 26 prompts."""
    from app.agents.mechanic import Mechanic
    plan, prompts = real_plan
    hidden = {r['prompt_id']: r['messages_hash'] for r in plan['requests'] if r['arm'] == 'N'}
    seen = []

    class Provider:
        def role_model(self, role):
            return probe.EXPECTED_MECHANIC_MODEL

        async def complete(self, messages, **kwargs):
            seen.append(messages)
            return SimpleNamespace(content=NO_STEP, model_id=probe.EXPECTED_MECHANIC_MODEL, input_tokens=1,
                                   output_tokens=1, cost_usd=None)
    connection = s2.connect(STORE)
    try:
        for study_id in plan['populations']['studies']:
            context, _ = s2.load_record(connection, 'completion_proposal_inputs', f'{study_id}-2')
            seen.clear()
            ledger = SimpleNamespace(consume_call=lambda **_: None, reconcile=lambda _: None)
            store = SimpleNamespace(put_record=lambda *_, **__: None)
            asyncio.run(Mechanic(Provider(), store, ledger).propose_completion({**context, 'candidate_history': []}))
            assert seen[0] == prompts[hidden[f'{study_id}:slot2']]['messages']
    finally:
        connection.close()


@needs_store
def test_the_request_order_is_three_rounds_of_every_arm_back_to_back(real_plan):
    plan, _ = real_plan
    requests = plan['requests']
    assert [r['request_id'] for r in requests] == [f'r{i:04d}' for i in range(1, 235)]
    for round_index in range(3):
        block = requests[78 * round_index: 78 * (round_index + 1)]
        assert {r['repeat'] for r in block} == {round_index}
        triples = [block[i: i + 3] for i in range(0, 78, 3)]
        assert all(len({r['prompt_id'] for r in t}) == 1 and {r['arm'] for r in t} == set(probe.ARMS) for t in triples)
        assert len({t[0]['prompt_id'] for t in triples}) == 26
    firsts = [[r['prompt_id'] for r in requests[78 * i: 78 * (i + 1): 3]] for i in range(3)]
    assert firsts[0] != firsts[1] != firsts[2], 'each round is ranked afresh'


@needs_store
def test_the_dry_plan_never_reads_env_and_refuses_an_altered_settings_file(tmp_path, monkeypatch, real_plan):
    real = probe.settings_from_file
    seen = []

    def spy(path, *, env_path):
        seen.append(env_path)
        return real(path, env_path=env_path)
    monkeypatch.setattr(probe, 'settings_from_file', spy)
    plan, _ = probe.build_plan()
    assert seen == [os.devnull] and probe.plan_hash(plan) == probe.plan_hash(real_plan[0])
    altered = tmp_path / 'settings.json'
    altered.write_text((ROOT / probe.DECLARED_SETTINGS).read_text().replace('0.55', '0.56'))
    with pytest.raises(probe.PlanningError, match='not the declared Phase 17 settings'):
        probe.build_plan(settings_path=altered)


@needs_phase17_settings
def test_build_plan_runs_the_pin_check(monkeypatch):
    def refuse(*_, **__):
        raise probe.PlanningError('pins sentinel')
    monkeypatch.setattr(probe, 'check_pins', refuse)
    with pytest.raises(probe.PlanningError, match='pins sentinel'):
        probe.build_plan()


def test_the_phase25_reference_is_pinned(tmp_path):
    for relative in (probe.PHASE25_LIVE_PLAN, probe.PHASE25_LIVE_RESPONSES):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text('{}\n')
    with pytest.raises(probe.PlanningError, match='not the pinned Phase 25 file'):
        probe.phase25_reference(tmp_path)


@pytest.mark.skipif(not (ROOT / probe.PHASE25_LIVE_PLAN).exists(), reason='needs the Phase 25 run')
def test_the_phase25_reference_holds_one_c_and_one_n_request_per_prompt():
    reference = probe.phase25_reference()
    assert len(reference) == 26 and all(set(entry) == {'C', 'N'} for entry in reference.values())
    assert all(entry['N']['raw_sha256'] for entry in reference.values())
    # 25 of Phase 25's 26 N draws were candidates; the other was an invalid output (PHASE25_RESULTS.md).
    assert sum(entry['N']['policy_hash'] is not None for entry in reference.values()) == 25


@needs_store
def test_the_phase25_planning_inputs_reproduce_the_figures_the_protocol_quotes(real_plan):
    """Review rounds 1 and 2: Phase 25's N wrote 25 distinct draws in only 14 policies, one of them on 7 prompts.
    Round 1 counted 14 of the 25 as a census slot-1 policy and 11 as novel, 1 of them WORKING. Round 2 counts against
    every policy an in-scope v4 study proposed (35): 15 already proposed (14 a census slot 1, 1 the certified
    5735a918...), 10 novel in 8 policies, 0 of them WORKING; N's only WORKING draw re-draws a certified policy. C: 10
    of 20 novel (round 1: 19); T 46 of 49; H 14 of 14. The same temperature-0 request returned the same policy in 57
    of 78 (C against history) to 64 of 78 (H repeats)."""
    inputs = probe.phase25_planning_inputs(already_proposed=real_plan[0]['populations']['already_proposed'])
    assert inputs['census_slot1_policies'] == 22 and 'never evidence' in inputs['label']
    assert (inputs['already_proposed_policies'], inputs['certified_policies']) == (35, 4)
    n = inputs['concentration_by_arm']['N']
    assert (n['received'], n['distinct_draws'], n['distinct_policies'], n['largest_policy_prompts']) == (26, 25, 14, 7)
    assert n['census_slot1_policy_redraws_round1_set']['distinct_draws'] == 14
    prior_n = n['already_proposed_in_an_in_scope_v4_study']
    assert (prior_n['distinct_draws'], prior_n['distinct_policies'], prior_n['working_draws']) == (15, 6, 1)
    assert (n['novel']['distinct_draws'], n['novel']['distinct_policies'], n['novel']['working_draws']) == (10, 8, 0)
    certified = n['certified_policy_redraws']
    assert (certified['distinct_draws'], certified['working_draws']) == (1, 1)
    novel = {arm: inputs['concentration_by_arm'][arm]['novel']['distinct_draws'] for arm in ('C', 'T', 'H')}
    distinct = {arm: inputs['concentration_by_arm'][arm]['distinct_draws'] for arm in ('C', 'T', 'H')}
    assert novel == {'C': 10, 'T': 46, 'H': 14} and distinct == {'C': 20, 'T': 49, 'H': 14}
    assert inputs['predicted_share_of_hidden_draws_re_drawing_phase25_N_policy'] == [round(57 / 78, 4), round(64 / 78, 4)]
    assert inputs['determinism_by_arm']['C']['same_policy_pairs'] == 59


def _precheck_row(context):
    return {'study': {'study_id': 's1'}, 'contexts': {2: context}, 'checks': {2: {'ok': True}}}


def test_the_precheck_compares_each_arm_with_the_control_and_with_phase25():
    context = {'campaign_id': 'c', 'study_id': 's1', 'candidate_history': [
        {'policy_hash': 'f' * 64, 'raw_outputs': [NO_STEP], 'content': json.loads(NO_STEP)['candidate']}],
        'development_evidence': [], 'observed_outcomes': []}
    control = s2.request_body(s2.mechanic_messages(context), 0)
    hidden = s2.request_body(s2.mechanic_messages({**context, 'candidate_history': []}), 0)
    phase25 = {'s1:slot2': {'C': {'messages_hash': content_hash(control['messages']),
                                  'request_hash': s2.request_digest(control)},
                            'N': {'messages_hash': content_hash(hidden['messages']),
                                  'request_hash': s2.request_digest(hidden)}}}
    assert probe.precheck([_precheck_row(context)], phase25)['passed'] is True
    # A Phase 25 request that is not this arm's request (another byte) fails the precheck.
    other = {'s1:slot2': {**phase25['s1:slot2'], 'N': {**phase25['s1:slot2']['N'], 'request_hash': '0' * 64}}}
    result = probe.precheck([_precheck_row(context)], other)
    assert result['passed'] is False and result['N_request_is_phase25_N_request'] == 0
    assert probe.precheck([_precheck_row(context)], {})['passed'] is False
    assert probe.precheck([], phase25)['passed'] is False


# ---------------------------------------------------------------- statistics and read-outs (pure)

def test_fisher_greater():
    assert probe.fisher_greater(3, 0, 0, 3) == pytest.approx(1 / 20)
    assert probe.fisher_greater(2, 1, 1, 2) == pytest.approx(10 / 20)
    assert probe.fisher_greater(0, 5, 0, 5) == 1.0 and probe.fisher_greater(0, 0, 3, 3) == 1.0
    assert probe.fisher_greater(15, 15, 0, 18) < 0.001
    with pytest.raises(ValueError):
        probe.fisher_greater(-1, 0, 0, 0)


def test_sim_draw_is_phase25s_simulated_draw_at_the_default_rates():
    for seed in range(20):
        mine, theirs = random.Random(seed), random.Random(seed)
        for p in range(4):
            for r in range(3):
                assert (probe.sim_draw(mine, p, r, distinct_p=0.6, firing_p=0.3)
                        == s2.simulated_draw(theirs, p, r, distinct_p=0.6, firing_p=0.3))


def test_a_recommendation_needs_every_condition():
    control = _rows('C', CONTROL)
    good = _rows('N', GOOD)
    result = probe.arm_decision(good, control, 'N')
    assert result['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP' and result['failed'] == []
    assert (result['duplicates_cut'], result['yield_gain']) == ('SHOWN', 'SHOWN')
    assert result['working']['gain'] == 9 and result['working']['sign_test']['favouring'] == 9
    assert result['harmful']['fisher_p_X_above_C'] is None and result['harmful']['fisher_note']
    no_step = probe.arm_decision(_rows('N', lambda p, r: _distinct(p + r)), control, 'N')
    assert no_step['failed'] == [GAIN, WORKING_SIGN] and no_step['decision'] == 'NOT_RECOMMENDED'
    assert (no_step['duplicates_cut'], no_step['yield_gain']) == ('SHOWN', 'NOT_SHOWN')
    duplicates = probe.arm_decision(_rows('N', CONTROL), control, 'N')
    assert duplicates['verdicts']['distinct'] == 'NOT_SHOWN' and duplicates['duplicates_cut'] == 'NOT_SHOWN'
    invalid = probe.arm_decision(_rows('N', lambda p, r: 'not json' if r == 0 else GOOD(p, r)), control, 'N')
    assert {'invalid_at_most_C_plus_0.10', 'invalid_not_shown_above_C_at_0.05', 'distinct_at_least_0.70'} <= set(
        invalid['failed']) and invalid['verdicts']['invalid'] == 'FAIL'
    harmful = probe.arm_decision(_rows('N', lambda p, r: STEP if p % 3 == 0 else STEP_AND_DEFER), control, 'N')
    assert harmful['failed'] == ['harmful_share_of_firing_at_most_0.50']
    assert (harmful['duplicates_cut'], harmful['yield_gain']) == ('SHOWN', 'NOT_SHOWN')


def test_the_harmful_guard_also_fails_on_a_fisher_contrast_against_c():
    """At most half of X's firing draws are harmful (the cap holds), but X's firing draws are harmful far more often
    than C's (15 of 30 against 0 of 18), so the exact contrast fails the guard."""
    control = _rows('C', lambda p, r: STEP if p >= 20 else NO_STEP)
    treated = _rows('N', lambda p, r: STEP if p < 5 else (STEP_AND_DEFER if p < 10 else _distinct(p + r)))
    result = probe.arm_decision(treated, control, 'N')
    assert result['conditions']['harmful_share_of_firing_at_most_0.50']
    assert not result['conditions']['harmful_not_shown_above_C_at_0.05'] and result['verdicts']['harmful'] == 'FAIL'
    assert result['harmful']['distinct_firing'] == {'X': 30, 'C': 18}
    assert result['harmful']['fisher_p_X_above_C'] < 0.001


def test_the_working_minimum_and_its_sign_test_boundaries():
    control = _rows('C', CONTROL)
    spread = lambda n: _rows('N', lambda p, r: STEP if r == 0 and p < n else _distinct(p + r))  # noqa: E731
    # One WORKING draw on each of 9 prompts is a gain of exactly 3 (sign test 9-0): shown; 8 (8/3) is not.
    assert probe.arm_decision(spread(9), control, 'N')['verdicts']['working'] == 'SHOWN'
    assert probe.arm_decision(spread(8), control, 'N')['failed'] == [GAIN]
    # Every repeat WORKING on n prompts: a gain of n, and the sign test needs 6 prompts at p < 0.025 (5-0 is 1/32).
    repeated = lambda n: _rows('N', lambda p, r: STEP if p < n else _distinct(p + r))  # noqa: E731
    assert probe.arm_decision(repeated(5), control, 'N')['failed'] == [WORKING_SIGN]
    assert probe.arm_decision(repeated(6), control, 'N')['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP'
    # The gain alone is not enough: 10 prompts for X against 7 for C is a gain of 3 and a sign test of 10-7.
    split = _rows('C', lambda p, r: STEP if 10 <= p < 17 else NO_STEP)
    result = probe.arm_decision(repeated(10), split, 'N')
    assert result['working']['gain'] == 3 and result['failed'] == [WORKING_SIGN]
    # The round-1 fallback's minimum (1) with one draw per prompt: 6-0 is shown, 5-0 is not.
    one = lambda n: probe.arm_decision(probe._round1(repeated(n)), probe._round1(control), 'N',  # noqa: E731
                                       working_gain_min=probe.WORKING_SHARE_GAIN_MIN_ROUND1)
    assert one(6)['verdicts']['working'] == 'SHOWN' and one(5)['failed'] == [WORKING_SIGN]
    assert one(6)['planned_draws'] == {'X': 26, 'C': 26}


def test_the_working_share_leaves_out_prompts_whose_slot1_policy_fires_and_flags_the_calibrated_range():
    fires = lambda p: {**HIDDEN_REFERENCE, 'slot1_step_fires': p < 9}  # noqa: E731
    control = _rows('C', lambda p, r: NO_STEP, reference=fires)
    treated = _rows('N', lambda p, r: STEP if p < 9 else _distinct(p + r), reference=fires)
    result = probe.arm_decision(treated, control, 'N')
    assert result['working']['share']['eligible_prompts'] == 17 and result['working']['gain'] == 0
    assert result['working']['calibrated_range_descriptive']['reading'] == 'within'
    firing_control = _rows('C', lambda p, r: STEP if p < 9 else NO_STEP)
    flag = probe.arm_decision(treated, firing_control, 'N')['working']
    assert flag['C_distinct_firing_rate_received'] == pytest.approx(27 / 78)
    assert flag['calibrated_range_descriptive']['reading'] == 'outside'
    # Review round 2: the old point-only flag is gone; the reading above is the only range flag.
    assert 'C_within_the_calibrated_firing_range_descriptive' not in flag


def test_the_invalid_guard_fails_on_a_shown_excess_below_the_margin():
    control = _rows('C', CONTROL)
    invalid_on = lambda n: _rows('N', lambda p, r: 'not json' if r == 0 and p < n else GOOD(p, r))  # noqa: E731
    six = probe.arm_decision(invalid_on(6), control, 'N')
    assert six['invalid']['excess'] == pytest.approx(6 / 78) and six['conditions']['invalid_at_most_C_plus_0.10']
    assert six['failed'] == ['invalid_not_shown_above_C_at_0.05'] and six['duplicates_cut'] == 'NOT_SHOWN'
    four = probe.arm_decision(invalid_on(4), control, 'N')
    assert four['verdicts']['invalid'] == 'PASS' and four['invalid']['sign_test_X_above_C']['favouring'] == 4
    # NO_CHANGE is not invalid: it lowers D_X but never fails the guard.
    no_change = probe.arm_decision(_rows('N', lambda p, r: NO_CHANGE if r == 0 and p < 6 else GOOD(p, r)), control, 'N')
    assert no_change['verdicts']['invalid'] == 'PASS' and no_change['distinct']['D_X'] == pytest.approx(72 / 78)


def test_missing_draws_count_against_the_treatment_and_make_an_arm_incomplete():
    control = _rows('C', CONTROL)
    treated = _rows('N', GOOD, missing=3)
    result = probe.arm_decision(treated, control, 'N')
    assert result['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP' and result['distinct']['D_X'] == pytest.approx(75 / 78)
    short = probe.arm_decision(_rows('N', GOOD, missing=4), control, 'N')
    assert short['decision'] == 'INCOMPLETE' and short['failed'][0] == 'complete'
    assert set(short['verdicts'].values()) == {'INCOMPLETE'} and short['duplicates_cut'] == 'INCOMPLETE'
    control_short = _rows('C', lambda p, r: NO_STEP, missing=3)
    assert probe.arm_decision(treated, control_short, 'N')['distinct']['D_C_worst_case'] == pytest.approx(3 / 78)


def _run_end(status='STOPPED', stop_reason='consecutive_errors', **changes):
    return s2.run_end_of({'status': status, 'stop_reason': stop_reason, 'traceback': None, 'stop_signal': None,
                          'resend_pass': None, **changes})


def _stopped_after_round_one():
    stopped = lambda p, r: r > 0  # noqa: E731
    return (_rows('C', CONTROL), _rows('N', GOOD, missing_if=stopped), _rows('NT', lambda p, r: NO_STEP, missing_if=stopped))


def test_compute_readouts_decisions_statement_and_descriptive_figures():
    control, hidden = _rows('C', CONTROL), _rows('N', GOOD)
    tempered = _rows('NT', lambda p, r: 'not json' if r == 0 else _distinct(p + r))
    readouts = probe.compute_readouts(*_saved(control, hidden, tempered), already_proposed=KNOWN,
                                      run_end=_run_end('COMPLETED', 'completed'))
    n, nt = readouts['decisions']['N'], readouts['decisions']['NT']
    assert n['declared'] == {'decision': 'RECOMMEND_FOR_A_LATER_LOOP', 'duplicates_cut': 'SHOWN', 'yield_gain': 'SHOWN',
                             'verdicts': n['verdicts'], 'basis': 'all_rounds', 'failed': []}
    assert nt['declared']['decision'] == 'NOT_RECOMMENDED' and nt['round1_fallback'] is None
    assert readouts['statement'].startswith("recommended for a later loop's own declaration: N. N RECOMMEND")
    assert 'NT NOT_RECOMMENDED (duplicates cut NOT_SHOWN, yield gain NOT_SHOWN' in readouts['statement']
    descriptive = readouts['descriptive']
    assert descriptive['duplicates_of_slot1']['C']['duplicate'] == 57 and descriptive['duplicates_of_slot1']['N']['duplicate'] == 0
    assert descriptive['duplicates_of_slot1']['C']['prompts_with_a_duplicate_draw'] == 19
    assert descriptive['duplicates_of_slot1']['N']['prompts_with_a_duplicate_draw'] == 0
    assert descriptive['duplicates_of_slot1']['NT']['prompts_with_a_received_draw'] == 26
    # 27 N draws are STEP, which is the policy the fake Phase 25 N draw wrote for every prompt.
    assert descriptive['phase25_dependence']['N']['same_policy_as_phase25_N_draw'] == 27
    assert descriptive['phase25_dependence']['N']['byte_identical_to_phase25_N_draw'] == 27
    assert descriptive['phase25_dependence']['NT']['same_policy_as_phase25_N_draw'] == 0
    assert 'sign_test_working_NT_above_N' in descriptive['N_against_NT_never_a_decision']
    assert set(readouts['determinism']) == {'C', 'N', 'NT'} and 'byte_identical_to_historical_output' in readouts['determinism']['C']
    assert 'byte_identical_to_historical_output' not in readouts['determinism']['N']
    # Review round 2: the statement splits DISTINCT into novel and already proposed (against the plan's set), and
    # reports re-draws of a certified policy on their own line. The decisions do not move with the set.
    assert ('N RECOMMEND_FOR_A_LATER_LOOP (duplicates cut SHOWN, yield gain SHOWN; failed: -; descriptive: 78 of 78 '
            'received draws differ from their own slot 1, 78 of them novel') in readouts['statement']
    assert 're-draws of a certified policy: 0 draws, 0 of them WORKING' in readouts['statement']
    certified = {'policy_hashes': sorted({*KNOWN['policy_hashes'], _hash(STEP)}), 'certified_policy_hashes': [_hash(STEP)]}
    again = probe.compute_readouts(*_saved(control, hidden, tempered), already_proposed=certified,
                                   run_end=_run_end('COMPLETED', 'completed'))
    assert again['decisions'] == readouts['decisions']
    assert ('51 of them novel (a policy no in-scope v4 study proposed) and 27 a policy an in-scope v4 study already '
            'proposed; WORKING draws 27 (novel 0), distinct WORKING policies 1; re-draws of a certified policy: 27 '
            'draws, 27 of them WORKING)') in again['statement']
    assert 'novel means none of the 3 policies the in-scope v4 studies proposed in either slot' in again['statement']
    rates = again['descriptive']['per_draw_rates_with_clustered_intervals']['N']
    assert (rates['working']['successes'], rates['working_novel']['successes'], rates['distinct_novel']['successes']) == (27, 0, 51)
    assert (again['descriptive']['already_proposed_policies'], again['descriptive']['certified_policies']) == (3, 1)


def test_the_dependence_figure_never_matches_a_missing_phase25_draw():
    reference = {**HIDDEN_REFERENCE, 'phase25_n_raw_sha256': None, 'phase25_n_policy_hash': None}
    rows = [{'request': {'reference': reference}, 'received': True, 'result': {'status': 'empty_response', 'raw': None},
             'c': s2.classify_response('', reference)}]
    assert probe.dependence_readout(rows)['byte_identical_to_phase25_N_draw'] == 0
    assert probe.dependence_readout(rows)['same_policy_as_phase25_N_draw'] == 0
    assert probe.dependence_readout(rows)['same_prompt_re_measurement'] is False
    assert probe.dependence_readout([])['same_prompt_re_measurement'] is False


RE_MEASURED = "N's duplicates-cut result is a same-prompt re-measurement of Phase 25's N draws"


def test_the_re_measurement_wording_rule_fires_at_half_of_the_received_draws():
    """Review round 1: the fake Phase 25 N draw is STEP for every prompt. 39 of 78 N draws re-drawing it is exactly
    1/2 and fires the rule; 36 of 78 does not. The rule changes the statement's wording, never a decision."""
    control, tempered = _rows('C', CONTROL), _rows('NT', lambda p, r: _distinct(p + r))
    redraw = lambda n: _rows('N', lambda p, r: STEP if p < n else _distinct(p + r))  # noqa: E731
    at = probe.compute_readouts(*_saved(control, redraw(13), tempered), already_proposed=KNOWN,
                                run_end=_run_end('COMPLETED', 'completed'))
    below = probe.compute_readouts(*_saved(control, redraw(12), tempered), already_proposed=KNOWN,
                                   run_end=_run_end('COMPLETED', 'completed'))
    assert at['descriptive']['phase25_dependence']['N']['same_policy_share'] == 0.5
    assert at['descriptive']['phase25_dependence']['N']['same_prompt_re_measurement'] is True
    assert RE_MEASURED in at['statement'] and '(39 of 78 received draws re-draw' in at['statement']
    assert RE_MEASURED not in below['statement'] and "NT's duplicates-cut result" not in at['statement']
    # The same draws with no Phase 25 policy on record: the rule is silent and every decision is unchanged.
    unlinked = lambda p: {**HIDDEN_REFERENCE, 'phase25_n_policy_hash': None, 'phase25_n_raw_sha256': None}  # noqa: E731
    same = probe.compute_readouts(*_saved(control, _rows('N', lambda p, r: STEP if p < 13 else _distinct(p + r),
                                                         reference=unlinked), tempered), already_proposed=KNOWN,
                                  run_end=_run_end('COMPLETED', 'completed'))
    assert RE_MEASURED not in same['statement'] and same['decisions'] == at['decisions']
    assert 'DISTINCT means only "not this study\'s own slot 1", not "new"' in at['statement']


def _census_reference(p):
    """Prompt p's slot-1 policy is _distinct(p): four census slot-1 policies over the 26 prompts."""
    slot1 = _distinct(p)
    return {**HIDDEN_REFERENCE, 'slot1_policy_hash': _hash(slot1), 'slot1_raw_sha256': s2.sha256_text(slot1),
            'slot1_rules_text_sha256': s2.sha256_text(s2.rules_text(slot1))}


def test_policy_concentration_separates_policies_already_proposed_from_novel_ones():
    """Review rounds 1 and 2: DISTINCT is only "not this study's own slot 1". A draw of a policy some in-scope v4
    study already proposed, in either slot, is distinct but not new; the concentration and the novel split say so,
    with re-draws of a certified policy on their own line."""
    rows = _rows('N', lambda p, r: _distinct(p + 1) if p < 13 else STEP, reference=_census_reference)
    census = probe.census_slot1_policies([r['request'] for r in rows])
    assert len(census) == 4
    result = probe.policy_concentration(rows, census, set(), census)
    assert (result['received'], result['distinct_draws'], result['distinct_policies']) == (78, 78, 5)
    assert (result['largest_policy_prompts'], result['largest_policy_draws']) == (13, 39)
    prior, novel = result['already_proposed_in_an_in_scope_v4_study'], result['novel']
    assert (prior['distinct_draws'], prior['distinct_policies'], prior['working_draws']) == (39, 4, 0)
    assert (novel['distinct_draws'], novel['distinct_policies'], novel['working_draws'], novel['working_policies']) == (39, 1, 39, 1)
    assert result['census_slot1_policy_redraws_round1_set']['distinct_draws'] == 39
    assert result['certified_policy_redraws']['distinct_draws'] == 0
    # Round 2: STEP was proposed by a study outside the census (say, a certified slot 1 of a study that never reached
    # slot 2). Round 1's census-only set called its 39 WORKING draws novel; the already-proposed set does not, and
    # the certified line reports them.
    wider = probe.policy_concentration(rows, census | {_hash(STEP)}, {_hash(STEP)}, census)
    assert wider['novel']['distinct_draws'] == 0 and wider['novel']['working_draws'] == 0
    assert wider['already_proposed_in_an_in_scope_v4_study']['distinct_draws'] == 78
    assert (wider['certified_policy_redraws']['distinct_draws'], wider['certified_policy_redraws']['working_draws']) == (39, 39)
    assert wider['census_slot1_policy_redraws_round1_set']['distinct_draws'] == 39
    assert result['working_per_distinct_working_policy'] == {
        'working_draws': 39, 'working_policies': 1, 'draws_per_policy': 39.0, 'largest_working_policy_draws': 39,
        'largest_working_policy_prompts': 13}
    # Prompts linked by a shared slot-1 policy or a shared drawn policy: 4 groups for a control that repeats its own
    # slot 1; 1 group once the draws cross between the groups.
    control = _rows('C', lambda p, r: _distinct(p), reference=_census_reference)
    assert len(set(probe.linked_prompt_groups(control).values())) == 4
    assert len(set(probe.linked_prompt_groups(rows).values())) == 1


def test_clustered_intervals_are_wider_than_the_wilson_interval_when_draws_cluster_and_are_deterministic():
    """Review round 1: 9 prompts WORKING on every draw and 17 on none is 27 of 78 draws, but only 26 prompts of
    information; the bootstrap by prompt is wider than the Wilson interval over draws. At zero successes the
    bootstrap collapses to [0, 0] and the one-observation-per-linked-group Wilson interval stays informative."""
    reference = lambda p: {**HIDDEN_REFERENCE, 'slot1_policy_hash': f'slot1-{p}'}  # noqa: E731
    clustered = _rows('N', lambda p, r: STEP if p < 9 else NO_CHANGE, reference=reference)
    rate = probe.clustered_rate(clustered, lambda r: r['c']['working'], 'working', arm='N')
    wilson, boot = rate['wilson95_over_draws'], rate['bootstrap95_by_prompt']
    assert (rate['successes'], rate['received'], rate['prompts']) == (27, 78, 26)
    assert boot[0] < wilson[0] and boot[1] > wilson[1]
    assert rate == probe.clustered_rate(clustered, lambda r: r['c']['working'], 'working', arm='N'), 'deterministic'
    # STEP drawn on prompts 0-8 links them into one group: 1 + 17 groups.
    assert rate['linked_prompt_groups'] == 18
    none = probe.clustered_rate(_rows('N', lambda p, r: NO_CHANGE, reference=reference),
                                lambda r: r['c']['working'], 'working', arm='N')
    assert none['bootstrap95_by_prompt'] == [0.0, 0.0] and none['wilson95_one_observation_per_linked_group'][1] > 0.1
    assert probe.cluster_bootstrap([], 'seed') == [None, None]
    rates = probe.clustered_rates(clustered, {HIDDEN_REFERENCE['slot1_policy_hash']}, 'N')
    assert set(rates) == {'distinct', 'distinct_novel', 'working', 'working_novel'}
    assert rates['working']['successes'] == rates['working_novel']['successes'] == 27
    # Review round 2: novel is judged against the already-proposed set; STEP proposed before is not novel.
    known = probe.clustered_rates(clustered, {HIDDEN_REFERENCE['slot1_policy_hash'], _hash(STEP)}, 'N')
    assert known['working']['successes'] == 27 and known['working_novel']['successes'] == 0


def test_a_bootstrap_over_fewer_than_ten_clusters_is_withheld():
    """Review round 2: prompts linked through shared policies can merge into very few groups, and a percentile
    bootstrap over G clusters has zero width at G = 1. Below 10 clusters it is withheld (null, with a note); the
    Wilson interval counting each linked group once is still reported, and it is the one a cost model uses."""
    assert probe.MIN_BOOTSTRAP_CLUSTERS == 10
    assert probe.cluster_bootstrap([(10, 26)], 'x') == [None, None]
    assert probe.cluster_bootstrap([(1, 3)] * 9, 'x') == [None, None]
    assert None not in probe.cluster_bootstrap([(1, 3)] * 10, 'x')
    # Every prompt draws STEP: all 26 prompts form one linked group.
    reference = lambda p: {**HIDDEN_REFERENCE, 'slot1_policy_hash': f'slot1-{p}'}  # noqa: E731
    one = probe.clustered_rate(_rows('N', lambda p, r: STEP, reference=reference), lambda r: r['c']['working'],
                               'working', arm='N')
    assert (one['linked_prompt_groups'], one['prompts'], one['rate']) == (1, 26, 1.0)
    assert one['bootstrap95_by_linked_prompt_group'] == [None, None]
    assert one['bootstrap_withheld'] == {'by_prompt': False, 'by_linked_prompt_group': True}
    assert None not in one['bootstrap95_by_prompt'] and 'wilson95_one_observation_per_linked_group' in one['interval_note']
    low, high = one['wilson95_one_observation_per_linked_group']
    assert low < 0.25 and high == 1.0, 'one group is one observation: the interval is wide, never [1, 1]'
    # Only 5 prompts received anything: both bootstraps are withheld.
    few = probe.clustered_rate(_rows('N', lambda p, r: STEP, prompts=5, reference=reference),
                               lambda r: r['c']['working'], 'working', arm='N')
    assert few['bootstrap95_by_prompt'] == few['bootstrap95_by_linked_prompt_group'] == [None, None]
    assert few['bootstrap_withheld'] == {'by_prompt': True, 'by_linked_prompt_group': True}


def test_invalid_draws_are_split_by_what_a_study_would_do():
    """Review round 1: a schema failure goes back for one format repair in a real study; an empty response, a
    CandidatePolicy failure and a stale parent do not. I1 and I2 count first attempts."""
    stale = json.loads(STEP)
    stale['candidate']['parent_version'] = 'policy-v9'
    raws = ['not json', '{"candidate": {}}', json.dumps(stale), STEP, NO_STEP]
    rows = _rows('N', lambda p, r: raws[p % 5] if r == 0 else STEP, prompts=5)
    rows.append({'request': {'prompt_id': 'e', 'reference': HIDDEN_REFERENCE}, 'received': True,
                 'result': {'status': 'empty_response', 'raw': None}, 'c': s2.classify_response('', HIDDEN_REFERENCE)})
    # A parsed candidate the study's later policy check rejects (classify_response's CandidatePolicy branch).
    rows.append({'request': {'prompt_id': 'f', 'reference': HIDDEN_REFERENCE}, 'received': True,
                 'result': {'status': 'ok', 'raw': STEP}, 'c': {'class': 'INVALID'}})
    split = probe.invalid_split(rows)
    assert split['schema_failure_a_study_sends_back_for_one_format_repair'] == 2
    assert split['not_repaired_by_a_study'] == {'empty': 1, 'candidate_policy': 1, 'stale_parent': 1, 'total': 3}
    assert split['invalid'] == 5 and split['received'] == 17
    assert split['not_repaired_rate_received'] == pytest.approx(3 / 17)


def test_the_calibrated_range_is_read_from_c_alone():
    """Review round 2: the working claim is calibrated at COMMON firing rates up to 0.10, i.e. under the null, where
    both arms share C's rate. So the range is read from C alone: its point rate ('outside' above 0.10) and its Wilson
    95% upper bound ('not_confirmed' above 0.10). The pooled X-and-C rate is reported and drives no wording, because
    X's own gain inflates it on every SHOWN claim (round 1 read it as a third leg)."""
    assert probe.calibrated_range(0, 78, 0, 78)['reading'] == 'within'
    assert probe.calibrated_range(0, 78, 2, 78)['reading'] == 'within'
    assert probe.calibrated_range(0, 78, 3, 78)['reading'] == 'not_confirmed'      # upper bound 0.107
    pooled = probe.calibrated_range(30, 78, 0, 78)                                   # pooled 30 of 156
    assert pooled['reading'] == 'within' and pooled['pooled_rate_descriptive'] == pytest.approx(30 / 156)
    assert probe.calibrated_range(0, 78, 8, 78)['reading'] == 'outside'            # 0.103
    assert probe.calibrated_range(0, 78, 0, 0)['reading'] == 'unknown'

    def readouts(control, hidden=GOOD):
        return probe.compute_readouts(*_saved(_rows('C', control), _rows('N', hidden), _rows('NT', GOOD)),
                                      already_proposed=KNOWN, run_end=_run_end('COMPLETED', 'completed'))
    # N's working claim is SHOWN while C fires 0 of 78: no caveat, although the pooled rate is 27 of 156.
    quiet = readouts(CONTROL)
    assert quiet['decisions']['N']['verdicts']['working'] == 'SHOWN'
    assert quiet['descriptive']['calibrated_range']['N']['reading'] == 'within' and "working claim" not in quiet['statement']
    # C fires 3 of 78 (one prompt): the claim is still SHOWN (9 prompts against 1) and the range is not confirmed.
    three = readouts(lambda p, r: STEP if p == 25 else CONTROL(p, r))
    assert three['decisions']['N']['verdicts']['working'] == 'SHOWN'
    assert three['descriptive']['calibrated_range']['N']['reading'] == 'not_confirmed'
    assert ("N's working claim: its calibrated range (common firing at most 0.10) is not confirmed (C's firing rate "
            '0.038, its 95% upper bound 0.107)') in three['statement']
    # C fires 9 of 78 on prompts where N fires too: SHOWN (6 prompts against 0), and outside the calibrated range.
    nine = readouts(lambda p, r: STEP if p in (0, 3, 6) else CONTROL(p, r))
    assert nine['decisions']['N']['verdicts']['working'] == 'SHOWN'
    assert "N's working claim is outside its calibrated range: C's firing rate 0.115 is above 0.10" in nine['statement']
    # A working claim that is not shown carries no caveat, whatever C does.
    silent = readouts(lambda p, r: STEP if p in (0, 3, 6) else CONTROL(p, r), hidden=lambda p, r: _distinct(p + r))
    assert silent['decisions']['N']['verdicts']['working'] == 'NOT_SHOWN' and "N's working claim" not in silent['statement']


def test_an_incomplete_decision_falls_back_to_a_complete_round_one():
    readouts = probe.compute_readouts(*_saved(*_stopped_after_round_one()), already_proposed=KNOWN, run_end=_run_end())
    n, nt = readouts['decisions']['N'], readouts['decisions']['NT']
    assert n['decision'] == nt['decision'] == 'INCOMPLETE'
    assert n['declared']['basis'] == 'round_1_only' and n['declared']['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP'
    assert n['round1_fallback']['working_share_gain_min'] == '1' and n['round1_fallback']['planned_draws'] == {'X': 26, 'C': 26}
    # The all-rounds figures stay beside the round-1 decision.
    assert n['distinct']['D_X'] == pytest.approx(26 / 78) and n['working']['gain'] == 3
    assert nt['declared']['basis'] == 'round_1_only' and nt['declared']['decision'] == 'NOT_RECOMMENDED'
    assert readouts['statement'].startswith("recommended for a later loop's own declaration: N. N RECOMMEND_FOR_A_LATER_LOOP (round 1 only)")


@pytest.mark.parametrize('run_end,permitted', [
    (_run_end('STOPPED', 'spend_guard'), True),
    (_run_end('COMPLETED', 'completed'), True),
    (_run_end('ABORTED', 'PlanningError', traceback='Traceback ...'), True),
    (_run_end('STOPPED', 'operator_stop'), False),
    (_run_end('ABORTED', 'abandoned'), False),
    (_run_end('COMPLETED', 'completed', stop_signal={'signal': 'SIGTERM'}), False),
    (_run_end('COMPLETED', 'completed', resend_pass={'ended': 'operator_stop'}), False),
    (_run_end('ABORTED', 'another_paid_run_after_claim'), False),
    (None, False),
])
def test_the_round1_fallback_applies_only_after_a_stop_the_operator_does_not_choose(run_end, permitted):
    readouts = probe.compute_readouts(*_saved(*_stopped_after_round_one()), already_proposed=KNOWN, run_end=run_end)
    n = readouts['decisions']['N']
    assert readouts['run_end']['round1_fallback_permitted'] is permitted
    if permitted:
        assert n['declared']['basis'] == 'round_1_only'
    else:
        assert n['round1_fallback'] is None and n['declared']['decision'] == 'INCOMPLETE'
        assert readouts['statement'].startswith('no arm is recommended. N INCOMPLETE')


def test_readouts_refuse_until_the_run_has_ended(tmp_path, capsys):
    requests, results = _saved(*_stopped_after_round_one())
    plan = {'requests': requests, 'populations': {'already_proposed': KNOWN}}
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    (tmp_path / 'responses.jsonl').write_text(''.join(json.dumps(line) + '\n' for line in results))
    manifest = {'status': 'RUNNING', 'ended_at': None, 'stop_reason': None, 'traceback': None, 'stop_signal': None,
                'resend_pass': None, 'harness_sha256': probe.sha256_file(probe.__file__), 'plan_hash': probe.plan_hash(plan)}
    path = tmp_path / probe.MANIFEST_NAME
    for status, ended_at in (('RUNNING', None), ('STARTING', None), ('COMPLETED', None), (None, 'x')):
        path.write_text(json.dumps({**manifest, 'status': status, 'ended_at': ended_at}))
        for other in (False, True):
            with pytest.raises(probe.PlanningError, match='has not ended'):
                probe.recompute_readouts(tmp_path, allow_other_harness=other)
    assert probe.main(['--readouts', str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    assert 'REJECTED' in printed and 'decisions' not in printed
    path.write_text(json.dumps({**manifest, 'status': 'STOPPED', 'stop_reason': 'consecutive_errors',
                                'ended_at': '2026-09-25T00:00:00Z'}))
    assert probe.recompute_readouts(tmp_path)['decisions']['N']['declared']['basis'] == 'round_1_only'
    path.write_text(json.dumps({**json.loads(path.read_text()), 'plan_hash': '0' * 64}))
    with pytest.raises(probe.PlanningError, match="NOT THE RUN'S HARNESS"):
        probe.recompute_readouts(tmp_path)
    assert probe.recompute_readouts(tmp_path, allow_other_harness=True)['plan_matches_run'] is False
    # Review round 2: a saved plan without its already-proposed record has no read-outs (never computed against an
    # empty set, which would call every draw novel).
    (tmp_path / 'plan.json').write_text(json.dumps({'requests': requests}))
    with pytest.raises(probe.PlanningError, match='already-proposed'):
        probe.recompute_readouts(tmp_path, allow_other_harness=True)


@pytest.mark.parametrize('record', [
    None, {}, {'policy_hashes': [], 'certified_policy_hashes': []},
    {'policy_hashes': ['a' * 64], 'certified_policy_hashes': ['b' * 64]},
    {'policy_hashes': 'a' * 64, 'certified_policy_hashes': []},
    {'policy_hashes': ['a' * 64, None], 'certified_policy_hashes': []},
])
def test_the_read_outs_refuse_a_missing_or_malformed_already_proposed_record(record):
    """Review round 2: the novel and certified figures are computed only against the plan's own record."""
    with pytest.raises(probe.PlanningError):
        probe.compute_readouts(*_saved(*_stopped_after_round_one()), already_proposed=record, run_end=_run_end())


def test_the_certified_policies_come_from_the_pinned_run_manifests(tmp_path, monkeypatch):
    """Review round 2: a missing or changed run manifest refuses; the real ones certify exactly the declared four."""
    with pytest.raises(probe.PlanningError, match='not the pinned one'):
        probe.certified_policies(tmp_path)
    if all((ROOT / path).exists() for path, _ in s2.PHASE_MANIFESTS.values()):
        certified = probe.certified_policies()
        assert sorted(certified) == sorted(probe.CERTIFIED_POLICY_HASHES) and len(certified) == 4
        assert certified['dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521'].startswith('phase17 attempt 9')
        # The manifests' certified set must equal the declared one; a declared set that differs refuses.
        monkeypatch.setattr(probe, 'CERTIFIED_POLICY_HASHES', probe.CERTIFIED_POLICY_HASHES[:3])
        with pytest.raises(probe.PlanningError, match='exactly the declared four'):
            probe.certified_policies()


def test_the_already_proposed_record_holds_both_slots_of_every_study_and_every_certified_policy(monkeypatch):
    """Review round 2: both slots of every in-scope v4 study (a study with no proposal adds nothing), the source
    case of each study that proposed, and a certified policy that is not among the proposals refuses."""
    a, b, c = 'a' * 64, 'b' * 64, 'c' * 64
    studies = [{'study_id': 's1', 'candidates': [{'policy_hash': a}, {'policy_hash': b}]},
               {'study_id': 's2', 'candidates': [{'policy_hash': b}]}, {'study_id': 's3', 'candidates': []}]
    monkeypatch.setattr(probe.s2, 'load_record', lambda connection, kind, record_id: ({'source_fault_spec': {'f': 4}}, True))
    monkeypatch.setattr(probe, 'certified_policies', lambda root=None: {b: 'phase23 attempt 1 (s1)'})
    record = probe.already_proposed_record(None, studies)
    assert record['policy_hashes'] == [a, b] and record['certified_policy_hashes'] == [b]
    assert (record['studies'], record['studies_with_a_proposal']) == (3, 2)
    assert record['proposals_with_a_policy_by_slot'] == {'slot1': 2, 'slot2': 1}
    assert list(record['source_fault_spec_content_hashes_of_the_studies_with_a_proposal'].values()) == [2]
    monkeypatch.setattr(probe, 'certified_policies', lambda root=None: {c: 'phase23 attempt 9 (elsewhere)'})
    with pytest.raises(probe.PlanningError, match='certified policy is not among'):
        probe.already_proposed_record(None, studies)
    monkeypatch.setattr(probe.s2, 'load_record', lambda connection, kind, record_id: (None, False))
    with pytest.raises(probe.PlanningError, match='cannot be read'):
        probe.already_proposed_record(None, studies)


# ---------------------------------------------------------------- the $0 simulation that set the minimums

def test_the_yield_null_chooses_the_smallest_minimum_under_the_target(monkeypatch):
    monkeypatch.setattr(probe, 'SCENARIOS', {'independent': (('beta', 0.0), ('beta', 0.0)),
                                             'C repeats': (('copy', 1.0), ('beta', 0.0))})
    monkeypatch.setattr(probe, 'SHARED_RHOS', (0.0,))
    result = probe.yield_null(random.Random('test'), 3, 60)
    chosen = Fraction(result['smallest_min_with_worst_cell_at_most_target'])
    worst = {Fraction(k): v for k, v in result['worst_cell_by_min'].items()}
    assert worst[chosen] <= probe.FALSE_ALARM_TARGET and all(v > probe.FALSE_ALARM_TARGET for k, v in worst.items() if k < chosen)
    assert all(worst[a] >= worst[b] for a, b in zip(sorted(worst), sorted(worst)[1:])), 'monotone in the minimum'


# Review rounds 1 and 2 changed the harness, so the numbers were recomputed into a new directory (protocol §12 step 2).
SAVED_NUMBERS = ROOT / 'artifacts/phase29-2026-09-25/protocol-numbers-r2/protocol_numbers.out.json'


@pytest.mark.skipif(not SAVED_NUMBERS.exists(), reason='the protocol numbers have not been written yet')
def test_the_saved_protocol_numbers_chose_the_harness_minimums():
    numbers = json.loads(SAVED_NUMBERS.read_text())
    assert numbers['harness_sha256'] == probe.sha256_file(probe.__file__), 'recompute the numbers after a harness edit'
    assert numbers['harness_minimum_is_the_chosen_one'] == {'all_rounds': True, 'round1_fallback': True}
    assert numbers['thresholds'] == json.loads(json.dumps(probe.thresholds()))
    assert Fraction(numbers['yield_null_all_rounds']['smallest_min_with_worst_cell_at_most_target']) == 3


# ---------------------------------------------------------------- live execution (fakes, no network)

def test_spend_guard_and_budget():
    guard = probe.SpendGuard(15.0)
    assert sum(guard.admit() for _ in range(400)) == 300 and guard.charged == pytest.approx(300 * 0.04984)
    probe.check_budget(234, 15.0)
    for total, cap in ((301, 15.0), (10, 15.01), (10, 0), (10, float('nan'))):
        with pytest.raises(probe.PlanningError):
            probe.check_budget(total, cap)
    with pytest.raises(probe.PlanningError):
        probe.SpendGuard(15.01)


class FakeSleep:
    def __init__(self, on_call=None):
        self.calls, self.on_call = [], on_call

    async def __call__(self, seconds):
        self.calls.append(seconds)
        if self.on_call:
            self.on_call(len(self.calls))


def _small_plan(n=6):
    requests, prompts = [], {}
    for index in range(n):
        arm = probe.ARMS[index % 3]
        user = f'prompt {index // 3}' + ('' if arm == 'C' else ' without the prior candidate')
        messages = [{'role': 'system', 'content': 'You are a test.'}, {'role': 'user', 'content': user}]
        messages_hash = content_hash(messages)
        prompts[messages_hash] = {'messages_hash': messages_hash, 'messages': messages}
        temperature = probe.ARM_TEMPERATURE[arm]
        requests.append({'request_id': f'r{index + 1:04d}', 'population': 'slot2', 'prompt_id': f's{index // 3}:slot2',
                         'study_id': f's{index // 3}', 'phase': 'phase23', 'arm': arm, 'repeat': 0,
                         'temperature': temperature, 'messages_hash': messages_hash,
                         'request_hash': s2.request_digest(s2.request_body(messages, temperature)),
                         'reference': REFERENCE if arm == 'C' else HIDDEN_REFERENCE})
    return {'counts': {'total_requests': n}, 'requests': requests,
            'populations': {'already_proposed': KNOWN}}, prompts


class FakeOpenAI:
    """Modelled on the openai client the real RuntimeProvider builds."""

    script, calls = [], []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        FakeOpenAI.calls.append(kwargs)
        outcome = FakeOpenAI.script.pop(0) if FakeOpenAI.script else STEP
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(model='served-by/another-model', system_fingerprint='fp_test',
                               usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
                               choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=outcome))])

    async def close(self):
        pass


def _fake_settings(dry_settings, **changes):
    return dataclasses.replace(dry_settings, wandb_api_key='fake-not-a-key', **changes)


def test_the_sender_sends_each_arms_temperature_and_never_an_unplanned_request(tmp_path, dry_settings):
    plan, prompts = _small_plan(3)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    sender = s2.RequestSender(base=FakeOpenAI)

    async def go(requests, recorder):
        async with RuntimeProvider(_fake_settings(dry_settings), live_authorized=True, client_factory=sender) as provider:
            return await s2.run_requests(requests, prompts, provider, probe.SpendGuard(15.0), recorder,
                                         sender=sender, sleep=FakeSleep())
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    try:
        assert asyncio.run(go(plan['requests'], recorder)) == 'completed'
    finally:
        recorder.close()
    assert [call['temperature'] for call in FakeOpenAI.calls] == [0, 0, 0.4]
    assert [s2.request_digest(call) for call in FakeOpenAI.calls] == [r['request_hash'] for r in plan['requests']]
    assert (tmp_path / probe.MANIFEST_NAME).exists() and not (tmp_path / s2.MANIFEST_NAME).exists()
    wrong = [{**plan['requests'][2], 'request_hash': '0' * 64}]
    FakeOpenAI.calls = []
    other = tmp_path / 'second'
    other.mkdir()
    recorder = probe.Recorder(other, {'statuses': {}})
    try:
        with pytest.raises(s2.PlanningError, match='Request mismatch'):
            asyncio.run(go(wrong, recorder))
    finally:
        recorder.close()
    assert FakeOpenAI.calls == []


def _artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    (tmp_path / 'artifacts').mkdir(exist_ok=True)
    return tmp_path / 'artifacts'


def _manifest(artifacts, relative, name=probe.MANIFEST_NAME, **fields):
    path = artifacts / relative / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {'status': 'STOPPED', 'ended_at': '2026-09-25T00:00:00Z', 'statuses': {'error': 5},
            'generations_delivered': 0, 'charged_upper_bound': 0.4984, **fields}
    path.write_text(json.dumps(body))
    return path


def _claim(artifacts, number, out, pid=999999, directory=probe.CLAIM_DIR):
    path = artifacts / directory / f'claim-{number:02d}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'claim': path.name, 'pid': pid, 'out': out, 'plan_hash': 'plan',
                                'harness_sha256': 'harness', 'spend_cap': 15.0}))
    return path


IDLE = lambda: ('down', None)  # noqa: E731


def test_output_directories_claims_and_one_delivering_run(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    for bad in ('artifacts/phase25-2026-09-25/live', 'artifacts/phase29-2026-09-25', 'artifacts/phase29-x/a/b',
                f'artifacts/{probe.CLAIM_DIR}/x', '/tmp/elsewhere', 'artifacts/phase29-x/li ve'):
        with pytest.raises(probe.PlanningError):
            probe.check_output(bad)
    assert probe.check_output('artifacts/phase29-2026-09-25/live')
    _manifest(artifacts, 'phase29-2026-09-25/live')
    with pytest.raises(probe.PlanningError, match='exists'):
        probe.check_output('artifacts/phase29-2026-09-25/live')
    earlier = probe.earlier_live_runs(artifacts)
    assert earlier == [{'manifest': f'artifacts/phase29-2026-09-25/live/{probe.MANIFEST_NAME}', 'charged_upper_bound': 0.4984}]
    assert probe.effective_spend_cap(15.0, earlier) == pytest.approx(15 - 0.4984)
    with pytest.raises(probe.PlanningError, match='changed during the launch checks'):
        probe.take_claim((artifacts / 'phase29-2026-09-25/live-2').resolve(), 'plan', 'harness', expected_earlier=[])
    path, _ = probe.take_claim((artifacts / 'phase29-2026-09-25/live-2').resolve(), 'plan', 'harness',
                               expected_earlier=earlier)
    assert path.name == 'claim-01.json' and json.loads(path.read_text())['out'] == 'artifacts/phase29-2026-09-25/live-2'
    with pytest.raises(probe.PlanningError, match='no manifest'):
        probe.check_output('artifacts/phase29-2026-09-25/live-3')
    _manifest(artifacts, 'phase29-2026-09-25/live-2', statuses={'ok': 1}, generations_delivered=1)
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase29-2026-09-25/live-3')
    # The dry plan and the protocol numbers need a new directory but never look at live runs.
    assert probe.check_output('artifacts/phase29-2026-09-25/dry-plan-2', live=False)


def test_a_claim_never_names_dot_or_dot_dot():
    """Review round 1: RUN_PATH_PART matches '.' and '..', so claimed_output refuses them itself (as Phase 25)."""
    for out in ('artifacts/phase29-x/..', 'artifacts/phase29-x/.', 'artifacts/phase29-x/../phase29-y'):
        assert probe.claimed_output('/X/artifacts', out) is None, out
    assert probe.claimed_output('/X/artifacts', 'artifacts/phase29-x/live') == pathlib.Path('/X/artifacts/phase29-x/live')


def test_a_claim_name_a_racing_launch_took_is_never_overwritten(tmp_path, monkeypatch):
    """Review round 1 (mutant R6): the claim is hard-linked, so a name that appeared after the earlier-run scan
    refuses; os.replace would silently overwrite the other launch's claim."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    raced = _claim(artifacts, 1, 'artifacts/phase29-2026-09-25/other')
    before = raced.read_text()
    monkeypatch.setattr(probe, 'live_run_records', lambda _: {'undelivered': [], 'claim_numbers': []})
    with pytest.raises(probe.PlanningError, match='already taken'):
        probe.take_claim((artifacts / 'phase29-2026-09-25/live').resolve(), 'plan', 'harness', expected_earlier=[])
    assert raced.read_text() == before
    assert sorted(p.name for p in (artifacts / probe.CLAIM_DIR).iterdir()) == ['claim-01.json']


def test_finalize_abandoned_closes_a_dead_claim_and_charges_what_was_recorded(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    claim = _claim(artifacts, 1, 'artifacts/phase29-2026-09-25/live', pid=4242)
    with pytest.raises(probe.PlanningError, match='may still be running'):
        probe.finalize_abandoned(claim, alive=lambda pid: True)
    _manifest(artifacts, 'phase29-2026-09-25/live', status='RUNNING', ended_at=None, attempts=1,
              statuses={'ok': 1}, generations_delivered=1, charged_upper_bound=0.04984)
    lines = [{'request_id': 'r0001', 'status': 'ok', 'raw': STEP, 'attempts': [{'attempt': 1}]},
             {'request_id': 'r0002', 'status': 'error', 'raw': None,
              'attempts': [{'attempt': 1, 'code': 'REQUEST_TIMEOUT'}, {'attempt': 2, 'code': 'REQUEST_TIMEOUT'}]}]
    (artifacts / 'phase29-2026-09-25/live/responses.jsonl').write_text(
        '\n'.join(json.dumps(line) for line in lines) + '\n{"request_id": "r00')
    path, manifest = probe.finalize_abandoned(claim, alive=lambda pid: False)
    assert path.name == probe.MANIFEST_NAME and manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'abandoned'
    assert manifest['attempts'] == 5 and manifest['charged_upper_bound'] == pytest.approx(5 * 0.04984)
    assert manifest['generations_delivered'] == 1 and manifest['finalized_abandoned']['partial_lines_skipped'] == 1
    with pytest.raises(probe.PlanningError, match='already final'):
        probe.finalize_abandoned(claim, alive=lambda pid: False)
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase29-2026-09-25/live-2')
    with pytest.raises(probe.PlanningError, match='takes a claim file'):
        probe.finalize_abandoned(artifacts / 'phase27-live-claims/claim-01.json', alive=lambda pid: False)


def test_a_live_hidden_probe_process_counts_as_alive():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'slot2_hidden_probe'])
    try:
        assert probe.claim_process_alive(child.pid) is True
    finally:
        child.kill()
        child.wait()
    assert probe.claim_process_alive(child.pid) is False
    assert probe.claim_process_alive(None) is True and probe.claim_process_alive(-1) is True


def test_a_claim_process_whose_command_cannot_be_read_counts_as_alive(monkeypatch):
    """Review round 1 (mutant I6): when the pid exists but ps fails, --finalize-abandoned must not close the claim."""
    monkeypatch.setattr(probe.os, 'kill', lambda pid, sig: None)

    def no_ps(*_, **__):
        raise OSError('no ps')

    def slow_ps(*_, **__):
        raise subprocess.TimeoutExpired('ps', 10)
    for broken in (no_ps, slow_ps):
        monkeypatch.setattr(probe.subprocess, 'run', broken)
        assert probe.claim_process_alive(4242) is True


# Written out, not read from the harness: a list taken from the module under test would shrink with it.
@pytest.mark.parametrize('relative,name', [
    ('phase20-2026-09-23/run', 'dev-probe-manifest.json'),
    ('phase21-2026-09-23/live', 'lapse-probe-manifest.json'),
    ('phase23-2026-09-24', 'full-loop-manifest.json'),
    ('phase25-2026-09-24/live', 'slot2-probe-manifest.json'),
    ('phase26-2026-09-24/run-1', 'gap-probe-manifest.json'),
    ('phase27-2026-09-24/live', 'report-word-probe-manifest.json'),
    ('phase28-2026-09-25', 'any-manifest.json'),
    ('phase28-2026-09-25/run', 'loop-manifest.json'),
    ('phase30-2026-09-25', 'run-manifest.json'),
    ('phase30-2026-09-25/live', 'report-field-probe-manifest.json'),
    ('phase31-2026-09-25/x', 'manifest.json'),
])
def test_every_sibling_manifest_glob_blocks_while_its_run_is_not_final(tmp_path, monkeypatch, relative, name):
    artifacts = _artifacts(tmp_path, monkeypatch)
    path = _manifest(artifacts, relative, name=name, status='RUNNING', ended_at=None)
    assert probe.other_paid_runs(status=IDLE)[0], relative
    path.write_text(json.dumps({'status': 'COMPLETED', 'ended_at': 'x'}))
    assert probe.other_paid_runs(status=IDLE)[0] == []
    path.write_text('not json')
    assert probe.other_paid_runs(status=IDLE)[0], 'an unreadable manifest counts as running'


@pytest.mark.parametrize('directory', ['phase20-live-claims', 'phase21-live-claims', 'phase23-live-claims',
                                       'phase25-live-claims', 'phase26-live-claims', 'phase27-live-claims',
                                       'phase28-live-claims', 'phase30-live-claims', 'phase31-live-claims'])
def test_every_sibling_claim_directory_blocks_until_its_run_is_final(tmp_path, monkeypatch, directory):
    artifacts = _artifacts(tmp_path, monkeypatch)
    phase = directory.split('-')[0]
    _claim(artifacts, 1, f'artifacts/{phase}-2026-09-25/live', directory=directory)
    assert 'no final manifest' in probe.other_paid_runs(status=IDLE)[0][0]
    _manifest(artifacts, f'{phase}-2026-09-25/live', name='run-manifest.json', status='COMPLETED')
    assert probe.other_paid_runs(status=IDLE)[0] == []


def test_other_paid_runs_skip_the_seal_the_heldout_check_and_heldout_manifests(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    assert probe.other_paid_runs(status=IDLE) == ([], 'down')
    _manifest(artifacts, 'phase22-2026-09-24/x', name='run-manifest.json', status='RUNNING', ended_at=None)
    _manifest(artifacts, 'phase24-2026-09-24', name='heldout-manifest.json', status='RUNNING', ended_at=None)
    _manifest(artifacts, 'phase30-2026-09-25/live', name='heldout-manifest.json', status='RUNNING', ended_at=None)
    assert probe.other_paid_runs(status=IDLE)[0] == []
    opened = []
    real = pathlib.Path.read_text

    def spy(self, *args, **kwargs):
        opened.append(str(self))
        return real(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, 'read_text', spy)
    for number, out in enumerate(('artifacts/phase22-2026-09-24/x', 'artifacts/phase24-2026-09-24/x',
                                  'artifacts/heldout2/x', 'artifacts/phase26-x/../phase22-2026-09-24/x',
                                  'artifacts/phase26-live-claims/x', '/etc/x', None), 1):
        claim = _claim(artifacts, number, out, directory='phase30-live-claims')
        blockers, _ = probe.other_paid_runs(status=IDLE)
        assert blockers == [f'phase30-live-claims/{claim.name} cannot be read or names no valid run directory; '
                            'nothing it names was read'], out
        claim.unlink()
    assert not any('phase22' in path or 'phase24' in path or 'heldout2' in path for path in opened)
    running = _manifest(artifacts, 'phase20-2026-09-24/run', name='dev-probe-manifest.json', stop_reason='running')
    assert probe.other_paid_runs(status=IDLE)[0]
    assert probe.other_paid_runs(status=IDLE, ignore=[str(running)])[0] == []


def test_this_phases_own_runs_are_not_another_paid_run(tmp_path, monkeypatch):
    """Phase 29's own manifests and claims are the one-delivering-run rule's (live_run_records), not blockers."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase29-2026-09-25/live', status='RUNNING', ended_at=None)
    _claim(artifacts, 1, 'artifacts/phase29-2026-09-25/live')
    assert probe.other_paid_runs(status=IDLE)[0] == []
    with pytest.raises(probe.PlanningError, match='not final'):
        probe.check_output('artifacts/phase29-2026-09-25/live-2')


LAUNCH = ('./.venv/bin/python scripts/experiments/slot2_hidden_probe.py --execute-live --confirm-entity '
          'shreetbohara-quinstreet --out artifacts/phase29-2026-09-25/live --expect-plan-hash X')
FOREIGN_RUN = (4242, 1, 'python scripts/experiments/report_word_probe.py --execute-live --out y')


def test_the_process_guard_sees_other_runs_but_not_this_runs_own_caffeinate_tree():
    own, shell = os.getpid(), os.getppid()
    rows = [(shell, 1, '/bin/zsh -c cd faultlab && nohup caffeinate -is ./.venv/bin/python ...'),
            (own, shell, LAUNCH), (own + 100000, own, f'caffeinate -is {LAUNCH}')]
    assert probe.live_experiment_processes(lambda: rows) == []
    other = [(9000, 1, LAUNCH.replace('/live', '/live-x')), (9001, 9000, f'caffeinate -is {LAUNCH}')]
    assert [b.split(':')[0] for b in probe.live_experiment_processes(lambda: rows + other)] == ['pid 9000']
    assert probe.live_experiment_processes(lambda: [FOREIGN_RUN]) == [f'pid 4242: {FOREIGN_RUN[2]}']
    not_runs = [(5001, 1, 'grep scripts/experiments/slot2_hidden_probe.py --execute-live'),
                (5002, 1, 'python -m pytest --execute-live'), (5003, 1, f'caffeinate -is {LAUNCH}')]
    assert probe.live_experiment_processes(lambda: not_runs) == []

    def broken():
        raise OSError('no ps')
    assert 'could not be read' in probe.live_experiment_processes(broken)[0]


def test_a_paid_run_started_from_the_same_shell_is_seen():
    """Review round 1 (mutant O12; Phase 26 round 3, row 3a): only this process's ancestors and descendants are
    excluded, never its siblings. A second paid run launched from the same shell is reported."""
    own, shell = os.getpid(), os.getppid()
    sibling = './.venv/bin/python scripts/experiments/report_narrow_probe.py --execute-live --out y'
    rows = [(shell, 1, '/bin/zsh'), (own, shell, LAUNCH), (own + 100000, own, f'caffeinate -is {LAUNCH}'),
            (own + 100001, shell, sibling)]
    assert [b.split(':')[0] for b in probe.live_experiment_processes(lambda: rows)] == [f'pid {own + 100001}']


def test_the_real_process_list_feeds_the_paid_run_check(tmp_path, monkeypatch):
    _artifacts(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, 'process_list', lambda: [FOREIGN_RUN])
    assert probe.other_paid_runs(status=IDLE)[0] == [f'pid 4242: {FOREIGN_RUN[2]}']
    with pytest.raises(probe.PlanningError, match='cannot clear a process'):
        probe.check_other_paid_runs(SimpleNamespace(ignore_manifest=[]), status=IDLE)
    monkeypatch.setattr(probe, 'process_list', lambda: [])
    assert 'active campaign' in probe.other_paid_runs(status=lambda: ('active', 'campaign-x'))[0][0]
    assert 'could not be read' in probe.other_paid_runs(status=lambda: ('unknown', 'TimeoutError'))[0][0]
    assert probe.other_paid_runs(status=lambda: ('idle', None))[0] == []


# Review round 2: never the program-level approval (the words the relayed request and the protocol's status block
# carry); the owner's own answer to §18 question 1, at least 20 characters.
OWNER_QUOTE = 'Yes: Phase 29 is worth its $11.66 bound; run it once before Phase 28 (test answer).'
PROGRAM_PHRASE = 'go ahead with whatever u recommend'


def _owner_answer(**changes):
    return {'question': '§18 question 1', 'verbatim': OWNER_QUOTE, 'given_by': 'the project owner (test)',
            'date': '2026-09-25', **changes}


def _owner_line(answer=None):
    answer = _owner_answer() if answer is None else answer
    return probe.OWNER_ANSWER_LINE.format(given_by=answer['given_by'], date=answer['date'], verbatim=answer['verbatim'])


def _closing(line):
    return ['', '### Review log — round 1 (test)', '', 'Every finding applied.', '',
            '### Review log — closing (test)', '', 'The owner answered §18 question 1 in writing:', '', line]


def _gate(tmp_path, monkeypatch, plan, *, review=True, reviewed_line=True, marker=None, pins=True, phase_cap=15.0,
          quote=True, record=None, status=(), log=None):
    """A protocol and a review record that pass the gate; `record` changes the record (a value of ... drops a key).
    The Review log's closing entry quotes the record's own answer on the owner's line (so that the check a test
    aims at is the one that refuses); `log` replaces the whole Review log, `quote=False` leaves it out, and `status`
    adds lines to the status block."""
    _artifacts(tmp_path, monkeypatch)
    harness = probe.sha256_file(probe.__file__)
    plan_hash = probe.plan_hash(plan)
    answer = (record or {}).get('owner_answer', _owner_answer())
    well_formed = isinstance(answer, dict) and all(isinstance(answer.get(k), str) for k in ('given_by', 'date', 'verbatim'))
    lines = ['# test protocol']
    if marker:
        lines.append(f'Status: {marker}.')
    lines += list(status)
    lines += ['', '## Pins'] + ([f'harness {harness}', f'plan {plan_hash}'] if pins else [])
    if reviewed_line:
        lines.append(probe.REVIEWED_LINE.format(harness=harness, plan=plan_hash))
    if log is not None:
        lines += ['', '## Review log'] + list(log)
    elif quote:
        lines += ['', '## Review log'] + _closing(_owner_line(answer if well_formed else None))
    protocol = tmp_path / 'protocol.md'
    protocol.write_text('\n'.join(lines) + '\n')
    monkeypatch.setattr(probe, 'PROTOCOL', protocol)
    protocol_sha = probe.sha256_file(protocol)
    if review:
        path = tmp_path / probe.REVIEW_RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {'phase': 29, 'status': 'approved', 'approved_by': 'the reviewer (test)', 'owner_answer': _owner_answer(),
                'protocol_sha256': protocol_sha, 'harness_sha256': harness, 'plan_hash': plan_hash}
        if phase_cap is not None:
            body['phase_cap'] = phase_cap
        body.update(record or {})
        path.write_text(json.dumps({key: value for key, value in body.items() if value is not ...}))
    return SimpleNamespace(out='artifacts/phase29-test/live', expect_harness_sha256=harness,
                           expect_protocol_sha256=protocol_sha, expect_plan_hash=plan_hash, spend_cap=15.0,
                           confirm_entity='shreetbohara-quinstreet', ignore_manifest=[])


class CredentialRead(Exception):
    pass


def _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts, status=IDLE):
    def no_credentials(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', no_credentials)
    with pytest.raises(probe.PlanningError) as error:
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=status)
    assert not (tmp_path / 'artifacts/phase29-test').exists() and not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()
    return str(error.value)


def test_the_live_gate_enforces_pins_review_and_one_paid_run(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    for change, message in ((dict(expect_harness_sha256='0' * 64), 'harness'),
                            (dict(expect_protocol_sha256='0' * 64), 'does not match the protocol'),
                            (dict(expect_plan_hash='0' * 64), '--expect-plan-hash'),
                            (dict(spend_cap=0.05), 'exceed')):
        assert message in _refused_before_credentials(tmp_path, monkeypatch, SimpleNamespace(**{**vars(args), **change}),
                                                      plan, prompts)
    tampered = {k: dict(v) for k, v in prompts.items()}
    tampered[plan['requests'][0]['messages_hash']]['messages'] = [{'role': 'system', 'content': 'other'}]
    assert 'no verified prompt' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, tampered)
    for marker in ('NOT yet reviewed', 'not YET reviewed'):
        args = _gate(tmp_path, monkeypatch, plan, marker=marker)
        assert 'NOT yet reviewed' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, pins=False, reviewed_line=False)
    assert 'does not declare this harness' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, reviewed_line=False)
    assert 'Reviewed for launch' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    (tmp_path / probe.REVIEW_RECORD).unlink()
    args = _gate(tmp_path, monkeypatch, plan, review=False)
    assert 'No readable review record' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    for cap in (None, 25.0, 'fifteen'):
        args = _gate(tmp_path, monkeypatch, plan, phase_cap=cap)
        assert 'phase_cap' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)
    record = tmp_path / probe.REVIEW_RECORD
    for key in ('protocol_sha256', 'harness_sha256', 'plan_hash'):
        good = record.read_text()
        record.write_text(json.dumps({**json.loads(good), key: '0' * 64}))
        assert 'review record does not name' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
        record.write_text(good)
    assert 'active campaign' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts,
                                                             status=lambda: ('active', 'c'))
    monkeypatch.setattr(probe, 'process_list', lambda: [FOREIGN_RUN])
    assert 'pid 4242' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    monkeypatch.setattr(probe, 'process_list', lambda: [])
    monkeypatch.setattr(probe, 'PROTOCOL', tmp_path / 'missing.md')
    assert 'No protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)

    def credential_read(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', credential_read)
    with pytest.raises(CredentialRead):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts/phase29-test').exists()


WRAPPED_QUOTE = ('Yes. I have read §9.3 and §18 question 1, and the new information from NT and the WORKING '
                 'estimates is worth the $11.66 bound, so run Phase 29 once before the Phase 28 build starts.')


@pytest.mark.parametrize('changes,message', [
    ({'status': ...}, 'status is not "approved"'),
    ({'status': 'pending'}, 'status is not "approved"'),
    ({'status': 'APPROVED'}, 'status is not "approved"'),
    ({'approved_by': ...}, 'names no approver'),
    ({'approved_by': ' '}, 'names no approver'),
    ({'approved_by': 7}, 'names no approver'),
    ({'owner_answer': ...}, 'no owner_answer'),
    ({'owner_answer': None}, 'no owner_answer'),
    ({'owner_answer': 'go ahead'}, 'no owner_answer'),
    ({'owner_answer': {k: v for k, v in _owner_answer().items() if k != 'given_by'}}, 'no owner_answer'),
    ({'owner_answer': {k: v for k, v in _owner_answer().items() if k != 'question'}}, 'no owner_answer'),
    ({'owner_answer': _owner_answer(date=' ')}, 'no owner_answer'),
    ({'owner_answer': _owner_answer(verbatim='')}, 'no owner_answer'),
    # Review round 2.
    ({'owner_answer': _owner_answer(question='§18 question 2')}, 'owner_answer.question'),
    ({'owner_answer': _owner_answer(question='question 1')}, 'owner_answer.question'),
    ({'owner_answer': _owner_answer(verbatim=' ' + OWNER_QUOTE)}, 'one line'),
    ({'owner_answer': _owner_answer(verbatim=WRAPPED_QUOTE[:100] + '\n' + WRAPPED_QUOTE[100:])}, 'one line'),
    ({'owner_answer': _owner_answer(verbatim='N')}, 'shorter than 20'),
    ({'owner_answer': _owner_answer(verbatim='Run it: zq7 ok')}, 'shorter than 20'),
    ({'owner_answer': _owner_answer(verbatim=PROGRAM_PHRASE)}, 'program document'),
    ({'owner_answer': _owner_answer(verbatim='Go ahead, with whatever U recommend!')}, 'program document'),
])
def test_the_review_record_must_say_approved_name_the_approver_and_carry_the_owners_words(
        tmp_path, monkeypatch, changes, message):
    """Review rounds 1 and 2 (as Phase 30, then stricter): a record with the three pins and the cap is not enough;
    the owner's own answer to §18 question 1 must be recorded, and the program-level approval, a one-letter answer or
    a wrapped one never stands in for it. The protocol quotes the record's own answer on the closing line, so each
    case is refused by the check it names, before the credential read and any claim."""
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan, record=changes)
    assert message in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)


def _log_variants():
    line = _owner_line()
    return {
        'no Review log at all': (None, 'no Review log closing entry'),
        'the owner line in a round-1 entry, no closing entry': (
            ['', '### Review log — round 1 (test)', '', line], 'no Review log closing entry'),
        'a closing entry under an earlier Review log only': (
            _closing(line) + ['', '## Later section', '', '## Review log', '', '### Review log — round 2 (test)'],
            'no Review log closing entry'),
        'the owner line under a later round heading': (
            _closing('Closed.')[:-1] + ['', '### Review log — round 3 (test)', '', line], 'does not carry'),
        'the owner line wrapped across two lines': (
            _closing(line[:60]) + [line[60:]], 'never wrapped'),
        'the owner line as a list item': (_closing(f'- {line}'), 'does not carry'),
        'the owner line in backticks': (_closing(f'`{line}`'), 'does not carry'),
        'the owner line in bold': (_closing(f'**{line}**'), 'does not carry'),
        'the owner line twice': (_closing(line) + [line], 'exactly once'),
        'another given_by on the line': (
            _closing(_owner_line(_owner_answer(given_by='someone else'))), 'does not carry'),
        'another date on the line': (_closing(_owner_line(_owner_answer(date='2026-09-24'))), 'does not carry'),
        'the words inside a sentence, not the owner line': (
            _closing(f'The owner said "{OWNER_QUOTE}" on 2026-09-25.'), 'does not carry'),
    }


@pytest.mark.parametrize('name', list(_log_variants()))
def test_the_owners_words_must_stand_on_one_bare_line_of_the_closing_entry(tmp_path, monkeypatch, name):
    """Review round 2: where the words stand is checked, not only that they occur somewhere in the file."""
    plan, prompts = _small_plan()
    log, message = _log_variants()[name]
    args = _gate(tmp_path, monkeypatch, plan, **({'quote': False} if log is None else {'log': log}))
    assert message in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)


def test_the_owners_words_must_not_be_in_the_status_block_or_the_program(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    # The status block carries the owner's words (the answer belongs only in the closing entry).
    args = _gate(tmp_path, monkeypatch, plan, status=[f'The owner said: "{OWNER_QUOTE}"'])
    assert 'status block' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    # The status block quotes the program-level approval and the record reuses it: refused.
    args = _gate(tmp_path, monkeypatch, plan, status=[f'The owner approved the program: "{PROGRAM_PHRASE}".'],
                 record={'owner_answer': _owner_answer(verbatim=PROGRAM_PHRASE)})
    assert 'status block' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    # The program document cannot be read: fail closed.
    args = _gate(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(probe, 'PROGRAM', tmp_path / 'no-such-program.md')
    assert 'cannot be read' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)


def test_a_complete_record_and_closing_entry_pass_and_a_bare_record_does_not(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    record = probe.check_review(probe.PROTOCOL.read_text(), args.expect_protocol_sha256, args.expect_harness_sha256,
                                args.expect_plan_hash, root=tmp_path)
    assert record['owner_answer'] == _owner_answer() and record['approved_by'] == 'the reviewer (test)'
    # A long answer on one line (however long the line) passes; the closing heading may carry a suffix.
    long_answer = _owner_answer(verbatim=WRAPPED_QUOTE)
    args = _gate(tmp_path, monkeypatch, plan, record={'owner_answer': long_answer},
                 log=['', '### Review log — closing (2026-09-26, test)', '', f'  {_owner_line(long_answer)}  '])
    assert probe.check_review(probe.PROTOCOL.read_text(), args.expect_protocol_sha256, args.expect_harness_sha256,
                              args.expect_plan_hash, root=tmp_path)['owner_answer']['verbatim'] == WRAPPED_QUOTE
    # The round-1 reviewer's record (three hashes and the cap only) no longer passes.
    bare = {key: ... for key in ('phase', 'status', 'approved_by', 'owner_answer')}
    args = _gate(tmp_path, monkeypatch, plan, record=bare)
    with pytest.raises(probe.PlanningError):
        probe.check_review(probe.PROTOCOL.read_text(), args.expect_protocol_sha256, args.expect_harness_sha256,
                           args.expect_plan_hash, root=tmp_path)


REAL_PROTOCOL = ROOT / 'docs/part2/PHASE29_EXPERIMENT.md'


def test_the_cancelled_phase_protocol_still_refuses_launch_review(tmp_path):
    """Cancellation did not approve the draft. The actual saved protocol still fails the
    review gate that run_live checks before reading credentials or creating a paid-run claim."""
    real = REAL_PROTOCOL.read_text()
    assert '\n## Cancellation (2026-09-25;' in real
    assert '**Phase 29 is cancelled before any paid call.**' in real
    assert probe.REVIEW_PENDING_MARKER.lower() in probe.status_block(real).lower()
    with pytest.raises(probe.PlanningError, match='NOT yet reviewed'):
        probe.check_review(real, probe.sha256_file(REAL_PROTOCOL), probe.sha256_file(probe.__file__),
                           'unused-plan-pin-review-status-refuses-first', root=tmp_path)


def test_the_owners_answer_gate_on_the_historical_review_protocol_text(tmp_path, monkeypatch):
    """Review round 2 (the round-2 reviewer's $0 launch rehearsal, as a test): on the REAL protocol text, whose
    status block quotes the program-level approval, round 1's substring test passed a record that reused that phrase,
    or the one-letter answer "N", with no closing entry at all. Closed as the runbook says (review-pending phrase
    gone, bare Reviewed line), only the owner's own answer on the closing line passes.
    This is an in-memory rehearsal of the historical review, not approval to revive Phase 29:
    the later Cancellation section stays on disk and is checked separately above."""
    real = REAL_PROTOCOL.read_text()
    before_log, log_heading, log_and_later = real.partition('\n' + probe.REVIEW_LOG_HEADING + '\n')
    assert log_heading, 'the historical protocol must retain its Review log'
    review_log, _, _ = log_and_later.partition('\n## ')
    real = before_log + log_heading + review_log
    head, _, body = real.partition('\n## ')
    h2 = [line for line in ('## ' + body).splitlines() if line.startswith('## ')]
    assert h2[-1] == probe.REVIEW_LOG_HEADING, 'the Review log is the protocol\'s last section'
    plan, _ = _small_plan()
    harness, plan_hash = probe.sha256_file(probe.__file__), probe.plan_hash(plan)
    program_sentence = f'Built under the program, which the owner approved in direction: "{PROGRAM_PHRASE}".'

    def close(entry=None, keep_program_sentence=True, extra=''):
        # The real status block with the review-pending phrase gone and the program sentence kept (as a closer
        # might plausibly leave it), or a new status block that quotes nothing; the body is the real protocol's.
        status = (head.replace(probe.REVIEW_PENDING_MARKER, 'reviewed (test)') + '\n' + program_sentence
                  if keep_program_sentence else '# Phase 29 protocol (test)\n\n**Status: reviewed (test).**')
        status += '\n\n' + probe.REVIEWED_LINE.format(harness=harness, plan=plan_hash) + '\n'
        text = status + '\n## ' + body.rstrip('\n') + '\n' + extra
        if entry is not None:
            text += '\n### Review log — closing (test)\n\n' + entry + '\n'
        return text

    def gate(text, answer):
        _artifacts(tmp_path, monkeypatch)
        sha = hashlib.sha256(text.encode()).hexdigest()
        path = tmp_path / probe.REVIEW_RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'phase': 29, 'status': 'approved', 'approved_by': 'rehearsal', 'owner_answer': answer,
                                    'protocol_sha256': sha, 'harness_sha256': harness, 'plan_hash': plan_hash,
                                    'phase_cap': 15.0}))
        try:
            return probe.check_review(text, sha, harness, plan_hash, root=tmp_path)
        except probe.PlanningError as error:
            return str(error)
    assert PROGRAM_PHRASE in probe.status_block(close())
    assert probe.REVIEW_PENDING_MARKER.lower() not in probe.status_block(close()).lower()
    # A: the program-level phrase reused as the answer, no closing entry (round 1: passed).
    assert 'status block' in gate(close(), _owner_answer(verbatim=PROGRAM_PHRASE))
    # B: a one-letter answer, no closing entry (round 1: passed).
    assert 'shorter than 20' in gate(close(), _owner_answer(verbatim='N'))
    # The program-level phrase on a proper closing line: refused by the status block and, with the status block's
    # quote removed, by the program document.
    phrase = _owner_answer(verbatim=PROGRAM_PHRASE)
    assert 'status block' in gate(close(_owner_line(phrase)), phrase)
    assert 'program document' in gate(close(_owner_line(phrase), keep_program_sentence=False), phrase)
    # The owner's own words somewhere in the text, but no closing entry: refused by where they stand.
    said = f'\nThe owner said "{OWNER_QUOTE}" (2026-09-25).\n'
    assert 'no Review log closing entry' in gate(close(extra=said), _owner_answer())
    # D: a proper answer wrapped across two Markdown lines (round 1: refused with a misleading message).
    wrapped = _owner_answer(verbatim=WRAPPED_QUOTE)
    line = _owner_line(wrapped)
    assert 'never wrapped' in gate(close(line[:120] + '\n' + line[120:]), wrapped)
    # C: a proper close passes every check of the review gate.
    assert gate(close(_owner_line()), _owner_answer())['owner_answer'] == _owner_answer()
    assert gate(close(line), wrapped)['owner_answer']['verbatim'] == WRAPPED_QUOTE


def test_the_run_cap_is_what_the_phase_cap_leaves_after_earlier_undelivered_runs(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    plan['counts']['total_requests'] = 234
    args = _gate(tmp_path, monkeypatch, plan)
    _manifest(tmp_path / 'artifacts', 'phase29-2026-09-25/live-0', charged_upper_bound=4.0)
    assert '234 planned requests exceed the $11.00 cap' in _refused_before_credentials(
        tmp_path, monkeypatch, args, plan, prompts)


def test_an_earlier_run_without_a_readable_charge_blocks(tmp_path, monkeypatch):
    """Review round 1 (mutant S5): an earlier run whose charged_upper_bound cannot be read is never charged at $0."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    for value in (..., None, 'x', -1.0, float('nan')):
        path = _manifest(artifacts, 'phase29-2026-09-25/live')
        body = json.loads(path.read_text())
        if value is ...:
            body.pop('charged_upper_bound')
        else:
            body['charged_upper_bound'] = value
        path.write_text(json.dumps(body))          # NaN is written as the JSON token NaN, which json reads back
        with pytest.raises(probe.PlanningError, match='charged_upper_bound'):
            probe.check_output('artifacts/phase29-2026-09-25/live-2')


def test_an_earlier_run_whose_delivered_count_is_unknown_blocks(tmp_path, monkeypatch):
    """Review round 1 (mutant R3): generations_delivered None (as --finalize-abandoned writes for an unreadable prior
    manifest) is never read as 'delivered nothing'; a second run would be repeat-until-lucky."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase29-2026-09-25/live', generations_delivered=None, statuses={})
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase29-2026-09-25/live-2')


@needs_store
def test_the_spend_guard_during_a_run_uses_the_phase_remainder(tmp_path, monkeypatch, dry_settings):
    """Review round 1 (mutant S1): after an earlier undelivered run charged $14.65, $0.35 is left, which is 7
    attempts at the bound; two requests that time out twice need 8, so the run stops at 7 with spend_guard, and the
    phase total stays within $15."""
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    _manifest(tmp_path / 'artifacts', 'phase29-2026-09-25/live-0', charged_upper_bound=14.65)
    FakeOpenAI.script, FakeOpenAI.calls = [TimeoutError(), TimeoutError(), TimeoutError(), TimeoutError()] + [NO_STEP] * 6, []
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['spend_cap'] == pytest.approx(0.35) and manifest['stop_reason'] == 'spend_guard'
    assert manifest['attempts'] == 7 and len(FakeOpenAI.calls) == 7
    assert manifest['charged_upper_bound'] + 14.65 <= probe.HARD_SPEND_CAP


@pytest.mark.parametrize('change,message', [
    ({'confirm_entity': 'someone-else'}, '--confirm-entity'),
    ({'settings': {'wandb_project': 'Other'}}, 'project'),
    ({'settings': {'wandb_mechanic_model': 'deepseek-ai/DeepSeek-V3.1'}}, 'configuration_hash'),
])
@needs_store
def test_the_live_run_refuses_a_wrong_entity_project_or_model_after_the_credential_read(
        tmp_path, monkeypatch, dry_settings, change, message):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    if 'confirm_entity' in change:
        args.confirm_entity = change['confirm_entity']
    settings = _fake_settings(dry_settings, **change.get('settings', {}))

    def live_settings(path, *, env_path):
        assert env_path is None, 'the live path reads credentials through the runtime loader only'
        return settings
    monkeypatch.setattr(probe, 'settings_from_file', live_settings)
    with pytest.raises(probe.PlanningError, match=message):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts/phase29-test').exists() and not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()


def _live(tmp_path, monkeypatch, dry_settings, factory=None):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    monkeypatch.setattr(probe, 'openai_client_factory', factory or FakeOpenAI)
    return plan, prompts, args


@needs_store
def test_a_live_run_end_to_end_on_the_real_provider_with_a_fake_client(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [NO_STEP, STEP, 'not json'], []
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 0
    assert [call['temperature'] for call in FakeOpenAI.calls] == [0, 0, 0.4, 0, 0, 0.4]
    directory = tmp_path / args.out
    manifest = json.loads((directory / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'COMPLETED' and manifest['generations_delivered'] == 6
    assert manifest['claim'] == f'artifacts/{probe.CLAIM_DIR}/claim-01.json' and manifest['traceback'] is None
    assert manifest['phase25_harness_sha256'] == probe.PHASE25_HARNESS_SHA256 and manifest['phase_spend_cap'] == 15.0
    assert manifest['review'] == {'status': 'approved', 'approved_by': 'the reviewer (test)', 'approved_at': None,
                                  'owner_answer': _owner_answer()}
    assert manifest['stop_signal'] is None and manifest['resend_pass']['ended'] == 'nothing_to_resend'
    assert 'fake-not-a-key' not in (directory / 'responses.jsonl').read_text()
    readouts = json.loads((directory / 'readouts.json').read_text())
    assert readouts['arms']['C']['duplicate'] == 1 and readouts['arms']['N']['working'] == 2
    assert readouts['arms']['NT']['invalid'] == 1 and readouts['provider']['served_model'] == {'served-by/another-model': 6}
    assert readouts['run_end']['round1_fallback_permitted'] is True
    assert probe.recompute_readouts(directory) == readouts
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase29-test/live-2')


@needs_store
def test_another_paid_run_seen_after_the_claim_ends_the_run_at_zero_cost(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    reads = []

    def rows():
        reads.append(1)
        return [] if len(reads) < 3 else [FOREIGN_RUN]
    monkeypatch.setattr(probe, 'process_list', rows)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    assert len(reads) == 3 and FakeOpenAI.calls == []
    directory = tmp_path / args.out
    manifest = json.loads((directory / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == probe.OTHER_RUN_AFTER_CLAIM
    assert manifest['attempts'] == 0 and manifest['charged_upper_bound'] == 0 and manifest['generations_delivered'] == 0
    assert manifest['blockers_after_claim'] == [f'pid 4242: {FOREIGN_RUN[2]}'] and not (directory / 'plan.json').exists()
    assert probe.check_output('artifacts/phase29-test/live-2')


@needs_store
def test_an_unexpected_exception_is_recorded_with_its_traceback(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [], []

    def broken(self, entry):
        raise RuntimeError('disk broke')
    monkeypatch.setattr(probe.Recorder, 'record', broken)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and 'disk broke' in manifest['traceback']
    assert 'fake-not-a-key' not in manifest['traceback']


@needs_store
def test_a_sigterm_during_a_request_stops_after_it_and_forfeits_the_fallback(tmp_path, monkeypatch, dry_settings):
    class Killer(FakeOpenAI):
        async def create(self, **kwargs):
            if not FakeOpenAI.calls:
                os.kill(os.getpid(), signal.SIGTERM)
            return await super().create(**kwargs)
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings, factory=Killer)
    FakeOpenAI.script, FakeOpenAI.calls = [NO_STEP] * 6, []
    before = signal.getsignal(signal.SIGTERM)
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE) == 1
    assert signal.getsignal(signal.SIGTERM) == before
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'operator_stop'
    assert manifest['requests_done'] == 1 and len(FakeOpenAI.calls) == 1
    assert manifest['stop_signal']['signal'] == 'SIGTERM'
    assert manifest['stop_signal']['in_flight_request'] == {'request_id': 'r0001', 'resend': False}
    readouts = json.loads((tmp_path / args.out / 'readouts.json').read_text())
    assert readouts['run_end']['round1_fallback_permitted'] is False


@needs_store
def test_a_stop_that_arrives_as_the_handlers_are_installed_refuses_before_the_claim(tmp_path, monkeypatch, dry_settings):
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    real = signal.signal

    def install_and_fire(sig, handler):
        previous = real(sig, handler)
        if sig == signal.SIGTERM and callable(handler):
            handler(sig, None)
        return previous
    monkeypatch.setattr(probe.signal, 'signal', install_and_fire)
    with pytest.raises(probe.PlanningError, match='before the claim'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists() and not (tmp_path / args.out).exists()


@needs_store
def test_an_output_directory_that_appears_during_the_launch_checks_refuses_before_the_claim(
        tmp_path, monkeypatch, dry_settings):
    """Review round 1 (mutant R5): the directory is created exclusively before the claim, so one that appeared after
    check_output refuses with nothing claimed or sent."""
    plan, prompts, args = _live(tmp_path, monkeypatch, dry_settings)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    real = probe.check_output

    def appearing(out, **kwargs):
        path = real(out, **kwargs)
        path.mkdir(parents=True)
        return path
    monkeypatch.setattr(probe, 'check_output', appearing)
    with pytest.raises(probe.PlanningError, match='appeared during the launch checks'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=IDLE)
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists() and FakeOpenAI.calls == []
    assert list((tmp_path / args.out).iterdir()) == []


def test_main_needs_every_live_flag_before_any_plan_is_built(capsys, monkeypatch):
    def no_plan(**_):
        raise AssertionError('no plan may be built')
    monkeypatch.setattr(probe, 'build_plan', no_plan)
    assert probe.main(['--execute-live', '--out', 'artifacts/phase29-x/live']) == 1
    assert '--execute-live needs' in capsys.readouterr().out


def test_main_checks_for_other_paid_runs_before_any_plan_is_built(tmp_path, capsys, monkeypatch):
    _artifacts(tmp_path, monkeypatch)

    def no_plan(**_):
        raise AssertionError('no plan may be built')
    monkeypatch.setattr(probe, 'build_plan', no_plan)
    monkeypatch.setattr(probe, 'other_paid_runs', lambda **_: (['phase30 run may be in progress (x)'], 'down'))
    assert probe.main(['--execute-live', '--out', 'artifacts/phase29-x/live', '--confirm-entity', 'e',
                       '--expect-plan-hash', 'p', '--expect-harness-sha256', 'h', '--expect-protocol-sha256', 'q']) == 1
    assert 'One paid run at a time' in capsys.readouterr().out


def test_main_writes_protocol_numbers_only_to_a_new_phase29_directory(tmp_path, capsys, monkeypatch):
    _artifacts(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, 'protocol_numbers', lambda: {'harness_minimum_is_the_chosen_one': {'all_rounds': True}})
    assert probe.main(['--protocol-numbers', 'artifacts/phase25-x/numbers']) == 1
    assert 'REJECTED' in capsys.readouterr().out
    assert probe.main(['--protocol-numbers', 'artifacts/phase29-x/numbers']) == 0
    assert (tmp_path / 'artifacts/phase29-x/numbers/protocol_numbers.out.json').exists()
    assert probe.main(['--protocol-numbers', 'artifacts/phase29-x/numbers']) == 1
