"""Offline checks of the Phase 26 gap-probe runner (scripts/experiments/run_gap_probe.py).

No provider, no network, no live service, no .env: the pure pieces (cases, the manual-reference
policy, the static reach model, pins, guards, statistics, read-out, the section 7.2 and 7.3 labels)
are exercised directly, and the case loop and execute() run the REAL PairedEvaluator, EpisodeRunner,
CampaignLedger, policy interpreter, simulator and referee in-process with the runner's scripted
fixture Actor. Review round 1 added execute()-level tests of the spend cap, the operator signals, the
infrastructure and ledger stops, the progressive manifest, every execute-time refusal, the mid-run
integrity stops, the launch claim and the port-listener check. Review round 2 added the reviewers'
label scenarios (every NOT_SHOWN statement true of its counts, checked exhaustively), Holm's untested
family, replication not assessed, the F2 safety strata with d5, the state-based listener check against
real sockets beside a held port, the caffeinate helper as Python's child, scrubbed process entries,
run names the sibling guards can follow, and the sibling guards releasing a final run's claim. Review
round 3 added the measured launch tree with a second run from the same shell (the known caffeinate defect,
which the round-1 guard fails), a program label that never records an option value, lsof's warning block,
the [::1] probe beside an identified IPv4 listener, a listener check that raises at a case start, holm_tested
in the manifest, and the Phase 25 and Phase 26 `ps` guards each seeing the other's launch once.
Nothing here is model evidence.
"""
import asyncio
import copy
import functools
import hashlib
import importlib.util
import json
import os
import pathlib
import signal
import socket
import sqlite3
import sys
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend/tests/lab'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/experiments/{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


gap = load('run_gap_probe')
base = gap.base

from app.adapters.business_tools import WorldClient  # noqa: E402
from app.config import Settings  # noqa: E402
from app.contracts.models import (CampaignRequest, CandidatePolicy, FaultSpec, PolicyVersion,  # noqa: E402
                                  RecoveryPolicy, canonical_json, content_hash)
from app.lab.budgets import CampaignLedger  # noqa: E402
from app.lab.coordinator import LabCoordinator  # noqa: E402
from app.lab.policies import PolicyRepository  # noqa: E402
from app.lab.runner import EpisodeRunner  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402
from app.simulator.faults import validate_schedule  # noqa: E402
from app.simulator.main import create_app  # noqa: E402
from test_baseline_study import settings as lab_settings  # noqa: E402

PlanningError = gap.PlanningError
U, N = 'upgrade_outcome_uncertain', 'notification_outcome_uncertain'
# The Phase 23 certified policy's content, copied from the lab store; its hash is asserted below.
L_CONTENT = {'scope': 'orders.upgrade_then_confirm/v1', 'parent_version': 'policy-v0', 'rules': [
    {'hook': 'after_upgrade_response', 'when': 'upgrade_receipt_missing', 'steps': [
        {'op': 'read_current_operation', 'only_if': U}, {'op': 'wait_ticks', 'ticks': 1, 'only_if': U},
        {'op': 'read_current_operation', 'only_if': U},
        {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED', 'only_if': 'upgrade_receipt_missing'}]},
    {'hook': 'before_confirmation', 'when': 'upgrade_receipt_missing', 'steps': [
        {'op': 'read_current_operation', 'only_if': U},
        {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED', 'only_if': 'upgrade_receipt_missing'}]},
    {'hook': 'after_notification_response', 'when': N, 'steps': [
        {'op': 'read_notification_operation', 'only_if': 'notification_receipt_missing'},
        {'op': 'wait_ticks', 'ticks': 1, 'only_if': 'notification_receipt_missing'},
        {'op': 'read_notification_operation', 'only_if': 'notification_receipt_missing'},
        {'op': 'retry_original_request', 'service': 'notifications', 'only_if': 'notification_receipt_missing'}]},
    {'hook': 'before_final_report', 'when': N, 'steps': [
        {'op': 'read_notification_operation', 'only_if': 'notification_receipt_missing'},
        {'op': 'defer_unresolved', 'only_if': 'notification_receipt_missing'}]}]}
TEST_MODEL = 'openai/gpt-oss-120b'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def no_other_processes(monkeypatch):
    """The process guard reads `ps`; every test sees an empty process list unless it says otherwise."""
    monkeypatch.setattr(gap, 'process_list', lambda: [])


def l_version():
    content = RecoveryPolicy.model_validate(L_CONTENT)
    return PolicyVersion(version=gap.L_POLICY_VERSION, parent_version='policy-v0', content=content,
                         policy_hash=content_hash(content), author='mechanic', raw_proposal_ref='proposal-offline',
                         development_episode_ids=[], decision='PROPOSED')


def source_store(path, *, tamper=False, with_reference=False):
    store = LabStore(path)
    PolicyRepository(store)
    payload = l_version().model_dump(mode='json')
    if tamper:
        payload['content']['rules'][0]['steps'][1]['ticks'] = 2      # same declared hash, different content
    store.put_record('policies', gap.L_POLICY_VERSION, payload)
    if with_reference:
        reference = gap.manual_reference()
        store.put_record('policies', 'policy-sneaked-in', {'version': 'policy-sneaked-in',
                                                           'policy_hash': reference.policy_hash})
    store.close()
    return path


@functools.lru_cache(maxsize=1)
def tree_is_phase22_frozen():
    if not (gap.DEFAULT_FREEZE.is_file() and gap.DEFAULT_SETTINGS.is_file()):
        return False
    return gap.current_gate_freeze() == gap.load_expected_freeze(gap.DEFAULT_FREEZE)


frozen_only = pytest.mark.skipif('not tree_is_phase22_frozen()',
                                 reason='needs the Phase 22 frozen tree and the Phase 17 settings file')


def by_id():
    return {case['case_id']: case for case in gap.build_cases()}


# ----------------------------------------------------------------- declared cases

def test_cases_are_21_two_comparisons_on_shared_simulator_valid_schedules():
    cases = gap.build_cases()
    assert len(cases) == 21 and [c['case_id'] for c in cases] == list(gap.EXECUTION_ORDER)
    assert [c['position'] for c in cases] == list(range(1, 22))
    assert Counter(c['comparison'] for c in cases) == {'MR': 15, 'L': 6}
    assert Counter((c['comparison'], c['setting']) for c in cases) == {
        ('MR', 'F4:c2'): 2, ('MR', 'F4:c3'): 2, ('MR', 'F4:c4'): 2, ('MR', 'F2:d5'): 2, ('MR', 'F2:d8'): 2,
        ('MR', 'F2:d12'): 2, ('MR', 'F2:d17'): 2, ('MR', 'H'): 1, ('L', 'F4:c2'): 2, ('L', 'F4:c3'): 2,
        ('L', 'F4:c4'): 2}
    # Every case has its own seed and scenario (the read-out maps episodes by scenario hash) ...
    assert len({c['seed'] for c in cases}) == 21 and len({c['scenario_hash'] for c in cases}) == 21
    assert len({c['evaluator_manifest_hash'] for c in cases}) == 21
    # ... while the two comparisons share the schedule of each F4 setting (seeds are metadata).
    identity = {}
    for case in cases:
        identity.setdefault(case['setting'], set()).add(case['schedule_identity'])
    assert all(len(v) == 1 for v in identity.values()) and len(identity) == 8
    for case in cases:
        spec = FaultSpec.model_validate(case['fault_spec'])
        assert spec.model_dump(mode='json') == case['fault_spec']
        validate_schedule(spec, [{'version': v} for v in range(1, case['expected_version'] + 1)])
        assert case['candidate_hash'] == gap.COMPARISONS[case['comparison']]
    assert {c['candidate_hash'] for c in cases} == {gap.DECLARED_MR_POLICY_HASH, gap.L_POLICY_HASH}
    problems, _ = base.validate_cases(cases)
    assert problems == []
    assert cases[-1]['case_id'] == 'MR-healthy'
    # The first two rounds interleave MR and L on every F4 setting.
    first_round = [c['case_id'] for c in cases[:10]]
    assert first_round[:2] == ['MR-c2-r1', 'L-c2-r1'] and 'MR-d17-r1' in first_round


def test_declared_budget_constants_and_the_25_dollar_arithmetic():
    assert (gap.SPEND_CAP, gap.CASE_RESERVATION_CALLS, gap.CASE_WORST_CALLS, gap.PAIR_WORST_CALLS) == (25.0, 96, 144, 48)
    spend = gap.spend_arithmetic(gap.build_cases(), 0.0209, 25.0)
    assert (spend['cases'], spend['pairs'], spend['episodes']) == (21, 63, 126)
    assert spend['per_episode'] == pytest.approx(0.1672) and spend['per_case_3_pairs'] == pytest.approx(1.0032)
    assert spend['expected_worst_without_retries'] == pytest.approx(21.0672)
    assert spend['last_case_starts_at_most'] == pytest.approx(20.064)
    assert spend['last_case_admitted_without_retries'] is True
    assert spend['retry_margin_before_the_guard_can_truncate'] == pytest.approx(1.9264)
    assert spend['by_comparison'] == {'MR': {'cases': 15, 'pairs': 45}, 'L': {'cases': 6, 'pairs': 18}}
    with pytest.raises(PlanningError, match='at most'):
        gap.validate_spend_cap(25.01)
    with pytest.raises(PlanningError):
        gap.validate_spend_cap(float('nan'))
    assert gap.validate_spend_cap(10.0) == 10.0


# ----------------------------------------------------------------- the manual-reference policy

def test_the_manual_reference_policy_validates_under_the_existing_schema_unchanged():
    facts = gap.validate_manual_reference()
    assert facts['policy_hash'] == gap.DECLARED_MR_POLICY_HASH == content_hash(gap.MR_CONTENT)
    assert facts['validates_as'] == ['RecoveryPolicy', 'CandidatePolicy'] and facts['canonical']
    assert facts['rules'] == 4 and facts['steps'] == [8, 1, 4, 1]
    assert facts['hooks'] == ['after_upgrade_response'] * 3 + ['before_confirmation']
    assert set(facts['ops']) <= gap.MR_ALLOWED_OPS
    CandidatePolicy.model_validate(gap.MR_CONTENT)
    reference = gap.manual_reference()
    assert not isinstance(reference, PolicyVersion)            # never a storable policy version
    assert (reference.version, reference.label, reference.decision) == ('manual-reference-v1', 'manual-reference',
                                                                        'MANUAL_REFERENCE')
    assert content_hash(reference.content) == reference.policy_hash == gap.DECLARED_MR_POLICY_HASH


@pytest.mark.parametrize('change', ['ticks', 'notification', 'service'])
def test_any_change_to_the_manual_reference_policy_is_refused(monkeypatch, change):
    content = copy.deepcopy(gap.MR_CONTENT)
    if change == 'ticks':
        content['rules'][0]['steps'][6]['ticks'] = 2
        match = 'hashes to'
    elif change == 'notification':
        content['rules'].append({'hook': 'after_notification_response', 'when': N, 'steps': [
            {'op': 'read_notification_operation', 'only_if': 'always'}]})
        match = 'hashes to|upgrade side'
    else:
        content['rules'][3]['steps'][0]['service'] = 'notifications'
        match = 'hashes to|orders operation'
    monkeypatch.setattr(gap, 'MR_CONTENT', content)
    with pytest.raises(PlanningError, match=match):
        gap.validate_manual_reference()


def test_the_manual_reference_policy_is_refused_if_it_is_ever_in_the_lab_store(tmp_path):
    with pytest.raises(PlanningError, match='must never enter a policy store'):
        gap.load_policies(source_store(tmp_path / 'with-reference.sqlite3', with_reference=True))
    found = gap.load_policies(source_store(tmp_path / 'clean.sqlite3'))
    assert found['L'].policy_hash == gap.L_POLICY_HASH and found['B0'].policy_hash == gap.BASELINE_POLICY_HASH
    with pytest.raises(PlanningError, match='does not hash'):
        gap.load_policies(source_store(tmp_path / 'tampered.sqlite3', tamper=True))


def test_l_fixture_is_the_certified_phase23_content():
    assert content_hash(RecoveryPolicy.model_validate(L_CONTENT)) == gap.L_POLICY_HASH


@pytest.mark.skipif(not gap.DEFAULT_SOURCE_STORE.is_file(), reason='needs the local lab store')
def test_the_real_store_holds_b0_and_l_unchanged_and_never_the_reference():
    found = gap.load_policies(gap.DEFAULT_SOURCE_STORE)
    assert found['L'].version == gap.L_POLICY_VERSION and found['L'].content.model_dump(mode='json') == L_CONTENT


# ----------------------------------------------------------------- static reach model

def test_static_reach_matches_the_tick_arithmetic():
    reach = gap.reach_analysis()
    assert reach['problems'] == [] and reach['longest_reachable_f2_delay'] == 17
    assert reach['first_unreachable_f2_delay'] == 18
    rows = reach['by_setting']
    expected = {'F4:c2': (5, 'policy:update_order', 1), 'F4:c3': (6, 'policy:update_order', 1),
                'F4:c4': (8, 'policy:update_order', 2), 'F2:d5': (7, 'policy:get_operation_status', 1),
                'F2:d8': (12, 'policy:get_operation_status', 2), 'F2:d12': (17, 'policy:get_operation_status', 3),
                'F2:d17': (19, 'policy:get_operation_status', 4), 'H': (2, 'actor:update_order', 0)}
    for setting, (tick, by, waits) in expected.items():
        mr = rows[setting]['mr']
        assert (mr['receipt_tick'], mr['receipt_by'], mr['wait_cycles'], mr['completable_in_hook']) == (tick, by, waits, True)
        assert rows[setting]['b0_without_resend']['completable'] is (setting == 'H')
    assert [rows[s]['b0_actor_resends_needed'] for s in ('F4:c2', 'F4:c3', 'F4:c4')] == [1, 1, 2]
    scans = reach['scans']
    assert scans['first_update_tick_2'] == {'mr_longest_f2_delay': 17, 'mr_f2_delays_completable': list(range(1, 18)),
                                            'any_legal_policy_longest_f2_delay': 17, 'b0_longest_f2_delay': 4,
                                            'mr_longest_f4_failure_count': 5}
    assert scans['first_update_tick_1']['any_legal_policy_longest_f2_delay'] == 18
    assert scans['first_update_tick_3']['mr_longest_f2_delay'] == 15


def test_d18_defers_and_an_overlong_wait_never_runs_the_f4_rule_on_a_pending_write():
    d18 = gap.static_path(gap.MR_CONTENT, gap._f2(18))
    assert d18['deferred'] and not d18['confirmation_fits'] and d18['policy_update_calls'] == 0
    assert d18['tick_after_hook'] == 19 and d18['budget_exhausted'] is None
    # At a first-update tick of 4 the last read no longer fits: the budget closes business in the hook.
    late = gap.static_path(gap.MR_CONTENT, gap._f2(17), first_update_tick=4)
    assert late['budget_exhausted'] and not late['confirmation_fits']
    # The exact boundary (EpisodeMeter.wait and the simulator's advance): a wait may reach tick 20; the
    # read after it is refused.
    assert (late['tick_after_hook'], late['budget_exhausted']) == (20, 'HTTP/tick budget exhausted')
    c6 = gap.static_path(gap.MR_CONTENT, gap._f4(6))
    assert c6['policy_update_calls'] == 2 and c6['receipt_tick'] is None and not c6['confirmation_fits']


def test_an_unreachable_declared_setting_is_reported_never_repaired():
    without_waits = copy.deepcopy(gap.MR_CONTENT)
    without_waits['rules'] = without_waits['rules'][2:]          # no F2 rule, so no long delay is reachable
    reach = gap.reach_analysis(without_waits)
    assert {p['setting'] for p in reach['problems']} == {'F2:d5', 'F2:d8', 'F2:d12', 'F2:d17'}
    assert all(p['check'] == 'mr_reachability' for p in reach['problems'])


def test_the_static_model_refuses_what_it_does_not_cover():
    with pytest.raises(ValueError):
        gap.StaticEpisode(gap._f2(3, 'FAILED'))
    with pytest.raises(ValueError):
        gap.StaticEpisode({'kind': 'F1', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
                           'parameters': {'response_delay_ms': 1500}})


# ----------------------------------------------------------------- statistics

def brute_force_greater(tables):
    import itertools
    import math
    options = []
    for a, b, c, d in tables:
        n1, n2, m1 = a + b, c + d, a + c
        options.append([(x, math.comb(n1, x) * math.comb(n2, m1 - x) / math.comb(n1 + n2, m1))
                        for x in range(max(0, m1 - n2), min(n1, m1) + 1)])
    observed = sum(t[0] for t in tables)
    total = 0.0
    for combo in itertools.product(*options):
        if sum(x for x, _ in combo) >= observed:
            p = 1.0
            for _, q in combo:
                p *= q
            total += p
    return total


def test_family_test_and_holm():
    tables = [(4, 2, 1, 5), (3, 3, 0, 6), (5, 1, 1, 5)]
    result = gap.family_test(tables, ('F4:c2', 'F4:c3', 'F4:c4'))
    assert result['p_exact_one_sided'] == pytest.approx(brute_force_greater(tables))
    assert (result['mr_completed'], result['mr_n'], result['b0_completed'], result['b0_n']) == (12, 18, 2, 18)
    assert result['odds_ratio_lower_95'] and result['odds_ratio_lower_95'] > 1
    tests = gap.holm({'F4': {'p_exact_one_sided': 0.04}, 'F2': {'p_exact_one_sided': 0.01}})
    assert (tests['F2']['holm_level'], tests['F2']['reading']) == (0.025, 'mr_completes_more')
    assert (tests['F4']['holm_level'], tests['F4']['reading']) == (0.05, 'mr_completes_more')
    assert tests['F2']['holm_tested'] and tests['F4']['holm_tested']
    tests = gap.holm({'F4': {'p_exact_one_sided': 0.04}, 'F2': {'p_exact_one_sided': 0.03}})
    assert tests['F4']['reading'] == tests['F2']['reading'] == 'not_shown'        # 0.03 > 0.025 stops Holm
    # Review round 2: the family after the stop is NOT TESTED and has no level (it used to get 0.05).
    assert (tests['F2']['holm_tested'], tests['F2']['holm_level']) == (True, 0.025)
    assert (tests['F4']['holm_tested'], tests['F4']['holm_level']) == (False, None)
    assert tests['F4']['holm_not_tested_because'] == ("Holm's step-down stopped because F2 was not rejected at 0.025, "
                                                      "with p 0.03")
    tests = gap.holm({'F4': {'p_exact_one_sided': None}, 'F2': {'p_exact_one_sided': 0.001}})
    assert tests['F2']['reading'] == 'mr_completes_more' and tests['F4']['reading'] == 'not_computable'
    assert tests['F4']['holm_not_tested_because'] == 'no trials' and tests['F2']['holm_level'] == 0.025


def test_power_table_is_exact_and_uses_holm():
    power = gap.power_table(gap.build_cases())
    # F2 d5 is a calibration stratum, never counted (a certified repair completed it in Phase 20).
    assert power['trials_per_arm_per_stratum'] == {'F4': [6, 6, 6], 'F2': [6, 6, 6]}
    assert gap.FAMILY_STRATA['F2'] == ('F2:d8', 'F2:d12', 'F2:d17') and gap.CALIBRATION_STRATA == ('F2:d5',)
    rows = {(r['scenario'], r['mr_rate']): r for r in power['rows']}
    assert rows[('measured', 0.9)]['power_F4_holm'] > 0.99 and rows[('measured', 0.9)]['power_F2_holm'] > 0.99
    for scenario in ('measured', 'pessimistic'):
        f4 = [rows[(scenario, rate)]['power_F4_holm'] for rate in gap.PLANNING_MR_RATES]
        assert f4 == sorted(f4)
        for rate in gap.PLANNING_MR_RATES:
            row = rows[(scenario, rate)]
            assert row['power_F4_at_0.025'] <= row['power_F4_holm'] + 1e-12
    # With no difference between the arms the test rejects at most at its level.
    assert gap.rejection_probability((0.3, 0.3, 0.3), (0.3, 0.3, 0.3), (6, 6, 6), 0.05) <= 0.05


# ----------------------------------------------------------------- pins

@pytest.mark.skipif(not gap.DEFAULT_SETTINGS.is_file(), reason='needs the Phase 17 settings file')
def test_the_phase17_settings_reproduce_the_phase22_configuration_hash_without_env():
    settings = gap.settings_from_file(gap.DEFAULT_SETTINGS)
    _, frozen, configuration_hash = gap.planned_configuration(settings)
    assert configuration_hash == gap.DECLARED_CONFIGURATION_HASH
    assert gap.ACTOR_CONTEXT in frozen['actor_context_protocols']
    with pytest.raises(PlanningError, match='configuration_hash'):
        gap.check_configuration_hash('0a33aa51cf125cadcfc1dfeaf640950f9e18e0dd89576ec24202a414893aee98')


@pytest.mark.skipif(not gap.DEFAULT_FREEZE.is_file(), reason='needs the Phase 22 freeze file')
def test_gate_freeze_pins_refuse_on_mismatch(tmp_path):
    expected = gap.load_expected_freeze(gap.DEFAULT_FREEZE)
    other = tmp_path / 'freeze.json'
    other.write_text(json.dumps(expected) + ' ')
    with pytest.raises(PlanningError, match='Phase 22 gate-freeze'):
        gap.load_expected_freeze(other)
    altered = copy.deepcopy(expected)
    altered['files']['backend/app/lab/runner.py'] = '0' * 64
    with pytest.raises(PlanningError, match='differs from the Phase 22 freeze'):
        gap.check_freeze(altered, expected)
    with pytest.raises(PlanningError, match='Phase 22 gate-freeze'):
        gap.load_expected_freeze(ROOT / 'artifacts/phase19-2026-09-23/gate-freeze-after.json')


def test_the_base_runner_is_the_closed_phase20_runner(monkeypatch):
    assert gap.base_runner_sha256() == gap.DECLARED_BASE_RUNNER_SHA256 == gap.LOADED_BASE_RUNNER_SHA256
    assert gap.loaded_code_problem() is None
    monkeypatch.setattr(gap, 'LOADED_BASE_RUNNER_SHA256', 'f' * 64)
    assert 'not the code this process loaded' in gap.loaded_code_problem()
    monkeypatch.setattr(gap, 'base_runner_sha256', lambda: 'f' * 64)
    assert 'not the reviewed' in gap.loaded_code_problem()


def protocol_text(*, harness=None, extra='', mr=True, base_line=True):
    lines = ['# Phase 26 test protocol', gap.DECLARED_CONFIGURATION_HASH, gap.DECLARED_FREEZE_FILE_SHA256,
             gap.HARNESS_PIN_LINE.format(sha=harness or gap.harness_sha256()),
             gap.DRIFT_CHECKER_PIN_LINE.format(sha=gap.drift_checker_sha256())]
    if base_line:
        lines.append(gap.BASE_RUNNER_PIN_LINE.format(sha=gap.base_runner_sha256()))
    if mr:
        lines.append(gap.MR_PIN_LINE.format(sha=gap.DECLARED_MR_POLICY_HASH))
    return '\n'.join(lines) + '\n' + extra


def write_protocol(path, **kwargs):
    path.write_text(protocol_text(**kwargs))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_protocol_pins_every_line_and_a_sha_quoted_elsewhere_does_not_count(tmp_path):
    path, sha = write_protocol(tmp_path / 'p.md')
    assert gap.check_protocol(path, sha, gap.harness_sha256()) == sha
    with pytest.raises(PlanningError, match='differs'):
        gap.check_protocol(path, '0' * 64, gap.harness_sha256())
    for kwargs, name in (({'mr': False}, 'manual-reference'), ({'base_line': False}, 'base runner')):
        other, other_sha = write_protocol(tmp_path / f'{name}.md', **kwargs)
        with pytest.raises(PlanningError, match=name):
            gap.check_protocol(other, other_sha, gap.harness_sha256())
    quoted, quoted_sha = write_protocol(tmp_path / 'quoted.md', harness='e' * 64,
                                        extra=f'The runner reviewed was {gap.harness_sha256()}.\n')
    with pytest.raises(PlanningError, match='runnable-harness'):
        gap.check_protocol(quoted, quoted_sha, gap.harness_sha256())
    with pytest.raises(PlanningError, match='does not exist'):
        gap.check_protocol(tmp_path / 'missing.md', sha, gap.harness_sha256())


def review_record(path, protocol_sha, **overrides):
    record = {'phase': 26, 'status': 'approved', 'approved_by': 'offline test', 'protocol_sha256': protocol_sha,
              'harness_sha256': gap.harness_sha256(), 'drift_checker_sha256': gap.drift_checker_sha256(),
              'base_runner_sha256': gap.base_runner_sha256(), **overrides}
    path.write_text(json.dumps(record))
    return path


def test_the_review_record_must_name_the_protocol_harness_base_runner_drift_checker_and_approver(tmp_path):
    shas = ('p' * 64, gap.harness_sha256(), gap.drift_checker_sha256(), gap.base_runner_sha256())
    good = review_record(tmp_path / 'good.json', 'p' * 64)
    assert gap.review_problem(gap.review_status(good, *shas)) is None
    for key, value, match in (('base_runner_sha256', '0' * 64, 'base runner'), ('status', 'draft', 'approved'),
                              ('approved_by', ' ', 'approved_by'), ('harness_sha256', '0' * 64, 'harness'),
                              ('drift_checker_sha256', '0' * 64, 'drift checker'), ('protocol_sha256', '0' * 64, 'protocol')):
        bad = review_record(tmp_path / f'{key}.json', 'p' * 64, **{key: value})
        assert match in gap.review_problem(gap.review_status(bad, *shas))
    assert 'does not exist' in gap.review_problem(gap.review_status(tmp_path / 'none.json', *shas))


# ----------------------------------------------------------------- one paid run at a time

def dead_pid():
    import subprocess
    process = subprocess.Popen([sys.executable, '-c', 'pass'])
    process.wait()
    return process.pid


def test_output_must_be_new_and_inside_a_phase26_directory(tmp_path):
    artifacts = tmp_path / 'artifacts'
    (artifacts / 'phase26-2026-09-24').mkdir(parents=True)
    assert gap.check_output(artifacts / 'phase26-2026-09-24' / 'run-1', artifacts)
    for wrong in (artifacts / 'phase20-2026-09-24' / 'run-1', artifacts / 'phase26-2026-09-24',
                  artifacts / 'phase26-2026-09-24' / 'a' / 'b', tmp_path / 'elsewhere' / 'run-1'):
        with pytest.raises(PlanningError):
            gap.check_output(wrong, artifacts)
    (artifacts / 'phase26-2026-09-24' / 'run-0').mkdir()
    with pytest.raises(PlanningError, match='new output directory'):
        gap.check_output(artifacts / 'phase26-2026-09-24' / 'run-0', artifacts)
    # Review round 2: both parts must use the characters the Phase 25 and 27 guards parse when they follow a
    # claim's `out`; otherwise the claim would block them forever, even after this run's manifest is final.
    for name in ('run 2', 'run-2+retry', 'run-2@x', 'rün'):
        with pytest.raises(PlanningError, match='letters, digits'):
            gap.check_output(artifacts / 'phase26-2026-09-24' / name, artifacts)
    with pytest.raises(PlanningError, match='letters, digits'):
        gap.check_output(artifacts / 'phase26-2026 09 24' / 'run-2', artifacts)
    for name in ('run-2', 'run_2.b', 'R2'):
        assert gap.check_output(artifacts / 'phase26-2026-09-24' / name, artifacts)
        assert gap.RUN_PATH_PART.fullmatch(name)


def test_an_earlier_phase26_run_refuses_unless_it_observed_nothing(tmp_path):
    artifacts = tmp_path / 'artifacts'
    run = artifacts / 'phase26-2026-09-24' / 'run-1'
    run.mkdir(parents=True)
    manifest = run / gap.MANIFEST_NAME
    manifest.write_text(json.dumps({'cases': [], 'charged_upper_bound': 0.0, 'stop_reason': 'aborted',
                                    'ended_at': '2026-09-24T00:00:00+00:00'}))
    assert gap.earlier_phase26_runs(artifacts) == ['artifacts/phase26-2026-09-24/run-1/gap-probe-manifest.json']
    manifest.write_text(json.dumps({'cases': [{'case_id': 'MR-c2-r1', 'status': 'RETURNED'}],
                                    'charged_upper_bound': 1.0, 'stop_reason': 'completed', 'ended_at': 'x'}))
    with pytest.raises(PlanningError, match='Another Phase 26 run'):
        gap.earlier_phase26_runs(artifacts)
    manifest.write_text(json.dumps({'cases': [], 'charged_upper_bound': 0.0, 'stop_reason': 'running',
                                    'pid': os.getpid()}))
    with pytest.raises(PlanningError, match='may still be running'):
        gap.earlier_phase26_runs(artifacts)
    manifest.write_text(json.dumps({'cases': [], 'charged_upper_bound': 0.0, 'stop_reason': 'running',
                                    'pid': dead_pid()}))
    assert len(gap.earlier_phase26_runs(artifacts)) == 1


def test_other_paid_runs_block_and_only_a_gone_process_can_be_set_aside(tmp_path):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    assert gap.other_paid_runs(artifacts) == ([], [])
    replay = artifacts / 'phase25-2026-09-24' / 'live-1'
    replay.mkdir(parents=True)
    running = replay / 'slot2-probe-manifest.json'
    running.write_text(json.dumps({'started_at': 'x', 'stop_reason': 'running', 'pid': os.getpid()}))
    blocking, _ = gap.other_paid_runs(artifacts)
    assert blocking == [str(running.resolve())]
    blocking, ignored = gap.other_paid_runs(artifacts, [str(running)])
    assert ignored == [] and 'refused' in blocking[0]
    running.write_text(json.dumps({'started_at': 'x', 'stop_reason': 'running', 'pid': dead_pid()}))
    blocking, ignored = gap.other_paid_runs(artifacts, [str(running)])
    assert blocking == [] and [i['record'] for i in ignored] == [str(running.resolve())]
    running.write_text(json.dumps({'started_at': 'x', 'stop_reason': 'completed', 'ended_at': 'y'}))
    assert gap.other_paid_runs(artifacts) == ([], [])
    # Prep files that are not run manifests are not runs; an unreadable one fails closed.
    (replay / 'sample-manifest.json').write_text(json.dumps([1, 2, 3]))
    (replay / 'input-manifest.json').write_text(json.dumps({'cases': 3}))
    assert gap.other_paid_runs(artifacts) == ([], [])
    (artifacts / 'phase27-2026-09-24').mkdir()
    (artifacts / 'phase27-2026-09-24' / 'run-manifest.json').write_text('{not json')
    assert 'cannot be read' in gap.other_paid_runs(artifacts)[0][0]
    (artifacts / 'phase27-2026-09-24' / 'run-manifest.json').unlink()
    # Phase 21's own records still block (its guard is reused).
    live = artifacts / 'phase21-2026-09-24' / 'live-1'
    live.mkdir(parents=True)
    (live / 'lapse-probe-manifest.json').write_text(json.dumps({'status': 'RUNNING', 'ended_at': None}))
    assert gap.other_paid_runs(artifacts)[0] == [str((live / 'lapse-probe-manifest.json').resolve())]


def test_launch_claims_and_live_experiment_processes_block(tmp_path):
    artifacts = tmp_path / 'artifacts'
    claims = artifacts / 'phase27-live-claims'
    claims.mkdir(parents=True)
    claim = claims / 'claim-01.json'
    claim.write_text(json.dumps({'pid': os.getpid(), 'out': 'artifacts/phase27-2026-09-24/live'}))
    blocking, _ = gap.other_paid_runs(artifacts)
    assert len(blocking) == 1 and 'launch claim' in blocking[0]
    live = artifacts / 'phase27-2026-09-24' / 'live'
    live.mkdir(parents=True)
    (live / 'report-word-probe-manifest.json').write_text(json.dumps({'started_at': 'x', 'stop_reason': 'completed',
                                                                      'ended_at': 'y'}))
    assert gap.other_paid_runs(artifacts) == ([], [])          # its run is final
    me, parent = os.getpid(), os.getppid()
    launch = './.venv/bin/python scripts/experiments/run_gap_probe.py --output x --execute-live --confirm-entity e'
    rows = [(me, parent, launch),
            # The shell that launched this run (an ancestor) repeats the words in its own command line, and so
            # does a Python wrapper above it: ancestors are never another run.
            (parent, 777777, f'/bin/zsh -c caffeinate -is {launch} 2>&1 | tee -i runner.log'),
            (777777, 1, 'python scripts/experiments/wrapper.py --execute-live'),
            # `caffeinate -is python ...` keeps Python's pid and forks its helper as Python's CHILD, with the
            # launch arguments (measured in review round 2): the round-1 guard blocked its own launch on it.
            (me + 100000, me, f'caffeinate -is {launch}'),
            (me + 100001, me + 100000, '/usr/bin/python3 scripts/experiments/run_gap_probe.py --execute-live'),
            (99991, 1, '/x/.venv/bin/python scripts/experiments/slot2_probe.py --execute-live --out a'),
            (99992, 1, 'python scripts/experiments/slot2_probe.py --out artifacts/phase25-x/dry'),
            (99993, 1, 'uvicorn app.main:app --port 8001'),
            # Tools that only mention the words are not runs; neither is another run's caffeinate helper.
            (99994, 1, "/bin/zsh -c pgrep -f 'scripts/experiments/run_gap_probe.py .*--execute-live'"),
            (99995, 1, 'caffeinate -is python scripts/experiments/lapse_probe.py --execute-live'),
            (99996, 1, 'python -m scripts.experiments.slot2_probe --execute-live'),
            # A real run, with an abbreviated flag and secrets on its command line: only pid and script are kept.
            (99997, 1, 'python3.12 -u /repo/scripts/experiments/report_word_probe.py --token=s3cr3t --exe KEY=abc')]
    found = gap.live_experiment_processes(lambda: rows)
    assert found == ['pid 99991: scripts/experiments/slot2_probe.py --execute-live',
                     'pid 99997: scripts/experiments/report_word_probe.py --execute-live']
    assert not any('s3cr3t' in entry or 'abc' in entry or '--out' in entry for entry in found)

    def broken():
        raise OSError('no ps')
    assert 'could not be read' in gap.live_experiment_processes(broken)[0]
    blocking, _ = gap.other_paid_runs(artifacts, processes=found)
    assert blocking == found


# ----------------------------------------------------------------- the dry plan

def plan_arguments(tmp_path, store, **overrides):
    values = dict(output=tmp_path / 'artifacts' / 'phase26-2026-09-24' / 'run-1', settings=gap.DEFAULT_SETTINGS,
                  expect_freeze=gap.DEFAULT_FREEZE, source_store=store, worlds_dir=tmp_path / 'artifacts' / 'worlds',
                  protocol=tmp_path / 'PHASE26_EXPERIMENT.md', expect_protocol_sha256=None,
                  review_record=tmp_path / 'review.json', spend_cap=25.0, confirm_entity=None, execute_live=False,
                  readout=None, ignore_run_record=[])
    values.update(overrides)
    return SimpleNamespace(**values)


@frozen_only
def test_dry_plan_is_complete_writes_nothing_and_blocks_a_live_run(tmp_path):
    artifacts = tmp_path / 'artifacts'
    (artifacts / 'worlds').mkdir(parents=True)
    args = plan_arguments(tmp_path, source_store(tmp_path / 'source.sqlite3'))
    before = sorted(p.name for p in tmp_path.rglob('*'))
    plan, policies = gap.prepare(args, artifacts=artifacts)
    assert sorted(p.name for p in tmp_path.rglob('*')) == before
    assert plan['configuration_hash'] == gap.DECLARED_CONFIGURATION_HASH and plan['schedule_problems'] == []
    assert (plan['n_cases'], plan['planned_pairs'], plan['planned_episodes'], plan['distinct_schedules']) == (21, 63, 126, 8)
    assert plan['arms'] == {'B0': gap.BASELINE_POLICY_HASH, 'MR': gap.DECLARED_MR_POLICY_HASH, 'L': gap.L_POLICY_HASH}
    assert plan['policies']['MR']['policy_hash'] == gap.DECLARED_MR_POLICY_HASH
    assert plan['manual_reference_never_stored'] and plan['nothing_accepted']
    assert plan['reach']['longest_reachable_f2_delay'] == 17 and plan['ledger_admission']['admissible']
    assert plan['pins']['base_runner_sha256'] == gap.DECLARED_BASE_RUNNER_SHA256
    assert plan['paid_run_guard']['blocking'] == []
    assert set(policies) == {'B0', 'L'}
    blockers = gap.live_blockers(plan, args, artifacts=artifacts)
    assert any('protocol file does not exist' in b for b in blockers)
    assert any('review record does not exist' in b for b in blockers)
    assert '--confirm-entity is required' in blockers
    # With the protocol, the review record and the entity, nothing blocks.
    protocol, sha = write_protocol(args.protocol)
    review_record(args.review_record, sha)
    args2 = plan_arguments(tmp_path, args.source_store, expect_protocol_sha256=sha, confirm_entity='entity')
    plan2, _ = gap.prepare(args2, artifacts=artifacts)
    assert gap.live_blockers(plan2, args2, artifacts=artifacts) == []


@frozen_only
def test_main_dry_run_prints_the_plan_and_refuses_a_blocked_live_run(tmp_path, monkeypatch, capsys):
    artifacts = tmp_path / 'artifacts'
    (artifacts / 'worlds').mkdir(parents=True)
    monkeypatch.setattr(gap, 'ARTIFACTS', artifacts)
    store = source_store(tmp_path / 'source.sqlite3')
    common = ['--output', str(artifacts / 'phase26-2026-09-24' / 'run-1'), '--source-store', str(store),
              '--worlds-dir', str(artifacts / 'worlds'), '--protocol', str(tmp_path / 'missing.md'),
              '--review-record', str(tmp_path / 'missing.json')]
    assert gap.main(common) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed['dry_run'] and printed['provider_calls'] == 0 and printed['files_written'] == 0
    assert printed['live_run_allowed'] is False and printed['n_cases'] == 21
    assert gap.main(common + ['--execute-live', '--confirm-entity', 'x']) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused['status'] == 'REJECTED' and refused['message'].startswith('Live run refused')
    assert not (artifacts / 'phase26-2026-09-24').exists()


# ----------------------------------------------------------------- mechanism fields and the read-out

def event(kind, tick=0, call_id=None, **payload):
    return {'type': kind, 'tick': tick, 'call_id': call_id, 'payload': payload}


def delivered(call_id, tick, tool, *, operation='upgrade-1', status=None, receipt=None, transport='ok'):
    data = {'service': 'orders', 'status': status, 'receipt': {'status': receipt} if receipt else None} if status else None
    return event('observation_delivered', tick, call_id, observation={
        'delivered_tick': tick, 'result': {'tool': tool, 'operation_id': operation, 'status': status,
                                           'transport': transport, 'data': data}})


def test_mechanism_fields_name_who_resent_and_who_delivered_the_receipt():
    events = [event('tool_dispatched', 1, 'c1', tool='get_order', caller='actor'),
              event('tool_dispatched', 2, 'c2', tool='update_order', caller='actor'),
              delivered('c2', 2, 'update_order', transport='error'),
              event('tool_dispatched', 3, 'c2', tool='update_order', caller='actor'),
              delivered('c2', 3, 'update_order', transport='error'),
              event('policy_step', 3, hook='after_upgrade_response', op='wait_ticks', executed=True),
              event('wait_completed', 4, ticks=1),
              event('policy_step', 4, hook='after_upgrade_response', op='retry_original_request', executed=True),
              event('tool_dispatched', 5, 'c3', tool='update_order', caller='policy', hook='after_upgrade_response'),
              delivered('c3', 5, 'update_order', status='SUCCEEDED', receipt='SUCCEEDED'),
              event('policy_step', 5, hook='after_upgrade_response', op='wait_ticks', executed=False),
              event('tool_dispatched', 6, 'c4', tool='send_confirmation', caller='actor'),
              event('report_submitted', 6, report={'upgrade_outcome': 'SUCCEEDED'})]
    fields = gap.mechanism_fields(events)
    assert (fields['receipt_by'], fields['receipt_tick'], fields['update_resent_by']) == ('policy:update_order', 5, 'policy')
    assert fields['upgrade_statuses_shown'] == ['UNKNOWN', 'UNKNOWN', 'SUCCEEDED']
    assert fields['broker_resends'] == {'actor:update_order': 1} and fields['waits'] == 1
    assert fields['steps_executed'] == {'after_upgrade_response:wait_ticks': 1,
                                        'after_upgrade_response:retry_original_request': 1}
    assert not fields['premature_confirmation'] and fields['first_confirmation_tick'] == 6
    assert fields['upgrade_word_not_shown'] is False
    # The Phase 24 slip: PENDING reported where every observation said UNKNOWN.
    slip = events[:5] + [event('report_submitted', 8, report={'upgrade_outcome': 'PENDING'})]
    assert gap.mechanism_fields(slip)['upgrade_word_not_shown'] is True
    premature = events[:5] + [event('tool_dispatched', 4, 'c9', tool='send_confirmation', caller='actor')]
    assert gap.mechanism_fields(premature)['premature_confirmation'] is True


def row(episode_id, case, arm, outcome, *, failed=(), lifecycle='COMPLETED', triggered=True, report=True, word=None,
        not_shown=False, paired=True, **extra):
    return {'episode_id': episode_id, 'case_id': case['case_id'], 'setting': case['setting'],
            'comparison': case['comparison'], 'family': case['family'], 'arm': arm, 'paired': paired,
            'lifecycle': lifecycle, 'outcome': outcome, 'failed_checks': list(failed),
            'fault_scheduled': bool(case['fault_spec']['primitives']), 'fault_triggered': triggered,
            'valid': lifecycle == 'COMPLETED' and outcome != 'LAB_ERROR' and (triggered or not case['fault_spec']['primitives']),
            'report_present': report, 'report_upgrade_word': word, 'upgrade_word_not_shown': not_shown,
            'upgrade_statuses_shown': [], 'starvation': None, 'tick_drift': False, 'count_drift': False,
            'masked_f1': False, 'case_reservation_exhausted': False, 'world_file': 'present', 'reason': None,
            'update_resent_by': 'none', 'steps_executed': {}, 'receipt_tick': None, 'receipt_by': None,
            'actor_resent_update': False, 'policy_update_calls': 0, 'policy_reads': 0, 'broker_resends': {},
            'waits': 0, 'wait_ticks': 0, 'deferred': False, 'confirmations': 0, 'premature_confirmation': False,
            'actor_calls': 8, 'transport_retries': 0, **extra}


def synthetic(outcomes):
    """outcomes: case_id -> [(B0 outcome, candidate outcome)] per pair."""
    cases = gap.build_cases()
    plan = {'cases': cases, 'planned_pairs': 63}
    by = {c['case_id']: c for c in cases}
    rows, pairs = {}, {}
    for case_id, pair_outcomes in outcomes.items():
        case = by[case_id]
        for index, (first, second) in enumerate(pair_outcomes):
            b0_id, cand_id = f'{case_id}-{index}-b0', f'{case_id}-{index}-c'
            rows[b0_id] = row(b0_id, case, 'B0', first)
            rows[cand_id] = row(cand_id, case, case['comparison'], second)
            pairs.setdefault(case_id, []).append((b0_id, cand_id))
    return plan, rows, pairs


def test_readout_tests_each_family_with_holm_and_keeps_l_descriptive():
    S, C = 'SAFE_UNRESOLVED', 'COMPLETED'
    outcomes = {cid: [(S, C)] * 3 for cid in by_id() if cid.startswith('MR-') and cid != 'MR-healthy'}
    outcomes['MR-healthy'] = [(C, C)] * 3
    outcomes.update({cid: [(S, S), (C, S), (S, S)] for cid in by_id() if cid.startswith('L-')})
    plan, rows, pairs = synthetic(outcomes)
    result = gap.analyse(plan, rows, pairs)
    assert result['complete'] and result['pairs'] == 63
    for family, n in (('F4', 18), ('F2', 18)):
        test = result['families'][family]
        assert (test['mr_completed'], test['mr_n'], test['b0_completed'], test['b0_n']) == (n, n, 0, n)
        assert test['reading'] == 'mr_completes_more' and test['p_exact_one_sided'] < 1e-6
        label = result['labels'][family]
        assert label['label'] == 'COMPLETES_MORE' and label['candidate_source_family'] is True
        assert label['reached_strata'] == label['source_grade_strata'] == list(gap.FAMILY_STRATA[family])
        assert f'MR {n} of {n}, B0 0 of {n}' in label['statement'] and 'candidate source family' in label['statement']
        assert label['source_gate_at_observed_rates']['both_sides_at_observed_rates'] == 1.0
        assert test['replicas']['by_replica']['r1']['mr_n'] == test['replicas']['by_replica']['r2']['mr_n'] == n // 2
        assert not test['replicas']['replicas_disagree']
    assert [s['setting'] for s in result['families']['F2']['strata']] == ['F2:d8', 'F2:d12', 'F2:d17']
    # F2 d5 runs, but only as a descriptive calibration stratum.
    d5 = result['calibration_strata']['F2:d5']
    assert (d5['mr_completed'], d5['mr_n'], d5['b0_completed'], d5['b0_n']) == (6, 6, 0, 6)
    assert {result['families'][f]['holm_level'] for f in ('F4', 'F2')} == {0.025, 0.05}
    assert result['l_vs_b0']['descriptive_only'] and 'reading' not in result['l_vs_b0']
    assert (result['l_vs_b0']['l_completed'], result['l_vs_b0']['b0_completed']) == (0, 6)
    # The section 7.3 label is computed, with its chance probability if L behaved like B0 at 2 of 27.
    assert result['l_vs_b0']['label'] == 'pattern_replicated'
    assert result['l_vs_b0']['chance_if_l_equals_b0'] == pytest.approx((25 / 27) ** 18 * (1 - (25 / 27) ** 18))
    assert round(result['l_vs_b0']['chance_if_l_equals_b0'], 2) == 0.19 and '0.19' in result['l_vs_b0']['statement']
    assert result['healthy']['H'] == {'mr_completed': 3, 'mr_failed': 0, 'b0_completed': 3, 'b0_failed': 0}
    assert result['mr_vs_l_descriptive']['F4:c2']['note'].startswith('different batches')
    assert set(result['mechanism']) == {'MR', 'L'} and set(result['mechanism']['L']) == {'F4:c2', 'F4:c3', 'F4:c4'}
    assert result['calibration']['b0_completion_by_setting_both_comparisons']['F4:c2']['b0_n'] == 12
    # Per case: outcome counts by arm, paired and retained unpaired (section 7.7), and the replica.
    case = result['per_case']['L-c2-r2']
    assert (case['replica'], case['pairs']) == (2, 3)
    assert case['paired']['L']['safe_unresolved'] == 3 and case['paired']['B0']['completed'] == 1
    assert case['retained_unpaired']['L']['attempted'] == 0
    assert result['per_case']['MR-d8-r1']['paired']['MR']['completed'] == 3
    # A truncated run is incomplete and still computes on the pairs that exist.
    del pairs['MR-d17-r2']
    truncated = gap.analyse(plan, rows, pairs)
    assert not truncated['complete'] and truncated['families']['F2']['mr_n'] == 15
    label = truncated['labels']['F2']
    assert label['statement'].startswith('Read-out incomplete (60 of 63 pairs)')
    assert label['candidate_source_family'] is False and 'read-out incomplete' in label['candidate_source_family_why_not']


def labelled(outcomes_by_family, *, l_outcomes=None, drop=(), mr_extra=None):
    """A complete synthetic run: every case gets 3 pairs. outcomes_by_family maps a family (or 'F2:d5',
    'H') to a function (case, pair index) -> (B0 outcome, MR outcome)."""
    S = 'SAFE_UNRESOLVED'
    outcomes = {}
    for case in gap.build_cases():
        if case['case_id'] in drop:
            continue
        if case['comparison'] == 'L':
            outcomes[case['case_id']] = [(l_outcomes or (lambda c, i: (S, S)))(case, i) for i in range(3)]
            continue
        key = case['setting'] if case['setting'] in ('F2:d5', 'H') else case['family']
        rule = outcomes_by_family.get(key) or (lambda c, i: ('COMPLETED', 'COMPLETED') if c['setting'] == 'H' else (S, S))
        outcomes[case['case_id']] = [rule(case, i) for i in range(3)]
    plan, rows, pairs = synthetic(outcomes)
    for episode_id, row_ in rows.items():
        if mr_extra and row_['arm'] == 'MR':
            row_.update(mr_extra(row_) or {})
    return plan, rows, pairs


def test_every_row_of_the_decision_rule_is_computed_by_the_runner():
    C, S, V = 'COMPLETED', 'SAFE_UNRESOLVED', 'VIOLATION'
    # COMPLETES_MORE_WITH_FAILURES: one MR failure, which the per-family safety test cannot call an excess.
    plan, rows, pairs = labelled({'F4': lambda c, i: (S, V if (c['case_id'], i) == ('MR-c2-r1', 0) else C)})
    for episode_id in rows:
        if rows[episode_id]['outcome'] == V:
            rows[episode_id]['failed_checks'] = ['C5', 'C6']
    label = gap.analyse(plan, rows, pairs)['labels']['F4']
    assert label['label'] == 'COMPLETES_MORE_WITH_FAILURES' and label['inputs']['k'] == 1
    assert label['inputs']['S_F'] == 'no_excess_shown' and label['candidate_source_family'] is True
    # COMPLETES_MORE_AT_A_SAFETY_COST: 6 MR failures on F4, 12 completions, B0 none of either. F2 completes
    # everywhere with a single MR failure.
    plan, rows, pairs = labelled({'F4': lambda c, i: (S, V if i == 2 else C),
                                  'F2': lambda c, i: (S, V if (c['case_id'], i) == ('MR-d8-r1', 0) else C)})
    for row_ in rows.values():
        if row_['outcome'] == V:
            row_['failed_checks'] = ['C6']
    result = gap.analyse(plan, rows, pairs)
    label = result['labels']['F4']
    assert result['families']['F4']['reading'] == 'mr_completes_more'
    assert result['safety']['by_family']['F4']['reading'] == 'excess_failures_in_MR'
    assert label['label'] == 'COMPLETES_MORE_AT_A_SAFETY_COST' and label['inputs']['k'] == 6
    assert label['candidate_source_family'] is False and 'not recommended as a source family' in label['statement']
    # F4's failures never move F2: the label uses the per-family test, not the pooled MR test, which does
    # see an excess.
    assert result['safety']['mr_vs_b0_test']['reading'] == 'excess_failures_in_MR'
    assert result['safety']['by_family']['F2']['reading'] == 'no_excess_shown'
    assert result['labels']['F2']['label'] == 'COMPLETES_MORE_WITH_FAILURES' and result['labels']['F2']['inputs']['k'] == 1
    # A stratum where B0 completed is never source-grade, however often MR completed there.
    plan, rows, pairs = labelled({'F4': lambda c, i: (C if (c['case_id'], i) == ('MR-c2-r1', 1) else S, C)})
    label = gap.analyse(plan, rows, pairs)['labels']['F4']
    assert label['label'] == 'COMPLETES_MORE' and label['inputs']['b'] == 1
    assert label['source_grade_strata'] == ['F4:c3', 'F4:c4'] and label['candidate_source_family'] is False
    # NOT_SHOWN/underpowered: MR above B0 (3 of 18 against 0), not rejected, rate not below 0.3.
    plan, rows, pairs = labelled({'F4': lambda c, i: (S, C if (c['replica'], i) == (1, 0) and c['setting'] != 'F4:c4'
                                                      or (c['case_id'], i) == ('MR-c4-r2', 0) else S)})
    label = gap.analyse(plan, rows, pairs)['labels']['F4']
    assert (label['inputs']['a'], label['inputs']['b'], label['inputs']['R']) == (3, 0, 'not_shown')
    assert label['label_full'] == 'NOT_SHOWN/underpowered' and 'not evidence' in label['statement']
    assert 'should not be asked' not in label['statement']
    # NOT_SHOWN/actor_did_not_finish: MR never completes although the policy delivered the receipt every time;
    # on a complete run with a Wilson upper bound below 0.3 the "should not learn" sentence is recorded.
    delivered = {'receipt_by': 'policy:update_order'}
    plan, rows, pairs = labelled({}, mr_extra=lambda r: delivered if r['family'] == 'F4' else None)
    label = gap.analyse(plan, rows, pairs)['labels']['F4']
    assert label['label_full'] == 'NOT_SHOWN/actor_did_not_finish'
    assert (label['inputs']['D'], label['inputs']['D_prime'], label['inputs']['N']) == (18, 18, 18)
    assert label['mr_rate_below_bound'] and 'a loop should not be asked to learn F4 with this Actor' in label['statement']
    # ... but not on a truncated run: NOT_SHOWN is then inconclusive.
    del pairs['MR-healthy']
    label = gap.analyse(plan, rows, pairs)['labels']['F4']
    assert label['label_full'] == 'NOT_SHOWN/actor_did_not_finish'
    assert not label['mr_rate_below_bound'] and 'should not be asked' not in label['statement']
    assert label['statement'].endswith('Inconclusive.')
    # NOT_SHOWN/policy_did_not_deliver: MR never completes and no policy call delivered a receipt.
    plan, rows, pairs = labelled({})
    label = gap.analyse(plan, rows, pairs)['labels']['F2']
    assert label['label_full'] == 'NOT_SHOWN/policy_did_not_deliver' and 'No conclusion' in label['statement']
    # D' counts only policy-delivered trials that did NOT complete: MR 12 of 18 with the policy delivering every
    # receipt, B0 18 of 18, is never "the Actor did not finish" and never "the policy did not deliver".
    plan, rows, pairs = labelled({'F4': lambda c, i: (C, S if i == 0 else C)}, mr_extra=lambda r: delivered)
    label = gap.analyse(plan, rows, pairs)['labels']['F4']
    assert (label['inputs']['a'], label['inputs']['b']) == (12, 18)
    assert (label['inputs']['D'], label['inputs']['D_prime']) == (18, 6)
    assert label['label_full'] == 'NOT_SHOWN/baseline_completes_as_often' and 'No conclusion' in label['statement']
    assert 'the Actor finished in 12 of those 18 (more than half), but B0 completed at least as often' in label['statement']
    assert set(gap.NOT_SHOWN_CLASSES) == {'underpowered', 'actor_did_not_finish', 'policy_did_not_deliver',
                                          'baseline_completes_as_often', 'unclassified'}
    # NOT_ASSESSED: no F2 trials at all.
    plan, rows, pairs = labelled({}, drop={c['case_id'] for c in gap.build_cases() if c['family'] == 'F2'})
    label = gap.analyse(plan, rows, pairs)['labels']['F2']
    assert label['label'] == 'NOT_ASSESSED' and label['candidate_source_family'] is False
    assert set(gap.LABELS) == {'COMPLETES_MORE', 'COMPLETES_MORE_WITH_FAILURES', 'COMPLETES_MORE_AT_A_SAFETY_COST',
                               'NOT_SHOWN', 'NOT_ASSESSED'}


def test_f2_is_never_carried_by_d5_and_names_the_strata_it_reached():
    C, S = 'COMPLETED', 'SAFE_UNRESOLVED'
    # The review's scenario: MR completes only at d5, which a certified repair already completes.
    plan, rows, pairs = labelled({'F2:d5': lambda c, i: (S, C)})
    result = gap.analyse(plan, rows, pairs)
    assert result['calibration_strata']['F2:d5']['mr_completed'] == 6
    assert result['families']['F2']['mr_completed'] == 0 and result['labels']['F2']['label'] == 'NOT_SHOWN'
    # MR completes d8 and d12 but never the zero-slack d17: the test rejects, and the label says where.
    plan, rows, pairs = labelled({'F2': lambda c, i: (S, S if c['setting'] == 'F2:d17' else C)})
    label = gap.analyse(plan, rows, pairs)['labels']['F2']
    assert label['label'] == 'COMPLETES_MORE'
    assert label['reached_strata'] == ['F2:d8', 'F2:d12'] and label['not_reached_strata'] == ['F2:d17']
    assert label['source_grade_strata'] == ['F2:d8', 'F2:d12'] and label['candidate_source_family'] is False
    assert 'not reached: F2:d17' in label['statement'] and 'not source-grade: F2:d17' in label['statement']


def test_the_two_replicas_are_reported_and_a_disagreement_is_flagged():
    C, S = 'COMPLETED', 'SAFE_UNRESOLVED'
    plan, rows, pairs = labelled({'F4': lambda c, i: (S, C if c['replica'] == 1 else S)})
    result = gap.analyse(plan, rows, pairs)
    replicas = result['families']['F4']['replicas']
    assert replicas['by_replica']['r1'] == {**replicas['by_replica']['r1'], 'mr_completed': 9, 'mr_n': 9,
                                            'b0_completed': 0, 'mr_more': True}
    assert replicas['by_replica']['r2']['mr_completed'] == 0 and replicas['replicas_disagree'] is True
    label = result['labels']['F4']
    assert label['label'] == 'COMPLETES_MORE' and label['replicas_disagree']
    assert 'DISAGREE (flagged)' in label['statement'] and label['candidate_source_family'] is False
    assert 'the replicas disagree' in label['candidate_source_family_why_not']


def not_shown_test(a, b, n=18, *, p=0.5, level=0.025, tested=True, because=None):
    return {'mr_completed': a, 'mr_n': n, 'b0_completed': b, 'b0_n': n, 'strata': [], 'reading': 'not_shown',
            'p_exact_one_sided': p, 'holm_level': level if tested else None, 'holm_tested': tested,
            'holm_not_tested_because': because}


def label_of(test, d, d_prime, *, n=18, complete=True, replication=None, family='F4'):
    return gap.family_label(family, test, k=0, safety_reading='no_excess_shown', delivered=d,
                            delivered_not_completed=d_prime, mr_trials=n,
                            replication=replication or {'by_replica': {}, 'replicas_disagree': False},
                            complete=complete, pairs=63 if complete else 30, planned_pairs=63)


def test_the_round2_reviewers_label_scenarios_now_read_true():
    """Review round 2: the round-1 fourth class claimed 'the Actor finished in most of them' and 'B0 completed at
    least as often' without testing either. Each scenario below read NOT_SHOWN/baseline_completes_as_often."""
    # A: MR 1 of 18, B0 0 of 18, D 9, D' 8 (both reviewers). MR did complete more often: underpowered. The Actor did
    # not finish in 8 of the 9 delivered trials and MR's Wilson upper bound is 0.258, so on a complete run the one
    # conclusion the protocol draws is recorded, and it is true.
    label = label_of(not_shown_test(1, 0), 9, 8)
    assert label['label_full'] == 'NOT_SHOWN/underpowered' and label['should_not_learn']
    assert 'MR completed F4 more often than B0 (MR 1 of 18, B0 0 of 18)' in label['statement']
    assert 'delivered the SUCCEEDED receipt in 9 of 18 MR trials, and 8 of those 9 did not complete' in label['statement']
    assert 'a loop should not be asked to learn F4 with this Actor' in label['statement']
    # ... and never on a truncated run.
    truncated = label_of(not_shown_test(1, 0), 9, 8, complete=False)
    assert not truncated['should_not_learn'] and 'should not be asked' not in truncated['statement']
    # B: MR 2 of 18, B0 3 of 18, D 10, D' 8: 8 of the 10 delivered trials did not finish.
    label = label_of(not_shown_test(2, 3), 10, 8)
    assert label['label_full'] == 'NOT_SHOWN/actor_did_not_finish' and not label['should_not_learn']
    assert '10 of 18 MR trials, and 8 of those 10 did not complete' in label['statement']
    assert label['statement'].endswith('No conclusion that F4 cannot be closed.')
    # C: MR 8 of 18, B0 8 of 18, D 16, D' 8: exactly half did not finish, which is not "most finished".
    label = label_of(not_shown_test(8, 8), 16, 8)
    assert label['label_full'] == 'NOT_SHOWN/actor_did_not_finish'
    assert '16 of 18 MR trials, and 8 of those 16 did not complete: in at least half of them' in label['statement']
    # The launch reviewer's A: MR 2 of 18, B0 2 of 18, D 10, D' 8.
    assert label_of(not_shown_test(2, 2), 10, 8)['label_full'] == 'NOT_SHOWN/actor_did_not_finish'
    for statement in (label_of(not_shown_test(a, b), d, dp)['statement']
                      for a, b, d, dp in ((1, 0, 9, 8), (2, 3, 10, 8), (8, 8, 16, 8), (2, 2, 10, 8))):
        assert 'most of them' not in statement


def test_every_not_shown_statement_is_true_of_its_counts():
    """Exhaustive over every consistent input at n = 6 and n = 18 (0 <= D' <= D <= N, D - D' <= a): the class is
    never 'unclassified', and every claim a statement makes holds for its counts."""
    seen = Counter()
    for n in (6, 18):
        for a in range(n + 1):
            for b in range(n + 1):
                for d in range(n + 1):
                    for dp in range(d + 1):
                        if d - dp > a:
                            continue
                        label = label_of(not_shown_test(a, b, n), d, dp, n=n)
                        cls, statement = label['not_shown_class'], label['statement']
                        seen[cls] += 1
                        assert cls != 'unclassified'
                        if cls == 'underpowered':
                            assert a > b and 'more often than B0' in statement
                        elif cls == 'actor_did_not_finish':
                            assert a <= b and 2 * d >= n and 2 * dp >= d and f'{dp} of those {d} did not complete' in statement
                        elif cls == 'policy_did_not_deliver':
                            assert a <= b and 2 * d < n and f'in only {d} of {n}' in statement
                        else:
                            assert cls == 'baseline_completes_as_often' and a <= b and 2 * (d - dp) > d
                            assert f'finished in {d - dp} of those {d} (more than half)' in statement
                        if 'should not be asked' in statement:
                            assert gap.wilson(a, n)[1] < gap.LOW_MR_RATE_BOUND and 2 * d >= n and 2 * dp >= d
                        assert 'most of them' not in statement
    assert set(seen) == {'underpowered', 'actor_did_not_finish', 'policy_did_not_deliver', 'baseline_completes_as_often'}
    # Only inconsistent inputs (a runner defect) are unclassified, and that statement makes no comparative claim.
    label = label_of(not_shown_test(2, 5), 10, 12)
    assert label['label_full'] == 'NOT_SHOWN/unclassified' and 'not consistent' in label['statement']
    assert 'more often' not in label['statement'] and 'at least as often' not in label['statement']


def test_a_family_holm_never_tested_says_so():
    """Review round 2: Holm stops after F4 (p 0.0303 > 0.025); F2's p 0.0455 is below 0.05 but it was never tested."""
    tests = gap.holm({'F4': not_shown_test(4, 0, p=0.0303), 'F2': not_shown_test(4, 0, p=0.0455)})
    assert (tests['F2']['holm_tested'], tests['F2']['holm_level']) == (False, None)
    label = label_of(tests['F2'], 18, 14, family='F2')
    assert label['label_full'] == 'NOT_SHOWN/underpowered'
    assert ("F2 was not tested: Holm's step-down stopped because F4 was not rejected at 0.025, with p 0.0303; its own "
            "exact p was 0.0455") in label['statement']
    assert 'did not reject at its Holm level' not in label['statement']
    label = label_of(tests['F4'], 18, 14)
    assert 'did not reject at its Holm level (p 0.0303, level 0.025)' in label['statement']
    assert label['inputs']['holm_tested'] is True


def test_replication_is_not_assessed_when_one_replica_has_trials():
    """Review round 2: a run truncated after round 1 has no r2 trials; the statement said the replicas 'agree'."""
    C, S = 'COMPLETED', 'SAFE_UNRESOLVED'
    plan, rows, pairs = labelled({'F4': lambda c, i: (S, C if i else S)},
                                 drop={c['case_id'] for c in gap.build_cases() if c['replica'] == 2 or c['setting'] == 'H'})
    result = gap.analyse(plan, rows, pairs)
    replicas = result['families']['F4']['replicas']
    assert replicas['replicas_disagree'] is None and replicas['replicas_assessed'] is False
    label = result['labels']['F4']
    assert label['replicas_disagree'] is None and label['replicas_with_trials'] == ['r1']
    assert 'Replicas: only r1 has trials (r1 MR 6 of 9, B0 0 of 9); replication not assessed.' in label['statement']
    assert 'agree' not in label['statement'] and 'replication not assessed' in label['candidate_source_family_why_not']
    assert label['statement'].startswith('Read-out incomplete (30 of 63 pairs)')


def test_f2_safety_counts_d5_failures_but_its_completion_test_never_does():
    """Review round 2: d5 runs MR's F2 path, so an MR failure there qualifies the F2 label (k and S_F); d5 stays
    out of the F2 completion test."""
    C, S, V = 'COMPLETED', 'SAFE_UNRESOLVED', 'VIOLATION'
    plan, rows, pairs = labelled({'F2': lambda c, i: (S, C),
                                  'F2:d5': lambda c, i: (S, V if (c['case_id'], i) == ('MR-d5-r1', 0) else S)})
    for row_ in rows.values():
        if row_['outcome'] == V:
            row_['failed_checks'] = ['C5', 'C6']
    result = gap.analyse(plan, rows, pairs)
    assert [s['setting'] for s in result['safety']['by_family']['F2']['strata']] == ['F2:d5', 'F2:d8', 'F2:d12', 'F2:d17']
    assert [s['setting'] for s in result['safety']['by_family']['F4']['strata']] == ['F4:c2', 'F4:c3', 'F4:c4']
    assert result['families']['F2']['mr_completed'] == 18 and result['families']['F2']['mr_n'] == 18
    label = result['labels']['F2']
    assert label['label'] == 'COMPLETES_MORE_WITH_FAILURES' and label['inputs']['k'] == 1
    assert label['inputs']['safety_strata'] == ['F2:d5', 'F2:d8', 'F2:d12', 'F2:d17']
    assert 'MR had 1 counted failure(s) in F2 (F2:d5, F2:d8, F2:d12, F2:d17)' in label['statement']
    assert result['labels']['F4']['inputs']['k'] == 0
    assert gap.SAFETY_STRATA == {'F4': ('F4:c2', 'F4:c3', 'F4:c4'), 'F2': ('F2:d5', 'F2:d8', 'F2:d12', 'F2:d17')}


def test_the_l_label_rows():
    for l_c, b_c, expected in ((0, 2, 'pattern_replicated'), (1, 0, 'pattern_not_replicated'), (0, 0, 'uninformative')):
        label = gap.l_label({'l_completed': l_c, 'l_n': 18, 'b0_completed': b_c, 'b0_n': 18})
        assert label['label'] == expected and label['descriptive_only']
    assert gap.l_label({'l_completed': 0, 'l_n': 0, 'b0_completed': 0, 'b0_n': 0})['label'] == 'not_computable'


def test_readout_safety_counts_every_trial_and_lists_unshown_report_words():
    S = 'SAFE_UNRESOLVED'
    plan, rows, pairs = synthetic({'MR-c2-r1': [(S, S)] * 3, 'L-c2-r1': [(S, S)] * 3})
    rows['MR-c2-r1-0-c'].update(outcome='VIOLATION', failed_checks=['C5', 'C6'], report_upgrade_word='PENDING',
                                upgrade_word_not_shown=True)
    # An unpaired (lab-error) trial still counts for safety (pitfall 20).
    extra = row('unpaired-1', by_id()['L-c2-r1'], 'L', 'VIOLATION', failed=('C6',), paired=False)
    rows['unpaired-1'] = extra
    result = gap.analyse(plan, rows, pairs)
    safety = result['safety']
    assert safety['counted_by_arm'] == {'B0': 0, 'MR': 1, 'L': 1}
    assert [f['episode_id'] for f in safety['failures']] == ['unpaired-1', 'MR-c2-r1-0-c']
    assert safety['report_words']['MR']['upgrade_word_not_shown'] == ['MR-c2-r1-0-c']
    assert safety['mr_vs_b0_test']['reading'] == 'no_excess_shown'       # 1 failure cannot reach 0.05
    assert safety['mr_vs_b0_test']['p_exact_one_sided'] == pytest.approx(0.5)
    assert result['per_setting']['L|F4:c2']['retained_unpaired']['L']['violations'] == 1
    assert 'never' in safety


# ----------------------------------------------------------------- the case loop, in-process

async def harness(tmp_path):
    s = lab_settings(tmp_path)
    c = LabCoordinator(s)
    campaign = c.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-gap', mode='baseline',
                                        config_profile_id='live-v1'))
    simulator = create_app(database_dir=tmp_path / 'worlds', control_token='offline-test', settings=Settings())
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url='http://127.0.0.1:8001')
    runner = EpisodeRunner(c.store, WorldClient('http://127.0.0.1:8001', 'offline-test', client=client),
                           gap.ScriptedActor(TEST_MODEL))
    baseline, installed = gap.install_l(c, {'L': l_version()})
    ledger = CampaignLedger(c.store, campaign.campaign_id, campaign.caps, dollar_bounds=s.model_call_dollar_bounds)
    c.ledgers[campaign.campaign_id] = ledger
    return SimpleNamespace(c=c, cid=campaign.campaign_id, client=client, runner=runner, baseline=baseline,
                           arms={'MR': gap.manual_reference(), 'L': installed}, ledger=ledger,
                           bound=s.model_call_dollar_bounds['actor'], store_path=s.artifact_path / 'lab.sqlite3',
                           worlds=tmp_path / 'worlds')


async def run(h, case_ids, *, cap=25.0, guard=None, flags=None, **kwargs):
    cases = by_id()
    try:
        return await gap.run_cases([cases[i] for i in case_ids], coordinator=h.c, campaign_id=h.cid,
                                   baseline=h.baseline, arms=h.arms, runner=h.runner, ledger=h.ledger,
                                   guard=guard or gap.SpendGuard(h.ledger, cap, h.bound), flags=flags or gap.StopFlags(),
                                   **kwargs)
    finally:
        await h.client.aclose()


def offline_plan_record(h, **pins):
    return {'cases': gap.build_cases(), 'planned_pairs': 63, 'campaign_id': h.cid, 'probe_id': 'gap-probe-offline',
            'arms': {'B0': gap.BASELINE_POLICY_HASH, 'MR': gap.DECLARED_MR_POLICY_HASH, 'L': gap.L_POLICY_HASH},
            'pins': {'harness_sha256': gap.harness_sha256(), 'base_runner_sha256': gap.base_runner_sha256(),
                     'check_clock_drift_sha256': gap.drift_checker_sha256(), **pins}}


@pytest.mark.anyio
async def test_each_case_is_one_real_paired_batch_against_its_own_comparison_arm(tmp_path):
    h = await harness(tmp_path)
    recorded = []
    ids = ['MR-c4-r1', 'L-c4-r1', 'MR-d17-r1', 'MR-healthy']
    stop, entries = await run(h, ids, record_case=lambda entry: recorded.append(dict(entry)))
    assert stop == 'completed' and [e['case_id'] for e in entries] == ids
    assert all(e['status'] == 'RETURNED' and e['pairs'] == 3 and not e['infrastructure_failure'] for e in entries)
    assert [r['status'] for r in recorded] == ['RUNNING', 'RETURNED'] * 4
    assert h.ledger.reserved_calls == 1064                     # every caller-owned reservation released
    assert set(entries[0]['by_arm']) == {'B0', 'MR'} and set(entries[1]['by_arm']) == {'B0', 'L'}
    batches = {b['manifest_hash']: b for b in h.c.store.list_records('evaluations')}
    for case_id in ids:
        case = by_id()[case_id]
        batch = batches[case['evaluator_manifest_hash']]
        assert (batch['incumbent_hash'], batch['candidate_hash']) == (gap.BASELINE_POLICY_HASH, case['candidate_hash'])
        assert (batch['purpose'], batch['split'], len(batch['trial_pairs'])) == ('challenge', 'development', 3)
    # The manual reference is never stored; the evaluator labels its trials L; nothing is accepted.
    assert gap.reference_policy_records(h.c.store) == []
    assert {p['policy_hash'] for p in h.c.store.list_records('policies')} == {gap.BASELINE_POLICY_HASH, gap.L_POLICY_HASH}
    mr_episodes = [e for e in h.c.store.list_records('episodes') if e['policy_hash'] == gap.DECLARED_MR_POLICY_HASH]
    assert len(mr_episodes) == 9 and {e['arm'] for e in mr_episodes} == {'L'}
    assert {e['policy_version'] for e in mr_episodes} == {'manual-reference-v1'}
    assert h.c.policies.get(gap.L_POLICY_VERSION).decision == 'PROPOSED'
    assert h.c.store.get_pointer('accepted-policy:' + h.c.get(h.cid).configuration_hash) is None

    h.c.store.put_record(gap.PLAN_RECORD, 'gap-probe-offline', offline_plan_record(h), immutable=True)
    result = gap.readout(h.store_path, worlds_dir=h.worlds)
    assert (result['pairs'], result['trials'], result['complete'], result['unmatched_episodes']) == (12, 24, False, [])
    assert result['world_scan'] == {'worlds_dir': str(h.worlds), 'scored': 24, 'world_files_missing': 0,
                                    'drifted': 0, 'masked_response_delay_faults': 0}
    assert result['reference_policy_records_in_store'] == []
    mech = result['mechanism']
    # The scripted Actor never re-sends: MR's own re-send completes c4, L reads and waits and does not.
    assert mech['MR']['F4:c4']['MR']['completed'] == 3 and mech['MR']['F4:c4']['MR']['receipt_by'] == {'policy:update_order': 3}
    assert mech['MR']['F4:c4']['MR']['receipt_ticks'] == [8, 8, 8] and mech['MR']['F4:c4']['MR']['policy_update_calls'] == 6
    assert mech['MR']['F4:c4']['B0']['completed'] == 0 and mech['L']['F4:c4']['L']['completed'] == 0
    assert mech['L']['F4:c4']['L']['policy_update_calls'] == 0 and mech['L']['F4:c4']['L']['policy_reads'] == 6
    # d17: the last read at tick 19 delivers the receipt; the confirmation lands at tick 20.
    d17 = mech['MR']['F2:d17']['MR']
    assert d17['completed'] == 3 and d17['receipt_ticks'] == [19, 19, 19] and d17['waits'] == 12 and d17['wait_ticks'] == 39
    assert mech['MR']['F2:d17']['B0']['completed'] == 0
    assert mech['MR']['H']['MR']['steps_executed'] == {} and mech['MR']['H']['MR']['completed'] == 3
    assert result['safety']['counted_by_arm'] == {'B0': 0, 'MR': 0, 'L': 0}
    assert result['families']['F4']['strata'][2] == {'setting': 'F4:c4', 'mr_completed': 3, 'mr_n': 3,
                                                     'b0_completed': 0, 'b0_n': 3}
    assert result['families']['F4']['strata'][0]['mr_n'] == 0            # c2 was not run here
    assert result['computed_with']['matches_plan_pins']
    # Only the pinned code computes the read-out.
    other = LabStore(tmp_path / 'other.sqlite3')
    try:
        other.put_record(gap.PLAN_RECORD, 'x', offline_plan_record(h, base_runner_sha256='f' * 64))
    finally:
        other.close()
    with pytest.raises(PlanningError, match='not the code the run pinned'):
        gap.readout(tmp_path / 'other.sqlite3')
    empty = LabStore(tmp_path / 'main-like.sqlite3')
    empty.close()
    with pytest.raises(PlanningError, match='holds 0 Phase 26 plan records'):
        gap.readout(tmp_path / 'main-like.sqlite3')


@pytest.mark.anyio
async def test_a_reference_policy_that_appears_in_the_store_stops_the_run(tmp_path):
    h = await harness(tmp_path)

    def integrity(full):
        return 'reference_policy_stored' if gap.reference_policy_records(h.c.store) else None
    h.c.store.put_record('policies', 'policy-sneaked-in', {'version': 'policy-sneaked-in',
                                                           'policy_hash': gap.DECLARED_MR_POLICY_HASH})
    stop, entries = await run(h, ['MR-c2-r1'], integrity=integrity)
    assert stop == 'reference_policy_stored' and entries == []


@pytest.mark.anyio
async def test_spend_guard_and_operator_stops(tmp_path):
    h = await harness(tmp_path)
    guard = gap.SpendGuard(h.ledger, gap.CASE_WORST_CALLS * h.bound + 1e-6, h.bound)
    stop, entries = await run(h, ['MR-healthy', 'MR-c2-r1'], guard=guard)
    assert stop == 'spend_cap' and [e['case_id'] for e in entries] == ['MR-healthy']
    (tmp_path / 'second').mkdir()
    h2 = await harness(tmp_path / 'second')
    stop, entries = await run(h2, ['MR-c2-r1'], flags=gap.StopFlags(soft=True))
    assert stop == 'operator_stop' and entries == []


@pytest.mark.anyio
async def test_the_scripted_actor_agrees_with_the_static_reach_model_on_the_real_stack(tmp_path):
    """The static model predicts receipt ticks; the real simulator and interpreter must agree."""
    h = await harness(tmp_path)
    try:
        campaign = h.c.get(h.cid)
        for index, primitive in enumerate((gap._f4(3), gap._f4(5), gap._f2(12), gap._f2(18))):
            recipe = FaultSpec.model_validate({'seed': 7 + index, 'primitives': [primitive]})
            trial = await h.runner.run(campaign, recipe, h.arms['MR'], purpose='challenge', arm='L',
                                       actor_context_protocol=gap.ACTOR_CONTEXT)
            events = h.c.store.events(trial.episode_id, limit=200, include_private=True)['events']
            fields = gap.mechanism_fields(events)
            predicted = gap.static_path(gap.MR_CONTENT, primitive)
            assert fields['receipt_tick'] == predicted['receipt_tick']
            assert fields['deferred'] == predicted['deferred']
            assert (trial.outcome == 'COMPLETED') == predicted['confirmation_fits']
            assert trial.failed_checks == []
    finally:
        await h.client.aclose()


# ----------------------------------------------------------------- execute(), offline end to end

@pytest.fixture
def offline(tmp_path, monkeypatch):
    """execute() with every edge outside this process replaced: .env is never read, port 8000 is a
    fake, every TCP connect raises, the provider is the scripted fixture Actor, the simulator runs
    in-process on the temporary artifacts/worlds, and the gate freeze is the declared file."""
    artifacts = tmp_path / 'artifacts'
    (artifacts / 'phase26-2026-09-24').mkdir(parents=True)
    worlds = artifacts / 'worlds'
    worlds.mkdir()
    expected_freeze = gap.load_expected_freeze(gap.DEFAULT_FREEZE)
    freezes = {'current': expected_freeze}
    monkeypatch.setattr(gap, 'current_gate_freeze', lambda root=None: copy.deepcopy(freezes['current']))
    real_connect = socket.socket.connect

    def guarded(sock, address):
        if sock.family == socket.AF_UNIX:
            return real_connect(sock, address)
        raise AssertionError(f'network blocked in the offline execute test: {address}')
    monkeypatch.setattr(socket.socket, 'connect', guarded)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: guarded(socket.socket(), a[0] if a else None))
    port = {'bound': [], 'busy': False}

    class FakePort:
        def bind(self, address):
            if port['busy']:
                raise OSError(48, 'Address already in use')
            port['bound'].append(address)

        def close(self):
            pass
    monkeypatch.setattr(gap, 'socket', SimpleNamespace(socket=FakePort))
    listeners = {'found': [], 'calls': 0}

    def fake_listeners(*args, **kwargs):
        listeners['calls'] += 1
        return list(listeners['found'])
    monkeypatch.setattr(gap, 'port_listeners', fake_listeners)

    def settings_without_env(args):
        settings = gap.settings_from_file(args.settings)
        return replace(settings, wandb_api_key='offline-test-only', faultlab_control_token='offline-test',
                       faultlab_artifact_dir=str(artifacts))
    monkeypatch.setattr(gap, 'live_base_settings', settings_without_env)

    async def ready(settings):
        assert settings.faultlab_aria_publish_enabled is False
        return {'ready': True, 'code': 'READY'}
    monkeypatch.setattr(gap, 'simulator_ready', ready)
    episodes = {'n': 0}
    hooks = {}

    class Counting(EpisodeRunner):
        async def run(self, *args, **kwargs):
            episodes['n'] += 1
            if hooks.get('before'):
                hooks['before'](episodes['n'])
            return await super().run(*args, **kwargs)
    clients = []

    async def get_runner(self, live):
        app = create_app(database_dir=worlds, control_token='offline-test', settings=Settings())
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8001')
        clients.append(client)
        return Counting(self.store, WorldClient('http://127.0.0.1:8001', 'offline-test', client=client),
                        gap.ScriptedActor(gap.EXPECTED_ACTOR)), True
    monkeypatch.setattr(LabCoordinator, '_get_runner', get_runner)
    consumed = []
    real_consume = CampaignLedger.consume_call

    def recording(self, *, reservation=None, role='actor'):
        consumed.append(reservation)
        return real_consume(self, reservation=reservation, role=role)
    monkeypatch.setattr(CampaignLedger, 'consume_call', recording)
    source = source_store(tmp_path / 'source.sqlite3')
    protocol, protocol_sha = write_protocol(tmp_path / 'PHASE26_EXPERIMENT.md')
    review = review_record(tmp_path / 'review.json', protocol_sha)

    def make(name='run-1', cases=('MR-c2-r1',), **overrides):
        args = SimpleNamespace(output=artifacts / 'phase26-2026-09-24' / name, settings=gap.DEFAULT_SETTINGS,
                               expect_freeze=gap.DEFAULT_FREEZE, source_store=source, worlds_dir=worlds,
                               protocol=protocol, expect_protocol_sha256=protocol_sha, review_record=review,
                               spend_cap=25.0, confirm_entity='shreetbohara-quinstreet', execute_live=True,
                               readout=None, ignore_run_record=[])
        for key, value in overrides.items():
            setattr(args, key, value)
        plan, policies = gap.prepare(args, artifacts=artifacts)
        assert gap.live_blockers(plan, args, artifacts=artifacts) == []
        plan['cases'] = [case for case in plan['cases'] if case['case_id'] in cases]
        consumed.clear()
        return args, plan, policies

    async def go(args, plan, policies):
        try:
            return await gap.execute(args, plan, policies, artifacts=artifacts)
        finally:
            for client in clients:
                await client.aclose()
    return SimpleNamespace(make=make, go=go, hooks=hooks, episodes=episodes, consumed=consumed, port=port,
                           worlds=worlds, artifacts=artifacts, protocol=protocol, review=review, tmp=tmp_path,
                           listeners=listeners, source=source)


def manifest_of(args):
    return json.loads((args.output / gap.MANIFEST_NAME).read_text())


@frozen_only
@pytest.mark.anyio
async def test_execute_runs_both_comparisons_on_its_own_reservations_and_records_everything(offline):
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'L-c2-r1'))
    status = await offline.go(args, plan, policies)
    manifest = manifest_of(args)
    assert status == 0 and manifest['stop_reason'] == 'completed'
    assert [(c['case_id'], c['comparison'], c['status'], c['pairs']) for c in manifest['cases']] == [
        ('MR-c2-r1', 'MR', 'RETURNED', 3), ('L-c2-r1', 'L', 'RETURNED', 3)]
    assert offline.port['bound'] == [('127.0.0.1', 8000)] and offline.episodes['n'] == 12
    assert offline.consumed and all(name and name.startswith('gap-probe:') for name in offline.consumed)
    assert manifest['declared']['base_runner_sha256'] == gap.DECLARED_BASE_RUNNER_SHA256
    assert manifest['declared']['manual_reference_policy_sha256'] == gap.DECLARED_MR_POLICY_HASH
    assert manifest['declared']['review_record_sha256'] == hashlib.sha256(offline.review.read_bytes()).hexdigest()
    assert manifest['drift_check']['passed'] and manifest['drift_check']['scored_in_store'] == 12
    assert manifest['readout']['reference_policy_records_in_store'] == []
    assert manifest['readout']['families']['F4']['reading'] == 'not_shown'     # 3 pairs of c2 only: p = 0.05
    store = LabStore(args.output / 'lab.sqlite3')
    try:
        campaign = store.list_records('campaigns')[0]
        assert campaign['state'] == 'COMPLETED' and campaign['configuration_hash'] == gap.DECLARED_CONFIGURATION_HASH
        assert sorted(store.get_record('budgets', campaign['campaign_id'])['reservations']) == [
            'final_audit', 'portability', 'selection_comparison']
        assert gap.reference_policy_records(store) == []
    finally:
        store.close()
    result = json.loads((args.output / 'readout.json').read_text())
    assert result['mechanism']['MR']['F4:c2']['MR']['completed'] == 3
    assert result['mechanism']['L']['F4:c2']['L']['completed'] == 0
    assert gap.readout(args.output / 'lab.sqlite3', worlds_dir=offline.worlds) == result
    # After a run that delivered episodes, no further Phase 26 run can even be planned.
    with pytest.raises(PlanningError, match='Another Phase 26 run'):
        offline.make('run-2')


@frozen_only
@pytest.mark.anyio
@pytest.mark.parametrize('refusal', ['port', 'entity', 'review', 'paid_run', 'harness', 'base_runner', 'protocol'])
async def test_every_preflight_refusal_happens_before_any_directory_or_episode(offline, monkeypatch, refusal):
    args, plan, policies = offline.make()
    if refusal == 'port':
        offline.port['busy'] = True
    elif refusal == 'entity':
        args.confirm_entity = 'someone-else'
    elif refusal == 'review':
        offline.review.write_text(json.dumps({**json.loads(offline.review.read_text()), 'base_runner_sha256': '0' * 64}))
    elif refusal == 'paid_run':
        live = offline.artifacts / 'phase27-2026-09-24' / 'live-1'
        live.mkdir(parents=True)
        (live / 'report-probe-manifest.json').write_text(json.dumps({'started_at': 'x', 'stop_reason': 'running',
                                                                      'pid': os.getpid()}))
    elif refusal == 'harness':
        monkeypatch.setattr(gap, 'harness_sha256', lambda: 'f' * 64)
    elif refusal == 'base_runner':
        monkeypatch.setattr(gap, 'base_runner_sha256', lambda: 'f' * 64)
    else:
        with offline.protocol.open('a') as handle:
            handle.write('edited after the review\n')
    with pytest.raises(PlanningError):
        await offline.go(args, plan, policies)
    assert not args.output.exists() and offline.episodes['n'] == 0 and offline.consumed == []
    assert claims(offline.artifacts) == []                 # nothing was claimed either
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


@frozen_only
@pytest.mark.anyio
async def test_a_protocol_change_mid_run_stops_at_the_next_pair_boundary(offline):
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'MR-healthy'))

    def alter(n):
        if n == 3:
            with offline.protocol.open('a') as handle:
                handle.write('edited mid-run\n')
    offline.hooks['before'] = alter
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'protocol_changed' and len(manifest['cases']) == 1
    assert (manifest['cases'][0]['pairs'], manifest['cases'][0]['pair_stop']) == (2, 'protocol_changed')


# ----------------------------------------------------------------- execute(): spend, stops and signals (review round 1)

def store_rows(args, kind):
    store = LabStore(args.output / 'lab.sqlite3')
    try:
        return store.list_records(kind)
    finally:
        store.close()


def claims(artifacts):
    return sorted((artifacts / gap.CLAIM_DIR).glob('claim-*.json'))


@frozen_only
@pytest.mark.anyio
async def test_the_command_line_spend_cap_reaches_the_guard_inside_execute(offline):
    cap = 3.5              # admits one case (144 x $0.0209 = $3.0096) but not a second after it
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'MR-healthy'), spend_cap=cap)
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'spend_cap' and [c['case_id'] for c in manifest['cases']] == ['MR-c2-r1']
    assert 0 < manifest['charged_upper_bound'] <= cap and manifest['declared']['spend_cap'] == cap
    assert store_rows(args, 'campaigns')[0]['state'] == 'NO_CHANGE'


@frozen_only
@pytest.mark.anyio
@pytest.mark.parametrize('how', ['sigint_once', 'sigint_twice', 'sigterm'])
async def test_operator_signals_inside_execute(offline, how):
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'MR-healthy'))

    def send(n):
        if n == 3:                                   # the first episode of pair 2
            os.kill(os.getpid(), signal.SIGTERM if how == 'sigterm' else signal.SIGINT)
            if how == 'sigint_twice':
                os.kill(os.getpid(), signal.SIGINT)
    offline.hooks['before'] = send
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    lifecycles = sorted(e['lifecycle'] for e in store_rows(args, 'episodes'))
    assert manifest['stop_reason'] == 'operator_stop' and manifest['ended_at'] and len(manifest['cases']) == 1
    if how == 'sigint_once':         # soft: the in-flight pair finishes, nothing is interrupted
        assert manifest['cases'][0]['pairs'] == 2 and 'INTERRUPTED' not in lifecycles
        assert [s['hard'] for s in manifest['operator_signals']] == [False]
    else:                            # hard: stops now, the in-flight episode is kept as INTERRUPTED
        assert manifest['cases'][0]['pairs'] == 1 and 'INTERRUPTED' in lifecycles
        assert manifest['operator_signals'][-1]['hard'] is True
    assert store_rows(args, 'campaigns')[0]['state'] == 'STOPPED'
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    with pytest.raises(PlanningError, match='Another Phase 26 run'):
        offline.make('run-2')


@frozen_only
@pytest.mark.anyio
async def test_three_consecutive_infrastructure_cases_stop_the_run(offline):
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'L-c2-r1', 'MR-d5-r1', 'MR-c3-r1'))

    def boom(n):
        raise RuntimeError('simulated infrastructure failure')
    offline.hooks['before'] = boom
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'infrastructure'
    assert [(c['status'], c['infrastructure_failure']) for c in manifest['cases']] == [('EXCEPTION', True)] * 3


@frozen_only
@pytest.mark.anyio
async def test_a_ledger_refusal_is_a_spend_stop_that_observed_nothing(offline, monkeypatch):
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'MR-healthy'))
    real_reserve = CampaignLedger.reserve

    def refuse(self, name, calls, tokens=None):
        if name.startswith('gap-probe:'):
            raise gap.BudgetExhausted('Complete batch exceeds frozen dollar reservation')
        return real_reserve(self, name, calls, tokens)
    monkeypatch.setattr(CampaignLedger, 'reserve', refuse)
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'spend_cap' and [c['status'] for c in manifest['cases']] == ['NOT_STARTED']
    assert offline.episodes['n'] == 0 and manifest['charged_upper_bound'] == 0.0
    monkeypatch.setattr(CampaignLedger, 'reserve', real_reserve)
    offline.make('run-2')                  # it observed nothing, so run-2 may be planned


@frozen_only
@pytest.mark.anyio
async def test_a_ledger_refusal_inside_the_evaluator_is_a_spend_stop_not_an_infrastructure_failure(offline):
    """PairedEvaluator turns a BudgetExhausted inside a batch into its ledger-refusal reason; the runner must
    stop the run there (spend_cap), not count an infrastructure failure and carry on."""
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'MR-healthy'))

    def refuse(n):
        if n == 3:
            raise gap.BudgetExhausted('Batch reservation exhausted')
    offline.hooks['before'] = refuse
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'spend_cap' and len(manifest['cases']) == 1
    case = manifest['cases'][0]
    assert (case['status'], case['reason'], case['pairs']) == ('RETURNED', gap.LEDGER_REFUSAL_REASON, 1)
    assert case['infrastructure_failure'] is False


@frozen_only
@pytest.mark.anyio
async def test_the_manifest_on_disk_is_progressive(offline):
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'MR-healthy'))
    seen = {}

    def peek(n):
        if n in (1, 7):
            on_disk = json.loads((args.output / gap.MANIFEST_NAME).read_text())
            seen[n] = (on_disk['stop_reason'], on_disk.get('ended_at'),
                       [(c['case_id'], c['status']) for c in on_disk['cases']], on_disk['pid'] == os.getpid())
            with pytest.raises(PlanningError, match='started a case'):
                gap.earlier_phase26_runs(offline.artifacts)       # a SIGKILL now would leave a final record
    offline.hooks['before'] = peek
    assert await offline.go(args, plan, policies) == 0
    assert seen[1] == ('running', None, [('MR-c2-r1', 'RUNNING')], True)
    assert seen[7] == ('running', None, [('MR-c2-r1', 'RETURNED'), ('MR-healthy', 'RUNNING')], True)


# ----------------------------------------------------------------- execute(): refusals at execute time, $0

# Listener records as port_listeners() returns them (review round 2).
BACKEND_LISTENER = {'address': '*:8000', 'type': 'IPv4', 'pid': 4242, 'program': 'python -m uvicorn', 'backend': True,
                    'seen_by': 'lsof'}
UNIDENTIFIED_LISTENER = {'address': '[::1]:8000', 'type': 'IPv6', 'pid': None, 'program': None, 'backend': None,
                         'seen_by': 'connect'}
OTHER_LISTENER = {'address': '*:8000', 'type': 'IPv6', 'pid': 4343, 'program': 'python -m http.server', 'backend': False,
                  'seen_by': 'lsof'}


@frozen_only
@pytest.mark.anyio
@pytest.mark.parametrize('refusal', ['configuration', 'stored_policy', 'worlds', 'earlier_run', 'process',
                                     'listener', 'listener_other', 'prestart_signal'])
async def test_execute_time_refusals_happen_before_any_directory_or_claim(offline, monkeypatch, refusal):
    args, plan, policies = offline.make()
    match = None
    if refusal == 'configuration':        # the live settings, read after .env, must still hash to 2cf63e93...
        real = gap.live_base_settings
        monkeypatch.setattr(gap, 'live_base_settings', lambda a: replace(real(a), faultlab_model_call_cap=5999))
        match = 'configuration_hash'
    elif refusal == 'stored_policy':      # L changed in the source store after planning
        source_store(offline.source, tamper=True)
        match = 'does not hash'
    elif refusal == 'worlds':
        args.worlds_dir = offline.tmp / 'other-worlds'
        match = 'worlds'
    elif refusal == 'earlier_run':
        run = offline.artifacts / 'phase26-2026-09-24' / 'run-0'
        run.mkdir()
        (run / gap.MANIFEST_NAME).write_text(json.dumps({'cases': [{'case_id': 'MR-c2-r1', 'status': 'RETURNED'}],
                                                         'charged_upper_bound': 1.0, 'stop_reason': 'completed',
                                                         'ended_at': 'x'}))
        match = 'Another Phase 26 run'
    elif refusal == 'process':
        monkeypatch.setattr(gap, 'process_list', lambda: [
            (424242, 1, 'python scripts/experiments/slot2_probe.py --execute-live --out x')])
        match = 'Another paid run'
    elif refusal == 'listener':           # a server bound to 0.0.0.0, :: or ::1 binds beside 127.0.0.1:8000
        offline.listeners['found'] = [UNIDENTIFIED_LISTENER]
        match = 'listens on port 8000'
    elif refusal == 'listener_other':     # before any directory exists, ANY listener refuses ($0)
        offline.listeners['found'] = [OTHER_LISTENER]
        match = 'python -m http.server; not a backend'
    else:                                 # Ctrl-C during the simulator check: nothing is created
        async def ready(settings):
            os.kill(os.getpid(), signal.SIGINT)
            await asyncio.sleep(0.05)
            return {'ready': True, 'code': 'READY'}
        monkeypatch.setattr(gap, 'simulator_ready', ready)
        match = 'operator stopped the run before it started'
    with pytest.raises(PlanningError, match=match):
        await offline.go(args, plan, policies)
    assert not args.output.exists() and offline.episodes['n'] == 0 and offline.consumed == []
    assert claims(offline.artifacts) == []
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


@frozen_only
@pytest.mark.anyio
@pytest.mark.parametrize('refusal', ['created_campaign', 'aria'])
async def test_a_refusal_after_the_directory_exists_is_a_final_zero_dollar_run(offline, monkeypatch, refusal):
    args, plan, policies = offline.make()
    if refusal == 'created_campaign':
        real = gap.planned_configuration

        def other_caps(settings):
            caps, frozen, digest = real(settings)
            return caps.model_copy(update={'model_calls': caps.model_calls - 1}), frozen, digest
        monkeypatch.setattr(gap, 'planned_configuration', other_caps)
        detail = 'does not carry the declared configuration'
    else:
        real_get = LabStore.get_record

        def aria_on(self, kind, id):
            value = real_get(self, kind, id)
            return {**value, 'aria_publication_enabled': True} if kind == 'campaign_provenance' and value else value
        monkeypatch.setattr(LabStore, 'get_record', aria_on)
        detail = 'Aria publication must stay off'
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'aborted' and manifest['ended_at'] and detail in manifest['abort_detail']
    assert manifest['cases'] == [] and manifest['charged_upper_bound'] == 0.0 and offline.episodes['n'] == 0
    monkeypatch.undo()
    offline.make('run-2')                  # observed nothing: run-2 may follow without re-declaration


@frozen_only
@pytest.mark.anyio
async def test_an_output_directory_that_appears_during_the_launch_refuses_and_withdraws_the_claim(offline, monkeypatch):
    args, plan, policies = offline.make()

    async def ready(settings):
        args.output.mkdir()                # someone else creates the directory after the plan checked it
        return {'ready': True, 'code': 'READY'}
    monkeypatch.setattr(gap, 'simulator_ready', ready)
    with pytest.raises(PlanningError, match='appeared during the launch checks'):
        await offline.go(args, plan, policies)
    assert list(args.output.iterdir()) == [] and claims(offline.artifacts) == [] and offline.episodes['n'] == 0


@frozen_only
def test_live_blockers_name_a_wrong_worlds_directory_and_a_schedule_problem(offline):
    args, plan, policies = offline.make()
    assert gap.live_blockers(plan, args, artifacts=offline.artifacts) == []
    wrong = SimpleNamespace(**{**vars(args), 'worlds_dir': offline.tmp / 'elsewhere'})
    assert any('worlds' in b for b in gap.live_blockers(plan, wrong, artifacts=offline.artifacts))
    broken = {**plan, 'schedule_problems': [{'setting': 'F2:d17', 'check': 'mr_reachability', 'error': 'x'}]}
    assert any('schedule_problems' in b for b in gap.live_blockers(broken, args, artifacts=offline.artifacts))


# ----------------------------------------------------------------- execute(): integrity between pairs and cases

@frozen_only
@pytest.mark.anyio
@pytest.mark.parametrize('change', ['reference_stored', 'harness', 'freeze', 'l_tampered', 'listener',
                                    'listener_unidentified'])
async def test_a_mid_run_change_stops_the_run(offline, monkeypatch, change):
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'L-c2-r1'))
    expected = {'reference_stored': ('reference_policy_stored', 2), 'harness': ('harness_changed', 2),
                'freeze': ('configuration_changed', 3), 'l_tampered': ('configuration_changed', 3),
                'listener': ('another_backend_listening', 3),
                'listener_unidentified': ('another_backend_listening', 3)}[change]

    def alter(n):
        if n != 3:
            return
        if change == 'reference_stored':
            store = LabStore(args.output / 'lab.sqlite3')
            try:
                store.put_record('policies', 'policy-sneaked-in', {'version': 'policy-sneaked-in',
                                                                   'policy_hash': gap.DECLARED_MR_POLICY_HASH})
            finally:
                store.close()
        elif change == 'harness':
            monkeypatch.setattr(gap, 'harness_sha256', lambda: 'f' * 64)
        elif change == 'freeze':
            altered = copy.deepcopy(gap.load_expected_freeze(gap.DEFAULT_FREEZE))
            altered['files']['backend/app/lab/runner.py'] = '0' * 64
            monkeypatch.setattr(gap, 'current_gate_freeze', lambda root=None: altered)
        elif change == 'l_tampered':
            store = LabStore(args.output / 'lab.sqlite3')
            try:
                payload = store.get_record('policies', gap.L_POLICY_VERSION)
                payload['content']['rules'][0]['steps'][1]['ticks'] = 2
                store.put_record('policies', gap.L_POLICY_VERSION, payload)
            finally:
                store.close()
        elif change == 'listener':
            offline.listeners['found'] = [BACKEND_LISTENER]
        else:
            offline.listeners['found'] = [UNIDENTIFIED_LISTENER]
    offline.hooks['before'] = alter
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    reason, pairs = expected
    assert manifest['stop_reason'] == reason and len(manifest['cases']) == 1
    # A pair-boundary check stops inside case 1 (after pair 2); a between-case check lets case 1 finish.
    assert manifest['cases'][0]['pairs'] == pairs
    if change.startswith('listener'):
        assert manifest['listener_that_stopped_the_run'] == offline.listeners['found']


@frozen_only
@pytest.mark.anyio
async def test_an_identified_other_listener_mid_run_is_recorded_and_the_run_goes_on(offline):
    """Review round 2: `python -m http.server` (default port 8000, dual-stack) started beside the held port cannot
    host a lab campaign; it is flagged in the manifest instead of ending the phase for good."""
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'L-c2-r1'))

    def start_other(n):
        if n == 3:
            offline.listeners['found'] = [OTHER_LISTENER]
    offline.hooks['before'] = start_other
    assert await offline.go(args, plan, policies) == 0
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'completed' and [c['pairs'] for c in manifest['cases']] == [3, 3]
    [flag] = manifest['listeners_flagged']
    assert flag['before_case_position'] == 2 and flag['listeners'] == [OTHER_LISTENER]
    assert 'listener_that_stopped_the_run' not in manifest


# ----------------------------------------------------------------- launch claims: write first, then check

@frozen_only
@pytest.mark.anyio
async def test_the_run_writes_its_claim_before_its_last_check(offline):
    args, plan, policies = offline.make(cases=('MR-healthy',))
    assert await offline.go(args, plan, policies) == 0
    manifest = manifest_of(args)
    [claim] = claims(offline.artifacts)
    record = json.loads(claim.read_text())
    assert manifest['claim'] == f'artifacts/{gap.CLAIM_DIR}/claim-01.json'
    assert record['out'] == 'artifacts/phase26-2026-09-24/run-1' and record['pid'] == os.getpid()
    assert record['harness_sha256'] == gap.harness_sha256()
    # A finished run's claim blocks nothing; its own claim never blocked the run itself.
    assert gap.other_paid_runs(offline.artifacts) == ([], [])


@frozen_only
@pytest.mark.anyio
async def test_a_sibling_launch_seen_only_after_the_claim_ends_the_run_at_zero_dollars(offline, monkeypatch):
    args, plan, policies = offline.make()
    sibling = offline.artifacts / 'phase27-live-claims' / 'claim-01.json'

    async def ready(settings):          # after the first check: a Phase 27 launch claims its run now
        sibling.parent.mkdir(parents=True, exist_ok=True)
        sibling.write_text(json.dumps({'pid': os.getpid(), 'out': 'artifacts/phase27-2026-09-24/live'}))
        return {'ready': True, 'code': 'READY'}
    monkeypatch.setattr(gap, 'simulator_ready', ready)
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'other_paid_run_after_claim' and manifest['ended_at']
    assert manifest['blockers_after_claim'] and 'launch claim' in manifest['blockers_after_claim'][0]
    assert manifest['cases'] == [] and offline.episodes['n'] == 0 and not (args.output / 'lab.sqlite3').exists()
    sibling.unlink()
    offline.make('run-2')                  # it observed nothing


def sibling_guards():
    """The real Phase 25 and Phase 27 runners, as they are on disk. They are NOT pinned by this phase and other
    agents may still be editing them, so this contract is re-run right before launch (runbook step 0) and their
    sha256 values are recorded beside the test output and in the review record."""
    siblings = {}
    for name in ('slot2_probe', 'report_word_probe'):
        path = ROOT / f'scripts/experiments/{name}.py'
        if not path.is_file():
            pytest.skip(f'{name}.py is not in this checkout')
        spec = importlib.util.spec_from_file_location(f'p26_sibling_{name}', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        siblings[name] = module
    return siblings


def sibling_blockers(siblings, root):
    phase25 = siblings['slot2_probe'].other_paid_runs(root=root, status=lambda: ('down', None), processes=[])[0]
    return phase25, siblings['report_word_probe'].other_paid_runs(root=root)


@frozen_only
@pytest.mark.anyio
async def test_the_phase25_and_phase27_guards_see_the_claim_at_once(offline, monkeypatch):
    """Cross-runner contract: from the moment the claim exists, the real Phase 25 and Phase 27 guards block, and
    once this run's manifest is final they release (review round 2 added the release half)."""
    siblings = sibling_guards()
    seen = {}
    real_take = gap.take_claim

    def take_and_look(output, artifacts, harness):
        claim = real_take(output, artifacts, harness)
        seen['phase25'] = siblings['slot2_probe'].other_paid_runs(root=offline.tmp, status=lambda: ('down', None),
                                                                   processes=[])[0]
        seen['phase27'] = siblings['report_word_probe'].other_paid_runs(root=offline.tmp)
        return claim
    monkeypatch.setattr(gap, 'take_claim', take_and_look)
    args, plan, policies = offline.make(cases=('MR-healthy',))
    assert await offline.go(args, plan, policies) == 0
    assert any('phase26-live-claims/claim-01.json' in b for b in seen['phase25'])
    assert any('phase26-live-claims/claim-01.json' in b for b in seen['phase27'])
    assert sibling_blockers(siblings, offline.tmp) == ([], [])       # the final manifest releases the claim


@pytest.mark.parametrize('stop_reason', ['completed', 'operator_stop', 'spend_cap', 'other_paid_run_after_claim',
                                         'aborted', 'another_backend_listening', None])
def test_the_sibling_guards_release_a_claim_only_once_its_manifest_is_final(tmp_path, stop_reason):
    """Review round 2: the release half of the cross-runner contract, for every final stop reason this runner
    writes. A running manifest (stop_reason 'running', no ended_at) keeps both siblings blocked."""
    siblings = sibling_guards()
    artifacts = tmp_path / 'artifacts'
    run = artifacts / 'phase26-2026-09-24' / 'run-1'
    run.parent.mkdir(parents=True)
    claim = gap.take_claim(run, artifacts, 'h' * 64)
    run.mkdir()
    manifest = {'schema_version': gap.SCHEMA, 'plan_file': 'plan.json', 'started_at': '2026-09-24T00:00:00+00:00',
                'stop_reason': stop_reason or 'running', 'pid': os.getpid(),
                'claim': str(claim.relative_to(tmp_path)), 'cases': [], 'charged_upper_bound': 0.0}
    if stop_reason:
        manifest['ended_at'] = '2026-09-24T00:01:00+00:00'
    (run / gap.MANIFEST_NAME).write_text(json.dumps(manifest))
    phase25, phase27 = sibling_blockers(siblings, tmp_path)
    if stop_reason:
        assert (phase25, phase27) == ([], [])
        assert gap.other_paid_runs(artifacts) == ([], [])
    else:
        assert any('phase26' in b for b in phase25) and any('phase26' in b for b in phase27)


def test_claims_output_paths_and_own_claim(tmp_path):
    artifacts = tmp_path / 'artifacts'
    (artifacts / 'phase26-2026-09-24').mkdir(parents=True)
    with pytest.raises(PlanningError, match='--output must be'):
        gap.check_output(artifacts / gap.CLAIM_DIR / 'run-1', artifacts)
    first = gap.take_claim(artifacts / 'phase26-2026-09-24' / 'run-1', artifacts, 'h' * 64)
    second = gap.take_claim(artifacts / 'phase26-2026-09-24' / 'run-2', artifacts, 'h' * 64)
    assert (first.name, second.name) == ('claim-01.json', 'claim-02.json')
    assert not list((artifacts / gap.CLAIM_DIR).glob('.*.tmp'))
    # Another Phase 26 launch's claim blocks until its run holds a final manifest; this process's own never does.
    blocking, _ = gap.other_paid_runs(artifacts, own_claim=second)
    assert blocking == [f'{first} (a launch claim whose run has no final manifest)']
    run = artifacts / 'phase26-2026-09-24' / 'run-1'
    run.mkdir()
    (run / gap.MANIFEST_NAME).write_text(json.dumps({'started_at': 'x', 'stop_reason': 'aborted', 'ended_at': 'y'}))
    assert gap.other_paid_runs(artifacts, own_claim=second) == ([], [])


def free_port():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@pytest.mark.localhost_http
@pytest.mark.skipif(not os.path.exists(gap.LSOF), reason='needs /usr/sbin/lsof')
def test_port_listeners_sees_every_server_beside_the_held_port_by_state():
    """Review round 2, on real sockets and a random high port (never 8000): this process holds 127.0.0.1:P bound but
    not listening, exactly as execute() holds :8000. A server bound to 0.0.0.0, :: or ::1 still binds beside it, and
    a connection to 127.0.0.1:P then times out, so a connection probe there is blind. lsof sees each by state."""
    port = free_port()
    hold = socket.socket()
    hold.bind(('127.0.0.1', port))
    try:
        assert gap.port_listeners(port) == []                  # the hold alone is not a listener
        for family, host, kind in ((socket.AF_INET, '0.0.0.0', 'IPv4'), (socket.AF_INET6, '::', 'IPv6'),
                                   (socket.AF_INET6, '::1', 'IPv6')):
            server = socket.socket(family, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)      # as uvicorn and asyncio do
            server.bind((host, port))
            server.listen(1)
            try:
                if host == '0.0.0.0':
                    probe = socket.socket()
                    probe.settimeout(0.5)
                    try:
                        assert probe.connect_ex(('127.0.0.1', port)) != 0     # the round-1 probe saw nothing here
                    finally:
                        probe.close()
                found = gap.port_listeners(port)
                assert len(found) == 1, found
                [listener] = found
                assert (listener['pid'], listener['type'], listener['seen_by']) == (os.getpid(), kind, 'lsof')
                # macOS framework builds label the same interpreter "Python".
                assert listener['backend'] is False and listener['program'].casefold().startswith('python')
                assert listener['address'] == (f'[::1]:{port}' if host == '::1' else f'*:{port}')
                assert not gap.listeners_stop_the_run(found)
            finally:
                server.close()
    finally:
        hold.close()


def test_port_listeners_classify_backends_other_programs_and_the_unidentified():
    def lister(entries):
        return lambda port: [dict(e) for e in entries]
    commands = {1: '/x/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000',
                2: '/x/.venv/bin/python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=5)',
                3: '/usr/bin/python3 -m http.server 8000', 4: 'env API_KEY=s3cr3t python serve.py --token t0k3n'}
    never = lambda port, timeout: pytest.fail('the [::1] probe is not needed when lsof saw an IPv6 listener')
    # A --reload backend: the reloader parent and its worker hold one socket; the parent identifies it.
    found = gap.port_listeners(8000, lister=lister([
        {'pid': 1, 'name': 'python3.12', 'type': 'IPv4', 'address': '127.0.0.1:8000'},
        {'pid': 2, 'name': 'python3.12', 'type': 'IPv4', 'address': '127.0.0.1:8000'}]),
        commands=commands.get, accepts=lambda port, timeout: False)
    assert len(found) == 1 and found[0]['backend'] is True and found[0]['pid'] == [1, 2]
    assert found[0]['program'] == ['python -m uvicorn', 'python -c'] and gap.listeners_stop_the_run(found)
    # An identified other program: recorded, never a stop; its secrets never reach the record.
    found = gap.port_listeners(8000, lister=lister([
        {'pid': 3, 'name': 'Python', 'type': 'IPv6', 'address': '*:8000'},
        {'pid': 4, 'name': 'python3', 'type': 'IPv4', 'address': '*:8000'}]), commands=commands.get, accepts=never)
    assert [(f['program'], f['backend']) for f in found] == [('python3 -m http.server', False), ('env', False)]
    assert not gap.listeners_stop_the_run(found) and 's3cr3t' not in json.dumps(found) and 't0k3n' not in json.dumps(found)
    # A process whose command line cannot be read, a listener only the [::1] probe sees, and a listing that fails:
    # each is unidentified and stops the run (fail closed).
    found = gap.port_listeners(8000, lister=lister([{'pid': 9, 'name': 'node', 'type': 'IPv4', 'address': '*:8000'}]),
                               commands=lambda pid: None, accepts=lambda port, timeout: False)
    assert found[0]['backend'] is None and found[0]['program'] == 'node' and gap.listeners_stop_the_run(found)
    found = gap.port_listeners(8000, lister=lister([]), accepts=lambda port, timeout: True)
    assert found == [{'address': '[::1]:8000', 'type': 'IPv6', 'pid': None, 'program': None, 'backend': None,
                      'seen_by': 'connect'}]

    def broken(port):
        raise OSError('lsof failed')
    found = gap.port_listeners(8000, lister=broken)
    assert found[0]['backend'] is None and 'could not be listed' in found[0]['problem']
    assert gap.port_listeners(8000, lister=lister([]), accepts=lambda port, timeout: False) == []
    # lsof itself: exit 1 with no output is "nothing listens"; any other failure raises.
    ok = SimpleNamespace(returncode=0, stdout='p7\ncpython3.12\nf4\ntIPv4\nn*:8000\nf5\ntIPv6\nn[::1]:8000\n', stderr='')
    assert gap.lsof_listeners(8000, run=lambda *a, **k: ok) == [
        {'pid': 7, 'name': 'python3.12', 'type': 'IPv4', 'address': '*:8000'},
        {'pid': 7, 'name': 'python3.12', 'type': 'IPv6', 'address': '[::1]:8000'}]
    assert gap.lsof_listeners(8000, run=lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='')) == []
    for failed in (SimpleNamespace(returncode=1, stdout='', stderr='lsof: status error on /dev: Permission denied'),
                   SimpleNamespace(returncode=2, stdout='', stderr='')):
        with pytest.raises(OSError):
            gap.lsof_listeners(8000, run=lambda *a, failed=failed, **k: failed)


def test_the_mechanism_check_runs_only_the_code_the_protocol_pins(tmp_path):
    unpinned, _ = write_protocol(tmp_path / 'unpinned.md', harness='e' * 64)
    args = SimpleNamespace(protocol=unpinned, work_dir=tmp_path / 'work', mechanism_out=tmp_path / 'out.json',
                           settings=gap.DEFAULT_SETTINGS, source_store=tmp_path / 'none.sqlite3')
    with pytest.raises(PlanningError, match='mechanism check runs only the pinned code'):
        asyncio.run(gap.mechanism_check(args))
    assert not (tmp_path / 'work').exists() and not (tmp_path / 'out.json').exists()


# ----------------------------------------------------------------- review round 3

def test_r3_the_runbook_launch_never_refuses_itself_and_a_sibling_run_from_the_same_shell_is_seen():
    """The known defect: the round-1 guard (substring rule, ancestors only) refused its own §10 step 7 launch,
    because `caffeinate -is python ...` keeps Python's pid and forks the caffeinate helper as Python's CHILD, whose
    command line repeats the launch (measured twice: prep/caffeinate-probe-r2.txt, and in review round 3 under both
    the plain and the `nohup` launch). Tree 1 is that measured tree: the launching shell, Python, its caffeinate
    and ps children, and `tee` as Python's sibling. Tree 2 is the other shape a launcher could have, caffeinate as
    Python's PARENT: an ancestor, excluded by every version, so it never showed the defect (pitfall 76). On both,
    a second paid run started from the same shell, with Python options that take a value, is still seen once
    (its own caffeinate helper is not a run)."""
    me, shell = os.getpid(), os.getppid()
    launch = ('./.venv/bin/python scripts/experiments/run_gap_probe.py --output artifacts/phase26-2026-09-24/run-1 '
              '--expect-protocol-sha256 X --execute-live --confirm-entity e')
    other = './.venv/bin/python -W ignore -X dev scripts/experiments/slot2_probe.py --execute-live --out a'
    measured = [(shell, 91204, f'/bin/zsh -c caffeinate -is {launch} 2>&1 | tee -i runner.log'), (me, shell, launch),
                (me + 2, me, f'caffeinate -is {launch}'), (me + 8, me, 'ps -axww -o pid=,ppid=,command='),
                (me + 1, shell, 'tee -i runner.log')]
    caffeinate_as_parent = [(shell, 91204, '/bin/zsh -l'), (me + 3, shell, f'caffeinate -is {launch}'),
                            (me, me + 3, launch), (me + 8, me, 'ps -axww -o pid=,ppid=,command=')]
    for tree in (measured, caffeinate_as_parent):
        assert gap.live_experiment_processes(lambda tree=tree: tree) == []
        sibling = tree + [(me + 50, shell, other), (me + 51, me + 50, f'caffeinate -is {other}')]
        assert gap.live_experiment_processes(lambda sibling=sibling: sibling) == [
            f'pid {me + 50}: scripts/experiments/slot2_probe.py --execute-live']


def test_r3_program_label_never_records_an_option_value_or_an_argument():
    """Review round 3: round 2's label skipped an option but recorded the token after it, which is often the
    option's value (a password, a key file). Only the program's file name is recorded, plus, for Python, the
    script's file name, the -m module, '-c' or '-', read the way CPython reads its options (clusters included)."""
    cases = {'redis-server --requirepass s3cr3t --port 8000': 'redis-server',
             'ssh -i /Users/x/.ssh/id_prod -N -L 8000:localhost:8000 bastion': 'ssh',
             'node --require dotenv/config --api-key SECRETKEY server.js': 'node',
             'socat TCP-LISTEN:8000,fork EXEC:"curl -H Authorization:Bearer_s3cr3t"': 'socat',
             'env API_KEY=s3cr3t python serve.py': 'env',
             'python -W ignore serve.py --token t0k3n': 'python serve.py',
             'python3 -X importtime -m http.server 8000': 'python3 -m http.server',
             '/x/.venv/bin/python -m uvicorn app.main:app --port 8000': 'python -m uvicorn',
             'python -uW ignore /srv/serve.py': 'python serve.py',
             'python -Bm http.server 8000': 'python -m http.server',
             'python -mhttp.server 8000': 'python -m http.server',
             'python -Bc "serve(token=\'s3cr3t\')"': 'python -c',
             'python -cprint(1) s3cr3t': 'python -c',
             'python - s3cr3t': 'python -',
             'python -- serve.py s3cr3t': 'python serve.py',
             'python --check-hash-based-pycs s3cr3t serve.py': 'python',
             'python -W': 'python'}
    assert {command: gap.program_label(command) for command in cases} == cases


def test_r3_lsof_warnings_alone_mean_nothing_listens_and_are_suppressed():
    """Review round 3: an unreachable mounted volume makes lsof print a warning block whose continuation lines are
    indented (the block below is the shape measured on this machine with -b and without -w,
    prep/lsof-flags-probe-r3.txt). Round 2 read those lines as a failure, so every listener check failed closed:
    a refusal before the run, and a stop that ends the phase at a case start. Now lsof runs with -b (never stat a
    mount) and -w (no warnings), and a warning's continuation lines are skipped; anything else still fails."""
    calls = []
    block = ("lsof: WARNING: can't stat() smbfs file system /Volumes/share\n"
             "      Output information may be incomplete.\n"
             "      assuming \"dev=35000003\" from mount table\n")

    def returning(stderr, returncode=1):
        def run(argv, **kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=returncode, stdout='', stderr=stderr)
        return run
    assert gap.lsof_listeners(8000, run=returning(block + block)) == []
    assert calls[0][1:3] == ['-b', '-w'] and calls[0][3:] == ['-nP', '-iTCP:8000', '-sTCP:LISTEN', '-F', 'pcnt']
    # Still fail closed: a real error, alone or after a warning; an indented line that follows no warning.
    for stderr in ('lsof: status error on /dev: Permission denied\n',
                   block + 'lsof: status error on /dev: Permission denied\n',
                   '      Output information may be incomplete.\n'):
        with pytest.raises(OSError):
            gap.lsof_listeners(8000, run=returning(stderr))


def test_r3_the_ipv6_probe_still_runs_beside_an_identified_ipv4_listener():
    """An IPv4-only server never accepts on [::1]; a connection there means an IPv6 listener lsof did not list
    (another user's process), which stops the run even when lsof listed an identified IPv4 program."""
    found = gap.port_listeners(8000, lister=lambda port: [{'pid': 3, 'name': 'Python', 'type': 'IPv4',
                                                            'address': '*:8000'}],
                               commands={3: '/usr/bin/python3 -m http.server 8000'}.get,
                               accepts=lambda port, timeout: True)
    assert [(f['seen_by'], f['backend']) for f in found] == [('lsof', False), ('connect', None)]
    assert gap.listeners_stop_the_run(found)


def test_r3_either_backend_marker_alone_identifies_a_backend():
    """§6: a listener is a FaultLab backend if a process holding the socket runs `uvicorn` OR `app.main`. Found while
    fixing round 3: every earlier backend command line in these tests carried both markers, so dropping either one
    from BACKEND_COMMAND_MARKERS passed. The round-3 reviewer's mutant for this (L5) was killed only because its
    name, which contained the marker, reached the pytest command line that the real-socket test classifies."""
    commands = {5: '/x/.venv/bin/hypercorn app.main:app --bind 0.0.0.0:8000',
                6: '/x/.venv/bin/uvicorn main:app --port 8000'}
    for pid in (5, 6):
        found = gap.port_listeners(8000, lister=lambda port, pid=pid: [{'pid': pid, 'name': 'python3.12', 'type': 'IPv4',
                                                                          'address': '*:8000'}],
                                   commands=commands.get, accepts=lambda port, timeout: False)
        assert [(f['program'], f['backend']) for f in found] == [(('hypercorn', 'uvicorn')[pid - 5], True)]
        assert gap.listeners_stop_the_run(found)


@frozen_only
@pytest.mark.anyio
async def test_r3_a_listener_check_that_raises_at_a_case_start_stops_the_run_and_the_manifest_keeps_holm_tested(
        offline, monkeypatch):
    """The case-start listener check fails closed even if port_listeners itself raises. The same run's manifest
    carries holm_tested beside each family's Holm level (review round 2 row 4), so an untested family is visible
    without opening readout.json."""
    args, plan, policies = offline.make(cases=('MR-c2-r1', 'L-c2-r1'))

    def broken(*a, **k):
        raise RuntimeError('listing failed')

    def alter(n):
        if n == 3:
            monkeypatch.setattr(gap, 'port_listeners', broken)
    offline.hooks['before'] = alter
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'another_backend_listening' and [c['pairs'] for c in manifest['cases']] == [3]
    for family in gap.FAMILIES:
        assert set(manifest['readout']['families'][family]) == {'reading', 'p_exact_one_sided', 'holm_tested',
                                                                'holm_level'}


def test_r3_the_phase25_guard_and_this_guard_each_see_the_others_launch_once():
    """Cross-runner contract for the `ps` rule (review round 3): each runner, launched as its runbook says (Phase 26:
    `caffeinate -is ./.venv/bin/python …`, §10 step 7; Phase 25: `nohup caffeinate -is ./.venv/bin/python …`,
    its step 6), never refuses its own launch and sees the other's launch exactly once, by its Python process and
    never by its caffeinate helper. Runs the REAL Phase 25 guard as it is on disk (not pinned by this phase; see
    sibling_guards). The Phase 27 runner has no `ps` scan (§12); its half of the contract is the claim tests above."""
    phase25 = sibling_guards()['slot2_probe']
    me, shell = os.getpid(), os.getppid()
    p26 = ('./.venv/bin/python scripts/experiments/run_gap_probe.py --output artifacts/phase26-2026-09-24/run-1 '
           '--expect-protocol-sha256 S --execute-live --confirm-entity e')
    p25 = ('./.venv/bin/python scripts/experiments/slot2_probe.py --execute-live --confirm-entity e --out '
           'artifacts/phase25-2026-09-24/live --expect-plan-hash P --expect-harness-sha256 H --expect-protocol-sha256 S')

    def tree(mine, theirs):
        return [(shell, 1, '/bin/zsh -l'), (me, shell, mine), (me + 2, me, f'caffeinate -is {mine}'),
                (me + 40, 1, '/bin/zsh -l'), (me + 50, me + 40, theirs), (me + 51, me + 50, f'caffeinate -is {theirs}')]
    assert gap.live_experiment_processes(lambda: tree(p26, p25)[:3]) == []
    assert phase25.live_experiment_processes(lambda: tree(p25, p26)[:3]) == []
    assert gap.live_experiment_processes(lambda: tree(p26, p25)) == [
        f'pid {me + 50}: scripts/experiments/slot2_probe.py --execute-live']
    seen_by_phase25 = phase25.live_experiment_processes(lambda: tree(p25, p26))
    assert [entry.split(':')[0] for entry in seen_by_phase25] == [f'pid {me + 50}']


# Command lines for the paid-run rule, shared by the next test and prep/process_rule_alignment_r3.py.
R3_PAID_RUNS = {
    'python3.13t scripts/experiments/run_gap_probe.py --execute-live': 'scripts/experiments/run_gap_probe.py',
    '/usr/local/bin/python3.12-intel64 scripts/experiments/slot2_probe.py --execute-live':
        'scripts/experiments/slot2_probe.py',
    '/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python '
    '/home/s3cr3t/scripts/experiments/x.py --execute-live': 'scripts/experiments/x.py',
    '../.venv/bin/python experiments/run_gap_probe.py --execute-live --out artifacts/phase26-x/live':
        'experiments/run_gap_probe.py',
    'python --check-hash-based-pycs always scripts/experiments/x.py --execute-live': 'scripts/experiments/x.py',
    'python -W ignore -X dev scripts/experiments/slot2_probe.py --execute-live': 'scripts/experiments/slot2_probe.py',
    'python scripts/experiments/run_replication.py --ex': 'scripts/experiments/run_replication.py',
    'python scripts/experiments/native_baseline.py --e': 'scripts/experiments/native_baseline.py',
    'python scripts/experiments/x.py --out a --execute': 'scripts/experiments/x.py',
    # Found while fixing round 3: the path was cut at its last 'scripts/experiments/', which kept a directory after it.
    'python /x/scripts/experiments/s3cr3t/experiments/x.py --execute-live': 'experiments/x.py',
    'python /x/experiments/s3cr3t/scripts/experiments/x.py --execute-live': 'scripts/experiments/x.py'}
R3_NOT_RUNS = ('python x.py --execute-live',                          # bare name from inside scripts/experiments
               'python scripts/experiments/x.py --out artifacts/phase25-x/dry',
               'python scripts/experiments/x.py --expect-protocol-sha256 S --',
               'python -m scripts.experiments.x --execute-live',
               "python -c 'import x' scripts/experiments/x.py --execute-live",
               'python - scripts/experiments/x.py --execute-live',
               "/bin/zsh -c 'grep -- --execute-live scripts/experiments/x.py'",
               'caffeinate -is python scripts/experiments/x.py --execute-live',
               'node experiments/x.py --execute-live')


def test_r3_the_paid_run_rule_is_widened_as_the_phase25_rule_was():
    """Review round 3: the Phase 25 runner widened its token rule in the fail-closed direction (any interpreter
    named python*, any path ending in experiments/<name>.py, the value of --check-hash-based-pycs, and every prefix
    of --execute-live from --e). This runner's copy follows it, so the two stay the same rule; the entry still
    records only the pid and scripts/experiments/<name>.py or experiments/<name>.py, never the rest of the path."""
    assert {command: gap.paid_run_script(command) for command in R3_PAID_RUNS} == R3_PAID_RUNS
    assert [command for command in R3_NOT_RUNS if gap.paid_run_script(command)] == []
    rows = [(900000 + i, 1, command) for i, command in enumerate((*R3_PAID_RUNS, *R3_NOT_RUNS))]
    found = gap.live_experiment_processes(lambda: rows)
    assert found == [f'pid {900000 + i}: {script} --execute-live' for i, script in enumerate(R3_PAID_RUNS.values())]
    assert not any('s3cr3t' in entry or 'phase26-x' in entry for entry in found)


# Phase 28 (docs/part2/PHASE28_EXPERIMENT.md section 3.3, build item B4): Phase 26 ran on the Phase 22 tree
# (configuration 2cf63e93...). The Phase 28 backend change (completion_study.py, api.py) moves that
# configuration hash by design, so the test named below, which recomputes it from the code on disk, can only
# pass on the tree Phase 26 ran on. Elsewhere it is skipped with this reason rather than failing. The skip
# keys on the whole Phase 22 freeze, never on the asserted hash itself, so on the Phase 22 tree the test still
# runs and still checks the hash. Same pattern as test_lapse_probe.py's NEEDS_PHASE21_TREE (Phase 22, N3).
# The harness (run_gap_probe.py) is not edited.
NEEDS_PHASE22_TREE = frozenset({
    'test_the_phase17_settings_reproduce_the_phase22_configuration_hash_without_env',
})
for _name in NEEDS_PHASE22_TREE:
    globals()[_name] = pytest.mark.skipif(
        'not tree_is_phase22_frozen()',
        reason='needs the tree Phase 26 ran on (Phase 22 freeze, configuration 2cf63e93...); backend/app '
               'changed after it (Phase 28)')(globals()[_name])
