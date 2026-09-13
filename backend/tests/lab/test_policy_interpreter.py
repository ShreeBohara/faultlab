from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.contracts.models import RecoveryPolicy,CandidatePolicy,ToolResult,OperationData,Receipt,canonical_json,new_id
from app.lab.storage import LabStore
from app.lab.budgets import EpisodeMeter
from app.adapters.journal import Journal,allocate_intent
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.policy_state import PolicyState

@pytest.fixture
def broker(tmp_path):
    store=LabStore(tmp_path/'lab.db'); store.put_record('episodes','e',{'campaign_id':'c'})
    journal=Journal(store,'e',allocate_intent('order-1','Upgrade and confirm'))
    return SimpleNamespace(journal=journal,meter=EpisodeMeter())

@pytest.mark.anyio
async def test_empty_overlay_has_no_recovery_behavior(broker):
    interpreter=PolicyInterpreter(RecoveryPolicy(parent_version='policy-v0',rules=[]),broker)
    result=await interpreter.invoke('before_confirmation','p')
    assert not result.blocked and not result.final_requested and not result.reasons
    assert broker.meter.usage.http_attempts==broker.meter.usage.policy_steps==0

@pytest.mark.anyio
async def test_scoped_requirement_blocks_confirmation_not_honest_report(broker):
    policy=RecoveryPolicy.model_validate_json(canonical_json({'parent_version':'policy-v0','rules':[{'hook':'before_confirmation','when':'always','steps':[{'op':'require_receipt','service':'orders','status':'SUCCEEDED'}]},{'hook':'before_final_report','when':'always','steps':[{'op':'require_receipt','service':'orders','status':'SUCCEEDED'}]}]}))
    interpreter=PolicyInterpreter(policy,broker)
    assert (await interpreter.invoke('before_confirmation','p')).blocked
    honest=SimpleNamespace(upgrade_outcome='UNKNOWN',notification_outcome='NOT_STARTED')
    assert not (await interpreter.invoke('before_final_report','q',honest)).blocked
    success=SimpleNamespace(upgrade_outcome='SUCCEEDED',notification_outcome='NOT_STARTED')
    assert (await interpreter.invoke('before_final_report','r',success)).blocked
    assert honest.upgrade_outcome=='UNKNOWN'

@pytest.mark.anyio
async def test_skipped_steps_count_and_hooks_cannot_reenter(broker):
    policy=RecoveryPolicy.model_validate_json(canonical_json({'parent_version':'policy-v0','rules':[{'hook':'before_confirmation','when':'always','steps':[{'op':'read_current_operation','only_if':'upgrade_succeeded'}]}]}))
    interpreter=PolicyInterpreter(policy,broker)
    await interpreter.invoke('before_confirmation','p')
    assert broker.meter.usage.policy_steps==1
    with pytest.raises(ValueError): await interpreter.invoke('before_confirmation','p')

@pytest.mark.parametrize('bad',[{'op':'exec','code':'x'},{'op':'read_order','url':'https://evil.test'},{'op':'wait_ticks','ticks':5},{'op':'retry_original_request','service':'notifications'}])
def test_unknown_or_disallowed_policy_rejected(bad):
    with pytest.raises(ValidationError): CandidatePolicy.model_validate_json(canonical_json({'parent_version':'policy-v0','rules':[{'hook':'before_confirmation','when':'always','steps':[bad]}]}))

def test_terminal_receipt_persists_after_unknown_and_stale(broker):
    i=broker.journal.intent
    receipt=Receipt(receipt_id='receipt-1',operation_id=i.upgrade_operation_id,service='orders',order_id=i.order_id,intent_hash=i.upgrade_intent_hash,status='SUCCEEDED',terminal_tick=1,committed_version=2)
    data=OperationData(operation_id=i.upgrade_operation_id,service='orders',order_id=i.order_id,intent_hash=i.upgrade_intent_hash,status='SUCCEEDED',receipt=receipt)
    broker.journal.deliver(ToolResult(call_id='c1',tool='update_order',transport='ok',operation_id=i.upgrade_operation_id,status='SUCCEEDED',receipt_id='receipt-1',data=data),1)
    broker.journal.deliver(ToolResult(call_id='c2',tool='get_operation_status',transport='error',operation_id=i.upgrade_operation_id,status='UNKNOWN'),2)
    state=PolicyState(broker.journal)
    assert state.condition('upgrade_succeeded') and not state.condition('upgrade_outcome_uncertain')
    assert not state.condition('receipt_missing')

@pytest.fixture
def anyio_backend(): return "asyncio"
