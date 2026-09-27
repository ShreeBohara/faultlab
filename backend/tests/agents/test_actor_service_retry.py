"""One charged blind 503 retry; no answer selection or relaxed execution caps."""
import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.adapters.journal import Journal, allocate_intent
from app.agents.actor import Actor
from app.config import Settings
from app.contracts.models import CampaignBudget, RecoveryPolicy, canonical_json
from app.lab.budgets import CampaignLedger, EpisodeMeter, PROTECTED
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration, RuntimeProvider, RuntimeProviderError


@pytest.fixture
def anyio_backend(): return 'asyncio'


MODEL='openai/gpt-oss-120b'
REPORT={'kind':'report','report':{'upgrade_outcome':'NOT_STARTED','notification_outcome':'NOT_STARTED',
        'overall':'SAFE_UNRESOLVED','evidence_ids':[],'next_action':{'kind':'ESCALATE'}}}
TOOL={'kind':'tool','tool':'get_order','arguments':{}}


def setup(tmp_path, monkeypatch, responses, *, calls=16, tokens=544000, dollars=20.0,reservation_calls=None):
    """Real Actor, RuntimeProvider, meter and ledger; SDK and time are offline boundaries."""
    from app.agents import actor
    store=LabStore(tmp_path/'lab.sqlite3')
    store.put_record('episodes','episode-test',{'campaign_id':'campaign-test'})
    ledger=CampaignLedger(store,'campaign-test',CampaignBudget(model_calls=calls,tokens=tokens,dollars=dollars),
                          dollar_bounds={'actor':.0209})
    for reserve in PROTECTED: ledger.release(reserve)
    if reservation_calls is not None: ledger.reserve('batch',reservation_calls)
    clock=[0.0]; delays=[]; requests=[]; client_options=[]; business=[]
    async def sleep(seconds):
        delays.append(seconds); clock[0]+=seconds
    monkeypatch.setattr(actor.asyncio,'sleep',sleep)
    meter=EpisodeMeter(campaign=ledger,reservation='batch' if reservation_calls is not None else None,clock=lambda:clock[0])
    intent=allocate_intent('order-test','Upgrade and confirm')
    broker=SimpleNamespace(meter=meter,journal=Journal(store,'episode-test',intent))
    async def call(tool,arguments):
        meter.http_attempt(); business.append((tool,arguments))
    broker.call=call
    async def create(**kwargs):
        requests.append(kwargs)
        item=responses[len(requests)-1]
        if isinstance(item,BaseException): raise item
        if type(item) is int:
            response=httpx.Response(item,request=httpx.Request('POST','https://provider.invalid/completions'))
            cls=openai.InternalServerError if item>=500 else openai.APIStatusError
            raise cls('private SDK text',response=response,body={'secret':'private SDK body'})
        if not isinstance(item,dict): return item
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=canonical_json(item)))],
            usage=SimpleNamespace(prompt_tokens=10,completion_tokens=20))
    def factory(**kwargs):
        client_options.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider=RuntimeProvider(Settings(wandb_api_key='fixture-key',wandb_entity='fixture',
        wandb_project='project',wandb_model=MODEL),live_authorized=True,client_factory=factory)
    context=SimpleNamespace(broker=broker,provider=provider,
        interpreter=PolicyInterpreter(RecoveryPolicy(parent_version='policy-v0',rules=[]),broker),
        metadata={'model_id':MODEL,'episode_id':'episode-test','campaign_id':'campaign-test'})
    return SimpleNamespace(intent=intent,context=context,store=store,meter=meter,ledger=ledger,
        requests=requests,client_options=client_options,clock=clock,delays=delays,business=business)


@pytest.mark.anyio
@pytest.mark.parametrize('prior_turns',[0,7])
async def test_sdk_503_retries_identical_request_once_even_on_final_turn_and_charges_it(tmp_path,monkeypatch,prior_turns):
    h=setup(tmp_path,monkeypatch,[TOOL]*prior_turns+[503,REPORT])
    report=await Actor()(h.intent,h.context)
    assert report.model_dump(mode='json')==REPORT['report']
    assert h.requests[-2]==h.requests[-1]  # Same prompt, format, model and output limit.
    assert h.meter.usage.actor_calls==prior_turns+1 and h.meter.usage.model_calls==prior_turns+2
    assert h.ledger.used_calls==prior_turns+2
    assert h.ledger.used_dollar_upper_bound==pytest.approx((prior_turns+2)*.0209)
    assert h.meter.caps.actor_calls==8 and h.meter.caps.wall_seconds==90
    assert h.delays==[1] and h.client_options[0]['max_retries']==0
    assert all(request['timeout']==20 and request['max_tokens']==2000 for request in h.requests)
    if prior_turns: assert h.requests[-1]['response_format']['type']=='json_schema'
    events=h.store.events('episode-test')['events']
    retries=[e['payload'] for e in events if e['type']=='actor_transport_retry']
    assert retries==[{'code':'HTTP_ERROR','attempt':1,'http_status':503,'retry_delay_seconds':1}]
    failures=h.store.list_records('provider_failures')
    assert len(failures)==1 and failures[0]['diagnostics']['http_status']==503
    assert 'private SDK' not in canonical_json(failures)
    h.store.close()


@pytest.mark.anyio
async def test_every_turn_can_retry_once_but_total_stays_sixteen_requests_eight_turns(tmp_path,monkeypatch):
    h=setup(tmp_path,monkeypatch,[entry for result in [TOOL]*7+[REPORT] for entry in (503,result)])
    await Actor()(h.intent,h.context)
    assert len(h.requests)==h.ledger.used_calls==h.meter.usage.model_calls==16
    assert h.meter.usage.actor_calls==8 and len(h.business)==7 and h.delays==[1]*8
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('second',[503,RuntimeProviderError('safe',code='CONNECTION_ERROR')])
async def test_second_failure_ends_turn_without_third_request(tmp_path,monkeypatch,second):
    h=setup(tmp_path,monkeypatch,[503,second,REPORT])
    with pytest.raises(RuntimeProviderError): await Actor()(h.intent,h.context)
    assert len(h.requests)==h.ledger.used_calls==h.meter.usage.model_calls==2
    assert h.meter.usage.actor_calls==1 and h.delays==[1]
    assert len(h.store.list_records('provider_failures'))==2
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('status',[400,401,403,404,408,409,422,429,500,502,504])
async def test_other_http_statuses_are_not_retried(tmp_path,monkeypatch,status):
    h=setup(tmp_path,monkeypatch,[status,REPORT])
    with pytest.raises(RuntimeProviderError) as caught: await Actor()(h.intent,h.context)
    assert caught.value.code=='HTTP_ERROR' and caught.value.http_status==status
    assert len(h.requests)==h.ledger.used_calls==1 and h.delays==[]
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('code,status',[('HTTP_ERROR',503),('CONNECTION_ERROR',None),('REQUEST_TIMEOUT',None)])
async def test_error_with_returned_generation_is_accounted_but_never_retried(tmp_path,monkeypatch,code,status):
    error=RuntimeProviderError('safe',code=code,http_status=status,
        generation=RuntimeGeneration('returned answer',MODEL,input_tokens=31,output_tokens=17))
    h=setup(tmp_path,monkeypatch,[error,REPORT])
    with pytest.raises(RuntimeProviderError) as caught: await Actor()(h.intent,h.context)
    assert caught.value is error and len(h.requests)==h.ledger.used_calls==1 and h.delays==[]
    assert h.meter.usage.input_tokens==31 and h.meter.usage.output_tokens==17
    assert h.ledger.measured_input==31 and h.ledger.measured_output==17
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('malformed',[False,True])
async def test_actual_empty_or_malformed_sdk_response_never_retries(tmp_path,monkeypatch,malformed):
    response=SimpleNamespace(choices=[] if malformed else [SimpleNamespace(finish_reason='length',
        message=SimpleNamespace(content=None))],usage=SimpleNamespace(prompt_tokens=7,completion_tokens=2000))
    h=setup(tmp_path,monkeypatch,[response,REPORT])
    with pytest.raises(RuntimeProviderError) as caught: await Actor()(h.intent,h.context)
    assert caught.value.code==('INVALID_RESPONSE_SHAPE' if malformed else 'EMPTY_FINAL_RESPONSE')
    assert caught.value.generation is not None
    assert len(h.requests)==h.ledger.used_calls==1 and h.delays==[]
    assert h.meter.usage.output_tokens==2000
    h.store.close()


@pytest.mark.anyio
async def test_invalid_actor_action_uses_existing_next_turn_correction_not_blind_retry(tmp_path,monkeypatch):
    h=setup(tmp_path,monkeypatch,[{'kind':'unsupported'},REPORT])
    await Actor()(h.intent,h.context)
    assert len(h.requests)==h.ledger.used_calls==h.meter.usage.model_calls==h.meter.usage.actor_calls==2
    assert h.delays==[] and h.requests[0]['messages']!=h.requests[1]['messages']
    assert not h.store.list_records('provider_failures')
    assert not [e for e in h.store.events('episode-test')['events'] if e['type']=='actor_transport_retry']
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('calls,tokens,dollars',[(1,544000,20.0),(16,34000,20.0),(16,544000,.0209)])
async def test_retry_refused_by_charged_campaign_limits_preserves_503(tmp_path,monkeypatch,calls,tokens,dollars):
    h=setup(tmp_path,monkeypatch,[503,REPORT],calls=calls,tokens=tokens,dollars=dollars)
    with pytest.raises(RuntimeProviderError) as caught: await Actor()(h.intent,h.context)
    assert caught.value.http_status==503
    assert len(h.requests)==h.ledger.used_calls==h.meter.usage.model_calls==1
    assert h.ledger.used_dollar_upper_bound==pytest.approx(.0209)
    assert not [e for e in h.store.events('episode-test')['events'] if e['type']=='actor_transport_retry']
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('calls,tokens,dollars',[(16,1088000,20.0),(32,544000,20.0),(32,1088000,16*.0209+1e-9)])
async def test_retry_does_not_steal_next_episode_reservation_and_retains_original_503(tmp_path,monkeypatch,calls,tokens,dollars):
    h=setup(tmp_path,monkeypatch,[503,REPORT],calls=calls,tokens=tokens,dollars=dollars,reservation_calls=16)
    with pytest.raises(RuntimeProviderError) as caught: await Actor()(h.intent,h.context)
    assert caught.value.code=='HTTP_ERROR' and caught.value.http_status==503
    assert len(h.requests)==h.ledger.used_calls==h.meter.usage.model_calls==1
    assert h.ledger.reservations['batch']=={'calls':15,'tokens':15*34000}
    assert h.meter.usage.actor_calls==1 and h.delays==[1]
    assert not [e for e in h.store.events('episode-test')['events'] if e['type']=='actor_transport_retry']
    assert h.store.list_records('provider_failures')[0]['diagnostics']['http_status']==503
    h.store.close()


@pytest.mark.anyio
async def test_last_turn_of_final_reserved_episode_can_retry_from_spare_capacity(tmp_path,monkeypatch):
    h=setup(tmp_path,monkeypatch,[TOOL]*7+[503,REPORT],calls=17,tokens=17*34000,reservation_calls=16)
    # A preceding episode used all eight of its required turns from this batch.
    preceding=EpisodeMeter(campaign=h.ledger,reservation='batch')
    for _ in range(8): preceding.model_call()
    report=await Actor()(h.intent,h.context)
    assert report.model_dump(mode='json')==REPORT['report']
    assert h.requests[-2]==h.requests[-1]
    assert h.requests[-1]['response_format']['type']=='json_schema'
    assert h.meter.usage.actor_calls==8 and h.meter.usage.model_calls==9
    assert h.ledger.used_calls==17 and h.ledger.reservations['batch']=={'calls':0,'tokens':0}
    assert h.ledger.used_dollar_upper_bound==pytest.approx(17*.0209)
    saved=h.store.get_record('budgets','campaign-test')
    restored=CampaignLedger(h.store,'campaign-test')
    assert h.store.get_record('budgets','campaign-test')==saved
    assert restored.used_calls==17 and restored.used_tokens==17*34000
    assert restored.reservations==h.ledger.reservations
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('stop',[False,True])
async def test_wait_then_admission_respects_episode_deadline_or_stop(tmp_path,monkeypatch,stop):
    h=setup(tmp_path,monkeypatch,[503,REPORT])
    if stop: h.meter.stop=lambda:bool(h.delays)
    else: h.clock[0]=89.5
    with pytest.raises(RuntimeProviderError) as caught: await Actor()(h.intent,h.context)
    assert caught.value.http_status==503
    assert h.delays==[1] and len(h.requests)==h.ledger.used_calls==1
    h.store.close()


@pytest.mark.anyio
async def test_retry_timeout_uses_remaining_wall_time_after_delay(tmp_path,monkeypatch):
    h=setup(tmp_path,monkeypatch,[503,REPORT]);h.clock[0]=88.5
    await Actor()(h.intent,h.context)
    assert [request['timeout'] for request in h.requests]==[1.5,.5]
    assert h.meter.usage.model_calls==h.ledger.used_calls==2
    h.store.close()


@pytest.mark.anyio
async def test_cancellation_during_delay_is_not_caught_or_charged_as_retry(tmp_path,monkeypatch):
    from app.agents import actor
    h=setup(tmp_path,monkeypatch,[503,REPORT])
    async def cancel(seconds): raise asyncio.CancelledError()
    monkeypatch.setattr(actor.asyncio,'sleep',cancel)
    with pytest.raises(asyncio.CancelledError): await Actor()(h.intent,h.context)
    assert len(h.requests)==h.ledger.used_calls==1
    assert len(h.store.list_records('provider_failures'))==1
    h.store.close()
