"""Rule v2 (faultlab-transport-retry/v2-lab-backoff) through the real coordinator and learning loop.

Campaign 44085f54's successor (b05ac280) ended ERROR when one Explorer request and its single blind retry
both lost the connection ~130 ms apart. Every new Learn plan now freezes rule v2: the Explorer and the
Mechanic back off (5 s, 20 s, 60 s) and retry up to 3 times, at most 12 times per campaign. Waits are
replaced by a recorder (or scaled down) so no test sleeps for long; no provider, W&B or model call is made.
"""
import asyncio
import json
import time

import httpx
import pytest

from app.agents import transport_retry
from app.agents.transport_retry import (TRANSPORT_RETRY_PROTOCOL_V2, declaration as rule_v1, declaration_v2 as rule_v2,
                                        lab_backoff_for_campaign)
from app.contracts.models import CampaignRequest
from app.lab.budgets import CampaignLedger
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2
from app.lab.exports import development_recording
from app.lab.operator_actions import register_agent
from app.lab.run_plans import build_run_options, prepare_run_plan, read_run_plan, validate_run_plan
from app.lab.storage import StoreConflict
from app.main import create_app
from app.providers.runtime import RuntimeProviderError

from test_campaign_transport_retry import Flaky, execute, learn_campaign_v1_rule
from test_discovery_v2_flow import DELAYED, learn_campaign, owner, raw, request  # noqa: F401  (owner is a fixture)


def record_waits(monkeypatch):
    """Replace the backoff wait with a recorder: every wait passes at once and its length is kept."""
    waits = []
    async def wait(seconds, stopped, **kwargs):
        waits.append(seconds)
        return bool(stopped())
    monkeypatch.setattr(transport_retry, 'cancellable_wait', wait)
    return waits


def answer(slot, request, context):
    return raw(DELAYED, seed=slot)


def v2_records(owner):
    return sorted((r for r in owner.store.list_records('transport_retries') if r['protocol'] == TRANSPORT_RETRY_PROTOCOL_V2),
                  key=lambda r: r['campaign_retry_number'])


# ----------------------------------------------------------------------------- new Learn plans

def test_run_options_and_every_new_learn_plan_declare_rule_v2(owner):
    assert build_run_options(owner.settings, owner.store)['learn']['transport_retry'] == rule_v2(8)
    campaign = learn_campaign(owner, DISCOVERY_V1)
    plan = read_run_plan(owner.store, campaign)['plan']
    assert plan['transport_retry'] == rule_v2(8)
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) == plan
    session = lab_backoff_for_campaign(owner.store, owner.get(campaign.campaign_id), stopped=lambda: False)
    assert session is not None and session.discovery_retries_max == plan['discovery']['explorer_transport_retries_max'] == 8


@pytest.mark.parametrize('protocol', [DISCOVERY_V1, DISCOVERY_V2])
def test_a_lost_explorer_request_backs_off_and_the_campaign_continues(owner, monkeypatch, protocol):
    waits = record_waits(monkeypatch)
    campaign = learn_campaign(owner, protocol)
    provider = Flaky(answer, failing={1, 2})            # the first request loses its connection twice
    final, ledger, runner = execute(owner, campaign, provider)
    assert final.state == 'NO_CHANGE', final.terminal_reason
    assert waits == [5, 20]
    first, second = v2_records(owner)
    assert [(r['attempt'], r['retry_delay_seconds'], r['role'], r['request']['phase']) for r in (first, second)] == [
        (1, 5, 'explorer', 'discovery'), (2, 20, 'explorer', 'discovery')]
    assert len(owner.store.list_records('provider_failures')) == 2 and not owner.store.list_records('execution_errors')
    assert provider.sent == len(provider.contexts) + 2 and ledger.used_calls == provider.sent   # both retries charged
    selection, = [row for row in owner.store.list_records('selections') if row.get('transport_retries')]
    assert selection['usage']['model_calls'] == 3 and [t['attempt'] for t in selection['transport_retries']] == [1, 2]


def test_when_every_retry_fails_the_campaign_ends_error_and_says_how_many_were_tried(owner, monkeypatch):
    waits = record_waits(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V2)
    provider = Flaky(answer, failing={3, 4, 5, 6})       # the third request and all three of its retries
    final, ledger, runner = execute(owner, campaign, provider)
    message = ('A model request failed after 3 transport retries (waits of 5 s, 20 s, 60 s); every allowed retry of this '
               'request failed. Inspect the saved provider diagnostics.')
    assert final.state == 'ERROR' and final.terminal_reason == 'CONNECTION_ERROR: ' + message
    error, = owner.store.list_records('execution_errors')
    assert error['code'] == 'CONNECTION_ERROR' and error['message'] == message
    assert error['transport_retries'] == {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'explorer', 'retries_tried': 3,
                                          'waits_seconds': [5, 20, 60], 'reason': 'ALL_RETRIES_FAILED'}
    assert waits == [5, 20, 60] and provider.sent == ledger.used_calls == 6 and len(v2_records(owner)) == 3


def test_the_declared_discovery_bound_still_caps_explorer_retries_during_discovery(owner, monkeypatch):
    waits = record_waits(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V1)       # 8 discovery requests, at most 8 Explorer retries in discovery
    # Every slot's request loses its connection twice, then is answered: 3 requests per slot.
    provider = Flaky(answer, failing={n for n in range(1, 40) if n % 3 != 0})
    final, ledger, runner = execute(owner, campaign, provider)
    assert final.state == 'ERROR' and 'declared discovery Explorer retry bound was reached' in final.terminal_reason
    assert len(v2_records(owner)) == 8 and waits == [5, 20] * 4
    assert provider.sent == ledger.used_calls == 13       # four slots of three requests, then the refused one


def test_a_retry_the_budget_cannot_cover_ends_the_campaign_error_without_waiting(owner, monkeypatch):
    """Review findings LOW-2 / P-4 (September 30): the unreserved budget is checked before the backoff wait (without
    charging), so the campaign ends at once, and the message says no retry was sent (not "after 0 transport retries")."""
    waits = record_waits(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V1)
    provider = Flaky(answer, failing={1})
    final, ledger, runner = execute(owner, campaign, provider, headroom=1)     # room for the first request only
    message = ("A model request failed and no transport retry was sent: a retry did not fit the campaign's unreserved "
               'budget. Inspect the saved provider diagnostics.')
    assert final.state == 'ERROR' and final.terminal_reason == 'CONNECTION_ERROR: ' + message
    error, = owner.store.list_records('execution_errors')
    assert error['message'] == message and error['transport_retries'] == {
        'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': 'explorer', 'retries_tried': 0, 'waits_seconds': [], 'reason': 'BUDGET_REFUSED'}
    assert waits == [] and provider.sent == 1 and not v2_records(owner)


def test_retries_are_visible_in_search_attempts_and_the_recording(owner, monkeypatch):
    record_waits(monkeypatch)
    campaign = learn_campaign(owner, DISCOVERY_V2)
    execute(owner, campaign, Flaky(answer, failing={1, 2}))
    records = v2_records(owner)

    async def read():
        transport = httpx.ASGITransport(app=create_app(coordinator=owner))
        async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1') as client:
            return (await client.get(f'/api/campaigns/{campaign.campaign_id}/search-attempts')).json()
    rows = asyncio.run(read())
    retried, = [row for row in rows if row['transport_retries']]
    assert retried['usage']['model_calls'] == 3
    assert retried['transport_retries'] == [
        {'retry_id': r['retry_id'], 'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'code': 'CONNECTION_ERROR', 'attempt': r['attempt'],
         'retry_delay_seconds': r['retry_delay_seconds'], 'provider_failure_id': r['provider_failure_id']} for r in records]
    with owner.store.transaction() as db:   # the fake runner's minimal episode rows are not exportable episodes
        db.execute("DELETE FROM records WHERE kind='episodes' AND json_extract(payload,'$.campaign_id')=?", (campaign.campaign_id,))
    recording = development_recording(owner.store, campaign.campaign_id)
    assert [(r['retry_id'], r['attempt'], r['retry_delay_seconds']) for r in recording['transport_retries']] == [
        (r['retry_id'], r['attempt'], r['retry_delay_seconds']) for r in sorted(records, key=lambda r: r['recorded_at'])]


# ----------------------------------------------------------------------------- Stop during a wait

def test_a_stop_during_a_backoff_wait_ends_the_campaign_stopped_promptly(owner, monkeypatch):
    """Real waits (poll 0.5 s): the Stop lands one second into the first 5-second wait."""
    campaign = learn_campaign(owner, DISCOVERY_V1)
    id = campaign.campaign_id
    provider = Flaky(answer, failing=set(range(1, 10)))   # the connection never comes back
    real_wait = transport_retry.cancellable_wait
    timing = {}

    async def wait_then_stop(seconds, stopped, **kwargs):
        async def press_stop():
            await asyncio.sleep(1)
            timing['stop'] = time.monotonic()
            await owner.stop(id)
        presser = asyncio.create_task(press_stop())
        try:
            return await real_wait(seconds, stopped, **kwargs)
        finally:
            timing['wait_ended'] = time.monotonic()
            await presser
    monkeypatch.setattr(transport_retry, 'cancellable_wait', wait_then_stop)
    final, ledger, runner = execute(owner, campaign, provider)
    assert final.state == 'STOPPED'
    assert final.terminal_reason == ('External stop requested while a failed Explorer model request waited to be re-sent '
                                     '(transport retry backoff); it was not sent again. Remote effects are retained.')
    # Ended at the next 0.5 s check, not after the 5-second wait (2 s leaves room for a busy test machine).
    assert timing['wait_ended'] - timing['stop'] < 2.0
    assert not owner.store.list_records('execution_errors')   # a stop is not an execution error
    assert provider.sent == ledger.used_calls == 1 and not owner.store.list_records('transport_retries')


# ----------------------------------------------------------------------------- plans saved before rule v2

def test_a_learn_plan_saved_before_rule_v2_reads_starts_and_keeps_rule_v1(owner, monkeypatch):
    waits = record_waits(monkeypatch)
    campaign = learn_campaign_v1_rule(owner, DISCOVERY_V2)
    plan = read_run_plan(owner.store, campaign)['plan']
    assert read_run_plan(owner.store, campaign)['status'] == 'PLANNED' and plan['transport_retry'] == rule_v1(8)
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) == plan   # Start accepts it
    assert lab_backoff_for_campaign(owner.store, owner.get(campaign.campaign_id), stopped=lambda: False) is None
    provider = Flaky(answer, failing={1, 2})
    final, ledger, runner = execute(owner, campaign, provider)
    # Rule v1 exactly: one blind retry at once, a second failure ends the campaign with rule v1's message.
    assert final.state == 'ERROR'
    assert final.terminal_reason == 'CONNECTION_ERROR: A model request failed; inspect the saved provider diagnostics.'
    assert waits == [] and provider.sent == ledger.used_calls == 2
    retry, = owner.store.list_records('transport_retries')
    assert retry['protocol'] == 'faultlab-transport-retry/v1' and 'retry_delay_seconds' not in retry
    assert 'transport_retries' not in owner.store.list_records('execution_errors')[0]


def test_only_a_learn_plan_may_declare_rule_v2_and_only_exactly_it(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-1'))
    assert baseline.plan['transport_retry'] == rule_v1(8)
    baseline.plan['transport_retry'] = rule_v2(8)
    with pytest.raises(StoreConflict, match='Only a Learn plan declares lab-role transport retries'):
        owner.create(baseline.campaign_request, run_plan=baseline)
    for change in ({'lab_backoff_seconds': [5, 20, 30]}, {'lab_retries_per_campaign_max': 24}, {'lab_retries_per_request': 4},
                   {'agent_retries_per_request': 2}, {'lab_roles': ['explorer']}, {'stop_during_wait': 'ERROR'}):
        learn = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
        learn.plan['transport_retry'] = {**rule_v2(8), **change}
        with pytest.raises(ValueError):          # the saved-plan schema (pydantic) refuses it before anything is written
            owner.create(learn.campaign_request, run_plan=learn)
    assert not [row for row in owner.store.list_records('campaign_plans') if row['mode'] == 'baseline']


# ----------------------------------------------------------------------------- the whole original loop

@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_lost_explorer_and_mechanic_requests_in_every_lab_phase_back_off_and_the_loop_completes(tmp_path, monkeypatch):
    """The planned native original loop (manual reference fixture, never generated learning) with lost discovery,
    diagnosis, candidate and challenge requests reaches the same accepted result as a clean run."""
    from original_loop_fixture import CONTROL, ManualPolicies, OfflineEvidence, OfflineRunner, fixture_settings, localhost_simulator
    from test_planned_agent_execution import NativeReferenceInputs, planned_campaign
    from app.adapters.business_tools import WorldClient
    from app.lab.coordinator import LabCoordinator
    waits = record_waits(monkeypatch)

    class LosingLabRequests(NativeReferenceInputs):
        def __init__(self, mode, lose):
            super().__init__(mode); self.lose = dict(lose); self.lost = []
        async def complete(self, messages, *, role='actor', **kwargs):
            if role != 'actor':
                context = json.loads(messages[-1]['content'])
                kind = (('challenge' if context.get('purpose') == 'challenge' else 'discovery') if role == 'explorer'
                        else 'diagnosis' if 'intervention_ids' in context else 'proposal')
                if self.lose.get((role, kind), 0):
                    self.lose[(role, kind)] -= 1; self.lost.append((role, kind))
                    raise RuntimeProviderError('scripted loss', code='CONNECTION_ERROR', error_class='APIConnectionError')
            return await super().complete(messages, role=role, **kwargs)

    settings = fixture_settings(tmp_path / 'lab')
    provider = LosingLabRequests('accepted', {('explorer', 'discovery'): 2, ('mechanic', 'diagnosis'): 1,
                                              ('mechanic', 'proposal'): 1, ('explorer', 'challenge'): 1})
    with localhost_simulator(tmp_path, settings) as url:
        c = LabCoordinator(settings)
        c.runner = OfflineRunner(c.store, WorldClient(url, CONTROL), provider, offline_fixture=True)
        c.policies = ManualPolicies(c.store)
        c.evidence_gateway = OfflineEvidence(c.store, 'offline-fixture/native-selected-loop')
        campaign = planned_campaign(c, mode='learn')
        try:
            assert read_run_plan(c.store, campaign)['plan']['transport_retry'] == rule_v2(8)
            await c.start(campaign.campaign_id)
            await asyncio.wait_for(c.tasks[campaign.campaign_id], timeout=240)
            current = c.get(campaign.campaign_id)
            assert current.state == 'COMPLETED', (current.terminal_reason, c.store.list_records('execution_errors'))
            assert c.policies.get(current.active_policy_version).decision == 'ACCEPTED'
            assert provider.lost == [('explorer', 'discovery'), ('explorer', 'discovery'), ('mechanic', 'diagnosis'),
                                     ('mechanic', 'proposal'), ('explorer', 'challenge')]
            records = sorted(c.store.list_records('transport_retries'), key=lambda r: r['campaign_retry_number'])
            assert [(r['role'], r['request']['phase'], r['attempt'], r['retry_delay_seconds']) for r in records] == [
                ('explorer', 'discovery', 1, 5), ('explorer', 'discovery', 2, 20), ('mechanic', 'mechanic_diagnosis', 1, 5),
                ('mechanic', 'mechanic_proposal', 1, 5), ('explorer', 'challenge', 1, 5)]
            assert [r['campaign_retry_number'] for r in records] == [1, 2, 3, 4, 5]
            assert waits == [5, 20, 5, 5, 5] and not c.store.list_records('execution_errors')
            budget = c.store.get_record('budgets', campaign.campaign_id)
            assert budget['used_calls'] == sum(provider.calls.values()) + len(provider.lost)   # every retry charged
        finally:
            await c.runner.world_client.close()
            await c.close()
