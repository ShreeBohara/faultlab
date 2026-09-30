"""Negative controls for the fixer's changes (September 30 review findings): each new test FAILS on the code before its fix.

Same method as builder/mutation_checks.py: each check builds a scratch copy OUTSIDE the cloud-synced Desktop
(/Users/shree/FaultLab_Scratch/fixer-v4/mutation-tree), applies ONE mutation -- the file as it was before the fix
(fixer/before/files/, saved from the working tree before any fixer edit) or a one-line mutant of the fix -- and runs the
named tests there. CAUGHT means the tests failed on the mutated copy; CONTROL lines show the tests pass on an unmutated
copy. EXPECT-PASS lines are characterization checks that must pass on the pre-fix code too (the loop is unchanged).
The working tree is never modified. backend/app/referee is symlinked, never copied or read; contracts, audit,
taskpacks, scripts and docs are symlinked. Frontend checks copy frontend/src and frontend/tests and symlink
node_modules. No .env exists in the scratch root; pytest runs with PYTHON_DOTENV_DISABLED and no bytecode or cache.

Run from faultlab/:  .venv/bin/python artifacts/product-discovery-v4-2026-09-30/fixer/mutation_checks.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BEFORE = Path(__file__).resolve().parent / 'before' / 'files'
SCRATCH = Path('/Users/shree/FaultLab_Scratch/fixer-v4/mutation-tree')
PYTHON = ROOT / '.venv' / 'bin' / 'python'
FIXES = 'tests/lab/test_discovery_v4_review_fixes.py'
T_MEDIUM1 = f'{FIXES}::test_a_replay_episode_never_enters_a_later_agent_history_but_the_explorers_pick_does'
T_F2_TEXT = f'{FIXES}::test_the_chooser_and_the_plan_say_a_replay_source_can_use_up_the_candidate_requests'
T_F2_LOOP = f'{FIXES}::test_the_unchanged_loop_ends_discovery_when_a_replay_source_uses_up_the_candidate_requests'
T_F4 = f'{FIXES}::test_a_v4_recording_names_v4_in_its_history_claim_rule_and_a_v3_recording_keeps_its_exact_text'
RELATED = [FIXES, 'tests/lab/test_discovery_v4_replay.py', 'tests/lab/test_agent_history.py', 'tests/lab/test_discovery_v3_flow.py',
           'tests/lab/test_discovery_v3_baseline_history.py']
FRONT = ['tests/discovery-v4.test.tsx']


def mutant(path, before, after):
    def apply(root):
        text = (root / path).read_text()
        assert text.count(before) == 1, (path, before)
        (root / path).write_text(text.replace(before, after))
    return apply


def restore(*paths):
    def apply(root):
        for path in paths:
            shutil.copy2(BEFORE / path, root / path)
    return apply


HISTORY = 'backend/app/lab/agent_history.py'
REPLAY = 'backend/app/lab/history_replay.py'
PLANS = 'backend/app/lab/run_plans.py'
EXPORTS = 'backend/app/lab/exports.py'
BACKEND_CHECKS = [
    ('MEDIUM-1/F3: agent_history.py as before the fix (replay episodes counted as learn discovery)', restore(HISTORY), [T_MEDIUM1]),
    ('MEDIUM-1/F3: the replay-episode exclusion disabled',
     mutant(HISTORY, "        if episode.get('episode_id') in replayed:\n", "        if False:\n"), [T_MEDIUM1]),
    ('MEDIUM-1/F3: replay selection records not collected',
     mutant(HISTORY, "                replayed.add(selection['history_replay.episode_id'])\n", "                pass\n"), [T_MEDIUM1]),
    ('F2: chooser sentence as before the fix (run_plans.py)', restore(PLANS), [T_F2_TEXT]),
    ('F2: saved-plan statement as before the fix (history_replay.py)', restore(REPLAY), [T_F2_TEXT]),
    ('F4: exports.py as before the fix (v4 recording says "discovery v3")', restore(EXPORTS), [T_F4]),
    ('F4: a v3 recording gets the v4 claim text',
     mutant(EXPORTS, "'claim_rule':V3_HISTORY_CLAIM_RULE if replay is None else V4_HISTORY_CLAIM_RULE}", "'claim_rule':V4_HISTORY_CLAIM_RULE}"), [T_F4]),
    ('F4: a v4 recording keeps the v3 claim text',
     mutant(EXPORTS, "'claim_rule':V3_HISTORY_CLAIM_RULE if replay is None else V4_HISTORY_CLAIM_RULE}", "'claim_rule':V3_HISTORY_CLAIM_RULE}"), [T_F4]),
]
# Must PASS on the code before every backend fix: the loop behaviour the F2 sentence describes is unchanged, not new.
EXPECT_PASS = [('F2 characterization: the unchanged loop ends discovery after a replay source uses all candidate requests '
                '(all four backend files as before the fixes)', restore(HISTORY, REPLAY, PLANS, EXPORTS), [T_F2_LOOP])]
PANEL = 'frontend/src/components/SearchAttemptsPanel.tsx'
FRONT_CHECKS = [
    ('F1: SearchAttemptsPanel.tsx as before the fix', restore(PANEL), FRONT),
    ('F1: the panel shows the old fixed sentence ("the Explorer chose the remaining slots")',
     mutant(PANEL, '{!!replays.length && <p className="muted">{replaySummaryText(rows ?? [])}</p>}',
            '{!!replays.length && <p className="muted">Discovery protocol v4: the first {replays.length === 1 ? \'slot was a history replay\' : `${replays.length} slots were history replays`} of the frozen agent history (see the saved plan), with no Explorer request; the Explorer chose the remaining slots.</p>}'), FRONT),
    ('LOW-2: DiscoveryProtocol.tsx as before the fix', restore('frontend/src/components/DiscoveryProtocol.tsx'), FRONT),
    ('LOW-2: a no-case replay row labelled "(Explorer pick)" again',
     mutant('frontend/src/components/DiscoveryProtocol.tsx', '({row.development_case_id ?? NO_CASE_REPLAY_ROW})',
            "{row.development_case_id ? ` (${row.development_case_id})` : ' (Explorer pick)'}"), FRONT),
    ('LOW-3: RunSummary.tsx as before the fix', restore('frontend/src/components/RunSummary.tsx'), FRONT),
    ('LOW-3: the run summary drops the Found-by line',
     mutant('frontend/src/components/RunSummary.tsx', '{foundBy && <p className="muted summary-found-by">{foundBy}</p>}', '{null}'), FRONT),
]


def build(front=False):
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    if front:
        (SCRATCH / 'frontend').mkdir()
        for name in ('src', 'tests'):
            shutil.copytree(ROOT / 'frontend' / name, SCRATCH / 'frontend' / name, ignore=shutil.ignore_patterns('.results'))
        for name in ('package.json', 'tsconfig.json', 'vite.config.ts', 'vitest.config.ts', 'local-ports.ts'):
            if (ROOT / 'frontend' / name).exists():
                shutil.copy2(ROOT / 'frontend' / name, SCRATCH / 'frontend' / name)
        (SCRATCH / 'frontend' / 'node_modules').symlink_to(ROOT / 'frontend' / 'node_modules')
        (SCRATCH / 'audit').symlink_to(ROOT / 'audit')
        (SCRATCH / 'contracts').symlink_to(ROOT / 'contracts')
        return
    def ignore(directory, names):
        skip = {'__pycache__', '.pytest_cache'}
        if Path(directory) == ROOT / 'backend' / 'app':
            skip.add('referee')
        return [name for name in names if name in skip]
    shutil.copytree(ROOT / 'backend', SCRATCH / 'backend', ignore=ignore)
    (SCRATCH / 'backend' / 'app' / 'referee').symlink_to(ROOT / 'backend' / 'app' / 'referee')
    for name in ('contracts', 'audit', 'taskpacks', 'scripts', 'docs'):
        (SCRATCH / name).symlink_to(ROOT / name)


def run(tests, front=False):
    if front:
        result = subprocess.run(['npx', 'vitest', 'run', *tests], cwd=SCRATCH / 'frontend', capture_output=True, text=True)
        lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
        summary = next((line.strip() for line in lines if line.strip().startswith('Tests ')), lines[-1] if lines else '(no output)')
        failed = [line.strip() for line in lines if line.strip().startswith('×') or line.strip().startswith('FAIL ')][:8]
        return result.returncode, summary + ''.join(f'\n      {name}' for name in failed)
    result = subprocess.run([str(PYTHON), '-m', 'pytest', '-q', '-rfE', '-p', 'no:cacheprovider', *tests], cwd=SCRATCH / 'backend',
                            capture_output=True, text=True, env={'PATH': '/usr/bin:/bin', 'PYTHON_DOTENV_DISABLED': '1',
                                                                 'PYTHONDONTWRITEBYTECODE': '1', 'HOME': str(SCRATCH)})
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    failed = [line.split(' - ')[0] for line in lines if line.startswith(('FAILED ', 'ERROR '))]
    return result.returncode, (lines[-1] if lines else '(no output)') + ''.join(f'\n      {name}' for name in failed)


def main():
    lines, ok = [], True
    for front, checks, control in ((False, BACKEND_CHECKS, RELATED), (True, FRONT_CHECKS, FRONT)):
        build(front)
        code, summary = run(control, front)
        lines.append(f'CONTROL unmutated {"frontend" if front else "backend"} copy ({" ".join(control)}): exit {code}: {summary}')
        print(lines[-1], flush=True)
        ok &= code == 0
        for name, apply, tests in checks:
            build(front)
            apply(SCRATCH)
            code, summary = run(tests, front)
            caught = code != 0
            ok &= caught
            lines.append(f'{"CAUGHT " if caught else "MISSED "} {name}: exit {code}: {summary}')
            print(lines[-1], flush=True)
        if not front:
            for name, apply, tests in EXPECT_PASS:
                build(False)
                apply(SCRATCH)
                code, summary = run(tests)
                ok &= code == 0
                lines.append(f'{"EXPECT-PASS ok " if code == 0 else "EXPECT-PASS FAILED "} {name}: exit {code}: {summary}')
                print(lines[-1], flush=True)
    shutil.rmtree(SCRATCH.parent)
    lines.append('ALL MUTATIONS CAUGHT, CONTROLS PASS' if ok else 'SOME MUTATION NOT CAUGHT OR A CONTROL FAILED')
    print('\n'.join(lines))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
