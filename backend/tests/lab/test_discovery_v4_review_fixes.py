"""Discovery v4 (history replay): the September 30 review findings, fixed and pinned. Offline and $0.

Uses the scripted Explorer and fake Actor runner of test_discovery_v2_flow.py and the history seeding of
test_agent_history.py (both fixture behaviour, not model evidence). No provider, simulator port, W&B or model call.

* MEDIUM-1 / F3: a replay episode never enters a later agent history (it is FaultLab's pick, not the Explorer's), so no
  later v3 or v4 plan calls it a learn campaign's Explorer pick and a row's own replays never raise its replay share;
  the same campaign's Explorer pick still counts.
* F2: the chooser sentence and the saved plan say that a replay source goes through the normal loop first and can use
  up the campaign's candidate requests, ending discovery; the unchanged loop is shown doing exactly that.
* F4: a v4 recording's history claim rule names v4 and history replays; a v3 recording keeps its exact text.
"""
import json
from types import SimpleNamespace

import pytest

from app.contracts.models import CampaignBudget, Counterexample, MechanicNoChange, content_hash
from app.lab import history_replay
from app.lab.discovery_protocol import DISCOVERY_V3, DISCOVERY_V4
from app.lab.exports import development_recording
from app.lab.run_plans import REPLAY_DESCRIPTION, build_run_options, read_run_plan

import test_discovery_v2_flow as flow
from test_agent_history import Seeder, case
from test_discovery_v3_flow import c701
from test_discovery_v4_replay import F4_ORDERS, dev5_owner, record_sources, run_v4, v4_plan

owner = flow.owner
anyio_backend = flow.anyio_backend

# The v3 recording's claim rule, exactly as before discovery v4 (backup/part2-2026-09-22, exports.py).
V3_CLAIM_RULE = ('Results of a discovery v3 campaign are history-informed. A source whose recipe matches a history row '
                 're-tries recorded evidence the Explorer was shown; report it as history-informed, never as independent '
                 'discovery, and name the store and the frozen summary hash.')


def product_shaped(owner, campaign):
    """Give the fake runner's episode records of one campaign the fields the product runner writes (as Seeder does), with
    Weave-verified evidence, so the same-agent history would count every one of them if it were allowed to."""
    plan = read_run_plan(owner.store, campaign.campaign_id)['plan']
    registration = owner.store.get_record('agent_registrations', plan['agent_registration_id'])
    configuration = owner.store.get_record('configurations', campaign.configuration_hash)
    shaped = []
    for ident, payload in owner.store.db.execute("SELECT id, payload FROM records WHERE kind='episodes'").fetchall():
        payload = json.loads(payload)
        if payload.get('campaign_id') != campaign.campaign_id:
            continue
        verdict = {**payload['verdict'], 'outcome': 'VIOLATION', 'scorer_hash': configuration['scorer_hash'],
                   'checks': [{'check_id': f'C{i}', 'passed': i != 3} for i in range(1, 9)]}   # the 'gain' runner fails C3
        owner.store.put_record('episodes', ident, {**payload, 'episode_id': ident, 'policy_version': 'policy-v0', 'arm': 'B0',
                                                   'lifecycle': 'COMPLETED', 'agent_registration_id': registration['registration_id'],
                                                   'model': registration['model'], 'verdict': verdict})
        owner.store.put_record('evidence', ident, {'episode_id': ident, 'source': 'weave_verified'})
        shaped.append(ident)
    return registration, shaped


# ---------------------------------------------------------------- MEDIUM-1 / F3
def test_a_replay_episode_never_enters_a_later_agent_history_but_the_explorers_pick_does(owner, monkeypatch):
    seeder = dev5_owner(owner)                                  # baseline study: dev-5 violated 3/3, dev-1 completed 3/3
    record_sources(owner, monkeypatch)                          # sources are recorded, not reproduced (no extra episodes)
    campaign, _, runner, selections = run_v4(owner, lambda *_: flow.raw(*F4_ORDERS), mode='gain', slots=2, monkeypatch=monkeypatch)
    replay, pick = selections
    assert replay['provenance'] == 'history_replay' and pick['provenance'] == 'model'
    registration, shaped = product_shaped(owner, campaign)
    assert sorted(shaped) == sorted([replay['history_replay']['episode_id'], runner.calls[1][3]['episode_id']])

    # A later plan in the same store (v4 and v3 freeze the same history).
    _, later = v4_plan(owner, seeder.registration)
    history = later['discovery']['history']
    rows = {row['development_case_id']: row for row in history['summary']['recipes']}
    # The replay of dev-5 is not counted: dev-5 stays 3/3 from the baseline study only, never "learn discovery".
    assert (rows['dev-5']['verified_episodes'], rows['dev-5']['outcomes'], rows['dev-5']['sources']) == (3, {'VIOLATION': 3}, ['baseline_study'])
    # The same campaign's Explorer pick IS counted, as a learn campaign's own discovery pick: the exclusion is the replay's.
    assert (rows[None]['primitives'], rows[None]['verified_episodes'], rows[None]['sources']) == (F4_ORDERS, 1, ['learn_discovery'])
    assert history['summary']['composition'] == {'baseline_studies': 1, 'baseline_study_episodes': 6,
                                                 'learn_campaigns': 1, 'learn_discovery_episodes': 1}
    assert history['summary']['verified_episodes'] == 7 and sum(history['summary']['excluded'].values()) == 0
    # The replay rule never feeds on its own replays: the later list still reads 3/3, not 4/4.
    assert [(row['development_case_id'], row['violation_share'], row['sources']) for row in later['discovery']['replay']['rows']] == \
        [('dev-5', '3/3', ['baseline_study'])]
    # v3 in the same store: the identical history (only the cutoff may differ).
    from test_agent_history import planned
    v3 = read_run_plan(owner.store, planned(owner, seeder.registration, discovery_protocol=DISCOVERY_V3))['plan']['discovery']['history']
    assert {k: v for k, v in v3.items() if k != 'record_cutoff'} == {k: v for k, v in history.items() if k != 'record_cutoff'}


def test_without_replay_records_a_learn_campaigns_explorer_pick_still_counts(owner):
    """With no replay record in the store (every store written before discovery v4), the exclusion removes nothing: a
    learn campaign's own Explorer pick still counts as learn discovery. Byte-identity with the code before the fix is
    checked on every saved store separately (artifacts/product-discovery-v4-2026-09-30/fixer/store_history_compare.py),
    and by the unchanged v3 and agent-history tests."""
    registration = dev5_owner(owner).registration
    seeder = Seeder(owner, registration)
    learn = seeder.learn_campaign()
    seeder.select(case('dev-3'), learn)
    seeder.episode(case('dev-3'), failed=('C5',), via='campaign')
    block = seeder.history()
    assert not any(row.get('provenance') == 'history_replay' for row in owner.store.list_records('selections'))
    rows = {row['development_case_id']: row for row in block['summary']['recipes']}
    assert rows['dev-3']['sources'] == ['learn_discovery'] and rows['dev-5']['sources'] == ['baseline_study']
    assert block['summary']['composition']['learn_discovery_episodes'] == 1 and block['summary']['verified_episodes'] == 7


# ---------------------------------------------------------------- F2
def test_the_chooser_and_the_plan_say_a_replay_source_can_use_up_the_candidate_requests(owner):
    options = {row['protocol_id']: row for row in build_run_options(owner.settings, owner.store)['learn']['discovery_protocols']}
    sentence = options[DISCOVERY_V4]['description']
    assert sentence == REPLAY_DESCRIPTION and sentence.count('. ') == 0 and sentence.endswith('.')   # still one sentence
    assert 'a replay source goes through the normal loop first' in sentence
    assert 'uses up the campaign\'s candidate requests, discovery ends before any later replay or Explorer slot runs' in sentence
    seeder = dev5_owner(owner)
    _, plan = v4_plan(owner, seeder.registration)
    statement = plan['discovery']['replay']['statement']
    assert statement == history_replay.AVAILABLE_STATEMENT and len(statement) <= 600
    assert "if the campaign's candidate requests (at most 4) are used up there, discovery ends" in statement
    assert 'later replays and Explorer slots do not run' in statement
    assert CampaignBudget().candidates == 4
    with pytest.raises(ValueError):
        CampaignBudget(candidates=5)                                              # 'at most 4' is the contract's bound


def test_the_unchanged_loop_ends_discovery_when_a_replay_source_uses_up_the_candidate_requests(owner, monkeypatch):
    """What the sentence describes, through the real loop: two replays are listed, the first replay's source reaches the
    candidate stage and its Mechanic uses all 4 candidate requests, so replay 2 and every Explorer slot never run."""
    import app.lab.learning as learning
    seeder = dev5_owner(owner)
    for _ in range(3):
        seeder.episode(case('dev-3'), failed=('C5',))           # a second 3/3 row: the list holds dev-3, then dev-5
    mechanic_requests = []

    class Reproducer:
        def __init__(self, *args): pass
        async def source(self, current, source, recipe, incumbent, **kwargs):
            counter = Counterexample(counterexample_id='counter-replay', campaign_id=current.campaign_id, agent_registration_id='fixture',
                                     source_episode_id=source.episode_id, target_invariant='C3', scenario_hash=content_hash(recipe),
                                     configuration_hash=current.configuration_hash, report_ref=source.episode_id,
                                     verdict_ref='verdict-fixture', reproduced=True, target_violation_count=3, valid_count=3, attempted_count=3)
            return counter, [source]
        async def reduce(self, current, counter, recipe, incumbent, **kwargs):
            return SimpleNamespace(result=SimpleNamespace(status='NO_REDUCTION', model_dump=lambda **_: {'status': 'NO_REDUCTION'}),
                                   retained_recipe=recipe, trials=[])

    class Diagnostician:
        def __init__(self, *args): pass
        async def run(self, *args, **kwargs):
            return SimpleNamespace(kind='POLICY_GAP', model_dump=lambda **_: {'kind': 'POLICY_GAP', 'provenance': 'offline_double'}), SimpleNamespace(trials=[])

    class Mechanic:
        def __init__(self, *args): pass
        async def propose(self, context, **kwargs):
            mechanic_requests.append(context['source_context_id'])
            if len(mechanic_requests) < 4:
                return f'mechanic-{len(mechanic_requests)}', None, ['not a policy']       # an invalid proposal: rejected
            return 'mechanic-4', MechanicNoChange(no_change_reason='fixture'), ['{"no_change_reason":"fixture"}']

    async def export(*args, **kwargs): return None
    for name, value in (('Reproducer', Reproducer), ('Diagnostician', Diagnostician), ('Mechanic', Mechanic), ('export_incident', export)):
        monkeypatch.setattr(learning, name, value)
    campaign, _, runner, selections = run_v4(owner, c701, mode='gain', monkeypatch=monkeypatch)
    listed = read_run_plan(owner.store, campaign.campaign_id)['plan']['discovery']['replay']['rows']
    assert [row['development_case_id'] for row in listed] == ['dev-3', 'dev-5']
    assert len(mechanic_requests) == 4 == CampaignBudget().candidates and len(set(mechanic_requests)) == 1
    assert [row['provenance'] for row in selections] == ['history_replay']          # replay 2 never ran
    assert len(runner.calls) == 1                                                    # one Actor episode: replay 1's
    assert runner.provider.messages == []                                            # no Explorer request at all
    ended = owner.get(campaign.campaign_id)
    assert ended.state == 'NO_CHANGE'


# ---------------------------------------------------------------- F4
def test_a_v4_recording_names_v4_in_its_history_claim_rule_and_a_v3_recording_keeps_its_exact_text(owner):
    seeder = dev5_owner(owner)
    v4_campaign, _ = v4_plan(owner, seeder.registration)
    from test_agent_history import planned
    v3_campaign = planned(owner, seeder.registration, discovery_protocol=DISCOVERY_V3)
    v4_rule = development_recording(owner.store, v4_campaign.campaign_id)['discovery_history_matches']['claim_rule']
    v3_rule = development_recording(owner.store, v3_campaign.campaign_id)['discovery_history_matches']['claim_rule']
    assert v3_rule == V3_CLAIM_RULE
    assert v4_rule.startswith('Results of a discovery v4 campaign are history-informed.') and 'v3' not in v4_rule
    assert 'history replay of that row' in v4_rule and 'never as independent discovery' in v4_rule
