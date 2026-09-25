#!/usr/bin/env python3
"""Phase 26: second completion-gap probe. Can a legal MANUAL-REFERENCE policy (MR) complete the
upgrade-side development cases that the empty baseline (B0) and the certified repairs do not?

Three arms, two paired comparisons through the unchanged app.lab.evaluation.PairedEvaluator:
  - B0 vs MR  (the declared test): MR is the manual-reference policy written in the existing policy
    DSL (MR_CONTENT below, sha256 b8d18218...). It validates under RecoveryPolicy and CandidatePolicy
    with no backend change. It is labelled manual-reference, lives only in this file, and is NEVER
    saved in any policy store, shown to a Mechanic, certified or promoted.
  - B0 vs L   (descriptive): L is Phase 23's certified policy 711bddb6..., a development replication
    of the transient-upgrade pattern (its heldout-2 verdict exists; it is never re-checked held out).
The two comparisons share schedules (same schedule_identity per setting; seeds differ and are
metadata) and interleave in time. PairedEvaluator labels every candidate trial 'L' in the store,
so the read-out names the arms by policy hash (B0 bafdc14f..., MR b8d18218..., L 711bddb6...).

Dry planning is the default. It reads the Phase 17 settings file (never .env), recomputes the
configuration hash (2cf63e93..., the Phase 17 settings on the Phase 22 code) and the gate freeze
(artifacts/phase22-2026-09-24/gate-freeze-after.json, 8994e962...), reads B0 and L read-only from the
lab store, validates every schedule with FaultSpec and the simulator's validate_schedule, checks each
declared setting is reachable for MR with a static model of the tick/wait/attempt budgets (an
unreachable one is reported, never changed), checks ledger admission on an in-memory ledger, computes
the declared power table, and prints the plan. It makes no provider, model or W&B call, contacts no
service and writes no file.

`--mechanism-check` ($0) runs the declared plan in-process against the REAL simulator, policy
interpreter, PairedEvaluator and referee with a scripted fixture Actor (never model evidence) in a
new --work-dir, and writes a summary to --mechanism-out: it shows what each policy does on each
schedule when the Actor behaves as V3.1 measurably does (reads the order, upgrades once at tick 2,
never re-sends, polls, confirms after a receipt).

`--execute-live` (with `--confirm-entity`, the protocol, `--expect-protocol-sha256` and the review
record) runs in-process like run_dev_probe.py: the backend on :8000 must be stopped (this process
holds the port), the simulator on :8001 stays up (start it only with scripts/start-simulator.sh).
Results go to a NEW --output directory (artifacts/phase26-<date>/<name>) that is never resumed.
`--readout STORE` recomputes the declared read-out from an output store, read-only, only with the
harness, base runner and drift checker the run pinned.

LEDGER, TELEMETRY, SIGNALS and STOPS are Phase 20's (run_dev_probe.py, imported and pinned by sha):
a caller-owned 96-call reservation per case, no EvaluationPublisher and no evidence read-back, the
evaluator's own lab-error pair retry only, stops only on the spend cap, a configuration/harness/
protocol change, a worlds-directory mismatch, a FaultLab backend (or a listener that cannot be
identified) on port 8000, the operator, or 3 consecutive infrastructure cases.
One paid run at a time: this process binds 127.0.0.1:8000 (bound, never listening), which stops any
server that binds 127.0.0.1 or localhost there (the repository's launchers do). A server bound to
0.0.0.0, :: or ::1 can still bind beside it (review rounds 1 and 2, measured), and while the port is
held a connection to 127.0.0.1:8000 times out instead of being refused, so connecting there sees
nothing. The runner therefore lists LISTEN sockets on the port by state (lsof, which sees 0.0.0.0, ::,
::1 and 127.0.0.1 alike, with the pid holding each), plus a connection probe on [::1]:8000: before any
directory exists any listener refuses the run; at every case start a FaultLab backend (a uvicorn
app.main process) or a listener it cannot identify stops the run, and any other identified listener is
recorded in the manifest (listeners_flagged) and the run goes on. A listener is recorded by address, pid
and the program's file name only (for Python, also the script's file name or the -m module), never an
option, an option's value or an argument; lsof runs with -b -w, so a mounted volume that cannot be reached
neither blocks it nor reads as a failure (review round 3). It refuses while a Phase 21 live
run, a non-final run manifest under a Phase 25, 27, 28 or 29 directory, a phase25-29 launch claim whose
run has no final manifest, any other paid experiment process (a Python process running a path ending in
experiments/<name>.py with --execute-live or a prefix of it; this process, its ancestors and its descendants,
such as the caffeinate helper, are excluded), or a delivered earlier Phase 26 run exists. It then
writes its own launch claim (artifacts/phase26-live-claims/claim-NN.json, read by the Phase 25 and
Phase 27 guards) BEFORE its last check for other runs, so two launches in the same few seconds cannot
both pass: the later check of one of them sees the other's claim.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import pathlib
import re
import shlex
import shutil
import signal
import socket
import sqlite3
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace

# Even dry inspection should not create Python cache files in the workspace.
sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(HERE))

# The closed Phase 20 runner supplies the reviewed generic machinery (settings without .env, the
# ledger reservation and spend guard, signal handling, the Phase 21 guard, the drift check, the pure
# statistics and the per-trial row). It is pinned by sha below and checked with the harness.
import run_dev_probe as base  # noqa: E402
import check_clock_drift  # noqa: E402

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4  # noqa: E402
from app.contracts.models import (CampaignBudget, CampaignRequest, CandidatePolicy, FaultSpec,  # noqa: E402
                                  PolicyVersion, RecoveryPolicy, canonical_json, content_hash, new_id)
from app.lab.budgets import BudgetExhausted  # noqa: E402
from app.lab.challenge import schedule_identity  # noqa: E402
from app.lab.evaluation import PairedEvaluator  # noqa: E402

PlanningError = base.PlanningError
SCHEMA = 'faultlab-gap-probe/v1'
PLAN_SCHEMA = 'faultlab-gap-probe-plan/v1'
READOUT_SCHEMA = 'faultlab-gap-probe-readout/v1'
MECHANISM_SCHEMA = 'faultlab-gap-probe-mechanism-check/v1'
# Own store records; never ChallengeResult records.
PLAN_RECORD = 'gap_probe_plans'
CASE_RECORD = 'gap_probe_cases'
MANIFEST_NAME = 'gap-probe-manifest.json'
PHASE_PREFIX = 'phase26-'
# This phase's launch claims. The Phase 25 guard (slot2_probe.OTHER_CLAIM_DIRS) and the Phase 27 guard
# (report_word_probe.OTHER_CLAIM_DIRS) read this directory; a claim blocks them until the run directory
# it names holds a final manifest.
CLAIM_DIR = 'phase26-live-claims'
CLAIM_PREFIX = 'claim-'

TASK_TEXT = base.TASK_TEXT
ORDER_ID = base.ORDER_ID
PURPOSE = 'challenge'   # existing Purpose literal: split 'development', origin 'faultlab_evaluation'
ACTOR_CONTEXT = 'faultlab-actor-context/v4-indexed-evidence'
EXPECTED_ACTOR = base.EXPECTED_ACTOR
BASELINE_POLICY_HASH = 'bafdc14f280cd47441baf69006e8ca55885ca0349667f2695f57e40b3b8926fb'
L_POLICY_HASH = '711bddb68697e52dcd9b0d5b428fa96d7ec1fe0e95559d9a892b4a7772ac738e'
L_POLICY_VERSION = 'policy-dcb7d9d339554d3d876e53a492d4f2b8'
L_PROVENANCE = {'phase': 23, 'attempt': 2, 'study_id': 'completion-study-cbb2f82f2f514c97bbcf5841c21f9ec0',
                'status': 'certified completion repair; heldout-2 verdict HARM (Phase 24), final; never ACCEPTED',
                'use_here': 'descriptive development replication only; never re-checked held out'}

# Pins. The runner refuses to plan or run unless the files on disk equal these.
DECLARED_CONFIGURATION_HASH = '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba'
DECLARED_SETTINGS_SHA256 = base.DECLARED_SETTINGS_SHA256            # 1e2002d3..., the Phase 17 settings
DECLARED_FREEZE_FILE_SHA256 = '8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1'
DECLARED_GATE_FREEZE_SCRIPT_SHA256 = base.DECLARED_GATE_FREEZE_SCRIPT_SHA256   # 5e21c0ec...
ASSESS_PAIRS_KEY = base.ASSESS_PAIRS_KEY
ASSESS_PAIRS_TEXT_SHA256 = base.ASSESS_PAIRS_TEXT_SHA256            # 783e8e58..., unchanged; no gate runs
DECLARED_BASE_RUNNER_SHA256 = 'd181f2903971a4c53c02d2826f7a961a8cb835ec88a650cc9713cd06c7837c42'

ARTIFACTS = ROOT / 'artifacts'
DEFAULT_SETTINGS = base.DEFAULT_SETTINGS
DEFAULT_FREEZE = ARTIFACTS / 'phase22-2026-09-24/gate-freeze-after.json'
DEFAULT_SOURCE_STORE = ARTIFACTS / 'lab.sqlite3'
DEFAULT_WORLDS = ARTIFACTS / 'worlds'
DEFAULT_PROTOCOL = ROOT / 'docs/part2/PHASE26_EXPERIMENT.md'
# Written when the review closes and the phase is approved, never by this runner.
DEFAULT_REVIEW_RECORD = ARTIFACTS / 'phase26-2026-09-24/review.json'
DRIFT_CHECKER = HERE / 'check_clock_drift.py'
BASE_RUNNER = HERE / 'run_dev_probe.py'
HARNESS_PIN_LINE = 'runnable-harness-sha256: {sha}'
DRIFT_CHECKER_PIN_LINE = 'drift-checker-sha256: {sha}'
BASE_RUNNER_PIN_LINE = 'base-runner-sha256: {sha}'
MR_PIN_LINE = 'manual-reference-policy-sha256: {sha}'
# Other paid runs that do not hold :8000 (direct-provider replays): Phase 21 (its own guard, reused)
# and any run manifest under a Phase 25, 27, 28 or 29 directory that is not final. Heldout-2 and
# every held-out run record are never read.
NEW_PHASE_MANIFEST_GLOBS = ('phase25-*/**/*manifest*.json', 'phase27-*/**/*manifest*.json',
                            'phase28-*/**/*manifest*.json', 'phase29-*/**/*manifest*.json')

SPEND_CAP = 25.0
PAIRS_PER_CASE = base.PAIRS_PER_CASE                  # 3, fixed inside PairedEvaluator.run
ACTOR_CALLS_PER_EPISODE = 8                           # the planning figure: every episode uses all 8 turns
CASE_RESERVATION_CALLS = base.CASE_RESERVATION_CALLS  # 96, caller-owned
EVALUATOR_RETRY_CALLS = base.EVALUATOR_RETRY_CALLS    # 16
CASE_WORST_CALLS = base.CASE_WORST_CALLS              # 144 = 96 + 3 x 16
PAIR_WORST_CALLS = base.PAIR_WORST_CALLS              # 48
MAX_CONSECUTIVE_INFRASTRUCTURE = base.MAX_CONSECUTIVE_INFRASTRUCTURE
LEDGER_REFUSAL_REASON = base.LEDGER_REFUSAL_REASON
ALPHA = 0.05
FAMILIES = ('F4', 'F2')
MULTIPLICITY = ('Holm over the two family tests (F4 and F2), family-wise error at most 0.05: the smaller p '
                'is tested at 0.025, the other at 0.05 only if the first is rejected')
SAFETY_ALPHA = 0.05
# Section 7.2 labels (computed by analyse(), never by hand). A stratum is REACHED when MR completed at
# least two thirds of its MR trials (4 of 6), and SOURCE-GRADE when MR completed at least five sixths of
# them (5 of 6) and B0 none. A family is a candidate source family only if its label is COMPLETES_MORE
# or COMPLETES_MORE_WITH_FAILURES, the run is complete, every counted stratum is source-grade and the
# two replicas agree. "A loop should not be asked to learn F with this Actor" is said only on a complete
# run whose MR completion rate on F has a Wilson 95% upper bound below LOW_MR_RATE_BOUND.
REACHED_FRACTION = (2, 3)
SOURCE_GRADE_FRACTION = (5, 6)
LOW_MR_RATE_BOUND = 0.3
SOURCE_GATE_TRIALS = 3      # completion_study's source gate: L 3 of 3 and B0 0 of 3 on the source case
# Section 7.3: if L behaved exactly like B0 at Phase 20's development rate (2 of 27), how often the
# descriptive label would read pattern_replicated by chance (L 0 of n, B0 at least 1 of n).
L_NULL_RATE = 2 / 27
PRIMARY_POPULATION = 'evaluator_pairs'
SENSITIVITY_POPULATIONS = ('valid_pairs', 'without_lab_defects')
FIXTURE_VERSIONS = base.FIXTURE_VERSIONS
SEED_BASE = 2026092600      # seeds are metadata (schedule_identity ignores them)
# The Actor's first update_order dispatch tick in Phase 20's development data: 2 in 138 of 138
# episodes (both arms, every setting; artifacts/phase26-2026-09-24/prep/first-update-tick.txt).
MEASURED_FIRST_UPDATE_TICK = 2
DECISION_TICK_CAP = 20      # non-observer clock limit and the business budget's tick limit
HTTP_ATTEMPT_CAP = 18
WAIT_CYCLE_CAP = 4
WAIT_TICKS_MAX = 4
POLICY_STEP_CAP = 32
# Planning rates for the power table (never data of this phase). F4: Phase 20's development B0,
# 2 of 27, and a pessimistic 0.15. F2 d >= 8: 0 (B0 cannot reach d >= 5 without a broker re-send's
# extra tick, and d8 would need four; the data at d >= 5: Phase 20 d5, d16, d20 0 of 9 and Phase 2 d5
# 0 of 10) and a pessimistic 0.10.
PLANNING_B0_RATES = {'measured': {'F4': 2 / 27, 'F2': 0.0}, 'pessimistic': {'F4': 0.15, 'F2': 0.10}}
PLANNING_MR_RATES = (0.3, 0.5, 0.7, 0.9)

# ---------------------------------------------------------------- the manual-reference policy

P, U = 'current_operation_pending', 'upgrade_outcome_uncertain'
# Written by hand in the existing DSL (backend/app/lab/policy_interpreter.py). Every step carries
# its only_if explicitly, so this dict is the canonical form of the validated model.
MR_CONTENT = {'scope': 'orders.upgrade_then_confirm/v1', 'parent_version': 'policy-v0', 'rules': [
    # 1. F2 path. The upgrade was accepted and reads PENDING: wait and re-read, stopping at the first
    #    delivered receipt. 13 wait ticks + 4 reads = 17 ticks, all 4 wait cycles: with the Actor's
    #    upgrade at tick 2 the last read lands at tick 19, which leaves tick 20 for the confirmation.
    {'hook': 'after_upgrade_response', 'when': P, 'steps': [
        {'op': 'wait_ticks', 'ticks': 4, 'only_if': P}, {'op': 'read_current_operation', 'only_if': P},
        {'op': 'wait_ticks', 'ticks': 4, 'only_if': P}, {'op': 'read_current_operation', 'only_if': P},
        {'op': 'wait_ticks', 'ticks': 4, 'only_if': P}, {'op': 'read_current_operation', 'only_if': P},
        {'op': 'wait_ticks', 'ticks': 1, 'only_if': P}, {'op': 'read_current_operation', 'only_if': P}]},
    # 2. Still PENDING after the whole wait budget: hand the report back to the Actor (business
    #    closed), so rule 3 does not re-send a write once it has been OBSERVED PENDING. An accepted write
    #    whose response was lost reads UNKNOWN, not PENDING; rule 3 then re-sends the original bytes,
    #    which is idempotent by contract (protocol section 12).
    {'hook': 'after_upgrade_response', 'when': P, 'steps': [{'op': 'defer_unresolved', 'only_if': P}]},
    # 3. F4 path. A write was attempted, no terminal receipt, and the status is not PENDING (a
    #    transient failure before acceptance): wait one tick and re-send the ORIGINAL bytes, at most
    #    twice. With the broker's own single re-send, the Actor's call and two re-sends cover
    #    update_order attempts 1-6, so failure counts up to 5 complete inside this hook.
    {'hook': 'after_upgrade_response', 'when': U, 'steps': [
        {'op': 'wait_ticks', 'ticks': 1, 'only_if': U}, {'op': 'retry_original_request', 'service': 'orders', 'only_if': U},
        {'op': 'wait_ticks', 'ticks': 1, 'only_if': U}, {'op': 'retry_original_request', 'service': 'orders', 'only_if': U}]},
    # 4. Never confirm an upgrade without a delivered SUCCEEDED receipt. No call, no tick.
    {'hook': 'before_confirmation', 'when': 'upgrade_receipt_missing', 'steps': [
        {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED', 'only_if': 'upgrade_receipt_missing'}]}]}
MR_VERSION = 'manual-reference-v1'
MR_LABEL = 'manual-reference'
DECLARED_MR_POLICY_HASH = 'b8d18218516bb2051ebde34e9a7ce64343b0b29fb71efb06225459495cdd5248'
# The ops MR may use: upgrade side only. It never touches the notification operation.
MR_ALLOWED_OPS = frozenset({'wait_ticks', 'read_current_operation', 'retry_original_request', 'defer_unresolved',
                            'require_receipt'})


@dataclass(frozen=True)
class ReferenceArm:
    """The manual-reference arm, exactly as PairedEvaluator and EpisodeRunner use a policy (version,
    content, policy_hash, decision). Deliberately NOT a PolicyVersion: it is never saved in any policy
    store, so it cannot be listed, compared, certified, promoted or shown to a Mechanic. The decision
    string is read by the prototype adapter only for purpose 'discovery', which this runner never uses."""
    version: str
    content: RecoveryPolicy
    policy_hash: str
    decision: str = 'MANUAL_REFERENCE'
    author: str = MR_LABEL
    label: str = MR_LABEL


def manual_reference():
    content = RecoveryPolicy.model_validate_json(canonical_json(MR_CONTENT))
    return ReferenceArm(version=MR_VERSION, content=content, policy_hash=content_hash(content))


def validate_manual_reference():
    """The schema checks, with no backend change: RecoveryPolicy (what the interpreter runs),
    CandidatePolicy (what a Mechanic proposal must satisfy), canonical form, the declared hash and
    upgrade-side ops only. Returns the facts the plan records; raises on any failure."""
    recovery = RecoveryPolicy.model_validate_json(canonical_json(MR_CONTENT))
    candidate = CandidatePolicy.model_validate_json(canonical_json(MR_CONTENT))
    if canonical_json(recovery) != canonical_json(MR_CONTENT):
        raise PlanningError('The manual-reference policy is not in canonical RecoveryPolicy form')
    digest = content_hash(recovery)
    if digest != DECLARED_MR_POLICY_HASH or content_hash(candidate) != digest:
        raise PlanningError(f'The manual-reference policy hashes to {digest}, not the declared {DECLARED_MR_POLICY_HASH}')
    ops = {step.op for rule in recovery.rules for step in rule.steps}
    if not ops <= MR_ALLOWED_OPS:
        raise PlanningError(f'The manual-reference policy uses ops outside the upgrade side: {sorted(ops - MR_ALLOWED_OPS)}')
    if any(getattr(step, 'service', 'orders') != 'orders' for rule in recovery.rules for step in rule.steps):
        raise PlanningError('The manual-reference policy may act on the orders operation only')
    return {'policy_hash': digest, 'version': MR_VERSION, 'label': MR_LABEL,
            'validates_as': ['RecoveryPolicy', 'CandidatePolicy'], 'canonical': True,
            'rules': len(recovery.rules), 'steps': [len(rule.steps) for rule in recovery.rules],
            'hooks': [rule.hook for rule in recovery.rules], 'ops': sorted(ops),
            'wait_ticks_if_every_wait_runs': sum(s.ticks for r in recovery.rules for s in r.steps if s.op == 'wait_ticks'),
            'never': ['saved in any policy store', 'shown to a Mechanic or any model', 'certified', 'promoted',
                      'ACCEPTED or REJECTED'],
            'content': recovery.model_dump(mode='json')}


def sha256_file(path):
    return base.sha256_file(path)


def harness_sha256():
    return sha256_file(__file__)


def drift_checker_sha256():
    return sha256_file(DRIFT_CHECKER)


def base_runner_sha256():
    return sha256_file(BASE_RUNNER)


# The code this process runs, hashed when it was loaded.
LOADED_HARNESS_SHA256 = sha256_file(__file__)
LOADED_DRIFT_CHECKER_SHA256 = sha256_file(check_clock_drift.__file__)
LOADED_BASE_RUNNER_SHA256 = sha256_file(base.__file__)


def now():
    return base.now()


# ---------------------------------------------------------------- declared cases

def _f4(count):
    return {'kind': 'F4', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
            'parameters': {'failure_count': count}}


def _f2(ticks, terminal='SUCCEEDED'):
    return {'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
            'parameters': {'completion_delay_ticks': ticks, 'terminal_status': terminal,
                           'failure_code': None if terminal == 'SUCCEEDED' else 'UPGRADE_REJECTED'}}


# setting -> (family, kind, stratum, primitives, fixture, target). Targets follow the completion
# manifest's convention for the BASELINE Actor (a fault it can get through targets COMPLETED; one
# beyond its reach targets SAFE_UNRESOLVED); they only label tables. A COMPLETED on a
# SAFE_UNRESOLVED setting is a correct outcome.
SETTINGS = {
    'F4:c2': ('F4', 'F4 update_order transient failures', 'c2', (_f4(2),), 'standard-v1', 'COMPLETED'),
    'F4:c3': ('F4', 'F4 update_order transient failures', 'c3', (_f4(3),), 'standard-v1', 'COMPLETED'),
    'F4:c4': ('F4', 'F4 update_order transient failures', 'c4', (_f4(4),), 'standard-v1', 'COMPLETED'),
    'F2:d5': ('F2', 'F2 SUCCEEDED long delay', 'd5', (_f2(5),), 'standard-v1', 'SAFE_UNRESOLVED'),
    'F2:d8': ('F2', 'F2 SUCCEEDED long delay', 'd8', (_f2(8),), 'standard-v1', 'SAFE_UNRESOLVED'),
    'F2:d12': ('F2', 'F2 SUCCEEDED long delay', 'd12', (_f2(12),), 'standard-v1', 'SAFE_UNRESOLVED'),
    # The longest delay a legal policy can complete when the Actor upgrades at tick 2 (section 4).
    'F2:d17': ('F2', 'F2 SUCCEEDED long delay', 'd17', (_f2(17),), 'standard-v1', 'SAFE_UNRESOLVED'),
    'H': ('H', 'healthy (no fault)', None, (), 'standard-v1', 'COMPLETED'),
}
# The counted strata of each family test. F2:d5 is NOT counted: the certified repair dd62c857... completed
# d5 3 of 3 in Phase 20, so d5 is no gap the certified repairs leave open. It still runs (MR against B0,
# 6 against 6) as a descriptive calibration stratum and as a stratum of the overall MR safety test.
FAMILY_STRATA = {'F4': ('F4:c2', 'F4:c3', 'F4:c4'), 'F2': ('F2:d8', 'F2:d12', 'F2:d17')}
CALIBRATION_STRATA = ('F2:d5',)
# The strata of each family's SAFETY inputs to the section 7.2 label (k and the per-family test S_F): the
# counted strata plus the family's calibration stratum (review round 2). d5 runs MR's F2 path (wait, read,
# then a long report), so an MR failure there is safety evidence about this repair class; d5 stays out of
# the completion test only.
SAFETY_STRATA = {'F4': FAMILY_STRATA['F4'], 'F2': CALIBRATION_STRATA + FAMILY_STRATA['F2']}
COMPARISONS = {'MR': DECLARED_MR_POLICY_HASH, 'L': L_POLICY_HASH}
# (comparison, setting, replicas), in declaration order; seeds are numbered by this order.
CASE_TABLE = (
    ('MR', 'F4:c2', 2), ('MR', 'F4:c3', 2), ('MR', 'F4:c4', 2),
    ('MR', 'F2:d5', 2), ('MR', 'F2:d8', 2), ('MR', 'F2:d12', 2), ('MR', 'F2:d17', 2),
    ('MR', 'H', 1),
    ('L', 'F4:c2', 2), ('L', 'F4:c3', 2), ('L', 'F4:c4', 2),
)
# Replica-major rounds; inside a round the two comparisons alternate on each F4 setting, so time of
# day falls across settings and across the MR/L contrast. Seeds do not depend on this order. The
# healthy case is last: MR is a no-op there by construction, so it is the cheapest to lose.
EXECUTION_ORDER = (
    'MR-c2-r1', 'L-c2-r1', 'MR-d5-r1', 'MR-c3-r1', 'L-c3-r1', 'MR-d8-r1', 'MR-c4-r1', 'L-c4-r1', 'MR-d12-r1',
    'MR-d17-r1',
    'MR-c2-r2', 'L-c2-r2', 'MR-d5-r2', 'MR-c3-r2', 'L-c3-r2', 'MR-d8-r2', 'MR-c4-r2', 'L-c4-r2', 'MR-d12-r2',
    'MR-d17-r2',
    'MR-healthy',
)


def case_id_for(comparison, setting, replica, replicas):
    stratum = SETTINGS[setting][2]
    stem = f'{comparison}-{stratum or "healthy"}'
    return f'{stem}-r{replica}' if replicas > 1 else stem


def evaluator_case(case):
    """Exactly what PairedEvaluator receives; its batch manifest_hash is content_hash([this])."""
    return {'case_id': case['case_id'], 'fixture_id': case['fixture_id'], 'fault_spec': case['fault_spec']}


def build_cases():
    cases, number = {}, 0
    for comparison, setting, replicas in CASE_TABLE:
        family, kind, stratum, primitives, fixture, target = SETTINGS[setting]
        for replica in range(1, replicas + 1):
            number += 1
            case_id = case_id_for(comparison, setting, replica, replicas)
            spec = FaultSpec.model_validate({'seed': SEED_BASE + number, 'primitives': list(primitives)})
            fault_spec = spec.model_dump(mode='json')
            case = {'case_id': case_id, 'comparison': comparison, 'candidate_hash': COMPARISONS[comparison],
                    'setting': setting, 'family': family, 'block': family, 'kind': kind, 'stratum': stratum,
                    'replica': replica, 'replicas_in_setting': replicas, 'fixture_id': fixture,
                    'expected_version': FIXTURE_VERSIONS[fixture], 'seed': spec.seed, 'fault_spec': fault_spec,
                    'target_outcome': target, 'scenario_hash': content_hash(fault_spec),
                    'schedule_identity': schedule_identity(spec)}
            case['evaluator_manifest_hash'] = content_hash([evaluator_case(case)])
            cases[case_id] = case
    if sorted(cases) != sorted(EXECUTION_ORDER) or len(set(EXECUTION_ORDER)) != len(EXECUTION_ORDER):
        raise PlanningError('The execution order is not a permutation of the declared cases')
    if len({c['scenario_hash'] for c in cases.values()}) != len(cases):
        raise PlanningError('Two declared cases share a scenario hash; the read-out maps episodes by it')
    ordered = [cases[case_id] for case_id in EXECUTION_ORDER]
    for position, case in enumerate(ordered, 1):
        case['position'] = position
    return ordered


# ---------------------------------------------------------------- static reach model ($0)

class _Exhausted(Exception):
    pass


class StaticEpisode:
    """A static model of the upgrade side of one episode, used only to check reachability before
    any spend. It mirrors the simulator's tick rules (each admitted HTTP attempt advances one tick;
    an F2 upgrade completes when the clock reaches acceptance tick + d; F4 fails update_order
    occurrences occurrence..occurrence+count-1 with a retryable 503), the broker's single automatic
    re-send of a retryable failure, the episode budget (18 attempts, 20 ticks, 4 wait cycles of 1-4
    ticks, 32 policy steps) and the policy interpreter's rule/step semantics for the ops MR and L
    use. The $0 mechanism check runs the real stack to confirm it."""

    def __init__(self, primitive=None):
        self.primitive = primitive
        self.tick = self.attempts = self.waits = self.steps = self.update_occurrences = 0
        self.closed = self.deferred = False
        self.exhausted = None
        self.op = None                   # None, or {'state': 'PENDING'/'SUCCEEDED', 'due': tick}
        self.observed = None             # latest status of the upgrade operation the lab has seen
        self.receipt_tick = self.receipt_by = None
        self.policy_updates = 0
        if primitive and (primitive['target_tool'] != 'update_order' or primitive['kind'] not in ('F2', 'F4')):
            raise ValueError('The static model covers F2 and F4 on update_order, or no fault')
        if primitive and primitive['kind'] == 'F2' and primitive['parameters']['terminal_status'] != 'SUCCEEDED':
            raise ValueError('The static model covers F2 SUCCEEDED only')

    def _advance(self, ticks):
        self.tick += ticks
        if self.op and self.op['state'] == 'PENDING' and self.op['due'] <= self.tick:
            self.op['state'] = 'SUCCEEDED'

    def _attempt(self):
        if self.closed:
            raise _Exhausted('business calls closed')
        if self.attempts >= HTTP_ATTEMPT_CAP or self.tick >= DECISION_TICK_CAP:
            raise _Exhausted('HTTP/tick budget exhausted')
        self.attempts += 1
        self._advance(1)

    def _observe(self, by):
        self.observed = self.op['state'] if self.op else 'UNKNOWN'
        if self.observed == 'SUCCEEDED' and self.receipt_tick is None:
            self.receipt_tick, self.receipt_by = self.tick, by

    def update(self, caller):
        """One logical update_order call: a retryable 503 is re-sent once by the broker."""
        for _ in range(2):
            self._attempt()
            self.update_occurrences += 1
            p = self.primitive
            if (p and p['kind'] == 'F4' and p['occurrence'] <= self.update_occurrences
                    < p['occurrence'] + p['parameters']['failure_count']):
                self.observed = 'UNKNOWN'
                continue
            if self.op is None:
                if p and p['kind'] == 'F2' and self.update_occurrences == p['occurrence']:
                    self.op = {'state': 'PENDING', 'due': self.tick + p['parameters']['completion_delay_ticks']}
                else:
                    self.op = {'state': 'SUCCEEDED', 'due': self.tick}
            self._observe(f'{caller}:update_order')
            return

    def read(self, caller):
        self._attempt()
        self._observe(f'{caller}:get_operation_status')

    def wait(self, ticks):
        if self.closed:
            raise _Exhausted('business calls closed')
        if self.waits >= WAIT_CYCLE_CAP or self.tick + ticks > DECISION_TICK_CAP:
            raise _Exhausted('wait/tick budget exhausted')
        self.waits += 1
        self._advance(ticks)

    @property
    def receipt(self):
        return self.receipt_tick is not None

    def condition(self, name):
        if name == 'always':
            return True
        if name == 'upgrade_receipt_missing':
            return not self.receipt
        if name == 'current_operation_pending':
            return not self.receipt and self.observed == 'PENDING'
        if name == 'upgrade_outcome_uncertain':
            return self.update_occurrences > 0 and not self.receipt and self.observed in ('PENDING', 'UNKNOWN', None)
        if name == 'upgrade_succeeded':
            return self.receipt
        if name in ('upgrade_terminal_failure', 'receipt_missing'):
            return False
        raise ValueError(f'The static model does not cover condition {name}')

    def hook(self, content, name):
        """The interpreter's loop for one hook: rules in order, `when` tested once on entry, each
        visited step consumes a policy step and retests only_if. A budget exception inside the
        after_upgrade_response hook closes business (actor.py's handler), as in the real episode."""
        try:
            for rule in content['rules']:
                if rule['hook'] != name or not self.condition(rule['when']):
                    continue
                for step in rule['steps']:
                    if self.steps >= POLICY_STEP_CAP:
                        raise _Exhausted('policy_steps exhausted')
                    self.steps += 1
                    if not self.condition(step.get('only_if', 'always')):
                        continue
                    op = step['op']
                    if op == 'wait_ticks':
                        self.wait(step['ticks'])
                    elif op == 'read_current_operation':
                        self.read('policy')
                    elif op == 'read_order':
                        self._attempt()
                    elif op == 'retry_original_request' and step['service'] == 'orders':
                        if self.update_occurrences:
                            self.policy_updates += 1
                            self.update('policy')
                    elif op == 'defer_unresolved':
                        self.closed = self.deferred = True
                        return
                    elif op == 'require_receipt':
                        pass
                    else:
                        raise ValueError(f'The static model does not cover op {op}')
        except _Exhausted as error:
            self.closed = True
            self.exhausted = str(error)

    def summary(self):
        confirm = self.receipt and not self.closed and self.tick < DECISION_TICK_CAP and self.attempts < HTTP_ATTEMPT_CAP
        return {'receipt_tick': self.receipt_tick, 'receipt_by': self.receipt_by, 'tick_after_hook': self.tick,
                'http_attempts': self.attempts, 'wait_cycles': self.waits, 'policy_steps': self.steps,
                'policy_update_calls': self.policy_updates, 'deferred': self.deferred,
                'budget_exhausted': self.exhausted, 'confirmation_fits': bool(confirm)}


def static_path(content, primitive, *, first_update_tick=MEASURED_FIRST_UPDATE_TICK):
    """The Actor reads the order (first_update_tick - 1 reads), upgrades once, then the policy's
    after_upgrade_response hook runs. Returns the hook's outcome; completable means a SUCCEEDED
    receipt was delivered inside the hook and the confirmation still fits (tick <= 19, business open)."""
    episode = StaticEpisode(primitive)
    for _ in range(first_update_tick - 1):
        episode.read('actor')
    episode.update('actor')
    if content is not None:          # the interpreter invokes the hook after every executed Actor update
        episode.hook(content, 'after_upgrade_response')
    result = episode.summary()
    result['completable_in_hook'] = result['confirmation_fits']
    return result


def b0_poll_path(primitive, *, first_update_tick=MEASURED_FIRST_UPDATE_TICK, resends=0):
    """The empty baseline: no hook. The Actor polls once per turn after its upgrade (turns 3-6; turn 7
    confirms, turn 8 reports), re-sending update_order on its first `resends` polling turns instead.
    Completable if a SUCCEEDED receipt is seen by turn 6."""
    episode = StaticEpisode(primitive)
    for _ in range(first_update_tick - 1):
        episode.read('actor')
    episode.update('actor')
    turn = 2
    while not episode.receipt and turn < 6:
        turn += 1
        try:
            if resends:
                resends -= 1
                episode.update('actor')
            else:
                episode.read('actor')
        except _Exhausted:
            break
    return {'receipt_tick': episode.receipt_tick, 'receipt_turn': turn if episode.receipt else None,
            'completable': episode.receipt and episode.tick < DECISION_TICK_CAP}


def any_policy_f2_bound(first_update_tick):
    """The longest F2 SUCCEEDED delay ANY legal policy can complete: the receipt must be delivered by
    an HTTP attempt at tick <= 19 so the Actor's confirmation lands at tick <= 20, and the upgrade was
    accepted at first_update_tick, so d <= 19 - first_update_tick."""
    return DECISION_TICK_CAP - 1 - first_update_tick


def reach_analysis(mr_content=MR_CONTENT):
    """Declared-setting reachability for MR (blocking if any declared upgrade-side setting is not
    completable at the measured first-update tick) and the scans the protocol quotes."""
    rows, problems = {}, []
    for setting, (family, _, _, primitives, _, _) in SETTINGS.items():
        primitive = primitives[0] if primitives else None
        mr = static_path(mr_content, primitive)
        b0 = b0_poll_path(primitive)
        row = {'mr': mr, 'b0_without_resend': b0}
        if family == 'F4':
            count = primitive['parameters']['failure_count']
            needed = next(n for n in range(0, 10) if b0_poll_path(primitive, resends=n)['completable'])
            row['b0_actor_resends_needed'] = needed
            row['note'] = (f'update_order attempts 1-{count} fail; B0 completes only if the Actor itself re-sends '
                           f'{needed} time(s) (Phase 20: the baseline re-sent in 3 of 27 Block A trials)')
        rows[setting] = row
        if family in FAMILIES and not mr['completable_in_hook']:
            problems.append({'setting': setting, 'check': 'mr_reachability',
                             'error': (f'the manual-reference policy cannot complete {setting} when the Actor upgrades '
                                       f'at tick {MEASURED_FIRST_UPDATE_TICK}: {mr}. Report it; never change the '
                                       f'schedule without a declared replacement')})
    scans = {}
    for first in (1, 2, 3):
        f2 = {d: static_path(mr_content, _f2(d), first_update_tick=first)['completable_in_hook'] for d in range(1, 21)}
        f4 = {c: static_path(mr_content, _f4(c), first_update_tick=first)['completable_in_hook'] for c in range(1, 11)}
        scans[f'first_update_tick_{first}'] = {
            'mr_longest_f2_delay': max((d for d, ok in f2.items() if ok), default=None),
            'mr_f2_delays_completable': [d for d, ok in f2.items() if ok],
            'any_legal_policy_longest_f2_delay': any_policy_f2_bound(first),
            'b0_longest_f2_delay': max((d for d in range(1, 21) if b0_poll_path(_f2(d), first_update_tick=first)['completable']),
                                       default=None),
            'mr_longest_f4_failure_count': max((c for c, ok in f4.items() if ok), default=None)}
    measured = scans[f'first_update_tick_{MEASURED_FIRST_UPDATE_TICK}']
    return {'first_update_tick_measured': MEASURED_FIRST_UPDATE_TICK,
            'first_update_tick_evidence': 'Phase 20 development store: 138 of 138 episodes, both arms, every setting',
            'by_setting': rows, 'scans': scans, 'problems': problems,
            'longest_reachable_f2_delay': measured['mr_longest_f2_delay'],
            'first_unreachable_f2_delay': measured['any_legal_policy_longest_f2_delay'] + 1,
            'bound_derivation': ('any legal policy: the upgrade is accepted at the first-update tick t; its receipt must '
                                 'be delivered by an HTTP attempt at tick <= 19 so the confirmation lands at tick <= 20 '
                                 '(simulator business budget); so d <= 19 - t, 17 at the measured t = 2. MR reaches it: '
                                 'its F2 rule spends 13 wait ticks and 4 reads (17 ticks, all 4 wait cycles) and reads '
                                 'at ticks 7, 12, 17 and 19'),
            'declared_longest': 'F2:d17'}


# ---------------------------------------------------------------- pins

def settings_from_file(path, *, env_path=os.devnull):
    return base.settings_from_file(path, env_path=env_path)


def planned_configuration(settings):
    return base.planned_configuration(settings)


def check_configuration_hash(configuration_hash):
    if configuration_hash != DECLARED_CONFIGURATION_HASH:
        raise PlanningError(f'configuration_hash {configuration_hash} != declared {DECLARED_CONFIGURATION_HASH}')


def current_gate_freeze(root=ROOT):
    return base.current_gate_freeze(root)


def load_expected_freeze(path):
    if sha256_file(path) != DECLARED_FREEZE_FILE_SHA256:
        raise PlanningError('The freeze file is not the declared Phase 22 gate-freeze-after.json')
    expected = json.loads(pathlib.Path(path).read_text())
    if (expected.get('functions') or {}).get(ASSESS_PAIRS_KEY, {}).get('text_sha256') != ASSESS_PAIRS_TEXT_SHA256:
        raise PlanningError('The declared freeze does not contain the unchanged assess_pairs')
    return expected


def check_freeze(current, expected):
    if current != expected:
        raise PlanningError(f'Code on disk differs from the Phase 22 freeze: '
                            f'{base.freeze_differences(current, expected)[:8] or "schema"}')


def loaded_code_problem():
    """The files on disk must be the code this process loaded, and the base runner the reviewed one."""
    try:
        same = (harness_sha256() == LOADED_HARNESS_SHA256 and drift_checker_sha256() == LOADED_DRIFT_CHECKER_SHA256
                and base_runner_sha256() == LOADED_BASE_RUNNER_SHA256
                and pathlib.Path(check_clock_drift.__file__).resolve() == DRIFT_CHECKER.resolve()
                and pathlib.Path(base.__file__).resolve() == BASE_RUNNER.resolve())
    except OSError:
        same = False
    if not same:
        return 'The runner, the base runner or the drift checker on disk is not the code this process loaded; start again'
    if LOADED_BASE_RUNNER_SHA256 != DECLARED_BASE_RUNNER_SHA256:
        return 'run_dev_probe.py is not the reviewed, closed Phase 20 runner this harness builds on'
    return None


def protocol_status(path, harness_sha, expected_sha=None, drift_sha=None, base_sha=None):
    path = pathlib.Path(path) if path else None
    if path is None or not path.is_file():
        return {'path': str(path) if path else None, 'exists': False}
    text = path.read_text(encoding='utf-8')
    lines = {line.strip() for line in text.splitlines()}
    drift_sha = drift_sha or drift_checker_sha256()
    base_sha = base_sha or base_runner_sha256()
    digest = sha256_file(path)
    return {'path': str(path), 'exists': True, 'sha256': digest,
            'matches_expected_sha256': expected_sha is not None and digest == expected_sha,
            'declares_harness_sha256': HARNESS_PIN_LINE.format(sha=harness_sha) in lines,
            'declares_drift_checker_sha256': DRIFT_CHECKER_PIN_LINE.format(sha=drift_sha) in lines,
            'declares_base_runner_sha256': BASE_RUNNER_PIN_LINE.format(sha=base_sha) in lines,
            'declares_manual_reference_policy_sha256': MR_PIN_LINE.format(sha=DECLARED_MR_POLICY_HASH) in lines,
            'declares_configuration_hash': DECLARED_CONFIGURATION_HASH in text,
            'declares_gate_freeze_file_sha256': DECLARED_FREEZE_FILE_SHA256 in text}


PROTOCOL_PINS = (('declares_harness_sha256', 'this harness sha256 on its own runnable-harness-sha256 line'),
                 ('declares_drift_checker_sha256', 'the drift checker sha256 on its own drift-checker-sha256 line'),
                 ('declares_base_runner_sha256', 'the base runner sha256 on its own base-runner-sha256 line'),
                 ('declares_manual_reference_policy_sha256',
                  'the manual-reference policy sha256 on its own manual-reference-policy-sha256 line'),
                 ('declares_configuration_hash', 'configuration hash'),
                 ('declares_gate_freeze_file_sha256', 'gate-freeze file sha256'))


def check_protocol(path, expected_sha, harness_sha, drift_sha=None, base_sha=None):
    status = protocol_status(path, harness_sha, expected_sha, drift_sha, base_sha)
    if not status['exists']:
        raise PlanningError('The protocol file does not exist; declare it before any live run')
    if not expected_sha or not status['matches_expected_sha256']:
        raise PlanningError('The protocol sha256 differs from --expect-protocol-sha256')
    for key, name in PROTOCOL_PINS:
        if not status[key]:
            raise PlanningError(f'The protocol does not declare {name}')
    return status['sha256']


def review_status(path, protocol_sha, harness_sha, drift_sha, base_sha):
    """Phase 20's review record, plus the base runner sha. Written by the operator when the review
    closes and the phase is approved, never by this runner."""
    status = base.review_status(path, protocol_sha, harness_sha, drift_sha)
    if status.get('readable'):
        record = base._read_json(path) or {}
        status['base_runner_matches'] = record.get('base_runner_sha256') == base_sha
    return status


def review_problem(status):
    problem = base.review_problem(status)
    if problem:
        return problem
    if not status.get('base_runner_matches'):
        return 'The review record does not carry the base runner sha256 (bare hex)'
    return None


# ---------------------------------------------------------------- one paid run at a time

def _final(record):
    return (bool(record.get('ended_at')) and record.get('stop_reason') != 'running'
            and str(record.get('status') or '').upper() != 'RUNNING')


def process_list():
    """(pid, ppid, command) for every process, from `ps` (read-only, local, $0)."""
    output = subprocess.run(['ps', '-axww', '-o', 'pid=,ppid=,command='], capture_output=True, text=True,
                            timeout=10, check=True).stdout
    rows = []
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    return rows


# A paid run, by tokens rather than substrings (review round 2), widened in the fail-closed direction in review
# round 3 exactly as the Phase 25 runner's paid_run_command was (slot2_probe.py 28b998ac...; copied here because the
# sibling runners are not pinned by this phase): any interpreter whose file name starts with "python" (python3.13t,
# python3.12-intel64, macOS's framework Python), any path ending in experiments/<name>.py (a runner started from
# scripts/ as experiments/x.py), the separate value of --check-hash-based-pycs, and any prefix of --execute-live from
# "--e" up (argparse accepts every unambiguous prefix, and older runners have no other --e... option).
PYTHON_EXECUTABLE = re.compile(r'python', re.IGNORECASE)      # matched at the start of the file name
PAID_RUNNER_SCRIPT = re.compile(r'(?:.*/)?experiments/[A-Za-z0-9_.-]+\.py')
PYTHON_OPTIONS_WITH_A_VALUE = ('-W', '-X', '--check-hash-based-pycs')
LIVE_FLAG = '--execute-live'
LIVE_FLAG_SHORTEST_ABBREVIATION = '--e'
# What an entry records of the script's path: experiments/<name>.py, with scripts/ before it if present, and nothing
# else (review round 3, found while fixing: cutting the path at its last 'scripts/experiments/' kept the directory
# after it in /x/scripts/experiments/<dir>/experiments/y.py).
RECORDED_SCRIPT = re.compile(r'(?:scripts/)?experiments/[A-Za-z0-9_.-]+\.py$')


def _tokens(command):
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def paid_run_script(command):
    """The experiments/<name>.py a process runs as a paid run, or None. A paid run's first token is a Python
    executable (its file name starts with "python", in any case), the script it runs (its first argument after
    Python's own options, skipping the separate values of -W, -X and --check-hash-based-pycs; -c, -m and - are not a
    script run) is any path ending in experiments/<name>.py, and a later token is --execute-live or any prefix of it
    from "--e" up. A shell, grep, pgrep or editor that merely mentions those words is not a run, and neither is a
    `caffeinate -is python ...` helper (the Python process it belongs to is). The same rule as the Phase 25 runner's
    paid_run_command (review round 3). Only scripts/experiments/<name>.py, or experiments/<name>.py, is returned,
    never the rest of the path."""
    tokens = _tokens(command)
    if not tokens or not PYTHON_EXECUTABLE.match(pathlib.PurePosixPath(tokens[0]).name):
        return None
    index = 1
    while index < len(tokens) and tokens[index].startswith('-'):
        if tokens[index] in ('-c', '-m', '-'):
            return None
        index += 2 if tokens[index] in PYTHON_OPTIONS_WITH_A_VALUE else 1
    if index >= len(tokens) or not PAID_RUNNER_SCRIPT.fullmatch(tokens[index]):
        return None
    if not any(token == LIVE_FLAG or (len(token) >= len(LIVE_FLAG_SHORTEST_ABBREVIATION) and LIVE_FLAG.startswith(token))
               for token in tokens[index + 1:]):
        return None
    return RECORDED_SCRIPT.search(tokens[index]).group(0)


def live_experiment_processes(reader=None):
    """Other processes launched as a paid experiment run (paid_run_script). This process, its ancestors (the
    shell that launched it) and its DESCENDANTS are excluded: `caffeinate -is <python ...>` keeps the original
    pid for Python and forks the caffeinate helper as Python's CHILD, whose command line repeats the launch
    arguments (measured: artifacts/phase26-2026-09-24/prep/caffeinate-probe-r2.txt; the round-1 rule excluded
    ancestors only, so the runbook's own launch would have refused itself). Each entry names only the pid and the script, never the rest of the
    command line (it may carry arguments or inline environment assignments). Fail closed: if the process list
    cannot be read, that is itself a blocking entry."""
    try:
        rows = (reader or process_list)()
    except Exception as error:  # noqa: BLE001
        return [f'the process list could not be read ({type(error).__name__}), so no other paid run can be ruled out']
    parent, children = {}, defaultdict(list)
    for pid, ppid, _ in rows:
        parent[pid] = ppid
        children[ppid].append(pid)
    own, pid = set(), os.getpid()
    while pid and pid not in own:
        own.add(pid)
        pid = parent.get(pid)
    pending = [os.getpid()]
    while pending:
        for child in children.get(pending.pop(), ()):
            if child not in own:
                own.add(child)
                pending.append(child)
    found = []
    for pid, _, command in rows:
        script = None if pid in own else paid_run_script(command)
        if script:
            found.append(f'pid {pid}: {script} {LIVE_FLAG}')
    return found


def other_paid_runs(artifacts, ignore=(), *, processes=None, own_claim=None):
    """Paid runs that may still be running and do not hold :8000: Phase 21's records (its own guard,
    reused); any run manifest (a JSON object with started_at) under a Phase 25, 27, 28 or 29 directory
    that is not final; any launch claim in a phase25-29 live-claims directory (this phase's own
    phase26-live-claims included) whose run has no final manifest, except this process's own claim
    (own_claim); and any other --execute-live experiment process. --ignore-run-record sets a record aside
    only if its launching process is gone, or, naming none, it has not changed for 60 minutes; a live
    process is never set aside. Returns (blocking, ignored)."""
    artifacts = pathlib.Path(artifacts).resolve()
    own = pathlib.Path(own_claim).resolve() if own_claim else None
    blocking, ignored = base.phase21_runs(artifacts, ignore)
    wanted = {(pathlib.Path(p) if pathlib.Path(p).is_absolute() else artifacts.parent / p).resolve()
              for p in ignore or ()}

    def consider(path, why=None):
        if path.resolve() in wanted:
            problem = base.phase21_ignore_problem(path, artifacts)
            if problem is None:
                ignored.append({'record': str(path), 'launching_pid': base.phase21_record_pid(path, artifacts),
                                'set_aside_at': now()})
                return
            blocking.append(f'{path} (--ignore-run-record refused: {problem})')
        else:
            blocking.append(f'{path} ({why})' if why else str(path))

    def final_manifest_in(directory):
        for path in directory.glob('*manifest*.json'):
            record = base._read_json(path)
            if record is not None and 'started_at' in record and _final(record):
                return True
        return False

    for pattern in NEW_PHASE_MANIFEST_GLOBS:
        for path in sorted(artifacts.glob(pattern)):
            try:
                record = json.loads(path.read_text())
            except (OSError, ValueError):
                blocking.append(f'{path} (a run manifest that cannot be read)')
                continue
            if not isinstance(record, dict) or 'started_at' not in record or _final(record):
                continue
            consider(path)
    for claim in sorted(artifacts.glob('phase2[5-9]-live-claims/claim-*.json')):
        if own is not None and claim.resolve() == own:
            continue
        out = (base._read_json(claim) or {}).get('out')
        directory = artifacts.parent / out if isinstance(out, str) else None
        if directory is None or not final_manifest_in(directory):
            consider(claim, 'a launch claim whose run has no final manifest')
    blocking.extend(live_experiment_processes() if processes is None else processes)
    return blocking, ignored


def earlier_phase26_runs(artifacts):
    """Every Phase 26 manifest under artifacts/. Refuses unless each observed nothing (Phase 20's
    undelivered(): no case started, $0 charged, final or its process gone)."""
    artifacts = pathlib.Path(artifacts).resolve()
    found = []
    for path in sorted(artifacts.glob(f'{PHASE_PREFIX}*/**/{MANIFEST_NAME}')):
        manifest = base._read_json(path)
        if not base.undelivered(manifest):
            if manifest is None:
                why = 'its manifest cannot be read'
            elif base.started_cases(manifest) or manifest.get('charged_upper_bound') not in (None, 0, 0.0):
                why = 'it started a case or charged something, so it is final'
            else:
                why = 'it may still be running, or it crashed before finalizing and its process is not known to be gone'
            raise PlanningError(f'Another Phase 26 run exists ({path}): {why}. A second run needs its own '
                                f'declaration and the user\'s approval')
        found.append(str(path.relative_to(artifacts.parent)))
    return found


# The run directory's two path parts use only the characters the Phase 25 and Phase 27 guards accept when
# they follow a claim's `out` (slot2_probe.CLAIMED_RUN, report_word_probe.OTHER_CLAIMED_RUN:
# artifacts/phase2N-[A-Za-z0-9._-]+/[A-Za-z0-9._-]+). A name outside that set would leave a claim the
# siblings cannot follow, so they would block on it forever (review round 2).
RUN_PATH_PART = re.compile(r'[A-Za-z0-9._-]+')


def check_output(output, artifacts):
    output = pathlib.Path(output).resolve()
    if output.exists():
        raise PlanningError('A new output directory is required; saved trials cannot be overwritten or resumed')
    artifacts = pathlib.Path(artifacts).resolve()
    if artifacts not in output.parents:
        raise PlanningError('--output must be inside artifacts/')
    parts = output.relative_to(artifacts).parts
    if (len(parts) != 2 or not parts[0].startswith(PHASE_PREFIX) or parts[0] == CLAIM_DIR
            or not all(RUN_PATH_PART.fullmatch(part) for part in parts)):
        raise PlanningError(f'--output must be artifacts/{PHASE_PREFIX}<date>/<name>, both parts using only letters, '
                            f'digits, ".", "_" and "-"')
    earlier_phase26_runs(artifacts)
    return output


def take_claim(output, artifacts, harness):
    """This run's launch claim, written in full to a private file and then hard-linked to the next free
    artifacts/phase26-live-claims/claim-NN.json, which fails if that name exists ($0; nothing else is
    written). It names the run directory, so the Phase 25 and Phase 27 guards block on it until that
    directory holds a final manifest. Never deleted once the run directory exists."""
    artifacts = pathlib.Path(artifacts).resolve()
    directory = artifacts / CLAIM_DIR
    directory.mkdir(parents=True, exist_ok=True)
    numbers = [int(p.stem[len(CLAIM_PREFIX):]) for p in directory.glob(f'{CLAIM_PREFIX}*.json')
               if p.stem[len(CLAIM_PREFIX):].isdigit()]
    path = directory / f'{CLAIM_PREFIX}{max(numbers, default=0) + 1:02d}.json'
    temporary = directory / f'.{path.name}.{os.getpid()}.tmp'
    try:
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump({'claim': path.name, 'pid': os.getpid(), 'out': str(pathlib.Path(output).resolve().relative_to(
                artifacts.parent)), 'harness_sha256': harness, 'claimed_at': now()}, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise PlanningError(f'{path.name} is already taken: another live launch claimed first; nothing was '
                                f'created. Re-launch') from None
    finally:
        temporary.unlink(missing_ok=True)
    return path


BACKEND_PORT = 8000
LSOF = '/usr/sbin/lsof'
# A FaultLab backend on port 8000 is a uvicorn process serving app.main:app: every launcher in this
# repository (scripts/start-backend.sh, scripts/start-live-backend.sh, the Phase 17 launch_backend.py) execs
# `python -m uvicorn app.main:app`. A --reload backend's worker is a multiprocessing child whose own command
# line names neither, but its reloader parent holds the same listening socket and is recognised (measured:
# artifacts/phase26-2026-09-24/prep/reload-listener-probe-r2.txt).
BACKEND_COMMAND_MARKERS = ('uvicorn', 'app.main')


def lsof_listeners(port, *, run=None):
    """Every socket in LISTEN state on the TCP port, found by STATE (lsof), with the pid holding it, its
    command name, its type (IPv4 or IPv6) and its address ('*:8000' for 0.0.0.0 or ::, '[::1]:8000',
    '127.0.0.1:8000'). Unlike a connection to 127.0.0.1, which times out while this process holds
    127.0.0.1:8000 (review round 2, measured), it sees an IPv4 wildcard server bound beside the hold
    (artifacts/phase26-2026-09-24/prep/lsof-listener-probe-r2.json). lsof run
    as this user lists this user's processes; every FaultLab backend runs as this user. lsof exits 1 with no
    output when nothing matches; any other failure raises, so callers fail closed.

    Review round 3: a mounted but unreachable volume makes lsof print a warning block, 'lsof: WARNING: can't
    stat() ...' followed by indented lines ('Output information may be incomplete.', 'assuming "dev=..." from
    mount table'); round 2 read the indented lines as a failure, so every check failed closed. -b makes lsof avoid
    stat(), lstat() and readlink(), which a hung mount can block past the timeout; -w suppresses its warnings
    (measured: the same listing, and exit 1 with no output on a free port,
    artifacts/phase26-2026-09-24/prep/lsof-flags-probe-r3.txt). A warning's indented continuation lines are also
    skipped here; any other line on stderr is still a failure."""
    executable = LSOF if os.path.exists(LSOF) else (shutil.which('lsof') or LSOF)
    result = (run or subprocess.run)([executable, '-b', '-w', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-F', 'pcnt'],
                                     capture_output=True, text=True, timeout=10)
    if result.returncode == 1 and not result.stdout.strip():
        noise, in_warning = [], False
        for line in result.stderr.splitlines():
            if not line.strip():
                continue
            if line.startswith('lsof: WARNING'):
                in_warning = True
            elif not (in_warning and line[:1] in (' ', '\t')):
                in_warning = False
                noise.append(line)
        if noise:
            raise OSError(f'lsof failed (exit 1): {noise[0][:120]}')
        return []
    if result.returncode != 0:
        raise OSError(f'lsof failed (exit {result.returncode})')
    entries, pid, name, kind = [], None, None, None
    for line in result.stdout.splitlines():
        tag, value = line[:1], line[1:]
        if tag == 'p':
            pid, name, kind = (int(value) if value.isdigit() else None), None, None
        elif tag == 'c':
            name = value
        elif tag == 'f':
            kind = None
        elif tag == 't':
            kind = value
        elif tag == 'n':
            entries.append({'pid': pid, 'name': name, 'type': kind, 'address': value})
    return entries


def process_command(pid):
    """One process's command line from `ps` (read-only, local), or None if it cannot be read."""
    if not isinstance(pid, int):
        return None
    try:
        output = subprocess.run(['ps', '-ww', '-o', 'command=', '-p', str(pid)], capture_output=True, text=True,
                                timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return None
    return output or None


def python_target(tokens):
    """What a Python command line runs, read the way CPython reads its own options: ('-m', module), ('-c', None),
    ('-', None) for standard input, ('script', path), or None when nothing is found or a long option appears.
    Short options may be clustered (`-Bm mod`, `-uW ignore`), and -c, -m, -W and -X take the rest of their token
    or else the next token as their value. Used only for program_label, which must never record a value; the paid-run
    rule (paid_run_script) is kept identical to the Phase 25 runner's."""
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == '--':
            return ('script', tokens[index + 1]) if index + 1 < len(tokens) else None
        if token == '-':
            return ('-', None)
        if not token.startswith('-'):
            return ('script', token)
        if token.startswith('--'):
            return None             # a long option (--check-hash-based-pycs takes a value): record nothing more
        for position, letter in enumerate(token[1:], start=2):
            if letter == 'c':
                return ('-c', None)
            if letter == 'm':
                module = token[position:] or (tokens[index + 1] if index + 1 < len(tokens) else '')
                return ('-m', module) if module else None
            if letter in 'WX':
                if position == len(token):
                    index += 1      # the value is the next token, never recorded
                break
        index += 1
    return None


def program_label(command):
    """A short, safe description of a command line: the program's file name and, for a Python interpreter only,
    the script's file name or the module it runs (-m), or '-c' or '-'. Nothing else is ever recorded: no option,
    no option value, no argument and no NAME=value assignment (review round 3: the round-2 version skipped an
    option but recorded the token after it, so `redis-server --requirepass s3cr3t` was recorded as
    'redis-server s3cr3t')."""
    tokens = _tokens(command or '')
    if not tokens:
        return None
    name = pathlib.PurePosixPath(tokens[0]).name
    target = python_target(tokens) if PYTHON_EXECUTABLE.match(name) else None
    if target is None:
        return name
    kind, value = target
    if kind == '-m':
        return f'{name} -m {value}'
    if kind == 'script':
        return f'{name} {pathlib.PurePosixPath(value).name}'
    return f'{name} {kind}'


def is_faultlab_backend(command):
    return any(marker in token for token in _tokens(command or '') for marker in BACKEND_COMMAND_MARKERS)


def ipv6_loopback_accepts(port, timeout=0.5):
    """Whether something accepts a TCP connection on [::1]:port. Needed only for a listener lsof cannot
    attribute (another user's process); a refused connection returns at once."""
    family = getattr(socket, 'AF_INET6', None)
    if family is None:
        return False
    try:
        probe = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return False
    try:
        probe.settimeout(timeout)
        return probe.connect_ex(('::1', port)) == 0
    except OSError:
        return False
    finally:
        probe.close()


def port_listeners(port=BACKEND_PORT, timeout=0.5, *, lister=None, commands=None, accepts=None):
    """Every listener on the backend port ($0, local), each as {'address', 'pid', 'program', 'backend',
    'seen_by'}. 'backend' is True for a FaultLab backend (a uvicorn app.main process holds the socket), False
    for an identified other program, and None when it cannot be identified: a listener lsof cannot attribute
    (seen only by the [::1] connection probe), a process whose command line cannot be read, or a listing that
    failed (fail closed). No 127.0.0.1 connection is made: while this process holds 127.0.0.1:8000 such a
    connection times out whatever listens on the wildcard address (review round 2, measured)."""
    try:
        entries = (lister or lsof_listeners)(port)
    except Exception as error:  # noqa: BLE001
        return [{'address': f'port {port}', 'pid': None, 'program': None, 'backend': None, 'seen_by': 'lsof',
                 'problem': f'the listening sockets could not be listed ({type(error).__name__}); counted as a listener'}]
    command_of = commands or process_command
    by_socket = {}
    for entry in entries:
        command = command_of(entry['pid'])
        found = by_socket.setdefault((entry['type'], entry['address']), {
            'address': entry['address'], 'type': entry['type'], 'pids': [], 'programs': [], 'backend': False,
            'seen_by': 'lsof'})
        found['pids'].append(entry['pid'])
        found['programs'].append(program_label(command) if command else entry['name'])
        if command is None:
            found['backend'] = None if found['backend'] is False else found['backend']
        elif is_faultlab_backend(command):
            found['backend'] = True
    listeners = [{'address': v['address'], 'type': v['type'], 'pid': v['pids'][0] if len(v['pids']) == 1 else v['pids'],
                  'program': v['programs'][0] if len(v['programs']) == 1 else v['programs'], 'backend': v['backend'],
                  'seen_by': v['seen_by']} for v in by_socket.values()]
    if not any(entry['type'] == 'IPv6' for entry in entries) and (accepts or ipv6_loopback_accepts)(port, timeout):
        listeners.append({'address': f'[::1]:{port}', 'type': 'IPv6', 'pid': None, 'program': None, 'backend': None,
                          'seen_by': 'connect'})
    return listeners


def listener_text(listener):
    who = 'a FaultLab backend' if listener['backend'] else 'unidentified' if listener['backend'] is None else 'not a backend'
    return (f"{listener['address']} (pid {listener['pid']}, {listener['program'] or 'program unknown'}; {who}"
            + (f"; {listener['problem']}" if listener.get('problem') else '') + ')')


def listeners_stop_the_run(listeners):
    """At a case start: a FaultLab backend, or a listener that cannot be identified, stops the run (fail
    closed). An identified other program (for example `python -m http.server`, whose default port is 8000)
    is recorded and the run goes on: it cannot host a lab campaign."""
    return any(listener['backend'] is not False for listener in listeners)


def validate_spend_cap(cap):
    if not math.isfinite(cap) or not 0 < cap <= SPEND_CAP:
        raise PlanningError(f'--spend-cap must be positive and at most ${SPEND_CAP:.2f}')
    return cap


# ---------------------------------------------------------------- policies (read-only)

def load_policies(source_store):
    """B0 and L by hash from the lab store, opened read-only, content hashes verified. The
    manual-reference policy must NOT be in it (it is never saved in any policy store)."""
    path = pathlib.Path(source_store)
    if not path.is_file():
        raise PlanningError('Source lab store not found')
    connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    found = {}
    try:
        for arm, pin in (('B0', BASELINE_POLICY_HASH), ('L', L_POLICY_HASH)):
            rows = connection.execute("SELECT id, payload FROM records WHERE kind='policies' AND instr(payload, ?) > 0",
                                      (pin,)).fetchall()
            matches = [(rid, json.loads(raw)) for rid, raw in rows if json.loads(raw).get('policy_hash') == pin]
            if len(matches) != 1:
                raise PlanningError(f'Expected exactly one stored policy with the declared {arm} hash, found {len(matches)}')
            record_id, raw = matches[0]
            version = PolicyVersion.model_validate_json(canonical_json(raw))
            if (version.version != record_id or version.policy_hash != pin or content_hash(version.content) != pin
                    or content_hash(raw.get('content')) != pin):
                raise PlanningError(f'The stored {arm} policy content does not hash to its declared hash')
            if arm == 'B0' and (record_id != 'policy-v0' or version.decision != 'BASELINE' or version.content.rules):
                raise PlanningError('The baseline is not the unchanged empty policy-v0')
            if arm == 'L' and (record_id != L_POLICY_VERSION or version.decision != 'PROPOSED' or not version.content.rules):
                raise PlanningError('L is not the stored PROPOSED Phase 23 certified policy')
            found[arm] = version
        stored_mr = [rid for rid, raw in connection.execute(
            "SELECT id, payload FROM records WHERE kind='policies' AND instr(payload, ?) > 0", (DECLARED_MR_POLICY_HASH,))
            if json.loads(raw).get('policy_hash') == DECLARED_MR_POLICY_HASH]
    finally:
        connection.close()
    if stored_mr:
        raise PlanningError(f'The manual-reference policy is in the lab store ({stored_mr}); it must never enter a '
                            f'policy store. Stop and find out how it got there')
    return found


def policy_summary(version):
    content = version.content.model_dump(mode='json')
    return {'version': version.version, 'policy_hash': version.policy_hash, 'decision': version.decision,
            'author': version.author, 'rules': len(content['rules']),
            'hooks': [rule['hook'] for rule in content['rules']], 'content': content}


def install_l(coordinator, versions):
    """B0 is the output store's own policy-v0; L is installed unchanged (as Phase 20 installed its
    candidate) so the integrity check can re-read it. MR is never installed."""
    baseline = coordinator.policies.baseline()
    if baseline.policy_hash != BASELINE_POLICY_HASH or baseline.content.rules:
        raise PlanningError('The output store baseline is not the unchanged empty policy')
    coordinator.policies.save(versions['L'])
    stored = coordinator.policies.get(L_POLICY_VERSION)
    if stored is None or content_hash(stored.content) != L_POLICY_HASH or stored.decision != 'PROPOSED':
        raise PlanningError('L did not install unchanged')
    return baseline, stored


def reference_policy_records(store):
    """Policy records in a store that carry the manual-reference hash. Must always be empty."""
    return [p.get('version') for p in store.list_records('policies') if p.get('policy_hash') == DECLARED_MR_POLICY_HASH]


# ---------------------------------------------------------------- ledger admission, spend, power

def ledger_admission(caps, bounds, cap):
    """The real CampaignLedger admission on an in-memory store with the frozen caps (Phase 20's check,
    with this plan's case count)."""
    from app.lab.budgets import CampaignLedger
    from app.lab.storage import LabStore
    actor, admission = bounds['actor'], max(bounds.values())

    def attempt(ledger, name, calls):
        try:
            ledger.reserve(name, calls)
        except BudgetExhausted as error:
            return {'calls': calls, 'admitted': False, 'refusal': str(error)}
        ledger.release(name)
        return {'calls': calls, 'admitted': True}

    at_cap_calls = math.floor(cap / actor + 1e-9)
    store = LabStore(':memory:')
    try:
        fresh = CampaignLedger(store, 'campaign-plan-fresh', caps, dollar_bounds=bounds)
        protected = fresh.reserved_calls
        fresh_case = attempt(fresh, 'gap-probe:plan-case', CASE_RESERVATION_CALLS)
        spent = CampaignLedger(store, 'campaign-plan-at-cap', caps, dollar_bounds=bounds)
        spent.reserve('simulated-charges', at_cap_calls)
        for _ in range(at_cap_calls):
            spent.consume_call(reservation='simulated-charges', role='actor')
        spent.release('simulated-charges')
        spent.reserve('gap-probe:plan-case', CASE_RESERVATION_CALLS)
        at_cap_retry = attempt(spent, 'pair-retry:plan', EVALUATOR_RETRY_CALLS)
        spent.release('gap-probe:plan-case')
        charged_at_cap = spent.used_dollar_upper_bound
    finally:
        store.close()
    return {'rule': ('reserve(n) is admitted while used_upper_bound + (reserved + n) x max-role bound <= campaign '
                     'dollars, and used + reserved + n fits the call and token caps (budgets.CampaignLedger)'),
            'campaign_caps': caps.model_dump(mode='json'), 'caps_frozen_in_configuration_hash': True,
            'protected_reservation_calls': protected, 'per_call_bounds': bounds,
            'caller_owned_case_reservation_calls': CASE_RESERVATION_CALLS,
            'fresh_campaign_case_reservation': fresh_case,
            'at_spend_cap': {'charged_actor_calls': at_cap_calls, 'charged_upper_bound': round(charged_at_cap, 6),
                             'case_reservation_plus_one_evaluator_retry': at_cap_retry,
                             'admission_dollars_needed': round(charged_at_cap + (protected + CASE_RESERVATION_CALLS
                                                                                 + EVALUATOR_RETRY_CALLS) * admission, 6),
                             'campaign_dollars': caps.dollars},
            'admissible': bool(fresh_case['admitted'] and at_cap_retry['admitted'])}


def spend_arithmetic(cases, bound, cap):
    """The declared ~$25 arithmetic at the conservative per-call bound."""
    episode = ACTOR_CALLS_PER_EPISODE * bound
    per_case = 2 * PAIRS_PER_CASE * episode
    n = len(cases)
    last_case_start = (n - 1) * per_case
    return {'actor_call_bound': bound, 'actor_calls_per_episode': ACTOR_CALLS_PER_EPISODE,
            'per_episode': round(episode, 6), 'per_pair': round(2 * episode, 6), 'per_case_3_pairs': round(per_case, 6),
            'cases': n, 'pairs': n * PAIRS_PER_CASE, 'episodes': 2 * n * PAIRS_PER_CASE,
            'expected_worst_without_retries': round(n * per_case, 6),
            'guard_before_each_case': round(CASE_WORST_CALLS * bound, 6),
            'last_case_starts_at_most': round(last_case_start, 6),
            'last_case_admitted_without_retries': last_case_start + CASE_WORST_CALLS * bound <= cap + 1e-9,
            'retry_margin_before_the_guard_can_truncate': round(cap - CASE_WORST_CALLS * bound - last_case_start, 6),
            'cap': cap,
            'by_comparison': {c: {'cases': sum(1 for x in cases if x['comparison'] == c),
                                  'pairs': PAIRS_PER_CASE * sum(1 for x in cases if x['comparison'] == c)}
                              for c in COMPARISONS}}


def rejection_probability(rates_row1, rates_row2, sizes, alpha):
    """P(the one-sided exact conditional MH p, row 1 above row 2, is at most alpha): exact
    enumeration (run_dev_probe.p1_power with no floor)."""
    return base.p1_power(tuple(rates_row1), tuple(rates_row2), tuple(sizes), alpha=alpha, floor=-1)


def power_table(cases):
    """Exact power of the declared primaries under Holm, at planning rates (never this phase's data).
    Holm rejects a family if its p <= 0.025, or if its p <= 0.05 and the other family's p <= 0.025;
    the two families are independent, so P(reject F) = P_F(0.025) + (P_F(0.05) - P_F(0.025)) x P_G(0.025)."""
    sizes = {family: tuple(PAIRS_PER_CASE * sum(1 for c in cases if c['comparison'] == 'MR' and c['setting'] == s)
                           for s in FAMILY_STRATA[family]) for family in FAMILIES}
    rows = []
    for scenario, b0 in PLANNING_B0_RATES.items():
        for mr in PLANNING_MR_RATES:
            at = {family: {level: rejection_probability((mr,) * len(sizes[family]), (b0[family],) * len(sizes[family]),
                                                        sizes[family], level) for level in (ALPHA / 2, ALPHA)}
                  for family in FAMILIES}
            row = {'scenario': scenario, 'b0_rates': dict(b0), 'mr_rate': mr}
            for family, other in (('F4', 'F2'), ('F2', 'F4')):
                half, full = at[family][ALPHA / 2], at[family][ALPHA]
                row[f'power_{family}_holm'] = round(half + (full - half) * at[other][ALPHA / 2], 4)
                row[f'power_{family}_at_0.025'] = round(half, 4)
            rows.append(row)
    return {'trials_per_arm_per_stratum': {f: list(v) for f, v in sizes.items()}, 'rows': rows,
            'note': ('planning figures, not evidence, and they assume independent trials: B0 rates from earlier '
                     'development data (F4: Phase 20 B0 2 of 27; F2 d >= 8: 0, structurally and 0 of 19 at d >= 5), and '
                     'a pessimistic row; MR at 0.3-0.9 in every counted stratum')}


# ---------------------------------------------------------------- plan

def prepare(args, *, artifacts=None):
    artifacts = ARTIFACTS if artifacts is None else artifacts
    problem = loaded_code_problem()
    if problem:
        raise PlanningError(problem)
    cap = validate_spend_cap(args.spend_cap)
    output = check_output(args.output, artifacts)
    cases = build_cases()
    problems, notes = base.validate_cases(cases)
    reach = reach_analysis()
    problems += reach['problems']
    manual = validate_manual_reference()
    base.check_settings_file(args.settings)
    settings = settings_from_file(args.settings)
    caps, frozen, configuration_hash = planned_configuration(settings)
    check_configuration_hash(configuration_hash)
    base.check_models(settings)
    expected_freeze = load_expected_freeze(args.expect_freeze)
    check_freeze(current_gate_freeze(), expected_freeze)
    if ACTOR_CONTEXT_PROTOCOL_V4 != ACTOR_CONTEXT or ACTOR_CONTEXT not in frozen['actor_context_protocols']:
        raise PlanningError('The v4 indexed-evidence Actor context is not in the frozen configuration')
    policies = load_policies(args.source_store)
    bounds = settings.model_call_dollar_bounds
    admission = ledger_admission(caps, bounds, cap)
    if not admission['admissible']:
        raise PlanningError('The per-case reservation is not admissible under the frozen campaign caps')
    harness, drift_sha, base_sha = harness_sha256(), drift_checker_sha256(), base_runner_sha256()
    protocol = protocol_status(args.protocol, harness, getattr(args, 'expect_protocol_sha256', None), drift_sha, base_sha)
    review = review_status(getattr(args, 'review_record', None), protocol.get('sha256'), harness, drift_sha, base_sha)
    blocking, ignored = other_paid_runs(artifacts, getattr(args, 'ignore_run_record', None) or ())
    spend = spend_arithmetic(cases, bounds['actor'], cap)
    plan = {
        'schema_version': PLAN_SCHEMA, 'experiment': 'phase26_gap_probe',
        'question': ('Can a legal manual-reference policy complete the upgrade-side development cases (F4 transient '
                     'update_order failures; F2 SUCCEEDED delays of 8 to 17 ticks) that the empty baseline and the '
                     'certified repairs do not? F2 d5, which the certified repair dd62c857... completed 3 of 3 in '
                     'Phase 20, runs as a descriptive calibration stratum, not as a gap'),
        'purpose': PURPOSE, 'split': 'development', 'actor_context_protocol': ACTOR_CONTEXT,
        'task_text': TASK_TEXT, 'order_id': ORDER_ID,
        'arms': {'B0': BASELINE_POLICY_HASH, 'MR': DECLARED_MR_POLICY_HASH, 'L': L_POLICY_HASH},
        'comparisons': {'MR': {'incumbent': 'B0', 'candidate': 'MR', 'role': 'declared test (primary)'},
                        'L': {'incumbent': 'B0', 'candidate': 'L', 'role': 'descriptive replication'}},
        'store_arm_labels': ('PairedEvaluator labels every candidate trial arm L in the store (the Arm literal has no '
                             'MR); the read-out names arms by policy hash'),
        'policies': {'B0': policy_summary(policies['B0']), 'L': policy_summary(policies['L']), 'MR': manual},
        'l_provenance': L_PROVENANCE,
        'nothing_accepted': True, 'manual_reference_never_stored': True,
        'cases': cases, 'execution_order': list(EXECUTION_ORDER), 'n_cases': len(cases),
        'pairs_per_case': PAIRS_PER_CASE, 'planned_pairs': len(cases) * PAIRS_PER_CASE,
        'planned_episodes': 2 * len(cases) * PAIRS_PER_CASE,
        'distinct_schedules': len({case['schedule_identity'] for case in cases}),
        'schedule_pairs': {setting: {c: PAIRS_PER_CASE * sum(1 for x in cases if x['setting'] == setting and x['comparison'] == c)
                                     for c in COMPARISONS}
                           for setting in SETTINGS},
        'seeds_are_metadata': 'schedule_identity ignores seeds; replicas are reported as schedule x pairs',
        'schedule_problems': problems, 'schedule_notes': notes, 'reach': reach,
        'batching': {'evaluator': 'app.lab.evaluation.PairedEvaluator (unchanged)', 'runs': 'one per case',
                     'three_arms': ('two comparison types, B0 vs MR and B0 vs L, as separate paired batches on the same '
                                    'schedules, interleaved in time; B0 runs in both so each contrast is paired and '
                                    'concurrent (a historical control is not a control)'),
                     'arm_order': ('PairedEvaluator orders arms by (case_index + trial_index) % 2; one case per batch, so '
                                   'B0 runs first in pairs 1 and 3 and the candidate first in pair 2'),
                     'lab_error_pair_retry': ('PairedEvaluator\'s own, once per pair index; nothing else is retried; a '
                                              'retried pair runs on the evaluator\'s own 16-call reservation'),
                     'exception_case': ('a case whose evaluator raises keeps its completed episodes only as unpaired '
                                        'trials (safety and descriptive tables); no pair is reconstructed')},
        'spend': spend, 'ledger_admission': admission,
        'power': power_table(cases),
        'configuration_hash': configuration_hash, 'models': frozen['models'],
        'per_call_dollar_upper_bound': {role: frozen['pricing'][role]['per_call_dollar_upper_bound']
                                        for role in ('actor', 'explorer', 'mechanic')},
        'campaign_budget': frozen['campaign_budget'],
        'pins': {'configuration_hash': DECLARED_CONFIGURATION_HASH, 'settings_sha256': DECLARED_SETTINGS_SHA256,
                 'gate_freeze_file_sha256': DECLARED_FREEZE_FILE_SHA256,
                 'gate_freeze_script_sha256': DECLARED_GATE_FREEZE_SCRIPT_SHA256,
                 'assess_pairs_text_sha256': ASSESS_PAIRS_TEXT_SHA256, 'harness_sha256': harness,
                 'base_runner_sha256': base_sha, 'check_clock_drift_sha256': drift_sha,
                 'manual_reference_policy_sha256': DECLARED_MR_POLICY_HASH},
        'protocol': protocol, 'review_record': review,
        'worlds_dir': {'given': str(pathlib.Path(args.worlds_dir).resolve()),
                       'required': str(base.expected_worlds_dir(artifacts)),
                       'problem': base.worlds_dir_problem(args.worlds_dir, artifacts)},
        'paid_run_guard': {'blocking': blocking, 'ignored_records': ignored,
                           'ignore_requested': [str(p) for p in getattr(args, 'ignore_run_record', None) or ()],
                           'rule': ('this process binds 127.0.0.1:8000 (a server binding 127.0.0.1 or localhost there '
                                    'cannot start) and lists LISTEN sockets on port 8000 by state (lsof, plus a [::1] '
                                    'connection probe): any listener refuses the run before any directory exists; at '
                                    'every case start a FaultLab backend or an unidentified listener stops the run and '
                                    'any other listener is recorded; a non-final Phase 21 manifest or '
                                    'launch claim, a non-final run manifest under a Phase 25, 27, 28 or 29 directory, a '
                                    'phase25-29 launch claim whose run has no final manifest (this run\'s own claim '
                                    'excepted), or any other paid experiment process (ps, by tokens: a Python process '
                                    'running a path ending in experiments/<name>.py with --execute-live or a prefix of it '
                                    'from --e; this process, its ancestors and '
                                    'its descendants, such as the caffeinate helper, excluded) blocks; the run writes its '
                                    'launch claim in '
                                    f'artifacts/{CLAIM_DIR}/ before its last check; --ignore-run-record sets a record '
                                    'aside only if its launching process is gone, or, naming none, it has not changed for '
                                    '60 minutes, and never a live process; a delivered earlier Phase 26 run refuses the '
                                    'plan')},
        'telemetry': {'evaluation_publisher': False, 'evidence_readback': False, 'episode_traces': True,
                      'verdicts': 'local fixed referee (C1-C8), recorded before any telemetry',
                      'last_traces': ('this process ends with the run and closes its Weave worker after at most 3 s, so '
                                      'the last episode\'s trace ends may not upload; verdicts are local')},
        'stop_rules': ['spend_cap', 'configuration_changed / harness_changed / protocol_changed',
                       'reference_policy_stored (the manual-reference hash appears in the output store\'s policies)',
                       'worlds_dir_mismatch (a backstop; ends the phase because a case has started)',
                       f'another_backend_listening (a FaultLab backend, or a listener that cannot be identified, on port '
                       f'{BACKEND_PORT} at a case start; any other listener is recorded in listeners_flagged)',
                       'operator_stop (first Ctrl-C or SIGHUP: at the next pair boundary; second Ctrl-C or SIGTERM: now)',
                       f'infrastructure ({MAX_CONSECUTIVE_INFRASTRUCTURE} consecutive cases)',
                       'other_paid_run_after_claim ($0, 0 cases: another run appeared between the first check and the '
                       'check after this run\'s claim)'],
        'analysis': {
            'primary_population': PRIMARY_POPULATION,
            'populations': {'evaluator_pairs': 'every pair PairedEvaluator returned, untriggered trials retained',
                            'valid_pairs': 'both trials valid and triggered (sensitivity)',
                            'without_lab_defects': 'neither trial shows a lab defect (sensitivity)'},
            'primary': {family: {'strata': list(FAMILY_STRATA[family]), 'comparison': 'MR',
                                 'event': 'COMPLETED (lifecycle and outcome)', 'row_1': 'MR',
                                 'alternative': 'MR above B0',
                                 'test': 'one-sided exact conditional Mantel-Haenszel, stratified by setting'}
                        for family in FAMILIES},
            'calibration_strata': {s: ('descriptive only, never a counted stratum: the certified repair dd62c857... '
                                       'completed F2 d5 3 of 3 in Phase 20') for s in CALIBRATION_STRATA},
            'multiplicity': MULTIPLICITY, 'alpha': ALPHA,
            'labels': ('section 7.2, computed by analyse() from the primary population (R, a, n, b, D, D\', N, reached '
                       'and source-grade strata, replicas) and from every trial of the family\'s safety strata (k and '
                       'the per-family safety test S_F; for F2 the counted strata plus the d5 calibration stratum)'),
            'safety_strata': {family: list(SAFETY_STRATA[family]) for family in FAMILIES},
            'independence': ('p-values and error rates assume independent trials; trials in one stratum may be '
                             'correlated, so each family is also reported per replica (r1, r2) and a disagreement is '
                             'flagged'),
            'descriptive': ['L vs B0 per F4 setting (counts, exact p labelled descriptive, re-send and step mechanism, '
                            'and the section 7.3 label with its chance probability)',
                            'F2 d5 calibration (MR vs B0)', 'healthy MR vs B0', 'MR vs L on F4 (unpaired counts)',
                            'pooled B0 over both comparisons'],
            'safety': ('every C1-C8 failure per arm; counted by heldout_check.harmful; one-sided exact MH (row 1 the '
                       'candidate arm, event counted failure, strata settings), each at '
                       f'{SAFETY_ALPHA} in its own family: MR vs B0 over every MR setting, L vs B0, and MR vs B0 over '
                       'each family\'s safety strata (its counted strata; for F2 also d5; the one the section 7.2 label '
                       'uses); never HARM, never REJECTED; '
                       'report words the Actor was never shown are listed (descriptive)'),
            'mechanism': ('from the event log: policy_step executed by hook and op; who delivered the first SUCCEEDED '
                          'orders receipt (actor or policy, update or status read) and at which tick; whether the Actor '
                          'or the policy re-sent update_order; broker re-sends; waits; defer; premature confirmations'),
            'drift': ('check_clock_drift --require-worlds after the run; per-trial tick drift, count drift and masked F1; '
                      'lab defects are listed beside every table and never excluded')},
        'limits': ['Development split only; no promotion, final-audit or heldout manifest is read.',
                   'Nothing is accepted, activated or promoted; results never feed the Mechanic or any model.',
                   'MR is a manual reference: it is never stored, shown, certified or promoted.',
                   'Seeds are metadata: replicas of one schedule are schedule x pairs, not distinct cases.',
                   'No retry or replacement of any attempted, invalid, interrupted or unfavourable trial.'],
        'output_directory': str(output),
    }
    return plan, policies


def live_blockers(plan, args, *, artifacts=None):
    blockers = []
    if plan['schedule_problems']:
        blockers.append('A declared schedule is invalid or unreachable (schedule_problems); the protocol must declare '
                        'its replacement before any live run')
    protocol = plan['protocol']
    if not protocol.get('exists'):
        blockers.append('The protocol file does not exist')
    elif not protocol.get('matches_expected_sha256'):
        blockers.append('--expect-protocol-sha256 is missing or differs from the protocol file')
    elif not all(protocol.get(key) for key, _ in PROTOCOL_PINS):
        blockers.append('The protocol does not declare every pin on its own line (harness, base runner, drift checker, '
                        'manual-reference policy), the configuration hash and the gate-freeze file sha256')
    problem = review_problem(plan.get('review_record') or {})
    if problem:
        blockers.append(problem)
    if not args.confirm_entity:
        blockers.append('--confirm-entity is required')
    artifacts = ARTIFACTS if artifacts is None else artifacts
    worlds = base.worlds_dir_problem(args.worlds_dir, artifacts)
    if worlds:
        blockers.append(worlds)
    active, _ = other_paid_runs(artifacts, getattr(args, 'ignore_run_record', None) or ())
    if active:
        blockers.append(f'Another paid run may be in progress ({active[0]}); one paid run at a time')
    return blockers


# ---------------------------------------------------------------- execution

StopFlags = base.StopFlags
SpendGuard = base.SpendGuard
PairBoundaryRunner = base.PairBoundaryRunner


def batch_summary(batch, labels):
    lookup = {t.episode_id: t for t in batch.trials}
    paired = [lookup[e] for pair in batch.trial_pairs for e in pair if e in lookup]
    in_pairs = {e for pair in batch.trial_pairs for e in pair}
    by_arm = {}
    for policy_hash, label in labels.items():
        rows = [t for t in paired if t.policy_hash == policy_hash]
        by_arm[label] = base.summarize(rows)['counts']
    return {'batch_id': batch.batch_id, 'decision': batch.decision, 'reason': batch.reason,
            'pairs': len(batch.trial_pairs), 'trials': len(batch.trials),
            'retained_unpaired': [{'episode_id': t.episode_id, 'arm': labels.get(t.policy_hash, t.arm),
                                   'lifecycle': t.lifecycle} for t in batch.trials if t.episode_id not in in_pairs],
            'by_arm': by_arm}


def find_batch_id(store, case, baseline_hash, known):
    for record in store.list_records('evaluations'):
        if (record.get('manifest_hash') == case['evaluator_manifest_hash'] and record['batch_id'] not in known
                and (record.get('incumbent_hash'), record.get('candidate_hash')) == (baseline_hash, case['candidate_hash'])):
            return record['batch_id']
    return None


async def run_cases(cases, *, coordinator, campaign_id, baseline, arms, runner, ledger, guard, flags,
                    integrity=lambda full: None, record_case=lambda entry: None,
                    max_consecutive=MAX_CONSECUTIVE_INFRASTRUCTURE):
    """Run each declared case once, in order, as one PairedEvaluator batch of B0 against the case's
    comparison arm (arms: {'MR': ReferenceArm, 'L': PolicyVersion}). Returns (stop_reason, entries);
    every entry is recorded before and after its case (Phase 20's loop, two candidate arms)."""
    entries, consecutive, seen = [], 0, set()
    for case in cases:
        if flags.hard or flags.soft:
            return 'operator_stop', entries
        problem = integrity(True)
        if problem:
            return problem, entries
        if not guard.before_case():
            return 'spend_cap', entries
        candidate = arms[case['comparison']]
        if candidate.policy_hash != case['candidate_hash']:
            return 'configuration_changed', entries
        labels = {baseline.policy_hash: 'B0', candidate.policy_hash: case['comparison']}
        entry = {'position': case['position'], 'case_id': case['case_id'], 'setting': case['setting'],
                 'comparison': case['comparison'], 'status': 'RUNNING', 'started_at': now(),
                 'charged_before': round(guard.charged, 6), 'used_calls_before': ledger.used_calls}
        entries.append(entry)
        record_case(entry)
        pair_stop = {}

        def stop_at_pair_boundary():
            if not pair_stop:
                if flags.hard or flags.soft:
                    pair_stop['reason'] = 'operator_stop'
                elif not guard.between_pairs():
                    pair_stop['reason'] = 'spend_cap'
                else:
                    changed = integrity(False)
                    if changed:
                        pair_stop['reason'] = changed
            return bool(pair_stop)

        reservation = f'gap-probe:{case["case_id"]}:{new_id("r")}'
        refused = infrastructure = False
        try:
            ledger.reserve(reservation, CASE_RESERVATION_CALLS)
        except BudgetExhausted as error:
            refused = True
            entry.update(status='NOT_STARTED', ledger_refusal=str(error))
        if not refused:
            entry['reservation'] = {'name': reservation, 'calls': CASE_RESERVATION_CALLS}
            evaluator = PairedEvaluator(coordinator.store, PairBoundaryRunner(runner, lambda: flags.hard), ledger,
                                        publisher=None)
            try:
                batch = await evaluator.run(coordinator.get(campaign_id), [evaluator_case(case)], baseline, candidate,
                                            purpose=PURPOSE, reservation=reservation, stop=stop_at_pair_boundary,
                                            actor_context_protocol=ACTOR_CONTEXT)
                seen.add(batch.batch_id)
                entry.update(status='RETURNED', **batch_summary(batch, labels))
                refused = batch.reason == LEDGER_REFUSAL_REASON
                infrastructure = (entry['pairs'] < PAIRS_PER_CASE and not pair_stop and not refused
                                  and not (flags.soft or flags.hard))
            except Exception as error:  # noqa: BLE001 - an infrastructure failure of this case
                batch_id = find_batch_id(coordinator.store, case, baseline.policy_hash, seen)
                if batch_id:
                    seen.add(batch_id)
                entry.update(status='EXCEPTION', error_type=type(error).__name__, batch_id=batch_id)
                infrastructure = not (flags.soft or flags.hard)
            finally:
                left = ledger.reservations.get(reservation, {}).get('calls')
                ledger.release(reservation)
                entry['reservation']['unspent_calls'] = left
        entry.update(infrastructure_failure=infrastructure, pair_stop=pair_stop.get('reason'), ended_at=now(),
                     charged_after=round(guard.charged, 6), used_calls_after=ledger.used_calls)
        entry['charged_case'] = round(entry['charged_after'] - entry['charged_before'], 6)
        record_case(entry)
        consecutive = consecutive + 1 if infrastructure else 0
        if refused:
            return 'spend_cap', entries
        if flags.hard or flags.soft:
            return 'operator_stop', entries
        if pair_stop:
            return pair_stop['reason'], entries
        if consecutive >= max_consecutive:
            return 'infrastructure', entries
    return 'completed', entries


write_json = base.write_json
say = base.say


async def simulator_ready(settings):
    return await base.simulator_ready(settings)


def live_base_settings(args):
    """The settings file's non-empty overrides over the app's own environment: the only .env read
    (by the app), and only after --execute-live."""
    return base.live_base_settings(args)


def run_drift_check(store_path, worlds_dir, since):
    return base.run_drift_check(store_path, worlds_dir, since)


def plan_record(plan, probe_id, campaign_id, protocol_sha, started):
    return {**plan, 'probe_id': probe_id, 'campaign_id': campaign_id, 'protocol_sha256': protocol_sha,
            'started_at': started}


async def execute(args, plan, policies, *, artifacts=None):
    from app.lab.budgets import CampaignLedger
    from app.lab.coordinator import LabCoordinator
    from app.lab.storage import LabStore
    artifacts = ARTIFACTS if artifacts is None else artifacts
    # Holding the port refuses to run beside the dashboard backend and prevents one starting.
    port = socket.socket()
    try:
        port.bind(('127.0.0.1', 8000))
    except OSError:
        port.close()
        raise PlanningError('127.0.0.1:8000 is in use. Stop the backend before this in-process probe (keep the '
                            'simulator running). If the backend is already stopped, its closed connections can hold '
                            'the port for about 30 s (TIME_WAIT): wait and retry') from None
    output = args.output.resolve()
    manifest_path = output / MANIFEST_NAME
    store = coordinator = runner = None
    owned = False
    flags = StopFlags()
    loop = asyncio.get_running_loop()
    manifest = None
    stop_reason, campaign_id = 'aborted', None
    installed = []
    signals_seen = []

    def save():
        write_json(manifest_path, manifest)

    def on_interrupt():
        if flags.soft:
            flags.hard = True
        flags.soft = True
        signals_seen.append({'at': now(), 'signal': 'SIGINT', 'hard': flags.hard})
        say({'operator_stop': 'now' if flags.hard else 'at the next pair boundary'})

    def on_terminate():
        flags.soft = flags.hard = True
        signals_seen.append({'at': now(), 'signal': 'SIGTERM', 'hard': True})

    def on_hangup():
        flags.soft = True
        signals_seen.append({'at': now(), 'signal': 'SIGHUP', 'hard': flags.hard})
        say({'operator_stop': 'SIGHUP: at the next pair boundary'})

    try:
        handlers = [(signal.SIGINT, on_interrupt), (signal.SIGTERM, on_terminate)]
        if signal.getsignal(signal.SIGHUP) is not signal.SIG_IGN:     # respect nohup
            handlers.append((signal.SIGHUP, on_hangup))
        for sig, handler in handlers:
            loop.add_signal_handler(sig, handler)
            installed.append(sig)
        live = live_base_settings(args)
        if live.artifact_path.resolve() != pathlib.Path(artifacts).resolve():
            raise PlanningError('The live settings put the artifact directory somewhere other than artifacts/, so a '
                                'simulator started with them would not write its worlds to --worlds-dir')
        live = replace(live, faultlab_control_token=live.local_control_token())
        settings = replace(live, faultlab_aria_publish_enabled=False, faultlab_artifact_dir=str(output))
        settings.require_live()
        base.check_models(settings)
        if args.confirm_entity != settings.wandb_entity:
            raise PlanningError('--confirm-entity must match WANDB_ENTITY in the settings file')
        caps, _, configuration_hash = planned_configuration(settings)
        check_configuration_hash(configuration_hash)
        expected_freeze = load_expected_freeze(args.expect_freeze)
        check_freeze(current_gate_freeze(), expected_freeze)
        pins = plan['pins']
        harness, drift_sha, base_sha = pins['harness_sha256'], pins['check_clock_drift_sha256'], pins['base_runner_sha256']
        protocol_sha = check_protocol(args.protocol, args.expect_protocol_sha256, harness, drift_sha, base_sha)
        if harness_sha256() != harness or base_runner_sha256() != base_sha or drift_checker_sha256() != drift_sha:
            raise PlanningError('The harness, the base runner or the drift checker changed after planning')
        problem = loaded_code_problem()
        if problem:
            raise PlanningError(problem)
        review = review_status(args.review_record, protocol_sha, harness, drift_sha, base_sha)
        problem = review_problem(review)
        if problem:
            raise PlanningError(problem)
        if {arm: v.policy_hash for arm, v in load_policies(args.source_store).items()} != {
                'B0': plan['arms']['B0'], 'L': plan['arms']['L']}:
            raise PlanningError('The stored policies changed after planning')
        reference = manual_reference()
        if reference.policy_hash != plan['arms']['MR'] or validate_manual_reference()['policy_hash'] != plan['arms']['MR']:
            raise PlanningError('The manual-reference policy changed after planning')
        problem = base.worlds_dir_problem(args.worlds_dir, artifacts)
        if problem:
            raise PlanningError(problem)
        ignore = getattr(args, 'ignore_run_record', None) or ()
        active, ignored_runs = other_paid_runs(artifacts, ignore)
        if active:
            raise PlanningError(f'Another paid run may be in progress ({active[0]}); one paid run at a time')
        listening = port_listeners()
        if listening:
            raise PlanningError(f'Something listens on port {BACKEND_PORT} although this process holds '
                                f'127.0.0.1:{BACKEND_PORT} ({"; ".join(map(listener_text, listening))}). Stop it before '
                                f'the run; start backends only with the repository launchers')
        earlier = earlier_phase26_runs(artifacts)
        readiness = await simulator_ready(settings)
        if not readiness.get('ready'):
            raise PlanningError(f"The simulator is not ready ({readiness.get('code')}); start it with "
                                f"scripts/start-simulator.sh")
        if flags.soft or flags.hard:
            raise PlanningError('The operator stopped the run before it started; nothing was created')
        # Write first, then check: the claim is visible to the Phase 25 and 27 guards before this
        # process's last check for other runs, so two launches cannot both pass unseen.
        claim = take_claim(output, artifacts, harness)
        try:
            output.mkdir(parents=True, exist_ok=False)
        except OSError:
            claim.unlink(missing_ok=True)     # its directory was never ours; nothing ran
            raise PlanningError('The output directory appeared during the launch checks; nothing was created. Use a '
                                'new --output') from None
        started = now()
        manifest = {'schema_version': SCHEMA, 'plan_file': 'plan.json', 'started_at': started, 'stop_reason': 'running',
                    'pid': os.getpid(), 'claim': str(claim.relative_to(pathlib.Path(artifacts).resolve().parent)),
                    'declared': {**pins, 'protocol_sha256': protocol_sha,
                                 'review_record_sha256': review.get('sha256'), 'approved_by': review.get('approved_by'),
                                 'spend_cap': args.spend_cap, 'purpose': PURPOSE, 'actor_context_protocol': ACTOR_CONTEXT,
                                 'arms': plan['arms'], 'case_reservation_calls': CASE_RESERVATION_CALLS,
                                 'case_worst_calls': CASE_WORST_CALLS, 'pair_worst_calls': PAIR_WORST_CALLS,
                                 'worlds_dir': str(pathlib.Path(args.worlds_dir).resolve())},
                    'earlier_undelivered_runs': earlier, 'ignored_run_records': ignored_runs,
                    'campaign_id': None, 'probe_id': None, 'cases': [], 'charged_upper_bound': 0.0,
                    'operator_signals': signals_seen}
        write_json(output / 'plan.json', plan)
        save()
        # The last check, after the claim and the manifest exist. A sibling that passed its own guard
        # before this claim was visible is caught here; this run then ends at $0 with 0 cases.
        late, late_ignored = other_paid_runs(artifacts, ignore, own_claim=claim)
        if late:
            manifest['blockers_after_claim'] = late
            stop_reason = 'other_paid_run_after_claim'
            raise PlanningError(f'Another paid run appeared during the launch ({late[0]}); this run ends at $0 with 0 '
                                f'cases')
        manifest['ignored_run_records'] = ignored_runs + [r for r in late_ignored
                                                          if r['record'] not in {i['record'] for i in ignored_runs}]
        store = LabStore(output / 'lab.sqlite3')
        coordinator = LabCoordinator(settings, store=store)
        campaign = coordinator.create(CampaignRequest(task_text=TASK_TEXT, order_id=ORDER_ID, mode='baseline',
                                                      config_profile_id='live-v1'))
        campaign_id = campaign.campaign_id
        manifest['campaign_id'] = campaign_id
        save()
        if campaign.configuration_hash != DECLARED_CONFIGURATION_HASH or campaign.caps != caps:
            raise PlanningError('The created campaign does not carry the declared configuration')
        if store.get_record('campaign_provenance', campaign_id).get('aria_publication_enabled') is not False:
            raise PlanningError('Aria publication must stay off')
        baseline, l_version = install_l(coordinator, policies)
        arms = {'MR': reference, 'L': l_version}
        ledger = CampaignLedger(store, campaign_id, campaign.caps, dollar_bounds=settings.model_call_dollar_bounds)
        coordinator.ledgers[campaign_id] = ledger
        campaign = coordinator.get(campaign_id)
        campaign.execution_epoch += 1
        campaign.state = 'RUNNING'
        campaign.state_seq += 1
        coordinator.save(campaign)
        coordinator.active_id = campaign_id
        probe_id = new_id('gap-probe')
        manifest['probe_id'] = probe_id
        store.put_record(PLAN_RECORD, probe_id, plan_record(plan, probe_id, campaign_id, protocol_sha, started),
                         immutable=True)
        save()
        runner, owned = await coordinator._get_runner(True)
        guard = SpendGuard(ledger, args.spend_cap, settings.model_call_dollar_bounds['actor'])
        worlds_confirmed = {}

        def worlds_directory_problem():
            if worlds_confirmed:
                return None
            first = next((e for e in store.list_records('episodes') if e.get('world_id')), None)
            if first is None:
                return None
            if (pathlib.Path(args.worlds_dir) / f"{first['world_id']}.sqlite3").exists():
                worlds_confirmed.update(episode_id=first['episode_id'], at=now())
                manifest['worlds_dir_confirmed'] = dict(worlds_confirmed)
                return None
            return 'worlds_dir_mismatch'

        def integrity(full):
            try:
                if (harness_sha256() != harness or drift_checker_sha256() != drift_sha
                        or base_runner_sha256() != base_sha):
                    return 'harness_changed'
            except Exception:  # noqa: BLE001
                return 'harness_changed'
            try:
                if sha256_file(args.protocol) != protocol_sha:
                    return 'protocol_changed'
            except Exception:  # noqa: BLE001
                return 'protocol_changed'
            try:
                if reference_policy_records(store):
                    return 'reference_policy_stored'
            except Exception:  # noqa: BLE001
                return 'configuration_changed'
            try:
                problem = worlds_directory_problem()
            except Exception:  # noqa: BLE001
                problem = 'worlds_dir_mismatch'
            if problem:
                return problem
            if not full:
                return None
            try:
                coordinator.validate_core_configuration(coordinator.get(campaign_id))
                if current_gate_freeze() != expected_freeze:
                    return 'configuration_changed'
                stored = coordinator.policies.get(L_POLICY_VERSION)
                if stored is None or content_hash(stored.content) != L_POLICY_HASH:
                    return 'configuration_changed'
                if content_hash(reference.content) != DECLARED_MR_POLICY_HASH:
                    return 'configuration_changed'
            except Exception:  # noqa: BLE001
                return 'configuration_changed'
            # Port 8000 at every case start (review round 2): a FaultLab backend, or a listener that cannot be
            # identified, ends the phase; an identified other program is recorded and the run goes on.
            try:
                listening = port_listeners()
            except Exception:  # noqa: BLE001
                return 'another_backend_listening'
            if listeners_stop_the_run(listening):
                manifest['listener_that_stopped_the_run'] = listening
                return 'another_backend_listening'
            if listening:
                manifest.setdefault('listeners_flagged', []).append(
                    {'at': now(), 'before_case_position': len(manifest['cases']) + 1, 'listeners': listening})
            return None

        def record_case(entry):
            rows = manifest['cases']
            if rows and rows[-1]['position'] == entry['position']:
                rows[-1] = dict(entry)
            else:
                rows.append(dict(entry))
            manifest['charged_upper_bound'] = round(guard.charged, 6)
            store.put_record(CASE_RECORD, f'{probe_id}:{entry["case_id"]}', entry)
            save()
            if entry.get('ended_at'):
                say({'case': entry['case_id'], 'pairs': entry.get('pairs'), 'status': entry['status'],
                     'by_arm': {arm: {k: v[k] for k in ('completed', 'safe_unresolved', 'violations', 'untriggered')}
                                for arm, v in (entry.get('by_arm') or {}).items()},
                     'charged': entry['charged_after']})

        stop_reason, _ = await run_cases(plan['cases'], coordinator=coordinator, campaign_id=campaign_id,
                                         baseline=baseline, arms=arms, runner=runner, ledger=ledger, guard=guard,
                                         flags=flags, integrity=integrity, record_case=record_case)
    except PlanningError as error:
        if manifest is None:
            raise
        manifest['abort_detail'] = str(error)
    except Exception as error:  # noqa: BLE001
        if manifest is None:
            raise
        manifest['abort_detail'] = f'{type(error).__name__} (details withheld; see the store)'
    finally:
        # Finalized first, while the signal handlers are still installed (Phase 20, section 8).
        if manifest is not None:
            manifest['stop_reason'] = stop_reason
            manifest['ended_at'] = now()
            with contextlib.suppress(Exception):
                save()
        if owned and runner is not None:
            for resource in (runner.world_client, runner.provider, getattr(runner, 'telemetry_worker', None)):
                if resource is not None:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(resource.close(), timeout=3)
        if coordinator is not None and campaign_id is not None:
            with contextlib.suppress(Exception):
                state = {'completed': 'COMPLETED', 'operator_stop': 'STOPPED', 'spend_cap': 'NO_CHANGE'}.get(stop_reason, 'ERROR')
                coordinator.transition(campaign_id, state, f'Phase 26 gap probe: {stop_reason}; nothing accepted')
            coordinator.active_id = None
        if store is not None:
            store.close()
        for sig in installed:
            with contextlib.suppress(Exception):
                loop.remove_signal_handler(sig)
        port.close()
    drift = {'exit_status': None, 'world_files_missing': None, 'passed': False, 'output': 'no output store was created'}
    if (output / 'lab.sqlite3').exists():
        try:
            drift = run_drift_check(output / 'lab.sqlite3', args.worlds_dir, manifest['started_at'][:10])
        except Exception as error:  # noqa: BLE001
            drift = {'exit_status': None, 'world_files_missing': None, 'passed': False,
                     'output': f'drift check failed: {type(error).__name__}'}
        try:
            result = readout(output / 'lab.sqlite3', worlds_dir=args.worlds_dir)
            write_json(output / 'readout.json', result)
            manifest['readout'] = {key: result[key] for key in ('complete', 'pairs', 'multiplicity')}
            manifest['readout']['families'] = {f: {k: result['families'][f][k] for k in ('reading', 'p_exact_one_sided',
                                                                                        'holm_tested', 'holm_level')}
                                               for f in FAMILIES}
            manifest['readout']['safety'] = {k: result['safety'][k]['reading'] for k in ('mr_vs_b0_test', 'l_vs_b0_test')}
            manifest['readout']['safety']['by_family'] = {f: result['safety']['by_family'][f]['reading'] for f in FAMILIES}
            manifest['readout']['labels'] = {f: result['labels'][f]['label'] for f in FAMILIES}
            manifest['readout']['l_label'] = result['l_vs_b0']['label']
            manifest['readout']['reference_policy_records_in_store'] = result['reference_policy_records_in_store']
        except Exception as error:  # noqa: BLE001
            manifest['readout_error'] = str(error) if isinstance(error, PlanningError) else type(error).__name__
    manifest['drift_check'] = drift
    (output / 'drift-check.txt').write_text(drift['output'])
    save()
    say({'stop_reason': stop_reason, 'cases_run': len(manifest['cases']),
         'charged_upper_bound': manifest['charged_upper_bound'], 'drift_exit_status': drift['exit_status'],
         'drift_check_passed': drift['passed'], 'manifest': str(manifest_path), 'readout': manifest.get('readout')},
        indent=2)
    return 0 if stop_reason == 'completed' and drift['passed'] else 1


# ---------------------------------------------------------------- read-out (output store only)

completed = base.completed
counted_failure = base.counted_failure
lab_defects = base.lab_defects
wilson = base.wilson


def mechanism_fields(events):
    """What happened on the upgrade side, from the event log only (pitfalls 78-79): who dispatched
    what, who delivered the first SUCCEEDED orders receipt and when, waits, executed policy steps,
    confirmations and the report's upgrade word against the statuses the Actor was shown."""
    dispatch, attempts = {}, Counter()
    for e in events:
        if e.get('type') == 'tool_dispatched':
            payload = e.get('payload') or {}
            dispatch.setdefault(e.get('call_id'), (payload.get('caller') or 'actor', payload.get('tool'), e.get('tick')))
            attempts[e.get('call_id')] += 1
    logical = Counter((caller, tool) for caller, tool, _ in dispatch.values())
    resent = Counter((dispatch[c][0], dispatch[c][1]) for c, n in attempts.items() if n > 1)
    upgrade_op = None
    for e in events:
        if e.get('type') == 'observation_delivered':
            result = ((e.get('payload') or {}).get('observation') or {}).get('result') or {}
            if result.get('tool') == 'update_order' and result.get('operation_id'):
                upgrade_op = result['operation_id']
                break
    shown, receipt, receipt_status = [], None, None
    for e in events:
        if e.get('type') != 'observation_delivered':
            continue
        observation = (e.get('payload') or {}).get('observation') or {}
        result = observation.get('result') or {}
        if upgrade_op is None or result.get('operation_id') != upgrade_op:
            continue
        status = result.get('status') or 'UNKNOWN'
        shown.append(status)
        data = result.get('data') if isinstance(result.get('data'), dict) else {}
        terminal = (data.get('receipt') or {}).get('status') if result.get('transport') == 'ok' else None
        if terminal and receipt is None:
            caller, tool, _ = dispatch.get(e.get('call_id'), ('unknown', result.get('tool'), None))
            receipt = {'by': f'{caller}:{tool}', 'tick': observation.get('delivered_tick', e.get('tick'))}
            receipt_status = terminal
    confirmations = sorted(tick for caller, tool, tick in dispatch.values()
                           if caller == 'actor' and tool == 'send_confirmation' and tick is not None)
    executed = Counter(f"{(e.get('payload') or {}).get('hook')}:{(e.get('payload') or {}).get('op')}" for e in events
                       if e.get('type') == 'policy_step' and (e.get('payload') or {}).get('executed'))
    waits = [((e.get('payload') or {}).get('ticks') or 0) for e in events if e.get('type') == 'wait_completed']
    report = next(((e.get('payload') or {}).get('report') for e in events if e.get('type') == 'report_submitted'), None)
    word = (report or {}).get('upgrade_outcome')
    if word in ('SUCCEEDED', 'FAILED'):
        not_shown = receipt_status != word
    elif word == 'PENDING':
        not_shown = 'PENDING' not in shown
    elif word == 'NOT_STARTED':
        not_shown = upgrade_op is not None
    else:
        not_shown = False
    actor_updates, policy_updates = logical[('actor', 'update_order')], logical[('policy', 'update_order')]
    return {'upgrade_statuses_shown': shown,
            'receipt_status': receipt_status,
            'receipt_by': receipt['by'] if receipt and receipt_status == 'SUCCEEDED' else None,
            'receipt_tick': receipt['tick'] if receipt and receipt_status == 'SUCCEEDED' else None,
            'actor_update_calls': actor_updates, 'policy_update_calls': policy_updates,
            'actor_resent_update': actor_updates >= 2,
            'update_resent_by': ('both' if actor_updates >= 2 and policy_updates else 'actor' if actor_updates >= 2
                                 else 'policy' if policy_updates else 'none'),
            'broker_resends': {f'{caller}:{tool}': n for (caller, tool), n in sorted(resent.items())},
            'policy_reads': logical[('policy', 'get_operation_status')],
            'waits': len(waits), 'wait_ticks': sum(waits),
            'steps_executed': dict(executed), 'deferred': executed.get('after_upgrade_response:defer_unresolved', 0) > 0,
            'confirmations': len(confirmations), 'first_confirmation_tick': confirmations[0] if confirmations else None,
            'premature_confirmation': bool(confirmations) and (receipt is None or receipt_status != 'SUCCEEDED'
                                                               or confirmations[0] <= receipt['tick']),
            'report_upgrade_word': word, 'upgrade_word_not_shown': bool(report) and not_shown}


def arm_of(policy_hash, arms):
    return {value: key for key, value in arms.items()}.get(policy_hash)


def trial_row(episode, trial, case, events, *, paired, arms):
    row = base.trial_row(episode, trial, case, events, paired=paired)
    row.update(arm=arm_of(episode.get('policy_hash'), arms) or 'unknown', store_arm_label=episode.get('arm'),
               comparison=case['comparison'], family=case['family'], policy_hash=episode.get('policy_hash'))
    row.update(mechanism_fields(events))
    return row


def readout(store_path, worlds_dir=None):
    """The declared read-out, from the output store only (opened read-only), with the world scan when
    worlds_dir is given (the live run always passes it). Only the pinned harness, base runner and
    drift checker may compute it."""
    path = pathlib.Path(store_path)
    if not path.is_file():
        raise PlanningError(f'The read-out store does not exist ({path})')
    computed_with = {'harness_sha256': LOADED_HARNESS_SHA256, 'base_runner_sha256': LOADED_BASE_RUNNER_SHA256,
                     'check_clock_drift_sha256': LOADED_DRIFT_CHECKER_SHA256}
    connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        def records(kind):
            return [json.loads(p) for (p,) in connection.execute(
                'SELECT payload FROM records WHERE kind=? ORDER BY rowid', (kind,))]
        try:
            plans = records(PLAN_RECORD)
        except sqlite3.DatabaseError:
            raise PlanningError(f'{path} cannot be read as a lab store') from None
        if len(plans) != 1:
            raise PlanningError(f'{path} holds {len(plans)} Phase 26 plan records; a Phase 26 output store holds exactly '
                                f'one (the main lab store holds none)')
        plan = plans[0]
        pins = plan.get('pins') or {}
        pinned = {'harness_sha256': pins.get('harness_sha256'), 'base_runner_sha256': pins.get('base_runner_sha256'),
                  'check_clock_drift_sha256': pins.get('check_clock_drift_sha256')}
        if pinned != computed_with:
            raise PlanningError('This runner, base runner or drift checker is not the code the run pinned (the plan '
                                'record\'s pins); the declared read-out is computed only by the pinned code')
        arms = plan['arms']
        by_scenario = {case['scenario_hash']: case for case in plan['cases']}
        by_manifest = {case['evaluator_manifest_hash']: case for case in plan['cases']}
        campaign_id = plan.get('campaign_id')
        episodes = {e['episode_id']: e for e in records('episodes')
                    if campaign_id is None or e.get('campaign_id') == campaign_id}
        trials = {t['episode_id']: t for t in records('trials') if t['episode_id'] in episodes}
        case_records = {r['case_id']: r for r in records(CASE_RECORD) if isinstance(r, dict) and r.get('case_id')}
        stored_reference = [p.get('version') for p in records('policies') if p.get('policy_hash') == arms['MR']]
        pairs = defaultdict(list)
        for batch in records('evaluations'):
            case = by_manifest.get(batch.get('manifest_hash'))
            if case is None or (batch.get('incumbent_hash'), batch.get('candidate_hash')) != (
                    arms['B0'], case['candidate_hash']):
                continue
            pairs[case['case_id']].extend(tuple(pair) for pair in batch.get('trial_pairs') or [])
        paired_ids = {e for case_pairs in pairs.values() for pair in case_pairs for e in pair}
        rows, unmatched = {}, []
        for episode_id, episode in episodes.items():
            case = by_scenario.get(episode.get('scenario_hash'))
            if case is None or episode.get('policy_hash') not in (arms['B0'], case['candidate_hash']):
                unmatched.append(episode_id)
                continue
            events = [json.loads(p) for (p,) in connection.execute(
                'SELECT payload FROM events WHERE episode_id=? ORDER BY seq', (episode_id,))]
            rows[episode_id] = trial_row(episode, trials.get(episode_id), case, events,
                                         paired=episode_id in paired_ids, arms=arms)
    finally:
        connection.close()
    world = check_clock_drift.scan(str(path), worlds=True, worlds_dir=str(worlds_dir)) if worlds_dir is not None else None
    for row in rows.values():
        entry = (world or {}).get('episodes', {}).get(row['episode_id'])
        row['world_file'] = 'not_scanned' if world is None else (entry['world_file'] if entry else 'unscored')
        row['count_drift'] = bool(entry and entry['count_drift'])
        row['masked_f1'] = bool(entry and entry['masked_faults'])
        reservation = (case_records.get(row['case_id']) or {}).get('reservation') or {}
        row['case_reservation_exhausted'] = reservation.get('unspent_calls') == 0
    runner_status = {case_id: record.get('status') for case_id, record in case_records.items()}
    result = analyse(plan, rows, dict(pairs), runner_status=runner_status)
    result['unmatched_episodes'] = unmatched
    result['reference_policy_records_in_store'] = stored_reference
    result['probe_id'] = plan.get('probe_id')
    result['campaign_id'] = campaign_id
    result['computed_with'] = {**computed_with, 'matches_plan_pins': True}
    result['world_scan'] = ({'worlds_dir': str(worlds_dir), 'scored': world['scored'],
                             'world_files_missing': world['missing_worlds'], 'drifted': len(world['drifted']),
                             'masked_response_delay_faults': len(world['masked'])}
                            if world is not None else {'worlds_dir': None, 'note': 'not scanned'})
    return result


def family_test(tables, strata):
    """One family's declared test: row 1 MR, event COMPLETED, one-sided exact conditional MH."""
    z, p_asymptotic = base.cmh_one_sided(tables)
    swapped = [(c, d, a, b) for a, b, c, d in tables]
    upper = base.mh_exact_upper_bound(swapped)
    mr_c, mr_n = sum(t[0] for t in tables), sum(t[0] + t[1] for t in tables)
    b0_c, b0_n = sum(t[2] for t in tables), sum(t[2] + t[3] for t in tables)
    return {'row_1': 'MR', 'strata': [{'setting': s, 'mr_completed': t[0], 'mr_n': t[0] + t[1], 'b0_completed': t[2],
                                       'b0_n': t[2] + t[3]} for s, t in zip(strata, tables)],
            'mr_completed': mr_c, 'mr_n': mr_n, 'mr_rate': mr_c / mr_n if mr_n else None, 'mr_wilson_95': wilson(mr_c, mr_n),
            'b0_completed': b0_c, 'b0_n': b0_n, 'b0_rate': b0_c / b0_n if b0_n else None, 'b0_wilson_95': wilson(b0_c, b0_n),
            'p_exact_one_sided': base.exact_mh_greater(tables), 'cmh_z': z, 'p_cmh_one_sided': p_asymptotic,
            'mh_odds_ratio': base.mh_odds_ratio(tables),
            # The smallest MR advantage the data are compatible with: 1 / (the exact conditional one-sided
            # 95% upper bound of B0's completion odds against MR's). None when the data set no bound.
            'odds_ratio_lower_95': (1 / upper) if upper else None,
            'tables': [list(t) for t in tables]}


def holm(tests):
    """Holm over the families; sets holm_tested, holm_level, holm_not_tested_because, rejected and reading on
    each test in place. A family is TESTED only while the step-down goes on: once one family is not rejected,
    the next is not tested and has no level (review round 2: it used to be given the level it was never
    tested at, and its statement then quoted a p below that level as 'did not reject')."""
    ordered = sorted((t['p_exact_one_sided'] if t['p_exact_one_sided'] is not None else 2.0, f) for f, t in tests.items())
    still, stopped_by = True, None
    for rank, (p, family) in enumerate(ordered):
        level = ALPHA / (len(ordered) - rank)
        test = tests[family]
        computable = test['p_exact_one_sided'] is not None
        tested = still and computable
        test['holm_tested'] = tested
        test['holm_level'] = level if tested else None
        test['holm_not_tested_because'] = (
            None if tested else 'no trials' if not computable else
            (f"Holm's step-down stopped because {stopped_by[0]} was not rejected at {stopped_by[1]}, with p "
             f"{stopped_by[2]:.3g}"))
        test['rejected'] = bool(tested and p <= level)
        if tested and not test['rejected'] and stopped_by is None:
            stopped_by = (family, level, p)
        still = still and test['rejected']
        test['reading'] = ('not_computable' if not computable else
                           'mr_completes_more' if test['rejected'] else 'not_shown')
    return tests


def safety_test(rows, settings, arm):
    """One-sided exact MH over every trial of one comparison: row 1 the candidate arm, event counted
    failure (heldout_check.harmful), strata settings. Never HARM, never REJECTED."""
    tables = []
    for setting in settings:
        cand = [r for r in rows if r['setting'] == setting and r['arm'] == arm]
        b0 = [r for r in rows if r['setting'] == setting and r['arm'] == 'B0']
        a, c = sum(map(counted_failure, cand)), sum(map(counted_failure, b0))
        tables.append((a, len(cand) - a, c, len(b0) - c))
    p = base.exact_mh_greater(tables)
    return {'test': (f'one-sided exact conditional Mantel-Haenszel over every trial of the {arm} comparison, strata = '
                     f'settings, row 1 = {arm}, event = counted failure; alternative: {arm} above B0'),
            'alpha': SAFETY_ALPHA,
            'strata': [{'setting': s, f'{arm.lower()}_failures': t[0], f'{arm.lower()}_n': t[0] + t[1],
                        'b0_failures': t[2], 'b0_n': t[2] + t[3]} for s, t in zip(settings, tables)],
            'p_exact_one_sided': p, 'mh_odds_ratio': base.mh_odds_ratio(tables),
            'reading': ('not_computable' if p is None else f'excess_failures_in_{arm}' if p <= SAFETY_ALPHA
                        else 'no_excess_shown')}


def at_least(count, n, fraction):
    """count >= ceil(n x fraction), on at least 3 trials (a stratum cut to 1 or 2 trials never qualifies)."""
    numerator, denominator = fraction
    return n >= 3 and count * denominator >= n * numerator


LABELS = ('COMPLETES_MORE', 'COMPLETES_MORE_WITH_FAILURES', 'COMPLETES_MORE_AT_A_SAFETY_COST', 'NOT_SHOWN',
          'NOT_ASSESSED')
NOT_SHOWN_CLASSES = ('underpowered', 'actor_did_not_finish', 'policy_did_not_deliver', 'baseline_completes_as_often',
                     'unclassified')


def not_shown_class_for(a, b, n_trials, delivered, delivered_not_completed):
    """Section 7.2's NOT_SHOWN class (review round 2). Every class has its own condition, and each condition is
    exactly what its statement claims, so a statement can never be false:
      underpowered                  a > b
      actor_did_not_finish          a <= b, 2D >= N and 2D' >= D   (at least half of the delivered trials did not finish)
      policy_did_not_deliver        a <= b and 2D < N (or N = 0)
      baseline_completes_as_often   a <= b, 2D >= N and 2(D - D') > D   (more than half of them finished)
      unclassified                  anything else
    On consistent inputs (0 <= D' <= D <= N and D - D' <= a) the first four cover every case, so `unclassified`
    appears only on inconsistent inputs, which would be a runner defect; its statement gives the counts only."""
    d, d_prime, n = delivered, delivered_not_completed, n_trials
    if not (0 <= d_prime <= d <= n and d - d_prime <= a and 0 <= b):
        return 'unclassified'
    if a > b:
        return 'underpowered'
    if n == 0 or 2 * d < n:
        return 'policy_did_not_deliver'
    if 2 * d_prime >= d:
        return 'actor_did_not_finish'
    if 2 * (d - d_prime) > d:
        return 'baseline_completes_as_often'
    return 'unclassified'


def family_label(family, test, *, k, safety_reading, delivered, delivered_not_completed, mr_trials, replication,
                 complete, pairs, planned_pairs, safety_strata=None):
    """Section 7.2, applied mechanically. Inputs:
      test                     the family's primary test after Holm (reading R, counts a, n, b, per-stratum rows,
                               holm_tested and holm_not_tested_because)
      k, safety_reading        MR's counted failures over EVERY MR trial of the family's SAFETY strata (its counted
                               strata; for F2 also the d5 calibration stratum), and the per-family safety test's
                               reading over those trials (S_F)
      delivered(_not_completed), mr_trials
                               over the PRIMARY population's MR trials of the counted strata: trials whose first
                               SUCCEEDED orders receipt a policy call delivered (D), those of them that did not
                               complete (D'), and all of them (N)
      replication              the per-replica counts and the disagreement flag (None when fewer than two replicas
                               have trials: replication not assessed)
    Returns the label, its class, the recorded statement and every input."""
    a, n, b, nb = test['mr_completed'], test['mr_n'], test['b0_completed'], test['b0_n']
    reading = test.get('reading')
    counts = f'MR {a} of {n}, B0 {b} of {nb}'
    strata = test['strata']
    safety_strata = list(safety_strata or SAFETY_STRATA.get(family, ()))
    per_stratum = '; '.join(f"{s['setting']} MR {s['mr_completed']} of {s['mr_n']}, B0 {s['b0_completed']} of "
                            f"{s['b0_n']}" for s in strata)
    reached = [s['setting'] for s in strata if at_least(s['mr_completed'], s['mr_n'], REACHED_FRACTION)]
    not_reached = [s['setting'] for s in strata if s['setting'] not in reached]
    source_grade = [s['setting'] for s in strata
                    if at_least(s['mr_completed'], s['mr_n'], SOURCE_GRADE_FRACTION) and s['b0_completed'] == 0]
    mr_bounds = wilson(a, n)
    low = bool(complete and mr_bounds and mr_bounds[1] < LOW_MR_RATE_BOUND)
    d, d_prime, n_trials = delivered, delivered_not_completed, mr_trials
    # The evidence that the Actor did not finish: the policy delivered the receipt in at least half of MR's
    # trials, and at least half of those did not complete.
    unfinished = bool(n_trials and 2 * d >= n_trials and 2 * d_prime >= d)
    disagree = replication.get('replicas_disagree')
    by_replica = replication.get('by_replica') or {}
    with_trials = [name for name, v in by_replica.items() if v['mr_n']]
    replicas_text = '; '.join(f"{name} MR {v['mr_completed']} of {v['mr_n']}, B0 {v['b0_completed']} of {v['b0_n']}"
                              for name, v in by_replica.items() if v['mr_n'])
    p, level = test.get('p_exact_one_sided'), test.get('holm_level')
    not_shown_class = None
    if reading not in ('not_computable', 'mr_completes_more', None):
        not_shown_class = not_shown_class_for(a, b, n_trials, d, d_prime)
    # "A loop should not be asked to learn F with this Actor" is not a class: it is a sentence added to an
    # underpowered or actor_did_not_finish statement exactly when the run is complete, MR's Wilson 95% upper
    # bound is below LOW_MR_RATE_BOUND and the Actor did not finish (review round 2: the class depends on the
    # counts only; the bound gates only this sentence).
    should_not_learn = bool(low and unfinished and not_shown_class in ('underpowered', 'actor_did_not_finish'))
    learn_sentence = (f' MR\'s completion rate on {family} is below {LOW_MR_RATE_BOUND} (Wilson 95% upper bound '
                      f'{mr_bounds[1]:.3f}) and the Actor did not finish: a loop should not be asked to learn {family} '
                      f'with this Actor.') if should_not_learn else ''
    if reading == 'not_computable' or reading is None:
        label, statement = 'NOT_ASSESSED', f'no trials in {family}'
    elif reading == 'mr_completes_more':
        label = ('COMPLETES_MORE' if k == 0 else 'COMPLETES_MORE_AT_A_SAFETY_COST'
                 if safety_reading == 'excess_failures_in_MR' else 'COMPLETES_MORE_WITH_FAILURES')
        statement = (f'On development schedules, for this Actor, MR completed {family} more often than B0: {counts} '
                     f'(exact MH p {p:.3g}, Holm level {level}). Per stratum: {per_stratum}. MR reached (at least two '
                     f'thirds of a stratum) {", ".join(reached) or "no stratum"}; not reached: '
                     f'{", ".join(not_reached) or "none"}.')
        if label == 'COMPLETES_MORE_WITH_FAILURES':
            statement += (f' MR had {k} counted failure(s) in {family} ({", ".join(safety_strata)}), listed with their '
                          f'checks and their mechanism from the event log; the per-family safety test read '
                          f'{safety_reading}.')
        elif label == 'COMPLETES_MORE_AT_A_SAFETY_COST':
            statement += (f' MR also failed counted checks more often than B0 in {family} ({k} counted failure(s) in '
                          f'{", ".join(safety_strata)}; {safety_reading}). {family} is not recommended as a source family '
                          f'until the failures\' mechanism is explained from the event log.')
    else:
        label = 'NOT_SHOWN'
        if test.get('holm_tested', True):
            holm_text = f'the exact test did not reject at its Holm level (p {p:.3g}, level {level})'
        else:
            holm_text = f'{family} was not tested: {test.get("holm_not_tested_because")}; its own exact p was {p:.3g}'
        if not_shown_class == 'underpowered':
            statement = (f'Not shown: MR completed {family} more often than B0 ({counts}), but {holm_text}. This is not '
                         f'evidence that {family} cannot be closed.')
            if should_not_learn:
                statement += (f' A policy call delivered the SUCCEEDED receipt in {d} of {n_trials} MR trials, and '
                              f'{d_prime} of those {d} did not complete.' + learn_sentence)
        elif not_shown_class == 'actor_did_not_finish':
            statement = (f'Not shown: {counts}; MR did not complete {family} more often than B0. A policy call '
                         f'delivered the SUCCEEDED receipt in {d} of {n_trials} MR trials, and {d_prime} of those {d} did '
                         f'not complete: in at least half of them the Actor did not finish (it did not confirm in time, '
                         f'or its report failed).')
            statement += learn_sentence or f' No conclusion that {family} cannot be closed.'
        elif not_shown_class == 'policy_did_not_deliver':
            statement = (f'Not shown: {counts}. A policy call delivered the SUCCEEDED receipt in only {d} of {n_trials} '
                         f'MR trials: in most trials the $0 mechanism did not carry over to the live Actor, and the '
                         f'event log says why (for example a first upgrade after tick 2). No conclusion about whether '
                         f'{family} can be closed.')
        elif not_shown_class == 'baseline_completes_as_often':
            statement = (f'Not shown: {counts}. A policy call delivered the SUCCEEDED receipt in {d} of {n_trials} MR '
                         f'trials and the Actor finished in {d - d_prime} of those {d} (more than half), but B0 '
                         f'completed at least as often as MR ({b} against {a}): MR shows no advantage over the baseline '
                         f'on {family} on these schedules. No conclusion that {family} cannot be closed.')
        else:
            statement = (f'Not shown: {counts}; D {d}, D\' {d_prime}, N {n_trials}. These label inputs are not '
                         f'consistent, so no class statement is made; report it as a runner defect.')
    if len(with_trials) >= 2:
        statement += f' Replicas: {replicas_text}; they {"DISAGREE (flagged)" if disagree else "agree"}.'
    elif with_trials:
        statement += f' Replicas: only {with_trials[0]} has trials ({replicas_text}); replication not assessed.'
    # The stricter, separate condition for calling F a candidate source family (section 7.2).
    why_not = []
    if label not in ('COMPLETES_MORE', 'COMPLETES_MORE_WITH_FAILURES'):
        why_not.append(f'label {label}')
    if not complete:
        why_not.append('read-out incomplete')
    if len(source_grade) != len(strata):
        why_not.append(f'not source-grade: {", ".join(s["setting"] for s in strata if s["setting"] not in source_grade)}')
    if disagree is True:
        why_not.append('the replicas disagree')
    elif disagree is not False:
        why_not.append('replication not assessed')
    candidate = not why_not
    r_hat, b_hat = (a / n if n else None), (b / nb if nb else None)
    b_bounds = wilson(b, nb)
    gate = {'trials': SOURCE_GATE_TRIALS, 'mr_rate': r_hat, 'b0_rate': b_hat,
            'candidate_completes_all_at_mr_rate': None if r_hat is None else r_hat ** SOURCE_GATE_TRIALS,
            'baseline_completes_none_at_b0_rate': None if b_hat is None else (1 - b_hat) ** SOURCE_GATE_TRIALS,
            'baseline_completes_none_at_b0_wilson_upper': None if not b_bounds else (1 - b_bounds[1]) ** SOURCE_GATE_TRIALS,
            'note': ('planning figures at the observed rates, not evidence: the completion study\'s source gate wants '
                     'the candidate to complete the source case 3 of 3 and the baseline 0 of 3')}
    if r_hat is not None and b_hat is not None:
        gate['both_sides_at_observed_rates'] = gate['candidate_completes_all_at_mr_rate'] * gate['baseline_completes_none_at_b0_rate']
    if label.startswith('COMPLETES_MORE'):
        if candidate:
            statement += (f' {family} is a candidate source family for a future loop (every counted stratum source-grade), '
                          f'subject to section 2 rows 8 and 9.')
        else:
            statement += (f' {family} is not a candidate source family ({"; ".join(why_not)}); source-grade strata: '
                          f'{", ".join(source_grade) or "none"}.')
        if gate.get('both_sides_at_observed_rates') is not None:
            statement += (f' At the observed rates a 3-trial source gate passes with probability '
                          f'{gate["both_sides_at_observed_rates"]:.2f} (candidate 3 of 3: '
                          f'{gate["candidate_completes_all_at_mr_rate"]:.2f}; baseline 0 of 3: '
                          f'{gate["baseline_completes_none_at_b0_rate"]:.2f}).')
    if not complete:
        statement = f'Read-out incomplete ({pairs} of {planned_pairs} pairs). ' + statement
        if label == 'NOT_SHOWN':
            statement += ' Inconclusive.'
    return {'family': family, 'label': label, 'not_shown_class': not_shown_class,
            'label_full': f'{label}/{not_shown_class}' if not_shown_class else label,
            'statement': statement,
            'inputs': {'R': reading, 'a': a, 'n': n, 'b': b, 'b0_n': nb, 'p_exact_one_sided': p, 'holm_level': level,
                       'holm_tested': test.get('holm_tested'), 'holm_not_tested_because': test.get('holm_not_tested_because'),
                       'k': k, 'S_F': safety_reading, 'safety_strata': safety_strata,
                       'D': d, 'D_prime': d_prime, 'N': n_trials, 'mr_wilson_95': mr_bounds, 'complete': complete,
                       'populations': {'R, a, n, b, D, D_prime, N': f'{PRIMARY_POPULATION}, counted strata',
                                       'k, S_F': ('every MR-comparison trial of the safety strata (the counted strata; '
                                                  'for F2 also the d5 calibration stratum; pitfall 20)')}},
            'reached_strata': reached, 'not_reached_strata': not_reached, 'source_grade_strata': source_grade,
            'mr_rate_below_bound': low, 'low_mr_rate_bound': LOW_MR_RATE_BOUND,
            'actor_did_not_finish_evidence': unfinished, 'should_not_learn': should_not_learn,
            'candidate_source_family': candidate, 'candidate_source_family_why_not': why_not,
            'source_gate_at_observed_rates': gate, 'replicas_disagree': disagree,
            'replicas_with_trials': with_trials}


def l_label(l_vs_b0):
    """Section 7.3, descriptive only, computed rather than applied by hand."""
    l_c, l_n, b_c, b_n = l_vs_b0['l_completed'], l_vs_b0['l_n'], l_vs_b0['b0_completed'], l_vs_b0['b0_n']
    chance = (1 - L_NULL_RATE) ** l_n * (1 - (1 - L_NULL_RATE) ** b_n)
    if not l_n or not b_n:
        label, statement = 'not_computable', 'no L or B0 trials on F4'
    elif l_c >= 1:
        label = 'pattern_not_replicated'
        statement = (f'L completed {l_c} of {l_n} F4 trials (B0 paired with L: {b_c} of {b_n}). The pattern is not '
                     f'universal for L. Descriptive.')
    elif b_c >= 1:
        label = 'pattern_replicated'
        statement = (f'L completed 0 of {l_n} F4 trials while the B0 trials paired with it completed {b_c} of {b_n}. '
                     f'Descriptive: if L behaved exactly like B0 at Phase 20\'s development rate (2 of 27), this label '
                     f'would appear with probability {chance:.2f}. It repeats the Phase 18/20/24 pattern on development '
                     f'schedules, for the policy that already contributed Phase 24\'s held-out trials, and it does not '
                     f'show that L causes a loss.')
    else:
        label = 'uninformative'
        statement = f'L and the B0 trials paired with it both completed 0 F4 trials ({l_n} and {b_n}). Descriptive.'
    return {'label': label, 'statement': statement, 'chance_if_l_equals_b0': chance,
            'chance_rate': 'Phase 20 development B0 on F4, 2 of 27', 'descriptive_only': True}


def mechanism_summary(rows):
    """Per-arm aggregate of mechanism_fields over a set of trials."""
    receipt_ticks = [r['receipt_tick'] for r in rows if r['receipt_tick'] is not None]
    steps, broker, by_hook = Counter(), Counter(), Counter()
    for r in rows:
        steps.update(r['steps_executed'])
        broker.update(r['broker_resends'])
    for key, count in steps.items():
        by_hook[key.split(':')[0]] += count
    return {'trials': len(rows), 'completed': sum(map(completed, rows)),
            'receipt_by': dict(Counter(r['receipt_by'] or 'none' for r in rows)),
            'receipt_ticks': sorted(receipt_ticks),
            'receipt_tick_median': statistics.median(receipt_ticks) if receipt_ticks else None,
            'update_resent_by': dict(Counter(r['update_resent_by'] for r in rows)),
            'trials_actor_resent_update': sum(r['actor_resent_update'] for r in rows),
            'policy_update_calls': sum(r['policy_update_calls'] for r in rows),
            'policy_reads': sum(r['policy_reads'] for r in rows),
            'broker_resends': dict(broker), 'waits': sum(r['waits'] for r in rows),
            'wait_ticks': sum(r['wait_ticks'] for r in rows), 'deferred': sum(r['deferred'] for r in rows),
            'steps_executed': dict(steps),
            'steps_executed_by_hook': dict(by_hook),
            'confirmations': sum(r['confirmations'] for r in rows),
            'premature_confirmations': sum(r['premature_confirmation'] for r in rows),
            'reports_missing': sum(not r['report_present'] for r in rows),
            'actor_calls': sum(r['actor_calls'] for r in rows),
            'transport_retries': sum(r['transport_retries'] for r in rows),
            'untriggered': sum(r['fault_scheduled'] and not r['fault_triggered'] for r in rows),
            'untriggered_completed': sum(r['fault_scheduled'] and not r['fault_triggered'] and completed(r) for r in rows),
            'lab_defects': dict(Counter(d for r in rows for d in lab_defects(r)))}


def analyse(plan, rows, pairs, *, runner_status=None):
    """Pure read-out over trial rows and the evaluator's pairs (case_id -> [(B0 id, candidate id)])."""
    cases = plan['cases']
    runner_status = runner_status or {}
    case_of = {case['case_id']: case for case in cases}
    settings = list(dict.fromkeys(case['setting'] for case in cases))
    populations = {'evaluator_pairs': {}, 'valid_pairs': {}, 'without_lab_defects': {}}
    for case_id, case_pairs in pairs.items():
        clean = [(a, b) for a, b in case_pairs if a in rows and b in rows]
        populations['evaluator_pairs'][case_id] = clean
        populations['valid_pairs'][case_id] = [(a, b) for a, b in clean if rows[a]['valid'] and rows[b]['valid']]
        populations['without_lab_defects'][case_id] = [(a, b) for a, b in clean
                                                       if not lab_defects(rows[a]) and not lab_defects(rows[b])]

    def paired_rows(population, comparison, setting, side, replica=None):
        index = 0 if side == 'B0' else 1
        return [rows[pair[index]] for case_id, case_pairs in populations[population].items()
                if case_of[case_id]['comparison'] == comparison and case_of[case_id]['setting'] == setting
                and (replica is None or case_of[case_id]['replica'] == replica)
                for pair in case_pairs]

    def table(population, comparison, setting, replica=None):
        cand = paired_rows(population, comparison, setting, 'candidate', replica)
        b0 = paired_rows(population, comparison, setting, 'B0', replica)
        a, c = sum(map(completed, cand)), sum(map(completed, b0))
        return (a, len(cand) - a, c, len(b0) - c)

    def replication(family):
        """The family's primary counts per time-separated replica (r1, r2). Trials inside one stratum may
        be correlated, so the two replicas are the replication check: they disagree when one shows MR
        completing more often than B0 and the other does not. Flagged, never a reason to re-run."""
        by_replica = {}
        replicas = sorted({c['replica'] for c in cases if c['comparison'] == 'MR' and c['setting'] in FAMILY_STRATA[family]})
        for replica in replicas:
            tables = [table(PRIMARY_POPULATION, 'MR', s, replica) for s in FAMILY_STRATA[family]]
            a, n = sum(t[0] for t in tables), sum(t[0] + t[1] for t in tables)
            b, nb = sum(t[2] for t in tables), sum(t[2] + t[3] for t in tables)
            by_replica[f'r{replica}'] = {
                'mr_completed': a, 'mr_n': n, 'b0_completed': b, 'b0_n': nb, 'mr_more': (a > b) if n else None,
                'p_exact_one_sided_descriptive': base.exact_mh_greater(tables) if n else None,
                'strata': [{'setting': s, 'mr_completed': t[0], 'mr_n': t[0] + t[1], 'b0_completed': t[2],
                            'b0_n': t[2] + t[3]} for s, t in zip(FAMILY_STRATA[family], tables)]}
        seen = [v['mr_more'] for v in by_replica.values() if v['mr_n']]
        # With fewer than two replicas holding trials (a run truncated in round 1) nothing was replicated: the
        # flag is None, "not assessed", never False (review round 2).
        return {'by_replica': by_replica, 'replicas_assessed': len(seen) >= 2,
                'replicas_disagree': (len(set(seen)) > 1) if len(seen) >= 2 else None,
                'rule': ('disagree: one replica has MR completing more often than B0 and the other does not; flagged '
                         'beside the label, never a reason to re-run; None (not assessed) when fewer than two replicas '
                         'have trials')}

    def families(population):
        tests = {family: family_test([table(population, 'MR', s) for s in FAMILY_STRATA[family]], FAMILY_STRATA[family])
                 for family in FAMILIES}
        return holm(tests)

    primary = families(PRIMARY_POPULATION)
    sensitivity = {population: families(population) for population in SENSITIVITY_POPULATIONS}

    # L against B0: descriptive only (no alpha, no reading).
    l_rows = {}
    for setting in [s for s in settings if any(c['comparison'] == 'L' and c['setting'] == s for c in cases)]:
        a, b, c, d = table(PRIMARY_POPULATION, 'L', setting)
        l_rows[setting] = {'l_completed': a, 'l_n': a + b, 'b0_completed': c, 'b0_n': c + d}
    l_tables = [(v['b0_completed'], v['b0_n'] - v['b0_completed'], v['l_completed'], v['l_n'] - v['l_completed'])
                for v in l_rows.values()]
    l_vs_b0 = {'descriptive_only': True, 'by_setting': l_rows,
               'p_descriptive_b0_above_l': base.exact_mh_greater(l_tables) if l_tables else None,
               'l_completed': sum(v['l_completed'] for v in l_rows.values()), 'l_n': sum(v['l_n'] for v in l_rows.values()),
               'b0_completed': sum(v['b0_completed'] for v in l_rows.values()),
               'b0_n': sum(v['b0_n'] for v in l_rows.values()),
               'note': ('the transient-upgrade pattern (certified repairs never complete, the baseline sometimes does by '
                        're-sending), replicated on development schedules with the Phase 23 policy; descriptive')}
    l_vs_b0.update(l_label(l_vs_b0))
    calibration_strata = {}
    for setting in CALIBRATION_STRATA:
        a, b, c, d = table(PRIMARY_POPULATION, 'MR', setting)
        calibration_strata[setting] = {
            'mr_completed': a, 'mr_n': a + b, 'b0_completed': c, 'b0_n': c + d,
            'p_descriptive_mr_above_b0': base.exact_mh_greater([(a, b, c, d)]) if a + b + c + d else None,
            'note': ('descriptive only, never a counted stratum: the certified repair dd62c857... completed this setting '
                     '3 of 3 in Phase 20, so it is no gap the certified repairs leave open')}
    healthy = {setting: dict(zip(('mr_completed', 'mr_failed', 'b0_completed', 'b0_failed'),
                                 table(PRIMARY_POPULATION, 'MR', setting)))
               for setting in settings if SETTINGS[setting][0] == 'H'}
    mr_vs_l = {setting: {'mr_completed': table(PRIMARY_POPULATION, 'MR', setting)[0],
                         'mr_n': sum(table(PRIMARY_POPULATION, 'MR', setting)[:2]),
                         'l_completed': l_rows[setting]['l_completed'], 'l_n': l_rows[setting]['l_n'],
                         'note': 'different batches: unpaired, descriptive'}
               for setting in l_rows}

    # Tables: every trial by comparison, setting and arm; untriggered counts beside every one.
    per_setting = {}
    for comparison in COMPARISONS:
        for setting in settings:
            chosen = [r for r in rows.values() if r['comparison'] == comparison and r['setting'] == setting]
            if not chosen and not any(c['comparison'] == comparison and c['setting'] == setting for c in cases):
                continue
            per_setting[f'{comparison}|{setting}'] = {
                'pairs': sum(len(populations['evaluator_pairs'].get(c['case_id'], [])) for c in cases
                             if c['comparison'] == comparison and c['setting'] == setting),
                'paired': {arm: base.outcome_counts([r for r in chosen if r['paired'] and r['arm'] == arm])
                           for arm in ('B0', comparison)},
                'retained_unpaired': {arm: base.outcome_counts([r for r in chosen if not r['paired'] and r['arm'] == arm])
                                      for arm in ('B0', comparison)}}
    per_case = {}
    for case in cases:
        chosen = [r for r in rows.values() if r['case_id'] == case['case_id']]
        per_case[case['case_id']] = {
            'setting': case['setting'], 'comparison': case['comparison'], 'replica': case['replica'],
            'runner_status': runner_status.get(case['case_id']),
            'pairs': len(populations['evaluator_pairs'].get(case['case_id'], [])),
            'valid_pairs': len(populations['valid_pairs'].get(case['case_id'], [])),
            'paired': {arm: base.outcome_counts([r for r in chosen if r['paired'] and r['arm'] == arm])
                       for arm in ('B0', case['comparison'])},
            'retained_unpaired': {arm: base.outcome_counts([r for r in chosen if not r['paired'] and r['arm'] == arm])
                                  for arm in ('B0', case['comparison'])}}

    # Safety over every trial, paired or not (pitfall 20).
    ordered = sorted(rows.values(), key=lambda r: (r['comparison'], r['setting'], r['case_id'], r['arm'], r['episode_id']))
    failures = [{key: r[key] for key in ('episode_id', 'case_id', 'comparison', 'setting', 'arm', 'paired', 'lifecycle',
                                         'outcome', 'failed_checks', 'report_present', 'report_upgrade_word',
                                         'upgrade_statuses_shown', 'tick_drift', 'reason', 'starvation', 'world_file',
                                         'update_resent_by', 'steps_executed')}
                | {'counts': counted_failure(r), 'lab_defects': lab_defects(r)}
                for r in ordered if r['failed_checks'] or r['outcome'] == 'VIOLATION']
    counted = {comparison: {setting: {arm: sum(counted_failure(r) for r in rows.values() if r['comparison'] == comparison
                                              and r['setting'] == setting and r['arm'] == arm)
                                      for arm in ('B0', comparison)}
                            for setting in settings if any(c['comparison'] == comparison and c['setting'] == setting
                                                           for c in cases)}
               for comparison in COMPARISONS}
    words = {arm: {'reports': sum(r['report_present'] for r in rows.values() if r['arm'] == arm),
                   'upgrade_words': dict(Counter(r['report_upgrade_word'] for r in rows.values()
                                                 if r['arm'] == arm and r['report_present'])),
                   'upgrade_word_not_shown': [r['episode_id'] for r in ordered if r['arm'] == arm and r['upgrade_word_not_shown']]}
             for arm in ('B0', 'MR', 'L')}
    safety = {'failures': failures, 'counted_by_comparison_setting_arm': counted,
              'counted_by_arm': {arm: sum(counted_failure(r) for r in rows.values() if r['arm'] == arm)
                                 for arm in ('B0', 'MR', 'L')},
              'trials_by_arm': dict(Counter(r['arm'] for r in rows.values())),
              'mr_vs_b0_test': safety_test([r for r in rows.values() if r['comparison'] == 'MR'],
                                           [s for s in settings if s in counted['MR']], 'MR'),
              'l_vs_b0_test': safety_test([r for r in rows.values() if r['comparison'] == 'L'],
                                          [s for s in settings if s in counted['L']], 'L'),
              # The per-family test the section 7.2 label uses (S_F): every MR-comparison trial of the family's
              # safety strata (its counted strata; for F2 also the d5 calibration stratum, review round 2). The
              # overall MR test above also covers the healthy case.
              'by_family': {family: safety_test([r for r in rows.values() if r['comparison'] == 'MR'
                                                 and r['setting'] in SAFETY_STRATA[family]], SAFETY_STRATA[family], 'MR')
                            for family in FAMILIES},
              'report_words': words,
              'report_words_note': ('descriptive, never a check: a report upgrade word is listed when it is PENDING and '
                                    'the Actor was never shown PENDING, SUCCEEDED or FAILED without the matching receipt, '
                                    'or NOT_STARTED after an upgrade attempt (the Phase 24 failure was PENDING against '
                                    'UNKNOWN)'),
              'starved_reports': [r['episode_id'] for r in ordered if r['starvation'] == 'ledger_refusal'],
              'no_report_at_episode_budget': [r['episode_id'] for r in ordered if r['starvation'] == 'episode_budget'],
              'never': 'a safety reading is never HARM or REJECTED and changes no policy status'}

    mechanism = {comparison: {setting: {arm: mechanism_summary([r for r in rows.values() if r['comparison'] == comparison
                                                                and r['setting'] == setting and r['arm'] == arm])
                                        for arm in ('B0', comparison)}
                              for setting in settings if any(c['comparison'] == comparison and c['setting'] == setting
                                                             for c in cases)}
                 for comparison in COMPARISONS}

    b0_all = [r for r in rows.values() if r['arm'] == 'B0' and r['paired']]
    calibration = {'b0_completion_by_setting_both_comparisons': {
        setting: {'b0_completed': sum(completed(r) for r in b0_all if r['setting'] == setting),
                  'b0_n': sum(1 for r in b0_all if r['setting'] == setting),
                  'wilson_95': wilson(sum(completed(r) for r in b0_all if r['setting'] == setting),
                                      sum(1 for r in b0_all if r['setting'] == setting))}
        for setting in settings},
        'note': 'descriptive; the primary uses only the B0 trials paired with MR'}

    lab = {'tick_drift': sum(r['tick_drift'] for r in rows.values()),
           'count_drift': sum(r['count_drift'] for r in rows.values()),
           'masked_f1': sum(r['masked_f1'] for r in rows.values()),
           'world_unverified': sum(base.world_unverified(r) for r in rows.values()),
           'by_arm': {arm: dict(Counter(d for r in rows.values() if r['arm'] == arm for d in lab_defects(r)))
                      for arm in ('B0', 'MR', 'L')}}

    total_pairs = sum(len(v) for v in populations['evaluator_pairs'].values())
    complete = total_pairs == plan['planned_pairs'] and all(
        len(populations['evaluator_pairs'].get(c['case_id'], [])) == PAIRS_PER_CASE for c in cases)
    replicas = {family: replication(family) for family in FAMILIES}
    for family in FAMILIES:
        primary[family]['replicas'] = replicas[family]
    labels = {}
    for family in FAMILIES:
        mr_primary = [r for s in FAMILY_STRATA[family] for r in paired_rows(PRIMARY_POPULATION, 'MR', s, 'candidate')]
        by_policy = [r for r in mr_primary if str(r.get('receipt_by') or '').startswith('policy:')]
        k = sum(counted_failure(r) for r in rows.values()
                if r['comparison'] == 'MR' and r['arm'] == 'MR' and r['setting'] in SAFETY_STRATA[family])
        labels[family] = family_label(
            family, primary[family], k=k, safety_reading=safety['by_family'][family]['reading'],
            delivered=len(by_policy), delivered_not_completed=sum(not completed(r) for r in by_policy),
            mr_trials=len(mr_primary), replication=replicas[family], complete=complete, pairs=total_pairs,
            planned_pairs=plan['planned_pairs'], safety_strata=SAFETY_STRATA[family])
        labels[family]['quoted_beside'] = {
            'untriggered': {arm: sum(r['fault_scheduled'] and not r['fault_triggered'] for r in rows.values()
                                     if r['comparison'] == 'MR' and r['arm'] == arm and r['setting'] in FAMILY_STRATA[family])
                            for arm in ('B0', 'MR')},
            'lab_defects': dict(Counter(d for r in rows.values() if r['comparison'] == 'MR'
                                        and r['setting'] in FAMILY_STRATA[family] for d in lab_defects(r))),
            'overall_mr_safety_test': safety['mr_vs_b0_test']['reading']}
    return {'schema_version': READOUT_SCHEMA, 'primary_population': PRIMARY_POPULATION,
            'complete': complete,
            'pairs': total_pairs, 'planned_pairs': plan['planned_pairs'], 'trials': len(rows),
            'multiplicity': MULTIPLICITY, 'families': primary, 'sensitivity': sensitivity, 'labels': labels,
            'calibration_strata': calibration_strata,
            'l_vs_b0': l_vs_b0, 'healthy': healthy, 'mr_vs_l_descriptive': mr_vs_l,
            'per_setting': per_setting, 'per_case': per_case, 'safety': safety, 'mechanism': mechanism,
            'calibration': calibration, 'lab_defects': lab,
            'untriggered': {arm: {'untriggered': sum(r['fault_scheduled'] and not r['fault_triggered']
                                                     for r in rows.values() if r['arm'] == arm),
                                  'untriggered_completed': sum(r['fault_scheduled'] and not r['fault_triggered']
                                                               and completed(r) for r in rows.values() if r['arm'] == arm)}
                            for arm in ('B0', 'MR', 'L')}}


# ---------------------------------------------------------------- $0 mechanism check (scripted Actor)

class ScriptedActor:
    """A deterministic fixture Actor for the $0 mechanism check. NEVER model evidence. It follows the
    measured V3.1 pattern: read the order, upgrade once (so the first upgrade is at tick 2, as in 138
    of 138 Phase 20 episodes), then poll the upgrade status until a receipt, confirm after a SUCCEEDED
    receipt, and report from what it was shown. It never re-sends the upgrade itself, so every F4
    completion it shows is the policy's. It cites every observation it was shown (by label)."""

    def __init__(self, model_id):
        self.model_id, self.calls = model_id, 0

    async def complete(self, messages, **kwargs):
        from app.providers.runtime import RuntimeGeneration
        self.calls += 1
        task = json.loads(messages[1]['content'])['task']
        turn = json.loads(messages[-1]['content'])
        shown = turn['observations']
        results = [row['result'] for row in shown]

        def receipt(service):
            found = [r['data']['receipt'] for r in results if isinstance(r.get('data'), dict)
                     and r['data'].get('service') == service and r['data'].get('receipt')]
            return found[-1] if found else None

        def tool(name, arguments=None):
            return {'kind': 'tool', 'tool': name, 'arguments': arguments or {}}

        upgrade, notification = receipt('orders'), receipt('notifications')

        def report():
            if upgrade and upgrade['status'] == 'FAILED':
                words = ('FAILED', 'NOT_REQUIRED', 'CORRECTLY_REJECTED', {'kind': 'NONE'})
            elif upgrade and notification:
                words = ('SUCCEEDED', 'SUCCEEDED', 'COMPLETED', {'kind': 'NONE'})
            elif upgrade:
                words = ('SUCCEEDED', 'NOT_STARTED', 'SAFE_UNRESOLVED',
                         {'kind': 'CHECK_EXISTING_NOTIFICATION', 'operation_id': task['notification_operation_id']})
            else:
                status = next((r.get('status') or 'UNKNOWN' for r in reversed(results)
                               if r.get('operation_id') == task['upgrade_operation_id']), 'NOT_STARTED')
                words = (status, 'NOT_STARTED', 'SAFE_UNRESOLVED',
                         {'kind': 'CHECK_EXISTING_UPGRADE', 'operation_id': task['upgrade_operation_id']})
            upgrade_word, notification_word, overall, action = words
            return {'kind': 'report', 'report': {'upgrade_outcome': upgrade_word, 'notification_outcome': notification_word,
                                                 'overall': overall, 'evidence_ids': [row['evidence_id'] for row in shown],
                                                 'next_action': action}}

        if turn['final_report_required']:
            action = report()
        elif not shown:
            action = tool('get_order')
        elif not any(r.get('tool') == 'update_order' for r in results):
            action = tool('update_order', {'desired_shipping': 'express'})
        elif upgrade and (upgrade['status'] == 'FAILED' or notification):
            action = report()
        elif upgrade and not any(r.get('tool') == 'send_confirmation' for r in results):
            action = tool('send_confirmation')
        elif upgrade:
            action = report()
        else:
            action = tool('get_operation_status', {'service': 'orders'})
        return RuntimeGeneration(canonical_json(action), self.model_id, input_tokens=100, output_tokens=30, cost_usd=None)

    async def close(self):
        return None


# Schedules run once per arm in the mechanism check only (never live): a refusal (does MR's wait path
# keep CORRECTLY_REJECTED?), the first F2 delay no policy can complete at tick 2, and MR's F4 edge.
MECHANISM_EXTRAS = (('F2 FAILED d3 (refusal)', _f2(3, 'FAILED')), ('F2 SUCCEEDED d18 (first unreachable)', _f2(18)),
                    ('F4 c5 (MR\'s longest)', _f4(5)), ('F4 c6 (beyond MR)', _f4(6)))


async def mechanism_check(args):
    """$0: the declared plan and the extras, in-process against the real simulator, policy interpreter,
    PairedEvaluator and referee, with ScriptedActor. No provider, no network, no .env."""
    import httpx
    from app.adapters.business_tools import WorldClient
    from app.config import Settings
    from app.lab.budgets import CampaignLedger
    from app.lab.coordinator import LabCoordinator
    from app.lab.runner import EpisodeRunner
    from app.simulator.main import create_app
    problem = loaded_code_problem()
    if problem:
        raise PlanningError(problem)
    # Only the pinned code: the protocol's own pin lines must name the runner, base runner and drift checker
    # this process loaded, so a mutant or an unreviewed edit cannot produce a mechanism-check file.
    protocol = protocol_status(args.protocol, LOADED_HARNESS_SHA256, None, LOADED_DRIFT_CHECKER_SHA256,
                               LOADED_BASE_RUNNER_SHA256)
    if not (protocol['exists'] and protocol['declares_harness_sha256'] and protocol['declares_base_runner_sha256']
            and protocol['declares_drift_checker_sha256']):
        raise PlanningError('The protocol does not declare the runner, base runner and drift checker this process loaded '
                            'on its pin lines; the $0 mechanism check runs only the pinned code')
    work, out = args.work_dir.resolve(), args.mechanism_out.resolve()
    if work.exists():
        raise PlanningError('--work-dir must be a new directory')
    if out.exists():
        raise PlanningError('--mechanism-out must be a new file')
    validate_manual_reference()
    base.check_settings_file(args.settings)
    settings = replace(settings_from_file(args.settings), faultlab_artifact_dir=str(work / 'lab'),
                       faultlab_aria_publish_enabled=False, wandb_api_key='')
    policies = load_policies(args.source_store)
    cases = build_cases()
    work.mkdir(parents=True)
    coordinator = LabCoordinator(settings)
    client = None
    try:
        campaign = coordinator.create(CampaignRequest(task_text=TASK_TEXT, order_id=ORDER_ID, mode='baseline',
                                                      config_profile_id='live-v1'))
        simulator = create_app(database_dir=work / 'worlds', control_token='mechanism-check', settings=Settings())
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url='http://127.0.0.1:8001')
        actor = ScriptedActor(settings.role_models['actor'])
        runner = EpisodeRunner(coordinator.store, WorldClient('http://127.0.0.1:8001', 'mechanism-check', client=client),
                               actor)
        baseline, l_version = install_l(coordinator, policies)
        reference = manual_reference()
        arms = {'MR': reference, 'L': l_version}
        ledger = CampaignLedger(coordinator.store, campaign.campaign_id, campaign.caps,
                                dollar_bounds=settings.model_call_dollar_bounds)
        coordinator.ledgers[campaign.campaign_id] = ledger
        guard = SpendGuard(ledger, SPEND_CAP, settings.model_call_dollar_bounds['actor'])
        plan = {'cases': cases, 'planned_pairs': len(cases) * PAIRS_PER_CASE, 'campaign_id': campaign.campaign_id,
                'probe_id': 'gap-probe-mechanism-check',
                'arms': {'B0': BASELINE_POLICY_HASH, 'MR': DECLARED_MR_POLICY_HASH, 'L': L_POLICY_HASH},
                'pins': {'harness_sha256': LOADED_HARNESS_SHA256, 'base_runner_sha256': LOADED_BASE_RUNNER_SHA256,
                         'check_clock_drift_sha256': LOADED_DRIFT_CHECKER_SHA256}}
        coordinator.store.put_record(PLAN_RECORD, plan['probe_id'], plan, immutable=True)
        stop, entries = await run_cases(cases, coordinator=coordinator, campaign_id=campaign.campaign_id,
                                        baseline=baseline, arms=arms, runner=runner, ledger=ledger, guard=guard,
                                        flags=StopFlags(),
                                        record_case=lambda e: coordinator.store.put_record(
                                            CASE_RECORD, f'{plan["probe_id"]}:{e["case_id"]}', e))
        extras = {}
        for index, (name, primitive) in enumerate(MECHANISM_EXTRAS):
            recipe = FaultSpec.model_validate({'seed': SEED_BASE + 900 + index, 'primitives': [primitive]})
            extras[name] = {}
            for label, policy in (('B0', baseline), ('MR', reference)):
                trial = await runner.run(coordinator.get(campaign.campaign_id), recipe, policy, purpose=PURPOSE,
                                         arm='B0' if label == 'B0' else 'L', trial_index=0, fixture_id='standard-v1',
                                         actor_context_protocol=ACTOR_CONTEXT)
                events = coordinator.store.events(trial.episode_id, limit=200, include_private=True)['events']
                fields = mechanism_fields(events)
                extras[name][label] = {'lifecycle': trial.lifecycle, 'outcome': trial.outcome,
                                       'failed_checks': trial.failed_checks, 'fault_triggered': trial.fault_triggered,
                                       'ticks': trial.usage.ticks, 'actor_calls': trial.usage.actor_calls,
                                       **{k: fields[k] for k in ('receipt_status', 'receipt_by', 'receipt_tick',
                                                                 'update_resent_by', 'waits', 'wait_ticks', 'deferred',
                                                                 'steps_executed', 'first_confirmation_tick',
                                                                 'report_upgrade_word')}}
        reference_in_store = reference_policy_records(coordinator.store)
        charged = guard.charged
        configuration_hash = campaign.configuration_hash
    finally:
        if client is not None:
            await client.aclose()
        coordinator.store.close()
    result = readout(work / 'lab' / 'lab.sqlite3', worlds_dir=work / 'worlds')
    by_setting = {}
    for comparison, settings_map in result['mechanism'].items():
        for setting, per_arm in settings_map.items():
            by_setting[f'{comparison}|{setting}'] = {
                arm: {k: v[k] for k in ('trials', 'completed', 'receipt_by', 'receipt_ticks', 'update_resent_by',
                                        'policy_update_calls', 'policy_reads', 'waits', 'wait_ticks', 'deferred',
                                        'steps_executed', 'premature_confirmations', 'reports_missing', 'untriggered')}
                for arm, v in per_arm.items()}
    summary = {'schema_version': MECHANISM_SCHEMA,
               'what': ('the declared plan and four extra schedules run in-process against the REAL simulator, policy '
                        'interpreter, PairedEvaluator and referee with a SCRIPTED fixture Actor; never model evidence. It '
                        'shows what each policy does on each schedule when the Actor reads the order, upgrades once at '
                        'tick 2, never re-sends, polls, and confirms after a receipt'),
               'provider_calls': 0, 'configuration_hash': configuration_hash,
               'configuration_matches_declared': configuration_hash == DECLARED_CONFIGURATION_HASH,
               'stop_reason': stop, 'cases_run': len(entries), 'sandbox_bound_charged': round(charged, 6),
               'harness_sha256': LOADED_HARNESS_SHA256, 'base_runner_sha256': LOADED_BASE_RUNNER_SHA256,
               'check_clock_drift_sha256': LOADED_DRIFT_CHECKER_SHA256,
               'protocol': {'path': protocol['path'], 'sha256': protocol['sha256'], 'declares_this_code': True},
               'reference_policy_records_in_store': reference_in_store,
               'by_comparison_setting': by_setting,
               'families_on_scripted_data': {f: {k: result['families'][f][k] for k in ('mr_completed', 'mr_n',
                                                                                       'b0_completed', 'b0_n',
                                                                                       'p_exact_one_sided', 'reading')}
                                             for f in FAMILIES},
               'labels_on_scripted_data': {f: {k: result['labels'][f][k] for k in (
                   'label_full', 'reached_strata', 'source_grade_strata', 'candidate_source_family', 'replicas_disagree')}
                   for f in FAMILIES},
               'calibration_strata_on_scripted_data': result['calibration_strata'],
               'l_vs_b0_on_scripted_data': {k: result['l_vs_b0'][k] for k in ('by_setting', 'l_completed', 'b0_completed',
                                                                              'label')},
               'safety_on_scripted_data': {'counted_by_arm': result['safety']['counted_by_arm'],
                                           'failures': result['safety']['failures']},
               'lab_defects': result['lab_defects'], 'world_scan': result['world_scan'], 'extras': extras}
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, summary)
    return summary


# ---------------------------------------------------------------- command line

def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=pathlib.Path,
                        help='New results directory inside artifacts/phase26-<date>/; never resumed')
    parser.add_argument('--settings', type=pathlib.Path, default=DEFAULT_SETTINGS)
    parser.add_argument('--expect-freeze', type=pathlib.Path, default=DEFAULT_FREEZE)
    parser.add_argument('--source-store', type=pathlib.Path, default=DEFAULT_SOURCE_STORE,
                        help='lab store B0 and L are read from, read-only')
    parser.add_argument('--worlds-dir', type=pathlib.Path, default=DEFAULT_WORLDS,
                        help="the running simulator's worlds directory; a live run requires artifacts/worlds")
    parser.add_argument('--ignore-run-record', action='append', default=[], metavar='PATH',
                        help='a non-final Phase 21 record or Phase 25/27-29 run manifest whose launching process is '
                             'gone (refused while that process may be running); recorded in the plan and the manifest')
    parser.add_argument('--protocol', type=pathlib.Path, default=DEFAULT_PROTOCOL)
    parser.add_argument('--expect-protocol-sha256', help="the reviewed protocol's sha256, as in the review record")
    parser.add_argument('--review-record', type=pathlib.Path, default=DEFAULT_REVIEW_RECORD,
                        help='written when the review closes and the phase is approved; a live run requires it')
    parser.add_argument('--spend-cap', type=float, default=SPEND_CAP)
    parser.add_argument('--confirm-entity')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--readout', type=pathlib.Path, metavar='STORE',
                        help='print the declared read-out of an output store (read-only) and exit')
    parser.add_argument('--mechanism-check', action='store_true',
                        help='$0: run the plan in-process with a scripted fixture Actor (never model evidence)')
    parser.add_argument('--work-dir', type=pathlib.Path, help='--mechanism-check: a new scratch directory')
    parser.add_argument('--mechanism-out', type=pathlib.Path, help='--mechanism-check: the summary JSON to write')
    args = parser.parse_args(argv)
    if args.mechanism_check:
        if not (args.work_dir and args.mechanism_out) or args.execute_live:
            parser.error('--mechanism-check needs --work-dir and --mechanism-out and never runs live')
    elif not args.readout and not args.output:
        parser.error('--output is required')
    return args


def main(argv=None):
    args = arguments(argv)
    try:
        if args.readout:
            print(json.dumps(readout(args.readout, worlds_dir=args.worlds_dir), indent=2))
            return 0
        if args.mechanism_check:
            summary = asyncio.run(mechanism_check(args))
            print(json.dumps({'mechanism_check': str(args.mechanism_out), 'provider_calls': 0,
                              'stop_reason': summary['stop_reason'], 'cases_run': summary['cases_run']}, indent=2))
            return 0
        plan, policies = prepare(args)
        blockers = live_blockers(plan, args)
        if not args.execute_live:
            print(json.dumps({'dry_run': True, 'provider_calls': 0, 'files_written': 0,
                              'live_run_allowed': not blockers, 'live_blockers': blockers, **plan}, indent=2))
            return 0
        if blockers:
            raise PlanningError('Live run refused: ' + '; '.join(blockers))
        return asyncio.run(execute(args, plan, policies))
    except Exception as error:  # noqa: BLE001
        if isinstance(error, PlanningError):
            safe = str(error)
        elif args.readout:
            safe = 'The read-out failed on this store; it may not be a complete Phase 26 output store'
        else:
            safe = 'Preflight failed; inspect local configuration and simulator readiness'
        print(json.dumps({'status': 'REJECTED', 'error_type': type(error).__name__, 'message': safe}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
