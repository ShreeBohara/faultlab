"""Offline checks of the Phase 21 lapse probe. No provider call, no .env read, no store write."""
import asyncio
from collections import Counter
import dataclasses
import hashlib
import importlib.util
import json
import os
import pathlib
import random
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('lapse_probe', ROOT / 'scripts/experiments/lapse_probe.py')
probe = importlib.util.module_from_spec(SPEC)
sys.modules['lapse_probe'] = probe
SPEC.loader.exec_module(probe)

from app.contracts.models import canonical_json, content_hash  # noqa: E402
from app.providers.runtime import RuntimeProvider, RuntimeProviderError  # noqa: E402

STORE = ROOT / 'artifacts/lab.sqlite3'
needs_store = pytest.mark.skipif(not STORE.exists(), reason='the local lab store is not present')
SEND = '{"kind":"tool","tool":"send_confirmation","arguments":{}}'


# ---------------------------------------------------------------- the real store (read-only)

def _connection():
    return sqlite3.connect(STORE.resolve().as_uri() + '?mode=ro', uri=True)


def _v4_completion_episodes(connection):
    rows = []
    for episode_id, payload in connection.execute("select id,payload from records where kind='episodes'"):
        episode = json.loads(payload)
        if (episode.get('split') == 'development' and episode.get('experiment_purpose') == 'completion_study'
                and probe.before_cutoff(episode.get('started_at'))):
            rows.append(episode_id)
    v4 = []
    for episode_id in sorted(rows):
        first = connection.execute("select payload from events where episode_id=? and "
                                   "json_extract(payload,'$.type')='actor_output' order by seq limit 1",
                                   (episode_id,)).fetchone()
        if first and json.loads(first[0])['payload'].get('actor_context_protocol') == probe.ACTOR_CONTEXT_PROTOCOL_V4:
            v4.append(episode_id)
    return v4


@pytest.fixture(scope='module')
def store_sample():
    if not STORE.exists():
        pytest.skip('the local lab store is not present')
    connection = _connection()
    episodes = _v4_completion_episodes(connection)
    ranked = sorted(episodes, key=lambda e: hashlib.sha256(f'test-sample:{e}'.encode()).hexdigest())
    invalid, eligible = [], set(episodes)
    for episode_id, payload in connection.execute(
            "select episode_id,payload from events where json_extract(payload,'$.type')='actor_output' order by episode_id,seq"):
        body = json.loads(payload)['payload']
        if (episode_id in eligible and body.get('actor_context_protocol') == probe.ACTOR_CONTEXT_PROTOCOL_V4
                and probe.parse_action(body.get('raw')) is None):
            invalid.append(episode_id)
    cases = {}
    for (payload,) in connection.execute("select payload from records where kind='completion_studies'"):
        for row in json.loads(payload).get('trial_rows') or []:
            cases[row['trial']['episode_id']] = row['case_id']
    rejection = [e for e in ranked if cases.get(e) == probe.TERMINAL_REJECTION_CASE][:3]
    yield SimpleNamespace(connection=connection, sample=ranked[:30], invalid=sorted(set(invalid))[:10],
                          rejection=rejection, cases=cases)
    connection.close()


def _rebuild(connection, episode_id, **kwargs):
    return probe.rebuild_episode(probe.load_events(connection, episode_id),
                                 probe.load_intent(connection, episode_id), **kwargs)


def test_rebuilt_prompts_match_the_stored_hashes_on_a_sample(store_sample):
    turns = [t for e in store_sample.sample for t in _rebuild(store_sample.connection, e)]
    assert len(turns) > 100
    assert [t['failure'] for t in turns if not t['verified']] == []


def test_invalid_json_corrections_are_replayed_exactly(store_sample):
    assert store_sample.invalid, 'expected at least one v4 episode with an answer that failed output_schema'
    followed = 0
    for episode_id in store_sample.invalid:
        turns = _rebuild(store_sample.connection, episode_id)
        bad = [t for t in turns if t['historical']['detail'] == 'invalid_action']
        assert bad and all(t['verified'] for t in turns)
        followed += any(t['actor_turn'] > bad[0]['actor_turn'] for t in turns)
    assert followed, 'a correction must be followed by a verified turn to prove it was replayed'


def test_a_tampered_observation_fails_verification_from_that_turn_on(store_sample):
    episode_id = store_sample.sample[0]
    events = probe.load_events(store_sample.connection, episode_id)
    intent = probe.load_intent(store_sample.connection, episode_id)
    delivered = [i for i, e in enumerate(events) if e['type'] == 'observation_delivered']
    target = delivered[len(delivered) // 2]
    tampered = json.loads(json.dumps(events))
    tampered[target]['payload']['observation']['delivered_tick'] += 1
    clean = probe.rebuild_episode(events, intent)
    broken = probe.rebuild_episode(tampered, intent)
    boundary = sum(1 for e in events[:target] if e['type'] == 'actor_output')
    assert all(t['verified'] for t in clean)
    assert all(t['verified'] for t in broken[:boundary])
    assert broken[boundary]['failure'] == 'hash_mismatch'
    assert all(t['failure'] == 'after_unverified_turn' for t in broken[boundary + 1:])


def test_a_wrong_intent_or_a_wrong_stored_hash_is_refused(store_sample):
    episode_id = store_sample.sample[1]
    events = probe.load_events(store_sample.connection, episode_id)
    intent = probe.load_intent(store_sample.connection, episode_id)
    assert not probe.rebuild_episode(events, {**intent, 'task_id': 'task-' + '0' * 32})[0]['verified']
    assert probe.rebuild_episode(events, None)[0]['failure'] == 'intent_missing'
    forged = json.loads(json.dumps(events))
    first = next(e for e in forged if e['type'] == 'actor_output')
    first['payload']['request_hash'] = '0' * 64
    assert not probe.rebuild_episode(forged, intent)[0]['verified']


def test_v5_and_placebo_never_touch_a_terminal_rejection_turn(store_sample):
    assert store_sample.rejection
    for episode_id in store_sample.rejection:
        for turn in _rebuild(store_sample.connection, episode_id, keep=True):
            assert turn['verified'] and not turn['window'] and not turn['treated']
            control = probe.arm_messages(turn['history'], turn['user'], 'C', turn['window'])
            for arm in ('T', 'P'):
                assert probe.arm_messages(turn['history'], turn['user'], arm, turn['window']) == control


def test_the_correction_messages_are_the_actors_own_text():
    source = (ROOT / 'backend/app/agents/actor.py').read_text()
    for text in (probe.CORRECTION_INSTRUCTION, probe.FINAL_TOOL_MESSAGE, probe.BUDGET_MESSAGE):
        assert f"'{text}'" in source


def test_an_actor_request_keeps_no_earlier_turn_message():
    # The fidelity premise the protocol states: each request is system + task + the current turn,
    # plus only correction, refusal, blocked or budget messages. Pinned to actor.py's source.
    source = (ROOT / 'backend/app/agents/actor.py').read_text()
    assert "call_messages=messages+[{'role':'user','content':canonical_json(user)}]" in source
    assert 'messages.append(call_messages' not in source and 'messages=call_messages' not in source


def test_survey_excludes_an_episode_started_at_or_after_the_cutoff(store_sample):
    episode_id = store_sample.sample[0]
    record = json.loads(store_sample.connection.execute(
        "select payload from records where kind='episodes' and id=?", (episode_id,)).fetchone()[0])
    for started, kept in (('2026-09-23T15:59:59Z', 1), ('2026-09-23T16:00:00Z', 0), ('2026-09-24T09:00:00Z', 0)):
        summaries, verification, _ = probe.survey(store_sample.connection, {episode_id: {**record, 'started_at': started}},
                                                  store_sample.cases, {})
        assert len(summaries) == kept and verification['episodes'] == kept


def _lapse_units(connection, episode_id):
    turns = _rebuild(connection, episode_id)
    turn3, turn4 = (next(t for t in turns if t['actor_turn'] == n) for n in (3, 4))
    summary = {'episode_id': episode_id, 'case': 'x', 'arm': 'B0'}
    return {'lapse': [(summary, turn3, turn4)], 'nonlapse': [], 'report': [], 'determinism': []}


@needs_store
def test_build_requests_refuses_a_prompt_that_no_longer_verifies_or_whose_control_differs(real_plan, monkeypatch):
    plan, _ = real_plan
    episode_id = next(r['episode_id'] for r in plan['requests'] if r['population'] == 'turn4')
    connection = _connection()
    try:
        populations = _lapse_units(connection, episode_id)
        requests, _, _ = probe.build_requests(connection, populations)
        assert {r['arm'] for r in requests} == set(probe.ARMS)
        original = probe.rebuild_episode

        def unverified(*args, **kwargs):
            return [{**turn, 'verified': False} for turn in original(*args, **kwargs)]
        monkeypatch.setattr(probe, 'rebuild_episode', unverified)
        with pytest.raises(probe.PlanningError, match='failed verification on rebuild'):
            probe.build_requests(connection, populations)
        monkeypatch.setattr(probe, 'rebuild_episode', original)
        messages = probe.arm_messages

        def altered(history, user, arm, window):
            return messages(history, {**user, 'remaining_actor_calls': -1} if arm == 'C' else user, arm, window)
        monkeypatch.setattr(probe, 'arm_messages', altered)
        with pytest.raises(probe.PlanningError, match='not the stored request'):
            probe.build_requests(connection, populations)
    finally:
        connection.close()


# ---------------------------------------------------------------- the full dry plan on the real store

@pytest.fixture(scope='module')
def real_plan():
    if not STORE.exists():
        pytest.skip('the local lab store is not present')
    import app.config
    import app.providers.runtime
    original = app.config.dotenv_values

    def guarded(dotenv_path=None, **kwargs):
        assert pathlib.Path(dotenv_path) != app.config.ROOT_ENV_PATH, 'the dry plan must never read the root .env'
        return original(dotenv_path=dotenv_path, **kwargs)

    class NoProvider:
        def __init__(self, *args, **kwargs):
            raise AssertionError('the dry plan must never build a provider')

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(app.config, 'dotenv_values', guarded)
        patch.setattr(app.providers.runtime, 'RuntimeProvider', NoProvider)
        patch.setattr(probe, 'openai_client_factory', NoProvider)
        plan, prompts = probe.build_plan()
    return plan, prompts


@needs_store
def test_dry_run_verifies_every_v4_development_turn(real_plan):
    plan, _ = real_plan
    verification = plan['verification']
    assert verification['turns'] >= 12661
    assert verification['failed'] == 0 and verification['pass_rate'] == 1.0


@needs_store
def test_precheck_changes_only_treated_turns_never_a_report_required_or_terminal_rejection_turn(real_plan):
    precheck = real_plan[0]['precheck']
    assert precheck['passed']
    assert precheck['turns_changed_by_T'] == precheck['turns_changed_by_P'] == precheck['treated_turns'] > 0
    assert precheck['treated_turns'] + precheck['window_report_required_turns'] == precheck['window_turns']
    assert precheck['window_report_required_turns'] > 0 and precheck['window_report_required_turns_changed'] == 0
    assert precheck['window_turns'] == precheck['independent_window_turns']
    assert precheck['window_rule_disagreements'] == precheck['structural_violations'] == 0
    assert precheck['terminal_rejection_turns_checked'] > 0 and precheck['terminal_rejection_turns_changed'] == 0
    assert probe.TERMINAL_REJECTION_CASE not in precheck['changed_turns_by_case']


@needs_store
def test_declared_populations_and_exact_request_count(real_plan):
    plan, prompts = real_plan
    populations = plan['populations']
    assert populations['lapse_count'] == populations['turn4_prompts'] == populations['turn3_prompts'] == 65
    assert populations['nonlapse_prompts'] == 100 and populations['report_prompts'] == 65
    assert populations['report_prompts_treated'] == 14 and populations['report_prompts_c_only'] == 51
    assert populations['report_prompts_c_only_arms_identical'] == 51
    assert populations['determinism_contexts'] == {'PENDING': 28, 'UNKNOWN': 28}
    requests = plan['requests']
    assert len(requests) == plan['counts']['total_requests'] == (
        65 * 3 * 2 + 100 * 3 + 65 + 14 * 2 + 56 * probe.DETERMINISM_REPEATS) == 1063
    assert plan['cost']['planned_upper_bound'] == round(len(requests) * probe.PER_REQUEST_DOLLAR_BOUND, 6) <= 25
    assert {r['actor_turn'] for r in requests if r['population'] == 'turn4'} == {4}
    assert {r['actor_turn'] for r in requests if r['population'] == 'turn3'} == {3}
    assert all(r['window'] for r in requests if r['population'] != 'determinism')
    assert all(r['treated'] for r in requests if r['arm'] != 'C')
    assert all(r['treated'] for r in requests if r['population'] in ('turn4', 'turn3', 'nonlapse'))
    assert len({r['request_id'] for r in requests}) == len(requests)
    assert all(r['request_hash'] in prompts for r in requests)
    assert plan['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    assert plan['actor_model_settings']['temperature'] == 0
    assert [r['population'] for r in requests] == sorted(
        (r['population'] for r in requests), key=probe.POPULATION_ORDER.index)


@needs_store
def test_every_control_prompt_is_the_stored_request(real_plan, store_sample):
    plan, prompts = real_plan
    controls = [r for r in plan['requests'] if r['arm'] == 'C' and r['repeat'] == 0]
    for request in random.Random(21).sample(controls, 40):
        stored = next(json.loads(p)['payload'] for (p,) in store_sample.connection.execute(
            "select payload from events where episode_id=? and json_extract(payload,'$.type')='actor_output' "
            "and json_extract(payload,'$.payload.actor_turn')=?", (request['episode_id'], request['actor_turn'])))
        prompt = prompts[request['request_hash']]
        assert content_hash(prompt['messages']) == stored['messages_hash']
        assert content_hash({'messages': prompt['messages'], 'response_format': prompt['response_format']}) == stored['request_hash']
        assert prompt['response_contract'] == stored['response_contract']


@needs_store
def test_treated_and_placebo_prompts_differ_from_control_by_one_declared_field(real_plan):
    plan, prompts = real_plan
    by_prompt = {}
    for request in plan['requests']:
        if request['population'] != 'determinism':
            by_prompt.setdefault(request['prompt_id'], {})[request['arm']] = prompts[request['request_hash']]
    assert len(by_prompt) == 65 * 3 + 100
    treated = [arms for arms in by_prompt.values() if 'T' in arms]
    assert len(treated) == 65 * 2 + 100 + 14
    for arms in treated:
        control = arms['C']['messages']
        assert probe.added_keys(arms['T']['messages'], control) == [probe.V5_FIELD]
        assert probe.added_keys(arms['P']['messages'], control) == [probe.PLACEBO_FIELD]
        assert json.loads(arms['T']['messages'][-1]['content'])[probe.V5_FIELD] == probe.V5_VALUE
        assert arms['T']['response_format'] == arms['P']['response_format'] == arms['C']['response_format']


@needs_store
def test_report_required_report_prompts_are_sent_under_control_only(real_plan):
    plan, _ = real_plan
    report = [r for r in plan['requests'] if r['population'] == 'report']
    final = [r for r in report if r['final_report_required']]
    assert len({r['prompt_id'] for r in final}) == 51 and {r['arm'] for r in final} == {'C'}
    assert all(r['response_contract'] == 'actor_final_report' for r in final)
    voluntary = [r for r in report if not r['final_report_required']]
    assert sorted(Counter(r['arm'] for r in voluntary).items()) == [('C', 14), ('P', 14), ('T', 14)]
    assert {r['historical']['notification_outcome'] for r in report} == {'UNKNOWN'}
    assert all(r['historical']['report_fields'] for r in report)


# ---------------------------------------------------------------- arm construction (synthetic)

USER = {'observations': [{'evidence_id': 'obs-1'}], 'final_report_required': False, 'remaining_actor_calls': 5}
FINAL_USER = {**USER, 'final_report_required': True, 'remaining_actor_calls': 1}
HISTORY = [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}]


def test_out_of_window_or_on_a_report_required_turn_every_arm_is_the_control():
    control = probe.arm_messages(HISTORY, USER, 'C', False)
    assert probe.arm_messages(HISTORY, USER, 'T', False) == control == probe.arm_messages(HISTORY, USER, 'P', False)
    assert probe.arm_messages(HISTORY, USER, 'C', True) == control
    final = probe.arm_messages(HISTORY, FINAL_USER, 'C', True)
    assert probe.arm_messages(HISTORY, FINAL_USER, 'T', True) == final == probe.arm_messages(HISTORY, FINAL_USER, 'P', True)
    with pytest.raises(probe.PlanningError):
        probe.arm_payload(USER, 'X', False)


def test_in_window_each_arm_adds_exactly_its_own_field():
    control = probe.arm_messages(HISTORY, USER, 'C', True)
    treated = probe.arm_messages(HISTORY, USER, 'T', True)
    placebo = probe.arm_messages(HISTORY, USER, 'P', True)
    assert probe.added_keys(treated, control) == [probe.V5_FIELD]
    assert probe.added_keys(placebo, control) == [probe.PLACEBO_FIELD]
    assert USER == {'observations': [{'evidence_id': 'obs-1'}], 'final_report_required': False, 'remaining_actor_calls': 5}
    with pytest.raises(probe.PlanningError):
        probe.arm_payload({**USER, probe.V5_FIELD: 1}, 'T', True)


def test_placebo_has_the_same_shape_and_position_as_v5():
    v5, placebo = probe.V5_VALUE, probe.PLACEBO_VALUE
    assert [type(v) for v in v5.values()] == [type(v) for v in placebo.values()]
    assert abs(len(v5['note']) - len(placebo['note'])) <= 5
    others = ['final_report_required', 'observations', 'remaining_actor_calls']
    assert sorted(others + [probe.V5_FIELD])[0] == probe.V5_FIELD
    assert sorted(others + [probe.PLACEBO_FIELD])[0] == probe.PLACEBO_FIELD
    assert 'confirm' not in placebo['note'].lower() and 'send' not in placebo['note'].lower()


def test_canonical_position_of_the_added_field():
    payload = probe.arm_payload(USER, 'T', True)
    assert canonical_json(payload).startswith('{"' + probe.V5_FIELD + '":')


# ---------------------------------------------------------------- population selection (synthetic)

def _turn(n, *, window, cls='get_operation_status', detail='notifications', word=None, final=False,
          submitted=False, verified=True, new=(), signature=None):
    return {'actor_turn': n, 'verified': verified, 'failure': None if verified else 'hash_mismatch',
            'window': window, 'treated': window and not final, 'final_report_required': final,
            'historical': {'class': cls, 'detail': detail, 'notification_outcome': word},
            'report_submitted_after': submitted, 'new_observations': list(new),
            'observation_signature': signature or [['get_order', 'ok', None, None]] * n, 'observation_count': n}


UNKNOWN_REPLY = [{'tool': 'get_operation_status', 'transport': 'ok', 'status': 'UNKNOWN', 'error_code': None,
                  'operation': 'notifications'}]


def _episode(episode_id, turns, *, sent=False, case='healthy', arm='B0', lifecycle='COMPLETED',
             purpose='completion_study', triggered=True):
    return {'episode_id': episode_id, 'case': case, 'arm': arm, 'purpose': purpose, 'lifecycle': lifecycle,
            'fault_triggered': triggered, 'ever_sent': sent, 'turns': turns}


def _lapse(episode_id, **kwargs):
    # A poll that is later followed by a send closes the window before the report.
    return _episode(episode_id, [_turn(1, window=False, cls='other', detail='get_order'),
                                 _turn(2, window=False, cls='other', detail='update_order'),
                                 _turn(3, window=True), _turn(4, window=True, new=UNKNOWN_REPLY),
                                 _turn(5, window=not kwargs.get('sent'), cls='report', word='UNKNOWN', final=True,
                                       submitted=True)],
                    **kwargs)


def _nonlapse(episode_id, **kwargs):
    return _episode(episode_id, [_turn(1, window=False, cls='other', detail='update_order'),
                                 _turn(2, window=True, cls='send_confirmation', detail=None),
                                 _turn(3, window=False, cls='report', word=kwargs.pop('word', 'SUCCEEDED'),
                                       submitted=True)], sent=True, **kwargs)


def _synthetic():
    rows = [_lapse(f'episode-l{i:02d}') for i in range(6)]
    rows += [_nonlapse(f'episode-n{i:03d}') for i in range(150)]
    rows += [_lapse('episode-sent', sent=True), _lapse('episode-lab', lifecycle='LAB_ERROR'),
             _lapse('episode-context', purpose='context_study'), _nonlapse('episode-pending', word='PENDING')]
    return rows


def _ids(populations):
    return {'lapse': [s['episode_id'] for s, _, _ in populations['lapse']],
            'nonlapse': [s['episode_id'] for s, _ in populations['nonlapse']],
            'report': [(s['episode_id'], t['actor_turn']) for s, t in populations['report']],
            'determinism': [(g, s['episode_id']) for g, s, _, _ in populations['determinism']]}


def test_population_selection_is_deterministic_and_order_independent():
    rows = _synthetic()
    first = _ids(probe.select_populations(rows))
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    assert _ids(probe.select_populations(shuffled)) == first == _ids(probe.select_populations(rows))
    assert first['lapse'] == [f'episode-l{i:02d}' for i in range(6)]
    assert len(first['nonlapse']) == probe.NONLAPSE_N
    assert first['report'] == [(f'episode-l{i:02d}', 5) for i in range(6)]


def test_population_rules_exclude_the_declared_cases():
    populations = probe.select_populations(_synthetic())
    ids = _ids(populations)
    for excluded in ('episode-sent', 'episode-lab', 'episode-context'):
        assert excluded not in ids['lapse']
    assert populations['excluded']['lapse_poll_then_sent'] == 1
    unverified = _lapse('episode-bad')
    unverified['turns'][3]['verified'] = False
    no_reply = _lapse('episode-noreply')
    no_reply['turns'][3]['new_observations'] = []
    selected = probe.select_populations([unverified, no_reply])
    assert selected['lapse'] == [] and selected['excluded'] == {'lapse_unverified': 1, 'lapse_without_unknown_reply': 1}


def test_nonlapse_sample_follows_the_seeded_rank(monkeypatch):
    rows = _synthetic()
    expected = sorted((r['episode_id'] for r in rows if r['episode_id'].startswith('episode-n')
                       or r['episode_id'] == 'episode-pending'),
                      key=lambda e: probe.rank('nonlapse', e))[:probe.NONLAPSE_N]
    assert _ids(probe.select_populations(rows))['nonlapse'] == expected
    monkeypatch.setattr(probe, 'SAMPLE_SEED', 'another-seed')
    assert _ids(probe.select_populations(rows))['nonlapse'] != expected


def test_determinism_matching_ladder_without_reuse():
    signature = [['send_confirmation', 'timeout', None, None]]
    other = [['get_order', 'ok', None, None]]

    def context(episode_id, word, sig, case='notification-2', final=True):
        return _episode(episode_id, [_turn(len(sig), window=False, cls='report', word=word, final=final,
                                           submitted=True, signature=sig)], sent=True, case=case)

    rows = [context('episode-p1', 'PENDING', signature), context('episode-p2', 'PENDING', signature),
            context('episode-u1', 'UNKNOWN', signature), context('episode-u2', 'UNKNOWN', other),
            context('episode-u3', 'UNKNOWN', signature, case='notification-3'),
            context('episode-p3', 'PENDING', signature, case='notification-18')]
    chosen, levels = probe.match_determinism(
        [(r, r['turns'][0]) for r in rows])
    pairs = [(g, s['episode_id'], m) for g, s, _, m in chosen]
    assert pairs == [('PENDING', 'episode-p1', None), ('UNKNOWN', 'episode-u1', 'episode-p1'),
                     ('PENDING', 'episode-p2', None), ('UNKNOWN', 'episode-u2', 'episode-p2'),
                     ('PENDING', 'episode-p3', None)]
    assert levels == {'observation_count': 1, 'signature': 1, 'unmatched': 1}


# ---------------------------------------------------------------- statistics and read-outs

def test_fisher_one_sided_exact_values():
    assert probe.fisher_greater(3, 4, 1, 4) == pytest.approx(17 / 70)
    assert probe.fisher_greater(4, 4, 0, 4) == pytest.approx(1 / 70)
    assert probe.fisher_greater(0, 5, 3, 5) == pytest.approx(1.0)
    assert probe.fisher_greater(52, 65, 19, 65) < 1e-8
    with pytest.raises(ValueError):
        probe.fisher_greater(5, 4, 0, 4)


def test_mcnemar_exact_one_sided_values():
    assert probe.mcnemar_greater(0, 0) == 1.0
    assert probe.mcnemar_greater(5, 0) == pytest.approx(1 / 32)
    assert probe.mcnemar_greater(3, 1) == pytest.approx(5 / 16)
    assert probe.mcnemar_greater(1, 3) == pytest.approx(15 / 16)
    with pytest.raises(ValueError):
        probe.mcnemar_greater(-1, 2)


def test_wilson_matches_the_intervals_quoted_in_the_project():
    assert probe.wilson(0, 13)[0] == 0 and probe.wilson(0, 13)[1] == pytest.approx(0.228, abs=5e-4)
    low, high = probe.wilson(5, 13)
    assert low == pytest.approx(0.177, abs=5e-4) and high == pytest.approx(0.645, abs=5e-4)
    assert probe.wilson(0, 0) == [None, None]


def _requests(population, prompts, arms=probe.ARMS, repeats=1, final=False, **extra):
    rows = []
    for index in range(prompts):
        for repeat in range(repeats):
            for arm in arms:
                rows.append({'request_id': f'{population}-{index}-{arm}-{repeat}', 'population': population,
                             'prompt_id': f'{population}:{index}', 'arm': arm, 'repeat': repeat,
                             'final_report_required': final(index) if callable(final) else final,
                             'historical': {'class': 'get_operation_status', 'detail': 'notifications',
                                            'notification_outcome': extra.get('word'), 'raw_sha256': 'h',
                                            'report_fields': extra.get('report_fields')},
                             'group': extra.get('group')})
    return rows


def _result(request, cls, *, detail=None, word=None, status='ok', raw=None, report=None):
    return {'request_id': request['request_id'], 'status': status, 'class': cls, 'detail': detail,
            'notification_outcome': word, 'raw': raw if raw is not None else f'{cls}:{word}',
            'matches_historical_raw': False, 'report': report}


def _primary(t_sends, p_sends, c_sends=0, n=65, missing=0, missing_arm='T'):
    requests = _requests('turn4', n)
    results = []
    counts = {'C': c_sends, 'T': t_sends, 'P': p_sends}
    seen = {'C': 0, 'T': 0, 'P': 0}
    for request in requests:
        arm = request['arm']
        if arm == missing_arm and missing and int(request['prompt_id'].split(':')[1]) >= n - missing:
            continue
        cls = 'send_confirmation' if seen[arm] < counts[arm] else 'get_operation_status'
        seen[arm] += 1
        results.append(_result(request, cls, detail=None if cls == 'send_confirmation' else 'notifications'))
    return probe.compute_readouts(requests, results)['primary']


def test_primary_passes_only_when_every_condition_holds():
    assert _primary(52, 19)['status'] == 'PASS'                  # 0.8 exactly, T-P = 33/65
    assert _primary(51, 5)['status'] == 'FAIL'                   # T below 0.8
    assert _primary(52, 20)['status'] == 'FAIL'                  # T-P = 32/65 < 0.5
    assert _primary(65, 32)['status'] == 'PASS'
    assert _primary(60, 10, missing=5)['status'] == 'INCOMPLETE'  # T received 60 of 65 < 95%
    small = probe.primary_readout([(r, _result(r, 'send_confirmation' if r['arm'] == 'T' else 'report'))
                                   for r in _requests('turn4', 4)])
    assert small['status'] == 'FAIL' and small['fisher_one_sided_p_unpaired_implied'] == pytest.approx(1 / 70)


def test_primary_also_requires_t_minus_c_at_least_half():
    # Review finding: C 45/65, T 52/65, P 10/65 passed T-P while T-C was only 0.108.
    failed = _primary(52, 10, c_sends=45)
    assert failed['status'] == 'FAIL' and failed['conditions']['observed']['t_minus_c_at_least_0.5'] is False
    assert _primary(52, 10, c_sends=19)['status'] == 'PASS'
    assert _primary(52, 10, c_sends=20)['status'] == 'FAIL'


def test_primary_counts_missing_responses_against_v5():
    # 50 of 62 received is 0.806 observed, but 50 of 65 planned is 0.769: FAIL.
    held = _primary(50, 5, missing=3)
    assert held['received']['T'] == 62 and held['conditions']['observed']['t_at_least_0.8'] is True
    assert held['conditions']['missing_counted_against_v5']['t_at_least_0.8'] is False
    assert held['status'] == 'FAIL'
    # Missing P responses count as sends: P 17 of 62 received + 3 missing = 20 of 65 -> T-P 32/65 < 0.5.
    assert _primary(52, 17, missing=3, missing_arm='P')['status'] == 'FAIL'
    assert _primary(52, 16, missing=3, missing_arm='P')['status'] == 'PASS'


def test_primary_reports_a_paired_mcnemar_figure():
    readout = _primary(52, 19)
    paired = readout['paired_t_vs_p']
    assert paired['pairs'] == 65 and paired['t_sends_p_not'] - paired['p_sends_t_not'] == 52 - 19
    assert paired['mcnemar_exact_one_sided_p_descriptive'] < 1e-6


def _r3(t_classes, p_classes=None, n=100, drop=0, control=None):
    requests = _requests('nonlapse', n)
    results = []
    for request in requests:
        index = int(request['prompt_id'].split(':')[1])
        if request['arm'] == 'C':
            cls, detail = (control or {}).get(index, ('send_confirmation', None))
            results.append(_result(request, cls, detail=detail))
        elif index >= drop:
            chosen = (t_classes if request['arm'] == 'T' else (p_classes or {})).get(index, ('send_confirmation', None))
            cls, detail = chosen if isinstance(chosen, tuple) else (chosen, None)
            results.append(_result(request, cls, detail=detail))
    return probe.compute_readouts(requests, results)['R3']


ORDERS = ('get_operation_status', 'orders')
NOTIFICATIONS = ('get_operation_status', 'notifications')


def test_r3_threshold_and_reports_decided_by_t_alone():
    assert _r3({i: ORDERS for i in range(4)})['status'] == 'PASS'     # 96%
    assert _r3({i: ORDERS for i in range(5)})['status'] == 'PASS'     # 95%
    assert _r3({i: ORDERS for i in range(6)})['status'] == 'FAIL'     # 94%
    assert _r3({0: 'report'})['status'] == 'FAIL'                     # one T report
    placebo_moved = _r3({}, {i: 'other' for i in range(10)})
    assert placebo_moved['status'] == 'PASS' and placebo_moved['P']['passes'] is False
    assert placebo_moved['P']['decides'] is False
    assert _r3({}, {0: 'report'})['status'] == 'PASS'                 # a P report is reported, not decisive
    assert _r3({}, drop=10)['status'] == 'INCOMPLETE'


def test_r3_does_not_count_a_move_into_send_as_a_mismatch():
    # Review case 6: C repeats 7 order polls, T sends on all 7 and changes nothing else.
    control = {i: ORDERS for i in range(7)}
    readout = _r3({}, control=control)
    assert readout['status'] == 'PASS'
    assert readout['T']['into_send'] == 7 and readout['T']['mismatches'] == 0
    assert readout['T']['transitions_from_C']['get_operation_status:orders->send_confirmation:None'] == 7


def test_r3_counts_a_move_from_order_polls_to_the_lapse():
    # Review case 7: T turns the 7 order polls into notification polls (it induces the lapse).
    control = {i: ORDERS for i in range(7)}
    readout = _r3({i: NOTIFICATIONS for i in range(7)}, control=control)
    assert readout['status'] == 'FAIL' and readout['T']['mismatches'] == 7
    # A move away from send is a mismatch too.
    assert _r3({i: ORDERS for i in range(6)})['T']['mismatches'] == 6


def _r4(t_words=None, *, n=65, final=lambda i: i < 51, c_words=None, drop_c=0, t_classes=None, drop_t=()):
    requests = _requests('report', n, final=final, word='UNKNOWN',
                         report_fields={'overall': 'SAFE_UNRESOLVED', 'upgrade_outcome': 'SUCCEEDED',
                                        'next_action': {'kind': 'NONE'}})
    # Report-required prompts carry C only, as the plan builds them.
    requests = [r for r in requests if r['arm'] == 'C' or not r['final_report_required']]
    results = []
    for request in requests:
        index = int(request['prompt_id'].split(':')[1])
        if request['arm'] == 'C' and index < drop_c:
            continue
        if request['arm'] == 'T' and index in drop_t:
            continue
        if request['arm'] == 'T' and index in (t_classes or {}):
            results.append(_result(request, t_classes[index]))
            continue
        words = (t_words if request['arm'] == 'T' else c_words if request['arm'] == 'C' else None) or {}
        word = words.get(index, 'UNKNOWN')
        results.append(_result(request, 'report', word=word,
                               report={'overall': 'SAFE_UNRESOLVED', 'upgrade_outcome': 'SUCCEEDED',
                                       'notification_outcome': word, 'next_action': {'kind': 'NONE'},
                                       'evidence_ids': []}))
    return probe.compute_readouts(requests, results)['R4']


def test_r4_judges_t_against_the_historical_word_with_the_one_allowed_change():
    passed = _r4({i: 'NOT_STARTED' for i in range(51, 60)}, t_classes={60: 'send_confirmation', 61: 'other'})
    assert passed['status'] == 'PASS' and passed['T']['allowed_pair_used'] == 9
    assert passed['T']['changes_from_historical'] == {'UNKNOWN->NOT_STARTED': 9}
    assert passed['T']['acted_instead_of_reporting_on_voluntary_turns'] == {'send_confirmation:None': 1}
    assert passed['T']['no_valid_report_on_voluntary_turns'] == 1
    assert passed['planned'] == {'C': 65, 'P': 14, 'T': 14}
    failed = _r4({52: 'PENDING'})
    assert failed['status'] == 'FAIL' and failed['T']['failures'] == 1
    assert _r4({51: 'NOT_REQUIRED'})['status'] == 'FAIL'


def test_r4_is_not_failed_by_c_alone():
    # Review case 4: C says NOT_REQUIRED on one prompt, T keeps the historical UNKNOWN.
    readout = _r4(c_words={0: 'NOT_REQUIRED', 55: 'PENDING'})
    assert readout['status'] == 'PASS'
    assert readout['C']['failures'] == 2 and readout['C']['decides'] is False
    assert readout['C']['word_outside_allowed_rate'] == pytest.approx(2 / 65)


def test_r4_is_incomplete_when_c_or_t_is_missing():
    # Review case 1: C received nothing; T said NOT_REQUIRED everywhere. INCOMPLETE, never PASS.
    missing_c = _r4({i: 'NOT_REQUIRED' for i in range(65)}, drop_c=65)
    assert missing_c['status'] == 'INCOMPLETE'
    assert _r4(drop_c=4)['status'] == 'INCOMPLETE'                    # C 61 of 65 < 95%
    assert _r4(drop_c=3)['status'] == 'PASS'                          # C 62 of 65
    assert _r4(drop_t=(55,))['status'] == 'INCOMPLETE'                # T 13 of 14 < 95%


def test_r4_fails_a_t_non_report_on_a_report_required_turn():
    # Review case 2, in the form the rule covers: if T is ever sent on a report-required turn,
    # anything but a report there is an R4 failure (the plan sends T on no such turn).
    requests = _requests('report', 3, final=True, word='UNKNOWN')
    results = [_result(r, 'report', word='UNKNOWN') if r['arm'] != 'T' else _result(r, 'other', detail='invalid_action')
               for r in requests]
    readout = probe.compute_readouts(requests, results)['R4']
    assert readout['status'] == 'FAIL' and readout['T']['failures'] == 3
    assert readout['T']['failure_examples'][0]['reason'] == 'no_report_on_report_required_turn'


def test_r4_tallies_the_other_report_fields_descriptively():
    readout = _r4()
    fields = readout['other_report_fields_descriptive']
    assert fields['T_vs_C'] == {'compared': 14, 'overall': 0, 'upgrade_outcome': 0, 'next_action': 0}
    assert fields['C_vs_historical']['compared'] == 65 and fields['C_vs_historical']['overall'] == 0


def test_determinism_readout():
    requests = _requests('determinism', 1, arms=('C',), repeats=5, word='PENDING', group='PENDING')
    unknown = _requests('determinism', 2, arms=('C',), repeats=5, word='UNKNOWN', group='UNKNOWN')[5:]
    results = [_result(r, 'report', word='PENDING', raw='same') for r in requests]
    words = ['UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'PENDING', 'PENDING']
    results += [_result(r, 'report', word=w, raw=w) for r, w in zip(unknown, words)]
    readout = probe.compute_readouts(requests + unknown, results)['determinism']
    assert readout['contexts'] == 2 and readout['contexts_all_repeats_byte_identical'] == 1
    assert (readout['repeat_pairs'], readout['repeat_pairs_byte_identical']) == (20, 14)
    assert readout['change_from_historical_word']['changes'] == 2
    assert readout['change_from_historical_word']['rate_per_call'] == pytest.approx(0.2)
    within = readout['within_context_word_disagreement']
    assert (within['report_pairs'], within['pairs_with_different_word']) == (20, 6)
    assert readout['pending_probability']['PENDING']['rate'] == 1.0
    assert readout['pending_probability']['UNKNOWN']['rate'] == pytest.approx(0.4)
    assert 'drift' not in json.dumps(readout)


def test_decision_requires_primary_r3_and_r4():
    requests = (_requests('turn4', 65) + _requests('nonlapse', 100)
                + [r for r in _requests('report', 65, final=lambda i: i < 51, word='UNKNOWN')
                   if r['arm'] == 'C' or not r['final_report_required']])
    results = []
    for request in requests:
        if request['population'] == 'turn4':
            results.append(_result(request, 'send_confirmation' if request['arm'] == 'T' else 'get_operation_status'))
        elif request['population'] == 'nonlapse':
            results.append(_result(request, 'send_confirmation'))
        else:
            results.append(_result(request, 'report', word='UNKNOWN'))
    readouts = probe.compute_readouts(requests, results)
    assert readouts['statuses'] == {'primary': 'PASS', 'R3': 'PASS', 'R4': 'PASS'}
    assert readouts['decision'] == 'V5_ELIGIBLE_FOR_PHASE_22'
    failed = probe.compute_readouts(requests, [dict(r, **{'class': 'get_operation_status'})
                                               if r['request_id'].startswith('turn4') else r for r in results])
    assert failed['decision'] == 'V5_NOT_ADOPTED' and failed['statement'].startswith('the lapse is not fixed')
    partial = probe.compute_readouts(requests, [r for r in results if not r['request_id'].startswith('nonlapse')])
    assert partial['decision'] == 'V5_NOT_ADOPTED' and 'R3 INCOMPLETE' in partial['statement']
    assert readouts['R4']['status_note'] == 'R4 PASS on 14 of 14 T reports'
    assert 'R4 PASS on 14 of 14 T reports' in readouts['statement'] and 'wording guard' not in readouts['statement']


def test_a_primary_fail_states_which_condition_failed():
    # Review round 2: the program's sentence is true only when T itself stays below 0.8.
    below = _primary(40, 0)
    assert below['status'] == 'FAIL'
    assert probe.primary_fail_statement(below).startswith('the lapse is not fixed by stating the missing state')
    placebo = _primary(60, 30)
    assert placebo['status'] == 'FAIL'
    text = probe.primary_fail_statement(placebo)
    assert text.startswith('a meaningless same-shape field recovered the Actor nearly as often (P sent on 30 of 65')
    assert 'plain re-send' not in text and 'the lapse is not fixed' not in text and text.endswith('stays fatal')
    control = _primary(65, 0, c_sends=33)
    assert control['status'] == 'FAIL'
    text = probe.primary_fail_statement(control)
    assert text.startswith('a plain re-send recovered the Actor on 33 of 65; the lapse does not reproduce reliably')
    assert 'meaningless' not in text
    both = probe.primary_fail_statement(_primary(60, 30, c_sends=33))
    assert 'meaningless' in both and 'plain re-send recovered the Actor on 33 of 65' in both
    lost = probe.primary_fail_statement(_primary(52, 17, missing=3, missing_arm='P'))
    assert 'P sent on 17 of 62 received (3 missing, counted against v5)' in lost


def test_the_decision_statement_carries_the_primary_route():
    requests = _requests('turn4', 65)
    results = [_result(r, 'send_confirmation' if r['arm'] in ('T', 'C') else 'get_operation_status',
                       detail=None if r['arm'] in ('T', 'C') else 'notifications') for r in requests]
    readouts = probe.compute_readouts(requests, results)
    assert readouts['primary']['status'] == 'FAIL'
    assert readouts['statement'].startswith('a plain re-send recovered the Actor on 65 of 65')


def test_r4_passes_on_zero_judged_words_when_t_sends_on_every_voluntary_prompt():
    # Review round 2: the plan sends T only on the 14 voluntary prompts, where a send is not a
    # failure. A v5 that sends there is judged on no word at all; R4 must say so.
    readout = _r4(t_classes={i: 'send_confirmation' for i in range(51, 65)})
    assert readout['status'] == 'PASS' and readout['T_words_judged'] == 0 and readout['T']['reports'] == 0
    assert readout['T']['acted_instead_of_reporting_on_voluntary_turns'] == {'send_confirmation:None': 14}
    assert readout['status_note'] == 'R4 PASS on 0 of 14 T reports'
    requests = (_requests('turn4', 65) + _requests('nonlapse', 100)
                + [r for r in _requests('report', 65, final=lambda i: i < 51, word='UNKNOWN')
                   if r['arm'] == 'C' or not r['final_report_required']])
    results = []
    for request in requests:
        if request['population'] == 'turn4':
            sends = request['arm'] == 'T'
            results.append(_result(request, 'send_confirmation' if sends else 'get_operation_status',
                                   detail=None if sends else 'notifications'))
        elif request['population'] == 'nonlapse' or request['arm'] == 'T':
            results.append(_result(request, 'send_confirmation'))
        else:
            results.append(_result(request, 'report', word='UNKNOWN'))
    readouts = probe.compute_readouts(requests, results)
    assert readouts['decision'] == 'V5_ELIGIBLE_FOR_PHASE_22'
    assert 'R4 PASS on 0 of 14 T reports' in readouts['statement'] and 'wording guard' in readouts['statement']


def test_r4_reports_c_on_the_voluntary_prompts_separately():
    readout = _r4(c_words={0: 'PENDING', 1: 'PENDING', 55: 'NOT_REQUIRED'})
    assert readout['C']['failures'] == 3 and readout['C']['word_outside_allowed_rate'] == pytest.approx(3 / 65)
    voluntary = readout['C']['voluntary_prompts_only']
    assert voluntary['received'] == voluntary['reports'] == 14 and voluntary['word_outside_allowed'] == 1
    assert voluntary['word_outside_allowed_rate'] == pytest.approx(1 / 14)
    assert voluntary['changes_from_historical'] == {'UNKNOWN->NOT_REQUIRED': 1}
    assert 'pooled' in readout['C']['note'] and '51 of them strict-schema' in readout['C']['note']
    assert readout['T']['voluntary_prompts_only']['reports'] == 14


def test_the_served_model_is_compared_only_where_the_requested_model_is_known():
    requests = _requests('turn4', 1, arms=('C', 'T'))
    ok = {**_result(requests[0], 'send_confirmation'), 'served_model': probe.EXPECTED_ACTOR_MODEL,
          'requested_model': probe.EXPECTED_ACTOR_MODEL}
    empty = {**_result(requests[1], 'other', status='empty_response'), 'served_model': probe.EXPECTED_ACTOR_MODEL}
    provider = probe.compute_readouts(requests, [ok, empty])['provider']
    assert provider['served_differs_from_requested'] == 0 and provider['served_compared_with_requested'] == 1
    assert provider['served_model'] == {probe.EXPECTED_ACTOR_MODEL: 2}


# ---------------------------------------------------------------- spend guard and live loop (fake provider)

def test_spend_guard_admits_exactly_what_the_cap_allows():
    guard = probe.SpendGuard(25.0)
    assert sum(guard.admit() for _ in range(1300)) == 1196
    assert guard.charged == pytest.approx(1196 * 0.0209)
    probe.check_budget(1063, 25.0)
    for total, cap in ((1197, 25.0), (10, 25.01), (10, 0), (10, float('nan'))):
        with pytest.raises(probe.PlanningError):
            probe.check_budget(total, cap)
    with pytest.raises(probe.PlanningError):
        probe.SpendGuard(30.0)


class FakeProvider:
    """Stands in for RuntimeProvider.complete. It never reports a model: the real provider's
    model_id is always the requested model, so the served model is tested on the real provider."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    async def complete(self, messages, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else SEND
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(content=outcome, model_id=probe.EXPECTED_ACTOR_MODEL, input_tokens=100,
                               output_tokens=20)


class FakeSleep:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)

    @property
    def total(self):
        return sum(self.calls)


def _live_fixture(tmp_path, n=3):
    requests = []
    for index in range(n):
        requests.append({'request_id': f'r{index + 1:04d}', 'population': 'turn4', 'prompt_id': f'e:{index // 3}',
                         'arm': probe.ARMS[index % 3], 'repeat': 0, 'request_hash': f'h{index}',
                         'final_report_required': False, 'group': None,
                         'historical': {'raw_sha256': hashlib.sha256(b'x').hexdigest(), 'class': 'get_operation_status',
                                        'detail': 'notifications', 'notification_outcome': None}})
    prompts = {f'h{index}': {'messages': [{'role': 'system', 'content': 'You are a test.'},
                                          {'role': 'user', 'content': f'prompt {index}'}],
                             'response_contract': None} for index in range(n)}
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    return requests, prompts, recorder


def _run(requests, prompts, provider, guard, recorder, **kwargs):
    kwargs.setdefault('sleep', FakeSleep())
    try:
        return asyncio.run(probe.run_requests(requests, prompts, provider, guard, recorder, **kwargs))
    finally:
        recorder.close()


def _lines(tmp_path):
    return [json.loads(line) for line in (tmp_path / 'responses.jsonl').read_text().splitlines()]


def test_live_loop_stops_at_the_spend_guard(tmp_path):
    requests, prompts, recorder = _live_fixture(tmp_path)
    guard = probe.SpendGuard(2 * probe.PER_REQUEST_DOLLAR_BOUND)
    provider = FakeProvider([])
    assert _run(requests, prompts, provider, guard, recorder) == 'spend_guard'
    assert len(provider.calls) == 2 and guard.attempts == 2
    manifest = json.loads((tmp_path / probe.MANIFEST_NAME).read_text())
    assert manifest['attempts'] == 2 and manifest['requests_done'] == 2 and manifest['generations_delivered'] == 2
    assert manifest['charged_upper_bound'] == pytest.approx(0.0418)
    assert [line['class'] for line in _lines(tmp_path)] == ['send_confirmation'] * 2


def test_only_a_transport_failure_is_retried_once_after_a_wait_and_every_attempt_is_charged(tmp_path):
    requests, prompts, recorder = _live_fixture(tmp_path)
    outcomes = [RuntimeProviderError('x', code='CONNECTION_ERROR'), 'x',
                RuntimeProviderError('x', code='HTTP_ERROR'),
                RuntimeProviderError('x', code='EMPTY_FINAL_RESPONSE')]
    guard = probe.SpendGuard(25.0)
    provider, sleep = FakeProvider(outcomes), FakeSleep()
    assert _run(requests, prompts, provider, guard, recorder, sleep=sleep) == 'completed'
    lines = _lines(tmp_path)
    assert guard.attempts == 4 and len(provider.calls) == 4
    assert [len(line['attempts']) for line in lines] == [2, 1, 1]
    assert [line['status'] for line in lines] == ['ok', 'error', 'empty_response']
    assert lines[0]['matches_historical_raw'] is True and lines[2]['class'] == 'other'
    # 10 s before the blind retry, then 30 s of backoff after the errored request.
    assert sleep.total == probe.BLIND_RETRY_WAIT_SECONDS + probe.BACKOFF_SECONDS[0]
    manifest = json.loads((tmp_path / probe.MANIFEST_NAME).read_text())
    assert manifest['backoff_waits'] == [{'after_request': 'r0002', 'seconds': 30, 'consecutive_errors': 1}]
    assert all(call['role'] == 'actor' and call['max_output_tokens'] == 2000 and call['timeout_seconds'] == 20
               for call in provider.calls)


def test_a_short_network_loss_costs_waiting_not_the_run(tmp_path):
    # Review: 3 s of CONNECTION_ERROR used to end the run in 0.5 s. Now the blind retry waits and the
    # loop backs off, so four failing requests in a row are waited out and the run completes.
    requests, prompts, recorder = _live_fixture(tmp_path, n=12)
    blip = [RuntimeProviderError('x', code='CONNECTION_ERROR') for _ in range(8)]
    sleep = FakeSleep()
    assert _run(requests, prompts, FakeProvider(blip), probe.SpendGuard(25.0), recorder, sleep=sleep) == 'completed'
    statuses = [line['status'] for line in _lines(tmp_path)]
    assert statuses == ['error'] * 4 + ['ok'] * 8
    assert sleep.total == 4 * probe.BLIND_RETRY_WAIT_SECONDS + sum(probe.BACKOFF_SECONDS)


def test_persistent_errors_stop_after_the_ladder_and_operator_stop_interrupts_a_wait(tmp_path):
    requests, prompts, recorder = _live_fixture(tmp_path, n=8)
    errors = [RuntimeProviderError('x', code='HTTP_ERROR') for _ in range(8)]
    sleep = FakeSleep()
    assert _run(requests, prompts, FakeProvider(errors), probe.SpendGuard(25.0), recorder, sleep=sleep) == 'consecutive_errors'
    assert len(_lines(tmp_path)) == probe.CONSECUTIVE_ERROR_ABORT
    assert sleep.total == sum(probe.BACKOFF_SECONDS) == 750
    manifest = json.loads((tmp_path / probe.MANIFEST_NAME).read_text())
    assert manifest['generations_delivered'] == 0 and manifest['statuses'] == {'error': 5}
    other = tmp_path / 'second'
    other.mkdir()
    requests, prompts, recorder = _live_fixture(other, n=3)
    flag = {'stop': False}

    class StopSleep(FakeSleep):
        async def __call__(self, seconds):
            await super().__call__(seconds)
            flag['stop'] = True
    sleep = StopSleep()
    reason = _run(requests, prompts, FakeProvider([RuntimeProviderError('x', code='HTTP_ERROR')]),
                  probe.SpendGuard(25.0), recorder, sleep=sleep, stop=lambda: flag['stop'])
    assert reason == 'operator_stop' and sleep.calls == [1.0]
    third = tmp_path / 'third'
    third.mkdir()
    requests, prompts, recorder = _live_fixture(third)
    provider = FakeProvider([])
    assert _run(requests, prompts, provider, probe.SpendGuard(25.0), recorder, stop=lambda: True) == 'operator_stop'
    assert provider.calls == []


class FakeOpenAI:
    """Modelled on the openai client the real RuntimeProvider builds: chat.completions.create and
    close, a response with model, system_fingerprint, usage and choices."""

    script = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        outcome = FakeOpenAI.script.pop(0) if FakeOpenAI.script else SEND
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(model='served-by/another-model', system_fingerprint='fp_test',
                               usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
                               choices=[SimpleNamespace(finish_reason='stop',
                                                        message=SimpleNamespace(content=outcome))])

    async def close(self):
        pass


class APIConnectionError(Exception):
    """Named like the SDK's error, which RuntimeProvider maps to CONNECTION_ERROR."""


@pytest.fixture(scope='module')
def dry_settings():
    return probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)


def _fake_settings(dry_settings, **changes):
    return dataclasses.replace(dry_settings, wandb_api_key='fake-not-a-key', **changes)


def test_the_served_model_is_recorded_from_the_real_provider_and_never_enforced(tmp_path, dry_settings):
    # Review: generation.model_id is the REQUESTED model, so the old abort could never fire. The
    # real RuntimeProvider with a fake client shows the served model is recorded instead.
    requests, prompts, recorder = _live_fixture(tmp_path)
    FakeOpenAI.script = [SEND, SEND, SEND]
    served = probe.ServedRecorder(base=FakeOpenAI)

    async def go():
        async with RuntimeProvider(_fake_settings(dry_settings), live_authorized=True, client_factory=served) as provider:
            return await probe.run_requests(requests, prompts, provider, probe.SpendGuard(25.0), recorder,
                                            served=served, sleep=FakeSleep())
    try:
        assert asyncio.run(go()) == 'completed'
    finally:
        recorder.close()
    lines = _lines(tmp_path)
    assert [line['status'] for line in lines] == ['ok'] * 3
    assert {line['requested_model'] for line in lines} == {probe.EXPECTED_ACTOR_MODEL}
    assert {line['served_model'] for line in lines} == {'served-by/another-model'}
    assert lines[0]['attempts'][0]['served'] == {'model': 'served-by/another-model', 'system_fingerprint': 'fp_test',
                                                 'prompt_tokens': 11, 'completion_tokens': 7}
    readouts = probe.compute_readouts(requests, lines)
    assert readouts['provider']['served_differs_from_requested'] == 3


def test_saved_responses_feed_the_readouts_and_a_cut_off_last_line_is_counted(tmp_path):
    requests, prompts, recorder = _live_fixture(tmp_path)
    _run(requests, prompts, FakeProvider([]), probe.SpendGuard(25.0), recorder)
    (tmp_path / 'plan.json').write_text(json.dumps({'requests': requests}))
    plan, results, partial = probe.load_run(tmp_path)
    readouts = probe.compute_readouts(plan['requests'], results, partial_lines_skipped=partial)
    assert readouts['requests_received'] == 3 and readouts['primary']['sends']['C'] == 1 and partial == 0
    with (tmp_path / 'responses.jsonl').open('a') as handle:
        handle.write('{"request_id": "r0004", "sta')
    _, results, partial = probe.load_run(tmp_path)
    assert len(results) == 3 and partial == 1
    text = (tmp_path / 'responses.jsonl').read_text()
    (tmp_path / 'responses.jsonl').write_text('not json\n' + text)
    with pytest.raises(probe.PlanningError, match='line 1'):
        probe.load_run(tmp_path)


# ---------------------------------------------------------------- output guards, claims and the live gate

def _artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    (tmp_path / 'artifacts').mkdir(exist_ok=True)
    return tmp_path / 'artifacts'


def _manifest(artifacts, relative, **fields):
    path = artifacts / relative / probe.MANIFEST_NAME
    path.parent.mkdir(parents=True)
    body = {'status': 'STOPPED', 'ended_at': '2026-09-24T00:00:00Z', 'statuses': {'error': 5},
            'generations_delivered': 0, 'charged_upper_bound': 0.209, **fields}
    path.write_text(json.dumps(body))
    return path


def _claim(artifacts, number, out, pid=999999):
    path = artifacts / probe.CLAIM_DIR / f'claim-{number:02d}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'claim': path.name, 'pid': pid, 'out': out, 'plan_hash': 'plan',
                                'harness_sha256': 'harness', 'spend_cap': 25.0}))
    return path


def test_output_directory_is_new_and_never_resumed(tmp_path, monkeypatch):
    _artifacts(tmp_path, monkeypatch)
    target = probe.check_output('artifacts/phase21-2026-09-24/live')
    assert target == (tmp_path / 'artifacts/phase21-2026-09-24/live').resolve()
    target.mkdir(parents=True)
    with pytest.raises(probe.PlanningError, match='never resumed'):
        probe.check_output('artifacts/phase21-2026-09-24/live')
    for bad in ('artifacts/phase20-x/live', 'artifacts/phase21-x', 'elsewhere/phase21-x/live', '/tmp/phase21-x/live',
                f'artifacts/{probe.CLAIM_DIR}/live', 'artifacts/phase21-x/review/live'):
        with pytest.raises(probe.PlanningError):
            probe.check_output(bad)
    for bad in ('artifacts/phase21-x/review/dry-plan', 'artifacts/phase21-x'):
        with pytest.raises(probe.PlanningError, match='exactly'):
            probe.check_output(bad, live=False)
    assert probe.check_output('artifacts/phase21-2026-09-25/dry-plan', live=False)


def test_evidence_copies_below_the_run_depth_are_not_live_gate_inputs(tmp_path, monkeypatch):
    # Review round 2: a reviewer's fixture tree saved under artifacts/ as evidence blocked the gate.
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase21-2026-09-23/review-round-2/roots/G10/artifacts/phase21-2026-09-23/live',
              status='COMPLETED', statuses={'ok': 3}, generations_delivered=3)
    assert probe.check_output('artifacts/phase21-2026-09-24/live')
    _manifest(artifacts, 'phase21-2026-09-23/live', status='COMPLETED', statuses={'ok': 3}, generations_delivered=3)
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase21-2026-09-24/live')


def test_a_run_that_delivered_anything_blocks_every_later_run(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase21-2026-09-24/live', status='COMPLETED', statuses={'ok': 1063}, generations_delivered=1063)
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase21-2026-09-25/live')
    assert probe.check_output('artifacts/phase21-2026-09-25/dry-plan', live=False)


def test_a_run_that_delivered_nothing_may_be_followed_by_one_new_claim(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    first_out = probe.check_output('artifacts/phase21-2026-09-24/live')
    claim, earlier = probe.take_claim(first_out, 'plan', 'harness')
    assert claim.name == 'claim-01.json' and earlier == []
    with pytest.raises(probe.PlanningError, match='claims a live run with no manifest'):
        probe.check_output('artifacts/phase21-2026-09-24/live-2')
    _manifest(artifacts, 'phase21-2026-09-24/live')
    second_out = probe.check_output('artifacts/phase21-2026-09-24/live-2')
    claim, earlier = probe.take_claim(second_out, 'plan', 'harness')
    assert claim.name == 'claim-02.json'
    assert earlier == [{'manifest': 'artifacts/phase21-2026-09-24/live/' + probe.MANIFEST_NAME,
                        'charged_upper_bound': 0.209}]
    assert json.loads(claim.read_text())['out'] == 'artifacts/phase21-2026-09-24/live-2'
    # An unreadable count or an empty response counts as delivered.
    _manifest(artifacts, 'phase21-2026-09-24/live-2', statuses={'empty_response': 1})
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase21-2026-09-24/live-3')


def test_claims_are_matched_to_manifests_by_their_directory_not_by_count(tmp_path, monkeypatch):
    # Review round 2 (R3): run A delivered nothing; launch B crashed after its claim. A copy of A's
    # manifest in another run-depth directory must not stand in for B's missing manifest.
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase21-2026-09-24/live')
    _claim(artifacts, 1, 'artifacts/phase21-2026-09-24/live')
    _claim(artifacts, 2, 'artifacts/phase21-2026-09-24/live-2')
    _manifest(artifacts, 'phase21-2026-09-24/evidence-copy')
    with pytest.raises(probe.PlanningError, match='claim-02.json claims a live run with no manifest'):
        probe.check_output('artifacts/phase21-2026-09-24/live-3')
    _manifest(artifacts, 'phase21-2026-09-24/live-2')
    assert probe.check_output('artifacts/phase21-2026-09-24/live-3')
    _claim(artifacts, 3, 'artifacts/phase21-2026-09-24/../../elsewhere')
    with pytest.raises(probe.PlanningError, match='claim-03.json cannot be read or names no valid output'):
        probe.check_output('artifacts/phase21-2026-09-24/live-3')


def test_a_claim_may_name_only_a_run_directory(tmp_path):
    artifacts = tmp_path / 'artifacts'
    assert probe.claimed_output(artifacts, 'artifacts/phase21-x/live') == artifacts / 'phase21-x/live'
    for bad in ('artifacts/phase21-x/..', 'artifacts/phase21-x/.', 'artifacts/phase21-x', '/abs/phase21-x/live',
                'artifacts/phase21-x/live/deeper', f'artifacts/{probe.CLAIM_DIR}/live', 'artifacts/phase20-x/live',
                '', None, 7):
        assert probe.claimed_output(artifacts, bad) is None


def test_an_earlier_run_without_a_readable_charge_blocks(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase21-2026-09-24/live', charged_upper_bound=None)
    with pytest.raises(probe.PlanningError, match='charged_upper_bound'):
        probe.check_output('artifacts/phase21-2026-09-24/live-2')


def test_the_phase_cap_is_shared_by_every_run():
    earlier = [{'manifest': 'a', 'charged_upper_bound': 0.209}, {'manifest': 'b', 'charged_upper_bound': 0.0418}]
    assert probe.phase_spend_remaining(earlier) == pytest.approx(25 - 0.2508)
    assert probe.effective_spend_cap(25.0, earlier) == pytest.approx(24.7492)
    assert probe.effective_spend_cap(10.0, earlier) == 10.0
    for bad in (float('nan'), 0, 30.0):
        with pytest.raises(probe.PlanningError, match='spend cap'):
            probe.effective_spend_cap(bad, earlier)
    with pytest.raises(probe.PlanningError, match='phase cap'):
        probe.effective_spend_cap(25.0, [{'manifest': 'a', 'charged_upper_bound': 25.0}])
    # The plan still fits after about 13 undelivered runs that each hit the error breaker.
    probe.check_budget(1063, probe.effective_spend_cap(25.0, [{'charged_upper_bound': 0.209}] * 13))
    with pytest.raises(probe.PlanningError, match='exceed'):
        probe.check_budget(1063, probe.effective_spend_cap(25.0, [{'charged_upper_bound': 0.209}] * 14))


def test_a_running_or_unreadable_earlier_manifest_blocks(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    running = _manifest(artifacts, 'phase21-2026-09-24/live', status='RUNNING', ended_at=None)
    with pytest.raises(probe.PlanningError, match='not final'):
        probe.check_output('artifacts/phase21-2026-09-24/other')
    running.write_text('{"status": "STOPP')
    with pytest.raises(probe.PlanningError, match='cannot be read'):
        probe.check_output('artifacts/phase21-2026-09-24/other')


def test_two_launches_cannot_both_take_the_same_claim(tmp_path, monkeypatch):
    _artifacts(tmp_path, monkeypatch)
    out = probe.check_output('artifacts/phase21-2026-09-24/live')
    probe.take_claim(out, 'plan', 'harness')
    # The racing launcher validated the claims before the first claim existed; it names the claim
    # after the claims it validated, so it computes the same name.
    monkeypatch.setattr(probe, 'live_run_records', lambda artifacts: {'undelivered': [], 'claim_numbers': []})
    with pytest.raises(probe.PlanningError, match='already taken'):
        probe.take_claim(probe.check_output('artifacts/phase21-2026-09-24/other', live=False), 'plan', 'harness')
    # The loser leaves the winner's claim whole and no private file behind.
    claims = tmp_path / 'artifacts' / probe.CLAIM_DIR
    assert json.loads((claims / 'claim-01.json').read_text())['out'] == 'artifacts/phase21-2026-09-24/live'
    assert sorted(p.name for p in claims.iterdir()) == ['claim-01.json']
    # The launch-time list of earlier runs must still hold when the claim is taken.
    monkeypatch.setattr(probe, 'live_run_records', lambda artifacts: {'undelivered': [], 'claim_numbers': [1]})
    with pytest.raises(probe.PlanningError, match='changed during the launch checks'):
        probe.take_claim(probe.check_output('artifacts/phase21-2026-09-24/other', live=False), 'plan', 'harness',
                         expected_earlier=[{'manifest': 'x', 'charged_upper_bound': 0.0}])
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR / 'claim-02.json').exists()


def test_a_phase20_run_in_progress_blocks_unless_named_as_crashed(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    path = artifacts / 'phase20-2026-09-24/run/dev-probe-manifest.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'stop_reason': 'running', 'cases': [{'status': 'RUNNING'}]}))
    args = SimpleNamespace(ignore_phase20_manifest=[])
    with pytest.raises(probe.PlanningError, match='Phase 20 run may be in progress'):
        probe.check_phase20(args)
    probe.check_phase20(SimpleNamespace(ignore_phase20_manifest=['artifacts/phase20-2026-09-24/run/dev-probe-manifest.json']))
    path.write_text(json.dumps({'stop_reason': 'completed', 'ended_at': '2026-09-24T01:00:00Z'}))
    probe.check_phase20(args)


def test_live_flags_are_required_before_any_plan_is_built(capsys, monkeypatch):
    monkeypatch.setattr(probe, 'build_plan', lambda **_: pytest.fail('no plan may be built'))
    every = {'--out': 'artifacts/phase21-never/live', '--confirm-entity': 'x', '--expect-plan-hash': 'p',
             '--expect-harness-sha256': 'h', '--expect-protocol-sha256': 's'}
    for missing in every:
        flags = ['--execute-live'] + [part for flag, value in every.items() if flag != missing for part in (flag, value)]
        assert probe.main(flags) == 1
        rejected = json.loads(capsys.readouterr().out)
        assert rejected['status'] == 'REJECTED' and '--execute-live needs' in rejected['message']


def test_main_refuses_a_second_live_run_before_any_plan_is_built(tmp_path, monkeypatch, capsys):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase21-2026-09-24/live', status='COMPLETED', statuses={'ok': 3}, generations_delivered=3)
    monkeypatch.setattr(probe, 'build_plan', lambda **_: pytest.fail('no plan may be built'))
    flags = ['--execute-live', '--confirm-entity', 'x', '--out', 'artifacts/phase21-2026-09-25/live',
             '--expect-plan-hash', 'p', '--expect-harness-sha256', 'h', '--expect-protocol-sha256', 's']
    assert probe.main(flags) == 1
    assert 'repeat-until-lucky' in json.loads(capsys.readouterr().out)['message']


def _small_plan(n=6):
    requests = []
    for index in range(n):
        requests.append({'request_id': f'r{index + 1:04d}', 'population': 'turn4', 'prompt_id': f'e:{index // 3}',
                         'arm': probe.ARMS[index % 3], 'repeat': 0, 'request_hash': f'h{index}', 'group': None,
                         'final_report_required': False,
                         'historical': {'raw_sha256': 'x', 'class': 'get_operation_status', 'detail': 'notifications',
                                        'notification_outcome': None}})
    prompts = {f'h{index}': {'request_hash': f'h{index}',
                             'messages': [{'role': 'system', 'content': 'You are a test.'},
                                          {'role': 'user', 'content': f'prompt {index}'}],
                             'response_contract': None} for index in range(n)}
    return {'counts': {'total_requests': n}, 'requests': requests}, prompts


def _gate(tmp_path, monkeypatch, plan, *, protocol_extra='', review=True, reviewed_line=True, marker=False):
    """A tmp repository in which every offline gate passes unless told otherwise."""
    _artifacts(tmp_path, monkeypatch)
    harness = probe.sha256_file(probe.__file__)
    plan_hash = probe.plan_hash(plan)
    lines = ['# test protocol', f'harness {harness}', f'plan {plan_hash}', protocol_extra]
    if reviewed_line:
        lines.append(probe.REVIEWED_LINE.format(harness=harness, plan=plan_hash))
    if marker:
        lines.append(f'Status: {probe.REVIEW_PENDING_MARKER}.')
    protocol = tmp_path / 'protocol.md'
    protocol.write_text('\n'.join(lines) + '\n')
    monkeypatch.setattr(probe, 'PROTOCOL', protocol)
    protocol_sha = probe.sha256_file(protocol)
    if review:
        record = tmp_path / probe.REVIEW_RECORD
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'protocol_sha256': protocol_sha, 'harness_sha256': harness, 'plan_hash': plan_hash}))
    return SimpleNamespace(out='artifacts/phase21-test/live', expect_harness_sha256=harness,
                           expect_protocol_sha256=protocol_sha, expect_plan_hash=plan_hash, spend_cap=25.0,
                           confirm_entity='shreetbohara-quinstreet', ignore_phase20_manifest=[])


class CredentialRead(Exception):
    pass


def _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts):
    def no_credentials(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', no_credentials)
    with pytest.raises(probe.PlanningError) as error:
        probe.run_live(args, plan, prompts, sleep=FakeSleep())
    assert not (tmp_path / 'artifacts/phase21-test').exists() and not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()
    return str(error.value)


def test_live_gate_refuses_without_a_reviewed_protocol_that_declares_the_pins(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    for change, message in ((dict(expect_harness_sha256='0' * 64), 'harness'),
                            (dict(expect_protocol_sha256='0' * 64), 'does not match the protocol'),
                            (dict(expect_plan_hash='0' * 64), '--expect-plan-hash'),
                            (dict(spend_cap=0.05), 'exceed')):
        assert message in _refused_before_credentials(tmp_path, monkeypatch, SimpleNamespace(**{**vars(args), **change}),
                                                      plan, prompts)
    monkeypatch.setattr(probe, 'PROTOCOL', tmp_path / 'missing.md')
    assert 'No protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    silent = tmp_path / 'silent.md'
    silent.write_text('a protocol that declares nothing')
    monkeypatch.setattr(probe, 'PROTOCOL', silent)
    assert 'does not declare' in _refused_before_credentials(
        tmp_path, monkeypatch, SimpleNamespace(**{**vars(args), 'expect_protocol_sha256': probe.sha256_file(silent)}),
        plan, prompts)
    # All offline gates pass: the credential read is reached, and still nothing is created.
    args = _gate(tmp_path, monkeypatch, plan)

    def credential_read(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', credential_read)
    with pytest.raises(CredentialRead):
        probe.run_live(args, plan, prompts, sleep=FakeSleep())
    assert not (tmp_path / 'artifacts/phase21-test').exists()


def test_live_gate_enforces_the_review(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan, marker=True)
    assert 'NOT yet reviewed' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, reviewed_line=False)
    assert 'Reviewed for launch' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    (tmp_path / probe.REVIEW_RECORD).unlink()
    args = _gate(tmp_path, monkeypatch, plan, review=False)
    assert 'No readable review record' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)
    record = tmp_path / probe.REVIEW_RECORD
    record.write_text(json.dumps({**json.loads(record.read_text()), 'protocol_sha256': '0' * 64}))
    assert 'review record does not name' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)


def test_live_gate_refuses_while_phase20_runs_or_after_a_delivering_run(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    phase20 = tmp_path / 'artifacts/phase20-2026-09-24/run/dev-probe-manifest.json'
    phase20.parent.mkdir(parents=True)
    phase20.write_text(json.dumps({'stop_reason': 'running'}))
    assert 'Phase 20' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    phase20.write_text(json.dumps({'stop_reason': 'completed', 'ended_at': 'x'}))
    _manifest(tmp_path / 'artifacts', 'phase21-2026-09-24/live', status='COMPLETED', statuses={'ok': 1},
              generations_delivered=1)
    assert 'repeat-until-lucky' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)


@pytest.mark.parametrize('change,message', [
    ({'confirm_entity': 'someone-else'}, '--confirm-entity'),
    ({'settings': {'wandb_project': 'Other'}}, 'project'),
    ({'settings': {'wandb_model': 'deepseek-ai/DeepSeek-V4-Pro-0813'}}, 'configuration_hash'),
    ({'settings': {'wandb_model': 'deepseek-ai/DeepSeek-V4-Pro-0813'}, 'real_pins': True}, 'Actor role'),
])
def test_live_run_refuses_a_wrong_entity_project_or_model_after_the_credential_read(
        tmp_path, monkeypatch, dry_settings, change, message):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    if 'confirm_entity' in change:
        args.confirm_entity = change['confirm_entity']
    settings = _fake_settings(dry_settings, **change.get('settings', {}))

    def live_settings(path, *, env_path):
        assert env_path is None, 'the live path reads credentials through the runtime loader only'
        return settings
    monkeypatch.setattr(probe, 'settings_from_file', live_settings)
    if change.get('real_pins'):
        pins = probe.configuration_pins(dry_settings)
        monkeypatch.setattr(probe, 'configuration_pins', lambda _: pins)
    with pytest.raises(probe.PlanningError, match=message):
        probe.run_live(args, plan, prompts, sleep=FakeSleep())
    assert not (tmp_path / 'artifacts/phase21-test').exists() and not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()


def _live_end_to_end(tmp_path, monkeypatch, dry_settings, script, *, out='artifacts/phase21-test/live', **kwargs):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    args.out = out
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    monkeypatch.setattr(probe, 'openai_client_factory', FakeOpenAI)
    FakeOpenAI.script = list(script)
    code = probe.run_live(args, plan, prompts, sleep=FakeSleep())
    directory = tmp_path / out
    return code, json.loads((directory / probe.MANIFEST_NAME).read_text()), directory


def test_live_run_end_to_end_on_the_real_provider_with_a_fake_client(tmp_path, monkeypatch, dry_settings):
    code, manifest, directory = _live_end_to_end(tmp_path, monkeypatch, dry_settings, [])
    assert code == 0 and manifest['status'] == 'COMPLETED' and manifest['generations_delivered'] == 6
    assert manifest['claim'] == f'artifacts/{probe.CLAIM_DIR}/claim-01.json' and manifest['traceback'] is None
    readouts = json.loads((directory / 'readouts.json').read_text())
    assert readouts['provider']['served_model'] == {'served-by/another-model': 6}
    assert readouts['requests_received'] == 6
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase21-test/live-2')


def test_a_run_that_received_nothing_may_be_restarted_in_a_new_directory(tmp_path, monkeypatch, dry_settings):
    failures = [APIConnectionError('down') for _ in range(20)]
    code, manifest, _ = _live_end_to_end(tmp_path, monkeypatch, dry_settings, failures)
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'consecutive_errors'
    assert manifest['generations_delivered'] == 0 and manifest['statuses'] == {'error': 5}
    assert [wait['seconds'] for wait in manifest['backoff_waits']] == list(probe.BACKOFF_SECONDS)
    assert manifest['attempts'] == 10 and manifest['charged_upper_bound'] == pytest.approx(0.209)
    code, manifest, _ = _live_end_to_end(tmp_path, monkeypatch, dry_settings, [], out='artifacts/phase21-test/live-2')
    assert code == 0 and manifest['claim'].endswith('claim-02.json')
    assert manifest['earlier_undelivered_runs'] == [{'manifest': f'artifacts/phase21-test/live/{probe.MANIFEST_NAME}',
                                                     'charged_upper_bound': 0.209}]
    # Review round 2: the $25 is a phase cap, so the second run gets what the first left.
    assert manifest['spend_cap'] == pytest.approx(25 - 0.209) and manifest['spend_cap_requested'] == 25.0
    assert manifest['earlier_undelivered_charged'] == pytest.approx(0.209)
    claim = json.loads((tmp_path / manifest['claim']).read_text())
    assert claim['spend_cap'] == pytest.approx(25 - 0.209)


def test_an_unexpected_exception_is_recorded_with_its_traceback(tmp_path, monkeypatch, dry_settings):
    def broken(raw):
        raise RuntimeError('classifier broke')
    monkeypatch.setattr(probe, 'classify', broken)
    code, manifest, directory = _live_end_to_end(tmp_path, monkeypatch, dry_settings, [])
    assert code == 1 and manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'RuntimeError'
    assert 'classifier broke' in manifest['traceback'] and 'fake-not-a-key' not in manifest['traceback']
    # The generation arrived before the failure, so this run can never be restarted.
    assert manifest['generations_delivered'] == 1
    assert (directory / 'readouts.json').exists()


def test_the_review_marker_is_read_only_in_the_status_block(tmp_path, monkeypatch):
    # Review round 2: a Review log that quotes the marker must not block the launch.
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan, protocol_extra=f'## Review log\nA reviewer quoted "{probe.REVIEW_PENDING_MARKER}".')

    def credential_read(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', credential_read)
    with pytest.raises(CredentialRead):
        probe.run_live(args, plan, prompts, sleep=FakeSleep())
    assert probe.status_block('# t\nStatus: x\n## A\n' + probe.REVIEW_PENDING_MARKER) == '# t\nStatus: x'
    with pytest.raises(probe.PlanningError, match='no bare "Reviewed for launch" line'):
        probe.check_review(f'`{probe.REVIEWED_LINE.format(harness="h", plan="p")}`', 's', 'h', 'p', root=tmp_path)


class SignalLog:
    """Stands in for signal.signal: records installs, keeps the handler, installs nothing."""

    def __init__(self, events, fire_on_install=None):
        self.events, self.handlers, self.fire_on_install = events, {}, fire_on_install

    def __call__(self, sig, handler):
        self.events.append(('signal', sig))
        self.handlers[sig] = handler
        if sig == self.fire_on_install and callable(handler):
            handler(sig, None)
        return probe.signal.SIG_DFL


def _record_claims(monkeypatch, events):
    original = probe.take_claim

    def take_claim(*args, **kwargs):
        events.append(('claim',))
        return original(*args, **kwargs)
    monkeypatch.setattr(probe, 'take_claim', take_claim)


def test_a_crash_while_writing_the_plan_leaves_a_final_manifest_and_allows_a_new_run(tmp_path, monkeypatch, dry_settings):
    # Review round 2 (R1): a disk error after the claim used to leave a claim with no manifest,
    # which blocked Phase 21 and Phase 20 for good.
    original = probe.write_json

    def broken(path, value):
        if path.name == 'plan.json':
            raise OSError('disk full')
        return original(path, value)
    monkeypatch.setattr(probe, 'write_json', broken)
    script = [SEND] * 6
    code, manifest, directory = _live_end_to_end(tmp_path, monkeypatch, dry_settings, script)
    assert code == 1 and manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'OSError'
    assert manifest['ended_at'] and manifest['generations_delivered'] == 0 and manifest['attempts'] == 0
    assert manifest['pid'] == os.getpid() and len(FakeOpenAI.script) == 6
    monkeypatch.setattr(probe, 'write_json', original)
    code, manifest, _ = _live_end_to_end(tmp_path, monkeypatch, dry_settings, [], out='artifacts/phase21-test/live-2')
    assert code == 0 and manifest['claim'].endswith('claim-02.json') and manifest['spend_cap'] == 25.0


def test_signal_handlers_are_installed_before_the_claim_and_a_stop_in_set_up_is_recorded(tmp_path, monkeypatch,
                                                                                         dry_settings):
    events = []
    log = SignalLog(events)
    monkeypatch.setattr(probe.signal, 'signal', log)
    _record_claims(monkeypatch, events)
    original = probe.write_json

    def stop_during_set_up(path, value):
        if path.name == 'plan.json':
            # The claim already has a manifest on disk, and it says no call can have been made yet.
            on_disk = json.loads((path.parent / probe.MANIFEST_NAME).read_text())
            events.append(('manifest', on_disk['status'], on_disk['pid']))
            log.handlers[probe.signal.SIGTERM](probe.signal.SIGTERM, None)
        return original(path, value)
    monkeypatch.setattr(probe, 'write_json', stop_during_set_up)
    code, manifest, _ = _live_end_to_end(tmp_path, monkeypatch, dry_settings, [SEND] * 6)
    assert events[:4] == [('signal', probe.signal.SIGINT), ('signal', probe.signal.SIGTERM), ('claim',),
                          ('manifest', 'STARTING', os.getpid())]
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'operator_stop'
    assert manifest['attempts'] == 0 and manifest['generations_delivered'] == 0 and len(FakeOpenAI.script) == 6


def test_an_operator_stop_before_the_claim_claims_nothing(tmp_path, monkeypatch, dry_settings):
    events = []
    monkeypatch.setattr(probe.signal, 'signal', SignalLog(events, fire_on_install=probe.signal.SIGTERM))
    _record_claims(monkeypatch, events)
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    with pytest.raises(probe.PlanningError, match='before the claim; nothing was claimed'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep())
    assert ('claim',) not in events
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists() and not (tmp_path / 'artifacts/phase21-test').exists()


def _phase20_module():
    """The real Phase 20 runner, loaded read-only, for its reading of Phase 21's claims."""
    name = 'run_dev_probe_read_by_phase21_tests'
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / 'scripts/experiments/run_dev_probe.py'
    if not path.exists():
        pytest.skip('the Phase 20 runner is not present')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    if not hasattr(module, 'phase21_active_runs'):
        pytest.skip('the Phase 20 runner does not read Phase 21 records')
    return module


def test_finalize_abandoned_closes_a_claim_left_without_a_manifest(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    claim = _claim(artifacts, 1, 'artifacts/phase21-2026-09-24/live', pid=4242)
    phase20 = _phase20_module()
    assert phase20.phase21_active_runs(artifacts) == [str(claim.resolve())]
    with pytest.raises(probe.PlanningError, match='claims a live run with no manifest'):
        probe.check_output('artifacts/phase21-2026-09-24/live-2')
    with pytest.raises(probe.PlanningError, match='may still be running'):
        probe.finalize_abandoned(claim, alive=lambda pid: True)
    assert not (artifacts / 'phase21-2026-09-24/live').exists()
    path, manifest = probe.finalize_abandoned(claim, alive=lambda pid: pid != 4242)
    assert path == (artifacts / 'phase21-2026-09-24/live' / probe.MANIFEST_NAME)
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'abandoned' and manifest['ended_at']
    assert manifest['generations_delivered'] == 0 and manifest['attempts'] == 0 and manifest['charged_upper_bound'] == 0
    assert manifest['finalized_abandoned']['previous_status'] is None
    assert manifest['plan_hash'] == 'plan' and manifest['harness_sha256'] == 'harness'
    assert phase20.phase21_active_runs(artifacts) == []
    assert probe.check_output('artifacts/phase21-2026-09-24/live-2')
    with pytest.raises(probe.PlanningError, match='already final'):
        probe.finalize_abandoned(claim, alive=lambda pid: False)
    for bad in (tmp_path / 'claim-01.json', artifacts / 'phase21-2026-09-24/live' / probe.MANIFEST_NAME):
        with pytest.raises(probe.PlanningError, match='takes a claim file'):
            probe.finalize_abandoned(bad, alive=lambda pid: False)


def _responses(directory, lines):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'responses.jsonl').write_text(''.join(json.dumps(line) + '\n' for line in lines))


def test_finalize_abandoned_counts_what_a_hard_killed_run_delivered_and_charges_the_in_flight_attempts(
        tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    claim = _claim(artifacts, 1, 'artifacts/phase21-2026-09-24/live')
    _manifest(artifacts, 'phase21-2026-09-24/live', status='RUNNING', ended_at=None, statuses={'ok': 1},
              generations_delivered=1, attempts=1, charged_upper_bound=0.0209)
    served = {'model': 'm', 'system_fingerprint': None, 'prompt_tokens': None, 'completion_tokens': None}
    _responses(artifacts / 'phase21-2026-09-24/live', [
        {'request_id': 'r0001', 'status': 'ok', 'attempts': [{'attempt': 1, 'error': None, 'served': served}]},
        {'request_id': 'r0002', 'status': 'error', 'attempts': [
            {'attempt': 1, 'code': 'CONNECTION_ERROR', 'served': None},
            {'attempt': 2, 'code': 'INVALID_RESPONSE_SHAPE', 'served': served}]}])
    with (artifacts / 'phase21-2026-09-24/live/responses.jsonl').open('a') as handle:
        handle.write('{"request_id": "r0003", "sta')
    monkeypatch.setattr(probe, 'claim_process_alive', lambda pid: False)
    assert probe.main(['--finalize-abandoned', f'artifacts/{probe.CLAIM_DIR}/claim-01.json']) == 0
    manifest = json.loads((artifacts / 'phase21-2026-09-24/live' / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['generations_delivered'] == 2
    assert manifest['statuses'] == {'error': 1, 'ok': 1} and manifest['requests_done'] == 2
    assert manifest['attempts'] == 3 + probe.ABANDONED_IN_FLIGHT_ATTEMPTS
    assert manifest['charged_upper_bound'] == pytest.approx(5 * probe.PER_REQUEST_DOLLAR_BOUND)
    assert manifest['finalized_abandoned']['partial_lines_skipped'] == 1
    assert manifest['finalized_abandoned']['previous_status'] == 'RUNNING'
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase21-2026-09-24/live-2')
    assert _phase20_module().phase21_active_runs(artifacts) == []


def test_finalize_abandoned_after_errors_only_allows_a_new_run_under_the_rest_of_the_phase_cap(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    claim = _claim(artifacts, 1, 'artifacts/phase21-2026-09-24/live')
    _manifest(artifacts, 'phase21-2026-09-24/live', status='RUNNING', ended_at=None, attempts=4)
    _responses(artifacts / 'phase21-2026-09-24/live', [
        {'request_id': f'r000{i}', 'status': 'error', 'attempts': [{'attempt': 1, 'code': 'HTTP_ERROR', 'served': None}]}
        for i in range(1, 5)])
    _, manifest = probe.finalize_abandoned(claim, alive=lambda pid: False)
    assert manifest['generations_delivered'] == 0 and manifest['attempts'] == 6
    earlier = probe.earlier_live_runs((tmp_path / 'artifacts').resolve())
    assert earlier[0]['charged_upper_bound'] == pytest.approx(6 * probe.PER_REQUEST_DOLLAR_BOUND)
    assert probe.effective_spend_cap(25.0, earlier) == pytest.approx(25 - 6 * probe.PER_REQUEST_DOLLAR_BOUND)


def test_entry_delivered_is_conservative():
    assert probe.entry_delivered({'status': 'ok'}) and probe.entry_delivered({'status': 'empty_response'})
    assert not probe.entry_delivered({'status': 'error', 'attempts': [{'code': 'HTTP_ERROR', 'served': None,
                                                                       'input_tokens': None}]})
    assert probe.entry_delivered({'status': 'error', 'attempts': [{'code': 'HTTP_ERROR', 'served': None,
                                                                   'input_tokens': 12}]})
    assert probe.entry_delivered({'status': 'error', 'attempts': [{'code': 'INVALID_RESPONSE_SHAPE', 'served': None}]})
    # A response object arrived (its served metadata was recorded) even though no usage or code says so.
    assert probe.entry_delivered({'status': 'error', 'attempts': [{'code': 'HTTP_ERROR', 'input_tokens': None,
                                                                   'served': {'model': 'm', 'prompt_tokens': None}}]})
    assert probe.entry_delivered('not a line') and probe.entry_delivered({'status': 'error', 'attempts': ['x']})


def test_claim_process_alive_refuses_on_anything_uncertain():
    import subprocess
    for pid in (None, 0, -1, True, '12'):
        assert probe.claim_process_alive(pid) is True
    finished = subprocess.Popen([sys.executable, '-c', 'pass'])
    finished.wait()
    assert probe.claim_process_alive(finished.pid) is False
    other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    harness_like = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'lapse_probe'])
    try:
        assert probe.claim_process_alive(other.pid) is False          # a recycled pid is not the harness
        assert probe.claim_process_alive(harness_like.pid) is True
    finally:
        for process in (other, harness_like):
            process.kill()
            process.wait()


def test_readouts_are_recomputed_only_with_the_runs_own_harness_and_plan(tmp_path, monkeypatch, dry_settings, capsys):
    # Review round 2: --readouts must not silently use an edited harness after a hard kill.
    _, _, directory = _live_end_to_end(tmp_path, monkeypatch, dry_settings, [])
    capsys.readouterr()
    assert probe.main(['--readouts', str(directory)]) == 0
    assert json.loads(capsys.readouterr().out) == json.loads((directory / 'readouts.json').read_text())
    manifest_path = directory / probe.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    manifest_path.write_text(json.dumps({**manifest, 'harness_sha256': '0' * 64}))
    assert probe.main(['--readouts', str(directory)]) == 1
    rejected = json.loads(capsys.readouterr().out)
    assert rejected['status'] == 'REJECTED' and "NOT THE RUN'S HARNESS" in rejected['message']
    assert probe.main(['--readouts', str(directory), '--not-the-runs-harness']) == 0
    labelled = json.loads(capsys.readouterr().out)
    assert labelled['label'] == probe.NOT_THE_RUNS_HARNESS and labelled['harness_matches_run'] is False
    assert labelled['plan_matches_run'] is True
    manifest_path.write_text(json.dumps(manifest))
    plan = json.loads((directory / 'plan.json').read_text())
    (directory / 'plan.json').write_text(json.dumps({**plan, 'requests': plan['requests'][:-1]}))
    assert probe.main(['--readouts', str(directory)]) == 1
    assert 'plan matches the run: False' in json.loads(capsys.readouterr().out)['message']
    (directory / 'plan.json').unlink()
    assert probe.main(['--readouts', str(directory)]) == 1
    assert 'cannot be read' in json.loads(capsys.readouterr().out)['message']


# ---------------------------------------------------------------- pins and planning refusals

@pytest.fixture(scope='module')
def real_pins(dry_settings):
    return probe.configuration_pins(dry_settings)


def test_check_pins_refuses_each_altered_pin(real_pins):
    probe.check_pins(real_pins)
    for key, bad in (('configuration_hash', '0' * 64), ('actor_model', 'deepseek-ai/DeepSeek-V4-Pro-0813'),
                     ('actor_model_settings', {**real_pins['actor_model_settings'], 'temperature': 0.7}),
                     ('per_request_dollar_bound', 0.05)):
        with pytest.raises(probe.PlanningError):
            probe.check_pins({**real_pins, key: bad})


def test_build_plan_refuses_an_altered_settings_file(tmp_path):
    values = json.loads((ROOT / probe.DECLARED_SETTINGS).read_text())
    altered = tmp_path / 'settings.json'
    altered.write_text(json.dumps({**values, 'WANDB_MODEL': 'deepseek-ai/DeepSeek-V4-Pro-0813'}))
    with pytest.raises(probe.PlanningError, match='not the declared Phase 17 settings'):
        probe.build_plan(settings_path=altered)
    # Even past the file check, the pins alone refuse the changed model.
    with pytest.raises(probe.PlanningError):
        probe.check_pins(probe.configuration_pins(probe.settings_from_file(altered, env_path=os.devnull)))


def test_build_plan_refuses_when_the_precheck_fails(tmp_path, monkeypatch):
    store = tmp_path / 'empty.sqlite3'
    connection = sqlite3.connect(store)
    connection.execute('create table records (id text, kind text, payload text)')
    connection.execute('create table events (episode_id text, seq integer, payload text)')
    connection.commit()
    connection.close()
    monkeypatch.setattr(probe, 'survey', lambda *a, **k: ([], {'turns': 0}, {'passed': False}))
    monkeypatch.setattr(probe, 'build_requests', lambda *a, **k: pytest.fail('nothing may be planned'))
    with pytest.raises(probe.PlanningError, match='pre-check failed'):
        probe.build_plan(store=store)
