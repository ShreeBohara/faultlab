"""Follow-up stage ($0): key shapes of a few saved records, to build the synthetic 'later live run' store copy. Read-only copy."""
import json, sys
sys.path.insert(0, 'tests/lab')
from pathlib import Path
from citation_status_saved import copy_read_only, remove_copy
from app.lab.storage import ReadOnlyLabStore
copy = Path('/Users/shree/FaultLab_Scratch/followup-diagnosis-rules/peek/lab.sqlite3'); copy.parent.mkdir(parents=True, exist_ok=True)
copy_read_only('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3', str(copy))
store = ReadOnlyLabStore(copy)
try:
    V2D = 'campaign-ea66672d7a904bd8a011d6922790c963'
    q = next(r for r in store.list_records('candidate_qualifications') if r['campaign_id'] == V2D)
    ch = store.get_record('challenges', q['challenge_ref'])
    evs = [(rid, e) for rid, e in store.records_upto('evaluations', 10**9) if e['purpose'] == 'challenge'
           and (e['candidate_hash'], e['incumbent_hash']) == (ch['candidate_hash'], ch['incumbent_hash'])]
    print('v2d challenge evaluations:', [(rid, e['batch_id'], len(e['trials'])) for rid, e in evs])
    e = evs[0][1]
    print('evaluation keys', sorted(e)); t = e['trials'][0]; print('trial keys', sorted(t)); print('lifecycles', sorted({x['lifecycle'] for x in e['trials']}))
    print('evidence keys', sorted(store.get_record('evidence', t['episode_id'])))
    sel = next(s for rid, s in store.records_upto('selections', 6748) if s.get('provenance') != 'history_replay' and not s['challenge']
               and all(p['target_tool'] == 'get_operation_status' for p in s['output']['fault_spec']['primitives']))
    print('selection keys', sorted(sel), 'output keys', sorted(sel['output']), json.dumps(sel['output']['fault_spec']))
    print('campaign keys', sorted(store.get_record('campaigns', 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530')))
finally:
    store.close(); assert remove_copy(str(copy))
