"""Product review, check 1 (continued): rule v2 in the real original loop for the Mechanic, the challenge Explorer and the
native agent. The planned native original loop (manual reference fixture; the backend tests' localhost simulator on an
owned loopback port) with scripted lab-model losses. Offline and $0: only loopback sockets (localhost_http marker).
"""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from app.agents import transport_retry
from app.agents.transport_retry import TRANSPORT_RETRY_PROTOCOL_V2
from app.lab.run_plans import read_run_plan
from app.providers.runtime import RuntimeProviderError

OUT = {}


@pytest.fixture
def anyio_backend(): return 'asyncio'


def dump(name, value):
    OUT[name] = value
    print(f'\n### {name}\n' + json.dumps(value, indent=1, sort_keys=True, default=str))


class VirtualClock:
    def __init__(self):
        self.total = 0.0
    async def sleep(self, seconds):
        self.total += seconds
        await asyncio.sleep(0)


def make_provider(lose, *, lose_actor=()):
    from test_planned_agent_execution import NativeReferenceInputs

    class Losing(NativeReferenceInputs):
        def __init__(self):
            super().__init__('accepted'); self.lose = dict(lose); self.lost = []; self.actor_sent = 0
            self.lose_actor = set(lose_actor)
        async def complete(self, messages, *, role='actor', **kwargs):
            if role == 'actor':
                self.actor_sent += 1
                if self.actor_sent in self.lose_actor:
                    self.lost.append(('actor', self.actor_sent))
                    raise RuntimeProviderError('scripted loss', code='CONNECTION_ERROR', error_class='APIConnectionError')
            else:
                context = json.loads(messages[-1]['content'])
                kind = (('challenge' if context.get('purpose') == 'challenge' else 'discovery') if role == 'explorer'
                        else 'diagnosis' if 'intervention_ids' in context else 'proposal')
                if self.lose.get((role, kind), 0):
                    self.lose[(role, kind)] -= 1; self.lost.append((role, kind))
                    raise RuntimeProviderError('scripted loss', code='CONNECTION_ERROR', error_class='APIConnectionError')
            return await super().complete(messages, role=role, **kwargs)
    return Losing()


async def run_loop(tmp_path, provider, *, on_start=None, timeout=240):
    from original_loop_fixture import CONTROL, ManualPolicies, OfflineEvidence, OfflineRunner, fixture_settings, localhost_simulator
    from test_planned_agent_execution import planned_campaign
    from app.adapters.business_tools import WorldClient
    from app.lab.coordinator import LabCoordinator
    settings = fixture_settings(tmp_path / 'lab')
    with localhost_simulator(tmp_path, settings) as url:
        c = LabCoordinator(settings)
        c.runner = OfflineRunner(c.store, WorldClient(url, CONTROL), provider, offline_fixture=True)
        c.policies = ManualPolicies(c.store)
        c.evidence_gateway = OfflineEvidence(c.store, 'offline-fixture/native-selected-loop')
        campaign = planned_campaign(c, mode='learn')
        try:
            assert read_run_plan(c.store, campaign)['plan']['transport_retry']['protocol'] == TRANSPORT_RETRY_PROTOCOL_V2
            await c.start(campaign.campaign_id)
            if on_start: await on_start(c, campaign.campaign_id)
            await asyncio.wait_for(c.tasks[campaign.campaign_id], timeout=timeout)
            current = c.get(campaign.campaign_id)
            return SimpleNamespace(state=current.state, reason=current.terminal_reason,
                                   decision=c.policies.get(current.active_policy_version).decision,
                                   errors=c.store.list_records('execution_errors'),
                                   retries=sorted(c.store.list_records('transport_retries'), key=lambda r: r['recorded_at']),
                                   budget=c.store.get_record('budgets', campaign.campaign_id),
                                   episodes=c.store.list_records('episodes'),
                                   events={e['episode_id']: c.store.events(e['episode_id'])['events'] for e in c.store.list_records('episodes')},
                                   mechanic_outputs=c.store.list_records('mechanic_outputs'),
                                   challenges=c.store.list_records('challenges'),
                                   decisions=[(r['context'].get('selection_index'), (r.get('search_decision') or {}).get('status'), (r.get('search_decision') or {}).get('reason')) for r in c.store.list_records('selections') if not r.get('challenge')])
        finally:
            await c.runner.world_client.close()
            await c.close()


@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_mechanic_diagnosis_lost_four_times_ends_error_naming_the_retries(tmp_path, monkeypatch):
    clock = VirtualClock(); monkeypatch.setattr(transport_retry, 'asyncio', SimpleNamespace(sleep=clock.sleep))
    provider = make_provider({('mechanic', 'diagnosis'): 4})
    result = await run_loop(tmp_path, provider)
    assert result.state == 'ERROR'
    error, = result.errors
    assert error['transport_retries'] == {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'mechanic', 'retries_tried': 3,
                                          'waits_seconds': [5, 20, 60], 'reason': 'ALL_RETRIES_FAILED'}
    assert [(r['role'], r['request']['phase'], r['attempt']) for r in result.retries] == [
        ('mechanic', 'mechanic_diagnosis', 1), ('mechanic', 'mechanic_diagnosis', 2), ('mechanic', 'mechanic_diagnosis', 3)]
    assert clock.total == 85.0
    dump('1d-mechanic-all-failed', {'state': result.state, 'reason': result.reason, 'execution_error_transport_retries': error['transport_retries']})


@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_stop_during_a_real_mechanic_wait(tmp_path, monkeypatch):
    provider = make_provider({('mechanic', 'diagnosis'): 99})
    real_wait = transport_retry.cancellable_wait
    timing = {}
    holder = {}

    async def wait_then_stop(seconds, stopped, **kwargs):
        async def press_stop():
            await asyncio.sleep(1.0)
            timing['stop'] = time.monotonic()
            await holder['c'].stop(holder['id'])
        presser = asyncio.create_task(press_stop())
        try:
            return await real_wait(seconds, stopped, **kwargs)
        finally:
            timing['wait_ended'] = time.monotonic()
            await presser
    monkeypatch.setattr(transport_retry, 'cancellable_wait', wait_then_stop)

    async def remember(c, id):
        holder['c'], holder['id'] = c, id
    result = await run_loop(tmp_path, provider, on_start=remember)
    assert result.state == 'STOPPED'
    assert result.reason.startswith('External stop requested while a failed Mechanic model request waited to be re-sent')
    assert not result.errors and not result.retries
    latency = timing['wait_ended'] - timing['stop']
    assert latency < 0.75
    dump('1e-mechanic-stop', {'state': result.state, 'reason': result.reason, 'stop_to_wait_end_seconds': round(latency, 3),
                              'lost': provider.lost})


@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_challenge_explorer_lost_four_times(tmp_path, monkeypatch):
    clock = VirtualClock(); monkeypatch.setattr(transport_retry, 'asyncio', SimpleNamespace(sleep=clock.sleep))
    provider = make_provider({('explorer', 'challenge'): 4})
    result = await run_loop(tmp_path, provider)
    dump('1f-challenge-all-failed', {'state': result.state, 'reason': result.reason,
                                     'errors': [e.get('transport_retries') for e in result.errors],
                                     'retries': [(r['role'], r['request'].get('phase'), r['attempt'], r['retry_delay_seconds']) for r in result.retries],
                                     'virtual_wait_seconds': clock.total})
    assert result.state == 'ERROR'
    assert result.errors[0]['transport_retries']['role'] == 'explorer' and result.errors[0]['transport_retries']['retries_tried'] == 3
    assert [r['request']['phase'] for r in result.retries] == ['challenge'] * 3


@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_native_agent_loss_in_a_rule_v2_learn_campaign_keeps_rule_v1(tmp_path, monkeypatch):
    """The first discovery episode's first actor request and its one retry are lost: that episode is LAB_ERROR (rule v1,
    no backoff), and the Learn loop carries on to its normal accepted end."""
    clock = VirtualClock(); monkeypatch.setattr(transport_retry, 'asyncio', SimpleNamespace(sleep=clock.sleep))
    provider = make_provider({}, lose_actor={1, 2})
    result = await run_loop(tmp_path, provider)
    lab_errors = [e for e in result.episodes if e.get('lifecycle') == 'LAB_ERROR']
    first = lab_errors[0]
    retry_events = [e for e in result.events[first['episode_id']] if e['type'] == 'actor_transport_retry']
    dump('1g-native-agent-loss', {'state': result.state, 'reason': result.reason, 'decision': result.decision,
                                  'lab_error_episodes': [(e['episode_id'], e.get('reason'), e.get('experiment_purpose')) for e in lab_errors],
                                  'actor_retry_events': [e['payload'] for e in retry_events],
                                  'lab_transport_retry_records': len(result.retries), 'virtual_wait_seconds': clock.total,
                                  'discovery_decisions': result.decisions})
    # Not ERROR: only the episode failed. (The fixture Explorer repeats one recipe, so later slots are duplicates of the
    # lab-errored pick; that is the pre-existing duplicate rule, not rule v2.)
    assert result.state != 'ERROR' and not result.errors
    assert len(lab_errors) == 1 and first['reason'] == 'CONNECTION_ERROR' and first['experiment_purpose'] == 'discovery'
    assert len(retry_events) == 1 and not result.retries and clock.total == 0.0
