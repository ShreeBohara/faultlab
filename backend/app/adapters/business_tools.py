"""Four public HTTP tools with exact-byte bounded retries and private controls."""
from __future__ import annotations
import json
from urllib.parse import urlsplit
import httpx
from app.contracts.models import ToolResult, WorldSnapshot, FaultExecution, new_id, canonical_json
from app.lab.budgets import BudgetExhausted


class WorldClient:
    def __init__(self,base_url,control_token,*,client=None):
        parsed=urlsplit(base_url)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.query:
            raise ValueError('Explicit localhost mock service required')
        self.client=client or httpx.AsyncClient(base_url=base_url,timeout=1.0)
        self.control_token=control_token

    async def control(self,method,path,payload=None):
        response=await self.client.request(method,path,json=payload,headers={'X-FaultLab-Control':self.control_token},timeout=3)
        response.raise_for_status()
        return response.json()

    async def create(self,episode_id,intent,fault_spec,fixture_id='standard-v1'):
        return await self.control('POST','/control/worlds',{'episode_id':episode_id,'intent':intent.model_dump(mode='json'),'fault_spec':fault_spec.model_dump(mode='json'),'fixture_id':fixture_id})

    async def advance(self,world_id,ticks,observer=False):
        return await self.control('POST',f'/control/worlds/{world_id}/advance',{'ticks':ticks,'observer':observer})

    async def stop(self,world_id):
        return await self.control('POST',f'/control/worlds/{world_id}/stop',{})

    async def snapshot(self,world_id):
        raw=await self.control('GET',f'/control/worlds/{world_id}/snapshot')
        return WorldSnapshot.model_validate_json(canonical_json(raw))

    async def faults(self,world_id):
        raw=await self.control('GET',f'/control/worlds/{world_id}/faults')
        if isinstance(raw,dict): raw=raw.get('fault_executions',raw.get('faults',[]))
        return [FaultExecution.model_validate_json(canonical_json(r)) for r in raw]

    async def close(self): await self.client.aclose()


class BusinessToolBroker:
    def __init__(self,world_client,world_id,capability,journal,meter,*,trace=None,metadata=None):
        self.world_client=world_client; self.world_id=world_id; self.capability=capability
        self.journal=journal; self.meter=meter; self.trace=trace; self.metadata=metadata
        self.logical_calls=[]

    def _request(self,tool,args):
        i=self.journal.intent
        if tool=='get_order': return 'GET',f'/business/orders/{i.order_id}',None,None
        if tool=='get_operation_status':
            service=args['service']; operation=i.upgrade_operation_id if service=='orders' else i.notification_operation_id
            return 'GET',f'/business/operations/{service}/{operation}',None,service
        if tool=='update_order':
            if args!={'desired_shipping':'express'}: raise ValueError('Invalid update arguments')
            return 'POST',f'/business/orders/{i.order_id}/upgrade',{'order_id':i.order_id,'desired_shipping':'express','expected_version':i.expected_version,'operation_id':i.upgrade_operation_id,'idempotency_key':i.upgrade_idempotency_key,'intent_hash':i.upgrade_intent_hash},'orders'
        if tool=='send_confirmation':
            return 'POST','/business/notifications',{'order_id':i.order_id,'upgrade_operation_id':i.upgrade_operation_id,'operation_id':i.notification_operation_id,'idempotency_key':i.notification_idempotency_key,'intent_hash':i.notification_intent_hash,'template_version':i.template_version},'notifications'
        raise ValueError('Unknown business tool')

    async def call(self,tool,arguments=None,*,caller='actor',hook=None,original_bytes=None):
        # Each attempt gets its own delivered-observation child span.
        return await self._call(tool,arguments,caller=caller,hook=hook,original_bytes=original_bytes)

    async def _call(self,tool,arguments=None,*,caller='actor',hook=None,original_bytes=None):
        args=arguments or {}; method,path,payload,service=self._request(tool,args)
        if tool in ('get_order','send_confirmation') and args: raise ValueError('Unexpected tool arguments')
        encoded=None
        if payload:
            record=self.journal.prepare(service,payload)
            encoded=record.original_request
            if original_bytes is not None and original_bytes!=encoded: raise ValueError('Original request mismatch')
        call_id=new_id('call'); attempts=[]; observation_ids=[]
        for retry in range(2):
            self.meter.http_attempt()
            attempt_id=new_id('attempt'); attempts.append(attempt_id)
            if payload: self.journal.attempt(service,attempt_id)
            self.journal.store.append_event(self.journal.episode_id,tick=self.meter.usage.ticks,role='policy' if caller=='policy' else 'actor',type='tool_dispatched',payload={'tool':tool,'attempt_id':attempt_id,'caller':caller,'hook':hook},call_id=call_id)
            headers={'X-FaultLab-World':self.world_id,'X-FaultLab-Capability':self.capability,'X-FaultLab-Call':call_id,'X-FaultLab-Attempt':attempt_id}
            if encoded: headers['Content-Type']='application/json'
            retryable=False
            try:
                response=await self.world_client.client.request(method,path,content=encoded,headers=headers,timeout=1.0)
                try:
                    result=ToolResult.model_validate_json(response.content)
                    if result.call_id!=call_id or result.tool!=tool: raise ValueError('Tool result correlation mismatch')
                    validate_result_binding(result,tool,args,self.journal.intent,self.meter.usage.ticks)
                except Exception:
                    from app.telemetry.safety import public_json
                    from hashlib import sha256
                    rejected={'response_hash':sha256(response.content).hexdigest(),'reason':'SCHEMA_OR_BINDING_MISMATCH'}
                    try: rejected['sanitized_response']=public_json(response.json(),secrets=(self.world_client.control_token,self.capability))
                    except Exception: pass
                    self.journal.store.put_record('rejected_tool_responses',attempt_id,rejected,immutable=True)
                    result=ToolResult(call_id=call_id,tool=tool,transport='error',error_code='INVALID_SERVICE_RESPONSE')
                retryable=result.error_code!='INVALID_SERVICE_RESPONSE' and (response.status_code in (429,502,503,504) or result.error_code in ('TRANSIENT_ERROR','TEMPORARY_UNAVAILABLE','SERVICE_UNAVAILABLE','TRANSIENT_UNAVAILABLE'))
            except (httpx.TimeoutException,httpx.TransportError) as error:
                result=ToolResult(call_id=call_id,tool=tool,transport='timeout' if isinstance(error,httpx.TimeoutException) else 'error',operation_id=payload['operation_id'] if payload else None,order_id=self.journal.intent.order_id,error_code='HTTP_TIMEOUT' if isinstance(error,httpx.TimeoutException) else 'TRANSPORT_ERROR')
                retryable=True
            observation=self.journal.deliver(result,self.meter.usage.ticks)
            observation_ids.append(observation.evidence_id)
            if self.trace is not None:
                try:
                    async with self.trace.span(tool,self.metadata,{'tool':tool,'caller':caller,'call_id':call_id,'attempt_id':attempt_id}) as span:
                        span.set_output({'observation':observation.model_dump(mode='json')})
                except Exception:
                    pass
            if not retryable or retry==1: break
        record={'call_id':call_id,'episode_id':self.journal.episode_id,'tool':tool,'caller':caller,'hook':hook,'attempt_ids':attempts,'observation_ids':observation_ids,'usage':self.meter.usage.model_dump(mode='json')}
        self.logical_calls.append(record)
        self.journal.store.put_record('tool_calls',call_id,record,immutable=True)
        return observation

    async def retry_original(self,service,*,hook=None):
        record=self.journal.original(service)
        if record is None or not record.attempt_ids: raise ValueError('Cannot retry an unattempted operation')
        return await self.call('update_order' if service=='orders' else 'send_confirmation',{'desired_shipping':'express'} if service=='orders' else {},caller='policy',hook=hook,original_bytes=record.original_request)

    async def wait_ticks(self,ticks):
        self.meter.wait(ticks)
        result=await self.world_client.advance(self.world_id,ticks)
        self.journal.store.append_event(self.journal.episode_id,tick=self.meter.usage.ticks,role='policy',type='wait_completed',payload={'ticks':ticks})
        return result


def validate_result_binding(result,tool,args,intent,tick):
    """Schema-valid public data still must match original authority and itself."""
    from app.contracts.models import OperationData,Order
    if result.order_id is not None and result.order_id!=intent.order_id: raise ValueError('Foreign order response')
    service=args.get('service') if tool=='get_operation_status' else 'notifications' if tool=='send_confirmation' else 'orders'
    operation=intent.notification_operation_id if service=='notifications' else intent.upgrade_operation_id
    intent_hash=intent.notification_intent_hash if service=='notifications' else intent.upgrade_intent_hash
    if tool!='get_order' and result.operation_id is not None and result.operation_id!=operation: raise ValueError('Foreign operation response')
    if result.transport!='ok' and (result.data is not None or result.receipt_id is not None or result.status in ('SUCCEEDED','FAILED')): raise ValueError('Failed transport cannot deliver terminal evidence')
    data=result.data
    if result.transport=='ok' and ((tool=='get_order' and not isinstance(data,Order)) or (tool!='get_order' and not isinstance(data,OperationData))): raise ValueError('Successful response requires the typed public data body')
    if isinstance(data,Order):
        if tool!='get_order' or data.order_id!=intent.order_id: raise ValueError('Order projection binding mismatch')
        if result.observed_version!=data.version: raise ValueError('Projection version mismatch')
    elif isinstance(data,OperationData):
        if tool=='get_order' or (data.service,data.operation_id,data.order_id,data.intent_hash)!=(service,operation,intent.order_id,intent_hash): raise ValueError('Operation data binding mismatch')
        if result.status!=data.status or result.operation_id!=data.operation_id: raise ValueError('Operation status mismatch')
        receipt=data.receipt
        if data.status in ('SUCCEEDED','FAILED') and receipt is None: raise ValueError('Terminal state requires a delivered receipt')
        if data.status in ('PENDING','UNKNOWN') and receipt is not None: raise ValueError('Nonterminal state cannot include terminal receipt')
        if receipt:
            if (receipt.service,receipt.operation_id,receipt.order_id,receipt.intent_hash)!=(service,operation,intent.order_id,intent_hash) or receipt.status!=data.status or result.receipt_id!=receipt.receipt_id or receipt.terminal_tick>tick: raise ValueError('Terminal receipt binding mismatch')
        elif result.receipt_id is not None: raise ValueError('Missing delivered receipt body')
    elif result.receipt_id is not None: raise ValueError('Receipt pointer without delivered receipt')
    return result
