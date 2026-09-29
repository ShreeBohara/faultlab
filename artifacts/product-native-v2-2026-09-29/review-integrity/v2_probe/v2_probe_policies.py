"""Extra v1-vs-v2 byte comparisons for policy paths: a blocked report (before_final_report), policy observations plus
business close (after_upgrade_response + defer_unresolved), and a blocked confirmation. Same method as v2_probe.py."""
import sys, re
from pathlib import Path
exec(compile(Path(__file__).with_name('_common.py').read_text(), '_common.py', 'exec'))
from app.integrations.external_agent_v2 import SmolagentsActorV2
REAL = re.compile(r'evidence-[0-9a-f]{32}')
BLOCK_REPORT = {'parent_version': 'policy-v0', 'rules': [{'hook': 'before_final_report', 'when': 'always', 'steps': [
    {'op': 'read_notification_operation'}, {'op': 'require_receipt', 'service': 'notifications', 'status': 'SUCCEEDED'}]}]}
DEFER = {'parent_version': 'policy-v0', 'rules': [{'hook': 'after_upgrade_response', 'when': 'always', 'steps': [
    {'op': 'read_current_operation'}, {'op': 'defer_unresolved'}]}]}
def s_block_report(call, m):
    if call == 1: return {'name': 'get_order', 'arguments': {}}
    if call == 2: return report(shown_ids(m))                       # claims SUCCEEDED without receipt -> blocked
    return report(shown_ids(m), outcome='NOT_STARTED', overall='SAFE_UNRESOLVED', nxt='ESCALATE')
def s_defer(call, m):
    if call == 1: return {'name': 'update_order', 'arguments': {'desired_shipping': 'express'}}
    return {'name': 'final_answer', 'arguments': {'answer': {'upgrade_outcome': 'SUCCEEDED', 'notification_outcome': 'NOT_STARTED',
            'overall': 'SAFE_UNRESOLVED', 'evidence_ids': shown_ids(m), 'next_action': {'kind': 'ESCALATE'}}}}
def s_block_conf(call, m):
    if call == 1: return {'name': 'send_confirmation', 'arguments': {}}
    return report(shown_ids(m), outcome='NOT_STARTED', overall='SAFE_UNRESOLVED', nxt='ESCALATE')
CASES = {'blocked_report': dict(script=s_block_report, policy=BLOCK_REPORT),
         'defer_business_close': dict(script=s_defer, policy=DEFER),
         'blocked_confirmation': dict(script=s_block_conf, policy=BLOCK_CONFIRMATION)}
for name, spec in CASES.items():
    v1 = asyncio.run(episode(name, spec, SmolagentsActor)); v2 = asyncio.run(episode(name, spec, SmolagentsActorV2))
    labels = {e: f'obs-{i}' for i, e in enumerate(v2['journal_ids'], 1)}
    res = []
    for a, b in zip(v1['requests'], v2['requests']):
        ta = json.dumps(a['messages'], ensure_ascii=False)
        for e, l in labels.items(): ta = ta.replace(e, l)
        tb = json.dumps(b['messages'], ensure_ascii=False)
        fin = json.loads(b['messages'][-1]['content'])['final_report_required']
        if fin and ta != tb:
            ma, mb = json.loads(ta), b['messages']
            la, lb = json.loads(ma[-1]['content']), json.loads(mb[-1]['content'])
            res.append(('FINAL', ma[:-1] == mb[:-1], sorted(k for k in la if la[k] != lb.get(k)), b['kwargs'].get('response_contract')))
        else:
            res.append((ta == tb, a['kwargs'] == b['kwargs'], bool(REAL.search(tb))))
    print(f"{name}: v1 {len(v1['requests'])} req / v2 {len(v2['requests'])} req; per request (v2==v1 relabelled, kwargs equal, real ID in v2) "
          f"or (FINAL, prefix identical, transport keys differing, response_contract): {res}; journal {len(v2['journal_ids'])}; "
          f"v1 outcome {str(v1['outcome'])[:70]}; v2 outcome {str(v2['outcome'])[:70]}")
print('blocked', BLOCKED)
