"""Phase 17: run FULL completion studies until one generated policy is certified.

Each attempt is one fresh, unmodified completion study: 6 controls, up to two Mechanic
proposals, a 3-pair source gate per distinct candidate, and - only for a candidate that
qualifies - one 42-episode validation batch, all through the unchanged execute_slots and
assess_pairs. Nothing is replayed, resumed, re-validated or selected after the fact.

Declared success ("certified completion repair", docs/part2/PHASE17_EXPERIMENT.md):
  1. a full study on the declared protocols and case manifest (never a replay);
  2. the study and its validation assessment are OBSERVED_IMPROVEMENT under the unchanged
     assess_pairs;
  3. on at least one validation case OTHER than the source case (notification-2) and the
     healthy control, the candidate completed at least FRESH_GAIN_MIN more trials than the
     baseline (L completed - B0 completed >= 2), so one baseline lapse cannot supply it.
Nothing is called ACCEPTED, no pointer moves, no policy is activated.

Sequential design, declared in advance: stop at the first certified study, at the operator
checkpoint (--stop-after), at the attempt cap, at the spend guard, or on the circuit breaker.
One manifest is the only record of the run: every attempt, every campaign and all spend.

Dry by default. `--execute-live` plus a matching `--confirm-entity` is required to run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

SCHEMA = 'faultlab-full-loop/v2'
EXPECTED_ACTOR = 'deepseek-ai/DeepSeek-V3.1'
EXPECTED_MECHANIC = 'deepseek-ai/DeepSeek-V4-Pro-0813'
EXPECTED_PROJECT = 'shreetbohara-quinstreet/Faultlab'
ACTOR_CONTEXT = 'faultlab-actor-context/v4-indexed-evidence'
EVIDENCE_PROTOCOL = 'faultlab-compact-evidence/v2-task-outcome'
# content_hash(case_manifest()) in every one of the 166 studies before Phase 16.
MANIFEST_HASH = '7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483'
# sha256 of assess_pairs' source text + '\n'; Phase 15 recorded its first 40 hex digits.
ASSESS_PAIRS_TEXT_SHA256 = '783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2'
ASSESS_PAIRS_KEY = 'backend/app/lab/completion_study.py::assess_pairs'
SOURCE_CASE = 'notification-2'
CONTROL_CASE = 'healthy'
FRESH_GAIN_MIN = 2
TASK_TEXT = 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'
ORDER_ID = 'order-1'
TERMINAL = ('COMPLETED', 'INCOMPLETE', 'INTERRUPTED')
TERMINAL_STOPS = ('certified', 'attempt_cap', 'spend_guard')
# Pins declared in docs/part2/PHASE17_EXPERIMENT.md. The runner refuses to start unless the
# typed flags AND the files on disk equal these; changing any of them means editing this
# reviewed file, whose own sha256 the protocol declares and the operator checks.
DECLARED_FREEZE_SHA256 = '96dc32a05d7e715c9752aa7837f1593c967efc02df975a332dea3e5f45faa20f'
DECLARED_CONFIGURATION_HASH = 'c4169ee49deb7fb27ac44205d6e74b4f89912d1b43bf945636745b1872110418'
DECLARED_SETTINGS_SHA256 = '1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d'
DECLARED_GATE_FREEZE_SCRIPT_SHA256 = '5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190'
PROTOCOL = ROOT / 'docs/part2/PHASE17_EXPERIMENT.md'


class Detached(BaseException):
    """SIGTERM/SIGHUP: the runner is going away. Leave the backend study running for recover()."""


class PhaseAbort(RuntimeError):
    """Raised when continuing would spend money blindly or against the wrong backend."""


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- pure read-out rules

def contains_step(content):
    """The working repair: a notifications retry_original_request at after_notification_response
    (the Phase 9 predicate: op AND service)."""
    for rule in (content or {}).get('rules') or []:
        if rule.get('hook') == 'after_notification_response' and any(
                step.get('op') == 'retry_original_request' and step.get('service') == 'notifications'
                for step in rule.get('steps') or []):
            return True
    return False


def case_gains(validation_assessment):
    by_case = (validation_assessment or {}).get('by_case') or {}
    return {case: arms['L']['completed'] - arms['B0']['completed'] for case, arms in by_case.items()}


def fresh_case_gain(validation_assessment):
    """Per case, never summed: two +1s can both be baseline lapses."""
    return any(gain >= FRESH_GAIN_MIN for case, gain in case_gains(validation_assessment).items()
               if case not in (SOURCE_CASE, CONTROL_CASE))


def identity_problems(study):
    problems = []
    if study.get('actor_context_protocol') != ACTOR_CONTEXT:
        problems.append(f'actor_context_protocol={study.get("actor_context_protocol")!r}')
    if study.get('evidence_protocol') != EVIDENCE_PROTOCOL:
        problems.append(f'evidence_protocol={study.get("evidence_protocol")!r}')
    if study.get('replay_of') is not None:
        problems.append(f'replay_of={study.get("replay_of")!r}')
    if study.get('manifest_hash') != MANIFEST_HASH:
        problems.append(f'manifest_hash={study.get("manifest_hash")!r}')
    return problems


def verify_study_identity(study, *, when):
    problems = identity_problems(study)
    if problems:
        raise PhaseAbort(f'{when}: study {study.get("study_id")} is not the declared study: ' + ', '.join(problems))


def certified(study):
    return (not identity_problems(study) and study.get('decision') == 'OBSERVED_IMPROVEMENT'
            and (study.get('validation_assessment') or {}).get('decision') == 'OBSERVED_IMPROVEMENT'
            and fresh_case_gain(study.get('validation_assessment')))


def summarize_study(study):
    """Everything the declared read-outs need, taken only from the saved study record."""
    candidates = []
    for index, attempt in enumerate(study.get('candidates') or []):
        candidates.append({'slot': index + 1, 'decision': attempt.get('decision'),
                           'policy_hash': attempt.get('policy_hash'),
                           'contains_step': contains_step(attempt.get('content')),
                           'source_decision': (attempt.get('source_assessment') or {}).get('decision')})
    va = study.get('validation_assessment') or {}
    return {
        'status': study.get('status'), 'decision': study.get('decision'), 'reason': study.get('reason'),
        'error_type': study.get('error_type'), 'control_operation': study.get('control_operation'),
        'stage': study.get('stage'), 'control_assessment': study.get('control_assessment'),
        # Phase 9 rule: a refusal or an invalid first proposal is a draw WITHOUT the step;
        # only "no proposal requested" is no draw at all.
        'first_proposal_drawn': bool(candidates),
        'first_proposal_contains_step': candidates[0]['contains_step'] if candidates else None,
        'candidates': candidates,
        'selected_candidate_hash': study.get('selected_candidate_hash'),
        'validation_decision': va.get('decision'), 'case_gains': case_gains(va) if va else None,
        'fresh_case_gain': fresh_case_gain(va) if va else None,
        'certified': certified(study),
        'evidence_reads': len(study.get('evidence') or {}),
        'evidence_rereads': [{k: r.get(k) for k in ('stage', 'first_error_code', 'result')}
                             for r in study.get('evidence_rereads') or []],
        'retained_invalid': len(study.get('retained_invalid_slots') or []),
        'trials': len(study.get('trial_rows') or []),
        'actor_context_protocol': study.get('actor_context_protocol'),
        'evidence_protocol': study.get('evidence_protocol'),
        'manifest_hash': study.get('manifest_hash'),
    }


def infrastructure_death(row):
    """Feeds the circuit breaker. A legitimate NO_CHANGE is a result, not a failure:
    in Phase 9, 29 of 32 full studies ended with no validation assessment by design."""
    if row.get('error'):
        return True
    return row.get('status') == 'INTERRUPTED' or (
        row.get('status') == 'INCOMPLETE' and bool(row.get('error_type')))


def summarize_run(rows):
    """Declared read-outs. S1/S2 are also given WITHOUT the terminating certified study,
    because stop-at-first-success always ends on a study that has the step and qualified."""
    def count(selected):
        step_candidates = [c for r in selected for c in r.get('candidates') or [] if c.get('contains_step')]
        tested = [c for c in step_candidates if c.get('source_decision')]
        complete = [c for c in tested if c['source_decision'] in ('SOURCE_QUALIFIED', 'NO_CHANGE')]
        return {'first_proposals_drawn': sum(1 for r in selected if r.get('first_proposal_drawn')),
                'first_proposals_with_step': sum(1 for r in selected if r.get('first_proposal_contains_step')),
                'distinct_step_policies': len({c['policy_hash'] for c in step_candidates if c.get('policy_hash')}),
                'step_candidates_tested': len(tested),
                'step_candidates_complete_pairs': len(complete),
                'step_candidates_qualified': sum(1 for c in tested if c['source_decision'] == 'SOURCE_QUALIFIED')}
    terminal = [r for r in rows if r.get('certified')][:1]
    certified_hash = terminal[0].get('selected_candidate_hash') if terminal else None
    validations = {}
    for r in rows:
        if r.get('stage') == 'validation' and r.get('selected_candidate_hash'):
            validations[r['selected_candidate_hash']] = validations.get(r['selected_candidate_hash'], 0) + 1
    return {
        # Temperature 0 lets the same policy be drawn in several studies; a certification
        # is always reported with every earlier attempt that carried the same policy.
        'certified_policy_hash': certified_hash,
        'certified_policy_prior_attempts': [
            {'attempt': r['attempt'], 'slot': c['slot'], 'decision': c.get('decision'),
             'source_decision': c.get('source_decision'), 'validation_decision': r.get('validation_decision')}
            for r in rows if terminal and r['attempt'] < terminal[0]['attempt']
            for c in r.get('candidates') or [] if c.get('policy_hash') == certified_hash] if certified_hash else [],
        'validations_per_policy': validations,
        'attempts': len(rows),
        'studies_started': sum(1 for r in rows if r.get('study_id')),
        'certified': sum(1 for r in rows if r.get('certified')),
        'first_certified_attempt': terminal[0]['attempt'] if terminal else None,
        'observed_improvement': sum(1 for r in rows if r.get('decision') == 'OBSERVED_IMPROVEMENT'),
        'observed_improvement_without_fresh_gain': sum(1 for r in rows if r.get('decision') == 'OBSERVED_IMPROVEMENT'
                                                       and not r.get('certified')),
        'infrastructure_deaths': sum(1 for r in rows if infrastructure_death(r)),
        'controls_stops': sum(1 for r in rows if r.get('stage') == 'controls' and r.get('decision') == 'NO_CHANGE'),
        # Reached = entered the 42-episode batch; assessed = assess_pairs returned any
        # decision on it (INCOMPLETE included, as Phase 15 counted 'scored').
        'validation_reached': sum(1 for r in rows if r.get('stage') == 'validation'),
        'validation_assessed': sum(1 for r in rows if r.get('validation_decision')),
        'evidence_reads': sum(r.get('evidence_reads') or 0 for r in rows),
        'evidence_rereads': sum(len(r.get('evidence_rereads') or []) for r in rows),
        'evidence_rereads_verified': sum(1 for r in rows for e in r.get('evidence_rereads') or []
                                         if e.get('result') == 'VERIFIED'),
        'all_studies': count(rows),
        'excluding_terminating_study': count([r for r in rows if r not in terminal]),
    }


# ---------------------------------------------------------------- HTTP and guards

def api(base, method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or 'null')


def campaign_spend(base, campaign_id, attempts=3):
    for attempt in range(attempts):
        try:
            budget = api(base, 'GET', f'/api/campaigns/{campaign_id}/budget')
            value = budget.get('charged_dollar_upper_bound')
            if value is None:
                # The route's fallback when no ledger was ever built (api.py): a campaign whose
                # study never reached queue_completion_study's ledger cannot have been charged.
                # Every real ledger row carries used_calls, so a real ledger with no bound
                # still aborts.
                if 'used_calls' not in budget and api(
                        base, 'GET', f'/api/campaigns/{campaign_id}/completion-studies') == []:
                    return 0.0
                raise PhaseAbort(f'No conservative charge bound for {campaign_id}; refusing to count it as $0')
            return float(value)
        except PhaseAbort:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, AttributeError):
            if attempt == attempts - 1:
                raise PhaseAbort(f'Cannot read the budget for {campaign_id}; refusing to '
                                 f'continue spending with an unknown total')
            time.sleep(3)
    return 0.0


def total_spend(base, campaigns):
    return sum(campaign_spend(base, c) for c in campaigns)


def record_charge(base, campaign_id, entry, save):
    """Spend is its own step, never an argument to the update that saves a verdict
    (the Phase 15 review found that an inline budget failure discarded the verdict)."""
    try:
        entry['charged'] = campaign_spend(base, campaign_id)
    except Exception as error:  # noqa: BLE001
        entry['charge_error'] = type(error).__name__
    save()


def backend_status(base):
    try:
        return api(base, 'GET', '/api/config/status')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def wait_until_idle(base, seconds, poll):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status = backend_status(base)
        if status is not None and not status.get('active_campaign_id'):
            return True
        time.sleep(poll)
    return False


def check_backend(base):
    status = backend_status(base)
    if status is None:
        raise PhaseAbort('Cannot read backend status')
    if not status.get('live_enabled'):
        raise PhaseAbort('Backend is not live-enabled')
    models = status.get('models') or {}
    if models.get('actor') != EXPECTED_ACTOR:
        raise PhaseAbort(f'Backend Actor is {models.get("actor")!r}, phase declares {EXPECTED_ACTOR!r}')
    if models.get('mechanic') != EXPECTED_MECHANIC:
        raise PhaseAbort(f'Backend Mechanic is {models.get("mechanic")!r}, phase declares {EXPECTED_MECHANIC!r}')
    return status


def newest_source_mtime():
    app = ROOT / 'backend/app'
    return max(p.stat().st_mtime for p in app.rglob('*')
               if p.is_file() and p.suffix in ('.py', '.md') and '__pycache__' not in str(p))


def check_backend_process(port=8000):
    """Phase 15 nearly measured the wrong code: the backend had been running since the day
    before under --reload. Every process listening on the port must be a non-reload
    uvicorn that started AFTER the newest source file on disk was written."""
    try:
        pids = subprocess.run(['lsof', '-ti', f'tcp:{port}', '-sTCP:LISTEN'], capture_output=True,
                              text=True, timeout=5).stdout.split()
        if not pids:
            raise ValueError('no listener')
        seen = []
        for pid in pids:
            command = subprocess.run(['ps', '-o', 'command=', '-p', pid], capture_output=True,
                                     text=True, timeout=5).stdout.strip()
            started = subprocess.run(['ps', '-o', 'lstart=', '-p', pid], capture_output=True, text=True,
                                     timeout=5, env={**os.environ, 'LC_ALL': 'C'}).stdout.strip()
            started_at = datetime.strptime(started, '%a %b %d %H:%M:%S %Y').timestamp()
            if '--reload' in command or 'uvicorn' not in command:
                raise PhaseAbort(f'Process {pid} on :{port} is not a non-reload uvicorn: {command[:120]}')
            if started_at < newest_source_mtime():
                raise PhaseAbort(f'Process {pid} on :{port} started before the newest backend/app source '
                                 f'file was written; it may be running old code. Restart it deliberately.')
            seen.append({'pid': int(pid), 'command': command, 'started_at': started})
    except PhaseAbort:
        raise
    except (OSError, IndexError, ValueError, subprocess.SubprocessError) as error:
        raise PhaseAbort(f'Cannot identify the backend process on :{port} ({type(error).__name__})') from error
    return {'processes': sorted(seen, key=lambda p: p['pid'])}


def gate_freeze():
    import contextlib
    import io
    import gate_freeze as freeze  # scripts/experiments/gate_freeze.py, stdlib only
    buffer = io.StringIO()
    argv = sys.argv
    try:
        sys.argv = ['gate_freeze.py', '--root', str(ROOT)]
        with contextlib.redirect_stdout(buffer):
            freeze.main()
    finally:
        sys.argv = argv
    return json.loads(buffer.getvalue())


# ---------------------------------------------------------------- store (read-only)

def store_records(db, kind, ids=None):
    connection = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        if ids is None:
            rows = connection.execute('select id,payload from records where kind=?', (kind,)).fetchall()
        else:
            ids = list(ids)
            rows = connection.execute(
                f'select id,payload from records where kind=? and id in ({",".join("?" * len(ids))})',
                (kind, *ids)).fetchall() if ids else []
    finally:
        connection.close()
    return {row[0]: json.loads(row[1]) for row in rows}


def check_campaign_in_store(db, campaign_id):
    """Proves the backend writes to the store this run reconciles against, and Aria is off."""
    provenance = store_records(db, 'campaign_provenance', [campaign_id]).get(campaign_id)
    if provenance is None:
        raise PhaseAbort(f'{campaign_id} is not in {db}: the backend writes to another store')
    if provenance.get('aria_publication_enabled') is not False:
        raise PhaseAbort('Aria publication is enabled on the backend; it must stay off')


def check_evidence_project(db, study):
    ids = list((study.get('evidence') or {}).keys())
    rows = store_records(db, 'evidence', ids)
    wrong = sorted({r.get('source_project') for r in rows.values()
                    if r.get('source') == 'weave_verified' and r.get('source_project') != EXPECTED_PROJECT})
    if wrong:
        raise PhaseAbort(f'Evidence was verified against {wrong}, not {EXPECTED_PROJECT}')


def reconcile(manifest, db):
    """Read-only. Every manifest study exists once with the recorded outcome and is terminal;
    nothing ran after the first certified study; no full study started in the run window
    is missing from the manifest. Returns (problems, untracked)."""
    studies = store_records(db, 'completion_studies')
    listed = {r['study_id']: r for r in manifest['attempts'] if r.get('study_id')}
    problems = []
    first_certified = None
    for row in manifest['attempts']:
        study = studies.get(row.get('study_id')) if row.get('study_id') else None
        if row.get('study_id') and study is None:
            problems.append(f"attempt {row['attempt']}: {row['study_id']} in manifest, not in store"); continue
        if study is None:
            continue
        if study.get('campaign_id') != row.get('campaign_id'):
            problems.append(f"attempt {row['attempt']}: campaign differs")
        if study.get('status') not in TERMINAL:
            problems.append(f"attempt {row['attempt']}: {row['study_id']} is still {study.get('status')}")
        for key in ('status', 'decision'):
            if row.get(key) != study.get(key):
                problems.append(f"attempt {row['attempt']}: {key} manifest={row.get(key)!r} store={study.get(key)!r}")
        if bool(row.get('certified')) != certified(study):
            problems.append(f"attempt {row['attempt']}: certified manifest={bool(row.get('certified'))} "
                            f"store={certified(study)}")
        if certified(study) and first_certified is None:
            first_certified = row['attempt']
    if first_certified is not None:
        for row in manifest['attempts']:
            if row['attempt'] > first_certified:
                problems.append(f"attempt {row['attempt']}: ran after the certified attempt {first_certified}")
    started = manifest.get('started_at') or ''
    untracked = sorted(sid for sid, s in studies.items()
                       if s.get('replay_of') is None and s.get('created_at', '') >= started and sid not in listed)
    return problems, untracked


# ---------------------------------------------------------------- main loop

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--out', required=True, help='the one artifacts/phase17-* folder for this run')
    parser.add_argument('--store', default=str(ROOT / 'artifacts/lab.sqlite3'))
    parser.add_argument('--settings', help='non-secret settings the backend was launched with')
    parser.add_argument('--expect-freeze', help='reviewed gate-freeze JSON the code on disk must equal')
    parser.add_argument('--expect-freeze-sha256', help='sha256 of that file, as declared in the protocol')
    parser.add_argument('--expect-configuration-hash', help='declared frozen configuration hash of the backend')
    parser.add_argument('--attempt-cap', type=int, default=60)
    parser.add_argument('--stop-after', type=int, help='operator checkpoint: stop after this many attempts in total')
    parser.add_argument('--spend-cap', type=float, default=150.0)
    parser.add_argument('--headroom', type=float, default=11.0, help='worst-case one study is ~$10.23')
    parser.add_argument('--study-timeout', type=float, default=5400.0)
    parser.add_argument('--idle-grace', type=float, default=900.0)
    parser.add_argument('--poll-failure-window', type=float, default=300.0)
    parser.add_argument('--consecutive-infrastructure-abort', type=int, default=5)
    parser.add_argument('--poll', type=float, default=5.0)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--after-abort', action='store_true',
                        help='resume a run that aborted; only with the user\'s explicit approval')
    parser.add_argument('--reconcile', action='store_true')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    args = parser.parse_args()

    out = ROOT / args.out
    manifest_path = out / 'full-loop-manifest.json'
    if args.reconcile:
        manifest = json.loads(manifest_path.read_text())
        problems, untracked = reconcile(manifest, args.store)
        print(f'reconciliation: {len(problems)} discrepancies, {len(untracked)} untracked full studies')
        for line in problems + [f'untracked: {sid}' for sid in untracked]:
            print('  ' + line)
        return 1 if problems or untracked else 0

    stop_after = min(args.stop_after or args.attempt_cap, args.attempt_cap)
    print(f'design     sequential; stop at the first CERTIFIED study, at {stop_after} attempts '
          f'(cap {args.attempt_cap}), at the spend guard, or on the breaker')
    print(f'success    OBSERVED_IMPROVEMENT under the unchanged assess_pairs AND L-B0 >= {FRESH_GAIN_MIN}')
    print(f'           completions on a validation case other than {SOURCE_CASE} and {CONTROL_CASE}')
    print(f'models     actor {EXPECTED_ACTOR}; mechanic {EXPECTED_MECHANIC}')
    print(f'protocols  actor {ACTOR_CONTEXT}; evidence {EVIDENCE_PROTOCOL}')
    print(f'spend      guard ${args.spend_cap:.2f} (conservative bound), headroom ${args.headroom:.2f} per study')
    print('never      replay, re-validate, resume a study, or write ACCEPTED')
    if args.plan or not args.execute_live:
        print('Dry plan only. Pass --execute-live --confirm-entity ENTITY to run.')
        return 0

    for flag in ('settings', 'expect_freeze', 'expect_freeze_sha256', 'expect_configuration_hash', 'stop_after'):
        if not getattr(args, flag):
            raise SystemExit(f'--{flag.replace("_", "-")} is required for a live run')
    if (args.expect_freeze_sha256, args.expect_configuration_hash) != (DECLARED_FREEZE_SHA256, DECLARED_CONFIGURATION_HASH):
        raise SystemExit('The typed pins differ from the values declared in this reviewed runner')
    if sha256_file(ROOT / args.settings) != DECLARED_SETTINGS_SHA256:
        raise SystemExit('The settings file is not the declared one')
    if sha256_file(pathlib.Path(__file__).with_name('gate_freeze.py')) != DECLARED_GATE_FREEZE_SCRIPT_SHA256:
        raise SystemExit('gate_freeze.py is not the reviewed script')
    if out.parent != ROOT / 'artifacts' or not out.name.startswith('phase17-'):
        raise SystemExit('--out must be artifacts/phase17-<date>')
    from app.config import Settings
    settings_path = ROOT / args.settings
    overrides = json.loads(settings_path.read_text())
    os.environ.update({k: str(v) for k, v in overrides.items() if v != ''})
    settings = Settings.from_env()
    if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
        raise SystemExit('--confirm-entity must match WANDB_ENTITY in the settings file')
    if settings.project_path != EXPECTED_PROJECT:
        raise SystemExit(f'Settings project is {settings.project_path!r}, phase declares {EXPECTED_PROJECT!r}')

    freeze_path = ROOT / args.expect_freeze
    if sha256_file(freeze_path) != args.expect_freeze_sha256:
        raise SystemExit('The freeze file is not the one declared in the protocol')
    expected_freeze = json.loads(freeze_path.read_text())
    if (expected_freeze.get('functions') or {}).get(ASSESS_PAIRS_KEY, {}).get('text_sha256') != ASSESS_PAIRS_TEXT_SHA256:
        raise SystemExit('The declared freeze does not contain the unchanged assess_pairs')
    current_freeze = gate_freeze()
    if current_freeze != expected_freeze:
        differing = sorted(f'{section}:{k}' for section in ('functions', 'files', 'fingerprints')
                           for k in set(current_freeze.get(section, {})) | set(expected_freeze.get(section, {}))
                           if current_freeze.get(section, {}).get(k) != expected_freeze.get(section, {}).get(k))
        raise SystemExit(f'Code on disk differs from the reviewed freeze: {differing[:8] or "schema"}')
    process = check_backend_process()

    status = check_backend(args.base)
    if status.get('active_campaign_id'):
        raise SystemExit('Another execution is active; refusing to start')

    declared = {'schema_version': SCHEMA, 'attempt_cap': args.attempt_cap, 'spend_cap': args.spend_cap,
                'headroom': args.headroom, 'consecutive_infrastructure_abort': args.consecutive_infrastructure_abort,
                'actor_context_protocol': ACTOR_CONTEXT, 'evidence_protocol': EVIDENCE_PROTOCOL,
                'expected_models': {'actor': EXPECTED_ACTOR, 'mechanic': EXPECTED_MECHANIC},
                'project': EXPECTED_PROJECT, 'manifest_hash': MANIFEST_HASH,
                'assess_pairs_text_sha256': ASSESS_PAIRS_TEXT_SHA256, 'fresh_gain_min': FRESH_GAIN_MIN,
                'configuration_hash': args.expect_configuration_hash,
                'gate_freeze_file_sha256': args.expect_freeze_sha256,
                'runner_sha256': sha256_file(__file__),
                'gate_freeze_script_sha256': sha256_file(pathlib.Path(__file__).with_name('gate_freeze.py')),
                'settings_sha256': sha256_file(settings_path),
                # Recorded, not pinned: resume refuses if the protocol text changed after the run began.
                'protocol_sha256': sha256_file(PROTOCOL)}
    out.mkdir(parents=True, exist_ok=True)
    if args.resume:
        if not manifest_path.exists():
            raise SystemExit(f'{manifest_path} does not exist; nothing to resume')
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('declared') != declared:
            raise SystemExit('Resume refused: the declared parameters, code, runner or settings differ from the run on record')
        previous = manifest.get('stop_reason')
        if previous in TERMINAL_STOPS:
            raise SystemExit(f'Resume refused: the run ended with {previous!r}')
        # Only a clean checkpoint continues without approval. 'aborted', a session that was
        # killed ('running' left behind) or anything unexpected needs the user's approval.
        if previous != 'checkpoint' and not args.after_abort:
            raise SystemExit(f'Resume refused: the last session ended with {previous!r}; continuing '
                             f'needs the user\'s approval (--after-abort)')
        if manifest.get('stop_incomplete'):
            if not args.after_abort or not wait_until_idle(args.base, 60, args.poll):
                raise SystemExit('Resume refused: the last stop did not settle and the backend is not idle')
            manifest['stop_incomplete_cleared'] = datetime.now(timezone.utc).isoformat()
            manifest.pop('stop_incomplete')
    else:
        if manifest_path.exists():
            raise SystemExit(f'{manifest_path} exists; refusing to overwrite a retained run record')
        others = [p for p in out.parent.glob('phase17-*/full-loop-manifest.json') if p != manifest_path]
        if others:
            raise SystemExit(f'Another Phase 17 run exists ({others[0]}); continue it with --resume, '
                             f'never in a new folder')
        previous = None
        manifest = {'schema_version': SCHEMA, 'declared': declared, 'models': status.get('models'),
                    'started_at': datetime.now(timezone.utc).isoformat(), 'configuration_hash': None,
                    'campaigns': [], 'attempts': [], 'sessions': []}

    def save():
        temporary = manifest_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n')
        os.replace(temporary, manifest_path)

    campaigns = manifest['campaigns']

    def needs_recovery(entry):
        # Started but never written, or a start interrupted before its study id was saved.
        return entry.get('status') is None and entry.get('campaign_id') and (
            entry.get('study_id') or not entry.get('error'))

    def recover(entry):
        """Fill a row whose outcome was never written, re-running the post-finish checks
        that do not depend on the (possibly different) process that ran it."""
        try:
            if not entry.get('study_id'):
                existing = api(args.base, 'GET', f"/api/campaigns/{entry['campaign_id']}/completion-studies")
                if len(existing) > 1:
                    return False
                if not existing:
                    entry['error'] = 'study start: interrupted before the server saw it'; save()
                    return True
                entry['study_id'] = existing[0]['study_id']; entry['adopted_after_start_error'] = True; save()
            study = api(args.base, 'GET', f"/api/completion-studies/{entry['study_id']}")
        except Exception:  # noqa: BLE001
            return False
        if study.get('status') not in TERMINAL:
            return False
        entry.update(summarize_study(study), recovered=True)
        try:
            verify_study_identity(study, when='recovered')
            check_evidence_project(args.store, study)
            entry['post_checks'] = 'passed on recovery (backend process pin not re-checkable)'
        except PhaseAbort as error:
            entry['certified'] = False; entry['post_checks'] = f'failed on recovery: {error}'
        save()
        record_charge(args.base, entry['campaign_id'], entry, save)
        return True

    if args.resume:
        for entry in manifest['attempts']:
            if needs_recovery(entry) and not recover(entry):
                raise SystemExit(f"Resume refused: attempt {entry['attempt']} has no recorded outcome and its "
                                 f"study is not terminal or not readable; resolve it first")
        problems, untracked = reconcile(manifest, args.store)
        if problems or untracked:
            raise SystemExit('Resume refused: manifest and store disagree: ' + '; '.join(problems + untracked)[:500])
    manifest['sessions'].append({'started_at': datetime.now(timezone.utc).isoformat(), 'stop_after': stop_after,
                                 'after_abort': bool(args.after_abort), 'previous_stop': previous,
                                 'backend_process': process})
    # Marks a session in progress: a session killed hard leaves 'running', which resume
    # treats as an abort needing approval.
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
        if not infrastructure_death(row):
            break
        consecutive += 1

    def pin_process():
        now = check_backend_process()
        if now != process:
            raise PhaseAbort(f'backend process changed during the run: {process} -> {now}')

    try:
        while True:
            attempts = len(manifest['attempts'])
            if any(r.get('certified') for r in manifest['attempts']):
                stop_reason = 'certified'; break
            if attempts >= args.attempt_cap:
                stop_reason = 'attempt_cap'; break
            if attempts >= stop_after:
                stop_reason = 'checkpoint'; break
            charged = total_spend(args.base, campaigns)
            if charged + args.headroom > args.spend_cap:
                stop_reason = 'spend_guard'; break
            check_backend(args.base)
            pin_process()
            if not wait_until_idle(args.base, args.idle_grace, args.poll):
                raise PhaseAbort('backend is not idle; refusing to start another study')
            entry = {'attempt': attempts + 1, 'campaign_id': None, 'study_id': None, 'spent_before': charged}
            manifest['attempts'].append(entry); save()
            print(f'[attempt {entry["attempt"]}] spent ${charged:.5f}', flush=True)

            try:
                campaign = api(args.base, 'POST', '/api/campaigns', {
                    'task_text': TASK_TEXT, 'order_id': ORDER_ID,
                    'mode': 'baseline', 'config_profile_id': 'live-v1'})
            except Exception as error:  # noqa: BLE001
                entry['error'] = f'campaign create: {type(error).__name__}'; save()
                consecutive += 1
                if consecutive >= args.consecutive_infrastructure_abort:
                    raise PhaseAbort(f'{consecutive} consecutive infrastructure failures')
                continue
            # Registered BEFORE the study starts, so its spend is always counted.
            campaigns.append(campaign['campaign_id'])
            entry['campaign_id'] = campaign['campaign_id']
            entry['configuration_hash'] = campaign.get('configuration_hash'); save()
            if not entry['configuration_hash']:
                entry['error'] = 'no configuration_hash (no study started)'; save()
                raise PhaseAbort('campaign carries no configuration_hash')
            if entry['configuration_hash'] != args.expect_configuration_hash:
                entry['error'] = 'configuration_hash mismatch (no study started)'; save()
                raise PhaseAbort(f"backend configuration_hash {entry['configuration_hash']} != declared "
                                 f"{args.expect_configuration_hash}")
            manifest['configuration_hash'] = entry['configuration_hash']
            try:
                check_campaign_in_store(args.store, campaign['campaign_id'])
            except PhaseAbort:
                entry['error'] = 'store or Aria check failed (no study started)'; save()
                raise

            try:
                started = api(args.base, 'POST', f"/api/campaigns/{campaign['campaign_id']}/completion-study",
                              {'execute_live': True, 'evidence_protocol': EVIDENCE_PROTOCOL,
                               'actor_context_protocol': ACTOR_CONTEXT})
            except Exception as error:  # noqa: BLE001
                # The server may have started it although the client saw a failure.
                entry['start_error'] = type(error).__name__; save()
                try:
                    existing = api(args.base, 'GET', f"/api/campaigns/{campaign['campaign_id']}/completion-studies")
                except Exception:  # noqa: BLE001
                    record_charge(args.base, campaign['campaign_id'], entry, save)
                    raise PhaseAbort('study start failed and the server cannot say whether a study exists')
                if not existing:
                    # The server may still be inside queue_completion_study; look again once idle.
                    if not wait_until_idle(args.base, args.idle_grace, args.poll):
                        raise PhaseAbort('backend did not return to idle after a failed start')
                    try:
                        existing = api(args.base, 'GET', f"/api/campaigns/{campaign['campaign_id']}/completion-studies")
                    except Exception:  # noqa: BLE001
                        raise PhaseAbort('study start failed and the server cannot say whether a study exists')
                if len(existing) > 1:
                    raise PhaseAbort('more than one study on a fresh campaign')
                if not existing:
                    entry['error'] = f"study start: {entry['start_error']}"; save()
                    record_charge(args.base, campaign['campaign_id'], entry, save)
                    consecutive += 1
                    if consecutive >= args.consecutive_infrastructure_abort:
                        raise PhaseAbort(f'{consecutive} consecutive infrastructure failures')
                    if not wait_until_idle(args.base, args.idle_grace, args.poll):
                        raise PhaseAbort('backend did not return to idle after a failed start')
                    continue
                started = existing[0]; entry['adopted_after_start_error'] = True
            entry['study_id'] = started['study_id']; save()
            verify_study_identity(started, when='at start')

            deadline = time.monotonic() + args.study_timeout
            study, failing_since = started, None
            while study.get('status') not in TERMINAL:
                if time.monotonic() > deadline:
                    raise PhaseAbort(f"{started['study_id']} still {study.get('status')} after the study timeout")
                time.sleep(args.poll)
                try:
                    study = api(args.base, 'GET', f"/api/completion-studies/{started['study_id']}")
                    failing_since = None
                except Exception as error:  # noqa: BLE001
                    entry['poll_errors'] = entry.get('poll_errors', 0) + 1
                    failing_since = failing_since or time.monotonic()
                    if time.monotonic() - failing_since > args.poll_failure_window:
                        raise PhaseAbort(f'lost contact with a running study ({type(error).__name__}); '
                                         f'stopping rather than starting another beside it')
            # Save the terminal outcome the moment it is seen; nothing below can lose it.
            entry.update(summarize_study(study), post_checks='pending'); save()
            if not wait_until_idle(args.base, args.idle_grace, args.poll):
                raise PhaseAbort('a finished study is still holding the coordinator')
            try:
                study = api(args.base, 'GET', f"/api/completion-studies/{started['study_id']}")
            except Exception as error:  # noqa: BLE001
                raise PhaseAbort(f'could not re-read the finished record ({type(error).__name__}); '
                                 f'the outcome seen at completion is kept')
            entry.update(summarize_study(study)); save()
            record_charge(args.base, campaign['campaign_id'], entry, save)
            try:
                # Part of condition 1: a row that fails these is never certified.
                verify_study_identity(study, when='after finishing')
                check_evidence_project(args.store, study)
                pin_process()
            except PhaseAbort as error:
                entry['certified'] = False; entry['post_checks'] = f'failed: {error}'; save()
                raise
            entry['post_checks'] = 'passed'; save()
            consecutive = consecutive + 1 if infrastructure_death(entry) else 0
            candidates = ', '.join(f"{c['decision']}{'+step' if c['contains_step'] else ''}"
                                   for c in entry['candidates']) or 'none'
            print(f"[attempt {entry['attempt']}] {entry['status']}/{entry['decision']} at {entry['stage']}"
                  f" | candidates: {candidates} | validation={entry['validation_decision']}"
                  f" | certified={entry['certified']}"
                  + (f" | error={entry['error_type']}" if entry.get('error_type') else ''), flush=True)
            if consecutive >= args.consecutive_infrastructure_abort:
                raise PhaseAbort(f'{consecutive} consecutive studies died of infrastructure errors; '
                                 f'check evidence ingestion and provider health')
    except PhaseAbort as error:
        stop_reason = 'aborted'; manifest['abort_detail'] = str(error)
        print(f'\nABORTED: {error}', flush=True)
    except Detached as signal_error:
        stop_reason = 'aborted'; leave_running = True
        manifest['abort_detail'] = f'signal {signal_error.args[0]}; any running study left running for recover()'
    except KeyboardInterrupt:
        stop_reason = 'aborted'; manifest['abort_detail'] = 'interrupted by operator or signal'
    except Exception as error:  # noqa: BLE001
        stop_reason = 'aborted'; manifest['abort_detail'] = f'{type(error).__name__}: {error}'
        print(f'\nABORTED: {manifest["abort_detail"]}', flush=True)

    if stop_reason == 'aborted' and campaigns and not leave_running:
        # Aborting the runner does not stop the backend. Stop OUR campaign only while its
        # study is still running; never rewrite a campaign whose study already finished.
        status = backend_status(args.base)
        last = manifest['attempts'][-1] if manifest['attempts'] else {}
        in_flight = last.get('status') is None and last.get('campaign_id') == campaigns[-1] and (
            (status or {}).get('active_campaign_id') == campaigns[-1] or status is None)
        if in_flight:
            try:
                api(args.base, 'POST', f'/api/campaigns/{campaigns[-1]}/stop', {})
            except Exception as error:  # noqa: BLE001
                print(f'  stop request failed: {type(error).__name__}', flush=True)
            if not wait_until_idle(args.base, args.idle_grace, args.poll):
                manifest['stop_incomplete'] = True
    if not leave_running:
        for entry in manifest['attempts']:
            if needs_recovery(entry):
                try:
                    recover(entry)
                except Exception:  # noqa: BLE001
                    pass

    manifest['stop_reason'] = stop_reason
    manifest['summary'] = summarize_run(manifest['attempts'])
    try:
        manifest['total_charged_upper_bound'] = total_spend(args.base, campaigns)
    except PhaseAbort as error:
        manifest['total_charged_upper_bound'] = None
        manifest['total_charged_error'] = str(error)
    manifest['sessions'][-1]['ended_at'] = datetime.now(timezone.utc).isoformat()
    save()
    s = manifest['summary']
    total = manifest['total_charged_upper_bound']
    print(f"\n{stop_reason} | {s['attempts']} attempts | certified {s['certified']} | step in "
          f"{s['all_studies']['first_proposals_with_step']} of {s['all_studies']['first_proposals_drawn']} first "
          f"proposals | validation reached {s['validation_reached']}, assessed {s['validation_assessed']} | "
          f"charged ${total if total is not None else float('nan'):.5f}")
    print(f'manifest {manifest_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
