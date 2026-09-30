"""Reviewer: what a v4 plan would freeze from a SCRATCH COPY of the native-v2b store (opened mode=ro&immutable=1), with the
product's own history reader and replay rule from the scratch 'current' tree. Also: plan_block twice (determinism), the
v3 summary equals the input of the v4 list, and each replay recipe equals the public development case recipe."""
import json, sqlite3, sys
from pathlib import Path
from threading import RLock
BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests')]
import conftest  # noqa: F401  (.env refusal hook, dotenv disabled)
from app.lab import agent_history, history_replay
from app.lab.storage import LabStore
from app.referee.manifests import development_case

def immutable_store(path):
    store = LabStore.__new__(LabStore)
    store.path, store.lock, store._closed, store._close_callbacks, store.read_only = str(path), RLock(), False, [], True
    store.db = sqlite3.connect(Path(path).as_uri() + '?mode=ro&immutable=1', uri=True, check_same_thread=False, isolation_level=None)
    store.db.row_factory = sqlite3.Row
    store.db.execute('PRAGMA query_only=ON')
    return store

store = immutable_store(sys.argv[1])
policy = store.get_record('policies', 'policy-v0')
out = []
for registration in store.list_records('agent_registrations'):
    configuration = store.get_record('configurations', registration.get('configuration_hash'))
    identity = agent_history.target_identity(registration, configuration)
    if identity is None:
        out.append({'registration': registration.get('registration_id'), 'identity': None}); continue
    block = agent_history.snapshot(store, registration=registration, configuration=configuration, policy_hash=policy['policy_hash'])
    a = history_replay.plan_block(block); b = history_replay.plan_block(json.loads(json.dumps(block)))
    rows = block['summary']['recipes']
    out.append({'registration': registration['registration_id'], 'entrypoint': registration['adapter_entrypoint_id'],
                'prompt_hash': registration.get('prompt_hash', '')[:8], 'history_status': block['summary']['status'],
                'verified': block['summary']['verified_episodes'], 'composition': block['summary']['composition'],
                'summary_hash': block['summary_hash'][:16], 'deterministic': a == b,
                'rows': [(i, r['development_case_id'], r['verified_episodes'], r['outcomes'].get('VIOLATION', 0), r['every_fault_fired'], history_replay.eligible(r)) for i, r in enumerate(rows, 1)],
                'replay': [(r['replay'], r['history_row'], r['development_case_id'], r['violation_share'], r['failed_checks'], r['sources'],
                            r['fault_spec'] == development_case(r['development_case_id'])['fault_spec'] if r['development_case_id'] else None) for r in a['rows']],
                'replay_status': a['status']})
store.db.close()
print(json.dumps(out, indent=1))
