"""Coordinator-only controls. Never included in actor tool descriptors."""
import ipaddress
import secrets
from typing import Literal
from fastapi import APIRouter,Depends,Header,HTTPException,Request
from pydantic import Field
from app.contracts.models import StrictModel,Id,TaskIntent,FaultSpec
from .storage import WorldError,event
from .clock import advance
from .faults import validate_schedule

class CreateWorld(StrictModel):
    episode_id:Id
    intent:TaskIntent
    fault_spec:FaultSpec
    fixture_id:str='standard-v1'
class DiagnosticWorld(StrictModel):
    episode_id:Id
    intent:TaskIntent
    profile_id:Literal['evidence_gap_v1','available_status_v1']
    committed:bool

class Advance(StrictModel):
    ticks:int=Field(ge=1,le=5)
    observer:bool=False


def router(store,control_token):
    api=APIRouter(prefix='/control')
    def authorize(request:Request,x_faultlab_control:str|None=Header(default=None)):
        host=request.client.host if request.client else ''
        try: local=ipaddress.ip_address(host).is_loopback
        except ValueError:local=host=='testclient'
        if not local or not control_token or not x_faultlab_control or not secrets.compare_digest(control_token,x_faultlab_control):raise HTTPException(403,'Control capability required')
    api.dependencies=[Depends(authorize)]
    @api.post('/worlds',status_code=201)
    def create(body:CreateWorld):return store.create(body.episode_id,body.intent,body.fault_spec,body.fixture_id)
    @api.post('/diagnostics/worlds',status_code=201)
    def diagnostic_world(body:DiagnosticWorld):
        from .capabilities import create_diagnostic_world
        return create_diagnostic_world(store,body.episode_id,body.intent,body.profile_id,body.committed)
    @api.get('/worlds/{world_id}/snapshot')
    def snapshot(world_id:str):return store.snapshot(world_id)
    @api.get('/worlds/{world_id}/faults')
    def faults(world_id:str):return store.read(world_id)['fault_executions']
    @api.post('/worlds/{world_id}/faults')
    def install(world_id:str,body:FaultSpec):
        with store.transaction(world_id) as s:
            if s['tick'] or s['stopped']:raise WorldError('WORLD_ALREADY_STARTED')
            validate_schedule(body,s['history']);s['fault_spec']=body.model_dump(mode='json')
            s['fault_executions']=[{'fault_id':f'fault-{n+1}','scheduled':True,'triggered':False,'trigger_tick':None,'call_id':None,'attempt_id':None,'reason':'target_not_reached'} for n,_ in enumerate(body.primitives)]
        return {'installed':True}
    @api.post('/worlds/{world_id}/advance')
    def wait(world_id:str,body:Advance):
        with store.transaction(world_id) as s:
            if not body.observer and (body.ticks>4 or s['waits']>=4):raise WorldError('WAIT_BUDGET',429)
            advance(s,body.ticks,observer=body.observer)
            if not body.observer:s['waits']+=1
            event(s,'observer_advanced' if body.observer else 'wait_advanced',{'ticks':body.ticks})
            tick=s['tick']
        return {'tick':tick}
    @api.post('/worlds/{world_id}/stop')
    def stop(world_id:str):
        with store.transaction(world_id) as s:
            if not s['stopped']:
                s['stopped']=True;s['decision_tick']=s['tick'];event(s,'world_stopped')
            tick=s['tick']
        return {'stopped':True,'tick':tick}
    return api
