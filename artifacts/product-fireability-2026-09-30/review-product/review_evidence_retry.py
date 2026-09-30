"""Product review, faultlab-evidence-retry/v3 ($0, offline): long scripted Learn campaigns, v3 plan against v2 plan.

Run from faultlab/backend:
    ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/review-product/review_evidence_retry.py OUT.json

Independent of the builder's scenario (a flaky six-episode batch). Here, like live run v2f (10 waits), a long discovery
campaign has MANY separate evidence waits: every discovery episode's first Weave read fails with TRANSPORT (8 discovery
slots, so 8 waits). The real coordinator, learning loop, EvidenceWait, retry-evidence job, ledger and plan run with the
doubles of tests/lab/test_evidence_wait.py (fake Weave, fake Actor runner, Explorer double). The wait clock runs 1000x
faster, so declared 30/120/300 s delays take 30/120/300 ms.

  S1 v3 plan, each wait cleared by its first retry          -> expect 8 automatic retries (> 6), never "needs operator"
  S2 v2 plan (saved before v3), same failures               -> expect exactly 6, then "needs operator" (PER_CAMPAIGN)
  S3 v3 plan, each wait needs all 3 of its retries           -> expect 24 retries = the cap, and the declared minutes
Start's plan check (validate_run_plan) must accept both the v3 and the v2 plan. No network (review_guard).
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests' / 'lab'), str(BACKEND / 'tests')]
SCRATCH = Path('/Users/shree/FaultLab_Scratch/review-product-fireability/evidence')


def scenario(name, *, v2_plan, retries_needed):
    import pytest
    from app.config import Settings
    from app.lab import evidence_wait
    from app.lab.coordinator import LabCoordinator
    from app.lab.run_plans import read_run_plan, validate_run_plan
    import app.lab.run_plans as run_plans
    import test_evidence_wait as tew
    directory = SCRATCH / name
    directory.mkdir(parents=True, exist_ok=True)
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(directory / 'lab'), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model='deepseek-ai/DeepSeek-V4-Pro-0813'))
    mp = pytest.MonkeyPatch()
    try:
        if v2_plan: mp.setattr(run_plans, 'evidence_retry_declaration', evidence_wait.declaration_v2)   # a plan saved before v3
        campaign, weave, runner, ledger = tew.harness(owner, mp, tew.purpose_is('discovery'), mode='tie')
        if v2_plan: mp.setattr(run_plans, 'evidence_retry_declaration', evidence_wait.declaration)       # today's installed rule
        ident = campaign.campaign_id
        declared = read_run_plan(owner.store, ident)['plan']['evidence_retry']
        start_ok = validate_run_plan(owner.store, owner.settings, owner.get(ident)) is not None
        tries = {}
        async def services():
            weave.jobs += 1
            class Worker:
                async def start(self): pass
                async def close(self): weave.closed += 1
            class Gateway:
                async def retry(self, episode_id, **kwargs):
                    weave.retried.append(episode_id)
                    tries[episode_id] = tries.get(episode_id, 0) + 1
                    if tries[episode_id] >= retries_needed:
                        weave.cleared.add(episode_id)
                        owner.store.put_record('evidence', episode_id, tew.verified_record(episode_id))
                        return SimpleNamespace(source='weave_verified')
                    raise RuntimeError('fake Weave outage for this episode')
            return Worker(), Gateway(), object()
        owner._evidence_retry_services = services
        async def run():
            task = asyncio.create_task(owner._execute(ident, True))
            deadline = time.monotonic() + 120
            while True:
                state = owner.get(ident).state
                all_waits = tew.waits(owner, ident)
                if task.done(): break
                if all_waits and all_waits[-1].get('status') == 'NEEDS_OPERATOR':
                    await asyncio.sleep(0.6)   # 600 declared seconds: no further automatic retry may start
                    break
                if time.monotonic() > deadline: break
                await asyncio.sleep(0.01)
            observed = {'waits': tew.waits(owner, ident), 'retries': tew.retries(owner, ident),
                        'evidence_wait_api': (await tew.api_get(owner, f'/api/campaigns/{ident}/evidence-wait'))[1],
                        'state_before_stop': owner.get(ident).state, 'reason_before_stop': owner.get(ident).terminal_reason}
            if not task.done():
                await owner.stop(ident)
            await task
            return observed
        observed = asyncio.run(run())
        waits_ = observed['waits']
        return {
            'plan_evidence_retry': {k: declared[k] for k in ('protocol', 'automatic_retries_per_wait', 'automatic_retries_per_campaign', 'delays_seconds')},
            'start_plan_check_accepts': start_ok,
            'waits': len(waits_),
            'automatic_attempts_per_wait': [len(w['automatic_attempts']) for w in waits_],
            'wait_statuses': [w['status'] for w in waits_],
            'limit_reached': [w.get('limit_reached') for w in waits_],
            'campaign_max_on_waits': sorted({w.get('automatic_retries_campaign_max') for w in waits_}, key=str),
            'automatic_retries_total': len([r for r in observed['retries'] if r.get('trigger') == 'automatic']),
            'declared_seconds_of_automatic_retries': sum(sum(w['delays_seconds'][:len(w['automatic_attempts'])]) for w in waits_),
            'evidence_wait_api': {k: observed['evidence_wait_api'].get(k) for k in ('needs_operator', 'automatic_retries_total')}
                                 | {'declared_cap': (observed['evidence_wait_api'].get('declared') or {}).get('automatic_retries_per_campaign')},
            'state_before_stop': observed['state_before_stop'], 'reason_before_stop': (observed['reason_before_stop'] or '')[:220],
            'final_state': owner.get(ident).state, 'actor_episodes': len(runner.calls)}
    finally:
        mp.undo()
        asyncio.run(owner.close())


def main(out):
    import shutil
    report = {}
    try:
        report['S1_v3_one_retry_per_wait'] = scenario('s1', v2_plan=False, retries_needed=1)
        report['S2_v2_one_retry_per_wait'] = scenario('s2', v2_plan=True, retries_needed=1)
        report['S3_v3_three_retries_per_wait'] = scenario('s3', v2_plan=False, retries_needed=3)
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    report['scratch_removed'] = not SCRATCH.exists()
    report['guard'] = review_guard.counts()
    Path(out).write_text(json.dumps(report, indent=1, sort_keys=True, default=str))
    print(json.dumps(report, indent=1, sort_keys=True, default=str))


if __name__ == '__main__':
    main(sys.argv[1])
