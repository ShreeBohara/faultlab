"""Phase 30: a non-scoring Actor replay probe of a NARROW report-status field (T2).

Why (docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md, Phase 30; PHASE27_RESULTS.md). Phase 27's field T
(`last_observed_status`, each operation's last observed status copied verbatim from the evidence) removed
the PENDING-for-UNKNOWN report slip on its primary prompts (0 of 225 against 4 of 225 for a plain
re-send), but it failed the guard: on terminal-rejection turns, where T stated `FAILED / null`, the Actor
stopped filing its correct `FAILED / NOT_REQUIRED` report in 23 of 45 prompts and polled again.

T2 is the same field with the same value, shown on far fewer turns. The declared window:

  T2 is added to a turn's user message if and only if
    (1) the turn is report-required (`final_report_required` is true: the reserved last turn, or every
        turn after business closure; the lab knows this before it sends the turn), and
    (2) the field would state `UNKNOWN` for at least one operation (the latest delivered observation
        that matches the operation under the runtime's binding reports `UNKNOWN`), and
    (3) no delivered observation or receipt shows the upgrade `FAILED` (never a terminal-rejection
        turn).
  On every other turn every arm is byte-identical to the stored request. When T2 is shown, its key,
  note and value are exactly Phase 27's T on that turn; only the window differs.

What that buys (the $0 pre-check, over every verified development v4 turn). T2's window holds only the
781 report-required report turns of strata U1, U2 and U3. No tool turn, no voluntary turn, none of the
2,070 prompts of Phase 27's guard strata G1-G5 (terminal rejection included) and no turn with the
upgrade FAILED is in it, and no in-window turn follows an earlier in-window turn, so the replayed
history is exactly what a later loop would send. On all of those out-of-window turns T2's request is
byte-identical to the control's. So Phase 27's guard strata cannot move under T2 by construction; the
plan refuses to exist otherwise. The live money goes where T2 is actually shown.

How a prompt is rebuilt. Phase 27's harness (scripts/experiments/report_word_probe.py) is loaded
unchanged under a private name with its sha256 pinned; it in turn loads Phase 21's rebuild
(lapse_probe.py, pinned by it). Every request is rebuilt with the runtime's own code and accepted only
if both stored hashes match. Phase 27's word rule, strata, status field, allocation method and read-out
helpers are imported, never copied or edited.

Populations (development only; heldout-2 is never read):
  primary  U2 (report-required; upgrade SUCCEEDED; confirmation written and reading UNKNOWN; where
           every development slip is), prompts NOT sent in Phase 27, allocated across (source, case,
           episode arm) cells by Webster's method, seeded rank within a cell. Arms C (plain re-send)
           and T2.
  guard    in-window non-target strata, all prompts: U1 (the Phase 24 situation; all 52, re-sent,
           because Phase 27 sent all of them with C and T) and U3 (the lapse reports; all 62; never
           sent with the field: Phase 21 re-sent 51 of them under a plain control, all correct).
           Arms R (plain re-send, the exchangeable reference) and T2.

Read-outs (compute_readouts, declared before any data):
  structural guard  the $0 pre-check above; PASS in any plan that exists, by construction (T2 is the
                    control there and nothing is sent), so it is never quoted as a measured pass.
  in-window guard   U1 + U3, R against T2. A response is OK when it is a received report whose two
                    words are both correct (Phase 27's word rule; a received non-report is not OK).
                    Two exact one-sided sign tests on (T2 not OK, R OK) against (R not OK, T2 OK),
                    among prompts where both were received: pooled U1 + U3, and U3 alone (the only
                    in-window context never sent with the field, so a harm there is not diluted by
                    U1). FAIL iff either gives p < 0.05 while its own completeness holds (>= 95% of
                    its planned prompts compared); else INCOMPLETE if either is incomplete; else PASS.
  non-inferiority   U2, C against T2, Phase 27's worst case for T2 (T2 bad unless a received report
                    with both words correct; C bad only for a received report with an unsupported
                    word). Tango's score test for paired proportions, H0: P(T2 bad) - P(C bad) >=
                    NI_MARGIN (1.5 points); PASS iff Tango's one-sided p < NI_ALPHA (0.024).
                    INCOMPLETE unless C and T2 each received >= 95% of the planned prompts. A
                    recommendation does not imply benefit: a field that does nothing passes 15-27% of
                    the time at the modelled slip rates. A REDUCTION is not a decision: at the
                    measured ~1.6-1.8% re-send slip rate, even a field that removed every slip would reach
                    p < 0.05 on the exact McNemar only about 55-66% of the time at this size, so a
                    reduction cannot be reliably shown; the test is reported, never deciding.
  decision          RECOMMENDED_FOR_A_LATER_LOOP iff all three PASS; otherwise NOT_RECOMMENDED. Never
                    adopted here.

Nothing here creates a campaign, study, trial, world, policy or store row. The stores are opened
read-only, results never enter a study and are never shown to any model. Nothing under backend/app
changes; the field exists only in this script.

Dry by default. `--execute-live` needs `--confirm-entity`, `--out` and the reviewed plan, harness and
protocol hashes; the protocol's status block must no longer say it is not yet reviewed (in any case), it
must carry the bare line "Reviewed for launch: harness <sha256> plan <hash>", and the review record must
repeat them, name this harness's phase cap, and carry the owner's quoted approval. A live run refuses
beside any other paid run that may be in progress: other phases' run manifests and launch claims, the
lab backend's active campaign, and any other `--execute-live` experiment process (by tokens, with this
process, its ancestors and its descendants such as the caffeinate helper excluded; Phase 26's reviewed
rule, imported). It checks before the credential read, after it, and once more after its claim, before
the first provider call. The $20 cap is a phase cap enforced by this harness's own SpendGuard.

Usage:
  python scripts/experiments/report_narrow_probe.py
  python scripts/experiments/report_narrow_probe.py --write-plan artifacts/phase30-<date>/dry-plan
  python scripts/experiments/report_narrow_probe.py --readouts artifacts/phase30-<date>/live
  python scripts/experiments/report_narrow_probe.py --finalize-abandoned artifacts/phase30-live-claims/claim-NN.json
  python scripts/experiments/report_narrow_probe.py --execute-live --confirm-entity ENTITY \\
      --out artifacts/phase30-<date>/live --expect-plan-hash H \\
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
import importlib.util
import json
import math
import os
import pathlib
import re
import signal
import subprocess
import sys
import traceback

# Even dry inspection should not create Python cache files in the workspace.
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

# Phase 27's harness, loaded unchanged under a private name (it loads Phase 21's rebuild, pinned by it).
# Its sha256 is checked before any plan, any live call and any read-out.
PHASE27_HARNESS = ROOT / 'scripts/experiments/report_word_probe.py'
PHASE27_HARNESS_SHA256 = 'f057ef2a1123f01bf50c61c5637cbba463f01d16593e8ee9d6d27f4f47869519'
_SPEC = importlib.util.spec_from_file_location('faultlab_phase30_report_word_probe', PHASE27_HARNESS)
rwp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rwp)
lp = rwp.lp

# Phase 26's runner supplies the reviewed token-based process rule (paid_run_script and
# live_experiment_processes: this process, its ancestors and its descendants, such as the
# `caffeinate -is python ...` helper, are excluded). Loaded lazily, and only after its sha256 matches.
PHASE26_RUNNER = ROOT / 'scripts/experiments/run_gap_probe.py'
PHASE26_RUNNER_SHA256 = '5d8e16901feda8ec4f6c9ecc3d2c410e549e52e982b66c646d9812f2b271589b'
_PHASE26_MODULE_NAME = 'faultlab_phase30_gap_probe'

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4  # noqa: E402
from app.contracts.models import canonical_json, content_hash  # noqa: E402
from app.providers.runtime import response_format_for, validate_request_input  # noqa: E402

SCHEMA = 'faultlab-report-narrow-probe/v1'
READOUT_SCHEMA = 'faultlab-report-narrow-probe-readouts/v1'
MANIFEST_NAME = 'report-narrow-probe-manifest.json'
PHASE_PREFIX = 'phase30-'
FINAL_STATUSES = ('COMPLETED', 'STOPPED', 'ABORTED')
LIVE_MANIFEST_GLOB = f'{PHASE_PREFIX}*/*/{MANIFEST_NAME}'
CLAIM_DIR = 'phase30-live-claims'
CLAIM_NAME = re.compile(r'claim-(\d+)\.json')
ABANDONED_IN_FLIGHT_ATTEMPTS = 2
# Other paid runs of the program: every run manifest (a JSON object with `started_at`) under a directory of
# Phases 20, 21, 23, 25-29 or 31+ that has no end marker, and every launch claim of those phases whose run
# directory holds no final run manifest. Phases 22 and 24 (the heldout-2 seal and its held-out check) are
# never listed and none of their files is opened. This phase's own runs are checked by live_run_records.
OTHER_RUN_DIR = re.compile(r'phase(?:2[01356789]|3[1-9])-[A-Za-z0-9._-]+')
OTHER_CLAIM_DIR = re.compile(r'phase(?:2[01356789]|3[1-9])-live-claims')
OTHER_CLAIMED_RUN = re.compile(r'artifacts/phase(?:2[01356789]|3[1-9])-[A-Za-z0-9._-]+/[A-Za-z0-9._-]+')
BACKEND_STATUS_URL = rwp.BACKEND_STATUS_URL
OTHER_RUN_AFTER_CLAIM = 'other_paid_run'

STORE = rwp.STORE
STORE_CUTOFF = rwp.STORE_CUTOFF          # 2026-09-24T05:50:00Z, before heldout-2's first episode
PHASE20_STORE = rwp.PHASE20_STORE
PHASE20_PLAN = rwp.PHASE20_PLAN
SOURCES = rwp.SOURCES

# Phase 27's sent plan (its live plan.json, identical to its reviewed dry plan r3) names the U2 prompts
# Phase 27 already sent; T2 was designed after seeing their responses, so they are not sent again. Its
# read-outs give the Phase 27 U2 discordance for one descriptive pooled figure, copied into the plan.
PHASE27_PLAN = ROOT / 'artifacts/phase27-2026-09-24/live/plan.json'
PHASE27_PLAN_SHA256 = '2f26cd34a494610b0ca4bb9ce77b2ee35eb616aa591dcb9bf4f5406cb6b5ddb6'
PHASE27_PLAN_HASH = 'cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682'
PHASE27_READOUTS = ROOT / 'artifacts/phase27-2026-09-24/live/readouts.json'
PHASE27_READOUTS_SHA256 = 'c58d162a7324f4276466017dc995d3d58626b197cfe4a06ce471faa9f710593e'
PHASE27_U2_SENT = 225

EXPECTED_ACTOR_MODEL = rwp.EXPECTED_ACTOR_MODEL
EXPECTED_PROJECT = rwp.EXPECTED_PROJECT
DECLARED_SETTINGS = rwp.DECLARED_SETTINGS
DECLARED_SETTINGS_SHA256 = rwp.DECLARED_SETTINGS_SHA256
DECLARED_CONFIGURATION_HASH = rwp.DECLARED_CONFIGURATION_HASH   # 2cf63e93..., the Phase 22 configuration
FREEZE_FILE = rwp.FREEZE_FILE
FREEZE_SHA256 = rwp.FREEZE_SHA256
PROTOCOL = ROOT / 'docs/part2/PHASE30_EXPERIMENT.md'
REVIEW_RECORD = 'artifacts/phase30-2026-09-25/review.json'
REVIEW_PENDING_MARKER = 'NOT yet reviewed'
REVIEWED_LINE = 'Reviewed for launch: harness {harness} plan {plan}'
OWNER_ANSWER_FIELDS = ('verbatim', 'given_by', 'date')
PER_REQUEST_DOLLAR_BOUND = 0.0209    # 32,000 in x $0.55/M + 2,000 out x $1.65/M, conservative
HARD_SPEND_CAP = 20.0
# The program's cap for this phase (EXPERIMENT_PROGRAM_PHASES_28-31.md, "cap ~$20"). This harness never
# runs above it: build_plan refuses a HARD_SPEND_CAP above PROGRAM_PHASE_CAP.
PROGRAM_PHASE_CAP = 20.0

ARMS = ('C', 'R', 'T2')
ARM_TEXT = {'C': 'the exact verified v4 request, re-sent (primary comparator)',
            'R': 'the exact verified v4 request, re-sent (the in-window guard\'s exchangeable reference)',
            'T2': "C plus Phase 27's T field, only on turns in T2's window"}
T2_FIELD = rwp.T_FIELD
T2_NOTE = rwp.T_NOTE
SERVICES = rwp.SERVICES
T2_WINDOW_RULE = ('in window iff (1) the turn is report-required, (2) the field would state UNKNOWN for at least '
                  'one operation (the latest delivered observation matching it under '
                  'app.agents.progress._matching_operation_data reports UNKNOWN), and (3) no delivered observation '
                  'or receipt shows the upgrade FAILED')
T2_VALUE_RULE = ("exactly Phase 27's T value on that turn (report_word_probe.status_field): each operation's latest "
                 'delivered matching status, verbatim, with its obs-k label, or null')

SAMPLE_SEED = 'faultlab-phase30-2026-09-25'
# Declared sizes: None sends every prompt of the stratum; U2 is allocated across its cells (Webster).
STRATUM_SIZES = {'U2': 316, 'U1': None, 'U3': None}
STRATUM_ARMS = {'U2': ('C', 'T2'), 'U1': ('R', 'T2'), 'U3': ('R', 'T2')}
STRATUM_POPULATION = {'U2': 'primary', 'U1': 'guard', 'U3': 'guard'}
# U2 prompts that Phase 27 sent are never sent here; U1 has no prompt Phase 27 did not send, so it is re-sent.
FRESH_ONLY = ('U2',)
STRATUM_RULES = {
    'U1': 'report-required; upgrade UNKNOWN, written at least once, never shown otherwise, no receipt (the Phase 24 situation); in-window guard, all prompts (re-sent: Phase 27 sent all 52)',
    'U2': "report-required; upgrade SUCCEEDED; confirmation written and reading UNKNOWN; the primary; prompts not sent in Phase 27",
    'U3': 'report-required; upgrade SUCCEEDED; confirmation reading UNKNOWN, never written (the lapse reports); in-window guard, all prompts (never sent with the field; Phase 21 re-sent 51 of the 62 under a plain control, all correct); also tested alone',
    'U_other': 'report-required; any other in-window context; none exists in development data; not sent'}
PHASE27_GUARD_STRATA = ('G1', 'G2', 'G3', 'G4', 'G5')
POPULATION_ORDER = ('primary', 'guard')
RECEIVED = rwp.RECEIVED

# Non-inferiority (primary, U2): Tango's score test for the difference of paired proportions.
# Margin 1.5 points (review round 1, S2): against a re-send slip rate of about 1.8%, 2 points is nearly a
# doubling, and 1.5 points costs nothing for a field like Phase 27's T (PASS 1.00 either way) while it halves
# the chance of recommending a field 1 point worse than the control.
NI_MARGIN = Fraction(3, 200)
# One-sided 0.024 rather than the conventional 0.025: at a 1.5-point margin, 0.025 has an exact size slightly
# above 0.025 at some nuisance rates (0.0256 at a C-only rate of 3%); at 0.024 the exact size at the margin,
# by enumeration, stays below 0.025 (artifacts/phase30-2026-09-25/protocol-numbers-r1/).
NI_ALPHA = 0.024
# In-window guard: the exact one-sided sign test (a variant of Phase 27's terminal-rejection word test that
# counts a received non-report as not OK), pooled over U1 + U3 and, separately, on U3 alone.
GUARD_ALPHA = 0.05
# U3 is the only in-window context besides U2 that has never been sent with the field (U1's R and T2 requests
# are Phase 27's C and T requests), so a harm confined to U3 must not be diluted by U1 (review round 1, S1).
GUARD_ALONE_STRATUM = 'U3'
COMPLETE_MIN = Fraction(95, 100)
REDUCTION_ALPHA = 0.05      # descriptive only

SOURCE_FILES = rwp.SOURCE_FILES + ('scripts/experiments/report_word_probe.py',)

PlanningError = rwp.PlanningError
sha256_file = rwp.sha256_file
wilson = rwp.wilson
mcnemar_greater = rwp.mcnemar_greater
load_results = rwp.load_results
write_json = rwp.write_json
status_block = rwp.status_block
settings_from_file = rwp.settings_from_file
configuration_pins = rwp.configuration_pins
entry_delivered = rwp.entry_delivered
backend_status = rwp.backend_status


class SpendGuard(lp.SpendGuard):
    """Phase 21's guard (every attempt charged at the bound, in whole micro-dollars), checked against THIS
    harness's cap (HARD_SPEND_CAP, read at call time), not lapse_probe's or report_word_probe's."""

    def __init__(self, cap, per_request=PER_REQUEST_DOLLAR_BOUND):
        if not (type(cap) in (int, float) and math.isfinite(cap) and 0 < cap <= HARD_SPEND_CAP):
            raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
        self.cap, self.per_request, self.attempts = cap, per_request, 0


def rank(*parts):
    """Deterministic, version-independent order: sha256 of this phase's seed and the parts."""
    return hashlib.sha256(':'.join((SAMPLE_SEED,) + tuple(str(p) for p in parts)).encode()).hexdigest()


def phase27_harness_problem():
    """The rebuild, word rule and helpers are Phase 27's reviewed code (which pins Phase 21's), or nothing
    is planned, sent or read out."""
    if sha256_file(PHASE27_HARNESS) != PHASE27_HARNESS_SHA256:
        return 'scripts/experiments/report_word_probe.py is not the pinned Phase 27 harness; its rebuild cannot be trusted'
    return rwp.phase21_harness_problem()


def phase26_runner_problem():
    if not PHASE26_RUNNER.is_file() or sha256_file(PHASE26_RUNNER) != PHASE26_RUNNER_SHA256:
        return 'scripts/experiments/run_gap_probe.py is not the pinned Phase 26 runner; its process rule cannot be trusted'
    return None


def _phase26_runner():
    """Phase 26's runner, loaded once after its sha256 matched (registered for its dataclasses)."""
    module = sys.modules.get(_PHASE26_MODULE_NAME)
    if module is None:
        problem = phase26_runner_problem()
        if problem:
            raise PlanningError(problem)
        spec = importlib.util.spec_from_file_location(_PHASE26_MODULE_NAME, PHASE26_RUNNER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PHASE26_MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(_PHASE26_MODULE_NAME, None)
            raise
    return module


def experiment_processes():
    """Other `--execute-live` experiment processes, by Phase 26's token rule (this process, its ancestors
    and its descendants excluded). Fail closed: a runner that is not the pinned file, or a process list
    that cannot be read, is itself a blocking entry."""
    problem = phase26_runner_problem()
    if problem:
        return [problem]
    try:
        return list(_phase26_runner().live_experiment_processes())
    except Exception as error:  # noqa: BLE001 - fail closed
        return [f'the process check could not run ({type(error).__name__}), so no other paid run can be ruled out']


# ---------------------------------------------------------------- the window (pure)

def terminal_rejection(upgrade):
    """The upgrade has been shown FAILED (a receipt or any bound observation): a terminal-rejection turn."""
    return upgrade.get('status') == 'FAILED' or 'FAILED' in (upgrade.get('seen') or ())


def states_unknown(field):
    return any(isinstance(field.get(service), dict) and field[service].get('status') == 'UNKNOWN'
               for service in SERVICES)


def t2_window(final_report_required, field, upgrade):
    """T2's declared window (T2_WINDOW_RULE)."""
    return final_report_required is True and states_unknown(field) and not terminal_rejection(upgrade)


def independent_t2_window(final_report_required, observations, intent):
    """The same window from raw observation dicts by separate code; the pre-check requires equality."""
    field = rwp.independent_status_field(observations, intent)
    unknown = any(field[service] is not None and field[service]['status'] == 'UNKNOWN' for service in SERVICES)
    failed = False
    for row in observations:
        result = row.get('result') or {}
        if result.get('operation_id') != intent['upgrade_operation_id']:
            continue
        data = result.get('data') if isinstance(result.get('data'), dict) else {}
        receipt = data.get('receipt') if isinstance(data.get('receipt'), dict) else {}
        if 'FAILED' in (result.get('status'), data.get('status'), receipt.get('status')):
            failed = True
    return final_report_required is True and unknown and not failed


def t2_messages(history, user, field, window):
    """T2's messages: Phase 27's T construction in window, the control outside it."""
    return rwp.arm_messages(history, user, 'T' if window else 'C', field)


def arm_messages(history, user, arm, field, window):
    if arm in ('C', 'R'):
        return rwp.arm_messages(history, user, 'C', field)
    if arm == 'T2':
        return t2_messages(history, user, field, window)
    raise PlanningError(f'Cannot build arm {arm}')


# ---------------------------------------------------------------- pass 1: every v4 turn of both sources

PRECHECK_ZERO = ('control_differs_from_stored', 't2_differs_from_control_outside_window',
                 't2_differs_from_phase27_t_in_window', 't2_equals_control_in_window', 'structural_violations',
                 'window_rule_disagreements', 'report_required_unknown_rule_disagreements',
                 'in_window_not_report_required', 'in_window_terminal_rejection', 'in_window_non_report_turns',
                 'in_window_after_earlier_in_window_turn', 'phase27_guard_prompts_in_window',
                 'phase27_content_disagreements')


def survey(connections, *, cutoff=STORE_CUTOFF, cases=None):
    """Verify every v4 turn of every eligible development episode (Phase 27's rebuild) and check T2's
    window and construction on every one of them. Returns (in-window report turns, verification, pre-check).
    A turn's history and messages are dropped once checked."""
    pre, problems, by_source = Counter(), [], Counter()
    in_window = []
    for source in SOURCES:
        connection = connections[source]
        for episode_id, summary in rwp.eligible_episodes(connection, source, cutoff=cutoff, cases=cases):
            events = lp.load_events(connection, episode_id)
            first = next((e for e in events if e['type'] == 'actor_output'), None)
            if first is None or first['payload'].get('actor_context_protocol') != ACTOR_CONTEXT_PROTOCOL_V4:
                continue
            by_source[source] += 1
            intent = lp.load_intent(connection, episode_id)
            turns, phase27_pre, _ = rwp.survey_episode(events, intent, summary, keep=True)
            pre['turns'] += phase27_pre['turns']
            pre['verified'] += phase27_pre['verified']
            pre['phase27_content_disagreements'] += phase27_pre['content_disagreements']
            for key, value in phase27_pre.items():
                if key.startswith('failed:'):
                    pre[key] += value
            raws = [raw for raw, _ in rwp.turn_observations(events)]
            earlier_in_window = False
            for turn, observations in zip(turns, raws):
                if not turn['verified']:
                    continue
                where = [source, episode_id, turn['actor_turn']]
                final = turn['final_report_required'] is True
                context, field = turn['context'], turn['field']
                window = t2_window(turn['final_report_required'], field, context['upgrade'])
                report = turn['historical']['class'] == 'report'
                stratum = rwp.stratum_of(context, final) if report else None
                control = rwp.arm_messages(turn['history'], turn['user'], 'C', field)
                treated = t2_messages(turn['history'], turn['user'], field, window)
                pre['report_required_turns'] += final
                pre['report_turns'] += report
                if content_hash(control) != turn['stored_messages_hash']:
                    pre['control_differs_from_stored'] += 1
                    problems.append(['control', *where])
                if window != independent_t2_window(turn['final_report_required'], observations, intent):
                    pre['window_rule_disagreements'] += 1
                    problems.append(['window_rule', *where])
                runtime_unknown = any(context[op]['status'] == 'UNKNOWN' for op in ('upgrade', 'notification'))
                if final and runtime_unknown != states_unknown(field):
                    pre['report_required_unknown_rule_disagreements'] += 1
                    problems.append(['unknown_rule', *where])
                if report and stratum in PHASE27_GUARD_STRATA:
                    pre['phase27_guard_prompts'] += 1
                    pre[f'phase27_guard_prompts:{stratum}'] += 1
                    pre['phase27_guard_prompts_in_window'] += window
                    pre['phase27_guard_prompts_identical_to_control'] += content_hash(treated) == content_hash(control)
                if summary.get('case') == lp.TERMINAL_REJECTION_CASE:
                    pre['terminal_rejection_case_turns'] += 1
                    pre['terminal_rejection_case_turns_in_window'] += window
                if not window:
                    pre['out_of_window_turns'] += 1
                    if content_hash(treated) != turn['stored_messages_hash'] or treated != control:
                        pre['t2_differs_from_control_outside_window'] += 1
                        problems.append(['outside', *where])
                    continue
                pre['in_window_turns'] += 1
                pre['in_window_not_report_required'] += not final
                pre['in_window_terminal_rejection'] += terminal_rejection(context['upgrade'])
                pre['in_window_non_report_turns'] += not report
                pre['in_window_after_earlier_in_window_turn'] += earlier_in_window
                earlier_in_window = True
                if treated != rwp.arm_messages(turn['history'], turn['user'], 'T', field):
                    pre['t2_differs_from_phase27_t_in_window'] += 1
                    problems.append(['phase27_t', *where])
                if content_hash(treated) == content_hash(control):
                    pre['t2_equals_control_in_window'] += 1
                    problems.append(['unchanged', *where])
                elif lp.added_keys(treated, control) != [T2_FIELD]:
                    pre['structural_violations'] += 1
                    problems.append(['structure', *where])
                if report:
                    pre[f'in_window_report_turns:{stratum}'] += 1
                    slim = {key: turn[key] for key in ('actor_turn', 'final_report_required', 'historical',
                                                       'context', 'response_contract')}
                    in_window.append((summary, {**slim, 'stratum': stratum}))
    failures = {key.split(':', 1)[1]: n for key, n in pre.items() if key.startswith('failed:')}
    verification = {'turns': pre['turns'], 'verified': pre['verified'], 'failed': pre['turns'] - pre['verified'],
                    'failures_by_reason': dict(sorted(failures.items())),
                    'pass_rate': pre['verified'] / pre['turns'] if pre['turns'] else None,
                    'episodes_by_source': dict(sorted(by_source.items()))}
    summary = {key: value for key, value in sorted(pre.items()) if not key.startswith('failed:')}
    for key in PRECHECK_ZERO:
        summary.setdefault(key, 0)
    summary['turns_checked'] = pre['verified']
    summary['problem_examples'] = problems[:20]
    summary['passed'] = (pre['verified'] > 0 and pre['in_window_turns'] > 0
                         and pre['in_window_turns'] + pre['out_of_window_turns'] == pre['verified']
                         and pre['phase27_guard_prompts'] > 0
                         and pre['phase27_guard_prompts_identical_to_control'] == pre['phase27_guard_prompts']
                         and len(in_window) == pre['in_window_turns']
                         and all(summary[key] == 0 for key in PRECHECK_ZERO))
    return in_window, verification, summary


# ---------------------------------------------------------------- populations (pure)

prompt_key = rwp.prompt_key
sample_cell = rwp.sample_cell
webster_allocation = rwp.webster_allocation


def allocate_sample(stratum, pairs, size):
    """Phase 27's allocation rule with this phase's seed: every prompt when size is None; otherwise
    Webster's allocation across (source, case, episode arm) cells, and within a cell the first prompts by
    seeded rank. Returns (chosen pairs in seeded rank order, {cell: {'available', 'chosen'}})."""
    cells = defaultdict(list)
    for pair in pairs:
        cells[sample_cell(pair[0])].append(pair)
    for cell in cells:
        cells[cell].sort(key=lambda pair: rank(stratum, prompt_key(*pair)))
    seats = ({cell: len(members) for cell, members in cells.items()} if size is None
             else webster_allocation({cell: len(members) for cell, members in cells.items()}, size))
    chosen = [pair for cell in sorted(cells) for pair in cells[cell][:seats[cell]]]
    chosen.sort(key=lambda pair: rank(stratum, prompt_key(*pair)))
    return chosen, {cell: {'available': len(cells[cell]), 'chosen': seats[cell]} for cell in sorted(cells)}


def select_populations(reports, phase27_sent, *, sizes=None):
    """Declared strata and samples over the in-window report turns. Input order never matters. Prompts of a
    FRESH_ONLY stratum that Phase 27 sent are excluded, and every one of them must be found."""
    sizes = STRATUM_SIZES if sizes is None else sizes
    available, excluded = defaultdict(list), Counter()
    historical = defaultdict(Counter)
    found = set()
    for summary, turn in sorted(reports, key=lambda pair: prompt_key(*pair)):
        stratum = turn['stratum']
        verdict = rwp.judge(rwp.report_words(turn['historical']), turn['context'])
        historical[stratum]['reports'] += 1
        historical[stratum]['unsupported'] += verdict['unsupported']
        historical[stratum]['correct'] += verdict['correct']
        if stratum not in sizes:
            excluded[f'{stratum}:not_sent'] += 1
            continue
        key = prompt_key(summary, turn)
        if stratum in FRESH_ONLY and key in set(phase27_sent.get(stratum, ())):
            found.add((stratum, key))
            excluded[f'{stratum}:sent_in_phase27'] += 1
            continue
        available[stratum].append((summary, turn))
    for stratum in FRESH_ONLY:
        missing = set(phase27_sent.get(stratum, ())) - {key for s, key in found if s == stratum}
        if missing:
            raise PlanningError(f'{len(missing)} {stratum} prompts that Phase 27 sent are not {stratum} prompts in '
                                'this survey; the populations changed and nothing is planned')
    chosen, allocation = {}, {}
    for stratum, size in sizes.items():
        chosen[stratum], allocation[stratum] = allocate_sample(stratum, available.get(stratum, []), size)
    return {'chosen': chosen, 'available': {s: len(v) for s, v in sorted(available.items())},
            'allocation': allocation, 'excluded': dict(sorted(excluded.items())),
            'historical_by_stratum': {s: dict(c) for s, c in sorted(historical.items())}}


# ---------------------------------------------------------------- Phase 27's sent prompts and read-outs

def phase27_reference(plan_path=None, readouts_path=None):
    """What this phase takes from Phase 27, from its pinned files: the U2 prompts it sent, and its U2
    discordance C against T (for one descriptive pooled figure). Refuses unless both files are the pinned ones."""
    plan_path = pathlib.Path(plan_path or PHASE27_PLAN)
    readouts_path = pathlib.Path(readouts_path or PHASE27_READOUTS)
    if not plan_path.is_file() or sha256_file(plan_path) != PHASE27_PLAN_SHA256:
        raise PlanningError("artifacts/phase27-2026-09-24/live/plan.json is not Phase 27's pinned sent plan")
    if not readouts_path.is_file() or sha256_file(readouts_path) != PHASE27_READOUTS_SHA256:
        raise PlanningError("artifacts/phase27-2026-09-24/live/readouts.json is not Phase 27's pinned read-out")
    plan = json.loads(plan_path.read_text())
    if content_hash(plan) != PHASE27_PLAN_HASH:
        raise PlanningError("Phase 27's plan does not hash to its reviewed plan hash cd3b7bc8...")
    sent = defaultdict(set)
    for request in plan['requests']:
        if request['stratum'] in FRESH_ONLY:
            sent[request['stratum']].add(request['prompt_id'])
    if len(sent['U2']) != PHASE27_U2_SENT:
        raise PlanningError(f"Phase 27's plan names {len(sent['U2'])} U2 prompts, not {PHASE27_U2_SENT}")
    primary = json.loads(readouts_path.read_text())['primary']
    tests = primary['tests']['C']
    reference = {'u2_prompts': primary['planned_prompts'], 'c_bad_worst_case': primary['arms']['C']['bad_worst_case'],
                 't_bad_worst_case': primary['arms']['T']['bad_worst_case'],
                 'c_only_bad': tests['t_only_better'], 't_only_bad': tests['t_only_worse'],
                 'source': 'artifacts/phase27-2026-09-24/live/readouts.json (primary, arms C and T; T is T2 on U2)'}
    return {stratum: sorted(ids) for stratum, ids in sent.items()}, reference


# ---------------------------------------------------------------- pass 2: the request plan

def build_requests(connections, populations, model=EXPECTED_ACTOR_MODEL):
    """Rebuild each chosen prompt again, re-verify it and its window, and lay out the ordered request list."""
    needed = defaultdict(set)
    for pairs in populations['chosen'].values():
        for summary, turn in pairs:
            needed[(summary['source'], summary['episode_id'])].add(turn['actor_turn'])
    rebuilt = {}
    for (source, episode_id) in sorted(needed):
        connection = connections[source]
        turns, _, _ = rwp.survey_episode(lp.load_events(connection, episode_id), lp.load_intent(connection, episode_id),
                                         {'episode_id': episode_id}, keep=True)
        for turn in turns:
            if turn['actor_turn'] in needed[(source, episode_id)]:
                if not turn['verified']:
                    raise PlanningError(f'Selected prompt {source}:{episode_id}:{turn["actor_turn"]} failed verification on rebuild')
                rebuilt[(source, episode_id, turn['actor_turn'])] = turn
    prompts, rows = {}, defaultdict(list)
    for stratum, pairs in populations['chosen'].items():
        population = STRATUM_POPULATION[stratum]
        for summary, turn in pairs:
            source = rebuilt[(summary['source'], summary['episode_id'], turn['actor_turn'])]
            prompt_id = prompt_key(summary, turn)
            window = t2_window(source['final_report_required'], source['field'], source['context']['upgrade'])
            if not window:
                raise PlanningError(f"Prompt {prompt_id} is not in T2's window; T2 would equal the control")
            response_format = response_format_for(response_contract=source['response_contract'])
            control = arm_messages(source['history'], source['user'], 'C', source['field'], window)
            control_request_hash = content_hash({'messages': control, 'response_format': response_format})
            if (content_hash(control), control_request_hash) != (source['stored_messages_hash'], source['stored_request_hash']):
                raise PlanningError(f'Control prompt {prompt_id} is not the stored request')
            historical = source['historical']
            verdict = rwp.judge(rwp.report_words(historical), source['context'])
            for arm in sorted(STRATUM_ARMS[stratum], key=lambda a: rank('arm', prompt_id, a)):
                messages = arm_messages(source['history'], source['user'], arm, source['field'], window)
                request_hash = content_hash({'messages': messages, 'response_format': response_format})
                if arm in ('C', 'R') and request_hash != control_request_hash:
                    raise PlanningError(f'Arm {arm} of prompt {prompt_id} is not the stored request')
                if arm == 'T2' and request_hash == control_request_hash:
                    raise PlanningError(f'Arm T2 of prompt {prompt_id} is identical to the control')
                if request_hash not in prompts:
                    bound = validate_request_input(messages, model, response_contract=source['response_contract'])
                    prompts[request_hash] = {'request_hash': request_hash, 'messages_hash': content_hash(messages),
                                             'response_contract': source['response_contract'],
                                             'response_format': response_format, 'messages': messages,
                                             'input_token_bound': bound}
                rows[population].append({
                    'population': population, 'stratum': stratum, 'prompt_id': prompt_id, 'source': summary['source'],
                    'episode_id': summary['episode_id'], 'actor_turn': turn['actor_turn'], 'case': summary['case'],
                    'episode_arm': summary['arm'], 'arm': arm, 'repeat': 0,
                    'final_report_required': source['final_report_required'],
                    'response_contract': source['response_contract'], 'request_hash': request_hash,
                    'messages_hash': prompts[request_hash]['messages_hash'],
                    'input_token_bound': prompts[request_hash]['input_token_bound'],
                    'context': source['context'], 't2_window': window,
                    'historical': {**historical, 'raw_sha256': source['raw_sha256'],
                                   'words': rwp.report_words(historical), 'judged': verdict}})
    requests = []
    for population in POPULATION_ORDER:
        order = {p: rank('order', population, p) for p in {r['prompt_id'] for r in rows[population]}}
        requests += sorted(rows[population], key=lambda r: (order[r['prompt_id']], rank('arm', r['prompt_id'], r['arm'])))
    for index, request in enumerate(requests, 1):
        request['request_id'] = f'r{index:04d}'
    return requests, prompts


# ---------------------------------------------------------------- settings, pins, plan

def check_pins(pins):
    rwp.check_pins(pins)
    if pins['per_request_dollar_bound'] != PER_REQUEST_DOLLAR_BOUND:
        raise PlanningError('The per-request dollar bound is not the declared $0.0209')


def check_files():
    """The immutable inputs: settings, the freeze record and Phase 21's harness (Phase 27's check), plus
    Phase 27's harness, Phase 26's runner and Phase 27's sent plan and read-outs."""
    problem = phase27_harness_problem()
    if problem:
        raise PlanningError(problem)
    rwp.check_files()
    problem = phase26_runner_problem()
    if problem:
        raise PlanningError(problem)


def check_budget(total_requests, spend_cap):
    if not (type(spend_cap) in (int, float) and math.isfinite(spend_cap) and 0 < spend_cap <= HARD_SPEND_CAP):
        raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    if SpendGuard.micro(total_requests * PER_REQUEST_DOLLAR_BOUND) > SpendGuard.micro(spend_cap):
        raise PlanningError(f'{total_requests} planned requests exceed the ${spend_cap:.2f} cap at ${PER_REQUEST_DOLLAR_BOUND}/request')


def cap_problem():
    if not (type(HARD_SPEND_CAP) in (int, float) and 0 < HARD_SPEND_CAP <= PROGRAM_PHASE_CAP):
        return f"HARD_SPEND_CAP (${HARD_SPEND_CAP}) is above the program's ${PROGRAM_PHASE_CAP:.2f} cap for Phase 30"
    return None


def readout_rules():
    return {
        'word_rule': ("Phase 27's (report_word_probe.judge): per operation match | allowed_pair (UNKNOWN <-> NOT_STARTED "
                      'for an operation never written and never shown other than UNKNOWN) | unsupported (PENDING, '
                      'SUCCEEDED or FAILED that no delivered observation of that operation shows; NOT_STARTED after a '
                      'write or a non-UNKNOWN status; NOT_REQUIRED without a delivered FAILED upgrade) | other_mismatch; '
                      'a report is correct when both words are match or allowed_pair'),
        'structural_guard': ("$0: on every verified development v4 turn outside T2's window (every tool turn, every "
                             "voluntary turn, every prompt of Phase 27's guard strata G1-G5, terminal rejection "
                             'included) T2 is byte-identical to the control; the plan is refused otherwise, so this '
                             'is PASS in any plan that exists, by construction: nothing is sent there and it is '
                             'never quoted as a measured pass'),
        'in_window_guard': ('U1 + U3 (T2 shown, not the target), arms R and T2. OK = a received report with both words '
                            'correct; a received non-report is not OK in either arm. Two exact one-sided sign tests on '
                            '(T2 not OK, R OK) against (R not OK, T2 OK), among prompts where R and T2 were both '
                            f'received: pooled U1 + U3, and {GUARD_ALONE_STRATUM} alone. Each part is INCOMPLETE unless '
                            f'>= {COMPLETE_MIN} of its own planned prompts were compared, else FAIL iff its p < '
                            f'{GUARD_ALPHA}, else PASS. The guard is FAIL if either part fails, else INCOMPLETE if '
                            'either part is incomplete, else PASS. No tolerance'),
        'non_inferiority': ("U2 (prompts not sent in Phase 27), arms C and T2. Phase 27's worst case for T2: T2 bad "
                            'unless a received report with both words correct; C bad only for a received report with '
                            'an unsupported word; every planned prompt counts (a missing T2 is bad, a missing C is '
                            f'not). Tango score test, H0: P(T2 bad) - P(C bad) >= {NI_MARGIN} ({100 * float(NI_MARGIN):.1f} percentage points); '
                            f'PASS iff one-sided p < {NI_ALPHA}; INCOMPLETE unless C and T2 each received >= '
                            f'{COMPLETE_MIN} of the planned prompts. A PASS does not imply benefit'),
        'reduction': (f'descriptive, never deciding: exact one-sided McNemar T2 < C on the worst-case discordance '
                      f'(p < {REDUCTION_ALPHA}), and the same pooled with Phase 27\'s U2 discordance (copied into '
                      'the plan); at the measured ~1.6-1.8% re-send slip rate this size cannot reliably show a '
                      'reduction (about 55-66% even for a field that removes every slip)'),
        'descriptive': ('per arm and stratum: reports, word pairs, word classes, response classes, R-to-T2 '
                        'transitions, citations of the stated label, C and R byte-identical to history, provider'),
        'decision': ('RECOMMENDED_FOR_A_LATER_LOOP iff structural guard PASS, in-window guard PASS and '
                     'non-inferiority PASS; otherwise NOT_RECOMMENDED')}


def field_shape():
    """How T2 looks on a U2 turn and on a U1 turn (its value is Phase 27's T)."""
    u2 = {'note': T2_NOTE, 'orders': {'evidence': 'obs-3', 'status': 'SUCCEEDED'},
          'notifications': {'evidence': 'obs-6', 'status': 'UNKNOWN'}}
    u1 = {'note': T2_NOTE, 'orders': {'evidence': 'obs-4', 'status': 'UNKNOWN'}, 'notifications': None}
    return {'u2_example': canonical_json({T2_FIELD: u2})[1:-1], 'u1_example': canonical_json({T2_FIELD: u1})[1:-1],
            'note_characters': len(T2_NOTE)}


def build_plan(*, store=STORE, phase20_store=PHASE20_STORE, phase20_plan=PHASE20_PLAN, settings_path=None,
               spend_cap=HARD_SPEND_CAP, cutoff=STORE_CUTOFF, phase27_plan=None, phase27_readouts=None):
    problem = cap_problem()
    if problem:
        raise PlanningError(f'{problem}; nothing is planned')
    settings_path = pathlib.Path(settings_path or ROOT / DECLARED_SETTINGS)
    if sha256_file(settings_path) != DECLARED_SETTINGS_SHA256:
        raise PlanningError('The settings file is not the declared Phase 17 settings file')
    check_files()
    for path, expected in ((phase20_store, rwp.PHASE20_STORE_SHA256), (phase20_plan, rwp.PHASE20_PLAN_SHA256)):
        if sha256_file(path) != expected:
            raise PlanningError(f'{pathlib.Path(path).name} is not the pinned Phase 20 file')
    phase27_sent, phase27_u2 = phase27_reference(phase27_plan, phase27_readouts)
    pins = configuration_pins(settings_from_file(settings_path, env_path=os.devnull))
    check_pins(pins)
    connections = rwp.open_sources(store, phase20_store)
    try:
        reports, verification, precheck = survey(connections, cutoff=cutoff, cases=rwp.phase20_cases(phase20_plan))
        if not precheck['passed']:
            raise PlanningError("The $0 T2 pre-check failed (T2's window or construction); nothing may be sent")
        populations = select_populations(reports, phase27_sent)
        requests, prompts = build_requests(connections, populations, pins['actor_model'])
    finally:
        for connection in connections.values():
            connection.close()
    total = len(requests)
    check_budget(total, spend_cap)
    counts = Counter((r['stratum'], r['arm']) for r in requests)
    attempts_under_cap = SpendGuard.micro(spend_cap) // SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND)
    plan = {
        'schema_version': SCHEMA, 'experiment': 'phase30_actor_narrow_report_field_replay_probe',
        'scoring': 'NON_SCORING_NEVER_FED_BACK', 'split': 'development',
        'sources': {'main': {'store': 'artifacts/lab.sqlite3', 'purpose': rwp.MAIN_PURPOSE, 'store_cutoff': cutoff},
                    'phase20': {'store': 'artifacts/phase20-2026-09-23/run-1/lab.sqlite3', 'purpose': rwp.PHASE20_PURPOSE,
                                'store_sha256': rwp.PHASE20_STORE_SHA256, 'plan_sha256': rwp.PHASE20_PLAN_SHA256}},
        'harness_sha256': sha256_file(__file__), 'phase27_harness_sha256': PHASE27_HARNESS_SHA256,
        'phase21_harness_sha256': rwp.PHASE21_HARNESS_SHA256, 'phase26_runner_sha256': PHASE26_RUNNER_SHA256,
        'phase27_plan_sha256': PHASE27_PLAN_SHA256, 'phase27_plan_hash': PHASE27_PLAN_HASH,
        'phase27_readouts_sha256': PHASE27_READOUTS_SHA256,
        'source_sha256': {name: sha256_file(ROOT / name) for name in SOURCE_FILES},
        'actor_prompt_hash': rwp.ACTOR_PROMPT_HASH, 'actor_context_protocol': ACTOR_CONTEXT_PROTOCOL_V4,
        'settings_file': DECLARED_SETTINGS, 'settings_sha256': DECLARED_SETTINGS_SHA256,
        'freeze_file': FREEZE_FILE, 'freeze_sha256': FREEZE_SHA256, **pins,
        'provider_call': {'role': 'actor', 'max_output_tokens': lp.ACTOR_MAX_OUTPUT_TOKENS,
                          'timeout_seconds': lp.ACTOR_TIMEOUT_SECONDS,
                          'response_format': 'response_format_for(stored response_contract)',
                          'blind_retry': list(lp.RETRYABLE_TRANSPORT_CODES) + [
                              f'at most once, charged, after {lp.BLIND_RETRY_WAIT_SECONDS} s'],
                          'backoff_after_errored_request_seconds': list(lp.BACKOFF_SECONDS),
                          'consecutive_errored_requests_stop': lp.CONSECUTIVE_ERROR_ABORT,
                          'served_model': 'recorded from each response, never enforced'},
        'arms': {'C': ARM_TEXT['C'], 'R': ARM_TEXT['R'],
                 'T2': {'field': T2_FIELD, 'note': T2_NOTE, 'value': T2_VALUE_RULE, 'window': T2_WINDOW_RULE},
                 'shape': field_shape()},
        'sampling': {'seed': SAMPLE_SEED, 'sizes': STRATUM_SIZES, 'arms_by_stratum': STRATUM_ARMS,
                     'strata': STRATUM_RULES, 'fresh_only': list(FRESH_ONLY), 'available': populations['available'],
                     'rule': ("a sized stratum is allocated across (source, case, episode arm) cells by Webster's "
                              'divisor method in proportion to the prompts each cell holds (house-monotone; ties to '
                              'the first cell by name); within a cell the first prompts by sha256 rank; U2 prompts '
                              'that Phase 27 sent are excluded first'),
                     'allocation': populations['allocation'],
                     'order': ('populations in order ' + ', '.join(POPULATION_ORDER) + '; prompts by sha256 rank; '
                               'arms of a prompt back to back by sha256 rank')},
        'populations': {'chosen': {s: len(v) for s, v in populations['chosen'].items()},
                        'excluded': populations['excluded'],
                        'historical_by_stratum': populations['historical_by_stratum']},
        'phase27_u2_reference': phase27_u2,
        'readout_rules': readout_rules(),
        'thresholds': {'ni_margin': str(NI_MARGIN), 'ni_alpha': NI_ALPHA, 'ni_test': 'Tango (1998) score test',
                       'guard_alpha': GUARD_ALPHA, 'guard_alone_stratum': GUARD_ALONE_STRATUM,
                       'reduction_alpha': REDUCTION_ALPHA, 'complete_min': str(COMPLETE_MIN)},
        'verification': verification, 'precheck': precheck,
        'counts': {'by_stratum_and_arm': {f'{s}/{a}': n for (s, a), n in sorted(counts.items())},
                   'by_population': dict(Counter(r['population'] for r in requests)),
                   'total_requests': total, 'distinct_prompts': len(prompts)},
        'cost': {'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                 'planned_upper_bound': round(total * PER_REQUEST_DOLLAR_BOUND, 6), 'spend_cap': spend_cap,
                 'phase_spend_cap': HARD_SPEND_CAP, 'program_phase_cap': PROGRAM_PHASE_CAP,
                 'max_attempts_under_cap': attempts_under_cap, 'retry_headroom_attempts': attempts_under_cap - total},
        'max_input_token_bound': max(p['input_token_bound'] for p in prompts.values()),
        'requests': requests,
    }
    return plan, prompts


def plan_hash(plan):
    return content_hash(plan)


# ---------------------------------------------------------------- guards: output, claims, other paid runs

def _root(root=None):
    """The repository root, read at call time so tests can point every guard at a tmp tree."""
    return pathlib.Path(root if root is not None else ROOT)


def _final(manifest):
    return manifest.get('status') in FINAL_STATUSES and bool(manifest.get('ended_at'))


def delivered_generations(manifest):
    return lp.delivered_generations(manifest)


def claimed_output(artifacts, out):
    """The output directory a claim names: artifacts/phase30-<date>/<name>, relative, nothing else."""
    parts = pathlib.PurePosixPath(out).parts if isinstance(out, str) and out else ()
    if (len(parts) != 3 or parts[0] != 'artifacts' or not parts[1].startswith(PHASE_PREFIX) or parts[1] == CLAIM_DIR
            or any(part in ('', '.', '..') for part in parts)):
        return None
    return pathlib.Path(artifacts).parent / parts[0] / parts[1] / parts[2]


def _charge(manifest, path):
    charged = manifest.get('charged_upper_bound')
    if type(charged) not in (int, float) or not math.isfinite(charged) or charged < 0:
        raise PlanningError(f'An earlier live run does not state a readable charged_upper_bound ({path}); '
                            'the phase cap cannot be applied. Investigate before any run')
    return charged


def live_run_records(artifacts):
    """Every earlier Phase 30 live run; refuses unless each is final and delivered nothing (as Phase 27)."""
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
            raise PlanningError(f'{claim.name} claims a live run with no manifest; if its process is gone, close it at '
                                f'$0 with --finalize-abandoned artifacts/{CLAIM_DIR}/{claim.name}')
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
            raise PlanningError(f'A live narrow-field run already exists ({path}); a second draw would be '
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


RUN_PATH_PART = re.compile(r'[A-Za-z0-9._-]+')


def check_output(out, *, root=None, live=True):
    """A new directory exactly artifacts/phase30-<date>/<name> (letters, digits, '.', '_', '-'), never an
    existing one."""
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


def _manifest_final_marker(manifest):
    """A run manifest is finished only when it says so: an end time, and no status or stop reason that
    means still running."""
    if not isinstance(manifest, dict) or not manifest.get('ended_at'):
        return False
    return all(str(manifest.get(key, '')).lower() not in ('running', 'starting') for key in ('status', 'stop_reason'))


def _is_run_manifest(record):
    return isinstance(record, dict) and 'started_at' in record


def other_run_files(*, root=None, ignore=()):
    """Other phases' run records that may still be running: a run manifest (a JSON object with started_at)
    without its end marker, an unreadable *manifest*.json, or a launch claim whose run directory holds no
    finished run manifest. Only directories of Phases 20, 21, 23, 25-29 and 31+ are read (never 22 or 24),
    and a claim is followed only to a run directory of one of those phases."""
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


def other_paid_runs(*, root=None, ignore=(), processes=None):
    """Everything that may be another paid run: run records (other_run_files) and experiment processes
    (Phase 26's token rule; never set aside by --ignore-manifest)."""
    found = other_run_files(root=root, ignore=ignore)
    found += list((processes or experiment_processes)())
    return found


def check_other_runs(args, *, root=None, status=None, processes=None):
    """One paid run at a time: no other run record may be open, no other --execute-live experiment process
    may exist, and the backend (if up) must show no active campaign. Returns what was seen, for the manifest."""
    active = other_paid_runs(root=root, ignore=getattr(args, 'ignore_manifest', None) or (), processes=processes)
    if active:
        raise PlanningError(f'Another paid run may be in progress ({active[0]}); one paid run at a time. If a run '
                            'record belongs to a crashed run, pass its exact path to --ignore-manifest')
    state, body = (status or backend_status)()
    if state == 'up' and (not isinstance(body, dict) or 'active_campaign_id' not in body
                          or body['active_campaign_id'] is not None):
        raise PlanningError('The lab backend shows an active campaign (or an unreadable status); one paid run at a time')
    return {'backend': state, 'active_campaign_id': None if body is None else body.get('active_campaign_id'),
            'processes': 'none'}


def take_claim(out, plan_hash_value, harness, *, root=None, spend_cap=None, expected_earlier=None):
    """Atomically claim the next live run (as Phase 27: private file, then hard link; never deleted)."""
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
    """False only when the claim's process is gone or is no longer this harness."""
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
    return not command.strip() or 'report_narrow_probe' in command


def finalize_abandoned(claim, *, root=None, alive=None):
    """Close, at $0, a claimed run whose process died before its manifest became final (as Phase 27)."""
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
    # Fail closed (review round 1, B3): a cut-off last line is a response being written when the process died,
    # and lapse_probe.run_requests counts a delivery before it saves the manifest, so the saved manifest can
    # still say 0. A truncated line therefore counts as delivered, as an unreadable record counts as running.
    delivered = sum(entry_delivered(r) for r in results) + partial
    now = datetime.now(timezone.utc).isoformat()
    manifest = dict(existing) if existing else {
        'schema_version': SCHEMA, 'mode': 'live', 'plan_hash': record.get('plan_hash'),
        'harness_sha256': record.get('harness_sha256'), 'claim': str(path.relative_to(artifacts.parent)),
        'pid': pid, 'spend_cap': record.get('spend_cap'), 'started_at': None, 'traceback': None}
    manifest.update({
        'status': 'ABORTED', 'stop_reason': 'abandoned', 'ended_at': now, 'requests_done': len(results),
        'statuses': dict(sorted(Counter(str(r.get('status')) if isinstance(r, dict) else 'unreadable'
                                        for r in results).items())),
        'generations_delivered': None if prior is None else max(prior, delivered),
        'attempts': attempts,
        'charged_upper_bound': attempts * SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND) / 1_000_000,
        'finalized_abandoned': {
            'at': now, 'claim': str(path.relative_to(artifacts.parent)), 'pid': pid, 'pid_alive': False,
            'previous_status': previous_status, 'responses_lines': len(results), 'partial_lines_skipped': partial,
            'unrecorded_in_flight_attempts_charged': in_flight,
            'rule': ('delivered = ok or empty responses, or any attempt that returned a response object or usage, '
                     'plus every cut-off (partial) line, which counts as delivered (fail closed); charged = recorded '
                     'attempts plus up to two unrecorded in-flight attempts when RUNNING')}})
    output.mkdir(parents=True, exist_ok=True)
    write_json(manifest_path, manifest)
    return manifest_path, manifest


def check_review(protocol_text, protocol_sha256, harness, plan_hash_value, *, root=None):
    """The review is enforced, not only procedural (as Phases 25 and 27). The record must name this harness's
    phase cap, who approved, and the owner's approval quoted verbatim exactly as the protocol quotes it.
    Returns the owner's answer."""
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
    if (type(cap) not in (int, float) or not math.isfinite(cap)
            or SpendGuard.micro(cap) != SpendGuard.micro(HARD_SPEND_CAP)):
        raise PlanningError(f"The review record does not name this harness's phase cap as phase_cap "
                            f'({HARD_SPEND_CAP:.2f}); live execution refuses')
    if not (isinstance(record.get('approved_by'), str) and record['approved_by'].strip()):
        raise PlanningError('The review record names no approver (approved_by); live execution refuses')
    answer = record.get('owner_answer')
    if not (isinstance(answer, dict)
            and all(isinstance(answer.get(key), str) and answer[key].strip() for key in OWNER_ANSWER_FIELDS)):
        raise PlanningError("The review record carries no owner_answer with verbatim, given_by and date (the owner's "
                            'approval of this program); live execution refuses')
    if answer['verbatim'] not in protocol_text:
        raise PlanningError("The owner's verbatim answer in the review record is not quoted in the protocol; the "
                            'protocol and the record must carry the same words')
    return answer


# ---------------------------------------------------------------- live execution

class Recorder(lp.Recorder):
    """Phase 21's recorder (fsynced response lines, scrubbed secrets), writing this probe's manifest."""

    def save(self):
        path = self.out / MANIFEST_NAME
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(self.scrub(json.dumps(self.manifest, indent=2, ensure_ascii=False)) + '\n')
        os.replace(temporary, path)


def openai_client_factory(**kwargs):
    """The provider client RuntimeProvider would build itself (read at call time; tests replace it)."""
    from openai import AsyncOpenAI
    return AsyncOpenAI(**kwargs)


def run_live(args, plan, prompts, *, sleep=asyncio.sleep, status=None, processes=None):
    out = check_output(args.out)
    check_other_runs(args, status=status, processes=processes)
    harness = sha256_file(__file__)
    if args.expect_harness_sha256 != harness:
        raise PlanningError('--expect-harness-sha256 does not match this script')
    if not PROTOCOL.exists():
        raise PlanningError('No protocol at docs/part2/PHASE30_EXPERIMENT.md; live execution refuses until one is reviewed')
    protocol_sha256 = sha256_file(PROTOCOL)
    if args.expect_protocol_sha256 != protocol_sha256:
        raise PlanningError('--expect-protocol-sha256 does not match the protocol file')
    if args.expect_plan_hash != plan_hash(plan):
        raise PlanningError('The recomputed plan differs from the reviewed dry plan (--expect-plan-hash)')
    protocol_text = PROTOCOL.read_text()
    if harness not in protocol_text or plan_hash(plan) not in protocol_text:
        raise PlanningError('The protocol does not declare this harness sha256 and this plan hash')
    owner_answer = check_review(protocol_text, protocol_sha256, harness, plan_hash(plan))
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
    if settings.model_for_role('actor') != EXPECTED_ACTOR_MODEL:
        raise PlanningError('The Actor role does not resolve to the declared model')
    seen = check_other_runs(args, status=status, processes=processes)
    stop_requested = False
    recorder = None

    def request_stop(*_):
        nonlocal stop_requested
        stop_requested = True

    async def execute():
        from app.providers.runtime import RuntimeProvider
        served = lp.ServedRecorder(base=lambda **kwargs: openai_client_factory(**kwargs))
        async with RuntimeProvider(settings, live_authorized=True, client_factory=served) as provider:
            return await lp.run_requests(plan['requests'], prompts, provider, guard, recorder,
                                         stop=lambda: stop_requested, served=served, sleep=sleep)

    # The handlers go in before the claim, so from the claim on an operator stop is recorded as a stop in a
    # final manifest; it can never leave a claim without one.
    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if stop_requested:
            raise PlanningError('An operator stop arrived before the claim; nothing was claimed or sent')
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
                    'phase27_harness_sha256': PHASE27_HARNESS_SHA256,
                    'phase21_harness_sha256': rwp.PHASE21_HARNESS_SHA256,
                    'phase26_runner_sha256': PHASE26_RUNNER_SHA256,
                    'configuration_hash': pins['configuration_hash'], 'settings_sha256': DECLARED_SETTINGS_SHA256,
                    'freeze_sha256': FREEZE_SHA256, 'actor_model': pins['actor_model'], 'spend_cap': spend_cap,
                    'spend_cap_requested': args.spend_cap, 'phase_spend_cap': HARD_SPEND_CAP,
                    'program_phase_cap': PROGRAM_PHASE_CAP,
                    'owner_answer': {key: owner_answer[key] for key in OWNER_ANSWER_FIELDS},
                    'earlier_undelivered_charged': round(HARD_SPEND_CAP - phase_spend_remaining(earlier), 6),
                    'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                    'claim': str(claim.relative_to(artifacts.parent)), 'earlier_undelivered_runs': earlier,
                    'other_runs_check': seen, 'ignored_manifests': list(getattr(args, 'ignore_manifest', None) or ()),
                    'requests_planned': plan['counts']['total_requests'], 'requests_done': 0, 'attempts': 0,
                    'charged_upper_bound': 0.0, 'statuses': {}, 'generations_delivered': 0,
                    'measured_input_tokens': 0, 'measured_output_tokens': 0, 'backoff_waits': [],
                    'stop_reason': None, 'traceback': None,
                    'started_at': datetime.now(timezone.utc).isoformat(), 'ended_at': None}
        recorder = Recorder(out, manifest, secrets=(settings.wandb_api_key, settings.typesafe_api_key))
        try:
            recorder.save()
            write_json(out / 'plan.json', plan)
            with (out / 'prompts.jsonl').open('w', encoding='utf-8') as handle:
                for request_hash in sorted(prompts):
                    handle.write(json.dumps(prompts[request_hash], sort_keys=True, ensure_ascii=False) + '\n')
            # The last check, after the claim exists and right before the first provider call: a sibling
            # runner that passed its own checks before this claim was visible is caught here, and this run
            # ends final at $0 with nothing sent, so a later launch is still allowed.
            try:
                manifest['other_runs_check_after_claim'] = check_other_runs(args, status=status, processes=processes)
            except PlanningError as blocked:
                manifest.update(status='STOPPED', stop_reason=OTHER_RUN_AFTER_CLAIM,
                                blockers_after_claim=recorder.scrub(str(blocked)))
            else:
                manifest['status'] = 'RUNNING'
                recorder.save()
                manifest['stop_reason'] = asyncio.run(execute())
                manifest['status'] = 'COMPLETED' if manifest['stop_reason'] == 'completed' else 'STOPPED'
        except Exception as error:  # noqa: BLE001 - recorded with its traceback, never silently dropped
            manifest.update(status='ABORTED', stop_reason=f'{type(error).__name__}',
                            traceback=recorder.scrub(traceback.format_exc()[-8000:]))
        finally:
            manifest['ended_at'] = datetime.now(timezone.utc).isoformat()
            recorder.save()
            recorder.close()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    results, partial = load_results(out / 'responses.jsonl')
    readouts = compute_readouts(plan, results, partial_lines_skipped=partial)
    write_json(out / 'readouts.json', readouts)
    print(json.dumps({'status': manifest['status'], 'stop_reason': manifest['stop_reason'],
                      'requests_done': manifest['requests_done'], 'attempts': manifest['attempts'],
                      'generations_delivered': manifest['generations_delivered'],
                      'charged_upper_bound': manifest['charged_upper_bound'],
                      'decision': readouts['decision'], 'output': str(out)}, indent=2))
    return 0 if manifest['status'] == 'COMPLETED' else 1


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
    directory = pathlib.Path(directory)
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable {MANIFEST_NAME} in {directory}; read-outs are tied to a run') from None
    plan, results, partial = load_run(directory)
    readouts = compute_readouts(plan, results, partial_lines_skipped=partial)
    harness_matches = isinstance(manifest, dict) and sha256_file(__file__) == manifest.get('harness_sha256')
    plan_matches = isinstance(manifest, dict) and plan_hash(plan) == manifest.get('plan_hash')
    # The word rule and exact statistics come from report_word_probe.py and lapse_probe.py, so both must
    # still be the pinned files.
    pinned = phase27_harness_problem() is None
    if harness_matches and plan_matches and pinned:
        return readouts
    if not allow_other_harness:
        raise PlanningError(f'{NOT_THE_RUNS_HARNESS} (harness matches the run: {harness_matches}; plan matches the '
                            f'run: {plan_matches}; report_word_probe.py and lapse_probe.py are the pinned files: '
                            f'{pinned}). Pass --not-the-runs-harness to print it labelled')
    return {'label': NOT_THE_RUNS_HARNESS, 'harness_matches_run': harness_matches, 'plan_matches_run': plan_matches,
            'pinned_imports_match': pinned, 'readouts': readouts}


# ---------------------------------------------------------------- statistics (pure)

def normal_cdf(z):
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def tango_z(b, c, n, margin):
    """Tango's (1998) score statistic for paired proportions, H0: p10 - p01 = margin, where b counts pairs
    with T2 bad and C not (p10) and c pairs with C bad and T2 not (p01). The restricted maximum-likelihood
    p01 solves 2n q^2 + (-(b + c) + margin (2n - b + c)) q - c margin (1 - margin) = 0; the statistic is
    (b - c - n margin) / sqrt(n (2q + margin (1 - margin))). None when it is undefined."""
    if not (isinstance(n, int) and n > 0 and 0 <= b and 0 <= c and b + c <= n):
        return None
    d = float(margin)
    if not -1 < d < 1:
        return None
    a_coefficient = 2 * n
    b_coefficient = -(b + c) + d * (2 * n - b + c)
    c_coefficient = -c * d * (1 - d)
    discriminant = b_coefficient * b_coefficient - 4 * a_coefficient * c_coefficient
    q = (math.sqrt(max(discriminant, 0.0)) - b_coefficient) / (2 * a_coefficient)
    variance = n * (2 * q + d * (1 - d))
    if variance <= 0:
        return None
    return (b - c - n * d) / math.sqrt(variance)


def noninferiority(b, c, n, margin=NI_MARGIN):
    """One-sided Tango test of H0: P(T2 bad) - P(C bad) >= margin. Returns (z, p); p = Phi(z)."""
    z = tango_z(b, c, n, margin)
    return (None, None) if z is None else (z, normal_cdf(z))


def difference_upper_bound(b, c, n, alpha=NI_ALPHA):
    """The one-sided (1 - alpha) upper confidence bound on P(T2 bad) - P(C bad) by inverting Tango's test:
    the smallest margin the test rejects at alpha, by bisection. Descriptive only."""
    if not (isinstance(n, int) and n > 0):
        return None
    low, high = (b - c) / n, 1 - 1e-9
    if noninferiority(b, c, n, high)[1] is None or noninferiority(b, c, n, high)[1] >= alpha:
        return None
    for _ in range(80):
        middle = (low + high) / 2
        p = noninferiority(b, c, n, middle)[1]
        if p is not None and p < alpha:
            high = middle
        else:
            low = middle
    return high


# ---------------------------------------------------------------- read-outs (pure)

_received = rwp._received
_report = rwp._report
report_verdict = rwp.report_verdict
response_outcome = rwp.response_outcome
worst_case_bad = rwp.worst_case_bad


def _ratio(k, n):
    return k / n if n else None


def _complete(received, planned):
    return planned > 0 and Fraction(received, planned) >= COMPLETE_MIN


def _by_prompt(rows):
    prompts = defaultdict(lambda: {'request': None, 'arms': {}, 'planned': set()})
    for request, result in rows:
        entry = prompts[request['prompt_id']]
        entry['request'] = entry['request'] or request
        entry['planned'].add(request['arm'])
        entry['arms'][request['arm']] = result
    return prompts


def t2_bad(result, context):
    """Phase 27's worst case for T: bad unless a received report with both words correct."""
    return worst_case_bad('T', report_verdict(result, context))


def c_bad(result, context):
    """Phase 27's rule for C: bad only for a received report with an unsupported word."""
    return worst_case_bad('C', report_verdict(result, context))


def ni_decision(*, planned, received, b, c):
    """The declared primary rule on counts: INCOMPLETE unless C and T2 each received >= 95% of the planned
    prompts; else PASS iff Tango's one-sided p < NI_ALPHA at NI_MARGIN, FAIL otherwise."""
    complete = all(_complete(received[arm], planned) for arm in ('C', 'T2'))
    z, p = noninferiority(b, c, planned, NI_MARGIN)
    passes = p is not None and p < NI_ALPHA
    status = 'INCOMPLETE' if not complete else 'PASS' if passes else 'FAIL'
    return {'status': status, 'complete': complete, 'planned_prompts': planned, 'margin': float(NI_MARGIN),
            'alpha': NI_ALPHA, 't2_only_bad': b, 'c_only_bad': c, 'tango_z': z, 'tango_one_sided_p': p,
            'difference_worst_case': _ratio(b - c, planned),
            'difference_upper_bound': difference_upper_bound(b, c, planned), 'upper_bound_level': 1 - NI_ALPHA}


def primary_readout(rows, phase27_reference_counts=None):
    prompts = _by_prompt(rows)
    planned = len(prompts)
    received, bad, reports, unsupported, incorrect, non_reports = (Counter() for _ in range(6))
    words, classes = defaultdict(Counter), defaultdict(Counter)
    b = c = both = 0
    received_only = [0, 0]
    all_reported = 0
    by_stratum = defaultdict(lambda: defaultdict(Counter))
    for entry in prompts.values():
        context = entry['request']['context']
        flags, verdicts = {}, {}
        for arm in ('C', 'T2'):
            result = entry['arms'].get(arm)
            received[arm] += _received(result)
            verdict = verdicts[arm] = report_verdict(result, context)
            if _received(result) and verdict is None:
                non_reports[arm] += 1
            if verdict is not None:
                reports[arm] += 1
                unsupported[arm] += verdict['unsupported']
                incorrect[arm] += not verdict['correct']
                report = _report(result)
                words[arm][f"{report.get('upgrade_outcome')}/{report.get('notification_outcome')}"] += 1
                classes[arm][f"{verdict['upgrade']}/{verdict['notification']}"] += 1
            flags[arm] = t2_bad(result, context) if arm == 'T2' else c_bad(result, context)
            bad[arm] += flags[arm]
            cell = rwp.sample_cell({'source': entry['request']['source'], 'case': entry['request']['case'],
                                    'arm': entry['request']['episode_arm']})
            by_stratum[cell][arm]['planned'] += 1
            by_stratum[cell][arm]['worst_case_bad'] += flags[arm]
        b += flags['T2'] and not flags['C']
        c += flags['C'] and not flags['T2']
        both += flags['T2'] and flags['C']
        if all(v is not None for v in verdicts.values()):
            all_reported += 1
            received_only[0] += verdicts['C']['unsupported'] and not verdicts['T2']['unsupported']
            received_only[1] += verdicts['T2']['unsupported'] and not verdicts['C']['unsupported']
    decision = ni_decision(planned=planned, received=received, b=b, c=c)
    arms = {arm: {'bad_worst_case' if arm == 'T2' else 'bad': bad[arm], 'planned': planned,
                  'rate': _ratio(bad[arm], planned), 'wilson95': wilson(bad[arm], planned),
                  'received': received[arm], 'reports': reports[arm],
                  'unsupported_among_reports': unsupported[arm],
                  'not_correct_among_reports': incorrect[arm], 'non_reports': non_reports[arm],
                  'words': dict(sorted(words[arm].items())), 'word_classes': dict(sorted(classes[arm].items()))}
            for arm in ('C', 'T2')}
    reduction_p = mcnemar_greater(c, b)
    reduction = {'c_only_bad': c, 't2_only_bad': b, 'mcnemar_exact_one_sided_p': reduction_p,
                 'p_below_alpha': reduction_p < REDUCTION_ALPHA, 'decides': False,
                 'note': ('descriptive only: at the measured ~1.6-1.8% re-send slip rate this size cannot reliably '
                          'show a reduction (about 55-66% even for a field that removes every slip); the primary is '
                          'non-inferiority')}
    if phase27_reference_counts:
        pooled_c = phase27_reference_counts['c_only_bad'] + c
        pooled_b = phase27_reference_counts['t_only_bad'] + b
        reduction['pooled_with_phase27'] = {
            'c_only_bad': pooled_c, 't2_only_bad': pooled_b, 'mcnemar_exact_one_sided_p': mcnemar_greater(pooled_c, pooled_b),
            'prompts': phase27_reference_counts['u2_prompts'] + planned, 'decides': False,
            'note': ("Phase 27's U2 C-against-T discordance (T is T2 on every U2 prompt) added to this phase's; "
                     'disjoint prompts; declared before this phase\'s data but after Phase 27\'s, whose result '
                     'motivated this phase, so it is descriptive and never deciding')}
    return {**decision, 'arms': arms, 'both_bad': both, 'reduction': reduction,
            'received_only': {'prompts_both_reported': all_reported, 'c_only_unsupported': received_only[0],
                              't2_only_unsupported': received_only[1],
                              'note': 'unsupported words only, where both arms reported; not a separate test'},
            'by_cell': {cell: {arm: dict(v) for arm, v in sorted(arms_.items())}
                        for cell, arms_ in sorted(by_stratum.items())},
            'worst_case_rule': ('T2 bad unless a received report with both words correct; C bad only for a received '
                                'report with an unsupported word')}


def ok_report(result, context):
    """A received report whose two words are both correct."""
    verdict = report_verdict(result, context)
    return verdict is not None and verdict['correct']


def guard_decision(*, planned, compared, b, c):
    complete = _complete(compared, planned)
    p_value = mcnemar_greater(b, c)
    status = 'INCOMPLETE' if not complete else 'FAIL' if p_value < GUARD_ALPHA else 'PASS'
    return {'status': status, 'complete': complete, 'planned_prompts': planned, 'compared': compared,
            't2_only_not_ok': b, 'r_only_not_ok': c, 'sign_test_one_sided_p': p_value, 'alpha': GUARD_ALPHA}


def _guard_counts(entries):
    compared = b = c = 0
    transitions, t2_classes, r_classes = Counter(), Counter(), Counter()
    reports = Counter()
    for entry in entries:
        arms, context = entry['arms'], entry['request']['context']
        for arm in ('R', 'T2'):
            verdict = report_verdict(arms.get(arm), context)
            if verdict is not None:
                reports[arm] += 1
                (t2_classes if arm == 'T2' else r_classes)[f"{verdict['upgrade']}/{verdict['notification']}"] += 1
        if not (_received(arms.get('R')) and _received(arms.get('T2'))):
            continue
        compared += 1
        r_ok, t2_ok = ok_report(arms['R'], context), ok_report(arms['T2'], context)
        b += r_ok and not t2_ok
        c += t2_ok and not r_ok
        before, after = response_outcome(arms['R'], context), response_outcome(arms['T2'], context)
        if before != after:
            transitions[f"{'/'.join(map(str, before))}->{'/'.join(map(str, after))}"] += 1
    return {'compared': compared, 'b': b, 'c': c, 'transitions_r_to_t2': dict(sorted(transitions.items())),
            'reports': dict(reports), 't2_word_classes': dict(sorted(t2_classes.items())),
            'r_word_classes': dict(sorted(r_classes.items()))}


def combined_guard_status(*statuses):
    """A part fails only when its own completeness holds (guard_decision), and a failed part is reported
    ahead of an incomplete one (as Phase 27's guard)."""
    if 'FAIL' in statuses:
        return 'FAIL'
    if 'INCOMPLETE' in statuses:
        return 'INCOMPLETE'
    return 'PASS'


def guard_readout(rows):
    prompts = _by_prompt(rows)
    entries = list(prompts.values())
    counts = _guard_counts(entries)
    pooled = guard_decision(planned=len(entries), compared=counts['compared'], b=counts['b'], c=counts['c'])
    alone_entries = [e for e in entries if e['request']['stratum'] == GUARD_ALONE_STRATUM]
    alone_counts = _guard_counts(alone_entries)
    alone = guard_decision(planned=len(alone_entries), compared=alone_counts['compared'], b=alone_counts['b'],
                           c=alone_counts['c'])
    decision = {**pooled, 'status': combined_guard_status(pooled['status'], alone['status']),
                'pooled_status': pooled['status'], 'alone': {'stratum': GUARD_ALONE_STRATUM, **alone}}
    by_stratum = {}
    for stratum in sorted({e['request']['stratum'] for e in entries}):
        subset = [e for e in entries if e['request']['stratum'] == stratum]
        sub = _guard_counts(subset)
        by_stratum[stratum] = {'planned_prompts': len(subset), 'compared': sub['compared'], 't2_only_not_ok': sub['b'],
                               'r_only_not_ok': sub['c'], 'reports': sub['reports'],
                               't2_word_classes': sub['t2_word_classes'], 'r_word_classes': sub['r_word_classes'],
                               'transitions_r_to_t2': sub['transitions_r_to_t2'], 'decides': False}
    return {**decision, 'transitions_r_to_t2': counts['transitions_r_to_t2'], 'reports': counts['reports'],
            't2_word_classes': counts['t2_word_classes'], 'r_word_classes': counts['r_word_classes'],
            'by_stratum': by_stratum,
            'note': (f'two parts decide: the pooled U1 + U3 sign test (the top-level counts, p and completeness) and '
                     f'the {GUARD_ALONE_STRATUM}-alone sign test (alone); FAIL if either fails while its own '
                     'completeness holds, else INCOMPLETE if either is incomplete, else PASS. The by_stratum figures '
                     'are descriptive. OK = a received report with both words correct; a received non-report counts '
                     'as not OK in either arm')}


def structural_readout(precheck):
    """The $0 structural guard, as the plan recorded it (the plan cannot exist unless it passed)."""
    keys = ('turns_checked', 'in_window_turns', 'out_of_window_turns', 'report_required_turns',
            'phase27_guard_prompts', 'phase27_guard_prompts_in_window', 'phase27_guard_prompts_identical_to_control',
            'terminal_rejection_case_turns', 'terminal_rejection_case_turns_in_window',
            't2_differs_from_control_outside_window', 'in_window_terminal_rejection', 'in_window_not_report_required',
            'in_window_non_report_turns', 'in_window_after_earlier_in_window_turn')
    out = {key: (precheck or {}).get(key) for key in keys}
    out['in_window_report_turns'] = {key.split(':', 1)[1]: value for key, value in sorted((precheck or {}).items())
                                     if key.startswith('in_window_report_turns:')}
    out['phase27_guard_prompts_by_stratum'] = {key.split(':', 1)[1]: value for key, value in
                                               sorted((precheck or {}).items())
                                               if key.startswith('phase27_guard_prompts:')}
    out['status'] = 'PASS' if (precheck or {}).get('passed') is True else 'FAIL'
    out['by_construction'] = True
    out['rule'] = ("on every out-of-window turn T2's request is byte-identical to the control, so its response "
                   "distribution is the control's; Phase 27's guard tolerances (pooled 0.05, terminal rejection 0.10, "
                   'word test p < 0.05) hold with an expected excess of exactly zero, and no request is sent there. '
                   'PASS by construction, not a measurement: never quote it as a measured pass; write it as "not '
                   'applicable: T2 is byte-identical to the control there; nothing was sent"')
    return out


def citation_tally(pairs):
    """Descriptive: reports that cite every obs-k label T2 would state (C6 needs matching cited evidence)."""
    counts = defaultdict(Counter)
    for request, result in pairs:
        report = _report(result)
        if report is None:
            continue
        stated = [value['evidence'] for value in (request['context'].get('stated') or {}).values() if value]
        cited = set(report.get('evidence_ids') or [])
        counts[request['arm']]['reports'] += 1
        counts[request['arm']]['cite_every_stated_label'] += bool(stated) and all(label in cited for label in stated)
    return {arm: dict(c) for arm, c in sorted(counts.items())}


def history_match(pairs):
    out = defaultdict(Counter)
    for request, result in pairs:
        if request['arm'] in ('C', 'R') and _received(result):
            out[request['arm']]['received'] += 1
            out[request['arm']]['byte_identical_to_historical'] += result.get('raw_sha256') == request['historical']['raw_sha256']
    return {arm: dict(c) for arm, c in sorted(out.items())}


def primary_statement(primary):
    t2, c = primary['arms']['T2'], primary['arms']['C']
    counts = (f"T2 {t2['bad_worst_case']} of {primary['planned_prompts']} worst case against C {c['bad']} unsupported; "
              f"Tango p {primary['tango_one_sided_p']:.4g} at a {100 * primary['margin']:.1f}-point margin"
              if primary['tango_one_sided_p'] is not None else f"T2 {t2['bad_worst_case']} against C {c['bad']}")
    if primary['status'] == 'INCOMPLETE':
        return 'non-inferiority INCOMPLETE: an arm received fewer than 95% of its planned requests; no evidence either way'
    if primary['status'] == 'PASS':
        return (f'non-inferiority PASS: a rise of {100 * primary["margin"]:.1f} percentage points or more in report slips '
                f'under the narrow field is ruled out; this does not show a benefit ({counts})')
    return (f'non-inferiority FAIL: a rise of {100 * primary["margin"]:.1f} percentage points or more in report slips under the narrow field '
            f'is not ruled out ({counts})')


def compute_readouts(plan, results, *, partial_lines_skipped=0):
    requests = plan['requests']
    by_id = {r['request_id']: r for r in results}
    pairs = [(q, by_id.get(q['request_id'])) for q in requests]
    grouped = defaultdict(list)
    for request, result in pairs:
        grouped[request['population']].append((request, result))
    structural = structural_readout(plan.get('precheck'))
    primary = primary_readout(grouped['primary'], plan.get('phase27_u2_reference'))
    guard = guard_readout(grouped['guard'])
    statuses = {'structural_guard': structural['status'], 'in_window_guard': guard['status'],
                'non_inferiority': primary['status']}
    recommended = all(status == 'PASS' for status in statuses.values())
    statement = primary_statement(primary)
    alone = guard['alone']
    statement += (f"; in-window guard {guard['status']} (pooled U1 + U3 {guard['pooled_status']}: T2-only not OK "
                  f"{guard['t2_only_not_ok']}, R-only not OK {guard['r_only_not_ok']} of {guard['compared']} compared, "
                  f"sign test p {guard['sign_test_one_sided_p']:.4g}; {alone['stratum']} alone {alone['status']}: "
                  f"T2-only not OK {alone['t2_only_not_ok']}, R-only not OK {alone['r_only_not_ok']} of "
                  f"{alone['compared']} compared, sign test p {alone['sign_test_one_sided_p']:.4g}); structural guard "
                  f"{structural['status']} by construction, not a measurement "
                  f"({structural['phase27_guard_prompts_in_window']} of {structural['phase27_guard_prompts']} Phase 27 "
                  'guard prompts in the window: T2 is byte-identical to the control there, and nothing was sent)')
    statement += ('; a reduction is not claimed: ' + ('the exact test reached p < 0.05 (descriptive)'
                                                     if primary['reduction']['p_below_alpha'] else
                                                     'the exact test did not reach p < 0.05 (descriptive)'))
    if recommended:
        statement += ('. Recommended for a later loop only: that loop must declare the same key, value and window and '
                      'measure it end to end against a concurrent control, with a held-out check on a new partition')
    return {'schema_version': READOUT_SCHEMA, 'scoring': 'NON_SCORING_NEVER_FED_BACK',
            'requests_planned': len(requests), 'requests_received': sum(_received(r) for _, r in pairs),
            'partial_lines_skipped': partial_lines_skipped,
            'structural_guard': structural, 'non_inferiority': primary, 'in_window_guard': guard,
            'report_fields': rwp.report_field_tallies(pairs), 'citations': citation_tally(pairs),
            'history_match': history_match(pairs), 'provider': lp.provider_readout(pairs), 'statuses': statuses,
            'decision': 'RECOMMENDED_FOR_A_LATER_LOOP' if recommended else 'NOT_RECOMMENDED',
            'statement': statement}


# ---------------------------------------------------------------- command line

def dry_summary(plan):
    return {'dry_run': True, 'provider_calls': 0, 'plan_hash': plan_hash(plan),
            'harness_sha256': plan['harness_sha256'], 'phase27_harness_sha256': plan['phase27_harness_sha256'],
            'phase21_harness_sha256': plan['phase21_harness_sha256'],
            'phase26_runner_sha256': plan['phase26_runner_sha256'],
            'configuration_hash': plan['configuration_hash'], 'freeze_sha256': plan['freeze_sha256'],
            'actor_model': plan['actor_model'], 'temperature': plan['actor_model_settings'].get('temperature'),
            'sources': plan['sources'], 'verification': plan['verification'], 'precheck': plan['precheck'],
            'sampling': {k: plan['sampling'][k] for k in ('seed', 'sizes', 'available', 'allocation')},
            'populations': plan['populations'], 'phase27_u2_reference': plan['phase27_u2_reference'],
            'thresholds': plan['thresholds'], 'counts': plan['counts'], 'cost': plan['cost'],
            'max_input_token_bound': plan['max_input_token_bound']}


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', default=str(STORE), help='read-only main lab store')
    parser.add_argument('--settings', default=DECLARED_SETTINGS, help='the declared non-secret settings file')
    parser.add_argument('--spend-cap', type=float, default=HARD_SPEND_CAP)
    parser.add_argument('--write-plan', help=f'new directory under artifacts/{PHASE_PREFIX}<date>/ for the dry plan')
    parser.add_argument('--readouts', help="recompute read-outs from a saved run directory ($0); refuses unless this "
                        "harness and the saved plan are the run's own")
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
    parser.add_argument('--ignore-manifest', action='append', default=[],
                        help='a crashed program run record (exact path) that is known not to be running')
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
            print(json.dumps(recompute_readouts(args.readouts, allow_other_harness=args.not_the_runs_harness), indent=2))
            return 0
        if args.execute_live and not (args.out and args.confirm_entity and args.expect_plan_hash
                                      and args.expect_harness_sha256 and args.expect_protocol_sha256):
            raise PlanningError('--execute-live needs --out, --confirm-entity, --expect-plan-hash, '
                                '--expect-harness-sha256 and --expect-protocol-sha256')
        if args.execute_live:
            check_output(args.out)
            active = other_paid_runs(ignore=args.ignore_manifest)
            if active:
                raise PlanningError(f'Another paid run may be in progress ({active[0]}); one paid run at a time')
        if args.write_plan:
            check_output(args.write_plan, live=False)
        settings_path = pathlib.Path(args.settings) if pathlib.Path(args.settings).is_absolute() else ROOT / args.settings
        plan, prompts = build_plan(store=args.store, settings_path=settings_path, spend_cap=args.spend_cap)
        if not args.execute_live:
            summary = dry_summary(plan)
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
