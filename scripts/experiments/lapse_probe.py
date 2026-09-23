"""Phase 21: a non-scoring Actor replay probe of the lapse behind every untriggered fault.

The lapse (docs/part2/EXPERIMENT_PROGRAM_PHASES_20-27.md, Phase 21). After a delivered,
matching, succeeded upgrade receipt, the Actor polls the status of a confirmation it never
sent, reads UNKNOWN, and never sends it. In the development store that is 65 v4 episodes,
and 0 of their 296 later turns ever sent. This probe asks, on those exact prompts, whether
ONE windowed field stating that no confirmation has been requested yet (v5) makes the Actor
send it, against a placebo field of the same shape. It also measures how often the Actor at
temperature 0 answers byte-identical input differently.

How a prompt is rebuilt. Each stored `actor_output` event carries the `messages_hash` and
`request_hash` of the request the runtime sent. The probe rebuilds that request with the
runtime's own code (ACTOR_PROMPT, ACTION_ADAPTER, progress.turn_message and
runtime.response_format_for), from the episode's delivered observations in store order and
its `private_episode_inputs.intent` (the task the Actor was given; the private recipe in the
same row is never used). An Actor request is the system prompt, the task and the CURRENT turn
message only; earlier turn messages are never kept. The history is extended exactly as
Actor.__call__ extends it (an invalid-JSON correction, a report-required refusal, a budget
message). A rebuilt prompt is used only if both hashes match the stored ones; any other prompt
is counted, reported and never sent.

Arms. C re-sends the exact verified v4 request. T (v5) adds one field, V5_FIELD, and P adds a
placebo field of the same shape, PLACEBO_FIELD. Both are added only on TREATED turns: in window
(a delivered matching succeeded upgrade receipt exists, by the runtime's PolicyState rule, and
no send_confirmation has been dispatched in the episode) AND not report-required. On a
report-required turn the runtime refuses any tool call, so the field could only change the
report's wording; it is withheld there, as v3 withholds its block (progress.py). v5 lives only
in this script; nothing in backend/app changes. A $0 pre-check rebuilds every v4 development
turn under T and P and requires that they change exactly the treated turns (the window checked
by an independent rule), 0 in-window report-required turns and 0 terminal-upgrade-rejection
turns.

Populations (development split, completion-study episodes started before STORE_CUTOFF):
turn-4 prompts (after the first UNKNOWN) and turn-3 prompts (the lapse decision) of every lapse
episode; NONLAPSE_N non-lapse first in-window prompts, chosen by a seeded sha256 rank; every
in-window report turn (T and P only where treated; C everywhere, as R4's noise reference); and,
for determinism, every historical-PENDING report-turn context plus one matched
historical-UNKNOWN context each, DETERMINISM_REPEATS times under C.

Read-outs are computed by compute_readouts() and declared before any data:
  primary  turn 4: T send rate >= 0.8 AND T - max(C, P) >= 0.5, on the received responses AND
           with every missing response counted against v5; one-sided Fisher p < 0.01 (implied).
  R3       T only: on non-lapse prompts, T's action (get_operation_status at the service level)
           agrees with C's on >= 95% of compared prompts, where a move INTO send_confirmation is
           not a mismatch; and T returns 0 reports. P is reported, never decides.
  R4       T only: on report turns, no T notification word outside the historical word and its
           R4_INTERCHANGEABLE partner, and no T non-report on a report-required turn. Always
           quoted with k, the number of T words it judged ("R4 PASS on k of 14 T reports"): a T
           that sends instead of reporting is not judged, so k shrinks exactly when v5 works.
  turn 3   flips, descriptive only, beside P.
  determinism  byte-identical repeat share; within-context word disagreement (Wilson); change
           from the historical word (confounded with time); PENDING probability by group.
A primary FAIL records which condition failed: T below 0.8, T not 0.5 above the placebo, or T
not 0.5 above a plain re-send; each has its own statement.

Nothing here creates a campaign, study, trial, world, policy or store row. The store is opened
read-only, results never enter a study and are never shown to any model.

Dry by default. `--execute-live`, a matching `--confirm-entity`, the reviewed plan hash and the
harness and protocol hashes are all required before any provider call. The protocol must exist,
its opening status block must no longer say it is not yet reviewed, and it must carry the bare
line "Reviewed for launch: harness <sha256> plan <hash>"; the review record (REVIEW_RECORD) must
name the same protocol sha256, harness sha256 and plan hash. A live run also refuses while a
Phase 20 run is in progress, and takes an atomic claim so two launches can never both spend.
The $25 cap is a phase cap: a new run after runs that delivered nothing gets the cap minus
their charged bounds. A claim whose process died before its manifest became final (a crash in
set-up, a hard kill) is closed at $0 by --finalize-abandoned, which refuses while the claim's
process is alive.

Usage:
  python scripts/experiments/lapse_probe.py
  python scripts/experiments/lapse_probe.py --write-plan artifacts/phase21-<date>/dry-plan-<n>
  python scripts/experiments/lapse_probe.py --readouts artifacts/phase21-<date>/live
  python scripts/experiments/lapse_probe.py --finalize-abandoned artifacts/phase21-live-claims/claim-NN.json
  python scripts/experiments/lapse_probe.py --execute-live --confirm-entity ENTITY \\
      --out artifacts/phase21-<date>/live --expect-plan-hash H \\
      --expect-harness-sha256 S --expect-protocol-sha256 P
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
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
from types import SimpleNamespace

# Even dry inspection should not create Python cache files in the workspace.
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from pydantic import ValidationError  # noqa: E402

from app.agents.actor import (ACTION_ADAPTER, ACTOR_PROMPT, ACTOR_PROMPT_HASH,  # noqa: E402
                              RETRYABLE_TRANSPORT_CODES)
from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4, turn_message  # noqa: E402
from app.contracts.models import (PublicObservation, ReportAction, TaskIntent,  # noqa: E402
                                  canonical_json, content_hash)
from app.lab.policy_state import PolicyState  # noqa: E402
from app.providers.runtime import (MODEL_REQUEST_SETTINGS, RuntimeProviderError,  # noqa: E402
                                   response_format_for, validate_request_input)

SCHEMA = 'faultlab-lapse-probe/v2'
READOUT_SCHEMA = 'faultlab-lapse-probe-readouts/v2'
MANIFEST_NAME = 'lapse-probe-manifest.json'
FINAL_STATUSES = ('COMPLETED', 'STOPPED', 'ABORTED')
# A live run writes its manifest at exactly artifacts/phase21-<date>/<name>/ (check_output), and
# only that depth is read: a copy saved deeper as evidence is never a live-gate input.
LIVE_MANIFEST_GLOB = f'phase21-*/*/{MANIFEST_NAME}'
# Atomic launch claims live here (under artifacts/). A claim file is never deleted.
CLAIM_DIR = 'phase21-live-claims'
CLAIM_NAME = re.compile(r'claim-(\d+)\.json')
# A run whose process died while RUNNING may have up to two attempts (one request and its blind
# retry) admitted and charged but not yet recorded; --finalize-abandoned charges them.
ABANDONED_IN_FLIGHT_ATTEMPTS = 2
# Phase 20 runs in parallel on the same provider; its manifest has no ended_at while it runs.
PHASE20_MANIFEST_GLOB = 'phase20-*/**/dev-probe-manifest.json'
STORE = ROOT / 'artifacts/lab.sqlite3'
# Every completion-study episode in the store started before this instant (the last, Phase 17,
# at 15:40Z). Defence in depth against any later completion-study episode in this main store;
# Phase 20 writes to its own store under its output directory, with purpose 'challenge'.
STORE_CUTOFF = '2026-09-23T16:00:00Z'
PURPOSE = 'completion_study'
TERMINAL_REJECTION_CASE = 'terminal-upgrade-rejection'

EXPECTED_ACTOR_MODEL = 'deepseek-ai/DeepSeek-V3.1'
EXPECTED_PROJECT = 'shreetbohara-quinstreet/Faultlab'
DECLARED_SETTINGS = 'artifacts/phase16-2026-09-22/settings-phase17.json'
DECLARED_SETTINGS_SHA256 = '1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d'
# The Phase 17 settings on the Phase 19 code (next-phase.md runbook item 3). Recomputed here
# from the settings file alone; backend/app must not change for it to hold.
DECLARED_CONFIGURATION_HASH = '0a33aa51cf125cadcfc1dfeaf640950f9e18e0dd89576ec24202a414893aee98'
# The reviewed protocol declares this harness's sha256 and the plan hash; the operator types the
# protocol's own sha256, and the review record repeats it. The script never pins the protocol, so
# the pins are not circular.
PROTOCOL = ROOT / 'docs/part2/PHASE21_EXPERIMENT.md'
REVIEW_RECORD = 'artifacts/phase21-2026-09-23/review.json'
# Searched only in the protocol's opening status block (before its first '## ' heading), so a
# review log that quotes it cannot block the launch.
REVIEW_PENDING_MARKER = 'NOT yet reviewed'
REVIEWED_LINE = 'Reviewed for launch: harness {harness} plan {plan}'
ACTOR_MAX_OUTPUT_TOKENS = 2000       # Actor.__call__
ACTOR_TIMEOUT_SECONDS = 20.0         # Actor.__call__: min(20, remaining wall); a replay has no wall
PER_REQUEST_DOLLAR_BOUND = 0.0209    # 32,000 in x $0.55/M + 2,000 out x $1.65/M, conservative
HARD_SPEND_CAP = 25.0
CONSECUTIVE_ERROR_ABORT = 5
# After a request that ends in error, wait before the next one. The fifth consecutive errored
# request stops the run, so a failure must persist about 12.5 minutes (30+120+300+300 s) first.
# Waiting is not resampling: an errored request delivered no generation and is never re-sent.
BACKOFF_SECONDS = (30, 120, 300, 300)
# The one blind retry of a transport failure (no generation arrived) waits this long first.
BLIND_RETRY_WAIT_SECONDS = 10

ARMS = ('C', 'T', 'P')
V5_FIELD = 'confirmation_progress'
V5_VALUE = {'confirmation_requested': False,
            'note': 'No send_confirmation request has been dispatched for you in this episode yet.'}
# Same shape (one boolean, one sentence of similar length), sorts to the same position in
# canonical JSON, present on exactly the same turns, and says nothing about the task.
PLACEBO_FIELD = 'context_marker'
PLACEBO_VALUE = {'marker_enabled': False,
                 'note': 'This marker is a fixed layout field and it describes nothing in this run.'}
WINDOW_RULE = ('in window iff a delivered observation carries a matching SUCCEEDED upgrade receipt '
               '(app.lab.policy_state.PolicyState.receipt, the policy condition upgrade_succeeded) '
               'and no send_confirmation has been dispatched in the episode before this turn')
TREATMENT_RULE = ('added only on treated turns: ' + WINDOW_RULE + ', and the turn is not report-required. '
                  'On a report-required turn the runtime refuses any tool call, so the field could only '
                  "change the report's wording; it is withheld there, as v3 withholds its block (progress.py)")

SAMPLE_SEED = 'faultlab-phase21-2026-09-23'
NONLAPSE_N = 100
DETERMINISM_REPEATS = 5
POPULATION_ORDER = ('turn4', 'nonlapse', 'report', 'turn3', 'determinism')
ACTION_CLASSES = ('send_confirmation', 'get_operation_status', 'report', 'other')
RECEIVED = ('ok', 'empty_response')
REPORT_FIELDS = ('overall', 'upgrade_outcome', 'next_action')

PRIMARY_T_MIN = Fraction(4, 5)
PRIMARY_DIFF_MIN = Fraction(1, 2)
PRIMARY_ALPHA = 0.01
R3_MATCH_MIN = Fraction(95, 100)
COMPLETE_MIN = Fraction(95, 100)
# On an in-window report turn the upgrade receipt is delivered and no confirmation was ever
# requested. The contract's words for that are NOT_STARTED (literal) and UNKNOWN (no terminal
# notification evidence). In the development store both occur in exactly that state (94 UNKNOWN,
# 4 NOT_STARTED) and the stored referee verdicts accepted every one on C5 (0 of the 4 NOT_STARTED
# under v4; 1 failed C6). A change between them is the one change allowed; any other word fails R4.
R4_INTERCHANGEABLE = frozenset({'UNKNOWN', 'NOT_STARTED'})

# Actor.__call__'s own history extensions, copied verbatim; a test pins them to actor.py and the
# stored hashes verify every rebuilt prompt that follows one.
CORRECTION_INSTRUCTION = ('Your action failed output_schema. Return exactly one allowed tool or report '
                          'action with only its declared fields. No business call was executed; this '
                          'correction consumes a turn.')
FINAL_TOOL_MESSAGE = 'A report was required on the reserved final turn; no business call executed.'
BUDGET_MESSAGE = 'Business budget exhausted. Return your truthful final report from existing observations.'

SOURCE_FILES = ('backend/app/agents/actor.py', 'backend/app/agents/progress.py',
                'backend/app/agents/prompts/actor.md', 'backend/app/providers/runtime.py',
                'backend/app/contracts/models.py', 'backend/app/lab/policy_state.py')


class PlanningError(ValueError):
    """Only locally authored, non-secret messages are printed to the terminal."""


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def rank(*parts):
    """Deterministic, version-independent order: sha256 of the seed and the parts."""
    return hashlib.sha256(':'.join((SAMPLE_SEED,) + tuple(str(p) for p in parts)).encode()).hexdigest()


def before_cutoff(started_at, cutoff=STORE_CUTOFF):
    if not started_at:
        return False
    parse = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))  # noqa: E731
    return parse(started_at) < parse(cutoff)


# ---------------------------------------------------------------- read-only store access

def connect(store):
    path = pathlib.Path(store).resolve()
    if not path.exists():
        raise PlanningError(f'Store not found: {path}')
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def load_index(connection):
    """Episode records, case ids from completion-study rows and trial trigger flags."""
    episodes = {i: json.loads(p) for i, p in connection.execute(
        "select id,payload from records where kind='episodes'")}
    cases = {}
    for (payload,) in connection.execute("select payload from records where kind='completion_studies'"):
        for row in json.loads(payload).get('trial_rows') or []:
            cases[row['trial']['episode_id']] = row['case_id']
    triggered = {}
    for i, p in connection.execute("select id,payload from records where kind='trials'"):
        triggered[i] = json.loads(p).get('fault_triggered')
    return episodes, cases, triggered


def load_events(connection, episode_id):
    return [json.loads(p) for (p,) in connection.execute(
        'select payload from events where episode_id=? order by seq', (episode_id,))]


def load_intent(connection, episode_id):
    """Only the task the Actor was given. The recipe parsed from the same row is never used."""
    row = connection.execute("select payload from records where kind='private_episode_inputs' and id=?",
                             (episode_id,)).fetchone()
    return json.loads(row[0])['intent'] if row else None


# ---------------------------------------------------------------- rebuilding the Actor's request

def base_messages(intent):
    return [{'role': 'system', 'content': ACTOR_PROMPT},
            {'role': 'user', 'content': canonical_json({'task': intent, 'output_schema': ACTION_ADAPTER.json_schema()})}]


def parse_action(raw):
    try:
        return ACTION_ADAPTER.validate_json(raw)
    except (ValidationError, ValueError):
        return None


def action_errors(raw):
    """The correction payload Actor.__call__ builds for an answer that failed output_schema."""
    try:
        ACTION_ADAPTER.validate_json(raw)
        return None
    except (ValidationError, ValueError) as error:
        return ([{'location': list(issue['loc']), 'type': issue['type']}
                 for issue in error.errors(include_input=False, include_context=False, include_url=False)]
                if isinstance(error, ValidationError) else [{'location': [], 'type': 'invalid_json'}])


def classify(raw):
    """Action class with the runtime's own parser (ACTION_ADAPTER)."""
    action = parse_action(raw) if isinstance(raw, str) else None
    if action is None:
        return {'class': 'other', 'detail': 'invalid_action', 'notification_outcome': None, 'report': None}
    if isinstance(action, ReportAction):
        report = action.report.model_dump(mode='json')
        return {'class': 'report', 'detail': None, 'notification_outcome': report['notification_outcome'],
                'report': report}
    if action.tool == 'send_confirmation':
        return {'class': 'send_confirmation', 'detail': None, 'notification_outcome': None, 'report': None}
    if action.tool == 'get_operation_status':
        return {'class': 'get_operation_status', 'detail': action.arguments.service,
                'notification_outcome': None, 'report': None}
    return {'class': 'other', 'detail': action.tool, 'notification_outcome': None, 'report': None}


def historical_summary(raw):
    """The historical action for the plan: class, detail, notification word, and the other report
    fields that carry C5 risk (descriptive only)."""
    result = classify(raw)
    report = result.pop('report')
    result['report_fields'] = {key: report[key] for key in REPORT_FIELDS} if report else None
    return result


def action_key(result):
    """What R3 compares: the class, with get_operation_status kept at the service level and any
    other tool (or invalid output) kept by name."""
    return (result.get('class'), result.get('detail'))


def upgrade_receipt_delivered(models, intent):
    """The runtime's own rule: PolicyState.receipt over delivered matching evidence."""
    receipt = PolicyState(SimpleNamespace(intent=intent, observations=models)).receipt('orders')
    return bool(receipt and receipt.status == 'SUCCEEDED')


def independent_window(observations):
    """A second rule on raw dicts only, used by the pre-check (program window.py)."""
    upgraded = False
    for row in observations:
        result = row.get('result') or {}
        data = result.get('data') if isinstance(result.get('data'), dict) else {}
        receipt = data.get('receipt') if isinstance(data.get('receipt'), dict) else {}
        if receipt.get('service') == 'orders' and receipt.get('status') == 'SUCCEEDED':
            upgraded = True
    sent = any((row.get('result') or {}).get('tool') == 'send_confirmation' for row in observations)
    return upgraded and not sent


def observation_brief(row, intent):
    result = row.get('result') or {}
    operation = result.get('operation_id')
    return {'tool': result.get('tool'), 'transport': result.get('transport'), 'status': result.get('status'),
            'error_code': result.get('error_code'),
            'operation': ('orders' if operation == intent.get('upgrade_operation_id') else
                          'notifications' if operation == intent.get('notification_operation_id') else None)}


def rebuild_episode(events, intent, *, keep=False):
    """Rebuild every Actor request of one episode and verify it against the stored hashes.

    Returns one dict per actor_output event. With keep=True each verified turn also carries
    `history` (the messages before this turn's user message) and `user` (its payload).
    """
    turns = []
    if intent is None:
        for event in events:
            if event['type'] == 'actor_output':
                turns.append({'actor_turn': event['payload'].get('actor_turn'), 'verified': False,
                              'failure': 'intent_missing'})
        return turns
    intent_model = TaskIntent.model_validate_json(json.dumps(intent))
    histories = [base_messages(intent)]
    observations, models, sends_dispatched = [], [], 0
    since_last, broken = [], None
    positions = [i for i, event in enumerate(events) if event['type'] == 'actor_output']
    for index, event in enumerate(events):
        kind, payload = event['type'], event.get('payload') or {}
        if kind == 'observation_delivered':
            observations.append(payload['observation'])
            models.append(PublicObservation.model_validate_json(json.dumps(payload['observation'])))
            since_last.append(observation_brief(payload['observation'], intent))
            continue
        if kind == 'tool_dispatched':
            sends_dispatched += payload.get('tool') == 'send_confirmation'
            continue
        if kind != 'actor_output':
            continue
        following = events[index + 1:next((j for j in positions if j > index), len(events))]
        turn = {'actor_turn': payload.get('actor_turn'), 'seq': event.get('seq'),
                'protocol': payload.get('actor_context_protocol'),
                'final_report_required': payload.get('final_report_required'),
                'response_contract': payload.get('response_contract'),
                'remaining_actor_calls': payload.get('remaining_actor_calls_at_request'),
                'stored_messages_hash': payload.get('messages_hash'),
                'stored_request_hash': payload.get('request_hash'),
                'raw_sha256': hashlib.sha256((payload.get('raw') or '').encode()).hexdigest(),
                'historical': historical_summary(payload.get('raw')),
                'report_submitted_after': any(e['type'] == 'report_submitted' for e in following),
                'observation_count': len(observations),
                'observation_signature': [[o['tool'], o['transport'], o['status'], o['error_code']]
                                          for o in (observation_brief(r, intent) for r in observations)],
                'new_observations': since_last,
                'window': upgrade_receipt_delivered(models, intent_model) and sends_dispatched == 0,
                'window_independent': independent_window(observations)}
        turn['treated'] = bool(turn['window']) and not turn['final_report_required']
        since_last = []
        match, user = None, None
        if broken is None and turn['protocol'] != ACTOR_CONTEXT_PROTOCOL_V4:
            broken = 'not_v4'
        if broken is None:
            user = turn_message(list(observations), final_report_required=turn['final_report_required'],
                                remaining_actor_calls=turn['remaining_actor_calls'], protocol=turn['protocol'])
            response_format = response_format_for(response_contract=turn['response_contract'])
            user_message = {'role': 'user', 'content': canonical_json(user)}
            for history in histories:
                messages = history + [user_message]
                if (content_hash(messages) == turn['stored_messages_hash']
                        and content_hash({'messages': messages, 'response_format': response_format})
                        == turn['stored_request_hash']):
                    match = history
                    break
        turn['verified'] = match is not None
        turn['failure'] = None if match is not None else (broken or 'hash_mismatch')
        if match is None:
            broken = broken or 'after_unverified_turn'
        elif keep:
            turn['history'], turn['user'] = match, user
        turns.append(turn)
        if match is None:
            continue
        # Extend the history exactly as Actor.__call__ does before its next request.
        raw = payload.get('raw')
        action = parse_action(raw)
        dispatched = any(e['type'] == 'tool_dispatched' and (e.get('payload') or {}).get('caller') == 'actor'
                         for e in following)
        if action is None:
            histories = [match + [{'role': 'assistant', 'content': raw},
                                  {'role': 'user', 'content': canonical_json(
                                      {'action_errors': action_errors(raw), 'instruction': CORRECTION_INSTRUCTION})}]]
        elif isinstance(action, ReportAction):
            histories = [match]
            if not turn['report_submitted_after']:
                broken = 'blocked_report_not_reconstructed'
        elif turn['final_report_required']:
            histories = [match + [{'role': 'user', 'content': FINAL_TOOL_MESSAGE}]]
        elif action.tool == 'send_confirmation' and not dispatched:
            # A blocked confirmation's hook reasons are not reconstructed; only a budget stop is.
            # The next stored hash decides, so a wrong candidate can never be used.
            histories = [match + [{'role': 'user', 'content': BUDGET_MESSAGE}]]
        else:
            histories = [match, match + [{'role': 'user', 'content': BUDGET_MESSAGE}]]
    return turns


def is_treated(user, window):
    """T and P differ from C only here: in window, and not on a report-required turn."""
    return bool(window) and not user.get('final_report_required')


def arm_payload(user, arm, window):
    if arm not in ARMS:
        raise PlanningError(f'Cannot build arm {arm}')
    if arm == 'C' or not is_treated(user, window):
        return user
    field, value = (V5_FIELD, V5_VALUE) if arm == 'T' else (PLACEBO_FIELD, PLACEBO_VALUE)
    if field in user:
        raise PlanningError(f'Cannot build arm {arm}')
    return {**user, field: dict(value)}


def arm_messages(history, user, arm, window):
    return history + [{'role': 'user', 'content': canonical_json(arm_payload(user, arm, window))}]


def added_keys(changed, control):
    """Keys added to the last message; None if anything else differs."""
    if changed[:-1] != control[:-1]:
        return None
    new, old = json.loads(changed[-1]['content']), json.loads(control[-1]['content'])
    if any(new.get(key) != value for key, value in old.items()):
        return None
    return sorted(set(new) - set(old))


# ---------------------------------------------------------------- pass 1: every v4 turn

def survey(connection, episodes, cases, triggered, cutoff=STORE_CUTOFF):
    """Verify every v4 development turn, run the v5/placebo pre-check, and summarise episodes."""
    verification = Counter()
    failures = Counter()
    pre = Counter()
    changed_by_case = Counter()
    disagreements, structural = [], []
    summaries = []
    for episode_id in sorted(episodes):
        episode = episodes[episode_id]
        if episode.get('split') != 'development' or episode.get('experiment_purpose') == 'promotion':
            continue
        if not before_cutoff(episode.get('started_at'), cutoff):
            continue
        events = load_events(connection, episode_id)
        first = next((e for e in events if e['type'] == 'actor_output'), None)
        if first is None or first['payload'].get('actor_context_protocol') != ACTOR_CONTEXT_PROTOCOL_V4:
            continue
        turns = rebuild_episode(events, load_intent(connection, episode_id), keep=True)
        case = cases.get(episode_id)
        for turn in turns:
            verification['turns'] += 1
            verification['verified'] += turn['verified']
            if not turn['verified']:
                failures[turn['failure']] += 1
                continue
            control = arm_messages(turn['history'], turn['user'], 'C', turn['window'])
            treated = arm_messages(turn['history'], turn['user'], 'T', turn['window'])
            placebo = arm_messages(turn['history'], turn['user'], 'P', turn['window'])
            control_hash = content_hash(control)
            t_changed = content_hash(treated) != control_hash
            p_changed = content_hash(placebo) != control_hash
            window_final = bool(turn['window']) and bool(turn['final_report_required'])
            pre['turns_checked'] += 1
            pre['window_turns'] += turn['window']
            pre['independent_window_turns'] += turn['window_independent']
            pre['treated_turns'] += turn['treated']
            pre['window_final_turns'] += window_final
            pre['t_changed'] += t_changed
            pre['p_changed'] += p_changed
            pre['c_differs_from_stored'] += control_hash != turn['stored_messages_hash']
            pre['terminal_rejection_checked'] += case == TERMINAL_REJECTION_CASE
            if t_changed != turn['treated'] or p_changed != turn['treated']:
                pre['changed_outside_treated_or_unchanged_inside'] += 1
            if window_final and (t_changed or p_changed):
                pre['window_final_changed'] += 1
            if turn['window'] != turn['window_independent']:
                disagreements.append([episode_id, turn['actor_turn']])
            if t_changed:
                changed_by_case[case or 'unknown'] += 1
                if case == TERMINAL_REJECTION_CASE:
                    pre['terminal_rejection_changed'] += 1
                if (added_keys(treated, control) != [V5_FIELD]
                        or added_keys(placebo, control) != [PLACEBO_FIELD]):
                    structural.append([episode_id, turn['actor_turn']])
        for turn in turns:
            turn.pop('history', None)
            turn.pop('user', None)
        summaries.append({'episode_id': episode_id, 'case': case, 'arm': episode.get('arm'),
                          'purpose': episode.get('experiment_purpose'), 'lifecycle': episode.get('lifecycle'),
                          'fault_triggered': triggered.get(episode_id),
                          'ever_sent': any(e['type'] == 'tool_dispatched'
                                           and (e.get('payload') or {}).get('tool') == 'send_confirmation'
                                           for e in events),
                          'turns': turns})
    precheck = {
        'turns_checked': pre['turns_checked'], 'window_turns': pre['window_turns'],
        'independent_window_turns': pre['independent_window_turns'],
        'window_report_required_turns': pre['window_final_turns'], 'treated_turns': pre['treated_turns'],
        'turns_changed_by_T': pre['t_changed'], 'turns_changed_by_P': pre['p_changed'],
        'changed_outside_treated_or_unchanged_inside': pre['changed_outside_treated_or_unchanged_inside'],
        'window_report_required_turns_changed': pre['window_final_changed'],
        'window_rule_disagreements': len(disagreements), 'disagreement_examples': disagreements[:20],
        'structural_violations': len(structural), 'structural_examples': structural[:20],
        'terminal_rejection_turns_checked': pre['terminal_rejection_checked'],
        'terminal_rejection_turns_changed': pre['terminal_rejection_changed'],
        'control_differs_from_stored': pre['c_differs_from_stored'],
        'changed_turns_by_case': dict(sorted(changed_by_case.items())),
    }
    precheck['passed'] = (precheck['turns_checked'] > 0 and precheck['window_turns'] > 0
                          and precheck['treated_turns'] > 0
                          and precheck['turns_changed_by_T'] == precheck['treated_turns']
                          and precheck['turns_changed_by_P'] == precheck['treated_turns']
                          and precheck['changed_outside_treated_or_unchanged_inside'] == 0
                          and precheck['window_report_required_turns_changed'] == 0
                          and precheck['window_rule_disagreements'] == 0
                          and precheck['structural_violations'] == 0
                          and precheck['terminal_rejection_turns_checked'] > 0
                          and precheck['terminal_rejection_turns_changed'] == 0
                          and precheck['control_differs_from_stored'] == 0)
    verification_summary = {'turns': verification['turns'], 'verified': verification['verified'],
                            'failed': verification['turns'] - verification['verified'],
                            'failures_by_reason': dict(sorted(failures.items())),
                            'pass_rate': (verification['verified'] / verification['turns']
                                          if verification['turns'] else None),
                            'episodes': len(summaries)}
    return summaries, verification_summary, precheck


# ---------------------------------------------------------------- populations (pure)

def unknown_notification_reply(observations):
    return any(o['tool'] == 'get_operation_status' and o['transport'] == 'ok' and o['status'] == 'UNKNOWN'
               and o['operation'] == 'notifications' for o in observations)


def _key(turn):
    return (turn['historical']['class'], turn['historical']['detail'])


def select_populations(summaries, *, nonlapse_n=NONLAPSE_N):
    """Declared selection over pass-1 summaries. Input order never matters."""
    eligible = sorted((s for s in summaries if s['lifecycle'] == 'COMPLETED' and s['purpose'] == PURPOSE),
                      key=lambda s: s['episode_id'])
    excluded = Counter()
    lapse, nonlapse_pool, report_turns, report_contexts = [], [], [], []
    for summary in eligible:
        turns = summary['turns']
        window = [t for t in turns if t['window']]
        for turn in window:
            if turn['historical']['class'] == 'report':
                if turn['verified']:
                    report_turns.append((summary, turn))
                else:
                    excluded['report_turn_unverified'] += 1
        submitted = [t for t in turns if t['report_submitted_after'] and t['historical']['class'] == 'report']
        if submitted:
            report_contexts.append((summary, submitted[-1]))
        if not window:
            excluded['no_window'] += 1
            continue
        first = window[0]
        if _key(first) == ('get_operation_status', 'notifications'):
            if summary['ever_sent']:
                excluded['lapse_poll_then_sent'] += 1
                continue
            position = turns.index(first)
            following = turns[position + 1] if position + 1 < len(turns) else None
            if following is None or not unknown_notification_reply(following['new_observations']):
                excluded['lapse_without_unknown_reply'] += 1
                continue
            if not (first['verified'] and following['verified']):
                excluded['lapse_unverified'] += 1
                continue
            lapse.append((summary, first, following))
        elif first['historical']['class'] == 'report' or first['historical']['detail'] == 'invalid_action':
            excluded['first_window_turn_not_a_tool'] += 1
        elif first['final_report_required']:
            excluded['first_window_turn_final'] += 1
        elif not first['verified']:
            excluded['nonlapse_unverified'] += 1
        else:
            nonlapse_pool.append((summary, first))
    nonlapse = sorted(nonlapse_pool, key=lambda pair: rank('nonlapse', pair[0]['episode_id']))[:nonlapse_n]
    determinism, levels = match_determinism(report_contexts)
    return {'lapse': lapse, 'nonlapse': nonlapse, 'nonlapse_pool': len(nonlapse_pool),
            'report': report_turns, 'determinism': determinism, 'determinism_match_levels': levels,
            'excluded': dict(sorted(excluded.items()))}


def match_determinism(report_contexts):
    """Every historical-PENDING report context, each with one matched historical-UNKNOWN context.

    Same case, arm, fault_triggered and final_report_required; then, in order, the same
    observation signature, the same observation count, any. Ties by seeded rank; no reuse.
    """
    verified = [(s, t) for s, t in report_contexts if t['verified']]
    pending = sorted(((s, t) for s, t in verified if t['historical']['notification_outcome'] == 'PENDING'),
                     key=lambda pair: pair[0]['episode_id'])
    pool = [(s, t) for s, t in verified if t['historical']['notification_outcome'] == 'UNKNOWN']
    used, chosen, levels = set(), [], Counter()
    for summary, turn in pending:
        base = [(s, t) for s, t in pool if s['episode_id'] not in used
                and (s['case'], s['arm'], s['fault_triggered'], t['final_report_required'])
                == (summary['case'], summary['arm'], summary['fault_triggered'], turn['final_report_required'])]
        ladder = (('signature', lambda t: t['observation_signature'] == turn['observation_signature']),
                  ('observation_count', lambda t: t['observation_count'] == turn['observation_count']),
                  ('case_only', lambda t: True))
        match = None
        for level, accept in ladder:
            candidates = sorted((pair for pair in base if accept(pair[1])),
                                key=lambda pair: rank('determinism', summary['episode_id'], pair[0]['episode_id']))
            if candidates:
                match, levels[level] = candidates[0], levels[level] + 1
                break
        chosen.append(('PENDING', summary, turn, None))
        if match is None:
            levels['unmatched'] += 1
            continue
        used.add(match[0]['episode_id'])
        chosen.append(('UNKNOWN', match[0], match[1], summary['episode_id']))
    return chosen, dict(sorted(levels.items()))


# ---------------------------------------------------------------- pass 2: the request plan

def prompt_units(populations):
    """(population, summary, turn, group, matched_to) for every prompt to send."""
    units = []
    for summary, turn3, turn4 in populations['lapse']:
        units.append(('turn4', summary, turn4, None, None))
        units.append(('turn3', summary, turn3, None, None))
    units += [('nonlapse', summary, turn, None, None) for summary, turn in populations['nonlapse']]
    units += [('report', summary, turn, None, None) for summary, turn in populations['report']]
    units += [('determinism', summary, turn, group, matched) for group, summary, turn, matched in populations['determinism']]
    return units


def build_requests(connection, populations, model=EXPECTED_ACTOR_MODEL):
    """Rebuild each selected prompt again, re-verify it, and lay out the ordered request list.

    T and P are sent only on treated prompts. A report prompt on a report-required turn is sent
    under C alone, after checking that T and P would be byte-identical to C there. Any other
    untreated prompt outside the determinism population is refused.
    """
    units = prompt_units(populations)
    needed = defaultdict(set)
    for _, summary, turn, _, _ in units:
        needed[summary['episode_id']].add(turn['actor_turn'])
    rebuilt = {}
    for episode_id in sorted(needed):
        turns = rebuild_episode(load_events(connection, episode_id), load_intent(connection, episode_id), keep=True)
        for turn in turns:
            if turn['actor_turn'] in needed[episode_id]:
                if not turn['verified']:
                    raise PlanningError(f'Selected prompt {episode_id}:{turn["actor_turn"]} failed verification on rebuild')
                rebuilt[(episode_id, turn['actor_turn'])] = turn
    prompts, by_population = {}, defaultdict(list)
    c_only_identical = 0
    for population, summary, turn, group, matched in units:
        source = rebuilt[(summary['episode_id'], turn['actor_turn'])]
        prompt_id = f"{summary['episode_id']}:{turn['actor_turn']}"
        control = arm_messages(source['history'], source['user'], 'C', source['window'])
        if population == 'determinism':
            arms = ('C',)
        elif source['treated']:
            arms = tuple(sorted(ARMS, key=lambda a: rank('arm', population, prompt_id, a)))
        elif population == 'report':
            if any(arm_messages(source['history'], source['user'], arm, source['window']) != control
                   for arm in ('T', 'P')):
                raise PlanningError(f'An arm differs from C on the untreated report prompt {prompt_id}')
            c_only_identical += 1
            arms = ('C',)
        else:
            raise PlanningError(f'Prompt {prompt_id} of population {population} is not a treated turn')
        response_format = response_format_for(response_contract=source['response_contract'])
        control_request_hash = content_hash({'messages': control, 'response_format': response_format})
        for arm in arms:
            messages = arm_messages(source['history'], source['user'], arm, source['window'])
            request_hash = content_hash({'messages': messages, 'response_format': response_format})
            if arm == 'C' and (content_hash(messages), request_hash) != (source['stored_messages_hash'], source['stored_request_hash']):
                raise PlanningError(f'Control prompt {prompt_id} is not the stored request')
            if arm != 'C' and request_hash == control_request_hash:
                raise PlanningError(f'Arm {arm} of prompt {prompt_id} is identical to C')
            if request_hash not in prompts:
                bound = validate_request_input(messages, model, response_contract=source['response_contract'])
                prompts[request_hash] = {'request_hash': request_hash, 'messages_hash': content_hash(messages),
                                         'response_contract': source['response_contract'],
                                         'response_format': response_format, 'messages': messages,
                                         'input_token_bound': bound}
            by_population[population].append({
                'population': population, 'prompt_id': prompt_id, 'episode_id': summary['episode_id'],
                'actor_turn': turn['actor_turn'], 'case': summary['case'], 'episode_arm': summary['arm'],
                'arm': arm, 'group': group, 'matched_to': matched, 'window': source['window'],
                'treated': source['treated'],
                'final_report_required': source['final_report_required'],
                'response_contract': source['response_contract'], 'request_hash': request_hash,
                'messages_hash': prompts[request_hash]['messages_hash'],
                'input_token_bound': prompts[request_hash]['input_token_bound'],
                'historical': {**source['historical'], 'raw_sha256': source['raw_sha256']}})
    requests = []
    for population in POPULATION_ORDER:
        rows = by_population.get(population, [])
        if population == 'determinism':
            contexts = sorted({r['prompt_id'] for r in rows}, key=lambda p: rank('order', population, p))
            by_prompt = {r['prompt_id']: r for r in rows}
            ordered = [{**by_prompt[p], 'repeat': repeat} for repeat in range(DETERMINISM_REPEATS) for p in contexts]
        else:
            prompt_order = {p: rank('order', population, p) for p in {r['prompt_id'] for r in rows}}
            ordered = [{**r, 'repeat': 0} for r in sorted(rows, key=lambda r: prompt_order[r['prompt_id']])]
        requests += ordered
    for index, request in enumerate(requests, 1):
        request['request_id'] = f'r{index:04d}'
    return requests, prompts, {'report_prompts_c_only_arms_identical': c_only_identical}


# ---------------------------------------------------------------- settings, pins, plan

def settings_from_file(settings_path, *, env_path):
    """Apply the non-empty values of the reviewed non-secret settings file, as the Phase 17 launch
    and runners do. env_path=os.devnull (dry) never reads the root .env; None (live) lets the
    runtime's own loader read credentials from it."""
    from app.config import Settings
    overrides = {k: str(v) for k, v in json.loads(pathlib.Path(settings_path).read_text()).items() if v != ''}
    saved = {k: os.environ.get(k) for k in overrides}
    try:
        os.environ.update(overrides)
        return Settings.from_env(env_path=env_path)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def configuration_pins(settings):
    from app.contracts.models import CampaignBudget
    from app.lab.configuration import frozen_configuration
    caps = CampaignBudget(model_calls=settings.faultlab_model_call_cap, tokens=settings.faultlab_token_cap,
                          dollars=float(settings.faultlab_dollar_cap))
    frozen = frozen_configuration(settings, caps, 'live-v1')
    return {'configuration_hash': content_hash(frozen), 'actor_model': frozen['models']['actor'],
            'actor_model_settings': frozen['model_settings_by_role']['actor'],
            'per_request_dollar_bound': frozen['pricing']['actor']['per_call_dollar_upper_bound']}


def check_pins(pins):
    if pins['configuration_hash'] != DECLARED_CONFIGURATION_HASH:
        raise PlanningError('configuration_hash differs from the declared Phase 19 value; backend/app or settings changed')
    if pins['actor_model'] != EXPECTED_ACTOR_MODEL:
        raise PlanningError('The Actor model is not the declared one')
    if pins['actor_model_settings'].get('temperature') != 0 or MODEL_REQUEST_SETTINGS['temperature'] != 0:
        raise PlanningError('The Actor temperature is not the frozen 0')
    if pins['per_request_dollar_bound'] != PER_REQUEST_DOLLAR_BOUND:
        raise PlanningError('The per-request dollar bound is not the declared $0.0209')


def check_budget(total_requests, spend_cap):
    if not (isinstance(spend_cap, (int, float)) and math.isfinite(spend_cap) and 0 < spend_cap <= HARD_SPEND_CAP):
        raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    if SpendGuard.micro(total_requests * PER_REQUEST_DOLLAR_BOUND) > SpendGuard.micro(spend_cap):
        raise PlanningError(f'{total_requests} planned requests exceed the ${spend_cap:.2f} cap at ${PER_REQUEST_DOLLAR_BOUND}/request')


def build_plan(*, store=STORE, settings_path=None, spend_cap=HARD_SPEND_CAP, cutoff=STORE_CUTOFF):
    settings_path = pathlib.Path(settings_path or ROOT / DECLARED_SETTINGS)
    if sha256_file(settings_path) != DECLARED_SETTINGS_SHA256:
        raise PlanningError('The settings file is not the declared Phase 17 settings file')
    pins = configuration_pins(settings_from_file(settings_path, env_path=os.devnull))
    check_pins(pins)
    connection = connect(store)
    try:
        episodes, cases, triggered = load_index(connection)
        summaries, verification, precheck = survey(connection, episodes, cases, triggered, cutoff)
        if not precheck['passed']:
            raise PlanningError('The $0 v5/placebo pre-check failed; nothing may be sent')
        populations = select_populations(summaries)
        requests, prompts, notes = build_requests(connection, populations, pins['actor_model'])
    finally:
        connection.close()
    counts = Counter((r['population'], r['arm']) for r in requests)
    total = len(requests)
    check_budget(total, spend_cap)
    lapse_ids = sorted(s['episode_id'] for s, _, _ in populations['lapse'])
    report_treated = sum(1 for _, turn in populations['report'] if turn['treated'])
    plan = {
        'schema_version': SCHEMA, 'experiment': 'phase21_actor_lapse_replay_probe',
        'scoring': 'NON_SCORING_NEVER_FED_BACK', 'split': 'development', 'purpose': PURPOSE,
        'store_cutoff': cutoff, 'harness_sha256': sha256_file(__file__),
        'source_sha256': {name: sha256_file(ROOT / name) for name in SOURCE_FILES},
        'actor_prompt_hash': ACTOR_PROMPT_HASH, 'actor_context_protocol': ACTOR_CONTEXT_PROTOCOL_V4,
        'settings_file': DECLARED_SETTINGS, 'settings_sha256': DECLARED_SETTINGS_SHA256, **pins,
        'provider_call': {'role': 'actor', 'max_output_tokens': ACTOR_MAX_OUTPUT_TOKENS,
                          'timeout_seconds': ACTOR_TIMEOUT_SECONDS,
                          'response_format': 'response_format_for(stored response_contract)',
                          'blind_retry': list(RETRYABLE_TRANSPORT_CODES) + [
                              f'at most once, charged, after {BLIND_RETRY_WAIT_SECONDS} s'],
                          'backoff_after_errored_request_seconds': list(BACKOFF_SECONDS),
                          'consecutive_errored_requests_stop': CONSECUTIVE_ERROR_ABORT,
                          'served_model': 'recorded from each response, never enforced'},
        'arms': {'C': 'the exact verified v4 request, re-sent',
                 'T': {'field': V5_FIELD, 'value': V5_VALUE, 'turns': TREATMENT_RULE},
                 'P': {'field': PLACEBO_FIELD, 'value': PLACEBO_VALUE, 'turns': TREATMENT_RULE}},
        'sampling': {'seed': SAMPLE_SEED, 'nonlapse_rule': ('eligible = first in-window turn of a COMPLETED '
                     'completion-study v4 episode whose historical action is a tool other than '
                     'get_operation_status(notifications), not report-required, verified; take the first '
                     f'{NONLAPSE_N} by sha256(seed:nonlapse:episode_id)'),
                     'nonlapse_pool': populations['nonlapse_pool'],
                     'determinism_rule': match_determinism.__doc__.strip(),
                     'determinism_match_levels': populations['determinism_match_levels'],
                     'order': ('populations in order ' + ', '.join(POPULATION_ORDER) + '; prompts by '
                               'sha256 rank; arms per prompt by sha256 rank; determinism repeats round-robin')},
        'populations': {'lapse_episodes': lapse_ids, 'lapse_count': len(lapse_ids),
                        'turn4_prompts': len(populations['lapse']), 'turn3_prompts': len(populations['lapse']),
                        'nonlapse_prompts': len(populations['nonlapse']),
                        'report_prompts': len(populations['report']),
                        'report_prompts_treated': report_treated,
                        'report_prompts_c_only': len(populations['report']) - report_treated,
                        **notes,
                        'determinism_contexts': dict(Counter(g for g, *_ in populations['determinism'])),
                        'excluded': populations['excluded']},
        'readout_rules': {
            'primary': ('turn4: T send rate >= 0.8 AND T - max(C, P) >= 0.5, with missing T counted as non-sends '
                        'and missing C and P as sends (the received-only rates are reported and implied); AND '
                        'one-sided Fisher p (T vs P, unpaired, implied by the rates) < 0.01. Exact McNemar T vs P '
                        'is descriptive. A FAIL states which condition failed: T < 0.8, T - P < 0.5, or T - C < 0.5'),
            'R3': ('nonlapse, T decides: agreement with C on action class (get_operation_status by service, '
                   'other tools by name) >= 0.95 of compared prompts, a move into send_confirmation not '
                   'counted as a mismatch; and 0 T reports. P is reported, never decides'),
            'R4': (f'report, T decides: no T word outside the historical word and {sorted(R4_INTERCHANGEABLE)}; '
                   'no T non-report on a report-required turn; a T tool action on a voluntary report turn is '
                   'not judged, so R4 is always quoted as "R4 <status> on k of <T planned> T reports". C word '
                   'vs historical word is the declared noise reference, reported pooled and on the voluntary '
                   'prompts alone; P and the other report fields are descriptive'),
            'turn3': 'descriptive only, beside P',
            'determinism': ('byte-identical repeat share; within-context word disagreement (Wilson); change '
                            'from the historical word (confounded with time); PENDING probability by group'),
            'complete': ('a read-out is INCOMPLETE unless each arm it uses received >= 95% of its planned '
                         'requests (R3: >= 95% of prompts compared; R4: T and C, and T on report-required turns)'),
            'decision': 'primary, R3 and R4 must all PASS before v5 enters Phase 22'},
        'verification': verification, 'precheck': precheck,
        'counts': {'by_population_and_arm': {f'{p}/{a}': n for (p, a), n in sorted(counts.items())},
                   'total_requests': total, 'distinct_prompts': len(prompts)},
        'cost': {'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                 'planned_upper_bound': round(total * PER_REQUEST_DOLLAR_BOUND, 6), 'spend_cap': spend_cap,
                 'phase_spend_cap': HARD_SPEND_CAP,
                 'phase_spend_cap_rule': ('a live run after earlier runs that delivered nothing gets the phase cap '
                                          'minus their charged_upper_bound, and the plan must fit under that'),
                 'max_attempts_under_cap': SpendGuard.micro(spend_cap) // SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND),
                 'retry_headroom_attempts': SpendGuard.micro(spend_cap) // SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND) - total},
        'max_input_token_bound': max(p['input_token_bound'] for p in prompts.values()),
        'requests': requests,
    }
    return plan, prompts


def plan_hash(plan):
    return content_hash(plan)


# ---------------------------------------------------------------- spend guard, output guard, claims

class SpendGuard:
    """Charges every attempt at the conservative bound, in integer micro-dollars."""

    def __init__(self, cap, per_request=PER_REQUEST_DOLLAR_BOUND):
        if not (math.isfinite(cap) and 0 < cap <= HARD_SPEND_CAP):
            raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
        self.cap, self.per_request, self.attempts = cap, per_request, 0

    @staticmethod
    def micro(dollars):
        return round(dollars * 1_000_000)

    def admit(self):
        if (self.attempts + 1) * self.micro(self.per_request) > self.micro(self.cap):
            return False
        self.attempts += 1
        return True

    @property
    def charged(self):
        return self.attempts * self.micro(self.per_request) / 1_000_000


def _root(root=None):
    """The repository root, read at call time so tests can point every guard at a tmp tree."""
    return pathlib.Path(root if root is not None else ROOT)


def delivered_generations(manifest):
    """Generations a run received (ok or empty responses, or any response that carried usage).
    None when the manifest cannot say, which counts as delivered."""
    counted = manifest.get('generations_delivered')
    statuses = manifest.get('statuses') or {}
    if type(counted) is not int or not isinstance(statuses, dict):
        return None
    return max(counted, int(statuses.get('ok', 0)) + int(statuses.get('empty_response', 0)))


def entry_delivered(entry):
    """Whether one saved response line shows that a generation arrived: an ok or empty response,
    or any attempt on which the provider returned a response object (its served metadata was
    recorded) or usage. Conservative: anything that may have arrived counts."""
    if not isinstance(entry, dict):
        return True
    if entry.get('status') in RECEIVED:
        return True
    for attempt in entry.get('attempts') or []:
        if not isinstance(attempt, dict):
            return True
        if (attempt.get('served') is not None or attempt.get('input_tokens') is not None
                or attempt.get('output_tokens') is not None
                or attempt.get('code') in ('EMPTY_FINAL_RESPONSE', 'INVALID_RESPONSE_SHAPE')):
            return True
    return False


def claimed_output(artifacts, out):
    """The output directory a claim names, which must have the shape check_output enforces:
    artifacts/phase21-<date>/<name>, relative, with nothing else in it."""
    parts = pathlib.PurePosixPath(out).parts if isinstance(out, str) and out else ()
    if (len(parts) != 3 or parts[0] != 'artifacts' or not parts[1].startswith('phase21-') or parts[1] == CLAIM_DIR
            or any(part in ('', '.', '..') for part in parts)):
        return None
    return pathlib.Path(artifacts).parent / parts[0] / parts[1] / parts[2]


def _final(manifest):
    return manifest.get('status') in FINAL_STATUSES and bool(manifest.get('ended_at'))


def _charge(manifest, path):
    charged = manifest.get('charged_upper_bound')
    if type(charged) not in (int, float) or not math.isfinite(charged) or charged < 0:
        raise PlanningError(f'An earlier live run does not state a readable charged_upper_bound ({path}); '
                            'the phase cap cannot be applied. Investigate before any run')
    return charged


def live_run_records(artifacts):
    """Every earlier live run, checked; refuses unless each one is final and delivered nothing.

    Each claim is matched to the manifest in the directory the claim names (as Phase 20's
    run_dev_probe.phase21_active_runs reads it), never by count, so a copied manifest cannot hide
    a claim whose run has no final manifest. Every manifest at the run depth must also be final
    and undelivered. Returns the undelivered runs with their charges, and the claim numbers this
    same listing validated: the next claim is named from them, so a launch can only take the
    claim that follows the claims it checked.
    """
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
            raise PlanningError(f'{claim.name} cannot be read or names no valid output directory; investigate '
                                'before any run')
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
            raise PlanningError(f'A live lapse-probe run already exists ({path}); a second draw would be '
                                'repeat-until-lucky and needs its own declared phase')
        undelivered.append({'manifest': str(path.relative_to(artifacts.parent)),
                            'charged_upper_bound': _charge(manifest, path)})
    return {'undelivered': undelivered, 'claim_numbers': sorted(numbers)}


def earlier_live_runs(artifacts):
    """Refuse unless every earlier live run is final and delivered no generation.

    A run that received nothing observed nothing, so there is nothing to select on and a new run
    in a new directory is not a second draw (pitfall 49). Any delivered generation, a run that
    may still be running, or a claim with no final manifest refuses. Returns the earlier
    undelivered runs with their charged bounds, which the next claim and manifest record.
    """
    return live_run_records(artifacts)['undelivered']


def phase_spend_remaining(earlier):
    """What the $25 phase cap leaves after the charged bounds of earlier undelivered runs."""
    used = sum(SpendGuard.micro(run['charged_upper_bound']) for run in earlier)
    return (SpendGuard.micro(HARD_SPEND_CAP) - used) / 1_000_000


def effective_spend_cap(requested, earlier):
    """The cap a live run gets: the requested cap, never more than the phase cap leaves."""
    if not (isinstance(requested, (int, float)) and math.isfinite(requested) and 0 < requested <= HARD_SPEND_CAP):
        raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    remaining = phase_spend_remaining(earlier)
    if remaining <= 0:
        raise PlanningError(f'Earlier runs that delivered nothing already charged the ${HARD_SPEND_CAP:.2f} phase cap')
    return min(requested, remaining)


def check_output(out, *, root=None, live=True):
    """A new directory exactly artifacts/phase21-<date>/<name>, never an existing one; one
    delivering live run only."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    out = pathlib.Path(out)
    out = (out if out.is_absolute() else root / out).resolve()
    try:
        relative = out.relative_to(artifacts)
    except ValueError:
        raise PlanningError('The output directory must be under artifacts/phase21-<date>/') from None
    if len(relative.parts) != 2 or not relative.parts[0].startswith('phase21-') or relative.parts[0] == CLAIM_DIR:
        raise PlanningError('The output directory must be exactly artifacts/phase21-<date>/<name>')
    if out.exists():
        raise PlanningError(f'{out} exists; a run is never resumed or overwritten - use a new directory')
    if live:
        earlier_live_runs(artifacts)
    return out


def take_claim(out, plan_hash_value, harness, *, root=None, spend_cap=None, expected_earlier=None):
    """Atomically claim the next live run. The name follows the claims this launch just
    validated, so two launches that passed their checks together compute the same name and only
    one can create it. The claim is written in full to a private file first and then hard-linked
    to its name (os.link fails if the name exists, like O_CREAT|O_EXCL), so a claim is either
    absent or complete: a kill can never leave an empty claim that no reader can parse. Never
    deleted."""
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
    """False only when the claim's process is gone: no such pid, or the pid now belongs to a
    process that is not this harness (recycled). Anything uncertain counts as alive."""
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
    return not command.strip() or 'lapse_probe' in command


def finalize_abandoned(claim, *, root=None, alive=None):
    """Close, at $0, a claimed run whose process died before its manifest became final.

    Refuses while the claim's process may be alive, and for a run that is already final. Counts
    what the run delivered from responses.jsonl (entry_delivered) and charges every recorded
    attempt, plus ABANDONED_IN_FLIGHT_ATTEMPTS when the run died while RUNNING. Writes a final
    ABORTED manifest in the claimed directory, which ends the claim for this harness and for
    Phase 20's reading of it. A later run is still allowed only if the count is 0.
    """
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
    # No provider call is made before the manifest says RUNNING (run_live), so a run with no
    # manifest, or one still STARTING, had nothing in flight.
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
        'requests_done': len(results),
        'statuses': dict(sorted(Counter(str(r.get('status')) if isinstance(r, dict) else 'unreadable'
                                        for r in results).items())),
        'generations_delivered': None if prior is None else max(prior, delivered),
        'attempts': attempts,
        'charged_upper_bound': attempts * SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND) / 1_000_000,
        'finalized_abandoned': {
            'at': now, 'claim': str(path.relative_to(artifacts.parent)), 'pid': pid, 'pid_alive': False,
            'previous_status': previous_status, 'responses_lines': len(results),
            'partial_lines_skipped': partial, 'unrecorded_in_flight_attempts_charged': in_flight,
            'rule': ('delivered = ok or empty responses, or any attempt that returned a response object or usage; '
                     'charged = recorded attempts plus up to two unrecorded in-flight attempts when RUNNING')}})
    output.mkdir(parents=True, exist_ok=True)
    write_json(manifest_path, manifest)
    return manifest_path, manifest


def active_phase20_runs(*, root=None, ignore=()):
    """Phase 20 manifests that may still be running (no ended_at, or stop_reason 'running')."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    ignored = {(pathlib.Path(p) if pathlib.Path(p).is_absolute() else root / p).resolve() for p in ignore or ()}
    active = []
    for path in sorted(artifacts.glob(PHASE20_MANIFEST_GLOB)):
        if path.resolve() in ignored:
            continue
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError):
            active.append(str(path))
            continue
        if not isinstance(manifest, dict) or not manifest.get('ended_at') or manifest.get('stop_reason') == 'running':
            active.append(str(path))
    return active


def check_phase20(args, *, root=None):
    active = active_phase20_runs(root=root, ignore=getattr(args, 'ignore_phase20_manifest', None) or ())
    if active:
        raise PlanningError(f'A Phase 20 run may be in progress ({active[0]}); one paid run at a time. If it '
                            'crashed, pass its manifest path to --ignore-phase20-manifest')


def status_block(protocol_text):
    """The protocol's opening block, before its first '## ' heading, where its status line lives."""
    lines = []
    for line in protocol_text.splitlines():
        if line.startswith('## '):
            break
        lines.append(line)
    return '\n'.join(lines)


def check_review(protocol_text, protocol_sha256, harness, plan_hash_value, *, root=None):
    """The review is enforced, not only procedural: the protocol's status block no longer says it
    is not yet reviewed, it names the reviewed pins on a bare line of their own, and the review
    record repeats them."""
    if REVIEW_PENDING_MARKER in status_block(protocol_text):
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
    expected = {'protocol_sha256': protocol_sha256, 'harness_sha256': harness, 'plan_hash': plan_hash_value}
    if not isinstance(record, dict) or any(record.get(key) != value for key, value in expected.items()):
        raise PlanningError('The review record does not name this protocol sha256, harness sha256 and plan hash')


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    os.replace(temporary, path)


# ---------------------------------------------------------------- live execution

class Recorder:
    """Appends each response as it arrives and rewrites the manifest after every request."""

    def __init__(self, out, manifest, secrets=()):
        self.out, self.manifest, self.secrets = out, manifest, tuple(s for s in secrets if s)
        self.stream = (out / 'responses.jsonl').open('a', encoding='utf-8')

    def scrub(self, text):
        for secret in self.secrets:
            text = text.replace(secret, '[redacted]')
        return text

    def record(self, entry):
        self.stream.write(self.scrub(json.dumps(entry, sort_keys=True, ensure_ascii=False)) + '\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def save(self):
        path = self.out / MANIFEST_NAME
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(self.scrub(json.dumps(self.manifest, indent=2, ensure_ascii=False)) + '\n')
        os.replace(temporary, path)

    def close(self):
        self.stream.close()


def openai_client_factory(**kwargs):
    """The provider client RuntimeProvider would build itself (read at call time; tests replace it)."""
    from openai import AsyncOpenAI
    return AsyncOpenAI(**kwargs)


def _short_text(value):
    return value[:200] if isinstance(value, str) else None


def served_metadata(response):
    usage = getattr(response, 'usage', None)

    def count(name):
        value = getattr(usage, name, None)
        return value if type(value) is int else None
    return {'model': _short_text(getattr(response, 'model', None)),
            'system_fingerprint': _short_text(getattr(response, 'system_fingerprint', None)),
            'prompt_tokens': count('prompt_tokens'), 'completion_tokens': count('completion_tokens')}


class ServedRecorder:
    """A client_factory for RuntimeProvider that records what actually served each request.

    RuntimeGeneration.model_id is the model the runtime REQUESTED (runtime.py builds it from the
    settings), so it can never show a different served model. This wrapper keeps each response's
    own `model`, `system_fingerprint` and usage. They are recorded and never enforced: the
    served-model string format is unverified, and an abort on it could end the one live run.
    """

    def __init__(self, base=None):
        self.base, self.last = base, None

    def __call__(self, **kwargs):
        return _RecordingClient((self.base or openai_client_factory)(**kwargs), self)

    def reset(self):
        self.last = None

    def take(self):
        value, self.last = self.last, None
        return value

    def observe(self, response):
        self.last = served_metadata(response)


class _RecordingClient:
    def __init__(self, client, recorder):
        self._client, self._recorder = client, recorder
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        response = await self._client.chat.completions.create(**kwargs)
        self._recorder.observe(response)
        return response

    async def close(self):
        await self._client.close()


async def run_requests(requests, prompts, provider, guard, recorder, *, stop=lambda: False, served=None,
                       sleep=asyncio.sleep, backoff=BACKOFF_SECONDS, retry_wait=BLIND_RETRY_WAIT_SECONDS):
    """Send the planned requests in order. Returns the stop reason. Never re-rolls a response:
    only a transport failure that delivered no generation is retried, once, after a short wait,
    and charged. After a request that ends in error the loop waits along `backoff` before the
    next request; the CONSECUTIVE_ERROR_ABORT-th consecutive errored request stops the run."""
    manifest = recorder.manifest
    for key, value in (('requests_done', 0), ('statuses', {}), ('measured_input_tokens', 0),
                       ('measured_output_tokens', 0), ('generations_delivered', 0), ('backoff_waits', [])):
        manifest.setdefault(key, value)

    async def pause(seconds):
        remaining = float(seconds)
        while remaining > 0 and not stop():
            step = min(1.0, remaining)
            await sleep(step)
            remaining -= step

    consecutive_errors = 0
    for request in requests:
        if stop():
            return 'operator_stop'
        prompt = prompts[request['request_hash']]
        entry = {key: request[key] for key in ('request_id', 'population', 'prompt_id', 'arm', 'repeat', 'request_hash')}
        entry.update(attempts=[], status='error', raw=None)
        generation, refused, delivered = None, False, False
        for attempt in (1, 2):
            if attempt == 2:
                await pause(retry_wait)
                if stop():
                    break
            if not guard.admit():
                refused = True
                break
            if served is not None:
                served.reset()
            started = datetime.now(timezone.utc).isoformat()
            try:
                generation = await provider.complete(prompt['messages'], role='actor',
                                                     max_output_tokens=ACTOR_MAX_OUTPUT_TOKENS,
                                                     timeout_seconds=ACTOR_TIMEOUT_SECONDS,
                                                     response_contract=prompt['response_contract'])
                entry['attempts'].append({'attempt': attempt, 'started_at': started, 'error': None,
                                          'served': served.take() if served is not None else None})
                break
            except RuntimeProviderError as error:
                delivered = delivered or error.generation is not None
                entry['attempts'].append({'attempt': attempt, 'started_at': started, **error.diagnostics,
                                          'served': served.take() if served is not None else None})
                if error.code == 'EMPTY_FINAL_RESPONSE':
                    entry['status'] = 'empty_response'
                    break
                if attempt == 1 and error.code in RETRYABLE_TRANSPORT_CODES:
                    continue
                break
        manifest['attempts'] = guard.attempts
        manifest['charged_upper_bound'] = guard.charged
        if generation is not None or delivered:
            # Counted as soon as anything arrived, before any processing that could fail.
            manifest['generations_delivered'] += 1
        if generation is not None:
            entry.update(status='ok', raw=generation.content, requested_model=generation.model_id,
                         input_tokens=generation.input_tokens, output_tokens=generation.output_tokens)
        served_last = (entry['attempts'][-1].get('served') if entry['attempts'] else None) or {}
        entry['served_model'] = served_last.get('model')
        entry['system_fingerprint'] = served_last.get('system_fingerprint')
        entry['raw_sha256'] = hashlib.sha256(entry['raw'].encode()).hexdigest() if entry['raw'] is not None else None
        entry.update(classify(entry['raw']) if entry['status'] == 'ok' else
                     {'class': 'other' if entry['status'] == 'empty_response' else None,
                      'detail': entry['status'], 'notification_outcome': None, 'report': None})
        entry['matches_historical_raw'] = (entry['raw_sha256'] == request['historical']['raw_sha256']
                                           if request['arm'] == 'C' and entry['raw'] is not None else None)
        if entry['attempts']:
            recorder.record(entry)
            manifest['requests_done'] += 1
            manifest['statuses'][entry['status']] = manifest['statuses'].get(entry['status'], 0) + 1
            if entry['status'] == 'ok':
                manifest['measured_input_tokens'] += entry.get('input_tokens') or 0
                manifest['measured_output_tokens'] += entry.get('output_tokens') or 0
        recorder.save()
        if refused:
            return 'spend_guard'
        consecutive_errors = consecutive_errors + 1 if entry['status'] == 'error' else 0
        if consecutive_errors >= CONSECUTIVE_ERROR_ABORT:
            return 'consecutive_errors'
        if consecutive_errors:
            wait = backoff[min(consecutive_errors, len(backoff)) - 1]
            manifest['backoff_waits'].append({'after_request': request['request_id'], 'seconds': wait,
                                              'consecutive_errors': consecutive_errors})
            recorder.save()
            await pause(wait)
    return 'completed'


def load_results(path):
    """Saved responses. Only a trailing line cut off by a hard kill (no final newline, not valid
    JSON) is skipped, and it is counted; any other unreadable line refuses."""
    lines = pathlib.Path(path).read_text(encoding='utf-8').split('\n')
    results, partial = [], 0
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            results.append(json.loads(line))
        except ValueError:
            if index == len(lines) - 1:
                partial += 1
                continue
            raise PlanningError(f'responses.jsonl line {index + 1} is not valid JSON') from None
    return results, partial


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
    """The read-outs of a saved run, recomputed at $0 by this harness. They are the declared
    read-outs only when this harness's sha256 and the saved plan's hash equal the run manifest's;
    otherwise this refuses, or with allow_other_harness returns them under NOT_THE_RUNS_HARNESS."""
    directory = pathlib.Path(directory)
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable {MANIFEST_NAME} in {directory}; read-outs are tied to a run') from None
    plan, results, partial = load_run(directory)
    readouts = compute_readouts(plan['requests'], results, partial_lines_skipped=partial)
    harness_matches = isinstance(manifest, dict) and sha256_file(__file__) == manifest.get('harness_sha256')
    plan_matches = isinstance(manifest, dict) and plan_hash(plan) == manifest.get('plan_hash')
    if harness_matches and plan_matches:
        return readouts
    if not allow_other_harness:
        raise PlanningError(f'{NOT_THE_RUNS_HARNESS} (harness matches the run: {harness_matches}; plan matches the '
                            f'run: {plan_matches}). Pass --not-the-runs-harness to print it labelled')
    return {'label': NOT_THE_RUNS_HARNESS, 'harness_matches_run': harness_matches, 'plan_matches_run': plan_matches,
            'readouts': readouts}


def run_live(args, plan, prompts, *, sleep=asyncio.sleep):
    out = check_output(args.out)
    check_phase20(args)
    harness = sha256_file(__file__)
    if args.expect_harness_sha256 != harness:
        raise PlanningError('--expect-harness-sha256 does not match this script')
    if not PROTOCOL.exists():
        raise PlanningError('No protocol at docs/part2/PHASE21_EXPERIMENT.md; live execution refuses until one is reviewed')
    protocol_sha256 = sha256_file(PROTOCOL)
    if args.expect_protocol_sha256 != protocol_sha256:
        raise PlanningError('--expect-protocol-sha256 does not match the protocol file')
    if args.expect_plan_hash != plan_hash(plan):
        raise PlanningError('The recomputed plan differs from the reviewed dry plan (--expect-plan-hash)')
    protocol_text = PROTOCOL.read_text()
    if harness not in protocol_text or plan_hash(plan) not in protocol_text:
        raise PlanningError('The protocol does not declare this harness sha256 and this plan hash')
    check_review(protocol_text, protocol_sha256, harness, plan_hash(plan))
    artifacts = (_root() / 'artifacts').resolve()
    # The $25 cap is a phase cap: earlier runs that delivered nothing still charged their bound.
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
    check_phase20(args)
    stop_requested = False
    recorder = None

    def request_stop(*_):
        nonlocal stop_requested
        stop_requested = True

    async def execute():
        from app.providers.runtime import RuntimeProvider
        served = ServedRecorder()
        async with RuntimeProvider(settings, live_authorized=True, client_factory=served) as provider:
            return await run_requests(plan['requests'], prompts, provider, guard, recorder,
                                      stop=lambda: stop_requested, served=served, sleep=sleep)

    # The handlers go in before the claim, so from the claim on an operator stop is recorded as a
    # stop in a final manifest; it can never leave a claim without one.
    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if stop_requested:
            raise PlanningError('An operator stop arrived before the claim; nothing was claimed or sent')
        claim, earlier = take_claim(out, plan_hash(plan), harness, spend_cap=spend_cap, expected_earlier=earlier)
        # The first manifest is written straight after the claim (only the directory is made and the
        # response file opened first) and says STARTING: no provider call is made before it says
        # RUNNING. A failure from here on ends in a final manifest; a claim left without one (a hard
        # kill, a failed disk) is closed at $0 by --finalize-abandoned.
        out.mkdir(parents=True, exist_ok=False)
        manifest = {'schema_version': SCHEMA, 'mode': 'live', 'status': 'STARTING', 'pid': os.getpid(),
                    'plan_hash': plan_hash(plan), 'harness_sha256': harness, 'protocol_sha256': protocol_sha256,
                    'configuration_hash': pins['configuration_hash'], 'settings_sha256': DECLARED_SETTINGS_SHA256,
                    'actor_model': pins['actor_model'], 'spend_cap': spend_cap,
                    'spend_cap_requested': args.spend_cap, 'phase_spend_cap': HARD_SPEND_CAP,
                    'earlier_undelivered_charged': round(HARD_SPEND_CAP - phase_spend_remaining(earlier), 6),
                    'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                    'claim': str(claim.relative_to(artifacts.parent)), 'earlier_undelivered_runs': earlier,
                    'ignored_phase20_manifests': list(getattr(args, 'ignore_phase20_manifest', None) or ()),
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
            manifest['status'] = 'RUNNING'
            recorder.save()
            manifest['stop_reason'] = asyncio.run(execute())
            manifest['status'] = 'COMPLETED' if manifest['stop_reason'] == 'completed' else 'STOPPED'
        except Exception as error:  # noqa: BLE001 - recorded with its traceback, never silently dropped
            manifest.update(status='ABORTED', stop_reason=f'{type(error).__name__}',
                            traceback=traceback.format_exc()[-8000:])
        finally:
            manifest['ended_at'] = datetime.now(timezone.utc).isoformat()
            recorder.save()
            recorder.close()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    results, partial = load_results(out / 'responses.jsonl')
    readouts = compute_readouts(plan['requests'], results, partial_lines_skipped=partial)
    write_json(out / 'readouts.json', readouts)
    print(json.dumps({'status': manifest['status'], 'stop_reason': manifest['stop_reason'],
                      'requests_done': manifest['requests_done'], 'attempts': manifest['attempts'],
                      'generations_delivered': manifest['generations_delivered'],
                      'charged_upper_bound': manifest['charged_upper_bound'],
                      'decision': readouts['decision'], 'output': str(out)}, indent=2))
    return 0 if manifest['status'] == 'COMPLETED' else 1


# ---------------------------------------------------------------- statistics and read-outs (pure)

def fisher_greater(a, n1, b, n2):
    """One-sided Fisher exact p: P(X >= a), X the first row's successes given both margins."""
    if not (0 <= a <= n1 and 0 <= b <= n2) or n1 + n2 == 0:
        raise ValueError('invalid 2x2 table')
    k, total = a + b, n1 + n2
    upper = min(k, n1)
    return sum(math.comb(n1, x) * math.comb(n2, k - x) for x in range(a, upper + 1)) / math.comb(total, k)


def mcnemar_greater(b, c):
    """Exact one-sided McNemar (sign) test: P(X >= b), X ~ Binomial(b + c, 1/2), over discordant pairs."""
    if b < 0 or c < 0:
        raise ValueError('invalid discordant counts')
    n = b + c
    if n == 0:
        return 1.0
    return sum(math.comb(n, x) for x in range(b, n + 1)) / 2 ** n


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def _received(result):
    return result is not None and result.get('status') in RECEIVED


def _ratio(k, n):
    return k / n if n else None


def _complete(received, planned):
    return planned > 0 and Fraction(received, planned) >= COMPLETE_MIN


def _by_arm(rows):
    planned, got = Counter(), defaultdict(list)
    for request, result in rows:
        planned[request['arm']] += 1
        if _received(result):
            got[request['arm']].append(result)
    return planned, got


def _by_prompt(rows):
    prompts = defaultdict(dict)
    planned = set()
    for request, result in rows:
        planned.add(request['prompt_id'])
        prompts[request['prompt_id']][request['arm']] = result
    return prompts, len(planned)


def _label(result):
    return f"{result['class']}:{result.get('detail')}"


def primary_readout(rows):
    planned, got = _by_arm(rows)
    sends = {arm: sum(r['class'] == 'send_confirmation' for r in got[arm]) for arm in ARMS}
    n = {arm: len(got[arm]) for arm in ARMS}
    missing = {arm: planned[arm] - n[arm] for arm in ARMS}
    complete = all(_complete(n[arm], planned[arm]) for arm in ARMS)
    prompts, _ = _by_prompt(rows)
    both = [(arms['T'], arms['P']) for arms in prompts.values() if _received(arms.get('T')) and _received(arms.get('P'))]
    t_only = sum(t['class'] == 'send_confirmation' and p['class'] != 'send_confirmation' for t, p in both)
    p_only = sum(p['class'] == 'send_confirmation' and t['class'] != 'send_confirmation' for t, p in both)
    out = {'planned': dict(planned), 'received': n, 'missing': missing, 'sends': sends,
           'send_rate': {arm: _ratio(sends[arm], n[arm]) for arm in ARMS},
           'send_rate_wilson95': {arm: wilson(sends[arm], n[arm]) for arm in ARMS},
           'classes': {arm: dict(Counter(r['class'] for r in got[arm])) for arm in ARMS},
           'paired_t_vs_p': {'pairs': len(both), 't_sends_p_not': t_only, 'p_sends_t_not': p_only,
                             'mcnemar_exact_one_sided_p_descriptive': mcnemar_greater(t_only, p_only)}}
    if not complete or not all(n[arm] for arm in ARMS):
        return {**out, 'status': 'INCOMPLETE', 'conditions': None, 't_minus_p': None, 't_minus_c': None,
                'fisher_one_sided_p_unpaired_implied': None}
    observed = {arm: Fraction(sends[arm], n[arm]) for arm in ARMS}
    # Worst case for v5: a missing T response is a non-send; a missing C or P response is a send.
    worst = {'T': Fraction(sends['T'], planned['T']),
             'C': Fraction(sends['C'] + missing['C'], planned['C']),
             'P': Fraction(sends['P'] + missing['P'], planned['P'])}

    def conditions(rates):
        return {'t_at_least_0.8': rates['T'] >= PRIMARY_T_MIN,
                't_minus_p_at_least_0.5': rates['T'] - rates['P'] >= PRIMARY_DIFF_MIN,
                't_minus_c_at_least_0.5': rates['T'] - rates['C'] >= PRIMARY_DIFF_MIN}
    p_value = fisher_greater(sends['T'], n['T'], sends['P'], n['P'])
    checks = {'observed': conditions(observed), 'missing_counted_against_v5': conditions(worst),
              'fisher_below_0.01': p_value < PRIMARY_ALPHA}
    passed = (all(checks['observed'].values()) and all(checks['missing_counted_against_v5'].values())
              and checks['fisher_below_0.01'])
    return {**out, 'conditions': checks,
            'conditions_note': ("'observed' (received responses only) is reported and implied by "
                                "'missing_counted_against_v5'; the Fisher condition is implied too"),
            't_minus_p': float(observed['T'] - observed['P']),
            't_minus_c': float(observed['T'] - observed['C']),
            'fisher_one_sided_p_unpaired_implied': p_value, 'status': 'PASS' if passed else 'FAIL'}


def _count(primary, arm):
    text = f"{primary['sends'][arm]} of {primary['received'][arm]}"
    missing = primary['missing'][arm]
    return text + (f' received ({missing} missing, counted against v5)' if missing else '')


def primary_fail_statement(primary):
    """Which condition failed, in order, judged on the set with missing responses counted against
    v5 (which implies the received-only set). Each route has its own meaning; all keep v5 out."""
    worst = primary['conditions']['missing_counted_against_v5']
    fatal = 'the untriggered channel stays fatal'
    if not worst['t_at_least_0.8']:
        return f'the lapse is not fixed by stating the missing state; {fatal}'
    parts = []
    if not worst['t_minus_p_at_least_0.5']:
        parts.append(f"a meaningless same-shape field recovered the Actor nearly as often (P sent on "
                     f"{_count(primary, 'P')}, T on {_count(primary, 'T')}); the recovery is not shown to come "
                     'from stating the missing state')
    if not worst['t_minus_c_at_least_0.5']:
        parts.append(f"a plain re-send recovered the Actor on {_count(primary, 'C')}; the lapse does not reproduce "
                     'reliably on replay, so this probe cannot attribute a recovery to v5')
    if not parts:
        parts.append('the one-sided Fisher condition failed')
    return '; '.join(parts) + f'; {fatal}'


def r3_readout(rows):
    """T decides. A move into send_confirmation is the task's correct next step in window, so it is
    listed, never counted as a mismatch; a move between services (orders -> notifications) is."""
    prompts, planned = _by_prompt(rows)
    out = {'planned_prompts': planned, 'decides': 'T'}
    for arm in ('T', 'P'):
        compared = exact = into_send = mismatches = reports = 0
        transitions = Counter()
        for arms in prompts.values():
            result, control = arms.get(arm), arms.get('C')
            if _received(result) and result['class'] == 'report':
                reports += 1
            if not (_received(control) and _received(result)):
                continue
            compared += 1
            transitions[f'{_label(control)}->{_label(result)}'] += 1
            if action_key(result) == action_key(control):
                exact += 1
            elif result['class'] == 'send_confirmation':
                into_send += 1
            else:
                mismatches += 1
        agreements = compared - mismatches
        complete = _complete(compared, planned)
        passes = bool(complete and compared and Fraction(agreements, compared) >= R3_MATCH_MIN and reports == 0)
        out[arm] = {'compared': compared, 'exact_matches': exact, 'into_send': into_send, 'mismatches': mismatches,
                    'agreements': agreements, 'agreement_rate': _ratio(agreements, compared),
                    'agreement_rate_wilson95': wilson(agreements, compared), 'reports': reports,
                    'complete': complete, 'passes': passes, 'decides': arm == 'T',
                    'transitions_from_C': dict(sorted(transitions.items()))}
    out['status'] = 'INCOMPLETE' if not out['T']['complete'] else 'PASS' if out['T']['passes'] else 'FAIL'
    return out


def allowed_words(historical_word):
    """The historical word, plus its declared partner when it is one of the interchangeable pair."""
    return (set(R4_INTERCHANGEABLE) | {historical_word}) if historical_word in R4_INTERCHANGEABLE else {historical_word}


def _report_field_changes(pairs):
    tally = Counter()
    for before, after in pairs:
        tally['compared'] += 1
        for key in REPORT_FIELDS:
            tally[key] += (before or {}).get(key) != (after or {}).get(key)
    return {key: tally[key] for key in ('compared',) + REPORT_FIELDS}


def r4_readout(rows):
    """T decides, against the historical word, not against C (C is a noisy draw itself)."""
    planned = Counter(request['arm'] for request, _ in rows)
    planned_final = Counter(request['arm'] for request, _ in rows if request['final_report_required'])
    by_prompt = defaultdict(dict)
    for request, result in rows:
        by_prompt[request['prompt_id']][request['arm']] = (request, result)
    out = {'decides': 'T', 'planned': dict(sorted(planned.items())),
           'planned_on_report_required_turns': dict(sorted(planned_final.items())),
           'interchangeable_words': sorted(R4_INTERCHANGEABLE)}
    for arm in ARMS:
        received = received_final = allowed_used = no_valid_report = 0
        words, changes, acted, failures = Counter(), Counter(), Counter(), []
        voluntary = Counter()
        voluntary_changes = Counter()
        for prompt_id in sorted(by_prompt):
            if arm not in by_prompt[prompt_id]:
                continue
            request, result = by_prompt[prompt_id][arm]
            if not _received(result):
                continue
            received += 1
            received_final += bool(request['final_report_required'])
            is_voluntary = not request['final_report_required']
            voluntary['received'] += is_voluntary
            historical = request['historical']['notification_outcome']
            if result['class'] == 'report':
                word = result['notification_outcome']
                words[str(word)] += 1
                voluntary['reports'] += is_voluntary
                if word != historical:
                    changes[f'{historical}->{word}'] += 1
                    if is_voluntary:
                        voluntary_changes[f'{historical}->{word}'] += 1
                    if word in allowed_words(historical):
                        allowed_used += 1
                    else:
                        voluntary['word_outside_allowed'] += is_voluntary
                        failures.append({'prompt_id': prompt_id, 'reason': 'word_outside_allowed',
                                         'historical': historical, 'word': word})
            elif request['final_report_required']:
                failures.append({'prompt_id': prompt_id, 'reason': 'no_report_on_report_required_turn',
                                 'class': _label(result)})
            elif result['class'] in ('send_confirmation', 'get_operation_status'):
                acted[_label(result)] += 1
            else:
                no_valid_report += 1
        reports = sum(words.values())
        word_failures = sum(f['reason'] == 'word_outside_allowed' for f in failures)
        out[arm] = {'received': received, 'received_on_report_required_turns': received_final,
                    'reports': reports, 'words': dict(sorted(words.items())),
                    'changes_from_historical': dict(sorted(changes.items())),
                    'allowed_pair_used': allowed_used, 'failures': len(failures),
                    'failure_examples': failures[:20],
                    'acted_instead_of_reporting_on_voluntary_turns': dict(sorted(acted.items())),
                    'no_valid_report_on_voluntary_turns': no_valid_report,
                    'word_outside_allowed_rate': _ratio(word_failures, reports),
                    'word_outside_allowed_wilson95': wilson(word_failures, reports),
                    'voluntary_prompts_only': {
                        'received': voluntary['received'], 'reports': voluntary['reports'],
                        'word_outside_allowed': voluntary['word_outside_allowed'],
                        'word_outside_allowed_rate': _ratio(voluntary['word_outside_allowed'], voluntary['reports']),
                        'word_outside_allowed_wilson95': wilson(voluntary['word_outside_allowed'], voluntary['reports']),
                        'changes_from_historical': dict(sorted(voluntary_changes.items()))},
                    'decides': arm == 'T'}
    out['C']['note'] = ("declared R4 noise reference: C's word against the historical word; the top-level figures are "
                        f"pooled over C's {planned['C']} report prompts, {planned_final['C']} of them strict-schema "
                        "report-required turns. The matched reference for T's voluntary prompts is "
                        "'voluntary_prompts_only'")

    def report(arm, prompt_id):
        pair = by_prompt[prompt_id].get(arm)
        return pair[1] if pair and _received(pair[1]) and pair[1]['class'] == 'report' else None
    fields = {}
    for arm in ('T', 'P'):
        fields[f'{arm}_vs_C'] = _report_field_changes(
            (report('C', p).get('report'), report(arm, p).get('report')) for p in sorted(by_prompt)
            if report('C', p) and report(arm, p))
    for arm in ARMS:
        fields[f'{arm}_vs_historical'] = _report_field_changes(
            (by_prompt[p][arm][0]['historical'].get('report_fields'), report(arm, p).get('report'))
            for p in sorted(by_prompt) if report(arm, p))
    out['other_report_fields_descriptive'] = fields
    complete = (_complete(out['T']['received'], planned['T']) and _complete(out['C']['received'], planned['C'])
                and (planned_final['T'] == 0
                     or _complete(out['T']['received_on_report_required_turns'], planned_final['T'])))
    out['complete'] = complete
    out['status'] = 'INCOMPLETE' if not complete else 'PASS' if out['T']['failures'] == 0 else 'FAIL'
    # A T tool action on a voluntary report turn is not judged, so R4 judges only the T words that
    # arrived: k shrinks exactly when v5 works. Its power against a wording harm w is 1-(1-w)^k.
    out['T_words_judged'] = out['T']['reports']
    out['status_note'] = f"R4 {out['status']} on {out['T']['reports']} of {planned['T']} T reports"
    return out


def turn3_readout(rows):
    planned, got = _by_arm(rows)
    out = {'note': 'descriptive only; never a decision input', 'planned': dict(planned)}
    sends = {}
    for arm in ARMS:
        results = got[arm]
        flips = sum((r['class'], r.get('detail')) != ('get_operation_status', 'notifications') for r in results)
        sends[arm] = sum(r['class'] == 'send_confirmation' for r in results)
        out[arm] = {'received': len(results), 'sends': sends[arm],
                    'classes': dict(Counter(f"{r['class']}:{r.get('detail')}" for r in results)),
                    'flips_from_historical_lapse': flips, 'flip_rate': _ratio(flips, len(results)),
                    'send_rate': _ratio(sends[arm], len(results)),
                    'send_rate_wilson95': wilson(sends[arm], len(results))}
    if got['T'] and got['P']:
        out['t_minus_p_send'] = out['T']['send_rate'] - out['P']['send_rate']
        out['fisher_one_sided_p_descriptive'] = fisher_greater(sends['T'], len(got['T']), sends['P'], len(got['P']))
    return out


def determinism_readout(rows):
    contexts = defaultdict(list)
    for request, result in rows:
        contexts[request['prompt_id']].append((request, result))
    pairs = identical_pairs = all_identical = with_repeats = 0
    matches_historical = repeats_total = 0
    changes = report_repeats = non_reports = 0
    word_pairs = word_pairs_differ = 0
    pending = {'PENDING': [0, 0], 'UNKNOWN': [0, 0]}
    modal = {'PENDING': Counter(), 'UNKNOWN': Counter()}
    for prompt_id, items in contexts.items():
        request = items[0][0]
        group, historical_word = request['group'], request['historical']['notification_outcome']
        received = [r for _, r in items if _received(r)]
        raws = [r.get('raw') for r in received]
        repeats_total += len(received)
        matches_historical += sum(bool(r.get('matches_historical_raw')) for r in received)
        if len(raws) >= 2:
            with_repeats += 1
            all_identical += len(set(raws)) == 1
            for i in range(len(raws)):
                for j in range(i + 1, len(raws)):
                    pairs += 1
                    identical_pairs += raws[i] == raws[j]
        words = [r['notification_outcome'] for r in received if r['class'] == 'report']
        for i in range(len(words)):
            for j in range(i + 1, len(words)):
                word_pairs += 1
                word_pairs_differ += words[i] != words[j]
        non_reports += len(received) - len(words)
        report_repeats += len(words)
        changes += sum(word != historical_word for word in words)
        if group in pending:
            pending[group][0] += sum(word == 'PENDING' for word in words)
            pending[group][1] += len(words)
            if words:
                modal[group][Counter(words).most_common(1)[0][0]] += 1
    return {
        'contexts': len(contexts), 'contexts_with_two_or_more_repeats': with_repeats,
        'contexts_all_repeats_byte_identical': all_identical,
        'repeat_pairs': pairs, 'repeat_pairs_byte_identical': identical_pairs,
        'byte_identical_pair_share': _ratio(identical_pairs, pairs),
        'repeats': repeats_total, 'repeats_byte_identical_to_historical': matches_historical,
        'historical_match_share': _ratio(matches_historical, repeats_total),
        'report_repeats': report_repeats, 'non_report_repeats': non_reports,
        'within_context_word_disagreement': {
            'report_pairs': word_pairs, 'pairs_with_different_word': word_pairs_differ,
            'rate': _ratio(word_pairs_differ, word_pairs), 'wilson95': wilson(word_pairs_differ, word_pairs),
            'note': 'repeats of one context sent in the same session; the within-session word noise'},
        'change_from_historical_word': {
            'changes': changes, 'rate_per_call': _ratio(changes, report_repeats),
            'wilson95': wilson(changes, report_repeats),
            'note': 'against the stored answer from 2026-09-21..23: confounded with any provider change since'},
        'pending_probability': {group: {'pending': k, 'reports': n, 'rate': _ratio(k, n), 'wilson95': wilson(k, n)}
                                for group, (k, n) in pending.items()},
        'modal_word_by_group': {group: dict(counter) for group, counter in modal.items()},
        'note': 'repeats of one context are not independent; per-call and per-pair intervals understate uncertainty',
    }


def c_arm_vs_history(pairs):
    out = {}
    for population in POPULATION_ORDER:
        results = [r for q, r in pairs if q['population'] == population and q['arm'] == 'C' and _received(r)]
        same = sum(bool(r.get('matches_historical_raw')) for r in results)
        out[population] = {'received': len(results), 'byte_identical_to_historical': same,
                           'share': _ratio(same, len(results))}
    return out


def provider_readout(pairs):
    received = [r for _, r in pairs if _received(r)]
    # Only an ok response carries the requested model (RuntimeGeneration.model_id); an empty
    # response does not, so it is not compared.
    compared = [r for r in received if r.get('requested_model') is not None and r.get('served_model') is not None]
    return {'served_model': dict(Counter(str(r.get('served_model')) for r in received)),
            'system_fingerprint': dict(Counter(str(r.get('system_fingerprint')) for r in received)),
            'served_compared_with_requested': len(compared),
            'served_differs_from_requested': sum(r['served_model'] != r['requested_model'] for r in compared),
            'note': ('recorded from each response, never enforced; the served-model string format is unverified; '
                     'compared only on responses that carry the requested model')}


def compute_readouts(requests, results, *, partial_lines_skipped=0):
    """Every declared read-out from the plan's requests and the saved responses."""
    by_id = {r['request_id']: r for r in results}
    pairs = [(q, by_id.get(q['request_id'])) for q in requests]
    grouped = defaultdict(list)
    for request, result in pairs:
        grouped[request['population']].append((request, result))
    primary = primary_readout(grouped['turn4'])
    r3 = r3_readout(grouped['nonlapse'])
    r4 = r4_readout(grouped['report'])
    statuses = {'primary': primary['status'], 'R3': r3['status'], 'R4': r4['status']}
    eligible = all(status == 'PASS' for status in statuses.values())
    if eligible:
        statement = (f"v5 passed the primary, R3 and R4 ({r4['status_note']}); it may enter the Phase 22 change set "
                     'and the Phase 25 A/B')
        if r4['T_words_judged'] < r4['planned'].get('T', 0):
            statement += ("; T acted instead of reporting on the rest, so R4's power against a wording change is "
                          "1-(1-w)^k at this k, and Phase 25's in-window wording guard is the main wording check")
    elif primary['status'] == 'FAIL':
        statement = primary_fail_statement(primary)
    else:
        statement = 'v5 is not adopted: ' + ', '.join(r4['status_note'] if k == 'R4' else f'{k} {v}'
                                                      for k, v in statuses.items() if v != 'PASS')
    return {'schema_version': READOUT_SCHEMA, 'scoring': 'NON_SCORING_NEVER_FED_BACK',
            'requests_planned': len(requests),
            'requests_received': sum(_received(r) for _, r in pairs),
            'partial_lines_skipped': partial_lines_skipped,
            'primary': primary, 'R3': r3, 'R4': r4, 'turn3': turn3_readout(grouped['turn3']),
            'determinism': determinism_readout(grouped['determinism']),
            'c_arm_vs_history': c_arm_vs_history(pairs),
            'provider': provider_readout(pairs),
            'statuses': statuses,
            'decision': 'V5_ELIGIBLE_FOR_PHASE_22' if eligible else 'V5_NOT_ADOPTED',
            'statement': statement}


# ---------------------------------------------------------------- command line

def dry_summary(plan):
    return {'dry_run': True, 'provider_calls': 0, 'plan_hash': plan_hash(plan),
            'harness_sha256': plan['harness_sha256'], 'configuration_hash': plan['configuration_hash'],
            'actor_model': plan['actor_model'], 'temperature': plan['actor_model_settings'].get('temperature'),
            'store_cutoff': plan['store_cutoff'], 'verification': plan['verification'],
            'precheck': plan['precheck'], 'populations': {k: v for k, v in plan['populations'].items()
                                                          if k != 'lapse_episodes'},
            'sampling': {k: plan['sampling'][k] for k in ('seed', 'nonlapse_pool', 'determinism_match_levels')},
            'counts': plan['counts'], 'cost': plan['cost'],
            'max_input_token_bound': plan['max_input_token_bound']}


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', default=str(STORE), help='read-only lab store')
    parser.add_argument('--settings', default=DECLARED_SETTINGS, help='the declared non-secret settings file')
    parser.add_argument('--spend-cap', type=float, default=HARD_SPEND_CAP)
    parser.add_argument('--write-plan', help='new directory under artifacts/phase21-<date>/ for the dry plan')
    parser.add_argument('--readouts', help='recompute read-outs from a saved run directory ($0); refuses unless '
                        "this harness and the saved plan are the run's own")
    parser.add_argument('--not-the-runs-harness', action='store_true',
                        help="with --readouts: print a mismatched recomputation, labelled as not the run's")
    parser.add_argument('--finalize-abandoned', metavar='CLAIM',
                        help='close at $0 a claimed run whose process died before its manifest was final')
    parser.add_argument('--out', help='new directory under artifacts/phase21-<date>/ for a live run')
    parser.add_argument('--expect-plan-hash')
    parser.add_argument('--expect-harness-sha256')
    parser.add_argument('--expect-protocol-sha256')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    parser.add_argument('--ignore-phase20-manifest', action='append', default=[],
                        help='a crashed Phase 20 manifest (exact path) that is known not to be running')
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
        if args.execute_live and not (args.out and args.confirm_entity and args.expect_plan_hash
                                      and args.expect_harness_sha256 and args.expect_protocol_sha256):
            raise PlanningError('--execute-live needs --out, --confirm-entity, --expect-plan-hash, '
                                '--expect-harness-sha256 and --expect-protocol-sha256')
        if args.execute_live:
            check_output(args.out)
            check_phase20(args)
        if args.write_plan:
            check_output(args.write_plan, live=False)
        if pathlib.Path(args.settings).is_absolute():
            settings_path = pathlib.Path(args.settings)
        else:
            settings_path = ROOT / args.settings
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
