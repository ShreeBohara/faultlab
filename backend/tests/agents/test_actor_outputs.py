"""Local diagnostics preserve actual answers, including rejected final tools."""
import json
from types import SimpleNamespace

import pytest

from app.adapters.journal import Journal, allocate_intent
from app.agents.actor import Actor, ActorReportError
from app.contracts.models import RecoveryPolicy, canonical_json, content_hash
from app.lab.budgets import EpisodeMeter
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration


@pytest.fixture
def anyio_backend(): return 'asyncio'


def setup(tmp_path, outputs):
    store=LabStore(tmp_path/'lab.db')
    store.put_record('episodes','episode-test',{'campaign_id':'campaign-test'})
    intent=allocate_intent('order-test','Upgrade and confirm')
    broker=SimpleNamespace(journal=Journal(store,'episode-test',intent),meter=EpisodeMeter())
    calls=[]; messages=[]; responses=iter(outputs)
    async def call(tool,arguments):
        broker.meter.http_attempt(); calls.append((tool,arguments))
    broker.call=call
    class Provider:
        async def complete(self,request,**kwargs):
            messages.append(request)
            return RuntimeGeneration(next(responses),'openai/gpt-oss-120b')
    context=SimpleNamespace(broker=broker,interpreter=PolicyInterpreter(RecoveryPolicy(parent_version='policy-v0',rules=[]),broker),
                            provider=Provider(),metadata={'model_id':'openai/gpt-oss-120b'})
    return intent,context,store,calls,messages


@pytest.mark.anyio
async def test_invalid_answer_and_original_report_are_preserved_without_dispatch_or_rewrite(tmp_path):
    invalid='{"kind":"tool","tool":"get_order","arguments":{"wrong":"original"}}'
    report={'upgrade_outcome':'NOT_STARTED','notification_outcome':'NOT_STARTED','overall':'SAFE_UNRESOLVED',
            'evidence_ids':[],'next_action':{'kind':'ESCALATE'}}
    raw=canonical_json({'kind':'report','report':report})
    intent,context,store,calls,messages=setup(tmp_path,[invalid,raw])
    returned=await Actor()(intent,context)
    events=store.events('episode-test')['events']
    outputs=[event['payload'] for event in events if event['type']=='actor_output']
    assert [row['raw'] for row in outputs]==[invalid,raw]
    assert [row['actor_turn'] for row in outputs]==[1,2]
    assert [row['messages_hash'] for row in outputs]==[content_hash(request) for request in messages]
    assert [row['request_hash'] for row in outputs]==[content_hash({'messages':request,'response_format':{'type':'json_object'}}) for request in messages]
    assert all(row['source']=='local_actor_output' and row['delivered_evidence_ids']==[] for row in outputs)
    assert calls==[] and context.broker.meter.usage.actor_calls==2
    assert returned.model_dump(mode='json')==report
    assert [e['payload']['report'] for e in events if e['type']=='report_submitted']==[report]


@pytest.mark.anyio
async def test_final_tool_remains_original_failed_attempt_and_does_not_get_dispatched(tmp_path):
    raw='{"kind":"tool","tool":"get_order","arguments":{}}'
    intent,context,store,calls,messages=setup(tmp_path,[raw]*8)
    with pytest.raises(ActorReportError): await Actor()(intent,context)
    events=store.events('episode-test')['events']
    outputs=[e['payload'] for e in events if e['type']=='actor_output']
    assert len(outputs)==8 and all(o['raw']==raw for o in outputs)
    assert [o['remaining_actor_calls_at_request'] for o in outputs]==list(range(8,0,-1))
    assert [o['final_report_required'] for o in outputs]==[False]*7+[True]
    assert len(calls)==7 and context.broker.meter.usage.actor_calls==8
    assert not any(e['type']=='report_submitted' for e in events)
    assert json.loads(messages[-1][-1]['content'])['final_report_required'] is True
