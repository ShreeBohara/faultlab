"""Real backend API responses for the native citation-status rule, validated by the dashboard's own validators ($0, offline).

Pattern copied from artifacts/product-loop-limits-2026-09-30/fixer/api_contract_check.py. In a scratch store outside the
Desktop (/Users/shree/FaultLab_Scratch/mechanic-citations-builder/contract) it creates, through prepare_run_plan/create:
  * a new Learn plan for native adapter v2 (declares the rule);
  * a native adapter v2 Learn plan as saved before the rule (no key);
  * a new Learn plan for the reference Actor (no key);
then saves the real JSON of GET /api/run-options, /plan (all three) and /recording (the new v2 plan), and runs a
throw-away vitest spec in a scratch copy of the frontend that validates them with validateRunOptions and
validateCampaignPlan. Both scratch folders are deleted afterwards.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/builder/api_contract_check.py
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
sys.path.insert(0, str(Path.cwd() / 'tests' / 'lab'))

SCRATCH = Path('/Users/shree/FaultLab_Scratch/mechanic-citations-builder/contract')
SPEC = """
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import { validateCampaignPlan, validateRunOptions } from '../src/runPlans'
const dir = process.env.CITATION_CONTRACT_DIR as string
const read = (name: string) => JSON.parse(readFileSync(`${dir}/${name}.json`, 'utf8'))
it('the dashboard accepts the real native citation-status API responses', () => {
  const ids = read('ids')
  const options = validateRunOptions(read('run-options'))
  expect(options.learn.mechanic_evidence?.protocol).toBe('faultlab-mechanic-evidence/v2-native-citation-status')
  const v2 = validateCampaignPlan(read('plan-v2-new'), ids.v2_new)
  expect(v2.plan?.mechanic_evidence?.agents).toEqual(['smolagents-v2'])
  expect(v2.plan?.mechanic_evidence?.reads_scoring).toBe(false)
  const older = validateCampaignPlan(read('plan-v2-old'), ids.v2_old)
  expect(older.plan?.mechanic_evidence).toBeUndefined()
  const reference = validateCampaignPlan(read('plan-reference'), ids.reference)
  expect(reference.plan?.mechanic_evidence).toBeUndefined()
  const recording = read('recording-v2-new')
  expect(validateCampaignPlan(recording.run_plan, ids.v2_new).plan?.mechanic_evidence?.block).toBe('native_citation_status')
})
"""


async def build():
    import httpx
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    from app.lab.operator_actions import register_agent
    from app.lab.run_plans import prepare_run_plan
    from app.main import create_app
    from test_discovery_v2_flow import EXPLORER_MODEL, request
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(SCRATCH / 'store'), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model=EXPLORER_MODEL))
    try:
        v2 = register_agent(owner.store, owner.settings, 'smolagents-v2')
        prepared = prepare_run_plan(owner.store, owner.settings, request(owner, v2, discovery_protocol='faultlab-discovery/v4-history-replay'))
        new = owner.create(prepared.campaign_request, run_plan=prepared)
        older = prepare_run_plan(owner.store, owner.settings, request(owner, v2, order_id='order-older'))
        older.plan.pop('mechanic_evidence')
        old = owner.create(older.campaign_request, run_plan=older)
        reference = prepare_run_plan(owner.store, owner.settings, request(owner, register_agent(owner.store, owner.settings, 'reference'), order_id='order-reference'))
        ref = owner.create(reference.campaign_request, run_plan=reference)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            responses = {'run-options': (await api.get('/api/run-options')).json(),
                         'plan-v2-new': (await api.get(f'/api/campaigns/{new.campaign_id}/plan')).json(),
                         'plan-v2-old': (await api.get(f'/api/campaigns/{old.campaign_id}/plan')).json(),
                         'plan-reference': (await api.get(f'/api/campaigns/{ref.campaign_id}/plan')).json(),
                         'recording-v2-new': (await api.get(f'/api/campaigns/{new.campaign_id}/recording')).json()}
        responses['ids'] = {'v2_new': new.campaign_id, 'v2_old': old.campaign_id, 'reference': ref.campaign_id}
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
        print('plan keys (v2 new):', sorted(k for k in responses['plan-v2-new']['plan'] if k in ('mechanic_context', 'mechanic_evidence', 'challenge_selection')))
        print('plan keys (v2 old):', sorted(k for k in responses['plan-v2-old']['plan'] if k in ('mechanic_context', 'mechanic_evidence', 'challenge_selection')))
        print('plan keys (reference):', sorted(k for k in responses['plan-reference']['plan'] if k in ('mechanic_context', 'mechanic_evidence', 'challenge_selection')))
        front = SCRATCH / 'frontend'
        shutil.copytree(ROOT / 'frontend', front, ignore=shutil.ignore_patterns('node_modules', 'dist', '.results', 'tests'))
        (front / 'node_modules').symlink_to(ROOT / 'frontend' / 'node_modules')
        shutil.copytree(ROOT / 'contracts', SCRATCH / 'contracts')
        (front / 'tests').mkdir(); (front / 'tests' / 'contract.test.ts').write_text(SPEC)
        run = subprocess.run(['npx', 'vitest', 'run', 'tests/contract.test.ts'], cwd=front, capture_output=True, text=True,
                             env={**os.environ, 'CITATION_CONTRACT_DIR': str(out)})
        print(run.stdout[-700:]); print(run.stderr[-400:])
        print('vitest exit', run.returncode)
        return run.returncode
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        print('scratch removed:', not SCRATCH.exists())


if __name__ == '__main__':
    sys.exit(main())
