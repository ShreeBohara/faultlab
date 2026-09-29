"""Discovery protocol v3 (history-informed) through the real learning loop, offline and $0.

A scripted Explorer answers from fixed text (the 8 saved raw outputs of the closed campaign c701e850,
read only as fixture data) and a fake Actor runner records episodes, exactly as in
test_discovery_v2_flow.py. No provider, simulator port, W&B or model call is made.

Shown here:
* the frozen history reaches every discovery request, byte-for-byte the plan's summary, and changes
  nothing else: v3 against v1 and v3-with-pre-check against v2 make the same decisions, episodes, requests
  and ledger charges; each Explorer context differs only by discovery_protocol and agent_history, and
  the system prompt only by the appended v3 section;
* v1 and v2 Explorer messages are byte-identical to those captured before v3 existed (pinned digests);
* seeded promotion / held-out / final-audit records never appear in any Explorer message;
* the saved plan, the dashboard plan response and the public recording show the summary and its hash.
"""
import hashlib
import json
import re

import httpx
import pytest

import test_discovery_v2_flow as flow
from app.agents.explorer import DISCOVERY_V2_PROMPT, DISCOVERY_V3_PROMPT, PROMPT
from app.contracts.models import canonical_json, content_hash
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2, DISCOVERY_V3, DISCOVERY_V3_PRECHECK
from app.lab.exports import development_recording
from app.lab.operator_actions import register_agent
from app.lab.run_plans import read_run_plan
from app.telemetry.safety import public_json
from test_agent_history import PROTECTED_WORDS, Seeder, seed_protected, seed_screen

owner = flow.owner
anyio_backend = flow.anyio_backend
C701 = flow.C701
IDS = re.compile(r'[a-z][a-z_]*-[0-9a-f]{32}|[0-9a-f]{64}')


class Recording(flow.ScriptedExplorer):
    """The scripted Explorer, also keeping the exact messages it was sent."""
    def __init__(self, answer):
        super().__init__(answer); self.messages = []
    async def complete(self, messages, **kwargs):
        self.messages.append([dict(m) for m in messages])
        return await super().complete(messages, **kwargs)


def normalize(messages):
    """Replace run-specific ids and digests by placeholders numbered by first appearance."""
    mapping = {}
    def sub(match): return mapping.setdefault(match.group(0), f'<ID{len(mapping)}>')
    return [[IDS.sub(sub, message['content']) for message in pair] for pair in messages]


def recorded_run(owner, campaign, answer, monkeypatch):
    monkeypatch.setattr(flow, 'ScriptedExplorer', Recording)
    ledger, runner, selections = flow.run(owner, campaign, answer)
    monkeypatch.undo()
    return ledger, runner, selections


def without_history(messages, base):
    """A v3 request as its base protocol would send it: no agent_history, the base's discovery_protocol."""
    stripped = []
    for system, user in messages:
        context = json.loads(user['content'])
        context.pop('agent_history')
        if base == DISCOVERY_V1: context.pop('discovery_protocol')
        else: context['discovery_protocol'] = base
        stripped.append([system, {**user, 'content': canonical_json(context)}])
    return stripped


def c701(slot, _request, _context): return C701[slot]['raw']


def seeded_owner(owner, agent):
    registration = register_agent(owner.store, owner.settings, agent)
    seeder = Seeder(owner, registration)
    seed_screen(seeder)
    return seeder


# ---------------------------------------------------------------- v1 / v2 unchanged (pinned before v3 existed)
# Captured on September 29, 2026 with the code before discovery v3 (runtime c9af0a47), by
# artifacts/product-discovery-v3-2026-09-29/builder/capture_goldens.py, through the real loop with the
# same scripted Explorer and fake runner as below. If an intended change to the Explorer's v1/v2 prompt
# or context ever moves one, re-capture deliberately; v3 must never move them.
PINNED = {
    ('v1-reference-c701', None, 'reference', 'repeat'): '6eff99da6f99d3356518fb6f045aac2f2c7293f88c274bd1f859af618ddcdc7e',
    ('v1-native-c701', None, 'smolagents', 'repeat'): 'e9cd470e798b4d35eedd4cf6ac50f48f8c349d7332c41af5e7e539a23eacfcff',
    ('v2-reference-c701-repeats', DISCOVERY_V2, 'reference', 'repeat'): '303a7a961d4e9b921347608cd58c75e30e492236fe835451de344d04f631427b',
    ('v2-reference-c701-feedback', DISCOVERY_V2, 'reference', 'feedback'): 'd765fb9e7e41c83c12a6f201863382db9b0c16dd9dc0a07eae36b18c9556bca4',
}
ALTERNATIVES = {2: flow.raw(flow.P('F1', 'update_order', 'orders', 1, response_delay_ms=2000)),
                5: flow.raw(flow.P('F4', 'send_confirmation', 'notifications', 1, failure_count=2)),
                6: flow.raw(flow.P('F4', 'update_order', 'orders', 1, failure_count=2)),
                7: flow.raw(flow.P('F2', 'update_order', 'orders', 1, completion_delay_ticks=2, terminal_status='FAILED',
                                   failure_code='UPGRADE_REJECTED'))}


@pytest.mark.parametrize('name,protocol,agent,mode', list(PINNED))
def test_v1_and_v2_explorer_messages_are_byte_identical_to_before_v3(owner, monkeypatch, name, protocol, agent, mode):
    campaign = flow.learn_campaign(owner, protocol, agent)
    answer = c701 if mode == 'repeat' else (lambda slot, n, _c: C701[slot]['raw'] if n == 1 else ALTERNATIVES[slot])
    _, runner, _ = recorded_run(owner, campaign, answer, monkeypatch)
    messages = normalize(runner.provider.messages)
    assert hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest() == PINNED[name, protocol, agent, mode]
    assert not any('agent_history' in json.loads(user) for _, user in messages)
    assert all(json.loads(user).get('discovery_protocol') == protocol for _, user in messages)  # v1: absent


# ---------------------------------------------------------------- v3 reaches the Explorer and changes nothing else
@pytest.mark.parametrize('agent,base,v3', [('reference', DISCOVERY_V1, DISCOVERY_V3), ('smolagents', DISCOVERY_V1, DISCOVERY_V3),
                                           ('reference', DISCOVERY_V2, DISCOVERY_V3_PRECHECK)])
def test_history_reaches_every_discovery_request_and_changes_nothing_else(tmp_path, monkeypatch, agent, base, v3):
    import asyncio
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    owners = [LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path / name), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                      wandb_explorer_model=flow.EXPLORER_MODEL)) for name in ('base', 'v3')]
    try:
        seeded_owner(owners[1], agent)
        runs = []
        for owner, protocol in zip(owners, (base, v3)):
            campaign = flow.learn_campaign(owner, protocol, agent)
            runs.append((owner, campaign, *recorded_run(owner, campaign, c701, monkeypatch)))
        (base_owner, base_campaign, base_ledger, base_runner, base_selections), \
            (v3_owner, v3_campaign, v3_ledger, v3_runner, v3_selections) = runs
        plan = read_run_plan(v3_owner.store, v3_campaign)['plan']
        history = plan['discovery']['history']
        assert history['status'] == 'AVAILABLE' and history['summary']['verified_episodes'] == 6
        # The frozen summary reaches every discovery request, byte-for-byte, with its declared protocol.
        requests = [json.loads(user['content']) for _, user in v3_runner.provider.messages]
        assert requests and all(r['agent_history'] == history['summary'] and r['discovery_protocol'] == v3 for r in requests)
        assert all(content_hash(r['agent_history']) == history['summary_hash'] for r in requests)
        dev5 = next(row for row in requests[0]['agent_history']['recipes'] if row['development_case_id'] == 'dev-5')
        assert dev5['failed_checks'] == {'C3': 3, 'C5': 3}
        # ...and nothing else changes: prompts, the rest of every context, decisions, episodes and charges.
        for (base_system, _), (v3_system, _) in zip(base_runner.provider.messages, v3_runner.provider.messages):
            assert v3_system['content'] == base_system['content'] + '\n' + DISCOVERY_V3_PROMPT
        expected_system = PROMPT + ('\n' + DISCOVERY_V2_PROMPT if base == DISCOVERY_V2 else '') + '\n' + DISCOVERY_V3_PROMPT
        assert {system['content'] for system, _ in v3_runner.provider.messages} == {expected_system}
        base_users = [[{'content': ''}, user] for _, user in base_runner.provider.messages]
        v3_users = [[{'content': ''}, user] for _, user in without_history(v3_runner.provider.messages, base)]
        assert normalize(v3_users) == normalize(base_users)
        assert 'discovery_protocol' not in json.loads(base_runner.provider.messages[0][1]['content']) or base == DISCOVERY_V2
        decisions = lambda selections: normalize([[{'content': canonical_json({k: v for k, v in row['search_decision'].items()
                                                                                if k != 'discovery_protocol'})}] for row in selections])
        assert decisions(v3_selections) == decisions(base_selections)
        assert [row['search_decision'].get('discovery_protocol') for row in v3_selections] == \
            [v3 if row['search_decision'].get('discovery_protocol') else None for row in base_selections]
        assert [call[1] for call in v3_runner.calls] == [call[1] for call in base_runner.calls]
        assert v3_ledger.used_calls == base_ledger.used_calls == len(v3_runner.provider.messages)
        assert v3_owner.get(v3_campaign.campaign_id).state == base_owner.get(base_campaign.campaign_id).state
        base_block = read_run_plan(base_owner.store, base_campaign)['plan']['discovery']
        assert {k: v for k, v in plan['discovery'].items() if k not in ('protocol', 'history')} == \
            {k: v for k, v in base_block.items() if k != 'protocol'}
    finally:
        for owner in owners: asyncio.run(owner.close())


def test_no_prior_history_reaches_the_explorer_as_a_plain_statement(owner, monkeypatch):
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    campaign.caps.discovery_selections = 1  # in-memory loop bound only; the saved plan and campaign keep 8
    _, runner, selections = recorded_run(owner, campaign, c701, monkeypatch)
    context = json.loads(runner.provider.messages[0][1]['content'])
    assert context['agent_history']['status'] == 'NO_PRIOR_HISTORY' and context['agent_history']['recipes'] == []
    assert context['agent_history']['statement'].startswith('No prior history')
    assert [row['search_decision']['status'] for row in selections] == ['SELECTED'] and len(runner.calls) == 1


def test_seeded_protected_records_never_reach_any_explorer_message(owner, monkeypatch):
    seeder = seeded_owner(owner, 'smolagents')
    protected_ids = seed_protected(seeder)
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    _, runner, _ = recorded_run(owner, campaign, c701, monkeypatch)
    text = '\n'.join(message['content'] for pair in runner.provider.messages for message in pair)
    assert all('agent_history' in json.loads(user['content']) for _, user in runner.provider.messages)
    assert PROTECTED_WORDS not in text and 'heldout-check' not in text and '"occurrence":7' not in text
    assert not any(ident in text for ident in protected_ids)
    history = read_run_plan(owner.store, campaign)['plan']['discovery']['history']
    assert history['summary']['verified_episodes'] == 6 and not any(history['summary']['excluded'].values())


# ---------------------------------------------------------------- shown in the plan, the dashboard and the recording
@pytest.mark.anyio
async def test_plan_dashboard_response_and_recording_show_the_summary_and_its_hash(owner, monkeypatch):
    seeded_owner(owner, 'smolagents')
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    stored = owner.store.get_record('campaign_plans', campaign.campaign_id)
    history = stored['discovery']['history']
    assert history['summary_hash'] == content_hash(history['summary']) and isinstance(history['record_cutoff'], int)
    from app.main import create_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
        response = await api.get(f'/api/campaigns/{campaign.campaign_id}/plan')
    assert response.status_code == 200, response.text
    assert response.json()['plan']['discovery']['history'] == history
    recording = development_recording(owner.store, campaign.campaign_id)
    assert recording['run_plan']['plan']['discovery']['history'] == history
    assert public_json(recording, max_bytes=64 * 1024 * 1024) == recording


def test_a_history_change_at_or_before_the_cutoff_stops_before_any_explorer_request(owner, monkeypatch):
    from app.lab.storage import StoreConflict
    seeder = seeded_owner(owner, 'smolagents')
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    cutoff = read_run_plan(owner.store, campaign)['plan']['discovery']['history']['record_cutoff']
    included = next(row for _, row in owner.store.records_upto('episodes', cutoff) if row['study_id'] == seeder.study_id)
    owner.store.put_record('evidence', included['episode_id'], {'episode_id': included['episode_id'], 'source': 'local_only'})
    with pytest.raises(StoreConflict, match='create a new plan'):
        recorded_run(owner, campaign, c701, monkeypatch)
    assert not owner.store.list_records('selections') or all(
        row['context'].get('campaign_id') != campaign.campaign_id for row in owner.store.list_records('selections'))
    assert owner.store.get_record('budgets', campaign.campaign_id) is None or \
        owner.store.get_record('budgets', campaign.campaign_id)['used_calls'] == 0


# ---------------------------------------------------------------- review fixes (September 29)
def complete_fixture_episodes(owner):
    """The v2 flow's fake runner saves minimal episode records; the product runner always writes the id and policy."""
    for row in owner.store.db.execute("SELECT id, payload FROM records WHERE kind='episodes'").fetchall():
        payload = json.loads(row[1])
        if 'episode_id' not in payload:
            owner.store.put_record('episodes', row[0], {**payload, 'episode_id': row[0], 'policy_version': 'policy-v0'})


def dev5_repick(_slot, _request, _context):
    """An Explorer that re-picks the dev-5 recipe it was shown, with another seed."""
    from test_agent_history import CASES
    return flow.raw(*CASES['dev-5']['fault_spec']['primitives'], seed=77)


def test_no_prior_history_is_still_a_v3_request_not_a_v1_one(owner, monkeypatch):
    """Review finding 3: under NO_PRIOR_HISTORY the Explorer still gets the v3 section and an empty block."""
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    campaign.caps.discovery_selections = 1
    _, runner, selections = recorded_run(owner, campaign, c701, monkeypatch)
    system, user = runner.provider.messages[0]
    assert system['content'].endswith('\n' + DISCOVERY_V3_PROMPT)
    context = json.loads(user['content'])
    assert context['discovery_protocol'] == DISCOVERY_V3 and context['agent_history']['status'] == 'NO_PRIOR_HISTORY'
    assert 'exactly those of the base protocol' in context['agent_history']['statement']
    assert selections[0]['matches_history_row'] is None  # v3 records say "checked, no match" explicitly


def test_v3_picks_and_sources_that_retry_a_history_row_are_flagged_in_records_api_and_recording(owner, monkeypatch):
    """Review finding 5: a v3 source that re-picks a recipe the history showed is marked, so a write-up
    cannot present it as independent discovery. v1 records never carry the flag."""
    from app.contracts.models import Counterexample, new_id
    seeded_owner(owner, 'smolagents')
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    campaign.caps.discovery_selections = 1
    summary = read_run_plan(owner.store, campaign.campaign_id)['plan']['discovery']['history']['summary']
    assert [row['development_case_id'] for row in summary['recipes']] == ['dev-1', 'dev-5']
    sources = []
    async def source(self, current, trial, recipe, incumbent, **kwargs):
        # Record the source exactly as Reproducer.source does, then stop (no reproduction trials here).
        counter = Counterexample(counterexample_id=new_id('counterexample'), campaign_id=current.campaign_id,
                                 agent_registration_id=read_run_plan(owner.store, current.campaign_id)['plan']['agent_registration_id'],
                                 source_episode_id=trial.episode_id, target_invariant='C3', scenario_hash=content_hash(recipe),
                                 configuration_hash=current.configuration_hash, report_ref=trial.episode_id, verdict_ref=trial.episode_id)
        owner.store.put_record('counterexamples', counter.counterexample_id, counter)
        owner.store.put_record('counterexample_recipes', counter.counterexample_id,
                               {'source_recipe': recipe.model_dump(mode='json'), 'fixture_id': 'standard-v1'}, immutable=True)
        sources.append(counter.counterexample_id)
        from types import SimpleNamespace
        return SimpleNamespace(reproduced=False), []
    monkeypatch.setattr('app.lab.learning.Reproducer.source', source)
    monkeypatch.setattr(flow, 'ScriptedExplorer', Recording)
    _, runner, selections = flow.run(owner, campaign, dev5_repick, mode='gain')
    monkeypatch.undo()
    expected = {'row': 2, 'development_case_id': 'dev-5', 'basis': 'faultlab-schedule-identity/v2-order-aware'}
    assert len(selections) == 1 and selections[0]['search_decision']['status'] == 'SELECTED'
    assert selections[0]['matches_history_row'] == expected and len(sources) == 1
    complete_fixture_episodes(owner)
    recording = development_recording(owner.store, campaign.campaign_id)
    assert recording['selections'][0]['matches_history_row'] == expected
    matches = recording['discovery_history_matches']
    assert matches['summary_hash'] == content_hash(summary)
    assert matches['sources'] == [{'counterexample_id': sources[0], 'source_episode_id': runner.calls[0][3]['episode_id'],
                                   'reproduced': False, 'source_recipe_recorded': True, 'matches_history_row': expected}]
    assert 'history-informed' in matches['claim_rule'] and 'never as independent' in matches['claim_rule']
    # The dashboard's search attempts and source projection show the same flag.
    import asyncio
    from app.main import create_app
    async def dashboard():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            return ((await api.get(f'/api/campaigns/{campaign.campaign_id}/search-attempts')).json(),
                    (await api.get(f'/api/campaigns/{campaign.campaign_id}/experiments')).json())
    attempts, experiments = asyncio.run(dashboard())
    assert [row['matches_history_row'] for row in attempts] == [expected]
    assert [row['matches_history_row'] for row in experiments['counterexamples']] == [expected]
    # The history itself never mentions this campaign's own pick: it was frozen before it.
    assert read_run_plan(owner.store, campaign.campaign_id)['plan']['discovery']['history']['summary'] == summary
    # A v1 campaign's selection records and recording carry no history field at all.
    v1 = flow.learn_campaign(owner, None, 'smolagents')
    v1.caps.discovery_selections = 1
    flow.run(owner, v1, dev5_repick)
    v1_rows = [row for row in owner.store.list_records('selections') if row['context']['campaign_id'] == v1.campaign_id]
    assert v1_rows and all('matches_history_row' not in row for row in v1_rows)
    complete_fixture_episodes(owner)
    v1_recording = development_recording(owner.store, v1.campaign_id)
    assert 'discovery_history_matches' not in v1_recording and all('matches_history_row' not in row for row in v1_recording['selections'])
    async def v1_dashboard():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            return (await api.get(f'/api/campaigns/{v1.campaign_id}/search-attempts')).json()
    assert all('matches_history_row' not in row for row in asyncio.run(v1_dashboard()))


@pytest.mark.anyio
async def test_dashboard_api_checks_history_on_demand(owner, monkeypatch):
    """The on-demand check (a button, never polled) reports a stale plan before Start; Start refuses it too."""
    from app.lab.run_plans import validate_run_plan
    from app.lab.storage import StoreConflict
    from app.main import create_app
    seeder = seeded_owner(owner, 'smolagents')
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    v1 = flow.learn_campaign(owner, None, 'smolagents')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
        check = (await api.get(f'/api/campaigns/{campaign.campaign_id}/plan/history-check')).json()
        assert check['status'] == 'CURRENT' and check['summary_hash'] == read_run_plan(owner.store, campaign)['plan']['discovery']['history']['summary_hash']
        assert (await api.get(f'/api/campaigns/{v1.campaign_id}/plan/history-check')).json()['status'] == 'NOT_APPLICABLE'
        # A counted record at or before the cutoff changes: the plan panel can now say so before Start.
        cutoff = check['record_cutoff']
        included = next(row for _, row in owner.store.records_upto('episodes', cutoff) if row['study_id'] == seeder.study_id)
        owner.store.put_record('evidence', included['episode_id'], {'episode_id': included['episode_id'], 'source': 'local_only'})
        changed = (await api.get(f'/api/campaigns/{campaign.campaign_id}/plan/history-check')).json()
        assert changed['status'] == 'CHANGED' and changed['message'].endswith('create a new plan')
        with pytest.raises(StoreConflict, match='create a new plan'):
            validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))  # what Start runs
        assert (await api.get(f'/api/campaigns/{campaign.campaign_id}/plan')).status_code == 200  # the frozen plan still reads
        current = owner.get(campaign.campaign_id); current.state = 'NO_CHANGE'; owner.save(current)
        assert (await api.get(f'/api/campaigns/{campaign.campaign_id}/plan/history-check')).json()['status'] == 'NOT_CHECKED'
    assert not owner.store.list_records('selections')


def test_a_history_change_before_the_first_explorer_request_ends_the_campaign_with_the_plain_reason(owner):
    """Review item (product): through the coordinator's own execution path, the campaign ends ERROR with
    AGENT_HISTORY_CHANGED and the plain message, before any Explorer request or charge."""
    import asyncio
    from app.lab.budgets import CampaignLedger
    seeder = seeded_owner(owner, 'smolagents')
    campaign = flow.learn_campaign(owner, DISCOVERY_V3, 'smolagents')
    cutoff = read_run_plan(owner.store, campaign)['plan']['discovery']['history']['record_cutoff']
    included = next(row for _, row in owner.store.records_upto('episodes', cutoff) if row['study_id'] == seeder.study_id)
    owner.store.put_record('evidence', included['episode_id'], {'episode_id': included['episode_id'], 'source': 'local_only'})
    owner.ledgers[campaign.campaign_id] = CampaignLedger(owner.store, campaign.campaign_id, campaign.caps)
    runner = flow.FakeRunner('tie'); runner.provider = Recording(c701)
    async def offline_runner(live): return runner, False
    owner._get_runner = offline_runner
    asyncio.run(owner._execute(campaign.campaign_id, True))
    ended = owner.get(campaign.campaign_id)
    assert ended.state == 'ERROR'
    assert ended.terminal_reason.startswith('AGENT_HISTORY_CHANGED: The store\'s prior history for this agent changed at or before')
    assert ended.terminal_reason.endswith('create a new plan')
    error = owner.store.get_record('execution_errors', campaign.campaign_id)
    assert error['code'] == 'AGENT_HISTORY_CHANGED' and error['error_class'] == 'HistoryChanged' and error['provider_dispatch'] is False
    assert runner.provider.messages == [] and runner.calls == [] and not owner.store.list_records('selections')
    assert owner.ledgers[campaign.campaign_id].used_calls == 0
