"""Follow-up stage ($0, offline): a scratch copy of the saved native-v2b store plus synthetic records standing in for a
LATER live run, to show that the pinned saved-store tests cannot be changed by records added after their snapshot.

Usage (from faultlab/backend, under run_guarded.py):  grow_store.py TARGET.sqlite3
The original is read once with copy_read_only (mode=ro&immutable=1); every write goes to TARGET (outside the Desktop).
Added records (all get row numbers above the store's current end, 8583):
  * a copy of live run v2g's campaign, plan, plan provenance, campaign registration and active-policy pointer under a
    new campaign id, the plan also declaring Rule 1
    (mechanic_diagnosis), as a plan this build saves would; plan_hash recomputed, so the product reads it as a valid plan;
  * a discovery pick that mixes the orders status read with an update_order fault (a copy of a saved lone status-read
    pick with one more primitive);
  * a challenge evaluation for the same candidate and incumbent as live run v2d's challenge (a copy of one of its three
    batches with new batch and episode ids), with evidence copies for the new episode ids.
"""
import copy as cp, json, sys
sys.path.insert(0, 'tests/lab')
from pathlib import Path
from citation_status_saved import copy_read_only
from app.contracts.models import content_hash
from app.lab import diagnosis_protocol
from app.lab.storage import LabStore

SAVED = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
V2G, V2D = 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530', 'campaign-ea66672d7a904bd8a011d6922790c963'
target = Path(sys.argv[1]); assert 'Desktop' not in str(target) and '/FaultLab_Runs/' not in str(target)
target.parent.mkdir(parents=True, exist_ok=True)
copy_read_only(SAVED, str(target))
store = LabStore(target)
added = []
try:
    end = store.max_record_rowid()
    new_campaign = 'campaign-' + 'f0' * 16
    campaign = {**store.get_record('campaigns', V2G), 'campaign_id': new_campaign}
    store.put_record('campaigns', new_campaign, campaign); added.append(('campaigns', new_campaign))
    plan = {**cp.deepcopy(store.get_record('campaign_plans', V2G)), 'campaign_id': new_campaign,
            'mechanic_diagnosis': diagnosis_protocol.declaration()}
    plan['plan_hash'] = content_hash({k: v for k, v in plan.items() if k != 'plan_hash'})
    store.put_record('campaign_plans', new_campaign, plan); added.append(('campaign_plans', new_campaign))
    provenance = {**store.get_record('campaign_provenance', V2G), 'run_plan_ref': new_campaign, 'run_plan_hash': plan['plan_hash']}
    if 'campaign_id' in provenance:
        provenance['campaign_id'] = new_campaign
    store.put_record('campaign_provenance', new_campaign, provenance); added.append(('campaign_provenance', new_campaign))
    owner = {**store.get_record('campaign_registrations', V2G)}
    if 'campaign_id' in owner:
        owner['campaign_id'] = new_campaign
    store.put_record('campaign_registrations', new_campaign, owner); added.append(('campaign_registrations', new_campaign))
    store.compare_and_set_pointer('active-policy:' + new_campaign, None, store.get_pointer('active-policy:' + V2G))

    lone = next(s for _, s in store.records_upto('selections', 6748) if s.get('provenance') != 'history_replay' and not s['challenge']
                and all(p['target_tool'] == 'get_operation_status' for p in s['output']['fault_spec']['primitives']))
    mixed = cp.deepcopy(lone); mixed_id = 'selection-' + 'f1' * 16
    mixed['selection_id'] = mixed_id
    extra = {'kind': 'F2', 'occurrence': 1, 'parameters': {'completion_delay_ticks': 9, 'terminal_status': 'SUCCEEDED', 'failure_code': None},
             'target_service': 'orders', 'target_tool': 'update_order'}
    for key in ('output', 'selected_output'):
        if isinstance(mixed.get(key), dict) and mixed[key].get('fault_spec'):
            mixed[key]['fault_spec']['primitives'].append(dict(extra))
    store.put_record('selections', mixed_id, mixed); added.append(('selections', mixed_id))

    qualification = next(r for r in store.list_records('candidate_qualifications') if r['campaign_id'] == V2D)
    challenge = store.get_record('challenges', qualification['challenge_ref'])
    batch = next(e for _, e in store.records_upto('evaluations', end) if e['purpose'] == 'challenge'
                 and (e['candidate_hash'], e['incumbent_hash']) == (challenge['candidate_hash'], challenge['incumbent_hash']))
    later = cp.deepcopy(batch); later['batch_id'] = 'batch-' + 'f2' * 16
    for index, trial in enumerate(later['trials']):
        old, new = trial['episode_id'], 'episode-' + f'{index:02d}' + 'f3' * 15
        trial['episode_id'] = new
        evidence = store.get_record('evidence', old)
        if evidence is not None:
            store.put_record('evidence', new, {**evidence, 'episode_id': new}); added.append(('evidence', new))
    store.put_record('evaluations', later['batch_id'], later); added.append(('evaluations', later['batch_id']))
    rows = {f'{kind}/{ident}': store.record_rowid(kind, ident) for kind, ident in added}
    print(json.dumps({'store_end_before': end, 'store_end_after': store.max_record_rowid(), 'added_rows': rows}, indent=1))
    assert min(rows.values()) > end
finally:
    store.close()
