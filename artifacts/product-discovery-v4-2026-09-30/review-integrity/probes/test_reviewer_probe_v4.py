"""Integrity reviewer probes for discovery v4 (history replay), $0 and offline, run only in the scratch 'current' tree.

A  tampered replay lists (and a tampered history + list) whose plan and provenance hashes were re-sealed by direct SQL:
   Start (validate_run_plan) and the pre-replay check (learning.discovery_history) must refuse; the coordinator's own
   execution must end ERROR with no replay selection, no Explorer message and no Actor episode.
B  exclusions: violating dev-6 episodes from promotion split, reproduction purpose, B1 arm, another policy, another model,
   another agent, unverified evidence, interrupted runs, a single-case baseline run, and a protected-only recipe must not
   make any row replay-eligible; only same-agent verified development discovery episodes count.
C  frozen: violating episodes written after the plan's record cutoff change neither Start's verdict nor the replay list.
D  determinism: the replay block is a pure function of the summary (key order, unrelated fields).
E  same downstream path: a v4 replay of dev-5 in slot 0 and a v3 Explorer pick of the same dev-5 recipe in slot 0 hand
   exactly the same recipe, fixture, arm and purpose to the Actor runner and to Reproducer.source.
Scripted Explorer and fake runner of test_discovery_v2_flow (fixture text, not model evidence). No network.
"""
import asyncio
import copy
import json

import pytest

import test_discovery_v2_flow as flow
from app.contracts.models import FaultSpec, canonical_json, content_hash
from app.lab import history_replay
from app.lab.agent_history import HistoryChanged
from app.lab.challenge import schedule_identity_v2
from app.lab.discovery_protocol import DISCOVERY_V3, DISCOVERY_V4
from app.lab.operator_actions import register_agent
from app.lab.run_plans import read_run_plan, validate_run_plan
from app.lab.storage import StoreConflict
from test_agent_history import CASES, PROTECTED, Seeder, case
from test_discovery_v3_flow import Recording, c701

owner = flow.owner
anyio_backend = flow.anyio_backend
RESULTS = {}


def seed_two_rows(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents')
    seeder = Seeder(owner, registration)
    for _ in range(3):
        seeder.episode(case('dev-5'), failed=('C3', 'C5'))
        seeder.episode(case('dev-1'))
    for failed in (('C5',), ('C5',), ()):
        seeder.episode(case('dev-3'), failed=failed)
    return seeder


def reseal(owner, campaign_id, mutate):
    """Rewrite the saved plan by direct SQL (the product refuses to overwrite it) and re-seal both hashes."""
    db = owner.store.db
    plan = json.loads(db.execute("SELECT payload FROM records WHERE kind='campaign_plans' AND id=?", (campaign_id,)).fetchone()[0])
    mutate(plan)
    plan['plan_hash'] = content_hash({k: v for k, v in plan.items() if k != 'plan_hash'})
    prov = json.loads(db.execute("SELECT payload FROM records WHERE kind='campaign_provenance' AND id=?", (campaign_id,)).fetchone()[0])
    prov['run_plan_hash'] = plan['plan_hash']
    db.execute("UPDATE records SET payload=? WHERE kind='campaign_plans' AND id=?", (canonical_json(plan), campaign_id))
    db.execute("UPDATE records SET payload=? WHERE kind='campaign_provenance' AND id=?", (canonical_json(prov), campaign_id))
    # The store connection is in autocommit mode (isolation_level=None): no commit is needed.


def swap_order(plan):
    rows = plan['discovery']['replay']['rows']
    rows.reverse()
    for index, row in enumerate(rows, start=1): row['replay'] = index


def drop_second(plan):
    plan['discovery']['replay']['rows'] = plan['discovery']['replay']['rows'][:1]


def inject_dev6(plan):
    spec = FaultSpec.model_validate(CASES['dev-6']['fault_spec'])
    rows = plan['discovery']['replay']['rows']
    rows.insert(0, {**copy.deepcopy(rows[0]), 'history_row': 99, 'development_case_id': 'dev-6', 'recipe': ['fabricated'],
                    'fault_spec': spec.model_dump(mode='json'), 'schedule_identity_v2': schedule_identity_v2(spec)})
    for index, row in enumerate(rows[:3], start=1): row['replay'] = index
    plan['discovery']['replay']['rows'] = rows[:3]


def emptied(plan):
    replay = plan['discovery']['replay']
    replay.update(status='EMPTY', rows=[], statement=history_replay.EMPTY_NONE_ELIGIBLE)


def forged_history_and_list(plan):
    """Add a fabricated dev-6 3/3 row to the frozen summary, re-hash it, and recompute the list from it consistently."""
    history = plan['discovery']['history']
    spec = FaultSpec.model_validate(CASES['dev-6']['fault_spec'])
    template = next(r for r in history['summary']['recipes'] if r['development_case_id'] == 'dev-5')
    history['summary']['recipes'].append({**copy.deepcopy(template), 'development_case_id': 'dev-6', 'recipe': ['fabricated'],
                                          'primitives': spec.model_dump(mode='json')['primitives'], 'failed_checks': {'C4': 3}})
    history['summary']['recipes_total'] += 1
    history['summary_hash'] = content_hash(history['summary'])
    plan['discovery']['replay'] = history_replay.plan_block(history)


@pytest.mark.parametrize('name,mutate', [('swap_order', swap_order), ('drop_second', drop_second), ('inject_dev6', inject_dev6),
                                         ('emptied', emptied), ('forged_history_and_list', forged_history_and_list)])
def test_A_resealed_tampered_plans_are_refused_before_any_replay(owner, name, mutate):
    from app.lab.budgets import CampaignLedger
    from app.lab.learning import discovery_history
    seed_two_rows(owner)
    campaign = flow.learn_campaign(owner, DISCOVERY_V4, 'smolagents')
    before = read_run_plan(owner.store, campaign)['plan']['discovery']['replay']['rows']
    assert [r['development_case_id'] for r in before] == ['dev-5', 'dev-3']
    reseal(owner, campaign.campaign_id, mutate)
    outcome = {}
    try:
        read_run_plan(owner.store, campaign); outcome['read_run_plan'] = 'accepted (hash-level consistent)'
    except StoreConflict as error:
        outcome['read_run_plan'] = f'refused: {error}'
    with pytest.raises(StoreConflict) as start:
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    outcome['start'] = f'refused: {type(start.value).__name__}: {start.value}'
    with pytest.raises(StoreConflict) as pre:
        discovery_history(owner.store, owner.get(campaign.campaign_id))
    outcome['pre_replay_check'] = f'refused: {type(pre.value).__name__}'
    # The coordinator's own execution path (Start was bypassed): ERROR before any replay or Explorer request.
    owner.ledgers[campaign.campaign_id] = CampaignLedger(owner.store, campaign.campaign_id, campaign.caps)
    runner = flow.FakeRunner('gain'); runner.provider = Recording(c701)
    async def offline_runner(live): return runner, False
    owner._get_runner = offline_runner
    asyncio.run(owner._execute(campaign.campaign_id, True))
    ended = owner.get(campaign.campaign_id)
    ours = [s for s in owner.store.list_records('selections') if s['context'].get('campaign_id') == campaign.campaign_id]
    outcome['execution'] = {'state': ended.state, 'reason': (ended.terminal_reason or '')[:160], 'selections': len(ours),
                            'explorer_messages': len(runner.provider.messages), 'actor_episodes': len(runner.calls)}
    assert ended.state == 'ERROR' and not ours and not runner.provider.messages and not runner.calls
    RESULTS[f'A_{name}'] = outcome


def test_B_excluded_evidence_never_makes_a_row_replay_eligible(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents')
    seeder = Seeder(owner, registration)
    for _ in range(3):
        seeder.episode(case('dev-5'), failed=('C3', 'C5'))
    seeder.episode(case('dev-6'), failed=('C4',))  # the only counted dev-6 episode
    dev6 = case('dev-6')
    for _ in range(3):
        seeder.episode(dev6, failed=('C4',), split='promotion', purpose='promotion')
        seeder.episode(dev6, failed=('C4',), purpose='reproduction')
        seeder.episode(dev6, failed=('C4',), arm='B1')
        seeder.episode(dev6, failed=('C4',), policy_hash='f' * 64)
        seeder.episode(dev6, failed=('C4',), model='other/model')
        seeder.episode(dev6, failed=('C4',), verified=False)
        seeder.episode(dev6, failed=('C4',), lifecycle='INTERRUPTED')
        seeder.episode(dev6, failed=('C4',), via='campaign', campaign=seeder.campaign)  # single-case baseline run
        seeder.episode(PROTECTED, failed=('C7',), split='promotion', purpose='promotion')
    other = Seeder(owner, register_agent(owner.store, owner.settings, 'reference'))
    for _ in range(3):
        other.episode(dev6, failed=('C4',))
    campaign = flow.learn_campaign(owner, DISCOVERY_V4, 'smolagents')
    discovery = read_run_plan(owner.store, campaign)['plan']['discovery']
    rows = {r['development_case_id']: r for r in discovery['history']['summary']['recipes']}
    replay = discovery['replay']['rows']
    assert [r['development_case_id'] for r in replay] == ['dev-5']
    assert rows['dev-6']['verified_episodes'] == 1
    protected_words = json.dumps(PROTECTED.model_dump(mode='json')['primitives'])
    assert protected_words not in canonical_json(discovery)
    RESULTS['B_exclusions'] = {'history_rows': {k: (v['verified_episodes'], v['outcomes']) for k, v in rows.items()},
                               'replay_rows': [(r['history_row'], r['development_case_id'], r['violation_share']) for r in replay],
                               'excluded_counts': discovery['history']['summary']['excluded'],
                               'protected_recipe_in_plan': protected_words in canonical_json(discovery)}


def test_C_records_after_the_cutoff_change_nothing(owner):
    seeder = seed_two_rows(owner)
    campaign = flow.learn_campaign(owner, DISCOVERY_V4, 'smolagents')
    frozen = read_run_plan(owner.store, campaign)['plan']['discovery']['replay']
    for _ in range(4):
        seeder.episode(case('dev-6'), failed=('C4',))       # would be 4/4 and replay first if it counted
        seeder.episode(case('dev-5'))                         # would drop dev-5 to 3/7 if it counted
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) is not None
    from app.lab.learning import discovery_history, discovery_replays
    assert discovery_history(owner.store, owner.get(campaign.campaign_id)) is not None
    assert discovery_replays(owner.store, owner.get(campaign.campaign_id)) == frozen['rows']
    RESULTS['C_after_cutoff'] = {'start': 'accepted', 'replay_list_unchanged': True,
                                 'rows': [(r['history_row'], r['development_case_id'], r['violation_share']) for r in frozen['rows']]}


def test_D_replay_block_is_a_pure_function_of_the_summary():
    from test_discovery_v4_replay import history_block, row
    history = history_block(row('dev-3', verified=3, violations=2), row('dev-5'), row('dev-2', verified=4, violations=4),
                            row('dev-6', verified=3, violations=3), row('dev-1'))
    first = history_replay.plan_block(history)
    shuffled = json.loads(json.dumps(history))
    shuffled['summary']['recipes'] = [dict(reversed(list(r.items()))) for r in shuffled['summary']['recipes']]
    for r in shuffled['summary']['recipes']:
        r['runtime_hashes'] = ['c' * 12]; r['excluded'] = {'lab_error': 9}
    assert history_replay.plan_block(shuffled)['rows'] == first['rows']
    assert [r['development_case_id'] for r in first['rows']] == ['dev-2', 'dev-5', 'dev-6']
    RESULTS['D_pure'] = {'order': [(r['history_row'], r['development_case_id'], r['violation_share']) for r in first['rows']]}


def downstream(owner, monkeypatch, protocol, answer):
    seen = []
    async def source(self, current, trial, recipe, incumbent, **kwargs):
        seen.append({'recipe': recipe.model_dump(mode='json'), 'fixture_id': kwargs.get('fixture_id'), 'arm': trial.arm,
                     'lifecycle': trial.lifecycle, 'outcome': trial.outcome})
        from types import SimpleNamespace
        return SimpleNamespace(reproduced=False), []
    monkeypatch.setattr('app.lab.learning.Reproducer.source', source)
    campaign = flow.learn_campaign(owner, protocol, 'smolagents')
    campaign.caps.discovery_selections = 1
    monkeypatch.setattr(flow, 'ScriptedExplorer', Recording)
    ledger, runner, _ = flow.run(owner, campaign, answer, mode='gain')
    call = runner.calls[0]
    return ({'recipe': call[1].model_dump(mode='json'), **{k: v for k, v in call[3].items() if k in ('purpose', 'arm', 'fixture_id')}},
            seen, ledger.used_calls)


def test_E_a_replay_and_an_explorer_pick_of_the_same_recipe_take_the_same_downstream_path(tmp_path, monkeypatch):
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    dev5 = CASES['dev-5']['fault_spec']
    out = {}
    for protocol in (DISCOVERY_V3, DISCOVERY_V4):
        coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path / protocol.split('/')[1]), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                              wandb_explorer_model=flow.EXPLORER_MODEL))
        try:
            seeder = Seeder(coordinator, register_agent(coordinator.store, coordinator.settings, 'smolagents'))
            for _ in range(3): seeder.episode(case('dev-5'), failed=('C3', 'C5'))
            out[protocol] = downstream(coordinator, monkeypatch, protocol, lambda *_: canonical_json({'fault_spec': dev5, 'hypothesis': 'pick dev-5'}))
            monkeypatch.undo()
        finally:
            asyncio.run(coordinator.close())
    (v3_call, v3_seen, v3_calls), (v4_call, v4_seen, v4_calls) = out[DISCOVERY_V3], out[DISCOVERY_V4]
    assert v3_call == v4_call and v3_seen == v4_seen and len(v4_seen) == 1
    assert (v3_calls, v4_calls) == (1, 0)  # the v3 pick cost one Explorer request; the replay none
    RESULTS['E_same_path'] = {'actor_call': v4_call, 'reproducer_source': v4_seen, 'explorer_requests': {'v3': v3_calls, 'v4': v4_calls}}


def test_zz_write_results():
    import os
    with open(os.environ['REVIEW_OUT'], 'w') as fh:
        json.dump(RESULTS, fh, indent=1, sort_keys=True, default=str)
