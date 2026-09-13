"""Live-study plumbing exercised with a labeled local provider/Weave double."""
import asyncio,json
from dataclasses import replace
import httpx,pytest
from app.config import Settings
from app.contracts.models import CampaignRequest,canonical_json
from app.adapters.business_tools import WorldClient
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.lab.baseline_study import queue_baseline_study
from app.lab.storage import StoreConflict
from app.lab.evidence import EvidenceContext,EvidenceDenied,EvidenceGateway
from app.providers.runtime import RuntimeGeneration
from app.simulator.main import create_app
from app.telemetry.tracing import TraceRecorder
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.evaluations import EvaluationPublisher
from test_evidence import RemoteTraceDouble

@pytest.fixture
def anyio_backend(): return 'asyncio'

def settings(tmp_path):
    return Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b',wandb_api_key='local-test-only',wandb_entity='entity',wandb_project='project',faultlab_live_enabled=True,faultlab_confirmed_entity='entity',faultlab_pricing_model='openai/gpt-oss-120b',faultlab_input_dollars_per_million=.1,faultlab_output_dollars_per_million=.1,faultlab_pricing_verified=True)

class BaselineFixtureProvider:
    """Deterministic action fixture; this is never scientific model evidence."""
    def __init__(self): self.calls=0; self.first_calls=[]
    async def complete(self,messages,**kwargs):
        self.calls+=1
        task=json.loads(messages[1]['content'])['task']; history=json.loads(messages[-1]['content']); obs=history['observations']
        results=[row['result'] for row in obs]
        def receipt(service):
            matches=[r['data']['receipt'] for r in results if isinstance(r.get('data'),dict) and r['data'].get('service')==service and r['data'].get('receipt')]
            return matches[-1] if matches else None
        upgrade,notification=receipt('orders'),receipt('notifications')
        def tool(name,arguments={}): return {'kind':'tool','tool':name,'arguments':arguments}
        def report():
            if upgrade and upgrade['status']=='FAILED': us,ns,overall,nxt='FAILED','NOT_REQUIRED','CORRECTLY_REJECTED',{'kind':'NONE'}
            elif upgrade and notification: us,ns,overall,nxt='SUCCEEDED','SUCCEEDED','COMPLETED',{'kind':'NONE'}
            else:
                service='notifications' if upgrade else 'orders'; operation=task['notification_operation_id'] if upgrade else task['upgrade_operation_id']
                status=next((r['data']['status'] for r in reversed(results) if isinstance(r.get('data'),dict) and r['data'].get('service')==service),'NOT_STARTED')
                us,ns,overall='SUCCEEDED' if upgrade else status,status if upgrade else 'NOT_STARTED','SAFE_UNRESOLVED'
                nxt={'kind':'CHECK_EXISTING_NOTIFICATION' if upgrade else 'CHECK_EXISTING_UPGRADE','operation_id':operation}
            return {'kind':'report','report':{'upgrade_outcome':us,'notification_outcome':ns,'overall':overall,'evidence_ids':[row['evidence_id'] for row in obs],'next_action':nxt}}
        if not obs: self.first_calls.append(task['task_id']); action=tool('get_order')
        elif history['final_report_required']: action=report()
        elif not any(r['tool']=='update_order' for r in results): action=tool('update_order',{'desired_shipping':'express'})
        elif not upgrade: action=tool('get_operation_status',{'service':'orders'})
        elif upgrade['status']=='FAILED' or notification: action=report()
        elif not any(r['tool']=='send_confirmation' for r in results): action=tool('send_confirmation')
        elif results[-1]['tool']=='get_operation_status' and results[-1].get('status')=='UNKNOWN': action=tool('send_confirmation')
        else: action=tool('get_operation_status',{'service':'notifications'})
        return RuntimeGeneration(canonical_json(action),'openai/gpt-oss-120b',input_tokens=100,output_tokens=30,cost_usd=.0001)

class StudyRemoteDouble(RemoteTraceDouble):
    def __init__(self): super().__init__(); self.operations=[]
    async def request(self,operation,payload,**kwargs):
        self.operations.append(operation)
        if operation=='evaluation_summary': return {'verified':True,'id':payload['batch_id'],'url':'https://wandb.ai/entity/project/weave/evaluations/'+payload['batch_id']}
        return await super().request(operation,payload,**kwargs)

@pytest.mark.anyio
async def test_fixed_36_fresh_trials_real_runner_and_isolated_evidence(tmp_path):
    c=LabCoordinator(settings(tmp_path)); campaign=c.create(CampaignRequest(task_text='Upgrade and confirm',order_id='order-baseline',mode='baseline',config_profile_id='live-v1'))
    simulator=create_app(database_dir=tmp_path/'worlds',control_token='test')
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator),base_url='http://127.0.0.1:8001')
    provider=BaselineFixtureProvider(); remote=StudyRemoteDouble(); outbox=TelemetryOutbox(c.store); trace=TraceRecorder(remote,outbox)
    c.runner=EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),provider,trace=trace)
    c.evidence_gateway=EvidenceGateway(c.store,'entity/project',trace=trace,worker=remote)
    c.evaluation_publisher=EvaluationPublisher(remote,outbox)
    queued=await queue_baseline_study(c,campaign.campaign_id)
    assert queued['status']=='QUEUED' and provider.calls==0 and not c.store.list_records('episodes')
    assert c.ledgers[campaign.campaign_id].reserved_calls==1064+144
    assert [s['arm'] for s in queued['slots'][:4]]==['B0','B1','B1','B0']
    await c.tasks[queued['study_id']]
    result=c.store.get_record('baseline_studies',queued['study_id'])
    assert result['status']=='COMPLETED',result['reason']
    assert len(result['trials'])==36 and len({t['world_id'] for t in result['trials']})==36
    assert len(set(provider.first_calls))==18 and provider.calls==result['charged_model_calls']<=144
    assert result['by_arm']['B0']['counts']['valid']==18 and result['by_arm']['B1']['counts']['valid']==18
    assert result['by_arm']['B1']['usage']['model_calls']==0
    assert c.ledgers[campaign.campaign_id].reserved_calls==1064 and c.get(campaign.campaign_id).active_policy_version=='policy-v0'
    assert len(c.policies.list())==1 and c.active_id is None
    assert len(result['evidence'])==18 and set(result['evidence'].values())=={'weave_verified'}
    assert remote.operations[0]=='evaluation_init' and len(c.store.list_records('telemetry_predictions'))==36
    assert result['telemetry']['B0']['status']=='weave_verified' and result['telemetry']['B1']['status']=='local_only'
    episodes=c.store.list_records('episodes')
    assert {e['configuration_hash'] for e in episodes}=={campaign.configuration_hash}
    assert {e['study_id'] for e in episodes}=={queued['study_id']}
    b0=next(e for e in episodes if e['arm']=='B0')
    with pytest.raises(EvidenceDenied): c.evidence_gateway.authorize(b0['episode_id'],EvidenceContext(campaign.campaign_id,campaign.campaign_id,campaign.campaign_id))
    with pytest.raises(StoreConflict): await queue_baseline_study(c,campaign.campaign_id)
    await client.aclose(); await c.close()

@pytest.mark.anyio
async def test_explicit_gate_stop_and_no_implicit_dispatch(tmp_path):
    from app.main import create_app as backend_app
    c=LabCoordinator(settings(tmp_path)); campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    calls=[]
    async def forbidden(*args): calls.append('runner'); raise AssertionError('Stopped before dispatch')
    c._get_runner=forbidden
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app(coordinator=c)),base_url='http://127.0.0.1:8000')
    path=f'/api/campaigns/{campaign.campaign_id}/baseline-study'
    for body in ({},{'execute_live':False},{'execute_live':True,'unknown':'field'}): assert (await client.post(path,json=body)).status_code==422
    assert not c.store.list_records('baseline_studies') and not calls
    queued=await queue_baseline_study(c,campaign.campaign_id)
    await c.stop(campaign.campaign_id)
    await c.tasks[queued['study_id']]
    result=(await client.get('/api/baseline-studies/'+queued['study_id'])).json()
    assert result['status']=='INTERRUPTED' and not result['trial_ids'] and not calls
    assert c.ledgers[campaign.campaign_id].reserved_calls==1064
    with pytest.raises(StoreConflict): await queue_baseline_study(c,campaign.campaign_id)
    await client.aclose(); await c.close()

@pytest.mark.anyio
async def test_active_and_budget_admission_reject_before_study(tmp_path):
    c=LabCoordinator(settings(tmp_path)); campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    c.active_id='another-campaign'
    with pytest.raises(StoreConflict): await queue_baseline_study(c,campaign.campaign_id)
    assert not c.store.list_records('baseline_studies')
    c.active_id=None
    from app.lab.budgets import CampaignLedger,BudgetExhausted
    ledger=CampaignLedger(c.store,campaign.campaign_id,campaign.caps,dollar_bound=c.settings.model_call_dollar_bound); c.ledgers[campaign.campaign_id]=ledger
    ledger.reserve('other-complete-batch',campaign.caps.model_calls-1064-100)
    with pytest.raises(BudgetExhausted): await queue_baseline_study(c,campaign.campaign_id)
    assert c.active_id is None and not c.store.list_records('baseline_studies') and not c.store.list_records('episodes')
    await c.close()

@pytest.mark.anyio
async def test_initialization_failure_is_retained_and_releases_active_reservation(tmp_path):
    c=LabCoordinator(settings(tmp_path)); campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    async def unavailable(live): raise RuntimeError('Local initialization fixture failure')
    c._get_runner=unavailable
    queued=await queue_baseline_study(c,campaign.campaign_id); await c.tasks[queued['study_id']]
    saved=c.store.get_record('baseline_studies',queued['study_id'])
    assert saved['status']=='INCOMPLETE' and not saved['trial_ids']
    assert c.active_id is None and c.ledgers[campaign.campaign_id].reserved_calls==1064
    with pytest.raises(StoreConflict): await queue_baseline_study(c,campaign.campaign_id)
    await c.close()

@pytest.mark.anyio
@pytest.mark.parametrize('state',['STOPPED','ERROR'])
async def test_terminal_failure_campaign_cannot_admit_new_study(tmp_path,state):
    c=LabCoordinator(settings(tmp_path)); campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    c.transition(campaign.campaign_id,state)
    with pytest.raises(StoreConflict): await queue_baseline_study(c,campaign.campaign_id)
    assert not c.store.list_records('baseline_studies') and not c.tasks
    await c.close()

@pytest.mark.anyio
async def test_restart_marks_abandoned_study_interrupted_without_reexecution(tmp_path):
    configured=settings(tmp_path); c=LabCoordinator(configured)
    c.store.put_record('baseline_studies','pending-study',{'study_id':'pending-study','status':'RUNNING'})
    c.store.close(); restarted=LabCoordinator(configured)
    assert restarted.store.get_record('baseline_studies','pending-study')['status']=='INTERRUPTED'
    assert not restarted.tasks and not restarted.store.list_records('episodes')
    await restarted.close()
