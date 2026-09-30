"""Build the Investigation C table and rates from live_enriched.json + validation.json + treatments.json (all read-only derived)."""
import json, csv, collections
from math import comb

BASE = '/Users/shree/FaultLab_Scratch/inv-c/'
OUT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/analysis-diagnosis-2026-09-30/inv-c/'
L = json.load(open(BASE + 'live_enriched.json'))
V = json.load(open(BASE + 'validation.json'))
T = json.load(open(BASE + 'treatments.json'))

RUN = {
    'campaign-86d3e2025fbd468398c0c47e03e3bc82': '2026-09-13 reference learn #1 (deepseek-learning-attempt1)',
    'campaign-e6ac7b05ebc049f6804d34dc04d4ef72': '2026-09-13 reference learn (deepseek-learning-final)',
    'campaign-44085f54a24144b78252d8eea211ebb8': '2026-09-13 reference learn (v31-repair-final)',
    'campaign-aa79023053da470984118fdb1e9d8138': '2026-09-13 reference learn, split-role V4-Pro lab model',
    'campaign-eb1bcf7e6614450fbfa631b42551ef86': '2026-09-13 reference learn, V4-Pro lab model',
    'campaign-2fdef056b7604ba0bc91a33a656595d1': '2026-09-20 reference learn (Phase 1 era)',
    'campaign-9e7f10cd29ea4eb2b41ad158e262ec5c': '2026-09-20 reference learn (Phase 1 era)',
    'campaign-5a0af912a5244423b61b5f13cff4ec0f': '2026-09-20 reference learn (Phase 2 learning-1)',
    'campaign-7ee35abe': 'native v1 Learn 2026-09-29 (PRODUCT_NATIVE_LEARN_RUN)',
    'campaign-a2fbffe3': 'native v1 Learn v3-history 2026-09-29 (PRODUCT_NATIVE_LEARN_V3_RUN)',
    'campaign-b05ac280': 'native v2 first live Learn 2026-09-29',
    'campaign-ea66672d7a904bd8a011d6922790c963': 'v2d',
    'campaign-37e66b6c3a544a4d9bde4161db6bf0aa': 'v2e',
    'campaign-53db74766f4d4635b94a0de89e492577': 'v2f',
    'campaign-d8d1e8cc0ea34feb92dbd8c22c264530': 'v2g',
}
def run_label(cid):
    if cid in RUN: return RUN[cid]
    for k, v in RUN.items():
        if cid.startswith(k): return v
    return cid

# Hypothesis theme: the analyst's manual reading of each final hypothesis (not a product classification).
THEME = {
    '93da89fe': 'INSUFFICIENT_EVIDENCE', '352d30ca': 'POLICY_RETRY_OR_VERIFY', '55ee968b': 'RECEIPT_TIMING',
    '7fe4d06b': 'POLICY_RETRY_OR_VERIFY', 'ffd281b9': 'POLICY_RETRY_OR_VERIFY', '2b06444a': 'POLICY_RETRY_OR_VERIFY',
    '4c3a41b4': 'POLICY_RETRY_OR_VERIFY', '5d606f16': 'RECEIPT_TIMING', 'b2a7dda4': 'POLICY_RETRY_OR_VERIFY',
    'a3397fd8': 'RECEIPT_TIMING', '0af91fe7': 'RECEIPT_TIMING', '112bdd98': 'RECEIPT_TIMING',
    'd96bd046': 'CITATION_BLAME', 'd6f22b2a': 'RECEIPT_TIMING', '52616f56': 'POLICY_RETRY_OR_VERIFY',
    '53ba2834': 'POLICY_RETRY_OR_VERIFY', 'dc1a11d2': 'RECEIPT_TIMING', 'e0a68956': 'POLICY_RETRY_OR_VERIFY',
    '6cb0e8ab': 'POLICY_RETRY_OR_VERIFY', 'bdf0f68d': 'RECEIPT_TIMING', 'eac3d243': 'INSUFFICIENT_EVIDENCE',
    'a4c8395a': 'RECEIPT_TIMING', 'b4c25b59': 'RECEIPT_TIMING', 'da825066': 'RECEIPT_TIMING',
    '723354f7': 'CITATION_BLAME', '57fa14bc': 'CITATION_BLAME', 'b0eeb89d': 'CITATION_BLAME',
    'dddc1a1b': 'REPORT_CONTENT', 'a0dd0c48': 'CITATION_BLAME', 'dc19567f': 'CITATION_BLAME',
}

# Candidate outcomes. New-era rows come from campaign_proposals / source_validation_results / challenges;
# old-era (2026-09-13) rows come from the record window after the diagnostic (proposals, policies, evaluations, challenges).
CAND = {
    'b2a7dda4': ('3 candidates; 1 PASSED source validation (policy-64f67c5099e741e7b18dab59f1513390) -> challenge-181807331b434fafbc5cb02a331e25ea COUNTEREXAMPLE_FOUND (C5,C6,C7); 4th Mechanic turn NO_CHANGE', 3, 1, 'CHALLENGE_COUNTEREXAMPLE'),
    'a3397fd8': ('4 candidates; all failed source validation (candidate violations 1,1,1,2 of 3)', 4, 0, 'SOURCE_VALIDATION_FAILED'),
    '0af91fe7': ('2 candidates; both failed source validation (incumbent flaky 1/3 and 2/3; candidate violations 1/3, 3/3)', 2, 0, 'SOURCE_VALIDATION_FAILED'),
    '112bdd98': ('1 candidate failed source validation (candidate 1/3 violations); next Mechanic turn NO_CHANGE', 1, 0, 'SOURCE_VALIDATION_FAILED'),
    'd6f22b2a': ('1 candidate CANDIDATE_FAILED; 3 duplicate proposals', 1, 0, 'SOURCE_VALIDATION_FAILED'),
    '6cb0e8ab': ('1 candidate CANDIDATE_FAILED; 3 duplicate proposals', 1, 0, 'SOURCE_VALIDATION_FAILED'),
    'e0a68956': ('none: campaign ended "Complete batch exceeds frozen dollar reservation"', 0, 0, 'NO_CANDIDATE'),
    'a4c8395a': ('2 candidates; policy-87ee150f PASSED -> challenge-2e7d5b9698b3471a9dfdafaa940bc7a0 COUNTEREXAMPLE_FOUND; policy-0e594f33 CANDIDATE_FAILED', 2, 1, 'CHALLENGE_COUNTEREXAMPLE'),
    '57fa14bc': ('1 candidate policy-c65cc08e PASSED -> challenge-559c5dd7 INCONCLUSIVE, 0 failed checks, 9 pairs; campaign then ERROR (Mechanic input limit)', 1, 1, 'CHALLENGE_INCONCLUSIVE_0_FAILED'),
    'dddc1a1b': ('2 candidates policy-93ca3d35 and policy-13f01971 both PASSED -> challenges 4b884740 and a0ca3bb0 INCONCLUSIVE, 0 failed checks, 12 pairs each; 1 duplicate', 2, 2, 'CHALLENGE_INCONCLUSIVE_0_FAILED'),
    'dc19567f': ('1 candidate policy-4fc79941 SOURCE_FLAKY (incumbent 2/3); 1 duplicate; Mechanic NO_CHANGE', 1, 0, 'SOURCE_FLAKY'),
}

def clean(errs, ref_era):
    # Reference-era option ids cannot be recomputed with today's code (hash inputs changed), so that one
    # recomputed error is dropped for them; their interventions ran, which proves the ids were accepted then.
    return '; '.join(e for e in errs if not (ref_era and e == 'unknown_intervention_reference'))

def cnt(lst):
    return f"{sum(x == 'V' for x in lst)}/{len(lst)}"

rows = []
for r in L:
    short = r['diagnostic_id'][11:19]
    atts = r['mechanic_attempts']; first = atts[0]; final = atts[-1]
    val = V[r['diagnostic_id']]
    ref_era = r['agent'].startswith('reference')
    iv = r['interventions'][0] if r['interventions'] else None
    if final['requested_intervention_id'] is None:
        req = 'no (null)'
    else:
        req = 'yes'
    if first['requested_intervention_id'] and not final['requested_intervention_id']:
        req = 'first attempt yes, final attempt no'
    accepted = r['proposal_accepted_by_validator']
    why_rejected = ''
    if not accepted:
        why_rejected = '; '.join(sorted({e for a in val['attempts'] for e in a['schema_and_option_errors']}))
    if accepted and final['requested_intervention_id'] is None:
        outcome = 'DECLINED (valid proposal, no intervention)'
    elif not accepted:
        outcome = 'OUTPUT_REJECTED after format repair -> recorded INCONCLUSIVE'
    else:
        outcome = 'INTERVENTION_RUN'
    requested_change = None
    if not ref_era:
        rc = [a['requested_change'] for a in val['attempts'] if a['requested_change']]
        requested_change = rc[-1] if rc else None
    if iv:
        tr = T.get(iv['id'], {})
        ivtxt = f"{iv['result']} (control {cnt(iv['control'])} target violations, treatment {cnt(iv['treatment'])}; treatment {tr.get('treatment', '?')[:60]})"
        if iv['result'] == 'INCONCLUSIVE':
            reason = 'control not 3/3' if cnt(iv['control']) != '3/3' else 'treatment still violated'
            ivtxt += f' [{reason}]'
    else:
        ivtxt = 'not run'
    cand = CAND.get(short, ('none (verdict not POLICY_GAP)', 0, 0, 'NOT_ELIGIBLE'))
    rows.append({
        'diagnostic_id': r['diagnostic_id'], 'run': run_label(r['campaign_id']), 'campaign_id': r['campaign_id'],
        'campaign_created_at': r['campaign_created_at'], 'agent': r['agent'],
        'agent_registration_id': r['agent_registration_id'], 'actor_model': r['actor_model'], 'mechanic_model': r['mechanic_model'],
        'store': r['store'], 'counterexample_id': r['counterexample_id'], 'source_episode_id': r['source_episode_id'],
        'target_invariant': r['target_invariant'], 'source_recipe': r['source_recipe'], 'source_recipe_hash': r['source_recipe_hash'],
        'retained_recipe': r['retained_recipe'], 'retained_recipe_hash': r['retained_recipe_hash'], 'seed': r['source_seed'],
        'mechanic_output_ids': ' '.join(a['mechanic_output_id'] for a in atts),
        'mechanic_first_attempt_kind': first['proposed_kind'], 'mechanic_final_kind_raw': final['proposed_kind'],
        'mechanic_requested_intervention_raw': req, 'requested_change_recomputed': requested_change,
        'format_repair_used': len(atts) > 1, 'first_attempt_errors': clean(val['attempts'][0]['schema_and_option_errors'], ref_era),
        'proposal_accepted_by_validator': accepted, 'rejection_reason': clean(sorted({e for a in val['attempts'] for e in a['schema_and_option_errors']}), ref_era) if not accepted else '',
        'diagnosis_path': outcome, 'recorded_proposed_kind': r['diag_proposed_kind_recorded'],
        'intervention_id': iv['id'] if iv else None, 'intervention': ivtxt,
        'verdict_kind': r['verdict_kind'], 'hypothesis_theme_analyst': THEME[short],
        'candidate_followed': cand[1] > 0, 'candidates_source_validated': cand[1], 'candidates_passed_source_validation': cand[2],
        'furthest_candidate_stage': cand[3], 'candidate_detail': cand[0],
        'final_hypothesis': final['hypothesis'],
    })

with open(OUT + 'diagnoses_table.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
json.dump(rows, open(OUT + 'diagnoses_table.json', 'w'), indent=1)

# ---- rates ----
def fisher(a, b, c, d):
    n1 = a + b; n2 = c + d; k = a + c; N = n1 + n2
    p = lambda x: comb(n1, x) * comb(n2, k - x) / comb(N, k)
    p0 = p(a); lo = max(0, k - n2); hi = min(k, n1)
    return round(sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 * (1 + 1e-9)), 5)

groups = collections.OrderedDict([('reference', lambda x: x['agent'].startswith('reference')),
                                  ('native v1', lambda x: x['agent'].startswith('native v1')),
                                  ('native v2', lambda x: x['agent'].startswith('native v2')),
                                  ('all native', lambda x: x['agent'].startswith('native')),
                                  ('all', lambda x: True),
                                  ('mechanic V3.1 (reference only)', lambda x: x['mechanic_model'].endswith('V3.1')),
                                  ('mechanic V4-Pro (all)', lambda x: x['mechanic_model'].endswith('V4-Pro-0813')),
                                  ('mechanic V4-Pro, reference', lambda x: x['mechanic_model'].endswith('V4-Pro-0813') and x['agent'].startswith('reference')),
                                  ('mechanic V4-Pro, native', lambda x: x['mechanic_model'].endswith('V4-Pro-0813') and x['agent'].startswith('native'))])
rates = {}
for name, f in groups.items():
    g = [x for x in rows if f(x)]; n = len(g)
    ran = [x for x in g if x['intervention_id']]
    pg = [x for x in g if x['verdict_kind'] == 'POLICY_GAP']
    rates[name] = {
        'diagnoses': n,
        'mechanic_final_kind_raw': dict(collections.Counter(x['mechanic_final_kind_raw'] for x in g)),
        'mechanic_first_attempt_kind': dict(collections.Counter(x['mechanic_first_attempt_kind'] for x in g)),
        'CONTRACT_EVIDENCE_GAP_final': f"{sum(x['mechanic_final_kind_raw']=='CONTRACT_EVIDENCE_GAP' for x in g)}/{n}",
        'requested_intervention_final_raw': f"{sum(x['mechanic_requested_intervention_raw']=='yes' for x in g)}/{n}",
        'declined_valid_null': f"{sum(x['diagnosis_path'].startswith('DECLINED') for x in g)}/{n}",
        'output_rejected_after_repair': f"{sum(x['diagnosis_path'].startswith('OUTPUT_REJECTED') for x in g)}/{n}",
        'overlong_first_attempt': f"{sum('string_too_long' in (x['first_attempt_errors'] or '') for x in g)}/{n}",
        'intervention_ran': f"{len(ran)}/{n}",
        'intervention_supported_when_ran': f"{sum('SUPPORTED' in x['intervention'] for x in ran)}/{len(ran)}",
        'verdict_POLICY_GAP': f"{len(pg)}/{n}",
        'candidate_followed_given_POLICY_GAP': f"{sum(x['candidate_followed'] for x in pg)}/{len(pg)}",
        'candidates_passed_source_validation': f"{sum(x['candidates_passed_source_validation'] for x in g)}/{sum(x['candidates_source_validated'] for x in g)}",
        'hypothesis_theme_analyst': dict(collections.Counter(x['hypothesis_theme_analyst'] for x in g)),
    }
rates['post_hoc_fisher_two_sided_descriptive_only'] = {
    'CEG final: V4-Pro Mechanic 15/16 vs V3.1 Mechanic 3/14': fisher(15, 1, 3, 11),
    'CEG final within V4-Pro: reference 5/5 vs native 10/11': fisher(5, 0, 10, 1),
    'declined: native 3/11 vs reference 0/19': fisher(3, 8, 0, 19),
    'declined within V4-Pro: native 3/11 vs reference 0/5': fisher(3, 8, 0, 5),
    'citation-blame theme: native v2 5/6 vs all others 1/24': fisher(5, 1, 1, 23),
    'POLICY_GAP verdict: CEG-proposed 8/18 vs POLICY_GAP-proposed 3/10': fisher(8, 10, 3, 7),
}
rates['same_source_repeats'] = {
    'exact source recipe f0f2cb22b9f3435e... (native v2 dev-5 replay, retained 193add68db726edf...)': 'v2d POLICY_GAP (57fa14bc) -> v2e INCONCLUSIVE (b0eeb89d, declined) -> v2f POLICY_GAP (dddc1a1b) -> v2g INCONCLUSIVE (a0dd0c48, output rejected: 614-char hypothesis)',
    'exact source recipe 27db91e968133... (reference, F2 delay 5, seed 42)': '93da89fe INCONCLUSIVE (output rejected) -> 7fe4d06b INCONCLUSIVE (treatment 1/3) -> 5d606f16 INCONCLUSIVE (reduced to delay 3; control 0/3); never POLICY_GAP',
    'exact source recipe beebb28ad1003cd2... (reference, F2 delay 8 -> 5, seed 20250716)': 'a3397fd8 POLICY_GAP (2026-09-13) -> 6cb0e8ab POLICY_GAP (2026-09-20)',
    'same fault shape, different seeds (reference, retained F2 SUCCEEDED delay 5)': '10 diagnoses: 5 POLICY_GAP, 5 INCONCLUSIVE',
    'same fault shape, different seeds (reference, retained delay 4)': '7 diagnoses: 2 POLICY_GAP, 5 INCONCLUSIVE',
    'same fault shape, different seeds (native v1, retained delay 4)': '3 diagnoses: 1 POLICY_GAP, 2 INCONCLUSIVE',
}
json.dump(rates, open(OUT + 'rates.json', 'w'), indent=1)
for k, v in rates.items(): print(k, json.dumps(v))
