"""faultlab-challenge-selection/v2-candidate-reach (app.lab.loop_limits, in the Explorer's selection handling).

WITHDRAWN before any live run (both $0 reviews, HIGH-1): no new plan declares it and a plan that does cannot start.
These tests keep the unused mechanism honest for the PM's decision, and one test checks that under a new Learn plan's
own rules a refusal can no longer turn a counterexample into a pass.

Live campaign ea66672d's challenge (run v2d) ended INCONCLUSIVE: its third pick (F4 on get_operation_status, orders,
and no other fault) did not fire in every pair. With the upgrade healthy, neither arm needs that read: it fired in 1 of
3 incumbent episodes and 0 of 3 candidate episodes, and the candidate policy (which reads the status only after an
uncertain upgrade or a missing receipt) read nothing there. Under the rule such a pick is refused before any pair runs
(the agent never called that read in the candidate arm's source validation) and the Explorer gets one re-plan, inside
the challenge's existing 8 Explorer requests. app/lab/challenge.py is unchanged. No provider or network call is made.
"""
import json

import pytest

from app.agents.explorer import CHALLENGER, PROMPT, Explorer
from app.contracts.models import canonical_json
from app.lab import loop_limits
from app.lab.challenge import Challenger
from app.lab.evaluation import PairedEvaluator
from app.lab.loop_limits import CHALLENGE_SELECTION_V2, challenge_selection_declaration
from app.providers.runtime import RuntimeGeneration
from test_evaluation import cases, setup
from test_discovery_v2_flow import owner  # noqa: F401  (a fixture)

MODEL = 'openai/gpt-oss-120b'


@pytest.fixture
def anyio_backend(): return 'asyncio'


def P(kind, tool, service, occurrence=1, **parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': occurrence, 'parameters': parameters}


def delayed(ticks): return P('F2', 'update_order', 'orders', completion_delay_ticks=ticks, terminal_status='SUCCEEDED', failure_code=None)


STATUS_ORDERS = P('F4', 'get_operation_status', 'orders', failure_count=1)            # the v2d third pick
CONFIRMATION = P('F4', 'send_confirmation', 'notifications', failure_count=1)


def pick(*primitives, seed=1):
    return canonical_json({'fault_spec': {'seed': seed, 'primitives': list(primitives)}, 'hypothesis': 'Offline scripted challenge pick'})


class Scripted:
    """Answers each challenge request in order and keeps every request it was sent."""
    def __init__(self, answers):
        self.answers = list(answers); self.contexts = []; self.systems = []
    def role_model(self, role): return MODEL
    async def complete(self, messages, **kwargs):
        self.systems.append(messages[0]['content']); self.contexts.append(json.loads(messages[-1]['content']))
        return RuntimeGeneration(self.answers.pop(0), MODEL, input_tokens=100, output_tokens=20)


def source_validation(c, campaign, candidate, *, agent_calls, policy_calls=()):
    """Save the candidate arm's source-validation episodes and their recorded calls, as the runner would."""
    for index in range(3):
        episode = f'episode-sv-{index}'
        c.store.put_record('episodes', episode, {'episode_id': episode, 'campaign_id': campaign.campaign_id, 'experiment_purpose': 'source_validation',
                                                 'policy_hash': candidate.policy_hash, 'policy_version': candidate.version, 'arm': 'L', 'split': 'development'})
        c.store.put_record('private_episode_inputs', episode, {'intent': {'upgrade_operation_id': f'op-up-{index}', 'notification_operation_id': f'op-note-{index}'}})
        calls = [('actor', tool) for tool in agent_calls] + [('policy', tool) for tool in policy_calls]
        for n, (caller, tool) in enumerate(calls):
            call = f'call-{index}-{n}'; observation = f'observation-{index}-{n}'
            data = {'service': 'orders'} if tool == 'get_operation_status' else None
            c.store.put_record('observations', observation, {'evidence_id': observation, 'episode_id': episode,
                                                             'result': {'tool': tool, 'data': data, 'operation_id': f'op-up-{index}'}})
            c.store.put_record('tool_calls', call, {'call_id': call, 'episode_id': episode, 'tool': tool, 'caller': caller,
                                                   'hook': None if caller == 'actor' else 'after_upgrade_response',
                                                   'attempt_ids': [f'attempt-{index}-{n}'], 'observation_ids': [observation]})


async def challenge(tmp_path, answers, *, declared=True, agent_calls=('get_order', 'update_order', 'send_confirmation'),
                    policy_calls=('get_operation_status',), write_episodes=True):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    if write_episodes:
        source_validation(c, campaign, candidate, agent_calls=agent_calls, policy_calls=policy_calls)
    ledger.reserve('candidate', 528)
    provider = Scripted(answers); explorer = Explorer(provider, c.store, ledger)
    explorer.challenge_reach = challenge_selection_declaration() if declared else None
    before = len(runner.calls)
    result = await Challenger(c.store, explorer, evaluator).run(campaign, c.policies.baseline(), candidate, source, reservation='candidate')
    selections = [c.store.get_record('selections', ref) for ref in result.selection_refs]
    return result, provider, selections, len(runner.calls) - before, ledger


def status(selections): return [s['challenge_reach']['status'] for s in selections]


@pytest.mark.anyio
async def test_a_pick_on_a_tool_the_agent_never_called_is_refused_and_replanned_once_inside_the_budget(tmp_path):
    answers = [pick(STATUS_ORDERS), pick(delayed(1)), pick(delayed(2)), pick(delayed(3)), pick(delayed(4))]
    result, provider, selections, episodes, ledger = await challenge(tmp_path, answers)
    # The refused pick ran no pair; the four schedules after it ran three pairs each; the challenge passed as before.
    assert status(selections) == ['REFUSED_UNREACHED', 'SELECTED', 'SELECTED', 'SELECTED', 'SELECTED']
    assert episodes == 4 * 6 and len(result.trial_pairs) == 12 and result.status == 'PASSED_OBSERVED'
    refused = selections[0]
    assert refused['selected_output'] is None and refused['output']['fault_spec']['primitives'][0]['target_tool'] == 'get_operation_status'
    decision = refused['challenge_reach']
    assert decision['unreached'] == ['get_operation_status:orders'] and decision['slot_request'] == 1
    assert decision['basis']['tool_services_called_by_agent'] == ['get_order:orders', 'send_confirmation:notifications', 'update_order:orders']
    assert decision['basis']['called_only_by_candidate_policy'] == ['get_operation_status:orders']
    assert "only the candidate policy's own hook steps read it there" in decision['reason']
    # The next request is the one re-plan, told why; it is charged like any other request.
    replan = provider.contexts[1]
    assert replan['slot_request'] == 2 and replan['replan_of'] == refused['selection_id']
    assert replan['slot_feedback']['unreached_tool_services'] == ['get_operation_status:orders']
    assert selections[1]['challenge_reach']['slot_request'] == 2 and selections[1]['challenge_reach']['replan_of'] == refused['selection_id']
    assert [ctx['slot_request'] for ctx in provider.contexts] == [1, 2, 1, 1, 1]
    assert len(provider.contexts) == 5 and ledger.used_calls == 5          # every request, the re-plan included, is charged
    # The Explorer is told the rule: in its system prompt and in its request.
    assert all(CHALLENGE_SELECTION_V2 in system for system in provider.systems)
    assert provider.contexts[0]['candidate_reach']['rule'] == loop_limits.CHALLENGE_REACH_RULE
    assert provider.contexts[2]['candidate_reach']['refused_picks_this_challenge'][0]['refused_selection_id'] == refused['selection_id']


@pytest.mark.anyio
async def test_the_replan_is_inside_the_existing_eight_requests_and_a_refused_replan_gets_no_second_one(tmp_path):
    answers = [pick(STATUS_ORDERS, seed=n) for n in range(8)]
    result, provider, selections, episodes, ledger = await challenge(tmp_path, answers)
    assert len(provider.contexts) == 8 and ledger.used_calls == 8                # bounded and charged exactly as before
    assert [ctx['slot_request'] for ctx in provider.contexts] == [1, 2, 1, 2, 1, 2, 1, 2]
    assert status(selections) == ['REFUSED_UNREACHED'] * 8 and episodes == 0
    assert result.status == 'INCONCLUSIVE' and result.stopping_reason == 'Fewer than four feasible schedules' and not result.trial_pairs
    assert 'This was already the re-plan, so there is no further re-plan' in selections[1]['challenge_reach']['reason']


@pytest.mark.anyio
async def test_reachable_picks_run_exactly_as_today(tmp_path):
    answers = [pick(delayed(n)) for n in range(1, 5)]
    declared, provider, selections, episodes, ledger = await challenge(tmp_path / 'declared', answers)
    before, old_provider, old_selections, old_episodes, old_ledger = await challenge(tmp_path / 'before', list(answers), declared=False)
    assert status(selections) == ['SELECTED'] * 4
    assert (declared.status, declared.stopping_reason, len(declared.trial_pairs), declared.failed_checks, episodes, ledger.used_calls) == \
           (before.status, before.stopping_reason, len(before.trial_pairs), before.failed_checks, old_episodes, old_ledger.used_calls) == \
           ('PASSED_OBSERVED', 'No candidate violation observed in four schedules × three pairs', 12, [], 24, 4)
    # Without the rule (every plan saved before it), the request is today's: no new field, no new prompt section.
    assert all(system == PROMPT + '\n' + CHALLENGER for system in old_provider.systems)
    assert not any(key in ctx for ctx in old_provider.contexts for key in ('candidate_reach', 'challenge_selection_protocol', 'slot_request'))
    assert not any('challenge_reach' in s for s in old_selections)


@pytest.mark.anyio
async def test_a_fault_on_a_service_the_agent_never_reached_is_refused_and_without_evidence_nothing_is(tmp_path):
    # A candidate that closed business before confirming in its source validation (as v2d's did): confirmation faults
    # are refused too. This narrows the challenge; the report states it.
    answers = [pick(CONFIRMATION), pick(delayed(1)), pick(delayed(2)), pick(delayed(3)), pick(delayed(4))]
    result, provider, selections, episodes, ledger = await challenge(tmp_path / 'closed', answers, agent_calls=('get_order', 'update_order'))
    assert status(selections)[0] == 'REFUSED_UNREACHED' and selections[0]['challenge_reach']['unreached'] == ['send_confirmation:notifications']
    assert "only the candidate policy's own hook steps" not in selections[0]['challenge_reach']['reason']
    # No source-validation episode on record: no evidence, so no refusal; the pick runs as before.
    result, provider, selections, episodes, ledger = await challenge(tmp_path / 'none', [pick(STATUS_ORDERS)] + [pick(delayed(n)) for n in range(1, 4)],
                                                                    write_episodes=False)
    assert status(selections) == ['NOT_CHECKED', 'NOT_CHECKED', 'NOT_CHECKED', 'NOT_CHECKED'] and episodes == 24
    assert provider.contexts[0]['candidate_reach']['source_validation_episode_ids'] == []


@pytest.mark.anyio
async def test_an_invalid_answer_is_recorded_and_clears_a_pending_replan(tmp_path):
    answers = [pick(STATUS_ORDERS), 'not json', pick(delayed(1)), pick(delayed(2)), pick(delayed(3)), pick(delayed(4))]
    result, provider, selections, episodes, ledger = await challenge(tmp_path, answers)
    assert status(selections) == ['REFUSED_UNREACHED', 'INVALID_OUTPUT', 'SELECTED', 'SELECTED', 'SELECTED', 'SELECTED']
    assert [ctx['slot_request'] for ctx in provider.contexts] == [1, 2, 1, 1, 1, 1] and result.status == 'PASSED_OBSERVED'


def test_the_v2d_third_pick_is_refused_under_the_rule_and_the_other_two_are_not():
    """The saved v2d candidate arm (store native-v2b, read-only analysis in artifacts/product-loop-limits-2026-09-30/builder
    and fixer/verify-v2d-picks.json): in its 3 source-validation episodes (a rejected upgrade) the agent called get_order
    and update_order; the candidate policy alone read the orders status. The challenge's picks were F1 and F2 on
    update_order, then F4 on the orders status read. The rule refuses pick 3 only because source validation did not
    include that read: in pick 2 the candidate's agent itself read the orders status 3-4 times per episode."""
    reach = {'episode_ids': ['sv-1', 'sv-2', 'sv-3'], 'agent': ['get_order:orders', 'update_order:orders'],
             'policy_only': ['get_operation_status:orders']}
    from app.contracts.models import ExplorerOutput
    session = loop_limits.ChallengeReachSession(('c', 'h', 'i'))
    picks = [P('F1', 'update_order', 'orders', response_delay_ms=2500), delayed(8), STATUS_ORDERS]
    decisions = []
    for index, primitive in enumerate(picks):
        output = ExplorerOutput.model_validate({'fault_spec': {'seed': index, 'primitives': [primitive]}, 'hypothesis': 'v2d pick'})
        decision, selected = loop_limits.decide(reach, session, {'proposal_index': index, 'slot_request': 1}, output, None)
        decisions.append((decision['status'], selected is not None))
    assert decisions == [('SELECTED', True), ('SELECTED', True), ('REFUSED_UNREACHED', False)]


class ConfirmationSensitiveRunner:
    """The incumbent fails C3 everywhere (as test_evaluation.FakeRunner does); the candidate fails C4 only when a schedule
    faults send_confirmation: a stand-in for a candidate that mishandles a confirmation failure after a healthy upgrade,
    a path its source validation (a rejected upgrade) never reached. From the integrity review's demonstration
    (artifacts/product-loop-limits-2026-09-30/review-integrity/demo_rule2_hides_counterexample.py)."""
    def __init__(self):
        from test_evaluation import FakeRunner
        self.base = FakeRunner(); self.calls = self.base.calls
    async def run(self, campaign, recipe, policy, **kwargs):
        from app.contracts.models import TrialResult, Usage, content_hash, new_id
        self.calls.append((campaign, recipe, policy, kwargs))
        candidate = kwargs['arm'] == 'L'
        failed = (['C4'] if any(p.target_tool == 'send_confirmation' for p in recipe.primitives) else []) if candidate else ['C3']
        return TrialResult(episode_id=kwargs.get('episode_id') or new_id('e'), world_id=new_id('world'), scenario_hash=content_hash(recipe),
                           policy_hash=policy.policy_hash, arm=kwargs['arm'], trial_index=kwargs.get('trial_index', 0), lifecycle='COMPLETED',
                           outcome='VIOLATION' if failed else 'COMPLETED', failed_checks=failed, fault_scheduled=bool(recipe.primitives),
                           fault_triggered=bool(recipe.primitives), usage=Usage(http_attempts=3 if candidate else 4))


async def confirmation_sensitive_challenge(tmp_path, rule):
    c, campaign, ledger, candidate, _ = setup(tmp_path)
    runner = ConfirmationSensitiveRunner(); evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    # As v2d's candidate: under the source's rejected upgrade its agent called only get_order and update_order.
    source_validation(c, campaign, candidate, agent_calls=('get_order', 'update_order'), policy_calls=('get_operation_status',))
    ledger.reserve('candidate', 528)
    explorer = Explorer(Scripted([pick(CONFIRMATION)] + [pick(delayed(n), seed=n) for n in range(1, 5)]), c.store, ledger)
    explorer.challenge_reach = rule
    return await Challenger(c.store, explorer, evaluator).run(campaign, c.policies.baseline(), candidate, source, reservation='candidate')


def test_under_a_new_learn_plan_a_pick_refusal_cannot_turn_a_counterexample_into_a_pass(tmp_path, owner):
    """Both reviews, HIGH-1: the candidate-reach rule refused the confirmation pick that finds this candidate's C4 and the
    challenge then PASSED (the integrity review's replay). The rule is withdrawn from new Learn plans until the PM picks a
    basis that does not depend on the candidate, so under a new plan's own rule the same answers find the counterexample."""
    import asyncio
    from app.lab.run_plans import read_run_plan
    from test_discovery_v2_flow import learn_campaign
    campaign = learn_campaign(owner, None, 'smolagents-v2')
    rule = loop_limits.challenge_selection_rule(owner.store, campaign)
    result = asyncio.run(confirmation_sensitive_challenge(tmp_path / 'challenge', rule))
    assert (result.status, result.failed_checks) == ('COUNTEREXAMPLE_FOUND', ['C4'])
    assert rule is None and 'challenge_selection' not in read_run_plan(owner.store, campaign)['plan']


def test_the_declaration_is_what_the_plan_freezes():
    from app.lab.run_plans import ChallengeSelectionPlan
    declaration = challenge_selection_declaration()
    assert ChallengeSelectionPlan.model_validate(declaration).model_dump(mode='json') == declaration
    assert declaration['explorer_requests_per_challenge'] == 8 and declaration['challenge_rules_changed'] is False
    assert declaration['caller_counted'] == 'actor' and declaration['replans_per_refused_pick'] == 1


@pytest.mark.anyio
@pytest.mark.parametrize('declared', [True, False])
async def test_the_learning_loop_hands_the_plans_rule_to_its_explorer(tmp_path, monkeypatch, declared):
    import app.lab.learning as learning
    from app.lab.learning import run_learning_cycle
    from test_learning_qualification import candidate, loop
    c, campaign, runner, contexts, exports = loop(tmp_path, monkeypatch, [candidate(), None])
    made = []
    Base = learning.Explorer
    class Recorded(Base):
        def __init__(self, *args):
            super().__init__(*args); made.append(self)
    monkeypatch.setattr(learning, 'Explorer', Recorded)
    monkeypatch.setattr(loop_limits, 'challenge_selection_rule', lambda store, campaign: challenge_selection_declaration() if declared else None)
    await run_learning_cycle(c, campaign, runner)
    explorer, = made
    assert explorer.challenge_reach == (challenge_selection_declaration() if declared else None)
