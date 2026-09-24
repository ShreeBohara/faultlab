"""Phase 24: one declared held-out no-harm check (predicate v2) of Phase 23's first new certified repair.

The policy is not chosen by anyone running this script. It is routed by rule from the one
Phase 23 run record: the first attempt, by attempt order, whose study is certified (per the
Phase 17 certification rule, re-checked against the store) and whose policy is not
dd62c857 (its Phase 18 verdict is final). The Phase 23 run must be final (fixed_n or
spend_guard), and its declared routing field (summary.routing) must be final, routable and
name the same study and policy, or nothing runs.

That policy is run, paired against the empty baseline, on the sealed heldout-2 partition
through the project's own PairedEvaluator with the v4 Actor context: every fault case as 5
replicas of 3 pairs (15 trials per arm), the no-fault case as 1 (3 per arm), 78 pairs and
156 episodes per attempt. It is judged by `faultlab-heldout-no-harm/v2`
(backend/app/lab/heldout_check.py, assess_heldout_v2); v1 on the first replica of each case
is stored beside it, descriptive only.

Declared design: at most MAX_ATTEMPTS attempts, counted as the held-out checks the backend
holds for the policy (an attempt that created no check does not count). The first attempt that
reaches a verdict (NO_HARM or HARM) ends the run and is final. Only an attempt that reached no
verdict (INCOMPLETE: an untriggered fault, an infrastructure failure, a stop) is replaced, and
any candidate check failure in any attempt is already HARM. A started check that is not the
declared one is stopped at once and is never the run's verdict; a check the runner adopted (after
a lost start reply, in the abort path, or on resume) is identity-checked before it can be one
(review round 2). Nothing is ever called ACCEPTED.

The spend guard admits an attempt only while (charged so far + the attempt's hard worst case)
stays within SPEND_CAP, a constant: the hard worst case is every one of the 78 pairs reserved
(16 calls) and retried once after a lab error (16 more): 2,496 actor calls.

Continuation: after an early stop only, `--resume --after-abort` on the same folder, with the
user's approval. Spend, campaigns and rows carry over; 'verdict', 'attempt_cap' and
'spend_guard' are final. A live run also needs the approved review record (--review-record),
which must repeat this runner's sha and every value it checks.

Runbook checks built in: check_ingestion_health and GET /api/readiness at the start of each
session, both RECORDED and never a refusal (review round 2: the ingestion check reads only
development ingestion rows, which heldout-2's split-promotion episodes never write, so it can say
nothing about this phase and nothing this phase does can change it; readiness checks the local
simulator and configuration, not the provider, and the backend refuses a check start itself when
the simulator is not ready), and check_clock_drift --worlds after each session (recorded, never a
re-run). Both scripts are the files the Phase 23 runner pins, reused through it.

The pins below are filled at the Phase 22 freeze. While any placeholder remains the runner
refuses to run live. Dry by default: `--execute-live` plus a matching `--confirm-entity` is
required to run.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_full_loop as base  # the reviewed Phase 17 guards; nothing in it is modified
# The Phase 23 runner (its sha is pinned below): it writes the routing field read here, and its
# ingestion and drift checks, with the pins it holds for those two scripts, are reused as they are.
import run_full_loop_fixed_n as fixed  # noqa: E402

ROOT = base.ROOT
SCHEMA = 'faultlab-heldout-run/v2'
PREDICATE = 'faultlab-heldout-no-harm/v2'
PARTITION = 'heldout-2'
# A policy with a held-out verdict is never checked again (the backend refuses it too).
EXCLUDED_POLICY_HASHES = ('dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521',)
MAX_ATTEMPTS = 3
VERDICTS = ('NO_HARM', 'HARM')
TERMINAL = ('COMPLETED', 'INCOMPLETE', 'INTERRUPTED')
# A Phase 24 stop that is never resumed or topped up.
FINAL_STOPS = ('verdict', 'attempt_cap', 'spend_guard')
# The declared heldout-2 shape: 5 fault cases x 5 replicas x 3 pairs + 1 no-fault case x 1 x 3.
PLANNED_PAIRS = 78
PLANNED_EPISODES = 2 * PLANNED_PAIRS
# PairedEvaluator reserves 16 calls per pair and 16 more for its one lab-error retry of a pair.
CALLS_PER_PAIR = 16
WORST_CASE_CALLS_PER_ATTEMPT = PLANNED_PAIRS * CALLS_PER_PAIR * 2
# Conservative dollars per admitted Actor call at the Phase 17 settings (32,000 input and
# 2,000 output tokens at the configured V3.1 rates); re-derived from the settings when live.
DECLARED_ACTOR_CALL_BOUND = 0.0209
# A constant, not a flag (Phase 22 review round 1): changing it is a code edit made before the
# freeze, never a command-line choice at run time.
SPEND_CAP = 87.0
# Rows the runner ended itself before any check existed.
INTERRUPTED_BEFORE_CREATE = 'interrupted before its campaign was recorded (no check)'
NO_CHECK_CREATED = 'no check was created'


def worst_case_dollars(call_bound=DECLARED_ACTOR_CALL_BOUND):
    """Hard worst case of one attempt, rounded UP to the cent."""
    return math.ceil(WORST_CASE_CALLS_PER_ATTEMPT * call_bound * 100 - 1e-9) / 100


# The Phase 23 run record that routes the policy: the one fixed-N loop manifest.
PHASE23_MANIFEST_GLOB = 'phase23-*/full-loop-manifest.json'
# Only a final Phase 23 run routes (PHASE22_EXPERIMENT.md R3): its declared stop rules.
PHASE23_FINAL_STOPS = ('fixed_n', 'spend_guard')

# Pins declared in docs/part2/PHASE24_EXPERIMENT.md, filled at the Phase 22 freeze.
PLACEHOLDER = 'FILL-AT-FREEZE'
DECLARED_FREEZE_SHA256 = '8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1'
DECLARED_CONFIGURATION_HASH = '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba'
DECLARED_PROTOCOL_SHA256 = '733d572df1aa73f7452b7d8d00dd6008649a7279a2bcf1121a19c71ac32df7e2'
DECLARED_PARTITION_MANIFEST_HASH = 'c902f1c982e99c57ae65a8c73ed331838a6f4ce4336a325058b918cd901846cf'    # content_hash(cases) of the sealed partition
DECLARED_PARTITION_DIR = 'artifacts/heldout2/partition'              # its directory, relative to the repo root
DECLARED_BASE_RUNNER_SHA256 = '07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342'         # run_full_loop.py, whose guards are reused
DECLARED_PHASE23_RUNNER_SHA256 = '95ef698d155986c209e1138d169b1bbb342656dd13152db457ff2185a5ff09d1'      # the fixed-N runner whose manifest routes
DECLARED_SETTINGS_SHA256 = base.DECLARED_SETTINGS_SHA256
PROTOCOL = 'docs/part2/PHASE24_EXPERIMENT.md'
PINS = ('DECLARED_FREEZE_SHA256', 'DECLARED_CONFIGURATION_HASH', 'DECLARED_PROTOCOL_SHA256',
        'DECLARED_PARTITION_MANIFEST_HASH', 'DECLARED_PARTITION_DIR', 'DECLARED_BASE_RUNNER_SHA256',
        'DECLARED_PHASE23_RUNNER_SHA256')


class Detached(BaseException):
    """SIGTERM/SIGHUP: leave any running check alone; its verdict stays in the store."""


class RoutingError(RuntimeError):
    """The Phase 23 record does not route exactly one declared policy; nothing is started."""


def unfilled_pins():
    return [name for name in PINS if PLACEHOLDER in str(globals()[name])]


def is_verdict(row):
    """A row whose decision may be the run's verdict: NO_HARM or HARM on a check that was compared
    with the declared check and matched it. A rejected or never-compared check is never the verdict."""
    return row.get('decision') in VERDICTS and row.get('identity_checked') is True and not row.get('identity_mismatch')


def is_repo_path(value):
    """A plain repository-relative POSIX path: no absolute path, no '.', '..' or empty part."""
    if not isinstance(value, str) or not value or value.startswith('/') or '\\' in value:
        return False
    return all(part not in ('', '.', '..') for part in value.split('/'))


def pin_problems():
    """Every pin filled and well formed before any HTTP call: 64 lowercase hex, and the partition
    directory a plain repository-relative path. A truncated hash must not reach the backend."""
    problems = []
    for name in PINS:
        value = globals()[name]
        if PLACEHOLDER in str(value):
            problems.append(f'{name} (placeholder)')
        elif name == 'DECLARED_PARTITION_DIR':
            if not is_repo_path(value):
                problems.append(f'{name} (not a repository-relative path)')
        elif not fixed.is_sha256(value):
            problems.append(f'{name} (not 64 lowercase hex)')
    return problems


# ---------------------------------------------------------------- scripted routing (pure)

def route(manifest, studies):
    """The first attempt, by attempt order, that the Phase 23 manifest records as certified,
    whose study the store still certifies, and whose policy is not excluded.

    `studies` maps study_id to the stored completion study. A manifest row that claims a
    certification the store does not support is refused, as is any earlier attempt with no
    recorded outcome (it might have been certified); a row with neither a campaign nor a study
    ran nothing and is resolved. A row the store certifies but the Phase 23 runner demoted
    (its post-checks failed) is skipped and listed. The chosen row's post-checks must have
    passed. Returns None only when every attempt is resolved and none routes."""
    rows = sorted(manifest.get('attempts') or [], key=lambda r: r.get('attempt') or 0)
    if [r.get('attempt') for r in rows] != list(range(1, len(rows) + 1)):
        raise RoutingError('Phase 23 attempts are not numbered 1..n')
    skipped, demoted = [], []
    for row in rows:
        if (row.get('status') not in TERMINAL and not row.get('error')
                and (row.get('campaign_id') or row.get('study_id'))):
            raise RoutingError(f"Phase 23 attempt {row['attempt']} has no recorded outcome; it cannot be passed over")
        study = studies.get(row.get('study_id')) if row.get('study_id') else None
        stored = study is not None and base.certified(study)
        if row.get('certified') and not stored:
            raise RoutingError(f"Phase 23 attempt {row['attempt']} is recorded certified but the store does not certify it")
        if stored and not row.get('certified'):
            demoted.append(row['attempt']); continue
        if not stored:
            continue
        policy_hash = study.get('selected_candidate_hash')
        if row.get('selected_candidate_hash') != policy_hash:
            raise RoutingError(f"Phase 23 attempt {row['attempt']}: manifest and store name different policies")
        if policy_hash in EXCLUDED_POLICY_HASHES:
            skipped.append({'attempt': row['attempt'], 'policy_hash': policy_hash}); continue
        if not str(row.get('post_checks') or '').startswith('passed'):
            raise RoutingError(f"Phase 23 attempt {row['attempt']}: its post-checks did not pass "
                               f"({row.get('post_checks')!r}); it is not routable")
        return {'attempt': row['attempt'], 'study_id': row['study_id'], 'policy_hash': policy_hash,
                'post_checks': row.get('post_checks'), 'skipped_excluded': skipped, 'demoted_by_post_checks': demoted}
    return None


def routed_policy(manifest, studies):
    """route(), on a final Phase 23 run only, cross-checked against the manifest's declared
    routing field (summary.routing: final, routable, the same study and policy) and runner pin."""
    if manifest.get('stop_reason') not in PHASE23_FINAL_STOPS:
        raise RoutingError(f"The Phase 23 run is not final (stop_reason {manifest.get('stop_reason')!r}); "
                           f"only {' or '.join(PHASE23_FINAL_STOPS)} routes")
    if (manifest.get('declared') or {}).get('runner_sha256') != DECLARED_PHASE23_RUNNER_SHA256:
        raise RoutingError('The Phase 23 manifest was not written by the declared fixed-N runner')
    declared = (manifest.get('summary') or {}).get('routing')
    routed = route(manifest, studies)
    if routed is None:
        if isinstance(declared, dict) and declared.get('policy_hash'):
            raise RoutingError('The Phase 23 manifest declares a routing the rule does not produce')
        raise RoutingError('Phase 23 certified no new policy; Phase 24 does not run')
    if not isinstance(declared, dict) or (declared.get('policy_hash'), declared.get('study_id')) != (
            routed['policy_hash'], routed['study_id']) or declared.get('attempt') != routed['attempt']:
        raise RoutingError('The Phase 23 manifest\'s declared routing (summary.routing) differs from the routing rule')
    if declared.get('run_final') is not True or declared.get('routable') is not True:
        raise RoutingError('The Phase 23 manifest does not declare its routing final and routable')
    return routed


def load_routing(store):
    found = sorted((ROOT / 'artifacts').glob(PHASE23_MANIFEST_GLOB))
    if len(found) != 1:
        raise RoutingError(f'Expected exactly one Phase 23 run record, found {len(found)}')
    manifest = json.loads(found[0].read_text())
    ids = [r['study_id'] for r in manifest.get('attempts') or [] if r.get('study_id')]
    routed = routed_policy(manifest, base.store_records(store, 'completion_studies', ids))
    return {**routed, 'phase23_manifest': str(found[0].relative_to(ROOT)),
            'phase23_manifest_sha256': base.sha256_file(found[0])}


# ---------------------------------------------------------------- binding and checks (no HTTP)

def review_problem(path, runner_sha, routing):
    """The review record binds a live run to what was reviewed: written by the approver when the
    phase is approved, never by this runner. Every value is compared exactly."""
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
                       ('configuration_hash', DECLARED_CONFIGURATION_HASH),
                       ('partition_manifest_hash', DECLARED_PARTITION_MANIFEST_HASH),
                       ('routed_policy_hash', routing['policy_hash']), ('routed_study_id', routing['study_id'])):
        if record.get(key) != value:
            return f'the review record does not carry this {key}'
    return None


def file_pins(args):
    """(refusal, file, declared sha) for every file the live run is bound to. In a dry plan without
    --settings the declared settings file is shown, and without --expect-freeze the freeze is None."""
    settings = ROOT / (args.settings or fixed.DEFAULT_SETTINGS)
    freeze = ROOT / args.expect_freeze if args.expect_freeze else None
    return [('run_full_loop.py is not the reviewed Phase 17 runner', HERE / 'run_full_loop.py', DECLARED_BASE_RUNNER_SHA256),
            ('gate_freeze.py is not the reviewed script', HERE / 'gate_freeze.py', base.DECLARED_GATE_FREEZE_SCRIPT_SHA256),
            ('run_full_loop_fixed_n.py is not the declared Phase 23 runner', HERE / 'run_full_loop_fixed_n.py',
             DECLARED_PHASE23_RUNNER_SHA256),
            ('check_clock_drift.py is not the drift checker the Phase 23 runner pins', HERE / 'check_clock_drift.py',
             fixed.DECLARED_DRIFT_CHECKER_SHA256),
            ('check_ingestion_health.py is not the ingestion check the Phase 23 runner pins',
             HERE / 'check_ingestion_health.py', fixed.DECLARED_INGESTION_CHECK_SHA256),
            ('The settings file is not the declared one', settings, DECLARED_SETTINGS_SHA256),
            ('The protocol is not the declared one', ROOT / PROTOCOL, DECLARED_PROTOCOL_SHA256),
            ('The freeze file is not the one declared in the protocol', freeze, DECLARED_FREEZE_SHA256)]


def pin_status(args):
    """Read-only, for the dry plan (review round 2): every pin's state and every file pin's match, so a
    mistyped pin shows before the approval record is written, not only at the live start. The partition
    is checked through its PUBLIC manifest_hash file only; the partition file is never opened."""
    rows = []
    for name in PINS:
        value = globals()[name]
        if PLACEHOLDER in str(value):
            state = 'NOT FILLED'
        elif name == 'DECLARED_PARTITION_DIR':
            state = 'well formed' if is_repo_path(value) else 'MALFORMED'
        else:
            state = 'filled' if fixed.is_sha256(value) else 'MALFORMED'
        rows.append({'pin': name, 'state': state, 'declared': value})
    for refusal, path, declared in file_pins(args):
        label = refusal.split(' is not')[0].replace('The ', '')
        if not fixed.is_sha256(declared):
            # 'UNFILLED', not 'NOT FILLED': the latter names this runner's own pins only.
            state, current = ('UNFILLED' if PLACEHOLDER in str(declared) or fixed.PLACEHOLDER in str(declared)
                              else 'MALFORMED'), None
        elif path is None:
            state, current = 'not given', None
        elif not pathlib.Path(path).is_file():
            state, current = 'FILE MISSING', None
        else:
            current = base.sha256_file(path)
            state = 'MATCH' if current == declared else 'DIFFERS'
        rows.append({'pin': label, 'state': state, 'declared': declared, 'current': current})
    filled = PLACEHOLDER not in str(DECLARED_PARTITION_DIR) and is_repo_path(DECLARED_PARTITION_DIR)
    public = ROOT / DECLARED_PARTITION_DIR / 'manifest_hash' if filled else None
    if public is None or not fixed.is_sha256(DECLARED_PARTITION_MANIFEST_HASH):
        state, current = 'UNFILLED', None
    elif not public.is_file():
        state, current = 'FILE MISSING', None
    else:
        current = public.read_text(encoding='utf-8').strip()
        state = 'MATCH' if current == DECLARED_PARTITION_MANIFEST_HASH else 'DIFFERS'
    rows.append({'pin': 'partition manifest_hash file (public)', 'state': state,
                 'declared': DECLARED_PARTITION_MANIFEST_HASH, 'current': current})
    return rows


def policy_checks(store, policy_hash):
    """Read-only: every held-out check the backend saved for this policy, on any partition. The
    backend counts attempts the same way (heldout_check.queue_heldout_check)."""
    return {cid: record for cid, record in base.store_records(store, 'heldout_checks').items()
            if record.get('policy_hash') == policy_hash}


def untriggered_by_case(assessment):
    """Untriggered paired trials per case and arm (section 8: a policy that suppresses the
    confirmation send can only read INCOMPLETE on that case, so an L-heavy count is reported)."""
    by_case = (assessment or {}).get('by_case') or {}
    return {case: {arm: (arms.get(arm) or {}).get('untriggered') for arm in ('B0', 'L')}
            for case, arms in by_case.items()}


def ingestion_health():
    return fixed.ingestion_health()


def readiness(base_url):
    """GET /api/readiness, recorded per session and never a refusal: it reports the local simulator and
    the live configuration, and says itself that it does not contact the provider ('provider_access':
    'not_checked'). The backend refuses a check start on its own when the simulator is not ready."""
    try:
        reading = base.api(base_url, 'GET', '/api/readiness')
    except Exception as error:  # noqa: BLE001
        return {'error': type(error).__name__}
    if not isinstance(reading, dict):
        return {'error': 'not a JSON object'}
    return {key: reading.get(key) for key in ('ready', 'simulator', 'live_configuration', 'provider_access')}


def clock_drift(store, since, worlds_dir=''):
    return fixed.clock_drift(store, since, worlds_dir)


def claim(out, manifest_path, manifest):
    """Create the run record exclusively, right after the re-run guard and before the slow
    ingestion check, so two launches cannot both pass the guard."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        with open(manifest_path, 'x', encoding='utf-8') as handle:
            handle.write(json.dumps(manifest, indent=2) + '\n')
    except FileExistsError:
        raise SystemExit(f'{manifest_path} was created by another launch; refusing to overwrite it') from None
    others = [q for q in out.parent.glob('phase24-*/heldout-manifest.json') if q != manifest_path]
    if others:
        manifest_path.unlink()
        raise SystemExit(f'Another Phase 24 run exists ({others[0]}); continue that one with --resume')


# ---------------------------------------------------------------- main loop

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--out', required=True, help='artifacts/phase24-<date>')
    parser.add_argument('--store', default=str(ROOT / 'artifacts/lab.sqlite3'))
    parser.add_argument('--worlds-dir', default='', help="for the drift check (default: the store's sibling 'worlds')")
    parser.add_argument('--settings')
    parser.add_argument('--expect-freeze')
    parser.add_argument('--review-record', help='the approved review record (PHASE24_EXPERIMENT.md section 9 step 0)')
    parser.add_argument('--headroom', type=float, default=worst_case_dollars(),
                        help=f'hard worst case per attempt: {WORST_CASE_CALLS_PER_ATTEMPT} calls '
                             f'= ${worst_case_dollars():.2f} at ${DECLARED_ACTOR_CALL_BOUND}/call; never lower')
    parser.add_argument('--check-timeout', type=float, default=7200.0)
    parser.add_argument('--idle-grace', type=float, default=900.0)
    parser.add_argument('--poll', type=float, default=5.0)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--after-abort', action='store_true',
                        help='continue a run that stopped early; only with the user\'s explicit approval')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    args = parser.parse_args()

    worst = worst_case_dollars()
    print('policy     routed by rule from the one Phase 23 record: first new certified hash by attempt order, '
          f'excluding {EXCLUDED_POLICY_HASHES[0][:8]}…; the Phase 23 run must be final and routable')
    print(f'partition  {PARTITION} (sealed, never opened; 5 fault cases x 5 replicas x 3 pairs + no-fault x 1 x 3 '
          f'= {PLANNED_PAIRS} pairs, {PLANNED_EPISODES} episodes), Actor context v4')
    print(f'verdict    {PREDICATE}: first attempt with NO_HARM or HARM is final; at most {MAX_ATTEMPTS} attempts '
          f'(held-out checks the backend holds for the policy)')
    print(f'spend      guard ${SPEND_CAP:.2f} (conservative bound, a constant); worst case per attempt '
          f'{WORST_CASE_CALLS_PER_ATTEMPT} calls = ${worst:.2f}; an attempt starts only while charged + '
          f'${args.headroom:.2f} <= cap, so {int(SPEND_CAP // args.headroom) if args.headroom > 0 else 0} '
          f'attempt(s) are guaranteed and each later one needs the total so far <= '
          f'${SPEND_CAP - args.headroom:.2f}')
    print('runbook    before: check_ingestion_health and /api/readiness (run and RECORDED by this runner, never a '
          'refusal); after: check_clock_drift --worlds --since <run start> (run by this runner)')
    print('never      accept, activate, tune, or show the partition to any model')
    missing = unfilled_pins()
    if missing:
        print('pins       NOT FILLED (live runs refused until the Phase 22 freeze fills them): ' + ', '.join(missing))
    if args.plan or not args.execute_live:
        for row in pin_status(args):
            print(f"pin        {row['pin']:<48} {row['state']:<11} declared {str(row['declared'])[:16]}"
                  + (f"  on disk {row['current'][:16]}" if row.get('current') else ''))
        print('Dry plan only. Pass --execute-live --confirm-entity ENTITY --review-record FILE to run.')
        return 0

    # ---- everything below until the backend checks needs no HTTP call
    problems = pin_problems()
    if problems:
        raise SystemExit('Refusing to run: pins still hold placeholders or are malformed: ' + ', '.join(problems))
    out = ROOT / args.out
    if out.parent != ROOT / 'artifacts' or not out.name.startswith('phase24-'):
        raise SystemExit('--out must be artifacts/phase24-<date>')
    manifest_path = out / 'heldout-manifest.json'
    others = [q for q in out.parent.glob('phase24-*/heldout-manifest.json') if q != manifest_path]
    if others:
        raise SystemExit(f'Another Phase 24 run exists ({others[0]}); continue that one with --resume, '
                         f'never in a new folder')
    if args.resume and not manifest_path.exists():
        raise SystemExit(f'{manifest_path} does not exist; nothing to resume')
    if not args.resume and manifest_path.exists():
        raise SystemExit(f'{manifest_path} exists; refusing to overwrite a retained run record '
                         f'(continue it with --resume --after-abort, with the user\'s approval)')
    for flag in ('settings', 'expect_freeze', 'review_record'):
        if not getattr(args, flag):
            raise SystemExit(f'--{flag.replace("_", "-")} is required for a live run')
    for refusal, path, declared_sha in file_pins(args):
        if not pathlib.Path(path).is_file() or base.sha256_file(path) != declared_sha:
            raise SystemExit(refusal)
    expected_freeze = json.loads((ROOT / args.expect_freeze).read_text())
    if expected_freeze['functions'].get(base.ASSESS_PAIRS_KEY, {}).get('text_sha256') != base.ASSESS_PAIRS_TEXT_SHA256:
        raise SystemExit('The declared freeze does not contain the unchanged assess_pairs')
    if base.gate_freeze() != expected_freeze:
        raise SystemExit('Code on disk differs from the reviewed freeze')
    from app.config import Settings
    overrides = json.loads((ROOT / args.settings).read_text())
    os.environ.update({k: str(v) for k, v in overrides.items() if v != ''})
    settings = Settings.from_env()
    if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
        raise SystemExit('--confirm-entity must match WANDB_ENTITY in the settings file')
    if settings.project_path != base.EXPECTED_PROJECT:
        raise SystemExit('Settings project is not the declared one')
    bound = (settings.model_call_dollar_bounds or {}).get('actor')
    if bound is None:
        raise SystemExit('The settings give no conservative Actor call bound; the worst case cannot be computed')
    worst = worst_case_dollars(bound)
    if args.headroom < worst:
        raise SystemExit(f'--headroom ${args.headroom:.2f} is below the hard worst case per attempt ${worst:.2f}')
    try:
        routing = load_routing(args.store)
    except RoutingError as error:
        raise SystemExit(f'Routing refused: {error}')
    runner_sha = base.sha256_file(__file__)
    problem = review_problem(ROOT / args.review_record, runner_sha, routing)
    if problem:
        raise SystemExit(f'Refusing a live run: {problem}')
    declared = {'schema_version': SCHEMA, 'phase': 24, 'predicate': PREDICATE, 'partition': PARTITION,
                'partition_dir': DECLARED_PARTITION_DIR, 'manifest_hash': DECLARED_PARTITION_MANIFEST_HASH,
                'planned_pairs': PLANNED_PAIRS, 'planned_episodes': PLANNED_EPISODES, 'max_attempts': MAX_ATTEMPTS,
                'spend_cap': SPEND_CAP, 'headroom': args.headroom,
                'worst_case_calls_per_attempt': WORST_CASE_CALLS_PER_ATTEMPT, 'worst_case_per_attempt': worst,
                'actor_call_bound': bound, 'configuration_hash': DECLARED_CONFIGURATION_HASH,
                'freeze_sha256': DECLARED_FREEZE_SHA256, 'runner_sha256': runner_sha,
                'base_runner_sha256': DECLARED_BASE_RUNNER_SHA256, 'phase23_runner_sha256': DECLARED_PHASE23_RUNNER_SHA256,
                'protocol_sha256': DECLARED_PROTOCOL_SHA256, 'settings_sha256': DECLARED_SETTINGS_SHA256,
                'drift_checker_sha256': fixed.DECLARED_DRIFT_CHECKER_SHA256,
                'ingestion_check_sha256': fixed.DECLARED_INGESTION_CHECK_SHA256,
                'review_record_sha256': base.sha256_file(ROOT / args.review_record),
                'routing': {key: routing[key] for key in ('attempt', 'study_id', 'policy_hash', 'phase23_manifest',
                                                          'phase23_manifest_sha256')}}
    previous = None
    if args.resume:
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('declared') != declared:
            raise SystemExit('Resume refused: the declared parameters, pins, code, runner, routing or review record '
                             'differ from the run on record')
        previous = manifest.get('stop_reason')
        if previous in FINAL_STOPS:
            raise SystemExit(f'Resume refused: the run ended with {previous!r}, which is final')
        if not args.after_abort:
            raise SystemExit(f'Resume refused: the last session ended with {previous!r}; continuing needs the '
                             f'user\'s approval (--after-abort)')
        mismatched = [r['attempt'] for r in manifest['attempts'] if r.get('identity_mismatch')]
        if mismatched:
            raise SystemExit(f'Resume refused: attempt {mismatched[0]} started a check that is not the declared one; '
                             f'the review decides what happens next')

    # ---- the backend
    process = base.check_backend_process()
    status = base.check_backend(args.base)
    if status.get('active_campaign_id'):
        raise SystemExit('Another execution is active; refusing to start')
    if not args.resume:
        manifest = {'schema_version': SCHEMA, 'declared': declared, 'routing': routing,
                    'certified_study': routing['study_id'], 'policy_hash': routing['policy_hash'],
                    'predicate': PREDICATE, 'partition': PARTITION, 'partition_dir': DECLARED_PARTITION_DIR,
                    'manifest_hash': DECLARED_PARTITION_MANIFEST_HASH, 'planned_pairs': PLANNED_PAIRS,
                    'planned_episodes': PLANNED_EPISODES, 'max_attempts': MAX_ATTEMPTS, 'spend_cap': SPEND_CAP,
                    'headroom': args.headroom, 'worst_case_calls_per_attempt': WORST_CASE_CALLS_PER_ATTEMPT,
                    'worst_case_per_attempt': worst, 'actor_call_bound': bound,
                    'configuration_hash': DECLARED_CONFIGURATION_HASH, 'freeze_sha256': DECLARED_FREEZE_SHA256,
                    'runner_sha256': runner_sha, 'base_runner_sha256': DECLARED_BASE_RUNNER_SHA256,
                    'protocol_sha256': DECLARED_PROTOCOL_SHA256, 'backend_process': process,
                    'started_at': datetime.now(timezone.utc).isoformat(), 'stop_reason': 'starting',
                    'campaigns': [], 'attempts': [], 'sessions': []}
        claim(out, manifest_path, manifest)
    # Recorded, never a refusal (review round 2): the ingestion check reads only the store's last
    # development 'ingestions' rows, and heldout-2's episodes (split promotion) never write one, so a
    # degraded reading left by earlier work could otherwise refuse every session of this phase for good.
    # The verdict needs no Weave. Readiness is recorded beside it; it does not contact the provider.
    ingestion = ingestion_health()
    ready = readiness(args.base)
    if ingestion.get('exit_status') != 0:
        print(f"note       check_ingestion_health.py exited {ingestion.get('exit_status')!r}; recorded, not a refusal "
              f"(heldout-2's episodes write no ingestion rows and the verdict needs no Weave)", flush=True)

    def save():
        temporary = manifest_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n')
        os.replace(temporary, manifest_path)
    campaigns = manifest['campaigns']
    policy = routing['policy_hash']

    def copy_check(entry, record):
        entry.update(status=record.get('status'), decision=record.get('decision'), reason=record.get('reason'),
                     error_type=record.get('error_type'), batch_id=record.get('batch_id'),
                     trials=record.get('trials'), pairs=record.get('pairs'),
                     candidate_failures=record.get('candidate_failures'), assessment=record.get('assessment'),
                     untriggered_by_case=untriggered_by_case(record.get('assessment')))
        save()

    def declared_identity(campaign_id):
        return (campaign_id, policy, PREDICATE, base.ACTOR_CONTEXT, PARTITION, routing['study_id'],
                DECLARED_PARTITION_MANIFEST_HASH, PLANNED_PAIRS)

    def identity(record):
        return tuple(record.get(key) for key in ('campaign_id', 'policy_hash', 'predicate', 'actor_context_protocol',
                                                 'partition', 'certified_study_id', 'manifest_hash', 'planned_pairs'))

    def check_identity(entry, record):
        """Compare a check with the declared one, wherever the runner first sees it (its start reply, an
        adoption after a lost reply, the abort path, or resume). A match marks the row identity_checked;
        a mismatch marks it identity_mismatch and stops the check if it is still running. Either way a
        check that is not the declared one is never the run's verdict (is_verdict)."""
        if identity(record) == declared_identity(entry['campaign_id']):
            entry['identity_checked'] = True; save()
            return True
        entry['identity_mismatch'] = True; save()
        if record.get('status') not in TERMINAL:
            try:
                base.api(args.base, 'POST', f"/api/campaigns/{entry['campaign_id']}/stop", {}); entry['stop_requested'] = True
            except Exception as error:  # noqa: BLE001
                entry['stop_error'] = type(error).__name__
            save()
        return False

    def attempts_used():
        """The backend's held-out checks of the routed policy are the authority: they must be exactly
        the checks this run tracks, and their number is the attempts used."""
        stored = policy_checks(args.store, policy)
        tracked = {r['check_id'] for r in manifest['attempts'] if r.get('check_id')}
        if set(stored) != tracked:
            raise base.PhaseAbort(f'the store holds {len(stored)} held-out check(s) of the routed policy and this run '
                                  f'tracks {len(tracked)}; they must be the same checks')
        return len(stored)

    def resolve(entry):
        """A row from an earlier session: label it, adopt its check, or read its check back."""
        if not entry.get('campaign_id'):
            entry.setdefault('error', INTERRUPTED_BEFORE_CREATE)
            return
        if not entry.get('check_id'):
            try:
                seen = base.api(args.base, 'GET', f"/api/campaigns/{entry['campaign_id']}/heldout-checks")
            except Exception as error:  # noqa: BLE001
                raise base.PhaseAbort(f"attempt {entry['attempt']}: its campaign's checks cannot be listed "
                                      f"({type(error).__name__})")
            if len(seen) > 1:
                raise base.PhaseAbort(f"attempt {entry['attempt']}: more than one check on its campaign")
            if not seen:
                entry.setdefault('error', NO_CHECK_CREATED)
                return
            entry['check_id'] = seen[0]['check_id']; entry['adopted_on_resume'] = True
        # A terminal row is final only once its check was compared with the declared one; a check
        # adopted in an earlier abort path (or whose comparison never ran) is compared here, even
        # though it has ended (review round 2).
        if entry.get('status') in TERMINAL and entry.get('identity_checked') is True:
            return
        try:
            record = base.api(args.base, 'GET', f"/api/heldout-checks/{entry['check_id']}")
        except Exception as error:  # noqa: BLE001
            raise base.PhaseAbort(f"attempt {entry['attempt']}: its check cannot be read ({type(error).__name__})")
        if not check_identity(entry, record):
            raise base.PhaseAbort(f"attempt {entry['attempt']}: its check is not the declared check")
        if record.get('status') not in TERMINAL:
            raise base.PhaseAbort(f"attempt {entry['attempt']}: check {entry['check_id']} is still "
                                  f"{record.get('status')}; wait for it to end")
        copy_check(entry, record)
        base.record_charge(args.base, entry['campaign_id'], entry, save)

    if args.resume:
        try:
            for entry in manifest['attempts']:
                resolve(entry)
            attempts_used()
        except base.PhaseAbort as error:
            save()
            raise SystemExit(f'Resume refused: {error}')
    # An earlier session's notes about a check it could not see end are resolved above; they move
    # into this session's record so they cannot skip this session's drift check.
    carried = {key: manifest.pop(key) for key in ('check_left_running', 'check_state_unknown', 'unresolved_checks')
               if key in manifest}
    manifest['sessions'].append({'started_at': datetime.now(timezone.utc).isoformat(), 'after_abort': bool(args.after_abort),
                                 'previous_stop': previous, 'previous_abort_detail': manifest.pop('abort_detail', None),
                                 'previous_session_notes': carried, 'backend_process': process,
                                 'ingestion_health': ingestion, 'readiness': ready})
    manifest['ingestion_health'] = ingestion           # the latest session's reading; each session keeps its own
    manifest['readiness'] = ready
    manifest['stop_reason'] = 'running'
    save()
    stop_reason = None
    operator_stop = False
    request = {'execute_live': True, 'certified_study_id': routing['study_id'], 'partition_dir': DECLARED_PARTITION_DIR,
               'manifest_hash': DECLARED_PARTITION_MANIFEST_HASH, 'predicate': PREDICATE}

    def detach(signum, frame):
        import signal as sig
        for s_ in (sig.SIGTERM, sig.SIGHUP):
            sig.signal(s_, sig.SIG_IGN)
        raise Detached(signum)
    import signal
    signal.signal(signal.SIGTERM, detach)
    if signal.getsignal(signal.SIGHUP) is not signal.SIG_IGN:  # respect nohup
        signal.signal(signal.SIGHUP, detach)

    try:
        while True:
            rows = manifest['attempts']
            if any(is_verdict(r) for r in rows):
                stop_reason = 'verdict'; break
            if attempts_used() >= MAX_ATTEMPTS:
                stop_reason = 'attempt_cap'; break
            charged = base.total_spend(args.base, campaigns)
            if charged + args.headroom > SPEND_CAP:
                stop_reason = 'spend_guard'; break
            base.check_backend(args.base)
            if base.check_backend_process() != process:
                raise base.PhaseAbort('backend process changed during the run')
            if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                raise base.PhaseAbort('backend is not idle')
            entry = {'attempt': len(rows) + 1, 'campaign_id': None, 'check_id': None, 'spent_before': charged}
            rows.append(entry); save()
            try:
                campaign = base.api(args.base, 'POST', '/api/campaigns', {
                    'task_text': base.TASK_TEXT, 'order_id': base.ORDER_ID, 'mode': 'baseline',
                    'config_profile_id': 'live-v1'})
            except Exception as error:  # noqa: BLE001
                entry['error'] = f'campaign create: {type(error).__name__}'; save()
                raise base.PhaseAbort('campaign create failed (no check started)')
            cid = campaign['campaign_id']
            campaigns.append(cid); entry['campaign_id'] = cid
            entry['configuration_hash'] = campaign.get('configuration_hash'); save()
            if entry['configuration_hash'] != DECLARED_CONFIGURATION_HASH:
                entry['error'] = 'configuration_hash mismatch (no check started)'; save()
                raise base.PhaseAbort(f"configuration_hash {entry['configuration_hash']} != declared")
            try:
                base.check_campaign_in_store(args.store, cid)
            except base.PhaseAbort:
                entry['error'] = 'store or Aria check failed (no check started)'; save()
                raise
            try:
                started = base.api(args.base, 'POST', f"/api/campaigns/{cid}/heldout-check", request)
            except Exception as error:  # noqa: BLE001
                # The server may have started it although the reply was lost, possibly after a
                # delay (coordinator lock, simulator readiness). An HTTP 4xx is a refusal: nothing
                # started. Anything else: look for up to 60 s, tolerating read errors.
                entry['start_error'] = type(error).__name__; save()
                existing = []
                if getattr(error, 'code', 500) >= 500:
                    until = time.monotonic() + 60
                    while True:
                        try:
                            existing = base.api(args.base, 'GET', f'/api/campaigns/{cid}/heldout-checks')
                        except Exception:  # noqa: BLE001
                            existing = []
                        if existing or time.monotonic() > until:
                            break
                        time.sleep(max(args.poll, 1))
                if len(existing) != 1:
                    entry['error'] = f'check start: {entry["start_error"]}; {len(existing)} checks seen'; save()
                    raise base.PhaseAbort('a check start failed and could not be resolved')
                started = existing[0]; entry['adopted_after_start_error'] = True
            entry['check_id'] = started['check_id']; save()
            if not check_identity(entry, started):
                # Never let a check the runner rejects run on and spend, or become the verdict.
                raise base.PhaseAbort('the started check is not the declared check; it was stopped if still running '
                                      'and is never the verdict')
            deadline = time.monotonic() + args.check_timeout
            record, failing_since = started, None
            while record.get('status') not in TERMINAL:
                if time.monotonic() > deadline:
                    raise base.PhaseAbort('check timeout; the check is left running and its verdict stays in the store')
                time.sleep(args.poll)
                try:
                    record = base.api(args.base, 'GET', f"/api/heldout-checks/{started['check_id']}"); failing_since = None
                except Exception:  # noqa: BLE001
                    failing_since = failing_since or time.monotonic()
                    if time.monotonic() - failing_since > 300:
                        raise base.PhaseAbort('lost contact with a running check; it is left running')
            copy_check(entry, record)
            base.record_charge(args.base, cid, entry, save)
            if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                raise base.PhaseAbort('a finished check is still holding the coordinator')
            print(f"[attempt {entry['attempt']}] {entry['status']}/{entry['decision']} | {entry['reason']} | "
                  f"untriggered by case (B0, L): {entry['untriggered_by_case']}", flush=True)
    except base.PhaseAbort as error:
        stop_reason = 'aborted'; manifest['abort_detail'] = str(error)
        print(f'\nABORTED: {error}', flush=True)
    except Detached as signal_error:
        stop_reason = 'aborted'; manifest['abort_detail'] = f'signal {signal_error.args[0]}; any running check left running'
    except KeyboardInterrupt:
        stop_reason = 'aborted'; operator_stop = True; manifest['abort_detail'] = 'interrupted by operator'
    except Exception as error:  # noqa: BLE001
        stop_reason = 'aborted'; manifest['abort_detail'] = f'{type(error).__name__}: {error}'
        print(f'\nABORTED: {manifest["abort_detail"]}', flush=True)
    if stop_reason == 'aborted':
        # Recorded at once, before any wait below: a second signal must not lose the reason.
        for entry in manifest['attempts']:
            if not entry.get('campaign_id') and not entry.get('error'):
                entry['error'] = INTERRUPTED_BEFORE_CREATE
        manifest['stop_reason'] = stop_reason; save()
    if stop_reason == 'aborted' and campaigns:
        last = manifest['attempts'][-1] if manifest['attempts'] else {}
        status = base.backend_status(args.base)
        # Only the held-out POST makes this campaign active, so an active campaign means a
        # check exists. It is only ever stopped by the operator's Ctrl-C (or, above, when it is
        # not the declared check); otherwise it runs on and its verdict (possibly final) is read
        # back below.
        if operator_stop and (status or {}).get('active_campaign_id') == campaigns[-1]:
            try:
                base.api(args.base, 'POST', f'/api/campaigns/{campaigns[-1]}/stop', {})
            except Exception:  # noqa: BLE001
                pass
        if last.get('campaign_id') and not last.get('check_id'):
            try:
                seen = base.api(args.base, 'GET', f"/api/campaigns/{last['campaign_id']}/heldout-checks")
                if len(seen) == 1:
                    last['check_id'] = seen[0]['check_id']; last['adopted_after_abort'] = True; save()
                    check_identity(last, seen[0])      # review round 2: an adopted check is compared too
                elif seen:
                    manifest['unresolved_checks'] = [x.get('check_id') for x in seen]; save()
            except Exception:  # noqa: BLE001
                manifest['check_state_unknown'] = last['campaign_id']; save()
        elif last.get('check_id') and last.get('identity_checked') is not True and not last.get('identity_mismatch'):
            # The start reply arrived but the stop came before it was compared: compare it now if the
            # check can be read; otherwise it is compared on resume (resolve) before it can count.
            try:
                check_identity(last, base.api(args.base, 'GET', f"/api/heldout-checks/{last['check_id']}"))
            except Exception:  # noqa: BLE001
                pass
        if last.get('check_id') and base.wait_until_idle(args.base, args.idle_grace, args.poll):
            try:
                copy_check(last, base.api(args.base, 'GET', f"/api/heldout-checks/{last['check_id']}"))
            except Exception:  # noqa: BLE001
                pass
        elif last.get('check_id'):
            manifest['check_left_running'] = last['check_id']
    manifest['stop_reason'] = stop_reason
    # A check the runner rejected, or never compared with the declared one, is never the run's verdict.
    verdicts = [r for r in manifest['attempts'] if is_verdict(r)]
    manifest['verdict'] = verdicts[0]['decision'] if verdicts else None
    manifest['attempts_used'] = sum(1 for r in manifest['attempts'] if r.get('check_id'))
    try:
        manifest['total_charged_upper_bound'] = base.total_spend(args.base, campaigns)
    except base.PhaseAbort as error:
        manifest['total_charged_upper_bound'] = None; manifest['total_charged_error'] = str(error)
    now = datetime.now(timezone.utc).isoformat()
    manifest['sessions'][-1].update(ended_at=now, stop_reason=stop_reason, abort_detail=manifest.get('abort_detail'))
    manifest['ended_at'] = now
    save()
    if manifest.get('check_left_running') or manifest.get('check_state_unknown') or manifest.get('unresolved_checks'):
        drift = {'skipped': 'a check may still be running; run the command after it ends',
                 'command': f"scripts/experiments/check_clock_drift.py --since {manifest['started_at']} --worlds --require-worlds"}
    else:
        try:
            drift = clock_drift(args.store, manifest['started_at'], args.worlds_dir)
        except Exception as error:  # noqa: BLE001
            drift = {'error': type(error).__name__, 'exit_status': None}
    manifest['sessions'][-1]['clock_drift'] = drift
    manifest['clock_drift'] = drift
    save()
    print(f"\n{stop_reason} | verdict {manifest['verdict']} | {len(manifest['attempts'])} rows, "
          f"{manifest['attempts_used']} attempts used | charged "
          f"${manifest['total_charged_upper_bound'] if manifest['total_charged_upper_bound'] is not None else float('nan'):.5f}")
    print(f"clock drift: {drift.get('drifted', drift.get('skipped') or drift.get('error'))}")
    print(f'manifest {manifest_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
