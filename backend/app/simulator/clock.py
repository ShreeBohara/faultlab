"""Logical time advances only at admitted requests and explicit bounded waits."""
from app.contracts.models import Receipt,new_id
from .storage import WorldError,event

def complete_upgrade(state,op):
    if op['state']!='PENDING': return
    failed=op.get('failure_code')
    if not failed and state['order']['version']!=op['expected_version']: failed='VERSION_CONFLICT'
    status='FAILED' if failed else 'SUCCEEDED'
    version=None
    if not failed:
        state['order']={**state['order'],'applied_shipping':op['desired_shipping'],'requested_shipping':op['desired_shipping'],'version':state['order']['version']+1,'last_upgrade_operation_id':op['operation_id']}
        state['history'].append(dict(state['order']));version=state['order']['version']
    else:
        state['order']['requested_shipping']=state['order']['applied_shipping']
    op['state']=status;op['terminal_tick']=state['tick']
    op['receipt']=Receipt(receipt_id=new_id('receipt'),operation_id=op['operation_id'],service='orders',order_id=op['order_id'],intent_hash=op['intent_hash'],status=status,terminal_tick=state['tick'],committed_version=version,failure_code=failed).model_dump(mode='json')
    event(state,'upgrade_committed' if not failed else 'upgrade_failed',{'operation_id':op['operation_id'],'order_id':op['order_id'],'receipt_id':op['receipt']['receipt_id'],'version':version})

def advance(state,ticks,*,observer=False):
    if observer:
        if not state['stopped'] or state['horizon_done'] or ticks!=5: raise WorldError('INVALID_OBSERVER_ADVANCE')
        if state['tick']+ticks>25: raise WorldError('TICK_BUDGET',429)
    else:
        if state['stopped']: raise WorldError('WORLD_STOPPED')
        if state['tick']+ticks>20: raise WorldError('TICK_BUDGET',429)
    for _ in range(ticks):
        state['tick']+=1
        for op in sorted(state['operations'].values(),key=lambda v:(v.get('due_tick',26),v['accepted_tick'],v['operation_id'])):
            if op['service']=='orders' and op['state']=='PENDING' and op.get('due_tick',26)<=state['tick']: complete_upgrade(state,op)
    if observer: state['horizon_done']=True
