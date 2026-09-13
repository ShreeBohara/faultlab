"""Admission and telemetry integration checks, with explicit local doubles only."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
import pytest
from app.config import Settings
from app.contracts.models import CampaignRequest,FaultSpec
from app.lab.coordinator import LabCoordinator
from app.lab.storage import StoreConflict
from app.lab.tracing import execute_phase,trace_metadata
from test_evidence import episode,RemoteTraceDouble
from app.telemetry.tracing import TraceRecorder
from app.telemetry.outbox import TelemetryOutbox

@pytest.fixture
def anyio_backend(): return 'asyncio'

@pytest.mark.anyio
@pytest.mark.parametrize('change',[{'wandb_model':'different-model'},{'faultlab_model_call_cap':1500},{'faultlab_token_cap':15000000},{'faultlab_dollar_cap':50.0}])
async def test_restart_changed_frozen_admission_rejects_before_any_dispatch(tmp_path,monkeypatch,change):
    original=Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b')
    c=LabCoordinator(original)
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    c.store.close()
    restarted=LabCoordinator(replace(original,**change))
    monkeypatch.setattr(Settings,'require_live',lambda self:None)
    async def forbidden(*args): raise AssertionError('Provider/world initialization must not happen')
    restarted._get_runner=forbidden
    with pytest.raises(StoreConflict): await restarted.start(campaign.campaign_id)
    assert restarted.active_id is None and not restarted.tasks and not restarted.store.list_records('episodes')
    await restarted.close()

@pytest.mark.anyio
async def test_phase_spans_keep_episode_roots_and_tool_parents(tmp_path):
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    remote=RemoteTraceDouble(); trace=TraceRecorder(remote,TelemetryOutbox(c.store))
    metadata=trace_metadata(campaign,'episode-test',c.policies.baseline(),c.store.get_record('configurations',campaign.configuration_hash))
    async def operation():
        async with trace.span('run_episode',metadata,{}) as root:
            async with trace.span('get_order',metadata,{}) as child: child.set_output({'observation':{}})
            root.set_output({'terminal_status':'COMPLETED','report':None})
        return 'original'
    assert await execute_phase(trace,'reproduce_counterexample',metadata,{},operation)=='original'
    calls=c.store.list_records('trace_calls'); root=next(r for r in calls if r['name']=='run_episode')
    assert root['parent_id'] is None
    assert next(r for r in calls if r['name']=='get_order')['parent_id']==root['call_id']
    await c.close()

@pytest.mark.anyio
async def test_retry_is_immediate_isolated_and_records_each_episode(tmp_path):
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline'))
    good=episode(c,campaign); bad=episode(c,campaign,purpose='promotion')
    active_gateway=object(); c.evidence_gateway=active_gateway; c.active_id='other-campaign'
    entered=asyncio.Event(); release=asyncio.Event(); calls=[]
    class Worker:
        async def start(self): entered.set(); await release.wait()
        async def close(self): calls.append('close')
    class Gateway:
        async def retry(self,id): calls.append(id); return SimpleNamespace(source='weave_verified')
    async def services(): return Worker(),Gateway(),object()
    c._evidence_retry_services=services
    response=await asyncio.wait_for(c.retry_evidence(campaign.campaign_id,[good.episode_id,bad.episode_id]),.1)
    assert response['status']=='QUEUED'
    await entered.wait()
    assert (await c.retry_evidence(campaign.campaign_id,[good.episode_id]))['request_id']==response['request_id']
    assert c.evidence_gateway is active_gateway and c.active_id=='other-campaign'
    release.set(); await c.tasks[response['request_id']]
    result=c.store.get_record('evidence_retries',response['request_id'])
    assert result['outcomes'][good.episode_id]['status']=='VERIFIED'
    assert result['outcomes'][bad.episode_id]['status']=='SKIPPED_INELIGIBLE'
    assert calls==[good.episode_id,'close'] and not c.store.list_records('tool_calls')
    c.active_id=None; await c.close()

@pytest.mark.anyio
async def test_restart_abandons_pending_evidence_jobs(tmp_path):
    settings=Settings(faultlab_artifact_dir=str(tmp_path)); c=LabCoordinator(settings)
    c.store.put_record('evidence_retries','abandoned',{'request_id':'abandoned','status':'RUNNING'})
    c.store.close(); restarted=LabCoordinator(settings)
    assert restarted.store.get_record('evidence_retries','abandoned')['status']=='INTERRUPTED'
    await restarted.close()

@pytest.mark.anyio
async def test_frozen_audit_initializes_evaluation_before_fresh_episodes(tmp_path):
    from app.lab.audit import queue_audit
    from app.referee.manifests import load_manifest
    from app.lab.promotion import commit_promotion
    from test_evaluation import setup,FakeRunner
    c,campaign,ledger,candidate,_=setup(tmp_path)
    commit_promotion(c.store,c.policies,campaign,candidate,'ACCEPTED','Offline audit binding fixture',evaluation_ref='fixture')
    campaign=c.get(campaign.campaign_id)
    manifest=load_manifest('final-audit')
    c.store.put_record('audit_freezes',campaign.campaign_id,{'policy_hash':candidate.policy_hash,'configuration_hash':campaign.configuration_hash,'manifest_hash':manifest['manifest_hash']})
    events=[]
    class Publisher:
        async def begin(self,id,metadata,**kwargs):
            assert metadata['split']=='final_audit' and kwargs['frozen'] and len(kwargs['expected_episode_ids'])==72
            events.append('begin'); return self
        async def record_prediction(self,*args,**kwargs): events.append('prediction')
        async def finish(self,*args): events.append('finish')
    class Runner(FakeRunner):
        async def run(self,*args,**kwargs):
            events.append('actor'); assert events[0]=='begin'
            return await super().run(*args,**kwargs)
    c.runner=Runner('tie'); c.runner.trace=SimpleNamespace(frozen=False); c.evaluation_publisher=Publisher()
    response=await queue_audit(c,campaign,candidate)
    await c.tasks[response['batch_id']]
    assert c.runner.trace.frozen is True and events.count('actor')==72 and events[-1]=='finish'
    assert c.store.get_record('audit_results',response['batch_id'])['status']=='COMPLETED'
    await c.close()

@pytest.mark.anyio
async def test_retry_readback_unlocks_aria_publication_without_reexecution(tmp_path):
    from app.telemetry.aria_bridge import AriaBridge
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_entity='entity',wandb_project='project'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline'))
    e=episode(c,campaign); c.transition(campaign.campaign_id,'COMPLETED')
    calls=[]
    class Worker:
        async def start(self): pass
        async def close(self): pass
        async def request(self,operation,payload,**kwargs):
            calls.append(operation)
            assert operation=='campaign_bridge'
            return {'run_id':payload['run_id'],'url':'https://wandb.ai/entity/project/runs/'+payload['run_id']}
    worker=Worker(); original_bridge=AriaBridge(worker,TelemetryOutbox(c.store),project='entity/project')
    c.store.put_record('aria_setup','entity/project',{'automation_id':'automation-local-fixture'},immutable=True)
    await c._publish_completion(campaign.campaign_id,bridge=original_bridge)
    assert not calls and not c.store.get_record('aria_publish_intents',campaign.campaign_id)
    sentinel_gateway=object(); sentinel_bridge=object(); c.evidence_gateway=sentinel_gateway; c.aria_bridge=sentinel_bridge
    class Gateway:
        async def retry(self,id):
            c.store.put_record('evidence',id,{'episode_id':id,'source':'weave_verified','root_call_id':'call-fixture','findings':[]})
            return SimpleNamespace(source='weave_verified')
    async def services(): return worker,Gateway(),object()
    c._evidence_retry_services=services
    request=await c.retry_evidence(campaign.campaign_id,[e.episode_id]); await c.tasks[request['request_id']]
    result=c.store.get_record('evidence_retries',request['request_id'])
    assert result['aria']['state']=='awaiting_aria_verification' and calls==['campaign_bridge']
    assert c.evidence_gateway is sentinel_gateway and c.aria_bridge is sentinel_bridge
    assert not c.store.list_records('tool_calls') and not c.store.list_records('budgets')
    # Existing successful or uncertain publication intents remain sponsor-owned;
    # repeating an evidence retry never sends another Finished campaign request.
    again=await c.retry_evidence(campaign.campaign_id,[e.episode_id]); await c.tasks[again['request_id']]
    assert calls==['campaign_bridge']
    await c.close()


@pytest.mark.anyio
async def test_verified_weave_does_not_publish_finished_campaign_without_aria_setup(tmp_path):
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_entity='entity',wandb_project='project'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline'))
    e=episode(c,campaign); c.transition(campaign.campaign_id,'COMPLETED')
    verified={'episode_id':e.episode_id,'source':'weave_verified','root_call_id':'actual-local-fixture-call','findings':[]}
    c.store.put_record('evidence',e.episode_id,verified)
    calls=[]
    class Bridge:
        async def publish_campaign(self,*args,**kwargs):
            calls.append('network')
            raise AssertionError('Aria remains explicitly pending')
    existing_gateway=object(); c.evidence_gateway=existing_gateway
    result=await c._publish_completion(campaign.campaign_id,bridge=Bridge())
    assert result['state']=='awaiting_aria_setup' and c.get(campaign.campaign_id).aria_status=='PENDING'
    assert not calls and not c.store.list_records('aria_publish_intents') and not c.store.list_records('aria_runs')
    assert c.store.get_record('evidence',e.episode_id)==verified and c.evidence_gateway is existing_gateway
    assert c.get(campaign.campaign_id).active_policy_version=='policy-v0'
    await c.close()
