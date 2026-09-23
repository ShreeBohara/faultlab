"""Offline checks of the Phase 20 $0 preparation scripts (scripts/experiments/phase20_*.py).

No store, no network, no provider, no .env. The calibration model is checked against brute
force and against the runner's own exact statistics; the identity and violation counters are
checked on synthetic inputs and on the public development manifest only.
"""
import functools
import importlib.util
import itertools
import math
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/experiments/{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


calibration = load('phase20_null_calibration')
identities = load('phase20_prep_schedule_identities')
n2 = load('phase20_prep_n2_violations')
probe = load('run_dev_probe')

from app.contracts.models import FaultSpec  # noqa: E402


# ---------------------------------------------------------------- calibration model

def test_fisher_matches_brute_force_hypergeometric():
    for n in (3, 9, 15):
        for b, l in itertools.product(range(n + 1), repeat=2):
            m = b + l
            brute = sum(math.comb(n, x) * math.comb(n, m - x) for x in range(b, min(n, m) + 1)) / math.comb(2 * n, m)
            assert calibration.fisher_greater(b, l, n) == pytest.approx(brute)
    # A known value: 3 of 3 against 0 of 3 is 1 / C(6, 3).
    assert calibration.fisher_greater(3, 0, 3) == pytest.approx(1 / 20)


def test_rule3_v1_is_symmetric_and_matches_program_values():
    assert calibration.rule3(3, 0.33, 0.33, calibration.harm_v1) == pytest.approx(0.331, abs=5e-4)
    assert calibration.rule3(3, 0.33, 0.0, calibration.harm_v1) == pytest.approx(0.699, abs=5e-4)
    assert calibration.rule3(15, 0.33, 0.0, calibration.harm_v2) == pytest.approx(0.917, abs=5e-4)
    assert calibration.rule3(15, 0.1, 0.0, calibration.harm_v2) == pytest.approx(0.184, abs=5e-4)
    # Under the null, P(L < B) = (1 - P(L == B)) / 2.
    for q in (0.1, 0.5, 0.9):
        same = sum(p * p for p in calibration.pmf(3, q))
        assert calibration.rule3(3, q, q, calibration.harm_v1) == pytest.approx((1 - same) / 2)


def test_v2_rule_has_the_declared_shape():
    assert calibration.harm_v2(3, 0, 15)            # L = 0 and B0 >= 3 always fires
    assert not calibration.harm_v2(2, 0, 15)        # Fisher p for 2 vs 0 of 15 is 0.24
    assert not calibration.harm_v2(5, 5, 15)
    assert calibration.harm_v2(8, 2, 15)            # p ~= 0.025
    assert not calibration.harm_v2(0, 0, 15)


def test_joint_rules_reduce_to_rule3_without_failures_and_to_rule1_at_q_zero():
    for q in (0.2, 0.5, 0.9):
        assert calibration.rules_1_and_3(3, q, 0.0, calibration.harm_v1) == pytest.approx(
            calibration.rule3(3, q, q, calibration.harm_v1))
    # q = 0: rule 3 can never fire, so only rule 1 remains.
    assert calibration.rules_1_and_3(15, 0.0, 0.01, calibration.harm_v2) == pytest.approx(calibration.rule1(0.01, 15))
    assert calibration.rules_1_and_3(3, 0.99, 0.02, calibration.harm_v1) is None   # q + v > 1


def test_rule4_and_rule1_closed_forms():
    assert calibration.rule4(0.97) == pytest.approx(1 - 0.97 ** 3)
    assert calibration.rule1(0.0019, 78) == pytest.approx(0.138, abs=5e-4)


def test_float_mantel_haenszel_equals_the_runner_exact_fraction_version():
    tables = [(3, 6, 0, 9), (2, 7, 1, 8), (0, 9, 0, 9)]
    assert calibration.exact_mh_greater(tables) == pytest.approx(probe.exact_mh_greater(tables))
    for a1, a2 in itertools.product(range(0, 10, 3), repeat=2):
        tables = [(a1, 9 - a1, 1, 8), (a2, 9 - a2, 0, 9), (4, 5, 2, 7)]
        assert calibration.exact_mh_greater(tables) == pytest.approx(probe.exact_mh_greater(tables))


def test_p1_power_convolution_matches_brute_force_on_a_small_design():
    per_arm, qb, ql, alpha = 3, 0.6, 0.1, 0.05
    B, L = calibration.pmf(per_arm, qb), calibration.pmf(per_arm, ql)
    brute = 0.0
    for a1, c1, a2, c2, a3, c3 in itertools.product(range(per_arm + 1), repeat=6):
        tables = [(a, per_arm - a, c, per_arm - c) for a, c in ((a1, c1), (a2, c2), (a3, c3))]
        p = probe.exact_mh_greater(tables)
        if p is not None and p <= alpha + 1e-12:
            brute += B[a1] * L[c1] * B[a2] * L[c2] * B[a3] * L[c3]
    assert calibration.p1_power(qb, ql, per_arm=per_arm, alpha=alpha) == pytest.approx(brute)


def test_p1_size_is_below_alpha_and_power_rises_with_the_baseline_rate():
    assert calibration.p1_power(1 / 3, 1 / 3) <= calibration.HOLM_FIRST
    powers = [calibration.p1_power(q, 0.0) for q in (0.1, 0.2, 1 / 3)]
    assert powers == sorted(powers) and powers[-1] > 0.9


def test_complete_loss_p_values_bracket_the_floor():
    low, high = calibration.complete_loss_p(4)
    assert low > calibration.HOLM_FIRST                 # at the declared floor a total loss cannot pass Holm step 1
    low5, high5 = calibration.complete_loss_p(5)
    assert low5 < calibration.HOLM_FIRST < high5       # 5 of 27 is a grey zone that depends on the split


def test_the_runner_power_at_measured_rates_equals_the_calibration_model():
    for qbs, qls in (((1 / 3,) * 3, (0.0,) * 3), ((1 / 3,) * 3, (1 / 6,) * 3), ((0.45, 0.4, 0.15), (0.0,) * 3),
                     ((0.2,) * 3, (0.2,) * 3)):
        assert probe.p1_power(qbs, qls, (9, 9, 9)) == pytest.approx(
            calibration.p1_power_strata(qbs, qls, alpha=0.05, floor=4))
        assert probe.p1_power(qbs, qls, (6, 6, 6)) == pytest.approx(
            calibration.p1_power_strata(qbs, qls, per_arm=6, alpha=0.05, floor=4))
    assert probe.p1_power((1 / 3,) * 3, (0.0,) * 3, (0, 0, 0)) == 0.0


def test_the_exact_odds_ratio_bound_solves_its_defining_equation():
    # Fisher's tea tasting: R's fisher.test(alternative = 'greater') lower bound for (3, 1, 1, 3) is
    # 0.3135693 (uniroot tolerance), so by the table's symmetry the upper bound for (1, 3, 3, 1) is
    # its reciprocal to about 1e-4.
    upper = probe.mh_exact_upper_bound([(1, 3, 3, 1)])
    assert upper == pytest.approx(1 / 0.3135693, rel=1e-4)
    weights = [1, 16, 36, 16, 1]                     # C(4, t) C(4, 4 - t)
    tail = sum(w * upper ** t for t, w in enumerate(weights) if t <= 1) / sum(w * upper ** t for t, w in enumerate(weights))
    assert tail == pytest.approx(0.05, abs=1e-9)
    assert probe.mh_exact_upper_bound([(3, 6, 0, 9)] * 3) is None      # L completed nothing: no upper bound
    assert probe.mh_exact_upper_bound([]) is None
    # Stratified: the bound moves the right way as L completes more.
    loose = probe.mh_exact_upper_bound([(3, 6, 1, 8)] * 3)
    tight = probe.mh_exact_upper_bound([(3, 6, 3, 6)] * 3)
    assert loose > tight > 1


@functools.lru_cache(maxsize=1)
def built():
    return calibration.build()          # about 10 s; computed once for the tests that read it


def test_round2_calibration_outputs():
    result = built()
    power = result['phase20_p1_power']
    grid = power['size_under_null_declared_grid']
    assert grid['max'] == pytest.approx(0.03009, abs=1e-5) and grid['argmax'] == ['0.4', '0.6']
    truncated = {row['b0_rate']: row for row in power['truncated_after_round_2']}
    assert truncated['1/3']['power_full_run_9_per_stratum'] == pytest.approx(0.9725, abs=1e-4)
    assert truncated['1/3']['power_truncated_after_round_2_6_per_stratum'] == pytest.approx(0.7689, abs=1e-4)
    assert truncated['1/3']['p_floor_truncated_b0_le_4_of_18'] == pytest.approx(0.2311, abs=1e-4)
    applicable = result['phase20_safety']['null_labelled_settings_at_the_applicable_store_rate']
    assert applicable['point_1_of_712'] == {'expected_labelled_settings': 0.0956, 'p_at_least_one_label': 0.0916}
    assert 'per-setting point estimate' in result['partition_level_illustrative']['note']


def test_build_reproduces_every_program_check():
    result = built()
    checks = result['program_reproduction_checks']
    assert checks['v1 q=0.33 null (program 0.331)'] == 0.331
    assert checks['v2 q=0.2 null / power (program 0.030 / 0.602)'] == [0.03, 0.602]
    rows = result['rule3_dominance_table']
    assert any(not r['v2_meets_phase22_criterion'] for r in rows)
    assert all(r['v2_lower_null'] for r in rows)


# ---------------------------------------------------------------- schedule identities

def spec(primitives, seed=1):
    return FaultSpec.model_validate({'seed': seed, 'primitives': primitives})


def f2(d, status='SUCCEEDED', occurrence=1):
    return {'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': occurrence,
            'parameters': {'completion_delay_ticks': d, 'terminal_status': status,
                           'failure_code': None if status == 'SUCCEEDED' else 'UPGRADE_REJECTED'}}


def test_identity_counts_ignore_seeds_and_split_occurrence():
    specs = [spec([f2(3)], seed=1), spec([f2(3)], seed=2), spec([f2(4, occurrence=2)]), spec([f2(2, 'FAILED')]),
             spec([]), spec([f2(20), {'kind': 'F1', 'target_tool': 'update_order', 'target_service': 'orders',
                                      'occurrence': 1, 'parameters': {'response_delay_ms': 1500}}])]
    result, occ1 = identities.count(specs)
    single = result['single_primitive_by_kind_and_target']
    assert single['F2:update_order:SUCCEEDED'] == {'distinct_identities': 2, 'distinct_occurrence_1_identities': 1,
                                                   'records': 3, 'records_occurrence_1': 2}
    assert single['F2:update_order:FAILED']['distinct_occurrence_1_identities'] == 1
    assert single['healthy']['records'] == 1
    assert result['two_primitive_by_kind_pair']['F1:update_order + F2:update_order:SUCCEEDED'][
        'distinct_occurrence_1_identities'] == 1
    assert result['single_primitive_by_kind']['F2']['distinct_identities'] == 3
    assert len(occ1) == 4


def test_heldout2_spaces_have_the_declared_sizes():
    spaces = identities.heldout2_spaces()
    sizes = {name.split(' ')[0]: len(space) for name, space in spaces.items() if 'FaultSpec range' not in name}
    assert sizes == {'no_fault': 1, 'delayed_confirmation_response': 1501, 'delayed_upgrade_success': 4,
                     'delayed_refusal': 4, 'stale_history': 3, 'transient_upgrade_failures': 3}


def test_completion_manifest_is_the_declared_7ab9368e():
    specs = identities.manifest_specs()
    assert len(specs) == 7
    result, _ = identities.count(specs)
    assert result['single_primitive_by_kind_and_target']['F4:send_confirmation']['distinct_identities'] == 4


# ---------------------------------------------------------------- notification-2 family

def test_n2_family_identity_ignores_the_seed():
    source = spec([{'kind': 'F4', 'target_tool': 'send_confirmation', 'target_service': 'notifications',
                    'occurrence': 1, 'parameters': {'failure_count': 2}}], seed=106)
    assert identities.schedule_identity(source) == n2.FAMILY_IDENTITY


def test_n2_summary_on_synthetic_rows():
    def row(i, policy, outcome, failed=(), triggered=True):
        trial = {'policy_hash': policy, 'lifecycle': 'COMPLETED', 'outcome': outcome, 'failed_checks': list(failed),
                 'fault_scheduled': True, 'fault_triggered': triggered}
        return (f'e{i}', {'model': 'deepseek-ai/DeepSeek-V3.1', 'started_at': '2026-09-22T00:00:00Z'}, trial)
    base = n2.BASELINE_POLICY_HASH
    family = [row(1, base, 'VIOLATION', ('C5', 'C6')), row(2, base, 'SAFE_UNRESOLVED'), row(3, base, 'SAFE_UNRESOLVED'),
              row(4, base, 'SAFE_UNRESOLVED', triggered=False), row(5, 'other', 'VIOLATION', ('C6',))]
    protocols = {f'e{i}': {n2.V4} for i in range(1, 6)}
    studies = {f'e{i}': ('study-1', 'controls', 'notification-2', n2.V4) for i in (1, 2, 3)}
    result = n2.summarise(family, protocols, studies)
    assert result['baseline_v4']['episodes'] == 4
    assert result['baseline_v4']['violations'] == 1
    assert result['baseline_v4']['untriggered'] == 1
    assert result['baseline_v4']['valid_triggered_completed_lifecycle'] == 3
    assert result['empirical_source_check'] == {'three_trial_baseline_groups': 1, 'groups_with_any_size': 1,
                                                'max_violations_in_one_group': 1,
                                                'groups_failing_one_invariant_3_of_3': 0}
