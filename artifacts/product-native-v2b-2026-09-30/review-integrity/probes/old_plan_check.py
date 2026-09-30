"""Integrity reviewer: a Learn plan saved before rule v2 (the live native-v2 run's campaign b05ac280, exported JSON,
not the SQLite store) still validates under the current SavedRunPlan schema to the SAME bytes, keeps rule v1, and the
learning loop would give it no backoff session. Guards: refuses any .env open and any non-loopback socket."""
import os, sys, json, socket
REAL_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../.env'))
def guard(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)) and os.path.abspath(os.fsdecode(args[0])) == REAL_ENV:
        raise PermissionError('reviewer guard: .env must not be read')
    if event == 'socket.connect' and isinstance(args[1], tuple) and not str(args[1][0]).startswith('127.'):
        raise PermissionError('reviewer guard: network')
    if event == 'socket.getaddrinfo' and str(args[0]) not in ('127.0.0.1', 'localhost', '::1'):
        raise PermissionError('reviewer guard: DNS')
sys.addaudithook(guard)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, os.path.join(root, 'backend'))
from app.contracts.models import canonical_json, content_hash
from app.lab.run_plans import SavedRunPlan
from app.agents.transport_retry import (declaration, declaration_v2, TRANSPORT_RETRY_PROTOCOL_V2)
run = os.path.join(root, 'artifacts/product-live-2026-09-30/native-v2-run')
out = {}
for name in ('learn-plan-before.json', 'learn-plan-final.json'):
    plan = json.load(open(os.path.join(run, name)))['plan']
    checked = SavedRunPlan.model_validate_json(canonical_json(plan)).model_dump(mode='json')
    out[name] = {
        'mode_is_learn_plan': 'discovery' in plan,
        'transport_retry_protocol': plan['transport_retry']['protocol'],
        'revalidated_bytes_identical': canonical_json(checked) == canonical_json(plan),
        'plan_hash_recomputes': plan['plan_hash'] == content_hash({k: v for k, v in plan.items() if k != 'plan_hash'}),
        'equals_installed_rule_v1': plan['transport_retry'] == declaration(plan['episode_budget']['actor_calls']),
        'would_get_backoff_session': plan['transport_retry'].get('protocol') == TRANSPORT_RETRY_PROTOCOL_V2,
    }
# A v2 block survives the same round trip byte for byte, and a tampered one is refused by the schema.
plan = json.load(open(os.path.join(run, 'learn-plan-before.json')))['plan']
v2 = {**plan, 'transport_retry': declaration_v2(plan['episode_budget']['actor_calls'])}
out['v2_block_round_trip_identical'] = canonical_json(SavedRunPlan.model_validate_json(canonical_json(v2)).model_dump(mode='json')) == canonical_json(v2)
refused = {}
for change in ({'lab_backoff_seconds': [5, 20, 61]}, {'lab_backoff_seconds': [1, 1, 1]}, {'lab_retries_per_campaign_max': 13},
               {'lab_retries_per_request': 2}, {'retryable': ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_500']},
               {'agent_roles': ['actor', 'explorer']}, {'lab_roles': ['mechanic', 'explorer']}, {'extra': 1},
               {'service_unavailable_delay_seconds': 5}):
    bad = {**plan, 'transport_retry': {**declaration_v2(8), **change}}
    try:
        SavedRunPlan.model_validate_json(canonical_json(bad)); refused[json.dumps(change)] = False
    except Exception:
        refused[json.dumps(change)] = True
out['tampered_v2_blocks_refused_by_schema'] = refused
# Changing only the rule text passes the schema; the exact-equality check in validate_run_plan is what refuses it.
text = {**plan, 'transport_retry': {**declaration_v2(8), 'rule': 'different text'}}
SavedRunPlan.model_validate_json(canonical_json(text))
out['rule_text_change_passes_schema_but_differs_from_installed'] = text['transport_retry'] != declaration_v2(8)
print(json.dumps(out, indent=1))
