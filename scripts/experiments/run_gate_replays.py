"""Phase 10: replay one saved policy's validation batch N times to measure the GATE.

Each replay runs the frozen seven-case x three-trial paired validation batch (42 episodes:
21 candidate-arm, 21 baseline-arm, on identical cases) for an already-decided policy,
through the unchanged execute_slots and assess_pairs. No Mechanic call is made, no
candidate is created, and nothing can be accepted or activated. The replayed policy's own
saved decision is never rewritten.

Predeclared primary read-out: of N replays, how many return OBSERVED_IMPROVEMENT - the
gate's own pass verdict? That estimates how often the gate rejects a repair already shown
to work, for reasons unrelated to the repair.

Dry by default. `--execute-live` plus a matching `--confirm-entity` is required to run.

Usage:
  python scripts/experiments/run_gate_replays.py --plan
  python scripts/experiments/run_gate_replays.py --execute-live --confirm-entity ENTITY
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

# The Phase 9 candidate: the only policy in the store ever to pass the source gate.
DEFAULT_POLICY = 'policy-d2b12ec1325742f5ac1428ec28f19639'
# Replay makes no Mechanic call, so pinning the Mechanic proves nothing. Every one of
# these episodes is produced by the ACTOR, which is the model this phase depends on.
EXPECTED_ACTOR = 'deepseek-ai/DeepSeek-V3.1'
EXPECTED_MECHANIC = 'deepseek-ai/DeepSeek-V4-Pro-0813'
TASK_TEXT = 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'
ORDER_ID = 'order-1'
TERMINAL = ('COMPLETED', 'INCOMPLETE', 'INTERRUPTED')
PASS_VERDICT = 'OBSERVED_IMPROVEMENT'


class PhaseAbort(RuntimeError):
    """Raised when continuing would spend money blindly or against a wedged backend."""


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
            return float(budget.get('charged_dollar_upper_bound') or 0.0)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            if attempt == attempts - 1:
                raise PhaseAbort(f'Cannot read the budget for {campaign_id}; refusing to '
                                 f'continue spending with an unknown total')
            time.sleep(3)
    return 0.0


def total_spend(base, campaigns):
    return sum(campaign_spend(base, c) for c in campaigns)


def record_charge(base, campaign_id, entry, save):
    """Record spend as its own step, never as an argument to the update that saves a verdict.

    campaign_spend() raises PhaseAbort after its retries. When it was evaluated inline as
    `entry.update(..., charged=campaign_spend(...))`, Python evaluated the argument first,
    so that raise discarded the whole update AND the save with it: a replay the gate had
    already judged was recorded as unscored because a budget GET failed.
    """
    try:
        entry['charged'] = campaign_spend(base, campaign_id)
    except Exception as error:  # noqa: BLE001
        entry['charge_error'] = type(error).__name__
    save()


def wait_until_idle(base, seconds, poll):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if not api(base, 'GET', '/api/config/status').get('active_campaign_id'):
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(poll)
    return False


def check_backend(base):
    """Any failure here aborts rather than escaping as a bare URLError mid-loop."""
    try:
        status = api(base, 'GET', '/api/config/status')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise PhaseAbort(f'Cannot read backend status: {type(error).__name__}') from error
    if not status.get('live_enabled'):
        raise PhaseAbort('Backend is not live-enabled')
    models = status.get('models') or {}
    if models.get('actor') != EXPECTED_ACTOR:
        raise PhaseAbort(f'Backend Actor is {models.get("actor")!r}, phase declares '
                         f'{EXPECTED_ACTOR!r}; the Actor produces every replay episode')
    if models.get('mechanic') != EXPECTED_MECHANIC:
        raise PhaseAbort('Backend Mechanic model is not the one this phase declares')
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--settings',
                        default='artifacts/phase9-2026-09-20/settings-phase9-mechanic-v4.json')
    parser.add_argument('--policy', default=DEFAULT_POLICY)
    parser.add_argument('--actor-context-protocol', default=None,
                        help='Declared Actor context protocol; omit for the preserved v1')
    parser.add_argument('--replays', type=int, default=20, help='SCORED replays to target')
    parser.add_argument('--attempt-cap', type=int, default=26)
    parser.add_argument('--spend-cap', type=float, default=220.0)
    parser.add_argument('--headroom', type=float, default=10.0)
    parser.add_argument('--study-timeout', type=float, default=3600.0)
    parser.add_argument('--idle-grace', type=float, default=900.0)
    parser.add_argument('--consecutive-unscored-abort', type=int, default=4,
                        help='abort if this many attempts in a row yield no assessment')
    parser.add_argument('--poll', type=float, default=5.0)
    parser.add_argument('--out', default='artifacts/phase10-2026-09-21')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    print(f'policy     {args.policy}')
    print(f'replays    {args.replays} SCORED x 42 episodes (21 candidate-arm, 21 baseline-arm)')
    print(f'           attempt cap {args.attempt_cap}; a replay that produces no validation')
    print(f'           assessment observed nothing about the gate and is replaced, not scored')
    print(f'actor      {EXPECTED_ACTOR} (verified before every replay)')
    print(f'protocol   {args.actor_context_protocol or "faultlab-actor-context/v1 (preserved default)"}')
    print(f'read-out   how many SCORED replays return {PASS_VERDICT}')
    print(f'spend      guard ${args.spend_cap:.2f}, headroom ${args.headroom:.2f} per replay')
    print('mode       validation only: no Mechanic call, no proposal, no acceptance')
    if args.plan or not args.execute_live:
        print('Dry plan only. Pass --execute-live --confirm-entity ENTITY to run.')
        return 0

    from app.config import Settings
    overrides = json.loads((ROOT / args.settings).read_text())
    os.environ.update({k: str(v) for k, v in overrides.items() if v != ''})
    settings = Settings.from_env()
    if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
        raise SystemExit('--confirm-entity must match the configured W&B entity')

    status = check_backend(args.base)
    if status.get('active_campaign_id'):
        raise SystemExit('Another execution is active; refusing to start')

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / 'replay-manifest.json'
    if manifest_path.exists() and not args.force:
        raise SystemExit(f'{manifest_path} exists; refusing to overwrite a retained run record')

    manifest = {'schema_version': 'faultlab-gate-replay/v2', 'policy_version': args.policy,
                'scored_replays_declared': args.replays, 'attempt_cap': args.attempt_cap,
                'pass_verdict': PASS_VERDICT, 'expected_actor': EXPECTED_ACTOR,
                'models': status.get('models'), 'spend_cap': args.spend_cap,
                'consecutive_unscored_abort': args.consecutive_unscored_abort,
                'actor_context_protocol': args.actor_context_protocol, 'replays': []}

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

    campaigns = []
    aborted = None
    attempts = 0
    # Circuit breaker. Phase 12 burned 28 attempts while W&B Weave ingestion was degraded
    # (31% of episodes failed to verify, so no 42-episode batch could ever complete). A run
    # that cannot produce a scored result should stop and say so, not spend to its cap.
    consecutive_unscored = 0
    try:
        while True:
            scored_now = [r for r in manifest['replays'] if r.get('validation_decision')]
            if len(scored_now) >= args.replays or attempts >= args.attempt_cap:
                break
            charged = total_spend(args.base, campaigns)
            if charged + args.headroom > args.spend_cap:
                aborted = (f'spend guard: ${charged:.5f} + ${args.headroom:.2f} headroom '
                           f'exceeds ${args.spend_cap:.2f}')
                raise PhaseAbort(aborted)
            status = check_backend(args.base)
            if status.get('active_campaign_id'):
                if not wait_until_idle(args.base, args.idle_grace, args.poll):
                    aborted = 'backend is not idle; refusing to start another replay'
                    raise PhaseAbort(aborted)
            attempts += 1
            entry = {'attempt': attempts, 'campaign_id': None, 'study_id': None,
                     'spent_before': charged}
            manifest['replays'].append(entry); save()
            print(f'[attempt {attempts}] scored {len(scored_now)}/{args.replays} '
                  f'(spent ${charged:.5f})', flush=True)

            try:
                campaign = api(args.base, 'POST', '/api/campaigns', {
                    'task_text': TASK_TEXT, 'order_id': ORDER_ID,
                    'mode': 'baseline', 'config_profile_id': 'live-v1'})
            except Exception as error:  # noqa: BLE001
                entry['error'] = f'campaign create: {type(error).__name__}: {error}'; save()
                print(f'[attempt {attempts}] {entry["error"]}', flush=True)
                continue
            # Registered BEFORE the study starts, so a campaign that is created and then
            # fails to start still counts against the spend guard and stays in the record.
            campaigns.append(campaign['campaign_id'])
            entry['campaign_id'] = campaign['campaign_id']; save()

            try:
                started = api(args.base, 'POST',
                              f"/api/campaigns/{campaign['campaign_id']}/completion-study",
                              {'execute_live': True, 'replay_policy_version': args.policy,
                               **({'actor_context_protocol': args.actor_context_protocol}
                                  if args.actor_context_protocol else {})})
            except Exception as error:  # noqa: BLE001
                entry['error'] = f'study start: {type(error).__name__}: {error}'
                entry['charged'] = campaign_spend(args.base, campaign['campaign_id'])
                consecutive_unscored += 1; save()
                print(f'[attempt {attempts}] {entry["error"]}', flush=True)
                if not wait_until_idle(args.base, args.idle_grace, args.poll):
                    aborted = 'backend did not return to idle after a failed start'
                    raise PhaseAbort(aborted)
                continue

            # The whole phase is void if the backend ran an ordinary study instead.
            if args.actor_context_protocol and \
                    started.get('actor_context_protocol') != args.actor_context_protocol:
                aborted = (f'started study runs Actor protocol '
                           f'{started.get("actor_context_protocol")!r}, not '
                           f'{args.actor_context_protocol!r}')
                raise PhaseAbort(aborted)
            if started.get('replay_of') != args.policy:
                aborted = (f'started study is not a replay of {args.policy}: '
                           f'replay_of={started.get("replay_of")!r}')
                raise PhaseAbort(aborted)
            entry.update(study_id=started['study_id'], replay_of=started.get('replay_of'),
                         actor_context_protocol=started.get('actor_context_protocol'),
                         replay_policy_hash=started.get('replay_policy_hash')); save()

            deadline = time.monotonic() + args.study_timeout
            study = started
            try:
                while study['status'] not in TERMINAL:
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"{started['study_id']} still {study['status']}")
                    time.sleep(args.poll)
                    study = api(args.base, 'GET', f"/api/completion-studies/{started['study_id']}")
            except Exception as error:  # noqa: BLE001
                poll_error = f'{type(error).__name__}: {error}'
                # The study record is authoritative; this poll loop is not. One dropped
                # localhost GET must not delete a verdict the gate has already reached.
                # The bias runs one way: the studies that poll longest are the ones that
                # complete all 42 episodes, so discarding on a poll failure preferentially
                # discards SCORABLE replays and understates both read-outs.
                try:
                    study = api(args.base, 'GET', f"/api/completion-studies/{started['study_id']}")
                except Exception:  # noqa: BLE001
                    study = None
                if not (study or {}).get('validation_assessment'):
                    entry['error'] = poll_error
                    consecutive_unscored += 1; save()
                    record_charge(args.base, campaign['campaign_id'], entry, save)
                    print(f'[attempt {attempts}] {entry["error"]}', flush=True)
                    if not wait_until_idle(args.base, args.idle_grace, args.poll):
                        aborted = 'a replay is still holding the coordinator'
                        raise PhaseAbort(aborted)
                    continue
                entry['poll_error'] = poll_error  # recovered, and the evidence is kept

            va = study.get('validation_assessment') or {}
            decision = va.get('decision')
            consecutive_unscored = 0 if decision else consecutive_unscored + 1
            entry.update(status=study.get('status'), decision=study.get('decision'),
                         reason=study.get('reason'), validation_decision=decision,
                         passed=(decision == PASS_VERDICT) if decision else None,
                         trials=len(study.get('trial_rows', []))); save()
            record_charge(args.base, campaign['campaign_id'], entry, save)
            if consecutive_unscored >= args.consecutive_unscored_abort:
                aborted = (f'{consecutive_unscored} consecutive attempts produced no validation '
                           f'assessment; the run cannot yield a scored result. Check evidence '
                           f'ingestion health before spending further.')
                raise PhaseAbort(aborted)
            scored = [r for r in manifest['replays'] if r.get('validation_decision')]
            note = '' if decision else '  (no validation assessment: observed nothing, replaced)'
            print(f"[attempt {attempts}] {study['status']}/{study['decision']} | "
                  f"validation={decision} | scored {sum(1 for r in scored if r['passed'])}"
                  f"/{len(scored)}{note}", flush=True)
    except PhaseAbort as error:
        aborted = aborted or str(error)
        print(f'\nABORTED: {aborted}', flush=True)
    except KeyboardInterrupt:
        aborted = 'interrupted by operator'

    if aborted and campaigns:
        # Aborting the runner does not stop the backend. Without this, a study keeps
        # running and charging after the operator believes they stopped it, and that
        # spend is missing from total_charged_upper_bound - the figure this project
        # carries forward against its shared ceiling. Ctrl-C had the same hole.
        print(f'stopping campaign {campaigns[-1]} and waiting for it to settle', flush=True)
        try:
            api(args.base, 'POST', f'/api/campaigns/{campaigns[-1]}/stop', {})
        except Exception as error:  # noqa: BLE001
            print(f'  stop request failed: {type(error).__name__}', flush=True)
        if not wait_until_idle(args.base, args.idle_grace, args.poll):
            print('  WARNING: coordinator still busy; spend below may be understated', flush=True)
            manifest['stop_incomplete'] = True

    scored = [r for r in manifest['replays'] if r.get('validation_decision')]
    manifest.update(aborted=aborted, campaigns=campaigns, attempts=attempts,
                    replays_scored=len(scored), unscored=attempts - len(scored),
                    passes=sum(1 for r in scored if r['passed']))
    try:
        manifest['total_charged_upper_bound'] = total_spend(args.base, campaigns)
    except PhaseAbort as error:
        manifest['total_charged_upper_bound'] = None
        manifest['total_charged_error'] = str(error)
    save()
    print(f"\ndone | {attempts} attempts, {manifest['unscored']} unscored | "
          f"{manifest['passes']} of {manifest['replays_scored']} scored replays returned "
          f"{PASS_VERDICT} | charged ${manifest['total_charged_upper_bound'] or float('nan'):.5f}"
          + (f' | ABORTED: {aborted}' if aborted else ''))
    print(f'manifest {manifest_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
