from types import SimpleNamespace
import httpx,pytest
from app.adapters.decorator import track_faultlab
from app.adapters.business_tools import WorldClient,BusinessToolBroker
from app.adapters.journal import Journal,allocate_intent
from app.contracts.models import RecoveryPolicy,content_hash
from app.lab.storage import LabStore
from app.lab.budgets import EpisodeMeter

@pytest.mark.anyio
async def test_decorator_preserves_exact_result_and_exception():
    policy=RecoveryPolicy(parent_version='policy-v0',rules=[])
    context=SimpleNamespace(lab_mode=True,adapter_id='orders/v1',policy=policy,policy_hash=content_hash(policy),policy_decision='BASELINE',provenance=SimpleNamespace(origin='prototype'),trace=None)
    expected=object()
    @track_faultlab()
    async def good(task,context): return expected
    assert await good(None,context) is expected
    error=RuntimeError('original')
    @track_faultlab()
    async def bad(task,context): raise error
    with pytest.raises(RuntimeError) as caught: await bad(None,context)
    assert caught.value is error

@pytest.mark.anyio
async def test_durable_intent_and_same_bytes_retry(tmp_path):
    store=LabStore(tmp_path/'lab.db'); store.put_record('episodes','e',{'campaign_id':'c'})
    journal=Journal(store,'e',allocate_intent('order-1','Upgrade and confirm'))
    received=[]
    def respond(request):
        original=journal.original('orders')
        assert original and original.attempt_ids
        received.append(request.content)
        if len(received)==1: raise httpx.ReadTimeout('timeout',request=request)
        return httpx.Response(409,json={'call_id':request.headers['X-FaultLab-Call'],'tool':'update_order','transport':'error','error_code':'VERSION_CONFLICT'})
    client=httpx.AsyncClient(transport=httpx.MockTransport(respond),base_url='http://127.0.0.1:8001')
    broker=BusinessToolBroker(WorldClient('http://127.0.0.1:8001','token',client=client),'w','cap',journal,EpisodeMeter())
    result=await broker.call('update_order',{'desired_shipping':'express'})
    assert len(received)==2 and received[0]==received[1]
    assert len(journal.observations)==2 and broker.meter.usage.http_attempts==2
    assert result.result.error_code=='VERSION_CONFLICT'

@pytest.mark.anyio
async def test_no_retry_schema_or_identity_error(tmp_path):
    store=LabStore(tmp_path/'lab.db'); store.put_record('episodes','e',{'campaign_id':'c'})
    journal=Journal(store,'e',allocate_intent('order-1','Upgrade and confirm'))
    client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(422,json={'wrong':'shape'})),base_url='http://127.0.0.1:8001')
    broker=BusinessToolBroker(WorldClient('http://127.0.0.1:8001','token',client=client),'w','cap',journal,EpisodeMeter())
    await broker.call('update_order',{'desired_shipping':'express'})
    assert broker.meter.usage.http_attempts==1

@pytest.fixture
def anyio_backend(): return "asyncio"

@pytest.mark.anyio
async def test_crossfield_foreign_terminal_receipt_never_delivered_as_success(tmp_path):
    from app.contracts.models import Receipt,OperationData,ToolResult
    store=LabStore(tmp_path/'lab.db'); store.put_record('episodes','e',{'campaign_id':'c'})
    journal=Journal(store,'e',allocate_intent('order-1','Upgrade and confirm')); intent=journal.intent
    def respond(request):
        receipt=Receipt(receipt_id='receipt-1',operation_id=intent.upgrade_operation_id,service='orders',order_id=intent.order_id,intent_hash=intent.upgrade_intent_hash,status='SUCCEEDED',terminal_tick=1,committed_version=2)
        wrong=OperationData(operation_id=intent.upgrade_operation_id,service='orders',order_id='FOREIGN',intent_hash=intent.upgrade_intent_hash,status='SUCCEEDED',receipt=receipt)
        result=ToolResult(call_id=request.headers['X-FaultLab-Call'],tool='update_order',transport='ok',operation_id=intent.upgrade_operation_id,order_id=intent.order_id,status='SUCCEEDED',receipt_id=receipt.receipt_id,data=wrong)
        return httpx.Response(200,content=result.model_dump_json())
    client=httpx.AsyncClient(transport=httpx.MockTransport(respond),base_url='http://127.0.0.1:8001')
    broker=BusinessToolBroker(WorldClient('http://127.0.0.1:8001','token',client=client),'w','cap',journal,EpisodeMeter())
    observation=await broker.call('update_order',{'desired_shipping':'express'})
    assert observation.result.error_code=='INVALID_SERVICE_RESPONSE' and observation.result.data is None
    assert broker.meter.usage.http_attempts==1 and len(store.list_records('rejected_tool_responses'))==1
    from app.lab.policy_state import PolicyState
    assert not PolicyState(journal).condition('upgrade_succeeded')
