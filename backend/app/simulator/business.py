"""Four real HTTP business routes with transaction-before-response semantics."""
import asyncio
from typing import Literal
from fastapi import APIRouter,Header,Request
from fastapi.responses import JSONResponse
from pydantic import Field
from app.contracts.models import StrictModel,Id,Digest,ToolResult,OperationData,Receipt,NotificationEffect,content_hash,new_id
from .storage import WorldError,event
from .clock import advance,complete_upgrade
from .faults import matching,trigger,prevented

class UpgradeRequest(StrictModel):
    order_id:Id
    desired_shipping:Literal['express']
    expected_version:int=Field(ge=1)
    operation_id:Id
    idempotency_key:Id
    intent_hash:Digest
class NotificationRequest(StrictModel):
    order_id:Id
    upgrade_operation_id:Id
    operation_id:Id
    idempotency_key:Id
    intent_hash:Digest
    template_version:Literal['confirmation/v1']


def operation_result(call_id,tool,op,intent):
    data=OperationData(operation_id=op['operation_id'],service=op['service'],order_id=op['order_id'],intent_hash=op['intent_hash'],status=op['state'],receipt=Receipt.model_validate(op['receipt']) if op['receipt'] else None)
    return ToolResult(call_id=call_id,tool=tool,transport='ok',operation_id=op['operation_id'],order_id=op['order_id'],status=op['state'],observed_version=op['receipt'].get('committed_version') if op['receipt'] else None,receipt_id=op['receipt']['receipt_id'] if op['receipt'] else None,retry_after_ticks=1 if op['state']=='PENDING' else None,data=data)


def perform(s,tool,service,order_id,operation_id,payload,call_id,faults):
    intent=s['intent']; oid=intent['upgrade_operation_id' if service=='orders' else 'notification_operation_id']
    expected_hash=intent['upgrade_intent_hash' if service=='orders' else 'notification_intent_hash']
    if order_id is not None and order_id!=intent['order_id'] or operation_id is not None and operation_id!=oid:raise WorldError('IDENTITY_CONFLICT')
    if tool=='get_order':
        projection=s['order']
        for i,p in faults:
            if p['kind']=='F3':
                projection=s['history'][-1-p['parameters']['versions_back']]
                trigger(s,i,call_id,s['_attempt_id'])
        return 200,ToolResult(call_id=call_id,tool=tool,transport='ok',order_id=order_id,observed_version=projection['version'],data=projection),False
    if tool=='get_operation_status':
        op=s['operations'].get(oid)
        if op:return 200,operation_result(call_id,tool,op,intent),False
        return 200,ToolResult(call_id=call_id,tool=tool,transport='ok',operation_id=oid,order_id=intent['order_id'],status='UNKNOWN',data=OperationData(operation_id=oid,service=service,order_id=intent['order_id'],intent_hash=expected_hash,status='UNKNOWN')),False
    body=payload.model_dump(mode='json');payload_hash=content_hash(body)
    key=service+':'+body['idempotency_key'];existing=s['idempotency'].get(key)
    # Identity-safe same-byte replay must precede the expected version precondition.
    if existing:
        if existing['payload_hash']!=payload_hash:raise WorldError('IDEMPOTENCY_CONFLICT')
        op=s['operations'][existing['operation_id']]
        return 200,operation_result(call_id,tool,op,intent),op['state']=='SUCCEEDED'
    if body['operation_id']!=oid or body['order_id']!=intent['order_id'] or body['intent_hash']!=expected_hash or body['idempotency_key']!=intent['upgrade_idempotency_key' if service=='orders' else 'notification_idempotency_key']:raise WorldError('IDENTITY_CONFLICT')
    if oid in s['operations']:raise WorldError('IDENTITY_CONFLICT')
    if tool=='update_order' and body['expected_version']!=s['order']['version']:raise WorldError('VERSION_CONFLICT')
    if tool=='send_confirmation' and (body['upgrade_operation_id']!=intent['upgrade_operation_id'] or body['template_version']!=intent['template_version']):raise WorldError('IDENTITY_CONFLICT')
    op=dict(schema_version='faultlab/v1',operation_id=oid,service=service,task_id=intent['task_id'],order_id=intent['order_id'],payload_hash=payload_hash,state='PENDING',accepted_tick=s['tick'],terminal_tick=None,receipt=None,intent_hash=expected_hash)
    s['operations'][oid]=op;s['idempotency'][key]={'payload_hash':payload_hash,'operation_id':oid}
    event(s,'operation_accepted',{'operation_id':oid,'service':service,'payload_hash':payload_hash},call_id)
    if tool=='update_order':
        op.update(expected_version=body['expected_version'],desired_shipping=body['desired_shipping'],failure_code=None)
        s['order']['requested_shipping']='express'
        f2=next(((i,p) for i,p in faults if p['kind']=='F2'),None)
        if f2:
            i,p=f2;op.update(due_tick=s['tick']+p['parameters']['completion_delay_ticks'],failure_code=p['parameters']['failure_code'])
            trigger(s,i,call_id,s['_attempt_id'])
            return 202,operation_result(call_id,tool,op,intent),False
        complete_upgrade(s,op)
        return 200,operation_result(call_id,tool,op,intent),True
    effect=NotificationEffect(notification_id=new_id('notification'),order_id=intent['order_id'],upgrade_operation_id=intent['upgrade_operation_id'],operation_id=oid,idempotency_key=body['idempotency_key'],payload_hash=payload_hash,created_tick=s['tick'])
    s['notifications'].append(effect.model_dump(mode='json'))
    op.update(state='SUCCEEDED',terminal_tick=s['tick'],receipt=Receipt(receipt_id=new_id('receipt'),operation_id=oid,service=service,order_id=intent['order_id'],intent_hash=expected_hash,status='SUCCEEDED',terminal_tick=s['tick'],effect_id=effect.notification_id).model_dump(mode='json'))
    event(s,'notification_committed',{'operation_id':oid,'upgrade_operation_id':intent['upgrade_operation_id'],'order_id':intent['order_id'],'effect_id':effect.notification_id},call_id)
    return 201,operation_result(call_id,tool,op,intent),True


def router(store):
    api=APIRouter(prefix='/business')
    async def dispatch(request,tool,service,order_id=None,operation_id=None,payload=None):
        world=request.headers.get('X-FaultLab-World','');cap=request.headers.get('X-FaultLab-Capability','')
        store.authorize(world,cap)
        call=request.headers.get('X-FaultLab-Call','');attempt=request.headers.get('X-FaultLab-Attempt','')
        # Validate transport identities independently of actor arguments.
        from pydantic import TypeAdapter
        try:TypeAdapter(Id).validate_python(call);TypeAdapter(Id).validate_python(attempt)
        except ValueError:raise WorldError('INVALID_TRANSPORT_ID',422)
        delay=0
        with store.transaction(world) as s:
            if s['stopped']:raise WorldError('WORLD_STOPPED')
            if s['attempts']>=18 or s['tick']>=20:raise WorldError('BUSINESS_BUDGET',429)
            advance(s,1);s['attempts']+=1;s['_attempt_id']=attempt
            event(s,'http_attempt',{'attempt_id':attempt,'tool':tool,'service':service},call)
            faults=matching(s,tool,service)
            f4=next(((i,p) for i,p in faults if p['kind']=='F4'),None)
            try:
                diagnostic=s.get('diagnostic')
                if diagnostic and not diagnostic['incident_done'] and tool=='update_order':
                    diagnostic['incident_done']=True
                    if diagnostic['committed_witness']:perform(s,tool,service,order_id,operation_id,payload,call,[])
                    delay=1.5
                    raise WorldError('DIAGNOSTIC_INCIDENT',503)
                if diagnostic and diagnostic['profile_id']=='evidence_gap_v1':
                    raise WorldError('DIAGNOSTIC_PATH_UNAVAILABLE',503)
                if f4:
                    trigger(s,f4[0],call,attempt)
                    for i,p in faults:
                        if p['kind']=='F1':prevented(s,i,'pre_effect_failure')
                    raise WorldError('TRANSIENT_UNAVAILABLE',503)
                status,result,committed=perform(s,tool,service,order_id,operation_id,payload,call,faults)
                for i,p in faults:
                    if p['kind']=='F1':
                        if committed:trigger(s,i,call,attempt);delay=max(delay,p['parameters']['response_delay_ms']/1000)
                        else:prevented(s,i,'target_not_committed')
            except WorldError as error:
                status=error.status;result=ToolResult(call_id=call,tool=tool,transport='error',operation_id=operation_id,order_id=order_id,error_code=error.code)
                event(s,'request_rejected',{'error_code':error.code,'attempt_id':attempt},call)
            s.pop('_attempt_id',None)
        # Transaction and locks are released before genuine socket timeout/disconnect.
        if delay:await asyncio.sleep(delay)
        return JSONResponse(status_code=status,content=result.model_dump(mode='json'))
    @api.get('/orders/{order_id}')
    async def get_order(order_id:str,request:Request):return await dispatch(request,'get_order','orders',order_id=order_id)
    @api.post('/orders/{order_id}/upgrade')
    async def upgrade(order_id:str,body:UpgradeRequest,request:Request):return await dispatch(request,'update_order','orders',order_id=order_id,operation_id=body.operation_id,payload=body)
    @api.get('/operations/{service}/{operation_id}')
    async def status(service:Literal['orders','notifications'],operation_id:str,request:Request):return await dispatch(request,'get_operation_status',service,operation_id=operation_id)
    @api.post('/notifications')
    async def notify(body:NotificationRequest,request:Request):return await dispatch(request,'send_confirmation','notifications',order_id=body.order_id,operation_id=body.operation_id,payload=body)
    return api
