"""Read-only enrichment of the 30 live diagnoses (reference + native stores)."""
import sqlite3, json, re, collections
from urllib.parse import quote

MAIN = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/lab.sqlite3'
LIVE_STORES = [MAIN,
               '/Users/shree/FaultLab_Runs/2026-09-29/native-learn/lab.sqlite3',
               '/Users/shree/FaultLab_Runs/2026-09-29/native-learn-v3/lab.sqlite3',
               '/Users/shree/FaultLab_Runs/2026-09-30/native-v2/lab.sqlite3',
               '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3']
Id = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')

rows = json.load(open('/Users/shree/FaultLab_Scratch/inv-c/raw_rows.json'))

def opendb(p): return sqlite3.connect(f'file:{quote(p)}?mode=ro&immutable=1', uri=True)

def get(db, kind, id):
    r = db.execute('select rowid,payload from records where kind=? and id=?', (kind, id)).fetchone()
    return (r[0], json.loads(r[1])) if r else (None, None)

def schema_issues(a):
    if not a['parsed']: return ['unparseable JSON']
    out = []
    h = a['hypothesis'] or ''
    if len(h) > 600: out.append(f'hypothesis {len(h)} chars > 600')
    ev = a['evidence_ids'] or []
    if not (1 <= len(ev) <= 36): out.append(f'{len(ev)} evidence ids (1..36 allowed)')
    bad = [e for e in ev if not isinstance(e, str) or not Id.match(e) or len(e) > 128]
    if bad: out.append(f'{len(bad)} malformed evidence id(s), e.g. {bad[0]!r}')
    return out

def recipe_summary(spec):
    if not spec: return None
    return ';'.join(f"{p['kind']}@{p.get('target_service')}.{p.get('target_tool')}#{p.get('occurrence')}{json.dumps(p.get('parameters') or {}, sort_keys=True, separators=(',', ':'))}" for p in spec.get('primitives', [])) or 'NO_FAULT'

out = []
for did, recs in rows.items():
    rec = next((r for r in recs if r['store'] in LIVE_STORES), None)
    if rec is None: continue
    db = opendb(rec['store'])
    cexid = rec['counterexample_id']
    _, cex = get(db, 'counterexamples', cexid)
    _, crec = get(db, 'counterexample_recipes', cexid)
    _, red = get(db, 'reductions', cexid)
    _, ret = get(db, 'retained_recipes', cexid)
    # intervention trial counts
    ivs = []
    for iv in rec['interventions']:
        _, full = get(db, 'interventions', iv['id'])
        ctrl = []; trt = []
        for c, t in full.get('trial_pairs', []):
            for ep, lst in ((c, ctrl), (t, trt)):
                _, tr = get(db, 'trials', ep)
                if tr is None: lst.append('?'); continue
                valid = tr['lifecycle'] == 'COMPLETED' and tr['outcome'] not in (None, 'LAB_ERROR') and (not tr['fault_scheduled'] or tr['fault_triggered'])
                lst.append('V' if valid and rec['target_invariant'] in tr['failed_checks'] else ('ok' if valid else 'invalid'))
        ivs.append({'id': iv['id'], 'result': full['result'], 'control': ctrl, 'treatment': trt, 'hypothesis': full.get('hypothesis'), 'proposal_ref': full.get('proposal_ref')})
    atts = rec['mechanic_attempts']
    for a in atts: a['schema_issues'] = schema_issues(a)
    final = atts[-1] if atts else None
    accepted = None
    if final:
        # The diagnosis record copies the proposal's kind only when the proposal validated; otherwise 'INCONCLUSIVE'.
        if rec['interventions']:
            accepted = True
        elif final['schema_issues']:
            accepted = False
        else:
            accepted = (final['proposed_kind'] == rec['diag_proposed_kind'])
    # candidates: new-era campaign_proposals; old-era by rowid window of 'policies' after the diagnostic
    cands = rec['candidates']
    old_era = []
    if not cands and rec['diag_kind'] == 'POLICY_GAP':
        drow = rec['diag_rowid']
        nxt = db.execute("select min(rowid) from records where rowid>? and kind in ('counterexamples','campaigns','diagnostics')", (drow,)).fetchone()[0] or 10**12
        for r, k, i, pl in db.execute("select rowid,kind,id,payload from records where rowid>? and rowid<? and kind in ('mechanic_outputs','policies','evaluations','challenges') order by rowid", (drow, nxt)):
            d = json.loads(pl)
            if k == 'mechanic_outputs' and d.get('prompt') == 'mechanic.md':
                try: raw = json.loads(d['raw'])
                except Exception: raw = {}
                old_era.append(('mechanic', d.get('attempt'), 'candidate' if 'candidate' in raw else ('no_change' if 'no_change_reason' in raw else 'other')))
            elif k == 'policies': old_era.append(('policy', d.get('decision')))
            elif k == 'evaluations': old_era.append(('evaluation', d.get('purpose'), d.get('decision')))
            elif k == 'challenges': old_era.append(('challenge', d.get('outcome') or d.get('result') or d.get('decision')))
    # challenges for new-era
    chs = []
    for v in rec['qualifications']:
        pass
    q = db.execute("select payload from records where kind='challenges'").fetchall()
    cand_versions = {c.get('candidate_version') for c in cands if c.get('candidate_version')}
    for (pl,) in q:
        d = json.loads(pl)
        if d.get('source_validation_ref') in {s['batch_id'] for s in rec['source_validation']}:
            chs.append({'challenge_id': d.get('challenge_id'), 'status': d.get('status'), 'failed_checks': d.get('failed_checks'), 'pairs': len(d.get('trial_pairs') or []), 'stopping_reason': d.get('stopping_reason')})
    agent = 'reference (V3.1 Actor)' if rec['plan_agent'] is None else ('native v1 (smolagents)' if rec['plan_agent'] == 'smolagents' else 'native v2 (smolagents-v2)')
    out.append({
        'diagnostic_id': did, 'store': rec['store'].replace('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/', ''),
        'campaign_id': rec['campaign_id'], 'campaign_created_at': rec['campaign_created_at'], 'campaign_state': rec['campaign_state'],
        'agent': agent, 'agent_registration_id': rec['agent_registration_id'], 'actor_model': rec['actor_model'],
        'mechanic_model': final['model_id'] if final else None,
        'counterexample_id': cexid, 'source_episode_id': rec['source_episode_id'], 'target_invariant': rec['target_invariant'],
        'source_recipe_hash': rec['scenario_hash'], 'source_recipe': recipe_summary((crec or {}).get('source_recipe')),
        'reduction_status': (red or {}).get('status'), 'retained_recipe_hash': (red or {}).get('retained_recipe_hash'),
        'retained_recipe': recipe_summary((ret or {}).get('retained_recipe')),
        'source_seed': ((crec or {}).get('source_recipe') or {}).get('seed'), 'retained_seed': ((ret or {}).get('retained_recipe') or {}).get('seed'),
        'fixture_id': (crec or {}).get('fixture_id'),
        'mechanic_attempts': [{k: a[k] for k in ('mechanic_output_id', 'attempt', 'proposed_kind', 'requested_intervention_id', 'schema_issues')} | {'hypothesis': a['hypothesis']} for a in atts],
        'mechanic_final_proposed_kind_raw': final['proposed_kind'] if final else None,
        'mechanic_requested_intervention_raw': bool(final and final['requested_intervention_id']),
        'proposal_accepted_by_validator': accepted,
        'diag_proposed_kind_recorded': rec['diag_proposed_kind'], 'verdict_kind': rec['diag_kind'],
        'intervention_ran': bool(ivs), 'interventions': ivs,
        'candidates_new_era': cands, 'source_validation': rec['source_validation'], 'challenges': chs,
        'old_era_after_diagnosis': old_era,
    })

out.sort(key=lambda r: (r['campaign_created_at'], r['diagnostic_id']))
json.dump(out, open('/Users/shree/FaultLab_Scratch/inv-c/live_enriched.json', 'w'), indent=1)
for r in out:
    print(r['campaign_created_at'][:16], r['campaign_id'][9:17], r['diagnostic_id'][11:19], r['agent'][:10], r['target_invariant'], 'src=', r['source_recipe'], '| red=', r['reduction_status'], r['retained_recipe'])
    print('    mech raw:', r['mechanic_final_proposed_kind_raw'], 'req=', r['mechanic_requested_intervention_raw'], 'accepted=', r['proposal_accepted_by_validator'], [a['schema_issues'] for a in r['mechanic_attempts']], '| rec:', r['diag_proposed_kind_recorded'], '->', r['verdict_kind'])
    for iv in r['interventions']: print('    iv', iv['result'], 'ctrl', iv['control'], 'trt', iv['treatment'])
    if r['candidates_new_era']: print('    cands', [(c['decision'], c.get('classification')) for c in r['candidates_new_era']], 'sv', [s['classification'] for s in r['source_validation']], 'ch', r['challenges'])
    if r['old_era_after_diagnosis']: print('    old-era', r['old_era_after_diagnosis'])
