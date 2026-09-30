"""Negative controls for discovery v4 (history replay): each new test must FAIL on deliberately broken code ($0, offline).

Each check builds a scratch copy OUTSIDE the cloud-synced Desktop (/Users/shree/FaultLab_Scratch/discovery-v4-builder/),
applies ONE mutation -- either the pre-round files from backup/part2-2026-09-22 (via `git show`, read-only) or a one-line
mutant of the new code -- and runs the named tests there. A check passes when the tests fail on the mutated copy; the
CONTROL line shows the same tests pass on an unmutated copy. The working tree is never modified. backend/app/referee
(gates, unchanged) is symlinked, never copied or read here; contracts, audit, taskpacks, scripts and docs are symlinked.
Frontend checks copy frontend/src and frontend/tests and symlink node_modules. No .env exists in the scratch root.

Run from faultlab/:  .venv/bin/python artifacts/product-discovery-v4-2026-09-30/builder/mutation_checks.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path('/Users/shree/FaultLab_Scratch/discovery-v4-builder/mutation-tree')
PYTHON = ROOT / '.venv' / 'bin' / 'python'
BRANCH = 'backup/part2-2026-09-22'
V4 = ['tests/lab/test_discovery_v4_replay.py']
FRONT = ['tests/discovery-v4.test.tsx']


def old(path):
    return subprocess.run(['git', '-C', str(ROOT), 'show', f'{BRANCH}:{path}'], check=True, capture_output=True, text=True).stdout


def mutant(path, before, after):
    def apply(root):
        text = (root / path).read_text()
        assert text.count(before) == 1, (path, before)
        (root / path).write_text(text.replace(before, after))
    return apply


def restore(*paths, remove=()):
    def apply(root):
        for path in paths:
            (root / path).write_text(old(path))
        for path in remove:
            (root / path).unlink()
    return apply


LEARN = 'backend/app/lab/learning.py'
REPLAY = 'backend/app/lab/history_replay.py'
PLANS = 'backend/app/lab/run_plans.py'
BACKEND_CHECKS = [
    ('every backend file of this round as before it (backup branch; history_replay.py removed)',
     restore('backend/app/lab/discovery_protocol.py', LEARN, PLANS, 'backend/app/agents/explorer.py', 'backend/app/lab/api.py',
             'backend/app/lab/exports.py', remove=(REPLAY, 'backend/app/agents/prompts/explorer_discovery_v4_history_replay.md')), V4),
    ('replay slots never run (the Explorer takes every slot)',
     mutant(LEARN, '            if selection_index<len(replays):', '            if False:'), V4),
    ('a replay row need not fire every fault in every verified episode',
     mutant(REPLAY, '            and fired == verified and violation_share(row)', '            and violation_share(row)'), V4),
    ('violation share threshold 1/2 instead of 2/3',
     mutant(REPLAY, 'MIN_VIOLATION_SHARE = Fraction(2, 3)', 'MIN_VIOLATION_SHARE = Fraction(1, 2)'), V4),
    ('at most 4 replays instead of 3',
     mutant(REPLAY, 'MAX_REPLAYS = 3\n', 'MAX_REPLAYS = 4\n'), V4),
    ('ties on share not broken by verified episodes',
     mutant(REPLAY, "-violation_share(item[1]), -item[1]['verified_episodes'], item[0]", "-violation_share(item[1]), item[0]"), V4),
    ('a no-fault row may be replayed',
     mutant(REPLAY, "    return (bool(row.get('primitives')) and fired is not None and verified >= MIN_VERIFIED_EPISODES\n            and fired == verified",
            "    return (verified >= MIN_VERIFIED_EPISODES\n            and (fired is None or fired == verified)"), V4),
    ('a replay record is hidden from the Explorer search ledger (no development_history in its context)',
     mutant(REPLAY, "'context': {**slot_context, 'discovery_protocol': protocol}",
            "'context': {**{k: v for k, v in slot_context.items() if k != 'development_history'}, 'discovery_protocol': protocol}"), V4),
    ('a replay record claims a model call',
     mutant(REPLAY, "'usage': {'model_calls': 0,", "'usage': {'model_calls': 1,"), V4),
    ('the v4 prompt section is appended even with an empty replay list',
     mutant(LEARN, "    if (plan['discovery'].get('replay') or {}).get('rows'): result['replay_prompt']=True",
            "    if plan['discovery'].get('replay') is not None: result['replay_prompt']=True"), V4),
    ('the v4 prompt section is never appended',
     mutant('backend/app/agents/explorer.py', "+('\\n'+DISCOVERY_V4_PROMPT if history is not None and history.get('replay_prompt') else '')", ''), V4),
    ('search-attempts API drops the history replay label',
     mutant('backend/app/lab/api.py', "**({'history_replay':row['history_replay']} if 'history_replay' in row else {})})",
            "})"), V4),
    ('source projection never names the replay that found a source',
     mutant('backend/app/lab/api.py', "row['history_replay']=replay_sources.get(counter['source_episode_id'])", "row['history_replay']=None"), V4),
    ('recording drops the replay label from selections',
     mutant('backend/app/lab/exports.py', ",'matches_history_row','history_replay')", ",'matches_history_row')"), V4),
    ('Start does not recompute the replay list',
     mutant(PLANS, "        history_replay.verify(plan['discovery'].get('replay'), history)\n", ''), V4),
    ('the plan does not freeze the replay list (empty list whatever the history)',
     mutant(PLANS, "            discovery['replay'] = history_replay.plan_block(discovery['history'])",
            "            discovery['replay'] = {**history_replay.plan_block(discovery['history']), 'rows': [], 'status': 'EMPTY'}"), V4),
]
FRONT_CHECKS = [
    ('frontend: a replay row may claim a model call',
     mutant('frontend/src/searchAttempts.ts', '(replay ? 0 : 1 + ', '(replay ? 1 : 1 + '), FRONT),
    ('frontend: a saved v4 plan is accepted without checking its replay list',
     mutant('frontend/src/runPlans.ts', "  if (value.protocol === REPLAY_PROTOCOL ? !(saved ? historyReplay(value.replay, value.history) : value.replay === null) : value.replay !== undefined) return false\n", ''), FRONT),
    ('frontend: the saved plan does not show the replay list',
     mutant('frontend/src/components/DiscoveryProtocol.tsx', '{replayed && (declaration.replay ? <HistoryReplayFacts replay={declaration.replay} /> : <p className="muted">{REPLAY_AT_PLAN_TIME}</p>)}', '{null}'), FRONT),
    ('frontend: the source panel does not say which replay found a source',
     mutant('frontend/src/components/CounterexamplePanel.tsx', '{record.history_replay !== undefined && <Field name="Found by">', '{false && <Field name="Found by">'), FRONT),
    ('frontend: the fault-search panel labels a replay as an ordinary selection',
     mutant('frontend/src/components/SearchAttemptsPanel.tsx', "{row.history_replay ? `${historyReplayTitle(row.history_replay)} · no Explorer request` : decisionLabel[row.search_decision.status]}",
            '{decisionLabel[row.search_decision.status]}'), FRONT),
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
        failed = [line.strip() for line in lines if line.strip().startswith('×') or line.strip().startswith('FAIL ')][:6]
        return result.returncode, summary + ''.join(f'\n      {name}' for name in failed)
    result = subprocess.run([str(PYTHON), '-m', 'pytest', '-q', '-rfE', '-p', 'no:cacheprovider', *tests], cwd=SCRATCH / 'backend',
                            capture_output=True, text=True, env={'PATH': '/usr/bin:/bin', 'PYTHON_DOTENV_DISABLED': '1', 'HOME': str(SCRATCH)})
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    failed = [line.split(' - ')[0] for line in lines if line.startswith(('FAILED ', 'ERROR '))]
    return result.returncode, (lines[-1] if lines else '(no output)') + ''.join(f'\n      {name}' for name in failed)


def main():
    lines, ok = [], True
    for front, checks, tests in ((False, BACKEND_CHECKS, V4), (True, FRONT_CHECKS, FRONT)):
        build(front)
        code, summary = run(tests, front)
        lines.append(f'CONTROL unmutated {"frontend" if front else "backend"} copy: exit {code}: {summary}')
        ok &= code == 0
        for name, apply, check_tests in checks:
            build(front)
            apply(SCRATCH)
            code, summary = run(check_tests, front)
            caught = code != 0
            ok &= caught
            lines.append(f'{"CAUGHT " if caught else "MISSED "} {name}: exit {code}: {summary}')
            print(lines[-1], flush=True)
    shutil.rmtree(SCRATCH)
    lines.append('ALL MUTATIONS CAUGHT' if ok else 'SOME MUTATION NOT CAUGHT')
    print('\n'.join(lines))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
