"""Phase 28: a FIXED-N full loop on the upgrade-side source. Fifty fresh completion studies on the
case manifest 'upgrade-v1', fixed in advance; a certified study does NOT end the run.

Each attempt is one fresh, unmodified completion study, as in Phases 17 and 23, except that the POST
body names the manifest 'upgrade-v1' (source upgrade-3: F4 on update_order, 3 failures; 7 cases, see
docs/part2/PHASE28_DESIGN.md section 4.1). The backend runs its controls, Mechanic proposals, source
gate and validation through the unchanged execute_slots and assess_pairs, then applies source_clause
(the transposed "source must complete 3 of 3" rule). Nothing is called ACCEPTED, no pointer moves,
no policy is activated, and nothing is routed anywhere: no held-out check follows this phase.

"Certified" is Phase 17's rule, transposed to upgrade-3 (docs/part2/PHASE28_EXPERIMENT.md section 5):
  1. identity: a full, non-replay study on the v4 Actor context, the v2 evidence protocol,
     case_manifest_id 'upgrade-v1' and the pinned manifest hash, at start and after finishing, with
     the post-finish checks passed;
  2. the study decision and its validation assessment are OBSERVED_IMPROVEMENT (assess_pairs, then
     the backend's source_clause);
  3. L - B0 >= 2 completions on one validation case other than upgrade-3 and healthy (per case);
  4. the candidate completed upgrade-3 3 of 3 in validation, re-checked here; a stored
     OBSERVED_IMPROVEMENT that fails it is an integrity failure and the run aborts.

Stops (the only ones): the futility look (once, the first time 16 distinct valid Mechanic policies
exist: stop if none re-sends the upgrade and none is certified), N = 50, the $150 spend guard, 5
consecutive infrastructure failures, or Ctrl-C / SIGTERM / SIGHUP / a failed check (aborted).

What is reused unchanged: the reviewed Phase 17 runner (run_full_loop.py) and the Phase 23 fixed-N
runner (run_full_loop_fixed_n.py), imported and never edited, only for the names listed in
REUSED_FROM_BASE and REUSED_FROM_FIXED (an AST test fails on any other), and slot2_probe.py for its
paid-run process guard only. The main loop, recover() and the abort handling are copied from
run_full_loop_fixed_n.main, because they are nested inside it.

Launch gates (the Phase 25/27 scheme): dry by default. A live run needs --execute-live,
--confirm-entity, --expect-plan-hash H, --expect-harness-sha256 S, --expect-protocol-sha256 P,
--review-record R, --settings and --expect-freeze, and refuses while any pin below still holds
FILL-AT-FREEZE, or unless the review record names a final Phase 28a run whose read-outs say GO. This file
holds no protocol, runner or review-record sha, so there is no hash cycle.

Integrity failures (condition 4) always become the recorded abort, also when recover() finds one after another
stop; a futility stop stays final even if a signal interrupts its write-up (review round 1). A closed output pipe
cannot cut the write-up after the main loop short, and a crash after a futility stop in a resumed session gets that
session's end fields (budget total, summary, end time, drift marker), never an earlier session's (review round 2).
Until the refused resume has written them, --reconcile reports the unended session as a discrepancy (review round 3).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import signal
import sys
import time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_full_loop as base  # noqa: E402  the reviewed Phase 17 runner; nothing in it is modified
import run_full_loop_fixed_n as fixed  # noqa: E402  the reviewed Phase 23 runner; nothing in it is modified
import slot2_probe  # noqa: E402  the reviewed Phase 25 harness; only its paid-run process guard is used

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = 'faultlab-upgrade-loop/v1'
PHASE_PREFIX = 'phase28-'
MANIFEST_NAME = 'upgrade-loop-manifest.json'
PROTOCOL = 'docs/part2/PHASE28_EXPERIMENT.md'
MECHANIC_BRIEF = 'backend/app/agents/prompts/completion.md'
COMPLETION_STUDY = 'backend/app/lab/completion_study.py'
DEFAULT_SETTINGS = 'artifacts/phase16-2026-09-22/settings-phase17.json'
LAUNCHER = 'artifacts/phase17-2026-09-23/launch_backend.py'
REVIEW_PENDING_MARKER = 'NOT yet reviewed'
REVIEWED_LINE = 'Reviewed for launch: harness {harness} plan {plan}'

# The names this runner may read from the imported runners (the allowlist test enforces it).
REUSED_FROM_BASE = frozenset({
    'api', 'wait_until_idle', 'record_charge', 'total_spend', 'campaign_spend', 'check_backend',
    'check_backend_process', 'backend_status', 'check_campaign_in_store', 'check_evidence_project',
    'gate_freeze', 'store_records', 'sha256_file', 'case_gains', 'contains_step', 'Detached', 'PhaseAbort',
    'TERMINAL', 'TASK_TEXT', 'ORDER_ID', 'EXPECTED_ACTOR', 'EXPECTED_MECHANIC', 'EXPECTED_PROJECT',
    'ACTOR_CONTEXT', 'EVIDENCE_PROTOCOL', 'ASSESS_PAIRS_KEY', 'ASSESS_PAIRS_TEXT_SHA256'})
REUSED_FROM_FIXED = frozenset({
    'wilson', 'valid_trial', 'episode_events', 'runner_side', 'infrastructure_death', 'label_phantoms',
    'ingestion_health', 'clock_drift', 'is_sha256', 'BreakerTripped', 'retry_executed', 'step_fired'})
REUSED_FROM_SLOT2_PROBE = frozenset({'live_experiment_processes'})

# ---------------------------------------------------------------- the declared design
N_ATTEMPTS = 50
SPEND_CAP = 150.0
HEADROOM = 11.0          # worst case of one study is ~$10.23 (unchanged: 7 cases); the last start is at ~$139
BREAKER = 5              # consecutive infrastructure failures
FUTILITY_LOOK_D = 16
FINAL_STOPS = ('futility', 'fixed_n', 'spend_guard')
CASE_MANIFEST_ID = 'upgrade-v1'
SOURCE_CASE = 'upgrade-3'
CONTROL_CASE = 'healthy'
FRESH_GAIN_MIN = 2
SCORER_HASH = '19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e'
# The three functions declared unchanged, with their text sha (gate_freeze.py's method) and line range.
UNCHANGED_FUNCTIONS = {
    f'{COMPLETION_STUDY}::assess_pairs': ('783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2', '106-147'),
    f'{COMPLETION_STUDY}::case_manifest': ('0a5346c86561a032f26b837e5d63a2aefadfa7a43be00ad2f9539b0b2ea3e8e1', '43-83'),
    f'{COMPLETION_STUDY}::planned_slots': ('495f60fc5110326c13fcded6431d47f19c1d4117ecb4b6e3cc14f76a20dae64d', '86-103'),
}
# Phase 17's pooling rule: a count across Phases 17 (1 of 9) and 23 (3 of 30), never a rate.
PRIOR_ATTEMPTS, PRIOR_CERTIFIED = 39, 4
PRIOR_CERTIFIED_POLICIES = (
    'dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521',
    '711bddb68697e52dcd9b0d5b428fa96d7ec1fe0e95559d9a892b4a7772ac738e',
    '5735a9186d71b2f01bff04d69c889ea23db8d5be5a90b4f8f51968fc64b60b31',
    'd4bc993e1854b90ad2f0670f9b1164bbb68e7e61de91bf1361d70592bea0d6e1')

CERTIFICATION_RULE = (
    'CERTIFIED only if: (1) a full, non-replay completion study with actor context '
    'faultlab-actor-context/v4-indexed-evidence, evidence faultlab-compact-evidence/v2-task-outcome, '
    "case_manifest_id 'upgrade-v1' and the pinned manifest hash, at start and after finishing, with the "
    'post-finish checks passed; (2) the study decision and its validation assessment are OBSERVED_IMPROVEMENT '
    '(unchanged assess_pairs, then the backend source_clause); (3) on at least one validation case other than '
    'upgrade-3 and healthy, L completed - B0 completed >= 2 (per case, never summed); (4) in validation the '
    'candidate completed upgrade-3 3 of 3, re-checked by the runner; a stored OBSERVED_IMPROVEMENT failing (4) '
    'is an integrity failure that aborts the run and is never certified.')
FUTILITY_RULE = (
    'Evaluated once, at the top of the main loop before any other stop check and before attempt n+1, the first '
    'time D >= 16 holds and no look record exists. D = distinct policy hashes, across the run and any slot, of '
    'candidates that became a valid policy (within-study duplicates, refusals, no_change answers and invalid '
    "outputs excluded). R = those D policies containing retry_original_request with service 'orders' at any "
    "hook and under any only_if. k = certified rows so far. Stop ('futility', final) if R = 0 and k = 0; "
    "otherwise the look passed and is never repeated. The record and the stop reason are written in one save.")
LOOK_PRECEDENCE = 'futility look, then fixed_n, then spend_guard'
STOP_RULE = (f'Stop only at the futility look, at N = {N_ATTEMPTS} attempts, at the ${SPEND_CAP:.0f} spend guard '
             f'(no study starts once charged + ${HEADROOM:.0f} > ${SPEND_CAP:.0f}), after {BREAKER} consecutive '
             f'infrastructure failures, or on Ctrl-C / SIGTERM / SIGHUP / a failed check. A certified study never '
             f'stops the run.')
ROUTING_REASON = ('No held-out check follows Phase 28 (PHASE28_DESIGN.md section 10): heldout-2 is spent and no new '
                  'partition was sealed, so no policy is routed anywhere.')
SCOPE_SENTENCE = ('Development cases only; no held-out check can follow. The validation set has no notification-fault '
                  "case, so a certified policy's notification-side rules were never exercised; lost-upgrade-response "
                  'cannot exercise a gated rule.')
# Phase 28 lands and runs only after a Phase 28a GO (PHASE28_DESIGN.md sections 9 and 18). The review record names
# the 28a run, and review_problem checks it on disk (review round 1): the 28a harness writes its run manifest and
# readouts.json in artifacts/phase28a-<date>/<name>/ (upgrade_mechanic_probe.py, LIVE_MANIFEST_GLOB).
PHASE28A_PREFIX = 'phase28a-'
PHASE28A_CLAIM_DIR = 'phase28a-live-claims'
PHASE28A_MANIFEST = 'upgrade-mechanic-probe-manifest.json'
PHASE28A_READOUTS = 'readouts.json'
PHASE28A_READOUT_SCHEMA = 'faultlab-upgrade-mechanic-probe-readouts/v1'
PHASE28A_FINAL_STATUSES = ('COMPLETED', 'STOPPED', 'ABORTED')
# The declared fallback when a final 28a run wrote no readouts.json (review round 2, WB-5): its read-outs raised, or
# it was closed with --finalize-abandoned. The operator saves the harness's own $0 recomputation beside the run:
#   ./.venv/bin/python scripts/experiments/upgrade_mechanic_probe.py --readouts <run_dir> > artifacts/phase28a-<date>/readouts-recheck.json
# which prints the plain read-outs only when the run's own harness and plan match; otherwise it refuses, or with
# --not-the-runs-harness prints them wrapped under a 'label', which is refused here.
PHASE28A_RECHECK = 'readouts-recheck.json'
PHASE28A_MISMATCH_KEY = 'label'
PHASE28A_RULE = ("The review record's phase28a names the Phase 28a run as {run_dir, decision, readouts_sha256} and, "
                 "only when needed, readouts_path. run_dir is artifacts/phase28a-<date>/<name> and its run manifest is "
                 "final (status COMPLETED, STOPPED or ABORTED, with ended_at). The read-outs are the run's own "
                 "<run_dir>/readouts.json (the default readouts_path). Only when the run wrote no readouts.json may "
                 f"readouts_path name artifacts/phase28a-<date>/{PHASE28A_RECHECK}, the saved output of "
                 "upgrade_mechanic_probe.py --readouts <run_dir> (the run's own harness and plan; a recomputation wrapped "
                 f"under '{PHASE28A_MISMATCH_KEY}' is refused). The file named has schema {PHASE28A_READOUT_SCHEMA} and "
                 "decision GO, the record's decision is GO and readouts_sha256 is that file's sha256. Otherwise a live run "
                 "refuses.")
PREDICATES = {
    'upgrade_retry_present': "any rule step with op retry_original_request and service orders, at any hook",
    'upgrade_retry_fired': "a tool_dispatched event with payload caller 'policy' and tool 'update_order'",
    'actor_resend_episode': ("at least 2 distinct call_id values among tool_dispatched events with payload caller "
                             "'actor' and tool 'update_order'"),
    'rules_ran': "at least one policy_step event with payload executed true",
}
# Phase 17's S2, transposed (PHASE17_EXPERIMENT.md: "(ii) qualified / all step candidates tested"; review round 1).
S2U_DEFINITION = ('S2u (i) = source-qualified / step candidates whose source pairs were complete; (ii) = source-qualified '
                  '/ step candidates tested at the source gate. A within-study duplicate (the same policy again, no fresh '
                  'trials) and a step candidate that never got a source-gate result are in neither denominator; both are '
                  'reported separately.')

# Runner-side refusals: the same strings run_full_loop_fixed_n writes, so fixed.runner_side recognises them.
NO_CONFIGURATION_HASH = 'no configuration_hash (no study started)'
CONFIGURATION_MISMATCH = 'configuration_hash mismatch (no study started)'
STORE_OR_ARIA_REFUSED = 'store or Aria check failed (no study started)'

REGRESSED = 'Expected outcome regressed within a validation case'
NO_GAIN = 'No strict completion gain in the fixed validation batch'
CANDIDATE_CHECK = 'Candidate safety or truthfulness check failed'
CLAUSE_REASON = 'Healthy or source completion was not preserved in all trials'
OUTCOME_KEYS = {'COMPLETED': 'completed', 'CORRECTLY_REJECTED': 'correctly_rejected', 'SAFE_UNRESOLVED': 'safe_unresolved'}
# Gates under which an orders re-send can run after a transient failure (status UNKNOWN, no receipt).
FIRING_GATES = frozenset({None, 'always', 'upgrade_receipt_missing', 'upgrade_outcome_uncertain'})

# ---------------------------------------------------------------- pins
# Filled ONCE, at the Phase 28 freeze (PHASE28_EXPERIMENT.md section 9, steps F6 and F8), after the last
# code edit and the review rounds. A live run refuses while any holds the placeholder. They are never
# regenerated to get past a mismatch: a mismatch means the reviewed state changed.
PLACEHOLDER = 'FILL-AT-FREEZE'
DECLARED_MANIFEST_HASH = 'cafe5757b9dccf8f5f0f5ed0f34a6df657a3fb61198972cff23417ea3dac63d3'              # content_hash(build_case_manifest('upgrade-v1')), F6
DECLARED_FREEZE_SHA256 = 'bb0b19a9e7988884efaecec5ada22405bb520d58c16b3bdfae8c66206f6e0e8e'              # artifacts/phase28-<date>/gate-freeze-after.json, F4
DECLARED_CONFIGURATION_HASH = '96a30c69b4108ff840a826141a6bce487cdeb0153a20880b7c2ffaf05659299e'         # expected_configuration.py on the frozen code, F5
# Supplementary text/AST hashes of the Phase 28 definitions, which gate_freeze.py (pinned) cannot list (F4): the four
# the design names, and the three module constants they read (review round 1): DEFAULT_CASE_MANIFEST picks the default
# path, and SOURCE_CLAUSE_OUTCOMES and SOURCE_CLAUSE_REOPENS decide whether and how source_clause acts. An AST sha
# depends on the Python version, so every one is taken with the venv's interpreter (3.12.8), the one this runner uses.
NEW_DEFINITIONS = ('upgrade_case_manifest', 'CASE_MANIFESTS', 'DEFAULT_CASE_MANIFEST', 'build_case_manifest',
                   'SOURCE_CLAUSE_OUTCOMES', 'SOURCE_CLAUSE_REOPENS', 'source_clause')
DECLARED_FUNCTION_HASHES = {
    f'{COMPLETION_STUDY}::upgrade_case_manifest': {'text_sha256': 'db52a8054061e30946756b2ce1681b6849438f605cb91b1821be29c4129e4592',
        'ast_sha256': 'fd77006c3c04d773481bf67a5f9f0fc2ee45813a9ccc3764aa0dd86b9056ae04'},
    f'{COMPLETION_STUDY}::CASE_MANIFESTS': {'text_sha256': '196327a2b9c83951d893c65025d0c2bf0fc8dccac18a5d81954eac8ae9d26467',
        'ast_sha256': 'c1a3248afecf9b08059e49f0db483fe9a383887475f49260ebee655656ff27c3'},
    f'{COMPLETION_STUDY}::DEFAULT_CASE_MANIFEST': {'text_sha256': '5adef5e2bd7a4f930af30a27b0ee81856ef882f9f33dd39b825626201dd2d265',
        'ast_sha256': 'a064c48ec6683fc153116089dc3e0a535e15fdff14ca9f5d78c4917b7c0ff7fa'},
    f'{COMPLETION_STUDY}::build_case_manifest': {'text_sha256': '3220e7e912dc0e9991cdc5e281d85ca460b59be72203b204e3e9ccc17fce08a5',
        'ast_sha256': 'c5df4b7969ac77cca5f065a199e75d6c575f3bd1d23e01c599cdc26971a15ac3'},
    f'{COMPLETION_STUDY}::SOURCE_CLAUSE_OUTCOMES': {'text_sha256': 'fb2a8d3622a4da6062b6a95fc42eaebf874804c60cb2a3d349149efde17a3332',
        'ast_sha256': '2755d2b9998c03adc7ad6cec5a643f998d41771646fe3fceae3af546eb8b25be'},
    f'{COMPLETION_STUDY}::SOURCE_CLAUSE_REOPENS': {'text_sha256': '555796149da78128f156077dd0238f6db4e29c4a4e1c96672bf345013ccf4a7e',
        'ast_sha256': '74874e9a5723a81f6873f2404e08a738fba1aa2f0f7e2c2307b082d00536165c'},
    f'{COMPLETION_STUDY}::source_clause': {'text_sha256': '4f3468cd4a904aa567e74201f68a9579c09f9f28e1557e32b0fb8db6ec78f4b9',
        'ast_sha256': '51d5b4c394a788127968e5d8e6d9ce3a488775bcf1ff0852542cbf4d1402c42e'},
}
# Known now and declared UNCHANGED, so they are pinned now: an edit to any of these files then fails the
# run instead of being re-pinned at the freeze.
DECLARED_SETTINGS_SHA256 = '1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d'  # settings-phase17.json
DECLARED_MECHANIC_BRIEF_SHA256 = 'e3b9362f281e1616fea7013fb3d9b7cf85432884f726a95cde39e4a9dadd1673'  # completion.md
DECLARED_BASE_RUNNER_SHA256 = '07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342'  # run_full_loop.py
DECLARED_FIXED_RUNNER_SHA256 = '95ef698d155986c209e1138d169b1bbb342656dd13152db457ff2185a5ff09d1'  # run_full_loop_fixed_n.py
DECLARED_SLOT2_PROBE_SHA256 = '28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0'  # slot2_probe.py
DECLARED_GATE_FREEZE_SCRIPT_SHA256 = '5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190'  # gate_freeze.py
DECLARED_DRIFT_CHECKER_SHA256 = 'fa25ab9d38ed1287ff530751a4157eedffb8a0692e756bce0edef64133ae956a'  # check_clock_drift.py
DECLARED_INGESTION_CHECK_SHA256 = 'edde0190836898e2a301aadbb16906ded3ae20a5f51cd51bd4c4ee7266313c02'  # check_ingestion_health.py
DECLARED_LAUNCHER_SHA256 = '78911a293492b803d6c688a6044cf6e578e2b1bd6b5ccd93c65029f42aca9827'  # phase17 launch_backend.py
PINS = ('DECLARED_MANIFEST_HASH', 'DECLARED_FREEZE_SHA256', 'DECLARED_CONFIGURATION_HASH',
        'DECLARED_SETTINGS_SHA256', 'DECLARED_MECHANIC_BRIEF_SHA256', 'DECLARED_BASE_RUNNER_SHA256',
        'DECLARED_FIXED_RUNNER_SHA256', 'DECLARED_SLOT2_PROBE_SHA256', 'DECLARED_GATE_FREEZE_SCRIPT_SHA256',
        'DECLARED_DRIFT_CHECKER_SHA256', 'DECLARED_INGESTION_CHECK_SHA256', 'DECLARED_LAUNCHER_SHA256')
FILE_PINS = ('DECLARED_FREEZE_SHA256', 'DECLARED_SETTINGS_SHA256', 'DECLARED_MECHANIC_BRIEF_SHA256',
             'DECLARED_BASE_RUNNER_SHA256', 'DECLARED_FIXED_RUNNER_SHA256', 'DECLARED_SLOT2_PROBE_SHA256',
             'DECLARED_GATE_FREEZE_SCRIPT_SHA256', 'DECLARED_DRIFT_CHECKER_SHA256',
             'DECLARED_INGESTION_CHECK_SHA256', 'DECLARED_LAUNCHER_SHA256')

Detached = base.Detached
PhaseAbort = base.PhaseAbort


def unfilled_pins():
    names = [name for name in PINS if not fixed.is_sha256(globals()[name])]
    names += [f'DECLARED_FUNCTION_HASHES[{key}].{field}' for key, value in sorted(DECLARED_FUNCTION_HASHES.items())
              for field in ('text_sha256', 'ast_sha256') if not fixed.is_sha256(value.get(field))]
    return names


def pin_files(args=None):
    """The file each file-level pin describes (the configuration and manifest hashes have no file)."""
    given = lambda name: getattr(args, name, None) if args is not None else None  # noqa: E731
    return {'DECLARED_FREEZE_SHA256': (ROOT / given('expect_freeze')) if given('expect_freeze') else None,
            'DECLARED_SETTINGS_SHA256': ROOT / (given('settings') or DEFAULT_SETTINGS),
            'DECLARED_MECHANIC_BRIEF_SHA256': ROOT / MECHANIC_BRIEF,
            'DECLARED_BASE_RUNNER_SHA256': HERE / 'run_full_loop.py',
            'DECLARED_FIXED_RUNNER_SHA256': HERE / 'run_full_loop_fixed_n.py',
            'DECLARED_SLOT2_PROBE_SHA256': HERE / 'slot2_probe.py',
            'DECLARED_GATE_FREEZE_SCRIPT_SHA256': HERE / 'gate_freeze.py',
            'DECLARED_DRIFT_CHECKER_SHA256': HERE / 'check_clock_drift.py',
            'DECLARED_INGESTION_CHECK_SHA256': HERE / 'check_ingestion_health.py',
            'DECLARED_LAUNCHER_SHA256': ROOT / LAUNCHER}


def supplementary_hashes(path=None):
    """Text and AST sha256 of the Phase 28 definitions in completion_study.py, by gate_freeze.py's method:
    sha256(ast.get_source_segment + '\\n') and sha256(ast.dump). CASE_MANIFESTS and the three constants are
    assignments. ast.dump changes with the Python version, so the pins hold only under the venv's interpreter."""
    path = pathlib.Path(path or ROOT / COMPLETION_STUDY)
    source = path.read_text(encoding='utf-8')
    found = {}
    for node in ast.parse(source).body:
        names = [node.name] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else [
            t.id for t in getattr(node, 'targets', []) if isinstance(t, ast.Name)]
        for name in names:
            segment = ast.get_source_segment(source, node)
            found[f'{COMPLETION_STUDY}::{name}'] = {
                'text_sha256': hashlib.sha256((segment + '\n').encode('utf-8')).hexdigest(),
                'ast_sha256': hashlib.sha256(ast.dump(node).encode('utf-8')).hexdigest()}
    return {key: found.get(key, {'missing': True}) for key in DECLARED_FUNCTION_HASHES}


def builder_manifest_hash():
    """content_hash of the backend builder's 'upgrade-v1' manifest, from the code on disk ($0, no settings)."""
    from app.contracts.models import content_hash
    from app.lab.completion_study import build_case_manifest
    return content_hash(build_case_manifest(CASE_MANIFEST_ID))


def pin_status(args=None):
    """Read-only: every pin, its declared value and whether the code or file on disk matches it."""
    files = pin_files(args)
    rows = []
    for name in PINS:
        declared = globals()[name]
        path = files.get(name)
        current = base.sha256_file(path) if path is not None and pathlib.Path(path).is_file() else None
        if name == 'DECLARED_MANIFEST_HASH':
            try:
                current = builder_manifest_hash()
            except Exception as error:  # noqa: BLE001
                current = None
                state = f'builder unavailable ({type(error).__name__})'
        if not fixed.is_sha256(declared):
            state = 'UNFILLED'
        elif name == 'DECLARED_CONFIGURATION_HASH':
            state = 'pinned (checked against the backend at the first campaign)'
        elif name == 'DECLARED_MANIFEST_HASH':
            state = ('MATCH' if current == declared else 'DIFFERS') if current else state
        elif path is None:
            state = 'pinned (no file given)'
        elif current is None:
            state = 'FILE MISSING'
        else:
            state = 'MATCH' if current == declared else 'DIFFERS'
        rows.append({'pin': name, 'declared': declared, 'file': str(path) if path else None, 'current': current,
                     'state': state})
    try:
        on_disk = supplementary_hashes()
    except OSError:
        on_disk = {}
    for key, declared in sorted(DECLARED_FUNCTION_HASHES.items()):
        current = on_disk.get(key) or {}
        for field in ('text_sha256', 'ast_sha256'):
            value = declared.get(field)
            state = ('UNFILLED' if not fixed.is_sha256(value) else
                     'MATCH' if current.get(field) == value else 'DIFFERS')
            rows.append({'pin': f'{key.split("::")[1]}.{field}', 'declared': value, 'file': COMPLETION_STUDY,
                         'current': current.get(field), 'state': state})
    return rows


def plan():
    """The canonical launch plan: design constants, pins, models, protocols, project and every declared rule.
    It holds no protocol sha, no runner sha and no review-record sha, and it is built without reading the
    protocol, so editing the protocol never moves it."""
    return {'schema_version': SCHEMA, 'phase': 28,
            'design': {'n_attempts': N_ATTEMPTS, 'spend_cap': SPEND_CAP, 'headroom': HEADROOM, 'breaker': BREAKER,
                       'futility_look_d': FUTILITY_LOOK_D, 'final_stops': list(FINAL_STOPS),
                       'phase_prefix': PHASE_PREFIX, 'manifest_name': MANIFEST_NAME, 'protocol': PROTOCOL,
                       'case_manifest_id': CASE_MANIFEST_ID, 'source_case': SOURCE_CASE,
                       'control_case': CONTROL_CASE, 'fresh_gain_min': FRESH_GAIN_MIN},
            'rules': {'certification': CERTIFICATION_RULE, 'futility_look': FUTILITY_RULE,
                      'look_precedence': LOOK_PRECEDENCE, 'stop_rule': STOP_RULE, 'routing': ROUTING_REASON,
                      'scope_sentence': SCOPE_SENTENCE, 'predicates': PREDICATES,
                      'phase28a_precondition': PHASE28A_RULE, 's2u_definition': S2U_DEFINITION},
            'models': {'actor': base.EXPECTED_ACTOR, 'mechanic': base.EXPECTED_MECHANIC},
            'protocols': {'actor_context': base.ACTOR_CONTEXT, 'evidence': base.EVIDENCE_PROTOCOL},
            'project': base.EXPECTED_PROJECT,
            'gate': {'assess_pairs_key': base.ASSESS_PAIRS_KEY,
                     'assess_pairs_text_sha256': base.ASSESS_PAIRS_TEXT_SHA256, 'scorer_hash': SCORER_HASH,
                     'unchanged_functions': {k: list(v) for k, v in UNCHANGED_FUNCTIONS.items()}},
            'pins': {**{name: globals()[name] for name in PINS},
                     'DECLARED_FUNCTION_HASHES': DECLARED_FUNCTION_HASHES},
            'prior': {'attempts': PRIOR_ATTEMPTS, 'certified': PRIOR_CERTIFIED,
                      'certified_policies': list(PRIOR_CERTIFIED_POLICIES)}}


def plan_hash(value=None):
    text = json.dumps(plan() if value is None else value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------- step predicates (pure)

def upgrade_retry_steps(content):
    """Every orders re-send step: its rule's hook and when, the step's only_if, and a static label.
    A step whose gates include current_operation_pending cannot run after a transient failure, because the
    status then reads UNKNOWN (pitfall 77, the upgrade-side twin)."""
    steps = []
    for rule in (content or {}).get('rules') or []:
        for step in rule.get('steps') or []:
            if step.get('op') == 'retry_original_request' and step.get('service') == 'orders':
                gates = {rule.get('when'), step.get('only_if')}
                label = ('cannot fire after a transient failure' if 'current_operation_pending' in gates
                         else 'can fire' if gates <= FIRING_GATES else 'unclear')
                steps.append({'hook': rule.get('hook'), 'when': rule.get('when'), 'only_if': step.get('only_if'),
                              'label': label})
    return steps


def contains_upgrade_retry(content):
    return bool(upgrade_retry_steps(content))


def _payload(event):
    return event.get('payload') or {}


def upgrade_retry_fired(events):
    """The policy itself dispatched update_order (business_tools.py): the re-send reached the broker."""
    return any(e.get('type') == 'tool_dispatched' and _payload(e).get('caller') == 'policy'
               and _payload(e).get('tool') == 'update_order' for e in events)


def actor_resend_episode(events):
    """The Actor re-sent the upgrade itself: two or more LOGICAL calls. The adapter emits one event per HTTP
    attempt and makes two attempts per call, so counting events would count every F4 episode (R1-7)."""
    return len({e.get('call_id') for e in events if e.get('type') == 'tool_dispatched'
                and _payload(e).get('caller') == 'actor' and _payload(e).get('tool') == 'update_order'}) >= 2


def rules_ran(events):
    """At least one policy step executed (pitfall 79: executed true, not steps listed)."""
    return any(e.get('type') == 'policy_step' and _payload(e).get('executed') is True for e in events)


# ---------------------------------------------------------------- certification (pure)

def source_completions(validation_assessment):
    counts = ((validation_assessment or {}).get('by_case') or {}).get(SOURCE_CASE) or {}
    return (counts.get('L') or {}).get('completed')


def fresh_case_gain(validation_assessment):
    """Per case, never summed: two +1s can both be baseline lapses (pitfall 73)."""
    return any(gain >= FRESH_GAIN_MIN for case, gain in base.case_gains(validation_assessment).items()
               if case not in (SOURCE_CASE, CONTROL_CASE))


def identity_problems(study):
    problems = []
    if study.get('actor_context_protocol') != base.ACTOR_CONTEXT:
        problems.append(f'actor_context_protocol={study.get("actor_context_protocol")!r}')
    if study.get('evidence_protocol') != base.EVIDENCE_PROTOCOL:
        problems.append(f'evidence_protocol={study.get("evidence_protocol")!r}')
    if study.get('replay_of') is not None:
        problems.append(f'replay_of={study.get("replay_of")!r}')
    if study.get('case_manifest_id') != CASE_MANIFEST_ID:
        problems.append(f'case_manifest_id={study.get("case_manifest_id")!r}')
    if study.get('manifest_hash') != DECLARED_MANIFEST_HASH:
        problems.append(f'manifest_hash={study.get("manifest_hash")!r}')
    return problems


def verify_study_identity(study, *, when):
    problems = identity_problems(study)
    if problems:
        raise PhaseAbort(f'{when}: study {study.get("study_id")} is not the declared study: ' + ', '.join(problems))


def integrity_problem(study):
    """Condition 4: the backend's source_clause means a stored OBSERVED_IMPROVEMENT always has the source 3 of 3.
    One that does not is an integrity failure, never a certification."""
    va = study.get('validation_assessment') or {}
    if 'OBSERVED_IMPROVEMENT' in (study.get('decision'), va.get('decision')) and source_completions(va) != 3:
        return (f'integrity failure: study {study.get("study_id")} is stored OBSERVED_IMPROVEMENT but the candidate '
                f'completed {SOURCE_CASE} {source_completions(va)!r} of 3 in validation (condition 4)')
    return None


def unreported_integrity_failures(manifest):
    """Integrity failures on record that no recorded stop names yet. Condition 4 makes each one an abort of its own.
    recover() can find one after another stop (a signal, lost contact), where it would otherwise sit in its row while
    the recorded stop still named the earlier cause; the runner then records it as the abort before anything goes on,
    so the next --after-abort is an informed approval (review round 1)."""
    named = [manifest.get('abort_detail')] + [r.get('reason') for r in manifest.get('resume_refusals') or []]
    for session in manifest.get('sessions') or []:
        named += [session.get('abort_detail'), session.get('previous_abort_detail')]
    named = [text for text in named if isinstance(text, str)]
    return [row['integrity_failure'] for row in manifest.get('attempts') or []
            if row.get('integrity_failure') and not any(row['integrity_failure'] in text for text in named)]


def integrity_abort_detail(found, earlier=None):
    return '; '.join(found) + (f' (found when its study was recovered, after the earlier stop: {earlier})' if earlier
                               else ' (found when its study was recovered)')


def certified(study):
    va = study.get('validation_assessment') or {}
    return (not identity_problems(study) and study.get('decision') == 'OBSERVED_IMPROVEMENT'
            and va.get('decision') == 'OBSERVED_IMPROVEMENT' and fresh_case_gain(va)
            and source_completions(va) == 3)


def summarize_study(study):
    """Everything the declared read-outs need, taken only from the saved study record."""
    candidates = []
    for index, attempt in enumerate(study.get('candidates') or []):
        content = attempt.get('content')
        source = ((attempt.get('source_assessment') or {}).get('by_case') or {}).get(SOURCE_CASE) or {}
        candidates.append({'slot': index + 1, 'decision': attempt.get('decision'),
                           'policy_hash': attempt.get('policy_hash'),
                           'contains_upgrade_retry': contains_upgrade_retry(content),
                           'upgrade_retry_steps': upgrade_retry_steps(content),
                           'contains_notification_step': base.contains_step(content),
                           'source_decision': (attempt.get('source_assessment') or {}).get('decision'),
                           'source_b0_completed': (source.get('B0') or {}).get('completed')})
    va = study.get('validation_assessment') or {}
    return {
        'status': study.get('status'), 'decision': study.get('decision'), 'reason': study.get('reason'),
        'error_type': study.get('error_type'), 'control_operation': study.get('control_operation'),
        'stage': study.get('stage'), 'control_assessment': study.get('control_assessment'),
        # Phase 9 rule: a refusal or an invalid first proposal is a draw WITHOUT the step;
        # only "no proposal requested" is no draw at all.
        'first_proposal_drawn': bool(candidates),
        'first_proposal_contains_upgrade_retry': candidates[0]['contains_upgrade_retry'] if candidates else None,
        'candidates': candidates,
        'selected_candidate_hash': study.get('selected_candidate_hash'),
        'validation_decision': va.get('decision'), 'validation_reason': va.get('reason'),
        'source_clause_case': va.get('source_clause_case'),
        'case_gains': base.case_gains(va) if va else None,
        'fresh_case_gain': fresh_case_gain(va) if va else None,
        'source_completed_in_validation': source_completions(va) if va else None,
        'certified': certified(study),
        'evidence_reads': len(study.get('evidence') or {}),
        'evidence_rereads': [{k: r.get(k) for k in ('stage', 'first_error_code', 'result')}
                             for r in study.get('evidence_rereads') or []],
        'retained_invalid': len(study.get('retained_invalid_slots') or []),
        'trials': len(study.get('trial_rows') or []),
        'actor_context_protocol': study.get('actor_context_protocol'),
        'evidence_protocol': study.get('evidence_protocol'),
        'case_manifest_id': study.get('case_manifest_id'),
        'manifest_hash': study.get('manifest_hash'),
    }


# ---------------------------------------------------------------- the funnel (read-only store reads)

def rejection_case(va, cases):
    """The case a validation NO_CHANGE was decided on, replaying assess_pairs' order (descriptive)."""
    if va.get('decision') != 'NO_CHANGE':
        return None
    by = va.get('by_case') or {}
    if va.get('source_clause_case'):
        return va['source_clause_case']
    if va.get('reason') == CANDIDATE_CHECK:
        return ','.join(c['case_id'] for c in cases if ((by.get(c['case_id']) or {}).get('L') or {}).get('violations')) \
            or 'candidate check failure'
    if va.get('reason') == CLAUSE_REASON:
        return CONTROL_CASE
    if va.get('reason') == REGRESSED:
        for case in cases:
            counts = by.get(case['case_id']) or {}
            key = OUTCOME_KEYS.get(case.get('expected_outcome'))
            if key and (counts.get('L') or {}).get(key, 0) < (counts.get('B0') or {}).get(key, 0):
                return case['case_id']
    if va.get('reason') == NO_GAIN:
        return 'no strict gain'
    return None


def attempt_funnel(db, study):
    """The per-attempt stage funnel, from the saved study record and the events table only."""
    rows = study.get('trial_rows') or []
    cases = (study.get('manifest') or {}).get('cases') or []
    by_id = {c['case_id']: c for c in cases}
    wanted = [r['trial']['episode_id'] for r in rows
              if r['trial'].get('arm') == 'L' or (r.get('case_id') == SOURCE_CASE and r.get('stage') != 'validation')]
    events = fixed.episode_events(db, wanted)

    def exercised(trials):
        return {'L_trials': len(trials),
                'rules_ran_in': sum(1 for t in trials if rules_ran(events.get(t['episode_id'], []))),
                'upgrade_retry_fired_in': sum(1 for t in trials if upgrade_retry_fired(events.get(t['episode_id'], []))),
                'notification_step_fired_in': sum(1 for t in trials if fixed.step_fired(events.get(t['episode_id'], [])))}

    candidates = []
    for slot, candidate in enumerate(study.get('candidates') or [], start=1):
        content = candidate.get('content')
        sa = candidate.get('source_assessment') or {}
        source = (sa.get('by_case') or {}).get(SOURCE_CASE) or {}
        candidates.append({'slot': slot, 'policy_hash': candidate.get('policy_hash'), 'decision': candidate.get('decision'),
                           'upgrade_retry_present': contains_upgrade_retry(content),
                           'upgrade_retry_steps': upgrade_retry_steps(content),
                           'notification_step_present': base.contains_step(content),
                           'source_decision': sa.get('decision'),
                           'source_b0_completed': (source.get('B0') or {}).get('completed'),
                           **exercised([r['trial'] for r in rows if r.get('stage') == f'candidate-{slot}'
                                        and r['trial'].get('arm') == 'L'])})
    validation = [r for r in rows if r.get('stage') == 'validation']
    va = study.get('validation_assessment') or {}
    assessed = bool(va.get('decision'))
    invalid = sum(1 for r in validation if not fixed.valid_trial(r['trial']))
    by_case = {}
    for case_id in dict.fromkeys(r['case_id'] for r in validation):
        seen = exercised([r['trial'] for r in validation if r['case_id'] == case_id and r['trial'].get('arm') == 'L'])
        by_case[case_id] = {**seen, 'exercised': bool(seen['rules_ran_in']),
                            'counts': (va.get('by_case') or {}).get(case_id)}
    b0_source = [r['trial'] for r in rows if r.get('case_id') == SOURCE_CASE and r['trial'].get('arm') == 'B0'
                 and r.get('stage') != 'validation']
    valid_b0 = [t for t in b0_source if fixed.valid_trial(t)]
    # S4 exactly as Phase 17 declared it: every stage, LAB_ERROR episodes excluded.
    counted = [r for r in rows
               if r['trial'].get('lifecycle') != 'LAB_ERROR' and r['trial'].get('outcome') != 'LAB_ERROR']
    fault_bearing = [r for r in counted if r['trial'].get('fault_scheduled')]
    notification = [r for r in fault_bearing
                    if any(p.get('target_service') == 'notifications'
                           for p in ((by_id.get(r['case_id']) or {}).get('fault_spec') or {}).get('primitives') or [])]
    return {'candidates': candidates,
            'validation': {'trials': len(validation), 'invalid_trials': invalid, 'assessed': assessed,
                           # clean = an assessed batch with zero invalid trials (Phase 15's split)
                           'batch': ('clean' if invalid == 0 else 'dirty') if assessed else None,
                           'decision': va.get('decision'), 'reason': va.get('reason'),
                           'source_clause_case': va.get('source_clause_case'),
                           'rejection_case': rejection_case(va, cases) if assessed else None,
                           'selected_candidate_hash': study.get('selected_candidate_hash'), 'by_case': by_case},
            'baseline_source': {'trials': len(b0_source), 'valid': len(valid_b0),
                                'completed': sum(1 for t in valid_b0 if t.get('outcome') == 'COMPLETED'),
                                'actor_resend': sum(1 for t in valid_b0
                                                    if actor_resend_episode(events.get(t['episode_id'], [])))},
            'fault_bearing': len(fault_bearing),
            'untriggered': sum(1 for r in fault_bearing if not r['trial'].get('fault_triggered')),
            'notification_fault_bearing': len(notification)}


def add_funnel(db, entry, study):
    """Derived and descriptive: a store read that fails never touches the verdict fields."""
    try:
        entry['funnel'] = attempt_funnel(db, study)
        entry.pop('funnel_error', None)
    except Exception as error:  # noqa: BLE001
        entry['funnel_error'] = type(error).__name__


# ---------------------------------------------------------------- the futility look (pure)

def distinct_valid_policies(rows):
    """{policy_hash: contains the upgrade re-send} over every candidate that became a valid policy."""
    policies = {}
    for row in rows:
        for candidate in row.get('candidates') or []:
            if candidate.get('policy_hash'):
                policies.setdefault(candidate['policy_hash'], bool(candidate.get('contains_upgrade_retry')))
    return policies


def first_look_attempt(rows, d=None):
    """The first attempt number j at which rows[:j] hold D >= d distinct valid policies, or None (reconcile)."""
    d = FUTILITY_LOOK_D if d is None else d
    policies = set()
    for index, row in enumerate(rows, start=1):
        policies.update(distinct_valid_policies([row]))
        if len(policies) >= d:
            return index
    return None


def futility_look(rows, existing):
    """A new look record the first time D >= FUTILITY_LOOK_D with no record yet; otherwise None."""
    if existing is not None:
        return None
    policies = distinct_valid_policies(rows)
    if len(policies) < FUTILITY_LOOK_D:
        return None
    r = sum(policies.values())
    k = sum(1 for row in rows if row.get('certified'))
    return {'attempt': len(rows), 'D': len(policies), 'R': r, 'k': k,
            'outcome': 'stop' if r == 0 and k == 0 else 'passed',
            'evaluated_at': datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- run summaries (pure)

def routing(rows, *, final):
    """Declared: no routing. The summary carries routing: null and the reason."""
    return None


def stage_funnel(rows):
    funnels = [r.get('funnel') for r in rows if r.get('funnel')]
    candidates = [c for f in funnels for c in f.get('candidates') or []]
    # A within-study DUPLICATE is the same policy again and gets no source trials (completion_study._execute), so it is
    # neither a new step candidate nor in any S2u denominator; it is counted on its own (S2U_DEFINITION, round 1).
    with_step = [c for c in candidates if c.get('upgrade_retry_present')]
    duplicates = [c for c in with_step if c.get('decision') == 'DUPLICATE']
    step = [c for c in with_step if c.get('decision') != 'DUPLICATE']
    tested = [c for c in step if c.get('source_decision')]
    complete = [c for c in tested if c['source_decision'] in ('SOURCE_QUALIFIED', 'NO_CHANGE')]
    validation = [f.get('validation') or {} for f in funnels]
    assessed = [v for v in validation if v.get('assessed')]
    clean = [v for v in assessed if v.get('batch') == 'clean']
    dirty = [v for v in assessed if v.get('batch') == 'dirty']
    controls = [r for r in rows if r.get('stage') == 'controls' and r.get('decision') == 'NO_CHANGE']

    def control_cause(row):
        a = row.get('control_assessment') or {}
        causes = []
        if (a.get('valid_source') or 0) < 2 or (a.get('valid_healthy') or 0) < 2:
            causes.append('too_few_valid_controls')
        if (a.get('source_completions') or 0) > 0:
            causes.append('source_leak')
        if (a.get('healthy_completions') or 0) < (a.get('valid_healthy') or 0):
            causes.append('healthy_lapse')
        return causes or ['unrecorded']
    policies = distinct_valid_policies(rows)
    rejected = [v for v in assessed if v.get('decision') == 'NO_CHANGE']
    reasons = {}
    for v in rejected:
        key = f"{v.get('reason')} | case: {v.get('rejection_case')}"
        reasons[key] = reasons.get(key, 0) + 1
    return {
        'attempts': len(rows),
        'studies_started': sum(1 for r in rows if r.get('study_id')),
        # Every attempt is in the denominator; these ran no study, by reason.
        'attempts_without_study': {reason: sum(1 for r in rows if not r.get('study_id')
                                               and (r.get('error') or 'no outcome recorded') == reason)
                                   for reason in sorted({r.get('error') or 'no outcome recorded'
                                                         for r in rows if not r.get('study_id')})},
        'runner_side_no_study': sum(1 for r in rows if fixed.runner_side(r)),
        'infrastructure_deaths': sum(1 for r in rows if fixed.infrastructure_death(r)),
        'controls_stops': len(controls),
        'controls_stops_by_cause': {cause: sum(1 for r in controls if cause in control_cause(r))
                                    for cause in ('source_leak', 'healthy_lapse', 'too_few_valid_controls', 'unrecorded')},
        # Phase 9 rule: a refusal or an invalid first proposal is a draw WITHOUT the step.
        'first_proposals_drawn': sum(1 for r in rows if r.get('first_proposal_drawn')),
        'first_proposals_with_upgrade_retry': sum(1 for r in rows if r.get('first_proposal_contains_upgrade_retry')),
        'distinct_valid_policies_D': len(policies),
        'distinct_with_upgrade_retry_R': sum(policies.values()),
        'candidates_with_policy': sum(1 for c in candidates if c.get('policy_hash')),
        'upgrade_retry_present': len(step),
        'upgrade_retry_within_study_duplicates': len(duplicates),
        'upgrade_retry_never_tested_at_source': len(step) - len(tested),
        'upgrade_retry_steps': [{'policy_hash': c.get('policy_hash'), 'steps': c.get('upgrade_retry_steps'),
                                 'resend_count': len(c.get('upgrade_retry_steps') or [])} for c in step],
        'upgrade_retry_tested_at_source': len(tested),
        'upgrade_retry_fired_at_source': sum(1 for c in tested if c.get('upgrade_retry_fired_in')),
        'upgrade_retry_present_never_fired_at_source': sum(1 for c in tested
                                                           if c.get('L_trials') and not c.get('upgrade_retry_fired_in')),
        'source_complete_pairs_with_retry': len(complete),
        'source_qualified_with_retry': sum(1 for c in tested if c['source_decision'] == 'SOURCE_QUALIFIED'),
        'S2u_given_complete_pairs': [sum(1 for c in complete if c['source_decision'] == 'SOURCE_QUALIFIED'), len(complete)],
        'S2u_given_step_candidates_tested': [sum(1 for c in tested if c['source_decision'] == 'SOURCE_QUALIFIED'),
                                             len(tested)],
        'S2u_definition': S2U_DEFINITION,
        'source_qualified_without_retry': sum(1 for c in candidates if not c.get('upgrade_retry_present')
                                              and c.get('source_decision') == 'SOURCE_QUALIFIED'),
        'source_gate_leaks': sum(1 for c in candidates if c.get('source_decision') == 'NO_CHANGE'
                                 and (c.get('source_b0_completed') or 0) > 0),
        'validation_reached': sum(1 for r in rows if r.get('stage') == 'validation'),
        'validation_assessed': len(assessed),
        'validation_clean': len(clean),
        'validation_dirty': len(dirty),
        'accepted_on_clean': sum(1 for v in clean if v.get('decision') == 'OBSERVED_IMPROVEMENT'),
        'accepted_on_dirty': sum(1 for v in dirty if v.get('decision') == 'OBSERVED_IMPROVEMENT'),
        'accepted_on_dirty_note': 'zero by construction: assess_pairs returns INCOMPLETE on any invalid trial (pitfall 72)',
        'rejection_reasons': reasons,
        'rejected_by_transposed_source_clause': sum(1 for v in assessed if v.get('source_clause_case') == SOURCE_CASE),
        'rejected_by_transposed_source_clause_wording': (
            "Phase 17's gate would also have returned NO_CHANGE: the candidate completed the source fewer than 3 of 3"),
        'validation_upgrade_retry_fired_in': sum((c.get('upgrade_retry_fired_in') or 0)
                                                 for v in validation for c in (v.get('by_case') or {}).values()),
        'observed_improvement': sum(1 for r in rows if r.get('decision') == 'OBSERVED_IMPROVEMENT'),
        'observed_improvement_not_certified': [
            {'attempt': r['attempt'], 'study_id': r.get('study_id'),
             'statement': 'store says OBSERVED_IMPROVEMENT; not certified (no fresh gain)'
             if not r.get('integrity_failure') and r.get('fresh_case_gain') is False else
             'store says OBSERVED_IMPROVEMENT; not certified'}
            for r in rows if r.get('decision') == 'OBSERVED_IMPROVEMENT' and not r.get('certified')],
        'integrity_failures': [{'attempt': r['attempt'], 'study_id': r.get('study_id'), 'detail': r['integrity_failure']}
                               for r in rows if r.get('integrity_failure')],
        'certified': sum(1 for r in rows if r.get('certified')),
        'funnel_unavailable': sum(1 for r in rows if r.get('study_id') and not r.get('funnel')),
    }


def guards_exercised(rows):
    """For every validation-reaching candidate, by case: L and B0 counts, L trials in which a rule ran and in
    which the policy dispatched update_order. A guard where no rule ran is 'not exercised' for it."""
    table = []
    for row in rows:
        validation = (row.get('funnel') or {}).get('validation') or {}
        if not validation.get('trials'):
            continue
        cases = {}
        for case_id, seen in (validation.get('by_case') or {}).items():
            counts = seen.get('counts') or {}
            cases[case_id] = {'L': counts.get('L'), 'B0': counts.get('B0'), 'rules_ran_in': seen.get('rules_ran_in'),
                              'upgrade_retry_fired_in': seen.get('upgrade_retry_fired_in'),
                              'label': 'exercised' if seen.get('exercised') else 'not exercised'}
        table.append({'attempt': row['attempt'], 'policy_hash': validation.get('selected_candidate_hash'),
                      'decision': validation.get('decision'), 'certified': bool(row.get('certified')), 'cases': cases})
    return table


def hash_accounting(rows):
    """Distinct policies, not proposals (pitfall 29); same-policy re-draws across studies are counted."""
    draws = [{'attempt': r['attempt'], 'slot': c.get('slot'), 'policy_hash': c.get('policy_hash'),
              'decision': c.get('decision'), 'source_decision': c.get('source_decision'),
              'upgrade_retry': bool(c.get('contains_upgrade_retry')),
              'notification_step': bool(c.get('contains_notification_step'))}
             for r in rows for c in r.get('candidates') or [] if c.get('policy_hash')]
    by_hash = {}
    for draw in draws:
        by_hash.setdefault(draw['policy_hash'], []).append(draw)
    certified_rows = [{'attempt': r['attempt'], 'policy_hash': r.get('selected_candidate_hash')}
                      for r in rows if r.get('certified')]
    return {'draws': len(draws),
            'distinct_policies': len(by_hash),
            'distinct_first_proposals': len({d['policy_hash'] for d in draws if d['slot'] == 1}),
            'distinct_with_upgrade_retry': len({h for h, ds in by_hash.items() if ds[0]['upgrade_retry']}),
            'within_study_duplicates': sum(1 for d in draws if d['decision'] == 'DUPLICATE'),
            'redrawn_across_attempts': {h: sorted({d['attempt'] for d in ds}) for h, ds in sorted(by_hash.items())
                                        if len({d['attempt'] for d in ds}) > 1},
            'attempts_per_policy': {h: sorted({d['attempt'] for d in ds}) for h, ds in sorted(by_hash.items())},
            'certified_in_order': certified_rows,
            'distinct_certified_policies': len({c['policy_hash'] for c in certified_rows}),
            'both_sides_policies': sorted(h for h, ds in by_hash.items()
                                          if ds[0]['upgrade_retry'] and ds[0]['notification_step']),
            'redraws_of_prior_certified': {h: sorted({d['attempt'] for d in by_hash[h]})
                                           for h in PRIOR_CERTIFIED_POLICIES if h in by_hash}}


def prior_existence(db, hashes, started_at):
    """Read-only, at report time: whether each certified hash existed in the store before the run began."""
    if not hashes:
        return {}
    policies = base.store_records(db, 'policies')
    earliest = {}
    for policy in policies.values():
        value = policy.get('policy_hash')
        if value in hashes:
            created = policy.get('created_at') or ''
            earliest[value] = min(earliest.get(value, created), created)
    return {h: bool(earliest.get(h)) and earliest[h] < (started_at or '') for h in sorted(hashes)}


def primary_statement(k, n, stop_reason, abort_detail=None, distinct=None):
    lo, hi = fixed.wilson(k, n)
    interval = f'Wilson 95% [{lo:.3f}, {hi:.3f}]' if n else 'no interval'
    core = f'{k} of {n} attempts produced a certified upgrade-side completion repair ({interval})'
    if stop_reason == 'fixed_n':
        text = core + '.'
    elif stop_reason == 'futility':
        text = (f'Stopped for futility at n = {n}: 0 of {distinct} distinct Mechanic policies re-sent the upgrade; '
                f'{core}.')
    elif stop_reason == 'spend_guard':
        text = f'Truncated at n={n} by the ${SPEND_CAP:.0f} spend guard: {core}.'
    elif stop_reason == 'breaker':
        text = (f'Stopped at n={n} after {BREAKER} consecutive infrastructure failures: {core} up to that point. '
                f'This is not a finding about the loop.')
    elif stop_reason == 'aborted':
        text = (f'Stopped at n={n} because {abort_detail or "of an abort"}: {core} up to that point. '
                f'This is not a finding about the loop.')
    else:
        text = f'Run not finished ({stop_reason}): {core} so far.'
    return f'{text} {SCOPE_SENTENCE}'


def summarize_upgrade(rows, *, stop_reason, abort_detail=None, total_charged=None, look=None, db=None,
                      started_at=None):
    """Every declared read-out, from the attempt rows (and, for one descriptive field, a read-only store query)."""
    n = len(rows)
    k = sum(1 for r in rows if r.get('certified'))
    fault_bearing = sum((r.get('funnel') or {}).get('fault_bearing') or 0 for r in rows)
    untriggered = sum((r.get('funnel') or {}).get('untriggered') or 0 for r in rows)
    notification = sum((r.get('funnel') or {}).get('notification_fault_bearing') or 0 for r in rows)
    baseline = [(r.get('funnel') or {}).get('baseline_source') or {} for r in rows]
    valid_b0 = sum(b.get('valid') or 0 for b in baseline)
    leaked = sum(b.get('completed') or 0 for b in baseline)
    resend = sum(b.get('actor_resend') or 0 for b in baseline)
    lo, hi = fixed.wilson(k, n)
    policies = distinct_valid_policies(rows)
    accounting = hash_accounting(rows)
    certified_hashes = {c['policy_hash'] for c in accounting['certified_in_order'] if c['policy_hash']}
    try:
        existed = prior_existence(db, certified_hashes, started_at) if db else None
    except Exception as error:  # noqa: BLE001
        existed = {'error': type(error).__name__}
    accounting['certified_hash_existed_before_run'] = existed
    return {
        'primary': {'certified': k, 'attempts': n, 'planned': N_ATTEMPTS, 'rate': k / n if n else None,
                    'wilson95': [lo, hi], 'truncated': n < N_ATTEMPTS and stop_reason != 'futility',
                    'stop_reason': stop_reason,
                    'statement': primary_statement(k, n, stop_reason, abort_detail,
                                                   distinct=(look or {}).get('D', len(policies)))},
        'scope_sentence': SCOPE_SENTENCE,
        'secondary_cumulative': {
            'statement': (f'{k + PRIOR_CERTIFIED} certified completion repairs in {n + PRIOR_ATTEMPTS} attempts across '
                          f'Phases 17, 23 and 28'),
            'certified': k + PRIOR_CERTIFIED, 'attempts': n + PRIOR_ATTEMPTS,
            'caveat': ('Phases 17 and 23 used the notification source and Phase 28 the upgrade source, so this is a '
                       "count required by Phase 17's rule, not a rate."),
            'rate': None},
        'certified_attempts': [r['attempt'] for r in rows if r.get('certified')],
        'futility_look': look,
        'funnel': stage_funnel(rows),
        'distinct_hashes': accounting,
        'guards_exercised': guards_exercised(rows),
        'routing': routing(rows, final=stop_reason in FINAL_STOPS),
        'routing_reason': ROUTING_REASON,
        'untriggered': {'fault_bearing_episodes': fault_bearing, 'untriggered': untriggered,
                        'rate': untriggered / fault_bearing if fault_bearing else None,
                        'wilson95': list(fixed.wilson(untriggered, fault_bearing)),
                        'notification_fault_episodes': notification,
                        'definition': ('per fault-bearing episode, all stages, LAB_ERROR excluded (Phase 17 S4); every '
                                       'fault here is upgrade-side, so it is not comparable with Phase 17 or 23')},
        'baseline_leak_on_source': {'valid_b0_trials': valid_b0, 'completed': leaked,
                                    'rate': leaked / valid_b0 if valid_b0 else None,
                                    'wilson95': list(fixed.wilson(leaked, valid_b0)),
                                    'actor_resend_episodes': resend,
                                    'definition': ('B0 trials on upgrade-3 at controls and source gates; an Actor '
                                                   're-send is >= 2 distinct update_order call_ids')},
        'evidence': {'reads': sum(r.get('evidence_reads') or 0 for r in rows),
                     'rereads': sum(len(r.get('evidence_rereads') or []) for r in rows),
                     'rereads_verified': sum(1 for r in rows for e in r.get('evidence_rereads') or []
                                             if e.get('result') == 'VERIFIED')},
        'cost': {'total_charged_upper_bound': total_charged,
                 'per_attempt': total_charged / n if total_charged is not None and n else None,
                 'per_certification': total_charged / k if total_charged is not None and k else None},
    }


# ---------------------------------------------------------------- fixed-N reconcile (read-only)

def expected_certified(row, study):
    """A post-finish check that failed, or an integrity failure, makes the row not certified."""
    return (certified(study) and not str(row.get('post_checks') or '').startswith('failed')
            and not row.get('integrity_failure'))


def reconcile(manifest, db):
    """Read-only. Attempts are numbered 1..n with n <= the fixed N; every manifest study exists once in the
    store with the recorded outcome, candidates and selection, and is terminal; the futility-look record exists at
    the first attempt where the rows reach the threshold (once the run went past it or ended final), recomputes,
    and nothing ran after a futility stop; no full study started inside the run window is missing.
    'futility', 'fixed_n' and 'spend_guard' are final: the window closes at the run's end. A final stop whose last
    session never ended is itself a problem (review round 3): its end fields are missing or an earlier session's until
    the refused resume writes them. Returns (problems, untracked)."""
    studies = base.store_records(db, 'completion_studies')
    rows = manifest['attempts']
    problems = []
    design = ((manifest.get('declared') or {}).get('plan') or {}).get('design') or {}
    declared_n = design.get('n_attempts', N_ATTEMPTS)
    declared_d = design.get('futility_look_d', FUTILITY_LOOK_D)
    numbers = [r.get('attempt') for r in rows]
    if numbers != list(range(1, len(rows) + 1)):
        problems.append(f'attempt numbers are not 1..{len(rows)}')
    if len(rows) > declared_n:
        problems.append(f'{len(rows)} attempts recorded; the fixed N is {declared_n}')
    for key in ('study_id', 'campaign_id'):
        values = [r.get(key) for r in rows if r.get(key)]
        if len(values) != len(set(values)):
            problems.append(f'a {key} appears in more than one attempt')
    listed = {r['study_id'] for r in rows if r.get('study_id')}
    for row in rows:
        study = studies.get(row.get('study_id')) if row.get('study_id') else None
        if row.get('study_id') and study is None:
            problems.append(f"attempt {row['attempt']}: {row['study_id']} in manifest, not in store"); continue
        if study is None:
            continue
        if study.get('campaign_id') != row.get('campaign_id'):
            problems.append(f"attempt {row['attempt']}: campaign differs")
        if study.get('status') not in base.TERMINAL:
            problems.append(f"attempt {row['attempt']}: {row['study_id']} is still {study.get('status')}")
        for key in ('status', 'decision', 'selected_candidate_hash', 'case_manifest_id'):
            if row.get(key) != study.get(key):
                problems.append(f"attempt {row['attempt']}: {key} manifest={row.get(key)!r} store={study.get(key)!r}")
        stored = [c.get('policy_hash') for c in study.get('candidates') or []]
        if [c.get('policy_hash') for c in row.get('candidates') or []] != stored:
            problems.append(f"attempt {row['attempt']}: candidate policy hashes differ from the store")
        if bool(row.get('certified')) != expected_certified(row, study):
            problems.append(f"attempt {row['attempt']}: certified manifest={bool(row.get('certified'))} "
                            f"store={expected_certified(row, study)}")
    look = manifest.get('futility_look')
    # The look is the phase's only interim stop, so its existence is checked too (review round 1): once the rows reach
    # D >= the declared threshold at attempt j, a run that went past j, or ended final, must hold a look evaluated at
    # exactly j. A run that stopped early AT j may not have one yet: resume evaluates it before anything else.
    crossing = first_look_attempt(rows, declared_d)
    if crossing is not None and (len(rows) > crossing or manifest.get('stop_reason') in FINAL_STOPS):
        if look is None:
            problems.append(f'the rows reach D >= {declared_d} at attempt {crossing}, but there is no futility look record')
        elif look.get('attempt') != crossing:
            problems.append(f"the futility look was evaluated at attempt {look.get('attempt')}, not at attempt {crossing} "
                            f"where the rows first reach D >= {declared_d}")
    if look is not None:
        seen = rows[:look.get('attempt') or 0]
        policies = distinct_valid_policies(seen)
        again = {'D': len(policies), 'R': sum(policies.values()), 'k': sum(1 for r in seen if r.get('certified'))}
        if any(look.get(key) != value for key, value in again.items()) or look.get('D', 0) < declared_d:
            problems.append(f'futility look record {({k: look.get(k) for k in again})} does not recompute ({again})')
        if look.get('outcome') != ('stop' if again['R'] == 0 and again['k'] == 0 else 'passed'):
            problems.append(f"futility look outcome {look.get('outcome')!r} does not follow from R and k")
        if look.get('outcome') == 'stop' and len(rows) > (look.get('attempt') or 0):
            problems.append(f"{len(rows) - look['attempt']} attempts ran after the futility stop at n = {look['attempt']}")
    if manifest.get('stop_reason') == 'futility' and (look or {}).get('outcome') != 'stop':
        problems.append("stop_reason is 'futility' without a stopping look record")
    sessions = manifest.get('sessions') or []
    if manifest.get('stop_reason') in FINAL_STOPS and sessions and not sessions[-1].get('ended_at'):
        # Review round 3 (R3-1): the runner died after a final stop and before the session's end save, so the record's
        # end time, total, summary and drift result are missing or an EARLIER session's, and the window below would
        # close at the wrong time. The resume writes them (futility_write_up); until then nothing here can be trusted.
        problems.append("the last session never ended (the runner died after a final stop): run the resume command "
                        "once (it refuses a final stop and first writes the session's end fields, protocol section "
                        "6.3), then reconcile again")
    started = manifest.get('started_at') or ''
    # A finished run's window closes at its end, so a later phase's studies are not "untracked".
    ended = manifest.get('ended_at') if manifest.get('stop_reason') in FINAL_STOPS else None
    untracked = sorted(sid for sid, s in studies.items()
                       if s.get('replay_of') is None and s.get('created_at', '') >= started
                       and (ended is None or s.get('created_at', '') <= ended) and sid not in listed)
    return problems, untracked


# ---------------------------------------------------------------- launch gates

def paid_run_blockers(reader=None):
    """Another process launched as a paid experiment run (slot2_probe's token rule), excluding this process,
    its ancestors and its descendants (its own caffeinate helper). Fail closed."""
    return slot2_probe.live_experiment_processes(reader)


def status_block(protocol_text):
    lines = []
    for line in protocol_text.splitlines():
        if line.startswith('## '):
            break
        lines.append(line)
    return '\n'.join(lines)


def phase28a_problem(entry):
    """PHASE28A_RULE, checked on disk ($0, read-only): the review record names a final Phase 28a run whose read-outs
    say GO. The build existing must not stand in for that decision (review round 1). The read-outs are the run's own
    readouts.json, or, only when the run wrote none, the declared recomputation saved beside it (review round 2)."""
    if not isinstance(entry, dict):
        return 'the review record does not name the Phase 28a run (phase28a: {run_dir, decision, readouts_sha256})'
    if entry.get('decision') != 'GO':
        return "the review record's phase28a decision is not GO"
    run_dir = entry.get('run_dir')
    parts = pathlib.PurePosixPath(run_dir).parts if isinstance(run_dir, str) else ()
    if (len(parts) != 3 or parts[0] != 'artifacts' or not parts[1].startswith(PHASE28A_PREFIX)
            or parts[1] == PHASE28A_CLAIM_DIR or parts[2] in ('.', '..')):
        return 'phase28a.run_dir is not a run directory artifacts/phase28a-<date>/<name>'
    own = f'{run_dir}/{PHASE28A_READOUTS}'
    recheck = f'artifacts/{parts[1]}/{PHASE28A_RECHECK}'
    named = entry.get('readouts_path', own)
    if named not in (own, recheck):
        return f'phase28a.readouts_path names neither {own} nor {recheck}'
    directory = ROOT / run_dir
    try:
        manifest = json.loads((directory / PHASE28A_MANIFEST).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return f'the Phase 28a run directory {run_dir} has no readable run manifest'
    if not (isinstance(manifest, dict) and manifest.get('status') in PHASE28A_FINAL_STATUSES and manifest.get('ended_at')):
        return 'the Phase 28a run has not ended (its run manifest is not final)'
    if named == recheck and (ROOT / own).exists():
        return (f'the Phase 28a run wrote its own {PHASE28A_READOUTS}, so phase28a.readouts_path must name it, '
                'not a recomputation')
    try:
        raw = (ROOT / named).read_bytes()
        readouts = json.loads(raw)
    except (OSError, ValueError):
        return f'the Phase 28a read-outs {named} are missing or not JSON'
    if isinstance(readouts, dict) and PHASE28A_MISMATCH_KEY in readouts:
        return (f"the Phase 28a read-outs {named} are a recomputation labelled {readouts.get(PHASE28A_MISMATCH_KEY)!r} "
                "(not the run's harness or plan), never the declared read-out")
    if not (isinstance(readouts, dict) and readouts.get('schema_version') == PHASE28A_READOUT_SCHEMA
            and readouts.get('decision') == 'GO'):
        return 'the Phase 28a read-outs do not say GO'
    if entry.get('readouts_sha256') != hashlib.sha256(raw).hexdigest():
        return f'phase28a.readouts_sha256 is not the sha256 of {named}'
    return None


def review_problem(path, *, protocol_sha256, harness_sha256, plan_hash_value):
    """The review record binds a live run to what was reviewed: written by the approver when review closes,
    never by this runner. Every value is compared as a bare 64-hex string. It must also name a final Phase 28a
    run whose read-outs say GO (phase28a_problem)."""
    try:
        record = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'the review record is missing or not JSON'
    if not isinstance(record, dict):
        return 'the review record is not a JSON object'
    if record.get('status') != 'approved':
        return "the review record does not carry status 'approved'"
    approver = record.get('approved_by')
    if not (isinstance(approver, str) and approver.strip()):
        return 'the review record does not name who approved it (approved_by)'
    for key, value in (('protocol_sha256', protocol_sha256), ('harness_sha256', harness_sha256),
                       ('plan_hash', plan_hash_value), ('gate_freeze_file_sha256', DECLARED_FREEZE_SHA256),
                       ('configuration_hash', DECLARED_CONFIGURATION_HASH),
                       ('manifest_hash', DECLARED_MANIFEST_HASH)):
        if record.get(key) != value:
            return f'the review record does not carry this {key}'
    return phase28a_problem(record.get('phase28a'))


def check_launch(args):
    """Every check that needs no backend and no credential. Raises SystemExit with the first problem.
    Returns (expected_freeze, protocol_sha256, harness_sha256, plan_hash)."""
    unfilled = unfilled_pins()
    if unfilled:
        raise SystemExit(f'Refusing a live run: these pins still hold {PLACEHOLDER} and are filled only at the '
                         'Phase 28 freeze: ' + ', '.join(unfilled))
    for flag in ('settings', 'expect_freeze', 'review_record', 'expect_plan_hash', 'expect_harness_sha256',
                 'expect_protocol_sha256', 'confirm_entity'):
        if not getattr(args, flag, None):
            raise SystemExit(f'--{flag.replace("_", "-")} is required for a live run')
    harness = base.sha256_file(__file__)
    if args.expect_harness_sha256 != harness:
        raise SystemExit('--expect-harness-sha256 does not match this runner')
    protocol = ROOT / PROTOCOL
    if not protocol.is_file():
        raise SystemExit(f'No protocol at {PROTOCOL}; a live run refuses until one is reviewed')
    protocol_sha256 = base.sha256_file(protocol)
    if args.expect_protocol_sha256 != protocol_sha256:
        raise SystemExit('--expect-protocol-sha256 does not match the protocol file')
    value = plan_hash()
    if args.expect_plan_hash != value:
        raise SystemExit('The recomputed plan differs from the reviewed dry plan (--expect-plan-hash)')
    text = protocol.read_text(encoding='utf-8')
    if REVIEW_PENDING_MARKER.lower() in status_block(text).lower():
        raise SystemExit(f'The protocol status still says "{REVIEW_PENDING_MARKER}"; a live run refuses')
    line = REVIEWED_LINE.format(harness=harness, plan=value)
    if not any(candidate.strip() == line for candidate in text.splitlines()):
        raise SystemExit('The protocol has no bare "Reviewed for launch" line (no backticks, list marker or bold) '
                         'naming this harness sha256 and plan hash')
    files = pin_files(args)
    for name in FILE_PINS:
        path = files[name]
        if path is None or not pathlib.Path(path).is_file() or base.sha256_file(path) != globals()[name]:
            raise SystemExit(f'{path} is not the declared file ({name})')
    expected_freeze = json.loads((ROOT / args.expect_freeze).read_text())
    functions = expected_freeze.get('functions') or {}
    if (functions.get(base.ASSESS_PAIRS_KEY) or {}).get('text_sha256') != base.ASSESS_PAIRS_TEXT_SHA256:
        raise SystemExit('The declared freeze does not contain the unchanged assess_pairs')
    for key, (text_sha, lines) in UNCHANGED_FUNCTIONS.items():
        entry = functions.get(key) or {}
        if (entry.get('text_sha256'), entry.get('lines')) != (text_sha, lines):
            raise SystemExit(f'The declared freeze does not carry {key} unchanged, at lines {lines}')
    if (expected_freeze.get('fingerprints') or {}).get('scorer_hash') != SCORER_HASH:
        raise SystemExit('The declared freeze does not carry the unchanged scorer_hash')
    if (expected_freeze.get('files') or {}).get(MECHANIC_BRIEF) != DECLARED_MECHANIC_BRIEF_SHA256:
        raise SystemExit('The declared freeze does not carry the Phase 17 Mechanic brief (completion.md)')
    on_disk = supplementary_hashes()
    moved = sorted(key for key, value in DECLARED_FUNCTION_HASHES.items() if on_disk.get(key) != value)
    if moved:
        raise SystemExit(f'The Phase 28 definitions on disk differ from their pinned hashes: {moved}')
    problem = review_problem(ROOT / args.review_record, protocol_sha256=protocol_sha256, harness_sha256=harness,
                             plan_hash_value=value)
    if problem:
        raise SystemExit(f'Refusing a live run: {problem}')
    return expected_freeze, protocol_sha256, harness, value


def claim(out, manifest_path, manifest):
    """Create the run record exclusively, before anything slow, so two launches cannot both pass the guard."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        with open(manifest_path, 'x', encoding='utf-8') as handle:
            handle.write(json.dumps(manifest, indent=2) + '\n')
    except FileExistsError:
        raise SystemExit(f'{manifest_path} was created by another launch; refusing to overwrite it') from None
    others = [p for p in out.parent.glob(f'{PHASE_PREFIX}*/{MANIFEST_NAME}') if p != manifest_path]
    if others:
        manifest_path.unlink()
        raise SystemExit(f'Another Phase 28 run exists ({others[0]}); continue it with --resume, never in a new folder')


def write_manifest(manifest_path, manifest):
    temporary = manifest_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest, indent=2) + '\n')
    os.replace(temporary, manifest_path)


def say(*values, **kwargs):
    """print() for the abort handlers and the write-up after the main loop (review round 2, WB-1). The run record on
    disk is the result and the console only a copy of it, so a closed pipe (a dead `tee`) or a lost terminal there
    must not escape main() and cut the write-up short: the error is dropped. Inside the main loop print() is used, so
    a closed pipe there still ends the run as an abort, or, after the futility look's save, keeps the final futility
    stop with the interruption in the session record."""
    try:
        print(*values, **kwargs)
    except OSError:
        pass


FUTILITY_END_SOURCE = ("the futility look's evaluation: the session that ran the look ended before its end time was "
                       'written, and nothing runs after the look')


def futility_write_up(manifest, look, args):
    """A futility stop is final, and its look record and stop reason reach the disk in one save. A crash or signal
    after that save and before the session's last save can leave the session's end fields unwritten, and a refused
    resume would then never write them (review round 1). This writes them from the rows on record, with no new work.

    It is keyed off the LAST session (review round 2, WB-1), because the look ran in that session: nothing can start
    a session after a futility stop. If that session has no ended_at, every end field the manifest carries is either
    missing or left over from an EARLIER session of a resumed run, so all of them are rewritten, never kept:
      - total_charged_upper_bound is read again from the ledgers of every campaign on record (a read);
      - the summary is recomputed from the rows on record, with that total;
      - ended_at (the run's and the session's) is the look's own evaluation time: nothing runs after the look, so
        reconcile's window closes where the run's own studies ended, and a foreign study started in that session
        is still inside it;
      - clock_drift is marked skipped, in the run record and in the session record. Each earlier session keeps the
        drift result it wrote in its own session record.
    A session that did end keeps its fields, except that a field it never wrote is still written (the drift check,
    say, when the process died between the session's last two saves). Every field written is returned, named, and
    also recorded in the run record's futility_write_ups. Returns [] when nothing was missing."""
    written = []
    sessions = manifest.get('sessions') or []
    last = sessions[-1] if sessions else None
    open_session = last is not None and not last.get('ended_at')
    evaluated_at = look.get('evaluated_at')
    if manifest.get('stop_reason') != 'futility':
        interrupted = manifest.pop('abort_detail', None)
        if interrupted and last is not None:
            last['interrupted_after_the_futility_stop'] = interrupted
        manifest['stop_reason'] = 'futility'
        written.append('stop_reason')
    if open_session or 'total_charged_upper_bound' not in manifest:
        manifest.pop('total_charged_error', None)
        try:
            manifest['total_charged_upper_bound'] = base.total_spend(args.base, manifest.get('campaigns') or [])
        except PhaseAbort as error:
            manifest['total_charged_upper_bound'] = None
            manifest['total_charged_error'] = str(error)
        written.append('total_charged_upper_bound')
    if open_session or ((manifest.get('summary') or {}).get('primary') or {}).get('stop_reason') != 'futility':
        manifest['summary'] = summarize_upgrade(manifest['attempts'], stop_reason='futility',
                                                total_charged=manifest.get('total_charged_upper_bound'), look=look,
                                                db=args.store, started_at=manifest.get('started_at'))
        written.append('summary')
    if open_session or not manifest.get('ended_at'):
        manifest['ended_at'] = evaluated_at
        manifest['ended_at_source'] = FUTILITY_END_SOURCE
        written.append('ended_at')
    if open_session:
        last.update(ended_at=evaluated_at, ended_at_source=FUTILITY_END_SOURCE, stop_reason='futility')
        written.append('sessions[-1].ended_at')
    if (last is not None and 'clock_drift' not in last) or 'clock_drift' not in manifest:
        skipped = {'skipped': "the session that ran the look ended before its drift check; run it by hand (runbook step 8)",
                   'command': (f"scripts/experiments/check_clock_drift.py --since {manifest.get('started_at')}"
                               ' --worlds --require-worlds')}
        manifest['clock_drift'] = skipped
        if last is not None:
            last['clock_drift'] = dict(skipped)
        written.append('clock_drift')
    if written:
        manifest.setdefault('futility_write_ups', []).append(
            {'at': datetime.now(timezone.utc).isoformat(), 'written': list(written)})
    return written


# ---------------------------------------------------------------- main loop

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--out', required=True, help='the one artifacts/phase28-* folder for this run')
    parser.add_argument('--store', default=str(ROOT / 'artifacts/lab.sqlite3'))
    parser.add_argument('--worlds-dir', default='', help="for the drift check (default: the store's sibling 'worlds')")
    parser.add_argument('--settings', help='non-secret settings the backend was launched with')
    parser.add_argument('--expect-freeze', help='the Phase 28 gate-freeze JSON the code on disk must equal')
    parser.add_argument('--review-record', help='the approved review record (protocol, harness and plan hashes)')
    parser.add_argument('--expect-plan-hash')
    parser.add_argument('--expect-harness-sha256')
    parser.add_argument('--expect-protocol-sha256')
    parser.add_argument('--study-timeout', type=float, default=5400.0)
    parser.add_argument('--idle-grace', type=float, default=900.0)
    parser.add_argument('--poll-failure-window', type=float, default=300.0)
    parser.add_argument('--poll', type=float, default=5.0)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--after-abort', action='store_true',
                        help='resume a run that stopped early; only with the user\'s explicit approval')
    parser.add_argument('--reconcile', action='store_true')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    args = parser.parse_args()

    out = ROOT / args.out
    manifest_path = out / MANIFEST_NAME
    if args.reconcile:
        manifest = json.loads(manifest_path.read_text())
        problems, untracked = reconcile(manifest, args.store)
        print(f'reconciliation: {len(problems)} discrepancies, {len(untracked)} untracked full studies')
        for line in problems + [f'untracked: {sid}' for sid in untracked]:
            print('  ' + line)
        return 1 if problems or untracked else 0

    print(f'design     fixed N = {N_ATTEMPTS} attempts on case manifest {CASE_MANIFEST_ID!r} (source {SOURCE_CASE}); '
          f'a CERTIFIED study never stops the run')
    print(f'look       once, at the first D >= {FUTILITY_LOOK_D} distinct valid policies: stop if none re-sends the '
          f'upgrade and none is certified ({LOOK_PRECEDENCE})')
    print(f'stops      futility, N, the ${SPEND_CAP:.0f} spend guard ("truncated at n=j"), {BREAKER} consecutive '
          f'infrastructure failures, Ctrl-C/SIGTERM/SIGHUP')
    print(f'success    Phase 17 certification transposed: OBSERVED_IMPROVEMENT (assess_pairs + source_clause), '
          f'{SOURCE_CASE} 3 of 3, L-B0 >= {FRESH_GAIN_MIN} on a case other than {SOURCE_CASE} and {CONTROL_CASE}')
    print(f'models     actor {base.EXPECTED_ACTOR}; mechanic {base.EXPECTED_MECHANIC}; brief {MECHANIC_BRIEF}')
    print(f'protocols  actor {base.ACTOR_CONTEXT} (explicit); evidence {base.EVIDENCE_PROTOCOL}')
    print('routing    none: no held-out check follows this phase')
    print(f'spend      guard ${SPEND_CAP:.2f} (conservative bound), headroom ${HEADROOM:.2f} per study')
    print('runbook    before: check_ingestion_health (run by this runner), start-simulator.sh, dashboard closed '
          '(loop_latency p99 < 100 ms); after: check_clock_drift --worlds --since <run start> (run by this runner)')
    print('never      replay, re-validate, resume a study, route anything, or write ACCEPTED')
    if args.plan or not args.execute_live:
        for row in pin_status(args):
            print(f"pin        {row['pin']:<42} {row['state']:<9} declared {str(row['declared'])[:16]}"
                  + (f"  on disk {row['current'][:16]}" if row['current'] else ''))
        print(f'python     {sys.version.split()[0]} ({sys.executable}); the definition pins are AST hashes, taken with '
              f'the venv interpreter')
        print(f'harness    sha256 {base.sha256_file(__file__)}')
        print(f'plan       hash {plan_hash()}')
        print('Dry plan only. A live run needs --execute-live with the launch gates of the protocol '
              '(refused while any pin is UNFILLED).')
        return 0

    expected_freeze, protocol_sha256, harness, value = check_launch(args)
    if out.parent != ROOT / 'artifacts' or not out.name.startswith(PHASE_PREFIX):
        raise SystemExit(f'--out must be artifacts/{PHASE_PREFIX}<date>')
    from app.config import Settings
    settings_path = ROOT / args.settings
    overrides = json.loads(settings_path.read_text())
    os.environ.update({k: str(v) for k, v in overrides.items() if v != ''})
    settings = Settings.from_env()
    if args.confirm_entity != settings.wandb_entity:
        raise SystemExit('--confirm-entity must match WANDB_ENTITY in the settings file')
    if settings.project_path != base.EXPECTED_PROJECT:
        raise SystemExit(f'Settings project is {settings.project_path!r}, phase declares {base.EXPECTED_PROJECT!r}')
    if builder_manifest_hash() != DECLARED_MANIFEST_HASH:
        raise SystemExit("The backend builder's upgrade-v1 manifest does not hash to DECLARED_MANIFEST_HASH")
    current_freeze = base.gate_freeze()
    if current_freeze != expected_freeze:
        differing = sorted(f'{section}:{k}' for section in ('functions', 'files', 'fingerprints')
                           for k in set(current_freeze.get(section, {})) | set(expected_freeze.get(section, {}))
                           if current_freeze.get(section, {}).get(k) != expected_freeze.get(section, {}).get(k))
        raise SystemExit(f'Code on disk differs from the reviewed freeze: {differing[:8] or "schema"}')
    blockers = paid_run_blockers()
    if blockers:
        raise SystemExit(f'One paid run at a time: {blockers[0]}')
    process = base.check_backend_process()
    status = base.check_backend(args.base)
    if status.get('active_campaign_id'):
        raise SystemExit('Another execution is active; refusing to start')

    declared = {'plan': plan(), 'plan_hash': value, 'harness_sha256': harness, 'protocol_sha256': protocol_sha256,
                'review_record_sha256': base.sha256_file(ROOT / args.review_record)}
    if args.resume:
        if not manifest_path.exists():
            raise SystemExit(f'{manifest_path} does not exist; nothing to resume')
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('declared') != declared:
            raise SystemExit('Resume refused: the plan, pins, runner, protocol or review record differ from the run on record')
        look = manifest.get('futility_look') or {}
        if look.get('outcome') == 'stop':
            written = futility_write_up(manifest, look, args)
            if written:
                write_manifest(manifest_path, manifest)
            raise SystemExit(f"Resume refused: the futility look stopped the run at n = {look.get('attempt')}, "
                             f"which is final" + (f' (written now from the rows on record: {", ".join(written)})'
                                                  if written else ''))
        previous = manifest.get('stop_reason')
        if previous in FINAL_STOPS:
            raise SystemExit(f'Resume refused: the run ended with {previous!r}, which is final')
        # There is no checkpoint: every continuation follows an early stop and needs the user's approval.
        if not args.after_abort:
            raise SystemExit(f'Resume refused: the last session ended with {previous!r}; continuing '
                             f'needs the user\'s approval (--after-abort)')
        if manifest.get('stop_incomplete'):
            if not base.wait_until_idle(args.base, 60, args.poll):
                raise SystemExit('Resume refused: the last stop did not settle and the backend is not idle')
            manifest['stop_incomplete_cleared'] = datetime.now(timezone.utc).isoformat()
            manifest.pop('stop_incomplete')
    else:
        # Re-run guard: one folder, one record, never overwritten, never a second phase28 folder.
        if manifest_path.exists():
            raise SystemExit(f'{manifest_path} exists; refusing to overwrite a retained run record')
        others = [p for p in out.parent.glob(f'{PHASE_PREFIX}*/{MANIFEST_NAME}') if p != manifest_path]
        if others:
            raise SystemExit(f'Another Phase 28 run exists ({others[0]}); continue it with --resume, '
                             f'never in a new folder')
        previous = None
        manifest = {'schema_version': SCHEMA, 'declared': declared, 'models': status.get('models'),
                    'started_at': datetime.now(timezone.utc).isoformat(), 'configuration_hash': None,
                    'campaigns': [], 'attempts': [], 'sessions': [], 'futility_look': None,
                    'stop_reason': 'starting'}
        claim(out, manifest_path, manifest)
    blockers = paid_run_blockers()
    if blockers:
        if not args.resume:
            manifest_path.unlink()          # the claim above; nothing ran, so no record is kept
        raise SystemExit(f'One paid run at a time: {blockers[0]}')
    # Runbook: Weave ingestion must be healthy before any paid work (Phase 12 lost $8.15 without it).
    ingestion = fixed.ingestion_health()
    if ingestion.get('exit_status') != 0:
        if not args.resume:
            manifest_path.unlink()
        raise SystemExit(f"Refusing to start: check_ingestion_health.py exited {ingestion.get('exit_status')!r}; "
                         f"a paid run would very likely produce no scored result")
    out.mkdir(parents=True, exist_ok=True)

    def save():
        write_manifest(manifest_path, manifest)

    campaigns = manifest['campaigns']

    def needs_recovery(entry):
        # Started but never written, a start interrupted before its study id was saved, or a finished row
        # whose post-finish checks never ran because the runner aborted.
        return entry.get('campaign_id') and (
            (entry.get('status') is None and (entry.get('study_id') or not entry.get('error')))
            or (entry.get('study_id') and entry.get('post_checks') == 'pending'))

    def recover(entry):
        """Fill a row whose outcome or post-finish checks were never written, re-running the checks that do
        not depend on the process (this module's own summary, identity and integrity rules)."""
        try:
            if not entry.get('study_id'):
                existing = base.api(args.base, 'GET', f"/api/campaigns/{entry['campaign_id']}/completion-studies")
                if len(existing) > 1:
                    return False
                if not existing:
                    entry['error'] = 'study start: interrupted before the server saw it'; save()
                    return True
                entry['study_id'] = existing[0]['study_id']; entry['adopted_after_start_error'] = True; save()
            study = base.api(args.base, 'GET', f"/api/completion-studies/{entry['study_id']}")
        except Exception:  # noqa: BLE001
            return False
        if study.get('status') not in base.TERMINAL:
            return False
        entry.update(summarize_study(study), recovered=True)
        add_funnel(args.store, entry, study)
        try:
            verify_study_identity(study, when='recovered')
            problem = integrity_problem(study)
            if problem:
                entry['integrity_failure'] = problem
                raise PhaseAbort(problem)
            base.check_evidence_project(args.store, study)
            entry['post_checks'] = 'passed on recovery (backend process pin not re-checkable)'
        except PhaseAbort as error:
            entry['certified'] = False; entry['post_checks'] = f'failed on recovery: {error}'
        save()
        base.record_charge(args.base, entry['campaign_id'], entry, save)
        return True

    if args.resume:
        fixed.label_phantoms(manifest['attempts'])
        for entry in manifest['attempts']:
            if needs_recovery(entry) and not recover(entry):
                raise SystemExit(f"Resume refused: attempt {entry['attempt']} has no recorded outcome and its "
                                 f"study is not terminal or not readable; resolve it first")
        # Condition 4: an integrity failure aborts the run (design section 5; protocol section 6.2). One that recover()
        # found just now, or that no recorded stop names yet, becomes the recorded abort and this resume is refused,
        # so the user's next --after-abort is given with it in view (review round 1). One already named passes.
        found = unreported_integrity_failures(manifest)
        if found:
            manifest['abort_detail'] = integrity_abort_detail(found, manifest.get('abort_detail'))
            manifest['stop_reason'] = previous = 'aborted'
        manifest['summary'] = summarize_upgrade(manifest['attempts'], stop_reason=previous,
                                                abort_detail=manifest.get('abort_detail'),
                                                total_charged=manifest.get('total_charged_upper_bound'),
                                                look=manifest.get('futility_look'))
        if found:
            manifest.setdefault('resume_refusals', []).append(
                {'at': datetime.now(timezone.utc).isoformat(), 'reason': manifest['abort_detail']})
            save()
            raise SystemExit(f"Resume refused: {manifest['abort_detail']}. It is now the recorded abort; continuing "
                             f"needs the user's approval with it in view (--resume --after-abort again)")
        problems, untracked = reconcile(manifest, args.store)
        if problems or untracked:
            raise SystemExit('Resume refused: manifest and store disagree: ' + '; '.join(problems + untracked)[:500])
    manifest['sessions'].append({'started_at': datetime.now(timezone.utc).isoformat(),
                                 'after_abort': bool(args.after_abort), 'previous_stop': previous,
                                 'previous_abort_detail': manifest.pop('abort_detail', None),
                                 'backend_process': process, 'ingestion_health': ingestion})
    # Marks a session in progress: a session killed hard leaves 'running', which resume treats as an
    # early stop needing approval.
    manifest['stop_reason'] = 'running'
    save()

    def detach(signum, frame):
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        raise Detached(signum)
    signal.signal(signal.SIGTERM, detach)
    if signal.getsignal(signal.SIGHUP) is not signal.SIG_IGN:  # respect nohup
        signal.signal(signal.SIGHUP, detach)
    leave_running = False

    stop_reason = None
    consecutive = 0
    for row in reversed(manifest['attempts']):
        if fixed.runner_side(row):
            continue                       # neither a failure of the loop nor a success: skipped
        if not fixed.infrastructure_death(row):
            break
        consecutive += 1

    def pin_process():
        now = base.check_backend_process()
        if now != process:
            raise PhaseAbort(f'backend process changed during the run: {process} -> {now}')

    def count_death(message):
        nonlocal consecutive
        consecutive += 1
        if consecutive >= BREAKER:
            raise fixed.BreakerTripped(message.format(n=consecutive))

    try:
        while True:
            attempts = len(manifest['attempts'])
            # The futility look comes first (also on resume, before any new attempt). It is evaluated
            # once; a stop and its record are written in the same save.
            look = futility_look(manifest['attempts'], manifest.get('futility_look'))
            if look is not None:
                manifest['futility_look'] = look
                if look['outcome'] == 'stop':
                    manifest['stop_reason'] = 'futility'
                save()
                print(f"[look at n={look['attempt']}] D={look['D']} R={look['R']} k={look['k']}: {look['outcome']}",
                      flush=True)
            if (manifest.get('futility_look') or {}).get('outcome') == 'stop':
                stop_reason = 'futility'; break
            # 'certified' is deliberately absent: every certified study counts and none ends the run.
            if attempts >= N_ATTEMPTS:
                stop_reason = 'fixed_n'; break
            charged = base.total_spend(args.base, campaigns)
            if charged + HEADROOM > SPEND_CAP:
                stop_reason = 'spend_guard'; break
            base.check_backend(args.base)
            pin_process()
            blockers = paid_run_blockers()
            if blockers:
                raise PhaseAbort(f'another paid run appeared: {blockers[0]}')
            if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                raise PhaseAbort('backend is not idle; refusing to start another study')
            entry = {'attempt': attempts + 1, 'campaign_id': None, 'study_id': None, 'spent_before': charged}
            manifest['attempts'].append(entry); save()
            print(f'[attempt {entry["attempt"]}/{N_ATTEMPTS}] spent ${charged:.5f}', flush=True)

            try:
                campaign = base.api(args.base, 'POST', '/api/campaigns', {
                    'task_text': base.TASK_TEXT, 'order_id': base.ORDER_ID,
                    'mode': 'baseline', 'config_profile_id': 'live-v1'})
            except Exception as error:  # noqa: BLE001
                entry['error'] = f'campaign create: {type(error).__name__}'; save()
                count_death('{n} consecutive infrastructure failures')
                continue
            # Registered BEFORE the study starts, so its spend is always counted.
            campaigns.append(campaign['campaign_id'])
            entry['campaign_id'] = campaign['campaign_id']
            entry['configuration_hash'] = campaign.get('configuration_hash'); save()
            if not entry['configuration_hash']:
                entry['error'] = NO_CONFIGURATION_HASH; save()
                raise PhaseAbort('campaign carries no configuration_hash')
            if entry['configuration_hash'] != DECLARED_CONFIGURATION_HASH:
                entry['error'] = CONFIGURATION_MISMATCH; save()
                raise PhaseAbort(f"backend configuration_hash {entry['configuration_hash']} != declared "
                                 f"{DECLARED_CONFIGURATION_HASH}")
            manifest['configuration_hash'] = entry['configuration_hash']
            try:
                base.check_campaign_in_store(args.store, campaign['campaign_id'])
            except PhaseAbort:
                entry['error'] = STORE_OR_ARIA_REFUSED; save()
                raise

            try:
                # v4 is passed explicitly (the backend default is still v1, pitfall 69), and so is the manifest.
                started = base.api(args.base, 'POST', f"/api/campaigns/{campaign['campaign_id']}/completion-study",
                                   {'execute_live': True, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
                                    'actor_context_protocol': base.ACTOR_CONTEXT,
                                    'case_manifest_id': CASE_MANIFEST_ID})
            except Exception as error:  # noqa: BLE001
                # The server may have started it although the client saw a failure.
                entry['start_error'] = type(error).__name__; save()
                try:
                    existing = base.api(args.base, 'GET', f"/api/campaigns/{campaign['campaign_id']}/completion-studies")
                except Exception:  # noqa: BLE001
                    base.record_charge(args.base, campaign['campaign_id'], entry, save)
                    raise PhaseAbort('study start failed and the server cannot say whether a study exists')
                if not existing:
                    # The server may still be inside queue_completion_study; look again once idle.
                    if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                        raise PhaseAbort('backend did not return to idle after a failed start')
                    try:
                        existing = base.api(args.base, 'GET', f"/api/campaigns/{campaign['campaign_id']}/completion-studies")
                    except Exception:  # noqa: BLE001
                        raise PhaseAbort('study start failed and the server cannot say whether a study exists')
                if len(existing) > 1:
                    raise PhaseAbort('more than one study on a fresh campaign')
                if not existing:
                    entry['error'] = f"study start: {entry['start_error']}"; save()
                    base.record_charge(args.base, campaign['campaign_id'], entry, save)
                    count_death('{n} consecutive infrastructure failures')
                    if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                        raise PhaseAbort('backend did not return to idle after a failed start')
                    continue
                started = existing[0]; entry['adopted_after_start_error'] = True
            entry['study_id'] = started['study_id']; save()
            verify_study_identity(started, when='at start')

            deadline = time.monotonic() + args.study_timeout
            study, failing_since = started, None
            while study.get('status') not in base.TERMINAL:
                if time.monotonic() > deadline:
                    raise PhaseAbort(f"{started['study_id']} still {study.get('status')} after the study timeout")
                time.sleep(args.poll)
                try:
                    study = base.api(args.base, 'GET', f"/api/completion-studies/{started['study_id']}")
                    failing_since = None
                except Exception as error:  # noqa: BLE001
                    entry['poll_errors'] = entry.get('poll_errors', 0) + 1
                    failing_since = failing_since or time.monotonic()
                    if time.monotonic() - failing_since > args.poll_failure_window:
                        raise PhaseAbort(f'lost contact with a running study ({type(error).__name__}); '
                                         f'stopping rather than starting another beside it')
            # Save the terminal outcome the moment it is seen; nothing below can lose it.
            entry.update(summarize_study(study), post_checks='pending'); save()
            if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                raise PhaseAbort('a finished study is still holding the coordinator')
            try:
                study = base.api(args.base, 'GET', f"/api/completion-studies/{started['study_id']}")
            except Exception as error:  # noqa: BLE001
                raise PhaseAbort(f'could not re-read the finished record ({type(error).__name__}); '
                                 f'the outcome seen at completion is kept')
            entry.update(summarize_study(study)); save()
            add_funnel(args.store, entry, study); save()
            base.record_charge(args.base, campaign['campaign_id'], entry, save)
            try:
                # Part of condition 1: a row that fails these is never certified. Condition 4's re-check is
                # an integrity failure that aborts the run.
                verify_study_identity(study, when='after finishing')
                problem = integrity_problem(study)
                if problem:
                    entry['integrity_failure'] = problem
                    raise PhaseAbort(problem)
                base.check_evidence_project(args.store, study)
                pin_process()
            except PhaseAbort as error:
                entry['certified'] = False; entry['post_checks'] = f'failed: {error}'; save()
                raise
            entry['post_checks'] = 'passed'; save()
            if fixed.infrastructure_death(entry):
                count_death('{n} consecutive studies died of infrastructure errors; '
                            'check evidence ingestion and provider health')
            else:
                consecutive = 0
            candidates = ', '.join(f"{c['decision']}{'+resend' if c['contains_upgrade_retry'] else ''}"
                                   for c in entry['candidates']) or 'none'
            print(f"[attempt {entry['attempt']}/{N_ATTEMPTS}] {entry['status']}/{entry['decision']} at {entry['stage']}"
                  f" | candidates: {candidates} | validation={entry['validation_decision']}"
                  f" | certified={entry['certified']}"
                  + (f" | error={entry['error_type']}" if entry.get('error_type') else ''), flush=True)
    except fixed.BreakerTripped as error:
        stop_reason = 'breaker'; manifest['abort_detail'] = str(error)
        say(f'\nSTOPPED (breaker): {error}', flush=True)
    except PhaseAbort as error:
        stop_reason = 'aborted'; manifest['abort_detail'] = str(error)
        say(f'\nABORTED: {error}', flush=True)
    except Detached as signal_error:
        stop_reason = 'aborted'; leave_running = True
        manifest['abort_detail'] = f'signal {signal_error.args[0]}; any running study left running for recover()'
    except KeyboardInterrupt:
        stop_reason = 'aborted'; manifest['abort_detail'] = 'interrupted by operator (Ctrl-C)'
    except Exception as error:  # noqa: BLE001
        stop_reason = 'aborted'; manifest['abort_detail'] = f'{type(error).__name__}: {error}'
        say(f'\nABORTED: {manifest["abort_detail"]}', flush=True)

    if (manifest.get('futility_look') or {}).get('outcome') == 'stop' and stop_reason != 'futility':
        # The look's stop reached the disk in the same save as its record. A signal, Ctrl-C or error after that save and
        # before the break (a print into a closed pipe, say) interrupts only the write-up: the stop stays the final
        # 'futility', never 'aborted', and nothing is in flight, because the look runs before any attempt starts
        # (review round 1). The interruption is kept in this session's record.
        manifest['sessions'][-1]['interrupted_after_the_futility_stop'] = manifest.pop('abort_detail', None)
        stop_reason, leave_running = 'futility', False

    if stop_reason in ('aborted', 'breaker'):
        # Recorded at once, before the in-flight stop, the idle wait and recovery below: a second
        # Ctrl-C or signal in that window must not leave 'running' on disk with no reason.
        fixed.label_phantoms(manifest['attempts'])
        manifest['stop_reason'] = stop_reason
        save()
    if stop_reason in ('aborted', 'breaker') and campaigns and not leave_running:
        # Aborting the runner does not stop the backend. Stop OUR campaign only while its study is still
        # running; never rewrite a campaign whose study already finished.
        status = base.backend_status(args.base)
        last = manifest['attempts'][-1] if manifest['attempts'] else {}
        in_flight = last.get('status') is None and last.get('campaign_id') == campaigns[-1] and (
            (status or {}).get('active_campaign_id') == campaigns[-1] or status is None)
        if in_flight:
            try:
                base.api(args.base, 'POST', f'/api/campaigns/{campaigns[-1]}/stop', {})
            except Exception as error:  # noqa: BLE001
                say(f'  stop request failed: {type(error).__name__}', flush=True)
            if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                manifest['stop_incomplete'] = True
    if not leave_running:
        for entry in manifest['attempts']:
            if needs_recovery(entry):
                try:
                    recover(entry)
                except Exception:  # noqa: BLE001
                    pass
        # Condition 4 again (review round 1): an integrity failure that recovery found after this stop is the abort of
        # record, not a row note beside an abort that names something else. (A final stop leaves no row to recover:
        # every row before it finished, and resume recovered the earlier ones before any new attempt.)
        found = unreported_integrity_failures(manifest)
        if found:
            stop_reason = 'aborted'
            manifest['abort_detail'] = integrity_abort_detail(found, manifest.get('abort_detail'))
            say(f"\nABORTED: {manifest['abort_detail']}", flush=True)

    manifest['stop_reason'] = stop_reason
    try:
        manifest['total_charged_upper_bound'] = base.total_spend(args.base, campaigns)
    except PhaseAbort as error:
        manifest['total_charged_upper_bound'] = None
        manifest['total_charged_error'] = str(error)
    manifest['summary'] = summarize_upgrade(manifest['attempts'], stop_reason=stop_reason,
                                            abort_detail=manifest.get('abort_detail'),
                                            total_charged=manifest['total_charged_upper_bound'],
                                            look=manifest.get('futility_look'), db=args.store,
                                            started_at=manifest.get('started_at'))
    now = datetime.now(timezone.utc).isoformat()
    manifest['sessions'][-1].update(ended_at=now, stop_reason=stop_reason, abort_detail=manifest.get('abort_detail'))
    manifest['ended_at'] = now
    save()
    if leave_running or manifest.get('stop_incomplete'):
        drift = {'skipped': 'a study was left running or did not stop; run the command after it ends',
                 'command': f"scripts/experiments/check_clock_drift.py --since {manifest['started_at']} --worlds --require-worlds"}
    else:
        try:
            drift = fixed.clock_drift(args.store, manifest['started_at'], args.worlds_dir)
        except Exception as error:  # noqa: BLE001
            drift = {'error': type(error).__name__, 'exit_status': None}
    manifest['sessions'][-1]['clock_drift'] = drift
    manifest['clock_drift'] = drift
    save()
    s = manifest['summary']
    total = manifest['total_charged_upper_bound']
    say(f"\n{stop_reason} | {s['primary']['statement']}")
    say(f"funnel: upgrade re-send in {s['funnel']['first_proposals_with_upgrade_retry']} of "
          f"{s['funnel']['first_proposals_drawn']} first proposals | D={s['funnel']['distinct_valid_policies_D']} "
          f"R={s['funnel']['distinct_with_upgrade_retry_R']} | fired at source {s['funnel']['upgrade_retry_fired_at_source']} "
          f"of {s['funnel']['upgrade_retry_tested_at_source']} | validation assessed {s['funnel']['validation_assessed']} "
          f"(clean {s['funnel']['validation_clean']}) | source-clause rejections "
          f"{s['funnel']['rejected_by_transposed_source_clause']}")
    say(f"clock drift: {drift.get('drifted', drift.get('skipped') or drift.get('error'))} | "
          f"charged ${total if total is not None else float('nan'):.5f}")
    say(f'manifest {manifest_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
