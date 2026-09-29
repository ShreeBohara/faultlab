"""The in-process pre-check replay matches a real socket run through the real adapter.

The same agent path (no waits, seven business calls, status once per turn while pending,
never a re-send: after UNKNOWN at most three status checks) drives the real BusinessToolBroker, with its real 1.0 s client
timeout and two-attempt retries, against the real simulator served on an owned loopback
port. The world's attempt sequence, the delivered timeouts and every fault record must
equal the in-process replay that skips the F1 server sleep. No provider or model is used.
"""
import asyncio

import pytest

from app.adapters.business_tools import BusinessToolBroker, WorldClient
from app.adapters.journal import Journal, allocate_intent
from app.contracts.models import FaultSpec
from app.lab.budgets import BudgetExhausted, EpisodeMeter
from app.lab.reachability import UNKNOWN_STATUS_CHECKS, caller_model_for, fixture_for, label_recipe
from app.lab.storage import LabStore


def P(kind, tool, service, occurrence, **parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': occurrence, 'parameters': parameters}


def F2(delay, ok=True, occurrence=1):
    return P('F2', 'update_order', 'orders', occurrence, completion_delay_ticks=delay, terminal_status='SUCCEEDED' if ok else 'FAILED',
             failure_code=None if ok else 'UPGRADE_REJECTED')


RECIPES = [
    [P('F1', 'update_order', 'orders', 1, response_delay_ms=1500)],
    [P('F1', 'send_confirmation', 'notifications', 1, response_delay_ms=3000)],
    [F2(5), P('F1', 'send_confirmation', 'notifications', 1, response_delay_ms=1500)],   # N5: never reaches the send
    [F2(4), P('F1', 'send_confirmation', 'notifications', 1, response_delay_ms=2000)],   # boundary: the send is call 7
    [F2(3), P('F4', 'get_operation_status', 'orders', 3, failure_count=1)],
    [P('F4', 'send_confirmation', 'notifications', 1, failure_count=2)],
    [P('F4', 'update_order', 'orders', 1, failure_count=1), F2(3, occurrence=2)],
    [F2(2, ok=False), P('F1', 'send_confirmation', 'notifications', 1, response_delay_ms=3000)],
    [P('F3', 'get_order', 'orders', 1, versions_back=2)],
    # Caller v2 (review finding): a write failing on both attempts is never re-sent.
    [P('F4', 'update_order', 'orders', 1, failure_count=2), P('F1', 'send_confirmation', 'notifications', 1, response_delay_ms=1500)],
    [P('F4', 'send_confirmation', 'notifications', 1, failure_count=3)],
    [P('F4', 'send_confirmation', 'notifications', 1, failure_count=2), P('F4', 'get_operation_status', 'notifications', 3, failure_count=1)],
    [P('F4', 'send_confirmation', 'notifications', 1, failure_count=2), P('F4', 'get_operation_status', 'notifications', 2, failure_count=8)],
]


async def agent_over_the_real_adapter(broker, limit):
    requested = []  # (service asked for, delivered observation) per logical call, as the agent sees them
    def receipt(service):
        for observation in broker.journal.observations:
            data = observation.result.data
            if observation.result.transport == 'ok' and getattr(data, 'service', None) == service and data.receipt:
                return data.receipt.status
        return None
    def latest(service):
        for asked, observation in reversed(requested):
            if asked == service: return observation.result.status if observation.result.transport == 'ok' else None
        return None
    calls = 0
    async def call(tool, service):
        nonlocal calls
        calls += 1
        args = {'desired_shipping': 'express'} if tool == 'update_order' else {'service': service} if tool == 'get_operation_status' else None
        requested.append((service, await broker.call(tool, args)))
    async def resolve(service):
        unresolved = 0
        while receipt(service) is None and calls < limit:
            await call('get_operation_status', service)
            if receipt(service) is None and latest(service) != 'PENDING':
                unresolved += 1
                if unresolved >= UNKNOWN_STATUS_CHECKS: break
    try:
        await call('get_order', 'orders'); await call('update_order', 'orders'); await resolve('orders')
        if receipt('orders') == 'SUCCEEDED' and calls < limit:
            await call('send_confirmation', 'notifications'); await resolve('notifications')
    except BudgetExhausted:
        pass
    return calls


@pytest.mark.localhost_http
@pytest.mark.parametrize('primitives', RECIPES)
def test_in_process_replay_matches_the_real_adapter_on_a_real_socket(tmp_path, simulator_server, primitives):
    url, app = simulator_server
    caller = caller_model_for('reference', [])
    spec = FaultSpec.model_validate({'seed': 3, 'primitives': primitives})
    predicted = label_recipe(spec, caller)

    async def live():
        world_client = WorldClient(url, 'integration-control')
        try:
            fixture = fixture_for(spec.model_dump(mode='json'))
            intent = allocate_intent('order-faithful', 'Upgrade and confirm', 4 if fixture == 'history-v1' else 1)
            world = await world_client.create('episode-faithfulness', intent, spec, fixture)
            store = LabStore(tmp_path / 'lab.db')
            store.put_record('episodes', 'episode-faithfulness', {'campaign_id': 'offline-faithfulness'})
            broker = BusinessToolBroker(world_client, world['world_id'], world['capability'], Journal(store, 'episode-faithfulness', intent), EpisodeMeter())
            calls = await agent_over_the_real_adapter(broker, caller.max_business_calls)
            timeouts = [o.result.transport == 'timeout' for o in broker.journal.observations]
            return world['world_id'], calls, timeouts
        finally:
            await world_client.close()
    world_id, calls, timeouts = asyncio.run(live())
    state = app.state.store.read(world_id)
    attempts = [f"{e['payload']['tool']}:{e['payload']['service']}" for e in state['events'] if e['type'] == 'http_attempt']
    assert attempts == [token.split('#')[0] for token in predicted['agent_path']]
    assert timeouts == [token.endswith('/timeout') for token in predicted['agent_path']]
    assert [f['triggered'] for f in state['fault_executions']] == [
        predicted_fault['verdict'] == 'FORCED' for predicted_fault in predicted['faults']]
    assert calls == predicted['agent_business_calls']
