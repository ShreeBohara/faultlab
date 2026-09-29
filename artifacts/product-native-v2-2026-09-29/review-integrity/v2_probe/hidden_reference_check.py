"""Same written answer, v1 vs v2, under a Mechanic-shaped policy (before_confirmation: read_current_operation +
require_receipt orders). The agent is shown obs-1 and obs-3; it writes ['obs-1','obs-3','obs-2'] (obs-2 = the hook's
read, never shown). Then the lab's own Journal.validate_report_references (every journal observation is 'delivered')
is applied to the report each adapter returned. Offline, scripted transport."""
import sys
from pathlib import Path
exec(compile(Path(__file__).with_name('_common.py').read_text(), '_common.py', 'exec'))
from app.integrations.external_agent_v2 import SmolagentsActorV2
from app.contracts.models import TaskReport

def written(call, m):
    if call == 1: return {'name': 'update_order', 'arguments': {'desired_shipping': 'express'}}
    if call == 2: return {'name': 'send_confirmation', 'arguments': {}}
    return report(['obs-1', 'obs-3', 'obs-2'])

async def run(actor_class):
    deterministic_ids()
    store = LabStore(':memory:'); baseline = PolicyRepository(store).baseline()
    provider = Recorder(written)
    intent, context, client = await native_context(scratch / 'hidden-ref' / actor_class.__name__, store, baseline, provider, 'hidden-ref')
    parsed = RecoveryPolicy.model_validate_json(json.dumps(BLOCK_CONFIRMATION))
    context.policy, context.policy_hash, context.policy_decision = parsed, content_hash(parsed), 'ACCEPTED'
    context.interpreter = PolicyInterpreter(parsed, context.broker)
    try:
        rep = await actor_class(model_id=MODEL)(intent, context)
    finally:
        await client.close()
    try:
        context.broker.journal.validate_report_references(rep); ref = 'PASSES'
    except ValueError as error:
        ref = f'FAILS: {error}'
    dispatch_hooks = [(c.get('tool'), c.get('caller'), c.get('hook')) for c in context.broker.logical_calls]
    return {'report_evidence_ids': rep.evidence_ids, 'journal': [o.evidence_id for o in context.broker.journal.observations],
            'shown_in_last_request': shown_ids(provider.requests[-1]['messages']), 'validate_report_references': ref,
            'logical_calls': dispatch_hooks}

for cls in (SmolagentsActor, SmolagentsActorV2):
    print(cls.__name__, json.dumps(asyncio.run(run(cls)), indent=1))
print('blocked', BLOCKED)
