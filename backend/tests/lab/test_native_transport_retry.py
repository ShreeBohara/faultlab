"""Native smolagents: the shared transport retry below the native loop, and the real report tick.

Real smolagents ToolCallingAgent, real simulator (in-process ASGI), real runner and ledger;
only the model transport is a declared scripted replacement. No provider or model call.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from app.contracts.models import FaultSpec
from app.lab.budgets import CampaignLedger
from app.providers.runtime import RuntimeProviderError
from test_planned_agent_execution import NativeReferenceInputs, ScriptedProvider, planned_campaign, runtime

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def anyio_backend(): return 'asyncio'


def load(name):
    spec = importlib.util.spec_from_file_location(name + '_under_test', ROOT / f'scripts/experiments/{name}.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def checker():
    """The companion check with the declared native rule; check_clock_drift.py itself stays pinned."""
    return load('check_clock_drift_native')


class Lossy(NativeReferenceInputs):
    """The native fixture's answers, with chosen requests lost before any answer arrives."""
    def __init__(self, failing=(), status=None):
        super().__init__('accepted'); self.failing = set(failing); self.status = status; self.sent = []
    async def complete(self, messages, *, role='actor', **kwargs):
        if role == 'actor':
            self.sent.append(messages)
            if len(self.sent) in self.failing:
                if self.status: raise RuntimeProviderError('scripted 503', code='HTTP_ERROR', http_status=self.status)
                raise RuntimeProviderError('scripted loss', code='CONNECTION_ERROR', error_class='APIConnectionError')
        return await super().complete(messages, role=role, **kwargs)


def remaining(messages):
    return json.loads(messages[-1]['content'])['remaining_actor_calls']


async def execute(tmp_path, provider, *, agent='smolagents', headroom=None):
    c = await runtime(tmp_path, provider=provider)
    campaign = planned_campaign(c, agent=agent)
    ledger = CampaignLedger(c.store, campaign.campaign_id, campaign.caps, dollar_bounds=c.settings.model_call_dollar_bounds)
    if headroom is not None:
        ledger.used_calls = ledger.caps.model_calls - ledger.reserved_calls - headroom; ledger._save()
    trial = await c.runner.run(campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline(), ledger=ledger)
    return c, trial, ledger


def events(c, trial, kind):
    return [e for e in c.store.events(trial.episode_id)['events'] if e['type'] == kind]


@pytest.mark.anyio
async def test_native_lost_request_is_resent_once_without_an_extra_step_or_a_changed_prompt(tmp_path):
    base_c, base, _ = await execute(tmp_path / 'base', Lossy())
    base_remaining = [remaining(m) for m in base_c.runner.provider.sent]
    await base_c.close()
    provider = Lossy(failing={2})
    c, trial, ledger = await execute(tmp_path / 'lossy', provider)
    try:
        assert trial.lifecycle == 'COMPLETED' and trial.outcome == base.outcome == 'COMPLETED'
        # smolagents took the same number of model steps; the retry was one more charged request.
        assert trial.usage.actor_calls == base.usage.actor_calls == 4
        assert trial.usage.model_calls == 5 and ledger.used_calls == 5 and len(provider.sent) == 5
        assert trial.usage.http_attempts == base.usage.http_attempts
        # The model saw exactly what it would have seen: the identical request was re-sent ...
        assert provider.sent[1] == provider.sent[2]
        # ... and every answered request carries the same turn budget as the run without a loss.
        answered = [m for index, m in enumerate(provider.sent, 1) if index not in provider.failing]
        assert [remaining(m) for m in answered] == base_remaining == [8, 7, 6, 5]
        retry, = events(c, trial, 'actor_transport_retry')
        assert retry['payload'] == {'code': 'CONNECTION_ERROR', 'attempt': 1} and retry['role'] == 'actor'
        failure, = c.store.list_records('provider_failures')
        assert failure['episode_id'] == trial.episode_id and failure['diagnostics']['code'] == 'CONNECTION_ERROR'
        assert trial.usage.cost_dollars is None                       # the lost request's cost is unknown
    finally: await c.close()


@pytest.mark.anyio
async def test_native_503_waits_then_retries_and_records_the_status(tmp_path):
    provider = Lossy(failing={1}, status=503)
    c, trial, ledger = await execute(tmp_path, provider)
    try:
        assert trial.outcome == 'COMPLETED' and ledger.used_calls == 5 and trial.usage.actor_calls == 4
        retry, = events(c, trial, 'actor_transport_retry')
        assert retry['payload'] == {'code': 'HTTP_ERROR', 'attempt': 1, 'http_status': 503, 'retry_delay_seconds': 1}
    finally: await c.close()


@pytest.mark.anyio
async def test_native_second_loss_is_still_a_lab_error(tmp_path):
    provider = Lossy(failing={2, 3})
    c, trial, ledger = await execute(tmp_path, provider)
    try:
        assert trial.lifecycle == trial.outcome == 'LAB_ERROR' and trial.reason == 'CONNECTION_ERROR'
        assert len(provider.sent) == ledger.used_calls == trial.usage.model_calls == 3 and trial.usage.actor_calls == 2
        assert len(events(c, trial, 'actor_transport_retry')) == 1 and len(c.store.list_records('provider_failures')) == 2
        assert c.store.get_record('episodes', trial.episode_id)['report'] is None
    finally: await c.close()


@pytest.mark.anyio
async def test_native_retry_the_budget_cannot_cover_is_refused_before_sending(tmp_path):
    provider = Lossy(failing={1})
    c, trial, ledger = await execute(tmp_path, provider, headroom=1)
    try:
        assert trial.lifecycle == 'LAB_ERROR' and trial.reason == 'CONNECTION_ERROR'   # the original failure stands
        assert len(provider.sent) == 1 and trial.usage.model_calls == 1
        assert not events(c, trial, 'actor_transport_retry') and len(c.store.list_records('provider_failures')) == 1
    finally: await c.close()


# ----------------------------------------------------------------------------- report tick and the drift check

@pytest.mark.anyio
async def test_native_report_carries_the_real_tick_and_passes_the_drift_check(tmp_path):
    c, trial, _ = await execute(tmp_path, Lossy())
    try:
        report, = events(c, trial, 'report_submitted')
        verdict = c.store.get_record('episodes', trial.episode_id)['verdict']
        assert report['tick'] == verdict['decision_tick'] == trial.usage.ticks == 3
        result = checker().scan(str(c.store.path), worlds=True, worlds_dir=str(tmp_path / 'worlds'))
        assert result['scored'] == 1 and result['drifted'] == [] and result['missing_worlds'] == 0
        assert result['native_report_tick0_cleared'] == [] and result['native_report_tick0_not_cleared'] == 0
        assert checker().exit_status(result, require_worlds=True) == 0
        # New stores need no rule: the unchanged original check passes this native episode by itself.
        original = load('check_clock_drift').scan(str(c.store.path), worlds=True, worlds_dir=str(tmp_path / 'worlds'))
        assert original['drifted'] == [] and original['scored'] == 1
    finally: await c.close()


def rewrite_report_tick(c, episode_id, tick):
    """Recreate what the old adapter stored: report_submitted at `tick` (a test-store edit only)."""
    with c.store.transaction() as db:
        for seq, payload in db.execute('SELECT seq,payload FROM events WHERE episode_id=?', (episode_id,)).fetchall():
            event = json.loads(payload)
            if event['type'] == 'report_submitted':
                event['tick'] = tick
                db.execute('UPDATE events SET payload=? WHERE episode_id=? AND seq=?', (json.dumps(event), episode_id, seq))


@pytest.mark.anyio
async def test_old_native_store_is_read_with_the_declared_rule(tmp_path):
    c, trial, _ = await execute(tmp_path, Lossy())
    try:
        rewrite_report_tick(c, trial.episode_id, 0)
        check = checker(); store = str(c.store.path); worlds = str(tmp_path / 'worlds')
        # All three hold (tick 0, equal attempt counts, integrity VALID): not drift, listed separately.
        result = check.scan(store, worlds=True, worlds_dir=worlds)
        assert result['drifted'] == [] and check.exit_status(result, require_worlds=True) == 0
        (row,) = result['native_report_tick0_cleared']
        assert row[0] == trial.episode_id and row[3] == 0 and row[5] == row[6] == 3
        assert result['episodes'][trial.episode_id]['native_report_tick0_cleared'] is True
        assert result['native_report_tick0_not_cleared_rows'] == []
        lines = check.render(result)
        assert any(line.startswith('native reports at tick 0 (old adapter, declared rule): 1 not drift, 0 still') for line in lines)
        # The unchanged original check still flags it, exactly as it did for the native probe.
        original = load('check_clock_drift').scan(store, worlds=True, worlds_dir=worlds)
        assert [row[0] for row in original['drifted']] == [trial.episode_id] and original['drifted'][0][3] == 0
        assert check.render(result)[:3] == load('check_clock_drift').render(result)[:3]
        # Without the world attempt count the rule cannot be applied: still drift.
        blind = check.scan(store)
        assert len(blind['drifted']) == 1 and blind['native_report_tick0_not_cleared'] == 1
        assert any('use --worlds' in line for line in check.render(blind))
        # Review finding (INFO, September 29): each row that stays drift says why.
        assert [row[-1] for row in blind['native_report_tick0_not_cleared_rows']] == ['no world attempt count (run with --worlds)']
        assert any(line.startswith(f'  {trial.episode_id} ') and line.endswith('still drift: no world attempt count (run with --worlds)')
                   for line in check.render(blind))
        # An integrity record that is not VALID keeps it drift.
        integrity = c.store.get_record('private_world_integrity', trial.episode_id)
        with c.store.transaction() as db:
            db.execute("UPDATE records SET payload=? WHERE kind='private_world_integrity' AND id=?",
                       (json.dumps({**integrity, 'status': 'INVALID', 'issues': ['DECISION_TICK_MISMATCH']}), trial.episode_id))
        invalid = check.scan(store, worlds=True, worlds_dir=worlds)
        assert len(invalid['drifted']) == 1 and invalid['native_report_tick0_cleared'] == []
        assert check.exit_status(invalid) == 1
        assert [row[-1] for row in invalid['native_report_tick0_not_cleared_rows']] == ['integrity INVALID, not VALID']
        # A missing integrity record (a Phase 1 store) keeps it drift too.
        with c.store.transaction() as db:
            db.execute("DELETE FROM records WHERE kind='private_world_integrity' AND id=?", (trial.episode_id,))
        missing = check.scan(store, worlds=True, worlds_dir=worlds)
        assert len(missing['drifted']) == 1
        assert [row[-1] for row in missing['native_report_tick0_not_cleared_rows']] == ['no private_world_integrity record']
        assert any(line.endswith('still drift: no private_world_integrity record') for line in check.render(missing))
    finally: await c.close()


@pytest.mark.anyio
async def test_declared_rule_needs_equal_attempt_counts(tmp_path):
    import sqlite3
    c, trial, _ = await execute(tmp_path, Lossy())
    try:
        rewrite_report_tick(c, trial.episode_id, 0)
        world = tmp_path / 'worlds' / f"{c.store.get_record('episodes', trial.episode_id)['world_id']}.sqlite3"
        # World history is append-only; an extra admitted attempt makes the counts differ.
        db = sqlite3.connect(world)
        value = next(value for (value,) in db.execute('SELECT value FROM events') if json.loads(value)['type'] == 'http_attempt')
        db.execute('INSERT INTO events(value) VALUES(?)', (value,)); db.commit(); db.close()
        result = checker().scan(str(c.store.path), worlds=True, worlds_dir=str(tmp_path / 'worlds'))
        assert len(result['drifted']) == 1 and result['native_report_tick0_cleared'] == []
        assert [row[-1] for row in result['native_report_tick0_not_cleared_rows']] == ['lab and world attempt counts differ (3 vs 4)']
    finally: await c.close()


@pytest.mark.anyio
async def test_the_rule_never_excuses_a_reference_actor_report_at_tick_0(tmp_path):
    c, trial, _ = await execute(tmp_path, ScriptedProvider('accepted'), agent='reference')
    try:
        report, = events(c, trial, 'report_submitted')
        assert report['tick'] == c.store.get_record('episodes', trial.episode_id)['verdict']['decision_tick']
        rewrite_report_tick(c, trial.episode_id, 0)
        result = checker().scan(str(c.store.path), worlds=True, worlds_dir=str(tmp_path / 'worlds'))
        assert len(result['drifted']) == 1 and result['native_report_tick0_cleared'] == []
        assert result['native_report_tick0_not_cleared'] == 0 and result['native_report_tick0_not_cleared_rows'] == []
    finally: await c.close()
