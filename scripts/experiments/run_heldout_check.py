"""Phase 18: one declared held-out no-harm check of Phase 17's certified completion repair.

The certified policy is run, paired against the empty baseline, on the six-case private
promotion partition (3 trials per case, 36 episodes) through the project's own
PairedEvaluator, with the v4 Actor context. It is judged by the declared no-harm predicate
in backend/app/lab/heldout_check.py (docs/part2/PHASE18_EXPERIMENT.md).

Declared design: at most MAX_ATTEMPTS attempts. The first attempt that reaches a verdict
(NO_HARM or HARM) ends the run and is final. Only an attempt that reached no verdict
(INCOMPLETE: an untriggered fault, an infrastructure failure, a stop) is replaced, and any
candidate check failure in any attempt is already HARM. Nothing is ever called ACCEPTED.

Dry by default. `--execute-live` plus a matching `--confirm-entity` is required to run.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_full_loop as base  # the reviewed Phase 17 guards; nothing in it is modified

ROOT = base.ROOT
SCHEMA = 'faultlab-heldout-run/v1'
CERTIFIED_STUDY = 'completion-study-2c2a11971fce4884a382c875bebb87f1'
CERTIFIED_POLICY_HASH = 'dd62c85780f8226a6c199d28c346ea579a3c2ad02a1db7c905cf3c3c2b45d521'
PREDICATE = 'faultlab-heldout-no-harm/v1'
MAX_ATTEMPTS = 3
VERDICTS = ('NO_HARM', 'HARM')
TERMINAL = ('COMPLETED', 'INCOMPLETE', 'INTERRUPTED')
# Pins declared in docs/part2/PHASE18_EXPERIMENT.md (filled in after the last code edit).
DECLARED_FREEZE_SHA256 = '3619a4aa2daca4ecb795bf888ab58273e6df146adcea22df4927d85217259444'
DECLARED_CONFIGURATION_HASH = '1b6e5ed0a17d79001f0f5b40b7ed7de5964f102b2303943c516dbe560eff7894'
DECLARED_SETTINGS_SHA256 = base.DECLARED_SETTINGS_SHA256
# The reused Phase 17 guards are pinned too: 'unchanged' is enforced, not asserted.
DECLARED_BASE_RUNNER_SHA256 = '07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342'


class Detached(BaseException):
    """SIGTERM/SIGHUP: leave any running check alone; its verdict stays in the store."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--out', required=True, help='artifacts/phase18-<date>')
    parser.add_argument('--store', default=str(ROOT / 'artifacts/lab.sqlite3'))
    parser.add_argument('--settings')
    parser.add_argument('--expect-freeze')
    parser.add_argument('--spend-cap', type=float, default=25.0)
    parser.add_argument('--headroom', type=float, default=12.05,
                        help='worst case per check: 288 reserved + 16 per lab-error pair retry = 576 calls = $12.04')
    parser.add_argument('--check-timeout', type=float, default=3600.0)
    parser.add_argument('--idle-grace', type=float, default=900.0)
    parser.add_argument('--poll', type=float, default=5.0)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    args = parser.parse_args()

    print(f'policy     {CERTIFIED_POLICY_HASH[:16]}… from {CERTIFIED_STUDY}')
    print('partition  promotion (private, 6 cases x 3 trials x 2 arms = 36 episodes), Actor context v4')
    print(f'verdict    {PREDICATE}: first attempt with NO_HARM or HARM is final; at most {MAX_ATTEMPTS} attempts')
    print(f'spend      guard ${args.spend_cap:.2f} (conservative bound), headroom ${args.headroom:.2f}')
    print('never      accept, activate, tune, or show the partition to any model')
    if args.plan or not args.execute_live:
        print('Dry plan only. Pass --execute-live --confirm-entity ENTITY to run.')
        return 0

    out = ROOT / args.out
    if out.parent != ROOT / 'artifacts' or not out.name.startswith('phase18-'):
        raise SystemExit('--out must be artifacts/phase18-<date>')
    manifest_path = out / 'heldout-manifest.json'
    if manifest_path.exists():
        raise SystemExit(f'{manifest_path} exists; refusing to overwrite a retained run record')
    others = [q for q in out.parent.glob('phase18-*/heldout-manifest.json') if q != manifest_path]
    if others:
        raise SystemExit(f'Another Phase 18 run exists ({others[0]}); the backend keeps the per-policy '
                         f'attempt count and verdict, continue only with the user\'s approval')
    if not args.settings or not args.expect_freeze:
        raise SystemExit('--settings and --expect-freeze are required for a live run')
    if base.sha256_file(HERE / 'run_full_loop.py') != DECLARED_BASE_RUNNER_SHA256:
        raise SystemExit('run_full_loop.py is not the reviewed Phase 17 runner')
    if base.sha256_file(HERE / 'gate_freeze.py') != base.DECLARED_GATE_FREEZE_SCRIPT_SHA256:
        raise SystemExit('gate_freeze.py is not the reviewed script')
    if base.sha256_file(ROOT / args.settings) != DECLARED_SETTINGS_SHA256:
        raise SystemExit('The settings file is not the declared one')
    freeze_path = ROOT / args.expect_freeze
    if base.sha256_file(freeze_path) != DECLARED_FREEZE_SHA256:
        raise SystemExit('The freeze file is not the one declared in the protocol')
    expected_freeze = json.loads(freeze_path.read_text())
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
    process = base.check_backend_process()
    status = base.check_backend(args.base)
    if status.get('active_campaign_id'):
        raise SystemExit('Another execution is active; refusing to start')
    study = base.store_records(args.store, 'completion_studies', [CERTIFIED_STUDY]).get(CERTIFIED_STUDY)
    if study is None or not base.certified(study) or study.get('selected_candidate_hash') != CERTIFIED_POLICY_HASH:
        raise SystemExit('The certified study is missing or no longer meets the certification rule')

    out.mkdir(parents=True, exist_ok=True)
    manifest = {'schema_version': SCHEMA, 'certified_study': CERTIFIED_STUDY, 'policy_hash': CERTIFIED_POLICY_HASH,
                'predicate': PREDICATE, 'max_attempts': MAX_ATTEMPTS, 'spend_cap': args.spend_cap,
                'configuration_hash': DECLARED_CONFIGURATION_HASH, 'freeze_sha256': DECLARED_FREEZE_SHA256,
                'runner_sha256': base.sha256_file(__file__), 'backend_process': process,
                'protocol_sha256': base.sha256_file(ROOT / 'docs/part2/PHASE18_EXPERIMENT.md'),
                'started_at': datetime.now(timezone.utc).isoformat(), 'stop_reason': 'running',
                'campaigns': [], 'attempts': []}

    def save():
        temporary = manifest_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n')
        os.replace(temporary, manifest_path)
    save()
    campaigns = manifest['campaigns']
    stop_reason = None
    operator_stop = False

    def detach(signum, frame):
        import signal as sig
        for s_ in (sig.SIGTERM, sig.SIGHUP):
            sig.signal(s_, sig.SIG_IGN)
        raise Detached(signum)
    import signal
    signal.signal(signal.SIGTERM, detach)
    if signal.getsignal(signal.SIGHUP) is not signal.SIG_IGN:  # respect nohup
        signal.signal(signal.SIGHUP, detach)

    def copy_check(entry, record):
        entry.update(status=record.get('status'), decision=record.get('decision'), reason=record.get('reason'),
                     error_type=record.get('error_type'), batch_id=record.get('batch_id'),
                     trials=record.get('trials'), pairs=record.get('pairs'),
                     candidate_failures=record.get('candidate_failures'), assessment=record.get('assessment'))
        save()

    try:
        while True:
            rows = manifest['attempts']
            if any(r.get('decision') in VERDICTS for r in rows):
                stop_reason = 'verdict'; break
            if len(rows) >= MAX_ATTEMPTS:
                stop_reason = 'attempt_cap'; break
            charged = base.total_spend(args.base, campaigns)
            if charged + args.headroom > args.spend_cap:
                stop_reason = 'spend_guard'; break
            base.check_backend(args.base)
            if base.check_backend_process() != process:
                raise base.PhaseAbort('backend process changed during the run')
            if not base.wait_until_idle(args.base, args.idle_grace, args.poll):
                raise base.PhaseAbort('backend is not idle')
            entry = {'attempt': len(rows) + 1, 'campaign_id': None, 'check_id': None, 'spent_before': charged}
            rows.append(entry); save()
            campaign = base.api(args.base, 'POST', '/api/campaigns', {
                'task_text': base.TASK_TEXT, 'order_id': base.ORDER_ID, 'mode': 'baseline', 'config_profile_id': 'live-v1'})
            cid = campaign['campaign_id']
            campaigns.append(cid); entry['campaign_id'] = cid
            entry['configuration_hash'] = campaign.get('configuration_hash'); save()
            if entry['configuration_hash'] != DECLARED_CONFIGURATION_HASH:
                entry['error'] = 'configuration_hash mismatch (no check started)'; save()
                raise base.PhaseAbort(f"configuration_hash {entry['configuration_hash']} != declared")
            base.check_campaign_in_store(args.store, cid)
            try:
                started = base.api(args.base, 'POST', f"/api/campaigns/{cid}/heldout-check",
                                   {'execute_live': True, 'certified_study_id': CERTIFIED_STUDY})
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
                    entry['error'] = f'study start: {entry["start_error"]}; {len(existing)} checks seen'; save()
                    raise base.PhaseAbort('a check start failed and could not be resolved')
                started = existing[0]; entry['adopted_after_start_error'] = True
            entry['check_id'] = started['check_id']; save()
            if (started.get('campaign_id'), started.get('policy_hash'), started.get('predicate'),
                    started.get('actor_context_protocol'), started.get('partition'), started.get('certified_study_id')) != (
                    cid, CERTIFIED_POLICY_HASH, PREDICATE, base.ACTOR_CONTEXT, 'promotion', CERTIFIED_STUDY):
                raise base.PhaseAbort('the started check is not the declared check')
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
            print(f"[attempt {entry['attempt']}] {entry['status']}/{entry['decision']} | {entry['reason']}", flush=True)
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
    if stop_reason == 'aborted' and campaigns:
        manifest['stop_reason'] = stop_reason; save()      # recorded before any wait below
        last = manifest['attempts'][-1] if manifest['attempts'] else {}
        status = base.backend_status(args.base)
        # Only the held-out POST makes this campaign active, so an active campaign means a
        # check exists. It is only ever stopped by the operator's Ctrl-C; otherwise it runs on
        # and its verdict (possibly final) is read back below.
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
                elif seen:
                    manifest['unresolved_checks'] = [x.get('check_id') for x in seen]; save()
            except Exception:  # noqa: BLE001
                manifest['check_state_unknown'] = last['campaign_id']; save()
        if last.get('check_id') and base.wait_until_idle(args.base, args.idle_grace, args.poll):
            try:
                copy_check(last, base.api(args.base, 'GET', f"/api/heldout-checks/{last['check_id']}"))
            except Exception:  # noqa: BLE001
                pass
        elif last.get('check_id'):
            manifest['check_left_running'] = last['check_id']
    manifest['stop_reason'] = stop_reason
    verdicts = [r for r in manifest['attempts'] if r.get('decision') in VERDICTS]
    manifest['verdict'] = verdicts[0]['decision'] if verdicts else None
    try:
        manifest['total_charged_upper_bound'] = base.total_spend(args.base, campaigns)
    except base.PhaseAbort as error:
        manifest['total_charged_upper_bound'] = None; manifest['total_charged_error'] = str(error)
    manifest['ended_at'] = datetime.now(timezone.utc).isoformat()
    save()
    print(f"\n{stop_reason} | verdict {manifest['verdict']} | {len(manifest['attempts'])} attempts | "
          f"charged ${manifest['total_charged_upper_bound'] if manifest['total_charged_upper_bound'] is not None else float('nan'):.5f}")
    print(f'manifest {manifest_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
