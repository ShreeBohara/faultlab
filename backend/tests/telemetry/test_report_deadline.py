"""A returned report ends Actor work, independently of trace delivery latency."""
import asyncio
import time

import httpx
import pytest

from app.adapters.business_tools import WorldClient
from app.adapters.decorator import track_faultlab
from app.agents.reference import ReferenceActor
from app.agents.actor import ActorReportError
from app.config import Settings
from app.contracts.models import CampaignRequest, FaultSpec, TaskReport
from app.lab.budgets import EpisodeMeter
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.providers.runtime import RuntimeProviderError
from app.simulator.main import create_app
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.tracing import TraceRecorder


@pytest.fixture
def anyio_backend(): return 'asyncio'


class FinalizationWorker:
    def __init__(self, mode):
        self.mode=mode
        self.finishing=asyncio.Event()

    async def request(self, command, payload, **kwargs):
        if command=='start_call': return {'id':payload['call_id']}
        if command=='finish_call':
            self.finishing.set()
            if self.mode=='slow': await asyncio.sleep(.2)
            elif self.mode=='cancel': await asyncio.Event().wait()
        return {}


async def setup(tmp_path, monkeypatch, mode, behavior='timely', arm='B0', decorated=True, reference=False, native=False):
    class ShortMeter(EpisodeMeter):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.caps=self.caps.model_copy(update={'wall_seconds':.1})
    monkeypatch.setattr('app.lab.runner.EpisodeMeter',ShortMeter)
    sim=create_app(database_dir=tmp_path/'worlds',control_token='test',settings=Settings())
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001')
    coordinator=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab')))
    campaign=coordinator.create(CampaignRequest(task_text='Upgrade and confirm',order_id='order-1',mode='baseline'))
    worker=FinalizationWorker(mode)
    trace=TraceRecorder(worker,TelemetryOutbox(coordinator.store))
    original=TaskReport(upgrade_outcome='NOT_STARTED',notification_outcome='NOT_STARTED',overall='SAFE_UNRESOLVED',evidence_ids=[],next_action={'kind':'ESCALATE'})
    calls=[]
    @track_faultlab()
    async def actor(task,context):
        calls.append(context)
        if behavior=='timeout': await asyncio.Event().wait()
        if behavior=='late': time.sleep(.12)
        if behavior=='report_error': raise ActorReportError('No final actor report')
        if behavior=='provider_error': raise RuntimeProviderError('Provider unavailable')
        context.broker.journal.store.append_event(context.provenance.episode_id,type='report_submitted',payload={'report':original.model_dump(mode='json')})
        return original
    chosen=ReferenceActor() if reference else actor if decorated else actor.__wrapped__
    if native:
        from app.integrations.external_agent import SmolagentsActor
        async def native_run(self,task,context):
            return await actor.__wrapped__(task,context)
        monkeypatch.setattr(SmolagentsActor,'_run',native_run)
        chosen=SmolagentsActor(model_id=campaign.model)
    runner=EpisodeRunner(coordinator.store,WorldClient('http://127.0.0.1:8001','test',client=client),trace=None if reference else trace)
    async def run():
        return await runner.run(campaign,FaultSpec(seed=1,primitives=[]),coordinator.policies.baseline(),purpose='reproduction',arm=arm,actor=chosen)
    return coordinator,client,worker,original,calls,run


@pytest.mark.anyio
@pytest.mark.parametrize('arm',['B0','L'])
@pytest.mark.parametrize('native',[False,True])
async def test_timely_original_report_survives_slow_trace_finalization(tmp_path,monkeypatch,arm,native):
    c,client,worker,original,calls,run=await setup(tmp_path,monkeypatch,'slow',arm=arm,native=native)
    trial=await run()
    episode=c.store.get_record('episodes',trial.episode_id)
    assert episode['report']==original.model_dump(mode='json')
    assert episode['reason'] is None
    assert trial.lifecycle=='COMPLETED' and trial.outcome=='SAFE_UNRESOLVED'
    assert trial.usage.wall_seconds<.1 and len(calls)==1
    assert c.store.list_records('trace_calls')[0]['output']['report']==episode['report']
    await client.aclose(); await c.close()


@pytest.mark.anyio
async def test_actual_actor_timeout_has_no_invented_report(tmp_path,monkeypatch):
    c,client,worker,original,calls,run=await setup(tmp_path,monkeypatch,'instant',behavior='timeout')
    trial=await run(); episode=c.store.get_record('episodes',trial.episode_id)
    assert episode['report'] is None and trial.outcome=='VIOLATION'
    assert 'deadline' in episode['reason'].lower()
    assert c.store.list_records('trace_calls')[0]['output']['error_category']=='EPISODE_DEADLINE_EXHAUSTED'
    await client.aclose(); await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('decorated',[True,False])
async def test_late_actor_return_does_not_extend_work_deadline(tmp_path,monkeypatch,decorated):
    c,client,worker,original,calls,run=await setup(tmp_path,monkeypatch,'instant',behavior='late',decorated=decorated)
    trial=await run(); episode=c.store.get_record('episodes',trial.episode_id)
    assert episode['report'] is None and trial.outcome=='VIOLATION'
    assert trial.usage.wall_seconds>=.1
    assert 'limit' in episode['reason'].lower() or 'deadline' in episode['reason'].lower()
    await client.aclose(); await c.close()


@pytest.mark.anyio
async def test_trace_cleanup_is_bounded_after_timely_report(tmp_path,monkeypatch):
    monkeypatch.setattr('app.telemetry.tracing.TRACE_FINISH_TIMEOUT_SECONDS',.02)
    c,client,worker,original,calls,run=await setup(tmp_path,monkeypatch,'cancel')
    trial=await asyncio.wait_for(run(),timeout=1)
    episode=c.store.get_record('episodes',trial.episode_id)
    assert episode['report']==original.model_dump(mode='json') and episode['reason'] is None
    assert trial.lifecycle=='COMPLETED' and trial.usage.wall_seconds<.1
    jobs=c.store.list_records('telemetry_outbox')
    assert len(jobs)==1 and jobs[0]['payload']['output']['terminal_status']=='COMPLETED'
    await client.aclose(); await c.close()


@pytest.mark.anyio
async def test_untracked_reference_report_preserves_work_and_result(tmp_path,monkeypatch):
    c,client,worker,original,calls,run=await setup(tmp_path,monkeypatch,'instant',arm='B1',reference=True)
    trial=await run(); episode=c.store.get_record('episodes',trial.episode_id)
    assert episode['report']['overall']=='COMPLETED' and episode['reason'] is None
    assert trial.lifecycle=='COMPLETED' and trial.outcome=='COMPLETED'
    assert trial.usage.wall_seconds<.1 and trial.usage.model_calls==0
    assert trial.usage.http_attempts==3
    await client.aclose(); await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('native',[False,True])
async def test_external_cancel_during_finalization_stays_interrupted(tmp_path,monkeypatch,native):
    c,client,worker,original,calls,run=await setup(tmp_path,monkeypatch,'cancel',native=native)
    task=asyncio.create_task(run())
    await worker.finishing.wait(); task.cancel()
    trial=await task; episode=c.store.get_record('episodes',trial.episode_id)
    assert trial.lifecycle=='INTERRUPTED' and episode['reason']=='TASK_CANCELLED'
    assert episode['report']==original.model_dump(mode='json')
    output=c.store.list_records('trace_calls')[0]['output']
    assert output['terminal_status']=='INTERRUPTED' and output['report']==episode['report']
    await client.aclose(); await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('behavior',['report_error','provider_error'])
async def test_external_cancel_after_actor_error_stays_interrupted(tmp_path,monkeypatch,behavior):
    c,client,worker,original,calls,run=await setup(tmp_path,monkeypatch,'cancel',behavior=behavior)
    task=asyncio.create_task(run())
    await worker.finishing.wait(); task.cancel()
    trial=await task; episode=c.store.get_record('episodes',trial.episode_id)
    assert trial.lifecycle=='INTERRUPTED' and episode['reason']=='TASK_CANCELLED'
    assert episode['report'] is None
    assert c.store.list_records('trace_calls')[0]['output']['terminal_status']=='INTERRUPTED'
    await client.aclose(); await c.close()
