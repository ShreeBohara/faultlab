"""Offline checks of the Phase 28 upgrade-side fixed-N runner against a scripted fake backend.

No network, no provider, no real store: the reused Phase 17 HTTP helper is replaced by an in-memory fake
that also writes to a throwaway SQLite store with the real records/events schema, and every file pin is
pointed at synthetic files under tmp_path. Mirrors test_run_full_loop_fixed_n.py for the copied main loop
and adds what is new: the allowlist of reused names, the transposed certification rule and its integrity
check, the Phase 25/27 launch gates, the futility look and its persistence, the upgrade-side predicates on
real stored event shapes, and the manifest id in the POST body.
"""
import ast
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/experiments'))
SPEC = importlib.util.spec_from_file_location('run_upgrade_loop', ROOT / 'scripts/experiments/run_upgrade_loop.py')
loop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loop)
base = loop.base
fixed = loop.fixed
RUNNER = ROOT / 'scripts/experiments/run_upgrade_loop.py'
SHIPPED_PINS = {name: getattr(loop, name) for name in loop.PINS}   # before any monkeypatch
SHIPPED_FUNCTION_HASHES = json.loads(json.dumps(loop.DECLARED_FUNCTION_HASHES))

CONFIG = 'c' * 64
MANIFEST = 'ab' * 32
UPGRADE = 'upgrade-3'
CASES = ('healthy', 'upgrade-3', 'upgrade-2', 'delayed-upgrade', 'upgrade-18', 'lost-upgrade-response',
         'terminal-upgrade-rejection')
EXPECTED = {'upgrade-18': 'SAFE_UNRESOLVED', 'terminal-upgrade-rejection': 'CORRECTLY_REJECTED'}
MANIFEST_CASES = [{'case_id': c, 'expected_outcome': EXPECTED.get(c, 'COMPLETED'),
                   'fault_spec': {'primitives': [] if c == 'healthy' else [
                       {'kind': 'F4', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1}]}}
                  for c in CASES]
RESEND = {'rules': [{'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain',
                     'steps': [{'op': 'wait_ticks', 'ticks': 1},
                               {'op': 'retry_original_request', 'service': 'orders'}]}]}
PENDING_RESEND = {'rules': [{'hook': 'after_upgrade_response', 'when': 'current_operation_pending',
                             'steps': [{'op': 'retry_original_request', 'service': 'orders',
                                        'only_if': 'current_operation_pending'}]}]}
NO_RESEND = {'rules': [{'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain',
                        'steps': [{'op': 'wait_ticks', 'ticks': 1}, {'op': 'read_current_operation'}]}]}
NOTIFICATION_STEP = {'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
                     'steps': [{'op': 'retry_original_request', 'service': 'notifications'}]}
BOTH_SIDES = {'rules': RESEND['rules'] + [NOTIFICATION_STEP]}
FIRES = [{'type': 'policy_step', 'payload': {'executed': True, 'hook': 'after_upgrade_response',
                                             'op': 'retry_original_request'}},
         {'type': 'tool_dispatched', 'call_id': 'call-p', 'payload': {'caller': 'policy',
                                                                     'hook': 'after_upgrade_response',
                                                                     'tool': 'update_order'}}]
GATED = [{'type': 'policy_step', 'payload': {'executed': False, 'hook': 'after_upgrade_response',
                                             'op': 'retry_original_request'}}]


def counts(completed, expected='COMPLETED'):
    other = {'COMPLETED': 'safe_unresolved', 'SAFE_UNRESOLVED': 'safe_unresolved',
             'CORRECTLY_REJECTED': 'correctly_rejected'}[expected]
    row = {'attempted': 3, 'valid': 3, 'completed': completed, 'violations': 0, 'safe_unresolved': 0,
           'correctly_rejected': 0, 'lab_errors': 0, 'interrupted': 0, 'scheduled': 3, 'triggered': 3,
           'untriggered': 0}
    row[other] += 3 - completed
    return row


def by_case(l_completed, b0_completed=None):
    b0_completed = b0_completed or {}
    return {case: {'B0': counts(b0_completed.get(case, 0), EXPECTED.get(case, 'COMPLETED')),
                   'L': counts(l_completed.get(case, 0), EXPECTED.get(case, 'COMPLETED'))} for case in CASES}


def study(*, status='COMPLETED', decision='NO_CHANGE', stage='controls', candidates=(), l=None, b0=None,
          error_type=None, protocol=base.ACTOR_CONTEXT, manifest_id='upgrade-v1', manifest_hash=MANIFEST,
          rereads=(), evidence=2, selected=None, trial_rows=(), events=None, reason='r', va_reason=None,
          clause=None, control=None):
    record = {'status': status, 'decision': decision, 'reason': reason, 'stage': stage,
              'actor_context_protocol': protocol, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
              'replay_of': None, 'manifest_hash': manifest_hash,
              'manifest': {'cases': MANIFEST_CASES, 'source_case_id': UPGRADE, 'control_case_id': 'healthy'},
              'candidates': list(candidates), 'trial_rows': list(trial_rows), 'evidence_rereads': list(rereads),
              'evidence_count': evidence, 'selected_candidate_hash': selected,
              'control_assessment': control,
              'validation_assessment': None if l is None else {'decision': decision, 'reason': va_reason or reason,
                                                               'by_case': by_case(l, b0)}}
    if manifest_id is not None:
        record['case_manifest_id'] = manifest_id
    if clause:
        record['validation_assessment']['source_clause_case'] = clause
    if error_type:
        record['error_type'] = error_type
    if events:
        record['_events'] = events
    return record


def candidate(content, decision, source=None, policy_hash='h' * 64, source_b0=0):
    assessment = None
    if source:
        assessment = {'decision': source, 'by_case': {UPGRADE: {'B0': counts(source_b0), 'L': counts(3)}}}
    return {'decision': decision, 'policy_hash': policy_hash, 'content': content, 'source_assessment': assessment}


def certified_study(policy_hash, content=RESEND, **kwargs):
    return study(decision='OBSERVED_IMPROVEMENT', stage='validation', reason='Strict completion gain',
                 l={UPGRADE: 3, 'healthy': 3, 'upgrade-2': 3, 'delayed-upgrade': 3, 'lost-upgrade-response': 3},
                 b0={'healthy': 3, 'upgrade-2': 1, 'delayed-upgrade': 3, 'lost-upgrade-response': 3},
                 candidates=[candidate(content, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED', policy_hash)],
                 selected=policy_hash, **kwargs)


def trial(stage, arm, eid, *, case=UPGRADE, scheduled=True, triggered=True, lifecycle='COMPLETED',
          outcome='COMPLETED'):
    return {'stage': stage, 'case_id': case,
            'trial': {'episode_id': eid, 'arm': arm, 'lifecycle': lifecycle, 'outcome': outcome,
                      'fault_scheduled': scheduled, 'fault_triggered': triggered if scheduled else False,
                      'failed_checks': [], 'trial_index': 0, 'policy_hash': 'x', 'world_id': 'world-' + eid}}


def one_policy_study(index, content=NO_RESEND):
    """A controls-passing study whose one proposal is a distinct valid policy that fails the source gate."""
    return study(stage='candidate-1', candidates=[candidate(content, 'NO_CHANGE', 'NO_CHANGE', f'{index:064x}')])


OK = study()
DEAD = study(status='INCOMPLETE', decision='INCOMPLETE', error_type='WaitingEvidence')


# ----------------------------------------------------------------- what is reused, and nothing else

def _attribute_reads(module_name):
    tree = ast.parse(RUNNER.read_text(encoding='utf-8'))
    return {node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == module_name}


def test_the_runner_reads_only_the_declared_names_from_the_imported_runners():
    assert _attribute_reads('base') <= loop.REUSED_FROM_BASE, _attribute_reads('base') - loop.REUSED_FROM_BASE
    assert _attribute_reads('fixed') <= loop.REUSED_FROM_FIXED, _attribute_reads('fixed') - loop.REUSED_FROM_FIXED
    assert _attribute_reads('slot2_probe') <= loop.REUSED_FROM_SLOT2_PROBE
    # The declared lists are exactly PHASE28_DESIGN.md section 8.3's "Reused unchanged", all three of them (review
    # round 1: the base list was checked only against itself, so a new base read such as base.infrastructure_death,
    # which counts $0 runner-side refusals toward the breaker, would have passed once added to the list).
    assert loop.REUSED_FROM_BASE == {
        'api', 'wait_until_idle', 'record_charge', 'total_spend', 'campaign_spend', 'check_backend',
        'check_backend_process', 'backend_status', 'check_campaign_in_store', 'check_evidence_project', 'gate_freeze',
        'store_records', 'sha256_file', 'case_gains', 'contains_step', 'Detached', 'PhaseAbort', 'TERMINAL',
        'TASK_TEXT', 'ORDER_ID', 'EXPECTED_ACTOR', 'EXPECTED_MECHANIC', 'EXPECTED_PROJECT', 'ACTOR_CONTEXT',
        'EVIDENCE_PROTOCOL', 'ASSESS_PAIRS_KEY', 'ASSESS_PAIRS_TEXT_SHA256'}
    assert loop.REUSED_FROM_FIXED == {'wilson', 'valid_trial', 'episode_events', 'runner_side', 'infrastructure_death',
                                      'label_phantoms', 'ingestion_health', 'clock_drift', 'is_sha256',
                                      'BreakerTripped', 'retry_executed', 'step_fired'}
    assert 'infrastructure_death' not in _attribute_reads('base')
    assert loop.REUSED_FROM_SLOT2_PROBE == {'live_experiment_processes'}
    forbidden = {'attempt_funnel', 'add_funnel', 'summarize_fixed_n', 'hash_accounting', 'primary_statement', 'routing',
                 'check_static_pins', 'review_problem', 'pin_files', 'pin_status', 'unfilled_pins', 'reconcile',
                 'expected_certified', 'claim', 'certified', 'summarize_study', 'verify_study_identity',
                 'identity_problems', 'fresh_case_gain', 'SOURCE_CASE', 'CONTROL_CASE', 'MANIFEST_HASH', 'PROTOCOL',
                 'N_ATTEMPTS', 'FINAL_STOPS', 'PHASE_PREFIX', 'ROOT'}
    for name in ('base', 'fixed', 'slot2_probe'):
        reads = _attribute_reads(name)
        assert not reads & forbidden, (name, reads & forbidden)
        assert not {r for r in reads if r.startswith(('PHASE17_', 'DECLARED_', 'pin_'))}, name


def test_the_allowlist_scan_catches_a_forbidden_read(tmp_path, monkeypatch):
    """The scan above is not vacuous: a copy that reads fixed.attempt_funnel or base.MANIFEST_HASH fails it."""
    text = RUNNER.read_text(encoding='utf-8') + '\nx = fixed.attempt_funnel\ny = base.MANIFEST_HASH\n'
    copy = tmp_path / 'run_upgrade_loop.py'
    copy.write_text(text)
    monkeypatch.setattr(sys.modules[__name__], 'RUNNER', copy)
    assert 'attempt_funnel' in _attribute_reads('fixed') - loop.REUSED_FROM_FIXED
    assert 'MANIFEST_HASH' in _attribute_reads('base') - loop.REUSED_FROM_BASE


HARNESS_28A = ROOT / 'scripts/experiments/upgrade_mechanic_probe.py'
# The runner's copies of the Phase 28a file format, by the 28a harness's own names (review round 2, LN-5).
COPIED_28A = {'READOUT_SCHEMA': 'PHASE28A_READOUT_SCHEMA', 'MANIFEST_NAME': 'PHASE28A_MANIFEST',
              'PHASE_PREFIX': 'PHASE28A_PREFIX', 'FINAL_STATUSES': 'PHASE28A_FINAL_STATUSES', 'CLAIM_DIR': 'PHASE28A_CLAIM_DIR'}


def _constant(node):
    """A string or a tuple of strings written literally; anything else is None (nothing is evaluated)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple) and all(isinstance(e, ast.Constant) for e in node.elts):
        return tuple(e.value for e in node.elts)
    return None


def _module_constants(path, names):
    """Literal module-level assignments, read with ast (the 28a harness is never imported here)."""
    found = {}
    for node in ast.parse(pathlib.Path(path).read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    found[target.id] = _constant(node.value)
    return found


@pytest.mark.skipif(not HARNESS_28A.is_file(), reason='the Phase 28a harness exists only on the main checkout; a '
                                                       'worktree of 3cda105 predates it')
def test_the_copied_phase28a_constants_equal_the_28a_harness_and_every_landing_check():
    """Review round 2 (LN-5): the runner (and landing_check_p28.py) copy Phase 28a's file format by hand. A rename in the
    28a harness must fail here, not as a $0 refusal on landing day."""
    theirs = _module_constants(HARNESS_28A, set(COPIED_28A))
    assert theirs == {name: getattr(loop, ours) for name, ours in COPIED_28A.items()}
    source = HARNESS_28A.read_text(encoding='utf-8')
    tree = ast.parse(source)
    # Where it writes the read-outs: write_json(out / 'readouts.json', readouts).
    writes = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'write_json'
              and node.args and isinstance(node.args[0], ast.BinOp)
              and getattr(node.args[0].right, 'value', None) == loop.PHASE28A_READOUTS]
    assert writes, f'the 28a harness no longer writes {loop.PHASE28A_READOUTS}'
    # The read-outs carry the schema and a top-level decision (compute_readouts' returned dict).
    readout_dicts = [node for node in ast.walk(tree) if isinstance(node, ast.Dict) and any(
        getattr(k, 'value', None) == 'schema_version' and getattr(v, 'id', None) == 'READOUT_SCHEMA'
        for k, v in zip(node.keys, node.values))]
    assert readout_dicts and all('decision' in [getattr(k, 'value', None) for k in d.keys] for d in readout_dicts)
    # --readouts prints the plain read-outs only for the run's own harness and plan; otherwise it wraps them under
    # a 'label', which the runner's fallback refuses (review round 2, WB-5).
    assert f"'{loop.PHASE28A_MISMATCH_KEY}': NOT_THE_RUNS_HARNESS" in source
    # The landing check's copies, wherever a preserve (P0) or the landing (F0) put them on this checkout.
    names = {f'PHASE28A_{n}' for n in ('PREFIX', 'CLAIM_DIR', 'MANIFEST', 'READOUTS', 'READOUT_SCHEMA',
                                       'FINAL_STATUSES', 'RECHECK', 'MISMATCH_KEY')}
    for check in sorted(ROOT.glob('artifacts/phase28-*/prep/landing_check_p28.py')) + \
            sorted(ROOT.glob('artifacts/builds/phase28-*/prep/landing_check_p28.py')):
        copies = _module_constants(check, names)
        if 'PHASE28A_RECHECK' not in copies:
            continue                                     # a superseded round-1 copy, kept for the record only
        assert copies == {name: getattr(loop, name) for name in names}, check


def test_runner_side_strings_are_the_ones_the_fixed_n_rule_recognises():
    for name in ('NO_CONFIGURATION_HASH', 'CONFIGURATION_MISMATCH', 'STORE_OR_ARIA_REFUSED'):
        assert getattr(loop, name) == getattr(fixed, name)
        assert fixed.runner_side({'error': getattr(loop, name)})


def test_the_shipped_design_is_the_declared_one():
    assert (loop.N_ATTEMPTS, loop.SPEND_CAP, loop.HEADROOM, loop.BREAKER, loop.FUTILITY_LOOK_D) == (50, 150.0, 11.0, 5, 16)
    assert loop.FINAL_STOPS == ('futility', 'fixed_n', 'spend_guard') and 'certified' not in loop.FINAL_STOPS
    assert (loop.PHASE_PREFIX, loop.CASE_MANIFEST_ID, loop.SOURCE_CASE, loop.CONTROL_CASE, loop.FRESH_GAIN_MIN) == (
        'phase28-', 'upgrade-v1', 'upgrade-3', 'healthy', 2)
    assert (loop.PRIOR_ATTEMPTS, loop.PRIOR_CERTIFIED) == (39, 4) and len(set(loop.PRIOR_CERTIFIED_POLICIES)) == 4
    assert loop.routing([], final=True) is None
    assert base.ACTOR_CONTEXT == 'faultlab-actor-context/v4-indexed-evidence'
    # The unchanged gate the plan carries is the one this repository runs.
    from app.lab import completion_study
    source = pathlib.Path(completion_study.__file__).read_text(encoding='utf-8')
    found = {n.name: n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    for key, (text_sha, lines) in loop.UNCHANGED_FUNCTIONS.items():
        node = found[key.split('::')[1]]
        segment = ast.get_source_segment(source, node)
        assert hashlib.sha256((segment + '\n').encode()).hexdigest() == text_sha
        assert f'{node.lineno}-{node.end_lineno}' == lines
    assert loop.UNCHANGED_FUNCTIONS[base.ASSESS_PAIRS_KEY][0] == base.ASSESS_PAIRS_TEXT_SHA256


# ----------------------------------------------------------------- pins

def test_every_shipped_pin_is_a_placeholder_or_a_well_formed_hash():
    freeze_time = {'DECLARED_MANIFEST_HASH', 'DECLARED_FREEZE_SHA256', 'DECLARED_CONFIGURATION_HASH'}
    for name, value in SHIPPED_PINS.items():
        if name in freeze_time:
            assert value == loop.PLACEHOLDER or fixed.is_sha256(value), name
        else:
            assert fixed.is_sha256(value), name
    for entry in SHIPPED_FUNCTION_HASHES.values():
        assert all(v == loop.PLACEHOLDER or fixed.is_sha256(v) for v in entry.values())
    # The four definitions the design names and the three module constants they read (review round 1).
    assert set(SHIPPED_FUNCTION_HASHES) == {f'{loop.COMPLETION_STUDY}::{n}' for n in (
        'upgrade_case_manifest', 'CASE_MANIFESTS', 'DEFAULT_CASE_MANIFEST', 'build_case_manifest',
        'SOURCE_CLAUSE_OUTCOMES', 'SOURCE_CLAUSE_REOPENS', 'source_clause')}


def test_every_module_level_definition_the_phase28_code_added_is_pinned():
    """Every top-level name completion_study.py defines after _execute (all Phase 28 code is appended there) has a
    supplementary pin, so none is bound only by the whole-file sha (review round 1: SOURCE_CLAUSE_REOPENS decides
    whether source_clause acts at all)."""
    from app.lab import completion_study
    tree = ast.parse(pathlib.Path(completion_study.__file__).read_text(encoding='utf-8'))
    names, after = [], False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == '_execute':
            after = True
            continue
        if after:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
            else:
                names.extend(t.id for t in getattr(node, 'targets', []) if isinstance(t, ast.Name))
    assert tuple(names) == loop.NEW_DEFINITIONS
    assert set(loop.supplementary_hashes()) == {f'{loop.COMPLETION_STUDY}::{name}' for name in names}


def test_a_changed_clause_constant_moves_its_pin_and_leaves_the_function_pin_alone(tmp_path):
    """The case the round-1 reviewers built: dropping a reason from SOURCE_CLAUSE_REOPENS turns the clause into a
    pass-through on that path while source_clause's own text and AST hashes stay the same."""
    from app.lab import completion_study
    source = pathlib.Path(completion_study.__file__).read_text(encoding='utf-8')
    reason = "                         'Strict completion gain on fresh development cases; no policy activated')"
    assert source.count(reason) == 1
    mutant = tmp_path / 'completion_study.py'
    mutant.write_text(source.replace("'No strict completion gain in the fixed validation batch',\n" + reason,
                                     "'No strict completion gain in the fixed validation batch')"), encoding='utf-8')
    before, after = loop.supplementary_hashes(), loop.supplementary_hashes(mutant)
    key = f'{loop.COMPLETION_STUDY}::'
    assert after[key + 'source_clause'] == before[key + 'source_clause']
    assert after[key + 'SOURCE_CLAUSE_REOPENS'] != before[key + 'SOURCE_CLAUSE_REOPENS']


def test_the_pins_known_now_match_the_files_on_disk():
    here = ROOT / 'scripts/experiments'
    for name, path in (('DECLARED_BASE_RUNNER_SHA256', here / 'run_full_loop.py'),
                       ('DECLARED_FIXED_RUNNER_SHA256', here / 'run_full_loop_fixed_n.py'),
                       ('DECLARED_SLOT2_PROBE_SHA256', here / 'slot2_probe.py'),
                       ('DECLARED_GATE_FREEZE_SCRIPT_SHA256', here / 'gate_freeze.py'),
                       ('DECLARED_DRIFT_CHECKER_SHA256', here / 'check_clock_drift.py'),
                       ('DECLARED_INGESTION_CHECK_SHA256', here / 'check_ingestion_health.py'),
                       ('DECLARED_MECHANIC_BRIEF_SHA256', ROOT / loop.MECHANIC_BRIEF)):
        assert base.sha256_file(path) == SHIPPED_PINS[name], name
    for name, rel in (('DECLARED_SETTINGS_SHA256', loop.DEFAULT_SETTINGS), ('DECLARED_LAUNCHER_SHA256', loop.LAUNCHER)):
        if not (ROOT / rel).exists():
            continue                     # artifacts/ is not in a worktree; the main checkout checks these
        assert base.sha256_file(ROOT / rel) == SHIPPED_PINS[name], name


def test_filled_freeze_time_pins_match_the_code_on_disk():
    """After F6/F8 fill them, the manifest pin equals the backend builder and the function pins the code."""
    if SHIPPED_PINS['DECLARED_MANIFEST_HASH'] == loop.PLACEHOLDER:
        assert loop.builder_manifest_hash() == 'cafe5757b9dccf8f5f0f5ed0f34a6df657a3fb61198972cff23417ea3dac63d3'
    else:
        assert loop.builder_manifest_hash() == SHIPPED_PINS['DECLARED_MANIFEST_HASH']
    on_disk = loop.supplementary_hashes()
    assert all('missing' not in value for value in on_disk.values())
    for key, declared in SHIPPED_FUNCTION_HASHES.items():
        for field, value in declared.items():
            if value != loop.PLACEHOLDER:
                assert on_disk[key][field] == value, (key, field)


# ----------------------------------------------------------------- predicates

# Excerpts of stored events (type, call_id, payload without attempt ids), copied read-only on 2026-09-25
# from development stores. The store test below re-reads them when the stores are present.
STORED = {
    'p20-L-F4c2': ('artifacts/phase20-2026-09-23/run-1/lab.sqlite3', 'episode-010b1e1ee8fd4527b1bb7461be5dc038', [
        ('tool_dispatched', 'call-ee2a234079ca4810803bfd4500bf2304', {'caller': 'actor', 'hook': None, 'tool': 'get_order'}),
        ('tool_dispatched', 'call-a36e0e981326405897da83d9fcc3b6a1', {'caller': 'actor', 'hook': None, 'tool': 'update_order'}),
        ('tool_dispatched', 'call-a36e0e981326405897da83d9fcc3b6a1', {'caller': 'actor', 'hook': None, 'tool': 'update_order'}),
        ('policy_step', None, {'executed': True, 'hook': 'after_upgrade_response', 'op': 'read_current_operation'}),
        ('tool_dispatched', 'call-989ebc2a8cae4806942e5a2da123f581', {'caller': 'policy', 'hook': 'after_upgrade_response', 'tool': 'get_operation_status'}),
        ('policy_step', None, {'executed': True, 'hook': 'after_upgrade_response', 'op': 'wait_ticks'}),
        ('policy_step', None, {'executed': True, 'hook': 'after_upgrade_response', 'op': 'read_current_operation'}),
        ('tool_dispatched', 'call-93963339a293435ba76c7209ded8f815', {'caller': 'policy', 'hook': 'after_upgrade_response', 'tool': 'get_operation_status'}),
        ('policy_step', None, {'executed': True, 'hook': 'after_upgrade_response', 'op': 'require_receipt'}),
        ('tool_dispatched', 'call-6a91c7faa5f742608d38508138f13cb2', {'caller': 'actor', 'hook': None, 'tool': 'get_operation_status'}),
        ('tool_dispatched', 'call-d351e0885fca4257993a46d1ecc4faa2', {'caller': 'actor', 'hook': None, 'tool': 'get_operation_status'}),
        ('tool_dispatched', 'call-80c5ec626a3440f3a868e2b14568ef1d', {'caller': 'actor', 'hook': None, 'tool': 'get_operation_status'}),
        ('tool_dispatched', 'call-14ebddc569744507b6672253778670e7', {'caller': 'actor', 'hook': None, 'tool': 'get_operation_status'}),
        ('tool_dispatched', 'call-c77f919a69864a6997aeb66c0729ca2f', {'caller': 'actor', 'hook': None, 'tool': 'get_operation_status'})]),
    'p20-B0-F4c3': ('artifacts/phase20-2026-09-23/run-1/lab.sqlite3', 'episode-89580c1cbbe941708573c0e15c0313d0', [
        ('tool_dispatched', 'call-79b8cc7206594c81b3b188454d96c2b9', {'caller': 'actor', 'hook': None, 'tool': 'get_order'}),
        ('tool_dispatched', 'call-b4fdbd55ad0247629da15e7a8c18619f', {'caller': 'actor', 'hook': None, 'tool': 'update_order'}),
        ('tool_dispatched', 'call-b4fdbd55ad0247629da15e7a8c18619f', {'caller': 'actor', 'hook': None, 'tool': 'update_order'}),
        ('tool_dispatched', 'call-27ac68d2f5ca418eac1aaf861ab25e8a', {'caller': 'actor', 'hook': None, 'tool': 'update_order'}),
        ('tool_dispatched', 'call-27ac68d2f5ca418eac1aaf861ab25e8a', {'caller': 'actor', 'hook': None, 'tool': 'update_order'}),
        ('tool_dispatched', 'call-7cdf47e6f17f40479abb3729be5a729f', {'caller': 'actor', 'hook': None, 'tool': 'send_confirmation'})]),
    'p26-MR-F4': ('artifacts/phase26-2026-09-24/run-1/lab.sqlite3', 'episode-1448b7f12f7b4e949e41f58788ceffe6', [
        ('tool_dispatched', 'call-1ba3c6d7f5bb4d62b95e16c34bdaab56', {'caller': 'actor', 'hook': None, 'tool': 'get_order'}),
        ('tool_dispatched', 'call-b17bfd1ea90c466dbdad244382a66b67', {'caller': 'actor', 'hook': None, 'tool': 'update_order'}),
        ('tool_dispatched', 'call-b17bfd1ea90c466dbdad244382a66b67', {'caller': 'actor', 'hook': None, 'tool': 'update_order'}),
        ('policy_step', None, {'executed': True, 'hook': 'after_upgrade_response', 'op': 'wait_ticks'}),
        ('policy_step', None, {'executed': True, 'hook': 'after_upgrade_response', 'op': 'retry_original_request'}),
        ('tool_dispatched', 'call-09ebb0b35ec14e01ac688af8c2f2f84b', {'caller': 'policy', 'hook': 'after_upgrade_response', 'tool': 'update_order'}),
        ('policy_step', None, {'executed': False, 'hook': 'after_upgrade_response', 'op': 'wait_ticks'}),
        ('policy_step', None, {'executed': False, 'hook': 'after_upgrade_response', 'op': 'retry_original_request'}),
        ('tool_dispatched', 'call-4152858cf13a4cc7b13f9e8ae518bdd5', {'caller': 'actor', 'hook': None, 'tool': 'send_confirmation'})]),
}


def _events(key):
    return [{'type': t, 'call_id': c, 'payload': dict(p)} for t, c, p in STORED[key][2]]


def test_predicates_on_real_stored_event_shapes():
    # An L episode on F4: two tool_dispatched events for ONE logical Actor call (the adapter's two attempts).
    assert not loop.actor_resend_episode(_events('p20-L-F4c2'))
    assert loop.rules_ran(_events('p20-L-F4c2')) and not loop.upgrade_retry_fired(_events('p20-L-F4c2'))
    # A B0 episode where the Actor itself re-sent: two distinct calls.
    assert loop.actor_resend_episode(_events('p20-B0-F4c3')) and not loop.rules_ran(_events('p20-B0-F4c3'))
    # The Phase 26 manual-reference policy's re-send reached the broker.
    assert loop.upgrade_retry_fired(_events('p26-MR-F4')) and not loop.actor_resend_episode(_events('p26-MR-F4'))
    # Counting events instead of calls would call every F4 episode a re-send (R1-7).
    events = [e for e in _events('p20-L-F4c2') if e['type'] == 'tool_dispatched' and e['payload']['tool'] == 'update_order']
    assert len(events) == 2 and len({e['call_id'] for e in events}) == 1


@pytest.mark.parametrize('key', sorted(STORED))
def test_the_excerpts_equal_the_stored_events(key):
    path, episode_id, _ = STORED[key]
    store = ROOT / path
    if not store.exists():
        pytest.skip('the development store is not present (worktree or fresh clone)')
    connection = sqlite3.connect(store.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        rows = [json.loads(p) for (p,) in connection.execute(
            'select payload from events where episode_id=? order by seq', (episode_id,))]
    finally:
        connection.close()
    stored = [{'type': e['type'], 'call_id': e.get('call_id'),
               'payload': {k: v for k, v in e['payload'].items() if k != 'attempt_id'}}
              for e in rows if e['type'] in ('tool_dispatched', 'policy_step')]
    assert stored == _events(key)


def test_upgrade_retry_steps_describe_hook_gates_and_whether_the_step_can_fire():
    assert loop.upgrade_retry_steps(RESEND) == [{'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain',
                                                 'only_if': None, 'label': 'can fire'}]
    assert loop.upgrade_retry_steps(PENDING_RESEND)[0]['label'] == 'cannot fire after a transient failure'
    odd = {'rules': [{'hook': 'before_final_report', 'when': 'notification_outcome_uncertain',
                      'steps': [{'op': 'retry_original_request', 'service': 'orders'},
                                {'op': 'retry_original_request', 'service': 'orders', 'only_if': 'always'}]}]}
    assert [s['label'] for s in loop.upgrade_retry_steps(odd)] == ['unclear', 'unclear']
    assert not loop.contains_upgrade_retry(NO_RESEND) and not loop.contains_upgrade_retry({'rules': [NOTIFICATION_STEP]})
    assert loop.contains_upgrade_retry(BOTH_SIDES) and base.contains_step(BOTH_SIDES)
    assert not loop.contains_upgrade_retry(None) and loop.upgrade_retry_steps({}) == []


# ----------------------------------------------------------------- certification (truth table)

def test_the_certification_truth_table(monkeypatch):
    monkeypatch.setattr(loop, 'DECLARED_MANIFEST_HASH', MANIFEST)
    good = certified_study('b' * 64)
    assert loop.certified(good) and loop.integrity_problem(good) is None
    # a gain of 2 on upgrade-2 with the source 3 of 3 is certified (above); a gain only on healthy is not fresh
    only_healthy = study(decision='OBSERVED_IMPROVEMENT', stage='validation', l={UPGRADE: 3, 'healthy': 3},
                         b0={'healthy': 1})
    assert not loop.fresh_case_gain(only_healthy['validation_assessment']) and not loop.certified(only_healthy)
    # a gain of 1 on two cases is never summed
    two_ones = study(decision='OBSERVED_IMPROVEMENT', stage='validation',
                     l={UPGRADE: 3, 'healthy': 3, 'upgrade-2': 1, 'delayed-upgrade': 3},
                     b0={'healthy': 3, 'delayed-upgrade': 2})
    assert not loop.certified(two_ones)
    # a stored OBSERVED_IMPROVEMENT with the source 2 of 3 is an integrity failure, never a certification
    leaky = study(decision='OBSERVED_IMPROVEMENT', stage='validation', l={UPGRADE: 2, 'healthy': 3, 'upgrade-2': 3},
                  b0={'healthy': 3})
    assert not loop.certified(leaky) and 'integrity failure' in loop.integrity_problem(leaky)
    # a transposed-clause NO_CHANGE is not certified and is no integrity failure
    clause = study(decision='NO_CHANGE', stage='validation', l={UPGRADE: 2, 'healthy': 3, 'upgrade-2': 3},
                   b0={'healthy': 3}, clause=UPGRADE, reason=loop.CLAUSE_REASON)
    assert not loop.certified(clause) and loop.integrity_problem(clause) is None
    # identity: a wrong manifest hash, a missing or wrong manifest id, a replay, another Actor context
    for changed in (dict(manifest_hash='n' * 64), dict(manifest_id=None), dict(manifest_id='notification-v1'),
                    dict(protocol='faultlab-actor-context/v1')):
        row = certified_study('b' * 64, **changed)
        assert not loop.certified(row) and loop.identity_problems(row)
    replay = {**good, 'replay_of': 'policy-x'}
    assert not loop.certified(replay)


# ----------------------------------------------------------------- the futility look (pure)

def _rows(*studies_):
    return [{'attempt': i + 1, **loop.summarize_study(s)} for i, s in enumerate(studies_)]


def test_the_look_fires_only_at_the_first_d16_only_on_r0_k0_and_never_twice():
    rows = _rows(*[one_policy_study(i) for i in range(15)])
    assert loop.futility_look(rows, None) is None                                   # D = 15
    rows = _rows(*[one_policy_study(i) for i in range(16)])
    look = loop.futility_look(rows, None)
    assert (look['attempt'], look['D'], look['R'], look['k'], look['outcome']) == (16, 16, 0, 0, 'stop')
    assert loop.futility_look(rows + _rows(one_policy_study(99)), look) is None    # never twice
    # A present but badly gated re-send keeps the run going (present, not working).
    with_step = _rows(*[one_policy_study(i) for i in range(15)], one_policy_study(15, PENDING_RESEND))
    assert loop.futility_look(with_step, None)['outcome'] == 'passed'
    # A certification keeps it going too.
    with_k = [*_rows(*[one_policy_study(i) for i in range(15)]), {'attempt': 16, 'certified': True, 'candidates': [
        {'policy_hash': 'f' * 64, 'contains_upgrade_retry': False}]}]
    assert loop.futility_look(with_k, None)['outcome'] == 'passed'


def test_d_excludes_duplicates_refusals_and_invalid_outputs():
    refusal = {'decision': 'NO_CHANGE', 'policy_hash': None, 'content': None, 'source_assessment': None}
    invalid = {'decision': 'REJECTED', 'policy_hash': None, 'content': None, 'source_assessment': None}
    duplicate = study(stage='candidate-1', candidates=[candidate(NO_RESEND, 'NO_CHANGE', 'NO_CHANGE', 'a' * 64),
                                                       candidate(NO_RESEND, 'DUPLICATE', None, 'a' * 64)])
    redrawn = study(stage='candidate-1', candidates=[candidate(NO_RESEND, 'NO_CHANGE', 'NO_CHANGE', 'a' * 64)])
    rows = _rows(duplicate, redrawn, study(candidates=[refusal]), study(candidates=[invalid, refusal]))
    assert loop.distinct_valid_policies(rows) == {'a' * 64: False}


# ----------------------------------------------------------------- the launch gates

PLAN_KEYS = ('schema_version', 'phase', 'design', 'rules', 'models', 'protocols', 'project', 'gate', 'pins', 'prior')


def test_the_plan_holds_no_protocol_runner_or_review_sha_and_moves_with_every_constant_and_pin(monkeypatch, tmp_path):
    plan = loop.plan()
    assert tuple(plan) == PLAN_KEYS
    text = json.dumps(plan)
    assert base.sha256_file(RUNNER) not in text
    before = loop.plan_hash()
    # The protocol is never read: editing it cannot move the plan.
    monkeypatch.setattr(loop, 'ROOT', tmp_path)
    (tmp_path / 'docs/part2').mkdir(parents=True)
    (tmp_path / loop.PROTOCOL).write_text('one text')
    assert loop.plan_hash() == before
    (tmp_path / loop.PROTOCOL).write_text('another text')
    assert loop.plan_hash() == before
    for name, value in (('N_ATTEMPTS', 40), ('SPEND_CAP', 130.0), ('FUTILITY_LOOK_D', 12), ('HEADROOM', 12.0),
                        ('BREAKER', 4), ('FRESH_GAIN_MIN', 1), ('SOURCE_CASE', 'upgrade-2'),
                        ('CASE_MANIFEST_ID', 'upgrade-v2'), ('FINAL_STOPS', ('fixed_n',)), ('SCOPE_SENTENCE', 'x'),
                        ('DECLARED_MANIFEST_HASH', 'e' * 64), ('DECLARED_CONFIGURATION_HASH', 'e' * 64),
                        ('DECLARED_FREEZE_SHA256', 'e' * 64), ('DECLARED_LAUNCHER_SHA256', 'e' * 64),
                        ('FUTILITY_RULE', 'another look'), ('CERTIFICATION_RULE', 'another rule')):
        with monkeypatch.context() as m:
            m.setattr(loop, name, value)
            assert loop.plan_hash() != before, name
    with monkeypatch.context() as m:
        changed = json.loads(json.dumps(loop.DECLARED_FUNCTION_HASHES))
        changed[next(iter(changed))]['text_sha256'] = 'e' * 64
        m.setattr(loop, 'DECLARED_FUNCTION_HASHES', changed)
        assert loop.plan_hash() != before
    assert loop.plan_hash() == before


class Launch:
    """Synthetic, fully pinned launch inputs under tmp_path: a protocol with the bare launch line, a review
    record, a freeze, the settings, launcher and brief files, and a copy of completion_study.py."""

    def __init__(self, tmp_path, monkeypatch):
        self.tmp, self.monkeypatch = tmp_path, monkeypatch
        monkeypatch.setattr(loop, 'ROOT', tmp_path)
        self.brief = self.put(loop.MECHANIC_BRIEF, 'the completion brief')
        self.settings = self.put('settings.json', '{}')
        self.launcher = self.put(loop.LAUNCHER, 'launcher')
        study_source = tmp_path / loop.COMPLETION_STUDY
        study_source.parent.mkdir(parents=True, exist_ok=True)
        from app.lab import completion_study
        shutil.copyfile(completion_study.__file__, study_source)
        self.freeze_data = {'schema_version': 'faultlab-gate-freeze/v1',
                            'files': {loop.MECHANIC_BRIEF: base.sha256_file(self.brief)},
                            'fingerprints': {'scorer_hash': loop.SCORER_HASH},
                            'functions': {key: {'text_sha256': text, 'lines': lines, 'ast_sha256': 'a' * 64}
                                          for key, (text, lines) in loop.UNCHANGED_FUNCTIONS.items()}}
        self.freeze = self.put('freeze.json', json.dumps(self.freeze_data))
        for name, value in {'DECLARED_MANIFEST_HASH': MANIFEST, 'DECLARED_CONFIGURATION_HASH': CONFIG,
                            'DECLARED_FREEZE_SHA256': base.sha256_file(self.freeze),
                            'DECLARED_SETTINGS_SHA256': base.sha256_file(self.settings),
                            'DECLARED_MECHANIC_BRIEF_SHA256': base.sha256_file(self.brief),
                            'DECLARED_LAUNCHER_SHA256': base.sha256_file(self.launcher),
                            'DECLARED_FUNCTION_HASHES': loop.supplementary_hashes(study_source)}.items():
            monkeypatch.setattr(loop, name, value)
        self.protocol = tmp_path / loop.PROTOCOL
        self.review = tmp_path / 'artifacts/phase28-test-review.json'
        # A final Phase 28a run whose read-outs say GO, as upgrade_mechanic_probe.py writes it.
        self.phase28a_dir = 'artifacts/phase28a-test/live'
        self.phase28a_run(status='COMPLETED', decision='GO')
        self.written_for = None
        self.prepare()

    def phase28a_run(self, *, status, decision, ended_at='2026-09-26T00:00:00+00:00'):
        directory = self.tmp / self.phase28a_dir
        directory.mkdir(parents=True, exist_ok=True)
        (directory / loop.PHASE28A_MANIFEST).write_text(json.dumps({'status': status, 'ended_at': ended_at}))
        (directory / loop.PHASE28A_READOUTS).write_text(json.dumps(
            {'schema_version': loop.PHASE28A_READOUT_SCHEMA, 'decision': decision, 'statement': 'synthetic'}))
        return base.sha256_file(directory / loop.PHASE28A_READOUTS)

    def put(self, rel, text):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def prepare(self, *, line=None, protocol_status='**Status: reviewed; approved for launch.**', force=False, **review):
        """(Re)write the protocol and review record for the CURRENT plan, only when it changed, so a resume
        sees the same protocol sha unless a test changes it on purpose."""
        value, harness = loop.plan_hash(), base.sha256_file(RUNNER)
        key = (value, line, protocol_status, tuple(sorted(review.items())))
        if self.written_for == key and not force:
            return
        self.written_for = key
        bare = loop.REVIEWED_LINE.format(harness=harness, plan=value)
        readouts = self.tmp / self.phase28a_dir / loop.PHASE28A_READOUTS
        self.protocol.parent.mkdir(parents=True, exist_ok=True)
        self.protocol.write_text(f'# Phase 28 protocol\n\n{protocol_status}\n\n{line if line is not None else bare}\n\n'
                                 '## 1. The question\n\ntext\n')
        record = {'status': 'approved', 'approved_by': 'test approver',
                  'protocol_sha256': base.sha256_file(self.protocol), 'harness_sha256': harness, 'plan_hash': value,
                  'gate_freeze_file_sha256': loop.DECLARED_FREEZE_SHA256,
                  'configuration_hash': loop.DECLARED_CONFIGURATION_HASH, 'manifest_hash': loop.DECLARED_MANIFEST_HASH,
                  'phase28a': {'run_dir': self.phase28a_dir, 'decision': 'GO',
                               'readouts_sha256': base.sha256_file(readouts) if readouts.exists() else None}}
        record.update(review)
        self.review.parent.mkdir(parents=True, exist_ok=True)
        self.review.write_text(json.dumps({k: v for k, v in record.items() if v is not None}))

    def args(self, **changes):
        values = {'settings': str(self.settings), 'expect_freeze': str(self.freeze), 'review_record': str(self.review),
                  'expect_plan_hash': loop.plan_hash(), 'expect_harness_sha256': base.sha256_file(RUNNER),
                  'expect_protocol_sha256': base.sha256_file(self.protocol), 'confirm_entity': 'entity'}
        values.update(changes)
        return SimpleNamespace(**values)

    def argv(self, **changes):
        args = self.args(**changes)
        flags = []
        for key, value in vars(args).items():
            if value is not None:
                flags += ['--' + key.replace('_', '-'), value]
        return flags


@pytest.fixture
def launch(tmp_path, monkeypatch):
    return Launch(tmp_path, monkeypatch)


def test_a_reviewed_launch_passes_the_static_gates(launch):
    expected, protocol_sha, harness, value = loop.check_launch(launch.args())
    assert expected == launch.freeze_data and harness == base.sha256_file(RUNNER) and value == loop.plan_hash()
    assert protocol_sha == base.sha256_file(launch.protocol)


def test_editing_the_protocol_after_the_launch_line_refuses(launch):
    args = launch.args()
    launch.protocol.write_text(launch.protocol.read_text() + '\nA late edit.\n')
    with pytest.raises(SystemExit, match='expect-protocol-sha256'):
        loop.check_launch(args)


@pytest.mark.parametrize('change,match', [
    ({'expect_harness_sha256': '0' * 64}, 'expect-harness-sha256'),
    ({'expect_plan_hash': '0' * 64}, 'expect-plan-hash'),
    ({'expect_protocol_sha256': '0' * 64}, 'expect-protocol-sha256'),
    ({'review_record': None}, 'review-record'),
    ({'expect_plan_hash': None}, 'expect-plan-hash'),
    ({'confirm_entity': None}, 'confirm-entity'),
])
def test_a_mismatched_or_missing_launch_value_refuses(launch, change, match):
    with pytest.raises(SystemExit, match=match):
        loop.check_launch(launch.args(**change))


@pytest.mark.parametrize('change,match', [
    ({'status': 'draft'}, "status 'approved'"),
    ({'approved_by': ' '}, 'approved_by'),
    ({'harness_sha256': '0' * 64}, 'harness_sha256'),
    ({'plan_hash': '0' * 64}, 'plan_hash'),
    ({'protocol_sha256': None}, 'protocol_sha256'),
    ({'gate_freeze_file_sha256': '0' * 64}, 'gate_freeze_file_sha256'),
    ({'configuration_hash': 'e' * 64}, 'configuration_hash'),
    ({'manifest_hash': 'e' * 64}, 'manifest_hash'),
])
def test_the_review_record_must_repeat_every_launch_value(launch, change, match):
    launch.prepare(**change)
    with pytest.raises(SystemExit, match=match):
        loop.check_launch(launch.args())


@pytest.mark.parametrize('phase28a,match', [
    (None, 'does not name the Phase 28a run'),
    ('artifacts/phase28a-test/live', 'does not name the Phase 28a run'),
    ({'run_dir': 'artifacts/phase28a-test/live', 'decision': 'NO_GO'}, 'decision is not GO'),
    ({'run_dir': 'artifacts/phase27-test/live', 'decision': 'GO'}, 'not a run directory'),
    ({'run_dir': 'artifacts/phase28a-test', 'decision': 'GO'}, 'not a run directory'),
    ({'run_dir': 'artifacts/phase28a-live-claims/live', 'decision': 'GO'}, 'not a run directory'),
    ({'run_dir': '/artifacts/phase28a-test/live', 'decision': 'GO'}, 'not a run directory'),
    ({'run_dir': 'artifacts/phase28a-test/..', 'decision': 'GO'}, 'not a run directory'),
    ({'run_dir': 'artifacts/phase28a-test/other', 'decision': 'GO'}, 'no readable run manifest'),
    ({'run_dir': 'artifacts/phase28a-test/live', 'decision': 'GO', 'readouts_sha256': '0' * 64}, 'readouts_sha256'),
])
def test_the_review_record_must_name_a_final_phase28a_run_that_said_go(launch, phase28a, match):
    """Design sections 9 and 18: Phase 28 lands and runs only after a Phase 28a GO (review round 1)."""
    launch.prepare(phase28a=phase28a)
    with pytest.raises(SystemExit, match=match):
        loop.check_launch(launch.args())


@pytest.mark.parametrize('status,decision,ended_at,match', [
    ('RUNNING', 'GO', '2026-09-26T00:00:00+00:00', 'has not ended'),
    ('COMPLETED', 'GO', None, 'has not ended'),
    ('COMPLETED', 'NO_GO', '2026-09-26T00:00:00+00:00', 'do not say GO'),
    ('COMPLETED', 'INCOMPLETE', '2026-09-26T00:00:00+00:00', 'do not say GO'),
])
def test_a_phase28a_run_that_did_not_end_on_go_refuses(launch, status, decision, ended_at, match):
    readouts_sha = launch.phase28a_run(status=status, decision=decision, ended_at=ended_at)
    launch.prepare(phase28a={'run_dir': launch.phase28a_dir, 'decision': 'GO', 'readouts_sha256': readouts_sha})
    with pytest.raises(SystemExit, match=match):
        loop.check_launch(launch.args())


def test_a_final_phase28a_go_passes_whatever_way_the_run_ended(launch):
    for status in loop.PHASE28A_FINAL_STATUSES:
        readouts_sha = launch.phase28a_run(status=status, decision='GO')
        launch.prepare(phase28a={'run_dir': launch.phase28a_dir, 'decision': 'GO', 'readouts_sha256': readouts_sha})
        loop.check_launch(launch.args())


def _phase28a_without_readouts(launch, recheck=None):
    """A final 28a GO run that wrote no readouts.json (its read-outs raised, or --finalize-abandoned closed it), and,
    if given, the operator's saved --readouts recomputation beside it. Returns the recheck's path and sha256."""
    launch.phase28a_run(status='ABORTED', decision='GO')
    (launch.tmp / launch.phase28a_dir / loop.PHASE28A_READOUTS).unlink()
    path = f'artifacts/phase28a-test/{loop.PHASE28A_RECHECK}'
    if recheck is None:
        return path, None
    launch.put(path, json.dumps(recheck, indent=2))
    return path, base.sha256_file(launch.tmp / path)


GO_READOUTS = {'schema_version': loop.PHASE28A_READOUT_SCHEMA, 'decision': 'GO', 'statement': 'synthetic'}


def test_a_28a_run_without_its_readouts_passes_only_with_the_declared_recomputation(launch):
    """Review round 2 (WB-5): a final 28a GO run whose read-outs raised, or that was closed with --finalize-abandoned,
    has no readouts.json. The declared fallback is the harness's own --readouts output saved beside the run as
    readouts-recheck.json, named by readouts_path and bound by its sha256."""
    path, sha = _phase28a_without_readouts(launch, GO_READOUTS)
    launch.prepare(phase28a={'run_dir': launch.phase28a_dir, 'decision': 'GO', 'readouts_sha256': sha,
                             'readouts_path': path})
    loop.check_launch(launch.args())
    # Without readouts_path the run's own (missing) file is meant: refused.
    launch.prepare(phase28a={'run_dir': launch.phase28a_dir, 'decision': 'GO', 'readouts_sha256': sha})
    with pytest.raises(SystemExit, match='readouts.json are missing or not JSON'):
        loop.check_launch(launch.args())


@pytest.mark.parametrize('recheck,path,match', [
    ({'label': "NOT THE RUN'S HARNESS OR PLAN: a recomputation, not the declared read-out", 'harness_matches_run': False,
      'plan_matches_run': True, 'readouts': GO_READOUTS}, None, 'recomputation labelled'),
    ({**GO_READOUTS, 'decision': 'NO_GO'}, None, 'do not say GO'),
    (GO_READOUTS, 'artifacts/phase28a-test/elsewhere.json', 'names neither'),
    (GO_READOUTS, 'artifacts/phase28a-other/readouts-recheck.json', 'names neither'),
    (GO_READOUTS, 'artifacts/phase28a-test/live/../readouts-recheck.json', 'names neither'),
])
def test_the_recomputation_fallback_refuses_a_label_a_no_go_and_any_other_path(launch, recheck, path, match):
    declared, sha = _phase28a_without_readouts(launch, recheck)
    launch.prepare(phase28a={'run_dir': launch.phase28a_dir, 'decision': 'GO', 'readouts_sha256': sha,
                             'readouts_path': path or declared})
    with pytest.raises(SystemExit, match=match):
        loop.check_launch(launch.args())


def test_the_recomputation_is_refused_when_the_run_wrote_its_own_readouts_and_its_sha_binds_it(launch):
    path = f'artifacts/phase28a-test/{loop.PHASE28A_RECHECK}'
    launch.put(path, json.dumps(GO_READOUTS))
    launch.prepare(phase28a={'run_dir': launch.phase28a_dir, 'decision': 'GO', 'readouts_path': path,
                             'readouts_sha256': base.sha256_file(launch.tmp / path)})
    with pytest.raises(SystemExit, match='wrote its own readouts.json'):
        loop.check_launch(launch.args())
    path, sha = _phase28a_without_readouts(launch, GO_READOUTS)
    launch.prepare(phase28a={'run_dir': launch.phase28a_dir, 'decision': 'GO', 'readouts_path': path,
                             'readouts_sha256': '0' * 64})
    with pytest.raises(SystemExit, match=r'readouts_sha256 is not the sha256 of artifacts/phase28a-test/readouts-recheck'):
        loop.check_launch(launch.args())


@pytest.mark.parametrize('line', ['', '`Reviewed for launch: harness {h} plan {p}`', '- Reviewed for launch: harness {h} plan {p}',
                                  '**Reviewed for launch: harness {h} plan {p}**', 'Reviewed for launch: harness {h} plan 0'])
def test_the_launch_line_must_be_bare_and_exact(launch, line):
    launch.prepare(line=line.format(h=base.sha256_file(RUNNER), p=loop.plan_hash()))
    with pytest.raises(SystemExit, match='bare "Reviewed for launch" line'):
        loop.check_launch(launch.args())


@pytest.mark.parametrize('status', ['**Status: declared before any paid call; NOT yet reviewed.**',
                                    'status: not yet reviewed'])
def test_a_protocol_still_marked_not_reviewed_refuses(launch, status):
    launch.prepare(protocol_status=status)
    with pytest.raises(SystemExit, match='NOT yet reviewed'):
        loop.check_launch(launch.args())


@pytest.mark.parametrize('pin', ['DECLARED_MANIFEST_HASH', 'DECLARED_FREEZE_SHA256', 'DECLARED_CONFIGURATION_HASH'])
def test_a_placeholder_pin_refuses_a_live_run(launch, monkeypatch, pin):
    monkeypatch.setattr(loop, pin, loop.PLACEHOLDER)
    with pytest.raises(SystemExit, match=f'FILL-AT-FREEZE.*{pin}'):
        loop.check_launch(launch.args())


def test_an_unfilled_function_hash_refuses_and_a_moved_definition_refuses(launch, monkeypatch):
    changed = json.loads(json.dumps(loop.DECLARED_FUNCTION_HASHES))
    key = f'{loop.COMPLETION_STUDY}::source_clause'
    changed[key]['ast_sha256'] = loop.PLACEHOLDER
    with monkeypatch.context() as m:
        m.setattr(loop, 'DECLARED_FUNCTION_HASHES', changed)
        with pytest.raises(SystemExit, match='source_clause'):
            loop.check_launch(launch.args())
    source = launch.tmp / loop.COMPLETION_STUDY
    source.write_text(source.read_text().replace("'source_clause_case': source}", "'source_clause_case': source, 'x': 1}"))
    with pytest.raises(SystemExit, match='differ from their pinned hashes'):
        loop.check_launch(launch.args())


@pytest.mark.parametrize('name', ['DECLARED_SETTINGS_SHA256', 'DECLARED_MECHANIC_BRIEF_SHA256', 'DECLARED_LAUNCHER_SHA256',
                                  'DECLARED_BASE_RUNNER_SHA256', 'DECLARED_FIXED_RUNNER_SHA256',
                                  'DECLARED_SLOT2_PROBE_SHA256', 'DECLARED_GATE_FREEZE_SCRIPT_SHA256',
                                  'DECLARED_DRIFT_CHECKER_SHA256', 'DECLARED_INGESTION_CHECK_SHA256'])
def test_every_file_pin_is_checked(launch, monkeypatch, name):
    monkeypatch.setattr(loop, name, 'e' * 64)
    launch.prepare()
    with pytest.raises(SystemExit, match=name):
        loop.check_launch(launch.args())


@pytest.mark.parametrize('section,key,value,match', [
    ('files', loop.MECHANIC_BRIEF, '0' * 64, 'Mechanic brief'),
    ('fingerprints', 'scorer_hash', '0' * 64, 'scorer_hash'),
    ('functions', base.ASSESS_PAIRS_KEY, {'text_sha256': '0' * 64}, 'unchanged assess_pairs'),
    ('functions', f'{loop.COMPLETION_STUDY}::planned_slots', {'text_sha256': '495f60fc5110326c13fcded6431d47f19c1d4117ecb4b6e3cc14f76a20dae64d',
                                                              'lines': '86-104'}, 'planned_slots unchanged'),
])
def test_a_freeze_without_the_unchanged_gate_scorer_or_brief_is_refused(launch, monkeypatch, section, key, value, match):
    data = json.loads(json.dumps(launch.freeze_data))
    data[section][key] = value
    launch.freeze.write_text(json.dumps(data))
    monkeypatch.setattr(loop, 'DECLARED_FREEZE_SHA256', base.sha256_file(launch.freeze))
    launch.prepare()
    with pytest.raises(SystemExit, match=match):
        loop.check_launch(launch.args())


# ----------------------------------------------------------------- fake backend and store

NO_LEDGER = {'usage_metadata_known': True, 'measured_input_tokens': 0, 'measured_output_tokens': 0,
             'reservations': {}}


def make_store(path):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,'
                'immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id))')
    con.execute('CREATE TABLE events(episode_id TEXT NOT NULL,seq INTEGER NOT NULL,payload TEXT NOT NULL,'
                'PRIMARY KEY(episode_id,seq))')
    con.commit(); con.close()


class FakeBackend:
    """Modelled on the real routes' fallback bodies (pitfall 76): /budget of a ledger-less campaign has no
    bound, the status route reports the active campaign, a study list is [] until one exists."""

    def __init__(self, store, outcomes, *, spend=2.0, config_hash=CONFIG, aria=False, project=base.EXPECTED_PROJECT,
                 start_fails=(), adopt=False):
        self.store, self.outcomes, self.spend = store, list(outcomes), spend
        self.config_hash, self.aria, self.project = config_hash, aria, project
        self.start_fails, self.adopt = set(start_fails), adopt
        self.campaigns, self.ledgers, self.studies, self.stops, self.started, self.bodies = [], {}, {}, [], [], []
        self.active = None
        self.actor = base.EXPECTED_ACTOR
        self.clock = 0
        self.on_poll = None

    def put(self, kind, id, payload):
        con = sqlite3.connect(self.store)
        con.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?) '
                    'ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload', (kind, id, json.dumps(payload)))
        con.commit(); con.close()

    def put_events(self, episode_id, events):
        con = sqlite3.connect(self.store)
        con.executemany('INSERT INTO events(episode_id,seq,payload) VALUES(?,?,?)',
                        [(episode_id, i, json.dumps(e)) for i, e in enumerate(events)])
        con.commit(); con.close()

    def __call__(self, base_url, method, path, body=None, timeout=30):
        if path == '/api/config/status':
            return {'live_enabled': True, 'active_campaign_id': self.active,
                    'models': {'actor': self.actor, 'mechanic': base.EXPECTED_MECHANIC}}
        if path == '/api/campaigns' and method == 'POST':
            cid = f'campaign-{len(self.campaigns) + 1}'
            self.campaigns.append(cid)
            self.put('campaign_provenance', cid, {'aria_publication_enabled': self.aria})
            return {'campaign_id': cid, 'configuration_hash': self.config_hash}
        if path.endswith('/completion-study') and method == 'POST':
            cid = path.split('/')[3]
            self.bodies.append(body)
            # v4 and the manifest id are passed explicitly, every time.
            assert body == {'execute_live': True, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
                            'actor_context_protocol': base.ACTOR_CONTEXT, 'case_manifest_id': 'upgrade-v1'}
            index = len(self.studies) + len([f for f in self.start_fails if f < 0]) + 1
            if index in self.start_fails and not self.adopt:
                self.start_fails.discard(index); self.start_fails.add(-index)
                raise OSError('start failed before the server saw it')
            sid = f'study-{len(self.studies) + 1}'
            self.clock += 1
            final = json.loads(json.dumps(self.outcomes.pop(0)))
            n = final.pop('evidence_count')
            for episode_id, events in (final.pop('_events', None) or {}).items():
                self.put_events(episode_id, events)
            final.update(study_id=sid, campaign_id=cid, created_at=f'2999-01-01T00:00:{self.clock:02d}',
                         evidence={f'{sid}-ep{i}': 'weave_verified' for i in range(n)})
            self.studies[sid] = final
            self.put('completion_studies', sid, final)
            for eid in final['evidence']:
                self.put('evidence', eid, {'source': 'weave_verified', 'source_project': self.project})
            self.ledgers[cid] = {'charged_dollar_upper_bound': self.spend, 'used_calls': 10, 'caps': {}}
            self.started.append(sid)
            self.active = cid
            if index in self.start_fails:
                self.start_fails.discard(index); raise TimeoutError('response lost after the server started it')
            return {**final, 'status': 'QUEUED', 'decision': 'PENDING'}
        if path.endswith('/completion-studies') and method == 'GET':
            cid = path.split('/')[3]
            found = [s for s in self.studies.values() if s['campaign_id'] == cid]
            if found and self.active == cid:
                self.active = None
            return found
        if path.startswith('/api/completion-studies/'):
            if self.on_poll:
                self.on_poll(self)
            self.active = None
            return self.studies[path.rsplit('/', 1)[1]]
        if path.endswith('/budget'):
            return self.ledgers.get(path.split('/')[3], NO_LEDGER)
        if path.endswith('/stop'):
            self.stops.append(path.split('/')[3]); self.active = None; return {}
        raise AssertionError(f'unexpected {method} {path}')


PROCESS = {'processes': [{'pid': 1, 'command': 'python -m uvicorn app.main:app', 'started_at': 'x'}]}


@pytest.fixture
def env(launch, tmp_path, monkeypatch):
    store = tmp_path / 'artifacts' / 'lab.sqlite3'
    store.parent.mkdir(parents=True, exist_ok=True)
    make_store(store)
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 6)
    monkeypatch.setattr(loop, 'builder_manifest_hash', lambda: MANIFEST)
    monkeypatch.setattr(loop, 'paid_run_blockers', lambda reader=None: [])
    monkeypatch.setattr(fixed, 'ingestion_health', lambda: {'exit_status': 0, 'output': 'HEALTHY'})
    monkeypatch.setattr(base, 'gate_freeze', lambda: json.loads(json.dumps(launch.freeze_data)))
    monkeypatch.setattr(base, 'check_backend_process', lambda: PROCESS)
    monkeypatch.setattr(loop.time, 'sleep', lambda s: None)
    monkeypatch.setattr(loop.signal, 'signal', lambda *a: None)
    import app.config
    monkeypatch.setattr(app.config.Settings, 'from_env', classmethod(
        lambda cls: type('S', (), {'wandb_entity': 'entity', 'project_path': base.EXPECTED_PROJECT})()))
    artifacts = tmp_path / 'artifacts'
    saves = []
    real_write = loop.write_manifest

    def recording_write(path, manifest):
        saves.append(json.loads(json.dumps({'stop_reason': manifest.get('stop_reason'),
                                            'futility_look': manifest.get('futility_look'),
                                            'attempts': len(manifest.get('attempts') or [])})))
        real_write(path, manifest)
    monkeypatch.setattr(loop, 'write_manifest', recording_write)

    def run(backend, *extra, out='phase28-test'):
        launch.prepare()
        monkeypatch.setattr(base, 'api', backend)
        monkeypatch.setattr(sys, 'argv', ['run_upgrade_loop.py', '--out', str(artifacts / out), '--store', str(store),
                                          '--poll', '0', '--idle-grace', '2', '--execute-live', *launch.argv(), *extra])
        loop.main()
        return json.loads((artifacts / out / loop.MANIFEST_NAME).read_text())
    run.store = store
    run.saves = saves
    run.launch = launch
    run.manifest = lambda out='phase28-test': artifacts / out / loop.MANIFEST_NAME
    return run


# ----------------------------------------------------------------- the fixed-N loop

def test_a_certified_study_never_stops_the_run_and_every_one_is_counted(env):
    backend = FakeBackend(env.store, [OK, certified_study('b' * 64), DEAD, certified_study('c' * 64),
                                      certified_study('d' * 64, content=BOTH_SIDES), one_policy_study(1), OK, OK])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'fixed_n' and len(backend.started) == 6 and len(backend.outcomes) == 2
    assert all(body['case_manifest_id'] == 'upgrade-v1' for body in backend.bodies)
    assert [r['certified'] for r in manifest['attempts']] == [False, True, False, True, True, False]
    assert all(r['post_checks'] == 'passed' for r in manifest['attempts'])
    s = manifest['summary']
    assert (s['primary']['certified'], s['primary']['attempts'], s['primary']['truncated']) == (3, 6, False)
    assert s['primary']['statement'].startswith('3 of 6 attempts produced a certified upgrade-side completion repair')
    assert s['primary']['statement'].endswith(loop.SCOPE_SENTENCE)
    assert s['certified_attempts'] == [2, 4, 5]
    assert s['secondary_cumulative']['certified'] == 7 and s['secondary_cumulative']['attempts'] == 45
    assert s['secondary_cumulative']['rate'] is None and 'not a rate' in s['secondary_cumulative']['caveat']
    assert s['routing'] is None and 'No held-out check' in s['routing_reason']
    assert s['distinct_hashes']['both_sides_policies'] == ['d' * 64]
    assert s['distinct_hashes']['certified_hash_existed_before_run'] == {'b' * 64: False, 'c' * 64: False, 'd' * 64: False}
    assert s['cost']['total_charged_upper_bound'] == pytest.approx(12.0)
    assert s['futility_look'] is None and manifest['futility_look'] is None
    assert not backend.stops
    assert loop.reconcile(manifest, env.store) == ([], [])


def test_the_run_is_exactly_the_declared_n_and_a_final_run_cannot_resume(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 12)
    backend = FakeBackend(env.store, [certified_study('b' * 64)] + [OK] * 20)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'fixed_n' and len(backend.started) == 12
    assert manifest['declared']['plan']['design']['n_attempts'] == 12 and manifest['summary']['primary']['planned'] == 12
    with pytest.raises(SystemExit, match='final'):
        env(backend, '--resume', '--after-abort')
    assert len(backend.started) == 12


def test_the_spend_guard_truncates_and_says_so(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 30)
    backend = FakeBackend(env.store, [OK] * 30, spend=10.0)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'spend_guard' and len(backend.started) == 14
    p = manifest['summary']['primary']
    assert p['truncated'] and p['statement'].startswith('Truncated at n=14 by the $150 spend guard: 0 of 14 attempts')
    assert p['statement'].endswith(loop.SCOPE_SENTENCE)
    with pytest.raises(SystemExit, match='final'):
        env(backend, '--resume', '--after-abort')


def test_five_consecutive_infrastructure_failures_stop_the_run_and_resume_needs_approval(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 12)
    backend = FakeBackend(env.store, [DEAD] * 4 + [OK] + [DEAD] * 5 + [OK, OK, OK])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'breaker' and len(backend.started) == 10
    assert manifest['summary']['primary']['statement'].startswith('Stopped at n=10 after 5 consecutive')
    assert 'not a finding about the loop' in manifest['summary']['primary']['statement']
    with pytest.raises(SystemExit, match='--after-abort'):
        env(backend, '--resume')
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'fixed_n' and [r['attempt'] for r in resumed['attempts']] == list(range(1, 13))


def test_every_stop_wording_carries_the_scope_sentence():
    for stop in ('fixed_n', 'futility', 'spend_guard', 'breaker', 'aborted', 'running'):
        text = loop.primary_statement(0, 16, stop, 'x', distinct=16)
        assert text.endswith(loop.SCOPE_SENTENCE), stop
    assert loop.primary_statement(0, 16, 'futility', distinct=16).startswith(
        'Stopped for futility at n = 16: 0 of 16 distinct Mechanic policies re-sent the upgrade; 0 of 16 attempts')
    assert 'not a finding about the loop' in loop.primary_statement(0, 3, 'aborted', 'a signal')


# ----------------------------------------------------------------- integrity and the transposed clause in the run

def test_a_stored_improvement_with_the_source_below_three_is_an_integrity_abort(env):
    leaky = study(decision='OBSERVED_IMPROVEMENT', stage='validation', l={UPGRADE: 2, 'healthy': 3, 'upgrade-2': 3},
                  b0={'healthy': 3}, candidates=[candidate(RESEND, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED', 'b' * 64)],
                  selected='b' * 64)
    backend = FakeBackend(env.store, [OK, leaky, OK, OK])
    manifest = env(backend)
    row = manifest['attempts'][1]
    assert manifest['stop_reason'] == 'aborted' and 'integrity failure' in manifest['abort_detail']
    assert row['certified'] is False and row['integrity_failure'] and row['post_checks'].startswith('failed')
    assert len(backend.started) == 2
    s = manifest['summary']
    assert s['primary']['certified'] == 0 and s['funnel']['integrity_failures'][0]['attempt'] == 2
    assert loop.reconcile(manifest, env.store) == ([], [])


def test_a_clause_rejection_is_counted_and_worded_and_a_no_gain_improvement_is_named(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 3)
    clause = study(decision='NO_CHANGE', stage='validation', l={UPGRADE: 2, 'healthy': 3, 'upgrade-2': 3},
                   b0={'healthy': 3}, clause=UPGRADE, reason=loop.CLAUSE_REASON, selected='b' * 64,
                   candidates=[candidate(RESEND, 'NO_CHANGE', 'SOURCE_QUALIFIED', 'b' * 64)],
                   trial_rows=[trial('validation', arm, f'v{arm}{i}', case=c) for c in CASES for i in range(3)
                               for arm in ('B0', 'L')])
    no_gain = study(decision='OBSERVED_IMPROVEMENT', stage='validation', l={UPGRADE: 3, 'healthy': 3, 'upgrade-2': 1},
                    b0={'healthy': 3}, selected='c' * 64,
                    candidates=[candidate(RESEND, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED', 'c' * 64)])
    manifest = env(FakeBackend(env.store, [clause, no_gain, OK]))
    f = manifest['summary']['funnel']
    assert f['rejected_by_transposed_source_clause'] == 1 and "Phase 17's gate" in f['rejected_by_transposed_source_clause_wording']
    assert f['rejection_reasons'] == {f'{loop.CLAUSE_REASON} | case: {UPGRADE}': 1}
    assert f['observed_improvement_not_certified'] == [
        {'attempt': 2, 'study_id': 'study-2', 'statement': 'store says OBSERVED_IMPROVEMENT; not certified (no fresh gain)'}]
    assert manifest['attempts'][0]['funnel']['validation']['source_clause_case'] == UPGRADE
    assert manifest['stop_reason'] == 'fixed_n' and manifest['summary']['primary']['certified'] == 0


def test_rejection_case_replays_the_gate_order():
    cases = MANIFEST_CASES
    regressed = {'decision': 'NO_CHANGE', 'reason': loop.REGRESSED,
                 'by_case': by_case({UPGRADE: 3, 'healthy': 3, 'delayed-upgrade': 2}, {'healthy': 3, 'delayed-upgrade': 3})}
    assert loop.rejection_case(regressed, cases) == 'delayed-upgrade'
    violated = {'decision': 'NO_CHANGE', 'reason': loop.CANDIDATE_CHECK, 'by_case': by_case({})}
    violated['by_case']['upgrade-18']['L']['violations'] = 1
    assert loop.rejection_case(violated, cases) == 'upgrade-18'
    assert loop.rejection_case({'decision': 'NO_CHANGE', 'reason': loop.NO_GAIN, 'by_case': {}}, cases) == 'no strict gain'
    assert loop.rejection_case({'decision': 'OBSERVED_IMPROVEMENT'}, cases) is None


# ----------------------------------------------------------------- the stage funnel

def test_the_funnel_separates_present_from_fired_and_counts_the_baseline_leak(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 2)
    gated, firing = 'g' * 64, 'f' * 64
    controls = [trial('controls', 'B0', f'e1-c{i}', case=UPGRADE if i % 2 == 0 else 'healthy',
                      scheduled=i % 2 == 0, outcome='SAFE_UNRESOLVED' if i % 2 == 0 else 'COMPLETED') for i in range(6)]
    cand1 = [trial('candidate-1', arm, f'e1-k1{arm}{i}', outcome='SAFE_UNRESOLVED') for i in range(3) for arm in ('B0', 'L')]
    cand2 = [trial('candidate-2', arm, f'e1-k2{arm}{i}', outcome='COMPLETED' if arm == 'L' else 'SAFE_UNRESOLVED')
             for i in range(3) for arm in ('B0', 'L')]
    dirty = [trial('validation', arm, f'e1-v{arm}{i}', triggered=not (arm == 'L' and i == 0))
             for i in range(3) for arm in ('B0', 'L')]
    first = study(decision='INCOMPLETE', status='INCOMPLETE', stage='validation', selected=firing,
                  trial_rows=controls + cand1 + cand2 + dirty,
                  candidates=[candidate(PENDING_RESEND, 'REJECTED', 'NO_CHANGE', gated),
                              candidate(RESEND, 'INCOMPLETE', 'SOURCE_QUALIFIED', firing)],
                  events={**{f'e1-k1L{i}': GATED for i in range(3)}, **{f'e1-k2L{i}': FIRES for i in range(3)},
                          **{f'e1-vL{i}': FIRES for i in (1, 2)}, 'e1-c0': _events('p20-B0-F4c3'),
                          'e1-c2': _events('p20-L-F4c2')},
                  control={'valid_source': 3, 'valid_healthy': 3, 'source_completions': 0, 'healthy_completions': 3})
    first['validation_assessment'] = {'decision': 'INCOMPLETE', 'by_case': {}}
    leak = study(stage='controls', control={'valid_source': 3, 'valid_healthy': 3, 'source_completions': 1,
                                            'healthy_completions': 2},
                 trial_rows=[trial('controls', 'B0', 'e2-c0', outcome='COMPLETED'),
                             trial('controls', 'B0', 'e2-c1', case='healthy', scheduled=False, outcome='SAFE_UNRESOLVED')],
                 events={'e2-c0': _events('p20-B0-F4c3')})
    manifest = env(FakeBackend(env.store, [first, leak]))
    f = manifest['summary']['funnel']
    assert (f['upgrade_retry_present'], f['upgrade_retry_tested_at_source'], f['upgrade_retry_fired_at_source']) == (2, 2, 1)
    assert f['upgrade_retry_present_never_fired_at_source'] == 1                   # gated on PENDING: never fired
    assert [s['steps'][0]['label'] for s in f['upgrade_retry_steps']] == ['cannot fire after a transient failure', 'can fire']
    assert (f['validation_assessed'], f['validation_clean'], f['validation_dirty']) == (1, 0, 1)
    assert f['accepted_on_dirty'] == 0 and 'by construction' in f['accepted_on_dirty_note']
    assert f['controls_stops'] == 1 and f['controls_stops_by_cause']['source_leak'] == 1
    assert f['controls_stops_by_cause']['healthy_lapse'] == 1
    row = manifest['attempts'][0]['funnel']
    assert [c['upgrade_retry_fired_in'] for c in row['candidates']] == [0, 3]
    assert [c['rules_ran_in'] for c in row['candidates']] == [0, 3]
    # controls and both source gates, pooled: 3 + 3 + 3 B0 trials on upgrade-3
    assert row['baseline_source'] == {'trials': 9, 'valid': 9, 'completed': 0, 'actor_resend': 1}
    assert row['notification_fault_bearing'] == 0
    s = manifest['summary']
    assert s['baseline_leak_on_source']['valid_b0_trials'] == 10 and s['baseline_leak_on_source']['completed'] == 1
    assert s['baseline_leak_on_source']['actor_resend_episodes'] == 2
    assert s['untriggered']['untriggered'] == 1 and s['untriggered']['notification_fault_episodes'] == 0


def test_s2u_counts_step_candidates_tested_at_the_source_and_reports_duplicates_apart(env, monkeypatch):
    """Phase 17's S2(ii) is 'qualified / all step candidates tested' (review round 1): a within-study duplicate gets no
    source trials and a candidate whose study died before its source gate has no result; neither is in a
    denominator, and both are reported on their own."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 2)
    rows = [trial('candidate-1', arm, f'k{arm}{i}', outcome='SAFE_UNRESOLVED') for i in range(3) for arm in ('B0', 'L')]
    duplicate = study(stage='candidate-2', trial_rows=rows, candidates=[
        candidate(RESEND, 'NO_CHANGE', 'NO_CHANGE', 'a' * 64),
        {'decision': 'DUPLICATE', 'policy_hash': 'a' * 64, 'content': RESEND, 'source_assessment': None}])
    died = study(status='INCOMPLETE', decision='INCOMPLETE', stage='candidate-1', error_type='WaitingEvidence',
                 candidates=[{'decision': 'PROPOSED', 'policy_hash': 'e' * 64, 'content': RESEND, 'source_assessment': None}])
    f = env(FakeBackend(env.store, [duplicate, died]))['summary']['funnel']
    assert (f['upgrade_retry_present'], f['upgrade_retry_within_study_duplicates'], f['upgrade_retry_never_tested_at_source'],
            f['upgrade_retry_tested_at_source']) == (2, 1, 1, 1)
    assert f['S2u_given_step_candidates_tested'] == [0, 1] and f['S2u_given_complete_pairs'] == [0, 1]
    assert 'S2u_given_all_step_candidates' not in f and 'tested at the source gate' in f['S2u_definition']
    assert [s['policy_hash'] for s in f['upgrade_retry_steps']] == ['a' * 64, 'e' * 64]
    assert (f['distinct_valid_policies_D'], f['distinct_with_upgrade_retry_R']) == (2, 2)


def test_the_guard_table_labels_a_case_where_no_rule_ran_not_exercised(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 1)
    rows = [trial('validation', arm, f'v{c}{arm}{i}', case=c, scheduled=c != 'healthy')
            for c in CASES for i in range(3) for arm in ('B0', 'L')]
    events = {f'v{UPGRADE}L{i}': FIRES for i in range(3)}
    events.update({f'vterminal-upgrade-rejectionL{i}': [FIRES[0]] for i in range(3)})
    manifest = env(FakeBackend(env.store, [certified_study('b' * 64, trial_rows=rows, events=events)]))
    table = manifest['summary']['guards_exercised']
    assert len(table) == 1 and table[0]['certified']
    cases = table[0]['cases']
    assert cases[UPGRADE]['label'] == 'exercised' and cases[UPGRADE]['upgrade_retry_fired_in'] == 3
    assert cases['terminal-upgrade-rejection']['label'] == 'exercised' and cases['terminal-upgrade-rejection']['upgrade_retry_fired_in'] == 0
    assert cases['lost-upgrade-response']['label'] == 'not exercised' and cases['healthy']['label'] == 'not exercised'


# ----------------------------------------------------------------- the futility look in the run

def test_the_look_stops_the_run_at_the_first_d16_in_the_same_save(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)])
    manifest = env(backend)
    look = manifest['futility_look']
    assert manifest['stop_reason'] == 'futility' and len(backend.started) == 16
    assert (look['attempt'], look['D'], look['R'], look['k'], look['outcome']) == (16, 16, 0, 0, 'stop')
    # The look record and the stop reason reached the disk together, never one without the other.
    stopped = [s for s in env.saves if (s['futility_look'] or {}).get('outcome') == 'stop']
    assert stopped and all(s['stop_reason'] == 'futility' for s in stopped)
    p = manifest['summary']['primary']
    assert p['statement'].startswith('Stopped for futility at n = 16: 0 of 16 distinct Mechanic policies re-sent the upgrade')
    assert not p['truncated'] and p['statement'].endswith(loop.SCOPE_SENTENCE)
    assert loop.reconcile(manifest, env.store) == ([], [])
    # A later phase's study, after the final run ended, is outside the window.
    backend.put('completion_studies', 'later', {'replay_of': None, 'created_at': '9999-01-01T00:00:00+00:00'})
    assert loop.reconcile(manifest, env.store) == ([], [])
    with pytest.raises(SystemExit, match='futility look stopped the run'):
        env(backend, '--resume', '--after-abort')
    assert len(backend.started) == 16


def test_a_look_that_passes_is_recorded_once_and_the_run_goes_on(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 20)
    outcomes = [one_policy_study(i) for i in range(15)] + [one_policy_study(15, PENDING_RESEND)] + \
               [one_policy_study(100 + i) for i in range(10)]
    backend = FakeBackend(env.store, outcomes)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'fixed_n' and len(backend.started) == 20
    look = manifest['futility_look']
    assert (look['attempt'], look['D'], look['R'], look['outcome']) == (16, 16, 1, 'passed')
    assert sum(1 for s in env.saves if s['futility_look']) >= 1
    assert len({json.dumps(s['futility_look'], sort_keys=True) for s in env.saves if s['futility_look']}) == 1


def test_an_abort_between_the_crossing_attempt_and_the_look_is_evaluated_first_on_resume(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)])
    calls = {'n': 0}
    real = base.check_evidence_project

    def fail_on_sixteenth(db, study_record):
        calls['n'] += 1
        if calls['n'] == 16:
            raise base.PhaseAbort('evidence project check failed')
        return real(db, study_record)
    monkeypatch.setattr(base, 'check_evidence_project', fail_on_sixteenth)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and first['futility_look'] is None and len(first['attempts']) == 16
    assert len(loop.distinct_valid_policies(first['attempts'])) == 16
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'futility' and resumed['futility_look']['attempt'] == 16
    assert len(backend.started) == 16 and len(backend.campaigns) == 16          # nothing new started
    assert loop.reconcile(resumed, env.store) == ([], [])


def test_a_stop_record_whose_stop_reason_was_lost_becomes_futility_and_refuses(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)])
    manifest = env(backend)
    crashed = {**manifest, 'stop_reason': 'running'}
    env.manifest().write_text(json.dumps(crashed))
    with pytest.raises(SystemExit, match='final'):
        env(backend, '--resume', '--after-abort')
    assert json.loads(env.manifest().read_text())['stop_reason'] == 'futility'
    assert len(backend.started) == 16


def test_a_crash_after_the_futility_save_gets_its_summary_and_end_on_the_refused_resume(env, monkeypatch):
    """Review round 1, window (a): the process dies after the look's save and before the session's last save (here a
    Ctrl-C during the post-loop budget read). The stop is final, so resume refuses, but it first writes the summary,
    the budget total and ended_at (the look's own time) from the rows on record, and reconcile's window closes."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)])
    calls = {'n': 0}
    real_total = base.total_spend

    def total(url, campaigns):
        calls['n'] += 1
        if calls['n'] == 17:                    # the post-loop call, after the look stopped the run at n = 16
            raise KeyboardInterrupt
        return real_total(url, campaigns)
    monkeypatch.setattr(base, 'total_spend', total)
    with pytest.raises(KeyboardInterrupt):
        env(backend)
    monkeypatch.setattr(base, 'total_spend', real_total)
    crashed = json.loads(env.manifest().read_text())
    assert crashed['stop_reason'] == 'futility' and 'summary' not in crashed and not crashed.get('ended_at')
    with pytest.raises(SystemExit, match='final .*written now from the rows on record: .*summary'):
        env(backend, '--resume', '--after-abort')
    after = json.loads(env.manifest().read_text())
    assert len(backend.started) == 16
    assert after['stop_reason'] == 'futility' and after['ended_at'] == after['futility_look']['evaluated_at']
    p = after['summary']['primary']
    assert p['stop_reason'] == 'futility' and p['statement'].startswith('Stopped for futility at n = 16: 0 of 16 distinct')
    assert after['total_charged_upper_bound'] == pytest.approx(32.0) and 'skipped' in after['clock_drift']
    # The window now closes at the stop: a later phase's study is not "untracked".
    backend.put('completion_studies', 'later-phase', {'replay_of': None, 'created_at': '9999-01-01T00:00:00+00:00'})
    assert loop.reconcile(after, env.store) == ([], [])
    # Nothing is left to write: a second refused resume changes nothing.
    with pytest.raises(SystemExit, match='which is final$'):
        env(backend, '--resume', '--after-abort')
    assert json.loads(env.manifest().read_text()) == after


def test_a_signal_between_the_futility_save_and_the_break_keeps_the_final_futility_stop(env, monkeypatch):
    """Review round 1, window (b): a SIGTERM (or a print into a closed pipe) after the look's save and before the loop
    breaks used to rewrite the stop as 'aborted' with an 'aborted' summary. The stop stays 'futility'; the
    interruption is kept in the session record, and the drift check runs because nothing is in flight."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)])
    real_print = print

    def printing(*args, **kwargs):
        if args and str(args[0]).startswith('[look'):
            raise base.Detached(15)
        return real_print(*args, **kwargs)
    monkeypatch.setattr(loop, 'print', printing, raising=False)
    manifest = env(backend)
    monkeypatch.setattr(loop, 'print', real_print, raising=False)
    assert manifest['stop_reason'] == 'futility' and 'abort_detail' not in manifest
    assert manifest['summary']['primary']['stop_reason'] == 'futility'
    assert manifest['summary']['primary']['statement'].startswith('Stopped for futility at n = 16')
    assert 'signal 15' in manifest['sessions'][-1]['interrupted_after_the_futility_stop']
    assert manifest['sessions'][-1]['stop_reason'] == 'futility' and 'skipped' not in manifest['clock_drift']
    assert all(s['stop_reason'] == 'futility' for s in env.saves if (s['futility_look'] or {}).get('outcome') == 'stop')
    assert len(backend.started) == 16 and not backend.stops
    assert loop.reconcile(manifest, env.store) == ([], [])


def test_a_crash_after_the_futility_save_in_a_resumed_session_writes_that_sessions_end_fields(env, monkeypatch):
    """Review round 2 (WB-1): the round-1 write-up decided what was missing by whether a key existed, but every earlier
    session's end writes the budget total, ended_at and clock_drift. Session 1 ran 5 studies and was stopped by Ctrl-C;
    session 2 (an approved resume) reached the look at n = 16 and died in the post-loop budget read. The refused resume
    must write session 2's end fields: the whole run's total, ended_at at the look, the drift check marked skipped
    (session 1 keeps its own result in its session record), so reconcile sees a foreign study from session 2."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)])
    stopped = {'done': False}

    def ctrl_c_at_attempt_six(reader=None):
        if len(backend.started) == 5 and not stopped['done']:
            stopped['done'] = True
            raise KeyboardInterrupt
        return []
    monkeypatch.setattr(loop, 'paid_run_blockers', ctrl_c_at_attempt_six)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and len(backend.started) == 5
    assert first['total_charged_upper_bound'] == pytest.approx(10.0) and first['clock_drift']['exit_status'] == 0
    session_one = json.loads(json.dumps(first['sessions'][0]))
    real_total = base.total_spend

    def total(url, campaigns):
        if len(backend.started) == 16:                  # only the post-loop read sees 16: the look breaks first
            raise KeyboardInterrupt
        return real_total(url, campaigns)
    monkeypatch.setattr(base, 'total_spend', total)
    with pytest.raises(KeyboardInterrupt):
        env(backend, '--resume', '--after-abort')
    monkeypatch.setattr(base, 'total_spend', real_total)
    crashed = json.loads(env.manifest().read_text())
    assert crashed['stop_reason'] == 'futility' and len(backend.started) == 16
    assert crashed['ended_at'] == first['ended_at'] and crashed['total_charged_upper_bound'] == pytest.approx(10.0)
    with pytest.raises(SystemExit, match='which is final') as refusal:
        env(backend, '--resume', '--after-abort')
    for field in ('total_charged_upper_bound', 'summary', 'ended_at', 'sessions[-1].ended_at', 'clock_drift'):
        assert field in str(refusal.value)
    after = json.loads(env.manifest().read_text())
    look = after['futility_look']
    assert len(backend.started) == 16 and after['stop_reason'] == 'futility'
    assert after['total_charged_upper_bound'] == pytest.approx(32.0)                     # 16 x $2, not session 1's 10
    assert after['summary']['cost']['total_charged_upper_bound'] == pytest.approx(32.0)
    assert after['summary']['primary']['statement'].startswith('Stopped for futility at n = 16')
    assert after['ended_at'] == look['evaluated_at'] != first['ended_at']
    assert after['sessions'][-1]['ended_at'] == look['evaluated_at'] and after['sessions'][-1]['stop_reason'] == 'futility'
    assert 'skipped' in after['clock_drift'] and 'skipped' in after['sessions'][-1]['clock_drift']
    assert after['sessions'][0] == session_one and session_one['clock_drift']['exit_status'] == 0
    assert after['futility_write_ups'][0]['written'] == ['total_charged_upper_bound', 'summary', 'ended_at',
                                                         'sessions[-1].ended_at', 'clock_drift']
    assert loop.reconcile(after, env.store) == ([], [])
    # A foreign full study started during session 2 is inside the window; one after the look is not.
    backend.put('completion_studies', 'foreign-during-session-2', {'replay_of': None, 'created_at': look['evaluated_at']})
    backend.put('completion_studies', 'later-phase', {'replay_of': None, 'created_at': '9999-01-01T00:00:00+00:00'})
    assert loop.reconcile(after, env.store) == ([], ['foreign-during-session-2'])
    # Nothing is left to write: another refused resume changes nothing.
    with pytest.raises(SystemExit, match='which is final$'):
        env(backend, '--resume', '--after-abort')
    assert json.loads(env.manifest().read_text()) == after


class _Died(BaseException):
    """The process dies here (kill -9, power loss): no handler in main() catches it."""


@pytest.mark.parametrize('point', ['after_the_looks_save', 'post_loop_budget_read', 'before_the_end_save'])
def test_reconcile_flags_a_final_stop_whose_last_session_never_ended_until_the_resume_writes_it(
        env, monkeypatch, capsys, point):
    """Review round 3 (R3-1): round 2's write-up completes a futility-stopped record only when a resume runs, but
    reconcile trusted the unfinished record. Session 1 ran 5 studies (Ctrl-C); session 2 reached the look at n = 16
    and died after the look's save, at `point`. The record still holds session 1's end time and $10 total, and a foreign
    full study started during session 2. Reconcile must not call that clean: it names the unended session and says to
    run the resume once. After the refused resume it sees the foreign study, as round 2's test shows."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)])
    stopped = {'done': False}

    def ctrl_c_at_attempt_six(reader=None):
        if len(backend.started) == 5 and not stopped['done']:
            stopped['done'] = True
            raise KeyboardInterrupt
        return []
    monkeypatch.setattr(loop, 'paid_run_blockers', ctrl_c_at_attempt_six)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and first['sessions'][-1]['ended_at']
    assert loop.reconcile(first, env.store) == ([], [])          # an ended session is not flagged
    state = {'looked': False, 'died': False}
    real_write, real_total = loop.write_manifest, base.total_spend

    def write(path, manifest):
        if point == 'before_the_end_save' and state['looked'] and not state['died']:
            state['died'] = True
            raise _Died(point)
        real_write(path, manifest)
        if (manifest.get('futility_look') or {}).get('outcome') == 'stop' and not state['looked']:
            state['looked'] = True
            if point == 'after_the_looks_save':
                state['died'] = True
                raise _Died(point)

    def total(url, campaigns):
        if point == 'post_loop_budget_read' and state['looked'] and not state['died']:
            state['died'] = True
            raise _Died(point)
        return real_total(url, campaigns)
    monkeypatch.setattr(loop, 'write_manifest', write)
    monkeypatch.setattr(base, 'total_spend', total)
    with pytest.raises(_Died):
        env(backend, '--resume', '--after-abort')
    assert state['died'] and len(backend.started) == 16
    crashed = json.loads(env.manifest().read_text())
    look = crashed['futility_look']
    assert crashed['stop_reason'] == 'futility' and not crashed['sessions'][-1].get('ended_at')
    assert crashed['ended_at'] == first['ended_at'] and crashed['total_charged_upper_bound'] == pytest.approx(10.0)
    backend.put('completion_studies', 'foreign-during-session-2', {'replay_of': None, 'created_at': look['evaluated_at']})
    problems, _ = loop.reconcile(crashed, env.store)
    assert len(problems) == 1 and problems[0].startswith('the last session never ended')
    assert 'run the resume command once' in problems[0] and 'then reconcile again' in problems[0]
    # The operator's command (runbook step 9) says so and exits 1.
    monkeypatch.setattr(sys, 'argv', ['run_upgrade_loop.py', '--out', str(env.manifest().parent), '--store',
                                      str(env.store), '--reconcile'])
    capsys.readouterr()
    assert loop.main() == 1
    assert 'the last session never ended' in capsys.readouterr().out
    # The resume refuses the final stop, writes session 2's end fields, and reconcile then sees the foreign study.
    with pytest.raises(SystemExit, match='which is final'):
        env(backend, '--resume', '--after-abort')
    after = json.loads(env.manifest().read_text())
    assert len(backend.started) == 16 and after['sessions'][-1]['ended_at'] == look['evaluated_at']
    assert after['total_charged_upper_bound'] == pytest.approx(32.0)
    assert loop.reconcile(after, env.store) == ([], ['foreign-during-session-2'])


def test_a_closed_pipe_after_the_look_keeps_the_final_futility_stop_and_its_whole_write_up(env, monkeypatch):
    """Review round 2 (WB-1): protocol section 6.3's own example. A dead `tee` makes every later print raise
    BrokenPipeError; the abort handler's own print used to re-raise it out of main(), so the session never ended and
    the interruption was never kept. Now main() returns, the stop is futility with its summary, end time and drift
    check, and the session record keeps the interruption."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)])
    real_print = print
    state = {'closed': False}

    def printing(*args, **kwargs):
        if args and str(args[0]).startswith('[look'):
            state['closed'] = True
        if state['closed']:
            raise BrokenPipeError(32, 'Broken pipe')     # this and every later print, as with a dead tee
        return real_print(*args, **kwargs)
    monkeypatch.setattr(loop, 'print', printing, raising=False)
    manifest = env(backend)
    monkeypatch.setattr(loop, 'print', real_print, raising=False)
    assert manifest['stop_reason'] == 'futility' and len(backend.started) == 16 and not backend.stops
    assert manifest['summary']['primary']['statement'].startswith('Stopped for futility at n = 16')
    assert manifest['ended_at'] and manifest['sessions'][-1]['stop_reason'] == 'futility'
    assert manifest['sessions'][-1]['interrupted_after_the_futility_stop'].startswith('BrokenPipeError')
    assert 'abort_detail' not in manifest and manifest['clock_drift']['exit_status'] == 0
    assert loop.reconcile(manifest, env.store) == ([], [])


def test_a_closed_pipe_inside_the_loop_is_a_recorded_abort_and_nothing_escapes_main(env, monkeypatch):
    """Review round 2 (WB-1): before the look, a closed pipe ends the run as an abort (print() inside the loop), and
    the write-up after it completes (say() drops the error), so an approved resume can continue."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 4)
    backend = FakeBackend(env.store, [OK] * 4)
    real_print = print
    state = {'closed': False}

    def printing(*args, **kwargs):
        if args and str(args[0]).startswith('[attempt 3/'):
            state['closed'] = True
        if state['closed']:
            raise BrokenPipeError(32, 'Broken pipe')
        return real_print(*args, **kwargs)
    monkeypatch.setattr(loop, 'print', printing, raising=False)
    first = env(backend)
    monkeypatch.setattr(loop, 'print', real_print, raising=False)
    assert first['stop_reason'] == 'aborted' and first['abort_detail'].startswith('BrokenPipeError')
    assert first['summary']['primary']['stop_reason'] == 'aborted' and first['ended_at']
    assert first['sessions'][-1]['ended_at'] and first['clock_drift']['exit_status'] == 0
    # Attempt 3 was appended and printed before its campaign existed: a labelled phantom row, still in the denominator.
    assert len(backend.started) == 2 and first['attempts'][-1]['attempt'] == 3
    assert first['attempts'][-1]['error'] == fixed.INTERRUPTED_BEFORE_CREATE
    assert loop.reconcile(first, env.store) == ([], [])
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'fixed_n' and len(resumed['attempts']) == 4 and len(backend.started) == 3


def test_the_look_takes_precedence_over_fixed_n_at_exactly_n(env, monkeypatch):
    """Design section 6.2: if the look fires at n = N, the stop is futility (review round 1: no test pinned it)."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 16)
    manifest = env(FakeBackend(env.store, [one_policy_study(i) for i in range(20)]))
    assert manifest['stop_reason'] == 'futility' and manifest['futility_look']['attempt'] == 16
    assert manifest['summary']['primary']['statement'].startswith('Stopped for futility at n = 16')


@pytest.mark.parametrize('look_d,stop', [(16, 'futility'), (17, 'spend_guard')])
def test_the_look_takes_precedence_over_the_spend_guard_on_the_same_iteration(env, monkeypatch, look_d, stop):
    """At $9 a study the guard trips at the top of iteration 17 (16 x 9 + 11 > 150): the same iteration where
    D = 16 is first reached. With the look at 16 the stop is futility; with it out of reach, the guard stops."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    monkeypatch.setattr(loop, 'FUTILITY_LOOK_D', look_d)
    backend = FakeBackend(env.store, [one_policy_study(i) for i in range(20)], spend=9.0)
    manifest = env(backend)
    assert manifest['stop_reason'] == stop and len(backend.started) == 16


def test_d_counts_distinct_valid_policies_from_any_slot():
    """D is 'across the whole run and any slot' (review round 1: no test built D from slot-2 policies)."""
    invalid = {'decision': 'REJECTED', 'policy_hash': None, 'content': None, 'source_assessment': None}
    # Slot 1 invalid, slot 2 a new valid policy: D reaches 16 only through slot 2.
    only_slot2 = _rows(*[study(stage='candidate-2', candidates=[
        invalid, candidate(NO_RESEND, 'NO_CHANGE', 'NO_CHANGE', f'{1000 + i:064x}')]) for i in range(16)])
    look = loop.futility_look(only_slot2, None)
    assert (look['attempt'], look['D'], look['outcome']) == (16, 16, 'stop')
    assert not loop.futility_look(only_slot2[:15], None)
    # Two distinct valid policies per study: D = 16 after 8 attempts, half of them slot 2.
    both = _rows(*[study(stage='candidate-2', candidates=[
        candidate(NO_RESEND, 'NO_CHANGE', 'NO_CHANGE', f'{2000 + 2 * i:064x}'),
        candidate(NO_RESEND, 'NO_CHANGE', 'NO_CHANGE', f'{2001 + 2 * i:064x}')]) for i in range(8)])
    assert loop.futility_look(both, None)['attempt'] == 8 and loop.first_look_attempt(both) == 8
    # An orders re-send written only in slot 2 is counted in R.
    slot2_step = _rows(*[study(stage='candidate-2', candidates=[
        invalid, candidate(RESEND if i == 3 else NO_RESEND, 'NO_CHANGE', 'NO_CHANGE', f'{3000 + i:064x}')])
        for i in range(16)])
    assert loop.futility_look(slot2_step, None)['R'] == 1


def test_a_resume_with_a_different_look_is_refused(env, monkeypatch):
    backend = FakeBackend(env.store, [study(protocol='faultlab-actor-context/v1')] + [OK] * 6)
    first = env(backend)
    assert first['stop_reason'] == 'aborted'
    monkeypatch.setattr(loop, 'FUTILITY_LOOK_D', 12)
    with pytest.raises(SystemExit, match='Resume refused: the plan'):
        env(backend, '--resume', '--after-abort')


def test_reconcile_catches_a_tampered_look_and_attempts_after_a_stop(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 50)
    manifest = env(FakeBackend(env.store, [one_policy_study(i) for i in range(20)]))
    tampered = json.loads(json.dumps(manifest))
    tampered['futility_look']['R'] = 1
    assert any('does not recompute' in p for p in loop.reconcile(tampered, env.store)[0])
    extra = json.loads(json.dumps(manifest))
    extra['attempts'].append({'attempt': 17, 'campaign_id': None, 'study_id': None})
    assert any('ran after the futility stop' in p for p in loop.reconcile(extra, env.store)[0])
    lost = {**json.loads(json.dumps(manifest)), 'futility_look': None}
    assert any('without a stopping look record' in p for p in loop.reconcile(lost, env.store)[0])


def test_reconcile_requires_the_look_at_the_first_crossing(env, monkeypatch):
    """Review round 1: a run whose rows reach D >= 16 must hold a look evaluated at exactly that attempt once it went
    past it or ended final; a run that stopped early AT the crossing may not have one yet (resume evaluates it)."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 20)
    outcomes = [one_policy_study(i) for i in range(15)] + [one_policy_study(15, RESEND)] + \
               [one_policy_study(100 + i) for i in range(10)]
    manifest = env(FakeBackend(env.store, outcomes))
    assert manifest['futility_look']['outcome'] == 'passed' and loop.reconcile(manifest, env.store) == ([], [])
    skipped = {**json.loads(json.dumps(manifest)), 'futility_look': None}
    assert any('no futility look record' in p for p in loop.reconcile(skipped, env.store)[0])
    late = json.loads(json.dumps(manifest))
    late['futility_look'].update(attempt=18, D=18)
    assert any('not at attempt 16' in p for p in loop.reconcile(late, env.store)[0])
    # Stopped (not final) exactly at the crossing, before the look was evaluated: not a discrepancy.
    at_crossing = {**json.loads(json.dumps(manifest)), 'futility_look': None, 'stop_reason': 'aborted'}
    at_crossing['attempts'] = at_crossing['attempts'][:16]
    assert loop.reconcile(at_crossing, env.store)[0] == []
    # The same rows ending FINAL at the crossing without a look are one.
    final = {**at_crossing, 'stop_reason': 'fixed_n'}
    assert any('no futility look record' in p for p in loop.reconcile(final, env.store)[0])


# ----------------------------------------------------------------- guards and refusals before any spend

def test_the_paid_run_guard_ignores_its_own_caffeinate_child_and_blocks_a_foreign_live_run(monkeypatch):
    own = os.getpid()
    rows = [(1, 0, '/sbin/launchd'), (own - 1 if own > 2 else 2, 1, '-zsh'),
            (own, own - 1 if own > 2 else 2, 'python scripts/experiments/run_upgrade_loop.py --execute-live --out x'),
            (own + 100000, own, 'caffeinate -is python scripts/experiments/run_upgrade_loop.py --execute-live'),
            (own + 100001, 1, '/usr/bin/python3 scripts/experiments/report_narrow_probe.py --execute-live --out y'),
            (own + 100002, 1, 'grep --execute-live scripts/experiments/x.py')]
    blockers = loop.paid_run_blockers(lambda: rows)
    assert len(blockers) == 1 and 'report_narrow_probe.py' in blockers[0]
    assert loop.paid_run_blockers(lambda: rows[:4]) == []
    assert 'could not be read' in loop.paid_run_blockers(lambda: (_ for _ in ()).throw(OSError('no ps')))[0]


def test_another_paid_run_refuses_before_the_claim_and_stops_the_loop_before_an_attempt(env, monkeypatch):
    monkeypatch.setattr(loop, 'paid_run_blockers', lambda reader=None: ['pid 7: python experiments/x.py --execute-live'])
    backend = FakeBackend(env.store, [OK] * 6)
    with pytest.raises(SystemExit, match='One paid run at a time'):
        env(backend)
    assert not backend.campaigns and not env.manifest().exists()
    calls = {'n': 0}

    def appears_later(reader=None):
        calls['n'] += 1
        return ['pid 8: python experiments/y.py --execute-live'] if calls['n'] >= 4 else []
    monkeypatch.setattr(loop, 'paid_run_blockers', appears_later)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'another paid run appeared' in manifest['abort_detail']
    assert len(backend.started) == 1


def test_unhealthy_ingestion_refuses_before_any_campaign_or_record(env, monkeypatch):
    monkeypatch.setattr(fixed, 'ingestion_health', lambda: {'exit_status': 2, 'output': 'DEGRADED'})
    backend = FakeBackend(env.store, [OK])
    with pytest.raises(SystemExit, match='check_ingestion_health'):
        env(backend)
    assert not backend.campaigns and not env.manifest().exists()


def test_a_builder_that_does_not_hash_to_the_pin_refuses(env, monkeypatch):
    monkeypatch.setattr(loop, 'builder_manifest_hash', lambda: 'n' * 64)
    backend = FakeBackend(env.store, [OK])
    with pytest.raises(SystemExit, match='DECLARED_MANIFEST_HASH'):
        env(backend)
    assert not backend.campaigns


def test_code_that_differs_from_the_reviewed_freeze_refuses_to_start(env, monkeypatch):
    monkeypatch.setattr(base, 'gate_freeze', lambda: {**env.launch.freeze_data, 'files': {'x': 1}})
    backend = FakeBackend(env.store, [OK])
    with pytest.raises(SystemExit, match='differs from the reviewed freeze'):
        env(backend)
    assert not backend.campaigns


def test_the_output_prefix_and_the_rerun_guard(env):
    backend = FakeBackend(env.store, [OK] * 12)
    with pytest.raises(SystemExit, match='must be artifacts/phase28-'):
        env(backend, out='phase23-2026-10-02')
    env(backend)
    with pytest.raises(SystemExit, match='refusing to overwrite'):
        env(backend)
    with pytest.raises(SystemExit, match='Another Phase 28 run exists'):
        env(backend, out='phase28-other')
    assert len(backend.started) == 6


def test_a_study_on_the_wrong_manifest_aborts_at_start_and_is_stopped(env):
    backend = FakeBackend(env.store, [study(manifest_id=None, manifest_hash='7' * 64), OK, OK])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'case_manifest_id' in manifest['abort_detail']
    assert backend.stops == ['campaign-1']


def test_a_configuration_abort_does_not_block_a_later_approved_resume(env):
    backend = FakeBackend(env.store, [OK] * 6, config_hash='d' * 64)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'configuration_hash' in first['abort_detail'] and not backend.started
    assert fixed.runner_side(first['attempts'][0])
    backend.config_hash = CONFIG
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'fixed_n' and len(backend.started) == 5
    assert resumed['summary']['funnel']['infrastructure_deaths'] == 0
    assert resumed['summary']['funnel']['runner_side_no_study'] == 1


def test_a_signal_leaves_the_running_study_alone_and_resume_recovers_it(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 3)
    backend = FakeBackend(env.store, [certified_study('b' * 64), OK, OK])

    def detach_on_first_poll(fake):
        fake.on_poll = None
        raise base.Detached(15)
    backend.on_poll = detach_on_first_poll
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'left running' in first['abort_detail']
    assert not backend.stops and first['attempts'][0].get('status') is None and 'skipped' in first['clock_drift']
    backend.active = None
    resumed = env(backend, '--resume', '--after-abort')
    row = resumed['attempts'][0]
    assert row['recovered'] and row['certified'] and row['post_checks'].startswith('passed on recovery')
    assert 'funnel' in row and resumed['stop_reason'] == 'fixed_n' and len(backend.started) == 3


def _leaky(policy_hash='b' * 64):
    """A study the store records as OBSERVED_IMPROVEMENT with the source only 2 of 3: condition 4 fails."""
    return study(decision='OBSERVED_IMPROVEMENT', stage='validation', l={UPGRADE: 2, 'healthy': 3, 'upgrade-2': 3},
                 b0={'healthy': 3}, candidates=[candidate(RESEND, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED', policy_hash)],
                 selected=policy_hash)


def test_an_integrity_failure_recovered_on_resume_becomes_the_abort_and_refuses_that_resume(env, monkeypatch):
    """Review round 1 (runner lens, major): condition 4 makes an integrity failure an abort, also when recover()
    finds it on resume after a signal. The resume that found it is refused and the failure becomes the recorded
    abort, so only the NEXT --after-abort (given with it in view) continues; that one is not refused again."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 3)
    backend = FakeBackend(env.store, [_leaky(), OK, OK])

    def detach_on_first_poll(fake):
        fake.on_poll = None
        raise base.Detached(15)
    backend.on_poll = detach_on_first_poll
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'signal 15' in first['abort_detail']
    backend.active = None
    with pytest.raises(SystemExit, match='Resume refused: integrity failure: study study-1'):
        env(backend, '--resume', '--after-abort')
    refused = json.loads(env.manifest().read_text())
    assert len(backend.started) == 1 and len(refused['attempts']) == 1          # nothing new was paid for
    assert refused['stop_reason'] == 'aborted' and refused['abort_detail'].startswith('integrity failure: study study-1')
    assert 'after the earlier stop: signal 15' in refused['abort_detail']
    assert refused['resume_refusals'][0]['reason'] == refused['abort_detail']
    statement = refused['summary']['primary']['statement']
    assert statement.startswith('Stopped at n=1 because integrity failure') and 'not a finding about the loop' in statement
    row = refused['attempts'][0]
    assert row['recovered'] and not row['certified'] and row['post_checks'].startswith('failed on recovery')
    # The user has now seen it; an approved continuation goes on, and the row stays not certified.
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'fixed_n' and len(backend.started) == 3
    assert resumed['sessions'][-1]['previous_abort_detail'] == refused['abort_detail']
    assert [r['certified'] for r in resumed['attempts']] == [False, False, False]
    assert resumed['summary']['funnel']['integrity_failures'][0]['attempt'] == 1
    assert loop.reconcile(resumed, env.store) == ([], [])


def test_an_integrity_failure_found_by_the_sweep_after_an_abort_is_the_recorded_abort(env, monkeypatch):
    """Review round 1: the sweep after an abort (here lost contact while the study ran) recovers the study; its
    integrity failure then names the stop, not the lost contact alone. A later approved resume continues."""
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 2)
    backend = FakeBackend(env.store, [_leaky(), OK])

    def lose_contact_once(fake):
        fake.on_poll = None
        raise OSError('connection refused')
    backend.on_poll = lose_contact_once
    first = env(backend, '--poll-failure-window', '-1')     # the first failed poll already exceeds the window
    assert first['stop_reason'] == 'aborted' and backend.stops == ['campaign-1']
    assert first['abort_detail'].startswith('integrity failure: study study-1')
    assert 'after the earlier stop: lost contact with a running study' in first['abort_detail']
    row = first['attempts'][0]
    assert row['recovered'] and not row['certified'] and row['integrity_failure']
    assert first['summary']['primary']['statement'].startswith('Stopped at n=1 because integrity failure')
    assert first['sessions'][-1]['abort_detail'] == first['abort_detail']
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'fixed_n' and len(backend.started) == 2
    assert loop.reconcile(resumed, env.store) == ([], [])


def test_plan_is_dry_and_shows_every_pin_the_harness_and_the_plan_hash(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(base, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no HTTP in a plan')))
    monkeypatch.setattr(fixed, 'ingestion_health', lambda: (_ for _ in ()).throw(AssertionError('no checks in a plan')))
    monkeypatch.setattr(loop, 'paid_run_blockers', lambda reader=None: (_ for _ in ()).throw(AssertionError('no guard')))
    monkeypatch.setattr(sys, 'argv', ['run_upgrade_loop.py', '--out', str(tmp_path / 'p'), '--plan'])
    assert loop.main() == 0
    text = capsys.readouterr().out
    assert 'Dry plan only' in text and not (tmp_path / 'p').exists()
    pins = [line for line in text.splitlines() if line.startswith('pin')]
    assert len(pins) == len(loop.PINS) + 2 * len(loop.DECLARED_FUNCTION_HASHES)
    assert sum('UNFILLED' in line for line in pins) == len(loop.unfilled_pins())
    assert f'plan       hash {loop.plan_hash()}' in text and f'harness    sha256 {base.sha256_file(RUNNER)}' in text
    assert 'never      replay' in text


def test_reconcile_catches_store_disagreement_and_untracked_studies(env, monkeypatch):
    monkeypatch.setattr(loop, 'N_ATTEMPTS', 3)
    backend = FakeBackend(env.store, [OK, certified_study('b' * 64), OK])
    manifest = env(backend)
    assert loop.reconcile(manifest, env.store) == ([], [])
    tampered = json.loads(json.dumps(manifest))
    tampered['attempts'][1]['decision'] = 'NO_CHANGE'
    tampered['attempts'][1]['case_manifest_id'] = None
    problems, _ = loop.reconcile(tampered, env.store)
    assert any('decision manifest' in p for p in problems) and any('case_manifest_id' in p for p in problems)
    open_run = {**json.loads(json.dumps(manifest)), 'stop_reason': 'aborted'}
    backend.put('completion_studies', 'stray', {'replay_of': None, 'created_at': manifest['ended_at']})
    assert loop.reconcile(open_run, env.store)[1] == ['stray']
