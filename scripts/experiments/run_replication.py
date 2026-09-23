"""Phase 9: paired, interleaved replication of the Phase 8 task_outcome result.

Runs completion studies in strict alternating pairs across two arms that differ in
exactly one thing - the declared presentation of the reviewed evidence the Mechanic reads:

  T (treatment)  faultlab-compact-evidence/v2-task-outcome   what Phase 8 ran
  C (control)    faultlab-compact-evidence/v1                what Phases 5 and 6 ran

Both arms run against the SAME backend process, alternating, with the leading arm swapped
each round, so neither provider drift nor a truncated run can separate them.

Predeclared primary read-out, one independent draw per study: does the study's FIRST
proposal contain a step with op == 'retry_original_request' and service == 'notifications'?
A first proposal that is a well-formed Mechanic refusal, or that is malformed, IS a draw
and does not contain the step. Only a study that produced no first proposal at all
(controls-gate stop, lab error before any Mechanic call) yields no draw; those are
retained, reported, and replaced up to a fixed attempt cap. A study that produced any
proposal is NEVER repeated.

Dry by default. `--execute-live` plus a matching `--confirm-entity` is required to run.

Usage:
  python scripts/experiments/run_replication.py --plan
  python scripts/experiments/run_replication.py --execute-live --confirm-entity ENTITY
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

TREATMENT = 'faultlab-compact-evidence/v2-task-outcome'
CONTROL = 'faultlab-compact-evidence/v1'
EXPECTED_MECHANIC = 'deepseek-ai/DeepSeek-V4-Pro-0813'
TASK_TEXT = 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'
ORDER_ID = 'order-1'
# The three statuses completion_study.py actually writes. FAILED/CANCELLED are never emitted.
TERMINAL = ('COMPLETED', 'INCOMPLETE', 'INTERRUPTED')


class PhaseAbort(RuntimeError):
    """Raised when continuing would spend money blindly or against a wedged backend."""


def api(base, method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or 'null')


def has_notification_retry(content):
    for rule in (content or {}).get('rules', []):
        for step in rule.get('steps', []):
            if step.get('op') == 'retry_original_request' and step.get('service') == 'notifications':
                return True
    return False


# A content-less candidate still carrying the provisional decision the study writes before
# it parses the model output means the study died between the Mechanic call and the parse:
# a request was made but its answer was never established. That is indeterminate, not zero.
UNRESOLVED_DECISION = 'PROPOSED'


def first_proposal_draw(study):
    """The predeclared primary read-out.

    A first proposal exists whenever the Mechanic returned something the study resolved
    into a candidate - a policy, a well-formed refusal (MechanicNoChange), or an output
    rejected as invalid. A refusal and an invalid output cannot contain the step, so both
    are False, NOT 'no draw': returning None for them would silently discard and resample
    a real Mechanic answer, which is selection on the outcome.

    None is reserved for the two cases where no answer was ever established: no candidate
    was recorded at all (controls-gate stop, or a lab error before any Mechanic call), or
    the only candidate is still unresolved because the study died mid-parse.
    """
    for candidate in study.get('candidates', []):
        content = candidate.get('content')
        if content is not None:
            return has_notification_retry(content)
        return None if candidate.get('decision') == UNRESOLVED_DECISION else False
    return None


def campaign_spend(base, campaign_id, attempts=3):
    """Never guess. A budget read that will not succeed aborts the phase."""
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
    return sum(campaign_spend(base, campaign_id) for campaign_id in campaigns)


def wait_until_idle(base, seconds, poll):
    """A study we stopped watching may still be running and holding the coordinator."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if not api(base, 'GET', '/api/config/status').get('active_campaign_id'):
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(poll)
    return False


def check_backend(base, expected_mechanic):
    status = api(base, 'GET', '/api/config/status')
    if not status.get('live_enabled'):
        raise PhaseAbort('Backend is not live-enabled')
    mechanic = (status.get('models') or {}).get('mechanic')
    if mechanic != expected_mechanic:
        raise PhaseAbort(f'Backend Mechanic is {mechanic!r}, phase declares {expected_mechanic!r}')
    return status


def start_study(base, protocol):
    campaign = api(base, 'POST', '/api/campaigns', {
        'task_text': TASK_TEXT, 'order_id': ORDER_ID,
        'mode': 'baseline', 'config_profile_id': 'live-v1'})
    started = api(base, 'POST', f"/api/campaigns/{campaign['campaign_id']}/completion-study",
                  {'execute_live': True, 'evidence_protocol': protocol})
    return campaign['campaign_id'], started


def poll_study(base, study_id, poll, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    while True:
        study = api(base, 'GET', f'/api/completion-studies/{study_id}')
        if study['status'] in TERMINAL:
            return study
        if time.monotonic() > deadline:
            raise TimeoutError(f'{study_id} still {study["status"]} after {timeout_seconds:.0f}s')
        time.sleep(poll)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--settings',
                        default='artifacts/phase8-2026-09-20/settings-8a-mechanic-v4.json',
                        help='Non-secret settings override the backend was launched with')
    parser.add_argument('--target', type=int, default=14, help='informative studies per arm')
    parser.add_argument('--attempt-cap', type=int, default=18, help='attempts per arm')
    parser.add_argument('--spend-cap', type=float, default=150.0,
                        help='hard dollar guard; tripping it aborts and is reported')
    parser.add_argument('--headroom', type=float, default=12.0,
                        help='reserve before another study; must exceed one qualifying study')
    parser.add_argument('--study-timeout', type=float, default=3600.0)
    parser.add_argument('--idle-grace', type=float, default=900.0)
    parser.add_argument('--poll', type=float, default=5.0)
    parser.add_argument('--out', default='artifacts/phase9-2026-09-20')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    parser.add_argument('--force', action='store_true', help='allow overwriting an existing manifest')
    args = parser.parse_args()

    print(f'arms       T={TREATMENT}\n           C={CONTROL}')
    print(f'mechanic   {EXPECTED_MECHANIC} (verified against the live backend before each round)')
    print(f'target     {args.target} informative per arm, attempt cap {args.attempt_cap}')
    print(f'pairing    strict alternating pairs; leading arm swaps each round;')
    print(f'           the phase ends as soon as EITHER arm reaches target or cap')
    print(f'spend      guard ${args.spend_cap:.2f}, headroom ${args.headroom:.2f} per study')
    print(f'timeouts   study {args.study_timeout:.0f}s, idle grace {args.idle_grace:.0f}s')
    if args.plan or not args.execute_live:
        print('Dry plan only. Pass --execute-live --confirm-entity ENTITY to run.')
        return 0

    # Entity check, same pattern as the Phase 6/7 probe harnesses: the backend never
    # exposes the entity over HTTP, so it is verified from the non-secret override file.
    from app.config import Settings
    overrides = json.loads((ROOT / args.settings).read_text())
    os.environ.update({k: str(v) for k, v in overrides.items() if v != ''})
    settings = Settings.from_env()
    if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
        raise SystemExit('--confirm-entity must match the configured W&B entity')
    if settings.model_for_role('mechanic') != EXPECTED_MECHANIC:
        raise SystemExit(f'Settings resolve the mechanic role to '
                         f'{settings.model_for_role("mechanic")!r}, not {EXPECTED_MECHANIC!r}')

    status = check_backend(args.base, EXPECTED_MECHANIC)
    if status.get('active_campaign_id'):
        raise SystemExit('Another execution is active; refusing to start')

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / 'replication-manifest.json'
    if manifest_path.exists() and not args.force:
        raise SystemExit(f'{manifest_path} exists; refusing to overwrite a retained run record')

    manifest = {'schema_version': 'faultlab-replication/v2', 'treatment': TREATMENT,
                'control': CONTROL, 'expected_mechanic': EXPECTED_MECHANIC,
                'target_per_arm': args.target, 'attempt_cap_per_arm': args.attempt_cap,
                'spend_cap': args.spend_cap, 'headroom': args.headroom,
                'models': status.get('models'), 'attempts': []}

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

    attempts = {'T': 0, 'C': 0}
    informative = {'T': 0, 'C': 0}
    campaigns = []                      # every campaign created, whatever happened to it
    aborted = None

    try:
        for round_index in range(args.attempt_cap):
            if any(informative[a] >= args.target or attempts[a] >= args.attempt_cap
                   for a in ('T', 'C')):
                break
            # Swap the leading arm each round so neither a truncation nor an ordering
            # effect can fall preferentially on one arm.
            order = [('T', TREATMENT), ('C', CONTROL)]
            if round_index % 2: order.reverse()
            for arm, protocol in order:
                charged = total_spend(args.base, campaigns)
                if charged + args.headroom > args.spend_cap:
                    aborted = (f'spend guard: ${charged:.5f} charged + ${args.headroom:.2f} '
                               f'headroom exceeds ${args.spend_cap:.2f}')
                    raise PhaseAbort(aborted)
                check_backend(args.base, EXPECTED_MECHANIC)

                attempts[arm] += 1
                label = f'{arm}{attempts[arm]}'
                entry = {'label': label, 'arm': arm, 'protocol': protocol,
                         'round': round_index + 1, 'campaign_id': None, 'study_id': None,
                         'spent_before': charged}
                manifest['attempts'].append(entry); save()
                print(f'[{label}] round {round_index + 1} starting (spent ${charged:.5f})', flush=True)

                try:
                    campaign_id, started = start_study(args.base, protocol)
                except Exception as error:  # noqa: BLE001 - recorded, never dropped
                    entry['error'] = f'{type(error).__name__}: {error}'; save()
                    print(f'[{label}] start failed: {entry["error"]}', flush=True)
                    if not wait_until_idle(args.base, args.idle_grace, args.poll):
                        aborted = 'backend did not return to idle after a failed start'
                        raise PhaseAbort(aborted)
                    continue

                # Record the campaign BEFORE polling, so its spend counts against the
                # guard and it is retained even if everything after this throws.
                campaigns.append(campaign_id)
                entry.update(campaign_id=campaign_id, study_id=started['study_id'],
                             evidence_protocol=started.get('evidence_protocol'))
                save()

                try:
                    study = poll_study(args.base, started['study_id'], args.poll, args.study_timeout)
                except Exception as error:  # noqa: BLE001
                    entry['error'] = f'{type(error).__name__}: {error}'
                    entry['charged'] = campaign_spend(args.base, campaign_id)
                    save()
                    print(f'[{label}] {entry["error"]}', flush=True)
                    if not wait_until_idle(args.base, args.idle_grace, args.poll):
                        aborted = (f'{started["study_id"]} is still holding the coordinator; '
                                   f'refusing to burn the attempt cap against a wedged backend')
                        raise PhaseAbort(aborted)
                    continue

                draw = first_proposal_draw(study)
                if draw is not None: informative[arm] += 1
                entry.update(status=study['status'], decision=study['decision'],
                             stage=study['stage'], reason=study.get('reason'),
                             evidence_protocol=study.get('evidence_protocol'),
                             first_proposal_contains_step=draw,
                             proposals=len(study.get('candidates', [])),
                             trials=len(study.get('trial_rows', [])),
                             charged_model_calls=study.get('charged_model_calls'),
                             charged=campaign_spend(args.base, campaign_id))
                save()
                print(f"[{label}] {study['status']}/{study['decision']} at {study['stage']} | "
                      f"draw={draw} | informative T={informative['T']} C={informative['C']}",
                      flush=True)
    except PhaseAbort as error:
        aborted = aborted or str(error)
        print(f'\nABORTED: {aborted}', flush=True)
    except KeyboardInterrupt:
        aborted = 'interrupted by operator'

    manifest['aborted'] = aborted
    manifest['attempts_by_arm'] = attempts
    manifest['informative_by_arm'] = informative
    manifest['campaigns'] = campaigns
    try:
        manifest['total_charged_upper_bound'] = total_spend(args.base, campaigns)
    except PhaseAbort as error:
        manifest['total_charged_upper_bound'] = None
        manifest['total_charged_error'] = str(error)
    save()
    print(f"\ndone | attempts {attempts} | informative {informative} | "
          f"charged ${manifest['total_charged_upper_bound'] or float('nan'):.5f}"
          + (f' | ABORTED: {aborted}' if aborted else ''))
    print(f'manifest {manifest_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
