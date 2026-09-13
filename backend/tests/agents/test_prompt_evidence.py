from types import SimpleNamespace
import pytest
from app.contracts.models import (ToolResult,PublicObservation,CheckResult,TaskReport,NoNextAction,Order,OperationData,Receipt,new_id,content_hash,canonical_json,CandidatePolicy)
from app.contracts.tokens import input_token_bound
from app.lab.diagnosis import summarize_evidence
from app.adapters.journal import allocate_intent
from app.agents.mechanic import Mechanic,PROMPTS
from app.lab.storage import LabStore
from app.lab.budgets import CampaignLedger
from app.providers.runtime import RuntimeGeneration

@pytest.fixture
def anyio_backend(): return 'asyncio'

def bundle(index,error_code=None):
    intent=allocate_intent('order-'+str(index),'Upgrade and confirm'); episode=new_id('episode'); observations=[]
    order=Order(order_id=intent.order_id,applied_shipping='standard',requested_shipping='standard',version=1)
    results=[ToolResult(call_id=new_id('call'),tool='get_order',transport='ok',order_id=intent.order_id,observed_version=1,data=order)]
    for tick,service in [(2,'orders'),(3,'notifications')]:
        operation=intent.upgrade_operation_id if service=='orders' else intent.notification_operation_id
        ih=intent.upgrade_intent_hash if service=='orders' else intent.notification_intent_hash
        receipt=Receipt(receipt_id=new_id('receipt'),operation_id=operation,service=service,order_id=intent.order_id,intent_hash=ih,status='SUCCEEDED',terminal_tick=tick,committed_version=2 if service=='orders' else None,effect_id=new_id('effect') if service=='notifications' else None)
        data=OperationData(operation_id=operation,service=service,order_id=intent.order_id,intent_hash=ih,status='SUCCEEDED',receipt=receipt)
        results.append(ToolResult(call_id=new_id('call'),tool='update_order' if service=='orders' else 'send_confirmation',transport='ok',operation_id=operation,order_id=intent.order_id,status='SUCCEEDED',receipt_id=receipt.receipt_id,data=data))
    if error_code: results.append(ToolResult(call_id=new_id('call'),tool='get_operation_status',transport='error',error_code=error_code))
    for tick,result in enumerate(results,1): observations.append(PublicObservation(evidence_id=new_id('evidence'),episode_id=episode,call_id=result.call_id,delivered_tick=tick,result=result))
    report=TaskReport(upgrade_outcome='SUCCEEDED',notification_outcome='SUCCEEDED',overall='COMPLETED',evidence_ids=[o.evidence_id for o in observations[:3]],next_action=NoNextAction(kind='NONE'))
    findings=[CheckResult(check_id=f'C{i}',passed=not(index==3 and i==3),category='premature_effect' if index==3 and i==3 else 'supported',evidence_ids=[o.evidence_id for o in observations],event_ids=[new_id('event')]) for i in range(1,9)]
    return SimpleNamespace(episode_id=episode,source='weave_verified',report=report,findings=findings,observations=observations)

@pytest.mark.anyio
async def test_ten_full_trials_fit_candidate_prompt_without_hiding_contradiction(tmp_path):
    bundles=[bundle(i) for i in range(10)]; compact=summarize_evidence(bundles)
    assert len(compact['episodes'])==10
    assert sum(len(e['observations']) for e in compact['episodes'])==30
    assert any(not check['passed'] for row in compact['checks'] for check in row)
    exact_ids={row[0] for episode in compact['episodes'] for row in episode['observations']}
    assert exact_ids=={o.evidence_id for b in bundles for o in b.observations}
    class Provider:
        async def complete(self,messages,**kwargs):
            assert input_token_bound(messages,'openai/gpt-oss-120b')<=8000
            return RuntimeGeneration('{"no_change_reason":"Offline fixture does not establish a repair"}','openai/gpt-oss-120b')
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c')
    result=await Mechanic(Provider(),store,ledger).propose({'parent_version':'policy-v0','development_evidence':compact})
    assert result[1] is not None and ledger.used_calls==1

def test_meaningful_hex_error_strings_are_not_normalized_to_identity():
    compact=summarize_evidence([bundle(1,'a'*32),bundle(2,'b'*32)])
    errors={r['error_code'] for r in compact['results'] if 'error_code' in r}
    assert errors=={'a'*32,'b'*32}
