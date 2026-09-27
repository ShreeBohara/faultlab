"""Invalid lab/world timing cannot become a learned defect in the tested agent."""
import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from app.adapters.business_tools import WorldClient
from app.agents.reference import ReferenceActor
from app.config import Settings
from app.contracts.models import CampaignRequest, FaultSpec, NoNextAction, TaskReport
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.simulator.main import create_app


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def setup(tmp_path, client=None):
    simulator = create_app(database_dir=tmp_path / 'worlds', control_token='clock-test')
    client = client or httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator),
                                       base_url='http://127.0.0.1:8001')
    world = WorldClient('http://127.0.0.1:8001', 'clock-test', client=client)
    coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path / 'lab')))
    campaign = coordinator.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-clock',
                                                 mode='baseline', config_profile_id='live-v1'))
    return coordinator, campaign, world, simulator


async def run(coordinator, campaign, world, primitives=(), actor=None):
    return await EpisodeRunner(coordinator.store, world, actor=actor or ReferenceActor()).run(
        campaign, FaultSpec(seed=1, primitives=list(primitives)), coordinator.policies.baseline(),
        source_mode='offline_fixture')


@pytest.mark.anyio
@pytest.mark.parametrize('primitives', [
    [],
    [{'kind': 'F4', 'target_tool': 'get_order', 'target_service': 'orders', 'occurrence': 1,
      'parameters': {'failure_count': 1}}],
    [{'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
      'parameters': {'completion_delay_ticks': 3, 'terminal_status': 'SUCCEEDED', 'failure_code': None}}],
])
async def test_clean_and_faulted_admissions_keep_their_valid_verdicts(tmp_path, primitives):
    coordinator, campaign, world, _ = setup(tmp_path)
    try:
        trial = await run(coordinator, campaign, world, primitives)
        integrity = coordinator.store.get_record('private_world_integrity', trial.episode_id)
        assert trial.lifecycle == trial.outcome == 'COMPLETED'
        assert trial.failed_checks == []
        assert integrity['status'] == 'VALID' and integrity['issues'] == []
        assert integrity['decision_tick'] == trial.usage.ticks
        assert integrity['horizon_tick'] == trial.usage.ticks + 5
        assert integrity['admitted_http_attempts'] == trial.usage.http_attempts
        if primitives:
            assert trial.fault_triggered
    finally:
        await world.close()
        coordinator.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('error_type', [httpx.ConnectError, httpx.ReadError])
async def test_unadmitted_request_is_lab_error_with_original_report_effects_and_charges(tmp_path, error_type):
    coordinator, campaign, world, _ = setup(tmp_path)
    original = world.client.request
    failed = False

    async def request(method, path, **kwargs):
        nonlocal failed
        if path.startswith('/business/') and not failed:
            failed = True
            raise error_type('offline transport failure before simulator admission')
        return await original(method, path, **kwargs)

    world.client.request = request
    try:
        trial = await run(coordinator, campaign, world)
        episode = coordinator.store.get_record('episodes', trial.episode_id)
        snapshots = coordinator.store.get_record('private_snapshots', trial.episode_id)
        integrity = coordinator.store.get_record('private_world_integrity', trial.episode_id)
        assert trial.lifecycle == trial.outcome == 'LAB_ERROR'
        assert trial.reason == 'WORLD_EXECUTION_MISMATCH'
        assert episode['report']['overall'] == 'COMPLETED'
        assert trial.usage.http_attempts == trial.usage.ticks == 4
        assert snapshots['decision']['tick'] == 3
        assert len(snapshots['horizon']['notifications']) == 1
        assert sum(e['type'] == 'upgrade_committed' for e in snapshots['horizon']['events']) == 1
        # Do not weaken or rewrite the fixed rules to force this invalid episode
        # to pass: the verdict is explicitly a lab error and checks remain saved.
        assert trial.failed_checks == ['C5', 'C6', 'C8']
        assert integrity['issues'] == ['DECISION_TICK_MISMATCH', 'HTTP_ADMISSION_COUNT_MISMATCH',
                                       'HTTP_ADMISSION_IDENTITY_MISMATCH']
        assert len(integrity['dispatched_attempt_ids']) == 4
        assert integrity['admitted_attempt_ids'] == integrity['dispatched_attempt_ids'][1:]
        events = coordinator.store.events(trial.episode_id, include_private=True)['events']
        observations = [e['payload']['observation'] for e in events if e['type'] == 'observation_delivered']
        assert [o['delivered_tick'] for o in observations] == [1, 2, 3, 4]
        assert observations[-1]['result']['status'] == 'SUCCEEDED'
        assert any(e['type'] == 'world_execution_mismatch' and e['visibility'] == 'PRIVATE_EVALUATOR'
                   for e in events)
    finally:
        await world.close()
        coordinator.store.close()


@pytest.mark.anyio
async def test_stops_admission_before_freezing_and_snapshot_reads_never_advance(tmp_path):
    coordinator, campaign, world, simulator = setup(tmp_path)
    original_create, original_snapshot = world.create, world.snapshot
    handle = None
    audit_statuses = []

    async def create(*args, **kwargs):
        nonlocal handle
        handle = await original_create(*args, **kwargs)
        return handle

    async def snapshot(world_id):
        # Exercise a late HTTP request at the precise old snapshot/stop window.
        # It must already be rejected, with no clock or effects change.
        before = simulator.state.store.snapshot(world_id)
        response = await world.client.get('/business/orders/order-clock', headers={
            'X-FaultLab-World': world_id, 'X-FaultLab-Capability': handle['capability'],
            'X-FaultLab-Call': 'call-late', 'X-FaultLab-Attempt': 'attempt-late',
        })
        audit_statuses.append(response.status_code)
        first, second = await original_snapshot(world_id), await original_snapshot(world_id)
        assert before == first == second
        return second

    world.create, world.snapshot = create, snapshot
    try:
        trial = await run(coordinator, campaign, world)
        assert trial.outcome == 'COMPLETED'
        assert audit_statuses == [409, 409]
        assert coordinator.store.get_record('private_world_integrity', trial.episode_id)['status'] == 'VALID'
    finally:
        await world.close()
        coordinator.store.close()


@pytest.mark.anyio
async def test_real_agent_ordering_mistake_remains_violation(tmp_path):
    coordinator, campaign, world, _ = setup(tmp_path)

    async def premature_notification(intent, context):
        notification = await context.broker.call('send_confirmation')
        upgrade = await context.broker.call('update_order', {'desired_shipping': 'express'})
        return TaskReport(upgrade_outcome='SUCCEEDED', notification_outcome='SUCCEEDED', overall='COMPLETED',
                          evidence_ids=[notification.evidence_id, upgrade.evidence_id], next_action=NoNextAction(kind='NONE'))

    try:
        trial = await run(coordinator, campaign, world, actor=premature_notification)
        assert trial.lifecycle == 'COMPLETED' and trial.outcome == 'VIOLATION'
        assert trial.failed_checks == ['C3']
        assert coordinator.store.get_record('private_world_integrity', trial.episode_id)['status'] == 'VALID'
    finally:
        await world.close()
        coordinator.store.close()


@pytest.mark.localhost_http
def test_real_response_timeout_after_commit_remains_valid(tmp_path):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    simulator = create_app(database_dir=tmp_path / 'http-worlds', control_token='clock-test')
    server = uvicorn.Server(uvicorn.Config(simulator, log_level='error', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(.01)
        assert server.started

        async def execute():
            client = httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}')
            coordinator, campaign, world, _ = setup(tmp_path, client)
            try:
                fault = [{'kind': 'F1', 'target_tool': 'send_confirmation', 'target_service': 'notifications',
                          'occurrence': 1, 'parameters': {'response_delay_ms': 1500}}]
                trial = await run(coordinator, campaign, world, fault)
                integrity = coordinator.store.get_record('private_world_integrity', trial.episode_id)
                assert trial.lifecycle == trial.outcome == 'COMPLETED'
                assert trial.fault_triggered and trial.usage.http_attempts == 4
                assert integrity['status'] == 'VALID'
                events = coordinator.store.events(trial.episode_id, include_private=True)['events']
                observations = [e['payload']['observation'] for e in events if e['type'] == 'observation_delivered']
                assert any(o['result']['transport'] == 'timeout' for o in observations)
                assert observations[-1]['result']['status'] == 'SUCCEEDED'
            finally:
                await world.close()
                coordinator.store.close()

        asyncio.run(execute())
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        listener.close()
        assert not thread.is_alive()
