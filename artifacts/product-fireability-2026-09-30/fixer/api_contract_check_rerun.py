"""Fixer rerun (builder's script; changed: scratch path, slot 2 is a MIXED pick, and the spec checks it) of: real backend API responses for history fireability and evidence retry v3, validated by the dashboard's own validators.

$0 and offline. Pattern copied from artifacts/product-mechanic-citations-2026-09-30/builder/api_contract_check.py. In a scratch
store outside the Desktop (/Users/shree/FaultLab_Scratch/builder/contract) it seeds a same-agent history with the product's
record shapes (test_agent_history.Seeder: dev-5 fired 3 of 3; an Explorer pick with a lone F4 on the orders status read,
fired 0 of 3), then creates through prepare_run_plan/create:
  * a new discovery v3-history Learn plan (declares the rule), and RUNS its discovery through the real learning loop with the
    scripted Explorer and fake runner of tests/lab/test_history_fireability.py (slot 1: the status pick is refused, its
    re-plan runs; the last slot gets no request);
  * a new discovery v4 Learn plan (declares the rule, not run);
  * a v3-history plan as saved before the rule (no key) and a v1 plan (no key);
then saves the real JSON of GET /api/run-options, /plan (all four), /search-attempts, /experiments and /recording (the run
v3 plan), and runs a throw-away vitest spec in a scratch copy of the frontend that validates them with validateRunOptions,
validateCampaignPlan, validateSearchAttempts, validateExperiments and validateExplorerFireability. Both scratch folders are
deleted afterwards. A negative control (a response altered to bind the table to another history) must be rejected.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/builder/api_contract_check.py
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401  (refuses .env and any non-loopback connection)
sys.path[:0] = [str(Path.cwd() / 'tests' / 'lab'), str(Path.cwd() / 'tests')]

SCRATCH = Path('/Users/shree/FaultLab_Scratch/fixer/contract')
SPEC = """
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import { validateCampaignPlan, validateRunOptions } from '../src/runPlans'
import { validateSearchAttempts } from '../src/searchAttempts'
import { validateExperiments } from '../src/experiments'
import { validateExplorerFireability } from '../src/historyFireability'
const dir = process.env.FIREABILITY_CONTRACT_DIR as string
const read = (name: string) => JSON.parse(readFileSync(`${dir}/${name}.json`, 'utf8'))
it('the dashboard accepts the real history fireability and evidence retry v3 API responses', () => {
  const ids = read('ids')
  const options = validateRunOptions(read('run-options'))
  expect(options.learn.explorer_selection?.protocol).toBe('faultlab-explorer-selection/v3-history-fireability')
  const v3 = validateCampaignPlan(read('plan-v3-new'), ids.v3_new)
  expect(v3.plan?.explorer_selection?.table.refused_targets).toEqual(['F4 on get_operation_status (orders): fired in 0 of 3 verified history episodes (below 1/2 of at least 3)'])
  expect(v3.plan?.evidence_retry?.protocol).toBe('faultlab-evidence-retry/v3')
  expect(v3.plan?.evidence_retry?.automatic_retries_per_campaign).toBe(24)
  const v4 = validateCampaignPlan(read('plan-v4-new'), ids.v4_new)
  expect(v4.plan?.explorer_selection?.table.rows.length).toBe(2)
  expect(validateCampaignPlan(read('plan-v3-old'), ids.v3_old).plan?.explorer_selection).toBeUndefined()
  expect(validateCampaignPlan(read('plan-v1'), ids.v1).plan?.explorer_selection).toBeUndefined()
  const attempts = validateSearchAttempts(read('search-attempts'), ids.v3_new)
  expect(attempts.map(row => row.search_decision.status)).toEqual(['SKIPPED_UNFIREABLE', 'SELECTED', 'SELECTED', 'SELECTED', 'SELECTED', 'SELECTED', 'SELECTED', 'SELECTED'])
  expect(attempts[1].fireability?.replan_of).toBe(attempts[0].selection_ref)
  // Fixer: the mixed pick (pending upgrade + status read) ran; its check names the REFUSED target and says why it runs.
  expect(attempts[2].fireability?.status).toBe('ALLOWED')
  expect(attempts[2].fireability?.targets.map(target => target.status)).toEqual(['ALLOWED', 'REFUSED'])
  expect(attempts[2].fireability?.reason).toMatch(/^Allowed: F4 on get_operation_status \\(orders\\) is REFUSED/)
  expect(validateCampaignPlan(read('plan-v3-new'), ids.v3_new).plan?.explorer_selection?.pick_refused_when).toBe('every_fault_on_a_refused_target')
  const experiments = validateExperiments(read('experiments'))
  expect(experiments.explorer_fireability?.picks_refused).toBe(1)
  expect(experiments.explorer_fireability?.slots_without_request.map(slot => slot.selection_index)).toEqual([7])
  const recording = read('recording')
  expect(validateCampaignPlan(recording.run_plan, ids.v3_new).plan?.explorer_selection?.table_hash).toBe(v3.plan?.explorer_selection?.table_hash)
  expect(validateExplorerFireability(recording.explorer_selection_rule).picks_checked).toBe(8)
  // Negative control: the same saved plan with its table bound to another history is rejected.
  const tampered = read('plan-v3-new'); tampered.plan.explorer_selection.table.history_summary_hash = 'f'.repeat(64)
  expect(() => validateCampaignPlan(tampered, ids.v3_new)).toThrow('Malformed')
})
"""


async def build():
    import httpx
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    from app.lab.operator_actions import register_agent
    from app.lab.run_plans import prepare_run_plan
    from app.main import create_app
    import test_history_fireability as t
    from test_agent_history import Seeder, plan_request
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(SCRATCH / 'store'), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model='deepseek-ai/DeepSeek-V4-Pro-0813'))
    try:
        registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
        t.seed_status_history(Seeder(owner, registration))
        def create(protocol, *, drop=False, order='order-contract'):
            prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, discovery_protocol=protocol, order_id=order))
            if drop: prepared.plan.pop('explorer_selection')
            return owner.create(prepared.campaign_request, run_plan=prepared)
        v3_new = create('faultlab-discovery/v3-history')
        v4_new = create('faultlab-discovery/v4-history-replay', order='order-v4')
        v3_old = create('faultlab-discovery/v3-history', drop=True, order='order-v3-old')
        v1 = create('faultlab-discovery/v1', order='order-v1')
        # Fixer: slot 2 pairs the status read with a pending upgrade (allowed under the fixed rule, recorded with its REFUSED target).
        answer = lambda slot, number, _c: t.raw(t.STATUS) if (slot, number) == (0, 1) else t.raw(t.DELAYED(3), t.STATUS) if slot == 1 else t.raw(t.DELAYED(slot + 1 if number == 1 else 9))
        await asyncio.to_thread(t.run_loop, owner, owner.get(v3_new.campaign_id), answer)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            responses = {'run-options': (await api.get('/api/run-options')).json(),
                         'plan-v3-new': (await api.get(f'/api/campaigns/{v3_new.campaign_id}/plan')).json(),
                         'plan-v4-new': (await api.get(f'/api/campaigns/{v4_new.campaign_id}/plan')).json(),
                         'plan-v3-old': (await api.get(f'/api/campaigns/{v3_old.campaign_id}/plan')).json(),
                         'plan-v1': (await api.get(f'/api/campaigns/{v1.campaign_id}/plan')).json(),
                         'search-attempts': (await api.get(f'/api/campaigns/{v3_new.campaign_id}/search-attempts')).json(),
                         'experiments': (await api.get(f'/api/campaigns/{v3_new.campaign_id}/experiments')).json(),
                         'recording': (await api.get(f'/api/campaigns/{v3_new.campaign_id}/recording')).json()}
        responses['ids'] = {'v3_new': v3_new.campaign_id, 'v4_new': v4_new.campaign_id, 'v3_old': v3_old.campaign_id, 'v1': v1.campaign_id}
        return responses
    finally:
        await owner.close()


def main():
    if SCRATCH.exists(): shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    try:
        responses = asyncio.run(build())
        out = SCRATCH / 'responses'; out.mkdir()
        for name, value in responses.items(): (out / f'{name}.json').write_text(json.dumps(value))
        for name in ('plan-v3-new', 'plan-v4-new', 'plan-v3-old', 'plan-v1'):
            plan = responses[name]['plan']
            print(f'{name}: explorer_selection={"explorer_selection" in plan}, evidence_retry={plan["evidence_retry"]["protocol"]}/{plan["evidence_retry"]["automatic_retries_per_campaign"]}')
        print('search-attempts statuses:', [row['search_decision']['status'] for row in responses['search-attempts']])
        print('experiments keys:', sorted(responses['experiments']), '| recording has rule block:', 'explorer_selection_rule' in responses['recording'])
        front = SCRATCH / 'frontend'
        shutil.copytree(ROOT / 'frontend', front, ignore=shutil.ignore_patterns('node_modules', 'dist', '.results', 'tests'))
        (front / 'node_modules').symlink_to(ROOT / 'frontend' / 'node_modules')
        shutil.copytree(ROOT / 'contracts', SCRATCH / 'contracts')
        (front / 'tests').mkdir(); (front / 'tests' / 'contract.test.ts').write_text(SPEC)
        run = subprocess.run(['npx', 'vitest', 'run', 'tests/contract.test.ts'], cwd=front, capture_output=True, text=True,
                             env={**os.environ, 'FIREABILITY_CONTRACT_DIR': str(out)})
        print(run.stdout[-900:]); print(run.stderr[-600:])
        print('vitest exit', run.returncode)
        return run.returncode
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        print('scratch removed:', not SCRATCH.exists())


if __name__ == '__main__':
    sys.exit(main())
