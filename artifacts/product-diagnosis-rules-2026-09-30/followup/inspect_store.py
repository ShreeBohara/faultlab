"""Follow-up stage ($0, offline): where is the pre-v2g snapshot of the saved native-v2b store?

Reads a scratch copy (outside the Desktop) made with the tests' own copy_read_only (original opened mode=ro&immutable=1).
Builds no run plan (so audit/promotion.json is never read). Prints JSON.
"""
import json, sys
sys.path.insert(0, "tests/lab")
from pathlib import Path
from citation_status_saved import copy_read_only, remove_copy
from app.lab.storage import ReadOnlyLabStore

SAVED = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
scratch = Path('/Users/shree/FaultLab_Scratch/followup-diagnosis-rules/inspect'); scratch.mkdir(parents=True, exist_ok=True)
copy = scratch / 'lab.sqlite3'
copy_read_only(SAVED, str(copy))
store = ReadOnlyLabStore(copy)
out = {}
try:
    db = store.db
    out['max_record_rowid'] = store.max_record_rowid()
    plans = []
    for rowid, plan in store.records_upto('campaign_plans', 10**12):
        d = plan.get('discovery') or {}
        hist = d.get('history') or {}
        es = plan.get('explorer_selection') or {}
        camp_rowid = store.record_rowid('campaigns', plan['campaign_id'])
        plans.append({'rowid': rowid, 'campaign_rowid': camp_rowid, 'campaign_id': plan['campaign_id'], 'mode': plan.get('mode'),
                      'agent': plan.get('agent'), 'discovery_protocol': d.get('protocol'), 'record_cutoff': hist.get('record_cutoff'),
                      'history_summary_hash': hist.get('summary_hash'), 'history_verified': (hist.get('summary') or {}).get('verified_episodes'),
                      'history_composition': (hist.get('summary') or {}).get('composition'),
                      'explorer_selection': bool(es), 'table_verified': (es.get('table') or {}).get('verified_episodes'),
                      'table_rows': [(r['kind'], r['target_service'], r['target_tool'], r['verified_episodes'], r['fired_episodes'], r['status'])
                                     for r in (es.get('table') or {}).get('rows', [])],
                      'keys': sorted(plan)})
    out['plans'] = plans
    sels = []
    for rowid, s in store.records_upto('selections', 10**12):
        spec = (s.get('output') or {}).get('fault_spec')
        sels.append({'rowid': rowid, 'campaign_id': s.get('campaign_id'), 'challenge': s.get('challenge'), 'provenance': s.get('provenance'),
                     'has_spec': spec is not None})
    out['selections'] = sels
    camps = []
    for rowid, c in store.records_upto('campaigns', 10**12):
        camps.append({'rowid': rowid, 'campaign_id': c['campaign_id'], 'mode': c.get('mode'), 'state': c.get('state') or c.get('status'),
                      'created_at': c.get('created_at')})
    out['campaigns'] = camps
    # rowid ranges of every record kind per campaign-less view: first rowid written by each campaign
    first = {}
    for rowid, fields in store.record_fields_upto('episodes', 10**12, ('campaign_id', 'experiment_purpose', 'split')):
        cid = fields['campaign_id']
        first.setdefault(cid, [rowid, rowid, 0]); first[cid][1] = rowid; first[cid][2] += 1
    out['episode_rowids_by_campaign'] = first
finally:
    store.close()
    assert remove_copy(str(copy))
print(json.dumps(out, indent=1, sort_keys=True))
