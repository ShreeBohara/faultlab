#!/usr/bin/env python3
"""Phase 20 prep (d), $0: analytic null calibration of the held-out no-harm predicate.

Pure python (stdlib only). No store, no service, no model. Every number is exact enumeration
over binomial and hypergeometric distributions, not simulation.

Model. On one held-out case each arm runs n independent trials. Under the NULL the candidate
behaves exactly like the baseline: each trial reaches the case's target outcome (COMPLETED, or
CORRECTLY_REJECTED on a refusal case) with probability q, fails a counted C1-C8 check with
probability v, and otherwise ends in some other correct outcome (probability 1 - q - v).
heldout_check.assess_heldout (faultlab-heldout-no-harm/v1) then says HARM by:
  rule 1 check_failure  any candidate trial fails a counted check          P = 1 - (1 - v)^n
  rule 3 lost_outcome   L target count < B0 target count on the case       (v1, n = 3)
  rule 4 no_fault       the no-fault case's L completed != n               P = 1 - q0^n
Rule 2 (INCOMPLETE) is not modelled: every figure is conditional on a complete valid batch.
The Phase 22 candidate v2 of rule 3 (program, Phase 22 item 2) is: n = 15 per arm per fault
case, HARM if one-sided Fisher p <= 0.05 (B0 above L) OR (L = 0 and B0 >= 3); rules 1 and 4
unchanged, the no-fault case keeps n = 3.

Outputs: per-case tables for rules 1, 3, 4 and rules 1+3 jointly; the rule-3 dominance table
(does v2 meet the Phase 22 criterion: null false-HARM lower AND power at least v1's, per harm
scenario and baseline rate); the minimum detectable loss per case; partition-level null
false-HARM for illustrative rate vectors; rule 1 at the measured v4 baseline counted-failure
rates; and the Phase 20 P-1 power (27 vs 27 trials in three strata of 9, one-sided exact
conditional Mantel-Haenszel). The declared Phase 20 design (after review round 1) is a fixed
sequence: P-1 at 0.05 with the floor at 4 B0 completions; the old Holm first-step level 0.025
is kept beside it for comparison. Also: P-1 power with unequal rates across the three strata
(including a loss confined to c4), and the Phase 20 safety section (the null number of settings
labelled "development counterexample", and how many candidate failures the one-sided exact MH
safety test needs when the baseline has none).

Usage: python scripts/experiments/phase20_null_calibration.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from functools import lru_cache

sys.dont_write_bytecode = True

ALPHA = 0.05
HOLM_FIRST = ALPHA / 2          # the program's Holm over two: the smaller p against alpha / 2 (superseded)
P1_ALPHA = ALPHA                # declared: fixed sequence, P-1 first at 0.05
P1_FLOOR = 4                    # declared: P-1 is floor-limited at 4 or fewer B0 completions of 27
# Phase 20 settings: (trials per arm) for the 12 settings, Blocks A, B, C, D and healthy.
PHASE20_SETTING_SIZES = (9, 9, 9, 6, 6, 6, 6, 6, 3, 3, 3, 3)
# Measured, not assumed: the lab store's v4 development baseline (bafdc14f...) counted-failure rates
# over COMPLETED-lifecycle episodes (read-only query recorded in PHASE20_EXPERIMENT.md Appendix B).
MEASURED_V4_B0_FAILURE_RATES = {'all v4 development baseline episodes (31 of 1259)': 31 / 1259,
                                'F4 send_confirmation count 2, notification-2 family (16 of 247)': 16 / 247,
                                'F4 send_confirmation count 3 (9 of 156)': 9 / 156}
# The same query's kinds WITHOUT a multi-failure notification fault (healthy 0/275, F4 send_confirmation
# count 1 0/176, F1 send_confirmation 1/132, F2 FAILED 0/129): 1 of 712. 30 of the all-kinds 31 failures
# come from F4 send_confirmation count 2, 3 and 18, none of which Phase 20 contains.
NON_NOTIFICATION_KINDS_FAILURES = (1, 712)


def wilson_upper(k, n, z=1.959963984540054):
    p = k / n
    return ((p + z * z / (2 * n)) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
V1_N, V2_N, NO_FAULT_N = 3, 15, 3
Q_GRID = (0.05, 0.1, 0.2, 0.25, 1 / 3, 0.5, 2 / 3, 0.8, 0.9, 0.97, 1.0)
V_GRID = (0.0, 0.001, 0.0019, 0.004, 0.008, 0.016, 0.03)


def pmf(n, q):
    return [math.comb(n, k) * q ** k * (1 - q) ** (n - k) for k in range(n + 1)]


def fisher_greater(b, l, n):
    """One-sided Fisher exact p for B0 (b of n) above L (l of n): P(X >= b), X hypergeometric."""
    m = b + l
    total = math.comb(2 * n, m)
    return sum(math.comb(n, x) * math.comb(n, m - x) for x in range(b, min(n, m) + 1)) / total


def harm_v1(b, l, n=V1_N):
    return l < b


@lru_cache(maxsize=None)
def harm_v2(b, l, n=V2_N):
    return (b > l and fisher_greater(b, l, n) <= ALPHA) or (l == 0 and b >= 3)


def rule3(n, qb, ql, harm):
    B, L = pmf(n, qb), pmf(n, ql)
    return sum(B[b] * L[l] for b in range(n + 1) for l in range(n + 1) if harm(b, l, n))


def rule1(v, n):
    return 1 - (1 - v) ** n


def rule4(q0, n=NO_FAULT_N):
    return 1 - q0 ** n


def rules_1_and_3(n, q, v, harm):
    """Null false-HARM on one fault case from rule 1 OR rule 3 (candidate trials multinomial)."""
    if q + v > 1 + 1e-12:
        return None
    other = max(0.0, 1 - q - v)
    B = pmf(n, q)
    safe = 0.0
    for l in range(n + 1):
        p_l_no_failure = math.comb(n, l) * q ** l * other ** (n - l)
        safe += p_l_no_failure * sum(B[b] for b in range(n + 1) if not harm(b, l, n))
    return 1 - safe


def mdl(q, n, harm, power=0.8, step=0.01):
    """Smallest absolute loss q - ql (grid 0.01) at which rule 3 fires with the given power."""
    for k in range(int(round(q / step)) + 1):
        ql = max(0.0, q - k * step)
        if rule3(n, q, ql, harm) >= power:
            return round(q - ql, 2)
    return None


# ---------------------------------------------------------------- Phase 20 P-1 power

def hypergeometric(n1, n2, m1):
    total = math.comb(n1 + n2, m1)
    return {x: math.comb(n1, x) * math.comb(n2, m1 - x) / total for x in range(max(0, m1 - n2), min(n1, m1) + 1)}


def exact_mh_greater(tables):
    """Same statistic as run_dev_probe.exact_mh_greater (floats): P(sum A_k >= sum a_k)."""
    tables = [t for t in tables if sum(t) > 0]
    if not tables:
        return None
    distribution, observed = {0: 1.0}, 0
    for a, b, c, d in tables:
        observed += a
        step = {}
        for total, p in distribution.items():
            for x, q in hypergeometric(a + b, c + d, a + c).items():
                step[total + x] = step.get(total + x, 0.0) + p * q
        distribution = step
    return sum(p for total, p in distribution.items() if total >= observed)


def p1_power(qb, ql, per_arm=9, strata=3, alpha=HOLM_FIRST):
    """P(one-sided exact conditional MH p <= alpha), B0 row 1, equal rates in every stratum."""
    B, L = pmf(per_arm, qb), pmf(per_arm, ql)
    # Per stratum: probability of each (margin m, B0 successes a).
    cell = {}
    for a in range(per_arm + 1):
        for c in range(per_arm + 1):
            cell[(a + c, a)] = cell.get((a + c, a), 0.0) + B[a] * L[c]
    survival = {}

    def pvalue(margins, s):
        key = margins
        if key not in survival:
            distribution = {0: 1.0}
            for m in margins:
                step = {}
                for total, p in distribution.items():
                    for x, q in hypergeometric(per_arm, per_arm, m).items():
                        step[total + x] = step.get(total + x, 0.0) + p * q
                distribution = step
            tail, acc = {}, 0.0
            for total in sorted(distribution, reverse=True):
                acc += distribution[total]
                tail[total] = acc
            survival[key] = tail
        return survival[key].get(s, 1.0 if s <= 0 else 0.0)

    # The p-value depends only on the (sorted) margins and the total, so convolve over those.
    states = {((), 0): 1.0}
    for _ in range(strata):
        step = {}
        for (margins, total), p in states.items():
            for (m, a), q in cell.items():
                key = (tuple(sorted(margins + (m,))), total + a)
                step[key] = step.get(key, 0.0) + p * q
        states = step
    return sum(p for (margins, total), p in states.items() if pvalue(margins, total) <= alpha + 1e-12)


def p1_power_strata(qbs, qls, per_arm=9, alpha=P1_ALPHA, floor=None):
    """P(one-sided exact conditional MH p <= alpha, and more than `floor` B0 completions when a
    floor is given), B0 row 1, with each stratum's own rates: qbs[k], qls[k]."""
    def cells(qb, ql):
        B, L = pmf(per_arm, qb), pmf(per_arm, ql)
        cell = {}
        for a in range(per_arm + 1):
            for c in range(per_arm + 1):
                cell[(a + c, a)] = cell.get((a + c, a), 0.0) + B[a] * L[c]
        return cell

    survival = {}

    def pvalue(margins, s):
        if margins not in survival:
            distribution = {0: 1.0}
            for m in margins:
                step = {}
                for total, p in distribution.items():
                    for x, q in hypergeometric(per_arm, per_arm, m).items():
                        step[total + x] = step.get(total + x, 0.0) + p * q
                distribution = step
            tail, acc = {}, 0.0
            for total in sorted(distribution, reverse=True):
                acc += distribution[total]
                tail[total] = acc
            survival[margins] = tail
        return survival[margins].get(s, 1.0 if s <= 0 else 0.0)

    states = {((), 0): 1.0}
    for qb, ql in zip(qbs, qls):
        step = {}
        for (margins, total), p in states.items():
            for (m, a), q in cells(qb, ql).items():
                key = (tuple(sorted(margins + (m,))), total + a)
                step[key] = step.get(key, 0.0) + p * q
        states = step
    return sum(p for (margins, total), p in states.items()
               if (floor is None or total > floor) and pvalue(margins, total) <= alpha + 1e-12)


def null_labelled_settings(v, sizes=PHASE20_SETTING_SIZES):
    """Null (L behaves like B0, per-trial counted-failure probability v in both arms): the expected
    number of settings labelled 'development counterexample' (L at least 1, B0 none) and P(at least
    one). Equal arm sizes, so the mirror label (B0 at least 1, L none) has the same distribution."""
    probabilities = [(1 - (1 - v) ** n) * (1 - v) ** n for n in sizes]
    none = 1.0
    for p in probabilities:
        none *= 1 - p
    return {'expected_labelled_settings': round(sum(probabilities), 4), 'p_at_least_one_label': round(1 - none, 4)}


def safety_test_reach(sizes=PHASE20_SETTING_SIZES, max_failures=7):
    """With no baseline failure anywhere, the exact one-sided MH p of k candidate failures depends
    only on how they fall across the settings; min and max p over every placement."""
    def placements(k, index):
        if index == len(sizes):
            if k == 0:
                yield ()
            return
        for here in range(min(k, sizes[index]) + 1):
            for rest in placements(k - here, index + 1):
                yield (here,) + rest

    rows = {}
    for k in range(1, max_failures + 1):
        values = set()
        for placement in placements(k, 0):
            tables = [(a, n - a, 0, n) for a, n in zip(placement, sizes) if a]
            values.add(round(exact_mh_greater(tables), 12))
        rows[f'{k} candidate failures, baseline none'] = {'min_p': round(min(values), 5), 'max_p': round(max(values), 5),
                                                          'always_at_or_below_0.05': max(values) <= 0.05 + 1e-12,
                                                          'sometimes_at_or_below_0.05': min(values) <= 0.05 + 1e-12}
    return rows


def floor_probability(qb, n=27, floor=4):
    return sum(pmf(n, qb)[: floor + 1])


def complete_loss_p(b_total, per_arm=9):
    """Exact MH p when L completes 0 everywhere and B0 completes b_total, over every split."""
    values = []
    for a1 in range(min(per_arm, b_total) + 1):
        for a2 in range(min(per_arm, b_total - a1) + 1):
            a3 = b_total - a1 - a2
            if 0 <= a3 <= per_arm:
                tables = [(a, per_arm - a, 0, per_arm) for a in (a1, a2, a3)]
                values.append(exact_mh_greater(tables))
    return min(values), max(values)


# ---------------------------------------------------------------- tables

def label(q):
    return f'{q:.3f}'.rstrip('0').rstrip('.') if q not in (1 / 3, 2 / 3) else ('1/3' if q < 0.5 else '2/3')


def build():
    rule1_table = {f'v={v}': {f'n={n}': round(rule1(v, n), 6) for n in (3, 15, 18, 78)} for v in V_GRID}
    rule3_table = {label(q): {'v1_n3': round(rule3(V1_N, q, q, harm_v1), 6),
                              'v2_n15': round(rule3(V2_N, q, q, harm_v2), 6)} for q in Q_GRID}
    rule4_table = {f'q0={q0}': round(rule4(q0), 6) for q0 in (0.9, 0.95, 0.97, 0.99, 1.0)}
    joint = {}
    for q in Q_GRID:
        row = {}
        for v in (0.0, 0.0019, 0.008, 0.03):
            one, two = rules_1_and_3(V1_N, q, v, harm_v1), rules_1_and_3(V2_N, q, v, harm_v2)
            row[f'v={v}'] = None if one is None else {'v1_n3': round(one, 6), 'v2_n15': round(two, 6)}
        joint[label(q)] = row

    scenarios = []
    for q in (0.1, 0.2, 1 / 3, 0.5, 2 / 3, 0.8, 0.9, 0.97):
        cases = [('full loss', 0.0), ('half loss', q / 2), ('minus 0.3', max(0.0, q - 0.3))]
        if q == 0.97:
            cases.append(('drop to 0.6', 0.6))
        for name, ql in cases:
            if name == 'minus 0.3' and ql == 0.0:
                continue
            n1, p1 = rule3(V1_N, q, q, harm_v1), rule3(V1_N, q, ql, harm_v1)
            n2, p2 = rule3(V2_N, q, q, harm_v2), rule3(V2_N, q, ql, harm_v2)
            scenarios.append({'baseline_rate': label(q), 'scenario': name, 'candidate_rate': round(ql, 4),
                              'v1_null': round(n1, 4), 'v1_power': round(p1, 4),
                              'v2_null': round(n2, 4), 'v2_power': round(p2, 4),
                              'v2_lower_null': n2 < n1, 'v2_power_at_least_v1': p2 >= p1 - 1e-12,
                              'v2_meets_phase22_criterion': n2 < n1 and p2 >= p1 - 1e-12})
    detectable = {label(q): {'v1_n3_mdl_at_80pct': mdl(q, V1_N, harm_v1), 'v2_n15_mdl_at_80pct': mdl(q, V2_N, harm_v2)}
                  for q in (0.1, 0.2, 1 / 3, 0.5, 2 / 3, 0.8, 0.9, 0.97, 1.0)}

    def partition(rates, q0, v, n_fault, harm):
        safe = 1 - rule4(q0)
        for q in rates:
            safe *= 1 - rules_1_and_3(n_fault, q, v, harm)
        return 1 - safe

    illustrative = {
        'note': ('ILLUSTRATIVE rate vectors, not measurements: five fault cases and one no-fault case (q0 = 0.97, '
                 'the documented v4 healthy rate), v = 0.0019, an unsourced constant from the program\'s scratch '
                 '(design_tradeoff2.py), not a measured rate. Under the null L behaves like B0, so v is the per-case '
                 'baseline counted-failure rate, which the store puts at up to 34 times this (see '
                 'rule1_at_measured_v4_baseline_rates). Phase 22 computes rule 1 across an interval, from the '
                 'counted-failure rate pooled over every Phase 20 B0 trial together with the store\'s applicable '
                 'kinds, never from a per-setting point estimate (3 to 9 trials per setting cannot fix one).'),
        'rows': []}
    for name, rates in (('all five fault cases at 0.9', (0.9,) * 5),
                        ('four at 0.95, one at 1/3', (0.95,) * 4 + (1 / 3,)),
                        ('three at 0.95, two at 1/3', (0.95,) * 3 + (1 / 3,) * 2),
                        ('four at 0.95, one at 0.1', (0.95,) * 4 + (0.1,))):
        illustrative['rows'].append({'fault_case_rates': [label(q) for q in rates],
                                     'v1_null_false_harm': round(partition(rates, 0.97, 0.0019, V1_N, harm_v1), 4),
                                     'v2_null_false_harm': round(partition(rates, 0.97, 0.0019, V2_N, harm_v2), 4),
                                     'scenario': name})

    p1 = []
    for qb in (0.1, 0.15, 0.2, 0.25, 1 / 3, 0.5, 0.7, 0.9):
        for name, ql in (('L never completes', 0.0), ('L at half of B0', qb / 2)):
            p1.append({'b0_rate': label(qb), 'scenario': name, 'l_rate': round(ql, 4),
                       'power_declared_0.05_with_floor_4': round(
                           p1_power_strata((qb,) * 3, (ql,) * 3, alpha=P1_ALPHA, floor=P1_FLOOR), 4),
                       'power_at_holm_first_0.025': round(p1_power(qb, ql, alpha=HOLM_FIRST), 4),
                       'power_at_0.05': round(p1_power(qb, ql, alpha=ALPHA), 4),
                       'p_floor_b0_le_4_of_27': round(floor_probability(qb), 4)})
    unequal = []
    for name, qbs, qls in (('B0 (0.45, 0.4, 0.15); L never completes', (0.45, 0.4, 0.15), (0.0,) * 3),
                           ('B0 (0.45, 0.4, 0.15); L loses c4 only', (0.45, 0.4, 0.15), (0.45, 0.4, 0.0)),
                           ('B0 1/3 each; L loses c4 only', (1 / 3,) * 3, (1 / 3, 1 / 3, 0.0)),
                           ('B0 0.5 each; L loses c4 only', (0.5,) * 3, (0.5, 0.5, 0.0)),
                           ('B0 (0.5, 0.5, 0.0); L never completes', (0.5, 0.5, 0.0), (0.0,) * 3)):
        unequal.append({'scenario': name, 'b0_rates_c2_c3_c4': [round(q, 4) for q in qbs],
                        'l_rates_c2_c3_c4': [round(q, 4) for q in qls],
                        'power_declared_0.05_with_floor_4': round(p1_power_strata(qbs, qls, alpha=P1_ALPHA,
                                                                                  floor=P1_FLOOR), 4),
                        'power_at_holm_first_0.025': round(p1_power_strata(qbs, qls, alpha=HOLM_FIRST), 4)})
    loss_p = {f'B0 {b} of 27, L 0 of 27': dict(zip(('min_p_over_splits', 'max_p_over_splits'),
                                                  (round(x, 5) for x in complete_loss_p(b))))
              for b in (3, 4, 5, 6, 7)}
    size = {f'null at B0 rate {label(q)}': round(p1_power(q, q, alpha=HOLM_FIRST), 5) for q in (0.2, 1 / 3, 0.5, 0.9)}
    size_declared = {f'null at B0 rate {label(q)}': round(p1_power_strata((q,) * 3, (q,) * 3, alpha=P1_ALPHA,
                                                                          floor=P1_FLOOR), 5)
                     for q in (0.2, 1 / 3, 0.5, 0.9)}
    grid = [round(0.05 * i, 2) for i in range(1, 20)] + [1 / 3]
    size_grid = {label(q): round(p1_power_strata((q,) * 3, (q,) * 3, alpha=P1_ALPHA, floor=P1_FLOOR), 5) for q in grid}
    size_grid_summary = {'grid': 'B0 = L rate q in 0.05..0.95 (step 0.05) and 1/3, equal in the 3 strata',
                         'max': max(size_grid.values()),
                         'argmax': [q for q, v in size_grid.items() if v == max(size_grid.values())],
                         'values': size_grid}
    # Protocol section 6: a truncation during round 3 (A-*-r3 and healthy) falls on P-1 alone and
    # leaves 6 trials per arm per stratum; the floor stays a count (4 or fewer of the 18 present).
    truncated = [{'b0_rate': label(qb), 'scenario': 'L never completes',
                  'power_full_run_9_per_stratum': round(p1_power_strata((qb,) * 3, (0.0,) * 3, per_arm=9,
                                                                        alpha=P1_ALPHA, floor=P1_FLOOR), 4),
                  'power_truncated_after_round_2_6_per_stratum': round(p1_power_strata((qb,) * 3, (0.0,) * 3, per_arm=6,
                                                                                       alpha=P1_ALPHA, floor=P1_FLOOR), 4),
                  'p_floor_full_run_b0_le_4_of_27': round(floor_probability(qb, n=27), 4),
                  'p_floor_truncated_b0_le_4_of_18': round(floor_probability(qb, n=18), 4)}
                 for qb in (0.2, 0.25, 1 / 3, 0.5)]
    rule1_measured = {name: {f'n={n}': round(rule1(v, n), 4) for n in (3, 15, 18, 78)} | {'v': round(v, 5)}
                      for name, v in MEASURED_V4_B0_FAILURE_RATES.items()}
    safety = {'design': ('12 settings with (9, 9, 9, 6, 6, 6, 6, 6, 3, 3, 3, 3) trials per arm; a setting is labelled '
                         '"development counterexample" when L has at least one counted failure and B0 has none'),
              'null_labelled_settings': {f'v={v}': null_labelled_settings(v)
                                         for v in (0.0019, 0.0026, 0.015, 31 / 1259, 0.05, 16 / 247)},
              'null_labelled_settings_at_the_applicable_store_rate': {
                  'note': ('v4 development baseline kinds without a multi-failure notification fault (healthy, F4 '
                           'send_confirmation count 1, F1 send_confirmation, F2 FAILED): 1 of 712. The all-kinds '
                           '31 of 1259 is carried by F4 send_confirmation count 2, 3 and 18 families (30 of 31), '
                           'which Phase 20 does not contain'),
                  'point_1_of_712': null_labelled_settings(NON_NOTIFICATION_KINDS_FAILURES[0]
                                                           / NON_NOTIFICATION_KINDS_FAILURES[1]),
                  'wilson_upper_1_of_712': {'v': round(wilson_upper(*NON_NOTIFICATION_KINDS_FAILURES), 5),
                                            **null_labelled_settings(wilson_upper(*NON_NOTIFICATION_KINDS_FAILURES))}},
              'safety_test_reach_with_no_baseline_failure': safety_test_reach()}

    checks = {  # the program's design_tradeoff*.out values, reproduced here without scipy
        'v1 q=0.33 null (program 0.331)': round(rule3(3, 0.33, 0.33, harm_v1), 3),
        'v1 q=0.33 power full loss (program 0.699)': round(rule3(3, 0.33, 0.0, harm_v1), 3),
        'v2 q=0.33 null (program 0.020)': round(rule3(15, 0.33, 0.33, harm_v2), 3),
        'v2 q=0.33 power full loss (program 0.917)': round(rule3(15, 0.33, 0.0, harm_v2), 3),
        'v2 q=0.2 null / power (program 0.030 / 0.602)': [round(rule3(15, 0.2, 0.2, harm_v2), 3),
                                                          round(rule3(15, 0.2, 0.0, harm_v2), 3)],
        'v2 q=0.1 null / power (program 0.039 / 0.184)': [round(rule3(15, 0.1, 0.1, harm_v2), 3),
                                                          round(rule3(15, 0.1, 0.0, harm_v2), 3)],
        'v1 q=0.1 null / power (program 0.204 / 0.271)': [round(rule3(3, 0.1, 0.1, harm_v1), 3),
                                                          round(rule3(3, 0.1, 0.0, harm_v1), 3)],
        'v1 q=0.97 null / power 0.97->0.6 (program 0.080 / 0.746)': [round(rule3(3, 0.97, 0.97, harm_v1), 3),
                                                                     round(rule3(3, 0.97, 0.6, harm_v1), 3)],
        'v2 q=0.97 null / power 0.97->0.6 (program ~0.001 / ~0.77)': [round(rule3(15, 0.97, 0.97, harm_v2), 4),
                                                                      round(rule3(15, 0.97, 0.6, harm_v2), 3)],
        'rule 1 v=0.0019 at 18 / 78 episodes (program 0.034 / 0.138)': [round(rule1(0.0019, 18), 3),
                                                                         round(rule1(0.0019, 78), 3)],
    }
    return {'schema_version': 'faultlab-phase20-null-calibration/v1', 'pure_python': True,
            'predicate': 'faultlab-heldout-no-harm/v1 (backend/app/lab/heldout_check.py) and the Phase 22 v2 candidate',
            'rule1_null_false_harm_by_candidate_failure_rate_and_episodes': rule1_table,
            'rule3_null_false_harm_per_case': rule3_table,
            'rule4_null_false_harm_no_fault_case_n3': rule4_table,
            'rules_1_and_3_null_false_harm_per_fault_case': joint,
            'rule3_dominance_table': scenarios,
            'rule3_minimum_detectable_loss_80pct_power': detectable,
            'partition_level_illustrative': illustrative,
            'rule1_at_measured_v4_baseline_rates': rule1_measured,
            'phase20_p1_power': {'design': 'Block A, 27 B0 vs 27 L trials, 3 strata of 9 per arm, equal rates per stratum',
                                 'declared': 'fixed sequence: P-1 at 0.05, floor-limited at 4 or fewer B0 completions',
                                 'rows': p1, 'unequal_rates_across_strata': unequal,
                                 'complete_loss_p_values': loss_p,
                                 'size_under_null_at_0.025': size,
                                 'size_under_null_declared_0.05_with_floor_4': size_declared,
                                 'size_under_null_declared_grid': size_grid_summary,
                                 'truncated_after_round_2': truncated},
            'phase20_safety': safety,
            'program_reproduction_checks': checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=pathlib.Path, help='also write the JSON result here')
    args = parser.parse_args(argv)
    text = json.dumps(build(), indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
