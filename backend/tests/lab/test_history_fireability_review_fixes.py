"""Review fixes for faultlab-explorer-selection/v3-history-fireability (fixer, September 30, 2026), offline and $0.

Both $0 reviews found (MEDIUM-1, F1) that the builder's rule refused a pick if ANY of its faults targeted a REFUSED row.
In native-v2b the only REFUSED row is the orders get_operation_status read, and every generated guardrail there adds a
read_current_operation step that calls exactly that read after an uncertain upgrade. So a pick that faults the status
read DURING A PENDING UPGRADE (a documented, fireable recipe, discovery family A4) was refused too, and a challenge under
a new plan could never test the guardrail's own new step failing. The fix: a pick is refused only when EVERY one of its
faults targets a REFUSED row (the v2d/v2f lone status-read pick). The table, its basis and everything else are unchanged.

Also here: the reviewers' test gaps (LOW-2: the ids-hash binding of compute_table, two challenges in one Session, and a
plan created through prepare_run_plan after fired candidate and challenge episodes), the Explorer request's statement that
the rule qualifies its instructions (F2, model side), and the experiments poll reading only this campaign's records (F3).

Scripted answers and the status-sensitive runner are fixture code, not model evidence. No provider, W&B, model, simulator
port or network call is made.
"""
import asyncio
import json

import pytest

import test_evaluation
import test_history_fireability as base
from app.agents.explorer import Explorer
from app.contracts.models import ExplorerOutput, TrialResult, Usage, content_hash, new_id
from app.lab import fireability
from app.lab.agent_history import HistoryChanged
from app.lab.challenge import Challenger
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V3, DISCOVERY_V4
from app.lab.evaluation import PairedEvaluator
from app.lab.operator_actions import register_agent
from app.lab.run_plans import ExplorerSelectionPlan, prepare_run_plan, read_run_plan
from test_agent_history import P, Seeder, plan_request
from test_history_fireability import (CONFIRM, DELAYED, STATUS, STATUS_TARGET, V2B_TABLE, Scripted, api_json, block_for,
                                      fire_status, raw, row_of, run_learn, seed_status_history, status_owner, table_row)

owner = base.owner
anyio_backend = base.anyio_backend

# The table a new v4 plan freezes on the saved native-v2b store (builder/saved-store-check.json): only the orders status
# read is REFUSED (0 of 4).
V2B_BLOCK = block_for([table_row(kind, service, tool, verified, fired) for kind, service, tool, verified, fired, _ in V2B_TABLE])
STATUS_AGAIN = P('F4', 'get_operation_status', 'orders', 3, failure_count=1)   # a second status-read fault in one pick
SEND_DELAYED = P('F1', 'send_confirmation', 'notifications', 1, response_delay_ms=2400)
STATUS_ROW = table_row('F4', 'orders', 'get_operation_status', 4, 0)


def decide(block, *primitives, challenge=True):
    session = fireability.Session(block, discovery_requests_max=8)
    pick = ExplorerOutput.model_validate({'fault_spec': {'seed': 1, 'primitives': list(primitives)}, 'hypothesis': 'Offline pick'})
    return fireability.decide(session, {'proposal_index': 0, 'selection_index': 0, 'slot_request': 1}, pick, None,
                              challenge=challenge, provenance='model')


# ---------------------------------------------------------------- MEDIUM-1 / F1: only picks made of REFUSED targets
def test_a_pick_is_refused_only_when_every_fault_targets_a_refused_row():
    assert fireability.declaration()['pick_refused_when'] == 'every_fault_on_a_refused_target'
    for challenge in (True, False):
        # The v2d/v2f lone status read, and two status-read faults: every target is REFUSED, so the pick is refused.
        for primitives in ([STATUS], [STATUS, STATUS_AGAIN]):
            decision, kept = decide(V2B_BLOCK, *primitives, challenge=challenge)
            assert (decision['status'], kept) == ('REFUSED_LOW_FIRED_SHARE', None)
            assert decision['refused_targets'] == [STATUS_ROW] and decision['refused_fault_spec']['primitives'] == primitives
        # A status-read fault beside a fault on any other target (in the table or not) runs: the history cannot say whether
        # the other fault makes the status read reached (a pending upgrade does: discovery family A4).
        for primitives in ([DELAYED(3), STATUS], [STATUS, DELAYED(3)], [CONFIRM, STATUS], [SEND_DELAYED, STATUS]):
            decision, kept = decide(V2B_BLOCK, *primitives, challenge=challenge)
            assert decision['status'] == 'ALLOWED' and kept is not None and kept.fault_spec.model_dump(mode='json')['primitives'] == primitives
            assert decision['refused_targets'] == [] and decision['refused_fault_spec'] is None
            statuses = {(t['kind'], t['target_service'], t['target_tool']): t['status'] for t in decision['targets']}
            assert statuses[STATUS_TARGET] == 'REFUSED' and len(statuses) == 2   # recorded, but it does not refuse the pick
            assert decision['reason'].startswith('Allowed: F4 on get_operation_status (orders) is REFUSED') and 'runs beside' in decision['reason']
        # A pick with no REFUSED target keeps a null reason, exactly as before.
        decision, _ = decide(V2B_BLOCK, DELAYED(3), challenge=challenge)
        assert (decision['status'], decision['reason']) == ('ALLOWED', None)


class StatusSensitiveRunner(test_evaluation.FakeRunner):
    """The integrity review's scripted weak guardrail (review-integrity/demo_fireability_hides_counterexample.py): the
    candidate fails C4 only when its status read is faulted during a pending upgrade; a lone status read is never reached
    (healthy upgrade), as in the saved store; the incumbent fails C3 everywhere, as in FakeRunner."""
    async def run(self, campaign, recipe, policy, **kwargs):
        self.calls.append((campaign, recipe, policy, kwargs))
        candidate = kwargs['arm'] == 'L'
        prims = recipe.primitives
        status = [p.kind == 'F4' and p.target_tool == 'get_operation_status' and p.target_service == 'orders' for p in prims]
        pending = any(p.kind == 'F2' and p.target_tool == 'update_order' for p in prims)
        failed = (['C4'] if any(status) and pending else []) if candidate else ['C3']
        return TrialResult(episode_id=kwargs.get('episode_id') or new_id('e'), world_id=new_id('world'),
                           scenario_hash=content_hash(recipe), policy_hash=policy.policy_hash, arm=kwargs['arm'],
                           trial_index=kwargs.get('trial_index', 0), lifecycle='COMPLETED',
                           outcome='VIOLATION' if failed else 'COMPLETED', failed_checks=failed,
                           fault_scheduled=bool(prims), fault_triggered=bool(prims) and not all(status),
                           usage=Usage(http_attempts=3 if candidate else 4))


OTHERS = [raw(DELAYED(1), seed=11), raw(CONFIRM, seed=12), raw(DELAYED(2), seed=13),
          raw(P('F1', 'update_order', 'orders', 1, response_delay_ms=2000), seed=14), raw(DELAYED(4), seed=15)]


async def status_challenge(tmp_path, first, *, declared):
    c, campaign, ledger, candidate, _ = test_evaluation.setup(tmp_path)
    runner = StatusSensitiveRunner()
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, test_evaluation.cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    ledger.reserve('candidate', 528)
    provider = Scripted([first] + list(OTHERS))
    explorer = Explorer(provider, c.store, ledger)
    explorer.fireability = fireability.Session(V2B_BLOCK, discovery_requests_max=8) if declared else None
    before = len(runner.calls)
    result = await Challenger(c.store, explorer, evaluator).run(campaign, c.policies.baseline(), candidate, source, reservation='candidate')
    selections = [c.store.get_record('selections', ref) for ref in result.selection_refs]
    return result, selections, len(runner.calls) - before


@pytest.mark.anyio
async def test_the_rule_no_longer_hides_a_counterexample_on_the_guardrails_status_read(tmp_path):
    """The integrity review's scenario A: with the builder's rule the combined pick was refused and a C4 counterexample
    became PASSED_OBSERVED. Now the pick runs, with the rule exactly as without it."""
    combined = raw(DELAYED(3), STATUS, seed=1)
    for declared in (False, True):
        result, selections, episodes = await status_challenge(tmp_path / f'combined-{declared}', combined, declared=declared)
        assert (result.status, result.failed_checks, len(result.schedule_hashes), episodes) == ('COUNTEREXAMPLE_FOUND', ['C4'], 1, 6)
        if declared:
            decision = selections[0]['fireability']
            assert decision['status'] == 'ALLOWED' and [t['status'] for t in decision['targets']] == ['ALLOWED', 'REFUSED']
    # Scenario B, the intended effect, is unchanged: the lone status read is refused, and the challenge completes.
    lone = raw(STATUS, seed=1)
    plain, _, _ = await status_challenge(tmp_path / 'lone-plain', lone, declared=False)
    ruled, selections, episodes = await status_challenge(tmp_path / 'lone-ruled', lone, declared=True)
    assert (plain.status, plain.stopping_reason) == ('INCONCLUSIVE', 'Incomplete or untriggered challenge pair')
    assert (ruled.status, len(ruled.schedule_hashes), episodes) == ('PASSED_OBSERVED', 4, 24)
    assert [s['fireability']['status'] for s in selections] == ['REFUSED_LOW_FIRED_SHARE'] + ['ALLOWED'] * 4


def test_a_discovery_pick_beside_a_pending_upgrade_runs_and_a_lone_one_is_still_refused(owner, monkeypatch):
    status_owner(owner)
    def answer(slot, number, _context):
        if slot == 0: return raw(DELAYED(3), STATUS)
        return raw(STATUS) if number == 1 else raw(DELAYED(9))
    campaign, ledger, runner, rows = run_learn(owner, DISCOVERY_V3, answer, slots=2, monkeypatch=monkeypatch)
    assert fire_status(rows) == [(0, 1, 'SELECTED', 'ALLOWED'), (1, 1, 'SKIPPED_UNFIREABLE', 'REFUSED_LOW_FIRED_SHARE'),
                                 (1, 2, 'SELECTED', 'ALLOWED')]
    assert [len(call[1].primitives) for call in runner.calls] == [2, 1] and ledger.used_calls == 3
    assert [t['status'] for t in rows[0]['fireability']['targets']] == ['ALLOWED', 'REFUSED']


def test_saved_plans_declare_the_every_fault_rule_and_the_model_refuses_another(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    seed_status_history(Seeder(owner, registration))
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V4))
    block = read_run_plan(owner.store, owner.create(prepared.campaign_request, run_plan=prepared))['plan']['explorer_selection']
    assert block['pick_refused_when'] == 'every_fault_on_a_refused_target' and 'every one of its faults' in block['rule']
    for bad in ({**block, 'pick_refused_when': 'any_fault_on_a_refused_target'},
                {key: value for key, value in block.items() if key != 'pick_refused_when'}):
        with pytest.raises(ValueError):
            ExplorerSelectionPlan.model_validate(bad)


# ---------------------------------------------------------------- F2 (model side): the request qualifies the prompt
@pytest.mark.anyio
async def test_the_request_says_the_rule_qualifies_every_valid_pick_runs(tmp_path):
    answers = [raw(STATUS), raw(DELAYED(1)), raw(DELAYED(2)), raw(DELAYED(3)), raw(DELAYED(4))]
    result, provider, selections, episodes, ledger = await base.challenge(tmp_path, answers)
    for context in provider.contexts:
        note = context['history_fireability']['note']
        assert note == fireability.EXPLORER_NOTE and 'takes precedence' in note and 'every valid schedule is tested' in note
    assert 'at least one fault on a target that is not REFUSED' in provider.contexts[1]['slot_feedback']['instruction']


# ---------------------------------------------------------------- LOW-2: test gaps
def test_compute_table_refuses_a_history_whose_episodes_are_not_the_stores(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    seeder = Seeder(owner, registration)
    seed_status_history(seeder)
    history = seeder.history()
    assert row_of(fireability.compute_table(owner.store, history))['fired_share'] == '0/3'
    for changed in ({**history, 'episode_ids_hash': 'f' * 64},
                    {**history, 'summary': {**history['summary'], 'verified_episodes': history['summary']['verified_episodes'] + 1}}):
        with pytest.raises(HistoryChanged, match='differ from the plan'):
            fireability.compute_table(owner.store, changed)


def test_a_fault_without_a_recorded_execution_never_counts_as_fired(owner):
    """Review mutation R16 (near-equivalent: the simulator writes one execution per fault), pinned anyway: a verified
    episode whose verdict lacks the execution entry for a fault counts that target as not fired."""
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    seeder = Seeder(owner, registration)
    pick = seed_status_history(seeder, fired=(True, True))
    assert row_of(fireability.compute_table(owner.store, seeder.history()))['fired_share'] == '2/2'
    episode_id = seeder.episode(pick, via='campaign', triggered=True)
    record = owner.store.get_record('episodes', episode_id)
    record['verdict']['fault_executions'] = []
    owner.store.put_record('episodes', episode_id, record)
    assert row_of(fireability.compute_table(owner.store, seeder.history()))['fired_share'] == '2/3'


@pytest.mark.anyio
async def test_two_challenges_in_one_session_never_share_refusals_or_a_pending_replan(tmp_path):
    c, campaign, ledger, first, runner = test_evaluation.setup(tmp_path)
    from app.contracts.models import CandidatePolicy, canonical_json
    second = c.policies.proposal(CandidatePolicy.model_validate_json(canonical_json({'parent_version': 'policy-v0', 'rules': [
        {'hook': 'before_confirmation', 'when': 'always', 'steps': [{'op': 'read_current_operation'}, {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}]})),
        parent='policy-v0', raw='second manual unit fixture', episode_ids=[], author='manual')
    evaluator = PairedEvaluator(c.store, runner, ledger)
    session = fireability.Session(V2B_BLOCK, discovery_requests_max=8)
    contexts = []
    for index, (candidate, answers) in enumerate(((first, [raw(STATUS), raw(STATUS, seed=2)] + [raw(DELAYED(n)) for n in range(1, 5)]),
                                                  (second, [raw(DELAYED(n)) for n in range(5, 9)]))):
        source = await evaluator.run(campaign, test_evaluation.cases(1), c.policies.baseline(), candidate, purpose='source_validation')
        ledger.reserve(f'candidate-{index}', 528)
        provider = Scripted(answers); explorer = Explorer(provider, c.store, ledger); explorer.fireability = session
        result = await Challenger(c.store, explorer, evaluator).run(campaign, c.policies.baseline(), candidate, source, reservation=f'candidate-{index}')
        assert result.status == 'PASSED_OBSERVED'
        contexts.append(provider.contexts)
    assert [len(ctx['history_fireability']['refused_picks']) for ctx in contexts[0]] == [0, 1, 2, 2, 2, 2]
    # The second candidate's challenge starts clean: its first request is slot 1, no re-plan, no refused pick listed.
    opening = contexts[1][0]
    assert opening['slot_request'] == 1 and 'replan_of' not in opening and 'slot_feedback' not in opening
    assert all(ctx['history_fireability']['refused_picks'] == [] for ctx in contexts[1])


def test_a_plan_saved_after_fired_candidate_and_challenge_episodes_freezes_the_same_table(owner):
    """Through the product path (prepare_run_plan), not a fixed block: episodes the rule must never read, all firing the
    status read, change nothing; an eligible verified discovery episode that fired does."""
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    seeder = Seeder(owner, registration)
    pick = seed_status_history(seeder)
    def frozen():
        prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V4))
        return prepared.plan['explorer_selection']['table']
    before = frozen()
    assert row_of(before)['fired_share'] == '0/3'
    for purpose in ('challenge', 'source_validation', 'reproduction', 'reduction', 'intervention'):
        seeder.episode(pick, via='campaign', purpose=purpose)                          # incumbent arm
        seeder.episode(pick, via='campaign', purpose=purpose, arm='L', policy_hash='c' * 64)   # candidate arm
    seeder.episode(pick, via='campaign', policy_hash='c' * 64)                           # a candidate policy's discovery episode
    assert frozen()['rows'] == before['rows']
    seeder.episode(pick, via='campaign', triggered=True)
    assert row_of(frozen())['fired_share'] == '1/4'


# ---------------------------------------------------------------- F3: the dashboard poll reads only this campaign
def full_scan_summary(store, campaign_id, block):
    """The builder's algorithm (every selection and challenge record parsed on each poll), kept here as the reference."""
    challenge_of = {ref: challenge['challenge_id'] for challenge in store.list_records('challenges') for ref in challenge.get('selection_refs', [])}
    rows = []
    for selection in store.list_records('selections'):
        decision = selection.get('fireability')
        if decision is None or (selection.get('context') or {}).get('campaign_id') != campaign_id:
            continue
        spec = (selection.get('output') or {}).get('fault_spec') or (selection.get('selected_output') or {}).get('fault_spec')
        rows.append({'selection_id': selection['selection_id'], 'challenge_id': challenge_of.get(selection['selection_id']),
                     'recipe': fireability._readable(spec) if spec else None, **decision})
    slots = [row for row in store.list_records('explorer_selection_slots') if row.get('campaign_id') == campaign_id]
    return {'protocol': block['protocol'], 'table_hash': block['table_hash'], 'refused_targets': list(block['table']['refused_targets']),
            'picks_checked': sum(row['status'] in ('ALLOWED', 'REFUSED_LOW_FIRED_SHARE') for row in rows),
            'picks_refused': sum(row['status'] == 'REFUSED_LOW_FIRED_SHARE' for row in rows), 'decisions': rows, 'slots_without_request': slots}


def test_the_experiments_poll_reads_only_this_campaigns_selections_challenges_and_slots(owner, monkeypatch):
    status_owner(owner)
    answer = lambda slot, number, _c: raw(STATUS) if (slot, number) == (0, 1) else raw(DELAYED(slot + 1 if number == 1 else 9))
    campaign, ledger, runner, rows = run_learn(owner, DISCOVERY_V3, answer, monkeypatch=monkeypatch)
    ident = campaign.campaign_id
    block = read_run_plan(owner.store, campaign)['plan']['explorer_selection']
    # A challenge of this campaign (one of its selections) and another campaign's challenge and selection.
    challenged = rows[1]['selection_id']
    owner.store.put_record('challenges', 'challenge-this', {'challenge_id': 'challenge-this', 'selection_refs': [challenged]})
    owner.store.put_record('challenge_campaigns', 'challenge-this', {'campaign_id': ident, 'challenge_id': 'challenge-this'})
    owner.store.put_record('selections', 'selection-elsewhere', {**rows[0], 'selection_id': 'selection-elsewhere',
                                                                  'context': {**rows[0]['context'], 'campaign_id': 'campaign-elsewhere'}})
    owner.store.put_record('challenges', 'challenge-elsewhere', {'challenge_id': 'challenge-elsewhere', 'selection_refs': ['selection-elsewhere']})
    owner.store.put_record('challenge_campaigns', 'challenge-elsewhere', {'campaign_id': 'campaign-elsewhere', 'challenge_id': 'challenge-elsewhere'})
    expected = full_scan_summary(owner.store, ident, block)
    assert [row['challenge_id'] for row in expected['decisions']][:2] == [None, 'challenge-this'] and len(expected['decisions']) == 8
    real = owner.store.list_records
    def narrow(kind):
        assert kind not in ('selections', 'challenges', 'explorer_selection_slots', 'challenge_campaigns'), f'full scan of {kind}'
        return real(kind)
    monkeypatch.setattr(owner.store, 'list_records', narrow)
    assert fireability.campaign_summary(owner.store, ident, block) == expected
    experiments, = api_json(owner, f'/api/campaigns/{ident}/experiments')
    assert experiments['explorer_fireability'] == json.loads(json.dumps(expected))


def test_the_experiments_poll_does_not_validate_the_plan_of_a_campaign_without_the_rule(owner, monkeypatch):
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=DISCOVERY_V1))
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    from app.lab import run_plans
    calls, real = [], run_plans.read_run_plan
    monkeypatch.setattr(run_plans, 'read_run_plan', lambda *args, **kwargs: calls.append(args) or real(*args, **kwargs))
    experiments, = api_json(owner, f'/api/campaigns/{campaign.campaign_id}/experiments')
    assert set(experiments) == {'counterexamples', 'evidence', 'ingestions', 'portability_ids'} and calls == []
