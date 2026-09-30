"""What would the challenge reachability rule have done in the two saved live challenges? ($0, read-only, stdlib only)

Run on SCRATCH COPIES of the saved stores (never the originals):
  python3 -B challenge_reach_saved_stores.py /Users/shree/FaultLab_Scratch/<stage>/lab.sqlite3 [more copies ...]

For every challenge in a store it lists each challenge pick (the Explorer's selection records, in order), which
tool/service pairs the candidate arm called in the campaign's source-validation episodes of that candidate, split by
caller (the agent under test, or the candidate policy's own hook steps), and whether the pick would be refused under
two readings of "a tool/service the candidate arm never called":
  agent_calls: only the agent's own tool calls count (the candidate policy's status reads are not agent calls);
  any_call:    every HTTP attempt in the candidate arm counts, the policy's reads included (this is what the simulator's
               fault matching counts: simulator/faults.py matching() counts every attempt at tool:service).
It also records, per pick, whether its fault fired in the challenge pairs that ran and whether a counterexample was found.
"""
import hashlib
import json
import sqlite3
import sys


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def open_copy(path):
    if '/FaultLab_Runs/' in path:
        raise SystemExit('Refusing: pass a scratch copy, not a saved run store')
    db = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True)
    return db


def records(db, kind):
    return [json.loads(row[0]) for row in db.execute('SELECT payload FROM records WHERE kind=? ORDER BY rowid', (kind,))]


def record(db, kind, ident):
    row = db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, ident)).fetchone()
    return json.loads(row[0]) if row else None


def call_targets(db, episode_id, intent):
    operations = {intent.get('upgrade_operation_id'): 'orders', intent.get('notification_operation_id'): 'notifications'}
    out = []
    for call in records(db, 'tool_calls'):
        if call['episode_id'] != episode_id:
            continue
        service = {'get_order': 'orders', 'update_order': 'orders', 'send_confirmation': 'notifications'}.get(call['tool'])
        for index, _ in enumerate(call['attempt_ids']):
            svc = service
            if svc is None:
                observations = call.get('observation_ids', [])
                result = ((record(db, 'observations', observations[index]) or {}).get('result') or {}) if index < len(observations) else {}
                svc = (result.get('data') or {}).get('service') or operations.get(result.get('operation_id')) or 'unknown'
            out.append((call.get('caller', 'actor'), f"{call['tool']}:{svc}"))
    return out


def analyse(path):
    db = open_copy(path)
    report = []
    for challenge in records(db, 'challenges'):
        link = record(db, 'challenge_campaigns', challenge['challenge_id'])
        campaign_id = link['campaign_id']
        candidate = challenge['candidate_hash']
        episodes = [e for e in records(db, 'episodes') if e['campaign_id'] == campaign_id
                    and e['experiment_purpose'] == 'source_validation' and e['policy_hash'] == candidate]
        agent, anyone = set(), set()
        per_episode = []
        for episode in episodes:
            intent = (record(db, 'private_episode_inputs', episode['episode_id']) or {}).get('intent') or {}
            calls = call_targets(db, episode['episode_id'], intent)
            per_episode.append({'episode_id': episode['episode_id'], 'calls': [f'{c}:{t}' for c, t in calls]})
            for caller, target in calls:
                anyone.add(target)
                if caller == 'actor':
                    agent.add(target)
        counter = record(db, 'challenge_counterexamples', next((p['candidate_version'] for p in records(db, 'candidate_qualifications')
                                                                 if p.get('candidate_hash') == candidate and p.get('campaign_id') == campaign_id), '')) or {}
        picks = []
        for ref in challenge['selection_refs']:
            selection = record(db, 'selections', ref) or {}
            spec = (selection.get('output') or {}).get('fault_spec')
            if spec is None:
                picks.append({'selection_ref': ref, 'fault_spec': None})
                continue
            targets = [f"{p['target_tool']}:{p['target_service']}" for p in spec['primitives']]
            fired = []
            for batch in records(db, 'evaluations'):
                if batch['purpose'] != 'challenge' or batch.get('candidate_hash') != candidate:
                    continue
                if batch['trials'] and all(t['scenario_hash'] == content_hash(spec) for t in batch['trials']):
                    fired = [{'episode_id': t['episode_id'], 'arm': t['arm'], 'fault_triggered': t['fault_triggered'],
                              'failed_checks': t['failed_checks']} for t in batch['trials']]
            picks.append({'selection_ref': ref, 'targets': targets, 'kinds': [p['kind'] for p in spec['primitives']],
                          'refused_under_agent_calls': [t for t in targets if t not in agent],
                          'refused_under_any_call': [t for t in targets if t not in anyone],
                          'found_counterexample': counter.get('recipe') == spec,
                          'trials': fired})
        report.append({'store_copy': path, 'campaign_id': campaign_id, 'challenge_id': challenge['challenge_id'],
                       'status': challenge['status'], 'stopping_reason': challenge['stopping_reason'],
                       'candidate_arm_source_validation_episodes': len(episodes),
                       'called_by_agent': sorted(agent), 'called_by_anyone': sorted(anyone),
                       'per_episode_calls': per_episode, 'picks': picks})
    db.close()
    return report


if __name__ == '__main__':
    print(json.dumps([row for path in sys.argv[1:] for row in analyse(path)], indent=1))
