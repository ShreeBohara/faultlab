"""Phase 29: a non-scoring replay probe of Mechanic slot 2 with the prior candidate hidden.

Why (docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md, Phase 29). A completion study asks the Mechanic twice.
In most studies slot 2 returns slot 1's policy, so a study gets one real draw, not two (pitfall 70). In
Phase 25's descriptive reference arm N (the slot-2 request with `candidate_history = []`, one draw per
prompt), the Mechanic never wrote slot 1's policy (0 of 26), against 57 of 78 duplicates for the unchanged
request. That observation is the REASON for this phase's hypothesis, and it is never evidence here: no
Phase 25 draw is pooled with, compared against or counted in any declared read-out of this phase. Phase 25's
N outputs are used for one descriptive figure only (how many Phase 29 hidden-arm draws re-draw the policy
Phase 25's N draw wrote for the same prompt), which decides nothing.

The question. As declared arms with repeats, against a concurrent control, does hiding the prior candidate
from slot 2 (a) cut duplicates into distinct policies without raising invalid output, and (b) raise the
share of WORKING proposals (distinct, the retry step present and able to fire after a transient failure, no
declared harmful side rule) without a harmful excess? A second arm hides it AND uses a moderate temperature.

Arms (the same 26 slot-2 prompts as Phase 25: the census of v4-era full-loop studies that asked for slot 2):
  C   the exact verified slot-2 request, re-sent at temperature 0 (the concurrent control). 3 draws.
  N   temperature 0; the verified slot-2 context with candidate_history = [] (no prior candidate in view;
      development_evidence and observed_outcomes, which carry slot 1's source episodes, stay). Byte for byte
      Phase 25's N request. 3 draws.
  NT  the same bytes as N at temperature NT_TEMPERATURE (0.4, declared before any data). 3 draws.
234 requests in all; 52 distinct prompts (26 stored, 26 hidden; N and NT share theirs).

What is imported, never edited. Phase 25's harness (scripts/experiments/slot2_probe.py) is loaded unchanged
under a private module name, its sha256 pinned and checked before any plan or send. From it this probe uses:
the verified request rebuild and its twelve checks (survey, verify_slot, mechanic_messages, request_body,
request_digest, without_prior_candidate), the census rule and its cross-check against the Phase 17 and 23
run manifests, the pins and the partial freeze check, the static auditor and the study's classification
rules (classify_response, audit_policy), the per-arm counts and per-prompt statistics (arm_summary,
paired_sign, working_share, sign_test_greater, wilson, newcombe, clustered_sign, determinism_readout),
the live loop (run_requests with its blind retry, waits, stop rule and re-send pass; RequestSender, which
checks every request's digest before it is sent), the round-1 fallback rule (fallback_permitted,
run_end_of), and the token-based paid-run process rule (live_experiment_processes, which excludes this
process, its ancestors and its descendants, such as its own caffeinate helper). What is new here: the arms,
the declared read-outs and their bars, the simulation that sets the working-share minimums, and this
phase's own output, claim, review and paid-run guards.

Declared read-outs (compute_readouts; per treated arm X in {N, NT}, against C; thresholds below; the protocol
states them before any data):
  duplicates cut (distinct)  D_X >= 0.70 AND D_X - D_C >= 0.30 (worst case for missing draws) AND an exact
                             one-sided sign test over prompts on each prompt's DISTINCT mean, X above C,
                             p < 0.025 (Bonferroni over the two treated arms).
  invalid guard              invalid_X - invalid_C <= 0.10 (received draws) AND NOT an exact one-sided sign
                             test over prompts on each prompt's invalid mean, X above C, at p < 0.05.
  working gain               over the prompts whose slot-1 policy's step does not already fire: the sum of
                             X's WORKING share minus C's WORKING-or-missing share >= WORKING_SHARE_GAIN_MIN
                             AND an exact one-sided sign test on those per-prompt differences, X above C,
                             p < 0.025. The minimum (3; 1 in the round-1 fallback) is the smallest multiple
                             of 1/3 whose worst simulated false-alarm probability, under the yield null, is at
                             most 0.025 (--protocol-numbers).
  harmful guard              at most half of X's distinct firing draws carry a declared harmful side rule
                             AND NOT an exact one-sided Fisher test (harmful among distinct firing draws, X
                             above C) at p < 0.05 (not computable when either arm has no firing draw).
  decision                   RECOMMEND_FOR_A_LATER_LOOP iff X and C are complete (95% of planned draws) and
                             all four hold; INCOMPLETE if not complete (the round-1 fallback applies only
                             after a stop the operator does not choose, as in Phase 25); otherwise
                             NOT_RECOMMENDED. Two declared part-verdicts: DUPLICATES_CUT (distinct and
                             invalid) and YIELD_GAIN (working and harmful).
  review rounds 1 and 2 (descriptive; declared before any Phase 29 data; none decides anything)
                             DISTINCT means only "not this study's own slot 1": per arm, the policy concentration
                             of DISTINCT draws and how many are a policy ALREADY PROPOSED (round 2: any candidate
                             policy either slot of any in-scope v4 study proposed, 39 studies, recorded in the
                             hashed plan) against the NOVEL ones, with re-draws of the four certified policies on
                             their own line; WORKING draws per WORKING policy; clustered intervals (bootstrap by
                             prompt and by linked prompt group, withheld below 10 clusters, and a Wilson interval
                             counting each linked group once, the one a cost model uses) beside the Wilson interval
                             over draws; invalid draws split by what a study would repair; C's firing rate read
                             from C alone (point rate and Wilson upper bound) against the calibrated range; and two
                             fixed wording rules in the statement (a same-prompt re-measurement of Phase 25's N at a
                             dependence share of 1/2 or more, and the calibrated-range caveat).

Nothing here creates a campaign, study, trial, world, policy or store row. The store is opened read-only;
results are never shown to any model and never enter a study. Nothing in backend/app changes.

Dry by default. `--execute-live`, a matching `--confirm-entity`, the reviewed plan hash and the harness and
protocol hashes are all required before any provider call. The protocol's status block must no longer say
it is not yet reviewed, it must carry the bare line "Reviewed for launch: harness <sha256> plan <hash>", and
the review record must repeat the three pins and this harness's phase cap, say status "approved", name the
approver, and carry the owner's answer to §18 question 1 (question, verbatim, given_by, date). Review round 2:
the verbatim words must be at least 20 characters, must not be words the status block or the program document
already hold (the program-level approval is not an answer to §18 question 1), and must stand on one bare line of
the Review log's closing entry, exactly: Owner's answer to §18 question 1 (<given_by>, <date>): "<verbatim>".
The pinned Phase 25 harness is checked at import, before any of it runs. A live run refuses beside any
other paid run (manifests, claims, processes, the lab backend), takes an atomic claim, and the $15 cap is a
phase cap.

Usage (from the repository root):
  python scripts/experiments/slot2_hidden_probe.py
  python scripts/experiments/slot2_hidden_probe.py --write-plan artifacts/phase29-<date>/dry-plan
  python scripts/experiments/slot2_hidden_probe.py --protocol-numbers artifacts/phase29-<date>/protocol-numbers
  python scripts/experiments/slot2_hidden_probe.py --readouts artifacts/phase29-<date>/live
  python scripts/experiments/slot2_hidden_probe.py --finalize-abandoned artifacts/phase29-live-claims/claim-NN.json
  python scripts/experiments/slot2_hidden_probe.py --execute-live --confirm-entity ENTITY \\
      --out artifacts/phase29-<date>/live --expect-plan-hash H \\
      --expect-harness-sha256 S --expect-protocol-sha256 P
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
import contextlib
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.abc
import importlib.util
import json
import math
import os
import pathlib
import random
import re
import signal
import statistics
import subprocess
import sys
import traceback

# Even dry inspection should not create Python cache files in the workspace.
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

# Phase 25's harness, loaded unchanged under a private name so its module state is never shared with
# anything else that imports it. Review round 1: its bytes are read ONCE, their sha256 is compared with the pin
# BEFORE any of it runs, and the import system then compiles and runs exactly those bytes (a loader that serves the
# checked bytes and never re-reads the file), so the code that ran is the pinned code. A mismatch refuses at
# import, with nothing of the changed file run. phase25_harness_problem() re-checks the file on disk before any
# plan or send.
PHASE25_HARNESS = ROOT / 'scripts/experiments/slot2_probe.py'
PHASE25_HARNESS_SHA256 = '28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0'


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


_PHASE25_SOURCE = PHASE25_HARNESS.read_bytes()
if hashlib.sha256(_PHASE25_SOURCE).hexdigest() != PHASE25_HARNESS_SHA256:
    raise ImportError(f'{PHASE25_HARNESS} is not the pinned Phase 25 harness (sha256 {PHASE25_HARNESS_SHA256}); '
                      'none of it was run, and this probe refuses to load')
_SPEC = importlib.util.spec_from_loader('faultlab_phase29_slot2_probe',
                                        _PinnedSourceLoader(PHASE25_HARNESS, _PHASE25_SOURCE))
s2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(s2)

from app.contracts.models import MechanicCandidate, canonical_json, content_hash  # noqa: E402

SCHEMA = 'faultlab-slot2-hidden-probe/v1'
READOUT_SCHEMA = 'faultlab-slot2-hidden-probe-readouts/v1'
NUMBERS_SCHEMA = 'faultlab-slot2-hidden-probe-protocol-numbers/v1'
MANIFEST_NAME = 'slot2-hidden-probe-manifest.json'
PHASE_PREFIX = 'phase29-'
FINAL_STATUSES = ('COMPLETED', 'STOPPED', 'ABORTED')
# A live run writes its manifest at exactly artifacts/phase29-<date>/<name>/ (check_output), and only that
# depth is read: a copy saved deeper as evidence is never a live-gate input.
LIVE_MANIFEST_GLOB = f'{PHASE_PREFIX}*/*/{MANIFEST_NAME}'
CLAIM_DIR = 'phase29-live-claims'
CLAIM_NAME = re.compile(r'claim-(\d+)\.json')
ABANDONED_IN_FLIGHT_ATTEMPTS = s2.ABANDONED_IN_FLIGHT_ATTEMPTS
STORE = ROOT / 'artifacts/lab.sqlite3'
STORE_CUTOFF = s2.STORE_CUTOFF

EXPECTED_MECHANIC_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
EXPECTED_PROJECT = 'shreetbohara-quinstreet/Faultlab'
DECLARED_SETTINGS = 'artifacts/phase16-2026-09-22/settings-phase17.json'
DECLARED_SETTINGS_SHA256 = '1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d'
# The Phase 17 settings on the Phase 22 frozen code (PHASE22_RESULTS.md). Recomputed from the settings file
# alone; backend/app must not change for it to hold.
DECLARED_CONFIGURATION_HASH = '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba'
DECLARED_FREEZE_SHA256 = '8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1'
PROTOCOL = ROOT / 'docs/part2/PHASE29_EXPERIMENT.md'
# The program the owner approved in direction ("go ahead with whatever u recommend"). Review round 2: words it holds
# are never an answer to this phase's §18 question 1.
PROGRAM = ROOT / 'docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md'
REVIEW_RECORD = 'artifacts/phase29-2026-09-25/review.json'
REVIEW_PENDING_MARKER = 'NOT yet reviewed'
REVIEWED_LINE = 'Reviewed for launch: harness {harness} plan {plan}'
# Review round 1: the record must say the phase is approved, by whom, and carry the owner's answer (as Phase 30).
REVIEW_APPROVED_STATUS = 'approved'
OWNER_ANSWER_FIELDS = ('question', 'verbatim', 'given_by', 'date')
# Review round 2: where and how the owner's answer must stand. The words are the owner's own answer to §18 question
# 1, at least OWNER_ANSWER_MIN_CHARS long, on one bare line (never wrapped) of the Review log's closing entry: the
# last REVIEW_LOG_HEADING, then the last heading under it that starts with CLOSING_ENTRY_HEADING, up to the next
# heading. Words the status block or the program document already hold are refused, compared on letters and digits
# only (case, spaces and punctuation ignored), so the program-level approval cannot stand in for the answer.
OWNER_QUESTION = '§18 question 1'
OWNER_ANSWER_MIN_CHARS = 20
REVIEW_LOG_HEADING = '## Review log'
CLOSING_ENTRY_HEADING = '### Review log — closing'
OWNER_ANSWER_LINE = 'Owner\'s answer to §18 question 1 ({given_by}, {date}): "{verbatim}"'
PER_REQUEST_DOLLAR_BOUND = 0.04984   # 32,000 in x $1.31/M + 2,000 out x $3.96/M (frozen Mechanic pricing)
HARD_SPEND_CAP = 15.0                # the program's cap for this phase (EXPERIMENT_PROGRAM_PHASES_28-31.md)

# Phase 25's live run, read only for (a) the same-intervention check (C and N requests byte for byte Phase 25's)
# and (b) one descriptive dependence figure. Never pooled, never a decision input.
PHASE25_LIVE_PLAN = 'artifacts/phase25-2026-09-24/live/plan.json'
PHASE25_LIVE_PLAN_SHA256 = 'ce5cb3ffb6823c1f1eb201de6a998ae462c9c3a414cd11401ad26f064fab186d'
PHASE25_LIVE_RESPONSES = 'artifacts/phase25-2026-09-24/live/responses.jsonl'
PHASE25_LIVE_RESPONSES_SHA256 = '2e3b9235507118d77378b0f697eacb6d3fb22d77588da7969a8c5f6f86020af9'

ARMS = ('C', 'N', 'NT')
TREATED_ARMS = ('N', 'NT')
# Declared before any Phase 29 data: a round value between 0 (C, N) and the 0.7 of Phase 25's T, which raised
# invalid output to 9 of 78. Not tuned; another value is another phase.
NT_TEMPERATURE = 0.4
ARM_TEMPERATURE = {'C': 0, 'N': 0, 'NT': NT_TEMPERATURE}
REPEATS = 3
SAMPLE_SEED = 'faultlab-phase29-2026-09-25'
HIDDEN_RULE = ('the verified slot-2 context with candidate_history = [] (no prior candidate in view); '
               'development_evidence and observed_outcomes, which carry slot 1\'s source episodes, stay')
ARM_TEXT = {'C': 'the exact verified slot-2 request, re-sent at temperature 0 (the concurrent control)',
            'N': f'temperature 0; {HIDDEN_RULE}; byte for byte Phase 25\'s reference request N',
            'NT': f'the same bytes as N at temperature {NT_TEMPERATURE}; only the temperature keyword differs'}

# Declared thresholds (PHASE29_EXPERIMENT.md §8). Read at call time.
COMPLETE_MIN = s2.COMPLETE_MIN                 # 95% of planned draws: 75 of 78; 25 of 26 in round 1
DISTINCT_MIN = Fraction(7, 10)
DISTINCT_GAIN_MIN = Fraction(3, 10)
POSITIVE_ALPHA = 0.025                         # each positive claim, per arm (Bonferroni over N and NT)
GUARD_ALPHA = 0.05                             # each guard test, per arm (no correction: stricter for adoption)
INVALID_MARGIN = Fraction(1, 10)
HARMFUL_FIRING_SHARE_MAX = Fraction(1, 2)
FALSE_ALARM_TARGET = 0.025                     # per arm, for the working claim under the yield null
# Chosen by --protocol-numbers (the smallest multiple of 1/draws-per-prompt whose worst yield-null cell is at
# most FALSE_ALARM_TARGET); the numbers output must say harness_minimum_is_the_chosen_one.
WORKING_SHARE_GAIN_MIN = Fraction(3)
WORKING_SHARE_GAIN_MIN_ROUND1 = Fraction(1)
# The yield null was calibrated at common firing rates up to this (C's measured rate in Phase 25 was 3 of 78). A
# concurrent C that fires more often is outside the calibrated range; the read-out flags it (descriptive).
CALIBRATED_FIRING_MAX = Fraction(1, 10)
# Review round 1, declared before any Phase 29 data. Neither decides anything.
# (a) The wording rule: when at least this share of a hidden arm's received draws re-draw the policy Phase 25's N
#     wrote for the same prompt, the statement calls that arm's duplicates-cut result a same-prompt re-measurement
#     of Phase 25's N draws, not an independent confirmation.
RE_MEASUREMENT_SHARE_MIN = Fraction(1, 2)
# (b) Clustered intervals for per-draw rates (descriptive, beside the Wilson interval over draws): percentile
#     bootstrap over prompts and over linked prompt groups (prompts sharing a slot-1 policy or any drawn policy).
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 'faultlab-phase29-bootstrap'
# Review round 2, declared before any Phase 29 data. Neither decides anything.
# (c) A percentile bootstrap over G clusters has zero width at G = 1 and is very coarse at small G; below this many
#     clusters it is withheld (null, with a note). A cost model uses the Wilson interval counting each linked prompt
#     group once, never a bootstrap.
MIN_BOOTSTRAP_CLUSTERS = 10
# (d) The four certified completion repairs (Phase 17 attempt 9; Phase 23 attempts 2, 21 and 24). Checked at plan time
#     against the pinned Phase 17 and 23 run manifests, and each must be among the policies already proposed. A
#     hidden-arm draw of one of them is reported on its own line: it is a re-draw of a certified policy, not new.
CERTIFIED_POLICY_HASHES = (
    'dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521',
    '711bddb68697e52dcd9b0d5b428fa96d7ec1fe0e95559d9a892b4a7772ac738e',
    '5735a9186d71b2f01bff04d69c889ea23db8d5be5a90b4f8f51968fc64b60b31',
    'd4bc993e1854b90ad2f0670f9b1164bbb68e7e61de91bf1361d70592bea0d6e1',
)

PlanningError = s2.PlanningError
sha256_file = s2.sha256_file
sha256_text = s2.sha256_text
load_results = s2.load_results
write_json = s2.write_json
status_block = s2.status_block
entry_delivered = s2.entry_delivered
delivered_generations = s2.delivered_generations
settings_from_file = s2.settings_from_file
configuration_pins = s2.configuration_pins
check_pins = s2.check_pins
process_list = s2.process_list
backend_status = s2.backend_status


class SpendGuard(s2.SpendGuard):
    """Phase 25's guard (every attempt charged at the bound, in whole micro-dollars), checked against THIS
    harness's cap (read at call time), not the one inside the pinned Phase 25 file."""

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


def phase25_harness_problem():
    """The rebuild, auditor, statistics and live loop are Phase 25's reviewed code, or nothing is planned or sent.
    The bytes that were executed were checked at import; this re-checks both them and the file on disk, so a file
    edited after import also refuses."""
    if (hashlib.sha256(_PHASE25_SOURCE).hexdigest() != PHASE25_HARNESS_SHA256
            or sha256_file(PHASE25_HARNESS) != PHASE25_HARNESS_SHA256):
        return 'scripts/experiments/slot2_probe.py is not the pinned Phase 25 harness; its rebuild cannot be trusted'
    if s2.PER_REQUEST_DOLLAR_BOUND != PER_REQUEST_DOLLAR_BOUND or s2.DECLARED_CONFIGURATION_HASH != DECLARED_CONFIGURATION_HASH:
        return 'The Phase 25 harness does not carry this phase\'s configuration pin and dollar bound'
    return None


def check_budget(total_requests, spend_cap):
    if not (type(spend_cap) in (int, float) and math.isfinite(spend_cap) and 0 < spend_cap <= HARD_SPEND_CAP):
        raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    if SpendGuard.micro(total_requests * PER_REQUEST_DOLLAR_BOUND) > SpendGuard.micro(spend_cap):
        raise PlanningError(f'{total_requests} planned requests exceed the ${spend_cap:.2f} cap at '
                            f'${PER_REQUEST_DOLLAR_BOUND}/request')


# ---------------------------------------------------------------- Phase 25 reference (read-only, pinned)

def _phase25_run(root=None):
    """Phase 25's live plan and responses, both pinned; a changed or missing file refuses."""
    root = _root(root)
    plan_path, responses_path = root / PHASE25_LIVE_PLAN, root / PHASE25_LIVE_RESPONSES
    for path, digest in ((plan_path, PHASE25_LIVE_PLAN_SHA256), (responses_path, PHASE25_LIVE_RESPONSES_SHA256)):
        if not path.is_file() or sha256_file(path) != digest:
            raise PlanningError(f'{path.relative_to(root)} is not the pinned Phase 25 file')
    plan = json.loads(plan_path.read_text())
    results, _ = load_results(responses_path)
    return plan, results


def phase25_reference(root=None):
    """Per slot-2 prompt: Phase 25's C and N request (messages hash, request digest) for the same-intervention
    check, and the policy Phase 25's single N draw wrote (raw sha256, policy hash) for the descriptive
    dependence figure. Both files are pinned; a changed file refuses."""
    plan, results = _phase25_run(root)
    lines = defaultdict(list)
    for result in results:
        if isinstance(result, dict) and result.get('request_id'):
            lines[result['request_id']].append(result)
    out = {}
    for request in plan['requests']:
        if request['arm'] not in ('C', 'N'):
            continue
        entry = out.setdefault(request['prompt_id'], {})
        pins = {'messages_hash': request['messages_hash'], 'request_hash': request['request_hash']}
        if request['arm'] == 'C':
            previous = entry.setdefault('C', pins)
            if previous != pins:
                raise PlanningError(f'Phase 25\'s C requests for {request["prompt_id"]} differ between repeats')
            continue
        found = lines.get(request['request_id'], [])
        received = [line for line in found if line.get('status') == 'ok']
        raw = received[0].get('raw') if received else None
        parsed = s2.parse_policy(raw or '')
        entry['N'] = {**pins, 'request_id': request['request_id'], 'raw_sha256': sha256_text(raw),
                      'policy_hash': content_hash(parsed.candidate) if isinstance(parsed, MechanicCandidate) else None}
    return out


def phase25_planning_inputs(root=None, *, already_proposed):
    """PLANNING INPUTS ONLY (review round 1), never evidence and never a read-out of this phase: Phase 25's own
    draws, classified by its pinned classify_results, with this harness's policy-concentration read-out (so the
    figure the protocol quotes in §5 is computed by the same code that will describe Phase 29's arms, against the
    plan's already-proposed set since review round 2), and its determinism figures (the basis of the predicted
    dependence in §9.3). Reported in the dry summary only, never in the hashed plan."""
    proposed, certified = proposed_sets(already_proposed)
    plan, results = _phase25_run(root)
    rows = s2.classify_results(plan['requests'], results)
    census = census_slot1_policies(plan['requests'])
    by_arm = defaultdict(list)
    for row in rows:
        by_arm[row['request']['arm']].append(row)
    determinism = s2.determinism_readout(dict(sorted(by_arm.items())))
    c, h = determinism.get('C') or {}, determinism.get('H') or {}
    shares = []
    if c.get('same_policy_as_historical_output') and c['same_policy_as_historical_output'][1]:
        shares.append(Fraction(*c['same_policy_as_historical_output']))
    for arm in (c, h):
        if arm.get('repeat_pairs'):
            shares.append(Fraction(arm['same_policy_pairs'], arm['repeat_pairs']))
    return {'label': 'planning inputs from Phase 25\'s pinned run; never evidence in Phase 29, never a read-out',
            'census_slot1_policies': len(census), 'already_proposed_policies': len(proposed),
            'certified_policies': len(certified),
            'concentration_by_arm': {arm: policy_concentration(by_arm[arm], proposed, certified, census)
                                     for arm in sorted(by_arm)},
            'determinism_by_arm': determinism,
            'predicted_share_of_hidden_draws_re_drawing_phase25_N_policy': (
                [round(float(min(shares)), 4), round(float(max(shares)), 4)] if shares else None),
            'prediction_basis': ('the same temperature-0 request returned the same policy in these shares of Phase 25\'s '
                                 're-sends: C against its historical output, C repeat pairs, H repeat pairs')}


# ---------------------------------------------------------------- the plan

def hidden_context(context):
    """Arms N and NT: Phase 25's reference context, exactly (s2.without_prior_candidate)."""
    return s2.without_prior_candidate(context)


def arm_messages(context, arm):
    return s2.mechanic_messages(context if arm == 'C' else hidden_context(context))


def _verified(row, slot=2):
    return row['contexts'][slot] is not None and all(row['checks'][slot].values())


def precheck(rows, phase25):
    """$0 checks that each arm is exactly the declared change, comparing each arm's request with the control's
    and with Phase 25's own requests (real checks, not self-checks)."""
    out = Counter()
    for row in rows:
        if not _verified(row):
            continue
        context = row['contexts'][2]
        prompt_id = f"{row['study']['study_id']}:slot2"
        control = s2.request_body(s2.mechanic_messages(context), ARM_TEMPERATURE['C'])
        hidden = s2.request_body(arm_messages(context, 'N'), ARM_TEMPERATURE['N'])
        tempered = s2.request_body(arm_messages(context, 'NT'), ARM_TEMPERATURE['NT'])
        out['slot2_prompts'] += 1
        emptied = json.loads(hidden['messages'][1]['content'])
        emptied.pop('output_schema')
        emptied['candidate_history'] = context['candidate_history']
        out['N_differs_from_C_only_by_an_empty_candidate_history'] += (
            canonical_json(emptied) == canonical_json(context)
            and hidden['messages'][0] == control['messages'][0]
            and {k: v for k, v in hidden.items() if k != 'messages'} == {k: v for k, v in control.items() if k != 'messages'})
        prior = context['candidate_history'][0]
        slot1_raws = prior.get('raw_outputs') or []
        user = hidden['messages'][1]['content']
        out['N_user_message_holds_no_prior_candidate'] += (
            json.loads(user)['candidate_history'] == [] and prior['policy_hash'] not in user
            and not any(json.dumps(raw, ensure_ascii=False)[1:-1] in user for raw in slot1_raws))
        out['NT_differs_from_N_only_in_temperature'] += (
            {k: v for k, v in tempered.items() if k != 'temperature'} == {k: v for k, v in hidden.items() if k != 'temperature'}
            and tempered['temperature'] == NT_TEMPERATURE and hidden['temperature'] == 0 == control['temperature'])
        earlier = phase25.get(prompt_id) or {}
        out['C_request_is_phase25_C_request'] += bool(earlier.get('C')) and (
            content_hash(control['messages']) == earlier['C']['messages_hash']
            and s2.request_digest(control) == earlier['C']['request_hash'])
        out['N_request_is_phase25_N_request'] += bool(earlier.get('N')) and (
            content_hash(hidden['messages']) == earlier['N']['messages_hash']
            and s2.request_digest(hidden) == earlier['N']['request_hash'])
    out = dict(out)
    keys = ('N_differs_from_C_only_by_an_empty_candidate_history', 'N_user_message_holds_no_prior_candidate',
            'NT_differs_from_N_only_in_temperature', 'C_request_is_phase25_C_request', 'N_request_is_phase25_N_request')
    out['passed'] = out.get('slot2_prompts', 0) > 0 and all(out.get(key) == out['slot2_prompts'] for key in keys)
    return out


def census_facts(rows):
    """$0 facts about the census (review round 1), recorded in the hashed plan: the source case each slot-2 prompt
    was asked about, what slot 1 did there, and how many slot-1 policies the census holds. A hidden-arm draw that
    equals another study's slot-1 policy is a policy already proposed, and already run, on this source case."""
    verified = [row for row in rows if _verified(row)]
    first = [row['study']['candidates'][0] for row in verified]
    return {'source_fault_spec_content_hashes': dict(Counter(
                content_hash(row['contexts'][2]['source_fault_spec']) for row in verified)),
            'slot1_decisions': dict(sorted(Counter(str(c.get('decision')) for c in first).items())),
            'slot1_ran_on_the_source_case': sum(1 for c in first if c.get('source_assessment')),
            'slot1_source_qualified': sum(1 for c in first
                                          if (c.get('source_assessment') or {}).get('decision') == 'SOURCE_QUALIFIED'),
            'slot1_policies': len({row['reference']['slot1_policy_hash'] for row in verified}),
            'note': ('every census slot 1 ran on this source case and none source-qualified; a hidden-arm draw equal to '
                     'a policy any in-scope v4 study proposed (populations.already_proposed, review round 2) is not new; '
                     'in a real loop the DUPLICATE rule compares only within one study (completion_study `seen`), so '
                     'such a re-proposal would be run again')}


def certified_policies(root=None):
    """Review round 2: the certified completion repairs, read from the pinned Phase 17 and 23 run manifests (each
    attempt with certified true names its selected candidate) and checked against the declared four."""
    root = _root(root)
    found = {}
    for phase, (path, digest) in s2.PHASE_MANIFESTS.items():
        if not (root / path).is_file() or sha256_file(root / path) != digest:
            raise PlanningError(f'The {phase} run manifest is not the pinned one ({path})')
        for attempt in json.loads((root / path).read_text())['attempts']:
            if attempt.get('certified') is True:
                found[attempt.get('selected_candidate_hash')] = (f'{phase} attempt {attempt.get("attempt")} '
                                                                 f'({attempt.get("study_id")})')
    if set(found) != set(CERTIFIED_POLICY_HASHES):
        raise PlanningError('The pinned Phase 17 and 23 run manifests do not certify exactly the declared four policies')
    return dict(sorted(found.items()))


def already_proposed_record(connection, studies, root=None):
    """Review round 2, recorded in the hashed plan: every candidate policy hash proposed, in either slot, by an
    in-scope v4 study of Phases 17 and 23 (the census and the in-scope v4 studies that never reached slot 2), with
    the source fault spec each study's slot-1 proposal was asked about, and the certified policies among them. A
    hidden-arm draw of any of these policies is ALREADY PROPOSED, not new; the rest are NOVEL."""
    hashes, slots, specs, with_proposal = set(), Counter(), Counter(), 0
    for study in studies:
        candidates = study.get('candidates') or []
        if candidates:
            with_proposal += 1
            context, _ = s2.load_record(connection, 'completion_proposal_inputs', f"{study['study_id']}-1")
            if not isinstance(context, dict) or 'source_fault_spec' not in context:
                raise PlanningError(f"{study['study_id']}: its slot-1 proposal input cannot be read")
            specs[content_hash(context['source_fault_spec'])] += 1
        for slot, candidate in enumerate(candidates, 1):
            if candidate.get('policy_hash'):
                hashes.add(candidate['policy_hash'])
                slots[f'slot{slot}'] += 1
    certified = certified_policies(root)
    if not set(certified) <= hashes:
        raise PlanningError('A certified policy is not among the policies the in-scope v4 studies proposed; '
                            'the already-proposed set cannot be trusted')
    return {'rule': ('every candidate policy hash proposed, in either slot, by an in-scope v4 study of Phases 17 and '
                     '23 (the census and the in-scope v4 studies that never reached slot 2); a draw of one of them is '
                     'ALREADY PROPOSED, any other is NOVEL; the certified completion repairs among them are read from '
                     'the pinned run manifests'),
            'studies': len(studies), 'studies_with_a_proposal': with_proposal,
            'proposals_with_a_policy_by_slot': dict(sorted(slots.items())),
            'source_fault_spec_content_hashes_of_the_studies_with_a_proposal': dict(sorted(specs.items())),
            'policy_hashes': sorted(hashes), 'certified_policy_hashes': sorted(certified),
            'certified': certified}


def proposed_sets(already_proposed):
    """The plan's already-proposed record (review round 2) as (policies already proposed, certified policies);
    refuses a missing or malformed record, so no read-out is computed against the wrong set."""
    proposed = already_proposed.get('policy_hashes') if isinstance(already_proposed, dict) else None
    certified = already_proposed.get('certified_policy_hashes') if isinstance(already_proposed, dict) else None
    if not (isinstance(proposed, list) and isinstance(certified, list) and proposed
            and all(isinstance(value, str) and value for value in proposed + certified)):
        raise PlanningError('The plan carries no readable already-proposed policy set (populations.already_proposed, '
                            'review round 2); the novel and certified read-outs cannot be computed')
    proposed, certified = set(proposed), set(certified)
    if not certified <= proposed:
        raise PlanningError('The plan\'s certified policies are not all among its already-proposed policies')
    return proposed, certified


def build_requests(rows, phase25):
    """Planned requests in their fixed order, and the distinct prompts they use (by messages hash). Only
    verified slot-2 prompts are sent; slot 1 is verified but never re-sent."""
    prompts, units = {}, []
    for row in rows:
        if not _verified(row):
            continue
        study, context = row['study'], row['contexts'][2]
        historical = row['facts'][2]['historical_raw']
        history_class = s2.classify_response(historical, row['reference'])
        parsed = s2.parse_policy(historical or '')
        prompt_id = f"{study['study_id']}:slot2"
        earlier_n = (phase25.get(prompt_id) or {}).get('N') or {}
        for arm in ARMS:
            messages = arm_messages(context, arm)
            messages_hash = content_hash(messages)
            prompts.setdefault(messages_hash, {'messages_hash': messages_hash, 'messages': messages,
                                               'prompt_id': prompt_id,
                                               'arm_context': 'stored' if arm == 'C' else 'prior_candidate_hidden'})
            reference = {**row['reference'],
                         'historical_raw_sha256': sha256_text(historical),
                         'historical_policy_hash': (content_hash(parsed.candidate)
                                                    if isinstance(parsed, MechanicCandidate) else None),
                         'historical_class': history_class['class'],
                         'historical_duplicate_of_slot1': history_class['duplicate_of_slot1'],
                         'historical_attempts': row['facts'][2]['attempts']}
            if arm != 'C':
                # Descriptive only (the dependence figure): what Phase 25's single N draw wrote for this prompt.
                reference.update(phase25_n_raw_sha256=earlier_n.get('raw_sha256'),
                                 phase25_n_policy_hash=earlier_n.get('policy_hash'))
            units.append({'population': 'slot2', 'prompt_id': prompt_id, 'study_id': study['study_id'],
                          'phase': row['phase'], 'arm': arm, 'temperature': ARM_TEMPERATURE[arm],
                          'messages_hash': messages_hash,
                          'request_hash': s2.request_digest(s2.request_body(messages, ARM_TEMPERATURE[arm])),
                          'reference': reference})
    order = lambda u, r: (rank('prompt', u['prompt_id'], r), rank('arm', u['prompt_id'], r, u['arm']))  # noqa: E731
    # Each round holds every arm of each prompt back to back (C, N and NT in ranked order), prompts by rank, each
    # round ranked afresh; so a run that stops after round 1 has a complete round 1 (the declared fallback).
    rounds = [sorted(({**u, 'repeat': r} for u in units), key=lambda u: order(u, r)) for r in range(REPEATS)]
    requests = [u for current in rounds for u in current]
    for index, request in enumerate(requests, 1):
        request['request_id'] = f'r{index:04d}'
    return requests, prompts


def thresholds():
    return {'complete_min': str(COMPLETE_MIN), 'distinct_min': str(DISTINCT_MIN),
            'distinct_gain_min': str(DISTINCT_GAIN_MIN), 'positive_alpha': POSITIVE_ALPHA,
            'guard_alpha': GUARD_ALPHA, 'invalid_margin': str(INVALID_MARGIN),
            'harmful_firing_share_max': str(HARMFUL_FIRING_SHARE_MAX),
            'working_share_gain_min': str(WORKING_SHARE_GAIN_MIN),
            'working_share_gain_min_round1': str(WORKING_SHARE_GAIN_MIN_ROUND1),
            'false_alarm_target_per_arm': FALSE_ALARM_TARGET, 'nt_temperature': NT_TEMPERATURE,
            'calibrated_common_firing_max': str(CALIBRATED_FIRING_MAX),
            're_measurement_share_min': str(RE_MEASUREMENT_SHARE_MIN),
            'bootstrap_resamples': BOOTSTRAP_RESAMPLES, 'bootstrap_seed': BOOTSTRAP_SEED,
            'min_bootstrap_clusters': MIN_BOOTSTRAP_CLUSTERS,
            'repeats': REPEATS}


def readout_rules():
    return {
        'unit': ('a draw is one planned request; each arm has 3 draws per prompt. Classes (Phase 25\'s auditor, '
                 'imported): INVALID, NO_CHANGE, STALE_PARENT, CANDIDATE; a CANDIDATE is DUPLICATE when its policy '
                 'hash equals slot 1\'s, else DISTINCT. WORKING = DISTINCT, the retry step is present and fires '
                 'after a transient failure (abstract interpreter run), and no declared harmful side rule '
                 '(premature defer, stops the first confirmation)'),
        'complete': 'an arm is complete when it received >= 95% of its planned draws (75 of 78; 25 of 26 in round 1)',
        'distinct': ('DUPLICATES CUT, part 1, per X in {N, NT} against C: D_X = X DISTINCT / planned (a missing X '
                     'draw is not distinct), D_C = (C DISTINCT + C missing) / planned; D_X >= 0.70 AND D_X - D_C >= '
                     '0.30 AND exact one-sided sign test over prompts on the per-prompt DISTINCT mean of received '
                     'draws, X above C, ties and prompts without draws in both arms dropped, p < 0.025'),
        'invalid': ('DUPLICATES CUT, part 2 (guard): invalid = (INVALID + STALE_PARENT) / received; invalid_X - '
                    'invalid_C <= 0.10 AND NOT (exact one-sided sign test over prompts on the per-prompt invalid '
                    'mean, X above C, p < 0.05). These are FIRST-ATTEMPT rates: a study sends a schema failure back '
                    'for one format repair, so the guard overstates what adoption would see; the split by what a '
                    'study would do is reported beside it (descriptive)'),
        'working': ('YIELD GAIN, part 1: over the prompts whose slot-1 policy\'s step does not fire, each prompt adds '
                    'X\'s WORKING share of its planned draws (a missing X draw is not WORKING) minus C\'s '
                    'WORKING-or-missing share of its planned draws (Phase 25\'s working_share); the sum >= '
                    f'{WORKING_SHARE_GAIN_MIN} AND exact one-sided sign test on the per-prompt differences, X above '
                    'C, p < 0.025'),
        'harmful': ('YIELD GAIN, part 2 (guard): harmful share of X\'s distinct firing draws <= 0.50 AND NOT (exact '
                    'one-sided Fisher test on harmful vs not harmful among distinct firing draws, X above C, p < '
                    '0.05); the Fisher test is not computable, and does not fail, when either arm has no distinct '
                    'firing draw'),
        'decision': ('RECOMMEND_FOR_A_LATER_LOOP iff X and C are complete, DUPLICATES_CUT (distinct and invalid) '
                     'and YIELD_GAIN (working and harmful); INCOMPLETE if not complete; otherwise NOT_RECOMMENDED, '
                     'listing every failed condition. DUPLICATES_CUT and YIELD_GAIN are each also declared on their '
                     'own (SHOWN / NOT_SHOWN / INCOMPLETE). If both arms are recommended the phase prefers neither'),
        'round1_fallback': ('only when an arm\'s all-rounds decision is INCOMPLETE and the run ended by a stop the '
                            'operator does not choose (completed, spend_guard, consecutive_errors, or a crash '
                            'recorded with its traceback) with no stop signal (Phase 25\'s fallback_permitted): the '
                            'same rule on round 1 alone (26 planned draws per arm, complete at 25), working-share '
                            f'minimum {WORKING_SHARE_GAIN_MIN_ROUND1}, labelled round 1 only, the all-rounds figures '
                            'beside it. After any SIGINT or SIGTERM, or a process closed by --finalize-abandoned, an '
                            'INCOMPLETE decision stays INCOMPLETE'),
        'descriptive': ('per-arm classes and flags; duplicates of slot 1 (the Phase 25 lead\'s measure) with Wilson '
                        'intervals; N against NT (Newcombe, sign tests), never a decision; determinism of C, N and NT; '
                        'the dependence of N and NT on Phase 25\'s single N draw per prompt; draws on the 2 prompts '
                        'whose slot-1 policy fires; how draws arrived; served model; tokens. Review rounds 1 and 2: per '
                        'arm, the policy concentration of DISTINCT draws (distinct policies, the prompt and draw count '
                        'of the largest one), the DISTINCT, firing and WORKING draws whose policy is ALREADY PROPOSED '
                        '(any candidate policy either slot of any in-scope v4 study proposed: populations.'
                        'already_proposed in this plan) against the NOVEL ones, re-draws of a certified policy on '
                        'their own line, WORKING draws per distinct WORKING policy, clustered intervals for the '
                        'per-draw DISTINCT, novel DISTINCT, WORKING and novel WORKING rates (a Wilson interval '
                        'counting each linked prompt group once, which a cost model uses, and percentile bootstraps '
                        f'by prompt and by linked prompt group, withheld below {MIN_BOOTSTRAP_CLUSTERS} clusters) beside '
                        'the Wilson interval over draws, invalid draws split by what a study would do, and C\'s firing '
                        'rate read from C alone (point rate and Wilson 95% upper bound) against the calibrated range, '
                        'with the pooled X-and-C rate reported beside it and driving no wording'),
        'distinct_is_not_new': ('DISTINCT means only "not this study\'s own slot-1 policy". A DUPLICATES_CUT of SHOWN '
                                'reads "slot 2 differs from this study\'s slot 1", never "slot 2 is a new draw". NOVEL '
                                'means a policy no in-scope v4 study proposed in either slot; a re-draw of a certified '
                                'policy is ALREADY PROPOSED and is reported on its own line. Any cost-model use of slot '
                                '2 rests on the novel DISTINCT and the novel WORKING figures with the Wilson interval '
                                'that counts each linked prompt group once'),
        'wording': ('a fixed wording rule, never a decision: when at least 1/2 of a hidden arm\'s received draws re-draw '
                    'the policy Phase 25\'s N wrote for the same prompt, the statement calls that arm\'s duplicates-cut '
                    'result a same-prompt re-measurement of Phase 25\'s N draws, not an independent confirmation; '
                    'beside a SHOWN working claim, when C\'s own firing rate is above 0.10 the claim is outside its '
                    'calibrated range, and when only C\'s own Wilson 95% upper bound is above 0.10 the range is not '
                    'confirmed (read from C alone; the pooled X-and-C rate drives no wording)'),
        'phase25': ('Phase 25\'s draws are never pooled with, compared against or counted in a declared read-out. '
                    'They are read only to check that C and N are byte for byte Phase 25\'s requests, for the '
                    'descriptive dependence figure and its wording rule, and (dry summary only, labelled) for the '
                    'planning inputs the protocol quotes: its arms\' policy concentration and determinism'),
        'adoption': ('a recommended arm is for a later loop\'s own declaration only; adopting it changes backend/app '
                     '(completion_study builds slot 2 with candidate_history = [] ONLY when slot 1\'s candidate ran '
                     'and added feedback rows, else keeps the history, since otherwise slot 2\'s request would be '
                     'byte-identical to slot 1\'s; and for NT a per-slot Mechanic temperature), so it needs a new '
                     'configuration, a new freeze and its own review. Every census study\'s slot 1 ran, so the '
                     'probe cannot see the other case'),
    }


def token_estimate(prompts, requests, output_median):
    """Token-priced estimate (unverified) and the ceiling at 2,000 output tokens per request."""
    tokens = {h: s2.local_prompt_tokens(p['messages']) + s2.FRAMING_TOKENS for h, p in prompts.items()}
    by_arm = defaultdict(list)
    for request in requests:
        by_arm[request['arm']].append(tokens[request['messages_hash']])
    price_in, price_out = 1.31e-6, 3.96e-6
    estimate = sum(t * price_in + output_median * price_out for values in by_arm.values() for t in values)
    ceiling = sum(t * price_in + s2.MECHANIC_MAX_OUTPUT_TOKENS * price_out for values in by_arm.values() for t in values)
    return {'input_tokens_by_arm': {arm: {'median': statistics.median(v), 'min': min(v), 'max': max(v)}
                                    for arm, v in sorted(by_arm.items())},
            'historical_slot2_output_tokens_median': output_median,
            'token_priced_estimate': round(estimate, 2), 'token_priced_ceiling_at_2000_output': round(ceiling, 2),
            'note': 'estimated from the local tokenizer + 24 framing tokens; unverified; the ledger carries the bound'}


def build_plan(*, store=STORE, settings_path=None, spend_cap=HARD_SPEND_CAP, cutoff=STORE_CUTOFF, root=None):
    problem = phase25_harness_problem()
    if problem:
        raise PlanningError(problem)
    root = _root(root)
    settings_path = pathlib.Path(settings_path or root / DECLARED_SETTINGS)
    if sha256_file(settings_path) != DECLARED_SETTINGS_SHA256:
        raise PlanningError('The settings file is not the declared Phase 17 settings file')
    pins = configuration_pins(settings_from_file(settings_path, env_path=os.devnull))
    check_pins(pins)
    if pins['configuration_hash'] != DECLARED_CONFIGURATION_HASH:
        raise PlanningError('configuration_hash differs from the declared Phase 22 value')
    freeze = s2.check_freeze(pins, root)
    phase25 = phase25_reference(root)
    connection = s2.connect(store)
    try:
        rows, excluded, failures = s2.survey(connection, pins, cutoff, root)
        checks = precheck(rows, phase25)
        if not checks['passed']:
            raise PlanningError('The $0 arm pre-check failed; nothing may be sent')
        requests, prompts = build_requests(rows, phase25)
        v4_studies = [r['study'] for r in rows] + s2._other_v4_studies(connection, rows, cutoff)
        auditor = s2.auditor_validation(connection, v4_studies)
        proposed = already_proposed_record(connection, v4_studies, root)
        outputs = []
        for row in rows:
            attempts = s2.output_attempts(connection, row['study']['candidates'][1].get('proposal_ref'))
            outputs.append(((attempts[0] if attempts else {}).get('usage') or {}).get('output_tokens'))
    finally:
        connection.close()
    counts = Counter((r['population'], r['arm']) for r in requests)
    total = len(requests)
    check_budget(total, spend_cap)
    max_attempts = SpendGuard.micro(spend_cap) // SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND)
    plan = {
        'schema_version': SCHEMA, 'experiment': 'phase29_mechanic_slot2_prior_hidden_probe',
        'scoring': 'NON_SCORING_NEVER_FED_BACK', 'split': 'development', 'purpose': s2.PURPOSE,
        'store_cutoff': cutoff, 'harness_sha256': sha256_file(__file__),
        'phase25_harness_sha256': PHASE25_HARNESS_SHA256,
        'source_sha256': {name: sha256_file(root / name) for name in s2.FREEZE_FILES
                          + ('backend/app/contracts/models.py', 'backend/app/providers/runtime.py',
                             'backend/app/lab/policy_state.py', 'backend/app/lab/policy_interpreter.py')},
        'settings_file': DECLARED_SETTINGS, 'settings_sha256': DECLARED_SETTINGS_SHA256, **pins, 'freeze': freeze,
        'provider_call': {'role': 'mechanic', 'max_output_tokens': s2.MECHANIC_MAX_OUTPUT_TOKENS,
                          'timeout_seconds': s2.MECHANIC_TIMEOUT_SECONDS,
                          'response_format': s2.response_format_for(role='mechanic'),
                          'model_options': s2.model_request_options(EXPECTED_MECHANIC_MODEL),
                          'format_repair': 'none: one request per draw (the study would allow one format repair)',
                          'blind_retry': list(s2.RETRYABLE_TRANSPORT_CODES) + [
                              f'at most once, charged, after {s2.BLIND_RETRY_WAIT_SECONDS} s'],
                          'resend_after_main_pass': (
                              'only if the main pass attempted every planned request: each request whose attempts all '
                              f'failed with {list(s2.RESEND_CODES)} and delivered no generation is re-sent once, in plan '
                              'order, charged; a delivered generation is never re-sent'),
                          'backoff_after_errored_request_seconds': list(s2.BACKOFF_SECONDS),
                          'consecutive_errored_requests_stop': s2.CONSECUTIVE_ERROR_ABORT,
                          'request_digest': f'content_hash of the create() keywords {list(s2.REQUEST_KEYS)}; '
                                            'checked before every send (Phase 25\'s RequestSender)',
                          'served_model': 'recorded from each response, never enforced'},
        'arms': {arm: {'temperature': ARM_TEMPERATURE[arm], 'rule': ARM_TEXT[arm], 'repeats': REPEATS} for arm in ARMS},
        'populations': {'rule': ('Phase 25\'s census (imported): every completion study in the read-only store with '
                                 f'configuration {sorted(s2.DECLARED_CONFIGURATIONS)} (Phases 17 and 23), v4 Actor '
                                 'context, evidence v2, not a replay, created before the cutoff, with two proposals; '
                                 'the set must equal the pinned run manifests\' studies with two proposals'),
                        'studies': [r['study']['study_id'] for r in rows],
                        'by_phase': dict(Counter(r['phase'] for r in rows)),
                        'excluded_in_scope': excluded, 'verification_failures': failures,
                        'slot2_prompts': sum(1 for r in requests if r['arm'] == 'C' and r['repeat'] == 0),
                        'prompts_whose_slot1_policy_fires': sorted(
                            r['prompt_id'] for r in requests
                            if r['arm'] == 'C' and r['repeat'] == 0 and r['reference']['slot1_step_fires']),
                        'census_facts': census_facts(rows),
                        'already_proposed': proposed,
                        'repeats': REPEATS,
                        'order': ('three rounds; in each, prompts by sha256 rank and each prompt\'s C, N and NT back to '
                                  'back in ranked order; each round ranked afresh (r0001-r0078, r0079-r0156, '
                                  'r0157-r0234 at full size)')},
        'verification': {'rule': sorted({k for r in rows for s in (1, 2) for k in r['checks'][s]}),
                         'framing_tokens': s2.FRAMING_TOKENS,
                         'slots_checked': sum(len(r['checks']) for r in rows),
                         'slots_verified': sum(all(r['checks'][s].values()) for r in rows for s in (1, 2))},
        'precheck': checks,
        'phase25_reference': {'plan': PHASE25_LIVE_PLAN, 'plan_sha256': PHASE25_LIVE_PLAN_SHA256,
                              'responses': PHASE25_LIVE_RESPONSES, 'responses_sha256': PHASE25_LIVE_RESPONSES_SHA256,
                              'use': readout_rules()['phase25']},
        'investigation': {'auditor_validation': auditor},
        'readout_rules': readout_rules(), 'thresholds': thresholds(),
        'counts': {'by_population_and_arm': {f'{p}/{a}': n for (p, a), n in sorted(counts.items())},
                   'total_requests': total, 'distinct_prompts': len(prompts)},
        'cost': {'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                 'planned_upper_bound': round(total * PER_REQUEST_DOLLAR_BOUND, 6), 'spend_cap': spend_cap,
                 'phase_spend_cap': HARD_SPEND_CAP, 'max_attempts_under_cap': max_attempts,
                 'retry_headroom_attempts': max_attempts - total,
                 **token_estimate(prompts, requests, statistics.median([o for o in outputs if isinstance(o, int)] or [0]))},
        'max_input_tokens_reported_historically': max(r['facts'][s]['reported_prompt_tokens'] or 0
                                                      for r in rows for s in (1, 2)),
        'requests': requests,
    }
    return plan, prompts


def plan_hash(plan):
    return content_hash(plan)


# ---------------------------------------------------------------- statistics and read-outs (pure)

def fisher_greater(a, b, c, d):
    """Exact one-sided Fisher test for the table [[a, b], [c, d]]: P(A >= a) with every margin fixed."""
    if min(a, b, c, d) < 0:
        raise ValueError('invalid counts')
    row1, row2, column = a + b, c + d, a + c
    total = row1 + row2
    if total == 0 or row1 == 0 or row2 == 0:
        return 1.0
    high = min(column, row1)
    return sum(math.comb(row1, x) * math.comb(row2, column - x) for x in range(a, high + 1)) / math.comb(total, column)


def _invalid(classified):
    return classified['class'] in ('INVALID', 'STALE_PARENT')


def invalid_sign(x_rows, c_rows):
    """Exact one-sided sign test over prompts on each prompt's invalid mean over its received draws, X above C."""
    def means(rows):
        groups = defaultdict(list)
        for r in rows:
            if r['received']:
                groups[r['request']['prompt_id']].append(_invalid(r['c']))
        return {p: Fraction(sum(v), len(v)) for p, v in groups.items() if v}
    x, c = means(x_rows), means(c_rows)
    both = sorted(set(x) & set(c))
    plus = sum(1 for p in both if x[p] > c[p])
    minus = sum(1 for p in both if x[p] < c[p])
    return {'prompts_compared': len(both), 'favouring': plus, 'against': minus, 'ties': len(both) - plus - minus,
            'p_one_sided': s2.sign_test_greater(plus, minus)}


def _label(value):
    return f'{float(value):.2f}'


def calibrated_range(fired_x, received_x, fired_c, received_c):
    """Descriptive: the yield null was calibrated at COMMON firing rates up to 0.10, i.e. under the null, where both
    arms share C's rate. Review round 2: the range is read from C alone. 'outside': C's point rate is above 0.10 (the
    declared caveat); 'not_confirmed': C's point rate is within, but its Wilson 95% upper bound is above 0.10 (from 3
    firing draws of 78 upward); 'within': both are at most 0.10; 'unknown': C received nothing. The pooled X-and-C
    rate is reported beside it and drives no wording: when the working claim is SHOWN, X's own gain inflates it, so
    it would mostly restate the claim (round 1 read it as a third leg)."""
    pooled = Fraction(fired_x + fired_c, received_x + received_c) if received_x + received_c else None
    pooled_note = 'descriptive only; drives no wording (X\'s own firing inflates it whenever the working claim is SHOWN)'
    if not received_c:
        return {'reading': 'unknown', 'C_rate': None, 'C_wilson95_upper': None,
                'pooled_rate_descriptive': None if pooled is None else float(pooled), 'pooled_note': pooled_note,
                'calibrated_common_firing_max': float(CALIBRATED_FIRING_MAX)}
    rate = Fraction(fired_c, received_c)
    upper = s2.wilson(fired_c, received_c)[1]
    if rate > CALIBRATED_FIRING_MAX:
        reading = 'outside'
    elif upper > float(CALIBRATED_FIRING_MAX):
        reading = 'not_confirmed'
    else:
        reading = 'within'
    return {'reading': reading, 'C_rate': float(rate), 'C_wilson95_upper': upper,
            'pooled_rate_descriptive': float(pooled), 'pooled_note': pooled_note,
            'calibrated_common_firing_max': float(CALIBRATED_FIRING_MAX)}


def arm_decision(x_rows, c_rows, arm, *, working_gain_min=None):
    """The declared contrast of treated arm X against C (§8 of the protocol)."""
    working_gain_min = WORKING_SHARE_GAIN_MIN if working_gain_min is None else Fraction(working_gain_min)
    x, c = s2.arm_summary(x_rows), s2.arm_summary(c_rows)
    planned_x, planned_c = x['planned'], c['planned']
    complete = bool(x['complete'] and c['complete'])
    d_x = Fraction(x['distinct'], planned_x) if planned_x else Fraction(0)
    d_c = Fraction(c['distinct'] + c['missing'], planned_c) if planned_c else Fraction(1)
    distinct_sign = s2.paired_sign(x_rows, c_rows, 'distinct', greater='x')
    working = s2.working_share(x_rows, c_rows)
    gain = Fraction(working['gain_exact'])
    working_sign = {'prompts_compared': working['eligible_prompts'], 'favouring': working['prompts_favouring'],
                    'against': working['prompts_against'],
                    'p_one_sided': s2.sign_test_greater(working['prompts_favouring'], working['prompts_against'])}
    inv_x = Fraction(x['invalid'], x['received']) if x['received'] else Fraction(1)
    inv_c = Fraction(c['invalid'], c['received']) if c['received'] else Fraction(0)
    inv_sign = invalid_sign(x_rows, c_rows)
    fired_x, harmed_x = x['distinct_firing'], x['distinct_firing_harmful']
    fired_c, harmed_c = c['distinct_firing'], c['distinct_firing_harmful']
    harm_share = Fraction(harmed_x, fired_x) if fired_x else Fraction(0)
    harm_p = fisher_greater(harmed_x, fired_x - harmed_x, harmed_c, fired_c - harmed_c) if fired_x and fired_c else None
    parts = {
        'distinct': {'distinct_at_least_0.70': d_x >= DISTINCT_MIN,
                     'distinct_gain_at_least_0.30': d_x - d_c >= DISTINCT_GAIN_MIN,
                     'distinct_sign_test_p_below_0.025': distinct_sign['p_one_sided'] < POSITIVE_ALPHA},
        'invalid': {'invalid_at_most_C_plus_0.10': inv_x - inv_c <= INVALID_MARGIN,
                    'invalid_not_shown_above_C_at_0.05': not inv_sign['p_one_sided'] < GUARD_ALPHA},
        'working': {f'working_share_gain_at_least_{_label(working_gain_min)}': gain >= working_gain_min,
                    'working_sign_test_p_below_0.025': working_sign['p_one_sided'] < POSITIVE_ALPHA},
        'harmful': {'harmful_share_of_firing_at_most_0.50': harm_share <= HARMFUL_FIRING_SHARE_MAX,
                    'harmful_not_shown_above_C_at_0.05': harm_p is None or not harm_p < GUARD_ALPHA},
    }

    def verdict(conditions, yes, no):
        return 'INCOMPLETE' if not complete else (yes if all(conditions.values()) else no)
    verdicts = {'distinct': verdict(parts['distinct'], 'SHOWN', 'NOT_SHOWN'),
                'invalid': verdict(parts['invalid'], 'PASS', 'FAIL'),
                'working': verdict(parts['working'], 'SHOWN', 'NOT_SHOWN'),
                'harmful': verdict(parts['harmful'], 'PASS', 'FAIL')}
    duplicates_cut = verdict({**parts['distinct'], **parts['invalid']}, 'SHOWN', 'NOT_SHOWN')
    yield_gain = verdict({**parts['working'], **parts['harmful']}, 'SHOWN', 'NOT_SHOWN')
    failed = [name for part in parts.values() for name, ok in part.items() if not ok]
    if not complete:
        decision = 'INCOMPLETE'
        failed = ['complete'] + failed
    elif not failed:
        decision = 'RECOMMEND_FOR_A_LATER_LOOP'
    else:
        decision = 'NOT_RECOMMENDED'
    return {'arm': arm, 'decision': decision, 'duplicates_cut': duplicates_cut, 'yield_gain': yield_gain,
            'verdicts': verdicts, 'failed': failed, 'conditions': {'complete': complete, **{
                name: ok for part in parts.values() for name, ok in part.items()}},
            'planned_draws': {'X': planned_x, 'C': planned_c},
            'working_share_gain_min': str(working_gain_min),
            'distinct': {'D_X': float(d_x), 'D_C_worst_case': float(d_c), 'D_gain': float(d_x - d_c),
                         'sign_test': distinct_sign,
                         'sign_test_clustered_by_slot1_policy_descriptive': s2.clustered_sign(x_rows, c_rows, 'distinct'),
                         'received': {'X': [x['distinct'], x['received']], 'C': [c['distinct'], c['received']]},
                         'difference_newcombe95_received': s2.newcombe(x['distinct'], x['received'],
                                                                       c['distinct'], c['received'])},
            'invalid': {'invalid_X': float(inv_x), 'invalid_C': float(inv_c), 'excess': float(inv_x - inv_c),
                        'counts': {'X': [x['invalid'], x['received']], 'C': [c['invalid'], c['received']]},
                        'sign_test_X_above_C': inv_sign},
            'working': {'share': working, 'gain': float(gain), 'gain_exact': str(gain), 'sign_test': working_sign,
                        'C_distinct_firing_rate_received': (float(Fraction(fired_c, c['received']))
                                                            if c['received'] else None),
                        'calibrated_range_descriptive': calibrated_range(fired_x, x['received'], fired_c, c['received']),
                        'received': {'X': [x['working'], x['received']], 'C': [c['working'], c['received']]},
                        'difference_newcombe95_received': s2.newcombe(x['working'], x['received'],
                                                                      c['working'], c['received'])},
            'harmful': {'distinct_firing': {'X': fired_x, 'C': fired_c},
                        'distinct_firing_harmful': {'X': harmed_x, 'C': harmed_c},
                        'harmful_share_of_firing_X': float(harm_share),
                        'fisher_p_X_above_C': harm_p,
                        'fisher_note': None if harm_p is not None else
                        'not computable: an arm has no distinct firing draw; the condition holds'}}


def _round1(rows):
    return [r for r in rows if r['request'].get('repeat', 0) == 0]


def _declared(full, fallback):
    chosen = fallback if fallback is not None else full
    return {'decision': chosen['decision'], 'duplicates_cut': chosen['duplicates_cut'],
            'yield_gain': chosen['yield_gain'], 'verdicts': chosen['verdicts'],
            'basis': 'round_1_only' if fallback is not None else 'all_rounds', 'failed': chosen['failed']}


def dependence_readout(rows):
    """Descriptive: how many received draws re-draw what Phase 25's single N draw wrote for the same prompt, and
    the declared wording rule (review round 1): at RE_MEASUREMENT_SHARE_MIN or more, this arm's duplicates-cut
    result is a same-prompt re-measurement of Phase 25's N draws, not an independent confirmation."""
    received = [r for r in rows if r['received']]
    same_policy = sum(1 for r in received if r['c']['policy_hash'] is not None
                      and r['c']['policy_hash'] == s2._reference(r).get('phase25_n_policy_hash'))
    same_bytes = sum(1 for r in received if s2._reference(r).get('phase25_n_raw_sha256') is not None
                     and sha256_text(r['result'].get('raw')) == s2._reference(r).get('phase25_n_raw_sha256'))
    return {'received': len(received), 'same_policy_as_phase25_N_draw': same_policy,
            'byte_identical_to_phase25_N_draw': same_bytes,
            'same_policy_share': float(Fraction(same_policy, len(received))) if received else None,
            'same_prompt_re_measurement': bool(received) and Fraction(same_policy, len(received)) >= RE_MEASUREMENT_SHARE_MIN,
            'note': ('descriptive, decides nothing: how much of this arm re-draws the one policy Phase 25\'s N wrote '
                     'for the same prompt, i.e. how far this phase re-measures the draws that suggested its hypothesis; '
                     'at a share of 1/2 or more the statement must call this arm\'s duplicates-cut result a same-prompt '
                     're-measurement, not an independent confirmation')}


# ---------------------------------------------------------------- descriptive read-outs added in review round 1

def census_slot1_policies(requests):
    """Every census study's slot-1 policy hash (from the plan's references). Each was proposed as slot 1 on this
    source case, ran there and did not qualify (plan: populations.census_facts). A subset of the already-proposed set
    (review round 2), which also holds both slots of every in-scope v4 study."""
    return {(request.get('reference') or {}).get('slot1_policy_hash') for request in requests} - {None}


def policy_concentration(rows, proposed, certified, census=()):
    """Descriptive (review rounds 1 and 2). DISTINCT means only "not this study's own slot-1 policy"; this says what
    the DISTINCT draws are: how many policies, how concentrated across prompts, how many are ALREADY PROPOSED (a
    policy some in-scope v4 study proposed in either slot: `proposed`, the plan's populations.already_proposed) and how
    many are NOVEL, re-draws of a CERTIFIED policy on their own line (a subset of the already proposed ones), how many
    equal a census slot-1 policy (round 1's narrower set, kept for comparison), and WORKING draws per distinct WORKING
    policy."""
    received = [r for r in rows if r['received'] and r['c']]
    distinct = [r for r in received if r['c']['distinct']]
    prompts, draws = defaultdict(set), Counter()
    for r in distinct:
        prompts[r['c']['policy_hash']].add(r['request']['prompt_id'])
        draws[r['c']['policy_hash']] += 1
    largest = max(prompts, key=lambda h: (len(prompts[h]), draws[h], h)) if prompts else None

    def split(chosen):
        return {'distinct_draws': len(chosen), 'distinct_policies': len({r['c']['policy_hash'] for r in chosen}),
                'distinct_firing_draws': sum(1 for r in chosen if r['c']['distinct_firing']),
                'working_draws': sum(1 for r in chosen if r['c']['working']),
                'working_policies': len({r['c']['policy_hash'] for r in chosen if r['c']['working']}),
                'prompts_with_such_a_draw': len({r['request']['prompt_id'] for r in chosen})}
    working = Counter(r['c']['policy_hash'] for r in distinct if r['c']['working'])
    working_prompts = defaultdict(set)
    for r in distinct:
        if r['c']['working']:
            working_prompts[r['c']['policy_hash']].add(r['request']['prompt_id'])
    return {'received': len(received), 'distinct_draws': len(distinct), 'distinct_policies': len(prompts),
            'largest_policy_prompts': len(prompts[largest]) if largest else 0,
            'largest_policy_draws': draws[largest] if largest else 0,
            'policies_on_more_than_one_prompt': sum(1 for v in prompts.values() if len(v) > 1),
            'prompt_counts_of_the_five_largest_policies': sorted((len(v) for v in prompts.values()), reverse=True)[:5],
            'already_proposed_in_an_in_scope_v4_study': split([r for r in distinct if r['c']['policy_hash'] in proposed]),
            'novel': split([r for r in distinct if r['c']['policy_hash'] not in proposed]),
            'certified_policy_redraws': split([r for r in distinct if r['c']['policy_hash'] in certified]),
            'census_slot1_policy_redraws_round1_set': split([r for r in distinct if r['c']['policy_hash'] in census]),
            'working_per_distinct_working_policy': {
                'working_draws': sum(working.values()), 'working_policies': len(working),
                'draws_per_policy': (float(Fraction(sum(working.values()), len(working))) if working else None),
                'largest_working_policy_draws': max(working.values(), default=0),
                'largest_working_policy_prompts': max((len(v) for v in working_prompts.values()), default=0)}}


def linked_prompt_groups(rows):
    """Prompts linked (transitively) when they share a slot-1 policy or any policy drawn in these rows: the
    dependence a Wilson interval over draws ignores (review round 1: one policy supplied 7 of Phase 25's 26 N
    prompts). Returns {prompt_id: group id}."""
    parent = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item
    owner = {}
    for r in rows:
        prompt = r['request']['prompt_id']
        find(prompt)
        hashes = [s2._reference(r).get('slot1_policy_hash')]
        if r['received'] and r['c'] and r['c'].get('policy_hash'):
            hashes.append(r['c']['policy_hash'])
        for policy in hashes:
            if policy is None:
                continue
            if policy in owner:
                a, b = find(prompt), find(owner[policy])
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                owner[policy] = prompt
    return {prompt: find(prompt) for prompt in list(parent)}


def cluster_bootstrap(units, seed, resamples=None):
    """Percentile 95% interval (nearest rank) of sum(successes) / sum(draws) when whole clusters are resampled with
    replacement. units: [(successes, draws)] per cluster with at least one draw. Deterministic for a seed. Review
    round 2: withheld ([None, None]) below MIN_BOOTSTRAP_CLUSTERS clusters, where it is falsely precise (zero width at
    one cluster)."""
    resamples = BOOTSTRAP_RESAMPLES if resamples is None else resamples
    units = [unit for unit in units if unit[1] > 0]
    if len(units) < MIN_BOOTSTRAP_CLUSTERS:
        return [None, None]
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        chosen = rng.choices(units, k=len(units))
        values.append(sum(a for a, _ in chosen) / sum(b for _, b in chosen))
    values.sort()
    return [values[math.ceil(0.025 * resamples) - 1], values[math.ceil(0.975 * resamples) - 1]]


def _wilson_real(rate, n, z=1.959963984540054):
    """Wilson's interval for an observed rate over n observations (n need not equal the draws)."""
    if not n:
        return [None, None]
    denominator = 1 + z * z / n
    centre = (rate + z * z / (2 * n)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def clustered_rate(rows, success, label, *, arm, groups=None):
    """A per-draw rate over received draws with its Wilson interval over draws AND clustered intervals
    (descriptive, review round 1): a Wilson interval that counts each linked prompt group once (the most
    conservative, and the one a cost model uses: it stays informative when no success arrived, where a percentile
    bootstrap collapses to [0, 0]), and percentile bootstraps by prompt and by linked prompt group, each withheld
    (null) below MIN_BOOTSTRAP_CLUSTERS clusters (review round 2: at few groups a bootstrap is falsely precise)."""
    groups = linked_prompt_groups(rows) if groups is None else groups
    by_prompt, by_group = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in rows:
        if not r['received']:
            continue
        ok = int(bool(success(r)))
        prompt = r['request']['prompt_id']
        for bucket in (by_prompt[prompt], by_group[groups[prompt]]):
            bucket[0] += ok
            bucket[1] += 1
    k = sum(a for a, _ in by_prompt.values())
    n = sum(b for _, b in by_prompt.values())
    rate = k / n if n else None
    return {'successes': k, 'received': n, 'rate': rate, 'wilson95_over_draws': s2.wilson(k, n),
            'prompts': len(by_prompt), 'linked_prompt_groups': len(by_group),
            'bootstrap95_by_prompt': cluster_bootstrap([tuple(v) for _, v in sorted(by_prompt.items())],
                                                       f'{BOOTSTRAP_SEED}:{arm}:{label}:prompt'),
            'bootstrap95_by_linked_prompt_group': cluster_bootstrap([tuple(v) for _, v in sorted(by_group.items())],
                                                                    f'{BOOTSTRAP_SEED}:{arm}:{label}:group'),
            'wilson95_one_observation_per_linked_group': _wilson_real(rate, len(by_group)) if n else [None, None],
            'bootstrap_withheld': {'by_prompt': 0 < len(by_prompt) < MIN_BOOTSTRAP_CLUSTERS,
                                   'by_linked_prompt_group': 0 < len(by_group) < MIN_BOOTSTRAP_CLUSTERS},
            'interval_note': (f'a percentile bootstrap is withheld (null) below {MIN_BOOTSTRAP_CLUSTERS} clusters, where '
                              'it is falsely precise; a cost model uses wilson95_one_observation_per_linked_group, never '
                              'a bootstrap or the Wilson interval over draws')}


def clustered_rates(rows, proposed, arm):
    """The per-draw DISTINCT, novel DISTINCT, WORKING and novel WORKING rates of one arm, each with its clustered
    intervals. NOVEL means a policy no in-scope v4 study proposed (review round 2: `proposed` is the plan's
    already-proposed set). A later loop's cost model uses the novel figures, never DISTINCT alone."""
    groups = linked_prompt_groups(rows)
    novel = lambda r: r['c']['policy_hash'] not in proposed  # noqa: E731
    return {'distinct': clustered_rate(rows, lambda r: r['c']['distinct'], 'distinct', arm=arm, groups=groups),
            'distinct_novel': clustered_rate(rows, lambda r: r['c']['distinct'] and novel(r), 'distinct_novel',
                                             arm=arm, groups=groups),
            'working': clustered_rate(rows, lambda r: r['c']['working'], 'working', arm=arm, groups=groups),
            'working_novel': clustered_rate(rows, lambda r: r['c']['working'] and novel(r), 'working_novel',
                                            arm=arm, groups=groups)}


def invalid_split(rows):
    """Descriptive (review round 1): the invalid draws by what a study would do with them. Mechanic._generate sends
    a MechanicOutput (schema) failure back for one format repair; an empty response (the runtime raises
    EMPTY_FINAL_RESPONSE), a CandidatePolicy failure and a stale parent are not repaired (completion_study rejects
    them). I1 and I2 count first attempts, so they overstate what adoption would see."""
    counts = Counter()
    for r in rows:
        if not r['received'] or not r['c']:
            continue
        if r['c']['class'] == 'STALE_PARENT':
            counts['stale_parent'] += 1
        elif r['c']['class'] == 'INVALID':
            raw = (r['result'] or {}).get('raw')
            if not isinstance(raw, str) or not raw.strip():
                counts['empty'] += 1
            elif s2.parse_policy(raw) is None:
                counts['schema'] += 1
            else:
                counts['candidate_policy'] += 1
    received = sum(1 for r in rows if r['received'])
    unrepaired = counts['empty'] + counts['candidate_policy'] + counts['stale_parent']
    return {'received': received, 'invalid': counts['schema'] + unrepaired,
            'schema_failure_a_study_sends_back_for_one_format_repair': counts['schema'],
            'not_repaired_by_a_study': {'empty': counts['empty'], 'candidate_policy': counts['candidate_policy'],
                                        'stale_parent': counts['stale_parent'], 'total': unrepaired},
            'not_repaired_rate_received': float(Fraction(unrepaired, received)) if received else None}


def compute_readouts(requests, results, *, already_proposed, partial_lines_skipped=0, run_end=None):
    """The declared read-outs and the descriptive figures. `already_proposed` is the plan's
    populations.already_proposed (review round 2); it moves no decision, only the novel and certified figures."""
    proposed, certified = proposed_sets(already_proposed)
    rows = s2.classify_results(requests, results)
    by_arm = defaultdict(list)
    for row in rows:
        by_arm[row['request']['arm']].append(row)
    summaries = {arm: s2.arm_summary(by_arm[arm]) for arm in ARMS}
    permitted, why = s2.fallback_permitted(run_end)
    decisions = {}
    for arm in TREATED_ARMS:
        full = arm_decision(by_arm[arm], by_arm['C'], arm)
        fallback = (arm_decision(_round1(by_arm[arm]), _round1(by_arm['C']), arm,
                                 working_gain_min=WORKING_SHARE_GAIN_MIN_ROUND1)
                    if full['decision'] == 'INCOMPLETE' and permitted else None)
        decisions[arm] = {**full, 'round1_fallback': fallback, 'declared': _declared(full, fallback)}
    n, nt = summaries['N'], summaries['NT']
    census = census_slot1_policies(requests)
    invalid_by_arm = {arm: invalid_split(by_arm[arm]) for arm in ARMS}
    for arm in TREATED_ARMS:
        x_rate, c_rate = invalid_by_arm[arm]['not_repaired_rate_received'], invalid_by_arm['C']['not_repaired_rate_received']
        invalid_by_arm[arm]['not_repaired_excess_over_C'] = (x_rate - c_rate if None not in (x_rate, c_rate) else None)
    descriptive = {
        'duplicates_of_slot1': {arm: {'duplicate': summaries[arm]['duplicate'], 'received': summaries[arm]['received'],
                                      'wilson95': s2.wilson(summaries[arm]['duplicate'], summaries[arm]['received']),
                                      'prompts_with_a_duplicate_draw': len({
                                          r['request']['prompt_id'] for r in by_arm[arm]
                                          if r['received'] and r['c']['duplicate_of_slot1']}),
                                      'prompts_with_a_received_draw': len({
                                          r['request']['prompt_id'] for r in by_arm[arm] if r['received']})}
                                for arm in ARMS},
        'N_against_NT_never_a_decision': {
            'distinct_difference_newcombe95': s2.newcombe(nt['distinct'], nt['received'], n['distinct'], n['received']),
            'working_difference_newcombe95': s2.newcombe(nt['working'], nt['received'], n['working'], n['received']),
            'invalid_difference_newcombe95': s2.newcombe(nt['invalid'], nt['received'], n['invalid'], n['received']),
            'sign_test_working_NT_above_N': s2.paired_sign(by_arm['NT'], by_arm['N'], 'working', greater='x'),
            'working_share_NT_minus_N': s2.working_share(by_arm['NT'], by_arm['N'])},
        'phase25_dependence': {arm: dependence_readout(by_arm[arm]) for arm in TREATED_ARMS},
        # Review rounds 1 and 2 (descriptive; stated before any Phase 29 data).
        'census_slot1_policies': len(census),
        'already_proposed_policies': len(proposed), 'certified_policies': len(certified),
        'policy_concentration': {arm: policy_concentration(by_arm[arm], proposed, certified, census) for arm in ARMS},
        'per_draw_rates_with_clustered_intervals': {arm: clustered_rates(by_arm[arm], proposed, arm) for arm in ARMS},
        'invalid_by_what_a_study_would_do': invalid_by_arm,
        # Read on the declared basis (the round-1 fallback's draws when it decides).
        'calibrated_range': {arm: (decisions[arm]['round1_fallback'] or decisions[arm])['working'][
            'calibrated_range_descriptive'] for arm in TREATED_ARMS},
    }
    served = Counter(r['result'].get('served_model') for r in rows if r['result'] and r['result'].get('status') == 'ok')

    def text(arm):
        declared = decisions[arm]['declared']
        basis = ' (round 1 only)' if declared['basis'] == 'round_1_only' else ''
        concentration = descriptive['policy_concentration'][arm]
        certified_redraws = concentration['certified_policy_redraws']
        return (f'{arm} {declared["decision"]}{basis} (duplicates cut {declared["duplicates_cut"]}, yield gain '
                f'{declared["yield_gain"]}; failed: {", ".join(declared["failed"]) or "-"}; descriptive: '
                f'{concentration["distinct_draws"]} of {concentration["received"]} received draws differ from their '
                f'own slot 1, {concentration["novel"]["distinct_draws"]} of them novel (a policy no in-scope v4 study '
                f'proposed) and {concentration["already_proposed_in_an_in_scope_v4_study"]["distinct_draws"]} a policy '
                f'an in-scope v4 study already proposed; WORKING draws '
                f'{concentration["working_per_distinct_working_policy"]["working_draws"]} (novel '
                f'{concentration["novel"]["working_draws"]}), distinct WORKING policies '
                f'{concentration["working_per_distinct_working_policy"]["working_policies"]}; re-draws of a certified '
                f'policy: {certified_redraws["distinct_draws"]} draws, {certified_redraws["working_draws"]} of them '
                'WORKING)')
    recommended = [arm for arm in TREATED_ARMS if decisions[arm]['declared']['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP']
    statement = (('recommended for a later loop\'s own declaration: ' + ', '.join(recommended) + '. ') if recommended
                 else 'no arm is recommended. ') + '; '.join(text(arm) for arm in TREATED_ARMS)
    notes = []
    for arm in TREATED_ARMS:
        dependence = descriptive['phase25_dependence'][arm]
        if dependence['same_prompt_re_measurement']:
            notes.append(f'{arm}\'s duplicates-cut result is a same-prompt re-measurement of Phase 25\'s N draws, not an '
                         f'independent confirmation ({dependence["same_policy_as_phase25_N_draw"]} of '
                         f'{dependence["received"]} received draws re-draw the policy Phase 25\'s N wrote for the '
                         'same prompt)')
        # The calibrated-range caveat qualifies a SHOWN working claim (its false-alarm rate); it says nothing otherwise.
        span = descriptive['calibrated_range'][arm]
        if decisions[arm]['declared']['verdicts']['working'] == 'SHOWN' and span['reading'] != 'within':
            if span['reading'] == 'outside':
                notes.append(f'{arm}\'s working claim is outside its calibrated range: C\'s firing rate '
                             f'{span["C_rate"]:.3f} is above 0.10')
            elif span['reading'] == 'not_confirmed':
                notes.append(f'{arm}\'s working claim: its calibrated range (common firing at most 0.10) is not '
                             f'confirmed (C\'s firing rate {span["C_rate"]:.3f}, its 95% upper bound '
                             f'{span["C_wilson95_upper"]:.3f})')
            else:
                notes.append(f'{arm}\'s working claim: C received nothing, so its calibrated range cannot be read')
    notes.append('DISTINCT means only "not this study\'s own slot 1", not "new"; novel means none of the '
                 f'{len(proposed)} policies the in-scope v4 studies proposed in either slot, and a re-draw of one of '
                 f'the {len(certified)} certified policies is not new')
    statement += '. Wording rules: ' + '; '.join(notes) + '.'
    return {'schema_version': READOUT_SCHEMA, 'requests_planned': len(requests),
            'requests_received': sum(r['received'] for r in rows), 'partial_lines_skipped': partial_lines_skipped,
            'run_end': {**(run_end or {}), 'round1_fallback_permitted': permitted, 'reason': why},
            'arms': summaries, 'decisions': decisions, 'descriptive': descriptive,
            'determinism': s2.determinism_readout({arm: by_arm[arm] for arm in ARMS}),
            'provider': {'served_model': dict(served),
                         'measured_input_tokens': sum((r['result'] or {}).get('input_tokens') or 0 for r in rows),
                         'measured_output_tokens': sum((r['result'] or {}).get('output_tokens') or 0 for r in rows)},
            'statement': statement}


# ---------------------------------------------------------------- simulation ($0): false alarms and power

SIM_PROMPTS = 26
SIM_SLOT1_FIRING_PROMPTS = s2.SIM_SLOT1_FIRING_PROMPTS
SIM_INVALID = s2.SIM_INVALID
NUMBERS_SEED = 'faultlab-phase29-protocol-numbers'


def sim_draw(rng, prompt, repeat, *, distinct_p, firing_p, invalid=SIM_INVALID,
             harm_firing=s2.SIM_HARMFUL_FIRING, harm_silent=s2.SIM_HARMFUL_NOT_FIRING):
    """Phase 25's simulated_draw with the harm rates as parameters (the same random calls in the same order, so
    at the default rates it returns exactly what s2.simulated_draw returns; a test checks this)."""
    is_invalid = rng.random() < invalid
    distinct = not is_invalid and rng.random() < distinct_p
    firing = distinct and rng.random() < firing_p
    harmful = distinct and rng.random() < float(harm_firing if firing else harm_silent)
    audit = None if is_invalid else {'harmful': harmful, 'step_present': firing, 'dead_step': False,
                                     'step_fires': firing, 'premature_defer': harmful,
                                     'stops_first_confirmation': False, 'orders_retry': False}
    c = {'class': 'INVALID' if is_invalid else 'CANDIDATE', 'distinct': distinct,
         'duplicate_of_slot1': not is_invalid and not distinct, 'distinct_firing': firing,
         'working': firing and not harmful, 'policy_hash': None, 'byte_identical_to_slot1': False,
         'rules_text_identical_to_slot1': False, 'audit': audit}
    reference = {'slot1_step_fires': prompt < SIM_SLOT1_FIRING_PROMPTS, 'slot1_policy_hash': f'p{prompt}'}
    return {'request': {'prompt_id': f'p{prompt}', 'repeat': repeat, 'reference': reference}, 'result': {},
            'received': True, 'c': c}


def prompt_probability(rng, mean, rho):
    """A per-prompt probability with mean `mean` and intra-prompt correlation rho (Beta), or the mean at rho 0."""
    if mean <= 0:
        return 0.0
    if mean >= 1:
        return 1.0
    if rho <= 0:
        return mean
    scale = (1 - rho) / rho
    return rng.betavariate(mean * scale, (1 - mean) * scale)


def sim_rows(rng, model, d, w, *, repeats=REPEATS, invalid=SIM_INVALID, harm_firing=s2.SIM_HARMFUL_FIRING):
    """One arm's rows. model ('beta', rho): per-prompt distinct and firing probabilities drawn with correlation
    rho; ('copy', q): each prompt's first draw at the mean rates, each later repeat a copy of it (class, WORKING and
    harm included) with probability q, else an independent draw (Phase 25 review round 3's repeat model)."""
    kind, value = model
    valid = 1 - invalid
    rows = []
    for p in range(SIM_PROMPTS):
        if kind == 'beta':
            pd = prompt_probability(rng, min(1.0, d / valid), value)
            pw = prompt_probability(rng, (w / d) if d > 0 else 0.0, value)
            rows.extend(sim_draw(rng, p, r, distinct_p=pd, firing_p=pw, invalid=invalid, harm_firing=harm_firing)
                        for r in range(repeats))
        elif kind == 'copy':
            pd, pw = min(1.0, d / valid), (w / d) if d > 0 else 0.0
            first = sim_draw(rng, p, 0, distinct_p=pd, firing_p=pw, invalid=invalid, harm_firing=harm_firing)
            rows.append(first)
            for r in range(1, repeats):
                rows.append({**first, 'request': {**first['request'], 'repeat': r}} if rng.random() < value
                            else sim_draw(rng, p, r, distinct_p=pd, firing_p=pw, invalid=invalid, harm_firing=harm_firing))
        else:
            raise ValueError(f'unknown model {model!r}')
    return rows


def shared_rows(rng, propensities, d, rho, *, repeats=REPEATS):
    """The shared-effect model: prompt p fires with the given per-draw propensity (among valid draws) in both arms;
    firing draws are distinct; the rest of the distinct rate makes the unconditional rate d."""
    valid = 1 - SIM_INVALID
    rows = []
    for p, q in enumerate(propensities):
        target = min(0.999, d / valid)
        rest = prompt_probability(rng, max(1e-6, (target - q) / (1 - q)), rho) if target > q else 0.0
        distinct_p = q + (1 - q) * rest
        firing_p = q / distinct_p if distinct_p > 0 else 0.0
        rows.extend(sim_draw(rng, p, r, distinct_p=distinct_p, firing_p=firing_p) for r in range(repeats))
    return rows


# (C's model, X's model). N is at temperature 0 like C, so both may repeat; NT at 0.4 may vary more than C.
SCENARIOS = {
    'independent (rho_C 0, rho_X 0)': (('beta', 0.0), ('beta', 0.0)),
    'both mildly clustered (rho_C 0.5, rho_X 0.2)': (('beta', 0.5), ('beta', 0.2)),
    'both clustered (rho_C 0.8, rho_X 0.8)': (('beta', 0.8), ('beta', 0.8)),
    'C clustered, X not (rho_C 0.8, rho_X 0.0)': (('beta', 0.8), ('beta', 0.0)),
    'C clustered, X mildly (rho_C 0.8, rho_X 0.2)': (('beta', 0.8), ('beta', 0.2)),
    'X clustered, C not (rho_C 0.0, rho_X 0.8)': (('beta', 0.0), ('beta', 0.8)),
    'both arms repeat (q 0.9)': (('copy', 0.9), ('copy', 0.9)),
    'both arms repeat (q 1.0)': (('copy', 1.0), ('copy', 1.0)),
    'C repeats (q 0.9), X not (rho_X 0.0)': (('copy', 0.9), ('beta', 0.0)),
    'C repeats (q 1.0), X not (rho_X 0.0)': (('copy', 1.0), ('beta', 0.0)),
    'C repeats (q 1.0), X mildly (rho_X 0.2)': (('copy', 1.0), ('beta', 0.2)),
    'X repeats (q 1.0), C not (rho_C 0.0)': (('beta', 0.0), ('copy', 1.0)),
}
# The yield null: X far more distinct than C (hiding the prior candidate), its step firing no more often.
YIELD_NULL_GRID = ((0.30, 0.04, 0.80, 0.04), (0.30, 0.04, 0.95, 0.04), (0.30, 0.10, 0.80, 0.10),
                   (0.30, 0.10, 0.95, 0.10))
OUTSIDE_GRID = ((0.30, 0.15, 0.95, 0.15), (0.30, 0.20, 0.95, 0.20))
SHARED_RHOS = (0.0, 0.5, 0.8)
POWER_SCENARIOS = {
    'N-like: both at temperature 0 and both repeat (q 0.9)': (('copy', 0.9), ('copy', 0.9)),
    'N-like, X varies more (C q 0.9, X rho 0.5)': (('copy', 0.9), ('beta', 0.5)),
    'NT-like: C repeats (q 0.9), X mildly clustered (rho 0.2)': (('copy', 0.9), ('beta', 0.2)),
    'independent (rho 0)': (('beta', 0.0), ('beta', 0.0)),
}
POWER_C = (0.30, 0.02)
POWER_X_FIRING = (0.02, 0.04, 0.08, 0.12, 0.16, 0.20, 0.25, 0.30, 0.40)
POWER_X_DISTINCT = 0.95


def _working_outcome(x_rows, c_rows):
    share = s2.working_share(x_rows, c_rows)
    p = s2.sign_test_greater(share['prompts_favouring'], share['prompts_against'])
    return Fraction(share['gain_exact']), p < POSITIVE_ALPHA


def yield_null(rng, repeats, simulations):
    """P(working SHOWN) for each candidate minimum under the yield null; the smallest minimum whose worst cell is
    at most FALSE_ALARM_TARGET is chosen. Cells at common firing rates 0.15 and 0.20 are reported, not chosen on."""
    candidates = [Fraction(i, repeats) for i in range(1, 10 * repeats + 1)]

    def cell(name, d_c, w_c, d_x, w_x, draw):
        outcomes = [draw() for _ in range(simulations)]
        return {'model': name, 'd_c': d_c, 'w_c': w_c, 'd_x': d_x, 'w_x': w_x,
                'p_sign_test_alone': round(sum(ok for _, ok in outcomes) / simulations, 4),
                'mean_share_gain': round(float(sum(g for g, _ in outcomes) / simulations), 4),
                'p_working_shown_by_min': {str(k): round(sum(1 for g, ok in outcomes if ok and g >= k) / simulations, 4)
                                           for k in candidates}}

    def cells(grid, shared_ws):
        out = []
        for name, (model_c, model_x) in SCENARIOS.items():
            for d_c, w_c, d_x, w_x in grid:
                out.append(cell(name, d_c, w_c, d_x, w_x, lambda: _working_outcome(
                    sim_rows(rng, model_x, d_x, w_x, repeats=repeats), sim_rows(rng, model_c, d_c, w_c, repeats=repeats))))
        for rho in SHARED_RHOS:
            for w in shared_ws:
                for d_x in (0.80, 0.95):
                    def draw(rho=rho, w=w, d_x=d_x):
                        propensities = [prompt_probability(rng, w / (1 - SIM_INVALID), rho) for _ in range(SIM_PROMPTS)]
                        return _working_outcome(shared_rows(rng, propensities, d_x, rho, repeats=repeats),
                                                shared_rows(rng, propensities, 0.30, rho, repeats=repeats))
                    out.append(cell(f'shared firing propensity (rho {rho})', 0.30, w, d_x, w, draw))
        return out
    table = cells(YIELD_NULL_GRID, (0.04, 0.10))
    worst = {str(k): max(c['p_working_shown_by_min'][str(k)] for c in table) for k in candidates}
    chosen = next(k for k in candidates if worst[str(k)] <= FALSE_ALARM_TARGET)
    outside = cells(OUTSIDE_GRID, (0.15, 0.20))
    for c in outside:
        c['p_working_shown_by_min'] = {str(chosen): c['p_working_shown_by_min'][str(chosen)]}
    return {'simulations_per_cell': simulations, 'repeats': repeats, 'cells': table,
            'worst_cell_by_min': worst, 'worst_sign_test_alone': max(c['p_sign_test_alone'] for c in table),
            'smallest_min_with_worst_cell_at_most_target': str(chosen), 'target': FALSE_ALARM_TARGET,
            'worst_cell_at_the_chosen_minimum': worst[str(chosen)],
            'outside_the_grid_at_the_chosen_minimum_descriptive': outside,
            'outside_the_grid_worst_cell_descriptive': max(c['p_working_shown_by_min'][str(chosen)] for c in outside)}


def power_table(rng, simulations, *, repeats=REPEATS, working_gain_min=None, scenarios=None, firing=POWER_X_FIRING):
    """P(each declared verdict) under alternatives: C at (0.30 distinct, 0.02 firing), X at 0.95 distinct and each
    firing rate; 3% invalid in both; harm at the store's rates (a firing draw is harmful with probability 3/9, so
    WORKING is about 2/3 of firing)."""
    table = []
    for name, (model_c, model_x) in (scenarios or POWER_SCENARIOS).items():
        for w_x in firing:
            counts = Counter()
            for _ in range(simulations):
                result = arm_decision(sim_rows(rng, model_x, POWER_X_DISTINCT, w_x, repeats=repeats),
                                      sim_rows(rng, model_c, POWER_C[0], POWER_C[1], repeats=repeats), 'X',
                                      working_gain_min=working_gain_min)
                counts['recommend'] += result['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP'
                counts['duplicates_cut'] += result['duplicates_cut'] == 'SHOWN'
                counts['yield_gain'] += result['yield_gain'] == 'SHOWN'
                counts['working'] += result['verdicts']['working'] == 'SHOWN'
                counts['invalid_fail'] += result['verdicts']['invalid'] == 'FAIL'
                counts['harmful_fail'] += result['verdicts']['harmful'] == 'FAIL'
            table.append({'scenario': name, 'd_c': POWER_C[0], 'w_c': POWER_C[1], 'd_x': POWER_X_DISTINCT, 'w_x': w_x,
                          'x_working_per_draw_approx': round(w_x * (1 - float(s2.SIM_HARMFUL_FIRING)), 4),
                          **{f'p_{k}': round(counts[k] / simulations, 3) for k in (
                              'recommend', 'duplicates_cut', 'yield_gain', 'working', 'invalid_fail', 'harmful_fail')}})
    return table


INVALID_GRID = (0.0, 0.03, 0.05, 0.08, 0.115, 0.15)


def invalid_guard_table(rng, simulations):
    """P(invalid guard FAIL) by X's per-draw invalid rate, C at 0 (Phase 25's C) and at 0.03."""
    scenarios = {'independent': (('beta', 0.0), ('beta', 0.0)),
                 'both repeat (q 0.9)': (('copy', 0.9), ('copy', 0.9)),
                 'C repeats (q 0.9), X mildly (rho 0.2)': (('copy', 0.9), ('beta', 0.2))}
    table = []
    for name, (model_c, model_x) in scenarios.items():
        for inv_c in (0.0, 0.03):
            for inv_x in INVALID_GRID:
                fails = sum(arm_decision(sim_rows(rng, model_x, 0.95, 0.04, invalid=inv_x),
                                         sim_rows(rng, model_c, 0.30, 0.02, invalid=inv_c), 'X')['verdicts']['invalid']
                            == 'FAIL' for _ in range(simulations))
                table.append({'scenario': name, 'invalid_c': inv_c, 'invalid_x': inv_x,
                              'p_invalid_guard_fail': round(fails / simulations, 3)})
    return table


def harm_guard_table(rng, simulations):
    """P(harmful guard FAIL) by the share of X's firing draws that are harmful (C at the store's 3/9)."""
    table = []
    for name, (model_c, model_x) in {'independent': (('beta', 0.0), ('beta', 0.0)),
                                     'both repeat (q 0.9)': (('copy', 0.9), ('copy', 0.9))}.items():
        for w_x in (0.10, 0.20):
            for harm in (Fraction(3, 9), Fraction(1, 2), Fraction(2, 3), Fraction(1)):
                counts = Counter()
                for _ in range(simulations):
                    result = arm_decision(sim_rows(rng, model_x, 0.95, w_x, harm_firing=harm),
                                          sim_rows(rng, model_c, 0.30, 0.04), 'X')
                    counts['fail'] += result['verdicts']['harmful'] == 'FAIL'
                    counts['cap'] += not result['conditions']['harmful_share_of_firing_at_most_0.50']
                    counts['fisher'] += not result['conditions']['harmful_not_shown_above_C_at_0.05']
                table.append({'scenario': name, 'w_x': w_x, 'x_harmful_share_of_firing': str(harm),
                              'p_harmful_guard_fail': round(counts['fail'] / simulations, 3),
                              'p_cap_fails': round(counts['cap'] / simulations, 3),
                              'p_fisher_fails': round(counts['fisher'] / simulations, 3)})
    return table


def distinct_table(rng, simulations):
    """P(duplicates cut SHOWN) by X's distinct rate (C at 0.30), both repeating (q 0.9) and independent."""
    table = []
    for name, (model_c, model_x) in {'independent': (('beta', 0.0), ('beta', 0.0)),
                                     'both repeat (q 0.9)': (('copy', 0.9), ('copy', 0.9))}.items():
        for d_x in (0.40, 0.60, 0.70, 0.80, 0.95):
            shown = sum(arm_decision(sim_rows(rng, model_x, d_x, 0.04), sim_rows(rng, model_c, 0.30, 0.02), 'X')
                        ['duplicates_cut'] == 'SHOWN' for _ in range(simulations))
            table.append({'scenario': name, 'd_c': 0.30, 'd_x': d_x, 'p_duplicates_cut': round(shown / simulations, 3)})
    return table


def boundaries():
    def smallest(predicate, upto):
        return next((k for k in range(upto + 1) if predicate(k)), None)

    def at(n):
        return {'planned_draws_per_arm': n,
                'complete_min_received': smallest(lambda k: Fraction(k, n) >= COMPLETE_MIN, n),
                'distinct_X_min': smallest(lambda k: Fraction(k, n) >= DISTINCT_MIN, n),
                'distinct_gain_min_draws': smallest(lambda k: Fraction(k, n) >= DISTINCT_GAIN_MIN, n),
                'invalid_excess_max_draws_at_full_receipt': max(k for k in range(n + 1)
                                                                if Fraction(k, n) <= INVALID_MARGIN)}
    sign = {}
    for alpha in (POSITIVE_ALPHA, GUARD_ALPHA):
        sign[str(alpha)] = {}
        for untied in range(1, SIM_PROMPTS + 1):
            k = smallest(lambda f: s2.sign_test_greater(f, untied - f) < alpha, untied)
            sign[str(alpha)][untied] = None if k is None else {'min_favouring': k, 'p': round(
                s2.sign_test_greater(k, untied - k), 5)}
    return {'all_rounds': at(SIM_PROMPTS * REPEATS), 'round1_fallback': at(SIM_PROMPTS),
            'eligible_prompts_for_working': SIM_PROMPTS - SIM_SLOT1_FIRING_PROMPTS,
            'sign_test_min_favouring_by_untied_prompts': sign,
            'harmful_of_firing_max_by_firing_draws': {f: max(k for k in range(f + 1)
                                                             if Fraction(k, f) <= HARMFUL_FIRING_SHARE_MAX)
                                                      for f in (1, 2, 3, 4, 6, 9, 12)}}


def protocol_numbers(*, simulations=2000, null_simulations=4000, seed=NUMBERS_SEED):
    """Every false-alarm, power and boundary figure the protocol quotes, computed with this harness's own decision
    code ($0: no provider call, no .env read, no store read)."""
    rng = random.Random(seed)
    null_full = yield_null(rng, REPEATS, null_simulations)
    null_round1 = yield_null(rng, 1, null_simulations)
    chosen = Fraction(null_full['smallest_min_with_worst_cell_at_most_target'])
    chosen_round1 = Fraction(null_round1['smallest_min_with_worst_cell_at_most_target'])
    return {'schema': NUMBERS_SCHEMA, 'seed': seed, 'harness_sha256': sha256_file(__file__),
            'thresholds': thresholds(),
            'models': ('26 prompts, 2 of them with a slot-1 policy whose step fires (left out of the working share); 3 '
                       'draws per prompt per arm (1 in the round-1 fallback); each draw INVALID with probability 0.03 '
                       'unless stated; otherwise DISTINCT with the arm\'s rate d and FIRING with its unconditional '
                       'rate w; a firing draw harmful with probability 3/9 and a distinct non-firing draw 1/26 (the '
                       'store\'s rates, Phase 25); per-prompt Beta clustering (rho) or the repeat model (q), per '
                       'arm; the shared-effect model gives both arms the same per-prompt firing propensity'),
            'boundaries': boundaries(),
            'yield_null_all_rounds': null_full, 'yield_null_round1_fallback': null_round1,
            'harness_minimum_is_the_chosen_one': {'all_rounds': chosen == WORKING_SHARE_GAIN_MIN,
                                                  'round1_fallback': chosen_round1 == WORKING_SHARE_GAIN_MIN_ROUND1},
            'power_all_rounds': power_table(rng, simulations),
            'power_round1_fallback': power_table(rng, simulations, repeats=1,
                                                 working_gain_min=WORKING_SHARE_GAIN_MIN_ROUND1,
                                                 scenarios={'one draw per prompt': (('beta', 0.0), ('beta', 0.0))}),
            'invalid_guard': invalid_guard_table(rng, simulations),
            'harm_guard': harm_guard_table(rng, simulations),
            'duplicates_cut': distinct_table(rng, simulations)}


# ---------------------------------------------------------------- guards: output, claims, other paid runs

def _final(manifest):
    return manifest.get('status') in FINAL_STATUSES and bool(manifest.get('ended_at'))


def claimed_output(artifacts, out):
    """The output directory a claim of this phase names: artifacts/phase29-<date>/<name>, relative, nothing else.
    '.' and '..' are refused although RUN_PATH_PART matches them (review round 1, as Phase 25's own rule), so a
    hand-written claim can never lead --finalize-abandoned outside a run directory."""
    parts = pathlib.PurePosixPath(out).parts if isinstance(out, str) and out else ()
    if (len(parts) != 3 or parts[0] != 'artifacts' or not parts[1].startswith(PHASE_PREFIX) or parts[1] == CLAIM_DIR
            or not all(RUN_PATH_PART.fullmatch(part) for part in parts[1:])
            or any(part in ('.', '..') for part in parts[1:])):
        return None
    return pathlib.Path(artifacts).parent / parts[0] / parts[1] / parts[2]


def _charge(manifest, path):
    charged = manifest.get('charged_upper_bound')
    if type(charged) not in (int, float) or not math.isfinite(charged) or charged < 0:
        raise PlanningError(f'An earlier live run does not state a readable charged_upper_bound ({path}); '
                            'the phase cap cannot be applied. Investigate before any run')
    return charged


def live_run_records(artifacts):
    """Every earlier Phase 29 live run; refuses unless each is final and delivered nothing. Claims are matched to
    the manifest in the directory each claim names, never by count."""
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
            raise PlanningError(f'{claim.name} cannot be read or names no valid output directory; investigate before any run')
        manifest = output / MANIFEST_NAME
        if not manifest.is_file():
            raise PlanningError(f'{claim.name} claims a live run with no manifest; it may be starting, or it crashed '
                                'before writing one. If its process is gone, close it at $0 with '
                                f'--finalize-abandoned artifacts/{CLAIM_DIR}/{claim.name}')
        manifests.setdefault(manifest.resolve(), manifest)
    undelivered = []
    for _, path in sorted(manifests.items()):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError):
            raise PlanningError(f'An earlier live manifest cannot be read ({path}); investigate before any run') from None
        if not isinstance(manifest, dict):
            raise PlanningError(f'An earlier live manifest cannot be read ({path}); investigate before any run')
        if not _final(manifest):
            raise PlanningError(f'An earlier live run is not final ({path}); it may still be running. If its process '
                                'is gone, close its claim at $0 with --finalize-abandoned')
        delivered = delivered_generations(manifest)
        if delivered is None or delivered > 0:
            raise PlanningError(f'A live Phase 29 run already exists ({path}); a second draw would be '
                                'repeat-until-lucky and needs its own declared phase')
        undelivered.append({'manifest': str(path.relative_to(artifacts.parent)),
                            'charged_upper_bound': _charge(manifest, path)})
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


# A run directory's two path parts use only the characters every sibling guard accepts when it follows a claim's
# `out` (Phase 26 review round 2), so this phase's claims never block a sibling forever.
RUN_PATH_PART = re.compile(r'[A-Za-z0-9._-]+')


def check_output(out, *, root=None, live=True):
    """A new directory exactly artifacts/phase29-<date>/<name>, never an existing one; one delivering live run."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    out = pathlib.Path(out)
    out = (out if out.is_absolute() else root / out).resolve()
    try:
        relative = out.relative_to(artifacts)
    except ValueError:
        raise PlanningError(f'The output directory must be under artifacts/{PHASE_PREFIX}<date>/') from None
    if (len(relative.parts) != 2 or not relative.parts[0].startswith(PHASE_PREFIX) or relative.parts[0] == CLAIM_DIR
            or not all(RUN_PATH_PART.fullmatch(part) for part in relative.parts)):
        raise PlanningError(f'The output directory must be exactly artifacts/{PHASE_PREFIX}<date>/<name>, both parts '
                            'using only letters, digits, ".", "_" and "-"')
    if out.exists():
        raise PlanningError(f'{out} exists; a run is never resumed or overwritten - use a new directory')
    if live:
        earlier_live_runs(artifacts)
    return out


def take_claim(out, plan_hash_value, harness, *, root=None, spend_cap=None, expected_earlier=None):
    """Atomically claim the next live run (written in full to a private file, then hard-linked to its name, which
    fails if the name exists). Never deleted."""
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
                       'claimed_at': datetime.now(timezone.utc).isoformat(),
                       'earlier_undelivered_runs': earlier}, handle, indent=2)
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
        command = subprocess.run(['ps', '-ww', '-o', 'command=', '-p', str(pid)], capture_output=True,
                                 text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return True
    return not command.strip() or 'slot2_hidden_probe' in command


def finalize_abandoned(claim, *, root=None, alive=None):
    """Close, at $0, a claimed run whose process died before its manifest became final (as Phase 25). Refuses
    while the claim's process may be alive and for a final run. Charges every recorded attempt, plus
    ABANDONED_IN_FLIGHT_ATTEMPTS when the run died while RUNNING. A later run is allowed only if nothing was
    delivered."""
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
        raise PlanningError(f'The process that took {path.name} (pid {pid}) may still be running. Stop it with '
                            f'kill -TERM {pid} and let it write its final manifest; nothing was changed')
    manifest_path = output / MANIFEST_NAME
    existing = None
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
        except (OSError, ValueError):
            existing = None
        if not isinstance(existing, dict):
            raise PlanningError(f'{manifest_path} cannot be read; inspect it and move it aside by hand, then re-run')
        if _final(existing):
            raise PlanningError(f'{manifest_path} is already final; there is nothing to finalize')
    responses = output / 'responses.jsonl'
    results, partial = load_results(responses) if responses.exists() else ([], 0)
    previous_status = existing.get('status') if existing else None
    in_flight = 0 if previous_status in (None, 'STARTING') else ABANDONED_IN_FLIGHT_ATTEMPTS
    recorded_attempts = sum(len(r.get('attempts') or []) if isinstance(r, dict) else 2 for r in results)
    prior_attempts = existing.get('attempts') if existing else 0
    attempts = max(prior_attempts if type(prior_attempts) is int else 0, recorded_attempts) + in_flight
    prior = delivered_generations(existing) if existing else 0
    delivered = sum(entry_delivered(r) for r in results)
    now = datetime.now(timezone.utc).isoformat()
    manifest = dict(existing) if existing else {
        'schema_version': SCHEMA, 'mode': 'live', 'plan_hash': record.get('plan_hash'),
        'harness_sha256': record.get('harness_sha256'), 'claim': str(path.relative_to(artifacts.parent)),
        'pid': pid, 'spend_cap': record.get('spend_cap'), 'started_at': None, 'traceback': None}
    manifest.update({
        'status': 'ABORTED', 'stop_reason': 'abandoned', 'ended_at': now,
        'requests_done': sum(1 for r in results if not (isinstance(r, dict) and r.get('resend'))),
        'resend_lines': sum(1 for r in results if isinstance(r, dict) and r.get('resend')),
        'statuses': dict(sorted(Counter(str(r.get('status')) if isinstance(r, dict) else 'unreadable'
                                        for r in results).items())),
        'generations_delivered': None if prior is None else max(prior, delivered),
        'attempts': attempts,
        'charged_upper_bound': attempts * SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND) / 1_000_000,
        'finalized_abandoned': {
            'at': now, 'claim': str(path.relative_to(artifacts.parent)), 'pid': pid, 'pid_alive': False,
            'previous_status': previous_status, 'responses_lines': len(results),
            'partial_lines_skipped': partial, 'unrecorded_in_flight_attempts_charged': in_flight}})
    output.mkdir(parents=True, exist_ok=True)
    write_json(manifest_path, manifest)
    return manifest_path, manifest


# One paid run at a time. Other phases' run manifests, by exact names and depths for closed phases and by wildcard
# at run depth for the phases being built beside this one (28, 30, 31: names unknown here). Nothing under phase22-*
# (the heldout-2 seal) or phase24-* (its held-out check) is listed, and a file named heldout-manifest.json is
# skipped wherever manifests are read.
OTHER_RUN_MANIFESTS = (('phase20', 'phase20-*/*/dev-probe-manifest.json'),
                       ('phase21', 'phase21-*/*/lapse-probe-manifest.json'),
                       ('phase23', 'phase23-*/full-loop-manifest.json'),
                       ('phase25', 'phase25-*/*/slot2-probe-manifest.json'),
                       ('phase26', 'phase26-*/*/gap-probe-manifest.json'),
                       ('phase27', 'phase27-*/*/report-word-probe-manifest.json'),
                       ('phase28/30/31', 'phase28-*/*manifest*.json'),
                       ('phase28/30/31', 'phase28-*/*/*manifest*.json'),
                       ('phase28/30/31', 'phase3[01]-*/*manifest*.json'),
                       ('phase28/30/31', 'phase3[01]-*/*/*manifest*.json'))
OTHER_CLAIM_DIRS = ('phase20-live-claims', 'phase21-live-claims', 'phase23-live-claims', 'phase25-live-claims',
                    'phase26-live-claims', 'phase27-live-claims', 'phase28-live-claims', 'phase30-live-claims',
                    'phase31-live-claims')
HELDOUT_MANIFEST_NAME = 'heldout-manifest.json'
OTHER_CLAIMED_RUN = re.compile(r'artifacts/phase(?:2[0-9]|3[0-9])-[A-Za-z0-9._-]+/[A-Za-z0-9._-]+')
NEVER_FOLLOWED = ('phase22-', 'phase24-')
OTHER_RUN_AFTER_CLAIM = 'another_paid_run_after_claim'


def claimed_run_directory(root, out):
    """The run directory a sibling phase's claim names, or None. Only exactly artifacts/phaseNN-<x>/<name> is
    accepted, never phase22-* (the heldout-2 seal) or phase24-* (its held-out check), a claims directory, '.' or
    '..': a malformed or foreign claim is a blocker and nothing it names is read."""
    if not isinstance(out, str) or not OTHER_CLAIMED_RUN.fullmatch(out):
        return None
    parts = pathlib.PurePosixPath(out).parts
    if (parts[1].startswith(NEVER_FOLLOWED) or parts[1].endswith('-live-claims')
            or any(part in ('.', '..') for part in parts)):
        return None
    return root / parts[0] / parts[1] / parts[2]


def live_experiment_processes(reader=None):
    """Phase 25's token rule (imported): another Python process running an experiments/<name>.py script with
    --execute-live or a prefix of it. This process, its ancestors and its descendants (its own caffeinate helper)
    are excluded. Fail closed: a process list that cannot be read is itself a blocker."""
    return s2.live_experiment_processes(reader or process_list)


def other_paid_runs(*, root=None, ignore=(), status=None, processes=None):
    """Every reason to believe another paid run may be in progress. Empty means none was found."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    ignored = {(pathlib.Path(p) if pathlib.Path(p).is_absolute() else root / p).resolve() for p in ignore or ()}
    blockers = []
    for phase, pattern in OTHER_RUN_MANIFESTS:
        for path in sorted(artifacts.glob(pattern)):
            if path.resolve() in ignored or path.name == HELDOUT_MANIFEST_NAME:
                continue
            try:
                manifest = json.loads(path.read_text())
            except (OSError, ValueError):
                manifest = None
            if s2.manifest_running(manifest):
                blockers.append(f'{phase} run may be in progress ({path.relative_to(root)})')
    for name in OTHER_CLAIM_DIRS:
        for claim in sorted((artifacts / name).glob('claim-*.json')):
            if claim.resolve() in ignored:
                continue
            try:
                record = json.loads(claim.read_text())
            except (OSError, ValueError):
                record = None
            directory = claimed_run_directory(root, record.get('out')) if isinstance(record, dict) else None
            if directory is None:
                blockers.append(f'{name}/{claim.name} cannot be read or names no valid run directory; nothing it '
                                'names was read')
                continue
            finals = []
            for path in directory.glob('*manifest*.json'):
                if path.name == HELDOUT_MANIFEST_NAME:
                    continue
                try:
                    finals.append(not s2.manifest_running(json.loads(path.read_text())))
                except (OSError, ValueError):
                    finals.append(False)
            if not any(finals):
                blockers.append(f'{name}/{claim.name} names a run with no final manifest')
    blockers.extend(live_experiment_processes() if processes is None else list(processes))
    state, detail = (status or backend_status)()
    if state == 'active':
        blockers.append(f'the lab backend reports an active campaign ({detail})')
    elif state == 'unknown':
        blockers.append(f'the lab backend status could not be read ({detail}); check it by hand')
    return blockers, state


def check_other_paid_runs(args, *, root=None, status=None):
    blockers, state = other_paid_runs(root=root, ignore=getattr(args, 'ignore_manifest', None) or (), status=status)
    if blockers:
        more = f' (and {len(blockers) - 1} more: {"; ".join(blockers[1:4])})' if len(blockers) > 1 else ''
        raise PlanningError(f'One paid run at a time: {blockers[0]}{more}. {s2.blocker_advice(blockers)}')
    return state


# ---------------------------------------------------------------- the review gate

def check_review(protocol_text, protocol_sha256, harness, plan_hash_value, *, root=None):
    """The review is enforced, not only procedural: no review-pending phrase (in any case) in the status block,
    the bare 'Reviewed for launch' line with both pins, and a review record naming this protocol's sha256, the
    harness sha256, the plan hash and this harness's phase cap. Review round 1 (as Phase 30): the record must also
    say it is approved (status "approved"), name who approved (approved_by), and carry the owner's answer
    (owner_answer: question, verbatim, given_by, date). Review round 2: question is exactly "§18 question 1"; the
    verbatim words are one line of at least OWNER_ANSWER_MIN_CHARS characters, are not words the status block or the
    program document already hold (compared on letters and digits), and stand exactly once on one bare line of the
    Review log's closing entry: Owner's answer to §18 question 1 (<given_by>, <date>): "<verbatim>". Returns the
    record."""
    if REVIEW_PENDING_MARKER.lower() in status_block(protocol_text).lower():
        raise PlanningError(f'The protocol status still says "{REVIEW_PENDING_MARKER}" (in any case); live execution '
                            'refuses')
    expected_line = REVIEWED_LINE.format(harness=harness, plan=plan_hash_value)
    if not any(line.strip() == expected_line for line in protocol_text.splitlines()):
        raise PlanningError('The protocol has no bare "Reviewed for launch" line (no backticks, list marker or bold) '
                            'naming this harness sha256 and plan hash')
    path = _root(root) / REVIEW_RECORD
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable review record at {REVIEW_RECORD}; live execution refuses') from None
    expected = {'protocol_sha256': protocol_sha256, 'harness_sha256': harness, 'plan_hash': plan_hash_value}
    if not isinstance(record, dict) or any(record.get(key) != value for key, value in expected.items()):
        raise PlanningError('The review record does not name this protocol sha256, harness sha256 and plan hash')
    cap = record.get('phase_cap')
    if type(cap) not in (int, float) or not math.isfinite(cap) or SpendGuard.micro(cap) != SpendGuard.micro(HARD_SPEND_CAP):
        raise PlanningError(f'The review record does not name this harness\'s phase cap as phase_cap '
                            f'({HARD_SPEND_CAP:.2f}); live execution refuses')
    if record.get('status') != REVIEW_APPROVED_STATUS:
        raise PlanningError(f'The review record\'s status is not "{REVIEW_APPROVED_STATUS}"; live execution refuses')
    if not (isinstance(record.get('approved_by'), str) and record['approved_by'].strip()):
        raise PlanningError('The review record names no approver (approved_by); live execution refuses')
    answer = record.get('owner_answer')
    if not (isinstance(answer, dict)
            and all(isinstance(answer.get(key), str) and answer[key].strip() for key in OWNER_ANSWER_FIELDS)):
        raise PlanningError("The review record carries no owner_answer with question, verbatim, given_by and date (the "
                            'owner\'s answer to the protocol\'s §18 question 1, that the phase is worth its bound); '
                            'live execution refuses')
    # Review round 2: the words must be the owner's own answer to §18 question 1, on one bare line of the Review
    # log's closing entry. A plain substring test over the whole file passed the program-level approval that the
    # status block already quotes, and a one-letter "answer".
    if answer['question'] != OWNER_QUESTION:
        raise PlanningError(f'The review record\'s owner_answer.question is not "{OWNER_QUESTION}"; live execution '
                            'refuses')
    verbatim = answer['verbatim']
    if verbatim != verbatim.strip() or '\n' in verbatim or '\r' in verbatim:
        raise PlanningError("The owner's verbatim answer must be one line, with no leading or trailing space")
    if len(verbatim) < OWNER_ANSWER_MIN_CHARS:
        raise PlanningError(f"The owner's verbatim answer is shorter than {OWNER_ANSWER_MIN_CHARS} characters; it must "
                            f"be the owner's own answer to {OWNER_QUESTION}, in the owner's words")
    words = _letters_and_digits(verbatim)
    if words in _letters_and_digits(status_block(protocol_text)):
        raise PlanningError("The owner's verbatim answer is already in the protocol's status block; the status block "
                            f"never carries the answer to {OWNER_QUESTION} (it quotes the program-level approval)")
    try:
        program = PROGRAM.read_text()
    except OSError:
        raise PlanningError(f'The program document {PROGRAM.name} cannot be read, so the owner\'s answer cannot be '
                            'checked against the program-level approval; live execution refuses') from None
    if words in _letters_and_digits(program):
        raise PlanningError(f"The owner's verbatim answer is words the program document ({PROGRAM.name}) already "
                            f'holds, such as its program-level approval; that is not an answer to {OWNER_QUESTION}')
    entry = closing_entry(protocol_text)
    if entry is None:
        raise PlanningError(f'The protocol has no Review log closing entry (a heading starting "{CLOSING_ENTRY_HEADING}" '
                            f'after the last "{REVIEW_LOG_HEADING}" heading); live execution refuses')
    expected = OWNER_ANSWER_LINE.format(given_by=answer['given_by'], date=answer['date'], verbatim=verbatim)
    if sum(1 for line in entry if line.strip() == expected) != 1:
        raise PlanningError("The Review log's closing entry does not carry, exactly once and on one bare line (never "
                            f'wrapped, no list marker, bold or backticks), the line: {expected}')
    return record


def _letters_and_digits(text):
    """Text compared on its letters and digits only (case, spaces and punctuation ignored)."""
    return ''.join(character for character in text.casefold() if character.isalnum())


def closing_entry(protocol_text):
    """The lines of the Review log's closing entry, or None: after the last REVIEW_LOG_HEADING line, from the last
    heading under it that starts with CLOSING_ENTRY_HEADING up to the next level-2 or level-3 heading."""
    lines = protocol_text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.rstrip() == REVIEW_LOG_HEADING]
    if not starts:
        return None
    log = lines[starts[-1] + 1:]
    log = log[:next((index for index, line in enumerate(log) if line.startswith('## ')), len(log))]
    heads = [index for index, line in enumerate(log) if line.startswith(CLOSING_ENTRY_HEADING)]
    if not heads:
        return None
    entry = log[heads[-1] + 1:]
    return entry[:next((index for index, line in enumerate(entry) if line.startswith(('## ', '### '))), len(entry))]


# ---------------------------------------------------------------- live execution

class Recorder(s2.Recorder):
    """Phase 25's recorder (fsynced response lines, scrubbed secrets), writing this probe's manifest."""

    def save(self):
        path = self.out / MANIFEST_NAME
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(self.scrub(json.dumps(self.manifest, indent=2, ensure_ascii=False)) + '\n')
        os.replace(temporary, path)


def openai_client_factory(**kwargs):
    """The provider client RuntimeProvider would build itself (read at call time; tests replace it)."""
    from openai import AsyncOpenAI
    return AsyncOpenAI(**kwargs)


def run_live(args, plan, prompts, *, sleep=asyncio.sleep, status=None):
    problem = phase25_harness_problem()
    if problem:
        raise PlanningError(problem)
    out = check_output(args.out)
    check_other_paid_runs(args, status=status)
    harness = sha256_file(__file__)
    if args.expect_harness_sha256 != harness:
        raise PlanningError('--expect-harness-sha256 does not match this script')
    if not PROTOCOL.exists():
        raise PlanningError('No protocol at docs/part2/PHASE29_EXPERIMENT.md; live execution refuses until one is reviewed')
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
                or s2.request_digest(s2.request_body(prompt['messages'], request['temperature'])) != request['request_hash']):
            raise PlanningError(f'{request["request_id"]} has no verified prompt matching the plan; nothing may be sent')
    artifacts = (_root() / 'artifacts').resolve()
    earlier = earlier_live_runs(artifacts)
    spend_cap = effective_spend_cap(args.spend_cap, earlier)
    check_budget(plan['counts']['total_requests'], spend_cap)
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
        raise PlanningError('configuration_hash differs from the declared Phase 22 value')
    if settings.model_for_role('mechanic') != EXPECTED_MECHANIC_MODEL:
        raise PlanningError('The Mechanic role does not resolve to the declared model')
    backend_state = check_other_paid_runs(args, status=status)
    stop_requested = False
    recorder = None
    # Where the first stop signal arrived (Phase 25 review rounds 2 and 3): any SIGINT or SIGTERM, whoever sent it,
    # is an operator stop and forfeits the round-1 fallback; the first one is recorded, later ones counted.
    signal_state = {'manifest': None, 'first': None, 'count': 0}

    def request_stop(signum=None, _frame=None):
        nonlocal stop_requested
        stop_requested = True
        signal_state['count'] += 1
        running = signal_state['manifest'] or {}
        if signal_state['first'] is None:
            in_flight = running.get('in_flight_request')
            signal_state['first'] = {
                'signal': signal.Signals(signum).name if signum in tuple(signal.Signals) else str(signum),
                'received_at': datetime.now(timezone.utc).isoformat(),
                'status_at_arrival': running.get('status'),
                'in_flight_request': dict(in_flight) if isinstance(in_flight, dict) else None,
                'last_request': dict(running['last_request']) if isinstance(running.get('last_request'), dict) else None,
                'requests_done_at_arrival': running.get('requests_done'),
                'resend_lines_at_arrival': running.get('resend_lines')}

    async def execute():
        from app.providers.runtime import RuntimeProvider
        sender = s2.RequestSender(base=lambda **kwargs: openai_client_factory(**kwargs))
        async with RuntimeProvider(settings, live_authorized=True, client_factory=sender) as provider:
            return await s2.run_requests(plan['requests'], prompts, provider, guard, recorder, sender=sender,
                                         stop=lambda: stop_requested, sleep=sleep)

    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if stop_requested:
            raise PlanningError('An operator stop arrived before the claim; nothing was claimed or sent')
        # The output directory is created exclusively BEFORE the claim (Phase 27), so a directory that appeared after
        # check_output refuses here with nothing claimed, and the claim always owns its directory.
        try:
            out.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise PlanningError(f'{out} appeared during the launch checks; nothing was claimed or sent. Use a new '
                                'directory') from None
        try:
            claim, earlier = take_claim(out, plan_hash(plan), harness, spend_cap=spend_cap, expected_earlier=earlier)
        except BaseException:
            with contextlib.suppress(OSError):
                out.rmdir()          # only the empty directory this launch just made
            raise
        manifest = {'schema_version': SCHEMA, 'mode': 'live', 'status': 'STARTING', 'pid': os.getpid(),
                    'plan_hash': plan_hash(plan), 'harness_sha256': harness, 'protocol_sha256': protocol_sha256,
                    'phase25_harness_sha256': PHASE25_HARNESS_SHA256,
                    'configuration_hash': pins['configuration_hash'], 'settings_sha256': DECLARED_SETTINGS_SHA256,
                    'mechanic_model': pins['mechanic_model'], 'spend_cap': spend_cap,
                    'spend_cap_requested': args.spend_cap, 'phase_spend_cap': HARD_SPEND_CAP,
                    'earlier_undelivered_charged': round(HARD_SPEND_CAP - phase_spend_remaining(earlier), 6),
                    'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                    'claim': str(claim.relative_to(artifacts.parent)), 'earlier_undelivered_runs': earlier,
                    'review': {'status': review['status'], 'approved_by': review['approved_by'],
                               'approved_at': review.get('approved_at'),
                               'owner_answer': {key: review['owner_answer'][key] for key in OWNER_ANSWER_FIELDS}},
                    'backend_state_at_launch': backend_state,
                    'ignored_manifests': list(getattr(args, 'ignore_manifest', None) or ()),
                    'requests_planned': plan['counts']['total_requests'], 'requests_done': 0, 'resend_lines': 0,
                    'attempts': 0, 'charged_upper_bound': 0.0, 'statuses': {}, 'generations_delivered': 0,
                    'measured_input_tokens': 0, 'measured_output_tokens': 0, 'backoff_waits': [], 'resend_pass': None,
                    'in_flight_request': None, 'last_request': None, 'stop_signal': None, 'stop_signals_received': 0,
                    'stop_reason': None, 'traceback': None,
                    'started_at': datetime.now(timezone.utc).isoformat(), 'ended_at': None}
        signal_state['manifest'] = manifest
        recorder = Recorder(out, manifest, secrets=(settings.wandb_api_key, settings.typesafe_api_key))
        try:
            recorder.save()
            # The last offline check, after the claim exists: a sibling runner that passed its own guard before this
            # claim was visible is caught here, and this run ends at $0 (nothing was sent).
            late, _ = other_paid_runs(ignore=getattr(args, 'ignore_manifest', None) or (), status=status)
            if late:
                manifest.update(status='ABORTED', stop_reason=OTHER_RUN_AFTER_CLAIM,
                                blockers_after_claim=[recorder.scrub(b) for b in late])
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
            manifest.update(status='ABORTED', stop_reason=f'{type(error).__name__}',
                            traceback=recorder.scrub(traceback.format_exc()[-8000:]))
        finally:
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
        results, partial = load_results(out / 'responses.jsonl')
        # From the saved final manifest, exactly as --readouts will read it.
        saved = json.loads((out / MANIFEST_NAME).read_text())
        readouts = compute_readouts(plan['requests'], results, already_proposed=already_proposed_of(plan),
                                    partial_lines_skipped=partial, run_end=s2.run_end_of(saved))
    except Exception as error:  # noqa: BLE001 - the run is already final; --readouts can recompute at $0
        summary['readouts_error'] = type(error).__name__
        print(json.dumps(summary, indent=2))
        return 1
    write_json(out / 'readouts.json', readouts)
    summary.update(decisions={arm: readouts['decisions'][arm]['declared'] for arm in TREATED_ARMS},
                   statement=readouts['statement'])
    print(json.dumps(summary, indent=2))
    return 0 if manifest['status'] == 'COMPLETED' else 1


def already_proposed_of(plan):
    """The plan's already-proposed record (review round 2); compute_readouts refuses it if missing or malformed."""
    return (plan.get('populations') or {}).get('already_proposed') if isinstance(plan, dict) else None


def load_run(directory):
    directory = pathlib.Path(directory)
    try:
        plan = json.loads((directory / 'plan.json').read_text())
        results, partial = load_results(directory / 'responses.jsonl')
    except PlanningError:
        raise
    except (OSError, ValueError) as error:
        raise PlanningError(f'The run in {directory} cannot be read ({type(error).__name__}); a run that stopped '
                            'before writing plan.json or responses.jsonl has no read-outs') from None
    return plan, results, partial


NOT_THE_RUNS_HARNESS = "NOT THE RUN'S HARNESS OR PLAN: a recomputation, not the declared read-out"


def recompute_readouts(directory, *, allow_other_harness=False):
    """The read-outs of a run that has ended; refuses while the run's manifest is not final, so nothing states
    which arm is ahead while the run is live (Phase 25 review round 3)."""
    directory = pathlib.Path(directory)
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable {MANIFEST_NAME} in {directory}; read-outs are tied to a run') from None
    if not isinstance(manifest, dict) or not _final(manifest):
        status = manifest.get('status') if isinstance(manifest, dict) else None
        raise PlanningError(f'The run in {directory} has not ended (manifest status {status}); --readouts refuses '
                            'until its manifest is final. If its process died, close its claim at $0 with '
                            '--finalize-abandoned first')
    plan, results, partial = load_run(directory)
    readouts = compute_readouts(plan['requests'], results, already_proposed=already_proposed_of(plan),
                                partial_lines_skipped=partial, run_end=s2.run_end_of(manifest))
    harness_matches = sha256_file(__file__) == manifest.get('harness_sha256')
    plan_matches = plan_hash(plan) == manifest.get('plan_hash')
    if harness_matches and plan_matches:
        return readouts
    if not allow_other_harness:
        raise PlanningError(f'{NOT_THE_RUNS_HARNESS} (harness matches the run: {harness_matches}; plan matches the '
                            f'run: {plan_matches}). Pass --not-the-runs-harness to print it labelled')
    return {'label': NOT_THE_RUNS_HARNESS, 'harness_matches_run': harness_matches, 'plan_matches_run': plan_matches,
            'readouts': readouts}


def dry_summary(plan, store_wide=None, planning_inputs=None):
    return {'status': 'DRY_RUN', 'plan_hash': plan_hash(plan), 'harness_sha256': plan['harness_sha256'],
            'phase25_harness_sha256': plan['phase25_harness_sha256'],
            'configuration_hash': plan['configuration_hash'], 'mechanic_model': plan['mechanic_model'],
            'arms': {arm: plan['arms'][arm]['temperature'] for arm in ARMS},
            'populations': {k: plan['populations'][k] for k in ('by_phase', 'slot2_prompts', 'excluded_in_scope',
                                                                 'prompts_whose_slot1_policy_fires',
                                                                 'verification_failures')},
            'census_facts': plan['populations']['census_facts'],
            # Review round 2: the already-proposed set (its hashes are in the hashed plan), summarised.
            'already_proposed': {k: v for k, v in plan['populations']['already_proposed'].items() if k != 'policy_hashes'}
                                | {'policies': len(plan['populations']['already_proposed']['policy_hashes'])},
            # Store-wide counts are reported here only, never in the hashed plan (as Phase 25).
            'store_wide_outside_scope_not_hashed': store_wide,
            # Review round 1: labelled planning inputs from Phase 25's pinned run, never evidence, never hashed.
            'phase25_planning_inputs_not_evidence_not_hashed': planning_inputs,
            'verification': plan['verification'], 'precheck': plan['precheck'],
            'auditor_validation': {k: v for k, v in plan['investigation']['auditor_validation'].items()
                                   if k != 'premature_defer_vs_terminal_rejection'},
            'thresholds': plan['thresholds'], 'counts': plan['counts'], 'cost': plan['cost']}


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', default=str(STORE), help='read-only lab store')
    parser.add_argument('--settings', default=DECLARED_SETTINGS, help='the declared non-secret settings file')
    parser.add_argument('--spend-cap', type=float, default=HARD_SPEND_CAP)
    parser.add_argument('--write-plan', help='new directory under artifacts/phase29-<date>/ for the dry plan')
    parser.add_argument('--protocol-numbers', help='new directory under artifacts/phase29-<date>/ for the $0 '
                        'false-alarm, power and boundary figures (no store or provider access)')
    parser.add_argument('--readouts', help='recompute read-outs from a saved run directory ($0); refuses until the '
                        "run's manifest is final, and unless this harness and the saved plan are the run's own")
    parser.add_argument('--not-the-runs-harness', action='store_true',
                        help="with --readouts: print a mismatched recomputation, labelled as not the run's")
    parser.add_argument('--finalize-abandoned', metavar='CLAIM',
                        help='close at $0 a claimed run whose process died before its manifest was final')
    parser.add_argument('--out', help='new directory under artifacts/phase29-<date>/ for a live run')
    parser.add_argument('--expect-plan-hash')
    parser.add_argument('--expect-harness-sha256')
    parser.add_argument('--expect-protocol-sha256')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    parser.add_argument('--ignore-manifest', action='append', default=[],
                        help='a crashed run manifest or claim (exact path) known not to be running')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = arguments(argv)
    try:
        if args.finalize_abandoned:
            path, manifest = finalize_abandoned(args.finalize_abandoned)
            delivered = manifest['generations_delivered']
            print(json.dumps({'status': 'FINALIZED', 'manifest': str(path), 'generations_delivered': delivered,
                              'charged_upper_bound': manifest['charged_upper_bound'],
                              'a_new_run_is_allowed': delivered == 0,
                              'note': 'add charged_upper_bound to the ledger; a new run needs a new --out'}, indent=2))
            return 0
        if args.readouts:
            print(json.dumps(recompute_readouts(args.readouts, allow_other_harness=args.not_the_runs_harness),
                             indent=2))
            return 0
        if args.protocol_numbers:
            directory = check_output(args.protocol_numbers, live=False)
            numbers = protocol_numbers()
            directory.mkdir(parents=True, exist_ok=False)
            write_json(directory / 'protocol_numbers.out.json', numbers)
            print(json.dumps({'written': str(directory), 'harness_minimum_is_the_chosen_one':
                              numbers['harness_minimum_is_the_chosen_one']}, indent=2))
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
        plan, prompts = build_plan(store=args.store, settings_path=settings_path, spend_cap=args.spend_cap)
        if not args.execute_live:
            connection = s2.connect(args.store)
            try:
                store_wide = s2.store_outside_scope(connection)
            finally:
                connection.close()
            planning_inputs = phase25_planning_inputs(already_proposed=already_proposed_of(plan))
            summary = dry_summary(plan, store_wide, planning_inputs)
            if args.write_plan:
                directory = check_output(args.write_plan, live=False)
                directory.mkdir(parents=True, exist_ok=False)
                write_json(directory / 'plan.json', plan)
                write_json(directory / 'dry-summary.json', summary)
                summary['written'] = str(directory)
            print(json.dumps(summary, indent=2))
            print('Dry plan only. Pass --execute-live with --confirm-entity, --out and the reviewed hashes to send.')
            return 0
        return run_live(args, plan, prompts)
    except PlanningError as error:
        print(json.dumps({'status': 'REJECTED', 'error_type': type(error).__name__, 'message': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
