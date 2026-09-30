"""Integrity review ($0, offline, read-only): where does the refused target (F4 on orders get_operation_status) sit
relative to what the candidates actually do?

Reads the saved native-v2b store ONLY through sqlite's mode=ro&immutable=1 URI (no app Store object, no writes), plus the
public development manifest (audit/development.json, which agent_history also reads). Never reads private_* records,
promotion, held-out or final-audit data.

For every completed episode it reports: purpose, policy (starting policy or candidate), arm, the recipe (from the
development manifest or a recorded Explorer selection, matched by content hash), whether every fault fired, failed
checks, and how many get_operation_status calls on orders were made, split by caller (actor = the agent itself,
policy = a candidate guardrail step such as read_current_operation).

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/review-integrity/status_read_exposure.py
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

from app.contracts.models import FaultSpec, canonical_json, content_hash  # noqa: E402
from app.referee.manifests import load_manifest  # noqa: E402

DB = 'file:/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3?mode=ro&immutable=1'
con = sqlite3.connect(DB, uri=True)


def rows(kind):
    for (payload,) in con.execute('select payload from records where kind=?', (kind,)):
        yield json.loads(payload)


recipes = {}
for case in load_manifest('development')['cases']:
    spec = FaultSpec.model_validate_json(canonical_json(case['fault_spec']))
    recipes[content_hash(spec)] = spec.model_dump(mode='json')
for sel in rows('selections'):
    for key in ('selected_output', 'output'):
        spec = (sel.get(key) or {}).get('fault_spec')
        if isinstance(spec, dict):
            try:
                parsed = FaultSpec.model_validate_json(canonical_json(spec))
            except Exception:
                continue
            recipes.setdefault(content_hash(parsed), parsed.model_dump(mode='json'))
    spec = (sel.get('search_decision') or {}).get('refused_fault_spec')
    if isinstance(spec, dict):
        parsed = FaultSpec.model_validate_json(canonical_json(spec))
        recipes.setdefault(content_hash(parsed), parsed.model_dump(mode='json'))

# get_operation_status calls on orders per episode and caller (service from the observation, when recorded)
obs_service = {}
for obs in rows('observations'):
    data = ((obs.get('result') or {}).get('data') or {})
    if obs.get('call_id'):
        obs_service[obs['call_id']] = data.get('service')
status_calls = defaultdict(Counter)
for call in rows('tool_calls'):
    if call.get('tool') == 'get_operation_status':
        service = obs_service.get(call.get('call_id'), 'unknown')
        status_calls[call['episode_id']][(call.get('caller'), service)] += 1

STATUS = ('F4', 'orders', 'get_operation_status')


def short(p):
    params = p.get('parameters') or {}
    extra = ','.join(f'{k}={v}' for k, v in sorted(params.items()) if k in ('failure_count', 'delay_ticks', 'ticks', 'outcome'))
    return f"{p['kind']}:{p['target_service']}.{p['target_tool']}({extra})"


table = []
for ep in rows('episodes'):
    if ep.get('lifecycle') != 'COMPLETED':
        continue
    verdict = ep.get('verdict') or {}
    recipe = recipes.get(ep.get('scenario_hash'))
    prims = (recipe or {}).get('primitives') or []
    has_status = any((p['kind'], p['target_service'], p['target_tool']) == STATUS for p in prims)
    execs = verdict.get('fault_executions') or []
    status_fired = None
    if has_status:
        idx = [i for i, p in enumerate(prims) if (p['kind'], p['target_service'], p['target_tool']) == STATUS]
        status_fired = all(i < len(execs) and execs[i].get('triggered') is True for i in idx)
    calls = status_calls.get(ep['episode_id'], Counter())
    table.append({
        'episode_id': ep['episode_id'], 'campaign_id': ep.get('campaign_id'), 'purpose': ep.get('experiment_purpose'),
        'policy': 'policy-v0' if ep.get('policy_version') == 'policy-v0' else 'candidate', 'arm': ep.get('arm'),
        'recipe': [short(p) for p in prims] if recipe else 'UNKNOWN', 'status_target_scheduled': has_status,
        'status_target_fired': status_fired, 'failed_checks': [c['check_id'] for c in verdict.get('checks', []) if not c.get('passed')],
        'orders_status_calls_actor': calls.get(('actor', 'orders'), 0), 'orders_status_calls_policy': calls.get(('policy', 'orders'), 0),
        'status_calls_unknown_service': sum(v for (caller, svc), v in calls.items() if svc not in ('orders', 'notifications'))})

summary = defaultdict(Counter)
for row in table:
    key = f"{row['purpose']}|{row['policy']}"
    s = summary[key]
    s['episodes'] += 1
    s['any_orders_status_call'] += (row['orders_status_calls_actor'] + row['orders_status_calls_policy']) > 0
    s['actor_orders_status_call'] += row['orders_status_calls_actor'] > 0
    s['policy_orders_status_call'] += row['orders_status_calls_policy'] > 0
    if row['status_target_scheduled']:
        s['status_target_scheduled'] += 1
        s['status_target_fired'] += bool(row['status_target_fired'])
    if any(r.startswith('F2:orders.update_order') for r in (row['recipe'] if isinstance(row['recipe'], list) else [])):
        s['F2_update_order_episodes'] += 1
        s['F2_update_order_with_orders_status_call'] += (row['orders_status_calls_actor'] + row['orders_status_calls_policy']) > 0

out = {'summary_by_purpose_and_policy': {k: dict(v) for k, v in sorted(summary.items())},
       'status_target_episodes': [r for r in table if r['status_target_scheduled']],
       'f2_update_order_policy_v0_discovery': [r for r in table if r['policy'] == 'policy-v0' and r['purpose'] == 'discovery'
                                               and isinstance(r['recipe'], list) and any(x.startswith('F2:orders.update_order') for x in r['recipe'])],
       'unknown_recipes': sum(1 for r in table if r['recipe'] == 'UNKNOWN')}
print(json.dumps(out, indent=1, sort_keys=True))
con.close()
