"""Fixer: failing-then-passing proof for every fix, as negative-control mutations ($0, offline).

Each mutation puts back the builder's behaviour for ONE fix (or re-applies one of the reviewers' surviving mutations) in a
SCRATCH COPY of the working tree, never on the Desktop tree, and runs the tests that pin that fix. A mutation is CAUGHT
when the tests fail. The baseline (the fixed code, unmutated) must pass first. The original file is restored and its
sha256 re-checked after every mutation. The scratch tree is deleted at the end.

Scratch tree: /Users/shree/FaultLab_Scratch/fixer/mut-tree (outside the synced Desktop), holding backend/, contracts/,
scripts/ and frontend/{src,tests,config files} copied, frontend/node_modules as a symlink to the real one, and audit/
development|freeze|portability|search-comparison.json copied. audit/promotion.json and audit/final-audit.json are SYMLINKS
to the real files, created without opening them, so the product's own plan code can hash the promotion manifest in tests
exactly as it does in the working tree (the integrity reviewer did the same and disclosed it). No .env is copied.

Run from anywhere:  /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python -B mutation_checks.py
Backend tests run under guard.py (refuses the real .env and every non-loopback socket); frontend tests run with vitest.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab')
HERE = Path(__file__).resolve().parent
M = Path('/Users/shree/FaultLab_Scratch/fixer/mut-tree')
PY = str(ROOT / '.venv/bin/python')


def build_tree():
    shutil.rmtree(M, ignore_errors=True)
    M.mkdir(parents=True)
    ignore = shutil.ignore_patterns('__pycache__', '.pytest_cache', '*.pyc', '.env', '.env.*')
    for name in ('backend', 'contracts', 'scripts'):
        shutil.copytree(ROOT / name, M / name, ignore=ignore, symlinks=True)
    (M / 'frontend').mkdir()
    for name in ('src', 'tests'):
        shutil.copytree(ROOT / 'frontend' / name, M / 'frontend' / name, ignore=shutil.ignore_patterns('.results'), symlinks=True)
    for name in ('package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts', 'index.html', 'local-ports.ts'):
        shutil.copy2(ROOT / 'frontend' / name, M / 'frontend' / name)
    os.symlink(ROOT / 'frontend' / 'node_modules', M / 'frontend' / 'node_modules')
    (M / 'audit').mkdir()
    for name in ('development.json', 'freeze.json', 'portability.json', 'search-comparison.json'):
        shutil.copy2(ROOT / 'audit' / name, M / 'audit' / name)
    for name in ('promotion.json', 'final-audit.json'):
        os.symlink(ROOT / 'audit' / name, M / 'audit' / name)   # never opened here; the product code under test reads it
    shutil.copy2(HERE / 'guard.py', M / 'guard.py')
    (M / 'run_guarded.py').write_text('''import sys
sys.path.insert(0, %r)
import guard
import pytest
code = pytest.main(['-q', '-p', 'no:cacheprovider', '-W', 'ignore::DeprecationWarning', *sys.argv[1:]])
print('[mut] refused outbound', len(guard.REFUSED), file=sys.stderr)
sys.exit(code)
''' % str(M))


FIX = ['tests/lab/test_history_fireability_review_fixes.py']
FIRE = FIX + ['tests/lab/test_history_fireability.py']
FRONT = ['tests/history-fireability-fixes.test.tsx', 'tests/history-fireability.test.tsx', 'tests/evidence-wait.test.tsx']

# (name, 'backend' or 'frontend', file relative to that folder, anchor, replacement, tests)
MUTATIONS = [
    # --- MEDIUM-1 / F1: put back the builder's "any fault on a REFUSED target" rule
    ('X1 MEDIUM-1: refuse a pick if ANY fault targets a REFUSED row (the builder\'s rule)', 'backend', 'app/lab/fireability.py',
     "    if len(refused) < len(decision['targets']):", "    if not refused:", FIX),
    ('X2 MEDIUM-1: the declaration no longer states pick_refused_when', 'backend', 'app/lab/fireability.py',
     "            'pick_refused_when': PICK_REFUSED_WHEN, 'min_verified_episodes'", "            'min_verified_episodes'", FIX),
    # --- F2 (model side): the request no longer says the rule qualifies the Explorer's instructions
    ('X3 F2: the Explorer request block without the precedence note', 'backend', 'app/lab/fireability.py',
     "    block = {'rule': RULE, 'meaning': MEANING, 'note': EXPLORER_NOTE, ", "    block = {'rule': RULE, 'meaning': MEANING, ", FIX),
    # --- F3: put back the builder's full scans on each dashboard poll
    ('X4 F3: every selection parsed on each poll', 'backend', 'app/lab/fireability.py',
     "    for selection in store.get_records('selections', ids):", "    for selection in store.list_records('selections'):", FIX),
    ('X5 F3: every challenge parsed on each poll', 'backend', 'app/lab/fireability.py',
     "    for challenge in store.get_records('challenges', challenge_ids):", "    for challenge in store.list_records('challenges'):", FIX),
    ('X6 F3: every unrequested-slot record parsed on each poll', 'backend', 'app/lab/fireability.py',
     "    slots = _campaign_rows(store, 'explorer_selection_slots', campaign_id)",
     "    slots = [row for row in store.list_records('explorer_selection_slots') if row.get('campaign_id') == campaign_id]", FIX),
    ('X7 F3: every campaign\'s plan validated on each poll', 'backend', 'app/lab/api.py',
     "        if not counters and 'explorer_selection' in (c().store.get_record('campaign_plans',id) or {}):",
     "        if not counters:", FIX),
    # --- LOW-2: the reviewers' surviving mutations, now pinned
    ('R4 LOW-2: compute_table\'s binding to the history\'s episode ids removed', 'backend', 'app/lab/fireability.py',
     "    if content_hash(sorted(ids)) != history['episode_ids_hash'] or len(ids) != history['summary']['verified_episodes']:",
     "    if False:", FIX),
    ('R15 LOW-2: challenge state never reset between challenges', 'backend', 'app/lab/fireability.py',
     "        if self.challenge is None or self.challenge.key != key or context.get('proposal_index') == 0:",
     "        if self.challenge is None:", FIX),
    ('R16 LOW-2 (near-equivalent, pinned anyway): a missing fault execution counts as fired', 'backend', 'app/lab/fireability.py',
     "            targets.setdefault(key, []).append(execution.get('triggered') is True)",
     "            targets.setdefault(key, []).append(execution.get('triggered') is not False)", FIRE),
    # --- frontend: MEDIUM-1, F2 and F4
    ('FX1 MEDIUM-1: an allowed decision may not name a REFUSED target (the builder\'s validator)', 'frontend', 'src/historyFireability.ts',
     "  if (value.status === 'ALLOWED') return targets.length > 0 && refusedRows < targets.length && (refusedRows === 0 || text(value.reason))",
     "  if (value.status === 'ALLOWED') return refusedRows === 0", FRONT),
    ('FX2 MEDIUM-1: the offered and saved rule accepted without pick_refused_when', 'frontend', 'src/historyFireability.ts',
     "    && value.pick_refused_when === 'every_fault_on_a_refused_target'\n", "", FRONT),
    ('FX3 F2: the discovery budget says "no re-plans" under the rule', 'frontend', 'src/components/DiscoveryProtocol.tsx',
     ": fireability ? `one re-plan per pick refused by history fireability, inside the same ${declaration.explorer_requests_max} Explorer requests` : 'no re-plans'}`",
     ": 'no re-plans'}`", FRONT),
    ('FX4 F2: the dispatch text is not qualified under the rule', 'frontend', 'src/components/DiscoveryProtocol.tsx',
     "    {fireability && <p className=\"muted\">{FIREABILITY_DISPATCH}</p>}\n", "", FRONT),
    ('FX5 F4: "Refused: Refused before any episode ran"', 'frontend', 'src/historyFireability.ts',
     "    return decision.slot_request === 2 ? `Re-plan. ${reason}` : reason\n",
     "    return `Refused${replan}: ${reason}`\n", FRONT),
    ('FX6 F4: the REFUSED row of the frozen table not marked', 'frontend', 'src/components/LoopLimits.tsx',
     " className={row.status === 'REFUSED' ? 'fireability-refused' : ''}", "", FRONT),
    ('FX7 F4: the evidence retry rule id not named beside its cap', 'frontend', 'src/components/CampaignPlan.tsx',
     " under rule ${plan.evidence_retry.protocol} (after", " (after", FRONT),
    ('FX8 MEDIUM-1 read-out: the challenge panel does not say which targets never ran alone', 'frontend', 'src/components/LoopLimits.tsx',
     "    {!!summary.refused_targets.length && <p className=\"muted\">Refused on their own in this campaign:",
     "    {false && <p className=\"muted\">Refused on their own in this campaign:", FRONT),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(side, tests):
    started = time.time()
    if side == 'backend':
        proc = subprocess.run([PY, '-B', str(M / 'run_guarded.py'), *tests], cwd=M / 'backend', capture_output=True, text=True,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1'})
        tail = (proc.stdout.strip().splitlines() or [''])[-1]
        guard = [line for line in proc.stderr.splitlines() if line.startswith('[mut] refused outbound')]
        return proc.returncode, tail, guard[-1] if guard else 'guard line missing', round(time.time() - started)
    proc = subprocess.run(['npx', 'vitest', 'run', *tests], cwd=M / 'frontend', capture_output=True, text=True)
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip().startswith('Tests ')]
    return proc.returncode, lines[-1] if lines else (proc.stdout.strip().splitlines() or [''])[-1], 'vitest (no network in these tests)', round(time.time() - started)


def main():
    build_tree()
    results = []
    try:
        for side, tests in (('backend', FIRE), ('frontend', FRONT)):
            code, tail, guard_line, secs = run(side, tests)
            results.append({'mutation': f'BASELINE {side} (the fixed code, no mutation)', 'exit': code, 'tail': tail, 'guard': guard_line, 'seconds': secs})
            print(json.dumps(results[-1]), flush=True)
            assert code == 0, 'baseline must pass'
        for name, side, rel, old, new, tests in MUTATIONS:
            path = M / side / rel
            original = path.read_text(); before = sha(path)
            if original.count(old) != 1:
                results.append({'mutation': name, 'error': f'anchor found {original.count(old)} times'}); print(json.dumps(results[-1]), flush=True); continue
            path.write_text(original.replace(old, new))
            try:
                code, tail, guard_line, secs = run(side, tests)
            finally:
                path.write_text(original)
            results.append({'mutation': name, 'file': f'{side}/{rel}', 'caught': code != 0, 'exit': code, 'tail': tail, 'guard': guard_line,
                            'seconds': secs, 'restored_sha256_identical': sha(path) == before})
            print(json.dumps(results[-1]), flush=True)
    finally:
        shutil.rmtree(M, ignore_errors=True)
    print(json.dumps({'caught': sum(1 for r in results if r.get('caught')), 'mutations': sum(1 for r in results if 'caught' in r),
                      'survived': [r['mutation'] for r in results if r.get('caught') is False],
                      'anchor_errors': [r['mutation'] for r in results if 'error' in r],
                      'all_restored': all(r.get('restored_sha256_identical', True) for r in results),
                      'scratch_removed': not M.exists()}))


main()
