import pytest
from app.contracts.models import CampaignBudget
from app.lab.storage import LabStore
from app.lab.budgets import CampaignLedger,EpisodeMeter,BudgetExhausted,StopRequested,CANDIDATE_CALLS

def test_protected_batches_and_complete_admission(tmp_path):
    ledger=CampaignLedger(LabStore(tmp_path/'lab.db'),'c',CampaignBudget(model_calls=1600,tokens=16000000))
    assert ledger.reserved_calls==1064
    with pytest.raises(BudgetExhausted): ledger.reserve('candidate',CANDIDATE_CALLS)
    assert set(ledger.reservations)=={'final_audit','portability','selection_comparison'}

def test_missing_usage_never_refunds(tmp_path):
    ledger=CampaignLedger(LabStore(tmp_path/'lab.db'),'c'); ledger.reserve('candidate',24)
    ledger.consume_call(reservation='candidate')
    from app.providers.runtime import RuntimeGeneration
    ledger.reconcile(RuntimeGeneration('x','m'))
    assert ledger.used_calls==1 and ledger.used_tokens==10000
    assert ledger.reservations['candidate']['calls']==23
    ledger.release('candidate'); assert ledger.reserved_calls==1064

def test_http_retry_wait_and_step_caps():
    meter=EpisodeMeter()
    for i in range(18): meter.http_attempt()
    with pytest.raises(BudgetExhausted): meter.http_attempt()
    assert meter.usage.http_attempts==18 and meter.usage.ticks==18
    with pytest.raises(BudgetExhausted): meter.wait(4)
    assert meter.usage.wait_cycles==0
    for i in range(32): meter.take('policy_steps')
    with pytest.raises(BudgetExhausted): meter.take('policy_steps')

def test_wait_cycles_and_actor_last_turn():
    meter=EpisodeMeter()
    for i in range(4): meter.wait(1)
    with pytest.raises(BudgetExhausted): meter.wait(1)
    for i in range(7): meter.model_call()
    assert meter.final_turn
    meter.model_call()
    with pytest.raises(BudgetExhausted): meter.model_call()
    assert meter.usage.input_tokens==0  # Unknown provider usage is never fabricated.

def test_stop_and_wall_admission():
    now=[0]; stop=[False]; meter=EpisodeMeter(clock=lambda:now[0],stop=lambda:stop[0])
    stop[0]=True
    with pytest.raises(StopRequested): meter.http_attempt()
    stop[0]=False; now[0]=90
    with pytest.raises(BudgetExhausted): meter.model_call()
    assert meter.usage.model_calls==0

def test_first_unknown_call_cannot_breach_protected_dollar_bound(tmp_path):
    ledger=CampaignLedger(LabStore(tmp_path/'lab.db'),'c',CampaignBudget(dollars=100.0),dollar_bound=.10)
    with pytest.raises(BudgetExhausted): ledger.consume_call()
    with pytest.raises(BudgetExhausted): ledger.reserve('candidate',24)
    assert ledger.used_calls==0 and ledger.used_cost is None and ledger.reserved_calls==1064

def test_known_and_unknown_costs_are_separate_from_upper_bound(tmp_path):
    from app.providers.runtime import RuntimeGeneration
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c',dollar_bound=.01)
    ledger.consume_call(); ledger.reconcile(RuntimeGeneration('x','m',input_tokens=12,output_tokens=4,cost_usd=.001))
    assert store.get_record('budgets','c')['actual_cost_dollars']==.001
    ledger.consume_call(); ledger.reconcile(RuntimeGeneration('x','m'))
    data=store.get_record('budgets','c')
    assert data['actual_cost_dollars'] is None and data['charged_dollar_upper_bound']==.02
    assert data['measured_input_tokens']==12 and data['unknown_cost_calls']==1

def test_unreturned_request_usage_is_unknown_immediately(tmp_path):
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c')
    ledger.consume_call()
    assert not ledger.usage_known and store.get_record('budgets','c')['usage_metadata_known'] is False
    assert ledger.unknown_token_calls==1 and ledger.measured_input==ledger.measured_output==0
