#!/usr/bin/env python3
"""Phase 22, $0: calibration of the held-out predicate v2 against v1 at the measured baseline rates.

Two parts.

1. Measurement (read-only SQLite, `mode=ro`). Baseline (policy bafdc14f..., the empty policy-v0)
   rates for each heldout-2 case KIND, from v4 development episodes only:
     - the Phase 20 run store (artifacts/phase20-2026-09-23/run-1/lab.sqlite3);
     - the main store (artifacts/lab.sqlite3).
   Only development-split private inputs are joined, so no promotion, final-audit or
   portability recipe is ever read, and no heldout-2 partition is read (none exists yet).
   An episode is v4 if one of its actor_output events carries the v4 context (as in Phase 20
   prep (e)). A trial belongs to a kind if its schedule identity (seed ignored) is in that
   kind's heldout-2 draw space, taken from make_heldout_partition.draw_spaces(). Rates:
     q  target rate: COMPLETED (CORRECTLY_REJECTED on the refusal kind) among VALID B0 trials
        (valid_trial: rule 3 is only reached when every pair is valid and triggered);
     v  counted-failure rate, heldout_check.harmful over EVERY B0 trial (Phase 20 section 7.6:
        pooled over every Phase 20 B0 trial together with the store's applicable v4 kinds,
        section 7.3: every v4 development B0 trial except F4 send_confirmation with
        failure_count >= 2; reported at the point rate and at the Wilson upper bound);
     u  untriggered rate: fault scheduled and not triggered, over every v4 trial of the kind
        (both arms: the lapse behind it is the Actor's), plus a mechanism proxy for the
        upgrade-side kinds (v4 episodes that never dispatch get_order / update_order at all).
   Every rate is quoted with n and a Wilson 95% interval.

2. Enumeration (pure python, exact binomial / hypergeometric sums, no simulation). Under the
   NULL the candidate behaves exactly like the baseline: per trial it reaches the target with
   probability q, fails a counted check with probability v, else ends in another correct outcome.
     v1 (faultlab-heldout-no-harm/v1, Phase 18): 3 trials per arm per case. Rule 1: HARM on any
        candidate failure. Rule 3: HARM if L's target count < B0's. Rule 4: HARM if the no-fault
        case's L does not complete 3 of 3.
     v2 (the program's declared rule, Phase 22 item 2): rules 1 and 4 unchanged (no-fault case
        still 3 trials), rule 3 on 15 trials per arm per fault case: HARM if one-sided Fisher
        p <= 0.05 (B0 above L) OR (L = 0 and B0 >= 3).
   Per case: rule-3 false-HARM under the null; power against a total loss (L rate 0) and a
   halving (L rate q/2); the minimum detectable absolute loss at 80% power (grid 0.01). Each at
   the point rate, and worst case over the rate's Wilson interval (Phase 20 section 7.6). Then
   the declared criterion (v2 matches or beats v1's power on each harm scenario at the measured
   rates AND has lower null false-HARM), the whole-partition P(HARM | policy has no effect), and
   P(verdict within 3 attempts) given the untriggered exposure.

   Added in Phase 22 review round 1 (the earlier keys are unchanged):
     - small losses on the high-rate cases (d = 0.1, 0.2, 0.25 at the point rates and at 0.975),
       the d from which v2's power reaches v1's, the MDL at 50% as well as 80% power, v2's
       detection floor (the largest L that fires for each B0 count of 15), and the program's
       '0.97 drops to 0.6' scenario;
     - the declared criterion read with Phase 20 section 7.6's worst-case values over the Wilson
       intervals, and, for the two kinds with unmeasured drawable identities, over 0 to 1;
     - the rule-1 pool's failing episodes, and the pool without the Phase 19 lab-defect (clock
       drift) episodes, read from artifacts/phase19-2026-09-23/clock-drift-and-masking-all-worlds.txt;
     - Phase 24 outcomes within 1, 2 and 3 attempts, for v1 and v2, for a policy with no effect
       and for harmful policies (P(HARM), P(NO_HARM), P(no verdict)), so every PHASE24 section 7
       figure comes from this file;
     - provenance: this script's sha256 and the inputs' paths, sizes, times and sha256.

The rule-3 arithmetic is imported from phase20_null_calibration.py (the Phase 20 prep, unchanged)
so both phases use one method.

Usage: python scripts/experiments/phase22_predicate_calibration.py [--store PATH] [--phase20-store PATH]
                                                                   [--out FILE]
Prints a text report; --out also writes the full JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(HERE))

import make_heldout_partition as partition  # noqa: E402  (draw spaces only; no seed, no partition)
import phase20_null_calibration as p20  # noqa: E402  (pmf, Fisher, harm_v1, harm_v2, rule3, rules_1_and_3, mdl)
from app.contracts.models import FaultSpec  # noqa: E402
from app.lab.challenge import schedule_identity  # noqa: E402

SCHEMA = 'faultlab-phase22-predicate-calibration/v1'
BASELINE_POLICY_HASH = 'bafdc14f280cd47441baf69006e8ca55885ca0349667f2695f57e40b3b8926fb'
V4 = 'faultlab-actor-context/v4-indexed-evidence'
MAIN_STORE = ROOT / 'artifacts/lab.sqlite3'
PHASE20_STORE = ROOT / 'artifacts/phase20-2026-09-23/run-1/lab.sqlite3'
V1_N, V2_N, NO_FAULT_N = 3, 15, 3
FAULT_KINDS = ('delayed_confirmation_response', 'delayed_upgrade_success', 'delayed_refusal', 'stale_history',
               'transient_upgrade_failures')
TARGET = {name: 'CORRECTLY_REJECTED' if name == 'delayed_refusal' else 'COMPLETED' for name in partition.draw_spaces()}
ATTEMPTS = 3
POWER = 0.8
INTERVAL_GRID = 101
SUP_GRID = 1001
PHASE20_FIGURES = {'store_applicable_b0_failures': (1, 712), 'phase20_pooled_all_b0': (0, 69),
                   'transient_upgrade_failures_b0_completed': (2, 27)}
# Review round 1 additions.
SMALL_LOSSES = (0.1, 0.2, 0.25)
HIGH_RATE_KINDS = FAULT_KINDS[:4]
PROBE_RATE = 0.975             # the no-fault rate, and a plausible lapse ceiling on every case
PROGRAM_SCENARIO = (0.97, 0.6)  # the program's table: a 0.97 baseline that drops to 0.6
DRIFT_ARTIFACT = ROOT / 'artifacts/phase19-2026-09-23/clock-drift-and-masking-all-worlds.txt'
# Kinds whose drawable identities are only partly measured (Phase 20 section 7.6: the unmeasured
# ones take the rate's full range 0 to 1; PHASE22_EXPERIMENT.md section 2 row 13).
PARTLY_MEASURED_KINDS = ('delayed_upgrade_success', 'stale_history')
PHASE24_ATTEMPTS = (1, 2, 3)


def wilson(k, n, z=1.959963984540054):
    if not n:
        return None
    p = k / n
    denominator = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0.0, (centre - half) / denominator), min(1.0, (centre + half) / denominator)]


def rate(k, n):
    return {'k': k, 'n': n, 'rate': (k / n) if n else None, 'wilson_95': wilson(k, n)}


def r(value, places=4):
    return None if value is None else round(value, places)


# ---------------------------------------------------------------- measurement (read-only)

def kind_of_identity():
    """{schedule identity: (kind, parameter label, in 7ab9368e)} over the heldout-2 draw spaces."""
    completion = partition.excluded_identities(partition.completion_manifest())
    found = {}
    for name, (_, _, specs) in partition.draw_spaces().items():
        for spec in specs:
            primitives = spec['primitives']
            label = 'no fault' if not primitives else ', '.join(f'{k}={v}' for k, v in sorted(
                primitives[0]['parameters'].items()) if v is not None and k not in ('failure_code',))
            never_drawn = partition.identity(spec) in completion and name not in partition.NOVELTY_EXEMPT
            found[partition.identity(spec)] = (name, label, never_drawn)
    return found


def notification_family(spec):
    """F4 send_confirmation, one primitive at occurrence 1, failure_count 1..3, or F1 send_confirmation:
    the notification-side kinds whose untriggered trials are the Actor's confirmation lapse."""
    primitives = spec['primitives']
    if len(primitives) != 1 or primitives[0]['target_tool'] != 'send_confirmation' or primitives[0]['occurrence'] != 1:
        return False
    p = primitives[0]
    return p['kind'] == 'F1' or (p['kind'] == 'F4' and p['parameters']['failure_count'] <= 3)


def multi_failure_notification(spec):
    return any(p['kind'] == 'F4' and p['target_tool'] == 'send_confirmation' and p['parameters']['failure_count'] >= 2
               for p in spec['primitives'])


def read_store(store):
    """Every v4 development trial of the store, with its schedule, plus per-episode dispatch facts."""
    connection = sqlite3.connect(f'file:{store}?mode=ro', uri=True)
    try:
        query = ("SELECT e.id, e.payload, t.payload, p.payload FROM records e "
                 "JOIN records t ON t.kind='trials' AND t.id=e.id "
                 "JOIN records p ON p.kind='private_episode_inputs' AND p.id=e.id "
                 "WHERE e.kind='episodes' AND json_extract(e.payload,'$.split')='development'")
        rows = [(eid, json.loads(e), json.loads(t), json.loads(p)['recipe']) for eid, e, t, p in connection.execute(query)]
        development = {eid for eid, _, _, _ in rows}
        v4 = {eid for (eid,) in connection.execute(
            "SELECT DISTINCT episode_id FROM events WHERE json_extract(payload,'$.type')='actor_output' "
            "AND json_extract(payload,'$.payload.actor_context_protocol')=?", (V4,)) if eid in development}
        dispatched = defaultdict(set)
        for eid, tool in connection.execute(
                "SELECT episode_id, json_extract(payload,'$.payload.tool') FROM events "
                "WHERE json_extract(payload,'$.type')='tool_dispatched'"):
            if eid in v4:
                dispatched[eid].add(tool)
    finally:
        connection.close()
    trials = []
    for eid, episode, trial, recipe in rows:
        if eid not in v4:
            continue
        spec = FaultSpec.model_validate(recipe)
        dumped = spec.model_dump(mode='json')
        trials.append({'episode_id': eid, 'baseline': trial.get('policy_hash') == BASELINE_POLICY_HASH,
                       'identity': schedule_identity(spec), 'spec': dumped, 'trial': trial,
                       'report_present': episode.get('report') is not None,
                       'valid': (trial.get('lifecycle') == 'COMPLETED' and trial.get('outcome') not in (None, 'LAB_ERROR')
                                 and (not trial.get('fault_scheduled') or bool(trial.get('fault_triggered')))),
                       'untriggered': bool(trial.get('fault_scheduled')) and not trial.get('fault_triggered'),
                       'scheduled': bool(trial.get('fault_scheduled')),
                       'dispatched': frozenset(dispatched.get(eid, ()))})
    return {'episodes_v4_development': len(v4), 'trials': trials}


def measure(stores, drift_artifact=DRIFT_ARTIFACT):
    """Per heldout-2 kind: per-identity and pooled B0 rates, untriggered rates, and the rule-1 pools."""
    from app.lab.heldout_check import harmful   # the one counted-failure criterion (Phase 18 and 20)
    kinds = kind_of_identity()
    per_identity = defaultdict(lambda: {'b0_valid': 0, 'b0_target': 0, 'b0_all': 0, 'b0_failures': 0,
                                        'scheduled_all_arms': 0, 'untriggered_all_arms': 0,
                                        'scheduled_b0': 0, 'untriggered_b0': 0, 'sources': set()})
    failure_pools = {'phase20_pooled_all_b0': [0, 0], 'store_applicable_b0': [0, 0],
                     'heldout2_kinds_b0_all_sources': [0, 0]}
    failure_ids = {'phase20_pooled_all_b0': [], 'store_applicable_b0': []}
    lapse_family = {'all_arms': [0, 0], 'b0': [0, 0]}
    dispatch = {'episodes': 0, 'without_get_order': 0, 'without_update_order': 0}
    sources = {}
    for label, store in stores.items():
        data = read_store(store)
        sources[label] = {'path': str(pathlib.Path(store).resolve().relative_to(ROOT))
                          if pathlib.Path(store).resolve().is_relative_to(ROOT) else str(store),
                          'v4_development_episodes': data['episodes_v4_development'],
                          'v4_development_trials_with_recipe': len(data['trials'])}
        seen = set()
        for item in data['trials']:
            trial, spec = item['trial'], item['spec']
            if item['episode_id'] not in seen:
                seen.add(item['episode_id'])
                dispatch['episodes'] += 1
                dispatch['without_get_order'] += 'get_order' not in item['dispatched']
                dispatch['without_update_order'] += 'update_order' not in item['dispatched']
            if item['baseline']:
                failed = harmful(trial, report_present=item['report_present'])
                if label == 'phase20':
                    failure_pools['phase20_pooled_all_b0'][0] += failed
                    failure_pools['phase20_pooled_all_b0'][1] += 1
                    if failed:
                        failure_ids['phase20_pooled_all_b0'].append(item['episode_id'])
                elif not multi_failure_notification(spec):
                    failure_pools['store_applicable_b0'][0] += failed
                    failure_pools['store_applicable_b0'][1] += 1
                    if failed:
                        failure_ids['store_applicable_b0'].append(item['episode_id'])
            if notification_family(spec) and item['scheduled']:
                lapse_family['all_arms'][0] += item['untriggered']
                lapse_family['all_arms'][1] += 1
                if item['baseline']:
                    lapse_family['b0'][0] += item['untriggered']
                    lapse_family['b0'][1] += 1
            if item['identity'] not in kinds:
                continue
            kind, parameter, in_completion = kinds[item['identity']]
            row = per_identity[item['identity']]
            row['sources'].add(label)
            if item['scheduled']:
                row['scheduled_all_arms'] += 1
                row['untriggered_all_arms'] += item['untriggered']
            if not item['baseline']:
                continue
            row['b0_all'] += 1
            row['b0_failures'] += harmful(trial, report_present=item['report_present'])
            failure_pools['heldout2_kinds_b0_all_sources'][0] += harmful(trial, report_present=item['report_present'])
            failure_pools['heldout2_kinds_b0_all_sources'][1] += 1
            if item['scheduled']:
                row['scheduled_b0'] += 1
                row['untriggered_b0'] += item['untriggered']
            if item['valid']:
                row['b0_valid'] += 1
                row['b0_target'] += trial.get('outcome') == TARGET[kind]
    by_kind = {}
    for name, (_, _, specs) in partition.draw_spaces().items():
        identities = [partition.identity(spec) for spec in specs]
        rows, pooled = [], defaultdict(int)
        for identity in identities:
            if identity not in per_identity:
                continue
            row = per_identity[identity]
            _, parameter, in_completion = kinds[identity]
            rows.append({'parameters': parameter, 'in_7ab9368e_so_never_drawn': in_completion,
                         'sources': sorted(row['sources']),
                         'b0_target': rate(row['b0_target'], row['b0_valid']),
                         'b0_counted_failures': rate(row['b0_failures'], row['b0_all']),
                         'untriggered_all_arms': rate(row['untriggered_all_arms'], row['scheduled_all_arms']),
                         'untriggered_b0': rate(row['untriggered_b0'], row['scheduled_b0'])})
            for key in ('b0_valid', 'b0_target', 'b0_all', 'b0_failures', 'scheduled_all_arms', 'untriggered_all_arms',
                        'scheduled_b0', 'untriggered_b0'):
                pooled[key] += row[key]
        measured = [i for i in identities if i in per_identity and per_identity[i]['b0_valid']]
        drawable = [i for i in identities if not kinds[i][2] or name in partition.NOVELTY_EXEMPT]
        drawable_measured = [i for i in measured if i in drawable]
        by_kind[name] = {
            'target_outcome': TARGET[name], 'space_size': len(identities),
            'identities_measured': len(measured), 'identities_drawable_after_7ab9368e': len(drawable),
            'drawable_identities_measured': len(drawable_measured),
            'measured_rate_is_a_proxy': not drawable_measured,
            'by_identity': rows,
            'b0_target': rate(pooled['b0_target'], pooled['b0_valid']),
            'b0_counted_failures': rate(pooled['b0_failures'], pooled['b0_all']),
            'untriggered_all_arms': rate(pooled['untriggered_all_arms'], pooled['scheduled_all_arms']),
            'untriggered_b0': rate(pooled['untriggered_b0'], pooled['scheduled_b0'])}
    pools = {name: rate(*values) for name, values in failure_pools.items()}
    combined = [failure_pools['phase20_pooled_all_b0'][i] + failure_pools['store_applicable_b0'][i] for i in (0, 1)]
    pools['declared_rule1_pool'] = rate(*combined)
    pools['declared_rule1_pool_definition'] = ('Phase 20 section 7.6: every Phase 20 B0 trial (pooled_all_b0) together '
                                               'with the main store\'s applicable v4 development B0 kinds (section 7.3: '
                                               'every kind except F4 send_confirmation with failure_count >= 2)')
    failing = sorted(failure_ids['phase20_pooled_all_b0'] + failure_ids['store_applicable_b0'])
    drifted = phase19_drifted_episodes(drift_artifact)
    defect = [episode for episode in failing if episode in drifted]
    pools['declared_rule1_pool_failures'] = failing
    pools['non_defect_rule1_pool'] = {
        **rate(combined[0] - len(defect), combined[1]),
        'excluded_failures': defect,
        'definition': ('the declared pool with its lab-defect failures (Phase 19 clock drift, listed in '
                       + str(DRIFT_ARTIFACT.relative_to(ROOT)) + ') counted as trials without a counted failure: '
                       'the drift made a truthful report fail, so the failure is the lab\'s, not the Actor\'s. '
                       'The declared pool is kept as declared (Phase 20 section 7.6); this row is shown beside it')}
    pools['matches_phase20_figures'] = {
        'store_applicable_b0 == 1 of 712': tuple(failure_pools['store_applicable_b0']) == PHASE20_FIGURES[
            'store_applicable_b0_failures'],
        'phase20_pooled_all_b0 == 0 of 69': tuple(failure_pools['phase20_pooled_all_b0']) == PHASE20_FIGURES[
            'phase20_pooled_all_b0'],
        'transient_upgrade_failures B0 completed == 2 of 27': (
            (by_kind['transient_upgrade_failures']['b0_target']['k'], by_kind['transient_upgrade_failures']['b0_target']['n'])
            == PHASE20_FIGURES['transient_upgrade_failures_b0_completed'])}
    untriggered_proxy = {
        'definition': ('v4 development episodes (both stores) that never dispatch the tool at all, so an F2/F4 '
                       'update_order or F3 get_order primitive at occurrence 1 could not fire'),
        'episodes': dispatch['episodes'],
        'without_get_order': rate(dispatch['without_get_order'], dispatch['episodes']),
        'without_update_order': rate(dispatch['without_update_order'], dispatch['episodes'])}
    lapse = {'definition': ('notification-side kinds whose untriggered trials are the confirmation lapse: F1 '
                            'send_confirmation and F4 send_confirmation failure_count 1..3, occurrence 1'),
             'all_arms': rate(*lapse_family['all_arms']), 'b0': rate(*lapse_family['b0'])}
    return {'sources': sources, 'by_kind': by_kind, 'rule1_failure_pools': pools,
            'untriggered_mechanism_proxy': untriggered_proxy, 'confirmation_lapse_family': lapse}


def phase19_drifted_episodes(path=DRIFT_ARTIFACT):
    """The episodes Phase 19's store-wide drift scan lists under 'drifted:' (lab defect, C6)."""
    drifted, inside = set(), False
    for line in pathlib.Path(path).read_text().splitlines():
        if line.startswith('drifted:'):
            inside = True
        elif line and not line.startswith(' '):
            inside = False
        elif inside and line.strip().startswith('episode-'):
            drifted.add(line.split()[0])
    return drifted


def file_facts(path):
    """Provenance of one input file: path, size, modification time and sha256."""
    path = pathlib.Path(path)
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    stat = path.stat()
    resolved = path.resolve()
    return {'path': str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(path),
            'size_bytes': stat.st_size, 'mtime_utc': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            'sha256': digest.hexdigest()}


# ---------------------------------------------------------------- enumeration (pure python)

def harm_rule(n):
    return p20.harm_v1 if n == V1_N else p20.harm_v2


def rule3(n, qb, ql):
    return p20.rule3(n, qb, ql, harm_rule(n))


def grid(lo, hi, points=INTERVAL_GRID):
    if hi - lo < 1e-12:
        return [lo]
    return [lo + (hi - lo) * i / (points - 1) for i in range(points)]


def case_metrics(n, q, interval):
    """Rule 3 on one fault case: null, total-loss and halving power, MDL; point and worst over the interval."""
    lo, hi = interval
    points = grid(lo, hi)
    coarse = grid(lo, hi, 21)

    def mdl_at(value):
        return p20.mdl(value, n, harm_rule(n), power=POWER)
    worst_mdl = [mdl_at(value) for value in coarse]
    return {'n_per_arm': n,
            'null_false_harm': r(rule3(n, q, q)), 'null_false_harm_max_over_interval': r(max(rule3(n, x, x) for x in points)),
            'power_total_loss': r(rule3(n, q, 0.0)),
            'power_total_loss_min_over_interval': r(min(rule3(n, x, 0.0) for x in points)),
            'power_halving': r(rule3(n, q, q / 2)),
            'power_halving_min_over_interval': r(min(rule3(n, x, x / 2) for x in points)),
            'mdl_80pct_absolute': mdl_at(q), 'mdl_80pct_relative': (r(mdl_at(q) / q, 3) if mdl_at(q) and q else None),
            'mdl_80pct_worst_over_interval': (None if any(m is None for m in worst_mdl) else max(worst_mdl))}


def sup_null(n):
    values = [(rule3(n, i / (SUP_GRID - 1), i / (SUP_GRID - 1)), i / (SUP_GRID - 1)) for i in range(SUP_GRID)]
    best = max(values)
    return {'max_null_false_harm_over_q_0_to_1': r(best[0]), 'at_q': r(best[1], 3)}


def criterion(v1, v2):
    """The declared Phase 22 criterion on one case: v2 power >= v1 power on each harm scenario AND a
    lower null false-HARM. 'Lower' is read strictly and, separately, as 'not higher' (at q = 1 both are 0)."""
    tolerance = 1e-9
    scenarios = {s: {'v1': v1[f'power_{s}'], 'v2': v2[f'power_{s}'],
                     'v2_matches_or_beats': v2[f'power_{s}'] >= v1[f'power_{s}'] - tolerance}
                 for s in ('total_loss', 'halving')}
    strict = v2['null_false_harm'] < v1['null_false_harm'] - tolerance
    not_higher = v2['null_false_harm'] <= v1['null_false_harm'] + tolerance
    power_ok = all(s['v2_matches_or_beats'] for s in scenarios.values())
    return {'power': scenarios, 'v2_null_strictly_lower': strict, 'v2_null_not_higher': not_higher,
            'meets_criterion_strict': power_ok and strict, 'meets_criterion_not_higher': power_ok and not_higher,
            'fails_on': [s for s, v in scenarios.items() if not v['v2_matches_or_beats']]
            + ([] if not_higher else ['null_false_harm'])}


def criterion_over_interval(q_interval):
    """Does the criterion hold at every q of the interval (grid)? Returns the share and the first q where it fails."""
    failures, points = [], grid(*q_interval, points=51)
    for x in points:
        nulls = (rule3(V1_N, x, x), rule3(V2_N, x, x))
        ok = (nulls[1] <= nulls[0] + 1e-9 and rule3(V2_N, x, 0.0) >= rule3(V1_N, x, 0.0) - 1e-9
              and rule3(V2_N, x, x / 2) >= rule3(V1_N, x, x / 2) - 1e-9)
        if not ok:
            failures.append(x)
    return {'grid_points': len(points), 'holds_at': len(points) - len(failures),
            'first_failing_q': r(failures[0]) if failures else None, 'last_failing_q': r(failures[-1]) if failures else None}


def case_null(n, q, v):
    """Null P(HARM) on one fault case from rules 1 and 3 jointly. Both arms alike: a trial fails a
    counted check with probability v, and otherwise reaches the target with probability q (q is
    measured on valid trials, so it is a rate among non-failing trials; Phase 20's
    rules_1_and_3 instead needs q + v <= 1, which a measured q of 1 violates). HARM if any
    candidate trial fails (rule 1) or rule 3 fires on the target counts."""
    return case_harm(n, q, q, v)


def case_harm(n, qb, ql, v):
    """P(HARM) on one fault case from rules 1 and 3 jointly when the baseline reaches the target
    at rate qb and the candidate at rate ql (both among non-failing trials; case_null is qb = ql)."""
    harm = harm_rule(n)
    target = ql * (1 - v)
    other = (1 - ql) * (1 - v)
    baseline = p20.pmf(n, qb * (1 - v))
    safe = 0.0
    for l in range(n + 1):
        candidate_clean = math.comb(n, l) * target ** l * other ** (n - l)   # no candidate failure, l targets
        safe += candidate_clean * sum(baseline[b] for b in range(n + 1) if not harm(b, l, n))
    return 1 - safe


def partition_null(fault_q, q0, v, design):
    """Whole-partition P(HARM | policy has no effect): on the no-fault case rules 4 and 1 (3 candidate
    trials that must all complete without a counted failure), on each fault case rules 1 and 3
    jointly (case_null). Cases independent; rules 1 and 3 share the candidate trials."""
    n = V1_N if design == 'v1' else V2_N
    no_fault_safe = (q0 * (1 - v)) ** NO_FAULT_N
    no_harm = no_fault_safe
    per_case = {}
    for name, q in fault_q.items():
        value = case_null(n, q, v)
        per_case[name] = r(value)
        no_harm *= 1 - value
    rule1_only = 1 - (1 - v) ** (n * len(fault_q) + NO_FAULT_N)
    return {'p_harm': r(1 - no_harm), 'no_fault_case_rules_4_and_1': r(1 - no_fault_safe),
            'rule4_alone': r(1 - q0 ** NO_FAULT_N), 'rule1_alone': r(rule1_only),
            'candidate_episodes': n * len(fault_q) + NO_FAULT_N, 'per_fault_case_rules_1_and_3': per_case}


def rule1_crossover(fault_q, q0, hi=0.05):
    """The per-trial counted-failure rate v above which v2's whole-partition null P(HARM) exceeds v1's at
    the measured target rates (v2 runs 78 candidate episodes against v1's 18, so rule 1 grows faster)."""
    def gap(v):
        return partition_null(fault_q, q0, v, 'v2')['p_harm'] - partition_null(fault_q, q0, v, 'v1')['p_harm']
    if gap(0.0) >= 0:
        return {'v': 0.0, 'note': 'v2 is not lower even at v = 0'}
    if gap(hi) < 0:
        return {'v': None, 'note': f'v2 stays lower for every v up to {hi}'}
    lo = 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gap(mid) < 0 else (lo, mid)
    return {'v': r(hi, 5), 'note': 'below this per-trial counted-failure rate v2\'s whole-partition null P(HARM) is lower'}


def worst_q_for_case(n, interval, v):
    return max(grid(*interval), key=lambda x: case_null(n, x, v))


def verdict_within_attempts(u_by_kind, v, design, attempts=ATTEMPTS):
    """Per attempt, under the null: a verdict is reached when a candidate trial fails a counted check
    (rule 1 fires even on an incomplete batch) or when every pair is valid and triggered. A trial on a
    case of kind k is untriggered with probability u_k in either arm. Lab errors are not modelled."""
    n = V1_N if design == 'v1' else V2_N
    all_triggered = 1.0
    exposure = {}
    for name, u in u_by_kind.items():
        exposed = 2 * n
        exposure[name] = exposed
        all_triggered *= (1 - u) ** exposed
    no_rule1 = (1 - v) ** (n * len(u_by_kind) + NO_FAULT_N)
    no_verdict = no_rule1 * (1 - all_triggered)
    return {'exposed_trials_per_attempt': exposure, 'p_all_triggered_per_attempt': r(all_triggered),
            'p_verdict_per_attempt': r(1 - no_verdict),
            f'p_verdict_within_{attempts}': r(1 - no_verdict ** attempts),
            f'p_clean_batch_within_{attempts}': r(1 - (1 - all_triggered) ** attempts),
            'note': 'p_verdict includes rule-1 verdicts, which under the null are false HARM'}


# ---------------------------------------------------------------- review round 1 (pure python)

def v2_detection_floor():
    """For each baseline count B0 of 15, the largest candidate count L at which v2's rule 3 fires
    (None: it never fires). At B0 = 15 it fires only for L <= 11, so a loss of 1 to 3 of 15 is unseen."""
    return {b: max((l for l in range(V2_N + 1) if p20.harm_v2(b, l, V2_N)), default=None) for b in range(V2_N + 1)}


def crossover_d(q):
    """The smallest absolute loss d (grid 0.01) from which v2's power is at least v1's."""
    for k in range(1, int(round(q * 100)) + 1):
        d = k / 100
        if rule3(V2_N, q, max(0.0, q - d)) >= rule3(V1_N, q, max(0.0, q - d)) - 1e-12:
            return d
    return None


def small_losses(q):
    """Rule 3 against small absolute losses d at a high baseline rate q, v1 against v2."""
    return {'q': r(q), 'null_false_harm': {'v1': r(rule3(V1_N, q, q)), 'v2': r(rule3(V2_N, q, q))},
            'power': {f'd={d}': {'v1': r(rule3(V1_N, q, max(0.0, q - d))), 'v2': r(rule3(V2_N, q, max(0.0, q - d)))}
                      for d in SMALL_LOSSES},
            'v2_power_at_least_v1_from_d': crossover_d(q),
            'mdl_50pct': {'v1': p20.mdl(q, V1_N, p20.harm_v1, power=0.5), 'v2': p20.mdl(q, V2_N, p20.harm_v2, power=0.5)},
            'mdl_80pct': {'v1': p20.mdl(q, V1_N, p20.harm_v1, power=0.8), 'v2': p20.mdl(q, V2_N, p20.harm_v2, power=0.8)}}


LOSSES = {'total_loss': lambda x: 0.0, 'halving': lambda x: x / 2}


def criterion_worst_case(interval):
    """Phase 20 section 7.6's reading of the declared criterion on one case: the worst value of each
    quantity over the interval (the null's maximum, each power's minimum), v2 against v1."""
    points = grid(*interval)
    null = {design: max(rule3(n, x, x) for x in points) for design, n in (('v1', V1_N), ('v2', V2_N))}
    power = {}
    for scenario, loss in LOSSES.items():
        values = {design: min(rule3(n, x, loss(x)) for x in points) for design, n in (('v1', V1_N), ('v2', V2_N))}
        below = [x for x in points if rule3(V2_N, x, loss(x)) < rule3(V1_N, x, loss(x)) - 1e-9]
        power[scenario] = {**{design: r(value) for design, value in values.items()},
                           'v2_matches_or_beats': values['v2'] >= values['v1'] - 1e-9,
                           'v2_below_v1_for_q': [r(below[0]), r(below[-1])] if below else None}
    strict = null['v2'] < null['v1'] - 1e-9
    return {'interval': [r(x) for x in interval], 'null_max': {design: r(value) for design, value in null.items()},
            'v2_null_strictly_lower': strict, 'power_min': power,
            'met': strict and all(item['v2_matches_or_beats'] for item in power.values()),
            'power_fails_on': [scenario for scenario, item in power.items() if not item['v2_matches_or_beats']]}


def partition_harm(qb, ql, q0, v, design):
    """P(HARM) on a complete batch when the candidate reaches the target at ql[kind] and the
    baseline at qb[kind]; the no-fault case unchanged (rules 4 and 1). ql == qb is partition_null."""
    n = V1_N if design == 'v1' else V2_N
    safe = (q0 * (1 - v)) ** NO_FAULT_N
    for name in FAULT_KINDS:
        safe *= 1 - case_harm(n, qb[name], ql[name], v)
    return 1 - safe


def phase24_outcome(u, v, harm_complete, design):
    """Phase 24's outcome over 1, 2 and 3 attempts (PHASE24_EXPERIMENT.md section 7): a batch is clean
    with probability (1 - u)^(2n) on the delayed-confirmation case; a clean batch reads HARM with
    probability harm_complete; an incomplete one reads HARM only through rule 1 over every candidate
    episode; otherwise no verdict, and the next attempt is independent. Lab errors are not modelled."""
    n = V1_N if design == 'v1' else V2_N
    clean = (1 - u) ** (2 * n)
    rule1 = 1 - (1 - v) ** (n * len(FAULT_KINDS) + NO_FAULT_N)
    no_harm, harm, none = clean * (1 - harm_complete), clean * harm_complete + (1 - clean) * rule1, (1 - clean) * (1 - rule1)
    rows = {}
    for attempts in PHASE24_ATTEMPTS:
        reach = sum(none ** i for i in range(attempts))
        rows[f'within_{attempts}'] = {'NO_HARM': r(no_harm * reach), 'HARM': r(harm * reach), 'no_verdict': r(none ** attempts)}
    return {'clean_per_attempt': r(clean), 'harm_on_a_complete_batch': r(harm_complete), **rows,
            'p_no_harm_given_a_verdict': r(no_harm / (no_harm + harm)) if no_harm + harm else None}


def build(measured):
    kinds = measured['by_kind']
    pools = measured['rule1_failure_pools']
    v_point = pools['declared_rule1_pool']['rate']
    v_upper = pools['declared_rule1_pool']['wilson_95'][1]
    q = {name: kinds[name]['b0_target']['rate'] for name in kinds}
    interval = {name: kinds[name]['b0_target']['wilson_95'] for name in kinds}
    per_case, failures, ties = {}, [], []
    for name in FAULT_KINDS:
        v1 = case_metrics(V1_N, q[name], interval[name])
        v2 = case_metrics(V2_N, q[name], interval[name])
        check = criterion(v1, v2)
        per_case[name] = {
            'baseline_rate': {'q': r(q[name]), 'k_of_n': [kinds[name]['b0_target']['k'], kinds[name]['b0_target']['n']],
                              'wilson_95': [r(x) for x in interval[name]],
                              'measured_rate_is_a_proxy': kinds[name]['measured_rate_is_a_proxy'],
                              'drawable_identities_measured': (f"{kinds[name]['drawable_identities_measured']} of "
                                                               f"{kinds[name]['identities_drawable_after_7ab9368e']}")},
            'v1': v1, 'v2': v2, 'criterion_at_measured_rate': check,
            'criterion_over_wilson_interval': criterion_over_interval(interval[name]),
            'rules_1_and_3_null': {'v1_at_point': r(case_null(V1_N, q[name], v_point)),
                                   'v2_at_point': r(case_null(V2_N, q[name], v_point)),
                                   'v1_worst': r(max(case_null(V1_N, x, v_upper) for x in grid(*interval[name]))),
                                   'v2_worst': r(max(case_null(V2_N, x, v_upper) for x in grid(*interval[name])))}}
        failures += [f'{name}: {what}' for what in check['fails_on']]
        if check['v2_null_not_higher'] and not check['v2_null_strictly_lower']:
            ties.append(f'{name}: null false-HARM equal in v1 and v2 ({v1["null_false_harm"]}) at the point rate '
                        f'{r(q[name])}; strictly lower everywhere else in the interval is checked separately')
    q0, q0_interval = q['no_fault'], interval['no_fault']
    no_fault = {'baseline_rate': {'q0': r(q0), 'k_of_n': [kinds['no_fault']['b0_target']['k'],
                                                          kinds['no_fault']['b0_target']['n']],
                                  'wilson_95': [r(x) for x in q0_interval]},
                'rule4_same_in_v1_and_v2': True, 'n_per_arm': NO_FAULT_N,
                'null_false_harm': r(1 - q0 ** 3), 'null_false_harm_at_wilson_lower': r(1 - q0_interval[0] ** 3),
                'power_total_loss': 1.0, 'power_halving': r(1 - (q0 / 2) ** 3),
                'mdl_80pct_absolute': next(k / 100 for k in range(101) if 1 - max(0.0, q0 - k / 100) ** 3 >= POWER),
                'criterion': 'rule 4 is unchanged, so v2 equals v1 here: power matches, null false-HARM is equal, not lower'}
    sup = {'v1': sup_null(V1_N), 'v2': sup_null(V2_N),
           'use': ('for kinds whose drawable identities are unmeasured, the rate can be anywhere in [0, 1]; rule 3\'s '
                   'null false-HARM is bounded by this maximum, while its power is not bounded below (it goes to 0 '
                   'as q goes to 0)')}

    fault_q = {name: q[name] for name in FAULT_KINDS}
    partition_rows = {}
    for design in ('v1', 'v2'):
        n = V1_N if design == 'v1' else V2_N
        worst_q = {name: worst_q_for_case(n, interval[name], v_upper) for name in FAULT_KINDS}
        unmeasured_q = dict(fault_q)
        for name in FAULT_KINDS:
            if kinds[name]['measured_rate_is_a_proxy']:
                unmeasured_q[name] = max((i / 200 for i in range(201)), key=lambda x: case_null(n, x, v_point))
        partition_rows[design] = {
            'at_measured_rates_and_pooled_v': partition_null(fault_q, q0, v_point, design),
            'at_measured_rates_v_zero': partition_null(fault_q, q0, 0.0, design),
            'at_measured_rates_v_upper': partition_null(fault_q, q0, v_upper, design),
            'worst_over_wilson_intervals_v_upper': {**partition_null(worst_q, q0_interval[0], v_upper, design),
                                                    'q_used': {k: r(x) for k, x in worst_q.items()},
                                                    'q0_used': r(q0_interval[0]), 'v_used': r(v_upper, 5)},
            'proxy_kinds_at_their_worst_q_v_point': {**partition_null(unmeasured_q, q0, v_point, design),
                                                     'q_used': {k: r(x) for k, x in unmeasured_q.items()}}}

    crossover = rule1_crossover(fault_q, q0)
    lapse = kinds['delayed_confirmation_response']['untriggered_all_arms']
    proxy = measured['untriggered_mechanism_proxy']
    upgrade_side_u_upper = max(proxy['without_get_order']['wilson_95'][1], proxy['without_update_order']['wilson_95'][1])
    scenarios = {
        'point: F1 lapse at the measured all-arms rate; upgrade-side kinds 0': {
            'delayed_confirmation_response': lapse['rate'], **{k: 0.0 for k in FAULT_KINDS[1:]}},
        'F1 lapse at its Wilson upper bound; upgrade-side kinds 0': {
            'delayed_confirmation_response': lapse['wilson_95'][1], **{k: 0.0 for k in FAULT_KINDS[1:]}},
        'F1 lapse at the notification-family all-arms rate; upgrade-side kinds 0': {
            'delayed_confirmation_response': measured['confirmation_lapse_family']['all_arms']['rate'],
            **{k: 0.0 for k in FAULT_KINDS[1:]}},
        'F1 lapse at Wilson upper; upgrade-side kinds at the dispatch proxy\'s Wilson upper': {
            'delayed_confirmation_response': lapse['wilson_95'][1],
            **{k: upgrade_side_u_upper for k in FAULT_KINDS[1:]}},
        'program figure: lapse 3%': {'delayed_confirmation_response': 0.03, **{k: 0.0 for k in FAULT_KINDS[1:]}},
        'program figure: lapse 0.65%': {'delayed_confirmation_response': 0.0065, **{k: 0.0 for k in FAULT_KINDS[1:]}},
    }
    verdicts = {name: {design: verdict_within_attempts(u, v_point, design) for design in ('v1', 'v2')}
                for name, u in scenarios.items()}
    untriggered = {
        # From the simulator's trigger rule (backend/app/simulator/faults.py matching(): the tool's Nth attempt).
        'which_cases_can_go_untriggered': {
            'no_fault': 'never (no fault is scheduled)',
            'delayed_confirmation_response': ('yes: F1 send_confirmation fires only when a confirmation is sent and '
                                              'commits; the Actor\'s confirmation lapse (it polls a confirmation it '
                                              'never sent) leaves it untriggered'),
            'delayed_upgrade_success': 'only if update_order is never dispatched',
            'delayed_refusal': 'only if update_order is never dispatched',
            'stale_history': 'only if get_order is never dispatched',
            'transient_upgrade_failures': 'only if update_order is never dispatched'},
        'measured_by_kind_all_arms': {name: kinds[name]['untriggered_all_arms'] for name in FAULT_KINDS},
        'measured_by_kind_b0': {name: kinds[name]['untriggered_b0'] for name in FAULT_KINDS},
        'mechanism_proxy': proxy,
        'confirmation_lapse_family': measured['confirmation_lapse_family'],
        'program_claim': 'P(verdict within 3 attempts) 0.74 to 0.98 for a lapse rate of 3% down to 0.65%'}

    power_failures = [f for f in failures if 'null false-HARM' not in f]

    # ---- review round 1
    small = {'at_point_rates': {name: small_losses(q[name]) for name in HIGH_RATE_KINDS},
             'at_q_0.975': small_losses(PROBE_RATE),
             'v2_detection_floor_max_L_by_B0_of_15': {str(b): l for b, l in v2_detection_floor().items()},
             'program_scenario_0.97_drops_to_0.6': {'v1': r(rule3(V1_N, *PROGRAM_SCENARIO)),
                                                   'v2': r(rule3(V2_N, *PROGRAM_SCENARIO))},
             'reading': ('rule 3 alone on one case, per complete batch; d is the absolute drop in the target rate. '
                         'mdl is the smallest d on a 0.01 grid reaching that power')}
    worst = {name: criterion_worst_case(interval[name]) for name in FAULT_KINDS}
    zero_to_one = {name: criterion_worst_case((0.0, 1.0)) for name in PARTLY_MEASURED_KINDS}
    criterion_worst = {
        'reading': ('Phase 20 section 7.6: the worst value over the Wilson interval of the measured rate (the null\'s '
                    'maximum, each power\'s minimum); the point readings above are secondary'),
        'per_case': worst,
        'null_strictly_lower_on': [name for name in FAULT_KINDS if worst[name]['v2_null_strictly_lower']],
        'power_fails_on': {name: worst[name]['power_fails_on'] for name in FAULT_KINDS if worst[name]['power_fails_on']},
        'zero_to_one_for_unmeasured_drawable_identities': {
            'kinds': list(PARTLY_MEASURED_KINDS),
            'why': ('Phase 20 section 7.6 gives an unmeasured drawable identity the full range 0 to 1; these kinds have '
                    'one (F2 SUCCEEDED d1; F3 versions_back 2 and 3). The calibration above uses the measured '
                    'identities\' interval instead, a declared departure (PHASE22_EXPERIMENT.md section 2 row 13)'),
            'per_case': zero_to_one}}
    lapse_rate, lapse_upper = lapse['rate'], lapse['wilson_95'][1]
    family = measured['confirmation_lapse_family']['all_arms']['rate']
    non_defect = pools['non_defect_rule1_pool']
    outcomes_null = {}
    for label, (u, v, worst_rates) in {
            'measured: lapse 8 of 264, v the declared pool (1 of 781)': (lapse_rate, v_point, False),
            'lapse at the notification-family rate, v the declared pool': (family, v_point, False),
            'lapse and v at their Wilson upper bounds': (lapse_upper, v_upper, False),
            'the same, worst baseline rates over every interval': (lapse_upper, v_upper, True),
            "lapse 0.65% (Phase 17's all-stage rate), v the declared pool": (0.0065, v_point, False),
            'measured lapse, v = 0 (the non-defect pool, 0 of 781)': (lapse_rate, non_defect['rate'], False),
            "measured lapse, v at the non-defect pool's Wilson upper bound": (lapse_rate, non_defect['wilson_95'][1], False),
    }.items():
        row = {'u': r(u, 5), 'v': r(v, 6)}
        for design in ('v1', 'v2'):
            n = V1_N if design == 'v1' else V2_N
            rates = ({name: worst_q_for_case(n, interval[name], v) for name in FAULT_KINDS} if worst_rates else fault_q)
            base_q0 = q0_interval[0] if worst_rates else q0
            row[design] = phase24_outcome(u, v, partition_harm(rates, rates, base_q0, v, design), design)
        outcomes_null[label] = row
    outcomes_harm = {}
    for label, (kind, loss) in {
            'stale history: total loss (1.0 to 0)': ('stale_history', lambda x: 0.0),
            'stale history: halving (1.0 to 0.5)': ('stale_history', lambda x: x / 2),
            'stale history: d = 0.2 (1.0 to 0.8)': ('stale_history', lambda x: max(0.0, x - 0.2)),
            'delayed refusal: halving (1.0 to 0.5)': ('delayed_refusal', lambda x: x / 2),
            'delayed refusal: d = 0.2 (1.0 to 0.8)': ('delayed_refusal', lambda x: max(0.0, x - 0.2)),
            'transient upgrade failures: total loss (0.074 to 0)': ('transient_upgrade_failures', lambda x: 0.0),
    }.items():
        harmed = {**fault_q, kind: loss(fault_q[kind])}
        row = {'case': kind, 'baseline_rate': r(fault_q[kind]), 'candidate_rate': r(harmed[kind]),
               'u': r(lapse_rate, 5), 'v': r(v_point, 6)}
        for design in ('v1', 'v2'):
            n = V1_N if design == 'v1' else V2_N
            row[design] = {'rule3_power_on_the_case': r(rule3(n, fault_q[kind], harmed[kind])),
                           **phase24_outcome(lapse_rate, v_point, partition_harm(fault_q, harmed, q0, v_point, design), design)}
        outcomes_harm[label] = row
    phase24 = {'model': ('PHASE24_EXPERIMENT.md section 7: clean = (1 - u)^(2n) on the delayed-confirmation case '
                         '(n = 15 for v2, 3 for v1); a clean batch reads HARM with the partition\'s complete-batch '
                         'P(HARM); an incomplete batch reads HARM only through rule 1 over every candidate episode '
                         '(78 for v2, 18 for v1); attempts independent; lab errors not modelled. A harmful policy '
                         'changes one case\'s candidate target rate and nothing else'),
               'policy_with_no_effect': outcomes_null, 'harmful_policy': outcomes_harm}

    return {'schema_version': SCHEMA, 'pure_python_enumeration': True,
            'designs': {'v1': 'faultlab-heldout-no-harm/v1: 3 trials per arm per case; rule 3 = L target < B0 target',
                        'v2': ('program Phase 22 item 2: rules 1 and 4 unchanged (no-fault 3 trials); rule 3 on 15 '
                               'trials per arm per fault case: one-sided Fisher p <= 0.05 OR (L = 0 and B0 >= 3)')},
            'measured': measured, 'per_fault_case': per_case, 'no_fault_case': no_fault,
            'rule3_null_bound_over_all_q': sup,
            'rule1': {'v_point': r(v_point, 6), 'v_wilson_upper': r(v_upper, 6),
                      'v1_18_candidate_episodes': {'point': r(1 - (1 - v_point) ** 18), 'upper': r(1 - (1 - v_upper) ** 18)},
                      'v2_78_candidate_episodes': {'point': r(1 - (1 - v_point) ** 78), 'upper': r(1 - (1 - v_upper) ** 78)}},
            'partition_null_p_harm': partition_rows,
            'partition_null_crossover': crossover,
            'untriggered_exposure': untriggered, 'p_verdict_within_3_attempts': verdicts,
            'declared_criterion': {
                'text': ('v2 must match or beat v1\'s power on each harm scenario at the measured baseline rates AND '
                         'have a lower false-HARM rate under the null (program, Phase 22 item 2)'),
                'failures_at_measured_rates': failures,
                'ties_not_failures': ties,
                'power_failures_at_measured_rates': power_failures,
                'met_on_every_fault_case_and_scenario': not failures,
                'met_on_power_everywhere': not power_failures,
                'worst_case_reading': criterion_worst},
            'small_losses': small, 'phase24_outcomes': phase24}


# ---------------------------------------------------------------- report

def pct(x):
    return 'n/a' if x is None else f'{100 * x:.1f}%'


def interval_text(values):
    return 'n/a' if not values else f'[{pct(values[0])}, {pct(values[1])}]'


def report(result):
    lines = ['Phase 22 predicate calibration (v2 vs v1), $0, read-only stores, exact enumeration', '']
    m = result['measured']
    for label, source in m['sources'].items():
        lines.append(f"source {label}: {source['path']} ({source['v4_development_episodes']} v4 development episodes)")
    lines += ['', 'Baseline (B0) rates per heldout-2 kind (valid trials for q; every B0 trial for failures):']
    for name, kind in m['by_kind'].items():
        t = kind['b0_target']
        lines.append(f"  {name}: target {kind['target_outcome']} {t['k']}/{t['n']} = {pct(t['rate'])} "
                     f"{interval_text(t['wilson_95'])}; drawable identities measured "
                     f"{kind['drawable_identities_measured']} of {kind['identities_drawable_after_7ab9368e']}"
                     f"{' (PROXY: only an identity 7ab9368e excludes is measured)' if kind['measured_rate_is_a_proxy'] else ''}")
        for row in kind['by_identity']:
            lines.append(f"      {row['parameters']}: {row['b0_target']['k']}/{row['b0_target']['n']}"
                         f"{' [in 7ab9368e, never drawn]' if row['in_7ab9368e_so_never_drawn'] else ''}; "
                         f"failures {row['b0_counted_failures']['k']}/{row['b0_counted_failures']['n']}; untriggered "
                         f"{row['untriggered_all_arms']['k']}/{row['untriggered_all_arms']['n']} (all arms)")
    rule1 = result['rule1']
    pool = m['rule1_failure_pools']['declared_rule1_pool']
    lines += ['', f"Rule 1 pool: {pool['k']}/{pool['n']} = {pct(pool['rate'])} {interval_text(pool['wilson_95'])} "
                  f"(matches Phase 20: {m['rule1_failure_pools']['matches_phase20_figures']})",
              f"  P(rule 1 false HARM): v1 18 episodes {pct(rule1['v1_18_candidate_episodes']['point'])} "
              f"(upper {pct(rule1['v1_18_candidate_episodes']['upper'])}); v2 78 episodes "
              f"{pct(rule1['v2_78_candidate_episodes']['point'])} (upper {pct(rule1['v2_78_candidate_episodes']['upper'])})",
              '', 'Rule 3 per fault case (point; worst over the Wilson interval in brackets):']
    for name, row in result['per_fault_case'].items():
        v1, v2, c = row['v1'], row['v2'], row['criterion_at_measured_rate']
        lines.append(f"  {name} (q {pct(row['baseline_rate']['q'])}):")
        lines.append(f"    null false-HARM   v1 {pct(v1['null_false_harm'])} [{pct(v1['null_false_harm_max_over_interval'])}]"
                     f"  v2 {pct(v2['null_false_harm'])} [{pct(v2['null_false_harm_max_over_interval'])}]")
        lines.append(f"    power total loss  v1 {pct(v1['power_total_loss'])} [{pct(v1['power_total_loss_min_over_interval'])}]"
                     f"  v2 {pct(v2['power_total_loss'])} [{pct(v2['power_total_loss_min_over_interval'])}]")
        lines.append(f"    power halving     v1 {pct(v1['power_halving'])} [{pct(v1['power_halving_min_over_interval'])}]"
                     f"  v2 {pct(v2['power_halving'])} [{pct(v2['power_halving_min_over_interval'])}]")
        lines.append(f"    MDL at 80%        v1 {v1['mdl_80pct_absolute']} [{v1['mdl_80pct_worst_over_interval']}]"
                     f"  v2 {v2['mdl_80pct_absolute']} [{v2['mdl_80pct_worst_over_interval']}]")
        joint = row['rules_1_and_3_null']
        lines.append(f"    with rule 1 (pooled v): null P(HARM) v1 {pct(joint['v1_at_point'])} [{pct(joint['v1_worst'])}]"
                     f"  v2 {pct(joint['v2_at_point'])} [{pct(joint['v2_worst'])}]")
        interval_check = row['criterion_over_wilson_interval']
        verdict = ('MET' if c['meets_criterion_strict'] else 'MET except a tie: both nulls are 0 at q = 1'
                   if c['meets_criterion_not_higher'] else 'FAILS on ' + ', '.join(c['fails_on']))
        where = ('' if interval_check['first_failing_q'] is None else
                 f" (fails for q in {interval_check['first_failing_q']}..{interval_check['last_failing_q']})")
        lines.append(f"    criterion (rule 3): {verdict}; over the interval it holds at {interval_check['holds_at']}/"
                     f"{interval_check['grid_points']} points{where}")
    nf = result['no_fault_case']
    lines += [f"  no_fault (q0 {pct(nf['baseline_rate']['q0'])}): rule 4 in both designs, null false-HARM "
              f"{pct(nf['null_false_harm'])} (at Wilson lower {pct(nf['null_false_harm_at_wilson_lower'])})",
              f"  sup over q of rule-3 null false-HARM: v1 {pct(result['rule3_null_bound_over_all_q']['v1']['max_null_false_harm_over_q_0_to_1'])}, "
              f"v2 {pct(result['rule3_null_bound_over_all_q']['v2']['max_null_false_harm_over_q_0_to_1'])}",
              '', 'Whole partition P(HARM | policy has no effect):']
    for design in ('v1', 'v2'):
        rows = result['partition_null_p_harm'][design]
        lines.append(f"  {design}: measured rates + pooled v {pct(rows['at_measured_rates_and_pooled_v']['p_harm'])}; "
                     f"v = 0 {pct(rows['at_measured_rates_v_zero']['p_harm'])}; worst over intervals "
                     f"{pct(rows['worst_over_wilson_intervals_v_upper']['p_harm'])}; proxy kinds at worst q "
                     f"{pct(rows['proxy_kinds_at_their_worst_q_v_point']['p_harm'])}")
    crossover = result['partition_null_crossover']
    lines.append(f"  v2's whole-partition null is lower than v1's only while v < {crossover['v']} "
                 f"(pooled point {pct(rule1['v_point'])}, Wilson upper {pct(rule1['v_wilson_upper'])}); at the upper: "
                 f"v1 {pct(result['partition_null_p_harm']['v1']['at_measured_rates_v_upper']['p_harm'])}, "
                 f"v2 {pct(result['partition_null_p_harm']['v2']['at_measured_rates_v_upper']['p_harm'])}")
    lines += ['', 'P(verdict within 3 attempts) under the null (and P(clean batch within 3)):']
    for name, designs in result['p_verdict_within_3_attempts'].items():
        lines.append(f"  {name}: v1 {pct(designs['v1']['p_verdict_within_3'])} ({pct(designs['v1']['p_clean_batch_within_3'])})"
                     f"  v2 {pct(designs['v2']['p_verdict_within_3'])} ({pct(designs['v2']['p_clean_batch_within_3'])})")
    criterion_block = result['declared_criterion']
    lines += ['', 'Declared criterion: ' + ('MET everywhere' if criterion_block['met_on_every_fault_case_and_scenario']
                                            else 'NOT met everywhere:')]
    lines += [f'  - {f}' for f in criterion_block['failures_at_measured_rates']]
    lines += [f'  (tie) {t}' for t in criterion_block['ties_not_failures']]
    return '\n'.join(lines + report_round1(result)) + '\n'


def report_round1(result):
    """The blocks added in Phase 22 review round 1."""
    lines = ['', 'Review round 1 additions']
    pools = result['measured']['rule1_failure_pools']
    declared, clean = pools['declared_rule1_pool'], pools['non_defect_rule1_pool']
    lines += [f"Rule-1 pool, declared: {declared['k']}/{declared['n']} {interval_text(declared['wilson_95'])}; failing "
              f"episodes {pools['declared_rule1_pool_failures']}",
              f"  without lab-defect (Phase 19 drift) failures: {clean['k']}/{clean['n']} "
              f"{interval_text(clean['wilson_95'])}; excluded {clean['excluded_failures']}"]
    block = result['declared_criterion']['worst_case_reading']
    lines += ['', 'Declared criterion, worst over each Wilson interval (Phase 20 section 7.6):']
    for name, row in block['per_case'].items():
        power = row['power_min']
        lines.append(f"  {name}: null max v1 {pct(row['null_max']['v1'])} v2 {pct(row['null_max']['v2'])} "
                     f"(strictly lower: {row['v2_null_strictly_lower']}); power min total loss v1 "
                     f"{pct(power['total_loss']['v1'])} v2 {pct(power['total_loss']['v2'])}, halving v1 "
                     f"{pct(power['halving']['v1'])} v2 {pct(power['halving']['v2'])}; "
                     + ('MET' if row['met'] else f"power FAILS on {', '.join(row['power_fails_on'])}"))
    lines.append(f"  null strictly lower on {len(block['null_strictly_lower_on'])} of {len(block['per_case'])}; "
                 f"power fails on {len(block['power_fails_on'])} of {len(block['per_case'])}: {sorted(block['power_fails_on'])}")
    for name, row in block['zero_to_one_for_unmeasured_drawable_identities']['per_case'].items():
        power = row['power_min']
        lines.append(f"  {name} over 0..1: null max v1 {pct(row['null_max']['v1'])} v2 {pct(row['null_max']['v2'])}; "
                     f"v2 below v1 for q in total loss {power['total_loss']['v2_below_v1_for_q']}, halving "
                     f"{power['halving']['v2_below_v1_for_q']}")
    small = result['small_losses']
    lines += ['', 'Small losses on the high-rate cases (rule 3 power, per complete batch):']
    for name, row in list(small['at_point_rates'].items()) + [('q = 0.975', small['at_q_0.975'])]:
        powers = '  '.join(f"{d}: v1 {pct(v['v1'])} v2 {pct(v['v2'])}" for d, v in row['power'].items())
        lines.append(f"  {name} (q {row['q']}): null v1 {pct(row['null_false_harm']['v1'])} v2 "
                     f"{pct(row['null_false_harm']['v2'])} | {powers} | v2 >= v1 from d = "
                     f"{row['v2_power_at_least_v1_from_d']} | MDL 50% v1 {row['mdl_50pct']['v1']} v2 {row['mdl_50pct']['v2']}, "
                     f"80% v1 {row['mdl_80pct']['v1']} v2 {row['mdl_80pct']['v2']}")
    lines.append(f"  v2 detection floor (largest L that fires, by B0 of 15): {small['v2_detection_floor_max_L_by_B0_of_15']}")
    program = small['program_scenario_0.97_drops_to_0.6']
    lines.append(f"  program scenario 0.97 -> 0.6: v1 {pct(program['v1'])} v2 {pct(program['v2'])}")
    outcomes = result['phase24_outcomes']
    lines += ['', 'Phase 24 outcomes (NO_HARM / HARM / no verdict), within 2 attempts [within 3]:']
    for group in ('policy_with_no_effect', 'harmful_policy'):
        for label, row in outcomes[group].items():
            parts = []
            for design in ('v1', 'v2'):
                two, three = row[design]['within_2'], row[design]['within_3']
                parts.append(f"{design} {two['NO_HARM']:.3f}/{two['HARM']:.3f}/{two['no_verdict']:.3f} "
                             f"[{three['NO_HARM']:.3f}/{three['HARM']:.3f}/{three['no_verdict']:.3f}] "
                             f"P(NH|v) {row[design]['p_no_harm_given_a_verdict']}")
            lines.append(f'  {label}: ' + ' | '.join(parts))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', type=pathlib.Path, default=MAIN_STORE)
    parser.add_argument('--phase20-store', type=pathlib.Path, default=PHASE20_STORE)
    parser.add_argument('--out', type=pathlib.Path, help='also write the JSON result here')
    args = parser.parse_args(argv)
    result = build(measure({'phase20': args.phase20_store, 'main': args.store}))
    # Provenance (review round 1): which script produced this output, from which inputs.
    result['provenance'] = {'script': str(pathlib.Path(__file__).resolve().relative_to(ROOT)),
                            'script_sha256': file_facts(__file__)['sha256'],
                            'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                            'inputs': {'phase20_store': file_facts(args.phase20_store), 'main_store': file_facts(args.store),
                                       'phase19_drift_list': file_facts(DRIFT_ARTIFACT)}}
    print(report(result), end='')
    print(f"provenance: script sha256 {result['provenance']['script_sha256']}")
    if args.out:
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
