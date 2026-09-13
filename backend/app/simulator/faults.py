"""Reviewed F1–F4 schedule validation and honest trigger accounting."""
from app.contracts.models import FaultSpec
from .storage import WorldError,event

def validate_schedule(spec:FaultSpec,history):
    for p in spec.primitives:
        if p.kind=='F3' and len(history)<=p.parameters.versions_back: raise WorldError('STALE_HISTORY_UNAVAILABLE',422)
    return spec

def matching(state,tool,service):
    key=tool+':'+service
    occurrence=state['occurrences'].get(key,0)+1;state['occurrences'][key]=occurrence
    found=[]
    for i,p in enumerate(state['fault_spec']['primitives']):
        if p['target_tool']!=tool or p['target_service']!=service: continue
        count=p['parameters'].get('failure_count',1) if p['kind']=='F4' else 1
        if p['occurrence']<=occurrence<p['occurrence']+count: found.append((i,p))
    return found

def trigger(state,index,call_id,attempt_id):
    record=state['fault_executions'][index]
    if not record['triggered']:
        record.update(triggered=True,trigger_tick=state['tick'],call_id=call_id,attempt_id=attempt_id,reason=None)
    event(state,'fault_triggered',{'fault_id':record['fault_id'],'attempt_id':attempt_id},call_id)

def prevented(state,index,reason):
    if not state['fault_executions'][index]['triggered']:state['fault_executions'][index]['reason']=reason
