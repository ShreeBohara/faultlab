"""Full local tracing/readback seam with a fake remote; never sponsor acceptance."""
import asyncio
import json
import pytest
from app.config import Settings
from app.contracts.models import CampaignRequest,FaultSpec,canonical_json
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.lab.evidence import EvidenceGateway,EvidenceContext,WaitingEvidence,EvidenceDenied
from app.adapters.business_tools import WorldClient
from app.providers.runtime import RuntimeGeneration
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.tracing import TraceRecorder

pytestmark=pytest.mark.localhost_http


class PublicActorDouble:
    calls=0
    async def complete(self,messages,**kwargs):
        self.calls+=1;observations=json.loads(messages[-1]['content'])['observations']
        if not observations:action={'kind':'tool','tool':'update_order','arguments':{'desired_shipping':'express'}}
        elif not any(o['result']['tool']=='send_confirmation' for o in observations):action={'kind':'tool','tool':'send_confirmation','arguments':{}}
        else:action={'kind':'report','report':{'upgrade_outcome':'SUCCEEDED','notification_outcome':'SUCCEEDED','overall':'COMPLETED','evidence_ids':[o['evidence_id'] for o in observations],'next_action':{'kind':'NONE'}}}
        return RuntimeGeneration(canonical_json(action),'openai/gpt-oss-120b',100,20,None)


class RemoteTraceDouble:
    """Strict in-memory SDK transport; makes zero provider/network calls."""
    def __init__(self):self.calls={};self.ready=False;self.queries=0;self.mismatch=False
    async def request(self,command,payload,**kwargs):
        if command=='start_call':
            self.calls[payload['call_id']]={**payload};return {'id':payload['call_id']}
        if command=='finish_call':self.calls[payload['call_id']].update(payload);return {}
        if command=='flush':return {}
        if command=='get_calls':
            self.queries+=1
            if not self.ready:raise TimeoutError('Fixture outage')
            result=[]
            for id in payload['call_ids']:
                call=self.calls[id]
                result.append({'id':id,'project_id':'fixture-team/fixture-project','attributes':call['metadata'],'ended_at':call['ended_at'],'inputs':call['inputs'],'output':call['output'],'parent_id':call['parent_id'],'trace_id':call['parent_id'] or id})
            if self.mismatch:result[0]={**result[0],'attributes':{**result[0]['attributes'],'campaign_id':'foreign'}}
            return result
        raise AssertionError(command)


@pytest.mark.parametrize('lost_response',[False,True])
def test_decorated_http_episode_outage_then_exact_readback_without_rerun(tmp_path,simulator_server,lost_response):
    url,world_app=simulator_server
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab'),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(mode='baseline',task_text='Upgrade and confirm',order_id='order-trace',config_profile_id='live-v1'))
    async def execute():
        worker=RemoteTraceDouble();provider=PublicActorDouble()
        trace=TraceRecorder(worker,TelemetryOutbox(c.store))
        world=WorldClient(url,'integration-control');runner=EpisodeRunner(c.store,world,provider,trace=trace)
        gate=EvidenceGateway(c.store,'fixture-team/fixture-project',trace=trace,worker=worker)
        context=EvidenceContext(campaign.campaign_id,campaign.campaign_id,campaign.campaign_id)
        try:
            primitives=[{'kind':'F1','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'response_delay_ms':1500}}] if lost_response else []
            fault=FaultSpec.model_validate_json(canonical_json({'seed':3,'primitives':primitives}))
            trial=await runner.run(campaign,fault,c.policies.baseline())
            assert trial.outcome=='COMPLETED' and provider.calls==3
            recorded=c.store.get_record('episodes',trial.episode_id)
            expected_observations=3 if lost_response else 2
            assert len(worker.calls)==1+expected_observations # Root + actual business attempts, including lost-response retry.
            assert trial.usage.http_attempts==expected_observations
            assert trial.fault_triggered==lost_response
            with pytest.raises(WaitingEvidence):await gate.get(trial.episode_id,context)
            assert c.store.get_record('ingestions',trial.episode_id)['state']=='RETRYABLE_ERROR'
            assert provider.calls==3 and len(list(world_app.state.store.directory.glob('*.sqlite3')))==1
            worker.ready=True
            evidence=await gate.get(trial.episode_id,context)
            assert evidence.source=='weave_verified' # Strict transport-double result, NOT real W&B evidence.
            assert evidence.report.model_dump(mode='json')==recorded['report']
            assert len(evidence.observations)==len(evidence.child_call_ids)==expected_observations
            assert (await gate.get(trial.episode_id,context)).digest==evidence.digest
            with pytest.raises(EvidenceDenied):await gate.get(trial.episode_id,EvidenceContext('foreign',campaign.campaign_id,campaign.campaign_id))
            assert worker.queries==2 and provider.calls==3
            assert len(c.store.list_records('episodes'))==1
        finally:await world.close();await c.close()
    asyncio.run(execute())
