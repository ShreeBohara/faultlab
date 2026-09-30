"""Independent verifier (discovery v4 review round, 2026-09-30), steps 4 and 5. $0, offline.

CLEAN COPY (step 5: new tests must not depend on git-ignored files)
  /Users/shree/FaultLab_Scratch/verify-v4/clean (outside the synced Desktop) =
    `git archive 4d1c21b` (backup/part2-2026-09-22) WITHOUT artifacts/, audit/promotion.json, audit/final-audit.json
    (never extracted; revision 2: the two audit JSONs are then SYMLINKED to the real tracked files, see build())
  + the 25 changed/new product files copied byte for byte from the working tree (sha256 checked against my commit list).
  No .env, no caches, no git-ignored file. The real .venv interpreter is used (installed environment; no .pth/editable
  install points at the real tree; pytest.ini sets pythonpath = . so the copy imports its own code), and
  frontend/node_modules is a symlink to the real installed packages (installed environment), removed afterwards.
  Runs: the new and changed backend test files plus the v2/v3 flow files they import; the whole frontend unit suite.

MUTANTS (step 4: my own negative controls, different from the fixer's 14)
  Each mutant is one exact string replacement (asserted to occur exactly once) in the clean copy, followed by the named
  tests; the file is restored byte for byte afterwards (sha256 re-checked). CAUGHT = the tests fail on the mutant.
All Python runs load the verifier guard (no outside connection, no .env); Node runs load the Node guard.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab')
V = ROOT / 'artifacts/product-discovery-v4-2026-09-30/verify'
OUT = V / 'clean_copy'
CLEAN = Path('/Users/shree/FaultLab_Scratch/verify-v4/clean')
TIP = '4d1c21ba83fea229c23ee086e6b566000fb8640a'
PY = str(ROOT / '.venv/bin/python')

BACKEND_TESTS = ['tests/lab/test_discovery_v4_review_fixes.py', 'tests/lab/test_discovery_v4_replay.py',
                 'tests/lab/test_agent_history.py', 'tests/lab/test_discovery_v3_flow.py', 'tests/lab/test_discovery_v2_flow.py',
                 'tests/lab/test_discovery_v3_baseline_history.py']
FIXES = 'tests/lab/test_discovery_v4_review_fixes.py'
T_MEDIUM1 = f'{FIXES}::test_a_replay_episode_never_enters_a_later_agent_history_but_the_explorers_pick_does'
T_F2 = f'{FIXES}::test_the_chooser_and_the_plan_say_a_replay_source_can_use_up_the_candidate_requests'
T_F4 = f'{FIXES}::test_a_v4_recording_names_v4_in_its_history_claim_rule_and_a_v3_recording_keeps_its_exact_text'
FRONT = ['tests/discovery-v4.test.tsx']

HISTORY = 'backend/app/lab/agent_history.py'
REPLAY = 'backend/app/lab/history_replay.py'
EXPORTS = 'backend/app/lab/exports.py'
PANEL = 'frontend/src/components/SearchAttemptsPanel.tsx'
SUMMARY = 'frontend/src/components/RunSummary.tsx'
PROTO = 'frontend/src/components/DiscoveryProtocol.tsx'

BACKEND_MUTANTS = [
    ('M1 MEDIUM-1: replay skip applied only to baseline-study episodes (a replay is learn_discovery, so it is counted again)',
     HISTORY, "        if episode.get('episode_id') in replayed:\n",
     "        if episode.get('episode_id') in replayed and source == 'baseline_study':\n", [T_MEDIUM1]),
    ('M2 MEDIUM-1: over-broad skip (every learn_discovery episode dropped once any replay exists: the Explorer pick is lost too)',
     HISTORY, "        if episode.get('episode_id') in replayed:\n",
     "        if episode.get('episode_id') in replayed or (replayed and source == 'learn_discovery'):\n", [T_MEDIUM1]),
    ('M3 MEDIUM-1: wrong field read from the replay selection (history_replay.selection_id, absent: nothing collected)',
     HISTORY, "'provenance', 'history_replay.episode_id')):", "'provenance', 'history_replay.selection_id')):", [T_MEDIUM1]),
    ('M4 MEDIUM-1: replay episodes counted as excluded instead of silently skipped',
     HISTORY, "            continue  # a discovery v4 history replay: FaultLab's pick, not the Explorer's; never used, not counted\n",
     "            excluded['lab_error'] += 1; continue\n", [T_MEDIUM1]),
    ('M5 F2: saved-plan statement says "at most 3" candidate requests',
     REPLAY, "(at most 4) are used up there", "(at most 3) are used up there", [T_F2]),
    ('M6 F2: saved-plan statement drops "later replays and Explorer slots do not run"',
     REPLAY, "discovery ends and later '\n                       'replays and Explorer slots do not run.')",
     "discovery ends.')", [T_F2]),
    ('M7 F4: v4 claim rule mentions v3 again',
     EXPORTS, "V4_HISTORY_CLAIM_RULE=('Results of a discovery v4 campaign are history-informed.",
     "V4_HISTORY_CLAIM_RULE=('Results of a discovery v4 campaign (like v3) are history-informed.", [T_F4]),
]
FRONT_MUTANTS = [
    ('M8 F1: every row counted as an Explorer slot (replays included)',
     PANEL, "new Set(rows.filter(row => !row.history_replay).map(row => row.selection_index)).size",
     "new Set(rows.map(row => row.selection_index)).size", FRONT),
    ('M9 F1: with no Explorer record the panel still says the Explorer chose the next slots',
     PANEL, "  return explorerSlots\n", "  return true\n", FRONT),
    ('M10 LOW-3: an Explorer pick (history_replay null) treated like a non-v4 campaign (no Found-by line)',
     SUMMARY, "record?.history_replay === undefined ? null", "record?.history_replay == null ? null", FRONT),
    ('M11 LOW-3: the two Found-by texts swapped',
     SUMMARY, "  : record.history_replay ? `Found by", "  : !record.history_replay ? `Found by", FRONT),
    ('M12 LOW-2: the no-case label reads as an Explorer pick',
     PROTO, "export const NO_CASE_REPLAY_ROW = 'no development case: a recipe first picked by the Explorer in an earlier learn campaign'",
     "export const NO_CASE_REPLAY_ROW = 'Explorer pick'", FRONT),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def env_py():
    e = {k: v for k, v in os.environ.items() if k not in ('WANDB_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')}
    e.update(PYTHONPATH=str(V / 'guard'), VERIFY_GUARD_LOG=str(OUT / 'guard-python.jsonl'), PYTHONDONTWRITEBYTECODE='1')
    return e


def env_node():
    e = {k: v for k, v in os.environ.items() if k not in ('WANDB_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')}
    e.update(NODE_OPTIONS=f"--require {V / 'guard/node-guard.cjs'}", VERIFY_NODE_GUARD_LOG=str(OUT / 'guard-node.jsonl'))
    return e


def build():
    if CLEAN.exists():
        shutil.rmtree(CLEAN)
    CLEAN.mkdir(parents=True)
    archive = subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', TIP], capture_output=True, check=True).stdout
    subprocess.run(['tar', '-x', '-C', str(CLEAN), '--exclude=artifacts/*', '--exclude=artifacts',
                    '--exclude=audit/promotion.json', '--exclude=audit/final-audit.json'], input=archive, check=True)
    # Revision 2 (after run 1, kept in clean_copy/run1/): product code opens audit/promotion.json through
    # run_plans._manifests -> referee.manifests.load_manifest (59 of 72 tests failed with FileNotFoundError without it).
    # Both files are TRACKED (a clean clone has them), so they are provided as SYMLINKS to the real files, exactly as the
    # native v2b verifier did: no copy is made and the verifier never opens them; only the product's loader does.
    for name in ('audit/promotion.json', 'audit/final-audit.json'):
        (CLEAN / name).symlink_to(ROOT / name)
    listed = {}
    for line in (V / 'commit_list/pass1_before_suite.txt').read_text().splitlines():
        digest, path = line.split('  ', 1)
        if not path.startswith('artifacts/'):
            listed[path] = digest
    copied = []
    for path, digest in sorted(listed.items()):
        assert sha(ROOT / path) == digest, path
        (CLEAN / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, CLEAN / path)
        assert sha(CLEAN / path) == digest, path
        copied.append(f'{digest}  {path}')
    (OUT / 'copied-files.txt').write_text('\n'.join(copied) + '\n')
    absent = [p for p in ('.env', 'artifacts', 'frontend/node_modules', 'frontend/dist')
              if (CLEAN / p).exists() or (CLEAN / p).is_symlink()]
    (OUT / 'tree-facts.txt').write_text(f'copied product files: {len(copied)} (all sha256 equal to COMMIT_LIST product lines)\n'
                                        f'present that should be absent: {absent}\n')
    return len(copied), absent


def run_backend(tests, log):
    r = subprocess.run([PY, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *tests], cwd=CLEAN / 'backend', env=env_py(),
                       capture_output=True, text=True)
    Path(log).write_text(r.stdout + r.stderr)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    return r.returncode, (lines[-1] if lines else '(no output)'), [l for l in r.stdout.splitlines() if l.startswith('FAILED')]


def run_front(tests, log):
    r = subprocess.run(['npx', 'vitest', 'run', *tests], cwd=CLEAN / 'frontend', env=env_node(), capture_output=True, text=True)
    Path(log).write_text(r.stdout + r.stderr)
    summary = [l.strip() for l in (r.stdout + r.stderr).splitlines() if l.strip().startswith(('Tests', 'Test Files'))]
    failed = [l.strip() for l in (r.stdout + r.stderr).splitlines() if l.strip().startswith('FAIL')]
    return r.returncode, ' | '.join(summary) or '(no summary)', failed


def mutate(path, before, after):
    target = CLEAN / path
    text = target.read_text()
    assert text.count(before) == 1, (path, before, text.count(before))
    target.write_text(text.replace(before, after))
    return text


REAL_SPEC = """
import { readFileSync, writeFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import { validateSearchAttempts } from '../src/searchAttempts'
import { validateExperiments } from '../src/experiments'
import { replaySummaryText } from '../src/components/SearchAttemptsPanel'
import { foundByText } from '../src/components/RunSummary'
const data = JSON.parse(readFileSync(process.env.VERIFY_M4_JSON as string, 'utf8'))
it('verifier: real M4 API responses through the dashboard validators', () => {
  const rows = validateSearchAttempts(data.search_attempts, data.campaign_id)
  const sentence = replaySummaryText(rows)
  const found = validateExperiments(data.experiments).counterexamples.map(record => foundByText(record))
  writeFileSync(process.env.VERIFY_M4_OUT as string, JSON.stringify({ rows: rows.length, sentence, found }, null, 1))
  expect(sentence).not.toMatch(/Explorer chose/)
  expect(found.every(line => line !== null && line.startsWith('Found by History replay '))).toBe(true)
})
"""


def real_m4():
    """F1 and LOW-3 on the REAL backend responses the fixer saved (fixer/manual-check.json, campaign M4, whose discovery
    ended after its two replays): print the exact panel sentence and Run summary lines the dashboard code produces."""
    fixer = json.loads((ROOT / 'artifacts/product-discovery-v4-2026-09-30/fixer/manual-check.json').read_text())
    data = {'campaign_id': fixer['m4']['campaign_id'], 'search_attempts': fixer['m4_search_attempts_raw'],
            'experiments': fixer['m4_experiments_raw']}
    data_path = CLEAN / 'verify-real-m4.json'
    data_path.write_text(json.dumps(data))
    spec = CLEAN / 'frontend/tests/verify-real-m4.test.ts'
    spec.write_text(REAL_SPEC)
    out_path = OUT / 'real-m4-output.json'
    if out_path.exists(): out_path.unlink()
    env = env_node(); env['VERIFY_M4_JSON'] = str(data_path); env['VERIFY_M4_OUT'] = str(out_path)
    r = subprocess.run(['npx', 'vitest', 'run', 'tests/verify-real-m4.test.ts'], cwd=CLEAN / 'frontend', env=env, capture_output=True, text=True)
    (OUT / 'real-m4.log').write_text(r.stdout + r.stderr)
    spec.unlink(); data_path.unlink()
    printed = out_path.read_text().splitlines() if out_path.exists() else ['(no output file written)']
    return r.returncode, printed


def main():
    for name in ('guard-python.jsonl', 'guard-node.jsonl'):
        (OUT / name).write_text('')
    report = []
    n, absent = build()
    report.append(f'clean copy built: {n} product files copied; unexpected paths present: {absent}')
    code, summary, failed = run_backend(BACKEND_TESTS, OUT / 'backend-new-tests.log')
    report.append(f'CLEAN backend new/changed test files ({len(BACKEND_TESTS)} files): exit {code}: {summary}')
    (CLEAN / 'frontend/node_modules').symlink_to(ROOT / 'frontend/node_modules')
    try:
        code_f, summary_f, _ = run_front(FRONT, OUT / 'frontend-new-tests.log')
        report.append(f'CLEAN frontend tests/discovery-v4.test.tsx: exit {code_f}: {summary_f}')
        code_a, summary_a, _ = run_front([], OUT / 'frontend-all-tests.log')
        report.append(f'CLEAN frontend whole unit suite: exit {code_a}: {summary_a}')
        results = []
        for label, path, before, after, tests in BACKEND_MUTANTS + FRONT_MUTANTS:
            original_text = mutate(path, before, after)
            original = hashlib.sha256(original_text.encode()).hexdigest()
            try:
                log = OUT / f"mutant-{label.split()[0]}.log"
                code_m, summary_m, failed_m = (run_backend if path.startswith('backend') else run_front)(tests, log)
            finally:
                (CLEAN / path).write_text(original_text)
                assert sha(CLEAN / path) == original, ('restore failed', path)
            caught = code_m != 0
            results.append(caught)
            report.append(f"{'CAUGHT' if caught else 'MISSED'} {label}: exit {code_m}: {summary_m}"
                          + ''.join(f'\n      {f}' for f in failed_m[:4]))
        code_c, summary_c, _ = run_backend([T_MEDIUM1, T_F2, T_F4], OUT / 'control-after-mutants-backend.log')
        code_d, summary_d, _ = run_front(FRONT, OUT / 'control-after-mutants-frontend.log')
        report.append(f'CONTROL after all mutants restored: backend exit {code_c}: {summary_c}; frontend exit {code_d}: {summary_d}')
        report.append(f'mutants caught: {sum(results)} of {len(results)}')
        code_r, printed = real_m4()
        report.append(f'REAL M4 responses (fixer/manual-check.json) through the dashboard code: exit {code_r}')
        for line in printed:
            report.append('      ' + line.strip())
    finally:
        (CLEAN / 'frontend/node_modules').unlink()
    text = '\n'.join(report) + '\n'
    (OUT / 'results.txt').write_text(text)
    print(text)


if __name__ == '__main__':
    main()
