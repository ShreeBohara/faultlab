"""Reachability pre-check (discovery protocol v2): fixed rules, Actor-faithful replay, isolation.

Every replay runs the real simulator source in-process on a temporary world store; the
autouse network guard in tests/conftest.py fails any socket use. No provider, no lab store.
"""
import asyncio
import itertools
import json
from pathlib import Path
import random
import tempfile

import pytest

from app.contracts.models import FaultSpec
from app.lab import reachability
from app.lab.reachability import (LABELLER_VERSION, TEMPLATES, UNKNOWN_STATUS_CHECKS, UnsupportedTarget,
                                   caller_model_for, fixed_rules, label_recipe, label_recipe_async, normal_path)

AUDIT = Path(__file__).resolve().parents[3] / 'audit'


@pytest.fixture(scope='module')
def caller():
    return caller_model_for('reference', [])


def P(kind, tool, service, occurrence, **parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': occurrence, 'parameters': parameters}


def R(*primitives):
    return {'seed': 1, 'primitives': list(primitives)}


def F2(delay, ok=True, occurrence=1):
    return P('F2', 'update_order', 'orders', occurrence, completion_delay_ticks=delay,
             terminal_status='SUCCEEDED' if ok else 'FAILED', failure_code=None if ok else 'UPGRADE_REJECTED')


def F4(tool, service, occurrence, count):
    return P('F4', tool, service, occurrence, failure_count=count)


def F1(tool, service, occurrence=1, delay=1500):
    return P('F1', tool, service, occurrence, response_delay_ms=delay)


def verdicts(result):
    return [(fault['verdict'], fault['reason_code']) for fault in result['faults']]


# ---------------------------------------------------------------- fixed rules S1-S4
def test_s1_same_first_update_attempt_blocks_f1_with_its_template(caller):
    result = label_recipe(R(F1('update_order', 'orders', 1, 2000), F2(10)), caller)
    assert verdicts(result)[0] == ('IMPOSSIBLE', 'S1')
    assert result['faults'][0]['explanation'] == TEMPLATES['S1']
    assert 'PENDING' in result['faults'][0]['explanation']


def test_s1_is_not_applied_after_occurrence_one_where_the_backtest_found_counterexamples(caller):
    # F2 at attempt 2 cannot install (S3), so attempt 2 is a replay that commits and F1 can fire.
    primitives = [F1('update_order', 'orders', 2), F2(3, occurrence=2)]
    assert fixed_rules(primitives) == [None, 'S3']
    result = label_recipe(R(*primitives), caller)
    assert verdicts(result) == [('NOT_FORCED', 'N3_REPEATED_WRITE'), ('IMPOSSIBLE', 'S3')]


@pytest.mark.parametrize('order', [0, 1])
def test_s2_any_covering_f4_blocks_a_non_f4_fault_whatever_its_position(caller, order):
    primitives = [F4('update_order', 'orders', 1, 1), F1('update_order', 'orders', 1)]
    if order: primitives.reverse()
    result = label_recipe(R(*primitives), caller)
    f1 = next(fault for fault in result['faults'] if fault['kind'] == 'F1')
    assert (f1['verdict'], f1['reason_code']) == ('IMPOSSIBLE', 'S2')
    assert 'rejects it with a 503' in f1['explanation']


def test_s2_f4_is_shadowed_only_by_an_earlier_f4(caller):
    shadowed = label_recipe(R(F4('update_order', 'orders', 1, 2), F4('update_order', 'orders', 1, 1)), caller)
    assert verdicts(shadowed) == [('FORCED', 'FORCED'), ('IMPOSSIBLE', 'S2')]
    assert 'earlier F4' in shadowed['faults'][1]['explanation']
    # The back-test counterexample: the later, wider F4 still fires on attempt 2.
    unshadowed = label_recipe(R(F4('update_order', 'orders', 1, 1), F4('update_order', 'orders', 1, 2)), caller)
    assert verdicts(unshadowed) == [('FORCED', 'FORCED'), ('FORCED', 'FORCED')]


def test_s3_f2_after_attempt_one_needs_every_earlier_update_rejected(caller):
    assert verdicts(label_recipe(R(F2(5, ok=False, occurrence=2)), caller)) == [('IMPOSSIBLE', 'S3')]
    assert 'replay' in label_recipe(R(F2(5, ok=False, occurrence=2)), caller)['faults'][0]['explanation']
    covered = label_recipe(R(F4('update_order', 'orders', 1, 1), F2(3, occurrence=2)), caller)
    assert verdicts(covered) == [('FORCED', 'FORCED'), ('FORCED', 'FORCED')]
    assert fixed_rules([F4('update_order', 'orders', 1, 2), F2(3, occurrence=3)]) == [None, None]
    assert fixed_rules([F4('update_order', 'orders', 2, 1), F2(3, occurrence=3)]) == [None, 'S3']


def test_s4_guard_beyond_the_world_attempt_budget():
    beyond = dict(F4('get_order', 'orders', 1, 1), occurrence=19)  # the contract caps occurrence at 18
    assert fixed_rules([beyond]) == ['S4']
    assert TEMPLATES['S4'].format(http_attempts=18).endswith('18 business HTTP attempts.')


# ---------------------------------------------------------------- Actor-faithful replay
C701 = [  # the c701e850 picks and the verdicts the back-test confirmed against their live outcomes
    (R(F2(3)), [('FORCED', 'FORCED')]),
    (R(P('F3', 'get_order', 'orders', 1, versions_back=1)), [('FORCED', 'FORCED')]),
    (R(F4('get_operation_status', 'orders', 1, 1)), [('NOT_FORCED', 'N2_UNNEEDED_STATUS_CHECK')]),
    (R(F1('send_confirmation', 'notifications', 1, 2000)), [('FORCED', 'FORCED')]),
    (R(F4('get_order', 'orders', 1, 1)), [('FORCED', 'FORCED')]),
    (R(F4('get_operation_status', 'orders', 1, 2)), [('NOT_FORCED', 'N2_UNNEEDED_STATUS_CHECK')]),
    (R(F4('get_operation_status', 'orders', 1, 1), F1('send_confirmation', 'notifications', 1, 2500)),
     [('NOT_FORCED', 'N2_UNNEEDED_STATUS_CHECK'), ('FORCED', 'FORCED')]),
]


@pytest.mark.parametrize('recipe,expected', C701)
def test_c701e850_picks_match_their_confirmed_verdicts(caller, recipe, expected):
    assert verdicts(label_recipe(recipe, caller)) == expected


@pytest.mark.parametrize('recipe,expected', [
    (R(F2(3), F4('get_operation_status', 'orders', 1, 1)), [('FORCED', 'FORCED')] * 2),
    (R(F4('get_operation_status', 'notifications', 1, 1)), [('NOT_FORCED', 'N2_UNNEEDED_STATUS_CHECK')]),
    (R(F2(2, ok=False), F1('send_confirmation', 'notifications', 1, 3000)), [('FORCED', 'FORCED'), ('NOT_FORCED', 'N4_RULE_BREAKING_CALL')]),
    (R(F4('get_order', 'orders', 2, 2)), [('NOT_FORCED', 'N1_OPTIONAL_READ')]),
    (R(F4('send_confirmation', 'notifications', 1, 2)), [('FORCED', 'FORCED')]),
    (R(F4('update_order', 'orders', 1, 2)), [('FORCED', 'FORCED')]),
])
def test_plan_dry_run_cases(caller, recipe, expected):
    assert verdicts(label_recipe(recipe, caller)) == expected


def test_review_counterexample_status_fault_on_third_check_is_forced(caller):
    # F2 delay 3: the agent polls PENDING, PENDING, then the third check gets the 503 and is retried.
    result = label_recipe(R(F2(3), F4('get_operation_status', 'orders', 3, 1)), caller)
    assert verdicts(result) == [('FORCED', 'FORCED'), ('FORCED', 'FORCED')]
    assert 'get_operation_status:orders#503' in result['agent_path']


@pytest.mark.parametrize('delay', [5, 6, 8, 12, 16, 20])
@pytest.mark.parametrize('send', [F1('send_confirmation', 'notifications', 1, 1500), F4('send_confirmation', 'notifications', 1, 1),
                                  F4('send_confirmation', 'notifications', 1, 2)])
def test_review_counterexample_long_delay_plus_send_fault_is_not_forced(caller, delay, send):
    # No wait action and seven business calls: status checks use up the turns before any send.
    result = label_recipe(R(F2(delay), send), caller)
    assert result['faults'][0]['verdict'] == 'FORCED'
    assert (result['faults'][1]['verdict'], result['faults'][1]['reason_code']) == ('NOT_FORCED', 'N5_OUT_OF_TURNS')
    assert not result['all_forced'] and result['agent_business_calls'] == caller.max_business_calls
    assert 'no wait action' in result['faults'][1]['explanation']


def test_delay_four_still_leaves_one_call_for_the_confirmation(caller):
    result = label_recipe(R(F2(4), F1('send_confirmation', 'notifications')), caller)
    assert result['all_forced'] and result['agent_business_calls'] == 7


def test_f1_delays_are_the_same_behaviour(caller):
    for tool, service in (('update_order', 'orders'), ('send_confirmation', 'notifications')):
        outs = [label_recipe(R(F1(tool, service, 1, delay)), caller) for delay in (1500, 2000, 3000)]
        assert all(o['agent_path'] == outs[0]['agent_path'] and verdicts(o) == verdicts(outs[0]) for o in outs)
        assert any(token.endswith('/timeout') for token in outs[0]['agent_path'])


def test_every_fault_bearing_development_fallback_recipe_is_forced(caller):
    cases = json.loads((AUDIT / 'development.json').read_text())['cases']
    bearing = [case for case in cases if case['fault_spec']['primitives']]
    assert len(bearing) == 5
    for case in bearing:
        result = label_recipe(case['fault_spec'], caller)
        assert result['all_forced'], case['case_id']
        assert result['fixture_id'] == case['fixture_id']


def test_normal_path_and_caller_facts(caller):
    assert normal_path(caller) == {'calls': ['get_order:orders', 'update_order:orders', 'send_confirmation:notifications'],
                                   'business_calls': 3, 'max_business_calls': 7}
    descriptor = caller.descriptor()
    assert descriptor['wait_action'] is False and descriptor['max_business_calls'] == 7
    assert descriptor['adapter_attempts'] == 2 and descriptor['client_timeout_seconds'] == 1.0
    assert any('no wait action' in fact for fact in descriptor['facts'])


# ---------------------------------------------------------------- caller v2: no re-send after UNKNOWN
def test_caller_v2_identity_and_facts_describe_no_resend(caller):
    # Review finding (MEDIUM): caller v1 claimed the Actor re-sends a write after UNKNOWN; stored
    # DeepSeek-V3.1 episodes show it keeps checking status instead. The identity was bumped.
    assert LABELLER_VERSION == 'faultlab-reachability/v2'
    descriptor = caller.descriptor()
    assert descriptor['caller_id'] == 'reference-actor/policy-v0/v2'
    assert descriptor['resends_failed_writes'] is False
    assert descriptor['unknown_status_checks'] == UNKNOWN_STATUS_CHECKS == 3
    facts = ' '.join(descriptor['facts'])
    assert 'does not send a failed write again' in facts and 'at most 3 times (a failed check counts too)' in facts
    assert 'sends a write again only after' not in facts
    assert 'DeepSeek-V3.1' in descriptor['validated_against'] and 'not other models' in descriptor['validated_against']
    assert 'check_reachability_caller.py' in descriptor['validated_against']


@pytest.mark.parametrize('write,service,status', [('update_order', 'orders', 'get_operation_status:orders'),
                                                  ('send_confirmation', 'notifications', 'get_operation_status:notifications')])
@pytest.mark.parametrize('count', [2, 3, 18])
def test_a_write_failing_on_both_attempts_is_never_resent_and_status_is_checked_three_times(caller, write, service, status, count):
    result = label_recipe(R(F4(write, service, 1, count)), caller)
    path = [token.split('#', 1)[0] for token in result['agent_path']]
    assert path.count(f'{write}:{service}') == 2  # the adapter's two attempts, never a re-send
    assert path.count(status) == UNKNOWN_STATUS_CHECKS and path[-UNKNOWN_STATUS_CHECKS:] == [status] * UNKNOWN_STATUS_CHECKS
    assert result['agent_business_calls'] < caller.max_business_calls  # it stops, not out of turns
    if write == 'update_order':
        assert 'send_confirmation:notifications' not in path  # no confirmation without a delivered upgrade
    assert result['agent_outcome'] == {'upgrade': None if write == 'update_order' else 'SUCCEEDED', 'notification': None}


RESEND_DEPENDENT = [  # the review's examples: all-FORCED under caller v1, reached only by a re-send
    R(F4('update_order', 'orders', 1, 2), F1('send_confirmation', 'notifications', 1)),
    R(F4('update_order', 'orders', 1, 2), F2(3, occurrence=3)),
    R(F4('update_order', 'orders', 1, 2), F1('update_order', 'orders', 3)),
    R(F4('update_order', 'orders', 1, 3), F4('send_confirmation', 'notifications', 1, 1)),
    R(F4('send_confirmation', 'notifications', 1, 2), F1('send_confirmation', 'notifications', 3)),
    R(F4('send_confirmation', 'notifications', 1, 2), F4('send_confirmation', 'notifications', 3, 1)),
    R(F4('send_confirmation', 'notifications', 1, 4), F4('send_confirmation', 'notifications', 3, 3)),
]


@pytest.mark.parametrize('recipe', RESEND_DEPENDENT)
def test_faults_reached_only_by_a_resend_are_not_forced_n3(caller, recipe):
    result = label_recipe(recipe, caller)
    assert verdicts(result) == [('FORCED', 'FORCED'), ('NOT_FORCED', 'N3_REPEATED_WRITE')]
    assert not result['all_forced']
    assert 'sends a write again' in result['faults'][1]['explanation']
    assert 'only checks status' in result['faults'][1]['explanation']


@pytest.mark.parametrize('recipe', RESEND_DEPENDENT)
def test_caller_v1_resend_would_have_called_them_forced(caller, recipe, monkeypatch):
    # Control: with caller v1's resolution the same picks were all-FORCED (the reported defect).
    monkeypatch.setattr(reachability, '_resolve', reachability._resolve_with_resend)
    assert label_recipe(recipe, caller)['all_forced']


def test_status_faults_after_a_double_write_failure_forced_only_within_three_checks(caller):
    send = F4('send_confirmation', 'notifications', 1, 2)
    third = label_recipe(R(send, F4('get_operation_status', 'notifications', 3, 1)), caller)
    assert verdicts(third) == [('FORCED', 'FORCED'), ('FORCED', 'FORCED')]
    fourth = label_recipe(R(send, F4('get_operation_status', 'notifications', 4, 1)), caller)
    assert verdicts(fourth) == [('FORCED', 'FORCED'), ('NOT_FORCED', 'N2_UNNEEDED_STATUS_CHECK')]
    assert 'at most 3 times after a write failed' in fourth['faults'][1]['explanation']


def test_failed_status_checks_after_a_double_write_failure_count_toward_the_cap(caller):
    # Stored Actors made a 4th status check after a failed write in only 53-61% of episodes, so a
    # check that itself fails counts too: no model path makes more than 3 checks after the write failed.
    send = F4('send_confirmation', 'notifications', 1, 2)
    result = label_recipe(R(send, F4('get_operation_status', 'notifications', 2, 8)), caller)
    path = [token.split('#', 1)[0] for token in result['agent_path']]
    # Three checks (attempt 1 UNKNOWN, attempts 2-3 failed, attempts 4-5 failed), then it stops;
    # counting only UNKNOWN answers would have polled until the 7-call limit (7 attempts).
    assert path.count('get_operation_status:notifications') == 5
    assert result['agent_business_calls'] == 6 and path[-1] == 'get_operation_status:notifications'
    # An F4 fires when its first attempt fails, so this one is FORCED; its later attempts are not needed.
    assert verdicts(result) == [('FORCED', 'FORCED'), ('FORCED', 'FORCED')]
    first_failed = label_recipe(R(send, F4('get_operation_status', 'notifications', 1, 2)), caller)
    first_path = [token.split('#', 1)[0] for token in first_failed['agent_path']]
    assert first_path.count('get_operation_status:notifications') == 4  # failed check (2 attempts) + 2 UNKNOWN


def test_pending_polling_is_not_capped_by_the_unknown_rule(caller):
    # An accepted upgrade that stays PENDING is polled once per turn until it finishes.
    result = label_recipe(R(F2(4), F1('send_confirmation', 'notifications')), caller)
    path = [token.split('#', 1)[0] for token in result['agent_path']]
    assert path.count('get_operation_status:orders') == 4 and result['all_forced']


def test_deterministic_output(caller):
    recipe = R(F2(3), F4('get_operation_status', 'orders', 3, 1))
    assert label_recipe(recipe, caller) == label_recipe(FaultSpec.model_validate(recipe), caller)


# ---------------------------------------------------------------- scope and isolation
def test_native_agent_and_policy_rules_are_refused_never_mislabelled():
    with pytest.raises(UnsupportedTarget) as native:
        caller_model_for('smolagents', [])
    assert native.value.code == 'NATIVE_AGENT_UNSUPPORTED'
    with pytest.raises(UnsupportedTarget) as rules:
        caller_model_for('reference', [{'hook': 'before_confirmation'}])
    assert rules.value.code == 'POLICY_RULES_UNSUPPORTED'


def test_replay_uses_only_its_temporary_directory_and_leaves_nothing(caller, tmp_path):
    before = set(Path(tempfile.gettempdir()).glob('faultlab-reachability-*'))
    label_recipe(R(F2(3)), caller)
    assert set(Path(tempfile.gettempdir()).glob('faultlab-reachability-*')) == before
    work = tmp_path / 'work'; work.mkdir()
    label_recipe(R(F4('send_confirmation', 'notifications', 1, 2)), caller, work_dir=work)
    assert list(work.iterdir()) == []  # every world file is dropped after its run


def test_the_shared_simulator_module_is_never_patched(caller):
    import asyncio as real_asyncio
    from app.simulator import business
    label_recipe(R(F1('update_order', 'orders')), caller)
    assert business.asyncio is real_asyncio
    private, _ = reachability._private_business()
    assert private is not business and Path(private.__file__) == Path(business.__file__)


def test_never_runs_on_an_event_loop_thread_and_async_form_keeps_the_loop_free(caller):
    async def scenario():
        with pytest.raises(RuntimeError, match='event loop'):
            label_recipe(R(F2(3)), caller)
        ticks = 0; done = False
        async def ticker():
            nonlocal ticks
            while not done:
                ticks += 1; await asyncio.sleep(0.001)
        task = asyncio.create_task(ticker())
        result = await label_recipe_async(R(F2(8), F1('send_confirmation', 'notifications')), caller)
        done = True; await task
        return result, ticks
    result, ticks = asyncio.run(scenario())
    assert not result['all_forced'] and ticks > 1


# ---------------------------------------------------------------- soundness of IMPOSSIBLE
def _grid():
    out = [F1('update_order', 'orders', occ) for occ in (1, 2)] + [F1('send_confirmation', 'notifications', 1)]
    out += [F2(3, occurrence=occ) for occ in (1, 2)] + [F2(2, ok=False, occurrence=1)]
    out += [P('F3', 'get_order', 'orders', 1, versions_back=1)]
    for tool, service in (('get_order', 'orders'), ('update_order', 'orders'), ('get_operation_status', 'orders'),
                          ('get_operation_status', 'notifications'), ('send_confirmation', 'notifications')):
        out += [F4(tool, service, occ, count) for occ in (1, 2) for count in (1, 2)]
    return out


ACTIONS = [('get_order', 'orders'), ('update_order', 'orders'), ('get_operation_status', 'orders'),
           ('get_operation_status', 'notifications'), ('send_confirmation', 'notifications')]


def test_rule_impossible_faults_never_fire_under_any_caller(caller):
    grid = _grid()
    recipes = [[p] for p in grid] + [[a, b] for a, b in itertools.product(grid, grid)]
    recipes = [r for r in recipes if any(fixed_rules(r))]
    assert len(recipes) > 100
    rng = random.Random(20260928)

    async def check(store, client, primitives):
        spec = R(*primitives); fixture = reachability.fixture_for(spec)
        scripts = [lambda r: reachability.agent_path(r, caller.http_attempts),
                   lambda r: reachability.resend_path(r, caller.http_attempts),
                   lambda r: reachability.diligent_path(r, caller.http_attempts),
                   lambda r: reachability.rule_breaking_path(r, caller.http_attempts, early=False),
                   lambda r: reachability.rule_breaking_path(r, caller.http_attempts, early=True)]
        for p in primitives:
            scripts += [lambda r, p=p: reachability.targeted_path(r, p, after_write=False),
                        lambda r, p=p: reachability.targeted_path(r, p, after_write=True)]
        for _ in range(4):
            sequence = [rng.choice(ACTIONS) for _ in range(rng.randint(1, 14))]
            async def fuzz(r, sequence=sequence):
                for tool, service in sequence: await r.call(tool, service)
            scripts.append(fuzz)
        rules = fixed_rules(primitives)
        for script in scripts:
            out = await reachability._execute(store, client, spec, fixture, caller, script)
            for index, rule in enumerate(rules):
                assert not (rule and out['fired'][index]), (primitives, index, rule, out['sequence'])

    async def main(directory):
        import httpx
        from app.simulator.storage import WorldStore
        store = WorldStore(directory)
        transport = httpx.ASGITransport(app=reachability._simulator_app(store))
        async with httpx.AsyncClient(transport=transport, base_url='http://reachability.invalid') as client:
            for primitives in recipes:
                await check(store, client, primitives)

    with tempfile.TemporaryDirectory() as directory:
        asyncio.run(main(Path(directory)))


def test_executed_explanations_distinguish_agent_skips_from_labelling_problems():
    recipe = R(F4('send_confirmation', 'notifications', 1, 2))
    skipped = reachability.explain_executed(recipe, fired=[False], reasons=['target_not_reached'],
        attempts_by_target={'get_operation_status:notifications': 5}, lifecycle='COMPLETED', predicted=['FORCED'])
    assert skipped[0]['reason_code'] == 'AGENT_SKIPPED_CALL' and 'left that path' in skipped[0]['explanation']
    contradicted = reachability.explain_executed(recipe, fired=[False], reasons=['pre_effect_failure'],
        attempts_by_target={'send_confirmation:notifications': 2}, lifecycle='COMPLETED', predicted=['FORCED'])
    assert contradicted[0]['reason_code'] == 'REACHED_BUT_NOT_TRIGGERED' and 'FaultLab labelling problem' in contradicted[0]['explanation']
    ended = reachability.explain_executed(recipe, fired=[False], reasons=['target_not_reached'],
        attempts_by_target={}, lifecycle='LAB_ERROR', predicted=['FORCED'])
    assert ended[0]['reason_code'] == 'EPISODE_ENDED_EARLY'
    fired = reachability.explain_executed(recipe, fired=[True], reasons=[None],
        attempts_by_target={'send_confirmation:notifications': 3}, lifecycle='COMPLETED', predicted=['FORCED'])
    assert fired[0]['reason_code'] == 'FIRED'
