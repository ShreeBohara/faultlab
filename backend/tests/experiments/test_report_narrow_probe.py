"""Offline checks of the Phase 30 narrow report-field probe. No provider call, no .env read, no store write."""
import asyncio
import dataclasses
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import random
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('report_narrow_probe', ROOT / 'scripts/experiments/report_narrow_probe.py')
probe = importlib.util.module_from_spec(SPEC)
sys.modules['report_narrow_probe'] = probe
SPEC.loader.exec_module(probe)
rwp = probe.rwp

STORE = ROOT / 'artifacts/lab.sqlite3'

# The Phase 17 settings file lives under the git-ignored artifacts/ folder, so a fresh clone does not have it.
# Tests that read it skip there with this reason (as test_run_dev_probe.py and test_run_gap_probe.py already
# do); where the file exists they run unchanged.
PHASE17_SETTINGS_ABSENT = not (ROOT / probe.DECLARED_SETTINGS).is_file()
NO_PHASE17_SETTINGS = ('needs the Phase 17 settings file (artifacts/phase16-2026-09-22/settings-phase17.json; '
                       'git-ignored, so a fresh clone does not have it)')
needs_phase17_settings = pytest.mark.skipif(PHASE17_SETTINGS_ABSENT, reason=NO_PHASE17_SETTINGS)


def _tree_is_phase22_configuration():
    """Phase 30 is pinned to the Phase 22 configuration (2cf63e93...). A later backend/app change moves the
    hash and the harness then refuses to plan, by design; the tests that plan are skipped there."""
    try:
        if not (STORE.exists() and probe.PHASE20_STORE.exists() and probe.PHASE27_PLAN.exists()):
            return False
        if probe.sha256_file(probe.PHASE20_STORE) != rwp.PHASE20_STORE_SHA256:
            return False
        settings = probe.settings_from_file(ROOT / probe.DECLARED_SETTINGS, env_path=os.devnull)
        return probe.configuration_pins(settings)['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    except Exception:
        return False


PHASE22_TREE = _tree_is_phase22_configuration()
needs_tree = pytest.mark.skipif(not PHASE22_TREE, reason='not the Phase 22 configuration or stores absent')
REPORT = ('{{"kind":"report","report":{{"upgrade_outcome":"{up}","notification_outcome":"{note}",'
          '"overall":"SAFE_UNRESOLVED","evidence_ids":["obs-1"],"next_action":{{"kind":"NONE"}}}}}}')
POLL = '{"kind":"tool","tool":"get_operation_status","arguments":{"service":"notifications"}}'


def report(up='SUCCEEDED', note='UNKNOWN'):
    return REPORT.format(up=up, note=note)


def facts(status, *, seen=None, writes=0, receipt=None):
    return {'status': status, 'receipt': receipt, 'seen': sorted(seen if seen is not None else ([status] if status else [])),
            'writes': writes}


def context(upgrade, notification, stated=None):
    return {'upgrade': upgrade, 'notification': notification,
            'reference': list(rwp.reference_words(upgrade, notification)),
            'stated': stated or {'orders': None, 'notifications': None}}


PHASE24 = context(facts('UNKNOWN', writes=2), facts(None))                                           # U1
LAPSE_AFTER_SEND = context(facts('SUCCEEDED', receipt='SUCCEEDED', writes=1), facts('UNKNOWN', writes=2))  # U2
LAPSE_NEVER_SENT = context(facts('SUCCEEDED', receipt='SUCCEEDED', writes=1), facts('UNKNOWN', writes=0))  # U3
REJECTED = context(facts('FAILED', receipt='FAILED', writes=1), facts(None))                         # G4


# ---------------------------------------------------------------- imports and pins

def test_the_rebuild_and_word_rule_are_phase27s_pinned_harness(tmp_path, monkeypatch):
    assert probe.sha256_file(probe.PHASE27_HARNESS) == probe.PHASE27_HARNESS_SHA256
    assert rwp.__file__ == str(probe.PHASE27_HARNESS)
    assert probe.lp is rwp.lp and probe.lp.__file__ == str(rwp.PHASE21_HARNESS)
    assert probe.phase27_harness_problem() is None
    # The field, its note and the word rule are Phase 27's objects, not copies.
    assert probe.T2_FIELD == rwp.T_FIELD == 'last_observed_status' and probe.T2_NOTE is rwp.T_NOTE
    altered = tmp_path / 'report_word_probe.py'
    altered.write_text(probe.PHASE27_HARNESS.read_text() + '\n# edited\n')
    monkeypatch.setattr(probe, 'PHASE27_HARNESS', altered)
    assert 'not the pinned Phase 27 harness' in probe.phase27_harness_problem()
    with pytest.raises(probe.PlanningError, match='not the pinned Phase 27 harness'):
        probe.check_files()
    monkeypatch.undo()
    altered21 = tmp_path / 'lapse_probe.py'
    altered21.write_text(rwp.PHASE21_HARNESS.read_text() + '\n# edited\n')
    monkeypatch.setattr(rwp, 'PHASE21_HARNESS', altered21)
    assert 'not the pinned Phase 21 harness' in probe.phase27_harness_problem()


@needs_phase17_settings
def test_the_process_rule_is_phase26s_pinned_runner_and_fails_closed(tmp_path, monkeypatch):
    assert probe.sha256_file(probe.PHASE26_RUNNER) == probe.PHASE26_RUNNER_SHA256
    assert probe.phase26_runner_problem() is None
    altered = tmp_path / 'run_gap_probe.py'
    altered.write_text(probe.PHASE26_RUNNER.read_text() + '\n# edited\n')
    monkeypatch.setattr(probe, 'PHASE26_RUNNER', altered)
    entries = probe.experiment_processes()
    assert len(entries) == 1 and 'not the pinned Phase 26 runner' in entries[0]
    with pytest.raises(probe.PlanningError, match='not the pinned Phase 26 runner'):
        probe.check_files()


def test_phase26s_token_rule_skips_the_caffeinate_helper_and_this_process_tree():
    module = probe._phase26_runner()
    assert module.__file__ == str(probe.PHASE26_RUNNER)
    script = 'scripts/experiments/report_narrow_probe.py'
    assert module.paid_run_script(f'/x/.venv/bin/python {script} --execute-live --out a') == script
    assert module.paid_run_script(f'python3.12 -B {script} --exec') == script           # an argparse prefix
    assert module.paid_run_script(f'caffeinate -is ./.venv/bin/python {script} --execute-live') is None
    assert module.paid_run_script(f'grep -E "report_narrow_probe|--execute-live" x') is None
    assert module.paid_run_script(f'./.venv/bin/python {script}') is None                  # a dry run
    me = os.getpid()
    rows = [(me, 1, f'./.venv/bin/python {script} --execute-live'),
            (me + 100000, me, f'caffeinate -is ./.venv/bin/python {script} --execute-live'),
            (me + 100001, me, f'./.venv/bin/python {script} --execute-live'),          # a descendant of this run
            (me + 100002, 1, './.venv/bin/python scripts/experiments/slot2_probe.py --execute-live')]
    found = module.live_experiment_processes(reader=lambda: rows)
    assert found == [f'pid {me + 100002}: scripts/experiments/slot2_probe.py --execute-live']
    assert module.live_experiment_processes(reader=lambda: (_ for _ in ()).throw(OSError()))[0].startswith(
        'the process list could not be read')


@needs_tree
def test_phase27s_sent_plan_and_readouts_are_the_pinned_files(tmp_path):
    sent, reference = probe.phase27_reference()
    assert len(sent['U2']) == 225 and reference == {
        'u2_prompts': 225, 'c_bad_worst_case': 4, 't_bad_worst_case': 0, 'c_only_bad': 4, 't_only_bad': 0,
        'source': reference['source']}
    edited = tmp_path / 'plan.json'
    edited.write_bytes(probe.PHASE27_PLAN.read_bytes() + b'\n')
    with pytest.raises(probe.PlanningError, match='pinned sent plan'):
        probe.phase27_reference(plan_path=edited)
    with pytest.raises(probe.PlanningError, match='pinned read-out'):
        probe.phase27_reference(readouts_path=edited)


# ---------------------------------------------------------------- the real dry plan (read-only, $0)

@pytest.fixture(scope='module')
def real_plan():
    if not PHASE22_TREE:
        pytest.skip('not the Phase 22 configuration or stores absent')
    return probe.build_plan()


@needs_tree
def test_dry_plan_verifies_every_turn_and_the_structural_guard_holds(real_plan):
    plan, _ = real_plan
    assert plan['verification']['failed'] == 0 and plan['verification']['verified'] == 17119
    pre = plan['precheck']
    assert pre['passed'] is True and pre['problem_examples'] == []
    for key in probe.PRECHECK_ZERO:
        assert pre[key] == 0, key
    # T2's whole reach in development data: 781 report-required report turns of U1, U2 and U3.
    assert pre['in_window_turns'] == 781 and pre['out_of_window_turns'] == 17119 - 781
    assert {k: v for k, v in pre.items() if k.startswith('in_window_report_turns:')} == {
        'in_window_report_turns:U1': 52, 'in_window_report_turns:U2': 667, 'in_window_report_turns:U3': 62}
    # Every prompt of Phase 27's guard strata is outside the window and byte-identical to the control.
    assert pre['phase27_guard_prompts'] == pre['phase27_guard_prompts_identical_to_control'] == 2070
    assert pre['phase27_guard_prompts:G4'] == 286 and pre['phase27_guard_prompts_in_window'] == 0
    assert pre['terminal_rejection_case_turns'] > 1000 and pre['terminal_rejection_case_turns_in_window'] == 0
    assert plan['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    assert plan['phase27_harness_sha256'] == probe.PHASE27_HARNESS_SHA256
    assert plan['phase26_runner_sha256'] == probe.PHASE26_RUNNER_SHA256
    assert plan['freeze_sha256'] == probe.FREEZE_SHA256
    structural = probe.structural_readout(pre)
    assert structural['status'] == 'PASS' and structural['phase27_guard_prompts_by_stratum']['G4'] == 286


@needs_tree
def test_declared_populations_arms_and_exact_request_count(real_plan):
    plan, prompts = real_plan
    assert plan['populations']['chosen'] == {'U2': 316, 'U1': 52, 'U3': 62}
    assert plan['populations']['excluded'] == {'U2:sent_in_phase27': 225}
    assert plan['sampling']['available'] == {'U1': 52, 'U2': 442, 'U3': 62}
    counts = plan['counts']
    assert counts['total_requests'] == 860 and counts['distinct_prompts'] == len(prompts) == 860
    assert counts['by_population'] == {'primary': 632, 'guard': 228}
    assert counts['by_stratum_and_arm'] == {'U1/R': 52, 'U1/T2': 52, 'U2/C': 316, 'U2/T2': 316,
                                            'U3/R': 62, 'U3/T2': 62}
    assert plan['cost']['planned_upper_bound'] == pytest.approx(17.974)
    assert plan['cost']['spend_cap'] == probe.HARD_SPEND_CAP == probe.PROGRAM_PHASE_CAP == 20.0
    assert plan['cost']['retry_headroom_attempts'] == 96
    cells = plan['sampling']['allocation']['U2']
    total = sum(v['available'] for v in cells.values())
    for v in cells.values():
        assert abs(v['chosen'] - 316 * v['available'] / total) < 1
    order = [r['population'] for r in plan['requests']]
    assert order == sorted(order, key=probe.POPULATION_ORDER.index)
    seen, last = set(), None
    for request in plan['requests']:
        if request['prompt_id'] != last:
            assert request['prompt_id'] not in seen
            seen.add(request['prompt_id'])
            last = request['prompt_id']
    assert plan['thresholds']['ni_margin'] == '3/200' and plan['thresholds']['ni_alpha'] == 0.024
    assert plan['thresholds']['guard_alone_stratum'] == 'U3'


@needs_tree
def test_no_u2_prompt_phase27_sent_is_sent_again_and_u1_is_every_prompt(real_plan):
    plan, _ = real_plan
    phase27 = json.loads(probe.PHASE27_PLAN.read_text())
    sent27 = {r['prompt_id'] for r in phase27['requests'] if r['stratum'] == 'U2'}
    u1_27 = {r['prompt_id'] for r in phase27['requests'] if r['stratum'] == 'U1'}
    ours = {s: {r['prompt_id'] for r in plan['requests'] if r['stratum'] == s} for s in ('U1', 'U2', 'U3')}
    assert len(sent27) == 225 and not (ours['U2'] & sent27)
    assert ours['U1'] == u1_27 and len(ours['U1']) == 52
    assert not (ours['U3'] & {r['prompt_id'] for r in phase27['requests']})


@needs_tree
def test_every_request_is_in_window_the_control_is_stored_and_t2_is_phase27s_t(real_plan):
    plan, prompts = real_plan
    by_prompt = {}
    for request in plan['requests']:
        assert request['t2_window'] is True and request['final_report_required'] is True
        assert request['stratum'] in ('U1', 'U2', 'U3') and request['arm'] in probe.STRATUM_ARMS[request['stratum']]
        by_prompt.setdefault(request['prompt_id'], {})[request['arm']] = prompts[request['request_hash']]
    for prompt_id, arms in by_prompt.items():
        control = arms.get('C') or arms.get('R')
        treated = arms['T2']
        assert control['messages'][:-1] == treated['messages'][:-1]
        before = json.loads(control['messages'][-1]['content'])
        after = json.loads(treated['messages'][-1]['content'])
        assert set(after) - set(before) == {probe.T2_FIELD} and {k: after[k] for k in before} == before
        assert sorted(after).index(probe.T2_FIELD) == 1 and after[probe.T2_FIELD]['note'] == probe.T2_NOTE
        assert any(v and v['status'] == 'UNKNOWN' for k, v in after[probe.T2_FIELD].items() if k != 'note')
        assert control['response_format'] == treated['response_format']


@needs_tree
def test_every_request_is_a_development_episode_before_the_cutoff(real_plan):
    plan, _ = real_plan
    connection = sqlite3.connect(STORE.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        main = {i: json.loads(p) for i, p in connection.execute(
            "select id,payload from records where kind='episodes' and json_extract(payload,'$.split')='development'")}
    finally:
        connection.close()
    for request in plan['requests']:
        if request['source'] == 'main':
            episode = main[request['episode_id']]
            assert episode['experiment_purpose'] == 'completion_study' and episode['lifecycle'] == 'COMPLETED'
            assert rwp.lp.before_cutoff(episode['started_at'], probe.STORE_CUTOFF)
        else:
            assert request['source'] == 'phase20' and request['stratum'] == 'U1'


def test_build_plan_never_reads_env_and_refuses_a_failed_precheck(monkeypatch):
    if not PHASE22_TREE:
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


def test_build_plan_refuses_a_cap_above_the_programs(monkeypatch):
    monkeypatch.setattr(probe, 'HARD_SPEND_CAP', 20.01)
    with pytest.raises(probe.PlanningError, match="above the program's"):
        probe.build_plan()


@needs_phase17_settings
def test_build_plan_refuses_an_altered_settings_file(tmp_path):
    settings = tmp_path / 'settings.json'
    settings.write_text((ROOT / probe.DECLARED_SETTINGS).read_text() + '\n')
    with pytest.raises(probe.PlanningError, match='not the declared Phase 17 settings file'):
        probe.build_plan(settings_path=settings)


# ---------------------------------------------------------------- the window (pure)

def _stated(orders=None, notifications=None):
    return {'note': probe.T2_NOTE, 'orders': orders, 'notifications': notifications}


UNKNOWN_NOTE = {'evidence': 'obs-6', 'status': 'UNKNOWN'}
SUCCEEDED_UP = {'evidence': 'obs-3', 'status': 'SUCCEEDED'}


@pytest.mark.parametrize('final,field,upgrade,expected', [
    (True, _stated(SUCCEEDED_UP, UNKNOWN_NOTE), facts('SUCCEEDED', receipt='SUCCEEDED'), True),        # U2
    (True, _stated({'evidence': 'obs-4', 'status': 'UNKNOWN'}, None), facts('UNKNOWN', writes=2), True),   # U1
    (False, _stated(SUCCEEDED_UP, UNKNOWN_NOTE), facts('SUCCEEDED'), False),                            # voluntary
    (None, _stated(SUCCEEDED_UP, UNKNOWN_NOTE), facts('SUCCEEDED'), False),
    (1, _stated(SUCCEEDED_UP, UNKNOWN_NOTE), facts('SUCCEEDED'), False),                                # only True
    (True, _stated(SUCCEEDED_UP, {'evidence': 'obs-6', 'status': 'PENDING'}), facts('SUCCEEDED'), False),
    (True, _stated({'evidence': 'obs-2', 'status': 'PENDING'}, None), facts('PENDING'), False),        # G1
    (True, _stated({'evidence': 'obs-2', 'status': 'FAILED'}, None), facts('FAILED'), False),          # rejection
    (True, _stated({'evidence': 'obs-2', 'status': 'FAILED'}, UNKNOWN_NOTE), facts('FAILED'), False),
    (True, _stated({'evidence': 'obs-5', 'status': 'UNKNOWN'}, None),
     facts('UNKNOWN', seen=['FAILED', 'UNKNOWN'], writes=1), False),                                   # FAILED seen earlier
    (True, _stated(None, None), facts(None), False),
])
def test_the_t2_window(final, field, upgrade, expected):
    assert probe.t2_window(final, field, upgrade) is expected


def test_t2_is_phase27s_t_in_window_and_the_control_outside_it():
    history = [{'role': 'system', 'content': 's'}]
    user = {'final_report_required': True, 'observations': [], 'remaining_actor_calls': 1}
    field = _stated(SUCCEEDED_UP, UNKNOWN_NOTE)
    control = rwp.arm_messages(history, user, 'C', field)
    assert probe.arm_messages(history, user, 'C', field, True) == control
    assert probe.arm_messages(history, user, 'R', field, True) == control
    assert probe.arm_messages(history, user, 'T2', field, True) == rwp.arm_messages(history, user, 'T', field) != control
    assert probe.arm_messages(history, user, 'T2', field, False) == control
    with pytest.raises(probe.PlanningError):
        probe.arm_messages(history, user, 'P', field, True)


INTENT = {'schema_version': 'faultlab/v1', 'task_id': 'task-1', 'order_id': 'order-1', 'desired_shipping': 'express',
          'expected_version': 1, 'template_version': 'confirmation/v1', 'upgrade_operation_id': 'upgrade-1',
          'notification_operation_id': 'notify-1', 'upgrade_idempotency_key': 'key-u', 'notification_idempotency_key': 'key-n',
          'upgrade_intent_hash': 'a' * 64, 'notification_intent_hash': 'b' * 64, 'task_text': 'Upgrade, then confirm.'}


def _observation(index, *, tool='get_operation_status', transport='ok', status='UNKNOWN', service='orders', data=True,
                 receipt=None):
    operation = INTENT['upgrade_operation_id'] if service == 'orders' else INTENT['notification_operation_id']
    intent_hash = INTENT['upgrade_intent_hash'] if service == 'orders' else INTENT['notification_intent_hash']
    receipt_body = None
    if receipt:
        receipt_body = {'receipt_id': f'rc-{index}', 'service': service, 'operation_id': operation,
                        'order_id': INTENT['order_id'], 'intent_hash': intent_hash, 'status': receipt,
                        'terminal_tick': index}
    result = {'call_id': f'call-{index}', 'tool': tool, 'transport': transport, 'operation_id': operation,
              'order_id': INTENT['order_id'], 'status': status if data else None,
              'error_code': None if data else 'TRANSIENT_UNAVAILABLE', 'observed_version': None,
              'receipt_id': receipt_body['receipt_id'] if receipt_body else None, 'retry_after_ticks': None,
              'data': ({'operation_id': operation, 'service': service, 'order_id': INTENT['order_id'],
                        'intent_hash': intent_hash, 'status': status, 'receipt': receipt_body} if data else None)}
    return {'schema_version': 'faultlab/v1', 'evidence_id': f'ev-{index}', 'episode_id': 'episode-x',
            'call_id': f'call-{index}', 'delivered_tick': index, 'result': result}


def _runtime_window(final, observations):
    intent = rwp.TaskIntent.model_validate_json(json.dumps(INTENT))
    models = [rwp.PublicObservation.model_validate_json(json.dumps(o)) for o in observations]
    upgrade = rwp.operation_facts(models, intent, 'orders')
    return probe.t2_window(final, rwp.status_field(models, intent), upgrade)


@pytest.mark.parametrize('final,observations,expected', [
    (True, [_observation(1, tool='update_order', transport='error', data=False), _observation(2)], True),     # U1-like
    (True, [_observation(1, status='SUCCEEDED', tool='update_order', receipt='SUCCEEDED'),
            _observation(2, service='notifications', tool='send_confirmation', transport='error', data=False),
            _observation(3, service='notifications')], True),                                                 # U2-like
    (False, [_observation(1, tool='update_order', transport='error', data=False), _observation(2)], False),
    (True, [_observation(1, status='PENDING', tool='update_order'), _observation(2, status='FAILED',
                                                                               receipt='FAILED')], False),
    (True, [_observation(1, status='FAILED', tool='update_order', receipt='FAILED'),
            _observation(2, service='notifications')], False),                                                # rejected
    (True, [_observation(1, status='PENDING', tool='update_order')], False),
    (True, [], False),
])
def test_the_independent_window_agrees_with_the_runtime_window(final, observations, expected):
    assert _runtime_window(final, observations) is expected
    assert probe.independent_t2_window(final, observations, INTENT) is expected


# ---------------------------------------------------------------- the survey's pre-check on synthetic turns

U2_OBSERVATIONS = [_observation(1, status='SUCCEEDED', tool='update_order', receipt='SUCCEEDED'),
                   _observation(2, service='notifications', tool='send_confirmation', transport='error', data=False),
                   _observation(3, service='notifications')]
G4_OBSERVATIONS = [_observation(1, status='FAILED', tool='update_order', receipt='FAILED')]


def _survey_turn(actor_turn, observations, *, final, klass='report', stored=None):
    """One verified turn as report_word_probe.survey_episode(keep=True) returns it."""
    intent = rwp.TaskIntent.model_validate_json(json.dumps(INTENT))
    models = [rwp.PublicObservation.model_validate_json(json.dumps(o)) for o in observations]
    upgrade, notification = rwp.operation_facts(models, intent, 'orders'), rwp.operation_facts(models, intent, 'notifications')
    field = rwp.status_field(models, intent)
    user = {'final_report_required': final, 'observations': observations, 'remaining_actor_calls': 1}
    history = [{'role': 'system', 'content': 's'}]
    control = rwp.arm_messages(history, user, 'C', field)
    return {'actor_turn': actor_turn, 'verified': True, 'final_report_required': final,
            'historical': {'class': klass}, 'response_contract': 'actor_final_report' if final else None,
            'context': {'upgrade': upgrade, 'notification': notification,
                        'reference': list(rwp.reference_words(upgrade, notification)),
                        'stated': {service: field[service] for service in probe.SERVICES}},
            'field': field, 'history': history, 'user': user,
            'stored_messages_hash': stored or probe.content_hash(control)}


def _survey(monkeypatch, episodes):
    """episodes: {episode_id: [(turn, observations), ...]} in the main source; phase20 empty."""
    monkeypatch.setattr(rwp, 'eligible_episodes', lambda connection, source, cutoff=None, cases=None: [
        (eid, {'episode_id': eid, 'source': 'main', 'case': 'c', 'arm': 'B0'}) for eid in episodes] if source == 'main' else [])
    monkeypatch.setattr(probe.lp, 'load_events', lambda connection, eid: [
        {'type': 'actor_output', 'payload': {'actor_context_protocol': probe.ACTOR_CONTEXT_PROTOCOL_V4, 'episode': eid}}])
    monkeypatch.setattr(probe.lp, 'load_intent', lambda connection, eid: INTENT)
    monkeypatch.setattr(rwp, 'survey_episode', lambda events, intent, summary, keep=False: (
        [turn for turn, _ in episodes[summary['episode_id']]],
        probe.Counter(turns=len(episodes[summary['episode_id']]), verified=len(episodes[summary['episode_id']]),
                      content_disagreements=0), []))
    monkeypatch.setattr(rwp, 'turn_observations', lambda events: [
        (observations, None) for _, observations in episodes[events[0]['payload']['episode']]])
    return probe.survey({'main': None, 'phase20': None})


def test_the_survey_pre_check_passes_a_clean_store_and_catches_each_violation(monkeypatch):
    clean = {'e-u2': [(_survey_turn(3, U2_OBSERVATIONS, final=False, klass='tool'), U2_OBSERVATIONS),
                      (_survey_turn(8, U2_OBSERVATIONS, final=True), U2_OBSERVATIONS)],
             'e-g4': [(_survey_turn(4, G4_OBSERVATIONS, final=False), G4_OBSERVATIONS)]}
    reports, verification, pre = _survey(monkeypatch, clean)
    assert pre['passed'] is True and verification['verified'] == 3
    assert pre['in_window_turns'] == 1 and pre['out_of_window_turns'] == 2
    assert pre['phase27_guard_prompts'] == pre['phase27_guard_prompts_identical_to_control'] == 1
    assert [(s['episode_id'], t['stratum']) for s, t in reports] == [('e-u2', 'U2')]
    violations = {
        'control_differs_from_stored': {'e-u2': [(_survey_turn(8, U2_OBSERVATIONS, final=True, stored='0' * 64),
                                                  U2_OBSERVATIONS)]},
        'in_window_after_earlier_in_window_turn': {'e-u2': [(_survey_turn(7, U2_OBSERVATIONS, final=True), U2_OBSERVATIONS),
                                                            (_survey_turn(8, U2_OBSERVATIONS, final=True), U2_OBSERVATIONS)]},
        'in_window_non_report_turns': {'e-u2': [(_survey_turn(8, U2_OBSERVATIONS, final=True, klass='other'),
                                                 U2_OBSERVATIONS)]},
        'window_rule_disagreements': {'e-u2': [(_survey_turn(8, U2_OBSERVATIONS, final=True), U2_OBSERVATIONS[:1])]},
    }
    for key, episodes in violations.items():
        _, _, pre = _survey(monkeypatch, {**episodes, 'e-g4': clean['e-g4']})
        assert pre[key] >= 1 and pre['passed'] is False, key
    # No Phase 27 guard prompt at all is not a pass either: the structural guard must have something to hold.
    _, _, pre = _survey(monkeypatch, {'e-u2': clean['e-u2']})
    assert pre['passed'] is False


# ---------------------------------------------------------------- populations (pure)

def _report_turn(episode, turn, ctx, stratum, *, source='main', case='c', arm='B0'):
    summary = {'episode_id': episode, 'source': source, 'case': case, 'arm': arm}
    return summary, {'actor_turn': turn, 'final_report_required': True, 'stratum': stratum, 'context': ctx,
                     'historical': {'class': 'report', 'notification_outcome': 'UNKNOWN',
                                    'report_fields': {'upgrade_outcome': ctx['reference'][0]}}}


def test_population_selection_excludes_phase27s_prompts_and_is_order_independent():
    reports = [_report_turn(f'e-u2-{i}', 8, LAPSE_AFTER_SEND, 'U2', arm=('B0', 'L')[i % 2]) for i in range(20)]
    reports += [_report_turn(f'e-u1-{i}', 8, PHASE24, 'U1', source='phase20') for i in range(3)]
    reports += [_report_turn(f'e-u3-{i}', 8, LAPSE_NEVER_SENT, 'U3') for i in range(4)]
    reports.append(_report_turn('e-other', 8, PHASE24, 'U_other'))
    sent = {'U2': [f'main:e-u2-{i}:8' for i in range(5)]}
    selection = probe.select_populations(reports, sent, sizes={'U2': 10, 'U1': None, 'U3': None})
    chosen = {s: sorted(p[0]['episode_id'] for p in pairs) for s, pairs in selection['chosen'].items()}
    assert len(chosen['U2']) == 10 and not set(chosen['U2']) & {f'e-u2-{i}' for i in range(5)}
    assert len(chosen['U1']) == 3 and len(chosen['U3']) == 4
    assert selection['excluded'] == {'U2:sent_in_phase27': 5, 'U_other:not_sent': 1}
    shuffled = list(reports)
    random.Random(7).shuffle(shuffled)
    again = probe.select_populations(shuffled, sent, sizes={'U2': 10, 'U1': None, 'U3': None})
    assert {s: [p[0]['episode_id'] for p in v] for s, v in again['chosen'].items()} == \
        {s: [p[0]['episode_id'] for p in v] for s, v in selection['chosen'].items()}
    # A Phase 27 prompt that is no longer a U2 prompt means the populations changed: nothing is planned.
    with pytest.raises(probe.PlanningError, match='populations changed'):
        probe.select_populations(reports, {'U2': sent['U2'] + ['main:e-missing:8']}, sizes={'U2': 10})


def test_the_sample_uses_this_phases_seed():
    pairs = [_report_turn(f'e-{i}', 8, LAPSE_AFTER_SEND, 'U2') for i in range(30)]
    chosen, _ = probe.allocate_sample('U2', pairs, 5)
    expected = sorted(pairs, key=lambda p: probe.rank('U2', probe.prompt_key(*p)))[:5]
    assert [p[0]['episode_id'] for p in chosen] == [p[0]['episode_id'] for p in expected]
    assert probe.rank('x') != rwp.rank('x') and probe.SAMPLE_SEED == 'faultlab-phase30-2026-09-25'


# ---------------------------------------------------------------- statistics (pure)

def _brute_force_score(b, c, n, d):
    """Tango's statistic with the restricted MLE found numerically (golden section), for cross-checking."""
    def loglik(q):
        p10, p01 = q + d, q
        rest = 1 - p10 - p01
        if p10 <= 0 or p01 <= 0 or rest <= 0:
            return -math.inf
        return b * math.log(p10) + c * math.log(p01) + (n - b - c) * math.log(rest)
    low, high = max(0.0, -d) + 1e-12, (1 - d) / 2 - 1e-12
    ratio = (math.sqrt(5) - 1) / 2
    for _ in range(300):
        a, e = high - ratio * (high - low), low + ratio * (high - low)
        if loglik(a) < loglik(e):
            low = a
        else:
            high = e
    q = (low + high) / 2
    return (b - c - n * d) / math.sqrt(n * (2 * q + d * (1 - d)))


@pytest.mark.parametrize('b,c,n,d', [(3, 3, 316, 0.02), (6, 6, 316, 0.02), (0, 6, 316, 0.02), (2, 9, 316, 0.02),
                                     (10, 1, 200, 0.03), (4, 7, 100, 0.05), (1, 1, 50, 0.1)])
def test_tango_matches_a_numerical_restricted_mle(b, c, n, d):
    assert probe.tango_z(b, c, n, d) == pytest.approx(_brute_force_score(b, c, n, d), abs=1e-6)


def test_tango_closed_forms_and_edges():
    # b = c = 0: the restricted p01 is 0, so z = -sqrt(n d / (1 - d)).
    assert probe.tango_z(0, 0, 316, 0.02) == pytest.approx(-math.sqrt(316 * 0.02 / 0.98))
    assert probe.tango_z(0, 0, 0, 0.02) is None and probe.tango_z(5, 5, 8, 0.02) is None
    assert probe.tango_z(1, 1, 10, 1.0) is None
    assert probe.normal_cdf(0) == 0.5 and probe.normal_cdf(-1.959963984540054) == pytest.approx(0.025)
    # More T2-only bad prompts can only make non-inferiority harder; more C-only bad prompts easier.
    ps = [probe.noninferiority(b, 3, 316)[1] for b in range(0, 12)]
    assert ps == sorted(ps)
    qs = [probe.noninferiority(3, c, 316)[1] for c in range(0, 12)]
    assert qs == sorted(qs, reverse=True)


def test_non_inferiority_boundaries_at_the_declared_size():
    # Review round 1 (S2): margin 1.5 points at one-sided 0.024 (exact size at the margin below 0.025).
    assert probe.NI_MARGIN == probe.Fraction(3, 200) and probe.NI_ALPHA == 0.024
    passes = lambda b, c: probe.noninferiority(b, c, 316)[1] < probe.NI_ALPHA  # noqa: E731
    # The most T2-only bad prompts that still pass, by C-only bad prompts: 0 0 1 2 2 3 3.
    for c, most in enumerate((0, 0, 1, 2, 2, 3, 3)):
        assert passes(most, c) and not passes(most + 1, c), c
    assert not passes(1, 1) and passes(0, 0)
    # The upper bound inverts the same test.
    for b, c in ((0, 0), (2, 5), (6, 6), (9, 2), (1, 1)):
        bound = probe.difference_upper_bound(b, c, 316)
        assert probe.noninferiority(b, c, 316, bound + 1e-6)[1] < probe.NI_ALPHA
        assert probe.noninferiority(b, c, 316, bound - 1e-6)[1] >= probe.NI_ALPHA
        assert (bound < 0.015) == passes(b, c)


# ---------------------------------------------------------------- read-outs (pure)

def _requests(stratum, n, arms, ctx, *, start=0):
    rows = []
    for i in range(n):
        for arm in arms:
            rows.append({'request_id': f'{stratum}-{start + i}-{arm}', 'population': probe.STRATUM_POPULATION[stratum],
                         'stratum': stratum, 'prompt_id': f'{stratum}:{start + i}', 'arm': arm, 'repeat': 0,
                         'source': 'main', 'case': 'c', 'episode_arm': 'B0', 'context': ctx,
                         'final_report_required': True, 't2_window': True,
                         'historical': {'raw_sha256': 'h', 'report_fields': {'overall': 'SAFE_UNRESOLVED'}}})
    return rows


def _result(request, raw, status='ok'):
    result = {'request_id': request['request_id'], 'status': status, 'raw': raw if status == 'ok' else None,
              'raw_sha256': hashlib.sha256(raw.encode()).hexdigest() if status == 'ok' else None}
    result.update(rwp.classify(raw) if status == 'ok' else {'class': None, 'detail': status,
                                                            'notification_outcome': None, 'report': None})
    return result


PASSED_PRECHECK = {'passed': True, 'phase27_guard_prompts': 2070, 'phase27_guard_prompts_in_window': 0,
                   'phase27_guard_prompts_identical_to_control': 2070}
REFERENCE = {'u2_prompts': 225, 'c_bad_worst_case': 4, 't_bad_worst_case': 0, 'c_only_bad': 4, 't_only_bad': 0,
             'source': 'test'}


def _plan(rows, precheck=None):
    return {'requests': rows, 'precheck': PASSED_PRECHECK if precheck is None else precheck,
            'phase27_u2_reference': REFERENCE}


def _run(*, n=300, c_slips=(), t2_slips=(), t2_other=(), missing=(), polls=(), m=100, t2_guard_bad=(),
         r_guard_bad=(), guard_missing=(), precheck=None):
    """U2: n prompts (C, T2); U3: m prompts (R, T2). Index sets name the prompts affected; missing and polls
    are (arm, stratum, index) triples."""
    rows = _requests('U2', n, ('C', 'T2'), LAPSE_AFTER_SEND) + _requests('U3', m, ('R', 'T2'), LAPSE_NEVER_SENT)
    results = []
    for request in rows:
        i, arm, stratum = int(request['prompt_id'].split(':')[1]), request['arm'], request['stratum']
        if (arm, stratum, i) in missing:
            results.append(_result(request, '', status='error'))
        elif (arm, stratum, i) in polls:
            results.append(_result(request, POLL))
        elif stratum == 'U2':
            if (arm == 'C' and i in c_slips) or (arm == 'T2' and i in t2_slips):
                results.append(_result(request, report(note='PENDING')))
            elif arm == 'T2' and i in t2_other:
                results.append(_result(request, report(up='UNKNOWN')))           # an other mismatch
            else:
                results.append(_result(request, report()))
        else:
            wrong = (arm == 'T2' and i in t2_guard_bad) or (arm == 'R' and i in r_guard_bad)
            results.append(_result(request, report(note='PENDING' if wrong else 'UNKNOWN')))
    return probe.compute_readouts(_plan(rows, precheck), results)


def test_a_clean_narrow_field_is_recommended():
    readouts = _run(c_slips=set(range(6)))
    ni = readouts['non_inferiority']
    assert ni['status'] == 'PASS' and ni['t2_only_bad'] == 0 and ni['c_only_bad'] == 6
    assert readouts['in_window_guard']['status'] == 'PASS' and readouts['structural_guard']['status'] == 'PASS'
    assert readouts['decision'] == 'RECOMMENDED_FOR_A_LATER_LOOP'
    assert 'non-inferiority PASS' in readouts['statement'] and 'Recommended for a later loop only' in readouts['statement']
    # The structural guard is never quoted as a measured pass (review round 1, S5); the U3-alone test is named.
    assert 'structural guard PASS by construction, not a measurement' in readouts['statement']
    assert 'nothing was sent' in readouts['statement'] and 'U3 alone PASS' in readouts['statement']
    assert 'does not show a benefit' in readouts['statement'] and '1.5-point margin' in readouts['statement']
    assert readouts['structural_guard']['by_construction'] is True
    assert ni['reduction']['decides'] is False and ni['reduction']['mcnemar_exact_one_sided_p'] == pytest.approx(1 / 64)
    pooled = ni['reduction']['pooled_with_phase27']
    assert (pooled['c_only_bad'], pooled['t2_only_bad'], pooled['prompts']) == (10, 0, 525)


def test_non_inferiority_fails_when_t2_slips_more_and_counts_every_t2_error():
    readouts = _run(c_slips={0, 1}, t2_slips=set(range(10, 20)))
    assert readouts['non_inferiority']['status'] == 'FAIL' and readouts['decision'] == 'NOT_RECOMMENDED'
    assert 'non-inferiority FAIL' in readouts['statement']
    # An other mismatch, a non-report and a missing T2 response all count against T2; the same for C does not.
    readouts = _run(t2_other={1}, polls={('T2', 'U2', 2)}, missing={('T2', 'U2', 3), ('C', 'U2', 4)})
    ni = readouts['non_inferiority']
    assert ni['arms']['T2']['bad_worst_case'] == 3 and ni['arms']['C']['bad'] == 0
    assert ni['arms']['T2']['non_reports'] == 1 and ni['arms']['T2']['received'] == 299
    readouts = _run(polls={('C', 'U2', i) for i in range(20)})
    assert readouts['non_inferiority']['arms']['C']['bad'] == 0


def test_non_inferiority_is_incomplete_below_95_percent_of_an_arm():
    missing = {('T2', 'U2', i) for i in range(16)}                 # 284 of 300 received < 285
    readouts = _run(missing=missing)
    assert readouts['non_inferiority']['status'] == 'INCOMPLETE' and readouts['decision'] == 'NOT_RECOMMENDED'
    readouts = _run(missing={('C', 'U2', i) for i in range(15)})    # 285 of 300: complete
    assert readouts['non_inferiority']['status'] == 'PASS'
    readouts = _run(missing={('C', 'U2', i) for i in range(16)})    # the comparator arm below 95% as well
    assert readouts['non_inferiority']['status'] == 'INCOMPLETE'


def test_a_reduction_is_never_needed_for_a_recommendation():
    readouts = _run(c_slips={0, 1})
    ni = readouts['non_inferiority']
    assert ni['reduction']['p_below_alpha'] is False and ni['reduction']['mcnemar_exact_one_sided_p'] == 0.25
    assert ni['status'] == 'PASS' and readouts['decision'] == 'RECOMMENDED_FOR_A_LATER_LOOP'
    assert 'did not reach p < 0.05 (descriptive)' in readouts['statement']


def test_the_in_window_guard_fails_a_t2_only_error_pattern_and_passes_noise():
    assert _run(t2_guard_bad=set(range(5)))['in_window_guard']['status'] == 'FAIL'
    assert _run(t2_guard_bad=set(range(4)))['in_window_guard']['status'] == 'PASS'
    assert _run(t2_guard_bad=set(range(7)), r_guard_bad={50})['in_window_guard']['status'] == 'FAIL'
    assert _run(t2_guard_bad=set(range(6)), r_guard_bad={50})['in_window_guard']['status'] == 'PASS'
    # Errors shared by both arms are not discordant.
    guard = _run(t2_guard_bad=set(range(9)), r_guard_bad=set(range(9)))['in_window_guard']
    assert guard['status'] == 'PASS' and guard['t2_only_not_ok'] == guard['r_only_not_ok'] == 0
    failed = _run(t2_guard_bad=set(range(5)))
    assert failed['decision'] == 'NOT_RECOMMENDED' and 'in-window guard FAIL' in failed['statement']


def test_the_in_window_guard_counts_a_non_report_against_either_arm_and_needs_95_percent():
    guard = _run(polls={('T2', 'U3', i) for i in range(5)})['in_window_guard']
    assert guard['status'] == 'FAIL' and guard['t2_only_not_ok'] == 5
    guard = _run(polls={('R', 'U3', i) for i in range(5)})['in_window_guard']
    assert guard['status'] == 'PASS' and guard['r_only_not_ok'] == 5
    guard = _run(guard_missing=set(), missing={('R', 'U3', i) for i in range(6)})['in_window_guard']
    assert guard['status'] == 'INCOMPLETE' and guard['compared'] == 94
    # A failure is reported only when the gate's own completeness holds.
    guard = _run(missing={('R', 'U3', i) for i in range(6)}, t2_guard_bad=set(range(10, 20)))['in_window_guard']
    assert guard['status'] == 'INCOMPLETE'


def test_the_structural_guard_is_read_from_the_plan_and_decides():
    readouts = _run(precheck={'passed': False})
    assert readouts['structural_guard']['status'] == 'FAIL' and readouts['decision'] == 'NOT_RECOMMENDED'
    assert _run(precheck={})['structural_guard']['status'] == 'FAIL'


def _guard(*, u1=52, u3=62, t2_bad=(), r_bad=(), missing=()):
    """The in-window guard over U1 (R, T2) and U3 (R, T2), as planned. t2_bad and r_bad name (stratum, index)
    prompts whose report has a wrong word in that arm; missing names (arm, stratum, index) errored responses."""
    rows = _requests('U1', u1, ('R', 'T2'), PHASE24) + _requests('U3', u3, ('R', 'T2'), LAPSE_NEVER_SENT)
    pairs = []
    for request in rows:
        stratum, arm, i = request['stratum'], request['arm'], int(request['prompt_id'].split(':')[1])
        if (arm, stratum, i) in missing:
            result = _result(request, '', status='error')
        else:
            wrong = (stratum, i) in (t2_bad if arm == 'T2' else r_bad)
            raw = (report(up='PENDING' if wrong else 'UNKNOWN', note='NOT_STARTED') if stratum == 'U1'
                   else report(note='PENDING' if wrong else 'UNKNOWN'))
            result = _result(request, raw)
        pairs.append((request, result))
    return probe.guard_readout(pairs)


def test_the_in_window_guard_also_tests_u3_alone_so_a_u3_harm_is_not_diluted_by_u1():
    clean = _guard()
    assert clean['status'] == clean['pooled_status'] == clean['alone']['status'] == 'PASS'
    assert clean['compared'] == 114 and clean['alone']['compared'] == 62 and clean['alone']['stratum'] == 'U3'
    assert clean['t2_only_not_ok'] == clean['r_only_not_ok'] == 0 and clean['reports'] == {'R': 114, 'T2': 114}
    # A harm confined to U3 (5 T2-only errors) beside R-only noise in U1 (2): pooled p = 29/128 passes, while
    # U3 alone (5 against 0, p = 1/32) fails, so the guard fails.
    guard = _guard(t2_bad={('U3', i) for i in range(5)}, r_bad={('U1', 0), ('U1', 1)})
    assert guard['pooled_status'] == 'PASS' and guard['sign_test_one_sided_p'] == pytest.approx(29 / 128)
    assert guard['alone']['status'] == 'FAIL' and guard['alone']['sign_test_one_sided_p'] == pytest.approx(1 / 32)
    assert (guard['alone']['t2_only_not_ok'], guard['alone']['r_only_not_ok']) == (5, 0)
    assert guard['status'] == 'FAIL'
    # The same errors in U1 are caught by the pooled test only.
    guard = _guard(t2_bad={('U1', i) for i in range(5)})
    assert guard['pooled_status'] == 'FAIL' and guard['alone']['status'] == 'PASS' and guard['status'] == 'FAIL'


def test_each_guard_part_needs_its_own_completeness_and_a_failure_is_reported_first():
    gone = {('R', 'U3', i) for i in range(58, 62)}           # U3: 58 of 62 compared (< 59); pooled 110 of 114
    guard = _guard(missing=gone)
    assert guard['pooled_status'] == 'PASS' and guard['compared'] == 110
    assert guard['alone']['status'] == 'INCOMPLETE' and guard['alone']['compared'] == 58
    assert guard['status'] == 'INCOMPLETE'
    # U3 alone reaches p < 0.05 but is incomplete, and U1's R-only noise keeps the pooled test passing.
    guard = _guard(missing=gone, t2_bad={('U3', i) for i in range(5)}, r_bad={('U1', i) for i in range(3)})
    assert guard['alone']['sign_test_one_sided_p'] < 0.05 and guard['alone']['status'] == 'INCOMPLETE'
    assert guard['pooled_status'] == 'PASS' and guard['status'] == 'INCOMPLETE'
    # A complete pooled failure is reported ahead of an incomplete U3 test.
    guard = _guard(missing=gone, t2_bad={('U1', i) for i in range(5)})
    assert guard['pooled_status'] == 'FAIL' and guard['alone']['status'] == 'INCOMPLETE' and guard['status'] == 'FAIL'
    # No U3 prompt at all: the U3 test cannot be complete, so the guard cannot pass.
    guard = _guard(u3=0)
    assert guard['pooled_status'] == 'PASS' and guard['alone']['status'] == 'INCOMPLETE'
    assert guard['status'] == 'INCOMPLETE'
    readouts = _run(t2_guard_bad=set(range(5)))
    assert 'U3 alone FAIL' in readouts['statement'] and readouts['decision'] == 'NOT_RECOMMENDED'


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


def _small_plan(n=3, m=2):
    requests = _requests('U2', n, ('C', 'T2'), LAPSE_AFTER_SEND) + _requests('U1', m, ('R', 'T2'), PHASE24)
    prompts = {}
    for index, request in enumerate(requests, 1):
        request['request_id'] = f'r{index:04d}'
        request['request_hash'] = f'h{index}'
        prompts[f'h{index}'] = {'request_hash': f'h{index}', 'response_contract': 'actor_final_report',
                                'messages': [{'role': 'system', 'content': 'You are a test.'},
                                             {'role': 'user', 'content': f'prompt {index}'}]}
    return {'counts': {'total_requests': len(requests)}, 'requests': requests, 'precheck': PASSED_PRECHECK,
            'phase27_u2_reference': REFERENCE}, prompts


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
    assert (tmp_path / probe.MANIFEST_NAME).is_file() and not (tmp_path / rwp.MANIFEST_NAME).exists()
    manifest = json.loads((tmp_path / probe.MANIFEST_NAME).read_text())
    assert manifest['generations_delivered'] == 2 and manifest['charged_upper_bound'] == pytest.approx(0.0418)
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    loaded, results, partial = probe.load_run(tmp_path)
    readouts = probe.compute_readouts(loaded, results, partial_lines_skipped=partial)
    assert readouts['requests_received'] == 2 and readouts['non_inferiority']['status'] == 'INCOMPLETE'


def test_spend_guard_follows_this_harness_cap(monkeypatch):
    assert probe.SpendGuard(20.0).cap == 20.0
    for bad in (20.01, 25.0, 0, -1, float('nan'), '20'):
        with pytest.raises(probe.PlanningError, match='at most'):
            probe.SpendGuard(bad)
    with pytest.raises(probe.PlanningError, match='exceed'):
        probe.check_budget(957, 20.0)
    probe.check_budget(956, 20.0)
    assert probe.cap_problem() is None
    monkeypatch.setattr(probe, 'HARD_SPEND_CAP', 25.0)
    assert "above the program's" in probe.cap_problem()


def _artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    return artifacts


def _manifest(artifacts, relative, name=None, **fields):
    directory = artifacts / relative
    directory.mkdir(parents=True, exist_ok=True)
    body = {'status': 'COMPLETED', 'started_at': 'x', 'ended_at': 'x', 'generations_delivered': 0, 'statuses': {},
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
    assert probe.check_output('artifacts/phase30-2026-09-25/live') == artifacts.resolve() / 'phase30-2026-09-25/live'
    for bad in ('artifacts/phase27-2026-09-24/live', 'artifacts/phase30-2026-09-25', 'artifacts/phase30-x/a/b',
                f'artifacts/{probe.CLAIM_DIR}/x', 'elsewhere/phase30-x/live', 'artifacts/phase30-x/li ve'):
        with pytest.raises(probe.PlanningError):
            probe.check_output(bad)
    (artifacts / 'phase30-2026-09-25/live').mkdir(parents=True)
    with pytest.raises(probe.PlanningError, match='never resumed'):
        probe.check_output('artifacts/phase30-2026-09-25/live')


def test_one_delivering_run_only_and_the_phase_cap_is_shared(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase30-2026-09-25/live', status='STOPPED', charged_upper_bound=1.5)
    earlier = probe.earlier_live_runs(artifacts)
    assert probe.effective_spend_cap(20.0, earlier) == pytest.approx(18.5)
    _manifest(artifacts, 'phase30-2026-09-25/live-2', status='COMPLETED', generations_delivered=3, statuses={'ok': 3})
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase30-2026-09-25/live-3')


def test_a_claim_without_a_final_manifest_blocks_until_finalized(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _claim(artifacts, 1, 'artifacts/phase30-2026-09-25/live')
    with pytest.raises(probe.PlanningError, match='no manifest'):
        probe.check_output('artifacts/phase30-2026-09-25/live-2')
    _manifest(artifacts, 'phase30-2026-09-25/live', status='RUNNING', ended_at=None)
    with pytest.raises(probe.PlanningError, match='not final'):
        probe.check_output('artifacts/phase30-2026-09-25/live-2')
    monkeypatch.setattr(probe, 'claim_process_alive', lambda pid: False)
    probe.finalize_abandoned(f'artifacts/{probe.CLAIM_DIR}/claim-01.json')
    manifest = json.loads((artifacts / 'phase30-2026-09-25/live' / probe.MANIFEST_NAME).read_text())
    assert manifest['status'] == 'ABORTED' and manifest['stop_reason'] == 'abandoned'
    assert manifest['charged_upper_bound'] == pytest.approx(2 * probe.PER_REQUEST_DOLLAR_BOUND)
    probe.check_output('artifacts/phase30-2026-09-25/live-2')


def test_other_run_records_block_until_final_or_named(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    none = lambda: []  # noqa: E731
    assert probe.other_paid_runs(root=tmp_path, processes=none) == []
    for relative, name in (('phase20-2026-09-23/run-2', 'dev-probe-manifest.json'),
                           ('phase21-2026-09-23/live-2', 'lapse-probe-manifest.json'),
                           ('phase23-2026-09-24', 'full-loop-manifest.json'),
                           ('phase25-2026-09-24/live-2', 'slot2-probe-manifest.json'),
                           ('phase26-2026-09-24/run-2', 'gap-probe-manifest.json'),
                           ('phase27-2026-09-24/live-2', 'report-word-probe-manifest.json'),
                           ('phase28-2026-09-26/run-1', 'anything-manifest.json'),
                           ('phase29-2026-09-26/live', 'slot2-hidden-manifest.json'),
                           ('phase31-2026-09-27/demo', 'demo-manifest.json')):
        path = _manifest(artifacts, relative, name=name, status='RUNNING', ended_at=None) / name
        assert probe.other_paid_runs(root=tmp_path, processes=none) == [f'artifacts/{relative}/{name}']
        with pytest.raises(probe.PlanningError, match='Another paid run'):
            probe.check_other_runs(SimpleNamespace(ignore_manifest=[]), root=tmp_path, status=lambda: ('down', None),
                                   processes=none)
        assert probe.other_paid_runs(root=tmp_path, ignore=[f'artifacts/{relative}/{name}'], processes=none) == []
        path.write_text(json.dumps({'status': 'COMPLETED', 'started_at': 'x', 'ended_at': 'x'}))
    # A file that is not a run manifest (no started_at) is not a run; an unreadable one counts as running.
    (artifacts / 'phase29-2026-09-26/fixture-manifest.json').write_text(json.dumps({'cases': []}))
    assert probe.other_paid_runs(root=tmp_path, processes=none) == []
    (artifacts / 'phase29-2026-09-26/broken-manifest.json').write_text('{not json')
    assert probe.other_paid_runs(root=tmp_path, processes=none) == ['artifacts/phase29-2026-09-26/broken-manifest.json']
    (artifacts / 'phase29-2026-09-26/broken-manifest.json').unlink()
    # A claim of another phase blocks until its run directory holds a final run manifest.
    _claim(artifacts, 1, 'artifacts/phase29-2026-09-26/live-9', directory='phase29-live-claims')
    assert probe.other_paid_runs(root=tmp_path, processes=none) == ['artifacts/phase29-live-claims/claim-01.json']
    _manifest(artifacts, 'phase29-2026-09-26/live-9', name='slot2-hidden-manifest.json')
    assert probe.other_paid_runs(root=tmp_path, processes=none) == []


def test_an_experiment_process_blocks_and_is_never_set_aside(tmp_path, monkeypatch):
    _artifacts(tmp_path, monkeypatch)
    entry = 'pid 4242: scripts/experiments/slot2_probe.py --execute-live'
    with pytest.raises(probe.PlanningError, match='pid 4242'):
        probe.check_other_runs(SimpleNamespace(ignore_manifest=[entry]), root=tmp_path, status=lambda: ('down', None),
                               processes=lambda: [entry])
    assert probe.other_paid_runs(root=tmp_path, ignore=[entry], processes=lambda: [entry]) == [entry]


@pytest.mark.parametrize('state,body,refused', [
    ('down', None, False), ('up', {'active_campaign_id': None}, False), ('up', {'active_campaign_id': 'c'}, True),
    ('up', {}, True), ('up', 'garbage', True)])
def test_the_backend_must_show_no_active_campaign(tmp_path, monkeypatch, state, body, refused):
    _artifacts(tmp_path, monkeypatch)
    args = SimpleNamespace(ignore_manifest=[])
    if refused:
        with pytest.raises(probe.PlanningError, match='active campaign'):
            probe.check_other_runs(args, root=tmp_path, status=lambda: (state, body), processes=lambda: [])
    else:
        assert probe.check_other_runs(args, root=tmp_path, status=lambda: (state, body),
                                      processes=lambda: [])['backend'] == state


def test_other_runs_never_list_or_open_the_heldout_phases(tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _manifest(artifacts, 'phase24-2026-09-24', name='heldout-manifest.json', ended_at=None)
    _manifest(artifacts, 'phase22-2026-09-24/seal', name='seal-manifest.json', ended_at=None)
    _manifest(artifacts, 'heldout2', name='partition-manifest.json', ended_at=None)
    _manifest(artifacts, 'audit', name='audit-manifest.json', ended_at=None)
    _manifest(artifacts, 'phase26-2026-09-24/run-1', name='gap-probe-manifest.json')
    _claim(artifacts, 1, 'artifacts/phase24-2026-09-24', directory='phase24-live-claims')
    _claim(artifacts, 1, 'artifacts/phase24-2026-09-24/check', directory='phase21-live-claims')
    _claim(artifacts, 2, 'artifacts/phase21-2026-09-23/../phase24-2026-09-24', directory='phase21-live-claims')
    opened = []
    original = pathlib.Path.read_text

    def spy(self, *args, **kwargs):
        opened.append(str(self))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, 'read_text', spy)
    active = probe.other_paid_runs(root=tmp_path, processes=lambda: [])
    monkeypatch.undo()
    assert active == ['artifacts/phase21-live-claims/claim-01.json', 'artifacts/phase21-live-claims/claim-02.json']
    inside = [path.split('/artifacts/', 1)[-1] for path in opened]
    assert not any(part in path for path in inside for part in ('phase24-2026', 'phase22-', 'heldout2', 'audit'))
    assert any(path.endswith('gap-probe-manifest.json') for path in opened)


OWNER_QUOTE = 'go ahead with whatever u recommend'


def _owner_answer(**changes):
    return {'verbatim': OWNER_QUOTE, 'given_by': 'the project owner (test)', 'date': '2026-09-25', **changes}


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
        lines += ['', '## Review log', f'The owner wrote: "{OWNER_QUOTE}".']
    protocol = tmp_path / 'protocol.md'
    protocol.write_text('\n'.join(lines) + '\n')
    monkeypatch.setattr(probe, 'PROTOCOL', protocol)
    protocol_sha = probe.sha256_file(protocol)
    if review:
        record = tmp_path / probe.REVIEW_RECORD
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'protocol_sha256': protocol_sha, 'harness_sha256': harness, 'plan_hash': plan_hash,
                                      'phase_cap': probe.HARD_SPEND_CAP, 'approved_by': 'the reviewer (test)',
                                      'owner_answer': _owner_answer()}))
    return SimpleNamespace(out='artifacts/phase30-test/live', expect_harness_sha256=harness,
                           expect_protocol_sha256=protocol_sha, expect_plan_hash=plan_hash, spend_cap=20.0,
                           confirm_entity='shreetbohara-quinstreet', ignore_manifest=[])


class CredentialRead(Exception):
    pass


def _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts, status=lambda: ('down', None),
                                processes=lambda: []):
    def no_credentials(*_, **__):
        raise CredentialRead()
    monkeypatch.setattr(probe, 'settings_from_file', no_credentials)
    with pytest.raises(probe.PlanningError) as error:
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=status, processes=processes)
    assert not (tmp_path / 'artifacts/phase30-test').exists()
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()
    return str(error.value)


def test_live_gate_refuses_before_any_credential_read(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    for change, message in ((dict(expect_harness_sha256='0' * 64), 'harness'),
                            (dict(expect_protocol_sha256='0' * 64), 'does not match the protocol'),
                            (dict(expect_plan_hash='0' * 64), '--expect-plan-hash'),
                            (dict(spend_cap=0.05), 'exceed'), (dict(spend_cap=25.0), 'at most')):
        assert message in _refused_before_credentials(tmp_path, monkeypatch, SimpleNamespace(**{**vars(args), **change}),
                                                      plan, prompts)
    assert 'active campaign' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts,
                                                            status=lambda: ('up', {'active_campaign_id': 'c'}))
    assert 'pid 7' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts,
                                                  processes=lambda: ['pid 7: experiments/x.py --execute-live'])
    monkeypatch.setattr(probe, 'PROTOCOL', tmp_path / 'missing.md')
    assert 'No protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    silent = tmp_path / 'silent.md'
    silent.write_text('a protocol that declares nothing')
    monkeypatch.setattr(probe, 'PROTOCOL', silent)
    assert 'does not declare' in _refused_before_credentials(
        tmp_path, monkeypatch, SimpleNamespace(**{**vars(args), 'expect_protocol_sha256': probe.sha256_file(silent)}),
        plan, prompts)


def test_live_gate_enforces_the_review(tmp_path, monkeypatch):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan, marker=True)
    assert 'NOT yet reviewed' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, marker=probe.REVIEW_PENDING_MARKER.lower())
    assert 'NOT yet reviewed' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, reviewed_line=False)
    assert 'Reviewed for launch' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    (tmp_path / probe.REVIEW_RECORD).unlink()
    args = _gate(tmp_path, monkeypatch, plan, review=False)
    assert 'No readable review record' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)
    args = _gate(tmp_path, monkeypatch, plan, quote=False)
    assert 'not quoted in the protocol' in _refused_before_credentials(tmp_path, monkeypatch, args, plan, prompts)


def _check_review_with(tmp_path, monkeypatch, **record_changes):
    plan, _ = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    record = tmp_path / probe.REVIEW_RECORD
    body = {**json.loads(record.read_text()), **record_changes}
    record.write_text(json.dumps({k: v for k, v in body.items() if v is not ...}))
    return probe.check_review(probe.PROTOCOL.read_text(), args.expect_protocol_sha256, args.expect_harness_sha256,
                              args.expect_plan_hash, root=tmp_path)


def test_the_review_record_must_carry_the_pins_the_cap_the_approver_and_the_owners_words(tmp_path, monkeypatch):
    assert _check_review_with(tmp_path, monkeypatch) == _owner_answer()
    assert _check_review_with(tmp_path, monkeypatch, phase_cap=20) == _owner_answer()
    refusals = [({'plan_hash': '0' * 64}, 'does not name this protocol'),
                ({'harness_sha256': ...}, 'does not name this protocol'),
                ({'phase_cap': 25.0}, 'phase_cap'), ({'phase_cap': 19.99}, 'phase_cap'), ({'phase_cap': '20'}, 'phase_cap'),
                ({'phase_cap': True}, 'phase_cap'), ({'phase_cap': ...}, 'phase_cap'),
                ({'approved_by': ' '}, 'approver'), ({'approved_by': ...}, 'approver'),
                ({'owner_answer': None}, 'no owner_answer'),
                ({'owner_answer': {k: v for k, v in _owner_answer().items() if k != 'given_by'}}, 'no owner_answer'),
                ({'owner_answer': _owner_answer(date=' ')}, 'no owner_answer'),
                ({'owner_answer': _owner_answer(verbatim='go ahead with the larger sample')}, 'not quoted'),
                ({'owner_answer': _owner_answer(verbatim=OWNER_QUOTE.upper())}, 'not quoted')]
    for changes, message in refusals:
        with pytest.raises(probe.PlanningError, match=message):
            _check_review_with(tmp_path, monkeypatch, **changes)


def test_the_review_marker_is_read_only_in_the_status_block(tmp_path, monkeypatch):
    plan, _ = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    text = probe.PROTOCOL.read_text() + f'\n## Review log\nRound 0 said "{probe.REVIEW_PENDING_MARKER}".\n'
    probe.PROTOCOL.write_text(text)
    record = tmp_path / probe.REVIEW_RECORD
    record.write_text(json.dumps({**json.loads(record.read_text()), 'protocol_sha256': probe.sha256_file(probe.PROTOCOL)}))
    assert probe.check_review(text, probe.sha256_file(probe.PROTOCOL), args.expect_harness_sha256,
                              args.expect_plan_hash, root=tmp_path) == _owner_answer()


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


DECLARED_PINS = {'configuration_hash': probe.DECLARED_CONFIGURATION_HASH, 'actor_model': probe.EXPECTED_ACTOR_MODEL,
                 'actor_model_settings': {'temperature': 0}, 'per_request_dollar_bound': probe.PER_REQUEST_DOLLAR_BOUND}


def _fake_settings(dry_settings, **changes):
    return dataclasses.replace(dry_settings, wandb_api_key='fake-not-a-key', **changes)


def _live(tmp_path, monkeypatch, dry_settings, script, out='artifacts/phase30-test/live', status=None,
          processes=None, real_pins=False):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    args.out = out
    status = status or (lambda: ('down', None))

    def live_settings(path, *, env_path):
        assert env_path is None, 'the live path reads credentials through the runtime loader only'
        return _fake_settings(dry_settings)
    monkeypatch.setattr(probe, 'settings_from_file', live_settings)
    if not real_pins:
        monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    monkeypatch.setattr(probe, 'openai_client_factory', FakeOpenAI)
    FakeOpenAI.script = list(script)
    code = probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=status, processes=processes or (lambda: []))
    directory = tmp_path / out
    return code, json.loads((directory / probe.MANIFEST_NAME).read_text()), directory


def test_live_run_end_to_end_on_the_real_provider_with_a_fake_client(tmp_path, monkeypatch, dry_settings):
    code, manifest, directory = _live(tmp_path, monkeypatch, dry_settings, [report(note='PENDING')])
    assert code == 0 and manifest['status'] == 'COMPLETED' and manifest['generations_delivered'] == 10
    assert manifest['claim'] == f'artifacts/{probe.CLAIM_DIR}/claim-01.json' and manifest['traceback'] is None
    assert manifest['phase27_harness_sha256'] == probe.PHASE27_HARNESS_SHA256
    assert manifest['phase26_runner_sha256'] == probe.PHASE26_RUNNER_SHA256
    assert manifest['other_runs_check'] == {'backend': 'down', 'active_campaign_id': None, 'processes': 'none'}
    assert manifest['owner_answer'] == _owner_answer() and manifest['program_phase_cap'] == 20.0
    assert manifest['charged_upper_bound'] == pytest.approx(10 * probe.PER_REQUEST_DOLLAR_BOUND)
    readouts = json.loads((directory / 'readouts.json').read_text())
    assert readouts['provider']['served_model'] == {'served-by/another-model': 10}
    assert readouts['requests_received'] == 10
    assert probe.recompute_readouts(directory) == readouts
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase30-test/live-2')


@needs_tree
def test_live_run_with_the_real_configuration_pins(tmp_path, monkeypatch, dry_settings):
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [], real_pins=True)
    assert code == 0 and manifest['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH


def test_a_run_that_received_nothing_may_be_followed_by_one_new_run(tmp_path, monkeypatch, dry_settings):
    failures = [APIConnectionError('down') for _ in range(20)]
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, failures)
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'consecutive_errors'
    assert manifest['generations_delivered'] == 0 and manifest['charged_upper_bound'] > 0
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [], out='artifacts/phase30-test/live-2')
    assert code == 0 and manifest['earlier_undelivered_charged'] > 0
    assert manifest['spend_cap'] == pytest.approx(20.0 - manifest['earlier_undelivered_charged'])


def test_a_paid_run_that_appears_after_the_claim_stops_this_run_at_zero(tmp_path, monkeypatch, dry_settings):
    calls = []

    def processes():
        calls.append(1)
        return ['pid 99: scripts/experiments/slot2_probe.py --execute-live'] if len(calls) >= 3 else []
    code, manifest, directory = _live(tmp_path, monkeypatch, dry_settings, [report()] * 10, processes=processes)
    assert len(calls) == 3
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == probe.OTHER_RUN_AFTER_CLAIM
    assert 'pid 99' in manifest['blockers_after_claim'] and manifest['ended_at']
    assert manifest['attempts'] == 0 and manifest['generations_delivered'] == 0 and len(FakeOpenAI.script) == 10
    assert json.loads((directory / 'readouts.json').read_text())['requests_received'] == 0
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [], out='artifacts/phase30-test/live-2')
    assert code == 0 and manifest['claim'].endswith('claim-02.json')


def test_a_run_manifest_that_appears_during_the_launch_is_refused_after_the_credential_read(tmp_path, monkeypatch,
                                                                                           dry_settings):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)

    def live_settings(path, *, env_path):
        _manifest(tmp_path / 'artifacts', 'phase29-2026-09-26/live', name='x-manifest.json', ended_at=None)
        return _fake_settings(dry_settings)
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    monkeypatch.setattr(probe, 'settings_from_file', live_settings)
    with pytest.raises(probe.PlanningError, match='Another paid run'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None), processes=lambda: [])
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()


def test_the_credential_dependent_checks_each_refuse_before_the_claim(tmp_path, monkeypatch, dry_settings):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    good = _fake_settings(dry_settings)

    def refused(settings, match, pins=DECLARED_PINS, arguments=args):
        monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: settings)
        monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: pins)
        monkeypatch.setattr(probe, 'openai_client_factory', lambda **_: pytest.fail('no provider client may be built'))
        with pytest.raises(probe.PlanningError, match=match):
            probe.run_live(arguments, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None),
                           processes=lambda: [])
        assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()
    refused(good, '--confirm-entity must match', arguments=SimpleNamespace(**{**vars(args), 'confirm_entity': 'x'}))
    refused(_fake_settings(dry_settings, wandb_project='OtherProject'), 'project is not the declared')
    refused(good, 'configuration_hash differs', pins={**DECLARED_PINS, 'configuration_hash': '0' * 64})

    class OtherActor(type(good)):
        def model_for_role(self, role):
            return 'other/model'
    refused(OtherActor(**{f.name: getattr(good, f.name) for f in dataclasses.fields(good)}),
            'does not resolve to the declared model')


def test_earlier_runs_that_change_during_the_launch_refuse_the_claim(tmp_path, monkeypatch, dry_settings):
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    artifacts = tmp_path / 'artifacts'
    original = probe.take_claim

    def take_claim(*a, **k):
        _manifest(artifacts, 'phase30-test/other', charged_upper_bound=0.0209, statuses={'error': 1})
        _claim(artifacts, 1, 'artifacts/phase30-test/other')
        return original(*a, **k)
    monkeypatch.setattr(probe, 'take_claim', take_claim)
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    monkeypatch.setattr(probe, 'openai_client_factory', lambda **_: pytest.fail('no provider client may be built'))
    with pytest.raises(probe.PlanningError, match='changed during the launch checks; nothing was claimed'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None), processes=lambda: [])
    assert sorted(p.name for p in (artifacts / probe.CLAIM_DIR).iterdir()) == ['claim-01.json']
    assert not (tmp_path / args.out).exists()        # the empty directory this launch made is removed


def test_an_output_directory_that_appears_during_the_launch_refuses_before_the_claim(tmp_path, monkeypatch,
                                                                                    dry_settings):
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
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None), processes=lambda: [])
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists()


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


def test_signal_handlers_are_installed_before_the_claim_and_a_stop_in_set_up_is_recorded(tmp_path, monkeypatch,
                                                                                         dry_settings):
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
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [report()] * 10)
    assert events[:4] == [('signal', probe.signal.SIGINT), ('signal', probe.signal.SIGTERM), ('claim',),
                          ('manifest', 'STARTING', os.getpid())]
    assert code == 1 and manifest['status'] == 'STOPPED' and manifest['stop_reason'] == 'operator_stop'
    assert manifest['attempts'] == 0 and manifest['generations_delivered'] == 0 and len(FakeOpenAI.script) == 10


def test_an_operator_stop_before_the_claim_claims_nothing(tmp_path, monkeypatch, dry_settings):
    events = []
    monkeypatch.setattr(probe.signal, 'signal', SignalLog(events, fire_on_install=probe.signal.SIGTERM))
    _record_claims(monkeypatch, events)
    plan, prompts = _small_plan()
    args = _gate(tmp_path, monkeypatch, plan)
    monkeypatch.setattr(probe, 'configuration_pins', lambda _settings: DECLARED_PINS)
    monkeypatch.setattr(probe, 'settings_from_file', lambda path, *, env_path: _fake_settings(dry_settings))
    with pytest.raises(probe.PlanningError, match='before the claim; nothing was claimed'):
        probe.run_live(args, plan, prompts, sleep=FakeSleep(), status=lambda: ('down', None), processes=lambda: [])
    assert ('claim',) not in events
    assert not (tmp_path / 'artifacts' / probe.CLAIM_DIR).exists() and not (tmp_path / 'artifacts/phase30-test').exists()


def _responses(directory, lines):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'responses.jsonl').write_text(''.join(json.dumps(line) + '\n' for line in lines))


def test_finalize_abandoned_counts_what_a_hard_killed_run_delivered_and_charges_the_in_flight_attempts(
        tmp_path, monkeypatch):
    artifacts = _artifacts(tmp_path, monkeypatch)
    _claim(artifacts, 1, 'artifacts/phase30-2026-09-25/live')
    _manifest(artifacts, 'phase30-2026-09-25/live', status='RUNNING', ended_at=None, statuses={'ok': 1},
              generations_delivered=1, attempts=1, charged_upper_bound=0.0209)
    served = {'model': 'm', 'system_fingerprint': None, 'prompt_tokens': None, 'completion_tokens': None}
    _responses(artifacts / 'phase30-2026-09-25/live', [
        {'request_id': 'r0001', 'status': 'ok', 'attempts': [{'attempt': 1, 'error': None, 'served': served}]},
        {'request_id': 'r0002', 'status': 'error', 'attempts': [
            {'attempt': 1, 'code': 'CONNECTION_ERROR', 'served': None},
            {'attempt': 2, 'code': 'INVALID_RESPONSE_SHAPE', 'served': served}]}])
    with (artifacts / 'phase30-2026-09-25/live/responses.jsonl').open('a') as handle:
        handle.write('{"request_id": "r0003", "sta')
    monkeypatch.setattr(probe, 'claim_process_alive', lambda pid: False)
    assert probe.main(['--finalize-abandoned', f'artifacts/{probe.CLAIM_DIR}/claim-01.json']) == 0
    manifest = json.loads((artifacts / 'phase30-2026-09-25/live' / probe.MANIFEST_NAME).read_text())
    # Two recorded deliveries, plus the cut-off third line, which counts as delivered (review round 1, B3).
    assert manifest['status'] == 'ABORTED' and manifest['generations_delivered'] == 3
    assert manifest['statuses'] == {'error': 1, 'ok': 1} and manifest['requests_done'] == 2
    assert manifest['attempts'] == 3 + probe.ABANDONED_IN_FLIGHT_ATTEMPTS
    assert manifest['charged_upper_bound'] == pytest.approx(5 * probe.PER_REQUEST_DOLLAR_BOUND)
    assert manifest['finalized_abandoned']['partial_lines_skipped'] == 1
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase30-2026-09-25/live-2')
    monkeypatch.setattr(probe, 'claim_process_alive', lambda pid: True)
    _claim(artifacts, 2, 'artifacts/phase30-2026-09-25/live-9')
    with pytest.raises(probe.PlanningError, match='may still be running'):
        probe.finalize_abandoned(f'artifacts/{probe.CLAIM_DIR}/claim-02.json')


def test_readouts_are_recomputed_only_with_the_runs_own_harness_and_plan(tmp_path):
    plan, _ = _small_plan()
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    (tmp_path / 'responses.jsonl').write_text('')
    (tmp_path / probe.MANIFEST_NAME).write_text(json.dumps({'harness_sha256': '0' * 64,
                                                            'plan_hash': probe.plan_hash(plan)}))
    with pytest.raises(probe.PlanningError, match="NOT THE RUN'S HARNESS"):
        probe.recompute_readouts(tmp_path)
    labelled = probe.recompute_readouts(tmp_path, allow_other_harness=True)
    assert labelled['label'] == probe.NOT_THE_RUNS_HARNESS and labelled['harness_matches_run'] is False
    (tmp_path / probe.MANIFEST_NAME).write_text(json.dumps({'harness_sha256': probe.sha256_file(probe.__file__),
                                                            'plan_hash': probe.plan_hash(plan)}))
    assert probe.recompute_readouts(tmp_path)['requests_received'] == 0


def test_live_flags_are_required_before_any_plan_is_built(capsys, monkeypatch):
    monkeypatch.setattr(probe, 'build_plan', lambda **_: pytest.fail('no plan may be built'))
    assert probe.main(['--execute-live', '--out', 'artifacts/phase30-x/live']) == 1
    assert 'needs --out, --confirm-entity' in capsys.readouterr().out


def test_main_refuses_beside_another_paid_run_before_any_plan_is_built(tmp_path, monkeypatch, capsys):
    _artifacts(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, 'build_plan', lambda **_: pytest.fail('no plan may be built'))
    monkeypatch.setattr(probe, 'experiment_processes', lambda: ['pid 5: experiments/x.py --execute-live'])
    argv = ['--execute-live', '--out', 'artifacts/phase30-2026-09-25/live', '--confirm-entity', 'e',
            '--expect-plan-hash', 'p', '--expect-harness-sha256', 'h', '--expect-protocol-sha256', 's']
    assert probe.main(argv) == 1
    assert 'pid 5' in capsys.readouterr().out


def test_claim_process_alive_tells_this_harness_from_a_reused_pid():
    import subprocess
    harness = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'report_narrow_probe'])
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


# ---------------------------------------------------------------- review round 1: run-safety tests (B1-B4)

def test_r1_default_process_source_is_the_real_table_minus_own_tree(tmp_path, monkeypatch):
    """Through Phase 30's own wrapper, with no processes= injection: the own caffeinate helper is skipped and a
    sibling runner is found (B1, mutant R08)."""
    _artifacts(tmp_path, monkeypatch)
    module = probe._phase26_runner()
    me = os.getpid()
    script = 'scripts/experiments/report_narrow_probe.py'
    rows = [(me, 1, f'./.venv/bin/python {script} --execute-live --out x'),
            (me + 100000, me, f'caffeinate -is ./.venv/bin/python {script} --execute-live --out x'),
            (me + 100001, 1, './.venv/bin/python scripts/experiments/slot2_hidden_probe.py --execute-live')]
    monkeypatch.setattr(module, 'process_list', lambda: rows)
    expected = [f'pid {me + 100001}: scripts/experiments/slot2_hidden_probe.py --execute-live']
    assert probe.experiment_processes() == expected
    assert probe.other_paid_runs(root=tmp_path) == expected
    with pytest.raises(probe.PlanningError, match=f'pid {me + 100001}'):
        probe.check_other_runs(SimpleNamespace(ignore_manifest=[]), root=tmp_path, status=lambda: ('down', None))
    monkeypatch.setattr(module, 'process_list', lambda: rows[:2])
    assert probe.other_paid_runs(root=tmp_path) == []


def test_r1_process_check_fails_closed_when_the_runner_breaks(tmp_path, monkeypatch):
    """B1, mutant R07: an exception inside the process check is itself a blocking entry."""
    def broken():
        raise RuntimeError('boom')
    monkeypatch.setattr(probe, '_phase26_runner', broken)
    entries = probe.experiment_processes()
    assert len(entries) == 1 and 'could not run' in entries[0]
    _artifacts(tmp_path, monkeypatch)
    with pytest.raises(probe.PlanningError, match='could not run'):
        probe.check_other_runs(SimpleNamespace(ignore_manifest=[]), root=tmp_path, status=lambda: ('down', None))


def test_r1_a_later_runs_guard_gets_only_what_the_phase_cap_leaves(tmp_path, monkeypatch, dry_settings):
    """B2, mutants R01 and R02: after an undelivered run charged $3, the SpendGuard enforces $17, not $20."""
    caps = []
    original = probe.SpendGuard

    class Recording(original):
        def __init__(self, cap, *a, **k):
            caps.append(cap)
            super().__init__(cap, *a, **k)
    monkeypatch.setattr(probe, 'SpendGuard', Recording)
    _manifest(tmp_path / 'artifacts', 'phase30-test/first', status='STOPPED', charged_upper_bound=3.0)
    _claim(tmp_path / 'artifacts', 1, 'artifacts/phase30-test/first')
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [], out='artifacts/phase30-test/live-2')
    assert code == 0 and caps and caps[-1] == pytest.approx(17.0)
    assert manifest['spend_cap'] == pytest.approx(17.0)


def test_r1_the_manifest_says_running_before_the_first_provider_call(tmp_path, monkeypatch, dry_settings):
    """B2, mutant R06: --finalize-abandoned charges in-flight attempts only for a RUNNING manifest, so RUNNING
    must be on disk before the first provider call."""
    seen = []
    original = FakeOpenAI.create

    async def create(self, **kwargs):
        on_disk = json.loads((tmp_path / 'artifacts/phase30-test/live' / probe.MANIFEST_NAME).read_text())
        seen.append(on_disk['status'])
        return await original(self, **kwargs)
    monkeypatch.setattr(FakeOpenAI, 'create', create)
    code, manifest, _ = _live(tmp_path, monkeypatch, dry_settings, [])
    assert code == 0 and seen and seen[0] == 'RUNNING'


def test_r1_a_cut_off_first_response_line_counts_as_delivered(tmp_path, monkeypatch, capsys):
    """B3, mutant R12: a hard kill while the first delivered response is written leaves a partial line and a
    manifest that still says 0 delivered; the partial line counts as delivered, so no second run is allowed."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    _claim(artifacts, 1, 'artifacts/phase30-2026-09-25/live')
    _manifest(artifacts, 'phase30-2026-09-25/live', status='RUNNING', ended_at=None, attempts=0,
              generations_delivered=0, statuses={}, charged_upper_bound=0.0)
    full = json.dumps({'request_id': 'r0001', 'status': 'ok', 'raw': report(),
                       'attempts': [{'attempt': 1, 'error': None}]}, sort_keys=True)
    (artifacts / 'phase30-2026-09-25/live/responses.jsonl').write_text(full[: len(full) // 2])
    monkeypatch.setattr(probe, 'claim_process_alive', lambda pid: False)
    assert probe.main(['--finalize-abandoned', f'artifacts/{probe.CLAIM_DIR}/claim-01.json']) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed['generations_delivered'] == 1 and printed['a_new_run_is_allowed'] is False
    manifest = json.loads((artifacts / 'phase30-2026-09-25/live' / probe.MANIFEST_NAME).read_text())
    assert manifest['finalized_abandoned']['partial_lines_skipped'] == 1 and manifest['requests_done'] == 0
    assert manifest['attempts'] == probe.ABANDONED_IN_FLIGHT_ATTEMPTS
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.check_output('artifacts/phase30-2026-09-25/live-2')


def test_r1_an_unknown_delivery_count_a_missing_charge_or_no_end_time_refuses_a_new_run(tmp_path, monkeypatch):
    """B4, mutants R03, R04 and R05."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    # finalize_abandoned writes generations_delivered None when the earlier count cannot be read: it counts as
    # delivered.
    directory = _manifest(artifacts, 'phase30-x/live', status='ABORTED', generations_delivered=None)
    with pytest.raises(probe.PlanningError, match='repeat-until-lucky'):
        probe.live_run_records(artifacts)
    manifest = directory / probe.MANIFEST_NAME
    base = {'status': 'STOPPED', 'started_at': 'x', 'ended_at': 'x', 'generations_delivered': 0, 'statuses': {}}
    # A final, undelivered run must state what it charged; a missing charge is not $0.
    for body in (base, {**base, 'charged_upper_bound': None}, {**base, 'charged_upper_bound': -1.0}):
        manifest.write_text(json.dumps(body))
        with pytest.raises(probe.PlanningError, match='charged_upper_bound'):
            probe.live_run_records(artifacts)
    # A final status without an end time is not final.
    for status in probe.FINAL_STATUSES:
        manifest.write_text(json.dumps({**base, 'status': status, 'ended_at': None, 'charged_upper_bound': 0.0}))
        with pytest.raises(probe.PlanningError, match='not final'):
            probe.live_run_records(artifacts)
    manifest.write_text(json.dumps({**base, 'charged_upper_bound': 0.0}))
    assert probe.live_run_records(artifacts)['undelivered'] == [
        {'manifest': f'artifacts/phase30-x/live/{probe.MANIFEST_NAME}', 'charged_upper_bound': 0.0}]


def test_r1_a_claim_is_exclusive_and_never_overwrites_another(tmp_path, monkeypatch):
    """B4, mutant R09: another launch linked claim-01 after this one counted the claims; the link refuses."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    taken = _claim(artifacts, 1, 'artifacts/phase30-x/first')
    before = taken.read_bytes()
    monkeypatch.setattr(probe, 'live_run_records', lambda _artifacts: {'undelivered': [], 'claim_numbers': []})
    out = (artifacts / 'phase30-x/second').resolve()
    out.mkdir(parents=True)
    with pytest.raises(probe.PlanningError, match='already taken'):
        probe.take_claim(out, 'p' * 64, 'h' * 64, root=tmp_path)
    assert taken.read_bytes() == before
    assert sorted(p.name for p in (artifacts / probe.CLAIM_DIR).iterdir()) == ['claim-01.json']


def test_r1_another_phases_manifest_that_says_running_is_open_even_with_an_end_time(tmp_path, monkeypatch):
    """B4, mutant R10."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    none = lambda: []  # noqa: E731
    name = 'x-manifest.json'
    for fields in ({'status': 'RUNNING'}, {'status': 'Starting'}, {'status': 'COMPLETED', 'stop_reason': 'running'}):
        path = _manifest(artifacts, 'phase29-2026-09-26/live', name=name, **fields) / name
        assert probe.other_paid_runs(root=tmp_path, processes=none) == [f'artifacts/phase29-2026-09-26/live/{name}']
    path.write_text(json.dumps({'status': 'COMPLETED', 'started_at': 'x', 'ended_at': 'x'}))
    assert probe.other_paid_runs(root=tmp_path, processes=none) == []


def test_r1_a_claim_that_names_a_dot_dot_path_is_refused(tmp_path, monkeypatch):
    """B4, mutant R11."""
    artifacts = _artifacts(tmp_path, monkeypatch)
    for out in ('artifacts/phase30-x/..', 'artifacts/phase30-x/.', 'artifacts/phase30-x', f'artifacts/{probe.CLAIM_DIR}/x',
                '/artifacts/phase30-x/live', 'artifacts/phase27-x/live', None, 7):
        assert probe.claimed_output(artifacts, out) is None, out
    assert probe.claimed_output(artifacts, 'artifacts/phase30-x/live') == artifacts.parent / 'artifacts/phase30-x/live'
    _claim(artifacts, 1, 'artifacts/phase30-x/..')
    with pytest.raises(probe.PlanningError, match='names no valid output directory'):
        probe.live_run_records(artifacts)
