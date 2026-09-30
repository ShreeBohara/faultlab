"""Summarise one scenario campaign from the API (experiments, recording, plan) and the harness message log."""
import json, sys, httpx
B = 'http://127.0.0.1:18531/api'; S = '/Users/shree/FaultLab_Scratch/review-product/ui'
cid, out = sys.argv[1], sys.argv[2]
msgs = [json.loads(l) for l in open(S + '/lab_messages.jsonl')]
with httpx.Client(timeout=60) as h:
    camp = h.get(B + f'/campaigns/{cid}').json()
    plan = h.get(B + f'/campaigns/{cid}/plan').json()['plan']
    ex = h.get(B + f'/campaigns/{cid}/experiments').json()
    rec = h.get(B + f'/campaigns/{cid}/recording').json()
episodes = {e['episode_id']: e for e in rec['episodes']}
def fired(eid):
    e = episodes.get(eid) or {}
    v = e.get('verdict') or {}
    return {'arm': e.get('arm'), 'purpose': e.get('experiment_purpose'), 'outcome': v.get('outcome'), 'failed': v.get('failed_checks'),
            'fault_triggered': v.get('fault_triggered')}
mine = [m for m in msgs if m['campaign_id'] == cid or (m['role'] == 'mechanic' and m['campaign_id'] is None)]
report = {
  'campaign': {k: camp.get(k) for k in ('campaign_id', 'state', 'terminal_reason')},
  'plan_rules': {'mechanic_context': plan.get('mechanic_context', {}).get('protocol'), 'challenge_selection': plan.get('challenge_selection', {}).get('protocol')},
  'experiments_keys': sorted(ex.keys()),
  'challenge_reach': [{k: r.get(k) for k in ('proposal_index', 'slot_request', 'replan_of', 'status', 'targets', 'unreached', 'reason', 'recipe')} | {'basis': r.get('basis')} for r in ex.get('challenge_reach', [])],
  'mechanic_context': ex.get('mechanic_context'),
  'challenges': [{k: c.get(k) for k in ('challenge_id', 'status', 'stopping_reason', 'failed_checks')} | {'schedules': len(c['schedule_hashes']), 'pairs': len(c['trial_pairs']), 'selection_refs': len(c['selection_refs'])}
                 for x in ex['counterexamples'] for c in x['challenges']],
  'challenge_trials': [[fired(a), fired(b)] for x in ex['counterexamples'] for c in x['challenges'] for a, b in c['trial_pairs']],
  'candidate_qualifications': [(q.get('candidate_version'), q.get('stage'), q.get('decision'), q.get('challenge_status')) for q in rec['candidate_qualifications']],
  'campaign_proposals': [(p.get('decision'), p.get('reason'), p.get('context_compaction_ref')) for p in rec['campaign_proposals']],
  'recording_keys_new': {k: (k in rec) for k in ('mechanic_context_records', 'challenge_selection_rule')},
  'recording_challenge_selection_rule': rec.get('challenge_selection_rule'),
  'recording_mechanic_context_records': [{k: r.get(k) for k in ('outcome', 'stage', 'request_kind', 'full_request_tokens', 'compacted_request_tokens', 'provider_dispatch', 'candidate_index', 'stages_applied', 'reason')} for r in rec.get('mechanic_context_records', [])],
  'recording_selection_challenge_reach': [(s.get('challenge'), (s.get('challenge_reach') or {}).get('status')) for s in rec['selections'] if s.get('challenge')],
  'lab_requests': [{'role': m['role'], 'kind': m['kind'], 'purpose': m['purpose'], 'proposal_index': m['proposal_index'], 'slot_request': m['slot_request'], 'dispatched_tokens': m['dispatched_tokens']} for m in mine],
  'max_mechanic_dispatched_tokens': max([m['dispatched_tokens'] for m in mine if m['role'] == 'mechanic'] or [0]),
  'max_explorer_dispatched_tokens': max([m['dispatched_tokens'] for m in mine if m['role'] == 'explorer'] or [0]),
  'execution_errors': rec['execution_errors'],
}
json.dump(report, open(out, 'w'), indent=1, default=str)
print(json.dumps({k: v for k, v in report.items() if k != 'lab_requests'}, indent=1, default=str)[:12000])
