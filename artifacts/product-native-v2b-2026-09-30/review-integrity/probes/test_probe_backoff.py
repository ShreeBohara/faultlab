"""Integrity reviewer's independent probe of transport retry rule v2 (lab-role backoff). Offline, $0.

Real Explorer / Mechanic / RuntimeProvider / CampaignLedger / LabStore (the older, already-reviewed harness in
tests/agents/test_role_transport_retry.py supplies a fake SDK client). Checks written by the reviewer, not the builder.
"""
import asyncio
import time

import pytest

from app.agents import transport_retry
from app.agents.explorer import Explorer
from app.agents.mechanic import Mechanic
from app.agents.transport_retry import (TRANSPORT_RETRY_PROTOCOL, TRANSPORT_RETRY_PROTOCOL_V2, LabBackoff,
                                        TransportRetryStopped)
from app.contracts.models import canonical_json
from app.lab.budgets import StopRequested
from app.lab.readiness import execution_failure
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError

from test_role_transport_retry import NO_CHANGE, PICK, MODEL, connection_error, setup, timeout_error

REAL_SLEEP = asyncio.sleep


@pytest.fixture
def anyio_backend(): return 'asyncio'


def session(h, *, discovery_max=8, campaign='campaign-own'):
    lab = LabBackoff(h.store, campaign, stopped=lambda: h.ledger.stopped, discovery_retries_max=discovery_max)
    h.explorer.lab_retry = h.mechanic.lab_retry = lab
    return lab


def event_log(h):
    """One chronological log of ledger charges, store writes of retry records, and requests handed to the SDK."""
    log = []
    consume = h.ledger.consume_call
    def charged(*args, **kwargs):
        result = consume(*args, **kwargs); log.append(('charge', kwargs.get('role'), kwargs.get('reservation'))); return result
    h.ledger.consume_call = charged
    put = h.store.put_record
    def put_record(kind, *args, **kwargs):
        if kind in ('transport_retries', 'provider_failures'): log.append(('record', kind))
        return put(kind, *args, **kwargs)
    h.store.put_record = put_record
    complete = h.provider.complete
    async def sent(messages, **kwargs):
        log.append(('send',)); return await complete(messages, **kwargs)
    h.provider.complete = sent
    return log


# ---------------------------------------------------------------- 1. never re-roll an answer (generation attached)

class AnsweredButFailed:
    """A provider whose failure carries a generation (an answer arrived), with a transport-looking code."""
    def __init__(self, code, status=None):
        self.code, self.status, self.calls = code, status, 0
    def role_model(self, role): return MODEL
    async def complete(self, messages, **kwargs):
        self.calls += 1
        raise RuntimeProviderError('answered', code=self.code, http_status=self.status,
                                   generation=RuntimeGeneration('{"partial":', MODEL, 10, 5))


@pytest.mark.anyio
@pytest.mark.parametrize('code,status', [('CONNECTION_ERROR', None), ('REQUEST_TIMEOUT', None), ('HTTP_ERROR', 503)])
@pytest.mark.parametrize('role', ['explorer', 'mechanic'])
async def test_failure_with_a_generation_is_never_retried(tmp_path, monkeypatch, code, status, role):
    h = setup(tmp_path, monkeypatch, [PICK])
    provider = AnsweredButFailed(code, status)
    h.explorer, h.mechanic = Explorer(provider, h.store, h.ledger), Mechanic(provider, h.store, h.ledger)
    lab = session(h)
    with pytest.raises(RuntimeProviderError) as caught:
        if role == 'explorer': await h.explorer.select(h.context)
        else: await h.mechanic.propose({'campaign_id': 'campaign-own'})
    assert provider.calls == 1 and h.delays == [] and not h.retries() and lab.used == 0
    assert not hasattr(caught.value, 'transport_retry_summary')          # rule v1's message, untouched
    assert execution_failure(caught.value)['message'] == 'A model request failed; inspect the saved provider diagnostics.'
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('status', [400, 401, 403, 404, 409, 422, 429, 500, 502, 504])
async def test_other_statuses_never_wait_or_retry(tmp_path, monkeypatch, status):
    h = setup(tmp_path, monkeypatch, [status, PICK])
    lab = session(h)
    with pytest.raises(RuntimeProviderError):
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 1 and h.delays == [] and not h.retries() and lab.used == 0
    h.store.close()


# ---------------------------------------------------------------- 2. charge -> record -> send, for every retry

@pytest.mark.anyio
@pytest.mark.parametrize('role', ['explorer', 'mechanic'])
async def test_each_retry_is_charged_then_recorded_then_sent(tmp_path, monkeypatch, role):
    h = setup(tmp_path, monkeypatch, [connection_error(), timeout_error(), 503, (PICK if role == 'explorer' else NO_CHANGE)])
    lab = session(h)
    log = event_log(h)
    if role == 'explorer': await h.explorer.select(h.context)
    else: await h.mechanic.propose({'campaign_id': 'campaign-own'})
    kinds = [e[0] if e[0] != 'record' else e[1] for e in log]
    # first attempt: charge, send, failure;  each retry: charge (unreserved), retry record, send
    assert kinds == ['charge', 'send', 'provider_failures',
                     'charge', 'transport_retries', 'send', 'provider_failures',
                     'charge', 'transport_retries', 'send', 'provider_failures',
                     'charge', 'transport_retries', 'send'], kinds
    assert [e for e in log if e[0] == 'charge'][1:] == [('charge', role, None)] * 3      # never from a reservation
    assert len(h.requests) == h.ledger.used_calls == 4 and all(r == h.requests[0] for r in h.requests)
    assert sum(h.delays) == 85 and [r['retry_delay_seconds'] for r in sorted(h.retries(), key=lambda r: r['attempt'])] == [5, 20, 60]
    assert lab.used == 3
    h.store.close()


# ---------------------------------------------------------------- 3. caps

@pytest.mark.anyio
async def test_three_retries_per_request_then_the_original_failure_with_a_count(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error()] * 5)
    session(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.mechanic.diagnose({'campaign_id': 'campaign-own', 'evidence_ids': [], 'intervention_ids': []})
    assert len(h.requests) == h.ledger.used_calls == 4
    failure = execution_failure(caught.value)
    assert failure['code'] == 'CONNECTION_ERROR'
    assert failure['message'] == ('A model request failed after 3 transport retries (waits of 5 s, 20 s, 60 s); every allowed '
                                  'retry of this request failed. Inspect the saved provider diagnostics.')
    assert failure['transport_retries'] == {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'mechanic', 'retries_tried': 3,
                                            'waits_seconds': [5, 20, 60], 'reason': 'ALL_RETRIES_FAILED'}
    assert 'private SDK' not in canonical_json(failure)
    h.store.close()


@pytest.mark.anyio
async def test_campaign_cap_counts_only_this_campaigns_v2_records_across_roles(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error()] * 3 + [NO_CHANGE])
    # 11 rule-v2 retries already recorded for this campaign (mixed roles), plus records that must NOT count.
    for n in range(11):
        h.store.put_record('transport_retries', f'own-{n}', {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'campaign_id': 'campaign-own',
                           'role': 'explorer' if n % 2 else 'mechanic', 'request': {'phase': 'challenge'}}, immutable=True)
    for n in range(5):
        h.store.put_record('transport_retries', f'other-{n}', {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'campaign_id': 'campaign-other',
                           'request': {}}, immutable=True)
        h.store.put_record('transport_retries', f'v1-{n}', {'protocol': TRANSPORT_RETRY_PROTOCOL, 'campaign_id': 'campaign-own',
                           'request': {}}, immutable=True)
    lab = session(h)
    assert lab.used == 11 and lab.discovery_used == 0
    with pytest.raises(RuntimeProviderError) as caught:
        await h.mechanic.propose({'campaign_id': 'campaign-own'})
    assert len(h.requests) == h.ledger.used_calls == 2 and h.delays and sum(h.delays) == 5     # exactly one more (the 12th)
    assert caught.value.transport_retry_summary['reason'] == 'CAMPAIGN_RETRY_LIMIT'
    assert caught.value.transport_retry_summary['retries_tried'] == 1
    twelfth, = [r for r in h.retries() if r.get('provider_failure_id')]
    assert twelfth['campaign_retry_number'] == 12 and twelfth['campaign_retries_max'] == 12
    # a later, fresh session of the same campaign (e.g. after Continue) reads 12 from the store and allows none
    mechanic = Mechanic(h.provider, h.store, h.ledger)
    lab2 = LabBackoff(h.store, 'campaign-own', stopped=lambda: False, discovery_retries_max=8)
    mechanic.lab_retry = lab2
    assert lab2.used == 12
    with pytest.raises(RuntimeProviderError) as again:
        await mechanic.propose({'campaign_id': 'campaign-own'})
    assert len(h.requests) == 3 and again.value.transport_retry_summary == {
        'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'mechanic', 'retries_tried': 0, 'waits_seconds': [], 'reason': 'CAMPAIGN_RETRY_LIMIT'}
    assert execution_failure(again.value)['message'].startswith('A model request failed after 0 transport retries;')
    h.store.close()


@pytest.mark.anyio
async def test_discovery_bound_limits_discovery_only(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error()] * 4 + [PICK])
    lab = session(h, discovery_max=2)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)                    # discovery: bound 2
    assert caught.value.transport_retry_summary['reason'] == 'DISCOVERY_RETRY_LIMIT' and len(h.requests) == 3
    # a challenge selection of the same campaign is not bound by the discovery number (campaign cap still applies)
    challenge = {'campaign_id': 'campaign-own', 'configuration_hash': h.context['configuration_hash'],
                 'policy_hash': h.context['policy_hash'], 'selection_index': 0}
    # (the harness indexes its scripted responses by request count, so requests are not cleared)
    await h.explorer.select(challenge, challenge=True)
    phases = sorted(r['request']['phase'] for r in h.retries())
    assert phases == ['challenge', 'discovery', 'discovery'] and lab.used == 3 and lab.discovery_used == 2
    h.store.close()


@pytest.mark.anyio
async def test_budget_refusal_sends_nothing_more(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK], calls=1, tokens=34000)
    session(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries()
    assert caught.value.transport_retry_summary['reason'] == 'BUDGET_REFUSED'
    # observation: the refusal is decided after the 5-second wait, not before it
    print('budget refusal waited', sum(h.delays), 's before refusing')
    h.store.close()


# ---------------------------------------------------------------- 4. Stop during a REAL wait (no patched sleep)

@pytest.mark.anyio
@pytest.mark.parametrize('role', ['explorer', 'mechanic'])
async def test_stop_during_a_real_wait(tmp_path, monkeypatch, role):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK if role == 'explorer' else NO_CHANGE])
    monkeypatch.setattr(transport_retry.asyncio, 'sleep', REAL_SLEEP)       # undo the harness's instant sleep
    session(h)
    stamps = {}
    async def press():
        await REAL_SLEEP(1.3); stamps['stop'] = time.monotonic(); h.ledger.stopped = True
    presser = asyncio.create_task(press())
    started = time.monotonic()
    with pytest.raises(TransportRetryStopped) as caught:
        if role == 'explorer': await h.explorer.select(h.context)
        else: await h.mechanic.propose({'campaign_id': 'campaign-own'})
    ended = time.monotonic(); await presser
    assert isinstance(caught.value, StopRequested)
    assert ended - stamps['stop'] < 0.75, ended - stamps['stop']            # next 0.5 s poll, not the 5 s end
    assert ended - started < 2.5
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries()
    print(role, 'stop->end seconds', round(ended - stamps['stop'], 3))
    h.store.close()


@pytest.mark.anyio
async def test_stop_arriving_exactly_as_the_wait_finishes_is_not_charged(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK])
    lab = session(h)
    steps = []
    async def sleep(seconds):
        steps.append(seconds)
        if sum(steps) >= 5: h.ledger.stopped = True          # during the very last poll step
    monkeypatch.setattr(transport_retry.asyncio, 'sleep', sleep)
    with pytest.raises(TransportRetryStopped):
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries() and lab.used == 0
    h.store.close()


# ---------------------------------------------------------------- 5. without a session: rule v1 exactly

@pytest.mark.anyio
async def test_no_session_is_rule_v1(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), NO_CHANGE])
    with pytest.raises(RuntimeProviderError) as caught:
        await h.mechanic.propose({'campaign_id': 'campaign-own'})
    assert len(h.requests) == h.ledger.used_calls == 2 and h.delays == []
    retry, = h.retries()
    assert retry['protocol'] == TRANSPORT_RETRY_PROTOCOL and set(retry) >= {'attempt', 'code'} and 'campaign_retry_number' not in retry
    assert execution_failure(caught.value)['message'] == 'A model request failed; inspect the saved provider diagnostics.'
    h.store.close()


# ---------------------------------------------------------------- negative controls (REVIEW_MUTANT=...): the probe must fail
import os as _os


@pytest.fixture(autouse=True)
def _review_mutant(monkeypatch):
    mutant = _os.environ.get('REVIEW_MUTANT')
    if mutant == 'reroll_answers':
        monkeypatch.setattr(transport_retry, 'blind_retry_allowed', lambda error: error.code in ('CONNECTION_ERROR', 'REQUEST_TIMEOUT')
                            or (error.code == 'HTTP_ERROR' and error.http_status == 503))
    elif mutant == 'no_charge':
        import app.agents.explorer as explorer_module, app.agents.mechanic as mechanic_module
        monkeypatch.setattr(explorer_module, 'charge_ledger_retry', lambda ledger, role: True)
        monkeypatch.setattr(mechanic_module, 'charge_ledger_retry', lambda ledger, role: True)
    elif mutant == 'stop_ignored':
        async def wait(seconds, stopped, *, poll=None):
            await transport_retry.asyncio.sleep(seconds); return False
        monkeypatch.setattr(transport_retry, 'cancellable_wait', wait)
    elif mutant == 'no_campaign_cap':
        monkeypatch.setattr(transport_retry, 'LAB_RETRIES_PER_CAMPAIGN_MAX', 99)
    yield
