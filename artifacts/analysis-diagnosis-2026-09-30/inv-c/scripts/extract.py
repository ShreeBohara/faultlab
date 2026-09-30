"""Read-only extraction of every diagnosis record across FaultLab stores.

Opens each store as file:PATH?mode=ro&immutable=1. Writes nothing to any store.
"""
import sqlite3, json, sys, collections
from urllib.parse import quote

STORES = [l.rstrip('\n') for l in open('/Users/shree/FaultLab_Scratch/inv-c/diag_stores.txt') if l.strip()]

def opendb(p):
    return sqlite3.connect(f'file:{quote(p)}?mode=ro&immutable=1', uri=True)

def load(db, kind):
    return {i: (r, json.loads(pl)) for r, i, pl in db.execute('select rowid,id,payload from records where kind=?', (kind,))}

def parse_raw(raw):
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except Exception:
        # try to find a JSON object inside
        s = raw.find('{'); e = raw.rfind('}')
        if s >= 0 and e > s:
            try: return json.loads(raw[s:e+1])
            except Exception: return None
        return None

rows = {}
for p in STORES:
    try:
        db = opendb(p)
    except Exception as e:
        print('ERR', p, e, file=sys.stderr); continue
    diags = load(db, 'diagnostics')
    if not diags: continue
    dcs = load(db, 'diagnostic_campaigns')
    cexs = load(db, 'counterexamples')
    ints = load(db, 'interventions')
    mos = load(db, 'mechanic_outputs')
    camps = load(db, 'campaigns')
    plans = load(db, 'campaign_plans')
    confs = load(db, 'configurations')
    props = load(db, 'campaign_proposals')
    quals = load(db, 'candidate_qualifications')
    svr = load(db, 'source_validation_results')
    chal = load(db, 'challenges')
    chalc = load(db, 'challenge_campaigns')
    regs = load(db, 'agent_registrations')
    diag_mos = sorted([(r, i, d) for i, (r, d) in mos.items() if d.get('prompt') == 'diagnosis.md'])
    diag_order = sorted([(r, i) for i, (r, d) in diags.items()])
    for idx, (drow, did) in enumerate(diag_order):
        d = diags[did][1]
        cid = (dcs.get(did, (None, {}))[1] or {}).get('campaign_id')
        cex = cexs.get(d.get('counterexample_id'), (None, {}))[1]
        camp = camps.get(cid, (None, {}))[1] if cid else {}
        plan = plans.get(cid, (None, {}))[1] if cid else {}
        conf = confs.get(camp.get('configuration_hash'), (None, {}))[1] if camp else {}
        # previous diagnostic in same campaign (or store-wide when outputs lack campaign ids)
        prev_same = max([r for r, i in diag_order if r < drow and ((dcs.get(i, (None, {}))[1] or {}).get('campaign_id') == cid)], default=0)
        prev_any = max([r for r, i in diag_order if r < drow], default=0)
        window = []
        for r, mid, m in diag_mos:
            if r >= drow: continue
            if m.get('campaign_id'):
                if m.get('campaign_id') == cid and r > prev_same: window.append((r, mid, m))
            else:
                if r > prev_any: window.append((r, mid, m))
        # keep the last request group in the window
        if window:
            last = window[-1][2]
            rid = last.get('request_id')
            if rid:
                window = [w for w in window if w[2].get('request_id') == rid]
            else:
                # without request ids: keep attempts after the last attempt==0 output
                starts = [k for k, w in enumerate(window) if w[2].get('attempt') == 0]
                window = window[starts[-1]:] if starts else window
        attempts = []
        for r, mid, m in window:
            pr = parse_raw(m.get('raw', ''))
            attempts.append({'mechanic_output_id': mid, 'rowid': r, 'attempt': m.get('attempt'), 'model_id': m.get('model_id'),
                             'proposed_kind': (pr or {}).get('proposed_kind'), 'requested_intervention_id': (pr or {}).get('requested_intervention_id'),
                             'hypothesis': (pr or {}).get('hypothesis'), 'evidence_ids': (pr or {}).get('evidence_ids'), 'parsed': pr is not None,
                             'raw_len': len(m.get('raw', ''))})
        its = [ints[i][1] for i in d.get('intervention_ids', []) if i in ints]
        cand = [v for k, (r, v) in props.items() if v.get('counterexample_id') == d.get('counterexample_id')]
        qual = [v for k, (r, v) in quals.items() if v.get('counterexample_id') == d.get('counterexample_id')]
        cand_versions = {v.get('candidate_version') for v in qual}
        svs = [v for k, (r, v) in svr.items() if v.get('candidate_version') in cand_versions and v.get('campaign_id') == cid]
        chs = []
        for k, (r, v) in chal.items():
            if v.get('candidate_version') in cand_versions or (isinstance(v.get('candidate'), dict) and v['candidate'].get('version') in cand_versions):
                chs.append(v)
        reg = regs.get(cex.get('agent_registration_id'), (None, {}))[1] if cex else {}
        rec = {
            'store': p, 'diagnostic_id': did, 'diag_rowid': drow, 'campaign_id': cid,
            'campaign_created_at': camp.get('created_at'), 'campaign_state': camp.get('state'), 'campaign_terminal_reason': camp.get('terminal_reason'),
            'plan_agent': plan.get('agent') if plan else None, 'agent_registration_id': (cex or {}).get('agent_registration_id') or (plan or {}).get('agent_registration_id'),
            'registration_kind': reg.get('kind') or reg.get('adapter') or reg.get('agent'),
            'actor_model': (conf.get('models') or {}).get('actor') or conf.get('model') or camp.get('model'),
            'mechanic_model_config': (conf.get('models') or {}).get('mechanic') or conf.get('model'),
            'counterexample_id': d.get('counterexample_id'), 'target_invariant': (cex or {}).get('target_invariant'),
            'scenario_hash': (cex or {}).get('scenario_hash'), 'source_episode_id': (cex or {}).get('source_episode_id'),
            'cex_created_at': (cex or {}).get('created_at'),
            'repro': [(cex or {}).get('attempted_count'), (cex or {}).get('valid_count'), (cex or {}).get('target_violation_count')],
            'diag_proposed_kind': d.get('proposed_kind'), 'diag_kind': d.get('kind'), 'diag_profile': d.get('diagnostic_profile_id'),
            'intervention_ids': d.get('intervention_ids'),
            'interventions': [{'id': x.get('intervention_id'), 'result': x.get('result'), 'proposal_ref': x.get('proposal_ref'), 'pairs': len(x.get('trial_pairs') or []), 'limitations': x.get('limitations'), 'control_hash': x.get('control_hash'), 'treatment_hash': x.get('treatment_hash')} for x in its],
            'mechanic_attempts': attempts,
            'candidates': [{'proposal_ref': v.get('proposal_ref'), 'decision': v.get('decision'), 'reason': v.get('reason'), 'candidate_version': v.get('candidate_version'), 'classification': v.get('classification')} for v in cand],
            'qualifications': [{'candidate_version': v.get('candidate_version'), 'stage': v.get('stage'), 'decision': v.get('decision'), 'source_classification': v.get('source_classification')} for v in qual],
            'source_validation': [{'batch_id': v.get('batch_id'), 'candidate_version': v.get('candidate_version'), 'classification': v.get('classification'), 'decision': v.get('decision')} for v in svs],
            'challenges_n': len(chs),
        }
        rows.setdefault(did, []).append(rec)

json.dump(rows, open('/Users/shree/FaultLab_Scratch/inv-c/raw_rows.json', 'w'), indent=1, default=str)
print(len(rows), 'distinct diagnostic ids')
for did, recs in rows.items():
    print(did, len(recs), sorted({r['store'].replace('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/', '') for r in recs})[:3])
