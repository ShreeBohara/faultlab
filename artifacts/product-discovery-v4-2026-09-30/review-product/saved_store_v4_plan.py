"""Product reviewer: what a v4 plan freezes in a COPY of the saved native-v2b store ($0, offline).

Run from faultlab/backend:
    ../.venv/bin/python ../artifacts/product-discovery-v4-2026-09-30/review-product/saved_store_v4_plan.py <copy_dir> <out.json>

<copy_dir>/lab/lab.sqlite3 is a byte copy of /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 (its WAL was
empty), made outside the synced Desktop. The original is never opened by this script. Through the real product API
(in-process ASGI client; no socket): register the configured native adapter v2 (as an operator would after the runtime
change), then create a v4 Learn plan and a v3 Learn plan for comparison, read the saved plans and press the history check.
Nothing is started: no episode, no model request. A socket guard refuses every non-loopback connection or lookup.
"""
import asyncio
import json
import socket
import sys
from pathlib import Path

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'tests' / 'lab')]
import conftest  # noqa: F401,E402

COPY = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2])
assert not str(COPY).startswith('/Users/shree/Desktop') and not str(COPY).startswith('/Users/shree/FaultLab_Runs')
REFUSED = []
_connect = socket.socket.connect
def _guard(sock, address):
    if sock.family == socket.AF_UNIX: return _connect(sock, address)
    REFUSED.append(repr(address)); raise RuntimeError('refused')
def _refuse(*a, **k):
    REFUSED.append(repr(a[:1])); raise OSError('refused')
socket.socket.connect = _guard; socket.getaddrinfo = _refuse; socket.create_connection = _refuse

import httpx  # noqa: E402
from app.lab.coordinator import LabCoordinator  # noqa: E402
from test_native_baseline_study_planned import plan_settings  # noqa: E402

V4, V3 = 'faultlab-discovery/v4-history-replay', 'faultlab-discovery/v3-history'


async def main():
    settings = plan_settings(COPY / 'lab')
    c = LabCoordinator(settings)
    from app.main import create_app
    api = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=c)), base_url='http://127.0.0.1:8000')
    report = {'store_copy': str(COPY / 'lab' / 'lab.sqlite3')}
    try:
        before = [r for r in c.store.list_records('agent_registrations')]
        report['saved_registrations'] = [(r['registration_id'], r['adapter_entrypoint_id'], r['prompt_hash'][:8], r['model']) for r in before]
        options = (await api.get('/api/run-options')).json()
        report['store_identity'] = options['data_store']['identity']
        reg = await api.post('/api/agent-registrations', json={'expected_store_identity': options['data_store']['identity'], 'agent': 'smolagents-v2'})
        report['register_status'] = reg.status_code
        registration = reg.json()
        report['new_registration'] = {k: registration.get(k) for k in ('registration_id', 'adapter_entrypoint_id', 'prompt_hash', 'adapter_hash', 'model')}
        options = (await api.get('/api/run-options')).json()
        plans = {}
        for protocol, order in ((V4, 'order-v4-review'), (V3, 'order-v3-review')):
            r = await api.post('/api/planned-campaigns', json={
                'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
                'task_definition_id': options['task']['task_definition_id'], 'agent_registration_id': registration['registration_id'],
                'mode': 'learn', 'config_profile_id': 'live-v1', 'task_text': options['task']['task_text_default'],
                'order_id': order, 'discovery_protocol': protocol})
            assert r.status_code == 201, r.text
            cid = r.json()['campaign_id']
            plans[protocol] = {'campaign_id': cid, 'plan': (await api.get(f'/api/campaigns/{cid}/plan')).json()['plan'],
                               'check': (await api.get(f'/api/campaigns/{cid}/plan/history-check')).json()}
        v4, v3 = plans[V4]['plan']['discovery'], plans[V3]['plan']['discovery']
        summary = v4['history']['summary']
        report['history'] = {'status': summary['status'], 'verified_episodes': summary['verified_episodes'],
                             'composition': summary['composition'], 'summary_hash': v4['history']['summary_hash'],
                             'record_cutoff': v4['history']['record_cutoff'],
                             'rows': [{'row': i, 'case': r['development_case_id'], 'recipe': r['recipe'], 'verified': r['verified_episodes'],
                                       'outcomes': r['outcomes'], 'every_fault_fired': r['every_fault_fired'], 'failed_checks': r['failed_checks'],
                                       'sources': r['sources']} for i, r in enumerate(summary['recipes'], 1)]}
        report['v4_replay'] = {k: v4['replay'][k] for k in ('status', 'statement', 'history_summary_hash')}
        report['v4_replay_rows'] = [{k: row[k] for k in ('replay', 'history_row', 'development_case_id', 'recipe', 'fault_spec', 'verified_episodes',
                                                         'violations', 'violation_share', 'every_fault_fired', 'outcomes', 'failed_checks', 'sources')}
                                    for row in v4['replay']['rows']]
        report['v4_history_equals_v3_history_except_cutoff'] = ({k: v for k, v in v4['history'].items() if k != 'record_cutoff'}
                                                             == {k: v for k, v in v3['history'].items() if k != 'record_cutoff'})
        report['v4_budget_equals_v3'] = ({k: v for k, v in v4.items() if k not in ('protocol', 'history', 'replay', 'dispatch_rule')}
                                         == {k: v for k, v in v3.items() if k not in ('protocol', 'history', 'dispatch_rule')})
        report['history_check'] = {p: plans[p]['check']['status'] for p in plans}
        report['campaigns'] = {p: plans[p]['campaign_id'] for p in plans}
        report['episodes_after'] = len(c.store.list_records('episodes'))
    finally:
        await api.aclose(); await c.close()
    report['refused_connections'] = REFUSED
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


asyncio.run(main())
