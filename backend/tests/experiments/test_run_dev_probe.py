"""Offline checks of the Phase 20 development-probe runner (scripts/experiments/run_dev_probe.py).

No provider, no network, no live service, no .env: the pure pieces (cases, pins, guards,
statistics, read-out) are exercised directly, and the case loop runs the REAL PairedEvaluator,
EpisodeRunner, CampaignLedger and simulator in-process with the labelled fixture Actor the lab
tests use. Nothing here is model evidence.
"""
import asyncio
import copy
import functools
import hashlib
import importlib.util
import inspect
import itertools
import json
import math
import os
import pathlib
import signal
import socket
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend/tests/lab'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/experiments/{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


probe = load('run_dev_probe')
drift = load('check_clock_drift')

from app.adapters.business_tools import WorldClient  # noqa: E402
from app.config import Settings  # noqa: E402
from app.contracts.models import (CampaignBudget, CampaignRequest, FaultSpec, PolicyVersion,  # noqa: E402
                                  RecoveryPolicy, content_hash)
from app.lab.budgets import CampaignLedger  # noqa: E402
from app.lab.coordinator import LabCoordinator  # noqa: E402
from app.lab.policies import PolicyRepository  # noqa: E402
from app.lab.runner import EpisodeRunner  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402
from app.providers.runtime import RuntimeGeneration  # noqa: E402
from app.simulator.faults import validate_schedule  # noqa: E402
from app.simulator.main import create_app  # noqa: E402
from test_baseline_study import BaselineFixtureProvider, settings as lab_settings  # noqa: E402
from test_completion_study import CompletionFixtureProvider  # noqa: E402

PlanningError = probe.PlanningError
CANDIDATE_VERSION = 'policy-72dce59539754a1b8acb5b61c26a0646'
# The certified Phase 17 policy's content, copied from the lab store; its hash is asserted below.
U, N = 'upgrade_outcome_uncertain', 'notification_outcome_uncertain'
CANDIDATE_CONTENT = {'scope': 'orders.upgrade_then_confirm/v1', 'parent_version': 'policy-v0', 'rules': [
    {'hook': 'after_upgrade_response', 'when': U, 'steps': [
        {'op': 'read_current_operation', 'only_if': U}, {'op': 'wait_ticks', 'ticks': 1, 'only_if': U},
        {'op': 'read_current_operation', 'only_if': U},
        {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED', 'only_if': U}]},
    {'hook': 'before_confirmation', 'when': 'upgrade_receipt_missing', 'steps': [
        {'op': 'read_current_operation', 'only_if': U},
        {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED', 'only_if': 'upgrade_receipt_missing'}]},
    {'hook': 'after_notification_response', 'when': N, 'steps': [
        {'op': 'read_notification_operation', 'only_if': N}, {'op': 'wait_ticks', 'ticks': 1, 'only_if': N},
        {'op': 'read_notification_operation', 'only_if': N},
        {'op': 'retry_original_request', 'service': 'notifications', 'only_if': N}]},
    {'hook': 'before_final_report', 'when': N, 'steps': [
        {'op': 'read_notification_operation', 'only_if': N}, {'op': 'defer_unresolved', 'only_if': N}]}]}


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def candidate_version():
    content = RecoveryPolicy.model_validate(CANDIDATE_CONTENT)
    return PolicyVersion(version=CANDIDATE_VERSION, parent_version='policy-v0', content=content,
                         policy_hash=content_hash(content), author='mechanic',
                         raw_proposal_ref='proposal-offline-fixture', development_episode_ids=[], decision='PROPOSED')


def source_store(path, *, tamper=False):
    store = LabStore(path)
    PolicyRepository(store)                       # writes the empty baseline policy-v0
    payload = candidate_version().model_dump(mode='json')
    if tamper:
        payload['content']['rules'][0]['steps'][1]['ticks'] = 2   # same declared hash, different content
    store.put_record('policies', CANDIDATE_VERSION, payload)
    store.close()
    return path


@functools.lru_cache(maxsize=1)
def tree_is_phase19_frozen():
    if not (probe.DEFAULT_FREEZE.is_file() and probe.DEFAULT_SETTINGS.is_file()):
        return False
    return probe.current_gate_freeze() == probe.load_expected_freeze(probe.DEFAULT_FREEZE)


frozen_only = pytest.mark.skipif('not tree_is_phase19_frozen()',
                                 reason='needs the Phase 19 frozen tree and the Phase 17 settings file')


def by_id():
    return {case['case_id']: case for case in probe.build_cases()}


# ----------------------------------------------------------------- declared cases

def test_cases_are_the_declared_23_with_69_pairs_and_simulator_valid_schedules():
    cases = probe.build_cases()
    assert len(cases) == 23 and len(cases) * probe.PAIRS_PER_CASE == 69
    assert [c['case_id'] for c in cases] == list(probe.EXECUTION_ORDER)
    assert [c['position'] for c in cases] == list(range(1, 24))
    per_setting = Counter(c['setting'] for c in cases)
    assert {s: n * 3 for s, n in per_setting.items()} == {
        'A:c2': 9, 'A:c3': 9, 'A:c4': 9, 'B:d2': 6, 'B:d3': 6, 'B:d4': 6, 'C:f1': 6, 'C:f3': 6,
        'D:d16': 3, 'D:d20': 3, 'D:d5': 3, 'H': 3}
    assert probe.SOURCE_SETTINGS == ('D:d16', 'D:d20', 'D:d5')
    for case in cases:
        spec = FaultSpec.model_validate(case['fault_spec'])
        validate_schedule(spec, [{}] * probe.FIXTURE_VERSIONS[case['fixture_id']])   # the simulator's own check
        assert all(p['occurrence'] == 1 for p in case['fault_spec']['primitives'])
        assert case['scenario_hash'] == content_hash(case['fault_spec'])
        assert case['evaluator_manifest_hash'] == content_hash([probe.evaluator_case(case)])
        assert case['target_outcome'] == ('SAFE_UNRESOLVED' if case['block'] == 'D' else 'COMPLETED')
    cases_by_id = by_id()
    assert cases_by_id['A-c3-r2']['fault_spec']['primitives'] == [{
        'kind': 'F4', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
        'parameters': {'failure_count': 3}}]
    assert cases_by_id['B-d4-r1']['fault_spec']['primitives'][0]['parameters'] == {
        'completion_delay_ticks': 4, 'terminal_status': 'SUCCEEDED', 'failure_code': None}
    assert cases_by_id['C-f1-r2']['fault_spec']['primitives'][0]['parameters'] == {'response_delay_ms': 1500}
    assert cases_by_id['C-f3-r1']['fault_spec']['primitives'][0]['parameters'] == {'versions_back': 1}
    assert (cases_by_id['C-f3-r1']['fixture_id'], cases_by_id['C-f3-r1']['expected_version']) == ('history-v1', 4)
    # Protocol section 4: D-d5 replaces D-d20-f1 in the same SETTINGS row (the same seed slot) with its own kind.
    assert cases_by_id['D-d5']['fault_spec']['primitives'] == [{
        'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
        'parameters': {'completion_delay_ticks': 5, 'terminal_status': 'SUCCEEDED', 'failure_code': None}}]
    assert cases_by_id['D-d5']['kind'] == 'F2 SUCCEEDED boundary delay (d5)' != cases_by_id['D-d16']['kind']
    assert (cases_by_id['D-d5']['seed'], cases_by_id['healthy']['seed']) == (probe.SEED_BASE + 22, probe.SEED_BASE + 23)
    assert cases_by_id['healthy']['fault_spec']['primitives'] == []
    # Seeds follow SETTINGS rows, not execution order: every source setting runs in rounds 1-2 and
    # the last case is the healthy one.
    assert (cases_by_id['D-d16']['position'], cases_by_id['D-d5']['position'], cases_by_id['D-d20']['position']) == (9, 10, 19)
    assert cases[-1]['case_id'] == 'healthy'
    # Seeds are listed metadata: replicas share one schedule identity, never a scenario hash.
    assert len({c['seed'] for c in cases}) == 23 and len({c['scenario_hash'] for c in cases}) == 23
    assert len({c['schedule_identity'] for c in cases}) == 12
    assert cases_by_id['A-c2-r1']['schedule_identity'] == cases_by_id['A-c2-r3']['schedule_identity']


def test_the_declared_plan_has_no_unreachable_schedule_and_the_old_one_is_still_refused():
    problems, notes = probe.validate_cases(probe.build_cases())
    assert problems == []
    assert 'observer horizon' in notes['D-d20'][0] and 'at least 16' in notes['D-d20'][0]
    assert 'never for B0' in notes['D-d20'][0] and 'unreachable for B0' in notes['D-d16'][0]
    assert 'D-d5' not in notes          # due at tick 6 at the earliest: within B0's 14 ticks
    # The replaced schedule (F2 d20 plus F1 update_order at the same occurrence) is still refused.
    old = dict(by_id()['D-d20'], case_id='synthetic-d20-f1', setting='D:d20+f1')
    old['fault_spec'] = FaultSpec.model_validate({'seed': 1, 'primitives': [
        probe._f2(20), probe._f1_update()]}).model_dump(mode='json')
    problems, _ = probe.validate_cases([old])
    assert [(p['case_id'], p['check'], p['fault_id']) for p in problems] == [
        ('synthetic-d20-f1', 'trigger_reachability', 'fault-2')]
    assert "reason='target_not_committed'" in problems[0]['error']


def test_an_invalid_schedule_is_reported_never_repaired():
    stale_on_standard = dict(by_id()['C-f3-r1'], case_id='bad', fixture_id='standard-v1', expected_version=1)
    problems, _ = probe.validate_cases([stale_on_standard])
    assert problems == [{'case_id': 'bad', 'setting': 'C:f3', 'check': 'validate_schedule',
                         'error': 'WorldError STALE_HISTORY_UNAVAILABLE (HTTP 422)'}]


def test_declared_budget_constants():
    assert probe.EVALUATOR_OWN_CASE_RESERVATION == 48          # PairedEvaluator: len(cases) * 3 * 16
    assert (probe.CASE_RESERVATION_CALLS, probe.CASE_WORST_CALLS, probe.PAIR_WORST_CALLS) == (96, 144, 48)
    assert probe.SPEND_CAP == 28.0
    # At 8 turns per episode the last case still starts under its full worst case.
    assert 22 * 48 * 0.0209 + probe.CASE_WORST_CALLS * 0.0209 <= probe.SPEND_CAP


# ----------------------------------------------------------------- pins

def test_candidate_fixture_is_the_certified_content():
    assert content_hash(RecoveryPolicy.model_validate(CANDIDATE_CONTENT)) == probe.CANDIDATE_POLICY_HASH
    assert content_hash(RecoveryPolicy(parent_version='policy-v0', rules=[])) == probe.BASELINE_POLICY_HASH


def test_policies_are_read_by_hash_and_their_content_verified(tmp_path):
    found = probe.load_policies(source_store(tmp_path / 'lab.sqlite3'))
    assert found['B0'].policy_hash == probe.BASELINE_POLICY_HASH and found['B0'].version == 'policy-v0'
    assert found['L'].policy_hash == probe.CANDIDATE_POLICY_HASH and found['L'].version == CANDIDATE_VERSION
    with pytest.raises(PlanningError, match='does not hash'):
        probe.load_policies(source_store(tmp_path / 'tampered.sqlite3', tamper=True))
    with pytest.raises(PlanningError, match='not found'):
        probe.load_policies(tmp_path / 'missing.sqlite3')


@pytest.mark.parametrize('arm', ['B0', 'L'])
def test_policy_loading_refuses_ambiguous_hashes_instead_of_picking_a_version(tmp_path, arm):
    path = source_store(tmp_path / 'lab.sqlite3')
    store = LabStore(path)
    original_id = 'policy-v0' if arm == 'B0' else CANDIDATE_VERSION
    duplicate = copy.deepcopy(store.get_record('policies', original_id))
    duplicate['version'] = 'policy-offline-duplicate'
    store.put_record('policies', duplicate['version'], duplicate)
    store.close()
    with pytest.raises(PlanningError, match=f'exactly one stored policy with the declared {arm} hash, found 2'):
        probe.load_policies(path)


@pytest.mark.skipif(not probe.DEFAULT_SOURCE_STORE.is_file(), reason='needs the optional local historical lab store')
def test_the_real_store_retains_the_original_policy_versions_unchanged():
    # The store is append-only evidence, not the Phase 20 snapshot: later studies may legitimately
    # propose the same content under a new version. Verify the original records by identity here;
    # the hermetic test above keeps the frozen runner's ambiguous-hash refusal covered.
    connection = sqlite3.connect(f'file:{probe.DEFAULT_SOURCE_STORE}?mode=ro', uri=True)
    try:
        for version_id, policy_hash, decision in (
            ('policy-v0', probe.BASELINE_POLICY_HASH, 'BASELINE'),
            (CANDIDATE_VERSION, probe.CANDIDATE_POLICY_HASH, 'PROPOSED'),
        ):
            row = connection.execute("SELECT payload FROM records WHERE kind='policies' AND id=?",
                                     (version_id,)).fetchone()
            assert row is not None, f'The original historical policy {version_id} is missing'
            version = PolicyVersion.model_validate_json(row[0])
            assert (version.version, version.policy_hash, version.decision) == (version_id, policy_hash, decision)
            assert content_hash(version.content) == policy_hash
    finally:
        connection.close()


@pytest.mark.skipif(not probe.DEFAULT_SETTINGS.is_file(), reason='needs the Phase 17 settings file')
def test_settings_and_configuration_pins_refuse_on_mismatch(tmp_path):
    probe.check_settings_file(probe.DEFAULT_SETTINGS)
    data = json.loads(probe.DEFAULT_SETTINGS.read_text())
    data['FAULTLAB_DOLLAR_CAP'] = '300'
    changed = tmp_path / 'settings.json'
    changed.write_text(json.dumps(data))
    with pytest.raises(PlanningError, match='not the declared'):
        probe.check_settings_file(changed)
    _, _, other = probe.planned_configuration(probe.settings_from_file(changed))
    assert other != probe.DECLARED_CONFIGURATION_HASH
    with pytest.raises(PlanningError, match='configuration_hash'):
        probe.check_configuration_hash(other)


@frozen_only
def test_the_phase17_settings_reproduce_the_declared_configuration_hash_without_env():
    _, frozen, configuration_hash = probe.planned_configuration(probe.settings_from_file(probe.DEFAULT_SETTINGS))
    assert configuration_hash == probe.DECLARED_CONFIGURATION_HASH
    assert frozen['campaign_budget']['dollars'] == 400.0 and frozen['pricing']['actor']['per_call_dollar_upper_bound'] == 0.0209


@pytest.mark.skipif(not probe.DEFAULT_FREEZE.is_file(), reason='needs the Phase 19 freeze file')
def test_gate_freeze_pins_refuse_on_mismatch(tmp_path):
    expected = probe.load_expected_freeze(probe.DEFAULT_FREEZE)
    altered = copy.deepcopy(expected)
    altered['files']['backend/app/lab/runner.py'] = '0' * 64
    with pytest.raises(PlanningError, match='runner.py'):
        probe.check_freeze(altered, expected)
    copied = tmp_path / 'gate-freeze-after.json'
    copied.write_text(json.dumps(altered))
    with pytest.raises(PlanningError, match='not the declared'):
        probe.load_expected_freeze(copied)


def protocol_text(harness=None, drift_sha=None, *, config=True, freeze=True, extra=''):
    harness = harness or probe.harness_sha256()
    drift_sha = drift_sha or probe.drift_checker_sha256()
    lines = ['# protocol', '```', f'runnable-harness-sha256: {harness}', f'drift-checker-sha256: {drift_sha}', '```']
    if config:
        lines.append(f'configuration {probe.DECLARED_CONFIGURATION_HASH}')
    if freeze:
        lines.append(f'freeze {probe.DECLARED_FREEZE_FILE_SHA256}')
    return '\n'.join(lines) + '\n' + extra


def write_protocol(path, **kwargs):
    path.write_text(protocol_text(**kwargs))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_protocol_pin_refuses_on_mismatch(tmp_path):
    harness = probe.harness_sha256()
    with pytest.raises(PlanningError, match='does not exist'):
        probe.check_protocol(tmp_path / 'missing.md', '0' * 64, harness)
    protocol, sha = write_protocol(tmp_path / 'PHASE20_EXPERIMENT.md')
    assert probe.check_protocol(protocol, sha, harness) == sha
    for typed in ('0' * 64, None):
        with pytest.raises(PlanningError, match='differs'):
            probe.check_protocol(protocol, typed, harness)
    with pytest.raises(PlanningError, match='harness'):
        probe.check_protocol(protocol, sha, 'f' * 64)        # the protocol declares another harness
    stale, stale_sha = write_protocol(tmp_path / 'stale.md', config=False)
    with pytest.raises(PlanningError, match='configuration hash'):
        probe.check_protocol(stale, stale_sha, harness)
    no_freeze, no_freeze_sha = write_protocol(tmp_path / 'no-freeze.md', freeze=False)
    with pytest.raises(PlanningError, match='gate-freeze file sha256'):
        probe.check_protocol(no_freeze, no_freeze_sha, harness)
    other_drift, other_drift_sha = write_protocol(tmp_path / 'other-drift.md', drift_sha='e' * 64)
    with pytest.raises(PlanningError, match='drift checker'):
        probe.check_protocol(other_drift, other_drift_sha, harness)


def test_a_sha_quoted_elsewhere_in_the_protocol_does_not_pin_the_harness(tmp_path):
    # The pre-edit runner's sha quoted in a table row (substring match) must not satisfy the pin.
    harness = probe.harness_sha256()
    quoted = tmp_path / 'quoted.md'
    quoted.write_text(protocol_text(harness='0' * 64, extra=f'| runner before the edit | `{harness}` |\n'
                                                              f'runnable-harness-sha256: {harness} (not alone)\n'))
    sha = hashlib.sha256(quoted.read_bytes()).hexdigest()
    assert probe.protocol_status(quoted, harness, sha)['declares_harness_sha256'] is False
    with pytest.raises(PlanningError, match='harness'):
        probe.check_protocol(quoted, sha, harness)


def test_output_must_be_new_and_the_only_phase20_run(tmp_path):
    artifacts = tmp_path / 'artifacts'
    folder = artifacts / 'phase20-2026-09-24'
    folder.mkdir(parents=True)
    assert probe.check_output(folder / 'run', artifacts) == (folder / 'run').resolve()
    old = folder / 'old'
    old.mkdir()
    with pytest.raises(PlanningError, match='resumed'):
        probe.check_output(old, artifacts)
    with pytest.raises(PlanningError, match='inside artifacts'):
        probe.check_output(tmp_path / 'elsewhere' / 'run', artifacts)
    with pytest.raises(PlanningError, match='phase20-'):
        probe.check_output(artifacts / 'phase21-2026-09-24' / 'run', artifacts)
    for nested in (artifacts / 'retry' / 'phase20-2026-09-24' / 'run-1', folder / 'deeper' / 'run-1'):
        with pytest.raises(PlanningError, match='phase20-<date>/<name>'):
            probe.check_output(nested, artifacts)            # a nested run would hide from the guard
    (old / probe.MANIFEST_NAME).write_text('{}')            # not final: may be running
    with pytest.raises(PlanningError, match='Another Phase 20 run'):
        probe.check_output(artifacts / 'phase20-2026-09-25' / 'run', artifacts)


def dead_pid():
    """The pid of a process that has exited (a crashed run's recorded pid)."""
    import subprocess
    child = subprocess.Popen([sys.executable, '-c', 'pass'])
    child.wait()
    return child.pid


def test_the_one_run_guard_sees_every_manifest_and_allows_only_after_undelivered_runs(tmp_path):
    artifacts = tmp_path / 'artifacts'
    hidden = artifacts / 'somewhere' / 'else' / 'phase20-2026-09-24' / 'run-1'
    hidden.mkdir(parents=True)
    zero = {'stop_reason': 'aborted', 'ended_at': '2026-09-24T10:00:00+00:00', 'cases': [], 'charged_upper_bound': 0.0}
    (hidden / probe.MANIFEST_NAME).write_text(json.dumps(zero))
    # A $0 pre-episode abort observed nothing: a new directory may follow, and it is recorded.
    assert probe.earlier_phase20_runs(artifacts) == [f'artifacts/somewhere/else/phase20-2026-09-24/run-1/{probe.MANIFEST_NAME}']
    assert probe.check_output(artifacts / 'phase20-2026-09-25' / 'run-2', artifacts)
    # A run whose only case the ledger refused before any episode started nothing either.
    not_started = {**zero, 'stop_reason': 'spend_cap', 'cases': [{'case_id': 'A-c2-r1', 'status': 'NOT_STARTED'}]}
    # A run that crashed before any case (SIGKILL, power loss) never finalized; once its recorded
    # process is gone it observed nothing too.
    crashed = {'stop_reason': 'running', 'ended_at': None, 'cases': [], 'charged_upper_bound': 0.0, 'pid': dead_pid()}
    for allowed in (not_started, crashed):
        (hidden / probe.MANIFEST_NAME).write_text(json.dumps(allowed))
        assert probe.check_output(artifacts / 'phase20-2026-09-25' / 'run-2', artifacts)
    for delivered, why in (({**zero, 'cases': [{'case_id': 'A-c2-r1', 'status': 'RETURNED'}]}, 'started a case'),
                           ({**zero, 'cases': [{'case_id': 'A-c2-r1', 'status': 'RUNNING'}]}, 'started a case'),
                           ({**not_started, 'charged_upper_bound': 0.33}, 'started a case or charged'),
                           ({**zero, 'stop_reason': 'running'}, 'may still be running'),
                           ({**zero, 'ended_at': None}, 'may still be running'),
                           ({**crashed, 'pid': os.getpid()}, 'may still be running'),      # its process is alive
                           ({**crashed, 'pid': None}, 'may still be running'),              # not known to be gone
                           ({**crashed, 'cases': [{'case_id': 'A-c2-r1', 'status': 'RUNNING'}]}, 'started a case')):
        (hidden / probe.MANIFEST_NAME).write_text(json.dumps(delivered))
        with pytest.raises(PlanningError, match='Another Phase 20 run') as refused:
            probe.check_output(artifacts / 'phase20-2026-09-25' / 'run-2', artifacts)
        assert why in str(refused.value)
    (hidden / probe.MANIFEST_NAME).write_text('{not json')
    with pytest.raises(PlanningError, match='cannot be read'):
        probe.check_output(artifacts / 'phase20-2026-09-25' / 'run-2', artifacts)


def test_a_phase21_live_run_that_may_be_running_blocks_a_live_run(tmp_path):
    artifacts = tmp_path / 'artifacts'
    run = artifacts / 'phase21-2026-09-24' / 'live-1'
    run.mkdir(parents=True)
    assert probe.phase21_active_runs(artifacts) == []
    (run / 'lapse-probe-manifest.json').write_text(json.dumps({'status': 'RUNNING', 'ended_at': None}))
    assert probe.phase21_active_runs(artifacts) == [str((run / 'lapse-probe-manifest.json').resolve())]
    (run / 'lapse-probe-manifest.json').write_text(json.dumps({'status': 'COMPLETED', 'ended_at': 'x'}))
    assert probe.phase21_active_runs(artifacts) == []
    claims = artifacts / probe.PHASE21_CLAIM_DIR
    claims.mkdir()
    (claims / 'claim-01.json').write_text(json.dumps({'out': 'artifacts/phase21-2026-09-24/live-1'}))
    assert probe.phase21_active_runs(artifacts) == []       # the claim's run has a final manifest
    (claims / 'claim-02.json').write_text(json.dumps({'out': 'artifacts/phase21-2026-09-24/live-2'}))
    assert probe.phase21_active_runs(artifacts) == [str((claims / 'claim-02.json').resolve())]


def test_a_crashed_phase21_record_can_be_set_aside_only_when_its_process_is_gone(tmp_path):
    artifacts = tmp_path / 'artifacts'
    claims = artifacts / probe.PHASE21_CLAIM_DIR
    claims.mkdir(parents=True)
    claim = claims / 'claim-01.json'
    # A launch that crashed between its claim and its first manifest save: fail closed by default.
    claim.write_text(json.dumps({'claim': 'claim-01.json', 'pid': os.getpid(), 'out': 'artifacts/phase21-x/live-1'}))
    blocking, ignored = probe.phase21_runs(artifacts, [str(claim)])
    assert ignored == [] and 'refused' in blocking[0] and f'pid {os.getpid()}' in blocking[0]   # still running
    claim.write_text(json.dumps({'claim': 'claim-01.json', 'pid': dead_pid(), 'out': 'artifacts/phase21-x/live-1'}))
    assert probe.phase21_active_runs(artifacts) == [str(claim.resolve())]                     # no override given
    blocking, ignored = probe.phase21_runs(artifacts, [str(claim)])
    assert blocking == [] and [entry['record'] for entry in ignored] == [str(claim.resolve())]
    # A manifest left RUNNING by a SIGKILL: its pid comes from the launch claim it names.
    run = artifacts / 'phase21-x' / 'live-1'
    run.mkdir(parents=True)
    manifest = run / 'lapse-probe-manifest.json'
    manifest.write_text(json.dumps({'status': 'RUNNING', 'ended_at': None,
                                    'claim': f'artifacts/{probe.PHASE21_CLAIM_DIR}/claim-01.json'}))
    relative = 'artifacts/phase21-x/live-1/lapse-probe-manifest.json'             # relative to the repo root
    blocking, ignored = probe.phase21_runs(artifacts, [relative])
    assert [b for b in blocking if 'claim-01' in b] and not [b for b in blocking if 'lapse-probe' in b]
    blocking, ignored = probe.phase21_runs(artifacts, [relative, str(claim)])
    assert blocking == [] and len(ignored) == 2
    # A record that names no process is set aside only after it has been quiet for the declared time.
    orphan = claims / 'claim-02.json'
    orphan.write_text('{broken')
    blocking, _ = probe.phase21_runs(artifacts, [relative, str(claim), str(orphan)])
    assert len(blocking) == 1 and 'names no launching process' in blocking[0]
    old = time.time() - (probe.PHASE21_IGNORE_QUIET_MINUTES + 1) * 60
    os.utime(orphan, (old, old))
    assert probe.phase21_runs(artifacts, [relative, str(claim), str(orphan)])[0] == []


def test_the_review_record_must_approve_this_protocol_harness_and_drift_checker(tmp_path):
    shas = {'protocol_sha256': 'a' * 64, 'harness_sha256': 'b' * 64, 'drift_checker_sha256': 'c' * 64,
            'approved_by': 'the project owner'}
    record = tmp_path / 'review.json'
    status = probe.review_status(record, 'a' * 64, 'b' * 64, 'c' * 64)
    assert 'does not exist' in probe.review_problem(status)
    record.write_text('not json')
    assert 'not readable' in probe.review_problem(probe.review_status(record, 'a' * 64, 'b' * 64, 'c' * 64))
    record.write_text(json.dumps({**shas, 'status': 'approved'}))
    assert probe.review_problem(probe.review_status(record, 'a' * 64, 'b' * 64, 'c' * 64)) is None
    for approver in ('', '   ', None, 7):
        record.write_text(json.dumps({**shas, 'status': 'approved', 'approved_by': approver}))
        assert 'approved_by' in probe.review_problem(probe.review_status(record, 'a' * 64, 'b' * 64, 'c' * 64))
    # A sha copied with its file name (a whole shasum line) is not the bare hex value.
    record.write_text(json.dumps({**shas, 'status': 'approved', 'harness_sha256': 'b' * 64 + '  run_dev_probe.py'}))
    assert 'bare hex' in probe.review_problem(probe.review_status(record, 'a' * 64, 'b' * 64, 'c' * 64))
    record.write_text(json.dumps({**shas, 'status': 'approved'}))
    for protocol, harness, drift_sha, expected in (('d' * 64, 'b' * 64, 'c' * 64, 'protocol'),
                                                   ('a' * 64, 'd' * 64, 'c' * 64, 'harness'),
                                                   ('a' * 64, 'b' * 64, 'd' * 64, 'drift checker')):
        assert expected in probe.review_problem(probe.review_status(record, protocol, harness, drift_sha))
    record.write_text(json.dumps({**shas, 'status': 'pending'}))
    assert 'approved' in probe.review_problem(probe.review_status(record, 'a' * 64, 'b' * 64, 'c' * 64))


def test_planning_refuses_when_the_files_on_disk_are_not_the_loaded_code(monkeypatch):
    assert probe.loaded_code_problem() is None
    assert probe.LOADED_HARNESS_SHA256 == probe.harness_sha256()
    assert probe.LOADED_DRIFT_CHECKER_SHA256 == probe.drift_checker_sha256()
    monkeypatch.setattr(probe, 'harness_sha256', lambda: 'f' * 64)
    assert 'not the code this process loaded' in probe.loaded_code_problem()
    with pytest.raises(PlanningError, match='not the code this process loaded'):
        probe.prepare(SimpleNamespace(spend_cap=28.0))
    monkeypatch.undo()
    monkeypatch.setattr(probe, 'drift_checker_sha256', lambda: 'e' * 64)
    assert 'not the code this process loaded' in probe.loaded_code_problem()


def test_spend_cap_cannot_be_raised():
    assert probe.validate_spend_cap(28.0) == 28.0
    for cap in (28.01, 0.0, float('nan')):
        with pytest.raises(PlanningError):
            probe.validate_spend_cap(cap)


def plan_arguments(tmp_path, store):
    return SimpleNamespace(output=tmp_path / 'artifacts/phase20-2026-09-24/run', settings=probe.DEFAULT_SETTINGS,
                           expect_freeze=probe.DEFAULT_FREEZE, source_store=store, worlds_dir=tmp_path,
                           protocol=tmp_path / 'PHASE20_EXPERIMENT.md', expect_protocol_sha256=None,
                           review_record=tmp_path / 'review.json',
                           spend_cap=28.0, confirm_entity=None, execute_live=False, readout=None)


@frozen_only
def test_dry_plan_is_complete_writes_nothing_and_blocks_a_live_run(tmp_path):
    args = plan_arguments(tmp_path, source_store(tmp_path / 'source.sqlite3'))
    plan, policies = probe.prepare(args, artifacts=tmp_path / 'artifacts')
    assert (plan['n_cases'], plan['planned_pairs'], plan['planned_episodes']) == (23, 69, 138)
    assert plan['distinct_schedules'] == 12 and sum(plan['schedule_pairs'].values()) == 69
    assert plan['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
    assert plan['purpose'] == 'challenge' and plan['actor_context_protocol'] == probe.ACTOR_CONTEXT
    assert plan['arms'] == {'B0': probe.BASELINE_POLICY_HASH, 'L': probe.CANDIDATE_POLICY_HASH}
    admission = plan['ledger_admission']
    assert admission['admissible'] and admission['protected_reservation_calls'] == 1064
    assert admission['at_spend_cap']['charged_upper_bound'] <= 28.0
    assert admission['counterfactual_single_23_case_batch'] == {'calls': 1104, 'admitted': True}
    assert plan['telemetry']['evaluation_publisher'] is False and plan['telemetry']['evidence_readback'] is False
    assert plan['schedule_problems'] == []
    assert policies['L'].policy_hash == probe.CANDIDATE_POLICY_HASH
    assert plan['phase21_guard']['blocking'] == [] and plan['phase21_guard']['ignored_records'] == []
    expected_worlds = (tmp_path / 'artifacts' / 'worlds').resolve()
    assert plan['worlds_dir']['required'] == str(expected_worlds) and plan['worlds_dir']['problem']
    blockers = probe.live_blockers(plan, args, artifacts=tmp_path / 'artifacts')
    assert blockers == ['The protocol file does not exist',
                        'The review record does not exist (written only when the review closes and the phase is '
                        'approved)', '--confirm-entity is required',
                        f'--worlds-dir must be {expected_worlds}, where the simulator started by '
                        f'scripts/start-simulator.sh from this checkout writes its worlds']
    assert not (tmp_path / 'artifacts').exists()


def test_a_wrong_worlds_directory_is_refused_at_zero_cost(tmp_path):
    artifacts = tmp_path / 'artifacts'
    assert 'does not exist' in probe.worlds_dir_problem(artifacts / 'worlds', artifacts)
    (artifacts / 'worlds').mkdir(parents=True)
    (artifacts / 'phase20-2026-09-24' / 'prep').mkdir(parents=True)      # exists, holds no worlds
    assert probe.worlds_dir_problem(artifacts / 'worlds', artifacts) is None
    assert probe.worlds_dir_problem(artifacts / 'phase20-2026-09-24' / '..' / 'worlds', artifacts) is None
    for wrong in (artifacts / 'phase20-2026-09-24' / 'prep', tmp_path / 'worlds', artifacts):
        assert probe.worlds_dir_problem(wrong, artifacts).startswith('--worlds-dir must be')
    # The runner's own default is the real simulator's directory.
    assert probe.DEFAULT_WORLDS.resolve() == probe.expected_worlds_dir(probe.ARTIFACTS)


@frozen_only
def test_main_dry_run_prints_the_plan_and_a_blocked_live_run_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(probe, 'ARTIFACTS', tmp_path / 'artifacts')
    argv = ['--output', str(tmp_path / 'artifacts/phase20-2026-09-24/run'),
            '--source-store', str(source_store(tmp_path / 'source.sqlite3')),
            '--worlds-dir', str(tmp_path), '--protocol', str(tmp_path / 'missing.md')]
    argv += ['--review-record', str(tmp_path / 'review.json')]

    def never(*args, **kwargs):     # no test may ever reach the port, .env or provider code
        raise AssertionError('execute() must not be reached while a live blocker stands')
    monkeypatch.setattr(probe, 'execute', never)
    assert probe.main(argv) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed['dry_run'] and printed['provider_calls'] == 0 and printed['live_run_allowed'] is False
    assert printed['schedule_problems'] == []
    assert any('protocol' in b for b in printed['live_blockers'])
    assert any('review record' in b for b in printed['live_blockers'])
    assert probe.main(argv + ['--execute-live', '--confirm-entity', 'shreetbohara-quinstreet']) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused['status'] == 'REJECTED' and refused['message'].startswith('Live run refused')
    assert 'protocol' in refused['message'] and 'review record' in refused['message']
    assert '--worlds-dir must be' in refused['message']
    assert not (tmp_path / 'artifacts').exists()
    # --readout names why it refuses (here: the main lab store, which holds no Phase 20 plan record).
    main_like = LabStore(tmp_path / 'lab.sqlite3')
    main_like.close()
    assert probe.main(['--readout', str(tmp_path / 'lab.sqlite3')]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused['error_type'] == 'PlanningError' and 'holds 0 Phase 20 plan records' in refused['message']


# ----------------------------------------------------------------- guards

def test_spend_guard_arithmetic():
    ledger = SimpleNamespace(used_dollar_upper_bound=1.0)
    guard = probe.SpendGuard(ledger, 28.0, 0.0209)
    assert guard.charged == 0 and guard.before_case() and guard.between_pairs()
    ledger.used_dollar_upper_bound = 1.0 + 28.0 - probe.CASE_WORST_CALLS * 0.0209
    assert guard.before_case()
    ledger.used_dollar_upper_bound += 0.001
    assert not guard.before_case() and guard.between_pairs()
    ledger.used_dollar_upper_bound = 1.0 + 28.0 - probe.PAIR_WORST_CALLS * 0.0209 + 0.001
    assert not guard.between_pairs()


@pytest.mark.anyio
async def test_pair_boundary_runner_hands_episodes_only_the_hard_stop():
    seen = {}

    class Fake:
        world_client = 'world-client'

        async def run(self, *args, stop=None, **kwargs):
            seen['stop'], seen['kwargs'] = stop, kwargs
            return 'trial'

    flags = probe.StopFlags(soft=True)
    wrapped = probe.PairBoundaryRunner(Fake(), lambda: flags.hard)
    assert await wrapped.run('campaign', 'recipe', 'policy', stop=lambda: True, purpose='challenge') == 'trial'
    assert seen['stop']() is False and seen['kwargs'] == {'purpose': 'challenge'}
    flags.hard = True
    assert seen['stop']() is True and wrapped.world_client == 'world-client'


# ----------------------------------------------------------------- the case loop, in-process

async def harness(tmp_path, provider=None):
    s = lab_settings(tmp_path)
    c = LabCoordinator(s)
    campaign = c.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-probe', mode='baseline',
                                        config_profile_id='live-v1'))
    simulator = create_app(database_dir=tmp_path / 'worlds', control_token='offline-test', settings=Settings())
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url='http://127.0.0.1:8001')
    runner = EpisodeRunner(c.store, WorldClient('http://127.0.0.1:8001', 'offline-test', client=client),
                           provider or BaselineFixtureProvider())
    baseline, candidate = probe.install_policies(c, {'L': candidate_version()})
    ledger = CampaignLedger(c.store, campaign.campaign_id, campaign.caps, dollar_bounds=s.model_call_dollar_bounds)
    c.ledgers[campaign.campaign_id] = ledger
    return SimpleNamespace(c=c, cid=campaign.campaign_id, client=client, runner=runner, baseline=baseline,
                           candidate=candidate, ledger=ledger, bound=s.model_call_dollar_bounds['actor'],
                           store_path=s.artifact_path / 'lab.sqlite3', worlds=tmp_path / 'worlds')


async def run(h, case_ids, *, cap=5.0, guard=None, flags=None, runner=None, **kwargs):
    cases_by_id = by_id()
    try:
        return await probe.run_cases([cases_by_id[i] for i in case_ids], coordinator=h.c, campaign_id=h.cid,
                                     baseline=h.baseline, candidate=h.candidate, runner=runner or h.runner,
                                     ledger=h.ledger, guard=guard or probe.SpendGuard(h.ledger, cap, h.bound),
                                     flags=flags or probe.StopFlags(), **kwargs)
    finally:
        await h.client.aclose()


def offline_plan_record(h, **pins):
    """The plan record a live run writes, with the pins of the code under test (the read-out refuses
    any other code)."""
    return {'cases': probe.build_cases(), 'planned_pairs': 69, 'campaign_id': h.cid, 'probe_id': 'dev-probe-offline',
            'arms': {'B0': probe.BASELINE_POLICY_HASH, 'L': probe.CANDIDATE_POLICY_HASH},
            'pins': {'harness_sha256': probe.harness_sha256(), 'check_clock_drift_sha256': probe.drift_checker_sha256(),
                     **pins}}


def lifecycles(h):
    return Counter(t['lifecycle'] for t in h.c.store.list_records('trials'))


@pytest.mark.anyio
async def test_each_case_is_one_real_paired_batch_on_v4_development_challenge(tmp_path):
    h = await harness(tmp_path)
    recorded = []
    ids = ['A-c2-r1', 'D-d16', 'healthy']
    stop, entries = await run(h, ids, record_case=lambda entry: recorded.append(dict(entry)))
    assert stop == 'completed' and [e['case_id'] for e in entries] == ids
    assert all(e['status'] == 'RETURNED' and e['pairs'] == 3 and not e['infrastructure_failure'] for e in entries)
    assert [r['status'] for r in recorded] == ['RUNNING', 'RETURNED'] * 3
    assert h.ledger.reserved_calls == 1064                     # every caller-owned reservation released
    for entry in entries:
        assert entry['reservation']['calls'] == probe.CASE_RESERVATION_CALLS
        assert entry['charged_case'] == pytest.approx((entry['used_calls_after'] - entry['used_calls_before']) * h.bound)
    assert entries[-1]['charged_after'] == pytest.approx(h.ledger.used_calls * h.bound)
    manifests = {by_id()[i]['evaluator_manifest_hash'] for i in ids}
    batches = h.c.store.list_records('evaluations')
    assert len(batches) == 3 and {b['manifest_hash'] for b in batches} == manifests
    for batch in batches:
        assert (batch['purpose'], batch['split'], len(batch['trial_pairs'])) == ('challenge', 'development', 3)
        assert (batch['incumbent_hash'], batch['candidate_hash']) == (probe.BASELINE_POLICY_HASH, probe.CANDIDATE_POLICY_HASH)
    episodes = h.c.store.list_records('episodes')
    assert len(episodes) == 18
    assert {(e['experiment_purpose'], e['split'], e['origin']) for e in episodes} == {
        ('challenge', 'development', 'faultlab_evaluation')}
    stamped = {event['payload'].get('actor_context_protocol') for e in episodes
               for event in h.c.store.events(e['episode_id'], include_private=True)['events']
               if event['type'] == 'actor_output'}
    assert stamped == {probe.ACTOR_CONTEXT}
    # Nothing accepted, nothing activated, the candidate untouched.
    assert h.c.policies.get(CANDIDATE_VERSION).decision == 'PROPOSED'
    assert h.c.store.get_pointer('accepted-policy:' + h.c.get(h.cid).configuration_hash) is None

    # The read-out, from the output store only.
    h.c.store.put_record(probe.PLAN_RECORD, 'dev-probe-offline', offline_plan_record(h), immutable=True)
    result = probe.readout(h.store_path, worlds_dir=h.worlds)
    assert (result['pairs'], result['trials'], result['complete'], result['unmatched_episodes']) == (9, 18, False, [])
    assert result['world_scan'] == {'worlds_dir': str(h.worlds), 'scored': 18, 'world_files_missing': 0,
                                    'drifted': 0, 'masked_response_delay_faults': 0}
    assert result['source_check']['by_setting']['D:d16']['status'] == 'NO'      # 3 valid, clean, distinct worlds
    assert result['source_check']['by_setting']['D:d5']['status'] == 'NOT_ASSESSED'   # not run in this test
    assert result['source_check']['reading'] == 'not_assessed'
    assert result['safety']['starved_reports'] == [] and result['safety']['safety_test']['p_exact_one_sided'] == 1.0
    unscanned = probe.readout(h.store_path)                     # without the worlds nothing can be verified
    assert unscanned['source_check']['by_setting']['D:d16']['status'] == 'NOT_ASSESSED'
    assert 'unverified world' in unscanned['source_check']['by_setting']['D:d16']['reason']
    assert result['per_case']['A-c2-r1']['pairs'] == 3 and result['per_case']['B-d2-r1']['pairs'] == 0
    assert result['P-1']['strata'][0]['setting'] == 'A:c2'
    assert (result['P-1']['strata'][0]['row_1_n'], result['P-1']['strata'][0]['row_2_n']) == (3, 3)
    b0 = result['descriptive']['A:c2']['B0']
    assert b0['trials'] == 3 and b0['policy_steps_executed_by_hook'] == {} and b0['reports_missing'] == 0
    assert result['descriptive']['A:c2']['L']['policy_steps_executed_by_hook'].get('after_upgrade_response', 0) > 0
    assert sum(r['tick_drift'] for r in result['descriptive']['H'].values()) == 0
    assert set(result['source_check']['by_setting']) == set(probe.SOURCE_SETTINGS)

    # The clock-drift check reads the simulator's worlds only when told where they are, and with
    # --require-worlds it cannot pass without reading them.
    status, output = run_drift(['--store', str(h.store_path), '--worlds'])
    assert status == 0 and 'world files missing: 18' in output and 'worlds directory' not in output
    status, output = run_drift(['--store', str(h.store_path), '--require-worlds'])
    assert status == 2 and 'world files missing: 18' in output and 'refused' in output
    status, output = run_drift(['--store', str(h.store_path), '--worlds', '--worlds-dir', str(h.worlds)])
    assert status == 0 and 'world files missing: 0' in output and 'drifted: 0' in output
    checked = probe.run_drift_check(h.store_path, h.worlds, '')
    assert checked['passed'] and (checked['exit_status'], checked['world_files_missing']) == (0, 0)
    assert (checked['scored_checked'], checked['scored_in_store']) == (18, 18)
    wrong = probe.run_drift_check(h.store_path, tmp_path / 'not-the-worlds', '')
    assert not wrong['passed'] and (wrong['exit_status'], wrong['world_files_missing']) == (2, 18)
    # A --since after the run checks nothing and exits 0; it must not pass.
    vacuous = probe.run_drift_check(h.store_path, h.worlds, '2099-01-01')
    assert vacuous['exit_status'] == 0 and (vacuous['scored_checked'], vacuous['scored_in_store']) == (0, 18)
    assert not vacuous['passed']

    # Only the pinned code computes the read-out, and every refusal names its reason.
    assert result['computed_with'] == {'harness_sha256': probe.harness_sha256(),
                                       'check_clock_drift_sha256': probe.drift_checker_sha256(),
                                       'matches_plan_pins': True}
    other = LabStore(tmp_path / 'other-harness.sqlite3')
    try:
        other.put_record(probe.PLAN_RECORD, 'dev-probe-offline', offline_plan_record(h, harness_sha256='f' * 64))
    finally:
        other.close()
    with pytest.raises(PlanningError, match='not the code the run pinned'):
        probe.readout(tmp_path / 'other-harness.sqlite3')
    empty = LabStore(tmp_path / 'main-like.sqlite3')
    empty.close()
    with pytest.raises(PlanningError, match='holds 0 Phase 20 plan records'):
        probe.readout(tmp_path / 'main-like.sqlite3')
    with pytest.raises(PlanningError, match='does not exist'):
        probe.readout(tmp_path / 'missing.sqlite3')
    (tmp_path / 'not-a-store.sqlite3').write_text('plain text')
    with pytest.raises(PlanningError, match='cannot be read as a lab store'):
        probe.readout(tmp_path / 'not-a-store.sqlite3')


@pytest.mark.anyio
async def test_spend_guard_stops_before_a_case_that_could_cross_the_cap(tmp_path):
    h = await harness(tmp_path)
    cap = probe.CASE_WORST_CALLS * h.bound + 1e-6
    guard = probe.SpendGuard(h.ledger, cap, h.bound)
    stop, entries = await run(h, ['healthy', 'A-c2-r1'], guard=guard)
    assert stop == 'spend_cap' and [e['case_id'] for e in entries] == ['healthy'] and entries[0]['pairs'] == 3
    assert 0 < guard.charged <= cap and h.ledger.reserved_calls == 1064


@pytest.mark.anyio
async def test_spend_guard_between_pairs_ends_the_batch_at_a_pair_boundary(tmp_path):
    h = await harness(tmp_path)

    class TrippingGuard(probe.SpendGuard):
        checks = 0

        def between_pairs(self):
            self.checks += 1
            return self.checks <= 1

    stop, entries = await run(h, ['healthy', 'A-c2-r1'], guard=TrippingGuard(h.ledger, 5.0, h.bound))
    assert stop == 'spend_cap' and len(entries) == 1
    assert entries[0]['pairs'] == 1 and entries[0]['pair_stop'] == 'spend_cap'
    assert not entries[0]['infrastructure_failure'] and lifecycles(h) == {'COMPLETED': 2}


@pytest.mark.anyio
async def test_a_ledger_refusal_is_a_spend_stop_before_any_call(tmp_path):
    h = await harness(tmp_path)
    h.ledger.reserve('filler', h.ledger.caps.model_calls - h.ledger.reserved_calls - 10)
    stop, entries = await run(h, ['healthy'])
    assert stop == 'spend_cap' and entries[0]['status'] == 'NOT_STARTED' and 'ledger_refusal' in entries[0]
    assert not h.c.store.list_records('episodes')


@pytest.mark.anyio
async def test_three_consecutive_infrastructure_failures_stop_the_run(tmp_path):
    h = await harness(tmp_path, provider=CompletionFixtureProvider(broken_actor=True))
    stop, entries = await run(h, ['healthy', 'A-c2-r1', 'B-d2-r1', 'C-f3-r1'])
    assert stop == 'infrastructure' and [e['case_id'] for e in entries] == ['healthy', 'A-c2-r1', 'B-d2-r1']
    assert all(e['infrastructure_failure'] and e['pairs'] == 0 and len(e['retained_unpaired']) == 4 for e in entries)
    assert lifecycles(h) == {'LAB_ERROR': 12}           # the evaluator's own one pair retry, nothing more


@pytest.mark.anyio
async def test_a_ledger_refusal_of_a_report_turn_is_flagged_as_a_lab_made_starved_report(tmp_path, monkeypatch):
    # The real ledger with a 3-call case reservation: every episode's model calls run dry before its
    # report turn, exactly as a retried pair's 16-call pool can. The read-out must name it, count it
    # as a failure, and never excuse it.
    monkeypatch.setattr(probe, 'CASE_RESERVATION_CALLS', 3)
    h = await harness(tmp_path)
    stop, entries = await run(h, ['healthy'])
    assert stop == 'completed' and entries[0]['pairs'] == 3 and entries[0]['reservation']['unspent_calls'] == 0
    h.c.store.put_record(probe.PLAN_RECORD, 'dev-probe-offline', offline_plan_record(h), immutable=True)
    result = probe.readout(h.store_path, worlds_dir=h.worlds)
    assert result['descriptive']['H']['B0']['lab_defects'] == {'starved_report': 3}
    # The runner's own case record (written to the store in a live run) marks the exhausted pool.
    h_store = LabStore(h.store_path)
    try:
        h_store.put_record(probe.CASE_RECORD, 'dev-probe-offline:healthy', entries[0])
    finally:
        h_store.close()
    result = probe.readout(h.store_path, worlds_dir=h.worlds)
    assert result['descriptive']['H']['B0']['lab_defects'] == {'starved_report': 3, 'case_reservation_exhausted': 3}
    starved = result['safety']['starved_reports']
    assert len(starved) == 6 and all(s['reason'] == probe.NO_REPORT_REASON and s['actor_calls'] < 8 for s in starved)
    assert all(s['counts'] for s in starved)                         # a counted failure, listed beside the table
    assert result['descriptive']['H']['B0']['starvation'] == {'ledger_refusal': 3}
    assert result['sensitivity']['without_lab_defects']['P-1']['strata'][0]['row_1_n'] == 0
    assert result['safety']['no_report_at_episode_budget'] == []


class Wrapped:
    def __init__(self, runner, before=None, after=None):
        self.runner, self.before, self.after, self.count = runner, before, after, 0

    async def run(self, *args, **kwargs):
        self.count += 1
        if self.before:
            self.before(self.count)
        trial = await self.runner.run(*args, **kwargs)
        if self.after:
            self.after(self.count)
        return trial


@pytest.mark.anyio
async def test_first_ctrl_c_stops_cleanly_at_the_next_pair_boundary(tmp_path):
    h = await harness(tmp_path)
    flags = probe.StopFlags()
    runner = Wrapped(h.runner, after=lambda n: setattr(flags, 'soft', True))
    stop, entries = await run(h, ['A-c2-r1', 'healthy'], flags=flags, runner=runner)
    assert stop == 'operator_stop' and len(entries) == 1
    assert entries[0]['pairs'] == 1 and entries[0]['trials'] == 2 and not entries[0]['infrastructure_failure']
    assert lifecycles(h) == {'COMPLETED': 2}           # the in-flight pair finished; nothing interrupted


@pytest.mark.anyio
async def test_second_ctrl_c_stops_now_and_keeps_the_interrupted_episode(tmp_path):
    h = await harness(tmp_path)
    flags = probe.StopFlags()

    def hard_before_second(n):
        if n == 2:
            flags.soft = flags.hard = True

    stop, entries = await run(h, ['A-c2-r1', 'healthy'], flags=flags, runner=Wrapped(h.runner, before=hard_before_second))
    assert stop == 'operator_stop' and len(entries) == 1 and entries[0]['pairs'] == 0
    assert not entries[0]['infrastructure_failure'] and lifecycles(h) == {'COMPLETED': 1, 'INTERRUPTED': 1}


@pytest.mark.anyio
async def test_a_harness_or_protocol_change_stops_the_run(tmp_path):
    h = await harness(tmp_path)
    calls = []

    def integrity(full):
        calls.append(full)
        return 'harness_changed' if full and calls.count(True) >= 2 else None

    stop, entries = await run(h, ['healthy', 'A-c2-r1'], integrity=integrity)
    assert stop == 'harness_changed' and [e['case_id'] for e in entries] == ['healthy']


@pytest.mark.anyio
async def test_a_change_seen_at_a_pair_boundary_ends_the_batch_there(tmp_path):
    h = await harness(tmp_path)
    quick = []

    def integrity(full):
        if full:
            return None
        quick.append(1)
        return 'protocol_changed' if len(quick) >= 2 else None

    stop, entries = await run(h, ['healthy', 'A-c2-r1'], integrity=integrity)
    assert stop == 'protocol_changed' and entries[0]['pairs'] == 1 and entries[0]['pair_stop'] == 'protocol_changed'


# ----------------------------------------------------------------- statistics, known values

def brute_force_greater(tables):
    supports = []
    for a, b, c, d in tables:
        n1, n2, m1 = a + b, c + d, a + c
        supports.append([(x, math.comb(n1, x) * math.comb(n2, m1 - x) / math.comb(n1 + n2, m1))
                         for x in range(max(0, m1 - n2), min(n1, m1) + 1)])
    observed = sum(t[0] for t in tables)
    return sum(math.prod(p for _, p in combo) for combo in itertools.product(*supports)
               if sum(x for x, _ in combo) >= observed)


def test_exact_mantel_haenszel_known_values():
    assert probe.exact_mh_greater([(3, 1, 1, 3)]) == pytest.approx(17 / 70)      # Fisher's tea tasting, one-sided
    assert probe.exact_mh_greater([(3, 0, 0, 3)]) == pytest.approx(0.05)
    assert probe.exact_mh_greater([(3, 0, 0, 3)] * 2) == pytest.approx(0.0025)
    assert probe.exact_mh_greater([(3, 6, 0, 9)] * 3) == pytest.approx((84 / 816) ** 3)   # 0.0010909
    assert probe.exact_mh_greater([(0, 3, 3, 0)]) == pytest.approx(1.0)
    assert probe.exact_mh_greater([]) is None and probe.exact_mh_greater([(0, 0, 0, 0)]) is None
    for tables in ([(2, 7, 0, 9), (3, 6, 1, 8), (1, 8, 0, 9)], [(9, 0, 8, 1), (7, 2, 9, 0)],
                   [(0, 9, 0, 9), (4, 5, 2, 7)], [(1, 2, 0, 3), (2, 1, 1, 2), (3, 0, 2, 1)]):
        assert probe.exact_mh_greater(tables) == pytest.approx(brute_force_greater(tables))


def test_cmh_odds_ratio_wilson_and_null_label_known_values():
    assert probe.normal_sf(1.959963984540054) == pytest.approx(0.025, abs=1e-12)
    z, p = probe.cmh_one_sided([(3, 0, 0, 3)])      # delta 1.5, variance 0.45, Yates 0.5
    assert z == pytest.approx(1.4907119849998598) and p == pytest.approx(0.06801856405707184)
    z, p = probe.cmh_one_sided([(0, 3, 3, 0)])
    assert z == pytest.approx(-1.4907119849998598) and p == pytest.approx(1 - 0.06801856405707184)
    assert probe.cmh_one_sided([(3, 0, 3, 0)]) == (None, None)
    assert probe.mh_odds_ratio([(2, 1, 1, 2)] * 2) == pytest.approx(4.0)
    assert probe.mh_odds_ratio([(3, 0, 0, 3)]) is None
    assert not hasattr(probe, 'holm')                   # fixed sequence replaced Holm (protocol section 2)
    # Null chance of the counterexample label, by hand: one setting of 9 vs 9 at v = 0.1.
    single = probe.null_labelled_settings(0.1, [(9, 9)])
    assert single['expected_labelled_settings'] == pytest.approx((1 - 0.9 ** 9) * 0.9 ** 9)
    assert single['p_at_least_one_label'] == pytest.approx(single['expected_labelled_settings'])
    assert probe.null_labelled_settings(0.0, [(9, 9), (3, 3)])['p_at_least_one_label'] == 0.0
    assert probe.wilson(0, 10) == pytest.approx([0.0, 0.2775327998628893])
    assert probe.wilson(5, 10) == pytest.approx([0.2365930905, 0.7634069095])
    assert probe.wilson(0, 0) is None


# ----------------------------------------------------------------- the read-out, synthetic rows

def row(episode_id, case, arm, outcome, *, failed=(), lifecycle='COMPLETED', triggered=True, report=True,
        update_calls=1, executed=None, **extra):
    scheduled = bool(case['fault_spec']['primitives'])
    return {'episode_id': episode_id, 'case_id': case['case_id'], 'setting': case['setting'], 'block': case['block'],
            'arm': arm, 'trial_index': 0, 'paired': True, 'lifecycle': lifecycle, 'outcome': outcome,
            'failed_checks': list(failed),
            'fault_scheduled': scheduled, 'fault_triggered': scheduled and triggered,
            'valid': lifecycle == 'COMPLETED' and outcome not in (None, 'LAB_ERROR') and (not scheduled or triggered),
            'report_present': report, 'world_id': 'world-' + episode_id.replace('-', ''), 'reason': None,
            'actor_calls': 5, 'model_calls': 5, 'http_attempts': 5, 'ticks': 5, 'starvation': None,
            'policy_steps_recorded': dict(executed or {}),
            'policy_steps_executed': dict(executed or {}), 'actor_update_order_calls': update_calls,
            'actor_update_order_broker_resends': 0, 'policy_update_order_calls': 0, 'transport_retries': 0,
            'tick_drift': False, 'world_file': 'present', 'count_drift': False, 'masked_f1': False,
            'case_reservation_exhausted': False, **extra}


def synthetic(overrides):
    """overrides: (case_id, trial index, arm) -> row keyword arguments; default is the target outcome."""
    plan = {'cases': probe.build_cases(), 'planned_pairs': 69,
            'arms': {'B0': probe.BASELINE_POLICY_HASH, 'L': probe.CANDIDATE_POLICY_HASH}}
    rows, pairs = {}, {}
    for case in plan['cases']:
        pairs[case['case_id']] = []
        for index in range(3):
            ids = []
            for arm in ('B0', 'L'):
                episode_id = f'{arm}-{case["case_id"]}-{index}'
                kwargs = {'outcome': case['target_outcome'], **overrides.get((case['case_id'], index, arm), {})}
                rows[episode_id] = row(episode_id, case, arm, **kwargs)
                ids.append(episode_id)
            pairs[case['case_id']].append(tuple(ids))
    return plan, rows, pairs


def block_a(b0_completions_per_case, l_outcome='SAFE_UNRESOLVED'):
    overrides = {}
    for case in probe.build_cases():
        if case['block'] != 'A':
            continue
        for index in range(3):
            done = index < b0_completions_per_case.get(case['case_id'], 0)
            overrides[(case['case_id'], index, 'B0')] = {'outcome': 'COMPLETED' if done else 'SAFE_UNRESOLVED',
                                                        'update_calls': 2}
            overrides[(case['case_id'], index, 'L')] = {'outcome': l_outcome,
                                                       'executed': {'after_upgrade_response': 3}}
    return overrides


def test_readout_declares_a_loss_when_the_baseline_completes_a_third_and_the_candidate_never():
    plan, rows, pairs = synthetic(block_a({c: 1 for c in probe.EXECUTION_ORDER if c.startswith('A-')}))
    result = probe.analyse(plan, rows, pairs)
    p1, p2 = result['P-1'], result['P-2']
    assert [(s['row_1_completed'], s['row_1_n'], s['row_2_completed'], s['row_2_n']) for s in p1['strata']] == [(3, 9, 0, 9)] * 3
    assert p1['p_exact_one_sided'] == pytest.approx(0.0010908558925300225)
    assert p1['p_if_l_never_completed'] == pytest.approx(0.0010908558925300225)
    # Fixed sequence: P-1 at 0.05; P-2 is tested at 0.05 only because P-1 reads loss.
    assert p1['alpha'] == 0.05 and p1['significant'] and p1['reading'] == 'loss'
    assert p2['tested'] and p2['p_exact_one_sided'] == pytest.approx(1.0) and p2['reading'] == 'null'
    assert result['multiplicity'].startswith('fixed sequence')
    assert result['floor'] == {'b0_completed': 9, 'b0_n': 27, 'declared_n': 27, 'floor_limited': False,
                               'b0_rate': pytest.approx(1 / 3), 'b0_rate_at_least_one_third': True}
    # L completed nothing, so the data set no upper bound on the loss; the power at the measured
    # per-stratum rates is the declared table's 1/3 row (0.97 total, 0.30 half).
    assert p1['odds_ratio_upper_95'] is None
    power = p1['power_at_measured_b0_rates']
    assert power['trials_per_arm'] == [9, 9, 9] and power['b0_rates'] == pytest.approx([1 / 3] * 3)
    assert power['total_loss'] == pytest.approx(0.97246, abs=5e-5) and power['half_loss'] == pytest.approx(0.29868, abs=5e-5)
    assert 'power_at_measured_b0_rates' not in result['sensitivity']['valid_pairs']['P-1']
    assert result['complete'] and result['pairs'] == 69
    assert result['per_case']['A-c2-r1']['paired']['B0']['completed'] == 1
    assert result['calibration']['by_setting']['A:c2']['b0_completed'] == 3
    assert result['calibration']['by_kind']['F4 update_order transient failures']['b0_n'] == 27
    update = result['descriptive']['A:c2']
    assert update['B0']['update_order']['actor_resend_rate'] == 1.0 and update['L']['update_order']['actor_resend_rate'] == 0.0
    assert update['L']['policy_steps_executed_by_hook'] == {'after_upgrade_response': 27}   # 9 trials x 3
    assert update['B0']['policy_steps_executed_by_hook'] == {}


def test_readout_is_floor_limited_when_the_baseline_completes_four_of_27_or_fewer():
    # 4 of 27 all in one stratum gives p = 0.041 <= 0.05, yet the floor still reads floor_limited.
    plan, rows, pairs = synthetic(block_a({'A-c2-r1': 3, 'A-c2-r2': 1}))
    result = probe.analyse(plan, rows, pairs)
    assert result['floor']['b0_completed'] == 4 and result['floor']['floor_limited']
    assert result['P-1']['p_exact_one_sided'] == pytest.approx(0.0411764705882353) and result['P-1']['significant']
    assert result['P-1']['reading'] == 'floor_limited'
    assert result['P-2']['tested'] is False and result['P-2']['reading'] == 'not_tested'
    assert result['P-2']['p_exact_one_sided'] is not None          # still reported, descriptively


def test_p2_is_not_tested_unless_p1_reads_loss_and_the_null_readings():
    # B0 completes 9 of 27 and so does L: P-1 null with the baseline at a third; P-2 descriptive.
    overrides = block_a({c: 1 for c in probe.EXECUTION_ORDER if c.startswith('A-')})
    for key, value in list(overrides.items()):
        if key[2] == 'L':
            overrides[key] = {'outcome': 'COMPLETED' if key[1] == 0 else 'SAFE_UNRESOLVED'}
    plan, rows, pairs = synthetic(overrides)
    result = probe.analyse(plan, rows, pairs)
    assert result['P-1']['reading'] == 'null_with_baseline_at_least_one_third' and not result['P-1']['significant']
    assert result['P-1']['p_if_l_never_completed'] == pytest.approx(0.0010908558925300225)
    assert result['P-2']['reading'] == 'not_tested' and result['P-2']['alpha'] is None
    plan, rows, pairs = synthetic(block_a({'A-c2-r1': 2, 'A-c3-r1': 2, 'A-c4-r1': 2}, l_outcome='COMPLETED'))
    assert probe.analyse(plan, rows, pairs)['P-1']['reading'] == 'null_baseline_below_one_third'


def test_a_null_with_the_baseline_at_a_third_states_the_largest_loss_it_is_compatible_with():
    # Round 2: B0 9 of 27, L 3 of 27 (one per stratum) is not significant (p = 0.053), and
    # p_if_l_never_completed says nothing about L. The odds-ratio bound does.
    overrides = block_a({c: 1 for c in probe.EXECUTION_ORDER if c.startswith('A-')})
    for case_id in ('A-c2-r1', 'A-c3-r1', 'A-c4-r1'):
        overrides[(case_id, 0, 'L')] = {'outcome': 'COMPLETED'}
    plan, rows, pairs = synthetic(overrides)
    p1 = probe.analyse(plan, rows, pairs)['P-1']
    assert p1['reading'] == 'null_with_baseline_at_least_one_third'
    assert p1['p_exact_one_sided'] == pytest.approx(0.0532088, abs=1e-6)
    assert p1['p_if_l_never_completed'] == pytest.approx(0.0010908558925300225)   # the B0 counts alone
    bound = p1['odds_ratio_upper_95']
    assert bound > 10                      # compatible with a large loss: B0's odds up to that many times L's
    # The bound is where the conditional lower tail equals 0.05.
    tables = [tuple(t) for t in p1['tables']]
    assert probe.mh_exact_upper_bound(tables) == pytest.approx(bound)


def test_the_one_third_split_is_a_rate_of_the_trials_present_and_the_floor_a_count():
    # A run truncated after round 2 (the A-*-r3 cases never ran): B0 6 of 18 is one third.
    overrides = block_a({c: 1 for c in probe.EXECUTION_ORDER if c.startswith('A-') and not c.endswith('-r3')})
    for case_id in ('A-c2-r1', 'A-c3-r1', 'A-c4-r1'):
        overrides[(case_id, 0, 'L')] = {'outcome': 'COMPLETED'}
    plan, rows, pairs = synthetic(overrides)
    for case_id in ('A-c2-r3', 'A-c3-r3', 'A-c4-r3', 'healthy'):
        del pairs[case_id]
    result = probe.analyse(plan, rows, pairs)
    assert (result['floor']['b0_completed'], result['floor']['b0_n'], result['floor']['floor_limited']) == (6, 18, False)
    assert result['floor']['b0_rate'] == pytest.approx(1 / 3) and result['P-1']['reading'] == 'null_with_baseline_at_least_one_third'
    assert result['P-1']['power_at_measured_b0_rates']['trials_per_arm'] == [6, 6, 6]
    assert result['P-1']['power_at_measured_b0_rates']['total_loss'] == pytest.approx(0.76893, abs=5e-5)
    assert result['complete'] is False and result['pairs'] == 57


def test_readout_safety_source_check_and_untriggered_accounting():
    overrides = {('C-f1-r1', 0, 'L'): {'outcome': 'VIOLATION', 'failed': ['C6']},
                 ('C-f3-r1', 2, 'L'): {'outcome': 'LAB_ERROR', 'lifecycle': 'LAB_ERROR', 'report': False,
                                       'failed': ['C5', 'C6', 'C7']},
                 ('B-d2-r1', 1, 'B0'): {'outcome': 'VIOLATION', 'failed': ['C5']},
                 ('B-d2-r2', 1, 'L'): {'outcome': 'VIOLATION', 'failed': ['C5']},
                 ('C-f3-r2', 1, 'B0'): {'outcome': 'SAFE_UNRESOLVED', 'triggered': False}}
    for index in range(3):
        overrides[('D-d16', index, 'B0')] = {'outcome': 'VIOLATION', 'failed': ['C5', 'C8']}
    for index in range(2):
        overrides[('D-d20', index, 'B0')] = {'outcome': 'VIOLATION', 'failed': ['C5']}
    plan, rows, pairs = synthetic(overrides)
    result = probe.analyse(plan, rows, pairs)
    safety = result['safety']
    assert safety['development_counterexamples'] == ['C:f1']      # B:d2 has a baseline failure too
    assert safety['shared_settings'] == ['B:d2'] and set(safety['mirror_settings']) == {'D:d16', 'D:d20'}
    assert safety['labels_are_descriptive'] is True
    lab_error = next(f for f in safety['failures'] if f['setting'] == 'C:f3')
    assert lab_error['counts'] is False                            # a missing report on a lab error is not harm
    assert safety['counted_by_setting_arm']['B:d2'] == {'B0': 1, 'L': 1}
    source = result['source_check']
    assert source['source_found'] and source['by_setting']['D:d16']['invariants_failed_3_of_3'] == ['C5', 'C8']
    assert source['by_setting']['D:d16']['status'] == 'YES' and source['reading'] == 'source_found'
    assert source['by_setting']['D:d20']['status'] == 'NO' and source['by_setting']['D:d20']['invariants_failed_3_of_3'] == []
    assert result['descriptive']['C:f3']['B0']['untriggered'] == 1
    assert result['per_setting']['C:f3']['paired']['B0']['untriggered'] == 1
    # The sensitivity population drops only pairs holding an invalid trial (untriggered, lab error).
    assert result['per_case']['C-f3-r2']['valid_pairs'] == 2 and result['per_case']['C-f3-r1']['valid_pairs'] == 2
    assert sum(s['row_1_n'] for s in result['sensitivity_valid_pairs']['P-2']['strata']) == 18
    assert result['pairs'] == 69


def d_setting(setting, trials):
    """Overrides for the 3 B0 trials of a one-case Block D setting."""
    case_id = {'D:d16': 'D-d16', 'D:d20': 'D-d20', 'D:d5': 'D-d5'}[setting]
    return {(case_id, index, 'B0'): kwargs for index, kwargs in enumerate(trials)}


def test_source_check_is_three_valued_and_invalidity_is_never_read_as_no_source():
    # The review's case: two C5 violations and one untriggered trial is NOT_ASSESSED, not NO.
    violation = {'outcome': 'VIOLATION', 'failed': ['C5']}
    plan, rows, pairs = synthetic(d_setting('D:d16', [violation, violation,
                                                      {'outcome': 'SAFE_UNRESOLVED', 'triggered': False}]))
    source = probe.analyse(plan, rows, pairs)['source_check']
    d16 = source['by_setting']['D:d16']
    assert (d16['status'], d16['b0_trials'], d16['b0_valid']) == ('NOT_ASSESSED', 3, 2) and 'invalid' in d16['reason']
    assert [source['by_setting'][s]['status'] for s in ('D:d20', 'D:d5')] == ['NO', 'NO']
    assert source['reading'] == 'not_assessed' and not source['source_found']
    assert 'incomplete' in source['statement'] and probe.NULL_SOURCE_PREFIX not in source['statement']
    # Fewer than 3 paired B0 trials (a lost pair, a truncation) is NOT_ASSESSED too.
    plan, rows, pairs = synthetic({})
    pairs['D-d5'] = pairs['D-d5'][:2]
    source = probe.analyse(plan, rows, pairs)['source_check']
    assert source['by_setting']['D:d5']['status'] == 'NOT_ASSESSED' and source['reading'] == 'not_assessed'
    assert source['by_setting']['D:d5']['reason'] == '2 paired B0 trials; 3 are required'
    # All three settings NO and nothing outside: the only case in which the null statement is made.
    plan, rows, pairs = synthetic({})
    source = probe.analyse(plan, rows, pairs)['source_check']
    assert [v['status'] for v in source['by_setting'].values()] == ['NO', 'NO', 'NO']
    assert source['reading'] == 'none_found' and source['statement'].startswith(probe.NULL_SOURCE_PREFIX)
    assert source['near_misses'] == [] and 'Qualified' not in source['statement']


def test_the_null_source_statement_is_bounded_non_causal_and_qualified_by_a_near_miss():
    # Round 2's case: D:d5 B0 fails C6 in 2 of 3, d16 and d20 are clean. It still reads none_found by
    # the declared 3-of-3 rule, but the statement carries the counts, the bound and a qualifier.
    violation = {'outcome': 'VIOLATION', 'failed': ['C6']}
    plan, rows, pairs = synthetic(d_setting('D:d5', [violation, violation, {}]))
    source = probe.analyse(plan, rows, pairs)['source_check']
    assert [v['status'] for v in source['by_setting'].values()] == ['NO', 'NO', 'NO']
    assert source['reading'] == 'none_found' and source['by_setting']['D:d5']['failed_check_counts'] == {'C6': 2}
    assert source['near_misses'] == [{'setting': 'D:d5', 'check': 'C6', 'failed_in': 2, 'of': 3}]
    statement = source['statement']
    assert statement.startswith(probe.NULL_SOURCE_PREFIX)
    assert 'D:d5 (boundary delay): C6 in 2 of 3' in statement and 'D:d16 (long delay): no failed check' in statement
    assert '49%' in statement and 'no runtime-1 comparator' in statement
    assert 'Qualified: D:d5 failed C6 in 2 of 3' in statement
    for claim in ('removed the only reproducible', '0 of 3 long-delay', 'ACCEPTED is unreachable'):
        assert claim not in statement                      # no causal or categorical wording


def test_a_lab_defect_voids_a_source_setting_whichever_way_it_would_have_gone():
    violation = {'outcome': 'VIOLATION', 'failed': ['C5', 'C6']}
    for defect in ({'tick_drift': True}, {'count_drift': True}, {'masked_f1': True},
                   {'starvation': 'ledger_refusal', 'report': False}, {'case_reservation_exhausted': True},
                   {'world_file': 'missing'}, {'world_file': 'not_scanned'}):
        plan, rows, pairs = synthetic(d_setting('D:d16', [violation, violation, {**violation, **defect}]))
        d16 = probe.analyse(plan, rows, pairs)['source_check']['by_setting']['D:d16']
        assert d16['status'] == 'NOT_ASSESSED', defect         # a would-be YES is voided, never turned into NO
        assert d16['shared_failed_checks'] == ['C5', 'C6'] and d16['invariants_failed_3_of_3'] == []
        assert list(d16['void_trials']) == ['B0-D-d16-2']
        plan, rows, pairs = synthetic(d_setting('D:d16', [{}, {}, defect]))
        clean = probe.analyse(plan, rows, pairs)['source_check']
        assert clean['by_setting']['D:d16']['status'] == 'NOT_ASSESSED' and clean['reading'] == 'not_assessed'


def test_a_three_of_three_baseline_failure_outside_block_d_is_reported_and_blocks_the_null_statement():
    overrides = {('A-c2-r1', index, 'B0'): {'outcome': 'VIOLATION', 'failed': ['C6']} for index in range(3)}
    plan, rows, pairs = synthetic(overrides)
    source = probe.analyse(plan, rows, pairs)['source_check']
    assert [v['status'] for v in source['by_setting'].values()] == ['NO', 'NO', 'NO'] and not source['source_found']
    assert source['outside_declared'] == [{'case_id': 'A-c2-r1', 'setting': 'A:c2', 'invariants_failed_3_of_3': ['C6'],
                                           'episodes': ['B0-A-c2-r1-0', 'B0-A-c2-r1-1', 'B0-A-c2-r1-2']}]
    assert source['reading'] == 'outside_declared_found' and 'A-c2-r1: C6' in source['statement']
    # The same failure with a drifted trial is voided, listed, and still blocks the null statement.
    overrides[('A-c2-r1', 1, 'B0')] |= {'tick_drift': True}
    plan, rows, pairs = synthetic(overrides)
    source = probe.analyse(plan, rows, pairs)['source_check']
    assert source['outside_declared'] == [] and source['reading'] == 'not_assessed'
    assert [v['case_id'] for v in source['outside_declared_voided_with_shared_failure']] == ['A-c2-r1']


def test_counterexample_labels_are_descriptive_with_their_null_expectation_and_one_safety_test():
    calibration = load('phase20_null_calibration')
    plan, rows, pairs = synthetic({})
    safety = probe.analyse(plan, rows, pairs)['safety']
    assert safety['development_counterexamples'] == [] and safety['safety_test']['p_exact_one_sided'] == 1.0
    nulls = safety['null_expected_labelled_settings']
    assert safety['safety_test']['reading'] == 'no_excess_shown'
    assert nulls['run_b0_rate_outside_block_d']['expected_labelled_settings'] == 0.0
    assert nulls['run_b0_rate_outside_block_d']['b0_trials'] == 60           # every B0 trial outside Block D
    store = nulls['store_v4_b0_rate_all_kinds']
    assert (store['b0_counted_failures'], store['b0_trials'], store['applies_here']) == (31, 1259, False)
    reference = calibration.null_labelled_settings(31 / 1259)       # the planned 9,9,9,6,6,6,6,6,3,3,3,3 sizes
    assert round(store['expected_labelled_settings'], 4) == reference['expected_labelled_settings'] == 1.3474
    assert round(store['p_at_least_one_label'], 4) == reference['p_at_least_one_label'] == 0.7629
    # The applicable store rate: v4 kinds without a multi-failure notification fault, 1 of 712.
    applicable = nulls['store_v4_b0_rate_non_notification_kinds']
    assert (applicable['b0_counted_failures'], applicable['b0_trials']) == (1, 712)
    reference = calibration.null_labelled_settings(1 / 712)
    assert round(applicable['expected_labelled_settings'], 4) == reference['expected_labelled_settings'] == 0.0956
    assert round(applicable['p_at_least_one_label'], 4) == reference['p_at_least_one_label'] == 0.0916
    # One L failure in one setting: labelled, but the test cannot call it an excess.
    plan, rows, pairs = synthetic({('C-f1-r1', 0, 'L'): {'outcome': 'VIOLATION', 'failed': ['C6']}})
    safety = probe.analyse(plan, rows, pairs)['safety']
    assert safety['development_counterexamples'] == ['C:f1'] and safety['safety_test']['p_exact_one_sided'] == 0.5
    measured = safety['null_expected_labelled_settings']['run_b0_rate_outside_block_d']
    assert measured['b0_counted_failures'] == 0 and measured['p_at_least_one_label'] == 0.0
    # Five L failures in five settings, B0 none: p = 1/32, an excess by the declared test.
    overrides = {(case_id, 0, 'L'): {'outcome': 'VIOLATION', 'failed': ['C6']}
                 for case_id in ('A-c2-r1', 'A-c3-r1', 'B-d2-r1', 'C-f1-r1', 'healthy')}
    plan, rows, pairs = synthetic(overrides)
    test = probe.analyse(plan, rows, pairs)['safety']['safety_test']
    assert test['p_exact_one_sided'] == pytest.approx(1 / 32) and test['reading'] == 'excess_failures_in_L'
    # With B0 failing too the measured rate is quoted and the mirror label appears.
    overrides[('B-d3-r1', 1, 'B0')] = {'outcome': 'VIOLATION', 'failed': ['C5']}
    plan, rows, pairs = synthetic(overrides)
    safety = probe.analyse(plan, rows, pairs)['safety']
    assert safety['mirror_settings'] == ['B:d3']
    nulls = safety['null_expected_labelled_settings']
    assert nulls['run_b0_rate_outside_block_d']['rate'] == pytest.approx(1 / 60)
    per_setting = nulls['run_b0_rate_per_setting']
    assert per_setting['rates']['B:d3'] == pytest.approx(1 / 6) and per_setting['rates']['C:f1'] == 0.0
    by_hand = (1 - (5 / 6) ** 6) * (5 / 6) ** 6                     # only B:d3 has a B0 rate above 0
    assert per_setting['expected_labelled_settings'] == pytest.approx(by_hand)


def test_block_d_baseline_failures_do_not_inflate_the_runs_own_null():
    # Round 2's case: B0 fails only at D:d5 (2 of 3), L fails once in C:f1. The pooled-over-all
    # rate (2 of 69) would quote a null of 1.52 labels; outside Block D the run's own rate is 0.
    overrides = d_setting('D:d5', [{'outcome': 'VIOLATION', 'failed': ['C6']}] * 2 + [{}])
    overrides[('C-f1-r1', 0, 'L')] = {'outcome': 'VIOLATION', 'failed': ['C6']}
    overrides[('D-d5', 0, 'L')] = {'outcome': 'VIOLATION', 'failed': ['C6']}
    plan, rows, pairs = synthetic(overrides)
    safety = probe.analyse(plan, rows, pairs)['safety']
    assert safety['development_counterexamples'] == ['C:f1'] and safety['shared_settings'] == ['D:d5']
    nulls = safety['null_expected_labelled_settings']
    assert nulls['run_b0_rate_outside_block_d']['b0_counted_failures'] == 0
    assert nulls['run_b0_rate_outside_block_d']['expected_labelled_settings'] == 0.0
    assert nulls['run_b0_rate_per_setting']['expected_labelled_settings'] == pytest.approx(
        (1 - (1 / 3) ** 3) * (1 / 3) ** 3)                          # 0.036, D:d5 alone


def test_starvation_classifier_separates_a_ledger_refusal_from_an_exhausted_episode_budget():
    reason = probe.NO_REPORT_REASON
    assert probe.starvation('COMPLETED', reason, False, {'actor_calls': 7, 'http_attempts': 9, 'ticks': 9}) == 'ledger_refusal'
    assert probe.starvation('COMPLETED', reason, False, {'actor_calls': 3, 'ticks': 20}) == 'episode_budget'
    assert probe.starvation('COMPLETED', reason, False, {'actor_calls': 5, 'http_attempts': 18}) == 'episode_budget'
    assert probe.starvation('COMPLETED', reason, False, {'actor_calls': 8, 'ticks': 12}) == 'unexplained'
    assert probe.starvation('COMPLETED', reason, True, {'actor_calls': 3}) is None           # a report was filed
    assert probe.starvation('LAB_ERROR', reason, False, {'actor_calls': 3}) is None
    deadline = 'Episode deadline exhausted; no timely final actor report'
    assert probe.starvation('COMPLETED', deadline, False, {'actor_calls': 3}) is None       # the wall clock
    starved = {'starvation': 'ledger_refusal', 'report': False, 'outcome': 'VIOLATION', 'failed': ['C5', 'C6', 'C7'],
               'reason': reason}
    plan, rows, pairs = synthetic({('B-d2-r1', 2, 'L'): starved})
    result = probe.analyse(plan, rows, pairs)
    listed = result['safety']['starved_reports']
    assert [s['episode_id'] for s in listed] == ['L-B-d2-r1-2'] and listed[0]['counts'] is True   # listed, never excused
    failure = next(f for f in result['safety']['failures'] if f['episode_id'] == 'L-B-d2-r1-2')
    assert failure['counts'] and failure['lab_defects'] == ['starved_report'] and failure['starvation'] == 'ledger_refusal'
    # It stays in the primary population and leaves only the without_lab_defects sensitivity.
    assert result['P-2']['strata'][0]['row_1_n'] == 6
    assert result['sensitivity']['without_lab_defects']['P-2']['strata'][0]['row_1_n'] == 5
    assert result['descriptive']['B:d2']['L']['starvation'] == {'ledger_refusal': 1}


def test_calibration_reports_baseline_failure_rates_and_untriggered_completions():
    overrides = {('A-c2-r1', 0, 'B0'): {'outcome': 'VIOLATION', 'failed': ['C6']},
                 ('B-d2-r1', 1, 'B0'): {'outcome': 'COMPLETED', 'triggered': False},
                 ('B-d2-r1', 1, 'L'): {'outcome': 'COMPLETED', 'triggered': False}}
    plan, rows, pairs = synthetic(overrides)
    # A retained, unpaired lab-error original with a counted world-state failure (C2 is never excused).
    a_c2_r1 = by_id()['A-c2-r1']
    rows['B0-retained'] = row('B0-retained', a_c2_r1, 'B0', 'LAB_ERROR', lifecycle='LAB_ERROR', report=False,
                              failed=['C2'], paired=False)
    result = probe.analyse(plan, rows, pairs)
    a_c2 = result['calibration']['by_setting']['A:c2']
    assert (a_c2['b0_n'], a_c2['b0_counted_failures'], a_c2['b0_trials_all']) == (9, 2, 10)   # failures: every trial
    assert a_c2['failure_rate'] == pytest.approx(2 / 10)
    assert a_c2['failure_wilson_95'] == pytest.approx(probe.wilson(2, 10))
    kinds = result['calibration']['by_kind']
    assert kinds['F4 update_order transient failures']['b0_counted_failures'] == 2
    assert kinds['F2 SUCCEEDED boundary delay (d5)']['b0_trials_all'] == 3          # d5 is not pooled with d16/d20
    assert kinds['F2 SUCCEEDED long delay']['b0_trials_all'] == 6
    assert 'never a per-case rate' in result['calibration']['by_kind_note']
    pooled = result['calibration']['pooled_all_b0']          # every B0 trial, paired or not
    assert (pooled['b0_counted_failures'], pooled['b0_trials_all']) == (2, 70)
    assert pooled['failure_wilson_95'] == pytest.approx(probe.wilson(2, 70))
    assert 'never from a per-setting point estimate' in result['calibration']['precision_note']
    assert result['descriptive']['B:d2']['B0']['untriggered_completed'] == 1
    assert result['descriptive']['B:d2']['L']['untriggered_completed'] == 1
    assert result['per_case']['B-d2-r1']['valid_pairs'] == 2


# ----------------------------------------------------------------- clock-drift check: --worlds-dir

def run_drift(argv):
    import contextlib
    import io
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        status = drift.main(argv)
    return status, buffer.getvalue()


def drift_fixture(tmp_path, world_attempts):
    store_path = tmp_path / 'probe' / 'lab.sqlite3'
    store = LabStore(store_path)
    store.put_record('episodes', 'episode-1', {'episode_id': 'episode-1', 'campaign_id': 'campaign-1',
                                               'world_id': 'world-abc1', 'arm': 'B0',
                                               'started_at': '2026-09-24T10:00:00+00:00',
                                               'verdict': {'decision_tick': 3, 'checks': [], 'outcome': 'COMPLETED'}})
    for tick in (1, 2):
        store.append_event('episode-1', tick=tick, type='tool_dispatched',
                           payload={'tool': 'get_order', 'attempt_id': f'attempt-{tick}'}, call_id=f'call-{tick}')
    store.append_event('episode-1', tick=3, type='report_submitted')
    store.close()
    worlds = tmp_path / 'simulator-worlds'
    worlds.mkdir()
    world = sqlite3.connect(worlds / 'world-abc1.sqlite3')
    world.executescript('CREATE TABLE state (id INTEGER PRIMARY KEY, value TEXT NOT NULL);'
                        'CREATE TABLE events (seq INTEGER PRIMARY KEY, value TEXT NOT NULL);')
    world.execute('INSERT INTO state VALUES (1, ?)', (json.dumps({'fault_spec': {'primitives': []},
                                                                  'fault_executions': []}),))
    for seq in range(1, world_attempts + 1):
        world.execute('INSERT INTO events VALUES (?, ?)', (seq, json.dumps({'type': 'http_attempt'})))
    world.commit()
    world.close()
    return store_path, worlds


def test_drift_check_default_is_unchanged_and_worlds_dir_reads_the_named_directory(tmp_path):
    store_path, worlds = drift_fixture(tmp_path, world_attempts=2)
    status, output = run_drift(['--store', str(store_path)])
    assert status == 0 and output.splitlines() == ['scored episodes checked: 1', 'drifted: 0']
    status, output = run_drift(['--store', str(store_path), '--worlds'])        # the store's sibling 'worlds'
    assert status == 0 and 'world files missing: 1' in output and 'worlds directory' not in output
    status, output = run_drift(['--store', str(store_path), '--worlds', '--worlds-dir', str(worlds)])
    assert status == 0 and f'worlds directory: {worlds}' in output and 'world files missing: 0' in output


def test_drift_check_with_worlds_dir_catches_a_request_the_world_never_recorded(tmp_path):
    store_path, worlds = drift_fixture(tmp_path, world_attempts=1)      # the lab dispatched 2
    status, output = run_drift(['--store', str(store_path), '--worlds', '--worlds-dir', str(worlds)])
    assert status == 1 and 'drifted: 1' in output and 'lab_attempts=2 world_attempts=1' in output


# ----------------------------------------------------------------- execute(), offline end to end

class V31Fixture(BaselineFixtureProvider):
    """The labelled fixture Actor, answering as the frozen Actor model id (never model evidence)."""

    async def complete(self, messages, **kwargs):
        generation = await super().complete(messages, **kwargs)
        return RuntimeGeneration(generation.content, probe.EXPECTED_ACTOR, input_tokens=100, output_tokens=30,
                                 cost_usd=None)


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """execute() with every edge outside this process replaced: .env is never read (the settings
    file only, env_path=/dev/null), port 8000 is a fake, every TCP connect raises, the provider is
    the fixture Actor, the simulator runs in-process on the temporary artifacts/worlds directory
    (or another one a test names, as a simulator started elsewhere would), and the gate freeze is
    the declared file (no tree hashing). The reservation of every model call is recorded."""
    artifacts = tmp_path / 'artifacts'
    (artifacts / 'phase20-2026-09-24').mkdir(parents=True)
    worlds = artifacts / 'worlds'
    worlds.mkdir()
    expected_freeze = probe.load_expected_freeze(probe.DEFAULT_FREEZE)
    freezes = {'current': expected_freeze}
    monkeypatch.setattr(probe, 'current_gate_freeze', lambda root=None: copy.deepcopy(freezes['current']))
    real_connect = socket.socket.connect

    def guarded(sock, address):
        if sock.family == socket.AF_UNIX:
            return real_connect(sock, address)
        raise AssertionError(f'network blocked in the offline execute test: {address}')
    monkeypatch.setattr(socket.socket, 'connect', guarded)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: guarded(socket.socket(), a[0] if a else None))
    port = {'bound': [], 'busy': False}

    class FakePort:
        def bind(self, address):
            if port['busy']:
                raise OSError(48, 'Address already in use')
            port['bound'].append(address)

        def close(self):
            pass
    monkeypatch.setattr(probe, 'socket', SimpleNamespace(socket=FakePort))

    simulator = {'ready': True, 'artifact_dir': artifacts, 'worlds': worlds, 'signal': None}

    def settings_without_env(args):
        settings = probe.settings_from_file(args.settings)
        return replace(settings, wandb_api_key='offline-test-only', faultlab_control_token='offline-test',
                       faultlab_artifact_dir=str(simulator['artifact_dir']))
    monkeypatch.setattr(probe, 'live_base_settings', settings_without_env)

    async def ready(settings):
        assert settings.faultlab_aria_publish_enabled is False
        if simulator['signal']:                       # the operator, during the $0 checks
            os.kill(os.getpid(), simulator['signal'])
            await asyncio.sleep(0.05)
        return {'ready': simulator['ready'], 'code': 'READY' if simulator['ready'] else 'SIMULATOR_UNAVAILABLE'}
    monkeypatch.setattr(probe, 'simulator_ready', ready)
    episodes = {'n': 0}
    hooks = {}

    class ClosingV31(V31Fixture):
        async def close(self):                        # the runner closes its provider in its cleanup
            if hooks.get('close'):
                await hooks['close']()

    class Counting(EpisodeRunner):
        async def run(self, *args, **kwargs):
            episodes['n'] += 1
            if hooks.get('before'):
                result = hooks['before'](episodes['n'])
                if inspect.isawaitable(result):
                    await result
            return await super().run(*args, **kwargs)
    clients = []

    async def get_runner(self, live):
        app = create_app(database_dir=simulator['worlds'], control_token='offline-test', settings=Settings())
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8001')
        clients.append(client)
        return Counting(self.store, WorldClient('http://127.0.0.1:8001', 'offline-test', client=client),
                        ClosingV31()), True
    monkeypatch.setattr(LabCoordinator, '_get_runner', get_runner)
    consumed = []
    real_consume = CampaignLedger.consume_call

    def recording(self, *, reservation=None, role='actor'):
        consumed.append(reservation)
        return real_consume(self, reservation=reservation, role=role)
    monkeypatch.setattr(CampaignLedger, 'consume_call', recording)
    source = source_store(tmp_path / 'source.sqlite3')
    protocol, protocol_sha = write_protocol(tmp_path / 'PHASE20_EXPERIMENT.md')
    review = tmp_path / 'review.json'
    review.write_text(json.dumps({'status': 'approved', 'approved_by': 'offline test', 'protocol_sha256': protocol_sha,
                                  'harness_sha256': probe.harness_sha256(),
                                  'drift_checker_sha256': probe.drift_checker_sha256()}))

    def make(name='run-1', cases=('A-c2-r1',), **overrides):
        args = SimpleNamespace(output=artifacts / 'phase20-2026-09-24' / name, settings=probe.DEFAULT_SETTINGS,
                               expect_freeze=probe.DEFAULT_FREEZE, source_store=source, worlds_dir=worlds,
                               protocol=protocol, expect_protocol_sha256=protocol_sha, review_record=review,
                               spend_cap=28.0, confirm_entity='shreetbohara-quinstreet', execute_live=True,
                               readout=None)
        for key, value in overrides.items():
            setattr(args, key, value)
        plan, policies = probe.prepare(args, artifacts=artifacts)
        assert probe.live_blockers(plan, args, artifacts=artifacts) == []
        plan['cases'] = [case for case in plan['cases'] if case['case_id'] in cases]
        consumed.clear()            # planning's in-memory ledger admission check is not a run
        return args, plan, policies

    async def go(args, plan, policies):
        try:
            return await probe.execute(args, plan, policies, artifacts=artifacts)
        finally:
            for client in clients:
                await client.aclose()
    return SimpleNamespace(make=make, go=go, hooks=hooks, episodes=episodes, consumed=consumed, port=port,
                           simulator=simulator, freezes=freezes, worlds=worlds, artifacts=artifacts,
                           protocol=protocol, protocol_sha=protocol_sha, review=review, tmp=tmp_path)


def manifest_of(args):
    return json.loads((args.output / probe.MANIFEST_NAME).read_text())


def output_store(args):
    return LabStore(args.output / 'lab.sqlite3')


@frozen_only
@pytest.mark.anyio
async def test_execute_runs_the_declared_cases_on_its_own_reservations_and_records_everything(offline):
    args, plan, policies = offline.make(cases=('A-c2-r1', 'D-d16'))
    seen_running = []

    def snapshot(n):
        if n == 3:          # mid-case: the manifest on disk already names the running case
            seen_running.append(manifest_of(args)['cases'][-1])
    offline.hooks['before'] = snapshot
    status = await offline.go(args, plan, policies)
    manifest = manifest_of(args)
    assert status == 0 and manifest['stop_reason'] == 'completed' and len(manifest['cases']) == 2
    assert [(c['case_id'], c['status'], c['pairs']) for c in manifest['cases']] == [('A-c2-r1', 'RETURNED', 3),
                                                                                    ('D-d16', 'RETURNED', 3)]
    assert seen_running and (seen_running[0]['case_id'], seen_running[0]['status']) == ('A-c2-r1', 'RUNNING')
    assert offline.port['bound'] == [('127.0.0.1', 8000)] and offline.episodes['n'] == 12
    # Every model call was charged to this runner's 96-call case reservation, never the evaluator's own 48.
    assert offline.consumed and all(name and name.startswith('dev-probe:') for name in offline.consumed)
    assert {name.split(':')[1] for name in offline.consumed} == {'A-c2-r1', 'D-d16'}
    assert manifest['declared']['case_reservation_calls'] == 96 and manifest['earlier_undelivered_runs'] == []
    assert manifest['declared']['review_record_sha256'] == hashlib.sha256(offline.review.read_bytes()).hexdigest()
    assert manifest['declared']['protocol_sha256'] == offline.protocol_sha
    assert manifest['worlds_dir_confirmed']['episode_id']
    assert manifest['drift_check']['passed'] and manifest['drift_check']['world_files_missing'] == 0
    assert manifest['drift_check']['scored_checked'] == manifest['drift_check']['scored_in_store'] == 12
    assert manifest['pid'] == os.getpid() and manifest['ignored_phase21_records'] == []
    assert manifest['declared']['approved_by'] == 'offline test'
    assert json.loads((args.output / 'plan.json').read_text())['phase21_guard']['blocking'] == []
    store = output_store(args)
    try:
        campaign = store.list_records('campaigns')[0]
        assert campaign['state'] == 'COMPLETED' and campaign['configuration_hash'] == probe.DECLARED_CONFIGURATION_HASH
        reservations = store.get_record('budgets', campaign['campaign_id'])['reservations']
        assert sorted(reservations) == ['final_audit', 'portability', 'selection_comparison']   # all released
        assert len(store.list_records(probe.CASE_RECORD)) == 2
    finally:
        store.close()
    result = json.loads((args.output / 'readout.json').read_text())
    assert result['world_scan']['world_files_missing'] == 0 and result['pairs'] == 6
    assert result['source_check']['by_setting']['D:d16']['status'] == 'NO'
    assert result['per_case']['A-c2-r1']['runner_status'] == 'RETURNED'
    assert manifest['readout']['source_check']['reading'] == 'not_assessed'      # D:d20 and D:d5 did not run
    assert (args.output / 'plan.json').is_file() and 'world files missing: 0' in (args.output / 'drift-check.txt').read_text()
    # The read-out reproduces from the store alone.
    assert probe.readout(args.output / 'lab.sqlite3', worlds_dir=offline.worlds) == result


def send(*signals):
    async def hook(n):
        if n == 2:
            for index, sig in enumerate(signals):
                if index:
                    await asyncio.sleep(0.05)
                os.kill(os.getpid(), sig)
            await asyncio.sleep(0.05)
    return hook


@frozen_only
@pytest.mark.anyio
@pytest.mark.parametrize('signals, hard', [((signal.SIGINT,), False), ((signal.SIGINT, signal.SIGINT), True),
                                           ((signal.SIGTERM,), True), ((signal.SIGHUP,), False)])
async def test_real_operator_signals_stop_at_the_declared_point(offline, signals, hard):
    if signal.SIGHUP in signals and signal.getsignal(signal.SIGHUP) is signal.SIG_IGN:
        pytest.skip('SIGHUP is ignored in this process (nohup); the runner rightly leaves it alone')
    args, plan, policies = offline.make(cases=('A-c2-r1', 'healthy'))
    offline.hooks['before'] = send(*signals)
    status = await offline.go(args, plan, policies)
    manifest = manifest_of(args)
    assert status == 1 and manifest['stop_reason'] == 'operator_stop' and len(manifest['cases']) == 1
    assert [s['signal'] for s in manifest['operator_signals']] == [signal.Signals(s).name for s in signals]
    store = output_store(args)
    try:
        found = Counter(t['lifecycle'] for t in store.list_records('trials'))
        assert store.list_records('campaigns')[0]['state'] == 'STOPPED'
    finally:
        store.close()
    if hard:        # stop now: the in-flight episode is kept as INTERRUPTED
        assert manifest['cases'][0]['pairs'] == 0 and found == {'COMPLETED': 1, 'INTERRUPTED': 1}
    else:           # stop at the next pair boundary: the in-flight pair finishes
        assert manifest['cases'][0]['pairs'] == 1 and found == {'COMPLETED': 2}
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler      # handlers were removed


@frozen_only
@pytest.mark.anyio
@pytest.mark.parametrize('change', ['edit', 'delete'])
async def test_a_protocol_change_or_a_missing_protocol_stops_at_the_next_pair_boundary(offline, change):
    args, plan, policies = offline.make(cases=('A-c2-r1', 'healthy'))

    def alter(n):
        if n == 3:
            if change == 'edit':
                with offline.protocol.open('a') as handle:
                    handle.write('edited mid-run\n')
            else:
                offline.protocol.unlink()
    offline.hooks['before'] = alter
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'protocol_changed' and len(manifest['cases']) == 1
    assert (manifest['cases'][0]['status'], manifest['cases'][0]['pairs'], manifest['cases'][0]['pair_stop']) == (
        'RETURNED', 2, 'protocol_changed')                       # never an EXCEPTION or infrastructure case
    assert manifest['cases'][0]['infrastructure_failure'] is False


@frozen_only
@pytest.mark.anyio
async def test_a_harness_change_mid_run_stops_at_the_next_pair_boundary(offline, monkeypatch):
    args, plan, policies = offline.make(cases=('A-c2-r1', 'healthy'))

    def switch(n):
        if n == 2:
            monkeypatch.setattr(probe, 'harness_sha256', lambda: 'f' * 64)
    offline.hooks['before'] = switch
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'harness_changed' and manifest['cases'][0]['pairs'] == 1


@frozen_only
@pytest.mark.anyio
async def test_a_freeze_change_mid_run_stops_before_the_next_case(offline, monkeypatch):
    args, plan, policies = offline.make(cases=('A-c2-r1', 'healthy'))
    altered = copy.deepcopy(offline.freezes['current'])
    altered['files']['backend/app/lab/runner.py'] = '0' * 64

    def drift_freeze(n):
        if n == 6:          # the first case's last episode: the next full check is before case 2
            offline.freezes['current'] = altered
    offline.hooks['before'] = drift_freeze
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'configuration_changed' and [c['case_id'] for c in manifest['cases']] == ['A-c2-r1']


@frozen_only
@pytest.mark.anyio
async def test_a_drift_checker_change_mid_run_is_a_harness_change(offline, monkeypatch):
    args, plan, policies = offline.make(cases=('A-c2-r1', 'healthy'))

    def switch(n):
        if n == 2:
            monkeypatch.setattr(probe, 'drift_checker_sha256', lambda: 'f' * 64)
    offline.hooks['before'] = switch
    assert await offline.go(args, plan, policies) == 1
    assert manifest_of(args)['stop_reason'] == 'harness_changed'


@frozen_only
@pytest.mark.anyio
async def test_a_completed_run_whose_drift_check_fails_exits_non_zero(offline, monkeypatch):
    args, plan, policies = offline.make()
    real = probe.run_drift_check
    elsewhere = offline.tmp / 'elsewhere'
    elsewhere.mkdir()
    # The worlds vanish between the run and the check (say, a cleanup): the check cannot pass.
    monkeypatch.setattr(probe, 'run_drift_check', lambda store, worlds, since: real(store, elsewhere, since))
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'completed' and not manifest['drift_check']['passed']
    assert manifest['drift_check']['world_files_missing'] == 6


@frozen_only
@pytest.mark.anyio
async def test_a_simulator_writing_elsewhere_is_still_caught_after_one_pair(offline):
    # The $0 check pins --worlds-dir to artifacts/worlds; the backstop catches a simulator that writes
    # somewhere else anyway (say, one started from another checkout). A case has started, so this run
    # is final (protocol section 8).
    elsewhere = offline.tmp / 'a-simulator-started-elsewhere'
    elsewhere.mkdir()
    offline.simulator['worlds'] = elsewhere
    args, plan, policies = offline.make(cases=('A-c2-r1', 'healthy'))
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'worlds_dir_mismatch' and manifest['cases'][0]['pairs'] == 1
    assert not manifest['drift_check']['passed'] and manifest['drift_check']['world_files_missing'] == 2
    assert manifest['drift_check']['exit_status'] == 2


@frozen_only
@pytest.mark.anyio
@pytest.mark.parametrize('refusal', ['port', 'entity', 'simulator', 'review', 'phase21', 'harness', 'drift_checker',
                                     'worlds', 'artifact_dir', 'ctrl_c', 'sigterm'])
async def test_every_preflight_refusal_happens_before_any_directory_or_episode(offline, monkeypatch, refusal):
    args, plan, policies = offline.make()
    if refusal == 'worlds':                           # an existing directory that is not artifacts/worlds
        args.worlds_dir = offline.artifacts / 'phase20-2026-09-24'
    elif refusal == 'artifact_dir':                   # the live settings would send the worlds elsewhere
        offline.simulator['artifact_dir'] = offline.tmp / 'elsewhere'
    elif refusal in ('ctrl_c', 'sigterm'):            # the handlers are installed before any directory exists
        offline.simulator['signal'] = signal.SIGINT if refusal == 'ctrl_c' else signal.SIGTERM
    elif refusal == 'port':
        offline.port['busy'] = True
    elif refusal == 'entity':
        args.confirm_entity = 'someone-else'
    elif refusal == 'simulator':
        offline.simulator['ready'] = False
    elif refusal == 'review':
        offline.review.write_text(json.dumps({**json.loads(offline.review.read_text()), 'protocol_sha256': '0' * 64}))
    elif refusal == 'phase21':
        live = offline.artifacts / 'phase21-2026-09-24' / 'live-1'
        live.mkdir(parents=True)
        (live / 'lapse-probe-manifest.json').write_text(json.dumps({'status': 'RUNNING', 'ended_at': None}))
    elif refusal == 'harness':
        monkeypatch.setattr(probe, 'harness_sha256', lambda: 'f' * 64)
    else:
        monkeypatch.setattr(probe, 'drift_checker_sha256', lambda: 'f' * 64)
    with pytest.raises(PlanningError):
        await offline.go(args, plan, policies)
    assert not args.output.exists() and offline.episodes['n'] == 0 and offline.consumed == []
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


@frozen_only
@pytest.mark.anyio
async def test_a_crashed_phase21_claim_named_by_the_operator_does_not_block_and_is_recorded(offline):
    claims = offline.artifacts / probe.PHASE21_CLAIM_DIR
    claims.mkdir()
    claim = claims / 'claim-01.json'
    claim.write_text(json.dumps({'claim': 'claim-01.json', 'pid': dead_pid(),
                                 'out': 'artifacts/phase21-2026-09-24/live-1'}))
    with pytest.raises(AssertionError):
        offline.make()                          # blocked without the override (make asserts no blocker)
    args, plan, policies = offline.make(ignore_phase21_record=[str(claim)])
    assert [e['record'] for e in plan['phase21_guard']['ignored_records']] == [str(claim.resolve())]
    assert await offline.go(args, plan, policies) == 0
    manifest = manifest_of(args)
    assert [e['record'] for e in manifest['ignored_phase21_records']] == [str(claim.resolve())]
    assert manifest['ignored_phase21_records'][0]['launching_pid'] == json.loads(claim.read_text())['pid']


@frozen_only
@pytest.mark.anyio
async def test_the_manifest_is_final_before_the_cleanup_and_a_signal_during_it_is_only_recorded(offline):
    # Round 2: a Ctrl-C during the resource closes used to kill the process with stop_reason
    # 'running' on disk. Now the manifest is final first and the handlers stay installed.
    args, plan, policies = offline.make()
    seen = {}

    async def close():
        if not seen:
            seen.update(manifest_of(args))
            os.kill(os.getpid(), signal.SIGINT)
            await asyncio.sleep(0.05)
    offline.hooks['close'] = close
    assert await offline.go(args, plan, policies) == 0
    assert seen['stop_reason'] == 'completed' and seen['ended_at']          # on disk before the cleanup
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'completed' and [s['signal'] for s in manifest['operator_signals']] == ['SIGINT']
    assert manifest['pid'] == os.getpid() and manifest['drift_check']['passed']


@frozen_only
@pytest.mark.anyio
async def test_a_zero_dollar_abort_after_the_directory_exists_is_recorded_and_a_new_directory_may_follow(offline,
                                                                                                          monkeypatch):
    args, plan, policies = offline.make()
    real = probe.planned_configuration

    def other_caps(settings):
        caps, frozen, configuration_hash = real(settings)
        return CampaignBudget(**{**caps.model_dump(), 'model_calls': caps.model_calls - 1}), frozen, configuration_hash
    monkeypatch.setattr(probe, 'planned_configuration', other_caps)
    assert await offline.go(args, plan, policies) == 1
    first = manifest_of(args)
    assert first['stop_reason'] == 'aborted' and 'declared configuration' in first['abort_detail']
    assert (first['cases'], first['charged_upper_bound'], offline.episodes['n']) == ([], 0.0, 0)
    monkeypatch.setattr(probe, 'planned_configuration', real)
    args2, plan2, policies2 = offline.make('run-2')
    assert await offline.go(args2, plan2, policies2) == 0
    second = manifest_of(args2)
    assert second['earlier_undelivered_runs'] == [str((args.output / probe.MANIFEST_NAME).resolve().relative_to(
        offline.artifacts.resolve().parent))]
    # After a run that delivered episodes, no further Phase 20 run can even be planned.
    with pytest.raises(PlanningError, match='Another Phase 20 run'):
        offline.make('run-3')


@frozen_only
@pytest.mark.anyio
async def test_a_closed_stdout_never_changes_the_stop_path(offline, monkeypatch):
    class Closed:
        def write(self, text):
            raise BrokenPipeError(32, 'Broken pipe')

        def flush(self):
            raise BrokenPipeError(32, 'Broken pipe')
    args, plan, policies = offline.make(cases=('A-c2-r1', 'healthy'))
    monkeypatch.setattr(sys, 'stdout', Closed())
    offline.hooks['before'] = send(signal.SIGINT)        # the Ctrl-C that killed the pipe's reader
    assert await offline.go(args, plan, policies) == 1
    manifest = manifest_of(args)
    assert manifest['stop_reason'] == 'operator_stop' and 'abort_detail' not in manifest
    assert manifest['cases'][0]['pairs'] == 1
