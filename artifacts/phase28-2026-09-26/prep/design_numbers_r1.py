"""Phase 28 design arithmetic, revision 1 ($0). Every number here is a MODEL ESTIMATE, not a measurement.

Changes against p28-design/design_numbers.py (design review round 1):
  1. Validation set: healthy, upgrade-3 (source), upgrade-2 (sibling), delayed-upgrade (dev-3, F2 d3
     SUCCEEDED), upgrade-18 (SAFE_UNRESOLVED), lost-upgrade-response, terminal-upgrade-rejection.
     No notification-fault case, so the untriggered nuisance is the upgrade-fault rate only (measured
     0 untriggered in every upgrade-side episode of the data pass).
  2. Futility look: the stop event is a SUBSET of {k = 0 before the look} (R = 0 means no step, and a
     certification needs the step), so P(k>=1) = 1 - stop - ((1-p)^L - stop) * (1-p)^(N-L).
     The old script multiplied P(stop) by P(k=0 before the look) as if independent.
  3. The look's timing is a declared assumption (Phase 23: 1.19 distinct valid policies per
     controls-passing study); a slower-rate scenario and the never-reached cost bound are added.
  4. Phase 28a Mechanic-only probe: P(NO_GO | s) = (1 - r)^K with K = 30 draws, r = s / 0.75.
"""
import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def p_le(n, k, p):
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def p_at_least(k, n, p):
    return 1 - sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k))


def funnel(p_leak, s, clean, lviol, u18, healthy3, refusal, src3, guard1, fresh, infra=0.949, slot2_gain=0.10):
    ctrl = (1 - p_leak) ** 3 * healthy3
    s_eff = s * (1 + slot2_gain)
    gate = (1 - p_leak) ** 3 * 0.95
    # two false-regression guards now: lost-upgrade-response and delayed-upgrade (both B0 6 of 6)
    val = clean * lviol * u18 * healthy3 * refusal * src3 * guard1 ** 2
    return {'ctrl': ctrl, 's_eff': s_eff, 'gate': gate, 'val': val, 'fresh': fresh,
            'P_val_reached': infra * ctrl * s_eff * gate,
            'P_cert': infra * ctrl * s_eff * gate * val * fresh}


SCEN = {
    'low': dict(p_leak=0.167, clean=0.97, lviol=0.93, u18=(1 - 0.02) ** 3, healthy3=0.893, refusal=0.90,
                src3=0.93, guard1=0.925, fresh=p_le(3, 1, 0.238) * 0.95),
    'mid': dict(p_leak=0.127, clean=0.99, lviol=0.97, u18=(1 - 0.01) ** 3, healthy3=0.905, refusal=0.95,
                src3=0.95, guard1=0.95, fresh=p_le(3, 1, 0.167) * 0.97),
    'high': dict(p_leak=0.095, clean=1.0, lviol=0.99, u18=(1 - 0.003) ** 3, healthy3=0.917, refusal=1.0,
                 src3=0.97, guard1=0.97, fresh=p_le(3, 1, 0.127) * 0.99),
}
# The design's first version, kept to show what the case change and the formula fix each move.
OLD_SCEN_MID = dict(p_leak=0.127, clean=(1 - 0.016) ** 12, lviol=0.97, u18=1.0, healthy3=0.905, refusal=0.95,
                    src3=0.95, guard1=math.sqrt(0.95), fresh=p_le(3, 1, 0.167) * 0.97)
S_VALUES = (0.02, 0.05, 0.10, 0.15, 0.27, 0.40)

A = 0.0209
M = 0.04984
EP = {  # (B0 $, L $) per episode, from p28-understand/costs.json; a working repair's L episodes assumed
    'healthy': (4.25 * A, 4.19 * A), 'upgrade-3': (7.76 * A, 6.0 * A), 'upgrade-2': (7.43 * A, 6.0 * A),
    'delayed-upgrade': (7.0 * A, 5.0 * A),          # B0 measured 7 (Phase 20, n=6); L assumed 5 (dd62c857: 4)
    'upgrade-18': (8.0 * A, 8.0 * A),               # B0 as count 4 (8, n=21); L assumed the 8-turn maximum
    'lost-upgrade-response': (4.33 * A, 4.17 * A),
    'terminal-upgrade-rejection': (5.07 * A, 3.22 * A)}
C_CTRL = 3 * (EP['upgrade-3'][0] + EP['healthy'][0])
C_SRC = 3 * (EP['upgrade-3'][0] + EP['upgrade-3'][1]) + 2 * M
C_VAL = sum(3 * (b + l) for b, l in EP.values())
WORST = 60 * 8 * A + 4 * M


def expected_cost(ctrl, s_eff, gate, p_slot2_src=0.35, infra=0.949):
    reach_val = s_eff * gate
    return C_CTRL + infra * ctrl * (0.9 * C_SRC + p_slot2_src * C_SRC + reach_val * C_VAL)


LOOK_D = 16
DIST_PER_STUDY = {'phase23 (1.19, declared assumption)': 1.19, 'slower (0.80)': 0.80, 'much slower (0.50)': 0.50}


def look_attempt(ctrl, dist_per_study):
    return math.ceil(LOOK_D / (0.949 * ctrl * dist_per_study))


def futility(s):
    r = min(1.0, s / 0.75)
    return (1 - r) ** LOOK_D


def power_with_futility(p, s, n, look):
    """Correct: the stop event (R = 0 at the look) is a subset of {k = 0 in the first `look` attempts}."""
    if look >= n:
        return p_at_least(1, n, p)
    stop = min(futility(s), (1 - p) ** look)
    return 1 - stop - ((1 - p) ** look - stop) * (1 - p) ** (n - look)


def power_with_futility_old(p, s, n, look):
    """The first version's formula (treats the stop and k = 0 before the look as independent)."""
    no_success_before = (1 - p) ** look
    stop = futility(s)
    return 1 - no_success_before * (stop + (1 - stop) * (1 - p) ** (n - look))


PROBE_K = 30


def probe_no_go(s, k=PROBE_K):
    r = min(1.0, s / 0.75)
    return (1 - r) ** k


def main():
    out = {'stage_costs': {'controls': round(C_CTRL, 2), 'per_source_gate_incl_mechanic': round(C_SRC, 2),
                           'validation_42_eps': round(C_VAL, 2),
                           'validation_reaching_attempt_1_slot': round(C_CTRL + C_SRC + C_VAL, 2),
                           'validation_reaching_attempt_2_slots': round(C_CTRL + 2 * C_SRC + C_VAL, 2),
                           'hard_worst_case_per_attempt': round(WORST, 2)},
           'per_attempt': {}, 'power': {}, 'futility': {}, 'cost': {}, 'probe': {}, 'check_old_formula': {}}
    for s in S_VALUES:
        row = {band: {k: round(v, 4) for k, v in funnel(s=s, **kw).items()} for band, kw in SCEN.items()}
        out['per_attempt'][f's={s}'] = row
        pw = {}
        for band in row:
            p = row[band]['P_cert']
            look = look_attempt(row[band]['ctrl'], 1.19)
            pw[band] = {'N50_no_look': round(p_at_least(1, 50, p), 3),
                        'N50_with_look': round(power_with_futility(p, s, 50, look), 3),
                        'look_at_attempt': look, 'E[k]_N50': round(50 * p, 2),
                        'N30_no_look': round(p_at_least(1, 30, p), 3), 'N40_no_look': round(p_at_least(1, 40, p), 3)}
            # also: with the probe in front (GO needed) - joint probability of a certification
            pw[band]['N50_with_look_and_probe_GO'] = round((1 - probe_no_go(s)) * pw[band]['N50_with_look'], 3)
        out['power'][f's={s}'] = pw
        out['futility'][f's={s}'] = {'r_present': round(min(1, s / 0.75), 4), 'P(stop at look)': round(futility(s), 3)}
        out['probe'][f's={s}'] = {'P(NO_GO) with K=30 draws': round(probe_no_go(s), 3)}
        f = funnel(s=s, **SCEN['mid'])
        c = expected_cost(f['ctrl'], f['s_eff'], f['gate'])
        look = look_attempt(f['ctrl'], 1.19)
        out['cost'][f's={s}'] = {'per_attempt_mid': round(c, 2), 'N50_total_mid_no_look': round(50 * c, 1),
                                 'to_look_mid': round(look * c, 1),
                                 'N50_expected_with_look_mid': round(c * (look + (1 - futility(s)) * (50 - look)), 1)}
        # the reviewer's check: the OLD case set and parameters, old vs corrected formula
        fo = funnel(s=s, **OLD_SCEN_MID)
        lo_ = math.ceil(LOOK_D / (0.949 * 0.60 * 1.19))
        out['check_old_formula'][f's={s}'] = {
            'old_set_P_cert_mid': round(fo['P_cert'], 4),
            'old_formula': round(power_with_futility_old(fo['P_cert'], s, 50, lo_), 3),
            'corrected_formula': round(power_with_futility(fo['P_cert'], s, 50, lo_), 3),
            'no_look': round(p_at_least(1, 50, fo['P_cert']), 3)}
    f0 = funnel(s=0.0, **SCEN['mid'])
    c0 = expected_cost(f0['ctrl'], 0.0, 0.5)
    out['cost']['s=0'] = {'per_attempt_mid': round(c0, 2), 'N50_total_mid_no_look (look never reached)': round(50 * c0, 1)}
    out['look_timing'] = {name: {band: look_attempt(funnel(s=0.05, **kw)['ctrl'], d) for band, kw in SCEN.items()}
                          for name, d in DIST_PER_STUDY.items()}
    out['look_timing_cost_at_s0_mid'] = {name: round(min(50, look_attempt(f0['ctrl'], d)) * c0, 1)
                                         for name, d in DIST_PER_STUDY.items()}
    out['wilson_k_of_50'] = {k: [round(x, 3) for x in wilson(k, 50)] for k in range(0, 9)}
    out['wilson_0_of_D'] = {d: [round(x, 3) for x in wilson(0, d)] for d in (16, 20, 30)}
    out['probe_cost'] = {'draws': PROBE_K, 'calls_worst (format repair on every draw)': 2 * PROBE_K,
                         'bound_worst': round(2 * PROBE_K * M, 2), 'cap': 5.0}
    remaining = 347.10
    p28_max = 150.0 - 11.0 + WORST
    out['budget'] = {'remaining_now': remaining, 'phase29_cap': 15.0, 'phase30_cap': 20.0, 'phase28a_cap': 5.0,
                     'phase28_cap': 150.0, 'max_phase28_charge': round(p28_max, 2),
                     'remaining_at_phase28_approval_if_all_earlier_at_cap': round(remaining - 40.0, 2),
                     'left_after_all_caps_worst': round(remaining - 15.0 - 20.0 - 5.0 - p28_max, 2),
                     'truncation_needs_mean_per_attempt_over': round((150.0 - 11.0) / 49, 2)}
    text = json.dumps(out, indent=1)
    (HERE / 'design_numbers_r1.json').write_text(text)
    print(text)


if __name__ == '__main__':
    main()
