"""Transport retries are declared in reviewed plans, bounded, and visible in saved evidence."""
import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.agents.transport_retry import declaration as retry_declaration, declaration_v2 as retry_declaration_v2
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2, campaign_discovery
from app.lab.exports import development_recording
from app.lab.operator_actions import register_agent
from app.lab.run_plans import DiscoveryPlan, TransportRetryPlan, prepare_run_plan, read_run_plan, validate_run_plan
from app.lab.storage import StoreConflict
from app.main import create_app
from app.providers.runtime import RuntimeProviderError
from test_campaign_transport_retry import Flaky, execute, learn_campaign_v1_rule
from test_discovery_v2_flow import DELAYED, learn_campaign, owner, raw, request  # noqa: F401  (fixture)


def test_every_new_plan_declares_the_shared_rule_and_learn_plans_the_explorer_bound(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-1'))
    assert baseline.plan['transport_retry'] == retry_declaration(8)            # baseline and compare keep rule v1
    assert baseline.plan['transport_retry']['actor_retries_per_episode_max'] == 8 and 'discovery' not in baseline.plan
    for protocol, requests in ((DISCOVERY_V1, 8), (DISCOVERY_V2, 16)):
        learn = learn_campaign(owner, protocol)
        plan = read_run_plan(owner.store, learn)['plan']
        assert plan['discovery']['explorer_requests_max'] == plan['discovery']['explorer_transport_retries_max'] == requests
        # Every new Learn plan freezes rule v2 (lab-role backoff); its agent roles keep rule v1.
        assert plan['transport_retry'] == retry_declaration_v2(8)
        assert plan['transport_retry']['agent_roles'] == ['actor'] and plan['transport_retry']['lab_roles'] == ['explorer', 'mechanic']
        assert validate_run_plan(owner.store, owner.settings, owner.get(learn.campaign_id)) == plan
    native = register_agent(owner.store, owner.settings, 'smolagents')
    native_plan = prepare_run_plan(owner.store, owner.settings, request(owner, native, mode='baseline', development_case_id='dev-3'))
    assert native_plan.plan['transport_retry'] == retry_declaration(8)


def test_declarations_must_be_coherent():
    v2 = learn_block = {'protocol': DISCOVERY_V2, 'schedule_identity': 'faultlab-schedule-identity/v2-order-aware', 'slots': 8,
                        'explorer_requests_max': 16, 'explorer_transport_retries_max': 16, 'actor_episodes_max': 8,
                        'replans_per_slot': 1, 'dispatch_rule': 'rule', 'pre_check': {'caller_model': {'agent': 'reference'}}}
    DiscoveryPlan.model_validate(v2)
    DiscoveryPlan.model_validate({k: v for k, v in learn_block.items() if k != 'explorer_transport_retries_max'})  # older plan
    for bad in (8, 17, 32, -1):
        with pytest.raises(ValidationError):
            DiscoveryPlan.model_validate({**v2, 'explorer_transport_retries_max': bad})
    TransportRetryPlan.model_validate(retry_declaration(8))
    for change in ({'retries_per_request': 2}, {'roles': ['actor', 'mechanic', 'explorer']},
                   {'retryable': ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_500']}, {'service_unavailable_delay_seconds': 0},
                   {'actor_retries_per_episode_max': 9}, {'protocol': 'faultlab-transport-retry/v2'}):
        with pytest.raises(ValidationError):
            TransportRetryPlan.model_validate({**retry_declaration(8), **change})


def test_a_plan_saved_before_retries_were_declared_reads_but_cannot_run_under_this_runtime(owner, monkeypatch):
    from app.lab import run_plans
    registration = register_agent(owner.store, owner.settings, 'reference')

    class SavedBeforeRetries(run_plans.SavedRunPlan):
        def model_dump(self, **kwargs):
            data = super().model_dump(**kwargs)
            data.pop('transport_retry', None)
            data['discovery'].pop('explorer_transport_retries_max', None)
            return data
    monkeypatch.setattr(run_plans, 'SavedRunPlan', SavedBeforeRetries)
    # The runtime that saved such a plan checked it against its own (retry-free) rule.
    monkeypatch.setattr(run_plans, 'validate_run_plan', lambda *args, **kwargs: None)
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration, discovery_protocol=DISCOVERY_V2))
    prepared.plan.pop('transport_retry'); prepared.plan['discovery'].pop('explorer_transport_retries_max')
    older = owner.create(prepared.campaign_request, run_plan=prepared)
    monkeypatch.undo()
    saved = owner.store.get_record('campaign_plans', older.campaign_id)
    assert 'transport_retry' not in saved and 'explorer_transport_retries_max' not in saved['discovery']
    read = read_run_plan(owner.store, older)
    assert read['status'] == 'PLANNED' and read['plan']['transport_retry'] is None
    assert read['plan']['discovery']['explorer_transport_retries_max'] is None
    assert campaign_discovery(owner.store, older).get('explorer_transport_retries_max') is None  # declared none
    with pytest.raises(StoreConflict, match='transport retry rule differs'):
        validate_run_plan(owner.store, owner.settings, owner.get(older.campaign_id))


def test_retries_are_visible_in_search_attempts_and_the_campaign_recording(owner):
    campaign = learn_campaign_v1_rule(owner, DISCOVERY_V2)   # rule v1 records (rule v2: test_lab_backoff_campaign.py)
    execute(owner, campaign, Flaky(lambda slot, request, context: raw(DELAYED, seed=slot), failing={1}))
    retry, = owner.store.list_records('transport_retries')

    async def read():
        transport = httpx.ASGITransport(app=create_app(coordinator=owner))
        async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1') as client:
            return (await client.get(f'/api/campaigns/{campaign.campaign_id}/search-attempts')).json()
    rows = asyncio.run(read())
    retried = [row for row in rows if row['transport_retries']]
    assert len(retried) == 1 and retried[0]['usage']['model_calls'] == 2
    assert retried[0]['transport_retries'] == [{'retry_id': retry['retry_id'], 'code': 'CONNECTION_ERROR', 'attempt': 1,
                                                'provider_failure_id': retry['provider_failure_id']}]
    assert all(row['transport_retries'] == [] and row['usage']['model_calls'] == 1 for row in rows if row is not retried[0])
    with owner.store.transaction() as db:   # the fake runner's minimal episode rows are not exportable episodes
        db.execute("DELETE FROM records WHERE kind='episodes' AND json_extract(payload,'$.campaign_id')=?", (campaign.campaign_id,))
    recording = development_recording(owner.store, campaign.campaign_id)
    assert [r['retry_id'] for r in recording['transport_retries']] == [retry['retry_id']]
    assert any(s.get('transport_retries') for s in recording['selections'])
