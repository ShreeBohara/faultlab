"""Real backend API responses of an offline v4 run, validated by the dashboard's own validators ($0, offline).

Why: the first build's frontend replay validator required `transport_retries` to be absent, but the backend's
search-attempts API sends `transport_retries: []` on every row, so the dashboard would have refused real replay rows.
The unit-test fixture had copied the wrong shape. This check closes that gap once: it runs manual_check.py's run A
(scripted native transport, in-process simulator, local Weave double, socket guard; reproduction stubbed), saves the
real JSON responses of GET .../plan, .../search-attempts and .../experiments to a scratch folder outside the Desktop,
then runs a throw-away vitest spec in a scratch copy of the frontend that validates them with validateCampaignPlan,
validateSearchAttempts and validateExperiments. Both scratch folders are deleted afterwards.

Run from faultlab/backend:
    ../.venv/bin/python ../artifacts/product-discovery-v4-2026-09-30/builder/api_contract_check.py
"""
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import manual_check as mc  # noqa: E402  (installs the socket guard and the .env audit hook first)

SCRATCH = Path('/Users/shree/FaultLab_Scratch/discovery-v4-builder/contract')
SPEC = """
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import { validateCampaignPlan } from '../src/runPlans'
import { validateSearchAttempts } from '../src/searchAttempts'
import { validateExperiments } from '../src/experiments'
const dir = process.env.V4_CONTRACT_DIR as string
const read = (name: string) => JSON.parse(readFileSync(`${dir}/${name}.json`, 'utf8'))
it('the dashboard accepts the real v4 API responses', () => {
  const ids = read('ids')
  const plan = validateCampaignPlan(read('plan'), ids.campaign_id)
  expect(plan.plan?.discovery?.replay?.rows.length).toBe(2)
  const rows = validateSearchAttempts(read('search-attempts'), ids.campaign_id)
  expect(rows.filter(row => row.history_replay).map(row => row.history_replay!.history_row)).toEqual([3, 5])
  expect(rows.filter(row => !row.history_replay).length).toBe(6)
  const experiments = validateExperiments(read('experiments'))
  expect(experiments.counterexamples.map(row => row.history_replay?.history_row ?? null)).toEqual([3, 5, null])
})
"""


async def dump():
    from app.lab import learning
    from app.lab.run_plans import read_run_plan
    provider = mc.Recorder('accepted')
    c, world, api, remote = mc.study_runtime(SCRATCH / 'store', provider)
    source = learning.Reproducer.source
    try:
        _, native_id = await mc.baseline_history(c, api)
        campaign, _, _ = await mc.create(api, native_id, mc.V4, 'order-v4-contract')
        learning.Reproducer.source = mc.stub_source(c)
        await api.post(f"/api/campaigns/{campaign['campaign_id']}/start", json={})
        await c.tasks[campaign['campaign_id']]
        out = SCRATCH / 'responses'; out.mkdir(parents=True)
        for name, path in (('plan', 'plan'), ('search-attempts', 'search-attempts'), ('experiments', 'experiments')):
            response = await api.get(f"/api/campaigns/{campaign['campaign_id']}/{path}")
            assert response.status_code == 200, response.text
            (out / f'{name}.json').write_text(response.text)
        (out / 'ids.json').write_text(json.dumps({'campaign_id': campaign['campaign_id']}))
        state = c.get(campaign['campaign_id']).state
    finally:
        learning.Reproducer.source = source
        await api.aclose(); await world.aclose(); await c.close()
    return out, state


def main():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    try:
        responses, state = asyncio.run(dump())
        rows = json.loads((responses / 'search-attempts.json').read_text())
        print('campaign state', state, '| replay row keys:', sorted(rows[0]))
        front = SCRATCH / 'frontend'; front.mkdir()
        for name in ('src', 'tests'):
            shutil.copytree(ROOT / 'frontend' / name, front / name, ignore=shutil.ignore_patterns('.results'))
        for name in ('package.json', 'tsconfig.json', 'vite.config.ts', 'local-ports.ts'):
            shutil.copy2(ROOT / 'frontend' / name, front / name)
        (front / 'node_modules').symlink_to(ROOT / 'frontend' / 'node_modules')
        (SCRATCH / 'audit').symlink_to(ROOT / 'audit'); (SCRATCH / 'contracts').symlink_to(ROOT / 'contracts')
        (front / 'tests' / 'v4-contract.check.test.ts').write_text(SPEC)
        if '--old-retry-check' in sys.argv:
            # Negative control: the first build's validator line (transport_retries had to be absent) in the scratch copy.
            target = front / 'src' / 'searchAttempts.ts'
            text = target.read_text()
            fixed = "!(row.transport_retries === undefined || (Array.isArray(row.transport_retries) && !row.transport_retries.length))"
            assert text.count(fixed) == 1
            target.write_text(text.replace(fixed, 'row.transport_retries !== undefined'))
            print('NEGATIVE CONTROL: first-build replay validator restored in the scratch copy; the check must fail')
        result = subprocess.run(['npx', 'vitest', 'run', 'tests/v4-contract.check.test.ts'], cwd=front, capture_output=True, text=True,
                                env={**__import__('os').environ, 'V4_CONTRACT_DIR': str(responses)})
        lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
        print('\n'.join(line for line in lines if 'Test' in line or '✓' in line or '×' in line or 'Error' in line))
        print('vitest exit', result.returncode, '| network connections refused', mc.REFUSED)
        return result.returncode
    finally:
        shutil.rmtree(SCRATCH)
        if SCRATCH.parent.exists() and not any(SCRATCH.parent.iterdir()):
            SCRATCH.parent.rmdir()


if __name__ == '__main__':
    sys.exit(main())
