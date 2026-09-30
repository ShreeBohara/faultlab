"""Negative controls for this round's new tests ($0, offline, network-silent like the suite itself).

Each check builds a scratch copy of backend/ (the working tree is never modified), applies ONE mutation -- either the
pre-change file from backup/part2-2026-09-22 (via `git show`, read-only) or a one-line mutant of the new code -- and
runs the named new tests there. A check passes when the tests FAIL on the mutated code (and they pass on the real
code: the CONTROL line). The first check restores the whole pre-round files, so the new tests fail at import (exit 2,
collection errors: the new names do not exist); every other check is a one-line behaviour mutant that imports cleanly. Sibling folders the tests read (contracts, audit, taskpacks, scripts, docs) and
backend/app/referee are symlinked, never copied or read here. No .env exists in the scratch root.

Run from faultlab/:  .venv/bin/python artifacts/product-native-v2b-2026-09-30/builder/mutation_checks.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SCRATCH = OUT / 'mutation-tree'
PYTHON = ROOT / '.venv' / 'bin' / 'python'
BRANCH = 'backup/part2-2026-09-22'

BACKOFF_TESTS = ['tests/agents/test_lab_role_backoff.py', 'tests/lab/test_lab_backoff_campaign.py']
LABEL_TESTS = ['tests/integrations/test_native_adapter_v2.py', 'tests/lab/test_native_v2_label_views.py']


def old(path):
    return subprocess.run(['git', '-C', str(ROOT), 'show', f'{BRANCH}:{path}'], check=True, capture_output=True, text=True).stdout


def mutant(path, before, after):
    def apply(root):
        text = (root / path).read_text()
        assert text.count(before) == 1, (path, before)
        (root / path).write_text(text.replace(before, after))
    return apply


def restore(*paths):
    def apply(root):
        for path in paths:
            (root / path).write_text(old(path))
    return apply


CHECKS = [
    ('rule v2 files as before this round (backup branch)',
     restore('backend/app/agents/transport_retry.py', 'backend/app/agents/explorer.py', 'backend/app/agents/mechanic.py',
             'backend/app/lab/learning.py', 'backend/app/lab/run_plans.py', 'backend/app/lab/provider_failures.py',
             'backend/app/lab/readiness.py'), BACKOFF_TESTS),
    ('learning loop never gives the Explorer/Mechanic the rule-v2 session',
     mutant('backend/app/lab/learning.py', 'explorer.lab_retry=mechanic.lab_retry=lab_backoff_for_campaign(',
            'explorer.lab_retry=mechanic.lab_retry=None and lab_backoff_for_campaign('), ['tests/lab/test_lab_backoff_campaign.py']),
    ('a wait ignores Stop',
     mutant('backend/app/agents/transport_retry.py', '        if stopped():\n            return True\n', ''), BACKOFF_TESTS),
    ('a retry is sent without being charged',
     mutant('backend/app/agents/transport_retry.py', 'if reason is None and not admit():', 'if reason is None and False:'),
     ['tests/agents/test_lab_role_backoff.py']),
    ('no campaign cap',
     mutant('backend/app/agents/transport_retry.py', 'if self.used >= LAB_RETRIES_PER_CAMPAIGN_MAX:', 'if False:'),
     ['tests/agents/test_lab_role_backoff.py']),
    ('waits of 1 s instead of 5/20/60',
     mutant('backend/app/agents/transport_retry.py', 'LAB_BACKOFF_SECONDS = (5, 20, 60)', 'LAB_BACKOFF_SECONDS = (1, 1, 1)'),
     BACKOFF_TESTS),
    ('Start refuses a Learn plan saved with rule v1',
     mutant('backend/app/lab/run_plans.py', "    installed = [transport_retry_declaration(actor_calls)]\n    if campaign.mode == 'learn':\n        installed.append(",
            "    installed = [] if campaign.mode == 'learn' else [transport_retry_declaration(actor_calls)]\n    if campaign.mode == 'learn':\n        installed.append("),
     ['tests/lab/test_lab_backoff_campaign.py']),
    ('error message does not say how many retries were tried',
     mutant('backend/app/lab/readiness.py', "        if isinstance(summary, dict):", "        if False:"), BACKOFF_TESTS),
    ('native adapter v2 as before this round (journal-position labels)',
     restore('backend/app/integrations/external_agent_v2.py'), LABEL_TESTS),
    ('v2 contract text for model readers as before this round (journal-label wording, constant kept for the import)',
     mutant('backend/app/lab/diagnosis.py', "                            'memory':V2_MEMORY,",
            "                            'memory':'Fresh native agent and empty native memory for each episode; the agent sees each "
            "delivered observation\\'s evidence_id as its journal label (obs-N), and its report\\'s cited labels are decoded back "
            "to the full evidence IDs before validation.',"), ['tests/lab/test_native_v2_label_views.py']),
]


def build():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir()
    # The referee (gates, never changed this round) is symlinked, not copied, so its files are not read here.
    def ignore(directory, names):
        skip = {'__pycache__', '.pytest_cache'}
        if Path(directory) == ROOT / 'backend' / 'app':
            skip.add('referee')
        return [name for name in names if name in skip]
    shutil.copytree(ROOT / 'backend', SCRATCH / 'backend', ignore=ignore)
    (SCRATCH / 'backend' / 'app' / 'referee').symlink_to(ROOT / 'backend' / 'app' / 'referee')
    for name in ('contracts', 'audit', 'taskpacks', 'scripts', 'docs'):
        (SCRATCH / name).symlink_to(ROOT / name)


def run(tests):
    result = subprocess.run([str(PYTHON), '-m', 'pytest', '-q', '-rfE', '-p', 'no:cacheprovider', *tests], cwd=SCRATCH / 'backend',
                            capture_output=True, text=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    failed = [line.split(' - ')[0] for line in lines if line.startswith(('FAILED ', 'ERROR '))]
    return result.returncode, (lines[-1] if lines else '(no output)') + ''.join(f'\n      {name}' for name in failed)


def control_only(times):
    build()
    for _ in range(times):
        print('CONTROL', *run(BACKOFF_TESTS + LABEL_TESTS), flush=True)
    shutil.rmtree(SCRATCH)


def main():
    if sys.argv[1:2] == ['--control']:
        control_only(int(sys.argv[2]))
        return 0
    lines, ok = [], True
    build()
    code, summary = run(BACKOFF_TESTS + LABEL_TESTS)
    lines.append(f'CONTROL unmutated copy: exit {code}: {summary}')
    ok &= code == 0
    for name, apply, tests in CHECKS:
        build()
        apply(SCRATCH)
        code, summary = run(tests)
        caught = code != 0
        ok &= caught
        lines.append(f'{"CAUGHT " if caught else "MISSED "} {name}: exit {code}: {summary}')
    shutil.rmtree(SCRATCH)
    lines.append('ALL MUTATIONS CAUGHT' if ok else 'SOME MUTATION NOT CAUGHT')
    print('\n'.join(lines))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
