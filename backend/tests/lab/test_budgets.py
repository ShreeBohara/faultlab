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
    assert ledger.used_calls==1 and ledger.used_tokens==34000
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


def test_new_token_reserves_derive_from_frozen_per_call_allowance(tmp_path):
    ledger=CampaignLedger(LabStore(tmp_path/'lab.db'),'c')
    assert ledger.tokens_per_call==34000 and ledger.caps.tokens==204000000
    assert ledger.reserved_tokens==36176000
    assert {name:r['tokens'] for name,r in ledger.reservations.items()}=={
        'final_audit':13056000,'portability':9792000,'selection_comparison':13328000}
    ledger.reserve('candidate',CANDIDATE_CALLS)
    assert ledger.reservations['candidate']['tokens']==18292000
    ledger.consume_call(reservation='candidate')
    assert ledger.used_tokens==34000
    assert ledger.reservations['candidate']['tokens']==18258000


def test_historical_caps_survive_ledger_reload_and_keep_old_debits(tmp_path):
    store=LabStore(tmp_path/'lab.db')
    old=CampaignBudget(tokens=60000000,input_tokens_per_call=8000,output_tokens_per_call=2000)
    ledger=CampaignLedger(store,'old',old,dollar_bound=.0077)
    ledger.consume_call()
    saved=store.get_record('budgets','old'); saved.pop('caps')
    store.put_record('budgets','old',saved)
    store.put_record('campaigns','old',{'caps':old.model_dump(mode='json')})
    restored=CampaignLedger(store,'old')
    assert restored.caps==old and restored.used_tokens==10000
    assert restored.tokens_per_call==10000 and restored.reserved_tokens==10640000
    assert restored.dollar_bound==.0077
    restored.consume_call()
    assert restored.used_tokens==20000
    with pytest.raises(BudgetExhausted,match='Frozen campaign budget changed'):
        CampaignLedger(store,'old',CampaignBudget())


def test_protected_token_admission_uses_raised_allowance(tmp_path):
    ledger=CampaignLedger(LabStore(tmp_path/'lab.db'),'c',CampaignBudget(tokens=36176000))
    with pytest.raises(BudgetExhausted):ledger.consume_call()
    with pytest.raises(BudgetExhausted):ledger.reserve('candidate',1)
    assert ledger.used_calls==0 and ledger.reserved_tokens==36176000


def test_coordinator_rejects_incomplete_protected_reserve_before_execution(tmp_path):
    import asyncio
    from app.config import Settings
    from app.contracts.models import CampaignRequest
    from app.lab.coordinator import LabCoordinator
    settings=Settings(faultlab_artifact_dir=str(tmp_path),wandb_api_key='fixture',wandb_entity='team',wandb_project='project',
        wandb_model='deepseek-ai/DeepSeek-V3.1',faultlab_live_enabled=True,faultlab_confirmed_entity='team',
        faultlab_token_cap=36175999,faultlab_input_dollars_per_million=.55,faultlab_output_dollars_per_million=1.65,
        faultlab_pricing_model='deepseek-ai/DeepSeek-V3.1',faultlab_pricing_verified=True)
    coordinator=LabCoordinator(settings)
    campaign=coordinator.create(CampaignRequest(task_text='Upgrade',order_id='order-fixture',mode='baseline',config_profile_id='live-v1'))
    with pytest.raises(BudgetExhausted,match='Mandatory protected batches'):
        asyncio.run(coordinator.start(campaign.campaign_id))
    assert coordinator.active_id is None and not coordinator.tasks and not coordinator.store.list_records('episodes')
    assert coordinator.store.get_record('configurations',campaign.configuration_hash)['model_settings']['max_input_tokens']==32000
    asyncio.run(coordinator.close())
