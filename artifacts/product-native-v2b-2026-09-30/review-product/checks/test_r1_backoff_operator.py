"""Product review, check 1: what an operator gets from rule v2 (lab-role transport backoff), offline and $0.

The real coordinator runs a real Learn plan (real Explorer, ledger, plan, learning loop, API app) with a scripted
Explorer transport and the fake Actor runner of the backend tests. Waits use the product's own cancellable_wait on a
virtual clock (asyncio.sleep replaced inside transport_retry only), except the Stop checks, which use real time.
No provider, W&B, Weave or model call; the backend suite's socket guard is active (see conftest.py).
"""
import asyncio
import json
import socket
import time
from types import SimpleNamespace

import httpx
import pytest

from app.agents import transport_retry
from app.agents.transport_retry import TRANSPORT_RETRY_PROTOCOL_V2, declaration_v2
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2
from app.lab.exports import development_recording
from app.lab.run_plans import read_run_plan
from app.main import create_app
from app.providers.runtime import RuntimeProviderError

from test_campaign_transport_retry import Flaky, execute
from test_discovery_v2_flow import DELAYED, learn_campaign, owner, raw  # noqa: F401  (owner is a fixture)

OUT = {}


def answer(slot, request, context):
    return raw(DELAYED, seed=slot)


class VirtualClock:
    """Replaces asyncio.sleep inside app.agents.transport_retry only; the product's cancellable_wait runs unchanged."""
    def __init__(self):
        self.steps, self.total = [], 0.0
    async def sleep(self, seconds):
        self.steps.append(seconds); self.total += seconds
        await asyncio.sleep(0)


def virtual_clock(monkeypatch):
    clock = VirtualClock()
    monkeypatch.setattr(transport_retry, 'asyncio', SimpleNamespace(sleep=clock.sleep))
    return clock


def v2_records(store, campaign_id):
    return sorted((r for r in store.list_records('transport_retries')
                   if r['campaign_id'] == campaign_id and r['protocol'] == TRANSPORT_RETRY_PROTOCOL_V2),
                  key=lambda r: r['campaign_retry_number'])


async def api_get(owner, path):
    transport = httpx.ASGITransport(app=create_app(coordinator=owner))
    async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1') as client:
        response = await client.get(path)
        return response.status_code, response.json()


def dump(name, value):
    OUT[name] = value
    print(f'\n### {name}\n' + json.dumps(value, indent=1, sort_keys=True, default=str))


def test_harness_is_network_silent():
    with pytest.raises(AssertionError, match='Offline tests may only use explicitly marked loopback HTTP'):
        socket.create_connection(('example.com', 443), timeout=1)


# ----------------------------------------------------------------------------- (1a) a lost request that recovers

@pytest.mark.parametrize('protocol', [DISCOVERY_V1, DISCOVERY_V2])
def test_explorer_loses_twice_then_answers_and_the_operator_sees_it_everywhere(owner, monkeypatch, protocol):
    clock = virtual_clock(monkeypatch)
    campaign = learn_campaign(owner, protocol)
    id = campaign.campaign_id
    plan = read_run_plan(owner.store, campaign)['plan']
    assert plan['transport_retry'] == declaration_v2(plan['episode_budget']['actor_calls'])
    provider = Flaky(answer, failing={1, 2})
    final, ledger, runner = execute(owner, campaign, provider)
    # The campaign ran to its normal end, not ERROR.
    assert final.state == 'NO_CHANGE', final.terminal_reason
    assert not owner.store.list_records('execution_errors')
    # The product's own wait ran 5 s then 20 s, in 0.5 s steps.
    assert clock.total == 25.0 and set(clock.steps) == {0.5} and len(clock.steps) == 50
    records = v2_records(owner.store, id)
    assert [(r['attempt'], r['retry_delay_seconds'], r['campaign_retry_number'], r['role'], r['request']['phase'],
             r['charged_model_calls']) for r in records] == [(1, 5, 1, 'explorer', 'discovery', 1), (2, 20, 2, 'explorer', 'discovery', 1)]
    # Budget: every attempt charged, on the ledger and on the API's budget view.
    status, budget = asyncio.run(api_get(owner, f'/api/campaigns/{id}/budget'))
    assert status == 200 and budget['used_calls'] == ledger.used_calls == provider.sent == len(provider.contexts) + 2
    # Dashboard (fault-search panel data): the retried selection lists both retries in order.
    status, rows = asyncio.run(api_get(owner, f'/api/campaigns/{id}/search-attempts'))
    retried = [row for row in rows if row['transport_retries']]
    assert status == 200 and len(retried) == 1 and retried[0]['usage']['model_calls'] == 3
    assert [(t['attempt'], t['retry_delay_seconds'], t['protocol']) for t in retried[0]['transport_retries']] == [
        (1, 5, TRANSPORT_RETRY_PROTOCOL_V2), (2, 20, TRANSPORT_RETRY_PROTOCOL_V2)]
    # Campaign state as the dashboard reads it.
    status, shown = asyncio.run(api_get(owner, f'/api/campaigns/{id}'))
    assert status == 200 and shown['state'] == 'NO_CHANGE'
    # Recording download (the fake runner's minimal episodes are not exportable, as in the builder's test).
    with owner.store.transaction() as db:
        db.execute("DELETE FROM records WHERE kind='episodes' AND json_extract(payload,'$.campaign_id')=?", (id,))
    recording = development_recording(owner.store, id)
    assert [(r['attempt'], r['retry_delay_seconds']) for r in recording['transport_retries']] == [(1, 5), (2, 20)]
    assert recording['run_plan']['plan']['transport_retry']['protocol'] == TRANSPORT_RETRY_PROTOCOL_V2
    dump(f'1a-{protocol}', {'state': final.state, 'terminal_reason': final.terminal_reason, 'virtual_wait_seconds': clock.total,
                            'records': [{k: r[k] for k in ('attempt', 'retry_delay_seconds', 'campaign_retry_number', 'role', 'request')}
                                        for r in records],
                            'budget_used_calls': budget['used_calls'], 'requests_sent': provider.sent,
                            'search_attempt_retries': retried[0]['transport_retries'], 'selection_model_calls': retried[0]['usage']['model_calls']})


# ----------------------------------------------------------------------------- (1b) when retries run out

def test_all_three_retries_fail_error_message(owner, monkeypatch):
    clock = virtual_clock(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V1)
    provider = Flaky(answer, failing={1, 2, 3, 4})
    final, ledger, runner = execute(owner, campaign, provider)
    assert final.state == 'ERROR'
    assert final.terminal_reason == ('CONNECTION_ERROR: A model request failed after 3 transport retries (waits of 5 s, 20 s, '
                                     '60 s); every allowed retry of this request failed. Inspect the saved provider diagnostics.')
    error, = owner.store.list_records('execution_errors')
    assert error['transport_retries']['reason'] == 'ALL_RETRIES_FAILED' and clock.total == 85.0
    assert provider.sent == ledger.used_calls == 4
    dump('1b-all-retries-failed', {'terminal_reason': final.terminal_reason, 'execution_error': error, 'virtual_wait_seconds': clock.total})


def test_campaign_cap_of_twelve_through_the_real_coordinator(owner, monkeypatch):
    """Discovery v2 declares 16 discovery retries, so the campaign cap (12) binds first: six slots lose twice each."""
    clock = virtual_clock(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V2)
    provider = Flaky(answer, failing={n for n in range(1, 60) if n % 3 != 0})
    final, ledger, runner = execute(owner, campaign, provider)
    records = v2_records(owner.store, campaign.campaign_id)
    assert final.state == 'ERROR', final.terminal_reason
    assert len(records) == 12 and [r['campaign_retry_number'] for r in records] == list(range(1, 13))
    error, = owner.store.list_records('execution_errors')
    assert error['transport_retries']['reason'] == 'CAMPAIGN_RETRY_LIMIT'
    assert provider.sent == ledger.used_calls
    dump('1b-campaign-cap', {'terminal_reason': final.terminal_reason, 'execution_error_transport_retries': error['transport_retries'],
                             'records': len(records), 'requests_sent': provider.sent, 'virtual_wait_seconds': clock.total})


def test_discovery_bound_message(owner, monkeypatch):
    virtual_clock(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V1)       # declared discovery bound 8
    provider = Flaky(answer, failing={n for n in range(1, 60) if n % 3 != 0})
    final, ledger, runner = execute(owner, campaign, provider)
    assert final.state == 'ERROR'
    error, = owner.store.list_records('execution_errors')
    assert error['transport_retries']['reason'] == 'DISCOVERY_RETRY_LIMIT' and len(v2_records(owner.store, campaign.campaign_id)) == 8
    dump('1b-discovery-bound', {'terminal_reason': final.terminal_reason})


def test_budget_refusal_message_and_whether_it_waited_first(owner, monkeypatch):
    clock = virtual_clock(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V1)
    provider = Flaky(answer, failing={1})
    final, ledger, runner = execute(owner, campaign, provider, headroom=1)
    assert final.state == 'ERROR' and provider.sent == 1
    error, = owner.store.list_records('execution_errors')
    assert error['transport_retries']['reason'] == 'BUDGET_REFUSED'
    dump('1b-budget-refused', {'terminal_reason': final.terminal_reason, 'waited_virtual_seconds_before_refusal': clock.total})


# ----------------------------------------------------------------------------- (1c) Stop during a real wait

@pytest.mark.parametrize('stop_after', [0.3, 1.2, 3.7])
def test_stop_during_a_real_backoff_wait_is_prompt(owner, monkeypatch, stop_after):
    campaign = learn_campaign(owner, DISCOVERY_V1)
    id = campaign.campaign_id
    provider = Flaky(answer, failing=set(range(1, 10)))
    real_wait = transport_retry.cancellable_wait
    timing = {}

    async def wait_then_stop(seconds, stopped, **kwargs):
        async def press_stop():
            await asyncio.sleep(stop_after)
            timing['stop'] = time.monotonic()
            await owner.stop(id)
        presser = asyncio.create_task(press_stop())
        timing['wait_started'] = time.monotonic()
        try:
            return await real_wait(seconds, stopped, **kwargs)
        finally:
            timing['wait_ended'] = time.monotonic()
            await presser
    monkeypatch.setattr(transport_retry, 'cancellable_wait', wait_then_stop)
    started = time.monotonic()
    final, ledger, runner = execute(owner, campaign, provider)
    ended = time.monotonic()
    status, shown = asyncio.run(api_get(owner, f'/api/campaigns/{id}'))
    assert final.state == 'STOPPED' and shown['state'] == 'STOPPED'
    assert 'waited to be re-sent' in final.terminal_reason
    assert not owner.store.list_records('execution_errors') and not owner.store.list_records('transport_retries')
    assert provider.sent == ledger.used_calls == 1
    latency = timing['wait_ended'] - timing['stop']
    assert latency < 0.75, latency
    dump(f'1c-stop-{stop_after}', {'terminal_reason': final.terminal_reason, 'api_state': shown['state'],
                                   'stop_to_wait_end_seconds': round(latency, 3), 'whole_execute_seconds': round(ended - started, 3)})


def test_the_agent_role_keeps_rule_v1_in_a_rule_v2_campaign():
    """Nothing agent-side reads the plan's rule; the native bridge and reference Actor use v1's complete_with_one_retry."""
    import inspect
    from app.agents import actor
    from app.integrations import external_agent
    for module in (actor, external_agent):
        source = inspect.getsource(module)
        assert 'complete_with_backoff' not in source and 'lab_retry' not in source


def test_save_real_api_json_for_the_frontend_validators(owner, monkeypatch):
    """Saves the real API responses of a rule-v2 Learn campaign with backed-off retries (discovery v2, a 503 then a
    timeout then an answer) so the dashboard's own validators can be run on them (ui-check/)."""
    from pathlib import Path
    virtual_clock(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V2)
    id = campaign.campaign_id

    class Mixed(Flaky):
        async def complete(self, messages, **kwargs):
            self.sent += 1
            if self.sent == 1:
                raise RuntimeProviderError('scripted 503', code='HTTP_ERROR', http_status=503)
            if self.sent == 2:
                raise RuntimeProviderError('scripted timeout', code='REQUEST_TIMEOUT', error_class='APITimeoutError')
            return await super(Flaky, self).complete(messages, **kwargs)
    final, ledger, runner = execute(owner, campaign, Mixed(answer, failing=set()))
    assert final.state == 'NO_CHANGE', final.terminal_reason
    out = Path(__file__).resolve().parents[1] / 'ui-fixtures'
    out.mkdir(exist_ok=True)
    for name, path in (('plan', f'/api/campaigns/{id}/plan'), ('search-attempts', f'/api/campaigns/{id}/search-attempts'),
                       ('campaign', f'/api/campaigns/{id}'), ('budget', f'/api/campaigns/{id}/budget'), ('run-options', '/api/run-options')):
        status, body = asyncio.run(api_get(owner, path))
        assert status == 200, (name, body)
        (out / f'{name}.json').write_text(json.dumps(body, indent=1, sort_keys=True) + '\n')
    rows = json.loads((out / 'search-attempts.json').read_text())
    retried = [r for r in rows if r['transport_retries']]
    assert [(t['code'], t.get('http_status'), t['attempt'], t['retry_delay_seconds']) for t in retried[0]['transport_retries']] == [
        ('HTTP_ERROR', 503, 1, 5), ('REQUEST_TIMEOUT', None, 2, 20)]


def test_task_cancellation_during_a_wait_propagates_at_once():
    async def run():
        task = asyncio.create_task(transport_retry.cancellable_wait(60, lambda: False))
        await asyncio.sleep(0.2)
        started = time.monotonic(); task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return time.monotonic() - started
    elapsed = asyncio.run(run())
    dump('1h-cancel', {'cancel_to_end_seconds': round(elapsed, 4)})
    assert elapsed < 0.1
