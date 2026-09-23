"""Final-turn format enforcement cannot substitute an answer or add a turn."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.adapters.business_tools import WorldClient
from app.adapters.journal import Journal,allocate_intent
from app.agents.actor import Actor,ACTION_ADAPTER
from app.config import Settings
from app.contracts.models import CampaignRequest,FaultSpec,RecoveryPolicy,canonical_json,content_hash
from app.contracts.tokens import input_token_bound
from app.lab.budgets import EpisodeMeter
from app.lab.coordinator import LabCoordinator
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.runner import EpisodeRunner
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration,actor_response_protocol,response_format_for,validate_request_input
from app.simulator.main import create_app


@pytest.fixture
def anyio_backend(): return 'asyncio'


REPORT={'upgrade_outcome':'NOT_STARTED','notification_outcome':'NOT_STARTED',
        'overall':'SAFE_UNRESOLVED','evidence_ids':[],'next_action':{'kind':'ESCALATE'}}
TOOL={'kind':'tool','tool':'get_order','arguments':{}}


def setup(tmp_path,*,close_after_tool=False):
    store=LabStore(tmp_path/'lab.db');store.put_record('episodes','episode-test',{'campaign_id':'campaign-test'})
    intent=allocate_intent('order-test','Upgrade and confirm')
    broker=SimpleNamespace(journal=Journal(store,'episode-test',intent),meter=EpisodeMeter())
    requests=[];business=[]
    async def call(tool,arguments):
        broker.meter.http_attempt();business.append((tool,arguments))
        if close_after_tool: broker.meter.business_closed=True
    broker.call=call
    class Provider:
        async def complete(self,messages,**kwargs):
            requests.append((messages,kwargs))
            final=json.loads(messages[-1]['content'])['final_report_required']
            output={'kind':'report','report':REPORT} if final else TOOL
            return RuntimeGeneration(canonical_json(output),'openai/gpt-oss-120b')
    context=SimpleNamespace(broker=broker,interpreter=PolicyInterpreter(RecoveryPolicy(parent_version='policy-v0',rules=[]),broker),
        provider=Provider(),metadata={'model_id':'openai/gpt-oss-120b'})
    return intent,context,requests,business,store


@pytest.mark.anyio
@pytest.mark.parametrize('close_after_tool,turns',[(False,8),(True,2)])
async def test_only_required_report_turns_select_fixed_schema(tmp_path,close_after_tool,turns):
    intent,context,requests,business,store=setup(tmp_path,close_after_tool=close_after_tool)
    returned=await Actor()(intent,context)
    assert returned.model_dump(mode='json')==REPORT
    assert len(requests)==context.broker.meter.usage.actor_calls==turns
    assert len(business)==turns-1
    assert [kwargs['response_contract'] for _,kwargs in requests]==[None]*(turns-1)+['actor_final_report']
    outputs=[e['payload'] for e in store.events('episode-test')['events'] if e['type']=='actor_output']
    for output,(messages,kwargs) in zip(outputs,requests,strict=True):
        fmt=response_format_for(response_contract=kwargs['response_contract'])
        assert output['request_hash']==content_hash({'messages':messages,'response_format':fmt})
        assert output['response_format_hash']==content_hash(fmt)
        assert output['actor_response_protocol_hash']==content_hash(actor_response_protocol())
        assert output['source']=='local_actor_output'
    store.close()


@pytest.mark.anyio
async def test_actor_admits_schema_before_debit_or_provider_dispatch(tmp_path,monkeypatch):
    from app.agents import actor
    intent,context,requests,business,store=setup(tmp_path)
    context.metadata['model_id']='unregistered-byte-bound-model'
    context.broker.meter.business_closed=True
    user={'observations':[],'final_report_required':True,'remaining_actor_calls':8}
    base=[{'role':'system','content':''},{'role':'user','content':canonical_json({'task':intent.model_dump(mode='json'),
          'output_schema':ACTION_ADAPTER.json_schema()})},{'role':'user','content':canonical_json(user)}]
    padding='x'*(31900-input_token_bound(base,context.metadata['model_id']))
    monkeypatch.setattr(actor,'ACTOR_PROMPT',padding)
    base[0]['content']=padding
    assert validate_request_input(base,context.metadata['model_id'])<=32000
    with pytest.raises(ValueError,match='32,000-token'):
        await Actor()(intent,context)
    assert context.broker.meter.usage.actor_calls==context.broker.meter.usage.model_calls==0
    assert requests==business==[] and store.events('episode-test')['events']==[]
    store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('evidence_id,has_report',[('evidence-foreign',True),('evidence-bad 极',False)])
async def test_final_original_citation_failure_is_preserved_and_scored(tmp_path,evidence_id,has_report):
    raw=canonical_json({'kind':'report','report':{**REPORT,'evidence_ids':[evidence_id]}})
    requests=[]
    class Provider:
        async def complete(self,messages,**kwargs):
            requests.append(kwargs)
            return RuntimeGeneration(raw if len(requests)==8 else canonical_json(TOOL),'openai/gpt-oss-120b')
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test')
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001')
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade and confirm',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    trial=await EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),Provider()).run(
        campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline(),source_mode='offline_fixture')
    episode=c.store.get_record('episodes',trial.episode_id)
    assert trial.lifecycle=='COMPLETED' and trial.outcome=='VIOLATION' and 'C6' in trial.failed_checks
    assert len(requests)==trial.usage.actor_calls==8 and trial.usage.http_attempts==7
    assert requests[-1]['response_contract']=='actor_final_report'
    assert episode['report']==({**REPORT,'evidence_ids':[evidence_id]} if has_report else None)
    outputs=[e['payload'] for e in c.store.events(trial.episode_id)['events'] if e['type']=='actor_output']
    assert outputs[-1]['raw']==raw
    await client.aclose();await c.close()


def transport_setup(tmp_path, failures, *, after=0):
    """setup() with a provider that raises the given codes before succeeding.

    ``after`` delays the failures until that many calls have already succeeded, which
    is how a transport failure on the final allowed turn is reproduced.
    """
    from app.providers.runtime import RuntimeProviderError
    intent, context, requests, business, store = setup(tmp_path)
    inner = context.provider
    class Flaky:
        raised = []
        delivered = 0
        async def complete(self, messages, **kwargs):
            if self.delivered >= after and self.raised != failures:
                code = failures[len(self.raised)]
                self.raised = self.raised + [code]
                raise RuntimeProviderError('SDK MESSAGE MUST NOT BE STORED', code=code,
                                           error_class='APIConnectionError')
            self.delivered = self.delivered + 1
            return await inner.complete(messages, **kwargs)
    context.provider = Flaky()
    return intent, context, requests, business, store


@pytest.mark.anyio
@pytest.mark.parametrize('code', ['CONNECTION_ERROR', 'REQUEST_TIMEOUT'])
async def test_one_transport_failure_is_retried_blind_and_the_episode_survives(tmp_path, code):
    """No generation arrived, so nothing was observed and nothing can be selected on."""
    intent, context, requests, business, store = transport_setup(tmp_path, [code])
    returned = await Actor()(intent, context)
    assert returned.model_dump(mode='json') == REPORT          # the episode completed
    events = store.events('episode-test')['events']
    retries = [e for e in events if e['type'] == 'actor_transport_retry']
    assert len(retries) == 1 and retries[0]['payload'] == {'code': code, 'attempt': 1}
    # The retry is charged as a model call but not as an actor turn. The failed attempt
    # delivered no generation, so it took nothing the actor could have read; charging it
    # a turn used to cost the episode one of its eight turns outright.
    meter = context.broker.meter
    assert meter.usage.actor_calls == len(requests) == meter.caps.actor_calls == 8
    assert meter.usage.model_calls == len(requests) + 1
    # The failure is still recorded, and no raw SDK text is persisted.
    saved = store.list_records('provider_failures')
    assert len(saved) == 1 and saved[0]['diagnostics']['code'] == code
    assert 'MUST NOT BE STORED' not in json.dumps(saved)
    store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('code', ['CONNECTION_ERROR', 'REQUEST_TIMEOUT'])
async def test_a_transport_failure_on_the_final_allowed_turn_is_still_retried(tmp_path, code):
    """Phase 13 lost an episode, and with it a 42-episode batch, exactly here.

    The turn that carries the report is the last of the eight. Admitting the retry
    through model_call() made it unreachable, because model_call() had already raised
    actor_calls to the cap before the guard could read it.
    """
    intent, context, requests, business, store = transport_setup(tmp_path, [code], after=7)
    returned = await Actor()(intent, context)
    assert returned.model_dump(mode='json') == REPORT          # the episode survived
    meter = context.broker.meter
    assert meter.usage.actor_calls == meter.caps.actor_calls == 8
    assert meter.usage.model_calls == 9
    retries = [e for e in store.events('episode-test')['events']
               if e['type'] == 'actor_transport_retry']
    assert len(retries) == 1 and retries[0]['payload'] == {'code': code, 'attempt': 1}
    # The failure that was survived is still on the record.
    assert [f['diagnostics']['code'] for f in store.list_records('provider_failures')] == [code]
    # The retried turn is the report turn, and it is the only one with the fixed schema.
    assert [kwargs['response_contract'] for _, kwargs in requests] == [None] * 7 + ['actor_final_report']
    store.close()


@pytest.mark.anyio
async def test_a_retry_that_cannot_be_admitted_reraises_the_transport_failure(tmp_path):
    """A retry must never replace the failure that caused it with a budget error."""
    from app.providers.runtime import RuntimeProviderError
    intent, context, requests, business, store = transport_setup(tmp_path, ['CONNECTION_ERROR'])
    flaky = context.provider
    # The stop arrives with the transport failure, so the first call is admitted and
    # only the retry is refused.
    context.broker.meter.stop = lambda: bool(flaky.raised)
    with pytest.raises(RuntimeProviderError) as raised:
        await Actor()(intent, context)
    assert raised.value.code == 'CONNECTION_ERROR'
    assert not [e for e in store.events('episode-test')['events']
                if e['type'] == 'actor_transport_retry']
    store.close()


@pytest.mark.anyio
async def test_a_second_transport_failure_on_the_same_turn_is_not_retried_again(tmp_path):
    from app.providers.runtime import RuntimeProviderError
    intent, context, requests, business, store = transport_setup(
        tmp_path, ['CONNECTION_ERROR', 'CONNECTION_ERROR'])
    with pytest.raises(RuntimeProviderError):
        await Actor()(intent, context)
    retries = [e for e in store.events('episode-test')['events'] if e['type'] == 'actor_transport_retry']
    assert len(retries) == 1, 'exactly one retry, never two'
    assert len(store.list_records('provider_failures')) == 2
    store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('code', ['EMPTY_FINAL_RESPONSE', 'INVALID_RESPONSE_SHAPE',
                                  'HTTP_ERROR', 'PROVIDER_ERROR'])
async def test_a_delivered_response_is_never_retried(tmp_path, code):
    """A response that arrived is a generation; retrying it would be a re-roll."""
    from app.providers.runtime import RuntimeProviderError
    intent, context, requests, business, store = transport_setup(tmp_path, [code])
    with pytest.raises(RuntimeProviderError) as raised:
        await Actor()(intent, context)
    assert raised.value.code == code
    assert not [e for e in store.events('episode-test')['events'] if e['type'] == 'actor_transport_retry']
    store.close()
