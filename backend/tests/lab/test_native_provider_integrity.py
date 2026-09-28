"""Native transport failures are lab failures; accounting survives native wrapping."""
import pytest

from app.contracts.models import FaultSpec, canonical_json
from app.lab.budgets import CampaignLedger, BudgetExhausted, StopRequested
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError
from test_planned_agent_execution import MODEL, NativeReferenceInputs, planned_campaign, runtime


@pytest.fixture
def anyio_backend(): return 'asyncio'


async def execute(tmp_path,provider):
    c=await runtime(tmp_path,provider=provider)
    campaign=planned_campaign(c)
    ledger=CampaignLedger(c.store,campaign.campaign_id,campaign.caps,dollar_bounds=c.settings.model_call_dollar_bounds)
    trial=await c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),ledger=ledger)
    return c,campaign,trial,ledger


@pytest.mark.anyio
async def test_wrong_model_retains_one_charge_and_becomes_lab_error_before_dispatch(tmp_path):
    class WrongModel:
        calls=0
        async def complete(self,*args,**kwargs):
            self.calls+=1
            return RuntimeGeneration('{"name":"update_order","arguments":{"desired_shipping":"express"}}',
                                     'unexpected-provider-model',123,17,.04)
    provider=WrongModel()
    c,campaign,trial,ledger=await execute(tmp_path,provider)
    try:
        assert provider.calls==trial.usage.actor_calls==trial.usage.model_calls==ledger.used_calls==1
        assert trial.lifecycle==trial.outcome=='LAB_ERROR' and trial.reason=='PROVIDER_ERROR'
        assert trial.usage.http_attempts==0 and trial.usage.input_tokens==123 and trial.usage.output_tokens==17
        assert trial.usage.cost_dollars==ledger.used_cost==.04
        assert ledger.measured_input==123 and ledger.measured_output==17
        assert ledger.unknown_cost_calls==ledger.unknown_token_calls==0
        assert not c.store.list_records('tool_calls')
        failure,=c.store.list_records('provider_failures')
        assert failure['episode_id']==trial.episode_id and failure['diagnostics']['code']=='PROVIDER_ERROR'
        assert failure['diagnostics']['input_tokens']==123
        snapshot=c.store.get_record('private_snapshots',trial.episode_id)['horizon']
        assert snapshot['orders'][0]['applied_shipping']=='standard' and snapshot['notifications']==[]
    finally: await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('with_generation',[True,False])
async def test_provider_error_never_rerolls_and_accounts_error_generation_once(tmp_path,with_generation):
    class Failure:
        calls=0
        async def complete(self,*args,**kwargs):
            self.calls+=1
            raise RuntimeProviderError('SECRET RAW ERROR MUST NOT BE SAVED',code='EMPTY_FINAL_RESPONSE',
                finish_reason='length',generation=RuntimeGeneration('PRIVATE RAW CONTENT',MODEL,31,2000,.07) if with_generation else None)
    provider=Failure()
    c,campaign,trial,ledger=await execute(tmp_path,provider)
    try:
        assert provider.calls==trial.usage.model_calls==ledger.used_calls==1
        assert trial.lifecycle==trial.outcome=='LAB_ERROR' and trial.reason=='EMPTY_FINAL_RESPONSE'
        assert trial.usage.http_attempts==0 and c.store.get_record('episodes',trial.episode_id)['report'] is None
        failure,=c.store.list_records('provider_failures')
        assert failure['diagnostics']['finish_reason']=='length'
        if with_generation:
            assert trial.usage.input_tokens==ledger.measured_input==31
            assert trial.usage.output_tokens==ledger.measured_output==2000
            assert trial.usage.cost_dollars==ledger.used_cost==.07 and ledger.unknown_cost_calls==0
        else:
            assert trial.usage.cost_dollars is None and ledger.unknown_cost_calls==1
            assert trial.usage.input_tokens==0 and ledger.unknown_token_calls==1
        dumped=' '.join(row[0] for row in c.store.db.execute('SELECT payload FROM records'))
        assert 'SECRET RAW ERROR' not in dumped and 'PRIVATE RAW CONTENT' not in dumped
    finally: await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('costs',[[.1,None,.2,.3],[None,.1,.2,.3],[.1,.2,.3,None],[.1,.2,.3,.4]])
async def test_unknown_native_cost_stays_unknown_across_later_generations(tmp_path,costs):
    class Costs(NativeReferenceInputs):
        async def complete(self,*args,**kwargs):
            output=await super().complete(*args,**kwargs)
            return RuntimeGeneration(output.content,output.model_id,100,20,costs[self.calls['actor']-1])
    c,campaign,trial,ledger=await execute(tmp_path,Costs('accepted'))
    try:
        assert trial.outcome=='COMPLETED' and trial.usage.actor_calls==ledger.used_calls==4
        assert trial.usage.input_tokens==ledger.measured_input==400
        assert trial.usage.output_tokens==ledger.measured_output==80
        assert ledger.used_cost==pytest.approx(sum(cost for cost in costs if cost is not None))
        assert ledger.unknown_cost_calls==sum(cost is None for cost in costs)
        if None in costs:
            assert trial.usage.cost_dollars is None
            assert c.store.get_record('budgets',campaign.campaign_id)['actual_cost_dollars'] is None
        else: assert trial.usage.cost_dollars==pytest.approx(sum(costs))
    finally: await c.close()


@pytest.mark.anyio
async def test_native_returned_fallback_cannot_hide_fatal_provider_error_or_retry_dispatch(tmp_path,monkeypatch):
    # Fault injection substitutes only native exception handling: even a library
    # which catches the error and returns a report must not permit a second call.
    class RecoveringNative:
        def __init__(self,bridge): self.bridge=bridge
        def run(self,*args,**kwargs):
            for _ in range(2):
                try: self.bridge.call(self.bridge.generate([],[]))
                except Exception: pass
            try: self.bridge.call(self.bridge.dispatch('update_order',{'desired_shipping':'express'}))
            except Exception: pass
            return {'upgrade_outcome':'SUCCEEDED','notification_outcome':'SUCCEEDED','overall':'COMPLETED',
                    'evidence_ids':['invented'],'next_action':{'kind':'NONE'}}
    monkeypatch.setattr('app.integrations.external_agent._native_agent',lambda bridge,model:RecoveringNative(bridge))
    class Failure:
        calls=0
        async def complete(self,*args,**kwargs):
            self.calls+=1
            raise RuntimeProviderError('No retry',code='HTTP_ERROR',http_status=503,
                                       generation=RuntimeGeneration('',MODEL,51,7,.02))
    provider=Failure()
    c,campaign,trial,ledger=await execute(tmp_path,provider)
    try:
        assert provider.calls==ledger.used_calls==1 and trial.usage.input_tokens==ledger.measured_input==51
        assert trial.lifecycle==trial.outcome=='LAB_ERROR' and trial.reason=='HTTP_ERROR'
        assert trial.usage.http_attempts==0 and not c.store.list_records('tool_calls')
        assert c.store.get_record('episodes',trial.episode_id)['report'] is None
        assert len(c.store.list_records('provider_failures'))==1
    finally: await c.close()


@pytest.mark.anyio
async def test_native_malformed_model_answer_keeps_ordinary_native_retry_semantics(tmp_path):
    class Malformed:
        calls=0
        async def complete(self,*args,**kwargs):
            self.calls+=1
            value='not json' if self.calls==1 else canonical_json({'name':'final_answer','arguments':{'answer':{
                'upgrade_outcome':'NOT_STARTED','notification_outcome':'NOT_STARTED','overall':'SAFE_UNRESOLVED',
                'evidence_ids':[],'next_action':{'kind':'ESCALATE'}}}})
            return RuntimeGeneration(value,MODEL,10,3,0)
    provider=Malformed()
    c,campaign,trial,ledger=await execute(tmp_path,provider)
    try:
        assert provider.calls==ledger.used_calls==2
        assert trial.lifecycle=='COMPLETED' and trial.outcome=='SAFE_UNRESOLVED'
        assert c.store.list_records('provider_failures')==[]
    finally: await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('error',[StopRequested,BudgetExhausted])
async def test_native_wrapping_preserves_stop_and_budget_classification(tmp_path,error):
    class Boundary:
        calls=0
        async def complete(self,*args,**kwargs):
            self.calls+=1
            raise error()
    provider=Boundary()
    c,campaign,trial,ledger=await execute(tmp_path,provider)
    try:
        assert provider.calls==ledger.used_calls==1
        assert trial.lifecycle==('INTERRUPTED' if error is StopRequested else 'COMPLETED')
        assert trial.outcome!='LAB_ERROR'
        assert c.store.list_records('provider_failures')==[]
    finally: await c.close()


@pytest.mark.anyio
async def test_native_cancelled_pending_call_keeps_cost_unknown_and_prior_effects(tmp_path):
    import asyncio
    class Pending:
        calls=0
        started=None
        async def complete(self,*args,**kwargs):
            self.calls+=1
            if self.calls==1:
                return RuntimeGeneration('{"name":"update_order","arguments":{"desired_shipping":"express"}}',MODEL,13,7,.03)
            self.started.set()
            await asyncio.Future()
    provider=Pending(); provider.started=asyncio.Event()
    c=await runtime(tmp_path,provider=provider)
    campaign=planned_campaign(c)
    ledger=CampaignLedger(c.store,campaign.campaign_id,campaign.caps,dollar_bounds=c.settings.model_call_dollar_bounds)
    try:
        task=asyncio.create_task(c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),ledger=ledger))
        await asyncio.wait_for(provider.started.wait(),timeout=5)
        task.cancel()
        trial=await task
        assert trial.lifecycle=='INTERRUPTED'
        assert provider.calls==ledger.used_calls==trial.usage.model_calls==2
        assert ledger.used_cost==.03 and ledger.unknown_cost_calls==1
        assert trial.usage.cost_dollars is None
        assert trial.usage.input_tokens==13 and trial.usage.output_tokens==7
        snapshot=c.store.get_record('private_snapshots',trial.episode_id)['horizon']
        assert snapshot['orders'][0]['applied_shipping']=='express' and snapshot['notifications']==[]
    finally: await c.close()
