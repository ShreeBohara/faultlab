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


@pytest.mark.anyio
@pytest.mark.parametrize('operation,call', [
    ('snapshot', lambda c: c.snapshot('world-1')),
    ('faults', lambda c: c.faults('world-1')),
    ('advance', lambda c: c.advance('world-1', 5)),
    ('stop', lambda c: c.stop('world-1')),
])
async def test_a_failed_control_call_names_its_operation(operation, call):
    """Phase 13 lost 11 of 30 attempts to a ReadError that named no operation.

    The wrapper adds the name and nothing else: it stays an httpx.TransportError so
    readiness probing and execution_failure() classify it exactly as before, and it
    retries nothing.
    """
    from app.adapters.business_tools import WorldControlError
    def respond(request): raise httpx.ReadError('socket read failed')
    client = WorldClient('http://127.0.0.1:8001', 'test',
                         client=httpx.AsyncClient(base_url='http://127.0.0.1:8001',
                                                  transport=httpx.MockTransport(respond)))
    with pytest.raises(WorldControlError) as caught:
        await call(client)
    assert caught.value.operation == operation
    assert caught.value.cause_class == 'ReadError'
    assert isinstance(caught.value, httpx.TransportError) and isinstance(caught.value, httpx.HTTPError)
    assert 'socket read failed' not in str(caught.value)
    await client.close()


@pytest.mark.anyio
async def test_a_rejected_control_request_is_not_wrapped():
    """An HTTP status rejection is not transport and keeps its own class."""
    from app.adapters.business_tools import WorldControlError
    def respond(request): return httpx.Response(403, json={'detail': 'denied'})
    client = WorldClient('http://127.0.0.1:8001', 'test',
                         client=httpx.AsyncClient(base_url='http://127.0.0.1:8001',
                                                  transport=httpx.MockTransport(respond)))
    with pytest.raises(httpx.HTTPStatusError) as caught:
        await client.snapshot('world-1')
    assert not isinstance(caught.value, WorldControlError)
    await client.close()


def flaky_world_client(raises, *, status=None):
    """A WorldClient whose transport fails `raises` times before succeeding."""
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if status is not None: return httpx.Response(status, json={'error_code': 'FIXTURE_VERSION_MISMATCH'})
        if len(calls) <= raises: raise httpx.ReadError('socket read failed')
        return httpx.Response(201, json={'world_id': 'world-1', 'capability': 'cap', 'tick': 0})
    client = WorldClient('http://127.0.0.1:8001', 'test',
                         client=httpx.AsyncClient(base_url='http://127.0.0.1:8001',
                                                  transport=httpx.MockTransport(respond)))
    return client, calls


def world_args():
    from app.contracts.models import FaultSpec
    return allocate_intent('order-1', 'Upgrade and confirm'), FaultSpec(seed=1, primitives=[])


@pytest.mark.anyio
@pytest.mark.parametrize('raises', [1, 2])
async def test_a_lost_world_creation_is_retried_and_the_batch_survives(raises):
    """Phase 13 lost 11 of 30 attempts here: create() is the one control call the
    runner makes outside its own error handling, so losing it aborts a whole batch."""
    from app.adapters.business_tools import CREATE_ATTEMPTS
    client, calls = flaky_world_client(raises)
    intent, spec = world_args()
    world = await client.create('episode-test', intent, spec)
    assert world['world_id'] == 'world-1'
    assert len(calls) == raises + 1 <= CREATE_ATTEMPTS
    # The possible orphan is recorded, with the cause class that says how likely it is.
    assert world['create_failures'] == ['ReadError'] * raises
    await client.close()


@pytest.mark.anyio
async def test_world_creation_that_never_succeeds_reports_the_operation():
    """Exhaustion must still abort loudly, and name the call Phase 13 could not."""
    from app.adapters.business_tools import CREATE_ATTEMPTS, WorldControlError
    client, calls = flaky_world_client(99)
    intent, spec = world_args()
    with pytest.raises(WorldControlError) as caught:
        await client.create('episode-test', intent, spec)
    assert len(calls) == CREATE_ATTEMPTS == 3
    assert caught.value.operation == 'create' and caught.value.cause_class == 'ReadError'
    # Classification is unchanged, so readiness and execution_failure still see it.
    assert isinstance(caught.value, httpx.TransportError) and isinstance(caught.value, httpx.HTTPError)
    await client.close()


@pytest.mark.anyio
async def test_a_rejected_world_creation_is_never_retried():
    """A 422 fixture mismatch is a rejection, not a lost response. Retrying it would
    just repeat a request the simulator has already refused on its merits."""
    from app.adapters.business_tools import WorldControlError
    client, calls = flaky_world_client(0, status=422)
    intent, spec = world_args()
    with pytest.raises(httpx.HTTPStatusError) as caught:
        await client.create('episode-test', intent, spec)
    assert len(calls) == 1, 'a rejection must fail on the first attempt'
    assert not isinstance(caught.value, WorldControlError)
    await client.close()


@pytest.mark.anyio
@pytest.mark.parametrize('operation,call', [
    ('advance', lambda c: c.advance('world-1', 5)),
    ('stop', lambda c: c.stop('world-1')),
    ('snapshot', lambda c: c.snapshot('world-1')),
    ('faults', lambda c: c.faults('world-1')),
])
async def test_no_control_call_other_than_create_is_ever_retried(operation, call):
    """The anti-regression test. The retry is safe for create ONLY, because nothing
    resolves a world from an episode_id. A non-observer advance double-applies ticks
    and can flip whether a fault triggered, which would silently change what the gate
    is measuring. This test is what stops the retry being moved into control()."""
    from app.adapters.business_tools import WorldControlError
    client, calls = flaky_world_client(1)
    with pytest.raises(WorldControlError) as caught:
        await call(client)
    assert len(calls) == 1, f'{operation} must not be retried'
    assert caught.value.operation == operation
    await client.close()


def test_create_backoff_is_jittered_so_a_fixed_ladder_cannot_resonate():
    """A fixed ladder retries at fixed offsets, so a cause recurring on a period that
    divides them is met at the same phase every time. Measured against a 0.25s-period
    fault: the unjittered ladder lost 12 exposures of 14, the jittered one lost 1."""
    from app.adapters.business_tools import CREATE_BACKOFF, CREATE_JITTER, create_backoff
    low, high = CREATE_JITTER
    for attempt, base in enumerate(CREATE_BACKOFF):
        draws = {create_backoff(attempt) for _ in range(200)}
        assert len(draws) > 190, 'backoff must not be a constant'
        assert all(base * low <= d <= base * high for d in draws)


def test_create_backoff_index_is_clamped():
    """CREATE_BACKOFF is one shorter than CREATE_ATTEMPTS. Raising the attempt count
    without extending the ladder must reuse the last rung, not raise IndexError."""
    from app.adapters.business_tools import CREATE_BACKOFF, create_backoff
    beyond = len(CREATE_BACKOFF) + 5
    assert create_backoff(beyond) > 0
    assert max(create_backoff(beyond) for _ in range(200)) <= CREATE_BACKOFF[-1] * 1.5


def test_create_jitter_never_touches_seeded_global_randomness():
    """Jitter must not perturb a reproducible run: it draws from its own source."""
    import random
    from app.adapters.business_tools import create_backoff
    random.seed(1234); expected = [random.random() for _ in range(5)]
    random.seed(1234)
    for _ in range(50): create_backoff(0)
    assert [random.random() for _ in range(5)] == expected


def test_client_retires_idle_connections_before_the_simulator_does():
    """The Phase 13 failure mechanism, closed structurally rather than by retrying.

    uvicorn arms its keep-alive timer when it finishes WRITING a response, which is
    strictly before the client finishes reading it and starts its own timer - so the
    server's deadline always falls first. Its handler then closes the transport
    without draining the socket, and on macOS closing a socket holding unread bytes
    emits RST. A request written onto that connection is discarded before the app
    runs, which is why no world file ever existed for the 14 failures.

    Keeping the client's expiry below the server's means the client always closes
    first, so the server never closes a socket with a request in it. Measured against
    a real uvicorn: at 4.9s idle the old client REUSED the connection (the dangerous
    state); the new one dials fresh at every idle age at or above 2.5s.
    """
    from app.adapters.business_tools import KEEPALIVE_EXPIRY, SIMULATOR_KEEPALIVE_SECONDS
    assert KEEPALIVE_EXPIRY < SIMULATOR_KEEPALIVE_SECONDS, (
        'the client must retire an idle connection before the simulator does')
    # A real margin, not a hair's breadth: the race is won by scheduling latency.
    assert SIMULATOR_KEEPALIVE_SECONDS - KEEPALIVE_EXPIRY >= 2.0


def test_the_world_client_applies_that_expiry_to_the_pool_it_builds():
    client = WorldClient('http://127.0.0.1:8001', 'test')
    from app.adapters.business_tools import KEEPALIVE_EXPIRY
    pool = client.client._transport._pool
    assert pool._keepalive_expiry == KEEPALIVE_EXPIRY
