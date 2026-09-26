"""Phase 28a: a non-scoring, Mechanic-only probe of the upgrade-side repair (the go/no-go for Phase 28).

Why (docs/part2/PHASE28_DESIGN.md §6.0, §8.4; EXPERIMENT_PROGRAM_PHASES_28-31.md, Phase 28). Phase 26 showed that
"wait, then re-send the upgrade" (retry_original_request on orders) completes transient upgrade failures that the
baseline Actor usually abandons. The loop's Mechanic has only ever been shown notification-side evidence, and no
stored proposal has ever re-sent the upgrade (0 of 59). Phase 28 would point the loop at an upgrade-side source,
which needs a backend change. This probe asks first, for at most $5, whether the Mechanic ever writes that step when
it is shown upgrade-side evidence in the loop's own first-proposal format.

The requests. K = 30 slot-1 proposal requests, each built exactly as completion_study._execute builds its first
proposal (lines 394-403) for a study whose source is the planned `upgrade-3` case (F4 on update_order/orders,
occurrence 1, failure_count 3, seed 703):
  controls  six stored B0 episodes in planned_slots order (upgrade-3, healthy, upgrade-3, healthy, upgrade-3, healthy)
  evidence  summarize_evidence(bundles, outcomes={episode: adjudicated outcome}) (the v2 task-outcome protocol)
  outcomes  trial_outcomes(trials); candidate_history = []; runtime_contract(); parent_version 'policy-v0'
  specs     source_fault_spec = the upgrade-3 spec; control_fault_spec = case_manifest()'s healthy spec
  messages  Phase 25's mechanic_messages(context) (Mechanic._generate's request, exactly), temperature 0
  repair    when the first output fails MechanicOutput validation, one format-repair follow-up with _generate's
            correction message verbatim, as the loop does

The episodes (development data only, B0 only, read-only; no private_* record is ever read):
  upgrade-3 pool  the 19 v4 DeepSeek-V3.1 B0 episodes on F4 update_order count 3 that are valid and NOT completed
                  (8 in Phase 20's store, 11 in Phase 26's). A loop context exists only when the valid source controls
                  show 0 completions, so the 2 completing episodes are excluded. The schedule is read from each
                  store's pinned plan (scenario_hash -> public fault spec), never from a private recipe.
  healthy pool    v4 DeepSeek-V3.1 B0 healthy episodes that are valid and COMPLETED: 3 in Phase 20, 2 in Phase 26,
                  and Phase 23's 84 controls-stage healthy episodes in the main store (configuration 2cf63e93...).
  draws           30 distinct upgrade-3 triples and 30 distinct healthy triples, by seeded sha256 rank with a
                  per-episode use cap; episodes repeat across contexts, so the draws are correlated.

Bundles are rebuilt locally exactly as EvidenceGateway.get(require_remote=False) builds them (the stored observations,
the episode's report, the verdict's checks as findings; source 'local_only'). Two $0 positive controls refuse the
plan on any difference: (1) every main-store bundle rebuilt here equals its stored weave_verified bundle on
observations, report and findings; (2) with each Phase 23 study's own control bundles, this builder reproduces the
study's stored slot-1 proposal input byte for byte, apart from the `source` label of each evidence row.

The decision (PHASE28_DESIGN.md §6.0, approved in §19 decision 4; restored in review round 1):
  GO          at least one of the 30 draws is a valid policy (CANDIDATE) containing retry_original_request with
              service orders, at any hook and under any when/only_if (the design's "present" predicate, the same one
              as Phase 28's futility look)
  NO_GO       all 30 draws were delivered and none is (0 of 30: Wilson 95% upper bound 11.4%)
  INCOMPLETE  fewer than 30 delivered and none so far is; completing it needs the owner's approval: after runs that
              delivered nothing, a relaunch record (RELAUNCH_RULE); after a run that delivered anything, also a
              separately reviewed harness change (there is no completion mode)
Everything else is descriptive and never decides: the static check's label (CAN_FIRE, CANNOT_FIRE, UNCLEAR), where a
re-send fires and why one does not, the firing rates R_fire_draw and R_fire_valid, how each re-send is written,
NO_CHANGE and invalid shares, the draws the loop would have recorded as an infrastructure death (an empty or
unreadable output), distinct policies, the Phase 9 notification step, the Phase 17 attempt-4 pattern, both-sides
policies.

The static check (descriptive). The declared source path after a transient upgrade failure: the Actor's update_order
exhausted its adapter retries (the upgrade is attempted, has no receipt and reads UNKNOWN, never PENDING);
after_upgrade_response runs; on the stored source path the Actor then files a report without sending a confirmation
(19 of 19), so before_final_report runs next. Phase 25's reviewed abstract interpreter (run_hook) runs the policy
through those two hooks. A re-send CAN_FIRE if it executes in either; CANNOT_FIRE if it never executes there (gated on
PENDING, closed by an earlier step, a bound exhausted); UNCLEAR if it would execute only at a hook the stored source
path never reaches (before_confirmation, after_notification_response). Only one label is checked against stored
behaviour: CAN_FIRE at after_upgrade_response, by the manual-reference policy (18 of 18 fired). The two other stored
policies have no orders re-send and cannot disagree; CAN_FIRE at before_final_report, CANNOT_FIRE and UNCLEAR have no
dynamic validation (plan['positive_controls']['auditor_validation'] and 'auditor_validation_scope').

Nothing here creates a campaign, study, trial, world, policy or store row. The stores are opened read-only; results
are never shown to any model and never enter a study. Nothing under backend/app changes.

Dry by default. `--execute-live` needs `--confirm-entity`, `--out` and the reviewed plan, harness and protocol hashes;
the protocol's status block must no longer say it is not yet reviewed, it must carry the bare line "Reviewed for
launch: harness <sha256> plan <hash>", and the review record must repeat them, say status "approved", name the
approver, the configuration pin and this harness's $5 phase cap. The configuration pin 2cf63e93... is recomputed from
the code on disk, so the harness refuses once any Phase 28 backend change lands. A live run refuses beside any other
paid run (other phases' open run manifests and claims, the lab backend's active campaign, and any other
`--execute-live` experiment process by Phase 25's token rule, which excludes this process, its ancestors and its
descendants such as its own caffeinate helper), takes an atomic claim, and runs once. A run that delivered anything
is never repeated; after runs that delivered nothing, another launch needs `--relaunch-approval` with the owner's
record naming exactly that launch (RELAUNCH_RULE). Every attempt the spend guard admitted is charged in the final
manifest, including one in flight when an exception escaped the run.

Usage (from the repository root):
  python scripts/experiments/upgrade_mechanic_probe.py
  python scripts/experiments/upgrade_mechanic_probe.py --write-plan artifacts/phase28a-<date>/dry-plan
  python scripts/experiments/upgrade_mechanic_probe.py --readouts artifacts/phase28a-<date>/live
  python scripts/experiments/upgrade_mechanic_probe.py --finalize-abandoned artifacts/phase28a-live-claims/claim-NN.json
  python scripts/experiments/upgrade_mechanic_probe.py --execute-live --confirm-entity ENTITY \\
      --out artifacts/phase28a-<date>/live --expect-plan-hash H \\
      --expect-harness-sha256 S --expect-protocol-sha256 P \\
      [--relaunch-approval artifacts/phase28a-<date>/relaunch-approval-NN.json]
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.util
import itertools
import json
import math
import os
import pathlib
import re
import signal
import sqlite3
import subprocess
import sys
import traceback

# Even dry inspection should not create Python cache files in the workspace.
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


# ---------------------------------------------------------------- pinned imports (never edited)

class _PinnedSourceLoader(importlib.abc.SourceLoader):
    """Serves the bytes that were already read and checked; never the file again, never a bytecode cache."""

    def __init__(self, path, data):
        self._path, self._data = str(path), data

    def get_filename(self, fullname):
        return self._path

    def get_data(self, path):
        if path != self._path:
            raise OSError(f'only the pinned source is served ({path})')
        return self._data


def _load_pinned(path, digest, name):
    """Read the file once, compare its sha256 with the pin BEFORE any of it runs, then run exactly those bytes."""
    data = pathlib.Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ImportError(f'{path} is not the pinned file (sha256 {digest}); none of it was run, and this probe '
                          'refuses to load')
    spec = importlib.util.spec_from_loader(name, _PinnedSourceLoader(path, data))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, data


# Phase 25's harness: the Mechanic request rebuild, the static auditor and abstract interpreter, the classification
# rules, the provider request checks and the token-based paid-run process rule.
PHASE25_HARNESS = ROOT / 'scripts/experiments/slot2_probe.py'
PHASE25_HARNESS_SHA256 = '28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0'
# Phase 17's runner: the Phase 9 notification-step predicate (contains_step), for one descriptive read-out.
PHASE17_RUNNER = ROOT / 'scripts/experiments/run_full_loop.py'
PHASE17_RUNNER_SHA256 = '07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342'
s2, _PHASE25_SOURCE = _load_pinned(PHASE25_HARNESS, PHASE25_HARNESS_SHA256, 'faultlab_phase28a_slot2_probe')
rfl, _PHASE17_SOURCE = _load_pinned(PHASE17_RUNNER, PHASE17_RUNNER_SHA256, 'faultlab_phase28a_run_full_loop')

from pydantic import TypeAdapter, ValidationError  # noqa: E402

from app.agents.actor import RETRYABLE_TRANSPORT_CODES  # noqa: E402
from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4  # noqa: E402
from app.contracts.models import (MODEL_INPUT_TOKEN_LIMIT, Episode, EvidenceBundle, FaultSpec,  # noqa: E402
                                  MechanicCandidate, MechanicOutput, PublicObservation, TrialResult, canonical_json,
                                  content_hash)
from app.contracts.tokens import input_token_bound  # noqa: E402
from app.lab.completion_study import SCHEMA as COMPLETION_SCHEMA  # noqa: E402
from app.lab.completion_study import case_manifest, planned_slots  # noqa: E402
from app.lab.diagnosis import COMPACT_EVIDENCE_V2, runtime_contract, summarize_evidence, trial_outcomes  # noqa: E402
from app.lab.reproduction import valid_trial  # noqa: E402
from app.providers.runtime import RuntimeProviderError  # noqa: E402

SCHEMA = 'faultlab-upgrade-mechanic-probe/v1'
READOUT_SCHEMA = 'faultlab-upgrade-mechanic-probe-readouts/v1'
MANIFEST_NAME = 'upgrade-mechanic-probe-manifest.json'
PHASE_PREFIX = 'phase28a-'
FINAL_STATUSES = ('COMPLETED', 'STOPPED', 'ABORTED')
# A live run writes its manifest at exactly artifacts/phase28a-<date>/<name>/ (check_output); only that depth is read.
LIVE_MANIFEST_GLOB = f'{PHASE_PREFIX}*/*/{MANIFEST_NAME}'
CLAIM_DIR = 'phase28a-live-claims'
CLAIM_NAME = re.compile(r'claim-(\d+)\.json')
# A run whose process died while RUNNING may have one request and its blind retry admitted and charged but not yet
# recorded; --finalize-abandoned charges them.
ABANDONED_IN_FLIGHT_ATTEMPTS = 2
# Other paid runs of the program: open run manifests (a JSON object with started_at and no end marker) in directories
# of Phases 20, 21, 23, 25-29 and 30+, and their launch claims. Phases 22 and 24 (the heldout-2 seal and its check)
# are never listed and none of their files is opened. `phase28a-` never matches (this phase's own runs are checked by
# live_run_records); `phase28-` (the loop) does.
OTHER_RUN_DIR = re.compile(r'phase(?:2[01356789]|3[0-9])-[A-Za-z0-9._-]+')
OTHER_CLAIM_DIR = re.compile(r'phase(?:2[01356789]|3[0-9])-live-claims')
OTHER_CLAIMED_RUN = re.compile(r'artifacts/phase(?:2[01356789]|3[0-9])-[A-Za-z0-9._-]+/[A-Za-z0-9._-]+')
OTHER_RUN_AFTER_CLAIM = 'another_paid_run_after_claim'

# ---------------------------------------------------------------- stores (read-only)

MAIN_STORE = ROOT / 'artifacts/lab.sqlite3'
# Phase 23's last completion study was created at 05:42:09Z; heldout-2's first episode (Phase 24) started 05:51:21Z.
MAIN_STORE_CUTOFF = '2026-09-24T05:50:00Z'
# The two finished development stores that hold every v4 upgrade-side B0 episode, and the plans that name their
# schedules. Pinned by sha256; read with immutable=1 (no WAL, no shared-memory file is touched).
STATIC_STORES = {
    'phase20': {'store': 'artifacts/phase20-2026-09-23/run-1/lab.sqlite3',
                'store_sha256': '8d78f09938f514e225cc914df33a20732fcc9ce3d09b180192e802d4284a4487',
                'plan': 'artifacts/phase20-2026-09-23/run-1/plan.json',
                'plan_sha256': '549a9eb18eaecfcbde88e60a4d258490b4a9e6b14ac32b237c239de6c3617426'},
    'phase26': {'store': 'artifacts/phase26-2026-09-24/run-1/lab.sqlite3',
                'store_sha256': 'd1f8e741d2c91669cb1c5ee051f76fa288955580af4bbee328e865619ee160b9',
                'plan': 'artifacts/phase26-2026-09-24/run-1/plan.json',
                'plan_sha256': '0a9dfbdc390052052ced551fc10466bbb7701222680566c4c14097caf0d03287'},
}
STATIC_PURPOSE = 'challenge'
# Phase 23's run manifest names its studies; the main-store healthy pool and the context positive control use them.
PHASE23_MANIFEST = 'artifacts/phase23-2026-09-24/full-loop-manifest.json'
PHASE23_MANIFEST_SHA256 = 'aac41711ea8df103ed1c5bdb6df7a75275d019f60c716a9a0aaf102b7b31b6f5'
PHASE23_CONFIGURATION = '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba'
# The record kinds this probe may read. Every records query binds its kind as a parameter from this list; no
# private_* kind (private inputs, snapshots) is ever read.
READ_KINDS = ('episodes', 'trials', 'observations', 'configurations', 'evidence', 'completion_studies',
              'completion_proposal_inputs')

# ---------------------------------------------------------------- pins

EXPECTED_ACTOR_MODEL = 'deepseek-ai/DeepSeek-V3.1'
EXPECTED_MECHANIC_MODEL = s2.EXPECTED_MECHANIC_MODEL      # deepseek-ai/DeepSeek-V4-Pro-0813
EXPECTED_PROJECT = s2.EXPECTED_PROJECT
DECLARED_SETTINGS = s2.DECLARED_SETTINGS                  # artifacts/phase16-2026-09-22/settings-phase17.json
DECLARED_SETTINGS_SHA256 = s2.DECLARED_SETTINGS_SHA256
# The Phase 17 settings on the Phase 22 frozen code. Recomputed from the code on disk (s2.configuration_pins); any
# Phase 28 backend change moves it and this probe refuses.
DECLARED_CONFIGURATION_HASH = '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba'
DECLARED_FREEZE = 'artifacts/phase22-2026-09-24/gate-freeze-after.json'
DECLARED_FREEZE_SHA256 = '8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1'
# Files this probe depends on beyond Phase 25's own list, each compared with the Phase 22 freeze's recorded sha256.
# Never the scorer, never a private partition: those entries of the freeze are not opened.
EXTRA_FREEZE_FILES = ('backend/app/lab/evidence.py', 'backend/app/lab/reproduction.py', 'backend/app/agents/progress.py',
                      'backend/app/agents/actor.py', 'backend/app/agents/prompts/actor.md',
                      'backend/app/referee/manifests.py', 'audit/development.json')
PROTOCOL = ROOT / 'docs/part2/PHASE28A_EXPERIMENT.md'
REVIEW_RECORD = 'artifacts/phase28a-2026-09-25/review.json'
REVIEW_PENDING_MARKER = 'NOT yet reviewed'
REVIEWED_LINE = 'Reviewed for launch: harness {harness} plan {plan}'
REVIEW_APPROVED_STATUS = 'approved'
# PHASE28_DESIGN.md §6.0: completing an INCOMPLETE run needs the owner's approval. After runs that delivered nothing,
# another launch (it sends all 30 missing draws) needs the owner's record, artifacts/phase28a-<date>/relaunch-approval-
# NN.json, bound to the exact earlier runs and to this launch's --out, so one record admits one launch (round 2).
RELAUNCH_APPROVAL_NAME = re.compile(r'relaunch-approval-(\d+)\.json')
RELAUNCH_RULE = ('a run that delivered anything is never repeated or resumed (no completion mode). After earlier runs '
                 'that all delivered nothing, another launch sends all 30 draws (the missing ones) and is admitted only '
                 'with --relaunch-approval naming the owner\'s record artifacts/phase28a-<date>/relaunch-approval-NN.json '
                 '(status approved, approved_by, approved_at, and exactly this launch: earlier_undelivered_runs as the '
                 'harness lists them, out, plan_hash, harness_sha256), so one record admits one launch; with no earlier '
                 'run the argument must be absent. The phase cap still applies: a launch needs the rest of the $5 to '
                 'cover the 60 planned calls ($2.99)')

B0_POLICY_HASH = 'bafdc14f280cd47441baf69006e8ca55885ca0349667f2695f57e40b3b8926fb'
BASELINE_VERSION = 'policy-v0'
# The four certified completion repairs (Phase 17 attempt 9; Phase 23 attempts 2, 21 and 24): a draw that re-draws one
# is reported on its own line.
CERTIFIED_POLICY_HASHES = (
    'dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521',
    '711bddb68697e52dcd9b0d5b428fa96d7ec1fe0e95559d9a892b4a7772ac738e',
    '5735a9186d71b2f01bff04d69c889ea23db8d5be5a90b4f8f51968fc64b60b31',
    'd4bc993e1854b90ad2f0670f9b1164bbb68e7e61de91bf1361d70592bea0d6e1',
)

# ---------------------------------------------------------------- the design (declared before any call)

SOURCE_CASE_ID = 'upgrade-3'
CONTROL_CASE_ID = 'healthy'
# PHASE28_DESIGN.md §4.1 row 2 and §6.0: F4 update_order/orders, occurrence 1, failure_count 3, seed 703, made by
# FaultSpec.model_validate(...).model_dump(mode='json') as the Phase 28 builder will make it (its F6 checks equality).
SOURCE_FAULT_SPEC_INPUT = {'seed': 703, 'primitives': [{
    'kind': 'F4', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
    'parameters': {'failure_count': 3}}]}
# content_hash of that spec; equal to the design's stdlib mirror (p28-revise/draft_manifest_r1.py) and its draft file.
SOURCE_FAULT_SPEC_CONTENT_HASH = 'c4decdb93f69db9bce758e4bdb9951a40025ff40c2dd4b6bb73df68465f57c76'
K_CONTEXTS = 30
TRIPLE = 3
SAMPLE_SEED = 'faultlab-phase28a-2026-09-25'
DRAW_RULE = ('for each pool, every 3-episode combination (episode ids sorted) is ranked by sha256("<seed>:triple:'
             '<pool>:<id1>:<id2>:<id3>"); combinations are taken in rank order, skipping any that would use an episode '
             'more than cap = ceil(90 / pool size) times, until 30 are chosen; context k takes the k-th upgrade-3 '
             'triple and the k-th healthy triple; within a triple the episodes are ordered by sha256("<seed>:position:'
             '<pool>:<k>:<id>"); the six controls are interleaved in planned_slots order')
ID_RULE = ('campaign_id = "campaign-" + the first 32 hex of sha256("<seed>:campaign:<k>"); study_id = '
           '"completion-study-" + the first 32 hex of sha256("<seed>:study:<k>") (the loop\'s id shapes; no word in '
           'them names the probe)')
TEMPERATURE = 0
PER_REQUEST_DOLLAR_BOUND = 0.04984   # 32,000 in x $1.31/M + 2,000 out x $3.96/M (frozen Mechanic pricing)
HARD_SPEND_CAP = 5.0                 # PHASE28_DESIGN.md §6.0: hard cap $5
# 30 first requests plus at most 30 format repairs. Blind retries come out of the rest of the cap.
PLANNED_CALLS = 2 * K_CONTEXTS
MECHANIC_MAX_OUTPUT_TOKENS = s2.MECHANIC_MAX_OUTPUT_TOKENS
MECHANIC_TIMEOUT_SECONDS = s2.MECHANIC_TIMEOUT_SECONDS
CONSECUTIVE_ERROR_ABORT = 5
BACKOFF_SECONDS = (30, 120, 300, 300)
BLIND_RETRY_WAIT_SECONDS = 10
RECEIVED = ('ok', 'empty_response')
# One blind re-send of a request whose attempt failed with one of these codes and delivered no generation
# (pitfall 49). A delivered generation is never re-sent.
RESEND_CODES = s2.RESEND_CODES
# Mechanic._generate's correction message, verbatim (a test reads it from backend/app/agents/mechanic.py).
FORMAT_REPAIR_INSTRUCTION = ('Your response failed output_schema or its supplied evidence/choice bindings. Correct '
                             'formatting only. Copy cited IDs exactly from the supplied allowed lists; cite only the '
                             'evidence needed. Do not add authority, a new hypothesis, or a replacement canned '
                             'solution.')
Z95 = 1.959963984540054

# The declared source path of the static check (pitfall 77): after the Actor's update_order exhausted its adapter
# retries with a transient failure, the upgrade is attempted, has no receipt, and reads UNKNOWN (never PENDING: the
# write was never accepted). A status read delivers UNKNOWN.
REACHED_HOOKS = ('after_upgrade_response', 'before_final_report')
UNREACHED_HOOKS = ('before_confirmation', 'after_notification_response')
CAN_FIRE, CANNOT_FIRE, UNCLEAR = 'CAN_FIRE', 'CANNOT_FIRE', 'UNCLEAR'
# Every label the static check can give, and which of them a stored policy's behaviour checks (auditor_validation).
STATIC_LABELS = ('CAN_FIRE@after_upgrade_response', 'CAN_FIRE@before_final_report', 'CANNOT_FIRE', 'UNCLEAR')
DECISION_RULE = ('GO iff at least one of the 30 draws is a valid policy (CANDIDATE) containing retry_original_request '
                 'with service orders, at any hook and under any when/only_if (the "present" predicate of '
                 'PHASE28_DESIGN.md §6.0, approved in §19 decision 4; the same predicate as Phase 28\'s futility look); '
                 'NO_GO iff all 30 draws were delivered and none is; INCOMPLETE iff fewer than 30 were delivered and '
                 'none so far is. A refusal (NO_CHANGE) or invalid output is a draw without the step. The static '
                 'check\'s label (CAN_FIRE, CANNOT_FIRE, UNCLEAR) and where a re-send fires are descriptive and never '
                 'decide')

PlanningError = s2.PlanningError
sha256_file = s2.sha256_file
sha256_text = s2.sha256_text
write_json = s2.write_json
load_results = s2.load_results
status_block = s2.status_block
entry_delivered = s2.entry_delivered
delivered_generations = s2.delivered_generations
backend_status = s2.backend_status
settings_from_file = s2.settings_from_file
configuration_pins = s2.configuration_pins
check_pins = s2.check_pins
process_list = s2.process_list


class SpendGuard(s2.SpendGuard):
    """Phase 25's guard (every attempt charged at the bound, in whole micro-dollars), checked against THIS harness's
    $5 cap, not the one inside the pinned Phase 25 file."""

    def __init__(self, cap, per_request=PER_REQUEST_DOLLAR_BOUND):
        if not (type(cap) in (int, float) and math.isfinite(cap) and 0 < cap <= HARD_SPEND_CAP):
            raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
        self.cap, self.per_request, self.attempts = cap, per_request, 0


def rank(*parts):
    """Deterministic, version-independent order: sha256 of the seed and the parts."""
    return hashlib.sha256(':'.join((SAMPLE_SEED,) + tuple(str(p) for p in parts)).encode()).hexdigest()


def _root(root=None):
    """The repository root, read at call time so tests can point every guard at a tmp tree."""
    return pathlib.Path(root if root is not None else ROOT)


def pinned_imports_problem():
    """The rebuild, auditor and request checks are the reviewed code, or nothing is planned or sent. The executed
    bytes were checked at import; this re-checks them and the files on disk."""
    for path, data, digest in ((PHASE25_HARNESS, _PHASE25_SOURCE, PHASE25_HARNESS_SHA256),
                               (PHASE17_RUNNER, _PHASE17_SOURCE, PHASE17_RUNNER_SHA256)):
        if hashlib.sha256(data).hexdigest() != digest or sha256_file(path) != digest:
            return f'scripts/experiments/{path.name} is not the pinned file; its code cannot be trusted'
    if s2.PER_REQUEST_DOLLAR_BOUND != PER_REQUEST_DOLLAR_BOUND or s2.DECLARED_CONFIGURATION_HASH != DECLARED_CONFIGURATION_HASH:
        return "The Phase 25 harness does not carry this phase's configuration pin and dollar bound"
    return None


def wilson(k, n, z=Z95):
    return s2.wilson(k, n, z)


# ---------------------------------------------------------------- read-only store access

class StoreReader:
    """A read-only view of one store. Every records query binds its kind from READ_KINDS; every statement and its
    parameters are recorded, so a test can show that no private_* record was ever read."""

    def __init__(self, connection, label):
        self.connection, self.label, self.statements = connection, label, []

    def _execute(self, sql, params=()):
        self.statements.append((sql, tuple(params)))
        return self.connection.execute(sql, params)

    @staticmethod
    def _kind(kind):
        if kind not in READ_KINDS:
            raise PlanningError(f'Record kind {kind!r} is not one this probe may read')
        return kind

    def record_text(self, kind, record_id):
        row = self._execute('select payload, immutable from records where kind=? and id=?',
                            (self._kind(kind), record_id)).fetchone()
        return (row[0], bool(row[1])) if row else (None, False)

    def record(self, kind, record_id):
        text, _ = self.record_text(kind, record_id)
        return json.loads(text) if text is not None else None

    def records(self, kind, *, configuration_hash=None):
        """(id, payload) of every record of one kind, in store order; optionally only one configuration's."""
        if configuration_hash is None:
            rows = self._execute('select id, payload from records where kind=? order by rowid', (self._kind(kind),))
        else:
            rows = self._execute("select id, payload from records where kind=? and "
                                 "json_extract(payload, '$.configuration_hash')=? order by rowid",
                                 (self._kind(kind), configuration_hash))
        return [(i, json.loads(p)) for i, p in rows]

    def observations(self, episode_ids):
        """{episode_id: [observation payloads in store order]} in ONE scan (list_records('observations') order,
        EvidenceGateway.get's order)."""
        wanted = sorted(set(episode_ids))
        out = {episode_id: [] for episode_id in wanted}
        rows = self._execute("select payload from records where kind=? and json_extract(payload, '$.episode_id') in "
                             "(select value from json_each(?)) order by rowid",
                             (self._kind('observations'), json.dumps(wanted)))
        for (payload,) in rows:
            value = json.loads(payload)
            out[value['episode_id']].append(value)
        return out

    def events(self, episode_id):
        return [json.loads(p) for (p,) in self._execute('select payload from events where episode_id=? order by seq',
                                                        (episode_id,))]

    def close(self):
        self.connection.close()


def open_main(path=None):
    path = pathlib.Path(path or MAIN_STORE).resolve()
    if not path.exists():
        raise PlanningError(f'No store at {path}')
    return StoreReader(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True), 'main')


def open_static(label, root=None):
    """A finished store, pinned by sha256, read without touching its WAL or shared-memory files."""
    entry = STATIC_STORES[label]
    root = _root(root)
    path = (root / entry['store']).resolve()
    if not path.exists():
        raise PlanningError(f'Store not found: {entry["store"]}')
    wal = path.with_name(path.name + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise PlanningError(f'{entry["store"]} has an unapplied write-ahead log; the pinned file is not the whole store')
    if sha256_file(path) != entry['store_sha256']:
        raise PlanningError(f'{entry["store"]} is not the pinned store')
    return StoreReader(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True), label)


def load_static_plan(label, root=None):
    entry = STATIC_STORES[label]
    path = _root(root) / entry['plan']
    if not path.is_file() or sha256_file(path) != entry['plan_sha256']:
        raise PlanningError(f'{entry["plan"]} is not the pinned plan')
    return json.loads(path.read_text())


# ---------------------------------------------------------------- the source spec and the controls order

def source_fault_spec():
    return FaultSpec.model_validate(SOURCE_FAULT_SPEC_INPUT).model_dump(mode='json')


def control_fault_spec():
    """case_manifest()'s healthy control (dev-1, seed 101), exactly as the loop's manifest carries it."""
    cases = {case['case_id']: case for case in case_manifest()['cases']}
    return cases[CONTROL_CASE_ID]['fault_spec']


def is_upgrade3(spec):
    """F4 on update_order/orders, occurrence 1, failure_count 3, in the task's scope: the source's fault family."""
    primitives = spec.get('primitives') or []
    return (spec.get('scope') == 'orders.upgrade_then_confirm/v1' and len(primitives) == 1
            and primitives[0].get('kind') == 'F4' and primitives[0].get('target_tool') == 'update_order'
            and primitives[0].get('target_service') == 'orders' and primitives[0].get('occurrence') == 1
            and primitives[0].get('parameters') == {'failure_count': 3})


def controls_order():
    """The controls stage of planned_slots (the loop's reviewed code) for a manifest whose source is upgrade-3."""
    manifest = {'cases': [{'case_id': SOURCE_CASE_ID, 'fault_spec': source_fault_spec(), 'fixture_id': 'standard-v1'},
                          {'case_id': CONTROL_CASE_ID, 'fault_spec': control_fault_spec(), 'fixture_id': 'standard-v1'}],
                'source_case_id': SOURCE_CASE_ID, 'control_case_id': CONTROL_CASE_ID}
    return [slot['case_id'] for slot in planned_slots(manifest) if slot['stage'] == 'controls']


# ---------------------------------------------------------------- the local evidence rebuild

def local_bundle(reader, episode_id, observations):
    """EvidenceGateway.get(require_remote=False), exactly, minus its cross-context check (the probe's episodes come
    from several campaigns by declaration). Its other eligibility rules are applied."""
    text, _ = reader.record_text('episodes', episode_id)
    if text is None:
        raise PlanningError(f'{reader.label}: no episode {episode_id}')
    episode = Episode.model_validate_json(text)
    if (episode.split != 'development' or episode.arm == 'B1' or episode.lifecycle != 'COMPLETED'
            or episode.experiment_purpose in ('diagnostic_profile', 'selection_comparison', 'portability')):
        raise PlanningError(f'{reader.label}: {episode_id} is not eligible optimizer evidence')
    config = reader.record('configurations', episode.configuration_hash)
    if not config:
        raise PlanningError(f'{reader.label}: no configuration {episode.configuration_hash}')
    parsed = [PublicObservation.model_validate_json(canonical_json(o)) for o in observations]
    fields = {'episode_id': episode_id, 'policy_hash': episode.policy_hash, 'contract_hash': config['contract_hash'],
              'scorer_hash': config['scorer_hash'], 'source': 'local_only', 'root_call_id': None, 'child_call_ids': [],
              'observations': parsed, 'report': episode.report,
              'findings': episode.verdict.checks if episode.verdict else [], 'retrieved_at': None,
              'source_project': None}
    bundle = EvidenceBundle(**fields, digest='0' * 64)
    bundle.digest = content_hash({k: v for k, v in bundle.model_dump(mode='json').items() if k != 'digest'})
    return bundle, episode


BUNDLE_COMPARED = ('episode_id', 'policy_hash', 'contract_hash', 'scorer_hash', 'observations', 'report', 'findings')


def bundle_matches_stored(bundle, stored):
    """Positive control: the local rebuild equals the stored weave_verified bundle on everything the loop's evidence
    summary can read (only the provenance fields differ)."""
    if not stored or stored.get('source') != 'weave_verified':
        return False
    try:
        verified = EvidenceBundle.model_validate_json(canonical_json(stored))
    except ValidationError:
        return False
    mine, theirs = bundle.model_dump(mode='json'), verified.model_dump(mode='json')
    return all(canonical_json(mine[key]) == canonical_json(theirs[key]) for key in BUNDLE_COMPARED)


def first_actor_context(events):
    for event in events:
        if event.get('type') == 'actor_output':
            return (event.get('payload') or {}).get('actor_context_protocol')
    return None


def actor_reached_confirmation(events):
    return any(e.get('type') == 'tool_dispatched' and (e.get('payload') or {}).get('caller') == 'actor'
               and (e.get('payload') or {}).get('tool') == 'send_confirmation' for e in events)


def policy_dispatched_upgrade(events):
    """The Phase 28 design's "fires" predicate (§7.2): the policy itself dispatched update_order."""
    return any(e.get('type') == 'tool_dispatched' and (e.get('payload') or {}).get('caller') == 'policy'
               and (e.get('payload') or {}).get('tool') == 'update_order' for e in events)


# ---------------------------------------------------------------- the pools

def _plan_cases(plan):
    """scenario_hash -> (case_id, role) from a pinned plan's public fault specs; each spec must hash to its
    scenario_hash, or the plan cannot name the episodes' schedules."""
    out = {}
    for case in plan['cases']:
        spec = FaultSpec.model_validate(case['fault_spec']).model_dump(mode='json')
        if content_hash(spec) != case['scenario_hash']:
            raise PlanningError(f'A pinned plan\'s case {case["case_id"]} does not hash to its scenario_hash')
        role = SOURCE_CASE_ID if is_upgrade3(spec) else CONTROL_CASE_ID if not spec['primitives'] else None
        out[case['scenario_hash']] = (case['case_id'], role, spec)
    return out


def _entry(store, trial, bundle, case, configuration_hash, study_id=None):
    return {'store': store, 'episode_id': trial.episode_id, 'case': case, 'study_id': study_id,
            'configuration_hash': configuration_hash,
            'scenario_hash': trial.scenario_hash, 'outcome': trial.outcome, 'failed_checks': list(trial.failed_checks),
            'actor_calls': trial.usage.actor_calls, 'http_attempts': trial.usage.http_attempts,
            'observations': len(bundle.observations), 'report_present': bundle.report is not None,
            'bundle_digest': bundle.digest}


def static_pools(label, root=None):
    """The upgrade-3 and healthy B0 episodes of one finished store. Returns (pools, exclusions, facts, rows, reader
    statements, configurations) where rows maps episode_id -> (trial, bundle) and configurations maps each pool
    episode's configuration_hash -> its stored configuration record."""
    plan = load_static_plan(label, root)
    if plan.get('actor_context_protocol') != ACTOR_CONTEXT_PROTOCOL_V4:
        raise PlanningError(f'The {label} plan is not a v4 Actor-context run')
    cases = _plan_cases(plan)
    reader = open_static(label, root)
    pools, excluded, rows, facts = {SOURCE_CASE_ID: [], CONTROL_CASE_ID: []}, Counter(), {}, Counter()
    configurations = {}
    try:
        trials = {i: p for i, p in reader.records('trials')}
        candidates = []
        for episode_id, payload in reader.records('episodes'):
            case = cases.get(payload.get('scenario_hash'))
            if case is None or case[1] is None:
                continue
            candidates.append((episode_id, payload, case))
        observations = reader.observations([c[0] for c in candidates])
        for episode_id, payload, (case_id, role, _) in candidates:
            if (payload.get('arm') != 'B0' or payload.get('policy_hash') != B0_POLICY_HASH
                    or payload.get('split') != 'development' or payload.get('experiment_purpose') != STATIC_PURPOSE):
                excluded[f'{role}:not_a_development_B0_challenge_episode (L or MR arm)'] += 1
                continue
            if payload.get('model') != EXPECTED_ACTOR_MODEL:
                excluded[f'{role}:other_actor_model'] += 1
                continue
            events = reader.events(episode_id)
            if first_actor_context(events) != ACTOR_CONTEXT_PROTOCOL_V4:
                excluded[f'{role}:not_v4'] += 1
                continue
            trial = TrialResult.model_validate(trials[episode_id]) if episode_id in trials else None
            if (trial is None or trial.episode_id != episode_id or trial.arm != 'B0' or trial.policy_hash != B0_POLICY_HASH
                    or trial.scenario_hash != payload['scenario_hash']):
                raise PlanningError(f'{label}: the trial record of {episode_id} does not match its episode')
            if not valid_trial(trial):
                excluded[f'{role}:invalid_trial'] += 1
                continue
            if role == SOURCE_CASE_ID and trial.outcome == 'COMPLETED':
                excluded[f'{role}:completed (a loop context needs 0 source completions)'] += 1
                continue
            if role == CONTROL_CASE_ID and trial.outcome != 'COMPLETED':
                excluded[f'{role}:not_completed'] += 1
                continue
            bundle, episode = local_bundle(reader, episode_id, observations[episode_id])
            if role == SOURCE_CASE_ID:
                facts['actor_sent_confirmation'] += actor_reached_confirmation(events)
                facts['report_submitted'] += any(e.get('type') == 'report_submitted' for e in events)
                facts['source_episodes'] += 1
            if episode.configuration_hash not in configurations:
                configurations[episode.configuration_hash] = reader.record('configurations', episode.configuration_hash)
            rows[episode_id] = (trial, bundle)
            pools[role].append(_entry(label, trial, bundle, case_id, episode.configuration_hash))
    finally:
        reader.close()
    return pools, dict(excluded), dict(facts), rows, list(reader.statements), configurations


def phase23_studies(reader, root=None):
    """The Phase 23 completion studies in the main store: configuration 2cf63e93..., created before the cutoff, not a
    replay, v4 Actor context and evidence v2. The set must equal the pinned Phase 23 run manifest's studies."""
    path = _root(root) / PHASE23_MANIFEST
    if not path.is_file() or sha256_file(path) != PHASE23_MANIFEST_SHA256:
        raise PlanningError(f'{PHASE23_MANIFEST} is not the pinned Phase 23 run manifest')
    expected = {a['study_id'] for a in json.loads(path.read_text())['attempts'] if a.get('study_id')}
    studies = []
    for _, study in reader.records('completion_studies', configuration_hash=PHASE23_CONFIGURATION):
        if not s2.before_cutoff(study.get('created_at'), MAIN_STORE_CUTOFF) or study.get('replay_of') is not None:
            continue
        if (study.get('actor_context_protocol') != ACTOR_CONTEXT_PROTOCOL_V4
                or study.get('evidence_protocol') != COMPACT_EVIDENCE_V2):
            raise PlanningError(f'Phase 23 study {study["study_id"]} is not a v4 / evidence-v2 study')
        studies.append(study)
    studies.sort(key=lambda s: (s['created_at'], s['study_id']))
    if {s['study_id'] for s in studies} != expected:
        raise PlanningError('The main store\'s Phase 23 studies differ from the pinned Phase 23 run manifest')
    return studies


def study_trial(row):
    return TrialResult.model_validate_json(canonical_json(row['trial']))


def main_store_inputs(store=None, root=None):
    """Phase 23's healthy controls (the main-store healthy pool) and the two positive controls. Returns (pool,
    excluded, rows, positive, statements, configurations)."""
    reader = open_main(store)
    try:
        studies = phase23_studies(reader, root)
        wanted = sorted({r['trial']['episode_id'] for s in studies for r in s.get('trial_rows') or []
                         if r['stage'] == 'controls'})
        observations = reader.observations(wanted)
        bundles, stored_equal, differing, not_rebuilt = {}, 0, [], []
        for episode_id in wanted:
            try:
                bundle, episode = local_bundle(reader, episode_id, observations[episode_id])
            except PlanningError:
                not_rebuilt.append(episode_id)   # not eligible evidence (e.g. a lab error); never used below
                continue
            bundles[episode_id] = (bundle, episode)
            if bundle_matches_stored(bundle, reader.record('evidence', episode_id)):
                stored_equal += 1
            else:
                differing.append(episode_id)
        # Positive control 2: the context builder against every stored slot-1 input of Phase 23.
        contexts_checked, contexts_equal, context_differing = 0, 0, []
        for study in studies:
            stored, immutable = reader.record_text('completion_proposal_inputs', f'{study["study_id"]}-1')
            if stored is None:
                continue
            contexts_checked += 1
            cases = {case['case_id']: case for case in study['manifest']['cases']}
            controls = [r for r in study['trial_rows'] if r['stage'] == 'controls']
            if any(r['trial']['episode_id'] not in bundles for r in controls):
                context_differing.append(study['study_id'])
                continue
            built = proposal_context(
                campaign_id=study['campaign_id'], study_id=study['study_id'],
                source_spec=cases[study['manifest']['source_case_id']]['fault_spec'],
                control_spec=cases[study['manifest']['control_case_id']]['fault_spec'],
                rows=[(study_trial(r), bundles[r['trial']['episode_id']][0]) for r in controls])
            if immutable and canonical_json(relabel_source(built, 'weave_verified')) == stored \
                    and all(row['source'] == 'weave_verified' for row in json.loads(stored)['development_evidence']['episodes']):
                contexts_equal += 1
            else:
                context_differing.append(study['study_id'])
        pool, excluded = [], Counter()
        rows, configurations = {}, {}
        for study in studies:
            for r in study.get('trial_rows') or []:
                if r['stage'] != 'controls' or r['case_id'] != CONTROL_CASE_ID:
                    continue
                trial = study_trial(r)
                if trial.episode_id not in bundles:
                    excluded['healthy:not_eligible_evidence'] += 1
                    continue
                bundle, episode = bundles[trial.episode_id]
                if trial.arm != 'B0' or trial.policy_hash != B0_POLICY_HASH or episode.model != EXPECTED_ACTOR_MODEL:
                    excluded['healthy:not_a_V3.1_B0_episode'] += 1
                    continue
                if not valid_trial(trial) or trial.outcome != 'COMPLETED':
                    excluded['healthy:not_valid_and_completed'] += 1
                    continue
                if episode.configuration_hash not in configurations:
                    configurations[episode.configuration_hash] = reader.record('configurations',
                                                                               episode.configuration_hash)
                rows[trial.episode_id] = (trial, bundle)
                pool.append(_entry('main', trial, bundle, 'phase23-controls-healthy', episode.configuration_hash,
                                   study['study_id']))
        positive = {
            'bundle_rebuild': {'rule': ('every main-store Phase 23 controls episode: the local rebuild equals the stored '
                                        f'weave_verified bundle on {list(BUNDLE_COMPARED)}'),
                               'episodes_checked': len(bundles), 'equal': stored_equal, 'differing': differing,
                               'controls_episodes': len(wanted), 'not_rebuilt_not_eligible': not_rebuilt},
            'context_rebuild': {'rule': ('every Phase 23 study with a stored slot-1 input: this builder, given the '
                                         'study\'s own ids, fault specs and locally rebuilt control bundles, reproduces '
                                         'the stored input byte for byte once each evidence row\'s source label reads '
                                         'weave_verified'),
                                'studies': len(studies), 'studies_checked': contexts_checked,
                                'byte_equal_apart_from_source': contexts_equal, 'differing': context_differing}}
    finally:
        reader.close()
    return pool, dict(excluded), rows, positive, list(reader.statements), configurations


def relabel_source(context, label):
    """The context with every evidence row's source label replaced (the one declared difference from the loop)."""
    changed = json.loads(canonical_json(context))
    for row in changed['development_evidence']['episodes']:
        row['source'] = label
    return changed


# ---------------------------------------------------------------- the context (completion_study._execute, slot 1)

def proposal_context(*, campaign_id, study_id, source_spec, control_spec, rows):
    """completion_study._execute's slot-1 proposal_context (lines 394-403), with rows = [(trial, bundle)] in the
    controls order and no candidate yet (candidate_history = deepcopy([]) = [])."""
    return {'campaign_id': campaign_id, 'study_id': study_id, 'objective': COMPLETION_SCHEMA,
            'parent_version': BASELINE_VERSION, 'source_fault_spec': source_spec, 'control_fault_spec': control_spec,
            'runtime_contract': runtime_contract(),
            'development_evidence': summarize_evidence([bundle for _, bundle in rows],
                                                       outcomes={t.episode_id: t.outcome for t, _ in rows}),
            'observed_outcomes': trial_outcomes([t for t, _ in rows]),
            'candidate_history': []}


def probe_ids(k):
    return f'campaign-{rank("campaign", k)[:32]}', f'completion-study-{rank("study", k)[:32]}'


def draw_triples(pool_ids, pool_name, count=K_CONTEXTS):
    """DRAW_RULE for one pool: `count` distinct triples by seeded rank, each episode used at most cap times."""
    ids = sorted(set(pool_ids))
    if len(ids) < TRIPLE:
        raise PlanningError(f'The {pool_name} pool has fewer than {TRIPLE} episodes')
    cap = math.ceil(TRIPLE * count / len(ids))
    ranked = sorted(itertools.combinations(ids, TRIPLE), key=lambda combo: rank('triple', pool_name, *combo))
    uses, chosen = Counter(), []
    for combo in ranked:
        if any(uses[e] >= cap for e in combo):
            continue
        chosen.append(combo)
        uses.update(combo)
        if len(chosen) == count:
            break
    if len(chosen) < count:
        raise PlanningError(f'The {pool_name} draw found only {len(chosen)} triples under a cap of {cap}')
    ordered = [sorted(combo, key=lambda e, k=k: rank('position', pool_name, k, e)) for k, combo in enumerate(chosen, 1)]
    return ordered, cap, dict(sorted(uses.items()))


def build_requests(pools, rows):
    """The 30 contexts and their requests, in context order. Returns (requests, prompts, draws)."""
    source_spec, control_spec = source_fault_spec(), control_fault_spec()
    order = controls_order()
    upgrade, upgrade_cap, upgrade_uses = draw_triples([e['episode_id'] for e in pools[SOURCE_CASE_ID]], SOURCE_CASE_ID)
    healthy, healthy_cap, healthy_uses = draw_triples([e['episode_id'] for e in pools[CONTROL_CASE_ID]], CONTROL_CASE_ID)
    where = {e['episode_id']: e['store'] for role in pools for e in pools[role]}
    requests, prompts = [], {}
    for k, (u, h) in enumerate(zip(upgrade, healthy), 1):
        queues = {SOURCE_CASE_ID: list(u), CONTROL_CASE_ID: list(h)}
        episodes = [queues[case].pop(0) for case in order]
        campaign_id, study_id = probe_ids(k)
        context = proposal_context(campaign_id=campaign_id, study_id=study_id, source_spec=source_spec,
                                   control_spec=control_spec, rows=[rows[e] for e in episodes])
        messages = s2.mechanic_messages(context)
        messages_hash = content_hash(messages)
        prompts[messages_hash] = {'messages_hash': messages_hash, 'messages': messages, 'context': k}
        requests.append({'request_id': f'r{k:04d}', 'context': k, 'campaign_id': campaign_id, 'study_id': study_id,
                         'controls': [{'case': case, 'store': where[e], 'episode_id': e} for case, e in zip(order, episodes)],
                         'messages_hash': messages_hash,
                         'request_hash': s2.request_digest(s2.request_body(messages, TEMPERATURE)),
                         'input_token_bound': input_token_bound(messages, EXPECTED_MECHANIC_MODEL),
                         'user_bytes': len(messages[1]['content'].encode('utf-8'))})
    draws = {'seed': SAMPLE_SEED, 'rule': DRAW_RULE, 'id_rule': ID_RULE, 'controls_order': order,
             'caps': {SOURCE_CASE_ID: upgrade_cap, CONTROL_CASE_ID: healthy_cap},
             'uses': {SOURCE_CASE_ID: upgrade_uses, CONTROL_CASE_ID: healthy_uses}}
    return requests, prompts, draws


# ---------------------------------------------------------------- the static check (pitfall 77)

def transient_state():
    """The declared source path's abstract state after the Actor's update_order exhausted its adapter retries with a
    transient failure (s2's abstract state shape)."""
    return {'orders': s2._service(True, None, 'UNKNOWN'), 'notifications': s2._service()}


TRANSIENT_READS = {'orders': 'UNKNOWN', 'notifications': 'UNKNOWN'}


def orders_retry_steps(rules):
    return [{'rule': i, 'step': j, 'hook': rule.get('hook'), 'when': rule.get('when'),
             'only_if': step.get('only_if', 'always')}
            for i, rule in enumerate(rules) for j, step in enumerate(rule.get('steps') or [])
            if step.get('op') == 'retry_original_request' and step.get('service') == 'orders']


def upgrade_audit(content):
    """Static read of one candidate policy's orders re-sends on the declared source path (descriptive: the decision
    counts present re-sends, and this label never decides).

    after_upgrade_response runs first (upgrade attempted, no receipt, UNKNOWN; reads deliver UNKNOWN); unless a step
    there closed business or exhausted a bound, before_final_report runs next on the same state and the same policy
    budget. A re-send CAN_FIRE if it executes in either hook, CANNOT_FIRE if it executes in neither and in no other
    hook, and is UNCLEAR if it would execute only at before_confirmation or after_notification_response, which the
    stored source path never reaches (the Actor sent no confirmation in any of the 19 pool episodes)."""
    rules = content.get('rules') or []
    steps = orders_retry_steps(rules)
    gates = sorted({step[key] for step in steps for key in ('when', 'only_if')})
    out = {'present': bool(steps), 'orders_retry_steps': len(steps), 'steps': steps,
           'hooks': sorted({step['hook'] for step in steps}), 'gates': gates,
           'label': None, 'fires_at': None, 'reason': None}
    if not steps:
        return out
    budget = {'steps': 0, 'waits': 0}
    state, events, closed, _, exhausted = s2.run_hook(rules, 'after_upgrade_response', transient_state(),
                                                      TRANSIENT_READS, budget)
    if ('retry', 'orders') in events:
        return {**out, 'label': CAN_FIRE, 'fires_at': 'after_upgrade_response', 'reason': 'executes on the source path'}
    if closed or exhausted:
        return {**out, 'label': CANNOT_FIRE,
                'reason': 'an earlier step at after_upgrade_response closed business or exhausted a bound'}
    _, events, _, _, _ = s2.run_hook(rules, 'before_final_report', state, TRANSIENT_READS, budget)
    if ('retry', 'orders') in events:
        return {**out, 'label': CAN_FIRE, 'fires_at': 'before_final_report', 'reason': 'executes on the source path'}
    for hook in UNREACHED_HOOKS:
        probe = transient_state()
        if hook == 'after_notification_response':
            probe['notifications'] = s2._service(True, None, 'UNKNOWN')
        _, events, _, _, _ = s2.run_hook(rules, hook, probe, TRANSIENT_READS, {'steps': 0, 'waits': 0})
        if ('retry', 'orders') in events:
            return {**out, 'label': UNCLEAR,
                    'reason': f'executes only at {hook}, which the stored source path never reaches'}
    if 'current_operation_pending' in gates:
        reason = ('gated on current_operation_pending: after a transient failure the upgrade reads UNKNOWN, never '
                  'PENDING (pitfall 77)')
    elif any(gate in ('upgrade_succeeded', 'upgrade_terminal_failure') for gate in gates):
        reason = 'gated on a receipt a transient failure never delivers'
    else:
        reason = 'never executes on the source path'
    return {**out, 'label': CANNOT_FIRE, 'reason': reason}


def auditor_validation(root=None):
    """The static label against what stored policies actually did on F4 upgrade failures (counts 2-4, L arm, valid
    trials): 'fired' = the policy itself dispatched update_order. Policies: every non-baseline policy with content in
    the pinned Phase 20 and Phase 26 plans (dd62c857..., 711bddb6... and the manual-reference b8d18218...). A policy
    with no orders re-send is not informative: its row "agrees" whenever the policy never dispatched update_order,
    which cannot fail, so it validates no label (auditor_validation_scope)."""
    out = []
    for label in STATIC_STORES:
        plan = load_static_plan(label, root)
        f4 = {c['scenario_hash']: c['fault_spec']['primitives'][0]['parameters']['failure_count'] for c in plan['cases']
              if len(c['fault_spec']['primitives']) == 1 and c['fault_spec']['primitives'][0]['kind'] == 'F4'
              and c['fault_spec']['primitives'][0]['target_tool'] == 'update_order'}
        policies = {}
        for name, policy in sorted((plan.get('policies') or {}).items()):
            content = policy.get('content') if isinstance(policy, dict) else None
            if content and policy.get('policy_hash') != B0_POLICY_HASH:
                policies[policy['policy_hash']] = (name, content)
        reader = open_static(label, root)
        try:
            trials = {i: TrialResult.model_validate(p) for i, p in reader.records('trials')}
            for policy_hash, (name, content) in sorted(policies.items()):
                audit = upgrade_audit(content)
                fired = Counter()
                for episode_id, trial in sorted(trials.items()):
                    if trial.policy_hash != policy_hash or trial.arm != 'L' or trial.scenario_hash not in f4:
                        continue
                    if not valid_trial(trial):
                        continue
                    fired[policy_dispatched_upgrade(reader.events(episode_id))] += 1
                expected_fire = audit['label'] == CAN_FIRE and audit['fires_at'] == 'after_upgrade_response'
                out.append({'store': label, 'plan_name': name, 'policy_hash': policy_hash,
                            'content_hash_matches': content_hash(content) == policy_hash,
                            'informative': audit['present'],
                            'static_present': audit['present'], 'static_label': audit['label'],
                            'static_fires_at': audit['fires_at'],
                            'dynamic_fired': fired[True], 'dynamic_not_fired': fired[False],
                            'agrees': (fired[True] + fired[False] > 0
                                       and (fired[False] == 0 if expected_fire else fired[True] == 0))})
        finally:
            reader.close()
    return out


def _label_key(label, fires_at):
    return f'{label}@{fires_at}' if label == CAN_FIRE else label


def auditor_validation_scope(validation):
    """What auditor_validation actually checks. Only a policy with an orders re-send can disagree with its label; each
    such policy validates the one label it carries. Every other label has no dynamic validation."""
    informative = [v for v in validation if v['static_present']]
    validated = sorted({_label_key(v['static_label'], v['static_fires_at']) for v in informative
                        if v['agrees'] and v['dynamic_fired'] + v['dynamic_not_fired'] > 0})
    return {'policies': len(validation), 'informative_policies': len(informative),
            'policies_without_an_orders_re_send_cannot_disagree': len(validation) - len(informative),
            'labels_validated': validated,
            'labels_not_validated': [label for label in STATIC_LABELS if label not in validated]}


# ---------------------------------------------------------------- the plan

def check_freeze_extra(root=None):
    """EXTRA_FREEZE_FILES against the Phase 22 freeze's recorded sha256 (Phase 25's check covers its own list)."""
    root = _root(root)
    freeze = json.loads((root / DECLARED_FREEZE).read_text())
    moved = [name for name in EXTRA_FREEZE_FILES if freeze['files'].get(name) != sha256_file(root / name)]
    if moved:
        raise PlanningError(f'The tree no longer matches the Phase 22 freeze: {", ".join(moved)}')
    return list(EXTRA_FREEZE_FILES)


def check_budget(planned_calls, spend_cap):
    if not (type(spend_cap) in (int, float) and math.isfinite(spend_cap) and 0 < spend_cap <= HARD_SPEND_CAP):
        raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    if SpendGuard.micro(planned_calls * PER_REQUEST_DOLLAR_BOUND) > SpendGuard.micro(spend_cap):
        raise PlanningError(f'{planned_calls} planned calls exceed the ${spend_cap:.2f} cap at '
                            f'${PER_REQUEST_DOLLAR_BOUND}/request')


def collect_inputs(*, store=None, root=None, settings_path=None):
    """Everything read from disk: pins, the three stores, the pools and the positive controls ($0, read-only)."""
    problem = pinned_imports_problem()
    if problem:
        raise PlanningError(problem)
    settings_path = pathlib.Path(settings_path or _root(root) / DECLARED_SETTINGS)
    if sha256_file(settings_path) != DECLARED_SETTINGS_SHA256:
        raise PlanningError('The settings file is not the declared Phase 17 settings file')
    pins = configuration_pins(settings_from_file(settings_path, env_path=os.devnull))
    check_pins(pins)
    if pins['configuration_hash'] != DECLARED_CONFIGURATION_HASH:
        raise PlanningError('configuration_hash differs from the declared Phase 22 value; backend/app or settings changed')
    freeze = s2.check_freeze(pins, root)
    freeze['extra_files_checked'] = check_freeze_extra(root)
    pools = {SOURCE_CASE_ID: [], CONTROL_CASE_ID: []}
    rows, excluded, statements, hook_facts, configurations = {}, {}, {}, Counter(), {}
    for label in STATIC_STORES:
        found, dropped, facts, found_rows, said, found_configurations = static_pools(label, root)
        for role in pools:
            pools[role].extend(found[role])
        rows.update(found_rows)
        excluded[label] = dropped
        statements[label] = said
        hook_facts.update(facts)
        configurations.update(found_configurations)
    main_pool, dropped, main_rows, positive, said, found_configurations = main_store_inputs(store, root)
    pools[CONTROL_CASE_ID].extend(main_pool)
    rows.update(main_rows)
    excluded['main'] = dropped
    statements['main'] = said
    configurations.update(found_configurations)
    positive['auditor_validation'] = auditor_validation(root)
    positive['auditor_validation_scope'] = auditor_validation_scope(positive['auditor_validation'])
    positive['hook_reach'] = {'rule': ('on the stored source path (the upgrade-3 pool) the Actor never sent a '
                                       'confirmation and always filed a report, so after_upgrade_response and '
                                       'before_final_report are the hooks it reaches'),
                              'source_episodes': hook_facts['source_episodes'],
                              'actor_sent_confirmation': hook_facts['actor_sent_confirmation'],
                              'report_submitted': hook_facts['report_submitted']}
    spec = source_fault_spec()
    positive['source_spec'] = {'spec': spec, 'content_hash': content_hash(spec), 'is_upgrade3': is_upgrade3(spec),
                               'seed': spec.get('seed')}
    healthy = control_fault_spec()
    main_reader = open_main(store)
    try:
        stored_healthy = {canonical_json({c['case_id']: c for c in s['manifest']['cases']}[CONTROL_CASE_ID]['fault_spec'])
                          for s in phase23_studies(main_reader, root)}
    finally:
        main_reader.close()
    positive['control_spec'] = {'spec': healthy, 'no_primitives': not healthy['primitives'], 'seed': healthy.get('seed'),
                                'equals_every_phase23_manifest': stored_healthy == {canonical_json(healthy)}}
    return {'pins': pins, 'freeze': freeze, 'pools': pools, 'rows': rows, 'excluded': excluded,
            'positive': positive, 'statements': statements,
            'configurations': pool_configurations(pools, configurations)}


def pool_configurations(pools, records):
    """Descriptive, declared in the protocol (§4): each configuration the pool episodes ran on, how many episodes of
    each pool, and which fields of its stored configuration record differ from the declared configuration's record."""
    declared = records.get(DECLARED_CONFIGURATION_HASH)
    if not isinstance(declared, dict):
        raise PlanningError(f'No pool episode ran on the declared configuration {DECLARED_CONFIGURATION_HASH[:8]}; the '
                            'configuration comparison has no reference record')
    out = {}
    for configuration_hash, record in sorted(records.items()):
        if not isinstance(record, dict):
            raise PlanningError(f'No stored configuration record {configuration_hash}')
        out[configuration_hash] = {
            'episodes': {role: sum(e['configuration_hash'] == configuration_hash for e in pools[role])
                         for role in (SOURCE_CASE_ID, CONTROL_CASE_ID)},
            'episodes_by_store': dict(sorted(Counter(e['store'] for role in pools for e in pools[role]
                                                     if e['configuration_hash'] == configuration_hash).items())),
            'fields_differing_from_declared': sorted(key for key in set(record) | set(declared)
                                                     if canonical_json(record.get(key)) != canonical_json(declared.get(key)))}
    return out


def positive_controls_pass(positive):
    """Every $0 control holds. The static check's own validation needs every stored policy's row to agree AND at least
    one informative row (a policy with an orders re-send) that shows CAN_FIRE at after_upgrade_response firing; rows of
    policies without an orders re-send cannot disagree, so they are never counted as validations."""
    bundle, context = positive['bundle_rebuild'], positive['context_rebuild']
    validation = positive['auditor_validation']
    return (bundle['episodes_checked'] > 0 and bundle['equal'] == bundle['episodes_checked']
            and context['studies_checked'] > 0 and context['byte_equal_apart_from_source'] == context['studies_checked']
            and all(v['agrees'] and v['content_hash_matches'] for v in validation)
            and any(v['static_present'] and v['static_label'] == CAN_FIRE
                    and v['static_fires_at'] == 'after_upgrade_response' and v['dynamic_fired'] > 0 for v in validation)
            and positive['hook_reach']['actor_sent_confirmation'] == 0
            and positive['hook_reach']['report_submitted'] == positive['hook_reach']['source_episodes']
            and positive['source_spec']['is_upgrade3'] and positive['source_spec']['seed'] == 703
            and positive['source_spec']['content_hash'] == SOURCE_FAULT_SPEC_CONTENT_HASH
            and positive['control_spec']['no_primitives'] and positive['control_spec']['equals_every_phase23_manifest'])


def operating_characteristics():
    """P(NO_GO) with every draw delivered and independent. s is the per-draw rate of a WORKING orders re-send; the
    decision counts PRESENT ones, so P(NO_GO) = (1 - r)^30 with r the per-draw rate of a present re-send. The design's
    column (§6.0) takes r = s / 0.75 (a present step works 3 times in 4, as in Phases 17 and 23); the second column
    takes r = s (every present re-send works), the largest P(NO_GO) for a given s. Correlated draws make NO_GO more
    likely than both columns say."""
    table = []
    for s in (0.0, 0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20):
        table.append({'s': s, 'r_design': round(min(1.0, s / 0.75), 4),
                      'p_no_go_design_r_equals_s_over_0_75': round((1 - min(1.0, s / 0.75)) ** K_CONTEXTS, 4),
                      'p_no_go_if_r_equals_s': round((1 - s) ** K_CONTEXTS, 4)})
    upper = wilson(0, K_CONTEXTS)[1]
    return {'rule': operating_characteristics.__doc__.strip(), 'table': table,
            'no_go_wilson95_upper_bound': round(upper, 4)}


def readout_rules():
    return {
        'unit': ('a draw is one of the 30 planned contexts. Its output is the first response if that parses under '
                 'MechanicOutput (or is empty or unreadable: never repaired, never re-sent); otherwise the '
                 'format-repair response. Classes (Phase 25\'s classify_response): CANDIDATE (a valid policy), '
                 'NO_CHANGE, INVALID (fails MechanicOutput after the repair, empty or unreadable, a stale parent or a '
                 'CandidatePolicy failure); UNDELIVERED when the output the loop would use never arrived'),
        'not_a_loop_proposal': ('an INVALID draw whose first output was empty or unreadable, or whose repair came back '
                                'empty or unreadable or was refused by the input bound (INPUT_LIMIT, REQUEST_LIMIT). The '
                                'loop\'s Mechanic._generate raises there, so the loop would have recorded an '
                                'infrastructure death and no proposal. The probe keeps such a draw as a delivered '
                                'INVALID draw (a generation arrived and is never re-sent, pitfall 49) and every '
                                'statement names how many there were'),
        'decision': DECISION_RULE,
        'static_check': upgrade_audit.__doc__.strip(),
        'R_draw': ('CANDIDATE draws containing an orders re-send (any hook, any gate) / 30, Wilson 95% (the design\'s '
                   'R_draw; draws are correlated)'),
        'R_valid': 'the same count / CANDIDATE draws',
        'R_fire_draw': 'descriptive: CANDIDATE draws whose orders re-send the static check labels CAN_FIRE / 30',
        'R_fire_valid': 'descriptive: the same count / CANDIDATE draws',
        'descriptive': ('the static check\'s labels; where each firing re-send fires; its hook, when, only_if and the '
                        'number of orders re-send steps; CANNOT_FIRE and UNCLEAR reasons; NO_CHANGE and INVALID shares '
                        'with Wilson intervals, INVALID split by cause, and the draws that are not a loop proposal; '
                        'distinct policies (content hash); distinct policies with a present and with a firing '
                        're-send; re-draws of the four certified policies; the Phase 9 notification step '
                        '(run_full_loop.contains_step); both-sides policies; the Phase 17 attempt-4 pattern '
                        '(premature defer, s2.audit_policy); format repairs used and their results; served model and '
                        'tokens'),
        'uses': ('the decision only: GO lets the Phase 28 build start; NO_GO closes Phase 28 with this probe as its '
                 'result. No tuning, no pooling with the loop\'s S1'),
    }


def assemble_plan(inputs, *, spend_cap=HARD_SPEND_CAP, root=None):
    """The hashed plan (pure given the inputs). It holds no protocol sha and no review-record sha."""
    if not positive_controls_pass(inputs['positive']):
        raise PlanningError('A $0 positive control failed; nothing may be sent (see the dry summary)')
    requests, prompts, draws = build_requests(inputs['pools'], inputs['rows'])
    largest = max(r['input_token_bound'] for r in requests)
    if largest > MODEL_INPUT_TOKEN_LIMIT:
        raise PlanningError(f'A planned request exceeds the {MODEL_INPUT_TOKEN_LIMIT:,}-token input bound')
    check_budget(PLANNED_CALLS, spend_cap)
    root = _root(root)
    pins = inputs['pins']
    return {
        'schema_version': SCHEMA, 'experiment': 'phase28a_upgrade_mechanic_probe',
        'scoring': 'NON_SCORING_NEVER_FED_BACK', 'split': 'development', 'purpose': 'completion_study',
        'design': 'docs/part2/PHASE28_DESIGN.md §6.0 and §8.4',
        'harness_sha256': sha256_file(__file__),
        'imported': {'slot2_probe.py': PHASE25_HARNESS_SHA256, 'run_full_loop.py': PHASE17_RUNNER_SHA256},
        'source_sha256': {name: sha256_file(root / name) for name in (
            'backend/app/lab/completion_study.py', 'backend/app/lab/evidence.py', 'backend/app/lab/diagnosis.py',
            'backend/app/agents/mechanic.py', 'backend/app/agents/prompts/completion.md', 'backend/app/contracts/models.py',
            'backend/app/contracts/tokens.py', 'backend/app/providers/runtime.py', 'backend/app/lab/policy_state.py',
            'backend/app/lab/policy_interpreter.py', 'backend/app/lab/reproduction.py')},
        'settings_file': DECLARED_SETTINGS, 'settings_sha256': DECLARED_SETTINGS_SHA256,
        'configuration_hash': pins['configuration_hash'], 'mechanic_model': pins['mechanic_model'],
        'mechanic_model_settings': pins['mechanic_model_settings'], 'freeze': inputs['freeze'],
        'fingerprints': {name: pins[name] for name in s2.FREEZE_FINGERPRINTS},
        'stores': {'main': {'path': 'artifacts/lab.sqlite3', 'mode': 'read-only', 'cutoff': MAIN_STORE_CUTOFF,
                            'phase23_manifest': PHASE23_MANIFEST, 'phase23_manifest_sha256': PHASE23_MANIFEST_SHA256,
                            'configuration': PHASE23_CONFIGURATION},
                   **{label: {**entry, 'mode': 'read-only, immutable', 'purpose': STATIC_PURPOSE}
                      for label, entry in STATIC_STORES.items()},
                   'kinds_read': list(READ_KINDS), 'tables_read': ['records', 'events']},
        'source_case': {'case_id': SOURCE_CASE_ID, 'fault_spec': source_fault_spec()},
        'control_case': {'case_id': CONTROL_CASE_ID, 'fault_spec': control_fault_spec()},
        'pools': {role: sorted(inputs['pools'][role], key=lambda e: (e['store'], e['episode_id']))
                  for role in (SOURCE_CASE_ID, CONTROL_CASE_ID)},
        'pool_sizes': {role: len(inputs['pools'][role]) for role in (SOURCE_CASE_ID, CONTROL_CASE_ID)},
        'pool_sizes_by_store': {role: dict(Counter(e['store'] for e in inputs['pools'][role]))
                                for role in (SOURCE_CASE_ID, CONTROL_CASE_ID)},
        'excluded': inputs['excluded'],
        'positive_controls': inputs['positive'],
        'draws': draws,
        'declared_input_differences': [
            'every evidence row reads source "local_only" where the loop\'s read "weave_verified" (the healthy rows are '
            'rebuilt too, so the label is uniform)',
            'the six controls come from different campaigns and stores (Phase 20, Phase 26, Phase 23), not one '
            'study\'s controls, and keep their stored episode ids',
            'the upgrade-3 episodes ran under their own seeds, not 703: source_fault_spec shows seed 703, and '
            'observed_outcomes groups by scenario_hash, so the three source controls carry up to three different '
            'scenario hashes where a loop\'s share one (none equals content_hash(source_fault_spec)); the Phase 20 '
            'and 26 healthy episodes also carry their own',
            'campaign_id and study_id are declared probe values (ID_RULE), shaped like the loop\'s',
            'the Phase 20 episodes (8 upgrade-3, 3 healthy) ran on configuration 0a33aa51... (Phase 20, before the '
            'Phase 22 freeze), not 2cf63e93...; the two stored configuration records differ only in algorithm_hash and '
            'runtime_hash (pool_configurations)',
        ],
        'pool_configurations': inputs['configurations'],
        'provider_call': {'role': 'mechanic', 'model': EXPECTED_MECHANIC_MODEL, 'temperature': TEMPERATURE,
                          'max_output_tokens': MECHANIC_MAX_OUTPUT_TOKENS, 'timeout_seconds': MECHANIC_TIMEOUT_SECONDS,
                          'format_repair': ('when the first output fails MechanicOutput validation, one follow-up: the '
                                            'first messages + the output as the assistant message + '
                                            'canonical_json({validation_errors, instruction}) with _generate\'s '
                                            'instruction verbatim; its request digest is computed from the saved '
                                            'output and checked before sending. An empty first output is recorded '
                                            'as delivered and INVALID and never repaired (the loop would raise)'),
                          'empty_or_unreadable': ('an empty or unreadable output (first or repair) and a repair refused '
                                                  'by the input bound are delivered INVALID draws, never re-sent; the '
                                                  'loop would have recorded an infrastructure death there, and the '
                                                  'read-outs count them as not_a_loop_proposal'),
                          'format_repair_instruction': FORMAT_REPAIR_INSTRUCTION,
                          'blind_retry': (f'each request whose attempt failed with {list(RESEND_CODES)} and delivered no '
                                          f'generation is re-sent once, after {BLIND_RETRY_WAIT_SECONDS} s, charged; '
                                          'a delivered generation is never re-sent'),
                          'backoff_after_errored_request_seconds': list(BACKOFF_SECONDS),
                          'consecutive_errored_requests_stop': CONSECUTIVE_ERROR_ABORT,
                          'request_digest': 'content_hash of the create() keywords, checked before every send'},
        'readout_rules': readout_rules(),
        'decision_rule': DECISION_RULE,
        'relaunch_rule': RELAUNCH_RULE,
        'operating_characteristics': operating_characteristics(),
        'counts': {'contexts': len(requests), 'first_requests': len(requests), 'planned_calls': PLANNED_CALLS,
                   'largest_input_token_bound': largest, 'input_token_limit': MODEL_INPUT_TOKEN_LIMIT,
                   'repair_headroom_tokens': MODEL_INPUT_TOKEN_LIMIT - largest - MECHANIC_MAX_OUTPUT_TOKENS - 600},
        'cost': {'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                 'planned_upper_bound': round(PLANNED_CALLS * PER_REQUEST_DOLLAR_BOUND, 6),
                 'spend_cap': spend_cap, 'phase_spend_cap': HARD_SPEND_CAP,
                 'max_attempts_under_cap': SpendGuard.micro(spend_cap) // SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND)},
        'requests': requests,
    }, prompts


def build_plan(*, store=None, root=None, settings_path=None, spend_cap=HARD_SPEND_CAP):
    inputs = collect_inputs(store=store, root=root, settings_path=settings_path)
    plan, prompts = assemble_plan(inputs, spend_cap=spend_cap, root=root)
    return plan, prompts, inputs


def plan_hash(plan):
    return content_hash(plan)


def dry_summary(plan):
    positive = plan['positive_controls']
    return {'status': 'DRY_RUN', 'plan_hash': plan_hash(plan), 'harness_sha256': plan['harness_sha256'],
            'configuration_hash': plan['configuration_hash'], 'mechanic_model': plan['mechanic_model'],
            'pool_sizes': plan['pool_sizes'], 'pool_sizes_by_store': plan['pool_sizes_by_store'],
            'excluded': plan['excluded'],
            'pool_configurations': plan['pool_configurations'],
            'positive_controls': {'bundle_rebuild': {k: v for k, v in positive['bundle_rebuild'].items() if k != 'rule'},
                                  'context_rebuild': {k: v for k, v in positive['context_rebuild'].items() if k != 'rule'},
                                  'auditor_validation': positive['auditor_validation'],
                                  'auditor_validation_scope': positive['auditor_validation_scope'],
                                  'hook_reach': {k: v for k, v in positive['hook_reach'].items() if k != 'rule'},
                                  'source_spec_content_hash': positive['source_spec']['content_hash']},
            'draws': {'caps': plan['draws']['caps'], 'controls_order': plan['draws']['controls_order'],
                      'upgrade3_uses': Counter(plan['draws']['uses'][SOURCE_CASE_ID].values())},
            'counts': plan['counts'], 'cost': plan['cost'],
            'operating_characteristics': plan['operating_characteristics']['table']}


# ---------------------------------------------------------------- output, claims and the one-run rule

def _final(manifest):
    return isinstance(manifest, dict) and manifest.get('status') in FINAL_STATUSES and bool(manifest.get('ended_at'))


def _charge(manifest, path):
    charged = manifest.get('charged_upper_bound')
    if type(charged) not in (int, float) or not math.isfinite(charged) or charged < 0:
        raise PlanningError(f'An earlier live run does not state a readable charged_upper_bound ({path}); the phase '
                            'cap cannot be applied. Investigate before any run')
    return charged


def claimed_output(artifacts, out):
    parts = pathlib.PurePosixPath(out).parts if isinstance(out, str) and out else ()
    if (len(parts) != 3 or parts[0] != 'artifacts' or not parts[1].startswith(PHASE_PREFIX) or parts[1] == CLAIM_DIR
            or any(part in ('', '.', '..') for part in parts)):
        return None
    return pathlib.Path(artifacts).parent / parts[0] / parts[1] / parts[2]


def live_run_records(artifacts):
    """Every earlier Phase 28a live run, checked; refuses unless each one is final and delivered nothing."""
    artifacts = pathlib.Path(artifacts)
    manifests = {path.resolve(): path for path in artifacts.glob(LIVE_MANIFEST_GLOB)}
    numbers = []
    for claim in sorted((artifacts / CLAIM_DIR).glob('claim-*.json')):
        match = CLAIM_NAME.fullmatch(claim.name)
        if match:
            numbers.append(int(match.group(1)))
        try:
            record = json.loads(claim.read_text())
        except (OSError, ValueError):
            record = None
        output = claimed_output(artifacts, record.get('out')) if isinstance(record, dict) else None
        if output is None:
            raise PlanningError(f'{claim.name} cannot be read or names no valid output directory; investigate before '
                                'any run')
        manifest = output / MANIFEST_NAME
        if not manifest.is_file():
            raise PlanningError(f'{claim.name} claims a live run with no manifest. If its process is gone, close it at '
                                f'$0 with --finalize-abandoned artifacts/{CLAIM_DIR}/{claim.name}')
        manifests.setdefault(manifest.resolve(), manifest)
    undelivered = []
    for _, path in sorted(manifests.items()):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError):
            raise PlanningError(f'An earlier live manifest cannot be read ({path}); investigate before any run') from None
        if not _final(manifest):
            raise PlanningError(f'An earlier live run is not final ({path}); it may still be running. If its process is '
                                'gone, close its claim at $0 with --finalize-abandoned')
        delivered = delivered_generations(manifest)
        if delivered is None or delivered > 0:
            raise PlanningError(f'A live Phase 28a run already exists ({path}); a second draw would be repeat-until-'
                                'lucky. Completing undelivered draws needs the owner\'s approval and its own reviewed '
                                'step')
        undelivered.append({'manifest': str(path.relative_to(artifacts.parent)), 'charged_upper_bound': _charge(manifest, path)})
    return {'undelivered': undelivered, 'claim_numbers': sorted(numbers)}


def earlier_live_runs(artifacts):
    return live_run_records(artifacts)['undelivered']


def phase_spend_remaining(earlier):
    used = sum(SpendGuard.micro(run['charged_upper_bound']) for run in earlier)
    return (SpendGuard.micro(HARD_SPEND_CAP) - used) / 1_000_000


def effective_spend_cap(requested, earlier):
    if not (type(requested) in (int, float) and math.isfinite(requested) and 0 < requested <= HARD_SPEND_CAP):
        raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    remaining = phase_spend_remaining(earlier)
    if remaining <= 0:
        raise PlanningError(f'Earlier runs that delivered nothing already charged the ${HARD_SPEND_CAP:.2f} phase cap')
    return min(requested, remaining)


def check_output(out, *, root=None, live=True):
    """A new directory exactly artifacts/phase28a-<date>/<name>, never an existing one."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    out = pathlib.Path(out)
    out = (out if out.is_absolute() else root / out).resolve()
    try:
        relative = out.relative_to(artifacts)
    except ValueError:
        raise PlanningError(f'The output directory must be under artifacts/{PHASE_PREFIX}<date>/') from None
    if len(relative.parts) != 2 or not relative.parts[0].startswith(PHASE_PREFIX) or relative.parts[0] == CLAIM_DIR:
        raise PlanningError(f'The output directory must be exactly artifacts/{PHASE_PREFIX}<date>/<name>')
    if out.exists():
        raise PlanningError(f'{out} exists; a run is never resumed or overwritten - use a new directory')
    if live:
        earlier_live_runs(artifacts)
    return out


def take_claim(out, plan_hash_value, harness, *, root=None, spend_cap=None, expected_earlier=None,
               relaunch_approval=None):
    """Atomically claim the next live run (private file, then hard link; fails if the name exists). Never deleted.
    `expected_earlier` must still equal the earlier runs, which also binds a relaunch approval to this one claim."""
    artifacts = (_root(root) / 'artifacts').resolve()
    records = live_run_records(artifacts)
    earlier = records['undelivered']
    if expected_earlier is not None and earlier != expected_earlier:
        raise PlanningError('The earlier live runs changed during the launch checks; nothing was claimed. Re-launch')
    directory = artifacts / CLAIM_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'claim-{max(records["claim_numbers"], default=0) + 1:02d}.json'
    temporary = directory / f'.{path.name}.{os.getpid()}.tmp'
    try:
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump({'claim': path.name, 'pid': os.getpid(), 'out': str(out.relative_to(artifacts.parent)),
                       'plan_hash': plan_hash_value, 'harness_sha256': harness, 'spend_cap': spend_cap,
                       'claimed_at': datetime.now(timezone.utc).isoformat(), 'earlier_undelivered_runs': earlier,
                       'relaunch_approval': relaunch_approval},
                      handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise PlanningError(f'{path.name} is already taken: another live launch claimed this run first') from None
    finally:
        temporary.unlink(missing_ok=True)
    return path, earlier


def claim_process_alive(pid):
    """False only when the claim's process is gone (or the pid now runs something else)."""
    if type(pid) is not int or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    try:
        command = subprocess.run(['ps', '-ww', '-o', 'command=', '-p', str(pid)], capture_output=True, text=True,
                                 timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return True
    return not command.strip() or 'upgrade_mechanic_probe' in command


def finalize_abandoned(claim, *, root=None, alive=None):
    """Close, at $0, a claimed run whose process died before its manifest became final. Charges every recorded
    attempt, plus ABANDONED_IN_FLIGHT_ATTEMPTS when the run died while RUNNING. A trailing response line cut off by the
    hard stop counts as a delivered generation (review round 3, finding 1)."""
    alive = claim_process_alive if alive is None else alive
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    path = pathlib.Path(claim)
    path = (path if path.is_absolute() else root / path).resolve()
    if path.parent != artifacts / CLAIM_DIR or not CLAIM_NAME.fullmatch(path.name):
        raise PlanningError(f'--finalize-abandoned takes a claim file in artifacts/{CLAIM_DIR}/')
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        raise PlanningError(f'{path.name} cannot be read') from None
    output = claimed_output(artifacts, record.get('out')) if isinstance(record, dict) else None
    if output is None:
        raise PlanningError(f'{path.name} names no valid output directory; investigate by hand')
    pid = record.get('pid')
    if alive(pid):
        raise PlanningError(f'The process that took {path.name} (pid {pid}) may still be running; nothing was changed')
    manifest_path = output / MANIFEST_NAME
    existing = None
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
        except (OSError, ValueError):
            existing = None
        if not isinstance(existing, dict):
            raise PlanningError(f'{manifest_path} cannot be read; inspect it by hand')
        if _final(existing):
            raise PlanningError(f'{manifest_path} is already final; there is nothing to finalize')
    responses = output / 'responses.jsonl'
    results, partial = load_results(responses) if responses.exists() else ([], 0)
    previous_status = existing.get('status') if existing else None
    in_flight = 0 if previous_status in (None, 'STARTING') else ABANDONED_IN_FLIGHT_ATTEMPTS
    recorded = sum(len(r.get('attempts') or []) if isinstance(r, dict) else 2 for r in results)
    prior_attempts = existing.get('attempts') if existing else 0
    attempts = max(prior_attempts if type(prior_attempts) is int else 0, recorded) + in_flight
    prior = delivered_generations(existing) if existing else 0
    # Review round 3, finding 1: a line cut off by the hard stop may hold part of the Mechanic's output, so it counts
    # as delivered. The one-run rule reads only this count, so it then refuses a second draw, as the read-outs'
    # any_generation_arrived already says (a skipped partial line counts there too).
    delivered = sum(entry_delivered(r) for r in results) + partial
    now = datetime.now(timezone.utc).isoformat()
    manifest = dict(existing) if existing else {
        'schema_version': SCHEMA, 'mode': 'live', 'plan_hash': record.get('plan_hash'),
        'harness_sha256': record.get('harness_sha256'), 'claim': str(path.relative_to(artifacts.parent)), 'pid': pid,
        'spend_cap': record.get('spend_cap'), 'started_at': None, 'traceback': None}
    manifest.update({
        'status': 'ABORTED', 'stop_reason': 'abandoned', 'ended_at': now,
        'statuses': dict(sorted(Counter(str(r.get('status')) if isinstance(r, dict) else 'unreadable'
                                        for r in results).items())),
        'generations_delivered': None if prior is None else max(prior, delivered), 'attempts': attempts,
        'charged_upper_bound': attempts * SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND) / 1_000_000,
        'finalized_abandoned': {'at': now, 'claim': str(path.relative_to(artifacts.parent)), 'pid': pid,
                                'previous_status': previous_status, 'responses_lines': len(results),
                                'partial_lines_skipped': partial, 'unrecorded_in_flight_attempts_charged': in_flight}})
    output.mkdir(parents=True, exist_ok=True)
    write_json(manifest_path, manifest)
    return manifest_path, manifest


# ---------------------------------------------------------------- one paid run at a time

def _manifest_final_marker(manifest):
    if not isinstance(manifest, dict) or not manifest.get('ended_at'):
        return False
    return all(str(manifest.get(key, '')).lower() not in ('running', 'starting') for key in ('status', 'stop_reason'))


def _is_run_manifest(record):
    return isinstance(record, dict) and 'started_at' in record


def other_run_files(*, root=None, ignore=()):
    """Other phases' run records that may still be running (Phase 30's rule): a run manifest (a JSON object with
    started_at) without its end marker, an unreadable *manifest*.json, or a launch claim whose run directory holds no
    finished run manifest. Only directories matching OTHER_RUN_DIR are read (never Phase 22 or 24)."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    ignored = {(pathlib.Path(p) if pathlib.Path(p).is_absolute() else root / p).resolve() for p in ignore or ()}
    active = []
    if not artifacts.is_dir():
        return active
    directories = sorted(d for d in artifacts.iterdir() if d.is_dir())
    for directory in directories:
        if not OTHER_RUN_DIR.fullmatch(directory.name) or OTHER_CLAIM_DIR.fullmatch(directory.name):
            continue
        for path in sorted(directory.glob('**/*manifest*.json')):
            if path.resolve() in ignored:
                continue
            try:
                record = json.loads(path.read_text())
            except (OSError, ValueError):
                active.append(str(path.relative_to(root)))
                continue
            if _is_run_manifest(record) and not _manifest_final_marker(record):
                active.append(str(path.relative_to(root)))
    for directory in directories:
        if not OTHER_CLAIM_DIR.fullmatch(directory.name):
            continue
        for claim in sorted(directory.glob('claim-*.json')):
            if claim.resolve() in ignored:
                continue
            try:
                record = json.loads(claim.read_text())
                if not (isinstance(record, dict) and isinstance(record.get('out'), str)
                        and OTHER_CLAIMED_RUN.fullmatch(record['out'])
                        and not any(part in ('.', '..') for part in pathlib.PurePosixPath(record['out']).parts)):
                    raise ValueError('not a run directory of a listed phase')
                out = (root / record['out']).resolve()
                finished = False
                for path in out.glob('*manifest*.json'):
                    manifest = json.loads(path.read_text())
                    finished = finished or (_is_run_manifest(manifest) and _manifest_final_marker(manifest))
            except (OSError, ValueError, KeyError, TypeError):
                finished = False
            if not finished:
                active.append(str(claim.relative_to(root)))
    return active


def experiment_processes():
    """Other --execute-live experiment processes by Phase 25's token rule (this process, its ancestors and its
    descendants, such as its own caffeinate helper, are excluded). The process list is read at call time."""
    return s2.live_experiment_processes(reader=process_list)


def other_paid_runs(*, root=None, ignore=(), status=None, processes=None):
    """Every reason to believe another paid run may be in progress: other phases' open run records, other
    --execute-live experiment processes (Phase 25's token rule; never set aside by --ignore-manifest) and the lab
    backend's active campaign. Empty means none was found."""
    blockers = other_run_files(root=root, ignore=ignore)
    blockers += list(experiment_processes() if processes is None else processes)
    state, detail = (status or backend_status)()
    if state == 'active':
        blockers.append(f'the lab backend reports an active campaign ({detail})')
    elif state == 'unknown':
        blockers.append(f'the lab backend status could not be read ({detail}); check it by hand')
    return blockers, state


def check_other_paid_runs(args, *, root=None, status=None, processes=None):
    blockers, state = other_paid_runs(root=root, ignore=getattr(args, 'ignore_manifest', None) or (), status=status,
                                      processes=processes)
    if blockers:
        more = f' (and {len(blockers) - 1} more: {"; ".join(blockers[1:4])})' if len(blockers) > 1 else ''
        raise PlanningError(f'One paid run at a time: {blockers[0]}{more}. A process or the backend cannot be set aside; '
                            'a crashed run\'s manifest or claim can, by its exact path in --ignore-manifest')
    return state


# ---------------------------------------------------------------- the review gate

def check_review(protocol_text, protocol_sha256, harness, plan_hash_value, *, root=None):
    if REVIEW_PENDING_MARKER.lower() in status_block(protocol_text).lower():
        raise PlanningError(f'The protocol status still says "{REVIEW_PENDING_MARKER}"; live execution refuses')
    expected_line = REVIEWED_LINE.format(harness=harness, plan=plan_hash_value)
    if not any(line.strip() == expected_line for line in protocol_text.splitlines()):
        raise PlanningError('The protocol has no bare "Reviewed for launch" line (no backticks, list marker or bold) '
                            'naming this harness sha256 and plan hash')
    path = _root(root) / REVIEW_RECORD
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable review record at {REVIEW_RECORD}; live execution refuses') from None
    expected = {'protocol_sha256': protocol_sha256, 'harness_sha256': harness, 'plan_hash': plan_hash_value,
                'configuration_hash': DECLARED_CONFIGURATION_HASH}
    if not isinstance(record, dict) or any(record.get(key) != value for key, value in expected.items()):
        raise PlanningError('The review record does not name this protocol sha256, harness sha256, plan hash and '
                            'configuration hash')
    if record.get('status') != REVIEW_APPROVED_STATUS:
        raise PlanningError('The review record does not say status "approved"; live execution refuses')
    if not (isinstance(record.get('approved_by'), str) and record['approved_by'].strip()):
        raise PlanningError('The review record names no approver (approved_by); live execution refuses')
    cap = record.get('phase_cap')
    if type(cap) not in (int, float) or not math.isfinite(cap) or SpendGuard.micro(cap) != SpendGuard.micro(HARD_SPEND_CAP):
        raise PlanningError(f"The review record does not name this harness's phase cap ({HARD_SPEND_CAP:.2f}) as "
                            'phase_cap; live execution refuses')
    return record


def check_relaunch_approval(path, earlier, out, plan_hash_value, harness, *, root=None):
    """RELAUNCH_RULE (review round 2, finding 2, option b): design §6.0 makes completing an INCOMPLETE run the owner's
    decision. `earlier` is earlier_live_runs(): runs that are final and delivered nothing. With none, no approval may
    be passed. With some, the owner's record must name exactly this launch; returns its path and sha256."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    if not earlier:
        if path:
            raise PlanningError('--relaunch-approval is only for a launch after earlier Phase 28a runs that delivered '
                                'nothing, and there is none; launch without it')
        return None
    listed = json.dumps(earlier)
    out_relative = str(pathlib.Path(out).relative_to(artifacts.parent))
    if not path:
        raise PlanningError('Earlier Phase 28a runs ended having delivered nothing, so the phase is INCOMPLETE. Another '
                            'launch sends the 30 missing draws, which needs the owner\'s approval (design §6.0): pass '
                            f'--relaunch-approval artifacts/{PHASE_PREFIX}<date>/relaunch-approval-NN.json, a record with '
                            f'status "approved", approved_by, approved_at, earlier_undelivered_runs {listed}, out '
                            f'"{out_relative}", plan_hash and harness_sha256')
    resolved = pathlib.Path(path)
    resolved = (resolved if resolved.is_absolute() else root / resolved).resolve()
    try:
        relative = resolved.relative_to(artifacts)
    except ValueError:
        relative = None
    if (relative is None or len(relative.parts) != 2 or not relative.parts[0].startswith(PHASE_PREFIX)
            or relative.parts[0] == CLAIM_DIR or not RELAUNCH_APPROVAL_NAME.fullmatch(relative.parts[1])):
        raise PlanningError(f'--relaunch-approval must name artifacts/{PHASE_PREFIX}<date>/relaunch-approval-NN.json')
    try:
        record = json.loads(resolved.read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable relaunch approval at {relative}; live execution refuses') from None
    expected = {'earlier_undelivered_runs': earlier, 'out': out_relative, 'plan_hash': plan_hash_value,
                'harness_sha256': harness}
    if not isinstance(record, dict) or any(record.get(key) != value for key, value in expected.items()):
        raise PlanningError('The relaunch approval does not name exactly this launch: earlier_undelivered_runs '
                            f'{listed}, out "{out_relative}", this plan hash and this harness sha256. One record admits '
                            'one launch')
    if record.get('status') != REVIEW_APPROVED_STATUS:
        raise PlanningError('The relaunch approval does not say status "approved"; live execution refuses')
    for key in ('approved_by', 'approved_at'):
        if not (isinstance(record.get(key), str) and record[key].strip()):
            raise PlanningError(f'The relaunch approval names no {key}; live execution refuses')
    return {'path': str(resolved.relative_to(artifacts.parent)), 'sha256': sha256_file(resolved),
            'approved_by': record['approved_by'], 'approved_at': record['approved_at']}


# ---------------------------------------------------------------- the draw's requests (pure)

def validation_errors(raw):
    """Mechanic._generate's check: [] when the output validates under MechanicOutput, else its error list."""
    try:
        TypeAdapter(MechanicOutput).validate_json(raw)
        return []
    except ValidationError as error:
        return [{'location': list(issue['loc']), 'type': issue['type']}
                for issue in error.errors(include_input=False, include_context=False, include_url=False)]


def repair_messages(messages, raw, errors):
    """Mechanic._generate's format-repair follow-up, exactly."""
    return list(messages) + [{'role': 'assistant', 'content': raw},
                             {'role': 'user', 'content': canonical_json({'validation_errors': errors,
                                                                         'instruction': FORMAT_REPAIR_INSTRUCTION})}]


# ---------------------------------------------------------------- live execution

def openai_client_factory(**kwargs):
    """The provider client RuntimeProvider would build itself (read at call time; tests replace it)."""
    from openai import AsyncOpenAI
    return AsyncOpenAI(**kwargs)


class Recorder(s2.Recorder):
    """Phase 25's recorder (fsynced response lines, scrubbed secrets), writing this probe's manifest."""

    def save(self):
        path = self.out / MANIFEST_NAME
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(self.scrub(json.dumps(self.manifest, indent=2, ensure_ascii=False)) + '\n')
        os.replace(temporary, path)


async def run_draws(requests, prompts, provider, guard, recorder, *, sender=None, stop=lambda: False,
                    sleep=asyncio.sleep, backoff=BACKOFF_SECONDS, retry_wait=BLIND_RETRY_WAIT_SECONDS):
    """Send each planned first request in order and, when its output fails MechanicOutput validation, its one format
    repair. Each request whose attempt failed at transport with nothing delivered is re-sent once (blind, charged).
    A delivered generation is never re-sent. Returns the stop reason. Each line is written and flushed before anything
    else can fail; a line carries no classification."""
    manifest = recorder.manifest
    for key, value in (('requests_done', 0), ('repairs_sent', 0), ('statuses', {}), ('measured_input_tokens', 0),
                       ('measured_output_tokens', 0), ('generations_delivered', 0), ('backoff_waits', []),
                       ('in_flight_request', None), ('last_request', None)):
        manifest.setdefault(key, value)

    async def pause(seconds):
        remaining = float(seconds)
        while remaining > 0 and not stop():
            step = min(1.0, remaining)
            await sleep(step)
            remaining -= step

    async def send(request, kind, messages, request_hash):
        manifest['in_flight_request'] = {'request_id': request['request_id'], 'kind': kind}
        entry = {'request_id': request['request_id'], 'kind': kind, 'context': request['context'],
                 'request_hash': request_hash, 'attempts': [], 'status': 'error', 'raw': None}
        if kind == 'first':
            entry['messages_hash'] = request['messages_hash']
        generation, refused, delivered = None, False, False
        for attempt in (1, 2):
            if attempt == 2:
                await pause(retry_wait)
                if stop():
                    break
            if not guard.admit():
                refused = True
                break
            if sender is not None:
                sender.arm(request_hash, TEMPERATURE)
            started = datetime.now(timezone.utc).isoformat()
            try:
                generation = await provider.complete(messages, role='mechanic',
                                                     max_output_tokens=MECHANIC_MAX_OUTPUT_TOKENS,
                                                     timeout_seconds=MECHANIC_TIMEOUT_SECONDS)
                entry['attempts'].append({'attempt': attempt, 'started_at': started, 'error': None,
                                          'served': sender.take() if sender is not None else None})
                break
            except RuntimeProviderError as error:
                delivered = delivered or error.generation is not None
                entry['attempts'].append({'attempt': attempt, 'started_at': started, **error.diagnostics,
                                          'served': sender.take() if sender is not None else None})
                if sender is not None and sender.mismatch:
                    break
                if error.code == 'EMPTY_FINAL_RESPONSE':
                    entry['status'] = 'empty_response'
                    break
                if (attempt == 1 and error.code in RESEND_CODES and error.generation is None
                        and not entry_delivered({'status': 'error', 'attempts': [entry['attempts'][-1]]})):
                    continue
                break
        manifest['attempts'] = guard.attempts
        manifest['charged_upper_bound'] = guard.charged
        if generation is not None or delivered or entry_delivered(entry):
            manifest['generations_delivered'] += 1
        if generation is not None:
            entry.update(status='ok', raw=generation.content, requested_model=generation.model_id,
                         input_tokens=generation.input_tokens, output_tokens=generation.output_tokens)
        served_last = (entry['attempts'][-1].get('served') if entry['attempts'] else None) or {}
        entry['served_model'] = served_last.get('model')
        entry['system_fingerprint'] = served_last.get('system_fingerprint')
        if sender is not None and sender.mismatch:
            entry['request_mismatch'] = sender.mismatch
        if entry['attempts']:
            recorder.record(entry)
            manifest['statuses'][entry['status']] = manifest['statuses'].get(entry['status'], 0) + 1
            if entry['status'] == 'ok':
                manifest['measured_input_tokens'] += entry.get('input_tokens') or 0
                manifest['measured_output_tokens'] += entry.get('output_tokens') or 0
        manifest['in_flight_request'] = None
        manifest['last_request'] = {'request_id': request['request_id'], 'kind': kind}
        recorder.save()
        if sender is not None and sender.mismatch:
            raise PlanningError(f'Request mismatch at {request["request_id"]} ({kind}): {sender.mismatch}; nothing was '
                                'sent for it and the run stops')
        return entry, refused

    consecutive_errors = 0
    for request in requests:
        if stop():
            return 'operator_stop'
        messages = prompts[request['messages_hash']]['messages']
        entry, refused = await send(request, 'first', messages, request['request_hash'])
        manifest['requests_done'] += bool(entry['attempts'])
        if refused:
            return 'spend_guard'
        errored = entry['status'] == 'error'
        if entry['status'] == 'ok':
            errors = validation_errors(entry['raw'])
            if errors:
                if stop():
                    return 'operator_stop'
                follow_up = repair_messages(messages, entry['raw'], errors)
                repair, refused = await send(request, 'repair', follow_up,
                                             s2.request_digest(s2.request_body(follow_up, TEMPERATURE)))
                manifest['repairs_sent'] += bool(repair['attempts'])
                if refused:
                    return 'spend_guard'
                errored = repair['status'] == 'error'
        consecutive_errors = consecutive_errors + 1 if errored else 0
        if consecutive_errors >= CONSECUTIVE_ERROR_ABORT:
            return 'consecutive_errors'
        if consecutive_errors:
            wait = backoff[min(consecutive_errors, len(backoff)) - 1]
            manifest['backoff_waits'].append({'after_request': request['request_id'], 'seconds': wait,
                                              'consecutive_errors': consecutive_errors})
            recorder.save()
            await pause(wait)
    return 'completed'


def run_live(args, plan, prompts, *, sleep=asyncio.sleep, status=None, processes=None):
    out = check_output(args.out)
    check_other_paid_runs(args, status=status, processes=processes)
    problem = pinned_imports_problem()
    if problem:
        raise PlanningError(problem)
    harness = sha256_file(__file__)
    if args.expect_harness_sha256 != harness:
        raise PlanningError('--expect-harness-sha256 does not match this script')
    if not PROTOCOL.exists():
        raise PlanningError('No protocol at docs/part2/PHASE28A_EXPERIMENT.md; live execution refuses')
    protocol_sha256 = sha256_file(PROTOCOL)
    if args.expect_protocol_sha256 != protocol_sha256:
        raise PlanningError('--expect-protocol-sha256 does not match the protocol file')
    if args.expect_plan_hash != plan_hash(plan):
        raise PlanningError('The recomputed plan differs from the reviewed dry plan (--expect-plan-hash)')
    protocol_text = PROTOCOL.read_text()
    if harness not in protocol_text or plan_hash(plan) not in protocol_text:
        raise PlanningError('The protocol does not declare this harness sha256 and this plan hash')
    review = check_review(protocol_text, protocol_sha256, harness, plan_hash(plan))
    for request in plan['requests']:
        prompt = prompts.get(request['messages_hash'])
        if (prompt is None or content_hash(prompt['messages']) != request['messages_hash']
                or s2.request_digest(s2.request_body(prompt['messages'], TEMPERATURE)) != request['request_hash']):
            raise PlanningError(f'{request["request_id"]} has no verified prompt matching the plan; nothing may be sent')
    artifacts = (_root() / 'artifacts').resolve()
    earlier = earlier_live_runs(artifacts)
    relaunch = check_relaunch_approval(getattr(args, 'relaunch_approval', None), earlier, out, plan_hash(plan), harness)
    spend_cap = effective_spend_cap(args.spend_cap, earlier)
    check_budget(PLANNED_CALLS, spend_cap)
    guard = SpendGuard(spend_cap)
    # The only credential read, after every offline check: the runtime's own loader.
    settings = settings_from_file(ROOT / DECLARED_SETTINGS, env_path=None)
    settings.require_wandb(require_model=True)
    if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
        raise PlanningError('--confirm-entity must match WANDB_ENTITY in the settings file')
    if settings.project_path != EXPECTED_PROJECT:
        raise PlanningError('Settings project is not the declared one')
    pins = configuration_pins(settings)
    check_pins(pins)
    if pins['configuration_hash'] != DECLARED_CONFIGURATION_HASH:
        raise PlanningError('configuration_hash differs from the declared pin')
    if settings.model_for_role('mechanic') != EXPECTED_MECHANIC_MODEL:
        raise PlanningError('The Mechanic role does not resolve to the declared model')
    backend_state = check_other_paid_runs(args, status=status, processes=processes)
    stop_requested = False
    recorder = None
    signal_state = {'manifest': None, 'first': None, 'count': 0}

    def request_stop(signum=None, _frame=None):
        nonlocal stop_requested
        stop_requested = True
        signal_state['count'] += 1
        running = signal_state['manifest'] or {}
        if signal_state['first'] is None:
            signal_state['first'] = {
                'signal': signal.Signals(signum).name if signum in tuple(signal.Signals) else str(signum),
                'received_at': datetime.now(timezone.utc).isoformat(), 'status_at_arrival': running.get('status'),
                'requests_done_at_arrival': running.get('requests_done')}

    async def execute():
        from app.providers.runtime import RuntimeProvider
        sender = s2.RequestSender(base=openai_client_factory)
        async with RuntimeProvider(settings, live_authorized=True, client_factory=sender) as provider:
            return await run_draws(plan['requests'], prompts, provider, guard, recorder, sender=sender,
                                   stop=lambda: stop_requested, sleep=sleep)

    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if stop_requested:
            raise PlanningError('An operator stop arrived before the claim; nothing was claimed or sent')
        if out.exists():
            raise PlanningError(f'{out} appeared during the launch checks; nothing was claimed or sent')
        claim, earlier = take_claim(out, plan_hash(plan), harness, spend_cap=spend_cap, expected_earlier=earlier,
                                    relaunch_approval=relaunch)
        out.mkdir(parents=True, exist_ok=False)
        manifest = {'schema_version': SCHEMA, 'mode': 'live', 'status': 'STARTING', 'pid': os.getpid(),
                    'plan_hash': plan_hash(plan), 'harness_sha256': harness, 'protocol_sha256': protocol_sha256,
                    'configuration_hash': pins['configuration_hash'], 'settings_sha256': DECLARED_SETTINGS_SHA256,
                    'mechanic_model': pins['mechanic_model'], 'spend_cap': spend_cap,
                    'spend_cap_requested': args.spend_cap, 'phase_spend_cap': HARD_SPEND_CAP,
                    'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                    'imported': {'slot2_probe.py': PHASE25_HARNESS_SHA256, 'run_full_loop.py': PHASE17_RUNNER_SHA256},
                    'review': {key: review.get(key) for key in ('status', 'approved_by', 'approved_at')},
                    'claim': str(claim.relative_to(artifacts.parent)), 'earlier_undelivered_runs': earlier,
                    'relaunch_approval': relaunch, 'backend_state_at_launch': backend_state,
                    'ignored_manifests': list(getattr(args, 'ignore_manifest', None) or ()),
                    'requests_planned': len(plan['requests']), 'requests_done': 0, 'repairs_sent': 0, 'attempts': 0,
                    'charged_upper_bound': 0.0, 'statuses': {}, 'generations_delivered': 0,
                    'measured_input_tokens': 0, 'measured_output_tokens': 0, 'backoff_waits': [],
                    'in_flight_request': None, 'last_request': None, 'stop_signal': None, 'stop_signals_received': 0,
                    'stop_reason': None, 'traceback': None,
                    'started_at': datetime.now(timezone.utc).isoformat(), 'ended_at': None}
        signal_state['manifest'] = manifest
        recorder = Recorder(out, manifest, secrets=(settings.wandb_api_key, settings.typesafe_api_key))
        try:
            recorder.save()
            late, _ = other_paid_runs(ignore=getattr(args, 'ignore_manifest', None) or (), status=status,
                                      processes=processes)
            if late:
                manifest.update(status='ABORTED', stop_reason=OTHER_RUN_AFTER_CLAIM, blockers_after_claim=late)
            else:
                write_json(out / 'plan.json', plan)
                with (out / 'prompts.jsonl').open('w', encoding='utf-8') as handle:
                    for messages_hash in sorted(prompts):
                        handle.write(json.dumps(prompts[messages_hash], sort_keys=True, ensure_ascii=False) + '\n')
                manifest['status'] = 'RUNNING'
                recorder.save()
                manifest['stop_reason'] = asyncio.run(execute())
                manifest['status'] = 'COMPLETED' if manifest['stop_reason'] == 'completed' else 'STOPPED'
        except Exception as error:  # noqa: BLE001 - recorded with its traceback, never silently dropped
            manifest.update(status='ABORTED', stop_reason=type(error).__name__,
                            traceback=recorder.scrub(traceback.format_exc()[-8000:]))
        except BaseException as error:
            # A cancellation or an exit that escapes the run (review round 1): the manifest is made final (ABORTED,
            # with the traceback) so an ended run is never left RUNNING, then the exception goes on. The finally block
            # charges every attempt the guard admitted, including one in flight (round 2, finding 1).
            manifest.update(status='ABORTED', stop_reason=type(error).__name__,
                            traceback=recorder.scrub(traceback.format_exc()[-8000:]))
            raise
        finally:
            # Charge every attempt the guard admitted (review round 2, finding 1). send() copies the guard's count
            # only after provider.complete returns, so an exception that escapes while a request is in flight (the
            # cancellation RuntimeProvider re-raises from inside the call) would otherwise leave that sent attempt,
            # and a blind re-send's errored first attempt, uncharged in a manifest that is already final.
            manifest['unrecorded_attempts_charged'] = max(0, guard.attempts - (manifest.get('attempts') or 0))
            manifest['attempts'] = max(manifest.get('attempts') or 0, guard.attempts)
            manifest['charged_upper_bound'] = guard.charged
            manifest['stop_signal'] = signal_state['first']
            manifest['stop_signals_received'] = signal_state['count']
            manifest['ended_at'] = datetime.now(timezone.utc).isoformat()
            recorder.save()
            recorder.close()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    summary = {'status': manifest['status'], 'stop_reason': manifest['stop_reason'],
               'requests_done': manifest['requests_done'], 'attempts': manifest['attempts'],
               'generations_delivered': manifest['generations_delivered'],
               'charged_upper_bound': manifest['charged_upper_bound'], 'output': str(out)}
    if manifest['stop_reason'] == OTHER_RUN_AFTER_CLAIM:
        summary['blockers_after_claim'] = manifest['blockers_after_claim']
        print(json.dumps(summary, indent=2))
        return 1
    try:
        results, partial = load_results(out / 'responses.jsonl') if (out / 'responses.jsonl').exists() else ([], 0)
        readouts = compute_readouts(plan['requests'], prompts, results, partial_lines_skipped=partial,
                                    manifest_delivered=delivered_generations(manifest))
    except Exception as error:  # noqa: BLE001 - the run is already final; --readouts can recompute at $0
        summary['readouts_error'] = type(error).__name__
        print(json.dumps(summary, indent=2))
        return 1
    write_json(out / 'readouts.json', readouts)
    summary.update(decision=readouts['decision'], statement=readouts['statement'])
    print(json.dumps(summary, indent=2))
    return 0 if manifest['status'] == 'COMPLETED' else 1


# ---------------------------------------------------------------- read-outs (pure)

def _lines_by_request(results):
    lines = defaultdict(lambda: {'first': [], 'repair': []})
    for result in results:
        if isinstance(result, dict) and result.get('request_id') and result.get('kind') in ('first', 'repair'):
            lines[result['request_id']][result['kind']].append(result)
    return lines


def _pick(found):
    received = [line for line in found if line.get('status') in RECEIVED]
    return received[0] if received else (found[-1] if found else None)


def classify_draw(request, prompt, lines):
    """One draw's final output, chosen as the loop would, and its classification. `not_a_loop_proposal` names the
    delivered INVALID draws where the loop's Mechanic._generate would have raised (an infrastructure death, no
    proposal): an empty or unreadable first output, or a repair that came back empty or unreadable or that the input
    bound refused."""
    first, repair = _pick(lines['first']), _pick(lines['repair'])
    out = {'request_id': request['request_id'], 'context': request['context'], 'repaired': False,
           'repair_status': None, 'final_raw': None, 'class': 'UNDELIVERED', 'integrity': [], 'c': None,
           'not_a_loop_proposal': None}
    if first is None:
        out['undelivered'] = 'first'
        return out
    if first.get('status') not in RECEIVED:
        # A generation that arrived but could not be read is delivered: never re-sent, and the loop gets no policy.
        if not entry_delivered(first):
            out['undelivered'] = 'first'
            return out
        out['final_raw'] = ''
        out['delivered_unreadable'] = 'first'
        out['not_a_loop_proposal'] = 'first_unreadable'
    elif first.get('status') == 'empty_response':
        out['final_raw'] = ''
        out['not_a_loop_proposal'] = 'first_empty'
    else:
        raw = first.get('raw') or ''
        errors = validation_errors(raw)
        if not errors:
            out['final_raw'] = raw
            if lines['repair']:
                out['integrity'].append('a repair was sent for a first output that validates')
        else:
            out['repaired'] = True
            if prompt is not None:
                expected = s2.request_digest(s2.request_body(repair_messages(prompt['messages'], raw, errors), TEMPERATURE))
                if any(line.get('request_hash') != expected for line in lines['repair']):
                    out['integrity'].append('a repair line does not carry the digest of the declared repair request')
            if repair is None:
                out['undelivered'] = 'repair'
                return out
            out['repair_status'] = repair.get('status')
            limited = any(a.get('code') in ('INPUT_LIMIT', 'REQUEST_LIMIT')
                          for a in repair.get('attempts') or [] if isinstance(a, dict))
            if repair.get('status') == 'ok':
                out['final_raw'] = repair.get('raw') or ''
            elif repair.get('status') == 'empty_response':
                out['final_raw'] = ''
                out['not_a_loop_proposal'] = 'repair_empty'
            elif entry_delivered(repair) or limited:
                out['final_raw'] = ''
                out['not_a_loop_proposal'] = 'repair_unreadable' if entry_delivered(repair) else 'repair_input_limit'
            else:
                out['undelivered'] = 'repair'
                return out
    classified = s2.classify_response(out['final_raw'], {})
    out['c'] = classified
    out['class'] = 'INVALID' if classified['class'] in ('INVALID', 'STALE_PARENT') else classified['class']
    out['subclass'] = classified['class']
    if classified['class'] == 'CANDIDATE':
        parsed = s2.parse_policy(out['final_raw'])
        content = parsed.candidate.model_dump(mode='json') if isinstance(parsed, MechanicCandidate) else {}
        out['upgrade'] = upgrade_audit(content)
        out['notification'] = classified['audit']
        out['phase9_step'] = rfl.contains_step(content)
        out['policy_hash'] = classified['policy_hash']
    return out


def decide(draws, planned=K_CONTEXTS):
    """DECISION_RULE: the design's "present" predicate. The static check's label never decides."""
    present = [d for d in draws if d['class'] == 'CANDIDATE' and d['upgrade']['present']]
    delivered = sum(d['class'] != 'UNDELIVERED' for d in draws)
    if present:
        return 'GO'
    if delivered == planned and len(draws) == planned:
        return 'NO_GO'
    return 'INCOMPLETE'


SCOPE_SENTENCE = ('Development evidence only, rebuilt locally (every evidence row reads local_only), from episodes of '
                  'several campaigns and stores; one draw per context at temperature 0; contexts share episodes, so the '
                  'intervals understate the uncertainty.')


def compute_readouts(requests, prompts, results, *, partial_lines_skipped=0, manifest_delivered=0):
    """`manifest_delivered` is delivered_generations(the run's manifest): None when it cannot say. The relaunch wording
    is used only when neither the manifest nor any line (a cut-off line included) shows that a generation may have
    arrived. The one-run rule (live_run_records) reads the manifest's count alone; run_live counts every line that
    shows a generation, and --finalize-abandoned also counts a cut-off line (review round 3), so on every manifest the
    harness writes the two tests agree, and where they could differ this one is the stricter. The wording does not
    check the rest of the $5 phase cap: after the last launch the cap admits it still appears, and the harness then
    refuses any further launch on the cap alone (protocol §9, §11)."""
    lines = _lines_by_request(results)
    draws = [classify_draw(r, (prompts or {}).get(r['messages_hash']), lines[r['request_id']]) for r in requests]
    n = len(requests)
    candidates = [d for d in draws if d['class'] == 'CANDIDATE']
    # The decision counts PRESENT re-sends (DECISION_RULE); the static check's labels are descriptive.
    present = [d for d in candidates if d['upgrade']['present']]
    firing = [d for d in present if d['upgrade']['label'] == CAN_FIRE]
    cannot = [d for d in present if d['upgrade']['label'] == CANNOT_FIRE]
    unclear = [d for d in present if d['upgrade']['label'] == UNCLEAR]
    classes = Counter(d['class'] for d in draws)
    subclasses = Counter(d.get('subclass') for d in draws if d['class'] == 'INVALID')
    not_loop = Counter(d['not_a_loop_proposal'] for d in draws if d['not_a_loop_proposal'])
    empty = sum(not_loop.values())
    delivered = n - classes.get('UNDELIVERED', 0)
    # Whether any generation may have arrived: the one-run rule's own test on the manifest, and line by line (a skipped
    # partial line counts), so the statement never offers a relaunch after a run the one-run rule refuses to follow.
    # It does not check the phase cap (review round 3, finding 2); check_budget refuses a launch the cap cannot cover.
    nothing_arrived = (manifest_delivered == 0 and not partial_lines_skipped
                       and not any(entry_delivered(line) for line in results))
    decision = decide(draws, n)
    hashes = lambda rows: sorted({d['policy_hash'] for d in rows})  # noqa: E731
    not_loop_text = (f'{empty} of the {n} draws were empty or unreadable outputs, which the loop would have recorded '
                     'as an infrastructure death, not a proposal')
    if decision == 'GO':
        low, high = wilson(len(present), n)
        early = sum(d['upgrade']['fires_at'] == 'after_upgrade_response' for d in firing)
        statement = (f'GO: {len(present)} of {n} first proposals (Wilson 95% [{low:.3f}, {high:.3f}]) contain an orders '
                     're-send (retry_original_request, service orders) at some hook under some gate. Descriptive, from '
                     f'the static check of the declared transient-failure path: {len(firing)} can fire ({early} at '
                     'after_upgrade_response, where a re-send can complete the task, and '
                     f'{len(firing) - early} only at before_final_report, after the Actor has proposed its report), '
                     f'{len(cannot)} cannot fire and {len(unclear)} are unclear. {not_loop_text}. This decides only '
                     'that the Phase 28 build may start; it does not mean that a re-send works or that the loop will '
                     'certify a repair.')
    elif decision == 'NO_GO':
        upper = wilson(0, n)[1]
        rest = wilson(0, n - empty)[1]
        statement = (f'NO_GO: none of the {n} draws contains an orders re-send at any hook under any gate (Wilson 95% '
                     f'upper bound {upper:.3f}). {not_loop_text}; over the other {n - empty} the upper bound is '
                     f'{"undefined" if rest is None else format(rest, ".3f")}. Phase 28 closes; the backend change is '
                     'not built.')
    elif nothing_arrived:
        # Review round 2, finding 2: after a run that delivered nothing, another launch (it sends all the draws) is
        # admitted only with the owner's relaunch approval (RELAUNCH_RULE); a run that delivered anything never is.
        statement = (f'INCOMPLETE: 0 of {n} draws delivered and no generation arrived, so nothing was observed. Another '
                     f'launch within the $5 phase cap sends all {n} draws and needs the owner\'s relaunch approval '
                     '(design §6.0; protocol §11).')
    else:
        statement = (f'INCOMPLETE: {delivered} of {n} draws delivered ({empty} of them empty or unreadable, which the '
                     'loop would have recorded as an infrastructure death), none so far with an orders re-send; '
                     'completing the missing draws needs the owner\'s approval and a separately reviewed harness '
                     'change (this harness has no completion mode).')
    statement += ' ' + SCOPE_SENTENCE
    exposure = defaultdict(lambda: [0, 0, 0])
    for draw, request in zip(draws, requests):
        for control in request['controls']:
            exposure[control['episode_id']][0] += 1
            exposure[control['episode_id']][1] += draw in present
            exposure[control['episode_id']][2] += draw in firing
    return {
        'schema_version': READOUT_SCHEMA, 'requests_planned': n, 'partial_lines_skipped': partial_lines_skipped,
        'decision': decision, 'decision_rule': DECISION_RULE, 'statement': statement,
        'delivered': delivered, 'any_generation_arrived': not nothing_arrived,
        'classes': dict(sorted(classes.items())), 'invalid_subclasses': dict(sorted(subclasses.items())),
        'not_a_loop_proposal': {'count': empty, 'by_cause': dict(sorted(not_loop.items())),
                                'loop_visible_draws': n - empty,
                                'wilson95_upper_over_loop_visible_if_none_present': wilson(0, n - empty)[1]},
        'format_repairs': {'needed': sum(d['repaired'] for d in draws),
                           'results': dict(Counter(str(d['repair_status']) for d in draws if d['repaired']))},
        'R_draw': {'present': len(present), 'planned': n, 'wilson95': wilson(len(present), n)},
        'R_valid': {'present': len(present), 'candidates': len(candidates),
                    'wilson95': wilson(len(present), len(candidates))},
        'R_fire_draw_descriptive': {'firing': len(firing), 'planned': n, 'wilson95': wilson(len(firing), n)},
        'R_fire_valid_descriptive': {'firing': len(firing), 'candidates': len(candidates),
                                     'wilson95': wilson(len(firing), len(candidates))},
        'labels': dict(Counter(str(d['upgrade']['label']) for d in present)),
        'fires_at': dict(Counter(d['upgrade']['fires_at'] for d in firing)),
        'reasons_not_firing': dict(Counter(d['upgrade']['reason'] for d in present if d['upgrade']['label'] != CAN_FIRE)),
        'how_written': [{'request_id': d['request_id'], 'policy_hash': d['policy_hash'], 'label': d['upgrade']['label'],
                         'fires_at': d['upgrade']['fires_at'], 'reason': d['upgrade']['reason'],
                         'orders_retry_steps': d['upgrade']['orders_retry_steps'],
                         'steps': d['upgrade']['steps']} for d in present],
        'orders_retry_step_counts': dict(Counter(str(min(d['upgrade']['orders_retry_steps'], 2)) for d in present)),
        'no_change': {'count': classes.get('NO_CHANGE', 0), 'wilson95': wilson(classes.get('NO_CHANGE', 0), n)},
        'invalid': {'count': classes.get('INVALID', 0), 'wilson95': wilson(classes.get('INVALID', 0), n)},
        'distinct': {'policies': len(hashes(candidates)), 'with_present_re_send': len(hashes(present)),
                     'with_firing_re_send': len(hashes(firing)),
                     'certified_policy_re_draws': sorted(h for h in hashes(candidates) if h in CERTIFIED_POLICY_HASHES)},
        'phase9_notification_step': sum(d['phase9_step'] for d in candidates),
        'both_sides': sum(d['phase9_step'] and d['upgrade']['present'] for d in candidates),
        'attempt4_pattern_premature_defer': sum(bool(d['notification']['premature_defer']) for d in candidates),
        'notification_audit_flags': {flag: sum(bool(d['notification'][flag]) for d in candidates)
                                     for flag in ('step_present', 'step_fires', 'premature_defer',
                                                  'stops_first_confirmation', 'harmful')},
        'integrity': [{'request_id': d['request_id'], 'problems': d['integrity']} for d in draws if d['integrity']],
        'episode_exposure_descriptive': {e: {'contexts': v[0], 'present_draws': v[1], 'firing_draws': v[2]}
                                         for e, v in sorted(exposure.items())},
        'per_draw': [{k: d.get(k) for k in ('request_id', 'context', 'class', 'subclass', 'repaired', 'repair_status',
                                            'policy_hash', 'undelivered', 'not_a_loop_proposal')}
                     | ({'label': d['upgrade']['label'], 'present': d['upgrade']['present'],
                         'phase9_step': d['phase9_step']} if d['class'] == 'CANDIDATE' else {}) for d in draws],
        'provider': {'served_model': dict(Counter(line.get('served_model') for line in results
                                                  if isinstance(line, dict) and line.get('status') == 'ok')),
                     'measured_input_tokens': sum((line or {}).get('input_tokens') or 0 for line in results
                                                  if isinstance(line, dict)),
                     'measured_output_tokens': sum((line or {}).get('output_tokens') or 0 for line in results
                                                   if isinstance(line, dict))},
    }


def load_run(directory):
    directory = pathlib.Path(directory)
    try:
        plan = json.loads((directory / 'plan.json').read_text())
        prompts = {}
        for line in (directory / 'prompts.jsonl').read_text(encoding='utf-8').splitlines():
            if line.strip():
                prompt = json.loads(line)
                prompts[prompt['messages_hash']] = prompt
        results, partial = load_results(directory / 'responses.jsonl')
    except PlanningError:
        raise
    except (OSError, ValueError) as error:
        raise PlanningError(f'The run in {directory} cannot be read ({type(error).__name__}); a run that stopped before '
                            'writing plan.json, prompts.jsonl or responses.jsonl has no read-outs') from None
    return plan, prompts, results, partial


NOT_THE_RUNS_HARNESS = "NOT THE RUN'S HARNESS OR PLAN: a recomputation, not the declared read-out"


def recompute_readouts(directory, *, allow_other_harness=False):
    """The read-outs of a run that has ended; refuses while its manifest is not final."""
    directory = pathlib.Path(directory)
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable {MANIFEST_NAME} in {directory}; read-outs are tied to a run') from None
    if not _final(manifest):
        raise PlanningError(f'The run in {directory} has not ended (manifest status {manifest.get("status")}); '
                            '--readouts refuses until its manifest is final')
    plan, prompts, results, partial = load_run(directory)
    readouts = compute_readouts(plan['requests'], prompts, results, partial_lines_skipped=partial,
                                manifest_delivered=delivered_generations(manifest))
    harness_matches = sha256_file(__file__) == manifest.get('harness_sha256')
    plan_matches = plan_hash(plan) == manifest.get('plan_hash')
    if harness_matches and plan_matches:
        return readouts
    if not allow_other_harness:
        raise PlanningError(f'{NOT_THE_RUNS_HARNESS} (harness matches the run: {harness_matches}; plan matches the run: '
                            f'{plan_matches}). Pass --not-the-runs-harness to print it labelled')
    return {'label': NOT_THE_RUNS_HARNESS, 'harness_matches_run': harness_matches, 'plan_matches_run': plan_matches,
            'readouts': readouts}


# ---------------------------------------------------------------- command line

def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', default=str(MAIN_STORE), help='the main lab store, read-only')
    parser.add_argument('--settings', default=DECLARED_SETTINGS, help='the declared non-secret settings file')
    parser.add_argument('--spend-cap', type=float, default=HARD_SPEND_CAP)
    parser.add_argument('--write-plan', help=f'new directory under artifacts/{PHASE_PREFIX}<date>/ for the dry plan')
    parser.add_argument('--readouts', help='recompute read-outs from a saved, final run directory ($0)')
    parser.add_argument('--not-the-runs-harness', action='store_true',
                        help="with --readouts: print a mismatched recomputation, labelled as not the run's")
    parser.add_argument('--finalize-abandoned', metavar='CLAIM',
                        help='close at $0 a claimed run whose process died before its manifest was final')
    parser.add_argument('--out', help=f'new directory under artifacts/{PHASE_PREFIX}<date>/ for a live run')
    parser.add_argument('--expect-plan-hash')
    parser.add_argument('--expect-harness-sha256')
    parser.add_argument('--expect-protocol-sha256')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    parser.add_argument('--relaunch-approval', metavar='RECORD',
                        help=('with --execute-live, only after earlier runs that delivered nothing: the owner\'s record '
                              f'artifacts/{PHASE_PREFIX}<date>/relaunch-approval-NN.json naming exactly this launch'))
    parser.add_argument('--ignore-manifest', action='append', default=[],
                        help="another phase's crashed run manifest or claim (exact path) known not to be running")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = arguments(argv)
    try:
        if args.finalize_abandoned:
            path, manifest = finalize_abandoned(args.finalize_abandoned)
            print(json.dumps({'status': 'FINALIZED', 'manifest': str(path),
                              'generations_delivered': manifest['generations_delivered'],
                              'charged_upper_bound': manifest['charged_upper_bound'],
                              'note': ('add charged_upper_bound to the ledger. A run that delivered anything is never '
                                       'repeated; after one that delivered nothing, another launch needs a new --out '
                                       'and the owner\'s --relaunch-approval')}, indent=2))
            return 0
        if args.readouts:
            print(json.dumps(recompute_readouts(args.readouts, allow_other_harness=args.not_the_runs_harness), indent=2))
            return 0
        if args.execute_live and not (args.out and args.confirm_entity and args.expect_plan_hash
                                      and args.expect_harness_sha256 and args.expect_protocol_sha256):
            raise PlanningError('--execute-live needs --out, --confirm-entity, --expect-plan-hash, '
                                '--expect-harness-sha256 and --expect-protocol-sha256')
        if args.execute_live:
            check_output(args.out)
            check_other_paid_runs(args)
        if args.write_plan:
            check_output(args.write_plan, live=False)
        settings_path = pathlib.Path(args.settings)
        settings_path = settings_path if settings_path.is_absolute() else ROOT / settings_path
        plan, prompts, _ = build_plan(store=args.store, settings_path=settings_path, spend_cap=args.spend_cap)
        if not args.execute_live:
            summary = dry_summary(plan)
            if args.write_plan:
                directory = check_output(args.write_plan, live=False)
                directory.mkdir(parents=True, exist_ok=False)
                write_json(directory / 'plan.json', plan)
                write_json(directory / 'dry-summary.json', summary)
                with (directory / 'prompts.jsonl').open('w', encoding='utf-8') as handle:
                    for messages_hash in sorted(prompts):
                        handle.write(json.dumps(prompts[messages_hash], sort_keys=True, ensure_ascii=False) + '\n')
                summary['written'] = str(directory)
            print(json.dumps(summary, indent=2, default=dict))
            print('Dry plan only. Pass --execute-live with --confirm-entity, --out and the reviewed hashes to send.')
            return 0
        return run_live(args, plan, prompts)
    except PlanningError as error:
        print(json.dumps({'status': 'REJECTED', 'error_type': type(error).__name__, 'message': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
