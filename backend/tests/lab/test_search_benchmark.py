import json
import pytest
from app.providers.runtime import RuntimeGeneration
from app.lab.search_benchmark import SearchBenchmark
from test_evaluation import setup as evaluation_setup
from dataclasses import replace
from app.contracts.models import CampaignRequest
from app.lab.budgets import CampaignLedger

def setup(tmp_path):
    c,_,_,candidate,runner=evaluation_setup(tmp_path)
    c.settings=replace(c.settings,wandb_model="openai/gpt-oss-120b")
    campaign=c.create(CampaignRequest(task_text="Upgrade and confirm",order_id="order-search",mode="baseline",config_profile_id="live-v1"))
    return c,campaign,CampaignLedger(c.store,campaign.campaign_id),candidate,runner

@pytest.fixture
def anyio_backend(): return 'asyncio'

class SelectorProvider:
    def __init__(self,model="openai/gpt-oss-120b"): self.contexts=[]; self.model=model
    async def complete(self,messages,**kwargs):
        ctx=json.loads(messages[-1]['content']); self.contexts.append(ctx); index=ctx['selection_index']
        return RuntimeGeneration(json.dumps({'fault_spec':{'seed':1000+index,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':index+1,'terminal_status':'SUCCEEDED','failure_code':None}}]},'hypothesis':'Offline study fixture'}),self.model,input_tokens=30,output_tokens=10,cost_usd=.25)

class Gateway:
    def __init__(self): self.requests=[]
    async def get(self,episode_id,context): self.requests.append((episode_id,context)); return None

@pytest.mark.anyio
async def test_equal_slots_fresh_trials_and_separate_selector_contexts(tmp_path):
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    runner.provider=SelectorProvider(campaign.model); gateway=Gateway()
    result=await SearchBenchmark(c.store,runner,ledger,evidence_gateway=gateway).run(campaign,c.policies.baseline())
    assert result.status=='COMPLETED' and len(result.trial_ids)==48
    assert len({kwargs['evidence_context_id'] for _,_,_,kwargs in runner.calls})==2
    assert len(runner.provider.contexts)==8 and ledger.used_calls==8
    assert all(ctx['selector_id']=='explorer' and all(t['selector']=='explorer' for t in ctx['own_preceding_trials']) for ctx in runner.provider.contexts)
    assert ledger.reserved_calls==672
    assert len(c.store.get_record('search_results',result.comparison_id)['slots'])==16

@pytest.mark.anyio
async def test_unverified_selector_history_cannot_adapt(tmp_path):
    c,campaign,ledger,candidate,runner=setup(tmp_path); runner.provider=SelectorProvider(campaign.model)
    result=await SearchBenchmark(c.store,runner,ledger).run(campaign,c.policies.baseline())
    assert result.status=='INCOMPLETE' and len(runner.provider.contexts)==1

@pytest.mark.anyio
async def test_selector_study_excludes_prior_usage_and_counts_selection_cost(tmp_path):
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    ledger.consume_call(); ledger.reconcile(RuntimeGeneration('earlier','m',input_tokens=100,output_tokens=50,cost_usd=3.0))
    runner.provider=SelectorProvider(campaign.model)
    result=await SearchBenchmark(c.store,runner,ledger,evidence_gateway=Gateway()).run(campaign,c.policies.baseline())
    assert result.usage.model_calls==8 and result.usage.input_tokens==240 and result.usage.output_tokens==80
    assert result.usage.cost_dollars==2.0
    usage=c.store.get_record('search_results',result.comparison_id)
    assert usage['by_selector']['explorer']['total']['known_cost_dollars']==2.0
    assert usage['by_selector']['systematic']['total']['model_calls']==0
    assert len(usage['by_selector']['explorer']['selection_records'])==8
    assert ledger.used_calls==9 and ledger.used_cost==5.0
