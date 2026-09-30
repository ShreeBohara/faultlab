"""F1 and LOW-3 on REAL API responses ($0, offline): the fixed dashboard text, computed from the manual check's M4 data.

Takes manual-check.json (fixer/manual_check_api.py: the real backend's search-attempts and experiments JSON of campaign
M4, whose discovery ended after its two replays), copies frontend/src and frontend/tests to a
scratch folder OUTSIDE the Desktop, and runs a throw-away vitest spec there that validates the responses with the
dashboard's own validators and prints what the fault-search panel sentence (replaySummaryText) and the Run summary line
(foundByText) would say. The scratch folder is deleted afterwards. Run from faultlab/.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRATCH = Path('/Users/shree/FaultLab_Scratch/fixer-v4-contract')
SPEC = """
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import { validateSearchAttempts } from '../src/searchAttempts'
import { validateExperiments } from '../src/experiments'
import { replaySummaryText } from '../src/components/SearchAttemptsPanel'
import { foundByText } from '../src/components/RunSummary'
const dir = process.env.FIXER_CONTRACT_DIR as string
const read = (name: string) => JSON.parse(readFileSync(`${dir}/${name}.json`, 'utf8'))
it('real M4 responses: the panel sentence and the Run summary line', () => {
  const ids = read('ids')
  const rows = validateSearchAttempts(read('search-attempts'), ids.campaign_id)
  const sentence = replaySummaryText(rows)
  const experiments = validateExperiments(read('experiments'))
  const found = experiments.counterexamples.map(record => foundByText(record))
  console.log('FIXER-CONTRACT ' + JSON.stringify({ rows: rows.length, replays: rows.filter(r => r.history_replay).length, sentence, found }))
  expect(sentence).not.toMatch(/the Explorer chose/)
  expect(sentence).toMatch(/No Explorer slot is recorded/)
  expect(found.length).toBeGreaterThan(0)
  for (const line of found) expect(line).toMatch(/^Found by History replay \\d of 2 · agent history row \\d \\(dev-\\d\\): a history replay of that row, never independent discovery\\.$/)
})
"""


def main(manual_json):
    data = json.loads(Path(manual_json).read_text())
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    (SCRATCH / 'data').mkdir(parents=True)
    (SCRATCH / 'data' / 'ids.json').write_text(json.dumps({'campaign_id': data['m4']['campaign_id']}))
    (SCRATCH / 'data' / 'search-attempts.json').write_text(json.dumps(data['m4_search_attempts_raw']))
    (SCRATCH / 'data' / 'experiments.json').write_text(json.dumps(data['m4_experiments_raw']))
    front = SCRATCH / 'frontend'
    front.mkdir()
    for name in ('src', 'tests'):
        shutil.copytree(ROOT / 'frontend' / name, front / name, ignore=shutil.ignore_patterns('.results'))
    for name in ('package.json', 'tsconfig.json', 'vite.config.ts', 'vitest.config.ts', 'local-ports.ts'):
        if (ROOT / 'frontend' / name).exists():
            shutil.copy2(ROOT / 'frontend' / name, front / name)
    (front / 'node_modules').symlink_to(ROOT / 'frontend' / 'node_modules')
    (SCRATCH / 'audit').symlink_to(ROOT / 'audit')
    (SCRATCH / 'contracts').symlink_to(ROOT / 'contracts')
    (front / 'tests' / 'fixer-contract.test.ts').write_text(SPEC)
    result = subprocess.run(['npx', 'vitest', 'run', 'tests/fixer-contract.test.ts'], cwd=front, capture_output=True, text=True,
                            env={**__import__('os').environ, 'FIXER_CONTRACT_DIR': str(SCRATCH / 'data')})
    lines = [line for line in (result.stdout + result.stderr).splitlines() if 'FIXER-CONTRACT' in line or 'Tests ' in line or '×' in line or 'Error' in line]
    print('\n'.join(lines))
    print('exit', result.returncode)
    shutil.rmtree(SCRATCH)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
