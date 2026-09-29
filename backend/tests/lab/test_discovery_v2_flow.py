"""Discovery protocol v2 through the real learning loop, offline.

A scripted Explorer answers from fixed text (including the 8 saved raw outputs of the closed
campaign c701e850, read only as fixture data) and a fake Actor runner records episodes.
No provider, simulator port, W&B or model call is made.
"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.explorer import PROMPT, DISCOVERY_V2_PROMPT
from app.config import Settings
from app.contracts.models import CampaignRequest, ExplorerOutput, canonical_json
from app.lab.budgets import CampaignLedger
from app.lab.challenge import schedule_identity_v2
from app.lab.coordinator import LabCoordinator
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2, DiscoveryV2, campaign_discovery
from app.lab.learning import run_learning_cycle
from app.lab.operator_actions import register_agent
from app.lab.reachability import UnsupportedTarget
from app.lab.run_plans import RunPlanRequest, TASK, TASK_TEXT, build_run_options, prepare_run_plan, read_run_plan
from app.lab.storage import StoreConflict
from app.providers.runtime import RuntimeGeneration
from test_evaluation import FakeRunner

C701 = json.loads((Path(__file__).resolve().parents[1] / 'fixtures' / 'c701e850_explorer_outputs.json').read_text())['selections']
EXPLORER_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.fixture
def owner(tmp_path):
    coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path / 'lab'),
        wandb_model='deepseek-ai/DeepSeek-V3.1', wandb_explorer_model=EXPLORER_MODEL))
    try: yield coordinator
    finally: asyncio.run(coordinator.close())


def request(owner, registration, **overrides):
    options = build_run_options(owner.settings, owner.store)
    return RunPlanRequest(**{'expected_store_identity': options['data_store']['identity'],
        'expected_setup_hash': options['setup_hash'], 'task_definition_id': TASK, 'mode': 'learn',
        'config_profile_id': 'live-v1', 'task_text': TASK_TEXT, 'order_id': 'order-planned',
        'agent_registration_id': registration.registration_id, **overrides})


def learn_campaign(owner, protocol=None, agent='reference'):
    registration = register_agent(owner.store, owner.settings, agent)
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration, discovery_protocol=protocol))
    return owner.create(prepared.campaign_request, run_plan=prepared)


def P(kind, tool, service, occurrence, **parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': occurrence, 'parameters': parameters}


def raw(*primitives, seed=1):
    return canonical_json({'fault_spec': {'seed': seed, 'primitives': list(primitives)}, 'hypothesis': 'Offline scripted selection'})


STATUS_ORDERS = lambda count=1: P('F4', 'get_operation_status', 'orders', 1, failure_count=count)  # NOT_FORCED (N2)
DELAYED = P('F2', 'update_order', 'orders', 1, completion_delay_ticks=3, terminal_status='SUCCEEDED', failure_code=None)  # FORCED


class ScriptedExplorer:
    """Answers each request from a function of (slot, request number); records every context."""
    def __init__(self, answer):
        self.answer = answer; self.contexts = []; self.systems = []
    def role_model(self, role): return EXPLORER_MODEL
    async def complete(self, messages, **kwargs):
        context = json.loads(messages[-1]['content'])
        self.contexts.append(context); self.systems.append(messages[0]['content'])
        return RuntimeGeneration(self.answer(context['selection_index'], context.get('slot_request', 1), context),
                                 EXPLORER_MODEL, input_tokens=100, output_tokens=20)


def run(owner, campaign, answer, *, mode='tie', mutate=None):
    ledger = CampaignLedger(owner.store, campaign.campaign_id, owner.get(campaign.campaign_id).caps)
    owner.ledgers[campaign.campaign_id] = ledger
    class Evidence:
        async def get(self, episode_id, context, **kwargs):
            return SimpleNamespace(episode_id=episode_id, source='weave_verified', report=None, findings=[], observations=[])
    owner.evidence_gateway = Evidence()
    runner = FakeRunner(mode); runner.provider = ScriptedExplorer(answer); original = runner.run
    async def persisted(current, recipe, policy, **kwargs):
        trial = await original(current, recipe, policy, **kwargs)
        if mutate: mutate(trial)
        owner.store.put_record('episodes', trial.episode_id, {'campaign_id': current.campaign_id,
            'configuration_hash': current.configuration_hash, 'policy_hash': policy.policy_hash, 'scenario_hash': trial.scenario_hash,
            'split': 'development', 'experiment_purpose': 'discovery', 'study_id': current.campaign_id,
            'evidence_context_id': current.campaign_id, 'selector_id': None,
            'verdict': {'fault_executions': [{'triggered': True, 'reason': None} for _ in recipe.primitives]}})
        return trial
    runner.run = persisted
    asyncio.run(run_learning_cycle(owner, campaign, runner))
    selections = sorted(owner.store.list_records('selections'),
                        key=lambda row: (row['context']['selection_index'], (row['search_decision'] or {}).get('slot_request', 1)))
    return ledger, runner, selections


def statuses(selections):
    return [(row['context']['selection_index'], row['search_decision'].get('slot_request', 1), row['search_decision']['status']) for row in selections]


# ---------------------------------------------------------------- c701e850 replay
def test_c701e850_outputs_through_v2_refuse_unreachable_picks_and_replan_once(owner):
    campaign = learn_campaign(owner, DISCOVERY_V2)
    # Worst case: the Explorer ignores the feedback and repeats its own answer on the re-plan.
    ledger, runner, selections = run(owner, campaign, lambda slot, _request, _context: C701[slot]['raw'])
    assert statuses(selections) == [
        (0, 1, 'SELECTED'), (1, 1, 'SELECTED'),
        (2, 1, 'SKIPPED_UNREACHABLE'), (2, 2, 'SKIPPED_DUPLICATE'),
        (3, 1, 'SELECTED'), (4, 1, 'SELECTED'),
        (5, 1, 'SKIPPED_UNREACHABLE'), (5, 2, 'SKIPPED_DUPLICATE'),
        (6, 1, 'SKIPPED_DUPLICATE'), (6, 2, 'SKIPPED_DUPLICATE'),   # pick 6 repeats refused pick 2
        (7, 1, 'SKIPPED_UNREACHABLE'), (7, 2, 'SKIPPED_DUPLICATE')]
    assert len(runner.calls) == 4 and ledger.used_calls == len(runner.provider.contexts) == 12
    by_ref = {row['selection_id']: row for row in selections}
    for row in selections:
        decision = row['search_decision']
        assert decision['discovery_protocol'] == DISCOVERY_V2
        recipe = (row['selected_output'] or {}).get('fault_spec') or decision['refused_fault_spec']
        assert decision['schedule_hash'] == schedule_identity_v2(ExplorerOutput.model_validate({'fault_spec': recipe, 'hypothesis': 'x'}).fault_spec)
        if decision['slot_request'] == 2:
            first = by_ref[decision['replan_of']]
            assert first['context']['selection_index'] == row['context']['selection_index']
            assert first['search_decision']['status'] in ('SKIPPED_UNREACHABLE', 'SKIPPED_DUPLICATE')
        if decision['status'] == 'SKIPPED_UNREACHABLE':
            faults = decision['reachability']['faults']
            assert any(f['verdict'] == 'NOT_FORCED' and f['reason_code'] == 'N2_UNNEEDED_STATUS_CHECK' for f in faults)
            assert all(f['explanation'] for f in faults)
    pick7 = next(row for row in selections if row['context']['selection_index'] == 7 and row['search_decision']['slot_request'] == 1)
    assert [f['verdict'] for f in pick7['search_decision']['reachability']['faults']] == ['NOT_FORCED', 'FORCED']
    # The re-plan request was shown the refused recipe and the templated reasons, in words.
    replan = next(c for c in runner.provider.contexts if c['selection_index'] == 2 and c.get('slot_request') == 2)
    feedback = replan['slot_feedback']
    assert feedback['status'] == 'SKIPPED_UNREACHABLE' and 'get_operation_status:orders attempt 1' in feedback['refused_recipe'][0]
    assert 'checks status only while an operation is pending' in feedback['faults'][0]['explanation']
    first = runner.provider.contexts[0]
    assert first['normal_path']['calls'] == ['get_order:orders', 'update_order:orders', 'send_confirmation:notifications']
    assert any('no wait action' in fact for fact in first['agent_action_space'])
    assert first['selection_budget'] == {'slots': 8, 'explorer_requests_max': 16, 'actor_episodes_max': 8, 'replans_per_slot': 1}
    assert first['search_ledger']['schema_version'] == 'faultlab-discovery-search/v2'
    last = runner.provider.contexts[-1]
    assert 'excluded_schedule_hashes' not in last['search_ledger'] and last['search_ledger']['excluded_recipes']
    assert all(isinstance(line, str) for recipe in last['search_ledger']['excluded_recipes'] for line in recipe)
    tested = last['search_ledger']['tested_schedules']
    assert len(tested) == 4 and all(result['reason_code'] == 'FIRED' for row in tested for result in row['fault_results'])
    assert all(system == PROMPT + '\n' + DISCOVERY_V2_PROMPT for system in runner.provider.systems)
    assert owner.get(campaign.campaign_id).state == 'NO_CHANGE'


def test_c701e850_outputs_through_the_default_v1_protocol_reproduce_the_recorded_decisions(owner):
    campaign = learn_campaign(owner)  # no discovery setting: the plan declares v1
    assert read_run_plan(owner.store, campaign)['plan']['discovery']['protocol'] == DISCOVERY_V1
    ledger, runner, selections = run(owner, campaign, lambda slot, _request, _context: C701[slot]['raw'])
    assert [row['search_decision']['status'] for row in selections] == [row['recorded_status'] for row in C701]
    assert [row['search_decision']['schedule_hash'] for row in selections] == [row['recorded_schedule_hash'] for row in C701]
    assert all(set(row['search_decision']) == {'status', 'schedule_hash', 'reason', 'prior_selection_refs', 'prior_episode_refs'} for row in selections)
    assert len(runner.calls) == 7 and ledger.used_calls == 8
    assert all(system == PROMPT for system in runner.provider.systems)
    assert all('slot_request' not in c and 'normal_path' not in c and c['search_ledger']['schema_version'] == 'faultlab-discovery-search/v1'
               for c in runner.provider.contexts)


def test_c701e850_with_an_explorer_that_uses_the_feedback_gets_every_slot_an_episode(owner):
    campaign = learn_campaign(owner, DISCOVERY_V2)
    alternatives = {2: raw(P('F1', 'update_order', 'orders', 1, response_delay_ms=2000)),
                    5: raw(P('F4', 'send_confirmation', 'notifications', 1, failure_count=2)),
                    6: raw(P('F4', 'update_order', 'orders', 1, failure_count=2)),
                    7: raw(P('F2', 'update_order', 'orders', 1, completion_delay_ticks=2, terminal_status='FAILED', failure_code='UPGRADE_REJECTED'))}
    ledger, runner, selections = run(owner, campaign, lambda slot, number, _c: C701[slot]['raw'] if number == 1 else alternatives[slot])
    assert len(runner.calls) == 8 and ledger.used_calls == 12
    assert sum(row['search_decision']['status'] == 'SELECTED' for row in selections) == 8


# ---------------------------------------------------------------- re-plan and budget
def test_refused_then_forced_replan_runs_one_episode_with_linked_records(owner):
    campaign = learn_campaign(owner, DISCOVERY_V2)
    campaign.caps.discovery_selections = 1  # in-memory loop bound only; the saved plan and campaign keep 8
    _, runner, selections = run(owner, campaign, lambda slot, number, _c: raw(STATUS_ORDERS()) if number == 1 else raw(DELAYED))
    assert statuses(selections) == [(0, 1, 'SKIPPED_UNREACHABLE'), (0, 2, 'SELECTED')]
    assert selections[1]['search_decision']['replan_of'] == selections[0]['selection_id']
    assert len(runner.calls) == 1 and runner.calls[0][1].primitives[0].kind == 'F2'


def test_refused_then_refused_again_ends_the_slot_without_a_third_request(owner):
    campaign = learn_campaign(owner, DISCOVERY_V2)
    campaign.caps.discovery_selections = 1  # in-memory loop bound only; the saved plan and campaign keep 8
    ledger, runner, selections = run(owner, campaign, lambda slot, number, _c: raw(STATUS_ORDERS(number)))
    assert statuses(selections) == [(0, 1, 'SKIPPED_UNREACHABLE'), (0, 2, 'SKIPPED_UNREACHABLE')]
    assert not runner.calls and ledger.used_calls == 2 and len(runner.provider.contexts) == 2


def test_declared_budget_holds_with_every_request_refused(owner):
    campaign = learn_campaign(owner, DISCOVERY_V2)
    plan = read_run_plan(owner.store, campaign)['plan']['discovery']
    assert (plan['slots'], plan['explorer_requests_max'], plan['actor_episodes_max'], plan['replans_per_slot']) == (8, 16, 8, 1)
    ledger, runner, selections = run(owner, campaign, lambda slot, number, _c: raw(STATUS_ORDERS(2 * slot + number)))
    assert len(selections) == 16 and ledger.used_calls == 16 and not runner.calls
    assert all(row['search_decision']['status'] == 'SKIPPED_UNREACHABLE' for row in selections)
    assert all(row['selected_output'] is None and row['search_decision']['refused_fault_spec'] for row in selections)
    assert owner.get(campaign.campaign_id).state == 'NO_CHANGE'


def test_invalid_output_keeps_the_fixed_fallback_which_is_forced(owner):
    campaign = learn_campaign(owner, DISCOVERY_V2)
    campaign.caps.discovery_selections = 1  # in-memory loop bound only; the saved plan and campaign keep 8
    _, runner, selections = run(owner, campaign, lambda *_: 'not JSON')
    assert statuses(selections) == [(0, 1, 'SELECTED')]
    assert selections[0]['provenance'] == 'fixed_invalid_output_fallback' and selections[0]['search_decision']['reachability']['all_forced']
    assert len(runner.calls) == 1


def test_a_precheck_failure_keeps_the_charged_answer_and_stops_loudly(owner, monkeypatch):
    campaign = learn_campaign(owner, DISCOVERY_V2)
    async def broken(self, recipe): raise RuntimeError('replay unavailable')
    monkeypatch.setattr('app.lab.discovery_protocol.DiscoveryV2.label', broken)
    with pytest.raises(RuntimeError, match='replay unavailable'):
        run(owner, campaign, lambda *_: raw(DELAYED))
    saved = owner.store.list_records('selections')
    assert len(saved) == 1 and saved[0]['search_decision']['status'] == 'PRECHECK_FAILED'
    assert saved[0]['raw'] == raw(DELAYED) and saved[0]['selected_output'] is None
    assert not owner.store.list_records('episodes')


def test_fully_fired_violation_still_goes_to_reproduction_unchanged(owner, monkeypatch):
    campaign = learn_campaign(owner, DISCOVERY_V2)
    campaign.caps.discovery_selections = 1  # in-memory loop bound only; the saved plan and campaign keep 8
    seen = []
    async def source(self, current, trial, recipe, incumbent, **kwargs):
        seen.append((trial.outcome, trial.failed_checks, recipe))
        return SimpleNamespace(reproduced=False), []
    monkeypatch.setattr('app.lab.learning.Reproducer.source', source)
    run(owner, campaign, lambda *_: raw(DELAYED), mode='gain')
    assert len(seen) == 1 and seen[0][0] == 'VIOLATION' and seen[0][1] == ['C3']


# ---------------------------------------------------------------- declaration and scope
def test_native_agent_cannot_declare_v2_and_the_runtime_refuses_it_too(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents')
    with pytest.raises(StoreConflict, match='native agent'):
        prepare_run_plan(owner.store, owner.settings, request(owner, registration, discovery_protocol=DISCOVERY_V2))
    v1 = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    assert v1.plan['discovery']['protocol'] == DISCOVERY_V1
    block = next(row for row in build_run_options(owner.settings, owner.store)['learn']['discovery_protocols'] if row['protocol_id'] == DISCOVERY_V2)
    assert block['supported_agents'] == ['reference'] and not block['default']
    with pytest.raises(UnsupportedTarget):
        DiscoveryV2(block['declaration'], agent='smolagents', incumbent=owner.policies.baseline())


def test_discovery_setting_is_learn_only_and_older_plans_mean_v1(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    with pytest.raises(ValueError, match='Learn'):
        request(owner, registration, mode='baseline', development_case_id='dev-2', discovery_protocol=DISCOVERY_V1)
    options = build_run_options(owner.settings, owner.store)
    assert [row['protocol_id'] for row in options['learn']['discovery_protocols']] == [DISCOVERY_V1, DISCOVERY_V2]
    v2 = learn_campaign(owner, DISCOVERY_V2)
    saved = read_run_plan(owner.store, v2)['plan']['discovery']
    assert saved['protocol'] == DISCOVERY_V2 and saved['schedule_identity'].endswith('v2-order-aware')
    assert saved['pre_check']['caller_model']['max_business_calls'] == 7
    assert campaign_discovery(owner.store, v2) == saved
    legacy = owner.create(CampaignRequest(task_text='Upgrade', order_id='order-legacy', mode='learn', config_profile_id='live-v1'))
    assert campaign_discovery(owner.store, legacy)['protocol'] == DISCOVERY_V1


def test_new_plan_records_carry_a_discovery_field_and_a_plan_saved_before_it_still_verifies_as_v1(owner, monkeypatch):
    """Review finding (LOW, September 28): new plan records are not byte-identical to earlier ones.
    A Learn plan stores its declared block (v1 by default) and a baseline plan stores
    discovery = null, so both hash differently from a record made before the field existed.
    Such an older record has no discovery key; its hash is checked on the raw record, so it
    still verifies and reads back as v1."""
    from app.lab import run_plans
    registration = register_agent(owner.store, owner.settings, 'reference')
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline',
                                                                    development_case_id='dev-2'))
    baseline = owner.create(baseline.campaign_request, run_plan=baseline)
    stored = owner.store.get_record('campaign_plans', baseline.campaign_id)
    assert 'discovery' in stored and stored['discovery'] is None
    learn = learn_campaign(owner)
    assert owner.store.get_record('campaign_plans', learn.campaign_id)['discovery']['protocol'] == DISCOVERY_V1

    class SavedBeforeTheField(run_plans.SavedRunPlan):
        def model_dump(self, **kwargs):
            data = super().model_dump(**kwargs)
            data.pop('discovery', None)
            return data
    monkeypatch.setattr(run_plans, 'SavedRunPlan', SavedBeforeTheField)
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration, order_id='order-older-plan'))
    prepared.plan.pop('discovery')
    older = owner.create(prepared.campaign_request, run_plan=prepared)
    monkeypatch.undo()
    raw_record = owner.store.get_record('campaign_plans', older.campaign_id)
    assert 'discovery' not in raw_record
    read = read_run_plan(owner.store, older)
    assert read['status'] == 'PLANNED' and read['plan']['discovery'] is None
    assert read['plan']['plan_hash'] == raw_record['plan_hash']
    assert campaign_discovery(owner.store, older)['protocol'] == DISCOVERY_V1
