"""Rule v2 (lab-role backoff): the September 30 review fixes (findings LOW-2 and P-4).

1. A retry the campaign's unreserved budget cannot cover is refused BEFORE its backoff wait (nothing is charged,
   nothing is sent, the run does not wait 5, 20 or 60 s for nothing). The charge after a wait stays the only admission.
2. When no retry was sent at all, the failure message says so plainly instead of "after 0 transport retries".
3. The read-only budget check (transport_retry.ledger_retry_fits) agrees with the real admission
   (CampaignLedger.consume_call through charge_ledger_retry) on every ledger state tried here. budgets.py is part of the
   frozen interpreter hash, so the check mirrors it instead of changing it; this test keeps the two in step.

Real Explorer, Mechanic, RuntimeProvider and CampaignLedger; only the SDK client and asyncio.sleep are offline
boundaries (see test_role_transport_retry.setup). No provider, W&B or model call is made.
"""
import itertools
from types import SimpleNamespace

import pytest

from app.agents import transport_retry
from app.agents.transport_retry import (TRANSPORT_RETRY_PROTOCOL_V2, LabBackoff, TransportRetryStopped, charge_ledger_retry,
                                        ledger_retry_fits, retry_failure_message)
from app.contracts.models import CampaignBudget
from app.lab.budgets import PROTECTED, CampaignLedger
from app.lab.readiness import execution_failure
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeProviderError

from test_role_transport_retry import NO_CHANGE, PICK, connection_error, setup


@pytest.fixture
def anyio_backend(): return 'asyncio'


def backoff(h, *, discovery_max=8):
    lab = LabBackoff(h.store, 'campaign-own', stopped=lambda: h.ledger.stopped, discovery_retries_max=discovery_max)
    h.explorer.lab_retry = h.mechanic.lab_retry = lab
    return lab


# ----------------------------------------------------------------------------- 1. no wait for a retry that cannot be paid

@pytest.mark.anyio
async def test_explorer_retry_the_budget_cannot_cover_is_refused_before_any_wait(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK], calls=1, tokens=34000)   # room for the first request only
    lab = backoff(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.code == 'CONNECTION_ERROR'
    assert h.delays == [] and lab.waits == []                         # no 5 s wait before refusing
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries() and len(h.failures()) == 1
    assert caught.value.transport_retry_summary == {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'explorer', 'retries_tried': 0,
                                                    'waits_seconds': [], 'reason': 'BUDGET_REFUSED'}
    assert lab.used == lab.discovery_used == 0
    assert execution_failure(caught.value)['message'] == (
        "A model request failed and no transport retry was sent: a retry did not fit the campaign's unreserved budget. "
        'Inspect the saved provider diagnostics.')
    h.store.close()


@pytest.mark.anyio
async def test_mechanic_second_retry_the_budget_cannot_cover_is_refused_before_its_20_s_wait(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), NO_CHANGE], calls=2, tokens=2 * 34000)
    lab = backoff(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.mechanic.propose({'campaign_id': 'campaign-own'})
    assert [seconds for _, _, seconds in lab.waits] == [5] and sum(h.delays) == 5   # the 20 s wait never started
    assert len(h.requests) == h.ledger.used_calls == 2 and len(h.retries()) == 1
    summary = caught.value.transport_retry_summary
    assert (summary['role'], summary['retries_tried'], summary['waits_seconds'], summary['reason']) == ('mechanic', 1, [5], 'BUDGET_REFUSED')
    assert execution_failure(caught.value)['message'] == (
        "A model request failed after 1 transport retry (waits of 5 s); the next retry did not fit the campaign's unreserved "
        'budget, so it was not sent. Inspect the saved provider diagnostics.')
    h.store.close()


@pytest.mark.anyio
async def test_the_dollar_bound_is_checked_before_the_wait_too(tmp_path, monkeypatch):
    # Calls and tokens would allow a retry; the frozen dollar cap does not (one role bound is $0.03 in the harness).
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK], dollars=0.04)
    lab = backoff(h)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.transport_retry_summary['reason'] == 'BUDGET_REFUSED' and h.delays == [] and lab.waits == []
    assert len(h.requests) == h.ledger.used_calls == 1
    h.store.close()


@pytest.mark.anyio
async def test_a_stop_still_wins_over_the_budget_check(tmp_path, monkeypatch):
    """A Stop requested when the failure is recorded ends the request STOPPED, even when the budget is also spent."""
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK], calls=1, tokens=34000)
    backoff(h)
    original = h.store.put_record
    def stop_on_failure(kind, *args, **kwargs):
        if kind == 'provider_failures': h.ledger.stopped = True
        return original(kind, *args, **kwargs)
    h.store.put_record = stop_on_failure
    with pytest.raises(TransportRetryStopped):
        await h.explorer.select(h.context)
    assert h.delays == [] and len(h.requests) == h.ledger.used_calls == 1
    h.store.close()


@pytest.mark.anyio
async def test_with_budget_room_the_schedule_is_unchanged(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), connection_error(), PICK], calls=4, tokens=4 * 34000)
    lab = backoff(h)
    await h.explorer.select(h.context)
    assert [seconds for _, _, seconds in lab.waits] == [5, 20, 60] and len(h.requests) == h.ledger.used_calls == 4
    h.store.close()


# ----------------------------------------------------------------------------- 2. the message when no retry was sent

@pytest.mark.parametrize('reason,detail', [
    ('CAMPAIGN_RETRY_LIMIT', "the campaign's limit of 12 lab-role transport retries was reached"),
    ('DISCOVERY_RETRY_LIMIT', "the plan's declared discovery Explorer retry bound was reached"),
    ('BUDGET_REFUSED', "a retry did not fit the campaign's unreserved budget"),
])
def test_a_request_that_got_no_retry_says_so_plainly(reason, detail):
    summary = {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'explorer', 'retries_tried': 0, 'waits_seconds': [], 'reason': reason}
    message = retry_failure_message(summary)
    assert message == f'A model request failed and no transport retry was sent: {detail}. Inspect the saved provider diagnostics.'
    assert 'after 0' not in message


def test_messages_after_one_or_more_retries_are_unchanged():
    base = {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'mechanic'}
    assert retry_failure_message({**base, 'retries_tried': 3, 'waits_seconds': [5, 20, 60], 'reason': 'ALL_RETRIES_FAILED'}) == (
        'A model request failed after 3 transport retries (waits of 5 s, 20 s, 60 s); every allowed retry of this request '
        'failed. Inspect the saved provider diagnostics.')
    assert retry_failure_message({**base, 'retries_tried': 2, 'waits_seconds': [5, 20], 'reason': 'CAMPAIGN_RETRY_LIMIT'}) == (
        "A model request failed after 2 transport retries (waits of 5 s, 20 s); the campaign's limit of 12 lab-role transport "
        'retries was reached. Inspect the saved provider diagnostics.')


# ----------------------------------------------------------------------------- 3. the read-only check agrees with admission

def _ledger(path, *, calls, tokens_calls, dollars, used, reserved, stopped, bounds, used_cost):
    store = LabStore(path)
    ledger = CampaignLedger(store, 'campaign-grid', CampaignBudget(model_calls=calls, tokens=tokens_calls * 34000, dollars=dollars),
                            dollar_bounds=bounds)
    for name in PROTECTED: ledger.release(name)
    for _ in range(used): ledger.consume_call(role='actor')
    if reserved: ledger.reserve('batch', reserved)
    if used_cost is not None: ledger.used_cost = used_cost
    ledger.stopped = stopped
    return store, ledger


def test_the_read_only_check_agrees_with_real_admission_on_every_state(tmp_path):
    bounds_options = [None, {'actor': .03, 'explorer': .03, 'mechanic': .05}]
    cases = 0
    for index, (calls, tokens_calls, dollars, used, reserved, stopped, bounds, used_cost, role) in enumerate(itertools.product(
            [3, 4], [3, 4], [.1, .2], [0, 1, 2], [0, 1], [False, True], bounds_options, [None, .05, .2], ['explorer', 'mechanic'])):
        if used + reserved > min(calls, tokens_calls):
            continue
        if bounds is not None and (used + reserved) * .05 > dollars:
            continue
        store, ledger = _ledger(tmp_path / f'grid-{index}.sqlite3', calls=calls, tokens_calls=tokens_calls, dollars=dollars,
                                used=used, reserved=reserved, stopped=stopped, bounds=bounds, used_cost=used_cost)
        before = (ledger.used_calls, ledger.used_tokens, ledger.used_dollar_upper_bound)
        fits = ledger_retry_fits(ledger, role)
        assert (ledger.used_calls, ledger.used_tokens, ledger.used_dollar_upper_bound) == before      # it charges nothing
        assert fits == charge_ledger_retry(ledger, role), (calls, tokens_calls, dollars, used, reserved, stopped, bounds, used_cost, role)
        store.close()
        cases += 1
    assert cases > 300


def test_a_test_double_ledger_leaves_the_decision_to_admission():
    assert ledger_retry_fits(SimpleNamespace(stopped=True), 'explorer') is True


def test_the_check_is_wired_into_both_lab_roles():
    import inspect
    from app.agents import explorer, mechanic
    for module, role in ((explorer, 'explorer'), (mechanic, 'mechanic')):
        assert f"fits=lambda:ledger_retry_fits(self.ledger,'{role}')" in inspect.getsource(module)
    assert 'fits' in inspect.signature(transport_retry.complete_with_backoff).parameters
