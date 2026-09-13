"""Real typed actor loop with offline provider outputs; no learning claim."""
import json
from types import SimpleNamespace

import pytest

from app.adapters.journal import Journal,allocate_intent
from app.agents.actor import Actor,ActorReportError,ACTION_ADAPTER
from app.contracts.models import RecoveryPolicy,canonical_json
from app.lab.budgets import EpisodeMeter
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration


@pytest.fixture
def anyio_backend(): return 'asyncio'


def context(tmp_path,provider):
    store=LabStore(tmp_path/'lab.db')
    store.put_record('episodes','episode-fixture',{'campaign_id':'campaign-fixture'})
    intent=allocate_intent('order-demo','Upgrade and confirm')
    broker=SimpleNamespace(journal=Journal(store,'episode-fixture',intent),meter=EpisodeMeter())
    calls=[]
    async def call(tool,arguments):
        calls.append((tool,arguments)); broker.meter.http_attempt()
    broker.call=call
    interpreter=PolicyInterpreter(RecoveryPolicy(parent_version='policy-v0',rules=[]),broker)
    return intent,SimpleNamespace(broker=broker,interpreter=interpreter,provider=provider,metadata={'model_id':'openai/gpt-oss-120b'}),calls


@pytest.mark.anyio
async def test_extra_tool_argument_feedback_keeps_original_and_requires_model_correction(tmp_path):
    bad=canonical_json({'kind':'tool','tool':'get_order','arguments':{'order_id':'order-demo'}})
    good=canonical_json({'kind':'tool','tool':'get_order','arguments':{}})
    report={'upgrade_outcome':'NOT_STARTED','notification_outcome':'NOT_STARTED','overall':'SAFE_UNRESOLVED','evidence_ids':[],'next_action':{'kind':'ESCALATE'}}
    class Provider:
        def __init__(self): self.messages=[]
        async def complete(self,messages,**kwargs):
            self.messages.append(messages)
            assert json.loads(messages[1]['content'])['output_schema']==ACTION_ADAPTER.json_schema()
            index=len(self.messages)
            if index==1: output=bad
            elif index==2:
                assert calls==[] and actor_context.broker.meter.usage.http_attempts==0
                assert messages[2]=={'role':'assistant','content':bad}
                feedback=json.loads(messages[3]['content'])
                assert feedback['action_errors']==[{'location':['tool','get_order','arguments','order_id'],'type':'extra_forbidden'}]
                assert 'No business call was executed' in feedback['instruction']
                assert json.loads(messages[-1]['content'])['remaining_actor_calls']==7
                output=good
            else:
                assert calls==[('get_order',{})]
                output=canonical_json({'kind':'report','report':report})
            return RuntimeGeneration(output,'openai/gpt-oss-120b',input_tokens=30,output_tokens=20)
    provider=Provider(); intent,actor_context,calls=context(tmp_path,provider)
    result=await Actor()(intent,actor_context)
    assert result.model_dump(mode='json')==report
    assert actor_context.broker.meter.usage.actor_calls==3 and len(calls)==1
    assert len(provider.messages)==3


@pytest.mark.anyio
async def test_repeated_invalid_actions_stop_at_original_turn_cap_without_dispatch(tmp_path):
    bad=canonical_json({'kind':'tool','tool':'get_order','arguments':{'order_id':'order-demo'}})
    class Provider:
        calls=0
        async def complete(self,messages,**kwargs):
            self.calls+=1
            assert sum(m['role']=='assistant' for m in messages)==self.calls-1
            return RuntimeGeneration(bad,'openai/gpt-oss-120b')
    provider=Provider(); intent,actor_context,calls=context(tmp_path,provider)
    with pytest.raises(ActorReportError,match='actor limit'):
        await Actor()(intent,actor_context)
    assert provider.calls==actor_context.broker.meter.usage.actor_calls==8
    assert calls==[] and actor_context.broker.meter.usage.http_attempts==0
