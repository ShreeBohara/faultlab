"""Phase 25 protocol numbers ($0: no provider call, no .env read, the store opened read-only).

Every boundary, false-alarm, power, token and retry figure quoted in
docs/part2/PHASE25_EXPERIMENT.md's "Boundaries, false alarms and power" and "Bounds, spend cap"
sections comes from this file. It imports the harness's own read-out code, thresholds, simulated
draw and plan builder (scripts/experiments/slot2_probe.py), so the numbers are computed by the code
that will decide. It writes nothing: run it and save its output.

Run from the repository root:
  ./.venv/bin/python -B scripts/experiments/slot2_protocol_numbers.py \
      > artifacts/phase25-2026-09-24/protocol-numbers/protocol_numbers-r3.out.json

If the harness changes again: set PLANNED_PLAN_HASH to the new dry plan's hash, give SEED and the output
file a new round label, re-run, and re-run the mutation check against the new harness (protocol §12).

Simulation models (stated, not measured):
- 26 prompts; 3 draws per prompt per slot-2 arm (the plan), or 1 in the round-1 fallback; every
  draw received;
- each draw is INVALID with probability 0.03 in both arms (the builder's model);
- otherwise it is DISTINCT with a per-prompt probability whose mean makes the unconditional
  distinct rate d, and a DISTINCT draw FIRES (its step fires) with a per-prompt probability whose
  mean makes the unconditional firing rate w; the rest are duplicates of slot 1;
- harm at the store's rates (round-1 review): a firing draw is harmful with probability 3/9, a
  distinct non-firing draw with 1/26 (the 35 distinct v4-era policies, audited at $0; recomputed
  below as harm_model_from_store). A WORKING draw fires and is not harmful, so the working rate is
  about 2w/3;
- 2 of the 26 prompts have a slot-1 policy whose step fires (the census); condition 5 leaves them out;
- the per-prompt probabilities are Beta draws with intra-prompt correlation rho (rho = 0 is the
  builder's independence model in the dry plan's power.json). C and the treated arm draw their prompt
  effects independently of each other, which is the conservative end for the paired sign test;
- review round 2: C and the treated arm may cluster differently (C at temperature 0 near-deterministic
  per prompt, rho_C 0.8, against T at 0.7, rho_X 0.0 or 0.2), and the reverse. Condition 5 is the
  working SHARE gain (X's WORKING share of its planned draws minus C's WORKING-or-missing share, summed
  over eligible prompts); its minimum is the smallest multiple of 1/(draws per prompt) whose worst yield-
  null cell is at most 0.05. The round-1 count of prompts with any WORKING draw is recomputed beside it
  (at its old minimum of 6) to show what the change removed;
- the shared-effect model (round-1 review): the per-prompt firing propensity is the SAME in both
  arms (firing draws are distinct). Positive correlation between the arms makes a false yield
  signal rarer; it is used only for the yield null;
- review round 3, the repeat (copy) model: an arm at temperature 0 may return the same output for the
  same input. Each prompt's first draw is drawn at the arm's mean rates (d, w); each later repeat is a
  copy of that first draw (its class, WORKING and harm included) with probability q, else an
  independent draw at the same rates. At q = 1 every prompt's share is 0 or 1, so the share gain is a
  whole number and a minimum of 7/3, 8/3 or 3 acts as a count of 3 prompts. The Beta model cannot reach
  this case: it draws each draw's class and harm independently, however large rho is. The grid runs the
  copy model in both arms (q 0.9 and 1.0; C and H are both at temperature 0), in C only (q 0.9 and 1.0,
  with X at rho 0.0, and q 1.0 with X at rho 0.2; T at 0.7 against C at 0), and in X only (q 1.0, C at
  rho 0.0).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import importlib.util  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import pathlib  # noqa: E402
import random  # noqa: E402
import statistics  # noqa: E402
from collections import Counter  # noqa: E402
from fractions import Fraction  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('slot2_probe', ROOT / 'scripts/experiments/slot2_probe.py')
probe = importlib.util.module_from_spec(SPEC)
sys.modules['slot2_probe'] = probe
SPEC.loader.exec_module(probe)

PROMPTS = 26
REPEATS = probe.SLOT2_REPEATS
DRAWS = PROMPTS * REPEATS
INVALID = probe.SIM_INVALID
SIMULATIONS = 2000
NULL_SIMULATIONS = 4000
SEED = 'faultlab-phase25-protocol-numbers-r3'
PLANNED_PLAN_HASH = '5db5c880905661cc37c1e813ef860e9e6c26d9e7e9ccbf50fb4730c2ea434df5'
PRICE_IN, PRICE_OUT = 1.31e-6, 3.96e-6   # frozen Mechanic pricing, per token
ROUND1_BREADTH_K = 6   # round 1's prompt-count minimum, recomputed beside the share gain (descriptive)


def thresholds(repeats):
    """Candidate working-share minimums: the multiples of 1/repeats from 1/repeats to 10 (the gain's lattice)."""
    return [Fraction(i, repeats) for i in range(1, 10 * repeats + 1)]


def smallest(predicate, upto):
    return next((k for k in range(upto + 1) if predicate(k)), None)


def boundaries_at(n):
    """Count boundaries of every declared rate condition at full receipt, n planned draws per arm."""
    need = smallest(lambda k: Fraction(k, n) >= probe.DISTINCT_GAIN_MIN, n)
    return {
        'planned_draws_per_arm': n,
        'complete_min_received': smallest(lambda k: Fraction(k, n) >= probe.COMPLETE_MIN, n),
        'distinct_X_min': smallest(lambda k: Fraction(k, n) >= probe.DISTINCT_MIN, n),
        'distinct_gain_min_draws': need,
        'C_distinct_plus_missing_max_for_any_recommendation': n - need,
        'C_distinct_ceiling_rate': round((n - need) / n, 4),
        'invalid_excess_max_draws_at_full_receipt': max(k for k in range(n + 1) if Fraction(k, n) <= probe.INVALID_MARGIN),
        'harmful_of_firing_max_by_firing_draws': {f: max(k for k in range(f + 1) if Fraction(k, f) <= probe.HARMFUL_FIRING_SHARE_MAX)
                                                  for f in (3, 6, 9, 12, 15, 20)},
        'mechanism_duplicate_drop_min_draws_at_full_receipt': smallest(
            lambda k: Fraction(k, n) >= probe.MECHANISM_GAIN_MIN, n),
        'mechanism_distinct_gain_min_draws_at_full_receipt': smallest(
            lambda k: Fraction(k, n) >= probe.MECHANISM_DISTINCT_GAIN_MIN, n),
        'mechanism_non_candidate_excess_max_draws_at_full_receipt': max(
            k for k in range(n + 1) if Fraction(k, n) <= probe.MECHANISM_NONCANDIDATE_MARGIN),
    }


def boundaries():
    sign = {}
    for untied in range(1, PROMPTS + 1):
        k = smallest(lambda f: probe.sign_test_greater(f, untied - f) < probe.SIGN_ALPHA, untied)
        sign[untied] = None if k is None else {'min_favouring': k,
                                               'p': round(probe.sign_test_greater(k, untied - k), 5)}
    return {'all_rounds': {**boundaries_at(DRAWS), 'working_share_gain_min': str(probe.WORKING_SHARE_GAIN_MIN),
                           'working_share_gain_min_in_draws_at_3_per_prompt': str(probe.WORKING_SHARE_GAIN_MIN * REPEATS)},
            'round1_fallback': {**boundaries_at(PROMPTS),
                                'working_share_gain_min': str(probe.WORKING_SHARE_GAIN_MIN_ROUND1),
                                'working_share_gain_min_in_draws_at_1_per_prompt': str(probe.WORKING_SHARE_GAIN_MIN_ROUND1)},
            'eligible_prompts_for_working': PROMPTS - probe.SIM_SLOT1_FIRING_PROMPTS,
            'sign_test_min_favouring_by_untied_prompts': sign}


def prompt_probability(rng, mean, rho):
    if mean <= 0:
        return 0.0
    if mean >= 1:
        return 1.0
    if rho <= 0:
        return mean
    scale = (1 - rho) / rho
    return rng.betavariate(mean * scale, (1 - mean) * scale)


def arm_rows(rng, d, w, rho, repeats=REPEATS):
    """The Beta model: per-prompt distinct and firing probabilities, independent of the other arm."""
    valid = 1 - INVALID
    rows = []
    for p in range(PROMPTS):
        pd = prompt_probability(rng, min(1.0, d / valid), rho)
        pw = prompt_probability(rng, (w / d) if d > 0 else 0.0, rho)
        rows.extend(probe.simulated_draw(rng, p, r, distinct_p=pd, firing_p=pw) for r in range(repeats))
    return rows


def copy_rows(rng, d, w, q, repeats=REPEATS):
    """The repeat (copy) model (review round 3): each prompt's first draw at the mean rates; each later repeat is
    a copy of the first draw (class, WORKING and harm included) with probability q, else an independent draw."""
    valid = 1 - INVALID
    pd, pw = min(1.0, d / valid), (w / d) if d > 0 else 0.0
    rows = []
    for p in range(PROMPTS):
        first = probe.simulated_draw(rng, p, 0, distinct_p=pd, firing_p=pw)
        rows.append(first)
        for r in range(1, repeats):
            rows.append({**first, 'request': {**first['request'], 'repeat': r}} if rng.random() < q
                        else probe.simulated_draw(rng, p, r, distinct_p=pd, firing_p=pw))
    return rows


def rows_for(rng, model, d, w, repeats=REPEATS):
    """One arm's rows under a scenario's model for that arm: ('beta', rho) or ('copy', q)."""
    kind, value = model
    if kind == 'beta':
        return arm_rows(rng, d, w, value, repeats)
    if kind == 'copy':
        return copy_rows(rng, d, w, value, repeats)
    raise ValueError(f'unknown model {model!r}')


def shared_rows(rng, propensities, d, rho, repeats=REPEATS):
    """The shared-effect model: prompt p fires with the given per-draw propensity (among valid draws) in
    both arms; firing draws are distinct; the remaining distinct rate makes the unconditional rate d."""
    valid = 1 - INVALID
    rows = []
    for p, q in enumerate(propensities):
        target = min(0.999, d / valid)
        rest = prompt_probability(rng, max(1e-6, (target - q) / (1 - q)), rho) if target > q else 0.0
        distinct_p = q + (1 - q) * rest
        firing_p = q / distinct_p if distinct_p > 0 else 0.0
        rows.extend(probe.simulated_draw(rng, p, r, distinct_p=distinct_p, firing_p=firing_p) for r in range(repeats))
    return rows


# Each scenario is (C's model, X's model): ('beta', rho) or ('copy', q).
SCENARIOS = {
    'independent (rho_C 0, rho_X 0; the builder\'s model)': (('beta', 0.0), ('beta', 0.0)),
    'T-like (rho_C 0.5, rho_X 0.2)': (('beta', 0.5), ('beta', 0.2)),
    'H-like (rho_C 0.8, rho_X 0.8)': (('beta', 0.8), ('beta', 0.8)),
    # Review round 2: the arms cluster differently. C at temperature 0 as clustered as the H-like C, T less.
    'C clustered, X not (rho_C 0.8, rho_X 0.0)': (('beta', 0.8), ('beta', 0.0)),
    'C clustered, X mildly (rho_C 0.8, rho_X 0.2)': (('beta', 0.8), ('beta', 0.2)),
    'X clustered, C not (rho_C 0.0, rho_X 0.8)': (('beta', 0.0), ('beta', 0.8)),
    # Review round 3: a temperature-0 arm repeats its own first draw (class and harm included) with probability q.
    'both arms repeat (q 0.9)': (('copy', 0.9), ('copy', 0.9)),
    'both arms repeat (q 1.0)': (('copy', 1.0), ('copy', 1.0)),
    'C repeats (q 0.9), X not (rho_X 0.0)': (('copy', 0.9), ('beta', 0.0)),
    'C repeats (q 1.0), X not (rho_X 0.0)': (('copy', 1.0), ('beta', 0.0)),
    'C repeats (q 1.0), X mildly (rho_X 0.2)': (('copy', 1.0), ('beta', 0.2)),
    'X repeats (q 1.0), C not (rho_C 0.0)': (('beta', 0.0), ('copy', 1.0)),
}
# The yield null (round-1 review): X more distinct than C, but its step fires no more often. The minimum is
# chosen on this grid; common firing rates 0.15 and 0.20 are reported beside it (review round 2), not chosen on.
YIELD_NULL_GRID = ((0.30, 0.04, 0.80, 0.04), (0.30, 0.04, 0.90, 0.04), (0.30, 0.10, 0.80, 0.10),
                   (0.30, 0.10, 0.90, 0.10))
OUTSIDE_GRID = ((0.30, 0.15, 0.80, 0.15), (0.30, 0.15, 0.90, 0.15), (0.30, 0.20, 0.80, 0.20),
                (0.30, 0.20, 0.90, 0.20))
SHARED_RHOS = (0.0, 0.5, 0.8)


def _k_free(result):
    """Whether every condition except the working-share gain holds, the share gain (exact), and the round-1
    breadth count (descriptive)."""
    others = all(v for k, v in result['conditions'].items() if not k.startswith('working_share_gain'))
    share = result['working_share']
    return others, Fraction(share['gain_exact']), share['breadth_prompt_count_descriptive']['gain']


def null_cells(rng, repeats, grid, shared_ws):
    cells = []
    for name, (model_c, model_x) in SCENARIOS.items():
        for d_c, w_c, d_x, w_x in grid:
            outcomes = [_k_free(probe.contrast(rows_for(rng, model_x, d_x, w_x, repeats),
                                               rows_for(rng, model_c, d_c, w_c, repeats), 'X', working_gain_min=0))
                        for _ in range(NULL_SIMULATIONS)]
            cells.append({'model': name, 'd_c': d_c, 'w_c': w_c, 'd_x': d_x, 'w_x': w_x, 'outcomes': outcomes})
    for rho in SHARED_RHOS:
        for w in shared_ws:
            for d_x in (0.80, 0.90):
                outcomes = []
                for _ in range(NULL_SIMULATIONS):
                    propensities = [prompt_probability(rng, w / (1 - INVALID), rho) for _ in range(PROMPTS)]
                    outcomes.append(_k_free(probe.contrast(shared_rows(rng, propensities, d_x, rho, repeats),
                                                           shared_rows(rng, propensities, 0.30, rho, repeats), 'X',
                                                           working_gain_min=0)))
                cells.append({'model': f'shared firing propensity (rho {rho})', 'd_c': 0.30, 'w_c': w, 'd_x': d_x,
                              'w_x': w, 'outcomes': outcomes})
    return cells


def summarise(cell, candidates):
    outcomes = cell.pop('outcomes')
    n = len(outcomes)
    cell['p_recommend_by_share_gain_min'] = {str(k): round(sum(1 for ok, gain, _ in outcomes if ok and gain >= k) / n, 4)
                                             for k in candidates}
    cell['p_other_conditions_pass'] = round(sum(1 for ok, _, _ in outcomes if ok) / n, 4)
    cell['mean_share_gain'] = round(float(sum(gain for _, gain, _ in outcomes) / n), 4)
    cell['mean_round1_breadth_count_gain_descriptive'] = round(sum(b for _, _, b in outcomes) / n, 4)
    cell[f'p_recommend_round1_breadth_count_at_{ROUND1_BREADTH_K}_descriptive'] = round(
        sum(1 for ok, _, b in outcomes if ok and b >= ROUND1_BREADTH_K) / n, 4)
    return cell


def yield_null(rng, repeats):
    """P(RECOMMEND) for each candidate working-share minimum under the yield null, in every Beta scenario and
    the shared model; the smallest minimum whose worst cell is at most 0.05 is the chosen one. The same cells
    at common firing rates 0.15 and 0.20 are reported at the chosen minimum, descriptive only."""
    candidates = thresholds(repeats)
    table = [summarise(cell, candidates) for cell in null_cells(rng, repeats, YIELD_NULL_GRID, (0.04, 0.10))]
    worst = {str(k): max(cell['p_recommend_by_share_gain_min'][str(k)] for cell in table) for k in candidates}
    chosen = next(k for k in candidates if worst[str(k)] <= 0.05)
    by_model = {}
    for cell in table:
        value = cell['p_recommend_by_share_gain_min'][str(chosen)]
        by_model[cell['model']] = max(by_model.get(cell['model'], 0.0), value)
    outside = [summarise(cell, [chosen]) for cell in null_cells(rng, repeats, OUTSIDE_GRID, (0.15, 0.20))]
    return {'simulations_per_cell': NULL_SIMULATIONS, 'cells': table, 'worst_cell_by_share_gain_min': worst,
            'smallest_share_gain_min_with_worst_cell_at_most_0.05': str(chosen),
            'worst_cell_at_the_chosen_minimum': worst[str(chosen)],
            'worst_cell_by_model_at_the_chosen_minimum': by_model,
            'worst_cell_of_the_round1_breadth_count_at_6_descriptive': max(
                cell[f'p_recommend_round1_breadth_count_at_{ROUND1_BREADTH_K}_descriptive'] for cell in table),
            'outside_the_grid_at_the_chosen_minimum_descriptive': outside,
            'outside_the_grid_worst_cell_descriptive': max(cell['p_recommend_by_share_gain_min'][str(chosen)]
                                                           for cell in outside)}


RECOMMEND_GRID = ((0.30, 0.04, 0.30, 0.04), (0.50, 0.10, 0.50, 0.10), (0.30, 0.04, 0.60, 0.10),
                  (0.30, 0.04, 0.70, 0.10), (0.30, 0.04, 0.80, 0.10), (0.30, 0.04, 0.80, 0.15),
                  (0.30, 0.04, 0.80, 0.25), (0.30, 0.04, 0.90, 0.25), (0.30, 0.04, 0.80, 0.35),
                  (0.30, 0.04, 0.90, 0.40), (0.50, 0.04, 0.90, 0.25))


def recommend_table(rng, repeats, k, scenarios):
    table = []
    for name, (model_c, model_x) in scenarios.items():
        for d_c, w_c, d_x, w_x in RECOMMEND_GRID:
            passed, failed = 0, Counter()
            for _ in range(SIMULATIONS):
                result = probe.contrast(rows_for(rng, model_x, d_x, w_x, repeats), rows_for(rng, model_c, d_c, w_c, repeats),
                                        'X', working_gain_min=k)
                passed += result['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP'
                failed.update(result['failed'])
            table.append({'scenario': name, 'd_c': d_c, 'w_c': w_c, 'd_x': d_x, 'w_x': w_x,
                          'p_recommend': round(passed / SIMULATIONS, 3),
                          'share_failing_each_condition': {c: round(v / SIMULATIONS, 3) for c, v in sorted(failed.items())}})
    return table


MECHANISM_GRID = (0.66, 0.50, 0.40, 0.36, 0.30, 0.10)   # H's duplicate rate; C at 0.66


def mechanism_table(rng, repeats=REPEATS):
    """P(COPYING_OF_THE_PRIOR_TEXT_SHOWN) with C duplicating at 0.66 of draws (18 of 26 historically, less
    the 3% invalid), H at each rate in MECHANISM_GRID; both at temperature 0, so both follow the same model: Beta
    at rho 0, 0.5 and 0.8, and (review round 3) the repeat model at q 1.0."""
    table = []
    for model in (('beta', 0.0), ('beta', 0.5), ('beta', 0.8), ('copy', 1.0)):
        for dup_h in MECHANISM_GRID:
            shown = 0
            for _ in range(SIMULATIONS):
                c_rows = rows_for(rng, model, 1 - INVALID - 0.66, 0.0, repeats)
                h_rows = rows_for(rng, model, 1 - INVALID - dup_h, 0.0, repeats)
                shown += probe.mechanism_readout(c_rows, h_rows, [], [])['decision'] == 'COPYING_OF_THE_PRIOR_TEXT_SHOWN'
            table.append({'model': f'{model[0]} {model[1]}', 'rho': model[1] if model[0] == 'beta' else None,
                          'dup_c': 0.66, 'dup_h': dup_h, 'p_shown': round(shown / SIMULATIONS, 3)})
    return table


def _row(prompt, cls='CANDIDATE', distinct=False, firing=False, harmful=False):
    audit = None if cls != 'CANDIDATE' else {'harmful': harmful, 'step_present': firing, 'dead_step': False,
                                             'step_fires': firing, 'premature_defer': harmful,
                                             'stops_first_confirmation': False, 'orders_retry': False}
    c = {'class': cls, 'distinct': distinct, 'duplicate_of_slot1': cls == 'CANDIDATE' and not distinct,
         'distinct_firing': distinct and firing, 'working': distinct and firing and not harmful, 'policy_hash': None,
         'byte_identical_to_slot1': False, 'rules_text_identical_to_slot1': False, 'audit': audit}
    return {'request': {'prompt_id': f'p{prompt}', 'repeat': 0,
                        'reference': {'slot1_step_fires': False, 'slot1_policy_hash': f'p{prompt}'}},
            'result': {}, 'received': True, 'c': c}


def adversarial_cases():
    """The round-1 review's constructed cases, re-run on the revised read-outs."""
    control = [_row(p, distinct=p >= 18) for p in range(26) for _ in range(3)]
    out = {}
    for name, cls in (('H answers NO_CHANGE on every prompt where C duplicates', 'NO_CHANGE'),
                      ('H answers INVALID on every prompt where C duplicates', 'INVALID')):
        hidden = [_row(p, cls=cls) if p < 18 else _row(p, distinct=True) for p in range(26) for _ in range(3)]
        result = probe.mechanism_readout(control, hidden, [], [])
        out[name] = {'decision': result['decision'], 'failed': result['failed']}
    history_like = [_row(p, distinct=p < 7, firing=p == 0, harmful=p == 0) for p in range(26) for _ in range(3)]
    all_harmful = [_row(p, distinct=p < 21, firing=p < 4, harmful=p < 4) for p in range(26) for _ in range(3)]
    result = probe.contrast(all_harmful, history_like, 'X')
    out['every firing draw of X is harmful (premature defer)'] = {'decision': result['decision'],
                                                                   'failed': result['failed']}
    return out


def plan_facts():
    """Token-priced cost of the actual planned prompts, and facts about the census, from the real plan."""
    plan, prompts = probe.build_plan()
    facts = {'plan_hash': probe.plan_hash(plan), 'plan_hash_is_the_declared_one': probe.plan_hash(plan) == PLANNED_PLAN_HASH,
             'harness_sha256': plan['harness_sha256']}
    tokens = {h: probe.local_prompt_tokens(p['messages']) + probe.FRAMING_TOKENS for h, p in prompts.items()}
    connection = probe.connect(probe.STORE)
    try:
        studies, _ = probe.load_population(connection)
        outputs = {1: [], 2: []}
        for study in studies:
            for slot in (1, 2):
                first = probe.output_attempts(connection, study['candidates'][slot - 1].get('proposal_ref'))[0]
                outputs[slot].append((first.get('usage') or {}).get('output_tokens'))
        history_keys = sorted({key for s in studies for key in s['candidates'][0]})
        feedback = Counter(sum(1 for r in s.get('trial_rows') or [] if r['stage'] == 'candidate-1') for s in studies)
        failures = Counter()
        for (payload,) in connection.execute("select payload from records where kind='provider_failures'"):
            record = json.loads(payload)
            if record.get('role') == 'mechanic':
                failures[(record.get('diagnostics') or {}).get('code')] += 1
        mechanic_outputs = connection.execute("select count(*) from records where kind='mechanic_outputs'").fetchone()[0]
        others = probe._other_v4_studies(connection, [{'study': s} for s in studies], probe.STORE_CUTOFF)
    finally:
        connection.close()
    policies = {}
    for study in studies + others:
        for candidate in study.get('candidates') or []:
            if candidate.get('content'):
                policies.setdefault(candidate['policy_hash'], probe.audit_policy(candidate['content']))
    firing = [a for a in policies.values() if a['step_fires']]
    silent = [a for a in policies.values() if not a['step_fires']]
    harm = {'distinct_v4_policies': len(policies),
            'firing': [sum(a['harmful'] for a in firing), len(firing)],
            'not_firing': [sum(a['harmful'] for a in silent), len(silent)]}
    harm['equals_the_simulation_model'] = (Fraction(*harm['firing']) == probe.SIM_HARMFUL_FIRING
                                           and Fraction(*harm['not_firing']) == probe.SIM_HARMFUL_NOT_FIRING)
    median_out = {slot: statistics.median(values) for slot, values in outputs.items()}
    by_arm = {}
    for request in plan['requests']:
        entry = by_arm.setdefault(request['arm'], {'requests': 0, 'input_tokens': []})
        entry['requests'] += 1
        entry['input_tokens'].append(tokens[request['messages_hash']])
    estimate = ceiling = 0.0
    arms = {}
    for arm, entry in sorted(by_arm.items()):
        out = median_out[2]
        est = sum(t * PRICE_IN + out * PRICE_OUT for t in entry['input_tokens'])
        top = sum(t * PRICE_IN + probe.MECHANIC_MAX_OUTPUT_TOKENS * PRICE_OUT for t in entry['input_tokens'])
        estimate, ceiling = estimate + est, ceiling + top
        arms[arm] = {'requests': entry['requests'], 'input_tokens_median': statistics.median(entry['input_tokens']),
                     'input_tokens_min': min(entry['input_tokens']), 'input_tokens_max': max(entry['input_tokens']),
                     'estimate_at_median_historical_slot2_output': round(est, 2), 'ceiling_at_2000_output': round(top, 2)}
    investigation = plan['investigation']['mechanism']['per_study']
    growth = [b[1] - b[0] for b in (row['user_bytes'] for row in investigation)]
    first_duplicates = Counter((row['phase'], row['policy_duplicate_of_slot1']) for row in investigation)
    final = Counter((probe.DECLARED_CONFIGURATIONS[s['configuration_hash']], s['candidates'][1].get('decision'))
                    for s in studies)
    calls = mechanic_outputs + sum(failures.values())
    rate = sum(failures.values()) / calls
    total = plan['counts']['total_requests']
    headroom = plan['cost']['retry_headroom_attempts']
    tail = sum(math.comb(total, k) * rate ** k * (1 - rate) ** (total - k) for k in range(headroom + 1, total + 1))
    requests = plan['requests']

    def nth(arm, count, *, round1=False):
        seen = 0
        for request in requests:
            if request['arm'] == arm and (not round1 or request['repeat'] == 0):
                seen += 1
                if seen == count:
                    return request['request_id']
        return None
    full = {arm: nth(arm, 75) for arm in probe.SLOT2_ARMS}
    facts.update({
        'tokens_by_arm': arms,
        'historical_output_tokens_median': median_out,
        'token_priced_estimate_total': round(estimate, 2),
        'token_priced_ceiling_total_at_2000_output': round(ceiling, 2),
        'planned_bound': plan['cost']['planned_upper_bound'],
        'slot2_user_message_growth_bytes': {'min': min(growth), 'max': max(growth)},
        'slot1_candidate_history_entry_keys': history_keys,
        'slot1_source_rows_in_slot2_input': dict(feedback),
        'first_attempt_duplicates_by_phase': {f'{p}/{d}': n for (p, d), n in sorted(first_duplicates.items())},
        'final_slot2_decisions_by_phase': {f'{p}/{d}': n for (p, d), n in sorted(final.items())},
        'harm_model_from_store': harm,
        'mechanic_transport_failures_in_store': dict(failures),
        'mechanic_outputs_in_store': mechanic_outputs,
        'mechanic_transport_failure_rate_per_call': round(rate, 4),
        'retry_headroom_attempts': headroom,
        'p_more_blind_retries_than_headroom_if_independent': tail,
        'stop_points': {
            'round1_last_request': max(r['request_id'] for r in requests if r['repeat'] == 0),
            'earliest_request_at_which_round1_can_be_complete_per_arm': {
                arm: nth(arm, 25, round1=True) for arm in probe.SLOT2_ARMS},
            'earliest_request_at_which_all_rounds_can_be_complete_per_arm': full,
        },
    })
    return facts


def undelivered_runs_before_the_plan_no_longer_fits():
    """How many earlier runs that delivered nothing (each charged 5 errored requests x 2 attempts) the
    phase cap absorbs before the 260-request plan no longer fits."""
    per_run = probe.CONSECUTIVE_ERROR_ABORT * 2
    attempts = probe.SpendGuard.micro(probe.HARD_SPEND_CAP) // probe.SpendGuard.micro(probe.PER_REQUEST_DOLLAR_BOUND)
    runs = 0
    while attempts - per_run * (runs + 1) >= 260:
        runs += 1
    return {'attempts_under_phase_cap': attempts, 'attempts_per_undelivered_run': per_run,
            'undelivered_runs_after_which_the_plan_still_fits': runs}


def main():
    rng = random.Random(SEED)
    null_full = yield_null(rng, REPEATS)
    null_round1 = yield_null(rng, 1)
    out = {'schema': 'faultlab-slot2-protocol-numbers/v4', 'models': __doc__.split('Simulation models')[1].strip(),
           'simulations': SIMULATIONS, 'boundaries': boundaries(),
           'undelivered_runs': undelivered_runs_before_the_plan_no_longer_fits(),
           'yield_null_all_rounds': null_full,
           'yield_null_round1_fallback': null_round1,
           'harness_minimum_is_the_chosen_one': {
               'all_rounds': (Fraction(null_full['smallest_share_gain_min_with_worst_cell_at_most_0.05'])
                              == probe.WORKING_SHARE_GAIN_MIN),
               'round1_fallback': (Fraction(null_round1['smallest_share_gain_min_with_worst_cell_at_most_0.05'])
                                   == probe.WORKING_SHARE_GAIN_MIN_ROUND1)},
           'builder_power_table_reproduced': probe.power_table()['table'],
           'recommend': recommend_table(rng, REPEATS, probe.WORKING_SHARE_GAIN_MIN, SCENARIOS),
           'recommend_round1_fallback': recommend_table(
               rng, 1, probe.WORKING_SHARE_GAIN_MIN_ROUND1,
               {'one draw per prompt (rho and q have no effect on a single draw)': (('beta', 0.0), ('beta', 0.0))}),
           'mechanism': mechanism_table(rng), 'mechanism_round1_fallback': mechanism_table(rng, 1),
           'adversarial_cases': adversarial_cases(), 'plan_facts': plan_facts()}
    print(json.dumps(out, indent=2, default=str))


if __name__ == '__main__':
    main()
