import io, json, sys, zipfile, httpx
B = 'http://127.0.0.1:18431/api'
cid = sys.argv[1]; out = sys.argv[2]
msgs = [json.loads(l) for l in open('ui/lab_messages.jsonl')]
with httpx.Client(timeout=60) as h:
    camp = h.get(B + f'/campaigns/{cid}').json()
    plan = h.get(B + f'/campaigns/{cid}/plan').json()['plan']
    attempts = h.get(B + f'/campaigns/{cid}/search-attempts').json()
    experiments = h.get(B + f'/campaigns/{cid}/experiments').json()
    recording = h.get(B + f'/campaigns/{cid}/recording').json()
    regressions = h.get(B + f'/campaigns/{cid}/regressions').json()
    bundles = []
    for reg in regressions:
        z = zipfile.ZipFile(io.BytesIO(h.get(B + f"/regressions/{reg['regression_id']}/download").content))
        ev = json.loads(z.read('evidence.json'))
        bundles.append({'regression_id': reg['regression_id'], 'artifact_kind': reg['artifact_kind'], 'counterexample_id': reg['counterexample_id'],
                        'stage': ev.get('stage'), 'source_episode_id': ev.get('source_episode_id'),
                        'has_replays_block': 'discovery_history_replays' in ev,
                        'replays_block': {k: ev['discovery_history_replays'][k] for k in ('label', 'status', 'sources_found_by_replay')} if 'discovery_history_replays' in ev else None,
                        'replay_slots_in_bundle': [(s['replay'], s['history_row'], s['development_case_id'], s['episode_id']) for s in ev.get('discovery_history_replays', {}).get('replay_slots', [])],
                        'source_history_replay': [(s['counterexample_id'], (s.get('history_replay') or {}).get('history_row')) for s in ev.get('discovery_history_matches', {}).get('sources', [])],
                        'selection_labels': [(s['provenance'], (s.get('history_replay') or {}).get('label'), (s.get('history_replay') or {}).get('history_row')) for s in ev.get('selections', [])]})
episodes = {e['episode_id']: e for e in recording['episodes']}
explorer = [m for m in msgs if m['campaign_id'] == cid and m['role'] == 'explorer' and m['purpose'] != 'challenge']
challenge = [m for m in msgs if m['campaign_id'] == cid and m['role'] == 'explorer' and m['purpose'] == 'challenge']
mechanic = [m for m in msgs if m['role'] == 'mechanic' and (m['campaign_id'] == cid or m['campaign_id'] is None)]
first = json.loads(explorer[0]['messages'][1]['content']) if explorer else None
rows = sorted(attempts, key=lambda r: r['selection_index'])
def outcome(ep):
    e = episodes.get(ep) or {}
    v = e.get('verdict') or {}
    return (v.get('outcome'), sorted(v.get('failed_checks') or []), e.get('experiment_purpose'))
report = {
  'campaign': {k: camp.get(k) for k in ('campaign_id', 'state', 'terminal_reason', 'usage')},
  'plan_replay_rows': [(r['replay'], r['history_row'], r['development_case_id'], r['violation_share'], r['fault_spec']) for r in plan['discovery']['replay']['rows']],
  'plan_replay_status': plan['discovery']['replay']['status'],
  'search_attempts': [{'slot': r['selection_index'], 'provenance': r['provenance'], 'status': r['search_decision']['status'], 'reason': r['search_decision'].get('reason'),
                       'model_calls': r['usage']['model_calls'], 'raw_len': len(r['raw_response']), 'transport_retries': r.get('transport_retries'),
                       'history_replay': {k: r['history_replay'][k] for k in ('label', 'replay', 'of', 'history_row', 'development_case_id', 'episode_id', 'explorer_request')} if r.get('history_replay') else None,
                       'decision_history_replay': r['search_decision'].get('history_replay'),
                       'matches_history_row': r.get('matches_history_row'),
                       'primitives': [(p['kind'], p['target_tool'], p['parameters']) for p in ((r.get('selected_output') or r.get('output') or {}).get('fault_spec') or {}).get('primitives', [])],
                       'episode_outcome': outcome(r['history_replay']['episode_id']) if r.get('history_replay') else None} for r in rows],
  'explorer_discovery_requests': [{'selection_index': m['selection_index'], 'answer_seed': m['answer']['fault_spec']['seed']} for m in explorer],
  'first_explorer_request': None if first is None else {
      'selection_index': first['selection_index'], 'discovery_protocol': first['discovery_protocol'],
      'agent_history_equals_plan_summary': first['agent_history'] == plan['discovery']['history']['summary'],
      'replay_prompt_key_in_context': 'replay_prompt' in first,
      'prior_selections': [(p.get('selection_index'), p.get('status'), p.get('history_replay')) for p in first['search_ledger']['prior_selections']],
      'tested_schedules': [(t.get('episode_id'), t.get('outcome'), t.get('failed_checks')) for t in first['search_ledger']['tested_schedules']],
      'system_has_v3_section': 'Discovery protocol v3' in explorer[0]['messages'][0]['content'],
      'system_has_v4_section': 'Discovery protocol v4 (history replay)' in explorer[0]['messages'][0]['content']},
  'challenge_requests': len(challenge), 'mechanic_requests_total_in_log': len(mechanic),
  'experiments': [{'counterexample_id': x['counterexample']['counterexample_id'], 'source_episode_id': x['counterexample']['source_episode_id'],
                   'target': x['counterexample']['target_invariant'], 'reproduced': x['counterexample'].get('reproduced'),
                   'reproduction_trials': len(x['counterexample'].get('reproduction_trial_ids') or []),
                   'reduction_status': (x.get('reduction') or {}).get('status'), 'diagnostics': [(d.get('kind'), d.get('diagnostic_id')) for d in x['diagnostics']],
                   'interventions': len(x['interventions']), 'challenges': len(x['challenges']),
                   'history_replay': {k: x['history_replay'][k] for k in ('label', 'replay', 'history_row', 'development_case_id', 'episode_id')} if x.get('history_replay') else x.get('history_replay', 'ABSENT'),
                   'matches_history_row': x.get('matches_history_row', 'ABSENT'),
                   'source_recipe': [(p['kind'], p['parameters']) for p in (x.get('source_recipe') or {}).get('primitives', [])]} for x in experiments['counterexamples']],
  'candidate_qualifications': [(q.get('candidate_version'), q.get('stage'), q.get('decision'), q.get('source_classification')) for q in recording['candidate_qualifications']],
  'campaign_proposals': [(p.get('decision'), p.get('reason')) for p in recording['campaign_proposals']],
  'recording': {'discovery_history_replays': {k: v for k, v in recording.get('discovery_history_replays', {}).items() if k not in ('replay_list', 'rule')},
                'replay_list_rows': [(r['replay'], r['history_row'], r['development_case_id']) for r in recording.get('discovery_history_replays', {}).get('replay_list', [])],
                'sources': recording.get('discovery_history_matches', {}).get('sources'),
                'v3_claim_rule': recording.get('discovery_history_matches', {}).get('claim_rule'),
                'selection_labels': [(s['provenance'], (s.get('history_replay') or {}).get('label'), (s.get('history_replay') or {}).get('history_row'), s['usage']['model_calls']) for s in recording['selections']]},
  'regression_bundles': bundles,
  'execution_errors': recording['execution_errors'],
}
json.dump(report, open(out, 'w'), indent=2, default=str)
print(json.dumps(report, indent=2, default=str)[:30000])
