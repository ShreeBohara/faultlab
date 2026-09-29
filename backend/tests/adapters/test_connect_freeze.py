"""Phase 19: a frozen lab event loop must never turn a request into one that was not sent.

Phase 18's only failure: the confirmation's response was delayed, attempt 1 timed out on
read, and the broker's automatic re-send was dialling a fresh connection when the lab's
event loop froze for over a second. httpx raised ConnectTimeout before writing the
request, so the simulator never saw it, but the broker had already counted its tick. The
lab's clock ran one ahead of the world's and the Actor's truthful citation failed C6.
"""
import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from app.adapters import business_tools
from app.adapters.business_tools import BusinessToolBroker, WorldClient
from app.adapters.journal import Journal, allocate_intent
from app.contracts.models import FaultSpec
from app.lab.budgets import EpisodeMeter
from app.lab.storage import LabStore
from app.simulator.main import create_app
from app.config import Settings

pytestmark = pytest.mark.localhost_http


@pytest.fixture
def store(tmp_path):
    return LabStore(tmp_path / 'lab.sqlite3')


@pytest.fixture
def live_url(tmp_path):
    listener = socket.socket(); listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    app = create_app(database_dir=tmp_path / 'worlds', control_token='test-control', settings=Settings())
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True); thread.start()
    until = time.monotonic() + 5
    while not server.started and time.monotonic() < until: time.sleep(.01)
    assert server.started
    yield f'http://127.0.0.1:{port}'
    server.should_exit = True; thread.join(timeout=6); listener.close()
    assert not thread.is_alive()


def delayed_confirmation(ms):
    return FaultSpec.model_validate({'seed': 7, 'primitives': [{'kind': 'F1', 'occurrence': 1, 'parameters': {'response_delay_ms': ms},
                                                               'target_service': 'notifications', 'target_tool': 'send_confirmation'}]})


async def upgraded_broker(url, store, fault_spec, episode_id):
    world_client = WorldClient(url, 'test-control')
    intent = allocate_intent('order-1', 'Upgrade this order to express and send its confirmation.')
    world = await world_client.create(episode_id, intent, fault_spec)
    store.put_record('episodes', episode_id, {'campaign_id': 'phase19'})
    meter = EpisodeMeter()
    broker = BusinessToolBroker(world_client, world['world_id'], world['capability'], Journal(store, episode_id, intent), meter)
    await broker.call('get_order'); await broker.call('update_order', {'desired_shipping': 'express'})
    return world_client, world, broker, meter


def test_every_request_gets_a_long_connect_budget_and_an_unchanged_read_budget(store):
    seen = []
    class Client:
        async def request(self, method, path, **kwargs):
            seen.append(kwargs['timeout'])
            raise httpx.ConnectError('refused')
    client = WorldClient('http://127.0.0.1:8001', 'token', client=Client())
    intent = allocate_intent('order-1', 'Upgrade this order to express and send its confirmation.')
    store.put_record('episodes', 'episode-1', {'campaign_id': 'phase19'})
    broker = BusinessToolBroker(client, 'world-1', 'cap', Journal(store, 'episode-1', intent), EpisodeMeter())
    asyncio.run(broker.call('get_order'))
    with pytest.raises(business_tools.WorldControlError): asyncio.run(client.stop('world-1'))
    business, control = seen[0], seen[-1]
    assert isinstance(business, httpx.Timeout) and isinstance(control, httpx.Timeout)
    assert business.connect == control.connect == business_tools.CONNECT_TIMEOUT >= 5
    # The response-delay faults are defined against these; they must not move.
    assert business.read == business.write == business.pool == business_tools.BUSINESS_TIMEOUT == 1.0
    assert control.read == control.write == control.pool == 3


def test_a_loop_freeze_while_the_resend_connects_still_reaches_the_world(live_url, store):
    async def run():
        world_client, world, broker, meter = await upgraded_broker(live_url, store, delayed_confirmation(2500), 'episode-freeze')
        original = world_client.client.request; sends = []
        async def request(method, path, **kwargs):
            if path == '/business/notifications':
                sends.append(path)
                if len(sends) == 2:  # the broker's automatic same-call re-send
                    pending = asyncio.ensure_future(original(method, path, **kwargs))
                    for _ in range(3): await asyncio.sleep(0)  # let it reach the connect
                    time.sleep(1.2)  # the lab's event loop is frozen
                    return await pending
            return await original(method, path, **kwargs)
        world_client.client.request = request
        observation = await broker.call('send_confirmation')
        snapshot = await world_client.snapshot(world['world_id'])
        await world_client.close()
        return observation, snapshot, meter
    observation, snapshot, meter = asyncio.run(run())
    world_attempts = sum(1 for e in snapshot.events if e.type == 'http_attempt')
    assert len([e for e in snapshot.events if e.type == 'http_attempt' and e.payload['tool'] == 'send_confirmation']) == 2
    assert meter.usage.http_attempts == world_attempts == 4
    assert meter.usage.ticks == snapshot.tick
    assert observation.result.status == 'SUCCEEDED' and observation.delivered_tick == snapshot.tick


FREEZE_PLACEMENTS = (1, 2, 3, 4, 6, 8)


async def fresh_connection_read(url, store, episode_id, yields):
    """One get_order on a brand-new connection with the lab loop frozen after `yields`
    event-loop steps. Returns (lab attempts, world attempts)."""
    control = WorldClient(url, 'test-control')
    intent = allocate_intent('order-1', 'Upgrade this order to express and send its confirmation.')
    world = await control.create(episode_id, intent, FaultSpec(seed=1, primitives=[])); await control.close()
    store.put_record('episodes', episode_id, {'campaign_id': 'phase19'})
    business = WorldClient(url, 'test-control')  # its own pool, so the first call must dial
    meter = EpisodeMeter()
    broker = BusinessToolBroker(business, world['world_id'], world['capability'], Journal(store, episode_id, intent), meter)
    original = business.client.request; frozen = []
    async def request(method, path, **kwargs):
        if path.startswith('/business/') and not frozen:
            frozen.append(path)
            pending = asyncio.ensure_future(original(method, path, **kwargs))
            for _ in range(yields): await asyncio.sleep(0)
            time.sleep(1.1)  # the lab's event loop is frozen
            return await pending
        return await original(method, path, **kwargs)
    business.client.request = request
    await broker.call('get_order')
    business.client.request = original
    snapshot = await business.snapshot(world['world_id']); await business.close()
    return meter.usage.http_attempts, sum(1 for e in snapshot.events if e.type == 'http_attempt')


def test_no_freeze_placement_during_a_fresh_connection_loses_a_request(live_url, store, monkeypatch):
    # Self-check first: with the old 1s connect budget, at least one of these placements
    # must land inside the connect and lose the request. Otherwise this sweep proves
    # nothing (an httpx/anyio update could move the connect window).
    monkeypatch.setattr(business_tools, 'CONNECT_TIMEOUT', business_tools.BUSINESS_TIMEOUT)
    old = [asyncio.run(fresh_connection_read(live_url, store, f'episode-old-{y}', y)) for y in FREEZE_PLACEMENTS]
    assert any(lab != world for lab, world in old), old
    monkeypatch.undo()
    new = [asyncio.run(fresh_connection_read(live_url, store, f'episode-new-{y}', y)) for y in FREEZE_PLACEMENTS]
    assert all(lab == world for lab, world in new), new


def test_a_response_delay_still_times_out_on_read(live_url, store):
    async def run():
        world_client, world, broker, meter = await upgraded_broker(live_url, store, delayed_confirmation(1500), 'episode-delay')
        observation = await broker.call('send_confirmation')
        attempts = [store.get_record('tool_calls', call['call_id']) for call in broker.logical_calls][-1]
        first = [e for e in store.events('episode-delay', include_private=True)['events'] if e['type'] == 'observation_delivered'][-2]
        snapshot = await world_client.snapshot(world['world_id'])
        await world_client.close()
        return observation, attempts, first, snapshot, meter
    observation, attempts, first, snapshot, meter = asyncio.run(run())
    assert len(attempts['attempt_ids']) == 2
    assert first['payload']['observation']['result']['error_code'] == 'HTTP_TIMEOUT'
    assert observation.result.status == 'SUCCEEDED'
    assert meter.usage.http_attempts == sum(1 for e in snapshot.events if e.type == 'http_attempt') == 4
