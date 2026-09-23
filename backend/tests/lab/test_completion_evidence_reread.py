"""Phase 16: one blind evidence re-read inside a completion study, and v4 end to end.

Offline plumbing evidence only. A remote double loses one episode's live trace so
its first read times out; the study must re-upload the saved local trace once, read
again, and continue with nothing about the trial, verdict or Mechanic call changed.
"""
from unittest.mock import AsyncMock

import pytest

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V4
from app.config import Settings
from app.lab.completion_study import queue_completion_study
from app.lab.evidence import WaitingEvidence
from app.telemetry.weave_reader import WeaveReader
from app.telemetry.worker import WeaveWorker
from test_baseline_study import StudyRemoteDouble
from test_completion_study import harness


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class LossyRemote(StudyRemoteDouble):
    """Accepts a live trace for chosen episodes and then loses it; restore_call delivers."""
    def __init__(self, *, restore_works=True):
        super().__init__()
        self.lose, self.restore_works = set(), restore_works
        self.lost_ids, self.restored = set(), []
        self.ensure_running = AsyncMock()

    async def request(self, operation, payload, **kwargs):
        if operation == 'start_call' and payload['metadata'].get('episode_id') in self.lose:
            self.operations.append(operation); self.lost_ids.add(payload['call_id'])
            return {'id': payload['call_id']}
        if operation == 'finish_call' and payload['call_id'] in self.lost_ids:
            self.operations.append(operation); return {}
        if operation == 'restore_call':
            self.operations.append(operation); self.restored.append(payload['call_id'])
            if self.restore_works:
                parent = payload.get('parent_id')
                self.calls[payload['call_id']] = {
                    'id': payload['call_id'], 'project_id': 'entity/project',
                    'attributes': payload['metadata'], 'inputs': payload['inputs'], 'parent_id': parent,
                    'trace_id': self.calls[parent]['trace_id'] if parent in self.calls else payload['call_id'],
                    'output': payload['output'], 'ended_at': payload['ended_at']}
            return {'id': payload['call_id'], 'reused': False}
        return await super().request(operation, payload, **kwargs)


async def lossy_harness(tmp_path, **kwargs):
    c, campaign, provider, _, client = await harness(tmp_path)
    remote = LossyRemote(**kwargs)
    # Rewire every telemetry consumer to the lossy double, and shorten the read
    # deadline so a lost trace fails in milliseconds instead of 60 seconds.
    c.runner.trace.worker = remote
    c.evidence_gateway.trace.worker = remote
    c.evidence_gateway.reader = WeaveReader(remote, 'entity/project', c.evidence_gateway.authorize_registration,
                                            deadline_seconds=0.2, poll_seconds=0.02)
    c.evaluation_publisher.worker = remote
    return c, campaign, provider, remote, client


async def run(c, campaign, remote, lose_slots=(), **kwargs):
    queued = await queue_completion_study(c, campaign.campaign_id, **kwargs)
    # The task is scheduled but has not run yet: choose the lost episodes by slot.
    remote.lose |= {queued['slots'][index]['episode_id'] for index in lose_slots}
    await c.tasks[queued['study_id']]
    return queued, c.store.get_record('completion_studies', queued['study_id'])


@pytest.mark.anyio
@pytest.mark.parametrize('slot', [0, 3, 7, 30], ids=['control-source', 'control-healthy', 'candidate', 'validation'])
async def test_lost_trace_is_reuploaded_once_and_study_continues(tmp_path, slot):
    c, campaign, provider, remote, client = await lossy_harness(tmp_path)
    try:
        queued, result = await run(c, campaign, remote, lose_slots=[slot])
        lost = queued['slots'][slot]['episode_id']
        assert result['decision'] == 'OBSERVED_IMPROVEMENT', result.get('error_type')
        assert result['evidence_rereads'] == [{'episode_id': lost, 'stage': queued['slots'][slot]['stage'],
                                               'first_error_code': 'DEADLINE', 'result': 'VERIFIED'}]
        assert set(result['evidence'].values()) == {'weave_verified'} and len(result['evidence']) == 54
        assert c.store.get_record('ingestions', lost)['state'] == 'INGESTED'
        assert remote.ensure_running.await_count == 1
        # Exactly the lost episode's registered trace was re-sent, and nothing ran twice:
        # one trial, one world and one verdict per slot, one Mechanic call. (For slot 0
        # the double also loses the later Mechanic span, which carries that episode's id
        # as its correlation tag; it was never evidence and is not re-sent in-study.)
        registration = c.store.get_record('trace_registrations', lost)
        assert set(remote.restored) == {registration['root_call_id'], *registration['child_call_ids']}
        assert set(remote.restored) <= remote.lost_ids
        assert len(result['trial_rows']) == 54 == len({r['trial']['world_id'] for r in result['trial_rows']})
        assert len(c.store.list_records('verdicts')) == 54
        assert len(provider.mechanic_inputs) == 1 and provider.calls == result['charged_model_calls']
        bundle = c.store.get_record('evidence', lost)
        episode = c.store.get_record('episodes', lost)
        assert bundle['report'] == episode['report'] and bundle['source'] == 'weave_verified'
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_reread_happens_at_most_once_then_the_original_failure_is_kept(tmp_path):
    c, campaign, provider, remote, client = await lossy_harness(tmp_path, restore_works=False)
    try:
        retry = AsyncMock(wraps=c.evidence_gateway.retry); c.evidence_gateway.retry = retry
        queued, result = await run(c, campaign, remote, lose_slots=[2])
        lost = queued['slots'][2]['episode_id']
        assert result['status'] == 'INCOMPLETE' and result['error_type'] == 'WaitingEvidence'
        assert result['evidence_rereads'] == [{'episode_id': lost, 'stage': 'controls',
                                               'first_error_code': 'DEADLINE', 'result': 'FAILED'}]
        assert retry.await_count == 1
        assert len(result['trial_rows']) == 3 and not provider.mechanic_inputs
        assert c.active_id is None and c.ledgers[campaign.campaign_id].reserved_calls == 1064
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize('state,code', [('REJECTED', 'INVALID_EVIDENCE'), ('REJECTED', 'NOT_AUTHORIZED'),
                                        ('RETRYABLE_ERROR', 'STOPPED'), (None, None)])
async def test_integrity_and_non_transport_failures_are_never_reread(tmp_path, state, code):
    c, campaign, provider, remote, client = await lossy_harness(tmp_path)
    try:
        async def failing_get(episode_id, context, **kwargs):
            if state is not None:
                c.store.put_record('ingestions', episode_id, {'episode_id': episode_id, 'state': state,
                                   'status': 'weave_error', 'execution_epoch': 1, 'error_code': code})
            raise WaitingEvidence(code or 'Registered root trace is unavailable')
        c.evidence_gateway.get = failing_get
        retry = AsyncMock(); c.evidence_gateway.retry = retry
        _, result = await run(c, campaign, remote)
        assert result['status'] == 'INCOMPLETE' and result['error_type'] == 'WaitingEvidence'
        assert 'evidence_rereads' not in result and retry.await_count == 0
        assert remote.ensure_running.await_count == 0
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_a_mismatch_found_on_reread_is_an_integrity_failure_not_a_retry(tmp_path):
    c, campaign, provider, remote, client = await lossy_harness(tmp_path)
    try:
        original = remote.request
        async def tampering(operation, payload, **kwargs):
            if operation == 'restore_call' and payload.get('parent_id') is not None:
                payload = {**payload, 'output': {**payload['output'], 'observation': {'tampered': True}}}
            return await original(operation, payload, **kwargs)
        remote.request = tampering
        queued, result = await run(c, campaign, remote, lose_slots=[1])
        assert result['status'] == 'INCOMPLETE' and result['error_type'] == 'EvidenceDenied'
        assert [e['result'] for e in result['evidence_rereads']] == ['DENIED']
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_stop_during_the_reread_interrupts_instead_of_retrying(tmp_path):
    c, campaign, provider, remote, client = await lossy_harness(tmp_path)
    try:
        async def stop_then_fail(*args, **kwargs):
            c.get(campaign.campaign_id)  # the campaign exists
            current = c.get(campaign.campaign_id); current.stop_requested = True; c.save(current)
            raise WaitingEvidence('DEADLINE')
        c.evidence_gateway.retry = stop_then_fail
        _, result = await run(c, campaign, remote, lose_slots=[0])
        assert result['status'] == 'INTERRUPTED'
        assert [e['result'] for e in result['evidence_rereads']] == ['FAILED']
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_worker_ensure_running_restarts_only_a_dead_worker(tmp_path):
    class Process:
        def __init__(self, alive): self.alive = alive; self.terminated = False
        def is_alive(self): return self.alive
        def terminate(self): self.terminated = True
        def join(self, timeout=None): pass
        def kill(self): pass
    worker = WeaveWorker(Settings(faultlab_artifact_dir=str(tmp_path)), live_authorized=True)
    worker.start = AsyncMock()
    dead = Process(False); worker._process = dead; worker._initialized = True
    await worker.ensure_running()
    assert worker._process is None and worker.start.await_count == 1
    # Alive but never initialized: the coordinator swallows a failed first start.
    half = Process(True); worker._process = half; worker._initialized = False
    await worker.ensure_running()
    assert worker._process is None and half.terminated and worker.start.await_count == 2
    live = Process(True); worker._process = live; worker._initialized = True
    await worker.ensure_running()
    assert worker._process is live and not live.terminated and worker.start.await_count == 3


@pytest.mark.anyio
async def test_full_study_runs_end_to_end_under_v4_indexed_evidence(tmp_path):
    """The first end-to-end completion study under v4; every Actor turn is stamped v4."""
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        queued = await queue_completion_study(c, campaign.campaign_id,
                                              actor_context_protocol=ACTOR_CONTEXT_PROTOCOL_V4)
        assert queued['actor_context_protocol'] == ACTOR_CONTEXT_PROTOCOL_V4
        await c.tasks[queued['study_id']]
        result = c.store.get_record('completion_studies', queued['study_id'])
        assert result['decision'] == 'OBSERVED_IMPROVEMENT', result.get('error_type')
        assert result['actor_context_protocol'] == ACTOR_CONTEXT_PROTOCOL_V4 and result['replay_of'] is None
        assert 'evidence_rereads' not in result
        stamped = set()
        for row in result['trial_rows']:
            stamped |= {event['payload'].get('actor_context_protocol')
                        for event in c.store.events(row['trial']['episode_id'])['events']
                        if event['type'] == 'actor_output'}
        assert stamped == {ACTOR_CONTEXT_PROTOCOL_V4}
        assert c.store.get_record('completion_plans', queued['study_id'])['actor_context_protocol'] \
            == ACTOR_CONTEXT_PROTOCOL_V4
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_default_actor_context_is_still_v1(tmp_path):
    """The default is unchanged on purpose; Phase 17 must pass v4 explicitly."""
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        queued = await queue_completion_study(c, campaign.campaign_id)
        assert queued['actor_context_protocol'] == ACTOR_CONTEXT_PROTOCOL_V1
        await c.tasks[queued['study_id']]
    finally:
        await client.aclose()


class DeadWorkerRemote(LossyRemote):
    """After the first lost episode the shared worker is 'dead' until ensure_running."""
    def __init__(self):
        super().__init__()
        self.dead = False
        async def revive():
            self.dead = False
        self.ensure_running = AsyncMock(side_effect=revive)

    async def request(self, operation, payload, **kwargs):
        if self.dead and operation in ('get_calls', 'flush', 'restore_call'):
            from app.telemetry.safety import TelemetryError
            raise TelemetryError('Telemetry worker is unavailable.')
        if operation == 'start_call' and payload['metadata'].get('episode_id') in self.lose:
            self.dead = True
        return await super().request(operation, payload, **kwargs)


@pytest.mark.anyio
async def test_a_dead_worker_is_restarted_and_a_transport_failure_recovers(tmp_path):
    c, campaign, provider, _, client = await harness(tmp_path)
    remote = DeadWorkerRemote()
    c.runner.trace.worker = remote
    c.evidence_gateway.reader = WeaveReader(remote, 'entity/project', c.evidence_gateway.authorize_registration,
                                            deadline_seconds=0.2, poll_seconds=0.02)
    c.evaluation_publisher.worker = remote
    try:
        queued, result = await run(c, campaign, remote, lose_slots=[4])
        assert result['decision'] == 'OBSERVED_IMPROVEMENT', result.get('error_type')
        assert [(e['first_error_code'], e['result']) for e in result['evidence_rereads']] == [('TRANSPORT', 'VERIFIED')]
        assert remote.ensure_running.await_count == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize('failure,label', [(TimeoutError(), 'FAILED'), (RuntimeError('settings'), 'ERROR')])
async def test_a_reread_that_times_out_or_breaks_is_labelled_and_ends_the_study(tmp_path, failure, label):
    c, campaign, provider, remote, client = await lossy_harness(tmp_path)
    try:
        c.evidence_gateway.retry = AsyncMock(side_effect=failure)
        _, result = await run(c, campaign, remote, lose_slots=[0])
        assert result['status'] == 'INCOMPLETE'
        assert [e['result'] for e in result['evidence_rereads']] == [label]
        assert result['error_type'] == ('WaitingEvidence' if label == 'FAILED' else 'RuntimeError')
    finally:
        await client.aclose()
