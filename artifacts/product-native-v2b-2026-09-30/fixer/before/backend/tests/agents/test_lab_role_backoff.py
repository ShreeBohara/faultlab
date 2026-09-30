"""Rule v2 (faultlab-transport-retry/v2-lab-backoff): the Explorer and the Mechanic back off and retry.

Real Explorer/Mechanic, real RuntimeProvider and a real CampaignLedger; only the SDK client and the
waits are offline boundaries (asyncio.sleep is replaced, so no test sleeps for real except the one
promptness test, which waits well under a second). No provider, W&B or model call is made.
"""
import asyncio
import time

import pytest

from app.agents import transport_retry
from app.agents.transport_retry import (LAB_BACKOFF_SECONDS, LAB_RETRIES_PER_CAMPAIGN_MAX, TRANSPORT_RETRY_PROTOCOL_V2,
                                        LabBackoff, TransportRetryStopped, retry_failure_message)
from app.contracts.models import FaultSpec, MechanicNoChange
from app.lab.budgets import StopRequested
from app.lab.readiness import execution_failure
from app.providers.runtime import RuntimeProviderError

from test_role_transport_retry import (FORCED, NO_CHANGE, PICK, connection_error, only_selection, setup, timeout_error,
                                       v2_session)


@pytest.fixture
def anyio_backend(): return 'asyncio'


def backoff(h, *, discovery_max=8, used=0):
    """Give the harness's Explorer and Mechanic one campaign session, as the learning loop does."""
    lab = LabBackoff(h.store, 'campaign-own', stopped=lambda: h.ledger.stopped, discovery_retries_max=discovery_max)
    lab.used = used
    h.explorer.lab_retry = h.mechanic.lab_retry = lab
    return lab


def watch_sends(h):
    """Record, at the moment each request is handed to the provider, what the ledger and store already hold."""
    original, seen = h.provider.complete, []
    async def complete(messages, **kwargs):
        seen.append({'used_calls': h.ledger.used_calls, 'retry_records': len(h.retries())})
        return await original(messages, **kwargs)
    h.provider.complete = complete
    return seen


def retries_in_order(h):
    return sorted(h.retries(), key=lambda row: (row['recorded_at'], row['attempt']))


# ----------------------------------------------------------------------------- the schedule

@pytest.mark.anyio
@pytest.mark.parametrize('failures', [1, 2, 3])
async def test_explorer_fails_n_times_then_succeeds_with_waits_of_5_20_60(tmp_path, monkeypatch, failures):
    h = setup(tmp_path, monkeypatch, [connection_error() for _ in range(failures)] + [PICK])
    lab = backoff(h)
    ref, selected = await h.explorer.select(h.context)
    assert selected.fault_spec == FaultSpec.model_validate(FORCED)
    waits = list(LAB_BACKOFF_SECONDS[:failures])
    assert [seconds for _, _, seconds in lab.waits] == waits and [a for _, a, _ in lab.waits] == list(range(1, failures + 1))
    assert sum(h.delays) == sum(waits) and max(h.delays) <= transport_retry.WAIT_POLL_SECONDS   # waited in short steps
    assert len(h.requests) == h.ledger.used_calls == failures + 1
    assert all(request == h.requests[0] for request in h.requests)                      # the identical request each time
    records = retries_in_order(h)
    assert [(r['attempt'], r['retry_delay_seconds'], r['protocol'], r['campaign_retry_number']) for r in records] == [
        (n, LAB_BACKOFF_SECONDS[n - 1], TRANSPORT_RETRY_PROTOCOL_V2, n) for n in range(1, failures + 1)]
    assert all(r['request']['phase'] == 'discovery' and r['charged_model_calls'] == 1 and r['campaign_retries_max'] == 12
               for r in records)
    selection = only_selection(h)
    assert selection['selection_id'] == ref and selection['usage']['model_calls'] == failures + 1
    assert [(t['attempt'], t['retry_delay_seconds'], t['protocol']) for t in selection['transport_retries']] == [
        (r['attempt'], r['retry_delay_seconds'], r['protocol']) for r in records]
    assert lab.used == lab.discovery_used == failures
    h.store.close()


@pytest.mark.anyio
async def test_all_three_retries_fail_raises_the_original_failure_and_says_how_many_were_tried(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error() for _ in range(4)] + [PICK])
    lab = backoff(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.code == 'CONNECTION_ERROR'
    assert len(h.requests) == h.ledger.used_calls == 4 and len(h.retries()) == 3 and len(h.failures()) == 4
    assert [seconds for _, _, seconds in lab.waits] == [5, 20, 60]
    summary = caught.value.transport_retry_summary
    assert summary == {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'explorer', 'retries_tried': 3,
                       'waits_seconds': [5, 20, 60], 'reason': 'ALL_RETRIES_FAILED'}
    failure = execution_failure(caught.value)
    assert failure['code'] == 'CONNECTION_ERROR' and failure['transport_retries'] == summary
    assert failure['message'] == ('A model request failed after 3 transport retries (waits of 5 s, 20 s, 60 s); every allowed '
                                  'retry of this request failed. Inspect the saved provider diagnostics.')
    assert not h.store.list_records('selections')
    h.store.close()


@pytest.mark.anyio
async def test_503_waits_the_backoff_not_one_second_and_timeouts_are_retried_too(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [503, timeout_error(), PICK])
    lab = backoff(h)
    await h.explorer.select(h.context)
    first, second = retries_in_order(h)
    assert (first['code'], first['http_status'], first['retry_delay_seconds']) == ('HTTP_ERROR', 503, 5)
    assert (second['code'], second['retry_delay_seconds'], 'http_status' in second) == ('REQUEST_TIMEOUT', 20, False)
    assert [seconds for _, _, seconds in lab.waits] == [5, 20] and sum(h.delays) == 25
    h.store.close()


# ----------------------------------------------------------------------------- never after an answer

@pytest.mark.anyio
@pytest.mark.parametrize('malformed', [False, True])
async def test_a_returned_empty_or_malformed_answer_is_never_retried(tmp_path, monkeypatch, malformed):
    from types import SimpleNamespace
    response = SimpleNamespace(choices=[] if malformed else [SimpleNamespace(finish_reason='length', message=SimpleNamespace(content=None))],
                               usage=SimpleNamespace(prompt_tokens=7, completion_tokens=2000))
    h = setup(tmp_path, monkeypatch, [response, PICK])
    lab = backoff(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries() and lab.waits == [] and h.delays == []
    assert not hasattr(caught.value, 'transport_retry_summary')          # rule v1's message is kept
    assert execution_failure(caught.value)['message'] == 'A model request failed; inspect the saved provider diagnostics.'
    h.store.close()


@pytest.mark.anyio
async def test_an_answer_after_a_lost_connection_is_not_re_rolled(tmp_path, monkeypatch):
    from types import SimpleNamespace
    empty = SimpleNamespace(choices=[SimpleNamespace(finish_reason='length', message=SimpleNamespace(content=None))],
                            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=2000))
    h = setup(tmp_path, monkeypatch, [connection_error(), empty, PICK])
    backoff(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.code == 'EMPTY_FINAL_RESPONSE' and len(h.requests) == h.ledger.used_calls == 2
    assert caught.value.transport_retry_summary['reason'] == 'NOT_RETRYABLE'
    assert caught.value.transport_retry_summary['retries_tried'] == 1
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('status', [400, 401, 429, 500, 502, 504])
async def test_other_http_statuses_are_never_retried_and_never_wait(tmp_path, monkeypatch, status):
    h = setup(tmp_path, monkeypatch, [status, PICK])
    lab = backoff(h)
    with pytest.raises(RuntimeProviderError):
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries() and lab.waits == [] and h.delays == []
    h.store.close()


# ----------------------------------------------------------------------------- charged before sent

@pytest.mark.anyio
async def test_each_retry_is_charged_and_recorded_before_it_is_sent(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), PICK])
    backoff(h)
    seen = watch_sends(h)
    await h.explorer.select(h.context)
    # Request k (0-based) is sent only after it was charged (k + 1 calls) and its retry record written (k records).
    assert seen == [{'used_calls': 1, 'retry_records': 0}, {'used_calls': 2, 'retry_records': 1},
                    {'used_calls': 3, 'retry_records': 2}]
    assert h.ledger.used_dollar_upper_bound == pytest.approx(3 * .03)
    h.store.close()


@pytest.mark.anyio
async def test_a_retry_the_budget_cannot_cover_is_not_sent_and_the_original_failure_stands(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), PICK], calls=2, tokens=2 * 34000)
    backoff(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.code == 'CONNECTION_ERROR' and len(h.requests) == h.ledger.used_calls == 2
    assert caught.value.transport_retry_summary['reason'] == 'BUDGET_REFUSED'
    assert caught.value.transport_retry_summary['retries_tried'] == 1 and len(h.retries()) == 1
    h.store.close()


@pytest.mark.anyio
async def test_a_retry_never_draws_on_a_batch_reservation(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK], calls=2, tokens=2 * 34000, reserve=2)
    backoff(h)
    with pytest.raises(RuntimeProviderError):
        await h.explorer.select(h.context, reservation='batch')
    assert len(h.requests) == h.ledger.used_calls == 1 and h.ledger.reservations['batch']['calls'] == 1
    h.store.close()


# ----------------------------------------------------------------------------- caps

@pytest.mark.anyio
async def test_the_campaign_cap_of_12_counts_every_lab_role_retry(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), PICK])
    lab = backoff(h, used=LAB_RETRIES_PER_CAMPAIGN_MAX - 1)        # 11 already used in this campaign
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 2 and lab.used == 12
    assert caught.value.transport_retry_summary['reason'] == 'CAMPAIGN_RETRY_LIMIT'
    assert 'limit of 12 lab-role transport retries was reached' in retry_failure_message(caught.value.transport_retry_summary)
    h.store.close()


@pytest.mark.anyio
async def test_the_campaign_count_is_read_from_the_store_so_it_holds_for_every_role(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), NO_CHANGE])
    for n in range(LAB_RETRIES_PER_CAMPAIGN_MAX):   # 12 earlier rule-v2 retries of this campaign (any role)
        h.store.put_record('transport_retries', f'transport-retry-{n}', {'retry_id': f'transport-retry-{n}', 'campaign_id': 'campaign-own',
                           'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'explorer', 'request': {'phase': 'discovery'}})
    h.store.put_record('transport_retries', 'transport-retry-v1', {'campaign_id': 'campaign-own', 'protocol': 'faultlab-transport-retry/v1'})
    lab = LabBackoff(h.store, 'campaign-own', stopped=lambda: False, discovery_retries_max=16)
    assert (lab.used, lab.discovery_used) == (12, 12)                  # rule-v1 records are not counted
    h.mechanic.lab_retry = lab
    with pytest.raises(RuntimeProviderError) as caught:
        await h.mechanic.propose({'campaign_id': 'campaign-own'})
    assert caught.value.transport_retry_summary == {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'mechanic', 'retries_tried': 0,
                                                    'waits_seconds': [], 'reason': 'CAMPAIGN_RETRY_LIMIT'}
    assert len(h.requests) == h.ledger.used_calls == 1 and h.delays == []   # no wait when no retry can follow
    h.store.close()


@pytest.mark.anyio
async def test_discovery_also_keeps_the_plans_declared_explorer_bound_but_challenge_does_not(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK])
    lab = backoff(h, discovery_max=1)
    lab.discovery_used = 1
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.transport_retry_summary['reason'] == 'DISCOVERY_RETRY_LIMIT' and len(h.requests) == 1
    h.store.close()
    # A challenge selection is not a discovery request: only the campaign cap applies.
    h = setup(tmp_path / 'challenge', monkeypatch, [connection_error(), PICK])
    lab = backoff(h, discovery_max=1)
    lab.discovery_used = 1
    challenge = {'campaign_id': 'campaign-own', 'purpose': 'challenge', 'proposal_index': 0}
    _, selected = await h.explorer.select(challenge, challenge=True)
    retry, = h.retries()
    assert selected is not None and retry['request']['phase'] == 'challenge' and retry['request']['challenge'] is True
    assert (lab.used, lab.discovery_used) == (1, 1)
    h.store.close()


@pytest.mark.anyio
async def test_discovery_v2_session_counts_the_same_retries(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), PICK])
    session = v2_session(h.store)
    lab = backoff(h, discovery_max=session.block['explorer_transport_retries_max'])
    _, selected = await h.explorer.select({**h.context, 'slot_request': 1}, discovery_v2=session)
    assert selected is not None and session.explorer_requests == 1          # retries are not selection requests
    assert session.transport_retries == lab.discovery_used == 2
    assert [r['request']['slot_request'] for r in retries_in_order(h)] == [1, 1]
    h.store.close()


# ----------------------------------------------------------------------------- stop during a wait

@pytest.mark.anyio
async def test_a_stop_during_a_wait_ends_it_at_once_uncharged_and_unsent(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK])
    lab = backoff(h)
    steps = []
    async def stop_on_third_step(seconds):
        steps.append(seconds)
        if len(steps) == 3: h.ledger.stopped = True         # what LabCoordinator.stop sets
    monkeypatch.setattr(transport_retry.asyncio, 'sleep', stop_on_third_step)
    with pytest.raises(TransportRetryStopped) as caught:
        await h.explorer.select(h.context)
    assert isinstance(caught.value, StopRequested)
    assert str(caught.value) == ('External stop requested while a failed Explorer model request waited to be re-sent '
                                 '(transport retry backoff); it was not sent again. Remote effects are retained.')
    assert steps == [.5, .5, .5]                               # noticed at the next check, not after 5 s
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries() and lab.waits == []
    assert len(h.failures()) == 1                              # the original failure stays recorded
    h.store.close()


@pytest.mark.anyio
async def test_a_stop_already_requested_ends_without_any_wait_for_the_mechanic_too(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), NO_CHANGE])
    backoff(h)
    original = h.store.put_record
    def stop_on_failure(kind, *args, **kwargs):
        if kind == 'provider_failures': h.ledger.stopped = True
        return original(kind, *args, **kwargs)
    h.store.put_record = stop_on_failure
    with pytest.raises(TransportRetryStopped, match='failed Mechanic model request'):
        await h.mechanic.diagnose({'campaign_id': 'campaign-own', 'evidence_ids': [], 'intervention_ids': []})
    assert len(h.requests) == h.ledger.used_calls == 1 and h.delays == [] and not h.retries()
    h.store.close()


@pytest.mark.anyio
async def test_a_real_wait_notices_a_stop_promptly():
    stopped = False
    async def press_stop():
        nonlocal stopped
        await asyncio.sleep(.2); stopped = True
    started = time.monotonic()
    presser = asyncio.create_task(press_stop())
    assert await transport_retry.cancellable_wait(60, lambda: stopped) is True
    await presser
    assert time.monotonic() - started < 2.0          # the Stop came at 0.2 s; the wait checks every 0.5 s
    assert await transport_retry.cancellable_wait(0, lambda: False) is False


# ----------------------------------------------------------------------------- Mechanic requests

@pytest.mark.anyio
@pytest.mark.parametrize('kind', ['diagnose', 'propose'])
async def test_mechanic_diagnosis_and_candidate_requests_back_off(tmp_path, monkeypatch, kind):
    answer = ({'proposed_kind': 'INCONCLUSIVE', 'hypothesis': 'Scripted.', 'evidence_ids': ['evidence-1'], 'requested_intervention_id': None}
              if kind == 'diagnose' else NO_CHANGE)
    h = setup(tmp_path, monkeypatch, [connection_error(), 503, answer])
    lab = backoff(h)
    call = (h.mechanic.diagnose({'campaign_id': 'campaign-own', 'evidence_ids': ['evidence-1'], 'intervention_ids': []}) if kind == 'diagnose'
            else h.mechanic.propose({'campaign_id': 'campaign-own'}))
    ref, result, raws = await call
    assert result is not None and len(raws) == 1
    assert [seconds for _, _, seconds in lab.waits] == [5, 20] and lab.discovery_used == 0
    records = retries_in_order(h)
    expected_kind = 'mechanic_diagnosis' if kind == 'diagnose' else 'mechanic_proposal'
    assert [(r['role'], r['request']['kind'], r['attempt']) for r in records] == [('mechanic', expected_kind, 1), ('mechanic', expected_kind, 2)]
    output = h.store.get_record('mechanic_outputs', ref)
    assert output['usage']['model_calls'] == 3 and [t['retry_delay_seconds'] for t in output['transport_retries']] == [5, 20]
    assert len(h.requests) == h.ledger.used_calls == 3
    h.store.close()


@pytest.mark.anyio
async def test_without_a_session_the_explorer_and_mechanic_keep_rule_v1(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), PICK])
    assert h.explorer.lab_retry is None and h.mechanic.lab_retry is None
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 2 and h.delays == []
    retry, = h.retries()
    assert retry['protocol'] == 'faultlab-transport-retry/v1' and 'retry_delay_seconds' not in retry
    assert not hasattr(caught.value, 'transport_retry_summary')
    h.store.close()


def test_the_declared_rule_v2():
    rule = transport_retry.declaration_v2(8)
    assert rule['protocol'] == TRANSPORT_RETRY_PROTOCOL_V2 and rule['agent_roles'] == ['actor']
    assert (rule['agent_retries_per_request'], rule['service_unavailable_delay_seconds'], rule['actor_retries_per_episode_max']) == (1, 1, 8)
    assert (rule['lab_roles'], rule['lab_retries_per_request'], rule['lab_backoff_seconds'], rule['lab_retries_per_campaign_max']) == (
        ['explorer', 'mechanic'], 3, [5, 20, 60], 12)
    assert rule['stop_during_wait'] == 'STOPPED' and rule['rule'] == transport_retry.RULE_V2
    # Rule v1 is unchanged: every older plan and the agent roles still use exactly it.
    assert transport_retry.declaration(8)['protocol'] == 'faultlab-transport-retry/v1'
    assert transport_retry.RETRIES_PER_REQUEST == 1
