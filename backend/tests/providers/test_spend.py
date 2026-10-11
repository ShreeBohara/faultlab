"""The monthly spend ledger: worst-case reservations against a cap, settled with measured cost."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app.providers.spend import MonthlyCapExceeded, SpendLedger, current_month

OCTOBER = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def test_reservations_charge_bounds_and_settlements_record_actuals(tmp_path):
    ledger = SpendLedger(tmp_path / 'ledger.sqlite3')
    first = ledger.reserve(provider='openai', model='openai:gpt-5-mini', role='actor', bound_usd=0.044, cap_usd=1.0, now=OCTOBER)
    second = ledger.reserve(provider='wandb', model='wandb:m', role='mechanic', bound_usd=0.05, cap_usd=1.0, note='smoke', now=OCTOBER)
    summary = ledger.summary('2026-10')
    assert summary.calls == 2 and summary.reserved_bound == pytest.approx(0.094) and summary.settled_actual is None
    ledger.settle(first, actual_usd=0.0012, input_tokens=300, output_tokens=40)
    assert ledger.summary('2026-10').settled_actual is None    # one row is still unsettled
    ledger.settle(second, actual_usd=0.002, input_tokens=10, output_tokens=5)
    settled = ledger.summary('2026-10')
    assert settled.settled_actual == pytest.approx(0.0032) and settled.reserved_bound == pytest.approx(0.094)
    assert ledger.summary('2026-11').calls == 0 and ledger.summary('2026-11').reserved_bound == 0


def test_the_cap_gates_on_reserved_bounds_and_a_refusal_records_nothing(tmp_path):
    ledger = SpendLedger(tmp_path / 'ledger.sqlite3')
    charge = ledger.reserve(provider='openai', model='m', role='actor', bound_usd=0.6, cap_usd=1.0, now=OCTOBER)
    ledger.settle(charge, actual_usd=0.01, input_tokens=1, output_tokens=1)   # cheap in fact; the bound still counts
    with pytest.raises(MonthlyCapExceeded) as refused:
        ledger.reserve(provider='openai', model='m', role='actor', bound_usd=0.5, cap_usd=1.0, now=OCTOBER)
    assert (refused.value.month, refused.value.bound, refused.value.cap) == ('2026-10', 0.5, 1.0)
    assert refused.value.reserved == pytest.approx(0.6) and ledger.summary('2026-10').calls == 1
    assert ledger.reserve(provider='openai', model='m', role='actor', bound_usd=0.4, cap_usd=1.0, now=OCTOBER)
    assert ledger.summary('2026-10').reserved_bound == pytest.approx(1.0)


def test_a_new_month_starts_from_zero(tmp_path):
    ledger = SpendLedger(tmp_path / 'ledger.sqlite3')
    last_minute = datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc)
    ledger.reserve(provider='p', model='m', role='actor', bound_usd=1.0, cap_usd=1.0, now=last_minute)
    with pytest.raises(MonthlyCapExceeded):
        ledger.reserve(provider='p', model='m', role='actor', bound_usd=0.01, cap_usd=1.0, now=last_minute)
    first_minute = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    ledger.reserve(provider='p', model='m', role='actor', bound_usd=1.0, cap_usd=1.0, now=first_minute)
    assert ledger.summary('2026-11').calls == 1 and current_month(first_minute) == '2026-11'


def test_concurrent_reservations_never_exceed_the_cap(tmp_path):
    path = tmp_path / 'ledger.sqlite3'
    SpendLedger(path)

    def attempt(_):
        try:
            return SpendLedger(path).reserve(provider='p', model='m', role='actor', bound_usd=0.1, cap_usd=1.0, now=OCTOBER)
        except MonthlyCapExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(40)))
    assert sum(result is not None for result in results) == 10
    assert SpendLedger(path).summary('2026-10').reserved_bound == pytest.approx(1.0)


@pytest.mark.parametrize('bound,cap', [(-0.1, 1.0), (0.1, -1.0), (float('nan'), 1.0)])
def test_negative_or_undefined_amounts_are_refused(tmp_path, bound, cap):
    with pytest.raises(ValueError):
        SpendLedger(tmp_path / 'ledger.sqlite3').reserve(provider='p', model='m', role='actor', bound_usd=bound, cap_usd=cap)


def test_the_ledger_survives_reopening(tmp_path):
    path = tmp_path / 'ledger.sqlite3'
    SpendLedger(path).reserve(provider='p', model='m', role='actor', bound_usd=0.2, cap_usd=1.0, now=OCTOBER)
    assert SpendLedger(path).summary('2026-10').reserved_bound == pytest.approx(0.2)
