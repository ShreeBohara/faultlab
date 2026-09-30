"""faultlab-explorer-selection/v3-history-fireability (app.lab.fireability), offline and $0.

Live runs v2d and v2f ended every challenge INCONCLUSIVE on one challenge pick, a lone F4 fault on the orders
get_operation_status read, whose fault seldom fires (with a healthy upgrade neither arm reads the status). Discovery picks
spent slots on the same target. New discovery v3-history and v4 Learn plans now freeze a per-target table computed from
exactly the plan's frozen same-agent history, and refuse (before any episode) a discovery or challenge pick with a fault
on a target that has at least 3 verified history episodes and a fired share below 1/2; the Explorer gets one re-plan
per refused pick inside the Explorer requests the plan already declares.

Records are seeded with the product's shapes (test_agent_history.Seeder); the learning loop and the challenge run with
the scripted Explorer and fake Actor runner of test_discovery_v2_flow.py and test_evaluation.py. The saved-store tests
read a scratch copy of /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 (opened mode=ro&immutable=1 for the
copy; the original is never written) at a pinned, recorded snapshot (SNAPSHOT_CUTOFF below: the record cutoff live run
v2g's own plan froze), so later live runs cannot change their expected numbers; they are skipped where the store is
absent. No provider, W&B, model, simulator port or network call is made; scripted answers are fixture text, not model
evidence.
"""
import asyncio
import json
from pathlib import Path
from unittest import mock

import httpx
import pytest

import test_discovery_v2_flow as flow
from app.agents.explorer import CHALLENGER, PROMPT, Explorer
from app.contracts.models import ExplorerOutput, FaultSpec, canonical_json, content_hash
from app.lab import agent_history, fireability
from app.lab.agent_history import HistoryChanged
from app.lab.challenge import Challenger
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2, DISCOVERY_V3, DISCOVERY_V3_PRECHECK, DISCOVERY_V4
from app.lab.evaluation import PairedEvaluator
from app.lab.exports import development_recording
from app.lab.operator_actions import register_agent
from app.lab.run_plans import (ExplorerSelectionPlan, SavedRunPlan, build_run_options, prepare_run_plan, read_run_plan,
                               validate_run_plan)
from app.lab.storage import StoreConflict
from app.providers.runtime import RuntimeGeneration
from test_agent_history import CASES, P, Seeder, case, plan_request, spec
from test_discovery_v3_flow import Recording
from test_evaluation import cases, setup

owner = flow.owner
anyio_backend = flow.anyio_backend

STATUS = P('F4', 'get_operation_status', 'orders', 1, failure_count=1)      # the v2d / v2f lone status-read pick
STATUS_2 = P('F4', 'get_operation_status', 'orders', 1, failure_count=2)
DELAYED = lambda ticks: P('F2', 'update_order', 'orders', 1, completion_delay_ticks=ticks, terminal_status='SUCCEEDED', failure_code=None)
CONFIRM = P('F4', 'send_confirmation', 'notifications', 1, failure_count=1)
STATUS_TARGET = ('F4', 'orders', 'get_operation_status')


def raw(*primitives, seed=1):
    return canonical_json({'fault_spec': {'seed': seed, 'primitives': list(primitives)}, 'hypothesis': 'Offline scripted pick'})


def row_of(table, key=STATUS_TARGET):
    return next((row for row in table['rows'] if (row['kind'], row['target_service'], row['target_tool']) == key), None)


def seed_status_history(seeder, *, fired=(False, False, False), healthy_dev5=3):
    """dev-5 (F2 on update_order) fired in every verified episode; the Explorer's lone status-read pick fired as given."""
    for _ in range(healthy_dev5):
        seeder.episode(case('dev-5'), failed=('C3',))
    learn = seeder.learn_campaign()
    pick = spec({'seed': 7, 'primitives': [STATUS]})
    seeder.select(pick, learn)
    for triggered in fired:
        seeder.episode(pick, via='campaign', triggered=triggered)
    return pick


# ---------------------------------------------------------------- the table: only the frozen history's own episodes
def test_the_table_counts_only_the_eligible_starting_policy_history(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    seeder = Seeder(owner, registration)
    pick = seed_status_history(seeder)
    before = seeder.history()
    table = fireability.compute_table(owner.store, before)
    assert row_of(table) == {'kind': 'F4', 'target_service': 'orders', 'target_tool': 'get_operation_status',
                             'verified_episodes': 3, 'fired_episodes': 0, 'fired_share': '0/3', 'status': 'REFUSED'}
    assert row_of(table, ('F2', 'orders', 'update_order'))['fired_share'] == '3/3'
    assert table['verified_episodes'] == before['summary']['verified_episodes'] == 6
    assert table['history_episode_ids_hash'] == before['episode_ids_hash'] and table['history_summary_hash'] == before['summary_hash']
    # The same target FIRED in every one of these, and none of them may count: a candidate policy, the challenge, source
    # validation, reproduction, reduction, intervention, the B1 control, another agent, an unverified or lab-error
    # episode, a single-case baseline run (operator-chosen), and a history replay slot.
    learn = seeder.learn_campaign()
    seeder.episode(pick, via='campaign', policy_hash='c' * 64)                           # a candidate policy
    for purpose in ('challenge', 'source_validation', 'reproduction', 'reduction', 'intervention'):
        seeder.episode(pick, via='campaign', purpose=purpose)
    seeder.episode(pick, via='campaign', arm='B1')
    seeder.episode(pick, via='campaign', verified=False)
    seeder.episode(pick, via='campaign', lifecycle='LAB_ERROR')
    seeder.episode(pick, via=seeder.campaign.campaign_id, campaign=seeder.campaign)       # the baseline's single-case run
    other = register_agent(owner.store, owner.settings, 'reference')
    other_seeder = Seeder(owner, other)
    other_seeder.select(pick, other_seeder.learn_campaign())
    other_seeder.episode(pick, via='campaign')                                           # another agent
    replayed = seeder.episode(pick, via='campaign')                                     # a history replay slot
    owner.store.put_record('selections', 'selection-replay', {'selection_id': 'selection-replay', 'challenge': False,
        'provenance': 'history_replay', 'history_replay': {'episode_id': replayed}, 'selected_output': None,
        'context': {'campaign_id': learn.campaign_id}})
    after = seeder.history()
    assert fireability.compute_table(owner.store, after)['rows'] == table['rows']
    assert after['summary']['verified_episodes'] == 6 and after['summary']['excluded']['lab_error'] == 1
    # An eligible verified episode that fired does count.
    seeder.episode(pick, via='campaign', triggered=True)
    grown = fireability.compute_table(owner.store, seeder.history())
    assert row_of(grown)['fired_share'] == '1/4' and row_of(grown)['status'] == 'REFUSED'


def test_the_threshold_is_at_least_three_verified_episodes_and_a_share_below_one_half():
    assert [fireability.row_status(v, f) for v, f in ((1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (4, 1), (4, 2), (6, 3), (7, 3))] == \
        ['ALLOWED_FEWER_THAN_3', 'ALLOWED_FEWER_THAN_3', 'REFUSED', 'REFUSED', 'ALLOWED', 'REFUSED', 'ALLOWED', 'ALLOWED', 'REFUSED']
    assert (fireability.MIN_VERIFIED_EPISODES, fireability.MIN_FIRED_SHARE_TEXT) == (3, '1/2')


def test_a_recipe_with_two_faults_counts_each_target_once_per_episode(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    seeder = Seeder(owner, registration)
    both = spec({'seed': 3, 'primitives': [DELAYED(2), STATUS]})
    seeder.select(both, seeder.learn_campaign())
    episodes = [seeder.episode(both, via='campaign') for _ in range(3)]
    # Record per-fault firing as the simulator does (fault-1, fault-2 by position): the delay fired, the status read fired once.
    for index, episode_id in enumerate(episodes):
        record = owner.store.get_record('episodes', episode_id)
        record['verdict']['fault_executions'] = [{'fault_id': 'fault-1', 'triggered': True}, {'fault_id': 'fault-2', 'triggered': index == 0}]
        owner.store.put_record('episodes', episode_id, record)
    table = fireability.compute_table(owner.store, seeder.history())
    assert row_of(table)['fired_share'] == '1/3' and row_of(table, ('F2', 'orders', 'update_order'))['fired_share'] == '3/3'
    # Two faults on the same target: the episode counts once, and as fired only when EVERY fault there fired.
    twice = spec({'seed': 4, 'primitives': [STATUS, P('F4', 'get_operation_status', 'orders', 3, failure_count=1)]})
    seeder.select(twice, seeder.learn_campaign())
    for fired in ([True, False], [True, True]):
        episode_id = seeder.episode(twice, via='campaign')
        record = owner.store.get_record('episodes', episode_id)
        record['verdict']['fault_executions'] = [{'triggered': flag} for flag in fired]
        owner.store.put_record('episodes', episode_id, record)
    assert row_of(fireability.compute_table(owner.store, seeder.history()))['fired_share'] == '2/5'


# ---------------------------------------------------------------- plans
@pytest.mark.parametrize('protocol', [DISCOVERY_V3, DISCOVERY_V4])
def test_new_v3_history_and_v4_plans_freeze_the_rule_and_the_table_from_their_history(owner, protocol):
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    seed_status_history(Seeder(owner, registration))
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=protocol))
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    plan = read_run_plan(owner.store, campaign)['plan']
    block = plan['explorer_selection']
    history = plan['discovery']['history']
    assert {k: v for k, v in block.items() if k not in ('table', 'table_hash')} == fireability.declaration()
    assert block['table'] == fireability.compute_table(owner.store, history) and block['table_hash'] == content_hash(block['table'])
    assert block['table']['record_cutoff'] == history['record_cutoff'] and block['table']['refused_targets'] == [
        'F4 on get_operation_status (orders): fired in 0 of 3 verified history episodes (below 1/2 of at least 3)']
    assert ExplorerSelectionPlan.model_validate(block).model_dump(mode='json') == block
    # The discovery block itself (budget, dispatch, history) is exactly what it was before the rule.
    assert plan['discovery']['explorer_requests_max'] == 8 and plan['discovery']['replans_per_slot'] == 0
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))['plan_hash'] == plan['plan_hash']


def test_no_other_plan_declares_it_and_run_options_offer_it_without_a_table(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    for protocol in (None, DISCOVERY_V1, DISCOVERY_V2, DISCOVERY_V3_PRECHECK):
        prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=protocol))
        campaign = owner.create(prepared.campaign_request, run_plan=prepared)
        assert 'explorer_selection' not in owner.store.get_record('campaign_plans', campaign.campaign_id)
    baseline = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, mode='baseline', development_case_id='dev-5'))
    assert 'explorer_selection' not in baseline.plan
    offered = build_run_options(owner.settings, owner.store)['learn']['explorer_selection']
    assert offered == fireability.declaration() and 'table' not in offered
    assert offered['discovery_protocols'] == [DISCOVERY_V3, DISCOVERY_V4] and offered['candidate_dependent'] is False


def test_start_refuses_another_rule_and_a_table_that_no_longer_matches_the_store(owner, monkeypatch):
    registration = register_agent(owner.store, owner.settings, 'reference')
    seeder = Seeder(owner, registration)
    both = spec({'seed': 3, 'primitives': [DELAYED(2), STATUS]})
    seeder.select(both, seeder.learn_campaign())
    episode_id = seeder.episode(both, via='campaign')
    record = owner.store.get_record('episodes', episode_id)
    record['verdict']['fault_executions'] = [{'triggered': True}, {'triggered': False}]
    owner.store.put_record('episodes', episode_id, record)
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V3))
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) is not None
    from app.lab import run_plans
    monkeypatch.setattr(run_plans, 'explorer_selection_declaration', lambda: {**fireability.declaration(), 'rule': 'another rule'})
    with pytest.raises(StoreConflict, match='Explorer selection rule'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    monkeypatch.undo()
    # The same episode, the other fault fired instead: the history summary is unchanged (not every fault fired either
    # way), so only the table can notice. Start and the check before the first request refuse.
    record['verdict']['fault_executions'] = [{'triggered': False}, {'triggered': True}]
    owner.store.put_record('episodes', episode_id, record)
    plan = read_run_plan(owner.store, campaign)['plan']
    registration_record = owner.store.get_record('agent_registrations', plan['agent_registration_id'])
    configuration = owner.store.get_record('configurations', plan['configuration_hash'])
    agent_history.verify(owner.store, plan['discovery']['history'], registration=registration_record,
                         configuration=configuration, policy_hash=plan['initial_policy_hash'])     # the history still verifies
    with pytest.raises(HistoryChanged, match='fireability table no longer matches'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    from app.lab.learning import discovery_history
    with pytest.raises(HistoryChanged):
        discovery_history(owner.store, owner.get(campaign.campaign_id))


def test_saved_plan_models_refuse_inconsistent_tables(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents')
    seed_status_history(Seeder(owner, registration))
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V4))
    plan = read_run_plan(owner.store, owner.create(prepared.campaign_request, run_plan=prepared))['plan']
    block = plan['explorer_selection']
    def changed(**table_rows):
        table = json.loads(json.dumps(block['table']))
        for key, value in table_rows.items(): table['rows'][-1 if key == 'last' else 0].update(value)
        return {**block, 'table': table, 'table_hash': content_hash(table)}
    status_row = next(i for i, row in enumerate(block['table']['rows']) if row['target_tool'] == 'get_operation_status')
    for bad in ({**block, 'table_hash': 'd' * 64}, {**block, 'min_fired_share': '2/3'}, {**block, 'candidate_dependent': True},
                {**block, 'discovery_protocols': [DISCOVERY_V3]}):
        with pytest.raises(ValueError):
            ExplorerSelectionPlan.model_validate(bad)
    table = json.loads(json.dumps(block['table'])); table['rows'][status_row]['status'] = 'ALLOWED'
    with pytest.raises(ValueError):
        ExplorerSelectionPlan.model_validate({**block, 'table': table, 'table_hash': content_hash(table)})
    table = json.loads(json.dumps(block['table'])); table['refused_targets'] = []
    with pytest.raises(ValueError):
        ExplorerSelectionPlan.model_validate({**block, 'table': table, 'table_hash': content_hash(table)})
    # A status that does not follow its counts, even with a refused list that agrees with it (only the row check sees it).
    table = json.loads(json.dumps(block['table']))
    fired_row = next(row for row in table['rows'] if row['status'] == 'ALLOWED')
    fired_row['status'] = 'REFUSED'
    table['refused_targets'] = [fireability.refused_text(row) for row in table['rows'] if row['status'] == 'REFUSED']
    with pytest.raises(ValueError, match='Inconsistent history fireability row'):
        ExplorerSelectionPlan.model_validate({**block, 'table': table, 'table_hash': content_hash(table)})
    # Bound to the plan's own frozen history.
    table = json.loads(json.dumps(block['table'])); table['history_summary_hash'] = 'e' * 64
    other = {**plan, 'explorer_selection': {**block, 'table': table, 'table_hash': content_hash(table)}}
    SavedRunPlan.model_validate(other)   # the model alone cannot know the history...
    from app.lab.run_plans import _bindings
    with pytest.raises(StoreConflict, match='another agent history'):
        _bindings(owner.store, owner.get(plan['campaign_id']), other)   # ...the bindings can
    with pytest.raises(StoreConflict, match='declares the history fireability rule'):
        _bindings(owner.store, owner.get(plan['campaign_id']), {**plan, 'discovery': {**plan['discovery'], 'protocol': DISCOVERY_V1}})


# ---------------------------------------------------------------- discovery through the real learning loop
def status_owner(owner, agent='smolagents'):
    registration = register_agent(owner.store, owner.settings, agent)
    seeder = Seeder(owner, registration)
    seed_status_history(seeder)
    return seeder


def run_learn(owner, protocol, answer, *, monkeypatch, slots=None, agent='smolagents'):
    campaign = flow.learn_campaign(owner, protocol, agent)
    if slots is not None:
        campaign.caps.discovery_selections = slots  # in-memory loop bound only; the saved plan and campaign keep 8
    ledger, runner, selections = run_loop(owner, campaign, answer)
    return campaign, ledger, runner, selections


def run_loop(owner, campaign, answer, *, mode='tie'):
    """test_discovery_v2_flow.run with the Recording Explorer, returning only this campaign's discovery selections (a saved
    store also holds other campaigns' challenge picks, which have no selection_index); its episode records also carry
    their episode_id, as the product's do, so the dashboard's experiments endpoint can read them."""
    from types import SimpleNamespace
    from app.lab.budgets import CampaignLedger
    from app.lab.learning import run_learning_cycle
    from test_evaluation import FakeRunner
    ledger = CampaignLedger(owner.store, campaign.campaign_id, owner.get(campaign.campaign_id).caps)
    owner.ledgers[campaign.campaign_id] = ledger
    class Evidence:
        async def get(self, episode_id, context, **kwargs):
            return SimpleNamespace(episode_id=episode_id, source='weave_verified', report=None, findings=[], observations=[])
    owner.evidence_gateway = Evidence()
    runner = FakeRunner(mode); runner.provider = Recording(answer); original = runner.run
    async def persisted(current, recipe, policy, **kwargs):
        trial = await original(current, recipe, policy, **kwargs)
        owner.store.put_record('episodes', trial.episode_id, {'episode_id': trial.episode_id, 'campaign_id': current.campaign_id,
            'configuration_hash': current.configuration_hash, 'policy_hash': policy.policy_hash, 'policy_version': policy.version,
            'scenario_hash': trial.scenario_hash, 'arm': kwargs['arm'], 'lifecycle': trial.lifecycle,
            'split': 'development', 'experiment_purpose': 'discovery', 'study_id': current.campaign_id,
            'evidence_context_id': current.campaign_id, 'selector_id': None,
            'verdict': {'fault_executions': [{'triggered': True, 'reason': None} for _ in recipe.primitives]}})
        return trial
    runner.run = persisted
    asyncio.run(run_learning_cycle(owner, campaign, runner))
    rows = [row for row in owner.store.list_records('selections') if (row.get('context') or {}).get('campaign_id') == campaign.campaign_id]
    rows.sort(key=lambda row: (row['context']['selection_index'], row['context'].get('slot_request', 1)))
    return ledger, runner, rows


def fire_status(rows):
    return [(row['context']['selection_index'], row['context'].get('slot_request'), row['search_decision']['status'],
             row['fireability']['status']) for row in rows]


def test_a_discovery_pick_on_the_target_is_refused_and_replanned_once_within_the_declared_requests(owner, monkeypatch):
    status_owner(owner)
    # Slot 0 picks the lone status read (refused), its re-plan picks a delayed upgrade; every later slot picks a new delay.
    answer = lambda slot, number, _c: raw(STATUS) if (slot, number) == (0, 1) else raw(DELAYED(slot + 1 if number == 1 else 9))
    campaign, ledger, runner, rows = run_learn(owner, DISCOVERY_V3, answer, monkeypatch=monkeypatch)
    assert fire_status(rows)[:3] == [(0, 1, 'SKIPPED_UNFIREABLE', 'REFUSED_LOW_FIRED_SHARE'), (0, 2, 'SELECTED', 'ALLOWED'),
                                     (1, 1, 'SELECTED', 'ALLOWED')]
    refused, replan = rows[0], rows[1]
    assert refused['selected_output'] is None and runner.calls[0][1].primitives[0].kind == 'F2'
    decision = refused['fireability']
    assert decision['refused_targets'] == [{'kind': 'F4', 'target_service': 'orders', 'target_tool': 'get_operation_status',
                                            'verified_episodes': 3, 'fired_episodes': 0, 'fired_share': '0/3', 'status': 'REFUSED'}]
    assert decision['refused_fault_spec']['primitives'] == [STATUS] and decision['pick'] == 'model'
    assert 'fired in 0 of 3 verified history episodes' in decision['reason'] and "slot's one re-plan" in decision['reason']
    assert refused['search_decision']['reason'] == 'HISTORY_FIRED_SHARE_BELOW_HALF'
    assert replan['context']['replan_of'] == refused['selection_id'] and replan['fireability']['replan_of'] == refused['selection_id']
    assert replan['context']['slot_feedback']['refused_targets'] == decision['refused_targets']
    # Budget: the plan declares 8 discovery Explorer requests. The re-plan was one of them, so the last slot sent none,
    # ran nothing and is recorded; every request was charged exactly once.
    assert len(runner.provider.messages) == ledger.used_calls == 8 and len(runner.calls) == 7
    assert [row['context']['selection_index'] for row in rows] == [0, 0, 1, 2, 3, 4, 5, 6]
    unrequested, = owner.store.list_records('explorer_selection_slots')
    assert (unrequested['selection_index'], unrequested['explorer_requests_used'], unrequested['explorer_requests_max'],
            unrequested['replans_after_refusals']) == (7, 8, 8, 1)
    # The request states the rule and carries the frozen table, and later requests list the refused pick.
    plan = read_run_plan(owner.store, campaign)['plan']
    first = json.loads(runner.provider.messages[0][1]['content'])
    assert first['explorer_selection_protocol'] == fireability.EXPLORER_SELECTION_V3 and first['slot_request'] == 1
    assert first['history_fireability']['rule'] == fireability.RULE and first['history_fireability']['rows'] == plan['explorer_selection']['table']['rows']
    later = json.loads(runner.provider.messages[2][1]['content'])
    assert later['history_fireability']['refused_picks'][0]['refused_selection_id'] == refused['selection_id']
    assert owner.get(campaign.campaign_id).state == 'NO_CHANGE'


def test_a_v4_plans_replay_slots_leave_room_for_replans_and_other_targets_run(owner, monkeypatch):
    status_owner(owner)   # dev-5 violated 3 of 3: one replay row
    answer = lambda slot, number, _c: raw(STATUS) if (slot, number) == (1, 1) else raw(DELAYED(slot + 1 if number == 1 else 9))
    campaign, ledger, runner, rows = run_learn(owner, DISCOVERY_V4, answer, monkeypatch=monkeypatch)
    assert rows[0]['provenance'] == 'history_replay' and 'fireability' not in rows[0]   # FaultLab's replay: not an Explorer pick
    assert fire_status(rows[1:3]) == [(1, 1, 'SKIPPED_UNFIREABLE', 'REFUSED_LOW_FIRED_SHARE'), (1, 2, 'SELECTED', 'ALLOWED')]
    # 7 Explorer slots and one re-plan: 8 requests, the declared number; every slot ran one episode.
    assert len(runner.provider.messages) == ledger.used_calls == 8 and len(runner.calls) == 8
    assert not owner.store.list_records('explorer_selection_slots')


def test_a_refused_replan_ends_the_slot_without_a_third_request(owner, monkeypatch):
    status_owner(owner)
    answer = lambda slot, number, _c: raw(STATUS if number == 1 else STATUS_2)
    _, ledger, runner, rows = run_learn(owner, DISCOVERY_V3, answer, slots=1, monkeypatch=monkeypatch)
    assert fire_status(rows) == [(0, 1, 'SKIPPED_UNFIREABLE', 'REFUSED_LOW_FIRED_SHARE'), (0, 2, 'SKIPPED_UNFIREABLE', 'REFUSED_LOW_FIRED_SHARE')]
    assert 'already the slot\'s re-plan' in rows[1]['fireability']['reason']
    assert not runner.calls and ledger.used_calls == len(runner.provider.messages) == 2


def test_duplicates_keep_todays_rule_and_an_invalid_answer_uses_the_checked_fallback(owner, monkeypatch):
    status_owner(owner)
    answer = lambda slot, number, _c: 'not json' if slot == 2 else raw(DELAYED(1))
    _, ledger, runner, rows = run_learn(owner, DISCOVERY_V3, answer, slots=3, monkeypatch=monkeypatch)
    assert [(r['search_decision']['status'], r['fireability']['status'], r['fireability']['pick']) for r in rows] == [
        ('SELECTED', 'ALLOWED', 'model'), ('SKIPPED_DUPLICATE', 'NOT_CHECKED_DUPLICATE', 'model'),
        ('SELECTED', 'ALLOWED', 'fixed_invalid_output_fallback')]
    assert 'slot_feedback' not in json.loads(runner.provider.messages[2][1]['content'])   # a duplicate gets no re-plan
    assert len(runner.calls) == 2 and ledger.used_calls == 3


def test_a_plan_saved_before_the_rule_keeps_todays_requests_and_records(owner, monkeypatch):
    """A v3-history plan without the block (saved before the rule): the same lone status pick runs, as in v2c/v2e/v2f."""
    status_owner(owner)
    from app.lab import run_plans
    monkeypatch.setattr(run_plans, 'FIREABILITY_PROTOCOLS', ())
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    monkeypatch.undo()
    assert 'explorer_selection' not in owner.store.get_record('campaign_plans', campaign.campaign_id)
    campaign.caps.discovery_selections = 2
    monkeypatch.setattr(flow, 'ScriptedExplorer', Recording)
    ledger, runner, rows = flow.run(owner, campaign, lambda slot, number, _c: raw(STATUS if slot == 0 else DELAYED(1)))
    monkeypatch.undo()
    rows = [r for r in rows if r['context']['campaign_id'] == campaign.campaign_id]
    assert [r['search_decision']['status'] for r in rows] == ['SELECTED', 'SELECTED'] and len(runner.calls) == 2
    assert not any('fireability' in r for r in rows)
    assert all(set(r['search_decision']) == {'status', 'schedule_hash', 'reason', 'prior_selection_refs', 'prior_episode_refs'} for r in rows)
    assert not any(key in json.loads(user['content']) for _, user in runner.provider.messages
                   for key in ('explorer_selection_protocol', 'history_fireability', 'slot_request'))


# ---------------------------------------------------------------- challenge picks (real Explorer and Challenger)
def block_for(rows):
    table = {'schema_version': fireability.TABLE_SCHEMA, 'meaning': fireability.MEANING, 'history_summary_hash': 'a' * 64,
             'history_episode_ids_hash': 'b' * 64, 'record_cutoff': 1, 'verified_episodes': max([r['verified_episodes'] for r in rows] + [0]),
             'rows': rows, 'refused_targets': [fireability.refused_text(r) for r in rows if r['status'] == 'REFUSED']}
    return {**fireability.declaration(), 'table': table, 'table_hash': content_hash(table)}


def table_row(kind, service, tool, verified, fired):
    return {'kind': kind, 'target_service': service, 'target_tool': tool, 'verified_episodes': verified,
            'fired_episodes': fired, 'fired_share': f'{fired}/{verified}', 'status': fireability.row_status(verified, fired)}


STATUS_BLOCK = block_for([table_row('F2', 'orders', 'update_order', 10, 10), table_row('F4', 'orders', 'get_operation_status', 4, 0)])


class Scripted:
    def __init__(self, answers):
        self.answers = list(answers); self.contexts = []; self.systems = []
    def role_model(self, role): return 'openai/gpt-oss-120b'
    async def complete(self, messages, **kwargs):
        self.systems.append(messages[0]['content']); self.contexts.append(json.loads(messages[-1]['content']))
        return RuntimeGeneration(self.answers.pop(0), 'openai/gpt-oss-120b', input_tokens=100, output_tokens=20)


async def challenge(tmp_path, answers, *, block=STATUS_BLOCK):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    ledger.reserve('candidate', 528)
    provider = Scripted(answers); explorer = Explorer(provider, c.store, ledger)
    explorer.fireability = fireability.Session(block, discovery_requests_max=8) if block is not None else None
    before = len(runner.calls)
    result = await Challenger(c.store, explorer, evaluator).run(campaign, c.policies.baseline(), candidate, source, reservation='candidate')
    selections = [c.store.get_record('selections', ref) for ref in result.selection_refs]
    return result, provider, selections, len(runner.calls) - before, ledger


@pytest.mark.anyio
async def test_a_challenge_pick_on_the_target_is_refused_and_replanned_once_inside_the_eight_requests(tmp_path):
    answers = [raw(STATUS), raw(DELAYED(1)), raw(DELAYED(2)), raw(DELAYED(3)), raw(DELAYED(4))]
    result, provider, selections, episodes, ledger = await challenge(tmp_path, answers)
    assert [s['fireability']['status'] for s in selections] == ['REFUSED_LOW_FIRED_SHARE'] + ['ALLOWED'] * 4
    assert episodes == 4 * 6 and len(result.trial_pairs) == 12 and result.status == 'PASSED_OBSERVED'
    refused = selections[0]['fireability']
    assert refused['refused_targets'] == [table_row('F4', 'orders', 'get_operation_status', 4, 0)] and refused['purpose'] == 'challenge'
    assert 'The next request in this challenge is its one re-plan' in refused['reason']
    assert [ctx['slot_request'] for ctx in provider.contexts] == [1, 2, 1, 1, 1] and ledger.used_calls == 5
    assert provider.contexts[1]['replan_of'] == selections[0]['selection_id']
    assert provider.contexts[1]['slot_feedback']['refused_targets'] == refused['refused_targets']
    assert provider.contexts[0]['history_fireability']['rows'] == STATUS_BLOCK['table']['rows']
    assert all(system == PROMPT + '\n' + CHALLENGER for system in provider.systems)   # the rule is in the request, not the prompt


@pytest.mark.anyio
async def test_the_challenge_stays_within_eight_requests_and_a_refused_replan_gets_none(tmp_path):
    result, provider, selections, episodes, ledger = await challenge(tmp_path, [raw(STATUS, seed=n) for n in range(8)])
    assert len(provider.contexts) == ledger.used_calls == 8 and episodes == 0
    assert [ctx['slot_request'] for ctx in provider.contexts] == [1, 2, 1, 2, 1, 2, 1, 2]
    assert result.status == 'INCONCLUSIVE' and result.stopping_reason == 'Fewer than four feasible schedules'
    assert 'already the re-plan' in selections[1]['fireability']['reason']


@pytest.mark.anyio
async def test_challenge_picks_on_other_targets_run_exactly_as_without_the_rule(tmp_path):
    answers = [raw(DELAYED(1)), raw(CONFIRM), raw(DELAYED(3)), raw(P('F1', 'update_order', 'orders', 1, response_delay_ms=2000))]
    ruled = await challenge(tmp_path / 'ruled', list(answers))
    plain = await challenge(tmp_path / 'plain', list(answers), block=None)
    for result, provider, selections, episodes, ledger in (ruled, plain):
        assert (result.status, len(result.trial_pairs), result.failed_checks, episodes, ledger.used_calls) == ('PASSED_OBSERVED', 12, [], 24, 4)
    assert [s['fireability']['status'] for s in ruled[2]] == ['ALLOWED'] * 4
    assert [t['status'] for t in ruled[2][1]['fireability']['targets']] == ['NOT_IN_HISTORY']   # not in the table: allowed
    # Without the rule (every plan without the block), the challenge request is today's: no new field, no record field.
    assert not any(key in ctx for ctx in plain[1].contexts for key in ('history_fireability', 'explorer_selection_protocol', 'slot_request'))
    assert not any('fireability' in s for s in plain[2])


@pytest.mark.anyio
async def test_challenge_decisions_come_only_from_the_sessions_frozen_block(tmp_path):
    """The Session holds only the frozen table: filling the store with candidate and challenge episodes whose status reads
    all fired changes no challenge decision. (Renamed by the fixer, review LOW-2: this does not show that the TABLE never
    reads such episodes; the first test and test_history_fireability_review_fixes.py
    test_a_plan_saved_after_fired_candidate_and_challenge_episodes_freezes_the_same_table do, through the product path.)"""
    answers = [raw(STATUS), raw(DELAYED(1)), raw(DELAYED(2)), raw(DELAYED(3)), raw(DELAYED(4))]
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    for index in range(12):
        c.store.put_record('episodes', f'episode-candidate-{index}', {'episode_id': f'episode-candidate-{index}', 'campaign_id': campaign.campaign_id,
            'split': 'development', 'experiment_purpose': 'challenge' if index % 2 else 'source_validation', 'arm': 'L',
            'policy_hash': candidate.policy_hash, 'verdict': {'fault_executions': [{'triggered': True}]}})
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    ledger.reserve('candidate', 528)
    explorer = Explorer(Scripted(answers), c.store, ledger)
    explorer.fireability = fireability.Session(STATUS_BLOCK, discovery_requests_max=8)
    result = await Challenger(c.store, explorer, evaluator).run(campaign, c.policies.baseline(), candidate, source, reservation='candidate')
    assert [c.store.get_record('selections', ref)['fireability']['status'] for ref in result.selection_refs] == \
        ['REFUSED_LOW_FIRED_SHARE'] + ['ALLOWED'] * 4


# ---------------------------------------------------------------- shown in the API and the recording
def api_json(owner, *paths):
    from app.main import create_app
    async def fetch():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            return [(await api.get(path)).json() for path in paths]
    return asyncio.run(fetch())


def test_the_api_and_the_recording_show_the_rule_the_table_and_every_decision(owner, monkeypatch):
    status_owner(owner)
    answer = lambda slot, number, _c: raw(STATUS) if (slot, number) == (0, 1) else raw(DELAYED(slot + 1 if number == 1 else 9))
    campaign, ledger, runner, rows = run_learn(owner, DISCOVERY_V3, answer, monkeypatch=monkeypatch)
    ident = campaign.campaign_id
    saved, attempts, experiments = api_json(owner, f'/api/campaigns/{ident}/plan', f'/api/campaigns/{ident}/search-attempts',
                                            f'/api/campaigns/{ident}/experiments')
    plan = saved['plan']
    assert plan['explorer_selection']['table']['refused_targets'][0].startswith('F4 on get_operation_status (orders)')
    assert [a['fireability']['status'] for a in attempts][:2] == ['REFUSED_LOW_FIRED_SHARE', 'ALLOWED']
    summary = experiments['explorer_fireability']
    assert (summary['picks_checked'], summary['picks_refused'], len(summary['slots_without_request'])) == (8, 1, 1)
    assert summary['table_hash'] == plan['explorer_selection']['table_hash']
    recording = development_recording(owner.store, ident)
    assert recording['explorer_selection_rule']['rule'] == fireability.RULE and recording['explorer_selection_rule']['picks_refused'] == 1
    assert recording['selections'][0]['fireability']['status'] == 'REFUSED_LOW_FIRED_SHARE'
    assert recording['run_plan']['plan']['explorer_selection'] == plan['explorer_selection']


def test_campaigns_without_the_rule_keep_their_exact_api_fields(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V1))
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    experiments, = api_json(owner, f'/api/campaigns/{campaign.campaign_id}/experiments')
    assert set(experiments) == {'counterexamples', 'evidence', 'ingestions', 'portability_ids'}
    assert 'explorer_selection_rule' not in development_recording(owner.store, campaign.campaign_id)


# ---------------------------------------------------------------- the saved native-v2b store (scratch copy, pinned snapshot)
SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
needs_store = pytest.mark.skipif(not SAVED.exists(), reason='Needs the saved native-v2b store (live runs v2c-v2f); absent on this machine')
# Live runs keep adding to this store: run v2g, after these tests were written, added 6 verified discovery episodes and 6
# discovery picks (36 instead of 30 episodes; 14 instead of 8 allowed discovery picks). So the tests read the store at a
# fixed, recorded snapshot: the record cutoff at which live run v2g's own saved plan froze its agent history, which is the
# store exactly as live runs v2b-v2f left it. A record written later always gets a higher row number (LabStore
# max_record_rowid), so a read at or below the cutoff never admits it. The new plan below must reproduce v2g's frozen
# history byte for byte (its summary hash is pinned too), so an edit to an older record would fail here loudly instead of
# silently changing the expected numbers.
SNAPSHOT_PLAN = 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530'        # live run v2g
SNAPSHOT_CUTOFF = 6748
SNAPSHOT_SUMMARY_HASH = 'd581867ce0f5c102314f508a9758eaf9fc9e1cacf589f394a834d80cec026a0e'


@pytest.fixture
def saved_owner(tmp_path):
    """A coordinator over a scratch copy of the saved store (the original is read with mode=ro&immutable=1 only)."""
    from citation_status_saved import copy_read_only, remove_copy
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    target = tmp_path / 'lab' / 'lab.sqlite3'; target.parent.mkdir()
    copy_read_only(str(SAVED), str(target))
    coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(target.parent), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                          wandb_explorer_model=flow.EXPLORER_MODEL))
    try: yield coordinator
    finally:
        asyncio.run(coordinator.close())
        assert remove_copy(str(target))


def saved_v4_plan(owner):
    """A new discovery v4 Learn plan for the native v2 agent, its agent history frozen at the pinned snapshot.

    The product freezes a plan's history at the store's current record cutoff (agent_history.snapshot reads
    store.max_record_rowid once); here that one read returns SNAPSHOT_CUTOFF, so this is exactly the plan this build would
    have made just before live run v2g. Its replay list and fireability table are functions of that history, and Start
    (validate_run_plan) recomputes all three at the plan's own cutoff, as for any plan."""
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    with mock.patch.object(owner.store, 'max_record_rowid', return_value=SNAPSHOT_CUTOFF) as now:
        prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V4))
    assert now.call_count == 1                          # the history's record cutoff is the only "now" the plan reads
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    plan = read_run_plan(owner.store, campaign)['plan']
    history = plan['discovery']['history']
    assert (history['record_cutoff'], history['summary_hash']) == (SNAPSHOT_CUTOFF, SNAPSHOT_SUMMARY_HASH)
    return campaign, plan


def snapshot_rows(store, kind):
    """The saved store's records of one kind as they were at the pinned snapshot, in row order."""
    return [payload for _, payload in store.records_upto(kind, SNAPSHOT_CUTOFF)]


V2B_TABLE = [('F1', 'orders', 'update_order', 4, 4, 'ALLOWED'), ('F2', 'orders', 'update_order', 10, 10, 'ALLOWED'),
             ('F3', 'orders', 'get_order', 4, 4, 'ALLOWED'), ('F4', 'notifications', 'send_confirmation', 4, 4, 'ALLOWED'),
             ('F4', 'orders', 'get_operation_status', 4, 0, 'REFUSED'), ('F4', 'orders', 'get_order', 1, 1, 'ALLOWED_FEWER_THAN_3')]


@needs_store
def test_a_new_v4_plan_on_the_saved_store_refuses_the_lone_status_read_target(saved_owner):
    campaign, plan = saved_v4_plan(saved_owner)
    history, table = plan['discovery']['history'], plan['explorer_selection']['table']
    assert history['summary']['verified_episodes'] == table['verified_episodes'] == 30
    assert history['summary']['composition'] == {'baseline_studies': 1, 'baseline_study_episodes': 18, 'learn_campaigns': 2,
                                                  'learn_discovery_episodes': 12}
    assert [(r['kind'], r['target_service'], r['target_tool'], r['verified_episodes'], r['fired_episodes'], r['status'])
            for r in table['rows']] == V2B_TABLE
    assert table['refused_targets'] == ['F4 on get_operation_status (orders): fired in 0 of 4 verified history episodes (below 1/2 of at least 3)']
    assert validate_run_plan(saved_owner.store, saved_owner.settings, saved_owner.get(campaign.campaign_id))['plan_hash'] == plan['plan_hash']
    # The snapshot is the one live run v2g froze: this plan's history, replay list and table equal its saved plan's.
    v2g = saved_owner.store.get_record('campaign_plans', SNAPSHOT_PLAN)
    assert v2g['discovery']['history'] == history and v2g['discovery']['replay'] == plan['discovery']['replay']
    assert v2g['explorer_selection']['table'] == table
    # Every plan saved in the store before the rule (v2b-v2f: the five at the snapshot) still reads byte for byte, without the block.
    before = snapshot_rows(saved_owner.store, 'campaign_plans')
    assert len(before) == 5 and campaign.campaign_id not in {saved['campaign_id'] for saved in before}
    for saved in before:
        assert 'explorer_selection' not in saved
        assert SavedRunPlan.model_validate(saved).model_dump(mode='json') == saved
        assert read_run_plan(saved_owner.store, saved['campaign_id'])['status'] == 'PLANNED'


@needs_store
def test_the_saved_stores_status_read_picks_are_refused_and_its_other_picks_are_allowed(saved_owner):
    """Every Explorer pick the saved store recorded at the snapshot (discovery in v2c/v2e/v2f, challenge in v2d/v2f), checked
    against the new plan's table: exactly the picks whose every fault is on the orders status read are refused (fixer: a
    pick is refused only when every fault targets a REFUSED row; every saved status-read pick is a lone one, so the counts
    are unchanged). Picks a later live run added (v2g's and after) are above the snapshot's cutoff and are not read."""
    _, plan = saved_v4_plan(saved_owner)
    session = fireability.Session(plan['explorer_selection'], discovery_requests_max=8)
    decided = []
    for selection in snapshot_rows(saved_owner.store, 'selections'):
        spec_ = (selection.get('output') or {}).get('fault_spec')
        if spec_ is None or selection.get('provenance') == 'history_replay':
            continue
        pick = ExplorerOutput.model_validate({'fault_spec': spec_, 'hypothesis': 'saved pick'})
        context = {'selection_index': 0, 'proposal_index': 0, 'slot_request': 1}
        decision, kept = fireability.decide(session, context, pick, None, challenge=bool(selection['challenge']), provenance='model')
        on_status = [p['target_tool'] == 'get_operation_status' and p['target_service'] == 'orders' for p in spec_['primitives']]
        status_read = all(on_status)
        assert (decision['status'] == 'REFUSED_LOW_FIRED_SHARE') == status_read and (kept is None) == status_read
        assert any(on_status) == status_read   # no saved pick mixes the status read with another target
        decided.append((bool(selection['challenge']), status_read))
    challenge_refused = sum(1 for challenge_, refused in decided if challenge_ and refused)
    discovery_refused = sum(1 for challenge_, refused in decided if not challenge_ and refused)
    assert (challenge_refused, discovery_refused) == (3, 7)
    assert sum(1 for challenge_, refused in decided if challenge_ and not refused) == 8
    assert sum(1 for challenge_, refused in decided if not challenge_ and not refused) == 8


@needs_store
def test_through_the_real_loop_on_the_saved_store_a_status_pick_is_refused_and_replanned(saved_owner, monkeypatch):
    campaign, plan = saved_v4_plan(saved_owner)
    replays = len(plan['discovery']['replay']['rows'])
    assert replays == 2   # dev-5 (3/3) and dev-6 (2/3)
    campaign.caps.discovery_selections = replays + 1   # in-memory loop bound only; the saved plan keeps 8
    answer = lambda slot, number, _c: raw(STATUS) if number == 1 else raw(DELAYED(9))
    ledger, runner, rows = run_loop(saved_owner, campaign, answer)
    assert [r['provenance'] for r in rows[:replays]] == ['history_replay'] * replays
    assert fire_status(rows[replays:]) == [(replays, 1, 'SKIPPED_UNFIREABLE', 'REFUSED_LOW_FIRED_SHARE'), (replays, 2, 'SELECTED', 'ALLOWED')]
    assert rows[replays]['fireability']['refused_targets'][0]['fired_share'] == '0/4'
    assert len(runner.calls) == replays + 1 and ledger.used_calls == 2
