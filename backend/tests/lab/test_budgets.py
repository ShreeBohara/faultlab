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


def test_role_specific_bounds_charge_the_model_actually_dispatched(tmp_path):
    store=LabStore(tmp_path/'lab.db')
    bounds={'actor':.001,'explorer':.01,'mechanic':.01}
    ledger=CampaignLedger(store,'c',dollar_bounds=bounds)
    ledger.consume_call(role='actor')
    ledger.consume_call(role='explorer')
    data=store.get_record('budgets','c')
    assert data['dollar_bounds']==bounds
    assert data['dollar_bound']==.01
    assert data['charged_dollar_upper_bound']==pytest.approx(.011)

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


def test_optional_retries_preserve_two_complete_reserved_episodes_and_protected_work(tmp_path):
    store=LabStore(tmp_path/'lab.db')
    # Sixteen required turns plus sixteen optional retries, with every protected
    # batch still reserved. All caps are exactly sufficient for this schedule.
    total=1064+32
    ledger=CampaignLedger(store,'c',CampaignBudget(model_calls=total,tokens=total*34000,dollars=total*.125),dollar_bound=.125)
    protected=store.get_record('budgets','c')['reservations']
    ledger.reserve('two_episodes',16)
    for episode in range(2):
        meter=EpisodeMeter(campaign=ledger,reservation='two_episodes')
        for turn in range(8):
            meter.model_call()
            remaining=16-(episode*8+turn+1)
            assert ledger.reservations['two_episodes']['calls']==remaining
            assert meter.transport_retry()
            assert ledger.reservations['two_episodes']=={'calls':remaining,'tokens':remaining*34000}
        assert meter.usage.actor_calls==8 and meter.usage.model_calls==16
    assert ledger.used_calls==32 and ledger.used_tokens==32*34000
    assert ledger.used_dollar_upper_bound==4
    assert all(ledger.reservations[name]==value for name,value in protected.items())
    saved=store.get_record('budgets','c')
    restored=CampaignLedger(store,'c')
    assert store.get_record('budgets','c')==saved
    assert restored.reservations==ledger.reservations
    assert not EpisodeMeter(campaign=restored).transport_retry()
    assert store.get_record('budgets','c')==saved
    store.close()


@pytest.mark.parametrize('limiting_cap',['calls','tokens','dollars'])
def test_retry_cannot_spend_reserved_turns_when_one_campaign_cap_has_no_spare(tmp_path,limiting_cap):
    total=1064+16
    caps=CampaignBudget(model_calls=total if limiting_cap=='calls' else 6000,
        tokens=total*34000 if limiting_cap=='tokens' else 204000000,
        dollars=total*.125 if limiting_cap=='dollars' else 500)
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c',caps,dollar_bound=.125)
    ledger.reserve('two_episodes',16)
    first=EpisodeMeter(campaign=ledger,reservation='two_episodes')
    first.model_call()
    saved=store.get_record('budgets','c')
    assert not first.transport_retry()
    assert store.get_record('budgets','c')==saved
    assert first.usage.actor_calls==first.usage.model_calls==1
    for _ in range(7): first.model_call()
    second=EpisodeMeter(campaign=ledger,reservation='two_episodes')
    for _ in range(8): second.model_call()
    assert ledger.used_calls==16 and ledger.reserved_calls==1064
    assert first.usage.actor_calls==second.usage.actor_calls==8
    store.close()


def test_retry_after_reload_preserves_historical_charges_caps_and_depleted_reservation(tmp_path):
    store=LabStore(tmp_path/'lab.db')
    old_caps=CampaignBudget(tokens=60000000,input_tokens_per_call=8000,output_tokens_per_call=2000)
    ledger=CampaignLedger(store,'old',old_caps,dollar_bound=.0077)
    ledger.reserve('batch',16)
    # Older runtime charged both initial turns and retries to this reservation.
    # Reload must not reconstruct, refund or top up those four saved requests.
    for _ in range(4): ledger.consume_call(reservation='batch')
    saved=store.get_record('budgets','old')
    restored=CampaignLedger(store,'old')
    assert store.get_record('budgets','old')==saved
    meter=EpisodeMeter(campaign=restored,reservation='batch')
    meter.model_call()
    before_retry=store.get_record('budgets','old')
    assert meter.transport_retry()
    current=store.get_record('budgets','old')
    assert current['reservations']==before_retry['reservations']
    assert current['caps']==saved['caps'] and current['dollar_bounds']==saved['dollar_bounds']
    assert current['used_calls']==6 and current['used_tokens']==60000
    assert current['charged_dollar_upper_bound']==pytest.approx(6*.0077)
    assert current['unknown_cost_calls']==current['unknown_token_calls']==6
    assert current['reservations']['batch']=={'calls':11,'tokens':110000}
    CampaignLedger(store,'old')
    assert store.get_record('budgets','old')==current
    store.close()
