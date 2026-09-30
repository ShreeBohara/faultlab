"""The Mechanic request-size rule is frozen into every new Learn plan, never into baseline/compare plans, and a plan
saved before it keeps its exact bytes and today's behaviour. The challenge-pick rule (v2-candidate-reach) is withdrawn
before any live run (both reviews, HIGH-1: it can hide counterexamples): no new plan declares it, and a plan that does
cannot be created or started. The dashboard and the recording show a declared rule. $0, offline."""
import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.contracts.models import canonical_json, content_hash
from app.lab import loop_limits
from app.lab.exports import development_recording
from app.lab.loop_limits import CHALLENGE_SELECTION_V2, MECHANIC_CONTEXT_V2, challenge_selection_declaration, mechanic_context_declaration
from app.lab.operator_actions import register_agent
from app.lab.run_plans import (ChallengeSelectionPlan, MechanicContextPlan, build_run_options, prepare_run_plan, read_run_plan,
                               validate_run_plan)
from app.lab.storage import StoreConflict
from app.main import create_app
from test_discovery_v2_flow import learn_campaign, owner, request  # noqa: F401  (owner is a fixture)


def test_run_options_and_every_new_learn_plan_declare_the_mechanic_rule_only_and_baseline_plans_neither(owner):
    options = build_run_options(owner.settings, owner.store)
    assert options['learn']['mechanic_context'] == mechanic_context_declaration()
    assert 'challenge_selection' not in options['learn']                     # withdrawn: not offered
    for agent in ('reference', 'smolagents', 'smolagents-v2'):
        campaign = learn_campaign(owner, None, agent)
        plan = read_run_plan(owner.store, campaign)['plan']
        assert plan['mechanic_context'] == mechanic_context_declaration() and 'challenge_selection' not in plan
        assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) == plan
        assert loop_limits.mechanic_context_rule(owner.store, campaign) == mechanic_context_declaration()
        assert loop_limits.challenge_selection_rule(owner.store, campaign) is None
    registration = register_agent(owner.store, owner.settings, 'reference')
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-5'))
    assert 'mechanic_context' not in baseline.plan and 'challenge_selection' not in baseline.plan
    saved = owner.create(baseline.campaign_request, run_plan=baseline)
    assert not {'mechanic_context', 'challenge_selection'} & set(owner.store.get_record('campaign_plans', saved.campaign_id))
    assert not {'mechanic_context', 'challenge_selection'} & set(read_run_plan(owner.store, saved)['plan'])


def older_learn_campaign(owner):
    """A Learn plan exactly as the runtime before these rules saved it (no block at all)."""
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan.pop('mechanic_context'); prepared.plan.pop('challenge_selection', None)
    return owner.create(prepared.campaign_request, run_plan=prepared)


def learn_campaign_declaring_the_withdrawn_rule(owner, monkeypatch):
    """A Learn plan as the unreviewed builder build saved it (both rules), created past today's checks."""
    from app.lab import run_plans
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan['challenge_selection'] = challenge_selection_declaration()
    with monkeypatch.context() as patch:
        patch.setattr(run_plans, 'validate_run_plan', lambda *args, **kwargs: None)
        patch.setattr(run_plans, 'withdrawn_rule_problem', lambda plan: None, raising=False)
        return owner.create(prepared.campaign_request, run_plan=prepared)


def test_a_plan_declaring_the_withdrawn_challenge_rule_cannot_be_created_or_started(owner, monkeypatch):
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan['challenge_selection'] = challenge_selection_declaration()      # exactly the installed declaration
    with pytest.raises(StoreConflict, match='withdrawn before any live run'):
        owner.create(prepared.campaign_request, run_plan=prepared)
    saved = learn_campaign_declaring_the_withdrawn_rule(owner, monkeypatch)
    assert read_run_plan(owner.store, saved)['plan']['challenge_selection'] == challenge_selection_declaration()   # it still reads
    with pytest.raises(StoreConflict, match='withdrawn before any live run'):
        validate_run_plan(owner.store, owner.settings, owner.get(saved.campaign_id))


def test_a_learn_plan_saved_before_the_rules_keeps_its_bytes_starts_and_keeps_todays_behaviour(owner):
    older = older_learn_campaign(owner)
    saved = owner.store.get_record('campaign_plans', older.campaign_id)
    assert not {'mechanic_context', 'challenge_selection'} & set(saved)
    assert saved['plan_hash'] == content_hash({k: v for k, v in saved.items() if k != 'plan_hash'})
    read = read_run_plan(owner.store, older)['plan']
    assert read == saved                                       # no null keys are added when it is read back
    assert validate_run_plan(owner.store, owner.settings, owner.get(older.campaign_id)) == read     # Start accepts it
    assert loop_limits.mechanic_context_rule(owner.store, older) is None
    assert loop_limits.challenge_selection_rule(owner.store, older) is None


@pytest.mark.parametrize('key,change,message', [
    ('mechanic_context', {'rule': 'An older wording of the rule.'}, 'Mechanic request-size rule differs'),
    ('challenge_selection', {'rule': 'An older wording of the rule.'}, 'withdrawn before any live run'),
])
def test_start_refuses_a_plan_whose_declared_rule_is_not_the_installed_one(owner, monkeypatch, key, change, message):
    from app.lab import run_plans
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan[key] = {**prepared.plan.get(key, challenge_selection_declaration()), **change}
    # As if another build (with other rule text) had saved it: that build checked the plan against its own rule.
    monkeypatch.setattr(run_plans, 'validate_run_plan', lambda *args, **kwargs: None)
    monkeypatch.setattr(run_plans, 'withdrawn_rule_problem', lambda plan: None, raising=False)
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    monkeypatch.undo()
    assert read_run_plan(owner.store, campaign)['plan'][key]['rule'] == change['rule']     # it still reads
    with pytest.raises(StoreConflict, match=message):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))


def test_only_a_learn_plan_may_declare_them_and_the_declarations_are_exact(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-1'))
    baseline.plan['mechanic_context'] = mechanic_context_declaration()
    with pytest.raises(StoreConflict, match='Only a Learn plan declares the Mechanic request-size and challenge-pick rules'):
        owner.create(baseline.campaign_request, run_plan=baseline)
    MechanicContextPlan.model_validate(mechanic_context_declaration())
    for change in ({'compaction_target_tokens': 30000}, {'format_repair_reserve_tokens': 0}, {'input_token_limit': 64000},
                   {'stages': ['NO_CLEAN_EPISODE_ROWS'] * 3}, {'when_unfit': 'ERROR'}, {'requests_over_limit_sent': 1},
                   {'applies_to': ['mechanic_proposal', 'mechanic_diagnosis']}, {'protocol': 'faultlab-mechanic-context/v1'}):
        with pytest.raises(ValidationError):
            MechanicContextPlan.model_validate({**mechanic_context_declaration(), **change})
    for change in ({'explorer_requests_per_challenge': 16}, {'replans_per_refused_pick': 2}, {'caller_counted': 'policy'},
                   {'challenge_rules_changed': True}, {'refused_pick_runs_episodes': True}):
        with pytest.raises(ValidationError):
            ChallengeSelectionPlan.model_validate({**challenge_selection_declaration(), **change})


def seed_records(owner, campaign):
    """One source, one Mechanic request-size record and one refused challenge pick, as the loop saves them."""
    ident = campaign.campaign_id
    owner.store.put_record('counterexamples', 'counterexample-x', {'counterexample_id': 'counterexample-x', 'campaign_id': ident,
                                                                   'source_episode_id': 'episode-source'})
    owner.store.put_record('mechanic_context_records', 'mechanic-context-x', {'record_id': 'mechanic-context-x', 'campaign_id': ident,
                           'protocol': MECHANIC_CONTEXT_V2, 'request_kind': 'mechanic_proposal', 'outcome': 'COMPACTED'})
    decision = {'protocol': CHALLENGE_SELECTION_V2, 'status': 'REFUSED_UNREACHED', 'unreached': ['get_operation_status:orders'],
                'slot_request': 1, 'replan_of': None, 'proposal_index': 0, 'reason': 'Refused before any pair ran'}
    spec = {'seed': 1, 'scope': 'orders.upgrade_then_confirm/v1', 'schema_version': 'faultlab/v1',
            'primitives': [{'kind': 'F4', 'target_tool': 'get_operation_status', 'target_service': 'orders', 'occurrence': 1, 'parameters': {'failure_count': 1}}]}
    owner.store.put_record('selections', 'selection-x', {'selection_id': 'selection-x', 'challenge': True, 'context': {'campaign_id': ident, 'candidate_hash': 'c' * 64},
                           'output': {'fault_spec': spec, 'hypothesis': 'x'}, 'selected_output': None, 'challenge_reach': decision})
    owner.store.put_record('challenges', 'challenge-x', {'challenge_id': 'challenge-x', 'selection_refs': ['selection-x']})
    owner.store.put_record('challenge_campaigns', 'challenge-x', {'challenge_id': 'challenge-x', 'campaign_id': ident})


def experiments(owner, ident):
    async def get():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            return (await api.get(f'/api/campaigns/{ident}/experiments')).json()
    return asyncio.run(get())


def test_the_dashboard_projection_and_the_recording_show_both_rules_only_where_declared(owner, monkeypatch):
    # A plan saved by the unreviewed build with both rules still reads and shows both (the challenge rule cannot start).
    new = learn_campaign_declaring_the_withdrawn_rule(owner, monkeypatch); seed_records(owner, new)
    body = experiments(owner, new.campaign_id)
    row, = body['challenge_reach']
    assert row['selection_id'] == 'selection-x' and row['challenge_id'] == 'challenge-x' and row['status'] == 'REFUSED_UNREACHED'
    assert row['recipe'] and row['unreached'] == ['get_operation_status:orders']
    assert [r['record_id'] for r in body['mechanic_context']] == ['mechanic-context-x']
    recording = development_recording(owner.store, new.campaign_id)
    assert [r['record_id'] for r in recording['mechanic_context_records']] == ['mechanic-context-x']
    assert recording['challenge_selection_rule']['refused_selection_ids'] == ['selection-x']
    assert [s['challenge_reach']['status'] for s in recording['selections']] == ['REFUSED_UNREACHED']
    assert recording['run_plan']['plan']['mechanic_context'] == mechanic_context_declaration()
    # A new Learn plan declares the Mechanic rule only: its experiments response has no challenge_reach list.
    current = learn_campaign(owner, None)
    owner.store.put_record('counterexamples', 'counterexample-new', {'counterexample_id': 'counterexample-new', 'campaign_id': current.campaign_id,
                                                                     'source_episode_id': 'episode-new'})
    body = experiments(owner, current.campaign_id)
    assert 'mechanic_context' in body and 'challenge_reach' not in body
    recording = development_recording(owner.store, current.campaign_id)
    assert 'mechanic_context_records' in recording and 'challenge_selection_rule' not in recording
    # A campaign whose plan was saved before the rules gets exactly today's fields.
    older = older_learn_campaign(owner)
    owner.store.put_record('counterexamples', 'counterexample-old', {'counterexample_id': 'counterexample-old', 'campaign_id': older.campaign_id,
                                                                     'source_episode_id': 'episode-old'})
    body = experiments(owner, older.campaign_id)
    assert set(body) == {'counterexamples', 'evidence', 'ingestions', 'portability_ids'}
    recording = development_recording(owner.store, older.campaign_id)
    assert 'mechanic_context_records' not in recording and 'challenge_selection_rule' not in recording
