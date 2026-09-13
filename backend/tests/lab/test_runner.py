import asyncio,json
import httpx,pytest
from app.config import Settings
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.adapters.business_tools import WorldClient
from app.simulator.main import create_app
from app.contracts.models import CampaignRequest,FaultSpec,canonical_json
from app.providers.runtime import RuntimeGeneration,RuntimeProviderError

@pytest.fixture
def anyio_backend(): return 'asyncio'

class HonestFixtureProvider:
    async def complete(self,messages,**kwargs):
        data=json.loads(messages[-1]['content']); obs=data['observations']
        if not obs: output={'kind':'tool','tool':'update_order','arguments':{'desired_shipping':'express'}}
        elif len(obs)==1: output={'kind':'tool','tool':'send_confirmation','arguments':{}}
        else: output={'kind':'report','report':{'upgrade_outcome':'SUCCEEDED','notification_outcome':'SUCCEEDED','overall':'COMPLETED','evidence_ids':[o['evidence_id'] for o in obs],'next_action':{'kind':'NONE'}}}
        return RuntimeGeneration(canonical_json(output),'openai/gpt-oss-120b',input_tokens=100,output_tokens=20)

@pytest.mark.anyio
async def test_fresh_actor_report_scored_unchanged_and_worlds_isolated(tmp_path):
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test')
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001')
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade and confirm',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    runner=EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),HonestFixtureProvider())
    trials=[await runner.run(campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline(),trial_index=i,source_mode='offline_fixture') for i in range(2)]
    assert all(t.outcome=='COMPLETED' and t.usage.actor_calls==3 for t in trials)
    assert trials[0].world_id!=trials[1].world_id and trials[0].episode_id!=trials[1].episode_id
    assert all(t.usage.input_tokens==300 for t in trials)
    e=c.store.get_record('episodes',trials[0].episode_id)
    assert e['report']['overall']=='COMPLETED' and len(e['report']['evidence_ids'])==2

@pytest.mark.anyio
async def test_provider_outage_is_lab_error_not_learning_failure(tmp_path):
    class Outage:
        async def complete(self,*args,**kwargs): raise RuntimeProviderError('outage')
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test')
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001')
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade and confirm',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    trial=await EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),Outage()).run(campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline(),source_mode='offline_fixture')
    assert trial.lifecycle=='LAB_ERROR' and trial.outcome=='LAB_ERROR'
    assert c.store.get_record('episodes',trial.episode_id)['report'] is None

@pytest.mark.anyio
async def test_provider_model_mismatch_is_lab_error_before_tool_dispatch(tmp_path):
    class WrongModel:
        async def complete(self,*args,**kwargs):
            return RuntimeGeneration(canonical_json({'kind':'tool','tool':'update_order','arguments':{'desired_shipping':'express'}}),'different-model',input_tokens=10,output_tokens=5,cost_usd=.01)
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test')
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001')
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    trial=await EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),WrongModel()).run(campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline(),source_mode='offline_fixture')
    assert trial.lifecycle=='LAB_ERROR' and trial.usage.http_attempts==0 and trial.usage.actor_calls==1
    assert trial.usage.input_tokens==10 and trial.usage.cost_dollars==.01
    assert not c.store.list_records('tool_calls')

@pytest.mark.anyio
async def test_empty_provider_response_retains_usage_and_machine_safe_failure(tmp_path):
    from app.lab.budgets import CampaignLedger
    class EmptyResponse:
        async def complete(self,*args,**kwargs):
            raise RuntimeProviderError('PRIVATE RESPONSE MUST NOT BE STORED',code='EMPTY_FINAL_RESPONSE',error_class='ValueError',finish_reason='length',generation=RuntimeGeneration('','openai/gpt-oss-120b',input_tokens=123,output_tokens=2000))
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test')
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001')
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    ledger=CampaignLedger(c.store,campaign.campaign_id)
    trial=await EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),EmptyResponse()).run(campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline(),source_mode='offline_fixture',ledger=ledger)
    assert trial.lifecycle=='LAB_ERROR' and trial.reason=='EMPTY_FINAL_RESPONSE'
    assert trial.usage.actor_calls==1 and trial.usage.input_tokens==123 and trial.usage.output_tokens==2000 and trial.usage.http_attempts==0
    assert ledger.used_calls==1 and ledger.measured_input==123 and ledger.measured_output==2000 and ledger.used_tokens==10000
    assert c.store.get_record('episodes',trial.episode_id)['report'] is None
    failures=c.store.list_records('provider_failures')
    assert len(failures)==1 and failures[0]['episode_id']==trial.episode_id and failures[0]['diagnostics']['finish_reason']=='length'
    assert 'PRIVATE RESPONSE' not in json.dumps(failures)
