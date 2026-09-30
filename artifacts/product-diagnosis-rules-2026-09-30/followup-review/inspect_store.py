#!/usr/bin/env python3
"""Reviewer ($0, offline): copy the saved native-v2b store read-only (mode=ro&immutable=1) to scratch and read the
row numbers the pinned tests rely on. Plain sqlite3 + json only; no product code."""
import json, sqlite3, sys
SRC = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
DST = '/Users/shree/FaultLab_Scratch/followup-review/store/lab.sqlite3'
s = sqlite3.connect(f'file:{SRC}?mode=ro&immutable=1', uri=True); d = sqlite3.connect(DST)
s.backup(d); d.execute('PRAGMA journal_mode=DELETE'); s.close()
d.row_factory = sqlite3.Row
q = lambda sql, *a: d.execute(sql, a).fetchall()
out = {}
out['max_rowid'] = q('SELECT MAX(rowid) m FROM records')[0]['m']
out['count_records'] = q('SELECT COUNT(*) c FROM records')[0]['c']
# rowid gaps: any deleted rows? (count vs max)
plans = []
for r in q("SELECT rowid, id, payload FROM records WHERE kind='campaign_plans' ORDER BY rowid"):
    p = json.loads(r['payload']); h = (p.get('discovery') or {}).get('history') or {}
    plans.append({'rowid': r['rowid'], 'campaign_id': r['id'], 'mode': p.get('mode'), 'agent': p.get('agent'),
                  'discovery_protocol': (p.get('discovery') or {}).get('protocol'),
                  'history_record_cutoff': h.get('record_cutoff'), 'history_summary_hash': h.get('summary_hash'),
                  'verified_episodes': (h.get('summary') or {}).get('verified_episodes'),
                  'keys_of_interest': sorted(k for k in p if k in ('explorer_selection', 'mechanic_evidence', 'mechanic_context', 'mechanic_diagnosis', 'diagnosis_guide'))})
out['campaign_plans'] = plans
for cut in (3022, 6748, 8583):
    out[f'plans_at_or_below_{cut}'] = [p['campaign_id'] for p in plans if p['rowid'] <= cut]
# campaigns rowids
out['campaigns'] = [{'rowid': r['rowid'], 'id': r['id']} for r in q("SELECT rowid,id FROM records WHERE kind='campaigns' ORDER BY rowid")]
# selections counts at cutoffs
for cut in (6748, 8583):
    rows = q("SELECT payload FROM records WHERE kind='selections' AND rowid<=? ORDER BY rowid", cut)
    n_model = 0
    for r in rows:
        p = json.loads(r['payload'])
        if ((p.get('output') or {}).get('fault_spec') is not None) and p.get('provenance') != 'history_replay': n_model += 1
    out[f'selections_upto_{cut}'] = {'all': len(rows), 'model_picks_with_fault_spec': n_model}
# v2d records above 3022? (the rebuild's campaign)
V2D = 'campaign-ea66672d7a904bd8a011d6922790c963'
out['v2d_records_above_3022'] = q("SELECT kind, COUNT(*) c FROM records WHERE rowid>3022 AND json_extract(payload,'$.campaign_id')=? GROUP BY kind", V2D)
out['v2d_records_above_3022'] = [dict(r) for r in out['v2d_records_above_3022']]
out['v2d_max_rowid_with_campaign_id'] = q("SELECT MAX(rowid) m FROM records WHERE json_extract(payload,'$.campaign_id')=?", V2D)[0]['m']
# records whose rowid <= 6748 but immutable=0 (could be edited in place later)
out['mutable_records_upto_6748_by_kind'] = [dict(r) for r in q("SELECT kind, COUNT(*) c FROM records WHERE rowid<=6748 AND immutable=0 GROUP BY kind ORDER BY c DESC")]
# challenge evaluations matching v2d's challenge across the store vs <= 3022
qual = [json.loads(r['payload']) for r in q("SELECT payload FROM records WHERE kind='candidate_qualifications' ORDER BY rowid")]
qual = [x for x in qual if x.get('campaign_id') == V2D]
if qual:
    ch = json.loads(q("SELECT payload FROM records WHERE kind='challenges' AND id=?", qual[0]['challenge_ref'])[0]['payload'])
    key = (ch['candidate_hash'], ch['incumbent_hash'])
    ev = [(r['rowid'], json.loads(r['payload'])) for r in q("SELECT rowid,payload FROM records WHERE kind='evaluations' ORDER BY rowid")]
    m = [(rid, p.get('batch_id') or p.get('evaluation_id')) for rid, p in ev if p.get('purpose') == 'challenge' and (p.get('candidate_hash'), p.get('incumbent_hash')) == key]
    out['v2d_matching_challenge_evaluations_rowids'] = [rid for rid, _ in m]
d.close()
json.dump(out, sys.stdout, indent=1, default=str)
