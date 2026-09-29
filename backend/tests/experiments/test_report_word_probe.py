"""Offline checks of the Phase 27 report-word probe. No provider call, no .env read, no store write."""
import asyncio
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
SPEC = importlib.util.spec_from_file_location('report_word_probe', ROOT / 'scripts/experiments/report_word_probe.py')
probe = importlib.util.module_from_spec(SPEC)
sys.modules['report_word_probe'] = probe
SPEC.loader.exec_module(probe)

from app.contracts.models import canonical_json  # noqa: E402
from app.providers.runtime import RuntimeProvider, RuntimeProviderError  # noqa: E402

STORE = ROOT / 'artifacts/lab.sqlite3'

# The Phase 17 settings file lives under the git-ignored artifacts/ folder, so a fresh clone does not have it.
# Tests that read it skip there with this reason (as test_run_dev_probe.py and test_run_gap_probe.py already
# do); where the file exists they run unchanged.
PHASE17_SETTINGS_ABSENT = not (ROOT / probe.DECLARED_SETTINGS).is_file()
NO_PHASE17_SETTINGS = ('needs the Phase 17 settings file (artifacts/phase16-2026-09-22/settings-phase17.json; '
                       'git-ignored, so a fresh clone does not have it)')
needs_phase17_settings = pytest.mark.skipif(PHASE17_SETTINGS_ABSENT, reason=NO_PHASE17_SETTINGS)


def _tree_is_phase27_configuration():
    """Phase 27 is pinned to the Phase 22 configuration (2cf63e93...). A later backend/app change
    moves the hash and the harness then refuses to plan, by design; the tests that plan are skipped
    there with this reason rather than failing (the Phase 21/22 N3 pattern)."""
    try:
        if not (STORE.exists() and probe.PHASE20_STORE.exists()):
            return False
        if probe.sha256_file(probe.PHASE20_STORE) != probe.PHASE20_STORE_SHA256:
            return False
        settings = probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)
        return probe.configuration_pins(settings)['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    except Exception:
        return False


PHASE27_TREE = _tree_is_phase27_configuration()
needs_phase27_tree = pytest.mark.skipif(not PHASE27_TREE, reason='not the Phase 22 configuration or stores absent')
REPORT = ('{{"kind":"report","report":{{"upgrade_outcome":"{up}","notification_outcome":"{note}",'
          '"overall":"SAFE_UNRESOLVED","evidence_ids":["obs-1"],"next_action":{{"kind":"NONE"}}}}}}')
POLL = '{"kind":"tool","tool":"get_operation_status","arguments":{"service":"notifications"}}'


def report(up='SUCCEEDED', note='UNKNOWN'):
    return REPORT.format(up=up, note=note)


# ---------------------------------------------------------------- the real dry plan (read-only, $0)

@pytest.fixture(scope='module')
def real_plan():
    if not PHASE27_TREE:
        pytest.skip('not the Phase 22 configuration or stores absent')
    return probe.build_plan()


def _store_episodes():
    connection = sqlite3.connect(STORE.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        return {i: json.loads(p) for i, p in connection.execute("select id,payload from records where kind='episodes'")}
    finally:
        connection.close()


def test_the_rebuild_is_phase21s_pinned_harness(tmp_path, monkeypatch):
    assert probe.sha256_file(probe.PHASE21_HARNESS) == probe.PHASE21_HARNESS_SHA256
    assert probe.phase21_harness_problem() is None
    assert probe.lp.__file__ == str(probe.PHASE21_HARNESS)
    altered = tmp_path / 'lapse_probe.py'
    altered.write_text(probe.PHASE21_HARNESS.read_text() + '\n# edited\n')
    monkeypatch.setattr(probe, 'PHASE21_HARNESS', altered)
    assert 'not the pinned Phase 21 harness' in probe.phase21_harness_problem()


@needs_phase27_tree
def test_dry_plan_verifies_every_turn_and_passes_the_precheck(real_plan):
    plan, _ = real_plan
    assert plan['verification']['failed'] == 0 and plan['verification']['turns'] > 17000
    pre = plan['precheck']
    assert pre['passed'] is True
    assert pre['turns_changed_by_T'] == pre['turns_changed_by_P'] == pre['window_turns'] > 0
    assert pre['report_turns_in_window'] == pre['report_turns'] > 3000
    assert pre['report_required_turns_in_window'] > 0
    for key in ('changed_outside_window_or_unchanged_inside', 'structural_violations', 'content_disagreements',
                'window_rule_disagreements', 'control_differs_from_stored'):
        assert pre[key] == 0, key
    assert plan['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    assert plan['phase21_harness_sha256'] == probe.PHASE21_HARNESS_SHA256
    assert plan['freeze_sha256'] == probe.FREEZE_SHA256


@needs_phase27_tree
def test_declared_populations_arms_and_exact_request_count(real_plan):
    plan, prompts = real_plan
    chosen = plan['populations']['chosen']
    assert chosen == {'U1': 52, 'U2': 225, 'G1': 18, 'G2': 7, 'G3': 3, 'G4': 45, 'G5': 22}
    assert plan['populations']['excluded'] == {'U3:not_sent': 62, 'U4:not_sent': 351}
    counts = plan['counts']
    assert counts['total_requests'] == 1064
    assert counts['by_population'] == {'primary': 675, 'guard': 285, 'descriptive': 104}
    for stratum, arms in probe.STRATUM_ARMS.items():
        for arm in probe.ARMS:
            assert counts['by_stratum_and_arm'].get(f'{stratum}/{arm}', 0) == (chosen[stratum] if arm in arms else 0)
    assert plan['cost']['planned_upper_bound'] == pytest.approx(22.2376)
    assert plan['cost']['retry_headroom_attempts'] == 132
    # Review round 1: U2 is allocated across case x arm cells in proportion to what each cell holds.
    assert {cell: v['chosen'] for cell, v in plan['sampling']['allocation']['U2'].items()} == {
        'main/notification-18/B0': 36, 'main/notification-18/L': 32, 'main/notification-2/B0': 105,
        'main/notification-2/L': 14, 'main/notification-3/B0': 38}
    for stratum in ('U2', 'G4', 'G5'):
        cells = plan['sampling']['allocation'][stratum]
        total = sum(v['available'] for v in cells.values())
        for v in cells.values():
            assert abs(v['chosen'] - chosen[stratum] * v['available'] / total) < 1
    # Primary and guard come first, the descriptive U1 prompts last.
    order = [r['population'] for r in plan['requests']]
    assert order == sorted(order, key=probe.POPULATION_ORDER.index)
    # The arms of one prompt are sent back to back.
    seen, last = set(), None
    for request in plan['requests']:
        if request['prompt_id'] != last:
            assert request['prompt_id'] not in seen
            seen.add(request['prompt_id'])
            last = request['prompt_id']
    assert len(prompts) == counts['distinct_prompts']


@needs_phase27_tree
def test_every_request_is_a_development_episode_before_the_cutoff(real_plan):
    plan, _ = real_plan
    main = _store_episodes()
    for request in plan['requests']:
        if request['source'] == 'main':
            episode = main[request['episode_id']]
            assert episode['split'] == 'development' and episode['experiment_purpose'] == 'completion_study'
            assert probe.lp.before_cutoff(episode['started_at'], probe.STORE_CUTOFF)
        else:
            assert request['source'] == 'phase20'
    phase20 = probe.connect_static(probe.PHASE20_STORE)
    try:
        episodes = {i: json.loads(p) for i, p in phase20.execute("select id,payload from records where kind='episodes'")}
    finally:
        phase20.close()
    for request in plan['requests']:
        if request['source'] == 'phase20':
            assert episodes[request['episode_id']]['split'] == 'development'
            assert episodes[request['episode_id']]['experiment_purpose'] == 'challenge'


@needs_phase27_tree
def test_control_and_repeat_are_the_stored_request_and_t_p_add_one_field(real_plan):
    plan, prompts = real_plan
    by_prompt = {}
    for request in plan['requests']:
        by_prompt.setdefault(request['prompt_id'], {})[request['arm']] = request
    for prompt_id, arms in by_prompt.items():
        control = arms['C']
        if 'R' in arms:
            assert arms['R']['request_hash'] == control['request_hash']
        base = prompts[control['request_hash']]['messages']
        for arm, key in (('T', probe.T_FIELD), ('P', probe.PLACEBO_FIELD)):
            if arm not in arms:
                continue
            changed = prompts[arms[arm]['request_hash']]['messages']
            assert probe.lp.added_keys(changed, base) == [key], prompt_id
            payload = json.loads(changed[-1]['content'])
            assert list(payload)[1] == key and list(payload)[0] == 'final_report_required'
            if arm == 'T':
                assert payload[key] == {'note': probe.T_NOTE, **control['context']['stated']}
            else:
                assert payload[key] == probe.PLACEBO_VALUE


@needs_phase27_tree
def test_control_prompts_match_the_stored_hashes(real_plan):
    plan, prompts = real_plan
    connection = sqlite3.connect(STORE.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        sample = [r for r in plan['requests'] if r['arm'] == 'C' and r['source'] == 'main'][:25]
        for request in sample:
            stored = None
            for (payload,) in connection.execute('select payload from events where episode_id=? order by seq',
                                                 (request['episode_id'],)):
                event = json.loads(payload)
                if event['type'] == 'actor_output' and event['payload'].get('actor_turn') == request['actor_turn']:
                    stored = event['payload']
            assert stored['messages_hash'] == request['messages_hash']
            assert stored['request_hash'] == request['request_hash']
    finally:
        connection.close()


@needs_phase27_tree
def test_the_phase24_situation_is_every_development_example(real_plan):
    plan, _ = real_plan
    u1 = [r for r in plan['requests'] if r['stratum'] == 'U1' and r['arm'] == 'C']
    assert len(u1) == plan['sampling']['available']['U1'] == 52
    assert {r['arm'] for r in plan['requests'] if r['stratum'] == 'U1'} == {'C', 'T'}
    assert {r['population'] for r in plan['requests'] if r['stratum'] == 'U1'} == {'descriptive'}
    for request in u1:
        upgrade = request['context']['upgrade']
        assert upgrade['status'] == 'UNKNOWN' and upgrade['writes'] > 0 and upgrade['receipt'] is None
        assert request['final_report_required'] is True and request['response_contract'] == 'actor_final_report'
        assert request['context']['stated']['orders']['status'] == 'UNKNOWN'


@needs_phase27_tree
def test_build_requests_refuses_a_control_that_is_not_the_stored_request(real_plan, monkeypatch):
    plan, _ = real_plan
    request = next(r for r in plan['requests'] if r['source'] == 'main')
    connections = probe.open_sources()
    try:
        connection = connections['main']
        summary = {'episode_id': request['episode_id'], 'source': 'main', 'case': None, 'arm': None}
        turns, _, _ = probe.survey_episode(probe.lp.load_events(connection, request['episode_id']),
                                           probe.lp.load_intent(connection, request['episode_id']), summary)
        turn = next(t for t in turns if t['actor_turn'] == request['actor_turn'])
        populations = {'chosen': {request['stratum']: [(summary, turn)]}}
        original = probe.arm_messages

        def altered(history, user, arm, field):
            messages = original(history, user, arm, field)
            return messages[:-1] + [{**messages[-1], 'content': messages[-1]['content'] + ' '}]
        monkeypatch.setattr(probe, 'arm_messages', altered)
        with pytest.raises(probe.PlanningError, match='not the stored request'):
            probe.build_requests(connections, populations)
    finally:
        for connection in connections.values():
            connection.close()


def test_build_plan_never_reads_env_and_refuses_a_failed_precheck(monkeypatch):
    if not PHASE27_TREE:
        pytest.skip('not the Phase 22 configuration or stores absent')
    seen = []
    original = probe.settings_from_file

    def spy(path, *, env_path):
        seen.append(env_path)
        return original(path, env_path=env_path)
    monkeypatch.setattr(probe, 'settings_from_file', spy)
    monkeypatch.setattr(probe, 'survey', lambda *a, **k: ([], {'turns': 0}, {'passed': False}))
    monkeypatch.setattr(probe, 'openai_client_factory', lambda **_: pytest.fail('no provider client may be built'))
    with pytest.raises(probe.PlanningError, match='pre-check failed'):
        probe.build_plan()
    assert seen == [os.devnull]


class Sentinel(Exception):
    pass


@needs_phase17_settings
def test_build_plan_refuses_altered_pinned_files(tmp_path, monkeypatch):
    # Review round 1 (M33): the settings file's own sha256 is checked, not only the configuration it
    # yields. The same settings with one extra newline keep the configuration but not the sha256.
    settings = tmp_path / 'settings.json'
    settings.write_text((ROOT / probe.DECLARED_SETTINGS).read_text() + '\n')
    monkeypatch.setattr(probe, 'check_files', lambda **_: (_ for _ in ()).throw(Sentinel()))
    with pytest.raises(probe.PlanningError, match='not the declared Phase 17 settings file'):
        probe.build_plan(settings_path=settings)
    monkeypatch.undo()
    if not PHASE27_TREE:
        return
    fake_store = tmp_path / 'phase20.sqlite3'
    fake_store.write_bytes(b'not the pinned store')
    with pytest.raises(probe.PlanningError, match='pinned Phase 20 file'):
        probe.build_plan(phase20_store=fake_store)


@needs_phase17_settings
def test_check_files_refuses_an_edited_freeze_record_or_settings_file(tmp_path, monkeypatch):
    # Review round 1 (M24). Only the files' hashes are checked; the real freeze record is not copied.
    (tmp_path / probe.DECLARED_SETTINGS).parent.mkdir(parents=True)
    (tmp_path / probe.DECLARED_SETTINGS).write_bytes((ROOT / probe.DECLARED_SETTINGS).read_bytes())
    freeze = tmp_path / probe.FREEZE_FILE
    freeze.parent.mkdir(parents=True)
    freeze.write_bytes(b'a stand-in freeze record')
    monkeypatch.setattr(probe, 'FREEZE_SHA256', hashlib.sha256(b'a stand-in freeze record').hexdigest())
    probe.check_files(root=tmp_path)
    freeze.write_bytes(b'a stand-in freeze record, edited')
    with pytest.raises(probe.PlanningError, match='gate freeze record'):
        probe.check_files(root=tmp_path)
    freeze.write_bytes(b'a stand-in freeze record')
    (tmp_path / probe.DECLARED_SETTINGS).write_text((ROOT / probe.DECLARED_SETTINGS).read_text() + '\n')
    with pytest.raises(probe.PlanningError, match='declared Phase 17 settings file'):
        probe.check_files(root=tmp_path)


def test_store_reads_parse_development_rows_only(tmp_path, monkeypatch):
    # Review round 1: the split and purpose are filtered in SQL, and case labels come from completion-study
    # trial rows only, so no payload of another split (heldout-2 is split 'promotion') is ever parsed.
    store = tmp_path / 'store.sqlite3'
    connection = sqlite3.connect(store)
    connection.execute('create table records (kind text, id text, payload text)')
    episode = {'split': 'development', 'experiment_purpose': 'completion_study', 'lifecycle': 'COMPLETED',
               'started_at': '2026-09-24T05:00:00Z', 'arm': 'B0'}
    rows = [('episodes', 'e-dev', episode), ('episodes', 'e-late', {**episode, 'started_at': '2026-09-24T05:51:21Z'}),
            ('episodes', 'e-held', {**episode, 'split': 'promotion', 'marker': 'PRIVATE'}),
            ('episodes', 'e-other', {**episode, 'experiment_purpose': 'context_study'}),
            ('completion_studies', 's-1', {'trial_rows': [{'case_id': 'notification-2', 'trial': {'episode_id': 'e-dev'}},
                                                          {'case_id': 'PRIVATE', 'trial': {'episode_id': 'e-held'}}]}),
            ('trials', 't-1', {'episode_id': 'e-held', 'marker': 'PRIVATE'})]
    connection.executemany('insert into records values (?, ?, ?)', [(k, i, json.dumps(p)) for k, i, p in rows])
    connection.commit()
    connection.close()
    parsed = []
    original = json.loads

    def spy(text, *args, **kwargs):
        parsed.append(text)
        return original(text, *args, **kwargs)
    monkeypatch.setattr(probe.json, 'loads', spy)
    connection = probe.lp.connect(store)
    try:
        eligible = probe.eligible_episodes(connection, 'main')
        labels = probe.completion_case_labels(connection, ['e-dev', 'e-late'])
    finally:
        connection.close()
    monkeypatch.undo()
    assert eligible == [('e-dev', {'episode_id': 'e-dev', 'source': 'main', 'case': 'notification-2', 'arm': 'B0'})]
    assert parsed and not any('PRIVATE' in text or 'promotion' in text for text in parsed)
    # Review round 2 (N06, N07): the purpose is filtered in SQL too, so no other purpose's payload is parsed,
    # and only the labels of the episodes asked for are kept (never a held-out episode's).
    assert not any('context_study' in text for text in parsed)
    assert labels == {'e-dev': 'notification-2'}
    assert probe.lp.before_cutoff('2026-09-24T05:48:32Z', probe.STORE_CUTOFF)
    assert not probe.lp.before_cutoff('2026-09-24T05:51:21Z', probe.STORE_CUTOFF)


@pytest.mark.parametrize('field,value', [('configuration_hash', '0' * 64), ('actor_model', 'other/model'),
                                         ('per_request_dollar_bound', 0.02)])
def test_check_pins_refuses_each_altered_pin(field, value):
    pins = {'configuration_hash': probe.DECLARED_CONFIGURATION_HASH, 'actor_model': probe.EXPECTED_ACTOR_MODEL,
            'actor_model_settings': {'temperature': 0}, 'per_request_dollar_bound': probe.PER_REQUEST_DOLLAR_BOUND}
    probe.check_pins(pins)
    with pytest.raises(probe.PlanningError):
        probe.check_pins({**pins, field: value})
    with pytest.raises(probe.PlanningError, match='temperature'):
        probe.check_pins({**pins, 'actor_model_settings': {'temperature': 0.7}})


# ---------------------------------------------------------------- word classes, context and arms (pure)

def facts(status, *, seen=None, writes=0, receipt=None):
    return {'status': status, 'receipt': receipt, 'seen': sorted(seen if seen is not None else ([status] if status else [])),
            'writes': writes}


def context(upgrade, notification, stated=None):
    return {'upgrade': upgrade, 'notification': notification,
            'reference': list(probe.reference_words(upgrade, notification)),
            'stated': stated or {'orders': None, 'notifications': None}}


PHASE24 = context(facts('UNKNOWN', writes=2), facts(None))
LAPSE_AFTER_SEND = context(facts('SUCCEEDED', receipt='SUCCEEDED', writes=1), facts('UNKNOWN', writes=2))
LAPSE_NEVER_SENT = context(facts('SUCCEEDED', receipt='SUCCEEDED', writes=1), facts('UNKNOWN', writes=0))
REJECTED = context(facts('FAILED', receipt='FAILED', writes=1), facts(None))
DONE = context(facts('SUCCEEDED', receipt='SUCCEEDED', writes=1), facts('SUCCEEDED', receipt='SUCCEEDED', writes=1))
UPGRADE_PENDING = context(facts('PENDING', writes=1), facts(None))


def test_reference_words_follow_the_reference_actor():
    assert PHASE24['reference'] == ['UNKNOWN', 'NOT_STARTED']
    assert REJECTED['reference'] == ['FAILED', 'NOT_REQUIRED']
    assert DONE['reference'] == ['SUCCEEDED', 'SUCCEEDED']
    assert LAPSE_AFTER_SEND['reference'] == ['SUCCEEDED', 'UNKNOWN']
    source = (ROOT / 'backend/app/agents/reference.py').read_text()
    assert "if us=='FAILED': overall='CORRECTLY_REJECTED'; ns='NOT_REQUIRED'" in source
    assert "state.status('orders') or 'NOT_STARTED'" in source


@pytest.mark.parametrize('ctx,up,note,expected', [
    (PHASE24, 'PENDING', 'NOT_STARTED', ('unsupported', 'match', True)),          # Phase 24's slip
    (PHASE24, 'UNKNOWN', 'NOT_STARTED', ('match', 'match', False)),
    (PHASE24, 'NOT_STARTED', 'NOT_STARTED', ('unsupported', 'match', True)),      # the upgrade was written
    (PHASE24, 'FAILED', 'NOT_REQUIRED', ('unsupported', 'unsupported', True)),
    (LAPSE_AFTER_SEND, 'SUCCEEDED', 'PENDING', ('match', 'unsupported', True)),   # the historical slip
    (LAPSE_AFTER_SEND, 'SUCCEEDED', 'NOT_STARTED', ('match', 'unsupported', True)),
    (LAPSE_AFTER_SEND, 'SUCCEEDED', 'SUCCEEDED', ('match', 'unsupported', True)),
    (LAPSE_NEVER_SENT, 'SUCCEEDED', 'NOT_STARTED', ('match', 'allowed_pair', False)),
    (REJECTED, 'FAILED', 'NOT_REQUIRED', ('match', 'match', False)),
    (REJECTED, 'FAILED', 'NOT_STARTED', ('match', 'other_mismatch', False)),      # Phase 4's regression word
    (DONE, 'SUCCEEDED', 'UNKNOWN', ('match', 'other_mismatch', False)),           # under-claim, not unsupported
    (DONE, 'SUCCEEDED', 'NOT_REQUIRED', ('match', 'unsupported', True)),
    (UPGRADE_PENDING, 'PENDING', 'NOT_STARTED', ('match', 'match', False)),
    (UPGRADE_PENDING, 'SUCCEEDED', 'NOT_STARTED', ('unsupported', 'match', True)),
])
def test_word_classes(ctx, up, note, expected):
    verdict = probe.judge({'upgrade_outcome': up, 'notification_outcome': note}, ctx)
    assert (verdict['upgrade'], verdict['notification'], verdict['unsupported']) == expected


def test_a_pending_seen_earlier_is_stale_not_unsupported():
    ctx = context(facts('SUCCEEDED', receipt='SUCCEEDED', writes=1), facts('UNKNOWN', seen=['PENDING', 'UNKNOWN'], writes=1))
    verdict = probe.judge({'upgrade_outcome': 'SUCCEEDED', 'notification_outcome': 'PENDING'}, ctx)
    assert verdict['notification'] == 'other_mismatch' and not verdict['unsupported'] and not verdict['correct']


@pytest.mark.parametrize('ctx,final,stratum', [
    (PHASE24, True, 'U1'), (LAPSE_AFTER_SEND, True, 'U2'), (LAPSE_NEVER_SENT, True, 'U3'),
    (LAPSE_AFTER_SEND, False, 'U4'), (PHASE24, False, 'U4'), (UPGRADE_PENDING, True, 'G1'), (DONE, True, 'G2'),
    (context(facts('SUCCEEDED', receipt='SUCCEEDED', writes=1), facts(None)), True, 'G3'),
    (REJECTED, False, 'G4'), (DONE, False, 'G5'), (REJECTED, True, 'G_other'),
    (context(facts('UNKNOWN', writes=0), facts(None)), True, 'U_other'),
])
def test_strata(ctx, final, stratum):
    assert probe.stratum_of(ctx, final) == stratum


def _field(orders=None, notifications=None):
    return {'note': probe.T_NOTE, 'orders': orders, 'notifications': notifications}


def test_out_of_window_every_arm_is_the_control_and_c_equals_r():
    user = {'observations': [], 'final_report_required': True, 'remaining_actor_calls': 0}
    for arm in probe.ARMS:
        assert probe.arm_payload(user, arm, _field()) is user
    field = _field(orders={'evidence': 'obs-2', 'status': 'UNKNOWN'})
    assert probe.arm_payload(user, 'C', field) is user and probe.arm_payload(user, 'R', field) is user


def test_in_window_t_and_p_each_add_one_field_in_the_same_position():
    user = {'observations': [{'evidence_id': 'obs-1'}], 'final_report_required': True, 'remaining_actor_calls': 0}
    field = _field(orders={'evidence': 'obs-1', 'status': 'UNKNOWN'})
    treated, placebo = probe.arm_payload(user, 'T', field), probe.arm_payload(user, 'P', field)
    assert set(treated) - set(user) == {probe.T_FIELD} and set(placebo) - set(user) == {probe.PLACEBO_FIELD}
    assert treated[probe.T_FIELD] == field and placebo[probe.PLACEBO_FIELD] == probe.PLACEBO_VALUE
    for payload, key in ((treated, probe.T_FIELD), (placebo, probe.PLACEBO_FIELD)):
        assert list(json.loads(canonical_json(payload))) == ['final_report_required', key, 'observations',
                                                             'remaining_actor_calls']
    with pytest.raises(probe.PlanningError):
        probe.arm_payload({**user, probe.T_FIELD: 1}, 'T', field)
    with pytest.raises(probe.PlanningError):
        probe.arm_payload(user, 'X', field)


def test_the_placebo_states_no_status_word():
    text = json.dumps(probe.PLACEBO_VALUE)
    for word in ('UNKNOWN', 'PENDING', 'SUCCEEDED', 'FAILED', 'NOT_STARTED', 'NOT_REQUIRED', 'obs-'):
        assert word not in text
    assert 'status' not in text


def _observation(index, *, tool='get_operation_status', transport='ok', status='UNKNOWN', service='orders',
                 intent=None, data=True, operation=None):
    intent = intent or INTENT
    operation = operation or (intent['upgrade_operation_id'] if service == 'orders' else intent['notification_operation_id'])
    intent_hash = intent['upgrade_intent_hash'] if service == 'orders' else intent['notification_intent_hash']
    result = {'call_id': f'call-{index}', 'tool': tool, 'transport': transport, 'operation_id': operation,
              'order_id': intent['order_id'], 'status': status if data else None, 'error_code': None if data else 'TRANSIENT_UNAVAILABLE',
              'observed_version': None, 'receipt_id': None, 'retry_after_ticks': None,
              'data': ({'operation_id': operation, 'service': service, 'order_id': intent['order_id'],
                        'intent_hash': intent_hash, 'status': status, 'receipt': None} if data else None)}
    return {'schema_version': 'faultlab/v1', 'evidence_id': f'ev-{index}', 'episode_id': 'episode-x',
            'call_id': f'call-{index}', 'delivered_tick': index, 'result': result}


INTENT = {'schema_version': 'faultlab/v1', 'task_id': 'task-1', 'order_id': 'order-1', 'desired_shipping': 'express',
          'expected_version': 1, 'template_version': 'confirmation/v1', 'upgrade_operation_id': 'upgrade-1',
          'notification_operation_id': 'notify-1', 'upgrade_idempotency_key': 'key-u', 'notification_idempotency_key': 'key-n',
          'upgrade_intent_hash': 'a' * 64, 'notification_intent_hash': 'b' * 64, 'task_text': 'Upgrade, then confirm.'}


def _models(observations):
    return [probe.PublicObservation.model_validate_json(json.dumps(o)) for o in observations]


def test_status_field_is_the_latest_matching_status_verbatim_and_independently_reproduced():
    intent = probe.TaskIntent.model_validate_json(json.dumps(INTENT))
    observations = [
        _observation(1, tool='update_order', transport='error', data=False),     # a refused write: no status
        _observation(2, status='UNKNOWN'),
        _observation(3, tool='update_order', transport='error', data=False),
        _observation(4, status='UNKNOWN'),
        _observation(5, service='notifications', status='PENDING', tool='send_confirmation'),
        _observation(6, status='UNKNOWN', operation='upgrade-other'),            # another operation: ignored
    ]
    field = probe.status_field(_models(observations), intent)
    assert field == {'note': probe.T_NOTE, 'orders': {'evidence': 'obs-4', 'status': 'UNKNOWN'},
                     'notifications': {'evidence': 'obs-5', 'status': 'PENDING'}}
    assert probe.independent_status_field(observations, INTENT) == field
    upgrade = probe.operation_facts(_models(observations), intent, 'orders')
    assert upgrade == {'status': 'UNKNOWN', 'receipt': None, 'seen': ['UNKNOWN'], 'writes': 2}
    tampered = [dict(o) for o in observations[:2]]
    tampered[1] = json.loads(json.dumps(tampered[1]))
    tampered[1]['result']['data']['intent_hash'] = 'c' * 64
    assert probe.status_field(_models(tampered), intent)['orders'] is None
    assert probe.independent_status_field(tampered, INTENT)['orders'] is None
    assert not probe.in_window(probe.status_field(_models(tampered), intent))


def test_turn_observations_are_what_each_turn_saw():
    events = [{'type': 'observation_delivered', 'payload': {'observation': _observation(1)}},
              {'type': 'actor_output', 'payload': {}},
              {'type': 'tool_dispatched', 'payload': {}},
              {'type': 'observation_delivered', 'payload': {'observation': _observation(2)}},
              {'type': 'actor_output', 'payload': {}}]
    turns = probe.turn_observations(events)
    assert [len(raws) for raws, _ in turns] == [1, 2] and [len(models) for _, models in turns] == [1, 2]


# ---------------------------------------------------------------- populations (pure)

def _report_turn(episode, turn, ctx, *, final=True, up='SUCCEEDED', note='UNKNOWN', source='main', window=True):
    summary = {'episode_id': episode, 'source': source, 'case': 'c', 'arm': 'B0'}
    return summary, {'actor_turn': turn, 'final_report_required': final, 'field_window': window, 'context': ctx,
                     'historical': {'class': 'report', 'notification_outcome': note,
                                    'report_fields': {'upgrade_outcome': up, 'overall': 'SAFE_UNRESOLVED',
                                                      'next_action': {'kind': 'NONE'}}}}


def _synthetic_reports():
    reports = [_report_turn(f'e-u2-{i}', 8, LAPSE_AFTER_SEND) for i in range(12)]
    reports += [_report_turn(f'e-u1-{i}', 8, PHASE24, up='UNKNOWN', note='NOT_STARTED', source='phase20') for i in range(3)]
    reports += [_report_turn(f'e-g4-{i}', 4, REJECTED, final=False, up='FAILED', note='NOT_REQUIRED') for i in range(6)]
    reports.append(_report_turn('e-g4-wrong', 4, REJECTED, final=False, up='FAILED', note='NOT_STARTED'))
    reports.append(_report_turn('e-u3', 8, LAPSE_NEVER_SENT))
    reports.append(_report_turn('e-out', 8, LAPSE_AFTER_SEND, window=False))
    return reports


def _chosen_ids(selection):
    return {s: [prompt[0]['episode_id'] for prompt in pairs] for s, pairs in selection['chosen'].items()}


def test_population_selection_is_deterministic_and_order_independent():
    sizes = {'U1': None, 'U2': 5, 'G4': 4}
    reports = _synthetic_reports()
    first = probe.select_populations(reports, sizes=sizes)
    shuffled = list(reports)
    random.Random(3).shuffle(shuffled)
    assert _chosen_ids(probe.select_populations(shuffled, sizes=sizes)) == _chosen_ids(first)
    chosen = _chosen_ids(first)
    assert len(chosen['U1']) == 3 and len(chosen['U2']) == 5 and len(chosen['G4']) == 4
    assert 'e-g4-wrong' not in chosen['G4']
    assert first['excluded'] == {'G4:historical_words_not_correct': 1, 'U2:out_of_window': 1, 'U3:not_sent': 1}
    ranked = sorted((f'main:e-u2-{i}:8' for i in range(12)), key=lambda key: probe.rank('U2', key))
    assert chosen['U2'] == [key.split(':')[1] for key in ranked[:5]]


def test_the_sample_follows_the_seeded_rank(monkeypatch):
    sizes = {'U2': 5}
    before = _chosen_ids(probe.select_populations(_synthetic_reports(), sizes=sizes))['U2']
    monkeypatch.setattr(probe, 'SAMPLE_SEED', 'another-seed')
    after = _chosen_ids(probe.select_populations(_synthetic_reports(), sizes=sizes))['U2']
    assert before != after


def test_the_allocation_is_proportional_by_cell_and_house_monotone():
    # Review round 1: the seeded prefix under-sampled the cell that slips most (notification-2/B0: 69 chosen
    # against 87.4 expected). Webster's method allocates by cell and never takes a prompt away as n grows.
    held = {'main/notification-18/B0': 108, 'main/notification-18/L': 95, 'main/notification-2/B0': 310,
            'main/notification-2/L': 40, 'main/notification-3/B0': 114}
    total = sum(held.values())
    previous = None
    for size in range(0, 300):
        seats = probe.webster_allocation(held, size)
        assert sum(seats.values()) == size and all(seats[c] <= held[c] for c in held)
        assert all(abs(seats[c] - size * held[c] / total) < 1 for c in held)
        if previous is not None:
            assert all(seats[c] >= previous[c] for c in held)
        previous = seats
    assert probe.webster_allocation({'b': 1, 'a': 1}, 1) == {'a': 1, 'b': 0}      # ties go to the first by name
    assert probe.webster_allocation({'a': 2, 'b': 50}, 60) == {'a': 2, 'b': 50}   # never above what a cell holds
    reports = [_report_turn(f'e-b0-{i}', 8, LAPSE_AFTER_SEND) for i in range(30)]
    reports += [(dict(s, arm='L'), t) for s, t in (_report_turn(f'e-l-{i}', 8, LAPSE_AFTER_SEND) for i in range(10))]
    selection = probe.select_populations(reports, sizes={'U2': 8})
    assert selection['allocation']['U2'] == {'main/c/B0': {'available': 30, 'chosen': 6},
                                             'main/c/L': {'available': 10, 'chosen': 2}}
    bigger = probe.select_populations(reports, sizes={'U2': 12})
    assert set(_chosen_ids(selection)['U2']) <= set(_chosen_ids(bigger)['U2'])
    shuffled = list(reports)
    random.Random(5).shuffle(shuffled)
    assert _chosen_ids(probe.select_populations(shuffled, sizes={'U2': 8})) == _chosen_ids(selection)


# ---------------------------------------------------------------- read-outs (pure)

def _requests(stratum, n, arms, ctx, *, population=None, start=0):
    population = population or probe.STRATUM_POPULATION[stratum]
    rows = []
    for i in range(n):
        for arm in arms:
            rows.append({'request_id': f'{stratum}-{start + i}-{arm}', 'population': population, 'stratum': stratum,
                         'prompt_id': f'{stratum}:{start + i}', 'arm': arm, 'repeat': 1 if arm == 'R' else 0,
                         'context': ctx, 'final_report_required': stratum not in ('G4', 'G5'),
                         'historical': {'raw_sha256': 'h', 'report_fields': {'overall': 'SAFE_UNRESOLVED'}}})
    return rows


def _result(request, raw, status='ok'):
    result = {'request_id': request['request_id'], 'status': status, 'raw': raw if status == 'ok' else None,
              'raw_sha256': hashlib.sha256(raw.encode()).hexdigest() if status == 'ok' else None}
    result.update(probe.classify(raw) if status == 'ok' else {'class': None, 'detail': status,
                                                              'notification_outcome': None, 'report': None})
    return result


def _primary(c_bad, t_bad, p_bad, *, n=100, t_missing=(), t_poll=(), words=None, missing=(), acts=()):
    """missing and acts are (arm, prompt) pairs whose response errored, or was a tool action."""
    rows = _requests('U2', n, ('C', 'T', 'P'), LAPSE_AFTER_SEND)
    results = []
    for request in rows:
        i = int(request['prompt_id'].split(':')[1])
        bad = {'C': c_bad, 'T': t_bad, 'P': p_bad}[request['arm']]
        if (request['arm'] == 'T' and i in t_missing) or (request['arm'], i) in missing:
            results.append(_result(request, '', status='error'))
        elif (request['arm'] == 'T' and i in t_poll) or (request['arm'], i) in acts:
            results.append(_result(request, POLL))
        elif (request['arm'], i) in (words or {}):
            results.append(_result(request, report(*words[(request['arm'], i)])))
        else:
            results.append(_result(request, report(note='PENDING' if i in bad else 'UNKNOWN')))
    return probe.compute_readouts(rows, results)['primary']


def test_primary_passes_only_against_both_the_resend_and_the_placebo():
    ten = set(range(10))
    passed = _primary(ten, set(), set(range(10, 20)))
    assert passed['status'] == 'PASS' and passed['arms']['C']['bad_worst_case'] == 10
    assert passed['tests']['C']['mcnemar_exact_one_sided_p'] == pytest.approx(2 ** -10)
    same = _primary(ten, ten, ten)
    assert same['status'] == 'FAIL' and same['route'] == 'a'
    placebo_also = _primary(ten, set(), set())
    assert placebo_also['status'] == 'FAIL' and placebo_also['route'] == 'b0'
    assert 'placebo arm itself' in probe.primary_statement(placebo_also)
    not_below_placebo = _primary(ten, {10, 11, 12}, set(range(13, 18)))
    assert not_below_placebo['tests']['C']['passes'] and not not_below_placebo['tests']['P']['passes']
    assert not_below_placebo['status'] == 'FAIL' and not_below_placebo['route'] == 'b'
    assert 'meaningless same-shape field' in probe.primary_statement(not_below_placebo)
    halved = _primary(ten, {0, 1, 2, 3, 4, 5}, set(range(10, 20)))
    assert halved['status'] == 'FAIL' and halved['route'] == 'a'   # 6 > half of 10


def test_primary_is_floor_limited_when_the_resend_rarely_slips():
    floor = _primary({0, 1, 2, 3}, set(), {5, 6, 7, 8})
    assert floor['status'] == 'FLOOR_LIMITED'
    assert 'cannot tell' in probe.primary_statement(floor)


def test_primary_counts_a_missing_or_non_report_t_response_as_unsupported():
    six = set(range(6))
    received_only = _primary(six, set(), set(range(10, 16)))
    assert received_only['status'] == 'PASS'
    worst = _primary(six, set(), set(range(10, 16)), t_poll={20, 21, 22, 23})
    assert worst['status'] == 'FAIL' and worst['arms']['T']['bad_worst_case'] == 4
    assert worst['received_only']['C']['t_only_better'] == 6 and worst['received_only']['C']['t_only_worse'] == 0
    incomplete = _primary(six, set(), set(range(10, 16)), t_missing=set(range(30, 36)))
    assert incomplete['status'] == 'INCOMPLETE'


def test_primary_counts_any_incorrect_t_word_against_t_but_not_against_c_or_p():
    # Review round 1: T moving the upgrade word to UNKNOWN despite a delivered SUCCEEDED receipt is an
    # 'other mismatch', not unsupported. On the primary prompts it now counts against T (worst case for T),
    # while the same word from C or P does not count for them.
    six = set(range(6))
    mismatch = {('T', i): ('UNKNOWN', 'UNKNOWN') for i in range(20, 24)}
    verdict = probe.judge({'upgrade_outcome': 'UNKNOWN', 'notification_outcome': 'UNKNOWN'}, LAPSE_AFTER_SEND)
    assert verdict['upgrade'] == 'other_mismatch' and not verdict['unsupported'] and not verdict['correct']
    worse = _primary(six, set(), set(range(10, 16)), words=mismatch)
    assert worse['status'] == 'FAIL' and worse['arms']['T']['bad_worst_case'] == 4
    assert worse['arms']['T']['word_classes']['other_mismatch/match'] == 4
    assert worse['t_other_mismatch_where_c_had_none'] == 4
    assert worse['received_only']['C'] == {'t_only_better': 6, 't_only_worse': 0,
                                           'mcnemar_exact_one_sided_p': pytest.approx(2 ** -6)}
    c_mismatch = {(arm, i): ('UNKNOWN', 'UNKNOWN') for arm in ('C', 'P') for i in range(30, 40)}
    unaffected = _primary(six, set(), set(range(10, 16)), words=c_mismatch)
    assert unaffected['status'] == 'PASS' and unaffected['arms']['C']['bad_worst_case'] == 6


def test_c_and_p_errors_and_non_reports_are_never_counted_bad():
    # Review round 2 (N01): a missing, errored or non-report C or P response is NOT bad. Counting it bad
    # would inflate C's (or P's) slips and make a PASS easier, the anti-conservative direction.
    floor = _primary({0, 1, 2}, set(), set(range(10, 16)))
    noisy = _primary({0, 1, 2}, set(), set(range(10, 16)), missing={('C', 30), ('P', 40)}, acts={('C', 31), ('P', 41)})
    assert floor['status'] == noisy['status'] == 'FLOOR_LIMITED'
    assert noisy['arms']['C']['bad_worst_case'] == 3 and noisy['arms']['C']['non_reports'] == 1
    assert noisy['arms']['C']['received'] == 99
    low_placebo = _primary(set(range(6)), set(), {10, 11, 12})
    noisy = _primary(set(range(6)), set(), {10, 11, 12}, missing={('P', 40)}, acts={('P', 41)})
    assert (low_placebo['status'], low_placebo['route']) == (noisy['status'], noisy['route']) == ('FAIL', 'b0')
    assert noisy['arms']['P']['bad_worst_case'] == 3 and noisy['tests']['P']['t_only_better'] == 3


def test_primary_boundaries():
    # Review round 2 (N05, N08, N09): the floor admits exactly 5 C slips, P needs 95% like C and T, and T
    # exactly half of its comparator passes.
    at_floor = _primary(set(range(5)), set(), set(range(10, 15)))
    assert at_floor['status'] == 'PASS' and at_floor['tests']['C']['mcnemar_exact_one_sided_p'] == pytest.approx(2 ** -5)
    p_short = _primary(set(range(6)), set(), set(range(10, 16)), missing={('P', i) for i in range(50, 56)})
    assert p_short['arms']['P']['received'] == 94 and p_short['status'] == 'INCOMPLETE'
    p_enough = _primary(set(range(6)), set(), set(range(10, 16)), missing={('P', i) for i in range(50, 55)})
    assert p_enough['arms']['P']['received'] == 95 and p_enough['status'] == 'PASS'
    half = _primary(set(range(10)), set(range(5)), set(range(10)))
    assert half['arms']['T']['bad_worst_case'] == 5 and half['tests']['C']['t_at_most_half']
    assert half['status'] == 'PASS'
    over_half = _primary(set(range(10)), set(range(5)) | {50}, set(range(10)))
    assert over_half['status'] == 'FAIL' and over_half['route'] == 'a'


def _guard(t_flips=(), r_flips=(), *, n=30, stratum='G4', missing=(), acts=(), start=0):
    rows = _requests(stratum, n, ('C', 'R', 'T'), REJECTED, start=start)
    results = []
    for request in rows:
        i = int(request['prompt_id'].split(':')[1])
        if i in missing and request['arm'] == 'T':
            results.append(_result(request, '', status='error'))
            continue
        if (request['arm'], i) in acts:
            results.append(_result(request, POLL))
            continue
        flipped = (request['arm'] == 'T' and i in t_flips) or (request['arm'] == 'R' and i in r_flips)
        raw = REPORT.format(up='FAILED', note='NOT_STARTED' if flipped else 'NOT_REQUIRED').replace(
            'SAFE_UNRESOLVED', 'CORRECTLY_REJECTED')
        results.append(_result(request, raw))
    return rows, results


def test_guard_fails_a_phase4_style_word_change_and_passes_noise():
    rows, results = _guard(t_flips=set(range(8)))
    guard = probe.compute_readouts(rows, results)['guard']
    assert guard['terminal_rejection']['status'] == 'FAIL' and guard['status'] == 'FAIL'
    assert guard['terminal_rejection']['transitions_from_C'] == {'report/FAILED/NOT_REQUIRED->report/FAILED/NOT_STARTED': 8}
    rows, results = _guard(t_flips={0, 1, 2}, r_flips={3, 4, 5})
    guard = probe.compute_readouts(rows, results)['guard']
    assert guard['status'] == 'PASS' and guard['pooled']['excess'] == 0


def test_guard_needs_both_the_tolerance_and_the_sign_test():
    beyond_tolerance_not_significant = probe.guard_decision(planned=20, compared=20, t_changed=5, r_changed=3, b=4, c=2,
                                                            tolerance=probe.GUARD_TOLERANCE)
    assert beyond_tolerance_not_significant['status'] == 'PASS'
    significant_within_tolerance = probe.guard_decision(planned=200, compared=200, t_changed=6, r_changed=0, b=6, c=0,
                                                        tolerance=probe.GUARD_TOLERANCE)
    assert significant_within_tolerance['sign_test_one_sided_p'] < 0.05 and significant_within_tolerance['status'] == 'PASS'
    both = probe.guard_decision(planned=20, compared=20, t_changed=6, r_changed=0, b=6, c=0, tolerance=probe.GUARD_TOLERANCE)
    assert both['status'] == 'FAIL'
    incomplete = probe.guard_decision(planned=20, compared=18, t_changed=0, r_changed=0, b=0, c=0,
                                      tolerance=probe.GUARD_TOLERANCE)
    assert incomplete['status'] == 'INCOMPLETE'


def test_guard_is_incomplete_without_the_terminal_rejection_stratum_or_with_missing_t():
    rows, results = _guard(missing={0, 1})
    assert probe.compute_readouts(rows, results)['guard']['status'] == 'INCOMPLETE'
    rows, results = _guard(stratum='G5')
    assert probe.compute_readouts(rows, results)['guard']['status'] == 'INCOMPLETE'


def test_the_terminal_rejection_gate_needs_enough_reports_and_tests_the_words_among_them():
    # Review round 1: G4 prompts are voluntary, so a re-send may act; Phase 4's harm shows only on reports.
    # Review round 2: the floor counts prompts where R and T both reported; C is not needed.
    few = {('R', i) for i in range(12)}
    rows, results = _guard(acts=few)
    tr = probe.compute_readouts(rows, results)['guard']['terminal_rejection']
    assert tr['word_test']['prompts_reported_by_r_and_t'] == 18 < probe.G4_REPORT_FLOOR
    assert tr['outcome_test']['status'] == 'PASS' and tr['word_test']['status'] == 'INCOMPLETE'
    assert tr['status'] == 'INCOMPLETE'
    # R's class changes can hide T's word harm from the outcome test; the word test among reports sees it.
    rows, results = _guard(t_flips=set(range(5)), acts={('R', i) for i in range(20, 30)})
    guard = probe.compute_readouts(rows, results)['guard']
    tr = guard['terminal_rejection']
    assert tr['outcome_test']['status'] == 'PASS' and tr['outcome_test']['excess'] < 0
    assert tr['word_test'] == {'status': 'FAIL', 'prompts_reported_by_r_and_t': 20, 'report_floor': 20,
                               't_only_not_correct': 5, 'r_only_not_correct': 0,
                               'sign_test_one_sided_p': pytest.approx(2 ** -5)}
    assert tr['status'] == 'FAIL' and guard['status'] == 'FAIL'
    # A failed outcome test is reported as FAIL even when the word test lacks reports.
    rows, results = _guard(acts={('T', i) for i in range(12)})
    tr = probe.compute_readouts(rows, results)['guard']['terminal_rejection']
    assert tr['outcome_test']['status'] == 'FAIL' and tr['word_test']['status'] == 'INCOMPLETE'
    assert tr['status'] == 'FAIL'


def test_the_terminal_rejection_word_test_does_not_need_c():
    # Review round 2: requiring C's report as well met the floor with probability q^3, not q^2, and C is
    # never used by the word test. C acting, or C errored, leaves the floor and the word test as they were.
    rows, results = _guard(acts={('C', i) for i in range(12)})
    tr = probe.compute_readouts(rows, results)['guard']['terminal_rejection']
    assert tr['word_test']['prompts_reported_by_r_and_t'] == 30 and tr['word_test']['status'] == 'PASS'
    assert tr['outcome_test']['t_changed'] == tr['outcome_test']['r_changed'] == 12
    assert tr['status'] == 'PASS'
    rows, results = _guard(t_flips=set(range(5)), acts={('C', i) for i in range(12)})
    tr = probe.compute_readouts(rows, results)['guard']['terminal_rejection']
    assert tr['word_test']['status'] == 'FAIL' and tr['word_test']['t_only_not_correct'] == 5
    # C errored on 12 prompts: the outcome test lacks 95% (INCOMPLETE), the word test still counts all 30.
    rows, results = _guard()
    for result in results:
        if result['request_id'].endswith('-C') and int(result['request_id'].split('-')[1]) < 12:
            result.update(status='error', raw=None, raw_sha256=None, **{'class': None, 'detail': 'error', 'report': None})
    guard = probe.compute_readouts(rows, results)['guard']
    tr = guard['terminal_rejection']
    assert tr['outcome_test']['status'] == 'INCOMPLETE' and tr['outcome_test']['compared'] == 18
    assert tr['word_test']['prompts_reported_by_r_and_t'] == 30 and tr['word_test']['status'] == 'PASS'
    assert guard['by_stratum']['G4']['prompts_reported_by_r_and_t'] == 30
    assert 'word test PASS on 30 prompts reported by R and T, floor 20' in probe.compute_readouts(rows, results)['statement']


def test_a_failed_gate_is_reported_ahead_of_an_incomplete_one():
    # Review round 1: a guard with a FAILED gate is FAIL, even if the other gate is incomplete.
    g4_rows, g4_results = _guard(t_flips=set(range(8)))
    g5_rows, g5_results = _guard(stratum='G5', n=30, start=100, missing=set(range(100, 110)))
    readouts = probe.compute_readouts(g4_rows + g5_rows, g4_results + g5_results)
    guard = readouts['guard']
    assert guard['pooled']['status'] == 'INCOMPLETE' and guard['terminal_rejection']['status'] == 'FAIL'
    assert guard['status'] == 'FAIL'
    assert 'guard FAIL (pooled INCOMPLETE, terminal rejection FAIL' in readouts['statement']
    assert probe.combined_status(('PASS', 'INCOMPLETE')) == 'INCOMPLETE'
    assert probe.combined_status(('INCOMPLETE', 'FAIL')) == 'FAIL'
    assert probe.combined_status(('PASS', 'PASS')) == 'PASS'


def test_the_guard_treats_an_allowed_pair_shift_as_no_change_and_tallies_it():
    # Review round 1: UNKNOWN <-> NOT_STARTED for a confirmation never written is correct under the word
    # rule, so it is not a changed word pair; it is counted apart.
    rows = _requests('G1', 30, ('C', 'R', 'T'), UPGRADE_PENDING)
    results = []
    for request in rows:
        i = int(request['prompt_id'].split(':')[1])
        shifted = request['arm'] == 'T' and i < 8
        results.append(_result(request, report(up='PENDING', note='UNKNOWN' if shifted else 'NOT_STARTED')))
    guard = probe.compute_readouts(rows, results)['guard']
    assert guard['pooled']['t_changed'] == 0 and guard['pooled']['status'] == 'PASS'
    assert guard['pooled']['allowed_pair_shifts'] == {'T': 8, 'R': 0}
    assert guard['by_stratum']['G1']['allowed_pair_shifts'] == {'T': 8, 'R': 0}
    request = {'request_id': 'x'}
    shifted = _result(request, report(up='PENDING', note='UNKNOWN'))
    assert probe.response_outcome(shifted) == ('report', 'PENDING', 'UNKNOWN')
    assert probe.response_outcome(shifted, UPGRADE_PENDING) == ('report', 'PENDING', 'NOT_STARTED')
    # Not on G4: NOT_REQUIRED is not in the allowed pair, so NOT_STARTED stays a change there.
    moved = _result(request, report(up='FAILED', note='NOT_STARTED'))
    assert probe.response_outcome(moved, REJECTED) == ('report', 'FAILED', 'NOT_STARTED')


def _passing_primary():
    rows = _requests('U2', 100, ('C', 'T', 'P'), LAPSE_AFTER_SEND)
    results = []
    for request in rows:
        i = int(request['prompt_id'].split(':')[1])
        slip = (request['arm'] == 'C' and i < 10) or (request['arm'] == 'P' and 10 <= i < 20)
        results.append(_result(request, report(note='PENDING' if slip else 'UNKNOWN')))
    return rows, results


def test_a_word_harm_outside_terminal_rejection_fails_the_guard_through_the_pooled_gate():
    # Review round 2 (N02): the pooled gate is the only gate over G1-G3 and G5, so it must decide the
    # guard: a clean G4 with T moving G5's confirmation word is guard FAIL and NOT_RECOMMENDED.
    primary_rows, primary_results = _passing_primary()
    g4_rows, g4_results = _guard()
    g5_rows = _requests('G5', 30, ('C', 'R', 'T'), DONE, start=100)
    g5_results = [_result(request, report(up='SUCCEEDED', note='UNKNOWN' if request['arm'] == 'T'
                                          and int(request['prompt_id'].split(':')[1]) < 110 else 'SUCCEEDED'))
                  for request in g5_rows]
    readouts = probe.compute_readouts(primary_rows + g4_rows + g5_rows, primary_results + g4_results + g5_results)
    guard = readouts['guard']
    assert readouts['primary']['status'] == 'PASS' and guard['terminal_rejection']['status'] == 'PASS'
    assert guard['pooled']['status'] == 'FAIL' and guard['pooled']['t_only_changed'] == 10
    assert guard['status'] == 'FAIL' and readouts['decision'] == 'NOT_RECOMMENDED'
    assert 'guard FAIL (pooled FAIL, terminal rejection PASS' in readouts['statement']
    assert guard['by_stratum']['G5']['transitions_from_C'] == {'report/SUCCEEDED/SUCCEEDED->report/SUCCEEDED/UNKNOWN': 10}


def test_decision_requires_primary_and_guard():
    primary_rows = _requests('U2', 100, ('C', 'T', 'P'), LAPSE_AFTER_SEND)
    guard_rows, guard_results = _guard()
    results = []
    for request in primary_rows:
        i = int(request['prompt_id'].split(':')[1])
        slip = (request['arm'] == 'C' and i < 10) or (request['arm'] == 'P' and 10 <= i < 20)
        results.append(_result(request, report(note='PENDING' if slip else 'UNKNOWN')))
    readouts = probe.compute_readouts(primary_rows + guard_rows, results + guard_results)
    assert readouts['decision'] == 'RECOMMENDED_FOR_A_LATER_LOOP' and 'later loop' in readouts['statement']
    guard_rows, guard_results = _guard(t_flips=set(range(8)))
    readouts = probe.compute_readouts(primary_rows + guard_rows, results + guard_results)
    assert readouts['decision'] == 'NOT_RECOMMENDED' and 'guard FAIL' in readouts['statement']


def test_determinism_the_descriptive_u1_readout_and_tallies():
    # U1 is descriptive (arms C, T); determinism is C against R on the guard prompts.
    rows = _requests('U1', 4, ('C', 'T'), PHASE24) + _requests('G1', 4, ('C', 'R', 'T'), UPGRADE_PENDING)
    results = []
    for request in rows:
        i = int(request['prompt_id'].split(':')[1])
        if request['stratum'] == 'U1':
            if request['arm'] == 'T' and i == 0:
                raw = report(up='PENDING', note='NOT_STARTED')        # the Phase 24 slip, from T
            elif request['arm'] == 'T' and i == 1:
                raw = POLL
            else:
                raw = report(up='UNKNOWN', note='NOT_STARTED')
        elif request['arm'] == 'R' and i == 0:
            raw = report(up='SUCCEEDED', note='NOT_STARTED')          # an unsupported upgrade word
        else:
            raw = report(up='PENDING', note='NOT_STARTED')
        results.append(_result(request, raw))
    readouts = probe.compute_readouts(rows, results)
    determinism = readouts['determinism']
    assert determinism['pairs'] == 4 and determinism['same_outcome'] == 3
    assert determinism['unsupported'] == {'pairs_both_reported': 4, 'both': 0, 'c_only': 0, 'r_only': 1}
    assert determinism['by_population'] == {'guard': {'pairs': 4, 'byte_identical': 3, 'same_outcome': 3}}
    u1 = readouts['descriptive']
    assert u1['planned_prompts'] == 4
    assert u1['C'] == {**u1['C'], 'received': 4, 'reports': 4, 'unsupported': 0, 'correct': 4}
    assert u1['T']['reports'] == 3 and u1['T']['unsupported'] == 1 and u1['T']['correct'] == 2
    assert u1['T']['classes'] == {'get_operation_status:notifications': 1, 'report:None': 3}
    against = u1['t_against_c']
    assert against['pairs_received'] == 4 and against['t_changed'] == 2 and against['pairs_both_reported'] == 3
    assert against['unsupported_t_only'] == 1 and against['unsupported_c_only'] == 0
    assert against['transitions'] == {'report/UNKNOWN/NOT_STARTED->get_operation_status/notifications': 1,
                                      'report/UNKNOWN/NOT_STARTED->report/PENDING/NOT_STARTED': 1}
    assert readouts['report_fields']['by_stratum']['U1']['C']['overall:SAFE_UNRESOLVED'] == 4
    assert readouts['citations']['C']['reports'] == 8
    assert readouts['primary']['status'] == 'INCOMPLETE'   # no primary prompt in this fixture


def test_response_outcome():
    request = {'request_id': 'x'}
    assert probe.response_outcome(None) == ('missing',)
    assert probe.response_outcome(_result(request, report())) == ('report', 'SUCCEEDED', 'UNKNOWN')
    assert probe.response_outcome(_result(request, POLL)) == ('get_operation_status', 'notifications')
    assert probe.response_outcome(_result(request, 'not json')) == ('other', 'invalid_action')


# ---------------------------------------------------------------- live loop, guards and the live gate

class FakeProvider:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    async def complete(self, messages, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else report()
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(content=outcome, model_id=probe.EXPECTED_ACTOR_MODEL, input_tokens=100, output_tokens=20)


class FakeSleep:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


def _small_plan(n=4):
    requests = _requests('U2', n, ('C', 'T', 'P'), LAPSE_AFTER_SEND)
    prompts = {}
    for index, request in enumerate(requests, 1):
        request['request_id'] = f'r{index:04d}'
        request['request_hash'] = f'h{index}'
        prompts[f'h{index}'] = {'request_hash': f'h{index}', 'response_contract': None,
                                'messages': [{'role': 'system', 'content': 'You are a test.'},
                                             {'role': 'user', 'content': f'prompt {index}'}]}
    return {'counts': {'total_requests': len(requests)}, 'requests': requests}, prompts


def test_live_loop_uses_phase21s_loop_and_writes_this_probes_manifest(tmp_path):
    plan, prompts = _small_plan()
    recorder = probe.Recorder(tmp_path, {'statuses': {}})
    guard = probe.SpendGuard(2 * probe.PER_REQUEST_DOLLAR_BOUND)
    try:
        reason = asyncio.run(probe.lp.run_requests(plan['requests'], prompts, FakeProvider([]), guard, recorder,
                                                   sleep=FakeSleep()))
    finally:
        recorder.close()
    assert reason == 'spend_guard' and guard.attempts == 2
    assert (tmp_path / probe.MANIFEST_NAME).is_file() and not (tmp_path / probe.lp.MANIFEST_NAME).exists()
    manifest = json.loads((tmp_path / probe.MANIFEST_NAME).read_text())
    assert manifest['generations_delivered'] == 2 and manifest['charged_upper_bound'] == pytest.approx(0.0418)
    lines = [json.loads(line) for line in (tmp_path / 'responses.jsonl').read_text().splitlines()]
    assert [line['class'] for line in lines] == ['report', 'report']
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    loaded, results, partial = probe.load_run(tmp_path)
    readouts = probe.compute_readouts(loaded['requests'], results, partial_lines_skipped=partial)
    assert readouts['requests_received'] == 2 and readouts['primary']['status'] == 'INCOMPLETE'


def _artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    return artifacts


def _manifest(artifacts, relative, name=None, **fields):
    directory = artifacts / relative
    directory.mkdir(parents=True, exist_ok=True)
    body = {'status': 'COMPLETED', 'ended_at': 'x', 'generations_delivered': 0, 'statuses': {},
            'charged_upper_bound': 0.0, **fields}
    (directory / (name or probe.MANIFEST_NAME)).write_text(json.dumps(body))
    return directory


def _claim(artifacts, number, out, directory=probe.CLAIM_DIR, pid=999999):
    path = artifacts / directory / f'claim-{number:02d}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'claim': path.name, 'pid': pid, 'out': out}))
    return path


def test_output_directory_is_new_exact_and_never_resumed(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    assert probe.check_output('artifacts/phase27-2026-09-24/live') == artifacts.resolve() / 'phase27-2026-09-24/live'
    for bad in ('artifacts/phase21-2026-09-24/live', 'artifacts/phase27-2026-09-24/a/b', 'artifacts/phase27-x',
                f'artifacts/{probe.CLAIM_DIR}/x', 'elsewhere/phase27-1/live'):
        with pytest.raises(probe.PlanningError):
            probe.check_output(bad)
    (artifacts / 'phase27-2026-09-24/live').mkdir(parents=True)
    with pytest.raises(probe.PlanningError, match='never resumed'):
        probe.check_output('artifacts/phase27-2026-09-24/live')


def test_one_delivering_run_only_and_the_phase_cap_is_shared(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase27-2026-09-24/first', charged_upper_bound=0.0418, statuses={'error': 1})
    _claim(artifacts, 1, 'artifacts/phase27-2026-09-24/first')
    records = probe.live_run_records(artifacts)
    assert records['claim_numbers'] == [1] and records['undelivered'][0]['charged_upper_bound'] == 0.0418
    assert probe.effective_spend_cap(25.0, records['undelivered']) == pytest.approx(25.0 - 0.0418)
    _manifest(artifacts, 'phase27-2026-09-24/second', generations_delivered=3, statuses={'ok': 3})
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase27-2026-09-24/third')


def test_a_claim_without_a_final_manifest_blocks_until_finalized(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    claim = _claim(artifacts, 1, 'artifacts/phase27-2026-09-24/live')
    with pytest.raises(probe.PlanningError, match='no manifest'):
        probe.check_output('artifacts/phase27-2026-09-24/live-2')
    with pytest.raises(probe.PlanningError, match='may still be running'):
        probe.finalize_abandoned(claim, root=tmp_path, alive=lambda pid: True)
    path, manifest = probe.finalize_abandoned(claim, root=tmp_path, alive=lambda pid: False)
    assert manifest['status'] == 'ABORTED' and manifest['generations_delivered'] == 0 and manifest['attempts'] == 0
    assert path.name == probe.MANIFEST_NAME
    assert probe.check_output('artifacts/phase27-2026-09-24/live-2')
    with pytest.raises(probe.PlanningError, match='already final'):
        probe.finalize_abandoned(claim, root=tmp_path, alive=lambda pid: False)


def test_two_launches_cannot_take_the_same_claim(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    out = artifacts.resolve() / 'phase27-2026-09-24/live'
    first, _ = probe.take_claim(out, 'plan', 'harness', root=tmp_path)
    assert first.name == 'claim-01.json'
    monkeypatch.setattr(probe, 'live_run_records', lambda artifacts: {'undelivered': [], 'claim_numbers': []})
    with pytest.raises(probe.PlanningError, match='already taken'):
        probe.take_claim(out, 'plan', 'harness', root=tmp_path)
    assert json.loads(first.read_text())['out'] == 'artifacts/phase27-2026-09-24/live'


def test_other_paid_runs_block_until_final_or_named(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    assert probe.other_paid_runs(root=tmp_path) == []
    _manifest(artifacts, 'phase23-2026-09-24', name='full-loop-manifest.json', status=None, stop_reason='fixed_n')
    _manifest(artifacts, 'phase21-2026-09-23/live', name='lapse-probe-manifest.json')
    _claim(artifacts, 1, 'artifacts/phase21-2026-09-23/live', directory='phase21-live-claims')
    assert probe.other_paid_runs(root=tmp_path) == []
    running = _manifest(artifacts, 'phase26-2026-09-25/live', name='run-manifest.json', ended_at=None)
    active = probe.other_paid_runs(root=tmp_path)
    assert active == ['artifacts/phase26-2026-09-25/live/run-manifest.json']
    assert probe.other_paid_runs(root=tmp_path, ignore=[str(running / 'run-manifest.json')]) == []
    _manifest(artifacts, 'phase25-2026-09-25/live', name='x-manifest.json', stop_reason='running')
    _claim(artifacts, 1, 'artifacts/phase25-2026-09-25/other', directory='phase25-live-claims')
    active = probe.other_paid_runs(root=tmp_path, ignore=[str(running / 'run-manifest.json')])
    assert 'artifacts/phase25-2026-09-25/live/x-manifest.json' in active
    assert 'artifacts/phase25-live-claims/claim-01.json' in active
    # A reader never touches the private partitions.
    assert not any('heldout' in path or 'audit' in path for path in active)


@pytest.mark.parametrize('state,body,refused', [
    ('down', None, False), ('up', {'active_campaign_id': None}, False),
    ('up', {'active_campaign_id': 'campaign-1'}, True), ('up', {}, True), ('up', ['x'], True)])
def test_the_backend_must_show_no_active_campaign(tmp_path, monkeypatch, state, body, refused):
    _artifacts(tmp_path, monkeypatch)
    args = SimpleNamespace(ignore_manifest=[])
    if refused:
        with pytest.raises(probe.PlanningError, match='active campaign'):
            probe.check_other_runs(args, status=lambda: (state, body))
    else:
        assert probe.check_other_runs(args, status=lambda: (state, body))['backend'] == state


def test_backend_status_reads_loopback_without_a_proxy_and_says_down_when_refused(monkeypatch):
    class Refused:
        def open(self, url, timeout):
            raise probe.urllib.error.URLError(ConnectionRefusedError())

    class Timeout:
        def open(self, url, timeout):
            raise probe.urllib.error.URLError(TimeoutError())
    monkeypatch.setattr(probe.urllib.request, 'build_opener', lambda *handlers: Refused())
    assert probe.backend_status() == ('down', None)
    monkeypatch.setattr(probe.urllib.request, 'build_opener', lambda *handlers: Timeout())
    with pytest.raises(probe.PlanningError, match='cannot tell'):
        probe.backend_status()
    assert probe.BACKEND_STATUS_URL.startswith('http://127.0.0.1:')


OWNER_QUOTE = 'okay gi ahead with whater u recommend'


def _owner_answer(**changes):
    """The owner's answer to §17 question 1 as the review record carries it; option read at call time."""
    return {'option': probe.DECLARED_OPTION, 'verbatim': OWNER_QUOTE, 'given_by': 'the project owner (test)',
            'date': '2026-09-24', **changes}


def _gate(tmp_path, monkeypatch, plan, *, review=True, reviewed_line=True, marker=False, quote=True):
    _artifacts(tmp_path, monkeypatch)
    harness = probe.sha256_file(probe.__file__)
    plan_hash = probe.plan_hash(plan)
    lines = ['# test protocol']
    if marker:
        lines.append(f'Status: {marker if isinstance(marker, str) else probe.REVIEW_PENDING_MARKER}.')
    lines += ['', '## Pins', f'harness {harness}', f'plan {plan_hash}']
    if reviewed_line:
        lines.append(probe.REVIEWED_LINE.format(harness=harness, plan=plan_hash))
    if quote:
        lines += ['', '## Review log', f'The owner answered: "{OWNER_QUOTE}".']
    protocol = tmp_path / 'protocol.md'
    protocol.write_text('\n'.join(lines) + '\n')
    monkeypatch.setattr(probe, 'PROTOCOL', protocol)
    protocol_sha = probe.sha256_file(protocol)
    if review:
        record = tmp_path / probe.REVIEW_RECORD
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'protocol_sha256': protocol_sha, 'harness_sha256': harness, 'plan_hash': plan_hash,
                                      'phase_cap': probe.HARD_SPEND_CAP, 'owner_answer': _owner_answer()}))
    return SimpleNamespace(out='artifacts/phase27-test/live', expect_harness_sha256=harness,
                           expect_protocol_sha256=protocol_sha, expect_plan_hash=plan_hash, spend_cap=25.0,
                           confirm_entity='shreetbohara-quinstreet', ignore_manifest=[])


class CredentialRead(Exception):
    pass


def _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts, status=lambda: ('down', None)):
    def no_credentials(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', no_credentials)
    with pytest.raises(probe.PlanningError) as error:
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=status)
    assert not (tmp_path / 'artifacts/phase27-test').exists()
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()
    return str(error.value)


def test_live_gate_refuses_before_any_credential_read(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    for change, message in ((dict(expect_harness_sha256='0' * 64), 'harness'),
                            (dict(expect_protocol_sha256='0' * 64), 'does not match the protocol'),
                            (dict(expect_plan_hash='0' * 64), '--expect-plan-hash'),
                            (dict(spend_cap=0.05), 'exceed'), (dict(spend_cap=30.0), 'at most')):
        assert message in _refused_before_credentials(tmp_path, monkeypatch, SimpleNamespace(**{**vars(args), **change}),
                                                      plan, prompts)
    assert 'active campaign' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts,
                                                            status=lambda: ('up', {'active_campaign_id': 'c'}))
    monkeypatch.setattr(probe, 'PROTOCOL', tmp_path / 'missing.md')
    assert 'No protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    silent = tmp_path / 'silent.md'
    silent.write_text('a protocol that declares nothing')
    monkeypatch.setattr(probe, 'PROTOCOL', silent)
    assert 'does not declare' in _refused_before_credentials(
        tmp_path, monkeypatch, SimpleNamespace(**{**vars(args), 'expect_protocol_sha256': probe.sha256_file(silent)}),
        plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(probe, 'settings_from_file', lambda *_, **__: (_ for _ in ()).throw(CredentialRead()))
    with pytest.raises(CredentialRead):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None))
    assert not (tmp_path / 'artifacts/phase27-test').exists()


def test_live_gate_enforces_the_review(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan, marker=True)
    assert 'NOT yet reviewed' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    # Review round 2: the status phrase is matched in any case, so a lower-case leftover also refuses.
    args = _gate(tmp_path, monkeypatch, plan, marker=probe.REVIEW_PENDING_MARKER.lower())
    assert 'NOT yet reviewed' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, reviewed_line=False)
    assert 'Reviewed for launch' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    (tmp_path / probe.REVIEW_RECORD).unlink()
    args = _gate(tmp_path, monkeypatch, plan, review=False)
    assert 'No readable review record' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)
    record = tmp_path / probe.REVIEW_RECORD
    record.write_text(json.dumps({**json.loads(record.read_text()), 'plan_hash': '0' * 64}))
    assert 'review record does not name' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    # Review round 2: a record holding only the three hashes no longer opens the gate.
    args = _gate(tmp_path, monkeypatch, plan)
    record.write_text(json.dumps({key: json.loads(record.read_text())[key]
                                  for key in ('protocol_sha256', 'harness_sha256', 'plan_hash')}))
    assert 'phase_cap' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan)
    record.write_text(json.dumps({**json.loads(record.read_text()), 'owner_answer': None}))
    assert 'no owner_answer' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, quote=False)
    assert 'not quoted in the protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)


def _check_review_with(tmp_path, monkeypatch, **record_changes):
    """Runs check_review on a gate whose review record carries these changes."""
    plan, _ = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    record = tmp_path / probe.REVIEW_RECORD
    record.write_text(json.dumps({**json.loads(record.read_text()), **record_changes}))
    return probe.check_review(probe.PROTOCOL.read_text(), args.expect_protocol_sha256, args.expect_harness_sha256,
                              args.expect_plan_hash, root=tmp_path)


def test_the_review_record_must_carry_the_owners_answer_and_the_phase_cap(tmp_path, monkeypatch):
    # Review round 2: the owner's answer to §17 question 1 is enforced, not only written down.
    assert _check_review_with(tmp_path, monkeypatch) == _owner_answer()
    refusals = [({'phase_cap': 30.0}, 'phase_cap'), ({'phase_cap': '25'}, 'phase_cap'), ({'phase_cap': True}, 'phase_cap'),
                ({'owner_answer': 'R'}, 'no owner_answer'),
                ({'owner_answer': {k: v for k, v in _owner_answer().items() if k != 'given_by'}}, 'no owner_answer'),
                ({'owner_answer': _owner_answer(date=' ')}, 'no owner_answer'),
                ({'owner_answer': _owner_answer(option='W1')}, 'not the option this harness implements'),
                ({'owner_answer': _owner_answer(verbatim='go ahead with the larger sample')}, 'not quoted in the protocol'),
                # Review round 3 (Z01-Z06): an above-cap option at $25, a phase_cap within a dollar of the cap or
                # below it, and a quote that differs only in case or spacing are refused as well.
                ({'owner_answer': _owner_answer(option='A1')}, 'not the option this harness implements'),
                ({'owner_answer': _owner_answer(option='A2')}, 'not the option this harness implements'),
                ({'phase_cap': 24.0}, 'phase_cap'), ({'phase_cap': 25.5}, 'phase_cap'),
                ({'owner_answer': _owner_answer(verbatim=OWNER_QUOTE.upper())}, 'not quoted in the protocol'),
                ({'owner_answer': _owner_answer(verbatim=OWNER_QUOTE.replace(' ', '  '))}, 'not quoted in the protocol')]
    for changes, message in refusals:
        with pytest.raises(probe.PlanningError, match=message):
            _check_review_with(tmp_path, monkeypatch, **changes)
    # A whole-dollar cap written as an integer is the same cap (round 3: nothing tested that it is accepted).
    assert _check_review_with(tmp_path, monkeypatch, phase_cap=25) == _owner_answer()


def test_a_raised_cap_needs_the_owners_above_cap_answer(tmp_path, monkeypatch):
    # Review round 2: raising HARD_SPEND_CAP alone no longer launches; the recorded answer must name an
    # above-cap option, and it must be the option this harness implements.
    monkeypatch.setattr(probe, 'HARD_SPEND_CAP', 37.2)
    with pytest.raises(probe.PlanningError, match="above the program's"):
        _check_review_with(tmp_path, monkeypatch)
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    args.spend_cap = 37.2
    assert "above the program's" in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    monkeypatch.setattr(probe, 'DECLARED_OPTION', 'A2')
    with pytest.raises(probe.PlanningError, match='not the option this harness implements'):
        _check_review_with(tmp_path, monkeypatch, owner_answer=_owner_answer(option='R'))
    # Review round 3: A2 is U2 400 at up to $37.20, so R's sizes under an A2 answer are refused too.
    with pytest.raises(probe.PlanningError, match='not the sizes of the declared option A2'):
        _check_review_with(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, 'STRATUM_SIZES', A2_SIZES)
    assert _check_review_with(tmp_path, monkeypatch)['option'] == 'A2'


R_SIZES = {'U1': None, 'U2': 225, 'G1': None, 'G2': None, 'G3': None, 'G4': 45, 'G5': 22}
A1_SIZES = {**R_SIZES, 'U2': 300}
A2_SIZES = {**R_SIZES, 'U2': 400}


def test_the_option_table_is_section_10_3():
    # Review round 3: the owner's answer is bound to these sizes and caps, so the table itself is pinned to
    # §10.3 (R $25; A1 and A2 are U2 300 and 400, capped at their bound plus about 12%: $30.17 and $37.20).
    assert probe.OPTION_TABLE == {'R': (R_SIZES, 25.0), 'A1': (A1_SIZES, 30.17), 'A2': (A2_SIZES, 37.2)}
    assert probe.DECLARED_OPTION == 'R' and probe.STRATUM_SIZES == R_SIZES and probe.HARD_SPEND_CAP == 25.0
    assert probe.option_problem() is None


@needs_phase27_tree
def test_the_above_cap_options_are_their_bound_plus_twelve_percent(real_plan):
    chosen = real_plan[0]['populations']['chosen']
    arms = {stratum: len(arms) for stratum, arms in probe.STRATUM_ARMS.items()}
    fixed = sum(chosen[s] * arms[s] for s in chosen if s != 'U2')
    assert fixed + chosen['U2'] * arms['U2'] == real_plan[0]['counts']['total_requests'] == 1064
    for option, requests in (('A1', 1289), ('A2', 1589)):
        sizes, cap = probe.OPTION_TABLE[option]
        assert fixed + sizes['U2'] * arms['U2'] == requests
        assert round(requests * probe.PER_REQUEST_DOLLAR_BOUND * 1.12, 2) == cap


def test_the_owners_option_binds_the_sizes_and_the_cap(tmp_path, monkeypatch):
    # Review round 3: before, an A1 answer opened any cap above $25 and an R answer any within-cap sizes
    # (the round-3 option_binding_probe). Now the option's row of OPTION_TABLE must hold both.
    for option, sizes, cap, message in (
            ('R', {**R_SIZES, 'U2': 240, 'G4': 30}, 25.0, 'not the sizes of the declared option R'),   # W1's sizes
            ('R', {**R_SIZES, 'U1': 0}, 25.0, 'not the sizes of the declared option R'),
            ('A1', A1_SIZES, 60.0, r'above the cap of the declared option A1 \(\$30.17\)'),
            ('A1', A1_SIZES, 37.2, r'above the cap of the declared option A1 \(\$30.17\)'),
            ('A1', A2_SIZES, 30.17, 'not the sizes of the declared option A1'),
            ('A2', A2_SIZES, 40.0, r'above the cap of the declared option A2 \(\$37.20\)'),
            ('A2', A2_SIZES, 37.21, r'above the cap of the declared option A2 \(\$37.20\)'),
            ('W1', {**R_SIZES, 'U2': 240, 'G4': 30}, 25.0, "'W1' is not in OPTION_TABLE")):
        monkeypatch.setattr(probe, 'DECLARED_OPTION', option)
        monkeypatch.setattr(probe, 'STRATUM_SIZES', sizes)
        monkeypatch.setattr(probe, 'HARD_SPEND_CAP', cap)
        with pytest.raises(probe.PlanningError, match=message):
            _check_review_with(tmp_path, monkeypatch)
        # The dry run refuses the same harness before it reads any file.
        monkeypatch.setattr(probe, 'sha256_file', lambda *_: (_ for _ in ()).throw(Sentinel()))
        with pytest.raises(probe.PlanningError, match=message + '.*nothing is planned'):
            probe.build_plan()
        monkeypatch.undo()
    # Each option at its own sizes and its own cap passes, and so does R under a lower cap (the plan's
    # $22.24 bound still fits under $24).
    for option, sizes, cap in [(option, sizes, cap) for option, (sizes, cap) in probe.OPTION_TABLE.items()] + [
            ('R', R_SIZES, 24.0)]:
        monkeypatch.setattr(probe, 'DECLARED_OPTION', option)
        monkeypatch.setattr(probe, 'STRATUM_SIZES', dict(sizes))
        monkeypatch.setattr(probe, 'HARD_SPEND_CAP', cap)
        assert probe.option_problem() is None
        assert _check_review_with(tmp_path, monkeypatch)['option'] == option
        monkeypatch.undo()


def test_live_gate_refuses_beside_another_paid_run(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    _manifest(tmp_path / 'artifacts', 'phase26-2026-09-25/live', name='run-manifest.json', ended_at=None)
    assert 'Another paid run' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)


def test_the_review_marker_is_read_only_in_the_status_block(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    protocol = probe.PROTOCOL
    protocol.write_text(protocol.read_text() + f'\n## Review log\n\nThe status once said "{probe.REVIEW_PENDING_MARKER}".\n')
    args.expect_protocol_sha256 = probe.sha256_file(protocol)
    record = tmp_path / probe.REVIEW_RECORD
    record.write_text(json.dumps({**json.loads(record.read_text()), 'protocol_sha256': args.expect_protocol_sha256}))
    monkeypatch.setattr(probe, 'settings_from_file', lambda *_, **__: (_ for _ in ()).throw(CredentialRead()))
    with pytest.raises(CredentialRead):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None))


def test_a_lower_case_status_phrase_in_the_protocol_body_does_not_block_the_launch(tmp_path, monkeypatch):
    # Review round 3 (Z11): the real protocol's runbook (§14 step 2) quotes the phrase in lower case above
    # its Review log, and the match is case-insensitive since round 2. Only the opening block may block.
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    protocol = probe.PROTOCOL
    text = protocol.read_text()
    assert '\n## Review log' in text
    body = ('## Runbook\n\n- check: `grep -n -i "' + probe.REVIEW_PENDING_MARKER.lower() + '" protocol.md` must print only '
            'lines below the first `## ` heading;\n  replace the bold sentence ending `(' + probe.REVIEW_PENDING_MARKER
            + ').**`.\n\n')
    protocol.write_text(text.replace('## Review log', body + '## Review log', 1))
    assert probe.REVIEW_PENDING_MARKER.lower() in probe.PROTOCOL.read_text().split('\n## Review log')[0]
    args.expect_protocol_sha256 = probe.sha256_file(protocol)
    record = tmp_path / probe.REVIEW_RECORD
    record.write_text(json.dumps({**json.loads(record.read_text()), 'protocol_sha256': args.expect_protocol_sha256}))
    monkeypatch.setattr(probe, 'settings_from_file', lambda *_, **__: (_ for _ in ()).throw(CredentialRead()))
    with pytest.raises(CredentialRead):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None))


class FakeOpenAI:
    script = []

    def __init__(self, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        outcome = FakeOpenAI.script.pop(0) if FakeOpenAI.script else report()
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(model='served-by/another-model', system_fingerprint='fp_test',
                               usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
                               choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=outcome))])

    async def close(self):
        pass


class APIConnectionError(Exception):
    """Named like the SDK's error, which RuntimeProvider maps to CONNECTION_ERROR."""


@pytest.fixture(scope='module')
def dry_settings():
    if PHASE17_SETTINGS_ABSENT:
        pytest.skip(NO_PHASE17_SETTINGS)
    return probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)


def _live(tmp_path, monkeypatch, dry_settings, script, out='artifacts/phase27-test/live', status=None):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    args.out = out
    status = status or (lambda: ('down', None))

    def live_settings(path, *, env_path):
        assert env_path is None, 'the live path reads credentials through the runtime loader only'
        return dataclasses.replace(dry_settings, wandb_api_key='fake-not-a-key')
    monkeypatch.setattr(probe, 'settings_from_file', live_settings)
    monkeypatch.setattr(probe, 'openai_client_factory', FakeOpenAI)
    FakeOpenAI.script = list(script)
    code = probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=status)
    directory = tmp_path / out
    return code, json.loads((directory / probe.MANIFEST_NAME).read_text()), directory


@needs_phase27_tree
def test_live_run_end_to_end_on_the_real_provider_with_a_fake_client(tmp_path, monkeypatch, dry_settings):
    code, manifest, directory = _live(tmp_path, monkeypatch, dry_settings, [report(note='PENDING')])
    assert code == 0 and manifest['status'] == 'COMPLETED' and manifest['generations_delivered'] == 12
    assert manifest['claim'] == f'artifacts/{probe.CLAIM_DIR}/claim-01.json' and manifest['traceback'] is None
    assert manifest['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    assert manifest['phase21_harness_sha256'] == probe.PHASE21_HARNESS_SHA256
    assert manifest['other_runs_check'] == {'backend': 'down', 'active_campaign_id': None}
    # Review round 2: the owner's recorded answer is copied into the manifest.
    assert manifest['owner_answer'] == _owner_answer() and manifest['size_option'] == probe.DECLARED_OPTION == 'R'
    assert manifest['program_phase_cap'] == probe.PROGRAM_PHASE_CAP == probe.HARD_SPEND_CAP == 25.0
    readouts = json.loads((directory / 'readouts.json').read_text())
    assert readouts['provider']['served_model'] == {'served-by/another-model': 12}
    assert readouts['requests_received'] == 12
    assert probe.recompute_readouts(directory) == readouts
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase27-test/live-2')


@needs_phase27_tree
def test_a_run_that_received_nothing_may_be_followed_by_one_new_run(tmp_path, monkeypatch, dry_settings):
    failures = [APIConnectionError('down') for _ in range(20)]
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, failures)
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'consecutive_errors'
    assert manifest['generations_delivered'] == 0 and manifest['charged_upper_bound'] > 0
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [], out='artifacts/phase27-test/live-2')
    assert code == 0 and manifest['earlier_undelivered_charged'] > 0
    assert manifest['spend_cap'] == pytest.approx(25.0 - manifest['earlier_undelivered_charged'])


def test_readouts_are_recomputed_only_with_the_runs_own_harness_and_plan(tmp_path):
    plan, _ = _small_plan()
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    (tmp_path / 'responses.jsonl').write_text('')
    (tmp_path / probe.MANIFEST_NAME).write_text(json.dumps({'harness_sha256': '0' * 64, 'plan_hash': probe.plan_hash(plan)}))
    with pytest.raises(probe.PlanningError, match="NOT THE RUN'S HARNESS"):
        probe.recompute_readouts(tmp_path)
    labelled = probe.recompute_readouts(tmp_path, allow_other_harness=True)
    assert labelled['label'] == probe.NOT_THE_RUNS_HARNESS and labelled['plan_matches_run'] is True


def test_readouts_refuse_when_lapse_probe_is_not_the_pinned_file(tmp_path, monkeypatch):
    # Review round 2: the exact statistics come from lapse_probe.py, so --readouts re-checks its sha256.
    plan, _ = _small_plan()
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'plan.json').write_text(json.dumps(plan))
    (run / 'responses.jsonl').write_text('')
    (run / probe.MANIFEST_NAME).write_text(json.dumps({'harness_sha256': probe.sha256_file(probe.__file__),
                                                       'plan_hash': probe.plan_hash(plan)}))
    assert probe.recompute_readouts(run)['schema_version'] == probe.READOUT_SCHEMA
    altered = tmp_path / 'lapse_probe.py'
    altered.write_text(probe.PHASE21_HARNESS.read_text() + '\n# edited\n')
    monkeypatch.setattr(probe, 'PHASE21_HARNESS', altered)
    with pytest.raises(probe.PlanningError, match='lapse_probe.py is the pinned Phase 21 file: False'):
        probe.recompute_readouts(run)
    labelled = probe.recompute_readouts(run, allow_other_harness=True)
    assert labelled['phase21_harness_matches_pin'] is False and labelled['harness_matches_run'] is True


def test_live_flags_are_required_before_any_plan_is_built(capsys, monkeypatch):
    monkeypatch.setattr(probe, 'build_plan', lambda **_: pytest.fail('no plan may be built'))
    assert probe.main(['--execute-live']) == 1
    assert 'needs --out' in capsys.readouterr().out


def test_main_refuses_beside_another_paid_run_before_any_plan_is_built(tmp_path, monkeypatch, capsys):
    _artifacts(tmp_path, monkeypatch)
    _manifest(tmp_path / 'artifacts', 'phase25-2026-09-25/live', name='a-manifest.json', ended_at=None)
    monkeypatch.setattr(probe, 'build_plan', lambda **_: pytest.fail('no plan may be built'))
    code = probe.main(['--execute-live', '--out', 'artifacts/phase27-test/live', '--confirm-entity', 'e',
                       '--expect-plan-hash', 'p', '--expect-harness-sha256', 'h', '--expect-protocol-sha256', 's'])
    assert code == 1 and 'Another paid run' in capsys.readouterr().out


def test_spend_guard_and_budget():
    probe.check_budget(1064, 25.0)
    with pytest.raises(probe.PlanningError, match='exceed'):
        probe.check_budget(1197, 25.0)
    with pytest.raises(probe.PlanningError):
        probe.check_budget(10, 25.01)
    guard = probe.SpendGuard(25.0)
    admitted = 0
    while guard.admit():
        admitted += 1
    assert admitted == 1196


def test_runtime_error_codes_used_by_the_loop_exist():
    assert {'CONNECTION_ERROR', 'REQUEST_TIMEOUT'} <= set(probe.lp.RETRYABLE_TRANSPORT_CODES)
    assert RuntimeProviderError('x', code='EMPTY_FINAL_RESPONSE').code == 'EMPTY_FINAL_RESPONSE'
    assert RuntimeProvider is not None


# ---------------------------------------------------------------- review round 1: live-safety coverage

def test_the_spend_guard_follows_this_harness_cap_not_phase21s(monkeypatch):
    # Review round 1: lapse_probe.SpendGuard refuses any cap above ITS $25, which sits in the pinned file.
    assert issubclass(probe.SpendGuard, probe.lp.SpendGuard) and probe.SpendGuard is not probe.lp.SpendGuard
    assert probe.SpendGuard(probe.HARD_SPEND_CAP).cap == probe.HARD_SPEND_CAP
    monkeypatch.setattr(probe, 'HARD_SPEND_CAP', 39.79)
    with pytest.raises(probe.PlanningError):
        probe.lp.SpendGuard(39.79)
    guard = probe.SpendGuard(39.79)
    admitted = 0
    while guard.admit():
        admitted += 1
    assert admitted == 39_790_000 // 20_900 == 1903
    for bad in (0, -1.0, 39.8, float('nan'), float('inf'), True):
        with pytest.raises(probe.PlanningError):
            probe.SpendGuard(bad)


@needs_phase27_tree
def test_a_raised_cap_gets_past_the_guard_on_a_fake_client(tmp_path, monkeypatch, dry_settings):
    # Review round 2: a raised cap also needs the harness to declare an above-cap option and the review
    # record to carry the owner's answer naming it (test_a_raised_cap_needs_the_owners_above_cap_answer).
    # Review round 3: the configuration is A2 as §10.3 defines it (U2 400, cap $37.20); the round-2 fixture
    # ($40 on R's sizes) is now refused (test_the_owners_option_binds_the_sizes_and_the_cap).
    monkeypatch.setattr(probe, 'HARD_SPEND_CAP', 37.2)
    monkeypatch.setattr(probe, 'DECLARED_OPTION', 'A2')
    monkeypatch.setattr(probe, 'STRATUM_SIZES', A2_SIZES)
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    args.spend_cap = 37.2
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    monkeypatch.setattr(probe, 'openai_client_factory', FakeOpenAI)
    FakeOpenAI.script = []
    assert probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None)) == 0
    manifest = json.loads((tmp_path / args.out / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'COMPLETED' and manifest['spend_cap'] == 37.2 and manifest['phase_spend_cap'] == 37.2
    assert manifest['owner_answer']['option'] == manifest['size_option'] == 'A2'


def _fake_settings(dry_settings, **changes):
    return dataclasses.replace(dry_settings, wandb_api_key='fake-not-a-key', **changes)


DECLARED_PINS = {'configuration_hash': probe.DECLARED_CONFIGURATION_HASH, 'actor_model': probe.EXPECTED_ACTOR_MODEL,
                 'actor_model_settings': {'temperature': 0}, 'per_request_dollar_bound': probe.PER_REQUEST_DOLLAR_BOUND}


def _refused_after_credentials(tmp_path, monkeypatch, args, plan, prompts, settings, match, *, pins=DECLARED_PINS):
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: settings)
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: pins)
    monkeypatch.setattr(probe, 'openai_client_factory', lambda **_: pytest.fail('no provider client may be built'))
    with pytest.raises(probe.PlanningError, match=match):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None))
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()
    assert not (tmp_path / 'artifacts/phase27-test').exists()


def test_the_credential_dependent_checks_each_refuse_before_the_claim(tmp_path, monkeypatch, dry_settings):
    # Review round 1 (M09-M12): entity, project, pins and the Actor model are re-checked after the one
    # credential read; each refuses on its own, with nothing claimed.
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    good = _fake_settings(dry_settings)
    other_entity = SimpleNamespace(**{**vars(args), 'confirm_entity': 'someone-else'})
    _refused_after_credentials(tmp_path, monkeypatch, other_entity, plan, prompts, good, '--confirm-entity must match')
    _refused_after_credentials(tmp_path, monkeypatch, args, plan, prompts,
                               _fake_settings(dry_settings, wandb_project='OtherProject'), 'project is not the declared')
    _refused_after_credentials(tmp_path, monkeypatch, args, plan, prompts, good, 'configuration_hash differs',
                               pins={**DECLARED_PINS, 'configuration_hash': '0' * 64})

    class OtherActor(type(good)):
        def model_for_role(self, role):
            return 'other/model'
    other_actor = OtherActor(**{f.name: getattr(good, f.name) for f in dataclasses.fields(good)})
    _refused_after_credentials(tmp_path, monkeypatch, args, plan, prompts, other_actor,
                               'does not resolve to the declared model')


def test_a_paid_run_that_appears_during_the_launch_checks_is_refused_after_the_credential_read(tmp_path, monkeypatch,
                                                                                              dry_settings):
    # Review round 1 (M03): the other-run check is repeated after the credential read.
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)

    def live_settings(path, *, env_path):
        _manifest(tmp_path / 'artifacts', 'phase26-2026-09-25/live', name='gap-probe-manifest.json', ended_at=None)
        return _fake_settings(dry_settings)
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    monkeypatch.setattr(probe, 'settings_from_file', live_settings)
    with pytest.raises(probe.PlanningError, match='Another paid run'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None))
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()


def test_earlier_runs_that_change_during_the_launch_refuse_the_claim(tmp_path, monkeypatch, dry_settings):
    # Review round 1 (M04): take_claim compares the earlier runs with those the offline checks saw.
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    artifacts = tmp_path / 'artifacts'
    original = probe.take_claim

    def take_claim(*a, **k):
        _manifest(artifacts, 'phase27-test/other', charged_upper_bound=0.0209, statuses={'error': 1})
        _claim(artifacts, 1, 'artifacts/phase27-test/other')
        return original(*a, **k)
    monkeypatch.setattr(probe, 'take_claim', take_claim)
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    monkeypatch.setattr(probe, 'openai_client_factory', lambda **_: pytest.fail('no provider client may be built'))
    with pytest.raises(probe.PlanningError, match='changed during the launch checks; nothing was claimed'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None))
    assert sorted(p.name for p in (artifacts / probe.CLAIM_DIR).iterdir()) == ['claim-01.json']
    assert not (tmp_path / args.out).exists()        # the empty directory this launch made is removed


def test_an_output_directory_that_appears_during_the_launch_refuses_before_the_claim(tmp_path, monkeypatch,
                                                                                    dry_settings):
    # Review round 1: the directory is created exclusively before the claim, never after it.
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    calls = []
    original = probe.check_other_runs

    def check_other_runs(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            (tmp_path / args.out).mkdir(parents=True)
        return original(*a, **k)
    monkeypatch.setattr(probe, 'check_other_runs', check_other_runs)
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    with pytest.raises(probe.PlanningError, match='appeared during the launch checks; nothing was claimed'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None))
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()


@needs_phase27_tree
def test_a_paid_run_that_appears_after_the_claim_stops_this_run_at_zero(tmp_path, monkeypatch, dry_settings):
    # Review round 1: the other-run check runs once more after the claim, before the first provider call.
    artifacts = tmp_path / 'artifacts'
    original = probe.take_claim

    def take_claim(*a, **k):
        result = original(*a, **k)
        _manifest(artifacts, 'phase26-2026-09-25/live', name='gap-probe-manifest.json', ended_at=None,
                  status='RUNNING')
        return result
    monkeypatch.setattr(probe, 'take_claim', take_claim)
    code, manifest, directory = _live(tmp_path, monkeypatch, dry_settings, [report()] * 12)
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == probe.OTHER_RUN_AFTER_CLAIM
    assert 'gap-probe-manifest.json' in manifest['blockers_after_claim'] and manifest['ended_at']
    assert manifest['attempts'] == 0 and manifest['generations_delivered'] == 0 and len(FakeOpenAI.script) == 12
    assert json.loads((directory / 'readouts.json').read_text())['requests_received'] == 0
    # Nothing was delivered, so once the other run is final a new launch is allowed under the rest of the cap.
    monkeypatch.setattr(probe, 'take_claim', original)
    _manifest(artifacts, 'phase26-2026-09-25/live', name='gap-probe-manifest.json')
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [], out='artifacts/phase27-test/live-2')
    assert code == 0 and manifest['claim'].endswith('claim-02.json')


def test_an_active_campaign_seen_after_the_claim_stops_this_run_at_zero(tmp_path, monkeypatch, dry_settings):
    # Review round 2 (N03): the check after the claim reads the backend too, not only the files.
    calls = []

    def status():
        calls.append(1)
        return 'up', {'active_campaign_id': 'campaign-1' if len(calls) >= 3 else None}
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    code, manifest, directory = _live(tmp_path, monkeypatch, dry_settings, [report()] * 12, status=status)
    assert len(calls) == 3
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == probe.OTHER_RUN_AFTER_CLAIM
    assert 'active campaign' in manifest['blockers_after_claim'] and manifest['ended_at']
    assert manifest['other_runs_check'] == {'backend': 'up', 'active_campaign_id': None}
    assert manifest['attempts'] == 0 and manifest['generations_delivered'] == 0 and len(FakeOpenAI.script) == 12
    assert json.loads((directory / 'readouts.json').read_text())['requests_received'] == 0


def test_a_running_past_phase_run_without_a_claim_counts_as_active(tmp_path, monkeypatch):
    # Review round 2 (N10): each exact manifest name of Phases 20, 21 and 23 is watched on its own, with no
    # claim to lean on; a misspelt name would leave a running run unseen.
    artifacts = _artifacts(tmp_path, monkeypatch)
    for relative, name in (('phase20-2026-09-23/run-2', 'dev-probe-manifest.json'),
                           ('phase21-2026-09-23/live-2', 'lapse-probe-manifest.json'),
                           ('phase23-2026-09-24', 'full-loop-manifest.json')):
        path = _manifest(artifacts, relative, name=name, status='RUNNING', ended_at=None) / name
        assert probe.other_paid_runs(root=tmp_path) == [f'artifacts/{relative}/{name}']
        path.write_text(json.dumps({'status': 'COMPLETED', 'ended_at': 'x'}))
    assert probe.other_paid_runs(root=tmp_path) == []


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


@needs_phase27_tree
def test_signal_handlers_are_installed_before_the_claim_and_a_stop_in_set_up_is_recorded(tmp_path, monkeypatch,
                                                                                         dry_settings):
    # Ported from Phase 21 (review round 1, M06): kill -TERM during set-up ends in a final STOPPED manifest.
    events = []
    log = SignalLog(events)
    monkeypatch.setattr(probe.signal, 'signal', log)
    _record_claims(monkeypatch, events)
    original = probe.write_json

    def stop_during_set_up(path, value):
        if path.name == 'plan.json':
            on_disk = json.loads((path.parent / probe.MANIFEST_NAME).read_text())
            events.append(('manifest', on_disk['status'], on_disk['pid']))
            log.handlers[probe.signal.SIGTERM](probe.signal.SIGTERM, None)
        return original(path, value)
    monkeypatch.setattr(probe, 'write_json', stop_during_set_up)
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [report()] * 12)
    assert events[:4] == [('signal', probe.signal.SIGINT), ('signal', probe.signal.SIGTERM), ('claim',),
                          ('manifest', 'STARTING', os.getpid())]
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'operator_stop'
    assert manifest['attempts'] == 0 and manifest['generations_delivered'] == 0 and len(FakeOpenAI.script) == 12


def test_an_operator_stop_before_the_claim_claims_nothing(tmp_path, monkeypatch, dry_settings):
    # Ported from Phase 21 (review round 1, M05).
    events = []
    monkeypatch.setattr(probe.signal, 'signal', SignalLog(events, fire_on_install=probe.signal.SIGTERM))
    _record_claims(monkeypatch, events)
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    with pytest.raises(probe.PlanningError, match='before the claim; nothing was claimed'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None))
    assert ('claim',) not in events
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists() and not (tmp_path / 'artifacts/phase27-test').exists()


def _responses(directory, lines):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'responses.jsonl').write_text(''.join(json.dumps(line) + '\n' for line in lines))


def test_finalize_abandoned_counts_what_a_hard_killed_run_delivered_and_charges_the_in_flight_attempts(
        tmp_path, monkeypatch):
    # Ported from Phase 21 (review round 1, M07).
    artifacts = _artifacts(tmp_path, monkeypatch)
    _claim(artifacts, 1, 'artifacts/phase27-2026-09-24/live')
    _manifest(artifacts, 'phase27-2026-09-24/live', status='RUNNING', ended_at=None, statuses={'ok': 1},
              generations_delivered=1, attempts=1, charged_upper_bound=0.0209)
    served = {'model': 'm', 'system_fingerprint': None, 'prompt_tokens': None, 'completion_tokens': None}
    _responses(artifacts / 'phase27-2026-09-24/live', [
        {'request_id': 'r0001', 'status': 'ok', 'attempts': [{'attempt': 1, 'error': None, 'served': served}]},
        {'request_id': 'r0002', 'status': 'error', 'attempts': [
            {'attempt': 1, 'code': 'CONNECTION_ERROR', 'served': None},
            {'attempt': 2, 'code': 'INVALID_RESPONSE_SHAPE', 'served': served}]}])
    with (artifacts / 'phase27-2026-09-24/live/responses.jsonl').open('a') as handle:
        handle.write('{"request_id": "r0003", "sta')
    monkeypatch.setattr(probe, 'claim_process_alive', lambda pid: False)
    assert probe.main(['--finalize-abandoned', f'artifacts/{probe.CLAIM_DIR}/claim-01.json']) == 0
    manifest = json.loads((artifacts / 'phase27-2026-09-24/live' / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['generations_delivered'] == 2
    assert manifest['statuses'] == {'error': 1, 'ok': 1} and manifest['requests_done'] == 2
    assert manifest['attempts'] == 3 + probe.ABANDONED_IN_FLIGHT_ATTEMPTS
    assert manifest['charged_upper_bound'] == pytest.approx(5 * probe.PER_REQUEST_DOLLAR_BOUND)
    assert manifest['finalized_abandoned']['partial_lines_skipped'] == 1
    assert manifest['finalized_abandoned']['previous_status'] == 'RUNNING'
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase27-2026-09-24/live-2')


def test_a_running_earlier_run_blocks_even_with_nothing_delivered(tmp_path, monkeypatch):
    # Review round 1 (M31): a RUNNING Phase 27 manifest that has delivered nothing yet is not final.
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase27-2026-09-24/live', status='RUNNING', ended_at=None)
    with pytest.raises(probe.PlanningError, match='not final'):
        probe.check_output('artifacts/phase27-2026-09-24/live-2')
    _manifest(artifacts, 'phase27-2026-09-24/live', status='STARTING', ended_at='x')
    with pytest.raises(probe.PlanningError, match='not final'):
        probe.check_output('artifacts/phase27-2026-09-24/live-2')


def test_claim_process_alive_tells_this_harness_from_a_reused_pid():
    # Review round 1 (M08): only a gone process, or a pid now running another program, is "not alive".
    import subprocess
    harness = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'report_word_probe'])
    other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        assert probe.claim_process_alive(harness.pid) is True
        assert probe.claim_process_alive(other.pid) is False
    finally:
        for process in (harness, other):
            process.kill()
            process.wait()
    assert probe.claim_process_alive(harness.pid) is False
    for unknown in (None, 0, -5, 'x', 1.5):
        assert probe.claim_process_alive(unknown) is True


def test_other_runs_never_list_or_open_the_heldout_phases(tmp_path, monkeypatch):
    # Review round 1: past phases by exact manifest name, 25 and 26 by wildcard; Phases 22 and 24 (the
    # heldout-2 seal and its held-out check), heldout2/ and audit/ are neither listed nor opened.
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase24-2026-09-24', name='heldout-manifest.json', ended_at=None)
    _manifest(artifacts, 'phase22-2026-09-24/seal', name='seal-manifest.json', ended_at=None)
    _manifest(artifacts, 'heldout2', name='partition-manifest.json', ended_at=None)
    _manifest(artifacts, 'phase20-2026-09-23/run-1', name='dev-probe-manifest.json')
    _manifest(artifacts, 'phase23-2026-09-24', name='full-loop-manifest.json')
    _manifest(artifacts, 'phase24-2026-09-24/check', name='check-manifest.json')
    (artifacts / 'top-manifest.json').write_text(json.dumps({'status': 'COMPLETED', 'ended_at': 'x'}))
    _claim(artifacts, 1, 'artifacts/phase24-2026-09-24', directory='phase24-live-claims')
    _claim(artifacts, 1, 'artifacts/phase24-2026-09-24/check', directory='phase21-live-claims')
    _claim(artifacts, 2, 'artifacts/phase21-2026-09-23/../phase24-2026-09-24', directory='phase21-live-claims')
    _claim(artifacts, 3, 'artifacts/phase21-2026-09-23/..', directory='phase21-live-claims')
    opened = []
    original = pathlib.Path.read_text

    def spy(self, *args, **kwargs):
        opened.append(str(self))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, 'read_text', spy)
    active = probe.other_paid_runs(root=tmp_path)
    monkeypatch.undo()
    # A claim naming another phase's directory, or leaving the run directory, counts as running unread.
    assert active == ['artifacts/phase21-live-claims/claim-01.json', 'artifacts/phase21-live-claims/claim-02.json',
                      'artifacts/phase21-live-claims/claim-03.json']
    inside = [path.split('/artifacts/', 1)[-1] for path in opened]
    assert not any(part in path for path in inside
                   for part in ('phase24-2026', 'phase22-', 'heldout2', 'audit', 'top-manifest'))
    assert any(path.endswith('dev-probe-manifest.json') for path in opened)
    assert any(path.endswith('full-loop-manifest.json') for path in opened)
