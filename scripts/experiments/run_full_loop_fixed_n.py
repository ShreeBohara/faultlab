"""Phase 23: a FIXED-N full loop. Thirty fresh completion studies, fixed in advance; a
certified study does NOT end the run.

Each attempt is one fresh, unmodified completion study exactly as in Phase 17: 6 controls, up
to two Mechanic proposals, a 3-pair source gate per distinct candidate, and one 42-episode
validation batch for a candidate that qualifies, all through the unchanged execute_slots and
assess_pairs, on the v4 Actor context passed explicitly. "Certified" is Phase 17's rule,
unchanged (run_full_loop.certified; conditions 1-3 of docs/part2/PHASE17_EXPERIMENT.md).
Nothing is called ACCEPTED, no pointer moves, no policy is activated.

Fixed-N design (docs/part2/EXPERIMENT_PROGRAM_PHASES_20-27.md, Phases 22 and 23):
  - N = 30 attempts, fixed in advance. Every certified attempt is counted; none ends the run.
  - The run stops only at N, at the $150 spend guard (reported "truncated at n=j"), after 5
    consecutive infrastructure failures, or on Ctrl-C / SIGTERM / SIGHUP (Detached).
  - Primary: k certified of n attempts with a Wilson interval. Also computed from the attempt
    rows by rules declared here: the stage funnel (step present vs step that fires, source
    gate, validation acceptance on clean vs dirty batches), distinct policy hashes, the
    untriggered rate and the cost per certification.
  - Routing (declared): the first certified policy hash by attempt order that is not
    dd62c857... (its Phase 18 verdict is final) is the only policy Phase 24 may check.
    Re-draws of dd62c857 are counted and never routed.

What is reused unchanged: every guard, HTTP helper, read-out rule and store reader of the
reviewed Phase 17 runner (run_full_loop.py, imported, sha pinned below, never edited). The
main loop, recover() and the abort handling are copied from run_full_loop.main, because they
are nested inside it; only the stop rule, the pins, the output prefix, the per-attempt funnel,
the pending-post-check recovery and the fixed-N reconcile() differ, plus four Phase 22 review
round 1 fixes: a row interrupted before its campaign was recorded is labelled (never left
without an outcome), a runner-side row is not an infrastructure death, an abort's reason is
saved before any wait, and the run record is claimed with an exclusive create before the slow
ingestion check.

Runbook checks built in: the Weave ingestion health check before each live session (refuses
if unhealthy) and check_clock_drift --worlds after each session (recorded, never a re-run).

Dry by default. `--execute-live` plus a matching `--confirm-entity` is required to run, and a
live run refuses while any pin below still holds its placeholder.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_full_loop as base  # noqa: E402  the reviewed Phase 17 runner; nothing in it is modified
# Imported now, not after the run, so the drift checker that runs is the file whose sha was checked.
import check_clock_drift  # noqa: E402  (scripts/experiments/check_clock_drift.py, stdlib only)

ROOT = base.ROOT
SCHEMA = 'faultlab-full-loop-fixed-n/v1'
PHASE_PREFIX = 'phase23-'
MANIFEST_NAME = 'full-loop-manifest.json'
PROTOCOL = 'docs/part2/PHASE23_EXPERIMENT.md'
# The Mechanic's completion-study brief: completion_study._execute calls
# Mechanic.propose_completion, which sends prompts/completion.md as the system message.
MECHANIC_BRIEF = 'backend/app/agents/prompts/completion.md'
DEFAULT_SETTINGS = 'artifacts/phase16-2026-09-22/settings-phase17.json'

# ---------------------------------------------------------------- the declared design
N_ATTEMPTS = 30
SPEND_CAP = 150.0
HEADROOM = 11.0          # worst case of one study is ~$10.23 (Phase 17); the last start is at ~$139
BREAKER = 5              # consecutive infrastructure failures
FINAL_STOPS = ('fixed_n', 'spend_guard')
STOP_RULE = (f'Stop only at N = {N_ATTEMPTS} attempts, at the ${SPEND_CAP:.0f} spend guard (no study starts once '
             f'charged + ${HEADROOM:.0f} > ${SPEND_CAP:.0f}), after {BREAKER} consecutive infrastructure failures, '
             f'or on Ctrl-C / SIGTERM / SIGHUP. A certified study never stops the run.')
PHASE17_POLICY_HASH = 'dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521'
EXCLUDED_FROM_ROUTING = {
    PHASE17_POLICY_HASH: 'Phase 18 held-out verdict HARM is final (heldout_check.py); a re-check would be '
                         'repeat-until-lucky. Re-draws are counted, never routed.'}
ROUTING_RULE = ('The first attempt, by attempt order, whose row is certified and whose certified policy hash '
                'is not excluded from routing; its policy hash is the only one Phase 24 may check.')
# Phase 17 stopped at its first success (attempt 9 of 9): the pooled figure is a secondary only.
PHASE17_ATTEMPTS, PHASE17_CERTIFIED = 9, 1
SCORER_HASH = '19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e'
SCORER_KEY = 'scorer_hash'
# Rows the runner itself ended at $0 before any study existed: a stop (Ctrl-C, SIGTERM, SIGHUP)
# while POST /api/campaigns was in flight, or a campaign the runner refused. Each keeps its
# attempt number and stays in the denominator (PHASE23_EXPERIMENT.md section 4.1), but none is
# an infrastructure failure of the loop: the breaker and the funnel's death count skip them.
INTERRUPTED_BEFORE_CREATE = 'interrupted before its campaign was recorded (no study)'
NO_CONFIGURATION_HASH = 'no configuration_hash (no study started)'
CONFIGURATION_MISMATCH = 'configuration_hash mismatch (no study started)'
STORE_OR_ARIA_REFUSED = 'store or Aria check failed (no study started)'
RUNNER_SIDE_ERRORS = (INTERRUPTED_BEFORE_CREATE, NO_CONFIGURATION_HASH, CONFIGURATION_MISMATCH, STORE_OR_ARIA_REFUSED)

# ---------------------------------------------------------------- pins
# Filled ONCE, at the Phase 22 freeze, after the last code edit and both review rounds. A live
# run refuses while any holds the placeholder. They are never regenerated to get past a mismatch:
# a mismatch means the reviewed state changed, and the freeze and the review are redone.
PLACEHOLDER = 'UNFILLED-AT-PHASE22-FREEZE'
DECLARED_FREEZE_SHA256 = '8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1'               # the Phase 22 gate-freeze JSON file
DECLARED_CONFIGURATION_HASH = '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba'          # expected_configuration.py on the frozen code + Phase 17 settings
DECLARED_PROTOCOL_SHA256 = 'b5bd37267f132ad70fd7e9a7ee51630743d4d3f0ea3201b6b18f37d6a33614a5'             # docs/part2/PHASE23_EXPERIMENT.md
DECLARED_GATE_FREEZE_SCRIPT_SHA256 = '5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190'   # scripts/experiments/gate_freeze.py
DECLARED_DRIFT_CHECKER_SHA256 = 'fa25ab9d38ed1287ff530751a4157eedffb8a0692e756bce0edef64133ae956a'        # scripts/experiments/check_clock_drift.py
DECLARED_INGESTION_CHECK_SHA256 = 'edde0190836898e2a301aadbb16906ded3ae20a5f51cd51bd4c4ee7266313c02'      # scripts/experiments/check_ingestion_health.py
# Known now and declared UNCHANGED from Phase 17, so they are pinned now: an edit to any of
# these files then fails the run instead of being re-pinned at the freeze.
DECLARED_SETTINGS_SHA256 = '1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d'  # settings-phase17.json
DECLARED_MECHANIC_BRIEF_SHA256 = 'e3b9362f281e1616fea7013fb3d9b7cf85432884f726a95cde39e4a9dadd1673'  # = Phase 16/17 freeze
DECLARED_BASE_RUNNER_SHA256 = '07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342'  # run_full_loop.py
# This runner's own sha cannot be a constant in this file, and the protocol cannot quote it
# while this file pins the protocol's sha (each would change the other). It is bound by the
# review record instead (--review-record, written by the operator when review closes), which
# must repeat this runner's sha, the protocol sha, the freeze sha and the configuration hash.
PINS = ('DECLARED_FREEZE_SHA256', 'DECLARED_CONFIGURATION_HASH', 'DECLARED_PROTOCOL_SHA256',
        'DECLARED_GATE_FREEZE_SCRIPT_SHA256', 'DECLARED_DRIFT_CHECKER_SHA256', 'DECLARED_INGESTION_CHECK_SHA256',
        'DECLARED_SETTINGS_SHA256', 'DECLARED_MECHANIC_BRIEF_SHA256', 'DECLARED_BASE_RUNNER_SHA256')

Detached = base.Detached
PhaseAbort = base.PhaseAbort


class BreakerTripped(base.PhaseAbort):
    """BREAKER consecutive infrastructure failures: the run stops; continuing needs approval."""


def is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def unfilled_pins():
    return [name for name in PINS if not is_sha256(globals()[name])]


def pin_files(args=None):
    """The file each file-level pin describes (the configuration hash has no file)."""
    return {'DECLARED_FREEZE_SHA256': (ROOT / args.expect_freeze) if args is not None and args.expect_freeze else None,
            'DECLARED_PROTOCOL_SHA256': ROOT / PROTOCOL,
            'DECLARED_GATE_FREEZE_SCRIPT_SHA256': HERE / 'gate_freeze.py',
            'DECLARED_DRIFT_CHECKER_SHA256': HERE / 'check_clock_drift.py',
            'DECLARED_INGESTION_CHECK_SHA256': HERE / 'check_ingestion_health.py',
            'DECLARED_SETTINGS_SHA256': ROOT / ((args.settings if args is not None and args.settings else None)
                                                or DEFAULT_SETTINGS),
            'DECLARED_MECHANIC_BRIEF_SHA256': ROOT / MECHANIC_BRIEF,
            'DECLARED_BASE_RUNNER_SHA256': HERE / 'run_full_loop.py'}


def pin_status(args=None):
    """Read-only: every pin, its declared value and whether the file on disk matches it."""
    files = pin_files(args)
    rows = []
    for name in PINS:
        declared = globals()[name]
        path = files.get(name)
        current = base.sha256_file(path) if path is not None and pathlib.Path(path).is_file() else None
        if not is_sha256(declared):
            state = 'UNFILLED'
        elif path is None:
            state = 'pinned (checked against the backend at the first campaign)' if name == 'DECLARED_CONFIGURATION_HASH' \
                else 'pinned (no file given)'
        elif current is None:
            state = 'FILE MISSING'
        else:
            state = 'MATCH' if current == declared else 'DIFFERS'
        rows.append({'pin': name, 'declared': declared, 'file': str(path) if path else None, 'current': current,
                     'state': state})
    return rows


# ---------------------------------------------------------------- read-out rules (pure)

def wilson(k, n, z=1.959964):
    if not n:
        return (None, None)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def runner_side(row):
    """A row the runner ended itself at $0, before any study existed (see RUNNER_SIDE_ERRORS)."""
    return row.get('error') in RUNNER_SIDE_ERRORS


def infrastructure_death(row):
    """run_full_loop.infrastructure_death, except a runner-side row, which is not a failure of the loop."""
    return not runner_side(row) and base.infrastructure_death(row)


def label_phantoms(rows):
    """A row appended before its campaign was recorded and never given an outcome: the runner
    stopped while POST /api/campaigns was in flight. It cannot have a study (studies start only
    on a recorded campaign), so it is labelled, never recovered. Returns the rows labelled."""
    labelled = []
    for row in rows:
        if (not row.get('campaign_id') and not row.get('study_id') and not row.get('error')
                and row.get('status') is None):
            row['error'] = INTERRUPTED_BEFORE_CREATE
            labelled.append(row['attempt'])
    return labelled


def valid_trial(trial):
    """Mirror of app.lab.reproduction.valid_trial on a stored (JSON) trial row."""
    return (trial.get('lifecycle') == 'COMPLETED' and trial.get('outcome') not in (None, 'LAB_ERROR')
            and (not trial.get('fault_scheduled') or bool(trial.get('fault_triggered'))))


def retry_executed(events):
    """The rule's notifications retry step ran (its only_if held). Pitfall 79: count
    policy_step events with executed true, not the steps a rule lists."""
    return any(e.get('type') == 'policy_step' and (e.get('payload') or {}).get('executed') is True
               and (e.get('payload') or {}).get('op') == 'retry_original_request'
               and (e.get('payload') or {}).get('hook') == 'after_notification_response' for e in events)


def step_fired(events):
    """The step that FIRES (pitfall 77): the policy itself dispatched send_confirmation, i.e. an
    executed notifications retry_original_request actually reached the broker. A retry gated on
    PENDING after a transient failure (which reads UNKNOWN) is present and never fires."""
    return any(e.get('type') == 'tool_dispatched' and (e.get('payload') or {}).get('caller') == 'policy'
               and (e.get('payload') or {}).get('tool') == 'send_confirmation' for e in events)


def episode_events(db, episode_ids):
    """Read-only: the events of these episodes, from the dedicated events table (pitfall 50)."""
    ids = sorted(set(episode_ids))
    if not ids:
        return {}
    connection = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        rows = connection.execute(
            f'select episode_id,payload from events where episode_id in ({",".join("?" * len(ids))}) '
            f'order by episode_id,seq', ids).fetchall()
    finally:
        connection.close()
    found = {}
    for episode_id, payload in rows:
        found.setdefault(episode_id, []).append(json.loads(payload))
    return found


def attempt_funnel(db, study):
    """The per-attempt stage funnel, from the saved study record and the events table only."""
    rows = study.get('trial_rows') or []
    events = episode_events(db, [r['trial']['episode_id'] for r in rows if (r.get('trial') or {}).get('arm') == 'L'])

    def fired(stage):
        trials = [r['trial'] for r in rows if r.get('stage') == stage and r['trial'].get('arm') == 'L']
        return {'L_trials': len(trials),
                'retry_executed_in': sum(1 for t in trials if retry_executed(events.get(t['episode_id'], []))),
                'step_fired_in': sum(1 for t in trials if step_fired(events.get(t['episode_id'], [])))}

    candidates = []
    for slot, candidate in enumerate(study.get('candidates') or [], start=1):
        candidates.append({'slot': slot, 'policy_hash': candidate.get('policy_hash'),
                           'decision': candidate.get('decision'),
                           'step_present': base.contains_step(candidate.get('content')),
                           'source_decision': (candidate.get('source_assessment') or {}).get('decision'),
                           **fired(f'candidate-{slot}')})
    validation = [r['trial'] for r in rows if r.get('stage') == 'validation']
    va = study.get('validation_assessment') or {}
    assessed = bool(va.get('decision'))
    invalid = sum(1 for t in validation if not valid_trial(t))
    # S4 exactly as phase17_readouts.py declared it: every stage, LAB_ERROR episodes excluded.
    counted = [r['trial'] for r in rows
               if r['trial'].get('lifecycle') != 'LAB_ERROR' and r['trial'].get('outcome') != 'LAB_ERROR']
    fault_bearing = [t for t in counted if t.get('fault_scheduled')]
    return {'candidates': candidates,
            'validation': {'trials': len(validation), 'invalid_trials': invalid, 'assessed': assessed,
                           # clean = an assessed batch with zero invalid trials (Phase 15's split)
                           'batch': ('clean' if invalid == 0 else 'dirty') if assessed else None,
                           'decision': va.get('decision'), 'selected_candidate_hash': study.get('selected_candidate_hash'),
                           **fired('validation')},
            'fault_bearing': len(fault_bearing),
            'untriggered': sum(1 for t in fault_bearing if not t.get('fault_triggered'))}


def add_funnel(db, entry, study):
    """Derived and descriptive: a store read that fails never touches the verdict fields."""
    try:
        entry['funnel'] = attempt_funnel(db, study)
        entry.pop('funnel_error', None)
    except Exception as error:  # noqa: BLE001
        entry['funnel_error'] = type(error).__name__


def routing(rows, *, final):
    """The declared routing field: the first new certified policy hash by attempt order."""
    certified = [r for r in rows if r.get('certified')]
    excluded = [{'attempt': r['attempt'], 'policy_hash': r.get('selected_candidate_hash')} for r in certified
                if r.get('selected_candidate_hash') in EXCLUDED_FROM_ROUTING]
    chosen = next((r for r in certified if r.get('selected_candidate_hash') not in EXCLUDED_FROM_ROUTING), None)
    field = {'rule': ROUTING_RULE, 'excluded_from_routing': sorted(EXCLUDED_FROM_ROUTING),
             'excluded_certified_attempts': excluded, 'run_final': bool(final),
             'policy_hash': None, 'attempt': None, 'study_id': None, 'campaign_id': None, 'post_checks': None}
    if chosen is not None:
        field.update(policy_hash=chosen.get('selected_candidate_hash'), attempt=chosen['attempt'],
                     study_id=chosen.get('study_id'), campaign_id=chosen.get('campaign_id'),
                     post_checks=chosen.get('post_checks'))
    # Only a finished run routes anything: a run that is still open could, in principle, be
    # resumed, but its first certified attempt can never change, because attempts only append.
    field['routable'] = bool(final and chosen is not None and str(chosen.get('post_checks') or '').startswith('passed'))
    return field


def hash_accounting(rows):
    """Distinct policies, not proposals (pitfall 29); same-policy re-draws across studies are
    part of the loop and counted, never excluded."""
    draws = [{'attempt': r['attempt'], 'slot': c.get('slot'), 'policy_hash': c.get('policy_hash'),
              'decision': c.get('decision'), 'source_decision': c.get('source_decision'),
              'step_present': bool(c.get('contains_step'))}
             for r in rows for c in r.get('candidates') or [] if c.get('policy_hash')]
    by_hash = {}
    for draw in draws:
        by_hash.setdefault(draw['policy_hash'], []).append(draw)
    certified = [{'attempt': r['attempt'], 'policy_hash': r.get('selected_candidate_hash')}
                 for r in rows if r.get('certified')]
    return {'draws': len(draws),
            'distinct_policies': len(by_hash),
            'distinct_first_proposals': len({d['policy_hash'] for d in draws if d['slot'] == 1}),
            'distinct_step_policies': len({h for h, ds in by_hash.items() if any(d['step_present'] for d in ds)}),
            'within_study_duplicates': sum(1 for d in draws if d['decision'] == 'DUPLICATE'),
            'redrawn_across_attempts': {h: sorted({d['attempt'] for d in ds}) for h, ds in sorted(by_hash.items())
                                        if len({d['attempt'] for d in ds}) > 1},
            'attempts_per_policy': {h: sorted({d['attempt'] for d in ds}) for h, ds in sorted(by_hash.items())},
            'certified_in_order': certified,
            'distinct_certified_policies': len({c['policy_hash'] for c in certified}),
            'phase17_policy': {'policy_hash': PHASE17_POLICY_HASH, 'draws': by_hash.get(PHASE17_POLICY_HASH, []),
                               'certified_attempts': [c['attempt'] for c in certified
                                                      if c['policy_hash'] == PHASE17_POLICY_HASH],
                               'routed': False}}


def stage_funnel(rows):
    funnels = [r.get('funnel') for r in rows if r.get('funnel')]
    candidates = [c for f in funnels for c in f.get('candidates') or []]
    step = [c for c in candidates if c.get('step_present')]
    tested = [c for c in step if c.get('source_decision')]
    validation = [f.get('validation') or {} for f in funnels]
    assessed = [v for v in validation if v.get('assessed')]
    clean = [v for v in assessed if v.get('batch') == 'clean']
    dirty = [v for v in assessed if v.get('batch') == 'dirty']
    return {
        'attempts': len(rows),
        'studies_started': sum(1 for r in rows if r.get('study_id')),
        # Every attempt is in the denominator (section 4.1); these ran no study, by reason.
        'attempts_without_study': {reason: sum(1 for r in rows if not r.get('study_id')
                                               and (r.get('error') or 'no outcome recorded') == reason)
                                   for reason in sorted({r.get('error') or 'no outcome recorded'
                                                         for r in rows if not r.get('study_id')})},
        'runner_side_no_study': sum(1 for r in rows if runner_side(r)),
        'infrastructure_deaths': sum(1 for r in rows if infrastructure_death(r)),
        'controls_stops': sum(1 for r in rows if r.get('stage') == 'controls' and r.get('decision') == 'NO_CHANGE'),
        # Phase 9 rule: a refusal or an invalid first proposal is a draw WITHOUT the step.
        'first_proposals_drawn': sum(1 for r in rows if r.get('first_proposal_drawn')),
        'first_proposals_with_step': sum(1 for r in rows if r.get('first_proposal_contains_step')),
        'candidates_with_policy': sum(1 for c in candidates if c.get('policy_hash')),
        'step_present': len(step),
        'step_tested_at_source': len(tested),
        'step_fired_at_source': sum(1 for c in tested if c.get('step_fired_in')),
        'step_present_never_fired_at_source': sum(1 for c in tested if c.get('L_trials') and not c.get('step_fired_in')),
        'source_complete_pairs_with_step': sum(1 for c in tested if c['source_decision'] in ('SOURCE_QUALIFIED', 'NO_CHANGE')),
        'source_qualified_with_step': sum(1 for c in tested if c['source_decision'] == 'SOURCE_QUALIFIED'),
        'source_qualified_without_step': sum(1 for c in candidates if not c.get('step_present')
                                             and c.get('source_decision') == 'SOURCE_QUALIFIED'),
        'validation_reached': sum(1 for r in rows if r.get('stage') == 'validation'),
        'validation_assessed': len(assessed),
        'validation_clean': len(clean),
        'validation_dirty': len(dirty),
        'accepted_on_clean': sum(1 for v in clean if v.get('decision') == 'OBSERVED_IMPROVEMENT'),
        'accepted_on_dirty': sum(1 for v in dirty if v.get('decision') == 'OBSERVED_IMPROVEMENT'),
        'accepted_on_dirty_note': 'zero by construction: assess_pairs returns INCOMPLETE on any invalid trial (pitfall 72)',
        'validation_step_fired_in': sum(v.get('step_fired_in') or 0 for v in validation),
        'observed_improvement': sum(1 for r in rows if r.get('decision') == 'OBSERVED_IMPROVEMENT'),
        'observed_improvement_without_fresh_gain': sum(1 for r in rows if r.get('decision') == 'OBSERVED_IMPROVEMENT'
                                                       and not r.get('certified')),
        'certified': sum(1 for r in rows if r.get('certified')),
        'funnel_unavailable': sum(1 for r in rows if r.get('study_id') and not r.get('funnel')),
    }


def primary_statement(k, n, stop_reason, abort_detail=None):
    lo, hi = wilson(k, n)
    interval = f'Wilson 95% [{lo:.3f}, {hi:.3f}]' if n else 'no interval'
    core = f'{k} of {n} attempts produced a certified completion repair ({interval})'
    if stop_reason == 'fixed_n':
        return core + '.'
    if stop_reason == 'spend_guard':
        return f'Truncated at n={n} by the ${SPEND_CAP:.0f} spend guard: {core}.'
    if stop_reason == 'breaker':
        return (f'Stopped at n={n} after {BREAKER} consecutive infrastructure failures: {core} up to that point. '
                f'This is not a finding about the loop.')
    if stop_reason == 'aborted':
        return f'Stopped at n={n} because {abort_detail or "of an abort"}: {core} up to that point.'
    return f'Run not finished ({stop_reason}): {core} so far.'


def summarize_fixed_n(rows, *, stop_reason, abort_detail=None, total_charged=None):
    """Every declared read-out, from the attempt rows only."""
    n = len(rows)
    k = sum(1 for r in rows if r.get('certified'))
    pooled_k, pooled_n = k + PHASE17_CERTIFIED, n + PHASE17_ATTEMPTS
    fault_bearing = sum((r.get('funnel') or {}).get('fault_bearing') or 0 for r in rows)
    untriggered = sum((r.get('funnel') or {}).get('untriggered') or 0 for r in rows)
    lo, hi = wilson(k, n)
    return {
        'primary': {'certified': k, 'attempts': n, 'planned': N_ATTEMPTS, 'rate': k / n if n else None,
                    'wilson95': [lo, hi], 'truncated': n < N_ATTEMPTS, 'stop_reason': stop_reason,
                    'statement': primary_statement(k, n, stop_reason, abort_detail)},
        'secondary_pooled_with_phase17': {
            'certified': pooled_k, 'attempts': pooled_n, 'rate': pooled_k / pooled_n,
            'wilson95': list(wilson(pooled_k, pooled_n)),
            'caveat': 'Phase 17 stopped at its first success (attempt 9 of 9), so its share is biased upward; '
                      'quoted only beside the primary, never alone.'},
        'certified_attempts': [r['attempt'] for r in rows if r.get('certified')],
        'funnel': stage_funnel(rows),
        'distinct_hashes': hash_accounting(rows),
        'routing': routing(rows, final=stop_reason in FINAL_STOPS),
        'untriggered': {'fault_bearing_episodes': fault_bearing, 'untriggered': untriggered,
                        'rate': untriggered / fault_bearing if fault_bearing else None,
                        'wilson95': list(wilson(untriggered, fault_bearing)),
                        'definition': 'per fault-bearing episode, all stages, LAB_ERROR excluded (Phase 17 S4)'},
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
    """A post-finish check that failed makes the row not certified (Phase 17 protocol, case (i))."""
    return base.certified(study) and not str(row.get('post_checks') or '').startswith('failed')


def reconcile(manifest, db):
    """Read-only. Attempts are numbered 1..n with n <= the fixed N; every manifest study exists once
    in the store with the recorded outcome, candidates and selection, and is terminal; the routing
    field recomputes; no full study started inside the run window is missing from the manifest.
    Unlike Phase 17 there is no 'ran after the first certified study' rule: the run never stops
    there. Returns (problems, untracked)."""
    studies = base.store_records(db, 'completion_studies')
    rows = manifest['attempts']
    problems = []
    declared_n = (manifest.get('declared') or {}).get('n_attempts', N_ATTEMPTS)
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
        for key in ('status', 'decision', 'selected_candidate_hash'):
            if row.get(key) != study.get(key):
                problems.append(f"attempt {row['attempt']}: {key} manifest={row.get(key)!r} store={study.get(key)!r}")
        stored = [c.get('policy_hash') for c in study.get('candidates') or []]
        if [c.get('policy_hash') for c in row.get('candidates') or []] != stored:
            problems.append(f"attempt {row['attempt']}: candidate policy hashes differ from the store")
        if bool(row.get('certified')) != expected_certified(row, study):
            problems.append(f"attempt {row['attempt']}: certified manifest={bool(row.get('certified'))} "
                            f"store={expected_certified(row, study)}")
    recorded = (manifest.get('summary') or {}).get('routing')
    if recorded is not None:
        again = routing(rows, final=manifest.get('stop_reason') in FINAL_STOPS)
        if (recorded.get('policy_hash'), recorded.get('attempt')) != (again['policy_hash'], again['attempt']):
            problems.append(f"routing field {recorded.get('policy_hash')!r} at attempt {recorded.get('attempt')} "
                            f"does not recompute ({again['policy_hash']!r} at {again['attempt']})")
    started = manifest.get('started_at') or ''
    # A finished run's window closes at its end, so a later phase's studies are not "untracked".
    ended = manifest.get('ended_at') if manifest.get('stop_reason') in FINAL_STOPS else None
    untracked = sorted(sid for sid, s in studies.items()
                       if s.get('replay_of') is None and s.get('created_at', '') >= started
                       and (ended is None or s.get('created_at', '') <= ended) and sid not in listed)
    return problems, untracked


# ---------------------------------------------------------------- runbook checks

def ingestion_health():
    """Runbook, before every live session (pitfall 45): read-only, $0. Exit 0 = healthy enough."""
    try:
        done = subprocess.run([sys.executable, str(HERE / 'check_ingestion_health.py')], capture_output=True,
                              text=True, timeout=300, cwd=str(ROOT))
    except (OSError, subprocess.SubprocessError) as error:
        return {'exit_status': None, 'error': type(error).__name__, 'output': ''}
    return {'exit_status': done.returncode, 'output': done.stdout[-3000:]}


def clock_drift(store, since, worlds_dir=''):
    """Runbook, after every session (Phase 19): drift and masked faults since the run began.
    Recorded as a lab defect if found; it never earns a re-run."""
    result = check_clock_drift.scan(str(store), since=since, worlds=True, worlds_dir=worlds_dir)
    return {'command': (f'scripts/experiments/check_clock_drift.py --store {store} --since {since} --worlds'
                        + (f' --worlds-dir {worlds_dir}' if worlds_dir else '') + ' --require-worlds'),
            'since': since, 'scored_episodes': result['scored'], 'drifted': len(result['drifted']),
            'masked': len(result['masked']), 'missing_worlds': result['missing_worlds'],
            'drifted_episodes': [row[0] for row in result['drifted']],
            'masked_episodes': [row[0] for row in result['masked']],
            'exit_status': check_clock_drift.exit_status(result, require_worlds=True)}


def review_problem(path, runner_sha):
    """The review record binds a live run to what was reviewed: written by the operator when the
    review closes, never by this runner. Every value is compared as a bare 64-hex string."""
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
    for key, value in (('protocol_sha256', DECLARED_PROTOCOL_SHA256), ('runner_sha256', runner_sha),
                       ('gate_freeze_file_sha256', DECLARED_FREEZE_SHA256),
                       ('configuration_hash', DECLARED_CONFIGURATION_HASH)):
        if record.get(key) != value:
            return f'the review record does not carry this {key}'
    return None


def claim(out, manifest_path, manifest):
    """Create the run record exclusively, right after the re-run guard and before anything slow
    (the ingestion check can take minutes), so two launches cannot both pass the guard: the second
    finds the file in the same folder, or the first's record in another phase23 folder."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        with open(manifest_path, 'x', encoding='utf-8') as handle:
            handle.write(json.dumps(manifest, indent=2) + '\n')
    except FileExistsError:
        raise SystemExit(f'{manifest_path} was created by another launch; refusing to overwrite it') from None
    others = [p for p in out.parent.glob(f'{PHASE_PREFIX}*/{MANIFEST_NAME}') if p != manifest_path]
    if others:
        manifest_path.unlink()
        raise SystemExit(f'Another Phase 23 run exists ({others[0]}); continue it with --resume, never in a new folder')


def check_static_pins(args):
    """Every check that needs no backend. Raises SystemExit with the first problem."""
    unfilled = unfilled_pins()
    if unfilled:
        raise SystemExit('Refusing a live run: these pins still hold the placeholder and are filled only at the '
                         'Phase 22 freeze: ' + ', '.join(unfilled))
    for flag in ('settings', 'expect_freeze', 'review_record'):
        if not getattr(args, flag):
            raise SystemExit(f'--{flag.replace("_", "-")} is required for a live run')
    files = pin_files(args)
    for name in ('DECLARED_BASE_RUNNER_SHA256', 'DECLARED_GATE_FREEZE_SCRIPT_SHA256', 'DECLARED_DRIFT_CHECKER_SHA256',
                 'DECLARED_INGESTION_CHECK_SHA256', 'DECLARED_SETTINGS_SHA256', 'DECLARED_MECHANIC_BRIEF_SHA256',
                 'DECLARED_PROTOCOL_SHA256', 'DECLARED_FREEZE_SHA256'):
        path = files[name]
        if not pathlib.Path(path).is_file() or base.sha256_file(path) != globals()[name]:
            raise SystemExit(f'{path} is not the declared file ({name})')
    expected_freeze = json.loads((ROOT / args.expect_freeze).read_text())
    if (expected_freeze.get('functions') or {}).get(base.ASSESS_PAIRS_KEY, {}).get('text_sha256') != base.ASSESS_PAIRS_TEXT_SHA256:
        raise SystemExit('The declared freeze does not contain the unchanged assess_pairs')
    if (expected_freeze.get('fingerprints') or {}).get(SCORER_KEY) != SCORER_HASH:
        raise SystemExit('The declared freeze does not carry the unchanged scorer_hash')
    if (expected_freeze.get('files') or {}).get(MECHANIC_BRIEF) != DECLARED_MECHANIC_BRIEF_SHA256:
        raise SystemExit('The declared freeze does not carry the Phase 17 Mechanic brief (completion.md)')
    problem = review_problem(ROOT / args.review_record, base.sha256_file(__file__))
    if problem:
        raise SystemExit(f'Refusing a live run: {problem}')
    return expected_freeze


# ---------------------------------------------------------------- main loop

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--out', required=True, help='the one artifacts/phase23-* folder for this run')
    parser.add_argument('--store', default=str(ROOT / 'artifacts/lab.sqlite3'))
    parser.add_argument('--worlds-dir', default='', help="for the drift check (default: the store's sibling 'worlds')")
    parser.add_argument('--settings', help='non-secret settings the backend was launched with')
    parser.add_argument('--expect-freeze', help='the Phase 22 gate-freeze JSON the code on disk must equal')
    parser.add_argument('--review-record', help='approved review record repeating this runner\'s sha')
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

    print(f'design     fixed N = {N_ATTEMPTS} attempts, declared in advance; a CERTIFIED study never stops the run')
    print(f'stops      N, the ${SPEND_CAP:.0f} spend guard ("truncated at n=j"), {BREAKER} consecutive '
          f'infrastructure failures, Ctrl-C/SIGTERM/SIGHUP')
    print(f'success    Phase 17 certification, unchanged: OBSERVED_IMPROVEMENT under assess_pairs AND L-B0 >= '
          f'{base.FRESH_GAIN_MIN} on a validation case other than {base.SOURCE_CASE} and {base.CONTROL_CASE}')
    print(f'models     actor {base.EXPECTED_ACTOR}; mechanic {base.EXPECTED_MECHANIC}; brief {MECHANIC_BRIEF}')
    print(f'protocols  actor {base.ACTOR_CONTEXT} (explicit); evidence {base.EVIDENCE_PROTOCOL}')
    print(f'routing    first certified hash by attempt order, excluding {PHASE17_POLICY_HASH[:12]}… (counted, never routed)')
    print(f'spend      guard ${SPEND_CAP:.2f} (conservative bound), headroom ${HEADROOM:.2f} per study')
    print('runbook    before: check_ingestion_health (run by this runner), start-simulator.sh, dashboard closed '
          '(loop_latency p99 < 100 ms); after: check_clock_drift --worlds --since <run start> (run by this runner)')
    print('never      replay, re-validate, resume a study, route dd62c857, or write ACCEPTED')
    if args.plan or not args.execute_live:
        for row in pin_status(args):
            print(f"pin        {row['pin']:<38} {row['state']:<9} declared {str(row['declared'])[:16]}"
                  + (f"  on disk {row['current'][:16]}" if row['current'] else ''))
        print('Dry plan only. Pass --execute-live --confirm-entity ENTITY to run (refused while any pin is UNFILLED).')
        return 0

    check_static_pins(args)
    if out.parent != ROOT / 'artifacts' or not out.name.startswith(PHASE_PREFIX):
        raise SystemExit(f'--out must be artifacts/{PHASE_PREFIX}<date>')
    from app.config import Settings
    settings_path = ROOT / args.settings
    overrides = json.loads(settings_path.read_text())
    os.environ.update({k: str(v) for k, v in overrides.items() if v != ''})
    settings = Settings.from_env()
    if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
        raise SystemExit('--confirm-entity must match WANDB_ENTITY in the settings file')
    if settings.project_path != base.EXPECTED_PROJECT:
        raise SystemExit(f'Settings project is {settings.project_path!r}, phase declares {base.EXPECTED_PROJECT!r}')
    expected_freeze = json.loads((ROOT / args.expect_freeze).read_text())
    current_freeze = base.gate_freeze()
    if current_freeze != expected_freeze:
        differing = sorted(f'{section}:{k}' for section in ('functions', 'files', 'fingerprints')
                           for k in set(current_freeze.get(section, {})) | set(expected_freeze.get(section, {}))
                           if current_freeze.get(section, {}).get(k) != expected_freeze.get(section, {}).get(k))
        raise SystemExit(f'Code on disk differs from the reviewed freeze: {differing[:8] or "schema"}')
    process = base.check_backend_process()
    status = base.check_backend(args.base)
    if status.get('active_campaign_id'):
        raise SystemExit('Another execution is active; refusing to start')

    declared = {'schema_version': SCHEMA, 'phase': 23, 'n_attempts': N_ATTEMPTS, 'spend_cap': SPEND_CAP,
                'headroom': HEADROOM, 'consecutive_infrastructure_abort': BREAKER, 'stop_rule': STOP_RULE,
                'routing_rule': ROUTING_RULE, 'excluded_from_routing': sorted(EXCLUDED_FROM_ROUTING),
                'actor_context_protocol': base.ACTOR_CONTEXT, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
                'expected_models': {'actor': base.EXPECTED_ACTOR, 'mechanic': base.EXPECTED_MECHANIC},
                'project': base.EXPECTED_PROJECT, 'manifest_hash': base.MANIFEST_HASH,
                'assess_pairs_text_sha256': base.ASSESS_PAIRS_TEXT_SHA256, 'scorer_hash': SCORER_HASH,
                'fresh_gain_min': base.FRESH_GAIN_MIN,
                'configuration_hash': DECLARED_CONFIGURATION_HASH,
                'gate_freeze_file_sha256': DECLARED_FREEZE_SHA256,
                'runner_sha256': base.sha256_file(__file__),
                'base_runner_sha256': DECLARED_BASE_RUNNER_SHA256,
                'gate_freeze_script_sha256': DECLARED_GATE_FREEZE_SCRIPT_SHA256,
                'drift_checker_sha256': DECLARED_DRIFT_CHECKER_SHA256,
                'ingestion_check_sha256': DECLARED_INGESTION_CHECK_SHA256,
                'settings_sha256': DECLARED_SETTINGS_SHA256,
                'mechanic_brief': MECHANIC_BRIEF, 'mechanic_brief_sha256': DECLARED_MECHANIC_BRIEF_SHA256,
                'protocol_sha256': DECLARED_PROTOCOL_SHA256,
                'review_record_sha256': base.sha256_file(ROOT / args.review_record)}
    if args.resume:
        if not manifest_path.exists():
            raise SystemExit(f'{manifest_path} does not exist; nothing to resume')
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('declared') != declared:
            raise SystemExit('Resume refused: the declared parameters, pins, code, runner or settings differ from the run on record')
        previous = manifest.get('stop_reason')
        if previous in FINAL_STOPS:
            raise SystemExit(f'Resume refused: the run ended with {previous!r}, which is final')
        # There is no checkpoint: every continuation follows an early stop (abort, breaker, signal,
        # or a session killed hard that left 'running') and needs the user's approval.
        if not args.after_abort:
            raise SystemExit(f'Resume refused: the last session ended with {previous!r}; continuing '
                             f'needs the user\'s approval (--after-abort)')
        if manifest.get('stop_incomplete'):
            if not base.wait_until_idle(args.base, 60, args.poll):
                raise SystemExit('Resume refused: the last stop did not settle and the backend is not idle')
            manifest['stop_incomplete_cleared'] = datetime.now(timezone.utc).isoformat()
            manifest.pop('stop_incomplete')
    else:
        # Re-run guard: one folder, one record, never overwritten, never a second phase23 folder.
        if manifest_path.exists():
            raise SystemExit(f'{manifest_path} exists; refusing to overwrite a retained run record')
        others = [p for p in out.parent.glob(f'{PHASE_PREFIX}*/{MANIFEST_NAME}') if p != manifest_path]
        if others:
            raise SystemExit(f'Another Phase 23 run exists ({others[0]}); continue it with --resume, '
                             f'never in a new folder')
        previous = None
        manifest = {'schema_version': SCHEMA, 'declared': declared, 'models': status.get('models'),
                    'started_at': datetime.now(timezone.utc).isoformat(), 'configuration_hash': None,
                    'campaigns': [], 'attempts': [], 'sessions': [], 'stop_reason': 'starting'}
        claim(out, manifest_path, manifest)
    # Runbook: Weave ingestion must be healthy before any paid work (Phase 12 lost $8.15 without it).
    ingestion = ingestion_health()
    if ingestion.get('exit_status') != 0:
        if not args.resume:
            manifest_path.unlink()          # the claim above; nothing ran, so no record is kept
        raise SystemExit(f"Refusing to start: check_ingestion_health.py exited {ingestion.get('exit_status')!r}; "
                         f"a paid run would very likely produce no scored result")
    out.mkdir(parents=True, exist_ok=True)

    def save():
        temporary = manifest_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n')
        os.replace(temporary, manifest_path)

    campaigns = manifest['campaigns']

    def needs_recovery(entry):
        # Started but never written, a start interrupted before its study id was saved, or (new
        # here) a finished row whose post-finish checks never ran because the runner aborted.
        return entry.get('campaign_id') and (
            (entry.get('status') is None and (entry.get('study_id') or not entry.get('error')))
            or (entry.get('study_id') and entry.get('post_checks') == 'pending'))

    def recover(entry):
        """run_full_loop.main's recover(), plus the funnel: fill a row whose outcome or post-finish
        checks were never written, re-running the checks that do not depend on the process."""
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
        entry.update(base.summarize_study(study), recovered=True)
        add_funnel(args.store, entry, study)
        try:
            base.verify_study_identity(study, when='recovered')
            base.check_evidence_project(args.store, study)
            entry['post_checks'] = 'passed on recovery (backend process pin not re-checkable)'
        except PhaseAbort as error:
            entry['certified'] = False; entry['post_checks'] = f'failed on recovery: {error}'
        save()
        base.record_charge(args.base, entry['campaign_id'], entry, save)
        return True

    if args.resume:
        label_phantoms(manifest['attempts'])
        for entry in manifest['attempts']:
            if needs_recovery(entry) and not recover(entry):
                raise SystemExit(f"Resume refused: attempt {entry['attempt']} has no recorded outcome and its "
                                 f"study is not terminal or not readable; resolve it first")
        # The summary is derived from the rows; a row recovered just now makes the stored one stale.
        manifest['summary'] = summarize_fixed_n(manifest['attempts'], stop_reason=previous,
                                                abort_detail=manifest.get('abort_detail'),
                                                total_charged=manifest.get('total_charged_upper_bound'))
        problems, untracked = reconcile(manifest, args.store)
        if problems or untracked:
            raise SystemExit('Resume refused: manifest and store disagree: ' + '; '.join(problems + untracked)[:500])
    manifest['sessions'].append({'started_at': datetime.now(timezone.utc).isoformat(),
                                 'after_abort': bool(args.after_abort), 'previous_stop': previous,
                                 'previous_abort_detail': manifest.pop('abort_detail', None),
                                 'backend_process': process, 'ingestion_health': ingestion})
    # Marks a session in progress: a session killed hard leaves 'running', which resume
    # treats as an early stop needing approval.
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
        if runner_side(row):
            continue                       # neither a failure of the loop nor a success: skipped
        if not infrastructure_death(row):
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
            raise BreakerTripped(message.format(n=consecutive))

    try:
        while True:
            attempts = len(manifest['attempts'])
            # The ONLY stop rules. 'certified' is deliberately absent: every certified study counts.
            if attempts >= N_ATTEMPTS:
                stop_reason = 'fixed_n'; break
            charged = base.total_spend(args.base, campaigns)
            if charged + HEADROOM > SPEND_CAP:
                stop_reason = 'spend_guard'; break
            base.check_backend(args.base)
            pin_process()
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
                # v4 is passed explicitly: the backend default is still v1 (pitfall 69).
                started = base.api(args.base, 'POST', f"/api/campaigns/{campaign['campaign_id']}/completion-study",
                                   {'execute_live': True, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
                                    'actor_context_protocol': base.ACTOR_CONTEXT})
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
            base.verify_study_identity(started, when='at start')

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
            entry.update(base.summarize_study(study), post_checks='pending'); save()
            if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                raise PhaseAbort('a finished study is still holding the coordinator')
            try:
                study = base.api(args.base, 'GET', f"/api/completion-studies/{started['study_id']}")
            except Exception as error:  # noqa: BLE001
                raise PhaseAbort(f'could not re-read the finished record ({type(error).__name__}); '
                                 f'the outcome seen at completion is kept')
            entry.update(base.summarize_study(study)); save()
            add_funnel(args.store, entry, study); save()
            base.record_charge(args.base, campaign['campaign_id'], entry, save)
            try:
                # Part of condition 1: a row that fails these is never certified.
                base.verify_study_identity(study, when='after finishing')
                base.check_evidence_project(args.store, study)
                pin_process()
            except PhaseAbort as error:
                entry['certified'] = False; entry['post_checks'] = f'failed: {error}'; save()
                raise
            entry['post_checks'] = 'passed'; save()
            if infrastructure_death(entry):
                count_death('{n} consecutive studies died of infrastructure errors; '
                            'check evidence ingestion and provider health')
            else:
                consecutive = 0
            candidates = ', '.join(f"{c['decision']}{'+step' if c['contains_step'] else ''}"
                                   for c in entry['candidates']) or 'none'
            print(f"[attempt {entry['attempt']}/{N_ATTEMPTS}] {entry['status']}/{entry['decision']} at {entry['stage']}"
                  f" | candidates: {candidates} | validation={entry['validation_decision']}"
                  f" | certified={entry['certified']}"
                  + (f" | error={entry['error_type']}" if entry.get('error_type') else ''), flush=True)
    except BreakerTripped as error:
        stop_reason = 'breaker'; manifest['abort_detail'] = str(error)
        print(f'\nSTOPPED (breaker): {error}', flush=True)
    except PhaseAbort as error:
        stop_reason = 'aborted'; manifest['abort_detail'] = str(error)
        print(f'\nABORTED: {error}', flush=True)
    except Detached as signal_error:
        stop_reason = 'aborted'; leave_running = True
        manifest['abort_detail'] = f'signal {signal_error.args[0]}; any running study left running for recover()'
    except KeyboardInterrupt:
        stop_reason = 'aborted'; manifest['abort_detail'] = 'interrupted by operator (Ctrl-C)'
    except Exception as error:  # noqa: BLE001
        stop_reason = 'aborted'; manifest['abort_detail'] = f'{type(error).__name__}: {error}'
        print(f'\nABORTED: {manifest["abort_detail"]}', flush=True)

    if stop_reason in ('aborted', 'breaker'):
        # Recorded at once, before the in-flight stop, the idle wait and recovery below: a second
        # Ctrl-C or signal in that window must not leave 'running' on disk with no reason.
        label_phantoms(manifest['attempts'])
        manifest['stop_reason'] = stop_reason
        save()
    if stop_reason in ('aborted', 'breaker') and campaigns and not leave_running:
        # Aborting the runner does not stop the backend. Stop OUR campaign only while its
        # study is still running; never rewrite a campaign whose study already finished.
        status = base.backend_status(args.base)
        last = manifest['attempts'][-1] if manifest['attempts'] else {}
        in_flight = last.get('status') is None and last.get('campaign_id') == campaigns[-1] and (
            (status or {}).get('active_campaign_id') == campaigns[-1] or status is None)
        if in_flight:
            try:
                base.api(args.base, 'POST', f'/api/campaigns/{campaigns[-1]}/stop', {})
            except Exception as error:  # noqa: BLE001
                print(f'  stop request failed: {type(error).__name__}', flush=True)
            if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                manifest['stop_incomplete'] = True
    if not leave_running:
        for entry in manifest['attempts']:
            if needs_recovery(entry):
                try:
                    recover(entry)
                except Exception:  # noqa: BLE001
                    pass

    manifest['stop_reason'] = stop_reason
    try:
        manifest['total_charged_upper_bound'] = base.total_spend(args.base, campaigns)
    except PhaseAbort as error:
        manifest['total_charged_upper_bound'] = None
        manifest['total_charged_error'] = str(error)
    manifest['summary'] = summarize_fixed_n(manifest['attempts'], stop_reason=stop_reason,
                                            abort_detail=manifest.get('abort_detail'),
                                            total_charged=manifest['total_charged_upper_bound'])
    now = datetime.now(timezone.utc).isoformat()
    manifest['sessions'][-1].update(ended_at=now, stop_reason=stop_reason, abort_detail=manifest.get('abort_detail'))
    manifest['ended_at'] = now
    save()
    if leave_running or manifest.get('stop_incomplete'):
        drift = {'skipped': 'a study was left running or did not stop; run the command after it ends',
                 'command': f"scripts/experiments/check_clock_drift.py --since {manifest['started_at']} --worlds --require-worlds"}
    else:
        try:
            drift = clock_drift(args.store, manifest['started_at'], args.worlds_dir)
        except Exception as error:  # noqa: BLE001
            drift = {'error': type(error).__name__, 'exit_status': None}
    manifest['sessions'][-1]['clock_drift'] = drift
    manifest['clock_drift'] = drift
    save()
    s = manifest['summary']
    total = manifest['total_charged_upper_bound']
    print(f"\n{stop_reason} | {s['primary']['statement']}")
    print(f"funnel: step in {s['funnel']['first_proposals_with_step']} of {s['funnel']['first_proposals_drawn']} first "
          f"proposals | step fired at source {s['funnel']['step_fired_at_source']} of {s['funnel']['step_tested_at_source']} "
          f"| validation assessed {s['funnel']['validation_assessed']} (clean {s['funnel']['validation_clean']}) "
          f"| distinct policies {s['distinct_hashes']['distinct_policies']} | routed {s['routing']['policy_hash']}")
    print(f"clock drift: {drift.get('drifted', drift.get('skipped') or drift.get('error'))} | "
          f"charged ${total if total is not None else float('nan'):.5f}")
    print(f'manifest {manifest_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
