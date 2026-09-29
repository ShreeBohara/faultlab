import pytest
from app.config import Settings
from app.contracts.models import CampaignRequest,Episode,Provenance,content_hash,new_id,utc_now
from app.lab.coordinator import LabCoordinator
from app.lab.evidence import EvidenceGateway,EvidenceContext,EvidenceDenied,WaitingEvidence


def episode(c,campaign,*,purpose='reproduction',selector=None,context=None,study=None,origin=None,split=None):
    p=Provenance(campaign_id=campaign.campaign_id,episode_id=new_id('e'),origin=origin or ('prototype' if purpose=='discovery' else 'faultlab_evaluation'),split=split or ('promotion' if purpose=='promotion' else 'final_audit' if purpose=='portability' else 'development'),arm='B0',source_mode='live',experiment_purpose=purpose,trial_index=0,study_id=study or campaign.campaign_id,evidence_context_id=context or campaign.campaign_id,selector_id=selector,execution_epoch=campaign.execution_epoch)
    e=Episode(**p.model_dump(),world_id=new_id('w'),task_id=new_id('task'),scenario_hash=content_hash('s'),policy_hash=c.policies.baseline().policy_hash,policy_version='policy-v0',model=campaign.model,configuration_hash=campaign.configuration_hash,lifecycle='COMPLETED')
    c.store.put_record('episodes',e.episode_id,e)
    return e

def test_denies_hidden_foreign_selector_and_reference_before_read(tmp_path):
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline'))
    gate=EvidenceGateway(c.store,'project'); ctx=EvidenceContext(campaign.campaign_id,campaign.campaign_id,campaign.campaign_id)
    for kwargs in [{'purpose':'promotion'},{'purpose':'portability'},{'purpose':'selection_comparison','selector':'systematic','context':'systematic','study':'comparison'},{'purpose':'diagnostic_profile'},{'context':'foreign'}]:
        e=episode(c,campaign,**kwargs)
        with pytest.raises(EvidenceDenied): gate.authorize(e.episode_id,ctx)
    e=episode(c,campaign); assert gate.authorize(e.episode_id,ctx).episode_id==e.episode_id

def test_restart_interrupts_unfinished_and_preserves_accepted_pointer(tmp_path):
    from test_evaluation import setup
    from app.lab.promotion import commit_promotion
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    commit_promotion(c.store,c.policies,campaign,candidate,'ACCEPTED','Offline persistence fixture',evaluation_ref='test-evaluation')
    e=episode(c,campaign); e.lifecycle='RUNNING'; c.store.put_record('episodes',e.episode_id,e)
    c.transition(campaign.campaign_id,'RUNNING'); c.store.close()
    restarted=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    assert restarted.get(campaign.campaign_id).state=='STOPPED'
    assert restarted.store.get_record('episodes',e.episode_id)['lifecycle']=='INTERRUPTED'
    assert restarted.store.get_pointer(f'active-policy:{campaign.campaign_id}')==candidate.version
    assert restarted.policies.get(candidate.version).decision=='ACCEPTED'

import httpx
from app.contracts.models import FaultSpec
from app.simulator.main import create_app
from app.adapters.business_tools import WorldClient
from app.lab.runner import EpisodeRunner
from app.telemetry.tracing import TraceRecorder
from app.telemetry.outbox import TelemetryOutbox
from test_runner import HonestFixtureProvider

@pytest.fixture
def anyio_backend(): return 'asyncio'

class RemoteTraceDouble:
    def __init__(self): self.calls={}; self.reads=0
    async def request(self,operation,payload,**kwargs):
        if operation=='start_call':
            parent=payload.get('parent_id')
            self.calls[payload['call_id']]={'id':payload['call_id'],'project_id':'entity/project','attributes':payload['metadata'],'inputs':payload['inputs'],'parent_id':parent,'trace_id':self.calls[parent]['trace_id'] if parent in self.calls else payload['call_id'],'output':None,'ended_at':None}
            return {'id':payload['call_id']}
        if operation=='finish_call':
            self.calls[payload['call_id']]['output']=payload['output']; self.calls[payload['call_id']]['ended_at']='2026-09-12T00:00:00Z'; return {}
        if operation=='get_calls': self.reads+=1; return [self.calls[id] for id in payload['call_ids'] if id in self.calls]
        return {}

@pytest.mark.anyio
async def test_connected_trace_double_exact_readback_and_no_reexecution(tmp_path):
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test',settings=Settings())
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001')
    remote=RemoteTraceDouble(); trace=TraceRecorder(remote,TelemetryOutbox(c.store))
    runner=EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),HonestFixtureProvider(),trace=trace)
    trial=await runner.run(campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline())
    assert trial.outcome=='COMPLETED'
    gate=EvidenceGateway(c.store,'entity/project',trace=trace,worker=remote)
    bundle=await gate.get(trial.episode_id,EvidenceContext(campaign.campaign_id,campaign.campaign_id,campaign.campaign_id))
    assert bundle.source=='weave_verified' and len(bundle.observations)==2
    assert bundle.report==c.store.get_model('episodes',trial.episode_id,Episode).report
    before=len(c.store.list_records('tool_calls'))
    again=await gate.get(trial.episode_id,EvidenceContext(campaign.campaign_id,campaign.campaign_id,campaign.campaign_id))
    assert again.digest==bundle.digest and remote.reads==1 and len(c.store.list_records('tool_calls'))==before


@pytest.mark.anyio
@pytest.mark.parametrize('native', [False, True])
async def test_registered_regression_actor_has_one_root_and_verified_missing_report(tmp_path, native):
    from app.integrations.registry import AgentRegistry,freeze_target_configuration
    from app.providers.runtime import RuntimeGeneration
    class PollingProvider:
        calls=0
        async def complete(self,messages,**kwargs):
            self.calls+=1
            action={'name':'get_order','arguments':{}} if native else {'kind':'tool','tool':'get_order','arguments':{}}
            return RuntimeGeneration(__import__('json').dumps(action),'openai/gpt-oss-120b',input_tokens=10,output_tokens=10)
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    registry=AgentRegistry(c.store)
    configuration=c.store.get_record('configurations',campaign.configuration_hash)
    registration=registry.register_smolagents(freeze_target_configuration(configuration,campaign.model)) if native else registry.register_reference(configuration)
    campaign=campaign.model_copy(update={'configuration_hash':registration.configuration_hash})
    provider=PollingProvider(); actor=registry.reviewed_actor(registration.registration_id,provider,campaign.model)
    remote=RemoteTraceDouble(); trace=TraceRecorder(remote,TelemetryOutbox(c.store))
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test',settings=Settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001') as client:
        runner=EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),provider,trace=trace)
        trial=await runner.run(campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline(),purpose='reproduction',study_id='execution-test',evidence_context_id='execution-test',agent_registration_id=registration.registration_id,actor=actor)
    assert trial.lifecycle=='COMPLETED' and trial.outcome=='VIOLATION'
    assert provider.calls==trial.usage.actor_calls==8 and trial.usage.http_attempts==7
    calls=trace.episode_calls(trial.episode_id)
    roots=[call for call in calls if call['name']=='run_episode']
    assert len(roots)==1 and len(calls)==8
    root=roots[0]
    assert root['parent_id'] is None and root['output']['terminal_status']=='COMPLETED' and root['output']['report'] is None
    assert all(call['parent_id']==root['call_id'] for call in calls if call is not root)
    gate=EvidenceGateway(c.store,'entity/project',trace=trace,worker=remote)
    bundle=await gate.get(trial.episode_id,EvidenceContext(campaign.campaign_id,'execution-test','execution-test'))
    assert bundle.source=='weave_verified' and bundle.report is None and len(bundle.observations)==7
    assert any(not finding.passed for finding in bundle.findings)
    assert provider.calls==8


@pytest.mark.anyio
@pytest.mark.parametrize('remote_status,legacy,allowed', [
    ('COMPLETED', False, True),
    ('LAB_ERROR', False, False),
    ('INTERRUPTED', False, False),
    ('LAB_ERROR', True, True),
])
async def test_missing_actor_report_trace_and_verified_lifecycle(tmp_path, remote_status, legacy, allowed):
    from app.providers.runtime import RuntimeGeneration
    class MissingReport:
        async def complete(self, *args, **kwargs):
            return RuntimeGeneration('{}', 'openai/gpt-oss-120b', input_tokens=10, output_tokens=1)
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test',settings=Settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001') as client:
        remote=RemoteTraceDouble(); trace=TraceRecorder(remote,TelemetryOutbox(c.store))
        runner=EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),MissingReport(),trace=trace)
        trial=await runner.run(campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline())
    assert trial.lifecycle == 'COMPLETED' and trial.outcome == 'VIOLATION'
    root=trace.episode_calls(trial.episode_id)[0]
    assert root['output'] == {'terminal_status':'COMPLETED','report':None,'error_category':'ACTOR_REPORT_MISSING'}
    assert c.store.get_record('episodes',trial.episode_id)['report'] is None
    remote.calls[root['call_id']]['output']['terminal_status']=remote_status
    if legacy:
        saved=c.store.get_record('configurations',campaign.configuration_hash)
        historical={key:value for key,value in saved.items() if key not in {'algorithm_hash','runtime_hash','trace_contract_version'}}
        historical_hash=content_hash(historical)
        c.store.put_record('configurations',historical_hash,historical,immutable=True)
        e=c.store.get_model('episodes',trial.episode_id,Episode)
        e.configuration_hash=historical_hash
        c.store.put_record('episodes',e.episode_id,e)
    gate=EvidenceGateway(c.store,'entity/project',trace=trace,worker=remote)
    ctx=EvidenceContext(campaign.campaign_id,campaign.campaign_id,campaign.campaign_id)
    if allowed:
        bundle=await gate.get(trial.episode_id,ctx)
        assert bundle.source == 'weave_verified' and bundle.report is None
        assert any(not finding.passed for finding in bundle.findings)
        assert remote.calls[root['call_id']]['output']['terminal_status'] == remote_status
    else:
        with pytest.raises(EvidenceDenied,match='terminal classification'):
            await gate.get(trial.episode_id,ctx)
        assert c.store.get_record('evidence',trial.episode_id) is None
        assert c.store.get_record('ingestions',trial.episode_id)['error_code'] == 'TERMINAL_CLASSIFICATION_MISMATCH'


@pytest.mark.anyio
@pytest.mark.parametrize('external_cancel', [False, True])
async def test_episode_deadline_is_not_external_interruption(tmp_path, monkeypatch, external_cancel):
    import asyncio
    from app.contracts.models import EpisodeBudget
    from app.lab.budgets import EpisodeMeter
    from app.lab import runner as runner_module
    class ShortMeter(EpisodeMeter):
        def __init__(self, **kwargs):
            super().__init__(caps=EpisodeBudget(wall_seconds=1), **kwargs)
    monkeypatch.setattr(runner_module, 'EpisodeMeter', ShortMeter)
    entered = asyncio.Event()
    class PendingProvider:
        async def complete(self, *args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline',config_profile_id='live-v1'))
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test',settings=Settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001') as client:
        remote=RemoteTraceDouble(); trace=TraceRecorder(remote,TelemetryOutbox(c.store))
        runner=EpisodeRunner(c.store,WorldClient('http://127.0.0.1:8001','test',client=client),PendingProvider(),trace=trace)
        task=asyncio.create_task(runner.run(campaign,FaultSpec(seed=1,primitives=[]),c.policies.baseline()))
        await asyncio.wait_for(entered.wait(), timeout=2)
        if external_cancel:
            task.cancel()
        trial=await asyncio.wait_for(task, timeout=3)
    root=trace.episode_calls(trial.episode_id)[0]
    expected='INTERRUPTED' if external_cancel else 'COMPLETED'
    assert trial.lifecycle == root['output']['terminal_status'] == expected
    assert root['output']['report'] is None
    if external_cancel:
        assert trial.reason == 'TASK_CANCELLED'
    else:
        assert trial.outcome == 'VIOLATION'
        assert root['output']['error_category'] == 'EPISODE_DEADLINE_EXHAUSTED'
        gate=EvidenceGateway(c.store,'entity/project',trace=trace,worker=remote)
        bundle=await gate.get(trial.episode_id,EvidenceContext(campaign.campaign_id,campaign.campaign_id,campaign.campaign_id))
        assert bundle.source == 'weave_verified' and bundle.report is None
