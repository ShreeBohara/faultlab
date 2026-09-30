"""Discovery protocol v4 (history replay, regression-first discovery), offline and $0.

The replay list is a pure function of v3's frozen agent history (app.lab.history_replay), frozen into the plan. Replay
slots run first through the real learning loop, with the scripted Explorer and fake Actor runner of
test_discovery_v2_flow.py; history is seeded with the product's record shapes (test_agent_history.Seeder). No provider,
simulator port, W&B or model call is made; the scripted answers are fixture text, not model evidence.

Shown here:
* plan freezing and ordering: violation share, then verified episodes, then row order; at most 3 rows; rows with
  fewer than 2 verified episodes, a share under 2/3, an unfired fault or no fault are never replayed; an empty
  history gives an empty list with a plain statement;
* replay slots run first, each with one Actor episode and NO Explorer request; the Explorer then continues with the
  remaining slots, sees the replays as prior selections, and its duplicate rule applies to them;
* a replay VIOLATION becomes a source through the unchanged discovery rule; a replay that does not violate only
  uses its slot;
* every replay is labelled "history replay" with its row: selection record, search-attempts API, source projection,
  recording; a replay source is never an Explorer pick;
* Start and the check before the first replay refuse a changed history; with an empty replay list v4's Explorer
  messages equal v3-history's except the declared protocol id; v1/v2/v3 plans and records are unchanged.
"""
import asyncio
import json
from fractions import Fraction

import httpx
import pytest

import test_discovery_v2_flow as flow
from app.agents.explorer import DISCOVERY_V3_PROMPT, DISCOVERY_V4_PROMPT, PROMPT
from app.contracts.models import Counterexample, FaultSpec, canonical_json, content_hash, new_id
from app.lab import history_replay
from app.lab.agent_history import HistoryChanged
from app.lab.challenge import schedule_identity, schedule_identity_v2
from app.lab.discovery_protocol import (BASE_PROTOCOL, DISCOVERY_V1, DISCOVERY_V3, DISCOVERY_V4, HISTORY_PROTOCOLS,
                                        REPLAY_PROTOCOLS, V4_DISPATCH_RULE)
from app.lab.exports import development_recording
from app.lab.operator_actions import register_agent
from app.lab.run_plans import (DiscoveryPlan, HistoryReplayRow, build_run_options, prepare_run_plan, read_run_plan,
                               validate_run_plan)
from app.lab.storage import StoreConflict
from app.telemetry.safety import public_json
from test_agent_history import CASES, EXPLORED, P, Seeder, case, plan_request
from test_discovery_v3_flow import Recording, c701, complete_fixture_episodes, dev5_repick, normalize

owner = flow.owner
anyio_backend = flow.anyio_backend


# ---------------------------------------------------------------- pure plan freezing (hand-made summaries)
def row(case_id=None, primitives=None, *, verified=3, violations=3, fired=None, recipe=None):
    """One frozen history row in the shape app.lab.agent_history writes."""
    primitives = CASES[case_id]['fault_spec']['primitives'] if primitives is None else primitives
    outcomes = {key: value for key, value in (('COMPLETED', verified - violations), ('VIOLATION', violations)) if value}
    return {'development_case_id': case_id, 'recipe': recipe or [f'fault {index}' for index, _ in enumerate(primitives)] or ['No injected fault'],
            'primitives': primitives, 'sources': ['baseline_study'], 'verified_episodes': verified,
            'every_fault_fired': (None if not primitives else verified if fired is None else fired),
            'outcomes': outcomes, 'failed_checks': {'C3': violations} if violations else {}, 'excluded': {},
            'runtime_hashes': ['a' * 12], 'adapter_hashes': ['b' * 12]}


def summary(*rows):
    return {'status': 'AVAILABLE' if rows else 'NO_PRIOR_HISTORY', 'recipes': list(rows)}


def history_block(*rows):
    body = summary(*rows)
    return {'summary': body, 'summary_hash': content_hash(body)}


F4_ORDERS = [P('F4', 'update_order', 'orders', 1, failure_count=2)]
F1_NOTIFY = [P('F1', 'send_confirmation', 'notifications', 1, response_delay_ms=2000)]


def test_replay_rows_order_by_share_then_verified_count_then_row_order_and_cap_at_three():
    rows = [row('dev-2', verified=3, violations=2),            # 1: share 2/3
            row('dev-3', verified=3, violations=3),            # 2: share 1, 3 verified
            row('dev-4', verified=4, violations=4),            # 3: share 1, 4 verified -> first
            row('dev-5', verified=3, violations=3),            # 4: ties row 2 -> after it (row order)
            row(None, F4_ORDERS, verified=6, violations=5)]    # 5: share 5/6 -> after every share-1 row
    listed = history_replay.replay_rows(summary(*rows))
    assert [(item['replay'], item['history_row'], item['development_case_id']) for item in listed] == \
        [(1, 3, 'dev-4'), (2, 2, 'dev-3'), (3, 4, 'dev-5')]            # capped at 3: rows 5 and 1 are not replayed
    assert history_replay.MAX_REPLAYS == 3
    # Without the cap, 5/6 would come before 2/3.
    uncapped = sorted((index for index, item in enumerate(rows, 1) if history_replay.eligible(item)),
                      key=lambda index: (-history_replay.violation_share(rows[index - 1]), -rows[index - 1]['verified_episodes'], index))
    assert uncapped == [3, 2, 4, 5, 1]
    first = listed[0]
    assert first['violation_share'] == '4/4' and first['violations'] == 4 and first['verified_episodes'] == 4
    assert first['every_fault_fired'] == 4 and first['failed_checks'] == {'C3': 4} and first['sources'] == ['baseline_study']


def test_ties_on_share_and_verified_count_keep_history_row_order():
    rows = [row(None, F1_NOTIFY, verified=2, violations=2), row('dev-5', verified=2, violations=2), row('dev-3', verified=2, violations=2)]
    assert [item['history_row'] for item in history_replay.replay_rows(summary(*rows))] == [1, 2, 3]


def test_ineligible_rows_are_never_replayed():
    no_fault = row('dev-1', verified=3, violations=3)                       # no scheduled fault, even though it violated
    one = row('dev-5', verified=1, violations=1)                            # fewer than 2 verified episodes
    half = row('dev-3', verified=4, violations=2)                           # share 1/2 < 2/3
    unfired = row('dev-6', verified=3, violations=3, fired=2)               # one verified episode did not fire every fault
    exactly = row('dev-2', verified=3, violations=2)                        # share exactly 2/3: eligible
    for item in (no_fault, one, half, unfired):
        assert not history_replay.eligible(item)
    assert history_replay.eligible(exactly) and history_replay.violation_share(exactly) == Fraction(2, 3)
    assert no_fault['every_fault_fired'] is None
    listed = history_replay.replay_rows(summary(no_fault, one, half, unfired, exactly))
    assert [(item['history_row'], item['development_case_id']) for item in listed] == [(5, 'dev-2')]


def test_empty_history_and_no_eligible_rows_say_so_plainly():
    empty = history_replay.plan_block(history_block())
    assert empty['status'] == 'EMPTY' and empty['rows'] == [] and empty['statement'] == history_replay.EMPTY_NO_HISTORY
    assert 'no prior history' in empty['statement'] and 'exactly as v3' in empty['statement']
    none = history_replay.plan_block(history_block(row('dev-1'), row('dev-5', verified=3, violations=1)))
    assert none['status'] == 'EMPTY' and none['rows'] == [] and none['statement'] == history_replay.EMPTY_NONE_ELIGIBLE
    assert 'no row of the frozen agent history meets the replay rule' in none['statement']


def test_replay_recipe_is_the_rows_schedule_a_case_uses_its_public_recipe_otherwise_seed_zero():
    dev5, explored = history_replay.replay_rows(summary(row('dev-5'), row(None, F4_ORDERS)))
    assert dev5['fault_spec'] == CASES['dev-5']['fault_spec']                           # the public case recipe, seed 105
    assert explored['fault_spec'] == FaultSpec(seed=0, primitives=F4_ORDERS).model_dump(mode='json')
    for item, listed in ((dev5, CASES['dev-5']['fault_spec']['primitives']), (explored, F4_ORDERS)):
        recipe = FaultSpec.model_validate(item['fault_spec'])
        assert item['schedule_identity_v2'] == schedule_identity_v2(recipe) == schedule_identity_v2(FaultSpec(seed=0, primitives=listed))


def test_the_frozen_block_records_the_rule_and_is_rechecked():
    history = history_block(row('dev-5'))
    block = history_replay.plan_block(history)
    assert block['rule'] == history_replay.RULE and block['basis'] == 'faultlab-schedule-identity/v2-order-aware'
    assert (block['max_rows'], block['min_verified_episodes'], block['min_violation_share']) == (3, 2, '2/3')
    assert block['history_summary_hash'] == history['summary_hash'] and block['status'] == 'AVAILABLE'
    assert 'at least 2 of every 3 verified episodes ended in VIOLATION' in block['rule'] and 'at most 3' in block['rule']
    assert history_replay.verify(block, history) == block
    tampered = json.loads(json.dumps(block)); tampered['rows'][0]['history_row'] = 2
    with pytest.raises(HistoryChanged, match='create a new plan'):
        history_replay.verify(tampered, history)
    with pytest.raises(HistoryChanged):
        history_replay.verify(block, history_block(row('dev-5'), row('dev-3')))   # a different history gives another list
    with pytest.raises(HistoryChanged):
        history_replay.verify(None, history)


def test_saved_plan_models_refuse_inconsistent_replay_blocks():
    good = history_replay.replay_rows(summary(row('dev-5')))[0]
    HistoryReplayRow.model_validate(good)
    for change in ({'violations': 1}, {'violation_share': '2/3'}, {'every_fault_fired': 2}, {'schedule_identity_v2': 'c' * 64},
                   {'verified_episodes': 1}, {'fault_spec': CASES['dev-1']['fault_spec']}):
        with pytest.raises(ValueError):
            HistoryReplayRow.model_validate({**good, **change})
    assert DISCOVERY_V4 in HISTORY_PROTOCOLS and REPLAY_PROTOCOLS == (DISCOVERY_V4,) and BASE_PROTOCOL[DISCOVERY_V4] == DISCOVERY_V1


# ---------------------------------------------------------------- plans through the product path
def seed_ordering(seeder):
    """Seven history rows (in this order): dev-1 no fault; dev-2 3/3; dev-3 2/3 (never reached: cap); dev-4 4/4;
    dev-5 3/3; dev-6 3/3 with one unfired fault; an Explorer pick with 1 verified episode."""
    for _ in range(3):
        seeder.episode(case('dev-1'), outcome='VIOLATION', failed=('C5',))
        seeder.episode(case('dev-2'), failed=('C5',))
        seeder.episode(case('dev-5'), failed=('C3', 'C5'))
    for failed in (('C5',), ('C5',), ()):
        seeder.episode(case('dev-3'), failed=failed)
    for _ in range(4):
        seeder.episode(case('dev-4'), failed=('C6',))
    seeder.episode(case('dev-6'), failed=('C4',)); seeder.episode(case('dev-6'), failed=('C4',))
    seeder.episode(case('dev-6'), failed=('C4',), triggered=False)
    learn = seeder.learn_campaign()
    seeder.select(EXPLORED, learn)
    seeder.episode(EXPLORED, failed=('C7',), via='campaign')


def v4_plan(owner, registration, **overrides):
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V4, **overrides))
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    return campaign, read_run_plan(owner.store, campaign)['plan']


@pytest.mark.parametrize('agent', ['smolagents', 'smolagents-v2', 'reference'])
def test_plan_freezes_the_replay_list_from_exactly_v3s_history(owner, agent):
    registration = register_agent(owner.store, owner.settings, agent)
    seeder = Seeder(owner, registration)
    seed_ordering(seeder)
    campaign, plan = v4_plan(owner, registration)
    discovery = plan['discovery']
    history, replay = discovery['history'], discovery['replay']
    # Exactly v3-history's history: same eligibility, exclusions, hash and cutoff rule.
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V3))
    v3 = read_run_plan(owner.store, owner.create(prepared.campaign_request, run_plan=prepared))['plan']
    assert {k: v for k, v in history.items() if k != 'record_cutoff'} == {k: v for k, v in v3['discovery']['history'].items() if k != 'record_cutoff'}
    assert history['summary']['excluded']['not_weave_verified'] == 0
    assert [r['development_case_id'] for r in history['summary']['recipes']] == ['dev-1', 'dev-2', 'dev-3', 'dev-4', 'dev-5', 'dev-6', None]
    # The frozen list: share, then verified count, then row order; capped at 3; ineligible rows never listed.
    assert [(r['replay'], r['history_row'], r['development_case_id'], r['violation_share']) for r in replay['rows']] == \
        [(1, 4, 'dev-4', '4/4'), (2, 2, 'dev-2', '3/3'), (3, 5, 'dev-5', '3/3')]
    assert replay['status'] == 'AVAILABLE' and replay['rule'] == history_replay.RULE
    assert replay['history_summary_hash'] == history['summary_hash'] and replay == history_replay.plan_block(history)
    dev5 = replay['rows'][2]
    assert dev5['fault_spec'] == CASES['dev-5']['fault_spec'] and dev5['failed_checks'] == {'C3': 3, 'C5': 3}
    assert dev5['every_fault_fired'] == dev5['verified_episodes'] == 3 and dev5['sources'] == ['baseline_study']
    # Budget and dispatch: v3-history's numbers (8/8/8/8, no re-plans); replay slots count toward them.
    assert {k: v for k, v in discovery.items() if k not in ('protocol', 'history', 'replay', 'dispatch_rule')} == \
        {k: v for k, v in v3['discovery'].items() if k not in ('protocol', 'history', 'dispatch_rule')}
    assert (discovery['slots'], discovery['explorer_requests_max'], discovery['explorer_transport_retries_max'],
            discovery['actor_episodes_max'], discovery['replans_per_slot'], discovery['pre_check']) == (8, 8, 8, 8, 0, None)
    assert discovery['dispatch_rule'] == V4_DISPATCH_RULE and discovery['schedule_identity'] == 'faultlab-schedule-identity/v1-sorted'
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))['plan_hash'] == plan['plan_hash']


def test_empty_history_plan_says_so_and_old_plans_keep_their_bytes(owner):
    native = register_agent(owner.store, owner.settings, 'smolagents')
    _, plan = v4_plan(owner, native)
    replay = plan['discovery']['replay']
    assert plan['discovery']['history']['status'] == 'NO_PRIOR_HISTORY'
    assert replay['status'] == 'EMPTY' and replay['rows'] == [] and replay['statement'] == history_replay.EMPTY_NO_HISTORY
    # Older protocols never get a replay key (not even null): their plan bytes are unchanged.
    for protocol in (None, DISCOVERY_V1, DISCOVERY_V3):
        prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, native, discovery_protocol=protocol))
        campaign = owner.create(prepared.campaign_request, run_plan=prepared)
        stored = owner.store.get_record('campaign_plans', campaign.campaign_id)['discovery']
        assert 'replay' not in stored and ('history' in stored) == (protocol == DISCOVERY_V3)
    # Saved-plan model: v4 needs both frozen blocks; v1/v3 refuse a replay block.
    discovery = plan['discovery']
    DiscoveryPlan.model_validate(discovery)
    with pytest.raises(ValueError):
        DiscoveryPlan.model_validate({k: v for k, v in discovery.items() if k != 'replay'})
    with pytest.raises(ValueError):
        DiscoveryPlan.model_validate({**discovery, 'protocol': DISCOVERY_V3, 'dispatch_rule': 'x'})
    with pytest.raises(ValueError):
        DiscoveryPlan.model_validate({**discovery, 'replay': {**replay, 'history_summary_hash': 'd' * 64}})


def test_run_options_offer_v4_with_one_plain_sentence_and_v3_budget(owner):
    options = {row['protocol_id']: row for row in build_run_options(owner.settings, owner.store)['learn']['discovery_protocols']}
    v4, v3 = options[DISCOVERY_V4], options[DISCOVERY_V3]
    assert v4['default'] is False and v4['supported_agents'] == ['reference', 'smolagents', 'smolagents-v2']
    assert v4['description'].count('. ') == 0 and v4['description'].endswith('.') and 'Explorer' in v4['description']
    assert v4['declaration']['history'] is None and v4['declaration']['replay'] is None
    assert {k: v for k, v in v4['declaration'].items() if k not in ('protocol', 'dispatch_rule', 'replay')} == \
        {k: v for k, v in v3['declaration'].items() if k not in ('protocol', 'dispatch_rule')}
    assert [row['protocol_id'] for row in options.values() if row['default']] == [DISCOVERY_V1]


# ---------------------------------------------------------------- the learning loop
def dev5_owner(owner, agent='smolagents'):
    registration = register_agent(owner.store, owner.settings, agent)
    seeder = Seeder(owner, registration)
    for _ in range(3):
        seeder.episode(case('dev-5'), failed=('C3', 'C5'))
        seeder.episode(case('dev-1'))
    return seeder


def run_v4(owner, answer, *, mode='tie', slots=None, monkeypatch):
    campaign = flow.learn_campaign(owner, DISCOVERY_V4, 'smolagents')
    if slots is not None:
        campaign.caps.discovery_selections = slots  # in-memory loop bound only; the saved plan and campaign keep 8
    monkeypatch.setattr(flow, 'ScriptedExplorer', Recording)
    ledger, runner, selections = flow.run(owner, campaign, answer, mode=mode)
    monkeypatch.undo()
    # Only this campaign's records (a seeded history may hold an earlier campaign's recorded pick).
    return campaign, ledger, runner, [row for row in selections if row['context']['campaign_id'] == campaign.campaign_id]


def test_replay_slots_run_first_without_an_explorer_request_and_the_explorer_continues(owner, monkeypatch):
    dev5_owner(owner)
    campaign, ledger, runner, selections = run_v4(owner, c701, monkeypatch=monkeypatch)
    plan = read_run_plan(owner.store, campaign.campaign_id)['plan']
    replay = plan['discovery']['replay']
    assert [(r['history_row'], r['development_case_id']) for r in replay['rows']] == [(2, 'dev-5')]
    # Slot 0 is the replay: one Actor episode of the dev-5 recipe, no Explorer request and no model charge.
    first = selections[0]
    assert first['context']['selection_index'] == 0 and first['provenance'] == 'history_replay'
    assert first['usage'] == {'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost_dollars': 0.0}
    assert first['raw'] == '' and first['model_id'] is None and 'transport_retries' not in first
    assert first['search_decision'] == {'status': 'SELECTED', 'schedule_hash': schedule_identity(FaultSpec.model_validate(CASES['dev-5']['fault_spec'])),
                                        'reason': None, 'prior_selection_refs': [], 'prior_episode_refs': [],
                                        'history_replay': {'replay': 1, 'history_row': 2, 'development_case_id': 'dev-5'}}
    block = first['history_replay']
    assert block['label'] == 'history replay' and block['explorer_request'] is False and block['episode_id'] == runner.calls[0][3]['episode_id']
    assert (block['replay'], block['of'], block['history_row'], block['violation_share']) == (1, 1, 2, '3/3')
    assert first['matches_history_row'] == {'row': 2, 'development_case_id': 'dev-5', 'basis': 'faultlab-schedule-identity/v2-order-aware'}
    assert runner.calls[0][1].model_dump(mode='json') == CASES['dev-5']['fault_spec']
    assert 'History replay 1 of 1' in first['selected_output']['hypothesis'] and 'not by the Explorer' in first['selected_output']['hypothesis']
    # The Explorer continues with the other 7 slots; the replay counted toward the 8 slots and 8 Actor episodes.
    explorer_rows = selections[1:]
    assert [row['context']['selection_index'] for row in explorer_rows] == list(range(1, 8))
    assert all(row['provenance'] != 'history_replay' and 'history_replay' not in row for row in explorer_rows)
    assert len(runner.provider.messages) == ledger.used_calls == 7
    assert [json.loads(user['content'])['selection_index'] for _, user in runner.provider.messages] == list(range(1, 8))
    assert len(runner.calls) == 1 + sum(row['search_decision']['status'] == 'SELECTED' for row in explorer_rows) <= 8
    # What the Explorer saw: the frozen history, its v3 section plus the v4 section, and the replay as a prior selection.
    context = json.loads(runner.provider.messages[0][1]['content'])
    assert context['discovery_protocol'] == DISCOVERY_V4 and context['agent_history'] == plan['discovery']['history']['summary']
    assert 'history_replay' not in context and 'replay_prompt' not in context
    assert {system['content'] for system, _ in runner.provider.messages} == {PROMPT + '\n' + DISCOVERY_V3_PROMPT + '\n' + DISCOVERY_V4_PROMPT}
    prior = context['search_ledger']['prior_selections']
    assert [(p['selection_index'], p['status'], p['history_replay']) for p in prior] == [(0, 'SELECTED', {'replay': 1, 'history_row': 2, 'development_case_id': 'dev-5'})]
    assert [t['episode_id'] for t in context['search_ledger']['tested_schedules']] == [block['episode_id']]
    assert owner.get(campaign.campaign_id).state == 'NO_CHANGE'


def test_the_explorer_duplicate_rule_applies_to_the_replayed_recipe(owner, monkeypatch):
    dev5_owner(owner)
    _, ledger, runner, selections = run_v4(owner, dev5_repick, slots=3, monkeypatch=monkeypatch)
    assert [row['search_decision']['status'] for row in selections] == ['SELECTED', 'SKIPPED_DUPLICATE', 'SKIPPED_DUPLICATE']
    replay = selections[0]
    assert selections[1]['search_decision']['prior_selection_refs'] == [replay['selection_id']]
    assert selections[1]['search_decision']['prior_episode_refs'] == [replay['history_replay']['episode_id']]
    assert selections[1]['matches_history_row']['row'] == 2  # the Explorer's own pick is still flagged history-informed
    assert len(runner.calls) == 1 and ledger.used_calls == 2


def record_sources(owner, monkeypatch):
    """Record each source exactly as Reproducer.source does, then stop (no reproduction trials here)."""
    sources = []
    async def source(self, current, trial, recipe, incumbent, **kwargs):
        counter = Counterexample(counterexample_id=new_id('counterexample'), campaign_id=current.campaign_id,
                                 agent_registration_id=read_run_plan(owner.store, current.campaign_id)['plan']['agent_registration_id'],
                                 source_episode_id=trial.episode_id, target_invariant='C3', scenario_hash=content_hash(recipe),
                                 configuration_hash=current.configuration_hash, report_ref=trial.episode_id, verdict_ref=trial.episode_id)
        owner.store.put_record('counterexamples', counter.counterexample_id, counter)
        owner.store.put_record('counterexample_recipes', counter.counterexample_id,
                               {'source_recipe': recipe.model_dump(mode='json'), 'fixture_id': 'standard-v1'}, immutable=True)
        sources.append((counter.counterexample_id, trial.episode_id))
        from types import SimpleNamespace
        return SimpleNamespace(reproduced=False), []
    monkeypatch.setattr('app.lab.learning.Reproducer.source', source)
    return sources


def dashboard(owner, campaign_id):
    from app.main import create_app
    async def read():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            return ((await api.get(f'/api/campaigns/{campaign_id}/search-attempts')).json(),
                    (await api.get(f'/api/campaigns/{campaign_id}/experiments')).json())
    return asyncio.run(read())


def test_a_replay_violation_becomes_a_source_and_is_labelled_a_history_replay_everywhere(owner, monkeypatch):
    dev5_owner(owner)
    sources = record_sources(owner, monkeypatch)
    alternative = lambda *_: flow.raw(*F4_ORDERS)
    campaign, _, runner, selections = run_v4(owner, alternative, mode='gain', slots=2, monkeypatch=monkeypatch)
    replay_episode = selections[0]['history_replay']['episode_id']
    # The unchanged rule: completed, every fault fired, VIOLATION -> Reproducer.source, for the replay and the pick alike.
    assert [episode for _, episode in sources] == [replay_episode, runner.calls[1][3]['episode_id']]
    complete_fixture_episodes(owner)  # the fake runner's episode records lack the id the product runner writes
    attempts, experiments = dashboard(owner, campaign.campaign_id)
    assert attempts[0]['history_replay']['history_row'] == 2 and attempts[0]['provenance'] == 'history_replay'
    assert attempts[0]['usage']['model_calls'] == 0 and 'history_replay' not in attempts[1]
    by_source = {row['counterexample']['source_episode_id']: row for row in experiments['counterexamples']}
    found = by_source[replay_episode]['history_replay']
    assert found['label'] == 'history replay' and found['history_row'] == 2 and found['development_case_id'] == 'dev-5'
    assert found['selection_id'] == selections[0]['selection_id']
    assert by_source[runner.calls[1][3]['episode_id']]['history_replay'] is None     # an Explorer pick: not a replay
    recording = development_recording(owner.store, campaign.campaign_id)
    recorded = {row['selection_id']: row for row in recording['selections']}
    assert recorded[selections[0]['selection_id']]['history_replay']['history_row'] == 2
    assert recorded[selections[0]['selection_id']]['provenance'] == 'history_replay'
    assert 'history_replay' not in recorded[selections[1]['selection_id']]
    replays = recording['discovery_history_replays']
    assert replays['label'] == 'history replay' and replays['status'] == 'AVAILABLE'
    assert [slot['episode_id'] for slot in replays['replay_slots']] == [replay_episode]
    assert replays['sources_found_by_replay'] == [sources[0][0]]
    assert 'never as independent discovery' in replays['claim_rule'] and replays['replay_list'] == read_run_plan(
        owner.store, campaign.campaign_id)['plan']['discovery']['replay']['rows']  # by id: the in-memory caps were narrowed
    matches = {s['counterexample_id']: s for s in recording['discovery_history_matches']['sources']}
    assert matches[sources[0][0]]['history_replay']['history_row'] == 2 and matches[sources[1][0]]['history_replay'] is None
    assert public_json(recording, max_bytes=64 * 1024 * 1024) == recording


def test_a_replay_that_does_not_violate_only_uses_its_slot(owner, monkeypatch):
    dev5_owner(owner)
    sources = record_sources(owner, monkeypatch)
    _, ledger, runner, selections = run_v4(owner, lambda *_: flow.raw(*F4_ORDERS), mode='tie', slots=2, monkeypatch=monkeypatch)
    assert sources == [] and len(runner.calls) == 2 and ledger.used_calls == 1
    assert [row['provenance'] for row in selections] == ['history_replay', 'model']


def test_at_most_three_replays_then_the_explorer_takes_the_remaining_slots(owner, monkeypatch):
    registration = register_agent(owner.store, owner.settings, 'smolagents')
    seed_ordering(Seeder(owner, registration))
    _, ledger, runner, selections = run_v4(owner, c701, monkeypatch=monkeypatch)
    assert [row.get('history_replay', {}).get('development_case_id') for row in selections[:3]] == ['dev-4', 'dev-2', 'dev-5']
    assert [row['provenance'] for row in selections[3:]] == ['model'] * 5
    assert [call[1].model_dump(mode='json') for call in runner.calls[:3]] == [CASES[c]['fault_spec'] for c in ('dev-4', 'dev-2', 'dev-5')]
    assert len(runner.provider.messages) == ledger.used_calls == 5 and len(selections) == 8


# ---------------------------------------------------------------- empty list: exactly v3-history
@pytest.mark.parametrize('seeded', [False, True])
def test_with_an_empty_replay_list_v4_sends_exactly_v3_history_requests_but_its_protocol_id(tmp_path, monkeypatch, seeded):
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    owners = [LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path / name), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                      wandb_explorer_model=flow.EXPLORER_MODEL)) for name in ('v3', 'v4')]
    try:
        runs = []
        for owner, protocol in zip(owners, (DISCOVERY_V3, DISCOVERY_V4)):
            registration = register_agent(owner.store, owner.settings, 'smolagents')
            if seeded:  # history exists, but no row qualifies (dev-5 violated only 1 of 3)
                seeder = Seeder(owner, registration)
                for failed in (('C3',), (), ()):
                    seeder.episode(case('dev-5'), failed=failed)
            campaign = flow.learn_campaign(owner, protocol, 'smolagents')
            monkeypatch.setattr(flow, 'ScriptedExplorer', Recording)
            runs.append((owner, campaign, *flow.run(owner, campaign, c701)))
            monkeypatch.undo()
        (_, v3_campaign, v3_ledger, v3_runner, v3_selections), (v4_owner, v4_campaign, v4_ledger, v4_runner, v4_selections) = runs
        replay = read_run_plan(v4_owner.store, v4_campaign)['plan']['discovery']['replay']
        assert replay['status'] == 'EMPTY' and replay['statement'] == (history_replay.EMPTY_NONE_ELIGIBLE if seeded else history_replay.EMPTY_NO_HISTORY)
        assert len(v4_runner.provider.messages) == len(v3_runner.provider.messages) == 8
        swapped = [[system, {**user, 'content': user['content'].replace(DISCOVERY_V4, DISCOVERY_V3)}] for system, user in v4_runner.provider.messages]
        assert normalize(swapped) == normalize(v3_runner.provider.messages)
        assert all(json.loads(user['content'])['discovery_protocol'] == DISCOVERY_V4 for _, user in v4_runner.provider.messages)
        assert all(DISCOVERY_V4_PROMPT not in system['content'] for system, _ in v4_runner.provider.messages)
        strip = lambda rows: normalize([[{'content': canonical_json(row['search_decision'])}] for row in rows])
        assert strip(v4_selections) == strip(v3_selections) and all('history_replay' not in row for row in v4_selections)
        assert [call[1] for call in v4_runner.calls] == [call[1] for call in v3_runner.calls]
        assert v4_ledger.used_calls == v3_ledger.used_calls == 8
    finally:
        for owner in owners: asyncio.run(owner.close())


# ---------------------------------------------------------------- Start refuses a changed history
def change_counted_record(owner, seeder, campaign):
    cutoff = read_run_plan(owner.store, campaign)['plan']['discovery']['history']['record_cutoff']
    included = next(row for _, row in owner.store.records_upto('episodes', cutoff) if row['study_id'] == seeder.study_id)
    owner.store.put_record('evidence', included['episode_id'], {'episode_id': included['episode_id'], 'source': 'local_only'})


def test_start_refuses_a_changed_history_and_no_replay_runs(owner):
    from app.lab.budgets import CampaignLedger
    seeder = dev5_owner(owner)
    campaign = flow.learn_campaign(owner, DISCOVERY_V4, 'smolagents')
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) is not None
    change_counted_record(owner, seeder, campaign)
    with pytest.raises(StoreConflict, match='create a new plan'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))    # what Start runs: 409
    # Through the coordinator's own execution path: ERROR with the plain reason before any replay or Explorer request.
    owner.ledgers[campaign.campaign_id] = CampaignLedger(owner.store, campaign.campaign_id, campaign.caps)
    runner = flow.FakeRunner('tie'); runner.provider = Recording(c701)
    async def offline_runner(live): return runner, False
    owner._get_runner = offline_runner
    asyncio.run(owner._execute(campaign.campaign_id, True))
    ended = owner.get(campaign.campaign_id)
    assert ended.state == 'ERROR' and ended.terminal_reason.startswith('AGENT_HISTORY_CHANGED:')
    assert runner.provider.messages == [] and runner.calls == [] and not owner.store.list_records('selections')


def test_start_refuses_a_saved_list_the_installed_replay_rule_would_not_produce(owner, monkeypatch):
    """The replay list is recomputed from the frozen history at Start and before the first replay: a plan saved under
    another replay rule (here: the installed rule is narrowed to 2 of 2 violations) is refused, not silently re-used."""
    dev5_owner(owner)
    for failed in (('C5',), ('C5',), ()):
        Seeder(owner, register_agent(owner.store, owner.settings, 'smolagents')).episode(case('dev-3'), failed=failed)
    campaign = flow.learn_campaign(owner, DISCOVERY_V4, 'smolagents')
    rows = read_run_plan(owner.store, campaign)['plan']['discovery']['replay']['rows']
    assert [row['development_case_id'] for row in rows] == ['dev-5', 'dev-3']          # 3/3 then 2/3
    monkeypatch.setattr(history_replay, 'MIN_VIOLATION_SHARE', Fraction(1, 1))
    with pytest.raises(StoreConflict, match='replay list does not match .* create a new plan'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    monkeypatch.undo()
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) is not None


def test_history_check_button_covers_the_replay_list(owner):
    from app.lab.run_plans import plan_history_check
    seeder = dev5_owner(owner)
    campaign = flow.learn_campaign(owner, DISCOVERY_V4, 'smolagents')
    assert plan_history_check(owner.store, owner.get(campaign.campaign_id))['status'] == 'CURRENT'
    change_counted_record(owner, seeder, campaign)
    assert plan_history_check(owner.store, owner.get(campaign.campaign_id))['status'] == 'CHANGED'


# ---------------------------------------------------------------- v3 records are unchanged
def test_v3_records_and_projections_never_carry_replay_fields(owner, monkeypatch):
    dev5_owner(owner)
    sources = record_sources(owner, monkeypatch)
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    campaign.caps.discovery_selections = 1
    monkeypatch.setattr(flow, 'ScriptedExplorer', Recording)
    _, runner, selections = flow.run(owner, campaign, dev5_repick, mode='gain')
    assert len(sources) == 1 and all('history_replay' not in row for row in selections)
    assert selections[0]['provenance'] == 'model' and runner.provider.messages
    assert all(DISCOVERY_V4_PROMPT not in system['content'] for system, _ in runner.provider.messages)
    complete_fixture_episodes(owner)
    attempts, experiments = dashboard(owner, campaign.campaign_id)
    assert all('history_replay' not in row for row in attempts)
    assert len(experiments['counterexamples']) == 1 and 'matches_history_row' in experiments['counterexamples'][0]
    assert all('history_replay' not in row for row in experiments['counterexamples'])
    recording = development_recording(owner.store, campaign.campaign_id)
    assert 'discovery_history_replays' not in recording
    assert all('history_replay' not in source for source in recording['discovery_history_matches']['sources'])
