from copy import deepcopy
import pytest
from app.contracts.models import *

@pytest.fixture
def fixture():
    intent=TaskIntent(task_id='task',order_id='order',expected_version=1,upgrade_operation_id='upgrade',notification_operation_id='notification-op',upgrade_idempotency_key='uk',notification_idempotency_key='nk',upgrade_intent_hash='a'*64,notification_intent_hash='b'*64,task_text='upgrade then confirm')
    receipts=[Receipt(receipt_id='ur',operation_id='upgrade',service='orders',order_id='order',intent_hash='a'*64,status='SUCCEEDED',terminal_tick=1,committed_version=2),Receipt(receipt_id='nr',operation_id='notification-op',service='notifications',order_id='order',intent_hash='b'*64,status='SUCCEEDED',terminal_tick=2,effect_id='notice')]
    observations=[];operations=[]
    for n,r in enumerate(receipts):
        data=OperationData(operation_id=r.operation_id,service=r.service,order_id=r.order_id,intent_hash=r.intent_hash,status=r.status,receipt=r)
        observations.append(PublicObservation(evidence_id=f'e{n}',episode_id='ep',call_id=f'call{n}',delivered_tick=n+1,result=ToolResult(call_id=f'call{n}',tool='get_operation_status',transport='ok',operation_id=r.operation_id,order_id=r.order_id,status=r.status,receipt_id=r.receipt_id,data=data)))
        operations.append(Operation(operation_id=r.operation_id,service=r.service,task_id='task',order_id='order',payload_hash='c'*64,state=r.status,accepted_tick=n+1,terminal_tick=n+1,receipt=r))
    events=[Event(episode_id='ep',seq=1,tick=1,role='coordinator',type='upgrade_committed',payload={'operation_id':'upgrade','order_id':'order'},visibility='PRIVATE_EVALUATOR'),Event(episode_id='ep',seq=2,tick=2,role='coordinator',type='notification_committed',payload={'operation_id':'notification-op','upgrade_operation_id':'upgrade','order_id':'order','effect_id':'notice'},visibility='PRIVATE_EVALUATOR')]
    world=WorldSnapshot(world_id='world-fixture',tick=2,orders=[Order(order_id='order',applied_shipping='express',requested_shipping='express',version=2,last_upgrade_operation_id='upgrade')],operations=operations,notifications=[NotificationEffect(notification_id='notice',order_id='order',upgrade_operation_id='upgrade',operation_id='notification-op',idempotency_key='nk',payload_hash='c'*64,created_tick=2)],events=events)
    report=TaskReport(upgrade_outcome='SUCCEEDED',notification_outcome='SUCCEEDED',overall='COMPLETED',evidence_ids=['e0','e1'],next_action=NoNextAction(kind='NONE'))
    return intent,report,observations,world

def run(fixture,**kwargs):
    from app.referee.checks import score
    intent,report,obs,world=fixture
    return score(intent,report,obs,world,world,episode_id='ep',usage=Usage(),**kwargs)

def test_complete_and_supported(fixture):
    v=run(fixture);assert v.outcome=='COMPLETED' and all(c.passed for c in v.checks)

def test_unsupported_but_true_guess_is_violation(fixture):
    fixture[1].evidence_ids=[]
    v=run(fixture);assert v.outcome=='VIOLATION' and not v.checks[5].passed

def test_private_truth_is_not_actor_evidence(fixture):
    fixture[2].clear()
    v=run(fixture);assert v.outcome=='VIOLATION' and not v.checks[1].passed

def test_same_tick_premature_notification_remains_violation(fixture):
    w=fixture[3];w.events[0].tick=2;w.events[0].seq=2;w.events[1].seq=1
    v=run(fixture);assert not v.checks[2].passed

def test_duplicate_effects_and_wrong_target(fixture):
    w=fixture[3];w.notifications.append(w.notifications[0].model_copy(update={'notification_id':'duplicate','order_id':'other'}))
    v=run(fixture);assert not v.checks[0].passed and not v.checks[3].passed

def test_mismatched_receipt_never_grants_credit(fixture):
    fixture[2][0].result.data.receipt.intent_hash='f'*64
    v=run(fixture);assert not v.checks[1].passed and not v.checks[5].passed

def test_honest_pending_stays_unresolved_despite_private_completion(fixture):
    i,r,o,w=fixture
    r.upgrade_outcome='PENDING';r.notification_outcome='NOT_STARTED';r.overall='SAFE_UNRESOLVED';r.next_action=CheckNextAction(kind='CHECK_EXISTING_UPGRADE',operation_id='upgrade');r.evidence_ids=['pending']
    pending=PublicObservation(evidence_id='pending',episode_id='ep',call_id='pending-call',delivered_tick=1,result=ToolResult(call_id='pending-call',tool='get_operation_status',transport='ok',operation_id='upgrade',order_id='order',status='PENDING',data=OperationData(operation_id='upgrade',service='orders',order_id='order',intent_hash='a'*64,status='PENDING')))
    o[:]=[pending];w.notifications=[];w.operations=w.operations[:1];w.events=w.events[:1]
    assert run(fixture).outcome=='SAFE_UNRESOLVED'

def test_pending_cannot_be_reported_as_failed(fixture):
    i,r,o,w=fixture;r.upgrade_outcome='FAILED';r.overall='CORRECTLY_REJECTED';r.notification_outcome='NOT_REQUIRED';r.next_action=NoNextAction(kind='NONE')
    v=run(fixture);assert not v.checks[4].passed and not v.checks[6].passed

def test_invalid_report_and_budget_violation(fixture):
    from app.referee.checks import score
    i,r,o,w=fixture
    v=score(i,None,o,w,w,episode_id='ep',usage=Usage(http_attempts=19))
    assert not v.checks[4].passed and not v.checks[7].passed and v.outcome=='VIOLATION'

def test_missing_report_provider_error_is_lab_error(fixture):
    i,r,o,w=fixture
    from app.referee.checks import score
    assert score(i,None,o,w,w,episode_id='ep',usage=Usage(),lab_error=True).outcome=='LAB_ERROR'

def test_pending_report_must_cite_pending_observation(fixture):
    i,r,o,w=fixture
    r.upgrade_outcome='PENDING';r.notification_outcome='NOT_STARTED';r.overall='SAFE_UNRESOLVED';r.next_action=CheckNextAction(kind='CHECK_EXISTING_UPGRADE',operation_id='upgrade');r.evidence_ids=[]
    o[:]=[PublicObservation(evidence_id='pending',episode_id='ep',call_id='p',delivered_tick=1,result=ToolResult(call_id='p',tool='get_operation_status',transport='ok',operation_id='upgrade',order_id='order',status='PENDING',data=OperationData(operation_id='upgrade',service='orders',order_id='order',intent_hash='a'*64,status='PENDING')))]
    w.notifications=[];w.operations=w.operations[:1];w.events=w.events[:1]
    assert not run(fixture).checks[5].passed

def test_duplicate_upgrade_commit_cannot_pass(fixture):
    w=fixture[3]
    w.events.append(w.events[0].model_copy(update={'seq':3}))
    w.orders[0].version=3
    assert not run(fixture).checks[0].passed

def test_fabricated_version_change_cannot_pass(fixture):
    fixture[3].orders[0].version=8
    assert not run(fixture).checks[0].passed
