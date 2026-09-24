"""Offline checks of the Phase 24 held-out v2 runner against a scripted fake backend.

Synthetic fixtures only: synthetic Phase 23 records in the shape the real runner writes (their
summary comes from the real summarize_fixed_n, and some are written end to end by the real
Phase 23 runner), synthetic studies and held-out checks in a temporary store, and no sealed
partition is ever read (the runner never opens it; the backend does).
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import signal
import sqlite3
import sys
import urllib.error

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/experiments'))
SPEC = importlib.util.spec_from_file_location('run_heldout2_check', ROOT / 'scripts/experiments/run_heldout2_check.py')
held = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(held)
base = held.base
SHIPPED_PINS = {name: getattr(held, name) for name in held.PINS}       # before any monkeypatch
REAL_SIGNAL = signal.signal                                             # before any monkeypatch


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


SCRIPTS = ROOT / 'scripts/experiments'
CONFIG = 'c' * 64
PARTITION_HASH = 'a' * 64
PARTITION_DIR = 'artifacts/phase22-test/heldout-2'
PHASE23_RUNNER = sha(SCRIPTS / 'run_full_loop_fixed_n.py')
OLD = held.EXCLUDED_POLICY_HASHES[0]
NEW = '9' * 64
OTHER = '8' * 64
FREEZE = {'schema_version': 'faultlab-gate-freeze/v1', 'files': {}, 'fingerprints': {},
          'functions': {base.ASSESS_PAIRS_KEY: {'text_sha256': base.ASSESS_PAIRS_TEXT_SHA256}}}
PROCESS = {'processes': [{'pid': 1, 'command': 'python -m uvicorn app.main:app', 'started_at': 'x'}]}


def study(study_id, policy_hash, **changes):
    return {'study_id': study_id, 'replay_of': None, 'decision': 'OBSERVED_IMPROVEMENT',
            'actor_context_protocol': base.ACTOR_CONTEXT, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
            'manifest_hash': base.MANIFEST_HASH, 'selected_candidate_hash': policy_hash,
            'validation_assessment': {'decision': 'OBSERVED_IMPROVEMENT', 'by_case': {
                'notification-3': {'B0': {'completed': 0}, 'L': {'completed': 3}},
                'notification-2': {'B0': {'completed': 0}, 'L': {'completed': 3}}}}, **changes}


def row(attempt, study_id=None, *, certified=False, policy_hash=None, status='COMPLETED', **extra):
    """A Phase 23 attempt row; a certified row's post-checks passed unless said otherwise."""
    value = {'attempt': attempt, 'campaign_id': f'campaign-23-{attempt}', 'study_id': study_id, 'certified': certified,
             'selected_candidate_hash': policy_hash, 'status': status, **extra}
    if certified:
        value.setdefault('post_checks', 'passed')
    return value


# Attempt 1 no certification, attempt 2 re-draws dd62c857 (counted, never re-checked),
# attempt 3 the first NEW certified policy, attempt 4 a later one.
STUDIES = {'s1': study('s1', OTHER, decision='NO_CHANGE'), 's2': study('s2', OLD), 's3': study('s3', NEW),
           's4': study('s4', OTHER)}
ATTEMPTS = [row(1, 's1', policy_hash=OTHER, decision='NO_CHANGE'), row(2, 's2', certified=True, policy_hash=OLD),
            row(3, 's3', certified=True, policy_hash=NEW), row(4, 's4', certified=True, policy_hash=OTHER)]


def phase23(attempts=ATTEMPTS, stop='fixed_n', routing=None, **changes):
    """A Phase 23 record in the shape run_full_loop_fixed_n writes: its summary, and so its
    routing field, comes from the real summarize_fixed_n (R5). `routing` edits summary.routing."""
    rows = json.loads(json.dumps(attempts))
    value = {'declared': {'runner_sha256': PHASE23_RUNNER}, 'stop_reason': stop, 'attempts': rows,
             'summary': held.fixed.summarize_fixed_n(rows, stop_reason=stop)}
    if isinstance(routing, dict):
        value['summary']['routing'].update(routing)
    elif routing is not None:
        value['summary']['routing'] = routing
    value.update(changes)
    return value


@pytest.fixture
def pins(monkeypatch):
    monkeypatch.setattr(held, 'DECLARED_PHASE23_RUNNER_SHA256', PHASE23_RUNNER)


# ---------------------------------------------------------------- scripted routing (pure)

def test_routing_takes_the_first_new_certified_hash_by_attempt_order(pins):
    routed = held.routed_policy(phase23(), STUDIES)
    assert (routed['attempt'], routed['study_id'], routed['policy_hash']) == (3, 's3', NEW)
    assert routed['skipped_excluded'] == [{'attempt': 2, 'policy_hash': OLD}] and routed['post_checks'] == 'passed'


def test_the_routing_field_is_read_where_the_real_runner_writes_it(pins):
    """R2: summary.routing, never a top-level key."""
    value = phase23()
    assert 'routing' not in value and value['summary']['routing']['routable'] is True
    value['routing'] = {'policy_hash': OTHER, 'study_id': 's4', 'attempt': 4}      # ignored
    assert held.routed_policy(value, STUDIES)['attempt'] == 3


def test_routing_ignores_row_order_in_the_file(pins):
    value = phase23()
    value['attempts'].reverse()
    assert held.routed_policy(value, STUDIES)['attempt'] == 3


def test_a_certification_the_store_does_not_support_is_refused(pins):
    studies = {**STUDIES, 's3': study('s3', NEW, replay_of='policy-x')}
    with pytest.raises(held.RoutingError, match='store does not certify'):
        held.routed_policy(phase23(), studies)


def test_a_row_the_phase23_runner_demoted_is_skipped_not_routed(pins):
    attempts = [ATTEMPTS[0], ATTEMPTS[1], row(3, 's3', certified=False, policy_hash=NEW, post_checks='failed: x'),
                ATTEMPTS[3]]
    routed = held.routed_policy(phase23(attempts), STUDIES)
    assert (routed['attempt'], routed['policy_hash'], routed['demoted_by_post_checks']) == (4, OTHER, [3])


def test_a_certified_row_whose_post_checks_never_ran_is_never_routed(pins):
    """R3: a row still 'pending' (the runner stopped between its outcome and its post-checks)."""
    attempts = [*ATTEMPTS[:2], row(3, 's3', certified=True, policy_hash=NEW, post_checks='pending'), ATTEMPTS[3]]
    value = phase23(attempts)
    assert value['summary']['routing']['routable'] is False
    with pytest.raises(held.RoutingError, match='post-checks did not pass'):
        held.routed_policy(value, STUDIES)
    value['summary']['routing']['routable'] = True                  # even if the field were edited
    with pytest.raises(held.RoutingError, match='post-checks did not pass'):
        held.routed_policy(value, STUDIES)


def test_an_unresolved_earlier_attempt_blocks_routing_but_a_later_one_does_not(pins):
    earlier = [row(1, 's1', status=None), *ATTEMPTS[1:]]
    with pytest.raises(held.RoutingError, match='no recorded outcome'):
        held.routed_policy(phase23(earlier), STUDIES)
    later = [*ATTEMPTS[:3], row(4, 's4', status=None)]
    assert held.routed_policy(phase23(later), STUDIES)['attempt'] == 3
    errored = [row(1, None, status=None, error='campaign create: TimeoutError'), *ATTEMPTS[1:]]
    assert held.routed_policy(phase23(errored), STUDIES)['attempt'] == 3


def test_a_row_that_never_got_a_campaign_is_resolved(pins):
    """A stop while POST /api/campaigns was in flight: no campaign, no study, so never certified."""
    phantom = [{'attempt': 1, 'campaign_id': None, 'study_id': None, 'spent_before': 0.0}, *ATTEMPTS[1:]]
    assert held.routed_policy(phase23(phantom), STUDIES)['attempt'] == 3


def test_a_row_with_a_campaign_but_no_study_and_no_outcome_is_never_passed_over(pins):
    """Review round 2: its study may have started after the runner lost sight of it, so it might have
    been certified; only a row with neither a campaign nor a study is passed over."""
    unresolved = [{'attempt': 1, 'campaign_id': 'campaign-23-1', 'study_id': None, 'spent_before': 0.0}, *ATTEMPTS[1:]]
    with pytest.raises(held.RoutingError, match='no recorded outcome'):
        held.routed_policy(phase23(unresolved), STUDIES)


def test_no_new_certified_policy_means_phase24_does_not_run(pins):
    only_old = ATTEMPTS[:2]
    with pytest.raises(held.RoutingError, match='no new policy'):
        held.routed_policy(phase23(only_old), STUDIES)
    with pytest.raises(held.RoutingError, match='declares a routing'):
        held.routed_policy(phase23(only_old, routing={'policy_hash': NEW, 'study_id': 's3', 'attempt': 3}), STUDIES)


@pytest.mark.parametrize('routing', [
    {'policy_hash': OTHER, 'study_id': 's4', 'attempt': 4},    # a later certified policy
    {'policy_hash': OLD, 'study_id': 's2', 'attempt': 2},      # the excluded one
    {'policy_hash': NEW, 'study_id': 's3', 'attempt': 4},      # right policy, wrong attempt
    {'study_id': None},                                        # no study
    'not-a-dict',
])
def test_the_declared_routing_field_must_equal_the_rule(pins, routing):
    with pytest.raises(held.RoutingError, match='differs from the routing rule'):
        held.routed_policy(phase23(routing=routing), STUDIES)


def test_a_missing_declared_routing_field_is_refused(pins):
    value = phase23(); value['summary'].pop('routing')
    with pytest.raises(held.RoutingError, match='differs from the routing rule'):
        held.routed_policy(value, STUDIES)
    value = phase23(); value.pop('summary')
    with pytest.raises(held.RoutingError, match='differs from the routing rule'):
        held.routed_policy(value, STUDIES)


@pytest.mark.parametrize('field', ['routable', 'run_final'])
def test_a_routing_field_that_is_not_final_and_routable_is_refused(pins, field):
    with pytest.raises(held.RoutingError, match='final and routable'):
        held.routed_policy(phase23(routing={field: False}), STUDIES)


@pytest.mark.parametrize('stop', [None, '', 'running', 'starting', 'checkpoint', 'breaker', 'aborted', 'attempt_cap'])
def test_only_a_final_phase23_run_can_route(pins, stop):
    """R3: breaker and aborted runs never route, though they have ended (review round 1)."""
    with pytest.raises(held.RoutingError, match='not final'):
        held.routed_policy(phase23(stop=stop), STUDIES)


def test_both_final_stops_route_and_they_are_phase23s(pins):
    assert held.PHASE23_FINAL_STOPS == held.fixed.FINAL_STOPS == ('fixed_n', 'spend_guard')
    assert held.routed_policy(phase23(stop='spend_guard'), STUDIES)['attempt'] == 3


def test_a_manifest_from_another_runner_cannot_route(pins):
    with pytest.raises(held.RoutingError, match='declared fixed-N runner'):
        held.routed_policy(phase23(declared={'runner_sha256': '3' * 64}), STUDIES)


def test_manifest_and_store_must_name_the_same_policy(pins):
    attempts = [*ATTEMPTS[:2], row(3, 's3', certified=True, policy_hash=OTHER), ATTEMPTS[3]]
    with pytest.raises(held.RoutingError, match='different policies'):
        held.routed_policy(phase23(attempts), STUDIES)


def test_attempts_must_be_numbered_from_one(pins):
    with pytest.raises(held.RoutingError, match='numbered'):
        held.routed_policy(phase23(ATTEMPTS[1:]), STUDIES)


@pytest.mark.parametrize('flag', ['--policy-hash', '--certified-study', '--certified-study-id', '--study', '--candidate',
                                  '--spend-cap', '--max-attempts'])
def test_no_human_argument_can_name_the_policy_the_cap_or_the_attempts(monkeypatch, flag):
    monkeypatch.setattr(sys, 'argv', ['run_heldout2_check.py', '--out', 'x', flag, '500', '--plan'])
    with pytest.raises(SystemExit) as refused:
        held.main()
    assert refused.value.code == 2      # argparse: unrecognized argument


# ---------------------------------------------------------------- routing from records the real Phase 23 runner writes

import test_run_full_loop_fixed_n as T23  # noqa: E402  (the Phase 23 runner's own fake backend and fixture)

NEW23 = 'b' * 64


@pytest.fixture
def real23(tmp_path, monkeypatch):
    run = T23.env.__wrapped__(tmp_path, monkeypatch)
    monkeypatch.setattr(held, 'ROOT', tmp_path)
    return run


def routed_from(run, monkeypatch, out='phase23-test'):
    manifest = json.loads(run.manifest(out).read_text())
    monkeypatch.setattr(held, 'DECLARED_PHASE23_RUNNER_SHA256', manifest['declared']['runner_sha256'])
    return manifest, held.load_routing(run.store)


def test_a_real_fixed_n_record_routes_its_first_new_certified_policy(real23, monkeypatch):
    monkeypatch.setattr(T23.fixed, 'N_ATTEMPTS', 3)
    real23(T23.FakeBackend(real23.store, [T23.OK, T23.certified_study(NEW23), T23.OK]))
    manifest, routed = routed_from(real23, monkeypatch)
    assert manifest['stop_reason'] == 'fixed_n' and 'routing' not in manifest
    assert (routed['attempt'], routed['policy_hash'], routed['post_checks']) == (2, NEW23, 'passed')
    assert routed['phase23_manifest'] == 'artifacts/phase23-test/full-loop-manifest.json'


def test_a_real_spend_guard_record_routes(real23, monkeypatch):
    monkeypatch.setattr(T23.fixed, 'N_ATTEMPTS', 30)
    real23(T23.FakeBackend(real23.store, [T23.certified_study(NEW23)] + [T23.OK] * 29, spend=10.0))
    manifest, routed = routed_from(real23, monkeypatch)
    assert manifest['stop_reason'] == 'spend_guard' and routed['attempt'] == 1


def test_a_real_breaker_record_never_routes(real23, monkeypatch):
    monkeypatch.setattr(T23.fixed, 'N_ATTEMPTS', 12)
    real23(T23.FakeBackend(real23.store, [T23.certified_study(NEW23)] + [T23.DEAD] * 5 + [T23.OK] * 6))
    with pytest.raises(held.RoutingError, match='not final'):
        routed_from(real23, monkeypatch)


def test_a_real_aborted_record_never_routes(real23, monkeypatch):
    real23(T23.FakeBackend(real23.store, [T23.certified_study(NEW23), T23.study(protocol='faultlab-actor-context/v1')]
                           + [T23.OK] * 4))
    with pytest.raises(held.RoutingError, match='not final'):
        routed_from(real23, monkeypatch)


def test_a_real_record_whose_post_checks_never_ran_never_routes(real23, monkeypatch):
    """A signal between a study's saved outcome and its post-checks: the row stays 'pending'."""
    monkeypatch.setattr(T23.fixed, 'N_ATTEMPTS', 3)
    backend = T23.FakeBackend(real23.store, [T23.certified_study(NEW23), T23.OK, T23.OK])
    state = {'polled': False, 'fired': False}

    def detach_in_the_idle_wait(base_url, method, path, body=None, timeout=30):
        if path.startswith('/api/completion-studies/'):
            state['polled'] = True
        elif path == '/api/config/status' and state['polled'] and not state['fired']:
            state['fired'] = True
            raise base.Detached(15)
        return backend(base_url, method, path, body, timeout)
    real23(detach_in_the_idle_wait)
    manifest = json.loads(real23.manifest().read_text())
    assert manifest['attempts'][0]['post_checks'] == 'pending' and manifest['stop_reason'] == 'aborted'
    with pytest.raises(held.RoutingError, match='not final'):
        routed_from(real23, monkeypatch)


def test_a_real_record_with_a_stop_during_campaign_create_still_routes(real23, monkeypatch):
    """The labelled row is resolved: it can never have been certified."""
    monkeypatch.setattr(T23.fixed, 'N_ATTEMPTS', 4)
    backend = T23.FakeBackend(real23.store, [T23.certified_study(NEW23), T23.OK, T23.OK, T23.OK])
    state = {'fired': False}

    def ctrl_c_on_first_create(base_url, method, path, body=None, timeout=30):
        if path == '/api/campaigns' and method == 'POST' and not state['fired']:
            state['fired'] = True
            raise KeyboardInterrupt
        return backend(base_url, method, path, body, timeout)
    real23(ctrl_c_on_first_create)
    real23(ctrl_c_on_first_create, '--resume', '--after-abort')
    manifest, routed = routed_from(real23, monkeypatch)
    assert manifest['attempts'][0]['campaign_id'] is None and routed['attempt'] == 2


# ---------------------------------------------------------------- worst case and pins

def test_the_worst_case_is_every_pair_reserved_and_retried_once():
    from app.lab.heldout_check import TRIALS_PER_REPLICA, replica_layout
    heldout2 = [{'case_id': 'none', 'fault_spec': {'primitives': []}}] + [
        {'case_id': f'k{i}', 'fault_spec': {'primitives': [{'kind': 'F'}]}} for i in range(5)]
    assert held.PLANNED_PAIRS == len(replica_layout(heldout2)) * TRIALS_PER_REPLICA == 78
    assert held.PLANNED_EPISODES == 156 and held.WORST_CASE_CALLS_PER_ATTEMPT == 2496
    assert held.worst_case_dollars() == 52.17 and held.worst_case_dollars(0.01) == 24.96
    # With the $87 cap the guard guarantees one attempt; a second needs <= $34.83 charged.
    assert held.SPEND_CAP == 87.0 and held.SPEND_CAP // held.worst_case_dollars() == 1


def test_the_runners_check_identity_is_the_backends(pins):
    """Review round 2: the identity a started check must carry is built from the runner's constants, and
    the fake backend builds it from the same constants, so a drift from the real service would pass every
    fake-backed test and then stop Phase 24 after one attempt. Pin them to the backend's own values."""
    from app.lab import heldout_check as backend_check
    assert held.PREDICATE == backend_check.PREDICATE_V2 and held.PARTITION == backend_check.PARTITION_V2
    assert base.ACTOR_CONTEXT == backend_check.CERTIFIED_ACTOR_CONTEXT
    assert held.EXCLUDED_POLICY_HASHES == tuple(held.fixed.EXCLUDED_FROM_ROUTING)
    heldout2 = [{'case_id': 'none', 'fault_spec': {'primitives': []}}] + [
        {'case_id': f'k{i}', 'fault_spec': {'primitives': [{'kind': 'F'}]}} for i in range(5)]
    layout = backend_check.replica_layout(heldout2)
    assert held.PLANNED_PAIRS == len(layout) * backend_check.TRIALS_PER_REPLICA
    assert held.MAX_ATTEMPTS == backend_check.MAX_ATTEMPTS_PER_POLICY


def test_only_a_compared_matching_check_can_be_the_verdict():
    """Review round 2: a decision on a check that was never compared with the declared one, or that
    failed the comparison, is never the run's verdict."""
    assert held.is_verdict({'decision': 'NO_HARM', 'identity_checked': True})
    assert held.is_verdict({'decision': 'HARM', 'identity_checked': True})
    assert not held.is_verdict({'decision': 'NO_HARM'})
    assert not held.is_verdict({'decision': 'NO_HARM', 'identity_checked': True, 'identity_mismatch': True})
    assert not held.is_verdict({'decision': 'INCOMPLETE', 'identity_checked': True})


def test_every_shipped_pin_is_a_placeholder_or_well_formed():
    """Holds before the Phase 22 freeze (placeholders) and after it (filled): R6."""
    for name, value in SHIPPED_PINS.items():
        if value == held.PLACEHOLDER:
            continue
        assert held.is_repo_path(value) if name == 'DECLARED_PARTITION_DIR' else held.fixed.is_sha256(value), name


FILLED_FILES = {'DECLARED_PROTOCOL_SHA256': held.PROTOCOL,
                'DECLARED_BASE_RUNNER_SHA256': 'scripts/experiments/run_full_loop.py',
                'DECLARED_PHASE23_RUNNER_SHA256': 'scripts/experiments/run_full_loop_fixed_n.py',
                'DECLARED_FREEZE_SHA256': 'artifacts/phase22-2026-09-24/gate-freeze-after.json'}


@pytest.mark.parametrize('name', sorted(FILLED_FILES))
def test_a_filled_pin_matches_its_file(name):
    if SHIPPED_PINS[name] == held.PLACEHOLDER:
        pytest.skip('not filled until the Phase 22 freeze')
    assert sha(ROOT / FILLED_FILES[name]) == SHIPPED_PINS[name]


@pytest.mark.parametrize('name,value,problem', [
    ('DECLARED_CONFIGURATION_HASH', 'c4169ee4…', 'not 64 lowercase hex'),
    ('DECLARED_PARTITION_MANIFEST_HASH', 'A' * 64, 'not 64 lowercase hex'),
    ('DECLARED_FREEZE_SHA256', 'f' * 63, 'not 64 lowercase hex'),
    ('DECLARED_PARTITION_DIR', '../heldout2/partition', 'not a repository-relative path'),
    ('DECLARED_PARTITION_DIR', '/abs/heldout2', 'not a repository-relative path'),
    ('DECLARED_PARTITION_DIR', 'artifacts//heldout2', 'not a repository-relative path'),
    ('DECLARED_PARTITION_DIR', held.PLACEHOLDER, 'placeholder'),
])
def test_pin_problems_names_every_malformed_pin(monkeypatch, name, value, problem):
    for pin in held.PINS:
        monkeypatch.setattr(held, pin, 'artifacts/heldout2/partition' if pin == 'DECLARED_PARTITION_DIR' else 'd' * 64)
    assert held.pin_problems() == []
    monkeypatch.setattr(held, name, value)
    assert held.pin_problems() == [f'{name} ({problem})']


def test_plan_is_dry_and_lists_the_unfilled_pins(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(base, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no HTTP')))
    monkeypatch.setattr(sys, 'argv', ['run_heldout2_check.py', '--out', str(tmp_path / 'p'), '--plan'])
    assert held.main() == 0
    out = capsys.readouterr().out
    assert 'Dry plan only' in out and '$52.17' in out and '1 attempt(s) are guaranteed' in out and '$87.00' in out
    assert ('NOT FILLED' in out) == bool(held.unfilled_pins())


def test_the_plan_shows_each_pins_state_and_whether_each_pinned_file_matches(tmp_path, monkeypatch, capsys):
    """Review round 2: a wrong pin shows in the dry plan, before the approval record is written."""
    monkeypatch.setattr(base, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no HTTP')))
    root = tmp_path / 'repo'
    (root / 'artifacts/heldout2/partition').mkdir(parents=True)
    (root / 'artifacts/heldout2/partition/manifest_hash').write_text(PARTITION_HASH + '\n')
    protocol = root / held.PROTOCOL
    protocol.parent.mkdir(parents=True)
    protocol.write_text('protocol')
    settings_file = root / 'settings.json'; settings_file.write_text('{}')
    freeze = root / 'freeze.json'; freeze.write_text('{}')
    monkeypatch.setattr(held, 'ROOT', root)
    filled = {'DECLARED_FREEZE_SHA256': sha(freeze), 'DECLARED_CONFIGURATION_HASH': CONFIG,
              'DECLARED_PROTOCOL_SHA256': sha(protocol), 'DECLARED_PARTITION_MANIFEST_HASH': PARTITION_HASH,
              'DECLARED_PARTITION_DIR': 'artifacts/heldout2/partition',
              'DECLARED_BASE_RUNNER_SHA256': sha(SCRIPTS / 'run_full_loop.py'),
              'DECLARED_PHASE23_RUNNER_SHA256': PHASE23_RUNNER, 'DECLARED_SETTINGS_SHA256': sha(settings_file)}
    for name, value in filled.items():
        monkeypatch.setattr(held, name, value)
    monkeypatch.setattr(held.fixed, 'DECLARED_DRIFT_CHECKER_SHA256', sha(SCRIPTS / 'check_clock_drift.py'))
    monkeypatch.setattr(held.fixed, 'DECLARED_INGESTION_CHECK_SHA256', sha(SCRIPTS / 'check_ingestion_health.py'))

    def plan():
        monkeypatch.setattr(sys, 'argv', ['run_heldout2_check.py', '--out', str(tmp_path / 'p'), '--plan',
                                          '--settings', str(settings_file), '--expect-freeze', str(freeze)])
        assert held.main() == 0
        return {line[11:59].strip(): line[59:].split()[0] for line in capsys.readouterr().out.splitlines()
                if line.startswith('pin        ')}
    states = plan()
    assert 'NOT FILLED' not in states.values() and 'MALFORMED' not in states.values()
    assert all(states[label] == 'MATCH' for label in ('run_full_loop.py', 'gate_freeze.py', 'run_full_loop_fixed_n.py',
                                                       'check_clock_drift.py', 'check_ingestion_health.py',
                                                       'settings file', 'protocol', 'freeze file',
                                                       'partition manifest_hash file (public)')), states
    monkeypatch.setattr(held, 'DECLARED_PROTOCOL_SHA256', '0' * 64)                  # a mistyped pin
    monkeypatch.setattr(held, 'DECLARED_PARTITION_MANIFEST_HASH', 'b' * 64)
    monkeypatch.setattr(held, 'DECLARED_CONFIGURATION_HASH', 'c4169ee4…')
    states = plan()
    assert states['protocol'] == 'DIFFERS' and states['partition manifest_hash file (public)'] == 'DIFFERS'
    assert states['DECLARED_CONFIGURATION_HASH'] == 'MALFORMED' and not (tmp_path / 'p').exists()


def test_a_live_run_is_refused_while_any_placeholder_remains(tmp_path, monkeypatch):
    monkeypatch.setattr(base, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no HTTP')))
    monkeypatch.setattr(held, 'DECLARED_CONFIGURATION_HASH', held.PLACEHOLDER)
    monkeypatch.setattr(sys, 'argv', ['run_heldout2_check.py', '--out', str(tmp_path / 'p'), '--execute-live',
                                      '--confirm-entity', 'entity'])
    with pytest.raises(SystemExit, match='placeholders'):
        held.main()


# ---------------------------------------------------------------- the runner, end to end

def by_case(untriggered_l=0):
    counts = lambda u: {'attempted': 15, 'completed': 15 - u, 'untriggered': u}  # noqa: E731
    return {'heldout-2-1': {'B0': counts(0), 'L': counts(0)}, 'heldout-2-2': {'B0': counts(1), 'L': counts(untriggered_l)}}


class FakeBackend:
    def __init__(self, store, outcomes, *, config_hash=CONFIG, spend=4.0, lose_reply=False, hang=False,
                 list_fails=False, commit_after_lists=0, on_poll=None, identity_changes=None, refuse=False,
                 aria=False, start_status=None, untriggered_l=0):
        self.store, self.outcomes, self.config_hash, self.spend = store, list(outcomes), config_hash, spend
        self.lose_reply, self.hang, self.list_fails = lose_reply, hang, list_fails
        self.commit_after_lists, self.list_calls, self.pending, self.on_poll = commit_after_lists, 0, None, on_poll
        self.identity_changes, self.refuse, self.aria = identity_changes or {}, refuse, aria
        self.start_status, self.untriggered_l = start_status, untriggered_l
        self.campaigns, self.ledgers, self.checks, self.stops, self.bodies = [], {}, {}, [], []
        self.active, self.created = None, 0
        self.actor = base.EXPECTED_ACTOR

    def put(self, kind, id, payload):
        con = sqlite3.connect(self.store)
        con.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload',
                    (kind, id, json.dumps(payload)))
        con.commit(); con.close()

    def finish(self, check_id, decision):
        """The backend ends a check that was left running."""
        self.checks[check_id].update(status='INCOMPLETE' if decision == 'INCOMPLETE' else 'COMPLETED', decision=decision)
        self.put('heldout_checks', check_id, self.checks[check_id]); self.active = None

    def __call__(self, b, method, path, body=None, timeout=30):
        if path == '/api/config/status':
            return {'live_enabled': True, 'active_campaign_id': self.active,
                    'models': {'actor': self.actor, 'mechanic': base.EXPECTED_MECHANIC}}
        if path == '/api/readiness':      # the real route's shape (coordinator.readiness)
            return {'ready': True, 'simulator': {'ready': True, 'code': 'READY', 'message': 'm'},
                    'live_configuration': {'ready': True, 'missing_fields': []}, 'provider_access': 'not_checked',
                    'provider_calls': 0, 'models': {'actor': self.actor}}
        if path == '/api/campaigns' and method == 'POST':
            cid = f'campaign-{len(self.campaigns) + 1}'; self.campaigns.append(cid)
            self.put('campaign_provenance', cid, {'aria_publication_enabled': self.aria})
            return {'campaign_id': cid, 'configuration_hash': self.config_hash}
        if path.endswith('/heldout-check') and method == 'POST':
            self.bodies.append(body)
            assert body == {'execute_live': True, 'certified_study_id': 's3', 'partition_dir': PARTITION_DIR,
                            'manifest_hash': PARTITION_HASH, 'predicate': held.PREDICATE}
            cid = path.split('/')[3]
            if self.refuse:      # e.g. the backend's finality guard: 409, nothing started
                raise urllib.error.HTTPError(path, 409, 'This policy already has a held-out verdict; it is final', {}, None)
            if self.start_status:   # e.g. ServiceNotReady: 503 before any check exists
                raise urllib.error.HTTPError(path, self.start_status, 'SERVICE_NOT_READY', {}, None)
            self.created += 1
            check_id = f'heldout-check-{self.created}'
            decision = self.outcomes.pop(0)
            identity = {'check_id': check_id, 'campaign_id': cid, 'policy_hash': NEW, 'predicate': held.PREDICATE,
                        'actor_context_protocol': base.ACTOR_CONTEXT, 'partition': 'heldout-2',
                        'certified_study_id': 's3', 'manifest_hash': PARTITION_HASH, 'planned_pairs': 78,
                        **self.identity_changes}
            record = {**identity, 'status': 'INCOMPLETE' if decision == 'INCOMPLETE' else 'COMPLETED',
                      'decision': decision, 'reason': 'r', 'batch_id': 'b', 'trials': 156, 'pairs': 78,
                      'assessment': {'decision': decision, 'by_case': by_case(self.untriggered_l)}}
            self.ledgers[cid] = {'charged_dollar_upper_bound': self.spend, 'used_calls': 100}
            if self.hang:
                self.active = cid
                record['status'] = 'RUNNING'
            if self.commit_after_lists:
                self.pending = record                             # not visible yet: committed late
                raise TimeoutError('reply timed out before the server committed the check')
            self.checks[check_id] = record
            self.put('heldout_checks', check_id, record)
            if self.lose_reply:
                self.lose_reply = False
                raise TimeoutError('reply lost after the server started the check')
            return {**identity, 'status': 'QUEUED'}
        if path.endswith('/heldout-checks') and method == 'GET':
            if self.list_fails:
                raise OSError('list failed')
            self.list_calls += 1
            if self.pending and self.list_calls >= self.commit_after_lists:
                self.checks[self.pending['check_id']] = self.pending
                self.put('heldout_checks', self.pending['check_id'], self.pending); self.pending = None
            cid = path.split('/')[3]
            return [c for c in self.checks.values() if c['campaign_id'] == cid]
        if path.startswith('/api/heldout-checks/'):
            if self.on_poll:
                self.on_poll(self)
            return self.checks[path.rsplit('/', 1)[1]]
        if path.endswith('/completion-studies'):
            return []
        if path.endswith('/budget'):
            return self.ledgers.get(path.split('/')[3], {'reservations': {}})
        if path.endswith('/stop'):
            self.stops.append(path); self.active = None
            for check in self.checks.values():
                if check['campaign_id'] == path.split('/')[3] and check['status'] == 'RUNNING':
                    check.update(status='INTERRUPTED', decision='INCOMPLETE')
                    self.put('heldout_checks', check['check_id'], check)
            return {}
        raise AssertionError(f'unexpected {method} {path}')


@pytest.fixture
def env(tmp_path, monkeypatch):
    freeze = tmp_path / 'freeze.json'; freeze.write_text(json.dumps(FREEZE))
    settings_file = tmp_path / 'settings.json'; settings_file.write_text('{}')
    protocol = tmp_path / held.PROTOCOL; protocol.parent.mkdir(parents=True); protocol.write_text('protocol')
    store = tmp_path / 'lab.sqlite3'
    con = sqlite3.connect(store)
    con.execute('CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id))')
    con.execute('CREATE TABLE events(episode_id TEXT NOT NULL,seq INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(episode_id,seq))')
    for sid, value in STUDIES.items():
        con.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?)', ('completion_studies', sid, json.dumps(value)))
    con.commit(); con.close()
    record23 = tmp_path / 'artifacts/phase23-test/full-loop-manifest.json'
    record23.parent.mkdir(parents=True); record23.write_text(json.dumps(phase23()))
    monkeypatch.setattr(held, 'ROOT', tmp_path)
    monkeypatch.setattr(held, 'DECLARED_FREEZE_SHA256', sha(freeze))
    monkeypatch.setattr(held, 'DECLARED_CONFIGURATION_HASH', CONFIG)
    monkeypatch.setattr(held, 'DECLARED_PROTOCOL_SHA256', sha(protocol))
    monkeypatch.setattr(held, 'DECLARED_PARTITION_MANIFEST_HASH', PARTITION_HASH)
    monkeypatch.setattr(held, 'DECLARED_PARTITION_DIR', PARTITION_DIR)
    monkeypatch.setattr(held, 'DECLARED_BASE_RUNNER_SHA256', sha(SCRIPTS / 'run_full_loop.py'))
    monkeypatch.setattr(held, 'DECLARED_PHASE23_RUNNER_SHA256', PHASE23_RUNNER)
    monkeypatch.setattr(held, 'DECLARED_SETTINGS_SHA256', sha(settings_file))
    monkeypatch.setattr(held.fixed, 'DECLARED_DRIFT_CHECKER_SHA256', sha(SCRIPTS / 'check_clock_drift.py'))
    monkeypatch.setattr(held.fixed, 'DECLARED_INGESTION_CHECK_SHA256', sha(SCRIPTS / 'check_ingestion_health.py'))
    monkeypatch.setattr(held, 'ingestion_health', lambda: {'exit_status': 0, 'output': 'HEALTHY'})
    monkeypatch.setattr(base, 'gate_freeze', lambda: json.loads(json.dumps(FREEZE)))
    monkeypatch.setattr(base, 'check_backend_process', lambda: PROCESS)
    monkeypatch.setattr(signal, 'signal', lambda *a: None)     # the runner imports signal inside main()
    # A fake clock: every wait advances it, so no deadline loop spins in real time.
    clock = [0.0]
    monkeypatch.setattr(base.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(base.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + max(s, 0.5)))
    import app.config
    monkeypatch.setattr(app.config.Settings, 'from_env', classmethod(
        lambda cls: type('S', (), {'wandb_entity': 'entity', 'project_path': base.EXPECTED_PROJECT,
                                   'model_call_dollar_bounds': {'actor': 0.0209, 'mechanic': 0.05}})()))
    review = tmp_path / 'review.json'

    def write_review(**changes):
        record = {'phase': 24, 'status': 'approved', 'approved_by': 'test reviewer',
                  'protocol_sha256': sha(protocol), 'runner_sha256': sha(SCRIPTS / 'run_heldout2_check.py'),
                  'gate_freeze_file_sha256': sha(freeze), 'configuration_hash': CONFIG,
                  'partition_manifest_hash': PARTITION_HASH, 'routed_policy_hash': NEW, 'routed_study_id': 's3'}
        record.update(changes)
        review.write_text(json.dumps({k: v for k, v in record.items() if v is not None}))
    write_review()

    def run(backend, *extra, out='phase24-test'):
        monkeypatch.setattr(base, 'api', backend)
        monkeypatch.setattr(sys, 'argv', ['run_heldout2_check.py', '--out', str(tmp_path / 'artifacts' / out),
                                          '--store', str(store), '--settings', str(settings_file),
                                          '--expect-freeze', str(freeze), '--review-record', str(review),
                                          '--poll', '0', '--idle-grace', '2', '--execute-live',
                                          '--confirm-entity', 'entity', *extra])
        held.main()
        return json.loads(run.manifest(out).read_text())
    run.store, run.root, run.record23, run.freeze, run.settings = store, tmp_path, record23, freeze, settings_file
    run.write_review = write_review
    run.manifest = lambda out='phase24-test': tmp_path / 'artifacts' / out / 'heldout-manifest.json'
    return run


@pytest.mark.parametrize('verdict', ['NO_HARM', 'HARM'])
def test_the_first_verdict_is_final_and_the_policy_is_the_routed_one(env, verdict):
    backend = FakeBackend(env.store, [verdict, 'NO_HARM'])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'verdict' and manifest['verdict'] == verdict
    assert len(manifest['attempts']) == 1 and len(backend.checks) == 1 and manifest['attempts_used'] == 1
    assert (manifest['policy_hash'], manifest['certified_study'], manifest['routing']['attempt']) == (NEW, 's3', 3)
    assert manifest['routing']['phase23_manifest'] == 'artifacts/phase23-test/full-loop-manifest.json'
    assert (manifest['predicate'], manifest['partition'], manifest['manifest_hash']) == (held.PREDICATE, 'heldout-2', PARTITION_HASH)
    assert manifest['worst_case_per_attempt'] == 52.17 and manifest['total_charged_upper_bound'] == pytest.approx(4.0)
    assert manifest['spend_cap'] == 87.0 and manifest['declared']['spend_cap'] == 87.0
    assert manifest['sessions'][0]['ingestion_health']['exit_status'] == 0


def test_only_an_attempt_without_a_verdict_is_replaced(env):
    backend = FakeBackend(env.store, ['INCOMPLETE', 'HARM', 'NO_HARM'])
    manifest = env(backend)
    assert [r['decision'] for r in manifest['attempts']] == ['INCOMPLETE', 'HARM'] and manifest['verdict'] == 'HARM'


def test_attempts_are_capped_at_three(env):
    backend = FakeBackend(env.store, ['INCOMPLETE'] * 5, spend=1.0)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'attempt_cap' and len(manifest['attempts']) == 3 and manifest['verdict'] is None


@pytest.mark.parametrize('spend,attempts', [(20.0, 2), (34.83, 2), (34.84, 1)])
def test_the_spend_guard_uses_the_hard_worst_case(env, spend, attempts):
    """At $87 with a $52.17 worst case, a later attempt needs the total so far <= $34.83."""
    backend = FakeBackend(env.store, ['INCOMPLETE'] * 5, spend=spend)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'spend_guard' and len(manifest['attempts']) == attempts


def test_a_headroom_below_the_worst_case_is_refused(env):
    backend = FakeBackend(env.store, ['NO_HARM'])
    with pytest.raises(SystemExit, match='below the hard worst case'):
        env(backend, '--headroom', '26.09')
    assert not backend.checks


def test_a_configuration_mismatch_stops_at_no_cost_and_uses_no_attempt(env):
    backend = FakeBackend(env.store, ['NO_HARM'], config_hash='d' * 64)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and not backend.checks and 'configuration_hash' in manifest['abort_detail']
    assert manifest['attempts_used'] == 0 and manifest['attempts'][0]['error'].startswith('configuration_hash mismatch')


@pytest.mark.parametrize('changes', [{'manifest_hash': 'b' * 64}, {'planned_pairs': 18}, {'partition': 'promotion'},
                                     {'predicate': 'faultlab-heldout-no-harm/v1'}, {'policy_hash': OTHER}])
def test_a_started_check_that_is_not_the_declared_one_is_stopped_and_is_never_the_verdict(env, changes):
    backend = FakeBackend(env.store, ['NO_HARM'], identity_changes=changes)
    manifest = env(backend)
    row_ = manifest['attempts'][0]
    assert manifest['stop_reason'] == 'aborted' and 'not the declared check' in manifest['abort_detail']
    assert backend.stops == ['/api/campaigns/campaign-1/stop'] and row_['identity_mismatch'] and row_['stop_requested']
    assert manifest['verdict'] is None


def test_it_refuses_to_overwrite_a_run_or_open_a_second_folder(env):
    backend = FakeBackend(env.store, ['NO_HARM'])
    env(backend)
    with pytest.raises(SystemExit, match='refusing to overwrite'):
        env(backend)
    with pytest.raises(SystemExit, match='Another Phase 24 run exists'):
        env(backend, out='phase24-other')
    with pytest.raises(SystemExit, match='Another Phase 24 run exists'):
        env(backend, '--resume', '--after-abort', out='phase24-other')


def test_routing_refusals_start_nothing(env):
    env.record23.write_text(json.dumps(phase23(routing={'policy_hash': OTHER, 'study_id': 's4', 'attempt': 4})))
    backend = FakeBackend(env.store, ['NO_HARM'])
    with pytest.raises(SystemExit, match='Routing refused'):
        env(backend)
    assert not backend.campaigns and not env.manifest().exists()


def test_two_phase23_records_cannot_route(env):
    second = env.root / 'artifacts/phase23-other/full-loop-manifest.json'
    second.parent.mkdir(parents=True); second.write_text(env.record23.read_text())
    backend = FakeBackend(env.store, ['NO_HARM'])
    with pytest.raises(SystemExit, match='exactly one Phase 23 run record, found 2'):
        env(backend)


def test_a_changed_protocol_or_freeze_is_refused(env, monkeypatch):
    (env.root / held.PROTOCOL).write_text('edited after the freeze')
    backend = FakeBackend(env.store, ['NO_HARM'])
    with pytest.raises(SystemExit, match='protocol is not the declared one'):
        env(backend)
    monkeypatch.setattr(held, 'DECLARED_PROTOCOL_SHA256', hashlib.sha256(b'edited after the freeze').hexdigest())
    env.write_review(protocol_sha256=hashlib.sha256(b'edited after the freeze').hexdigest())
    monkeypatch.setattr(base, 'gate_freeze', lambda: {**FREEZE, 'files': {'x': 1}})
    with pytest.raises(SystemExit, match='differs from the reviewed freeze'):
        env(backend)
    assert not backend.checks


def no_http(*a, **k):
    raise AssertionError('no HTTP call may happen before this refusal')


@pytest.mark.parametrize('pin,match', [
    ('settings', 'settings file is not the declared one'),
    ('base', 'run_full_loop.py is not the reviewed Phase 17 runner'),
    ('gate_freeze', 'gate_freeze.py is not the reviewed script'),
    ('phase23', 'not the declared Phase 23 runner'),
    ('drift', 'check_clock_drift.py is not'),
    ('ingestion', 'check_ingestion_health.py is not'),
    ('freeze', 'freeze file is not the one declared'),
])
def test_every_file_pin_refuses_before_any_http_call(env, monkeypatch, pin, match):
    if pin == 'settings':
        env.settings.write_text('{"edited": true}')
    elif pin == 'base':
        monkeypatch.setattr(held, 'DECLARED_BASE_RUNNER_SHA256', '0' * 64)
    elif pin == 'gate_freeze':
        monkeypatch.setattr(base, 'DECLARED_GATE_FREEZE_SCRIPT_SHA256', '0' * 64)
    elif pin == 'phase23':
        monkeypatch.setattr(held, 'DECLARED_PHASE23_RUNNER_SHA256', '0' * 64)
    elif pin == 'drift':
        monkeypatch.setattr(held.fixed, 'DECLARED_DRIFT_CHECKER_SHA256', held.fixed.PLACEHOLDER)
    elif pin == 'ingestion':
        monkeypatch.setattr(held.fixed, 'DECLARED_INGESTION_CHECK_SHA256', '0' * 64)
    elif pin == 'freeze':
        env.freeze.write_text(json.dumps(FREEZE, indent=2))       # the same content, another file
    with pytest.raises(SystemExit, match=match):
        env(no_http)


@pytest.mark.parametrize('name,value', [('DECLARED_CONFIGURATION_HASH', 'c4169ee4…'),
                                        ('DECLARED_PARTITION_MANIFEST_HASH', 'a' * 63),
                                        ('DECLARED_PARTITION_DIR', '../heldout2/partition')])
def test_a_malformed_pin_is_refused_before_any_http_call(env, monkeypatch, name, value):
    monkeypatch.setattr(held, name, value)
    with pytest.raises(SystemExit, match=name):
        env(no_http)
    assert not env.manifest().exists()


@pytest.mark.parametrize('change,match', [
    ({'status': 'draft'}, "status 'approved'"),
    ({'approved_by': ' '}, 'approved_by'),
    ({'runner_sha256': '0' * 64}, 'runner_sha256'),
    ({'protocol_sha256': None}, 'protocol_sha256'),
    ({'gate_freeze_file_sha256': '0' * 64}, 'gate_freeze_file_sha256'),
    ({'configuration_hash': 'e' * 64}, 'configuration_hash'),
    ({'partition_manifest_hash': 'b' * 64}, 'partition_manifest_hash'),
    ({'routed_policy_hash': OTHER}, 'routed_policy_hash'),
    ({'routed_study_id': 's4'}, 'routed_study_id'),
])
def test_the_review_record_must_approve_this_runner_and_repeat_every_value(env, change, match):
    """R7: the Phase 24 runner is bound to what was reviewed, before any HTTP call."""
    env.write_review(**change)
    with pytest.raises(SystemExit, match=match):
        env(no_http)
    assert not env.manifest().exists()


def test_a_missing_review_record_is_refused(env):
    (env.root / 'review.json').unlink()
    with pytest.raises(SystemExit, match='missing or not JSON'):
        env(no_http)


def test_the_entity_must_match_the_settings(env):
    with pytest.raises(SystemExit, match='--confirm-entity'):
        env(no_http, '--confirm-entity', 'someone-else')


def test_an_active_backend_is_refused_before_anything_is_created(env):
    backend = FakeBackend(env.store, ['NO_HARM'])
    backend.active = 'campaign-other'
    with pytest.raises(SystemExit, match='Another execution is active'):
        env(backend)
    assert not backend.campaigns and not env.manifest().exists()


def test_a_backend_process_that_changes_between_attempts_starts_nothing_more(env, monkeypatch):
    calls = {'n': 0}

    def process():
        calls['n'] += 1                          # 1 start of run, 2 before attempt 1, 3 before attempt 2
        return PROCESS if calls['n'] < 3 else {'processes': [{'pid': 2, 'command': 'uvicorn', 'started_at': 'y'}]}
    monkeypatch.setattr(base, 'check_backend_process', process)
    backend = FakeBackend(env.store, ['INCOMPLETE', 'NO_HARM'])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'process changed' in manifest['abort_detail']
    assert len(backend.campaigns) == 1 and manifest['verdict'] is None


def test_aria_on_refuses_the_campaign_before_any_check(env):
    backend = FakeBackend(env.store, ['NO_HARM'], aria=True)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'Aria' in manifest['abort_detail'] and not backend.checks
    assert manifest['attempts'][0]['error'].startswith('store or Aria')


def test_a_backend_whose_models_change_between_attempts_is_refused(env):
    def swap(fake):
        fake.actor = 'someone/else'
    backend = FakeBackend(env.store, ['INCOMPLETE', 'NO_HARM'], on_poll=swap)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'Backend Actor' in manifest['abort_detail']
    assert len(backend.checks) == 1


def test_an_attempt_waits_for_an_idle_backend_before_it_starts(env, monkeypatch):
    calls = {'n': 0}

    def idle(base_url, seconds, poll):
        calls['n'] += 1
        return calls['n'] != 3                   # 1 before attempt 1, 2 after it, 3 before attempt 2
    monkeypatch.setattr(base, 'wait_until_idle', idle)
    backend = FakeBackend(env.store, ['INCOMPLETE', 'NO_HARM'])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and manifest['abort_detail'] == 'backend is not idle'
    assert len(backend.checks) == 1


def test_a_refused_start_uses_no_attempt_and_nothing_is_adopted(env):
    backend = FakeBackend(env.store, ['NO_HARM'], refuse=True)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and manifest['verdict'] is None and not backend.checks
    assert manifest['attempts'][0]['start_error'] == 'HTTPError' and backend.list_calls == 1 and not backend.stops
    assert manifest['attempts_used'] == 0


def test_a_lost_start_reply_is_adopted_not_lost(env):
    backend = FakeBackend(env.store, ['NO_HARM'], lose_reply=True)
    manifest = env(backend)
    row_ = manifest['attempts'][0]
    assert row_['adopted_after_start_error'] and row_['start_error'] == 'TimeoutError'
    assert manifest['verdict'] == 'NO_HARM' and len(backend.checks) == 1


def test_a_check_the_server_commits_late_is_adopted(env):
    backend = FakeBackend(env.store, ['NO_HARM'], commit_after_lists=3)
    manifest = env(backend)
    assert manifest['attempts'][0]['adopted_after_start_error'] and manifest['verdict'] == 'NO_HARM'


def test_a_lost_reply_with_a_failing_lookup_stops_nothing(env):
    backend = FakeBackend(env.store, ['NO_HARM'], lose_reply=True, hang=True, list_fails=True)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and not backend.stops
    assert manifest['check_state_unknown'] == 'campaign-1' and 'skipped' in manifest['clock_drift']


def test_a_timed_out_check_is_left_running_not_stopped(env):
    backend = FakeBackend(env.store, ['NO_HARM'], hang=True)
    manifest = env(backend, '--check-timeout', '0')
    assert manifest['stop_reason'] == 'aborted' and not backend.stops
    assert manifest['check_left_running'] == 'heldout-check-1' and 'skipped' in manifest['clock_drift']


def test_a_signal_leaves_the_running_check_alone(env):
    def detach(fake):
        fake.on_poll = None
        raise held.Detached(15)
    backend = FakeBackend(env.store, ['NO_HARM'], hang=True, on_poll=detach)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'left running' in manifest['abort_detail'] and not backend.stops


def test_a_real_sigterm_is_handled_and_leaves_the_check_alone(env, monkeypatch):
    """The handler is really installed (review round 1, H16)."""
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    monkeypatch.setattr(signal, 'signal', REAL_SIGNAL)

    def terminate(fake):
        fake.on_poll = None
        os.kill(os.getpid(), signal.SIGTERM)

    def no_handler(signum, frame):
        raise AssertionError('the runner installed no SIGTERM handler')
    backend = FakeBackend(env.store, ['NO_HARM'], hang=True, on_poll=terminate)
    try:
        REAL_SIGNAL(signal.SIGTERM, no_handler)
        manifest = env(backend)
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN
    finally:
        for sig, handler in saved.items():
            REAL_SIGNAL(sig, handler)
    assert manifest['stop_reason'] == 'aborted' and 'signal 15' in manifest['abort_detail'] and not backend.stops


def test_only_the_operators_ctrl_c_stops_a_running_check(env):
    def interrupt(fake):
        fake.on_poll = None
        raise KeyboardInterrupt
    backend = FakeBackend(env.store, ['NO_HARM'], hang=True, on_poll=interrupt)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and manifest['abort_detail'] == 'interrupted by operator'
    assert backend.stops == ['/api/campaigns/campaign-1/stop'] and manifest['attempts'][0]['check_id'] == 'heldout-check-1'
    assert manifest['attempts'][0]['decision'] == 'INCOMPLETE' and manifest['verdict'] is None


def test_untriggered_trials_are_recorded_by_case_and_arm(env):
    """Section 8: suppressing the confirmation send can only read INCOMPLETE on that case."""
    backend = FakeBackend(env.store, ['INCOMPLETE', 'NO_HARM'], untriggered_l=4)
    manifest = env(backend)
    assert manifest['attempts'][0]['untriggered_by_case'] == {'heldout-2-1': {'B0': 0, 'L': 0},
                                                              'heldout-2-2': {'B0': 1, 'L': 4}}


def test_the_drift_check_runs_after_the_session_and_is_recorded(env):
    manifest = env(FakeBackend(env.store, ['NO_HARM']))
    drift = manifest['clock_drift']
    assert drift['exit_status'] == 0 and drift['since'] == manifest['started_at'] and '--worlds' in drift['command']
    assert manifest['sessions'][0]['clock_drift'] == drift


def test_an_unhealthy_ingestion_reading_is_recorded_and_never_refuses(env, monkeypatch):
    """Review round 2: the check reads only development ingestion rows, which heldout-2's episodes
    never write, so a degraded tail left by earlier work would otherwise refuse Phase 24 for good."""
    monkeypatch.setattr(held, 'ingestion_health', lambda: {'exit_status': 2, 'output': 'DEGRADED'})
    manifest = env(FakeBackend(env.store, ['NO_HARM']))
    assert manifest['stop_reason'] == 'verdict' and manifest['verdict'] == 'NO_HARM'
    assert manifest['sessions'][0]['ingestion_health'] == manifest['ingestion_health'] == {
        'exit_status': 2, 'output': 'DEGRADED'}
    assert manifest['sessions'][0]['readiness']['provider_access'] == 'not_checked'
    assert manifest['readiness']['ready'] is True


def test_a_stale_ingestion_reading_never_blocks_an_approved_resume(env, monkeypatch):
    """Probe P2 (review round 2): after a $0 abort, a degraded reading that nothing in Phase 24 can move
    must not refuse the resume; the reading is recorded in the new session and the run record is kept."""
    backend = FakeBackend(env.store, ['NO_HARM'], config_hash='d' * 64)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and first['attempts_used'] == 0
    backend.config_hash = CONFIG
    monkeypatch.setattr(held, 'ingestion_health', lambda: {'exit_status': 2, 'output': 'DEGRADED'})
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['verdict'] == 'NO_HARM' and resumed['attempts_used'] == 1 and len(backend.campaigns) == 2
    assert [s_['ingestion_health']['exit_status'] for s_ in resumed['sessions']] == [0, 2]


def test_a_readiness_read_that_fails_is_recorded_and_never_refuses(env):
    backend = FakeBackend(env.store, ['NO_HARM'])

    def no_readiness(b, method, path, body=None, timeout=30):
        if path == '/api/readiness':
            raise OSError('readiness down')
        return backend(b, method, path, body, timeout)
    manifest = env(no_readiness)
    assert manifest['verdict'] == 'NO_HARM' and manifest['sessions'][0]['readiness'] == {'error': 'OSError'}


def test_the_run_record_is_claimed_before_the_slow_checks(env, monkeypatch):
    seen = {}

    def ingestion():
        seen['claimed'] = json.loads(env.manifest().read_text())['stop_reason']
        return {'exit_status': 0, 'output': 'HEALTHY'}
    monkeypatch.setattr(held, 'ingestion_health', ingestion)
    env(FakeBackend(env.store, ['NO_HARM']))
    assert seen['claimed'] == 'starting'


def test_a_launch_that_loses_the_claim_refuses(tmp_path):
    out = tmp_path / 'artifacts' / 'phase24-a'
    held.claim(out, out / 'heldout-manifest.json', {'stop_reason': 'starting'})
    with pytest.raises(SystemExit, match='created by another launch'):
        held.claim(out, out / 'heldout-manifest.json', {})
    other = tmp_path / 'artifacts' / 'phase24-b'
    with pytest.raises(SystemExit, match='Another Phase 24 run exists'):
        held.claim(other, other / 'heldout-manifest.json', {})
    assert not (other / 'heldout-manifest.json').exists()


# ---------------------------------------------------------------- continuation after an early stop (review round 1)

def test_an_attempt_that_created_no_check_uses_none_and_an_approved_resume_continues(env):
    backend = FakeBackend(env.store, ['INCOMPLETE'] * 5, config_hash='d' * 64, spend=1.0)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and first['attempts_used'] == 0
    backend.config_hash = CONFIG
    with pytest.raises(SystemExit, match='--after-abort'):
        env(backend, '--resume')
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'attempt_cap' and resumed['attempts_used'] == 3 and len(backend.checks) == 3
    assert len(resumed['attempts']) == 4 and resumed['sessions'][1]['previous_stop'] == 'aborted'
    assert 'abort_detail' not in resumed and 'configuration_hash' in resumed['sessions'][0]['abort_detail']


def test_a_transient_503_at_start_uses_no_attempt(env):
    backend = FakeBackend(env.store, ['NO_HARM'], start_status=503)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'could not be resolved' in first['abort_detail']
    assert first['attempts_used'] == 0 and not backend.checks
    backend.start_status = None
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['verdict'] == 'NO_HARM' and resumed['attempts_used'] == 1


@pytest.mark.parametrize('outcomes,spend,stop', [(['NO_HARM'], 4.0, 'verdict'), (['INCOMPLETE'] * 3, 1.0, 'attempt_cap'),
                                                (['INCOMPLETE'] * 3, 40.0, 'spend_guard')])
def test_a_final_stop_is_never_resumed(env, outcomes, spend, stop):
    backend = FakeBackend(env.store, outcomes + ['NO_HARM'], spend=spend)
    assert env(backend)['stop_reason'] == stop
    with pytest.raises(SystemExit, match='final'):
        env(backend, '--resume', '--after-abort')


def test_a_resume_can_never_change_the_declared_design(env):
    backend = FakeBackend(env.store, ['NO_HARM'], config_hash='d' * 64)
    env(backend)
    with pytest.raises(SystemExit, match='declared parameters'):
        env(backend, '--resume', '--after-abort', '--headroom', '60')


def test_a_check_left_running_is_read_back_on_resume_and_its_verdict_ends_the_run(env):
    backend = FakeBackend(env.store, ['NO_HARM'], hang=True)
    first = env(backend, '--check-timeout', '0')
    assert first['check_left_running'] == 'heldout-check-1'
    backend.active = None
    with pytest.raises(SystemExit, match='still RUNNING'):
        env(backend, '--resume', '--after-abort')
    backend.finish('heldout-check-1', 'NO_HARM')
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'verdict' and resumed['verdict'] == 'NO_HARM' and len(backend.campaigns) == 1
    # The first session's note moves into the new session's record and no longer skips the drift check.
    assert 'check_left_running' not in resumed and resumed['clock_drift']['exit_status'] == 0
    assert resumed['sessions'][1]['previous_session_notes'] == {'check_left_running': 'heldout-check-1'}


def test_the_backend_is_the_authority_on_attempts_used(env):
    backend = FakeBackend(env.store, ['NO_HARM'], config_hash='d' * 64)
    env(backend)
    backend.put('heldout_checks', 'heldout-check-untracked', {'check_id': 'heldout-check-untracked', 'policy_hash': NEW,
                                                              'status': 'INCOMPLETE', 'decision': 'INCOMPLETE'})
    backend.config_hash = CONFIG
    with pytest.raises(SystemExit, match='held-out check'):
        env(backend, '--resume', '--after-abort')


def test_spend_carries_across_a_resume(env):
    backend = FakeBackend(env.store, ['INCOMPLETE'] * 4, spend=30.0)
    original = backend.__call__
    state = {'creates': 0}

    def mismatch_on_second_create(b, method, path, body=None, timeout=30):
        result = original(b, method, path, body, timeout)
        if path == '/api/campaigns' and method == 'POST':
            state['creates'] += 1
            if state['creates'] == 2:
                return {**result, 'configuration_hash': 'd' * 64}
        return result
    first = env(mismatch_on_second_create)
    assert first['stop_reason'] == 'aborted' and len(backend.checks) == 1
    resumed = env(mismatch_on_second_create, '--resume', '--after-abort')
    # $30 carried over: attempt 3 is admitted ($30 + $52.17 <= $87), then $60 + $52.17 is not.
    assert resumed['stop_reason'] == 'spend_guard' and len(backend.checks) == 2
    assert resumed['total_charged_upper_bound'] == pytest.approx(60.0)


def test_resume_is_refused_after_an_identity_mismatch(env):
    backend = FakeBackend(env.store, ['NO_HARM'], identity_changes={'planned_pairs': 18})
    env(backend)
    with pytest.raises(SystemExit, match='not the declared one'):
        env(backend, '--resume', '--after-abort')


def test_a_stop_during_campaign_create_is_labelled_and_uses_no_attempt(env):
    backend = FakeBackend(env.store, ['NO_HARM'])
    state = {'fired': False}

    def ctrl_c_on_first_create(b, method, path, body=None, timeout=30):
        if path == '/api/campaigns' and method == 'POST' and not state['fired']:
            state['fired'] = True
            raise KeyboardInterrupt
        return backend(b, method, path, body, timeout)
    first = env(ctrl_c_on_first_create)
    assert first['attempts'][0]['error'] == held.INTERRUPTED_BEFORE_CREATE and first['attempts_used'] == 0
    resumed = env(ctrl_c_on_first_create, '--resume', '--after-abort')
    assert resumed['verdict'] == 'NO_HARM' and len(resumed['attempts']) == 2 and resumed['attempts_used'] == 1


def test_an_aborts_reason_is_on_disk_before_the_post_abort_wait(env):
    """A second Ctrl-C while the abort path waits must not leave 'running' with no reason."""
    def interrupt(fake):
        fake.on_poll = None
        raise KeyboardInterrupt
    backend = FakeBackend(env.store, ['NO_HARM'], hang=True, on_poll=interrupt)

    def second_interrupt_in_the_wait(b, method, path, body=None, timeout=30):
        if path == '/api/config/status' and backend.stops:
            raise KeyboardInterrupt
        return backend(b, method, path, body, timeout)
    with pytest.raises(KeyboardInterrupt):
        env(second_interrupt_in_the_wait)
    on_disk = json.loads(env.manifest().read_text())
    assert on_disk['stop_reason'] == 'aborted' and on_disk['abort_detail'] == 'interrupted by operator'


def ctrl_c_after_the_server_created_the_check(backend):
    def call(b, method, path, body=None, timeout=30):
        result = backend(b, method, path, body, timeout)
        if path.endswith('/heldout-check') and method == 'POST':
            raise KeyboardInterrupt          # the reply is lost to the operator's Ctrl-C
        return result
    return call


def test_a_check_adopted_in_the_abort_path_is_compared_and_a_wrong_one_is_never_the_verdict(env):
    """Probe P1 (review round 2): a Ctrl-C while POST /heldout-check is in flight, on a backend whose
    check is not the declared one. The adopted check was copied into the row with no comparison, its
    NO_HARM became the verdict, and the resume ended with it."""
    backend = FakeBackend(env.store, ['NO_HARM'], identity_changes={'planned_pairs': 18})
    first = env(ctrl_c_after_the_server_created_the_check(backend))
    row_ = first['attempts'][0]
    assert row_['adopted_after_abort'] and row_['identity_mismatch'] and row_['decision'] == 'NO_HARM'
    assert first['stop_reason'] == 'aborted' and first['verdict'] is None
    with pytest.raises(SystemExit, match='not the declared one'):
        env(backend, '--resume', '--after-abort')


def test_a_matching_check_adopted_in_the_abort_path_is_the_verdict_and_a_resume_starts_nothing(env):
    backend = FakeBackend(env.store, ['NO_HARM'])
    first = env(ctrl_c_after_the_server_created_the_check(backend))
    row_ = first['attempts'][0]
    assert row_['adopted_after_abort'] and row_['identity_checked'] and not row_.get('identity_mismatch')
    assert first['stop_reason'] == 'aborted' and first['verdict'] == 'NO_HARM'
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'verdict' and resumed['verdict'] == 'NO_HARM' and len(backend.campaigns) == 1


def test_resolve_compares_an_ended_check_that_was_never_compared(env):
    """Review round 2: resolve() used to return early for any terminal row, so a check copied in without
    a comparison was never compared on resume either."""
    backend = FakeBackend(env.store, ['NO_HARM', 'NO_HARM'], config_hash='d' * 64)
    env(backend)                                         # a $0 abort: row 1 has a campaign and no check
    backend.config_hash = CONFIG
    record = {'check_id': 'heldout-check-9', 'campaign_id': 'campaign-1', 'policy_hash': NEW,
              'predicate': held.PREDICATE, 'actor_context_protocol': base.ACTOR_CONTEXT, 'partition': 'heldout-2',
              'certified_study_id': 's3', 'manifest_hash': PARTITION_HASH, 'planned_pairs': 18,
              'status': 'COMPLETED', 'decision': 'NO_HARM', 'reason': 'r', 'assessment': {'by_case': {}}}
    backend.checks['heldout-check-9'] = record; backend.put('heldout_checks', 'heldout-check-9', record)
    manifest = json.loads(env.manifest().read_text())
    manifest['attempts'][0].update(check_id='heldout-check-9', status='COMPLETED', decision='NO_HARM')
    manifest['attempts'][0].pop('error', None)
    env.manifest().write_text(json.dumps(manifest))
    with pytest.raises(SystemExit, match='not the declared check'):
        env(backend, '--resume', '--after-abort')
    assert json.loads(env.manifest().read_text())['attempts'][0]['identity_mismatch'] is True
    # The same row on a check that IS the declared one is compared, marked, and ends the run.
    record['planned_pairs'] = 78; backend.put('heldout_checks', 'heldout-check-9', record)
    manifest['attempts'][0].pop('identity_mismatch', None)
    env.manifest().write_text(json.dumps(manifest))
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'verdict' and resumed['verdict'] == 'NO_HARM'
    assert resumed['attempts'][0]['identity_checked'] is True and len(backend.campaigns) == 1


def test_a_check_adopted_on_resume_must_be_the_declared_one(env):
    backend = FakeBackend(env.store, ['NO_HARM'], lose_reply=True, list_fails=True, identity_changes={'planned_pairs': 18})
    first = env(backend)
    assert first['check_state_unknown'] == 'campaign-1' and not first['attempts'][0].get('check_id')
    backend.list_fails = False
    with pytest.raises(SystemExit, match='not the declared check'):
        env(backend, '--resume', '--after-abort')
    row_ = json.loads(env.manifest().read_text())['attempts'][0]
    assert row_['identity_mismatch'] and row_['adopted_on_resume'] and row_['check_id'] == 'heldout-check-1'
