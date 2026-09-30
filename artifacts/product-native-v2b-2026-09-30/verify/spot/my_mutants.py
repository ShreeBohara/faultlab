"""Independent verifier (native v2b, 2026-09-30): my OWN negative controls for the fixer's FIXED findings ($0, offline).

Different mutants from the fixer's mutation_checks.py where possible. Each check builds a scratch copy under
verify/spot/mutation-tree (the working tree is never modified), applies ONE mutation, and runs the named tests there
under the verifier guard (verify/guard/sitecustomize.py: non-loopback network and the real .env refused). CAUGHT = the
tests FAIL on the mutated copy; the CONTROL lines show the same tests PASS on an unmutated copy.
backend/app/referee is symlinked (never copied or read here); audit/ in the scratch root holds copies of the
NON-protected audit files only (development.json, freeze.json, portability.json, search-comparison.json), so
audit/promotion.json and audit/final-audit.json are not reachable from the scratch tree. contracts, taskpacks,
scripts and docs are symlinked; frontend/node_modules is symlinked. The scratch tree is deleted at the end.

Run from faultlab/:  .venv/bin/python -B artifacts/product-native-v2b-2026-09-30/verify/spot/my_mutants.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab')
VERIFY = ROOT / 'artifacts/product-native-v2b-2026-09-30/verify'
SCRATCH = VERIFY / 'spot' / 'mutation-tree'
PYTHON = ROOT / '.venv' / 'bin' / 'python'
GUARD_ENV = {'PYTHONPATH': str(VERIFY / 'guard'), 'VERIFY_GUARD_LOG': str(VERIFY / 'spot' / 'my-mutants-guard.jsonl'),
             'NODE_OPTIONS': f"--require {VERIFY / 'guard' / 'node-guard.cjs'}",
             'VERIFY_NODE_GUARD_LOG': str(VERIFY / 'spot' / 'my-mutants-node-guard.jsonl'), 'PYTHONDONTWRITEBYTECODE': '1'}

FIXES = ['tests/agents/test_lab_backoff_review_fixes.py']
CAMPAIGN = ['tests/lab/test_lab_backoff_campaign.py']
REG = ['tests/lab/test_native_adapter_v2_product.py']
VIEWS = ['tests/lab/test_native_v2_label_views.py']
GOLDEN = ['tests/integrations/test_native_adapter_v1_golden.py']
ROLE = ['tests/agents/test_lab_role_backoff.py']
BACKEND_CONTROL = FIXES + CAMPAIGN + REG + VIEWS + GOLDEN + ROLE
FRONT = ['tests/transport-backoff.test.tsx', 'tests/native-adapter-v2.test.tsx']

TR = 'backend/app/agents/transport_retry.py'


def mutant(path, before, after):
    def apply(root):
        text = (root / path).read_text()
        assert text.count(before) == 1, (path, before, text.count(before))
        (root / path).write_text(text.replace(before, after))
    return apply


def append_comment(path):
    def apply(root):
        (root / path).write_bytes((root / path).read_bytes() + b'\n# verifier mutant\n')
    return apply


BACKEND_CHECKS = [
    ('LOW-2 mine: the read-only check is off by one on the call cap (>= instead of >)',
     mutant(TR, '        if (ledger.used_calls + 1 + protected_calls > ledger.caps.model_calls',
            '        if (ledger.used_calls + 1 + protected_calls >= ledger.caps.model_calls'), FIXES),
    ('LOW-2 mine: the budget is checked only before the FIRST wait, not before later ones',
     mutant(TR, 'if reason is None and fits is not None and not session.stopped() and not fits():',
            'if reason is None and fits is not None and attempt == 1 and not session.stopped() and not fits():'), FIXES),
    ('LOW-2 mine: the Explorer asks the budget check for the wrong role (mechanic bound)',
     mutant('backend/app/agents/explorer.py', "fits=lambda:ledger_retry_fits(self.ledger,'explorer'))",
            "fits=lambda:ledger_retry_fits(self.ledger,'mechanic'))"), FIXES),
    ('LOW-2 mine: a Stop no longer wins over the budget check (the stopped() guard dropped)',
     mutant(TR, 'if reason is None and fits is not None and not session.stopped() and not fits():',
            'if reason is None and fits is not None and not fits():'), FIXES),
    ('P-4 mine: a budget refusal with no retry uses the "next retry ... so it was not sent" wording',
     mutant(TR, "        if reason == 'BUDGET_REFUSED':\n            detail = 'a retry did not fit the campaign\\'s unreserved budget'\n",
            ''), FIXES + CAMPAIGN),
    ('P-4 mine: messages after 1+ retries changed (plural helper broken)',
     mutant(TR, "return f'{count} {one if count == 1 else many}'", "return f'{count} {many}'"), FIXES),
    ('P-2 mine: the v2 registration text still says journal labels',
     mutant('backend/app/integrations/registry.py', 'numbered in the order the agent first sees them', 'numbered by journal position'), REG),
    ('v1 golden sensitivity: a comment line appended to the v1 module (must fail the v1 golden/byte tests)',
     append_comment('backend/app/integrations/external_agent.py'), GOLDEN + REG),
]
FRONTEND_CHECKS = [
    ('P-6 mine: the discovery bound uses Math.max instead of Math.min',
     mutant('frontend/src/components/DiscoveryProtocol.tsx', '${Math.min(declared, cap)}', '${Math.max(declared, cap)}'), FRONT[:1]),
    ('P-6 mine: the cap note is dropped (only the number is shown)',
     mutant('frontend/src/components/DiscoveryProtocol.tsx', "declared > cap ? `; the plan declares", "false ? `; the plan declares"), FRONT[:1]),
    ('P-2 mine: RunSetup v2 text omits "an observation it never sees gets no label"',
     mutant('frontend/src/components/RunSetup.tsx', '; an observation it never sees gets no label)', ')'), FRONT[1:]),
]


def build_backend():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    def ignore(directory, names):
        skip = {'__pycache__', '.pytest_cache'}
        if Path(directory) == ROOT / 'backend' / 'app':
            skip.add('referee')
        return [name for name in names if name in skip]
    shutil.copytree(ROOT / 'backend', SCRATCH / 'backend', ignore=ignore)
    (SCRATCH / 'backend' / 'app' / 'referee').symlink_to(ROOT / 'backend' / 'app' / 'referee')
    for name in ('contracts', 'taskpacks', 'scripts', 'docs'):
        (SCRATCH / name).symlink_to(ROOT / name)
    (SCRATCH / 'audit').mkdir()
    for name in ('development.json', 'freeze.json', 'portability.json', 'search-comparison.json'):
        shutil.copyfile(ROOT / 'audit' / name, SCRATCH / 'audit' / name)


def build_frontend():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    (SCRATCH / 'frontend').mkdir(parents=True)
    for name in ('src', 'tests'):
        shutil.copytree(ROOT / 'frontend' / name, SCRATCH / 'frontend' / name)
    for name in ('package.json', 'tsconfig.json', 'vite.config.ts', 'local-ports.ts', 'index.html'):
        shutil.copyfile(ROOT / 'frontend' / name, SCRATCH / 'frontend' / name)
    (SCRATCH / 'frontend' / 'node_modules').symlink_to(ROOT / 'frontend' / 'node_modules')
    (SCRATCH / 'contracts').symlink_to(ROOT / 'contracts')
    (SCRATCH / 'audit').mkdir()
    shutil.copyfile(ROOT / 'audit' / 'development.json', SCRATCH / 'audit' / 'development.json')


def env():
    base = {k: v for k, v in os.environ.items() if k not in ('WANDB_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')}
    return {**base, **GUARD_ENV}


def summarize(result, frontend=False):
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    if frontend:
        keep = [line.strip() for line in lines if line.strip().startswith(('Tests ', 'Test Files ', '×', 'FAIL'))]
        return result.returncode, ' | '.join(keep[:6]) or (lines[-1] if lines else '(no output)')
    failed = [line.split(' - ')[0] for line in lines if line.startswith(('FAILED ', 'ERROR '))]
    tail = next((line for line in reversed(lines) if ' passed' in line or ' failed' in line or ' error' in line), lines[-1] if lines else '(no output)')
    return result.returncode, tail + ''.join(f'\n      {name}' for name in failed[:8])


def run_backend(tests):
    r = subprocess.run([str(PYTHON), '-B', '-m', 'pytest', '-q', '-rfE', '-p', 'no:cacheprovider', *tests],
                       cwd=SCRATCH / 'backend', capture_output=True, text=True, env=env())
    return summarize(r)


def run_frontend(tests):
    r = subprocess.run([shutil.which('npx'), 'vitest', 'run', *tests], cwd=SCRATCH / 'frontend', capture_output=True, text=True, env=env())
    return summarize(r, frontend=True)


def main():
    lines, ok = [], True
    build_backend()
    code, summary = run_backend(BACKEND_CONTROL)
    lines.append(f'CONTROL backend (unmutated copy): exit {code}: {summary}'); ok &= code == 0
    for name, apply, tests in BACKEND_CHECKS:
        build_backend(); apply(SCRATCH)
        code, summary = run_backend(tests)
        lines.append(f'{"CAUGHT " if code != 0 else "MISSED "} {name}: exit {code}: {summary}'); ok &= code != 0
        print(lines[-1], flush=True)
    build_frontend()
    code, summary = run_frontend(FRONT)
    lines.append(f'CONTROL frontend (unmutated copy): exit {code}: {summary}'); ok &= code == 0
    for name, apply, tests in FRONTEND_CHECKS:
        build_frontend(); apply(SCRATCH)
        code, summary = run_frontend(tests)
        lines.append(f'{"CAUGHT " if code != 0 else "MISSED "} {name}: exit {code}: {summary}'); ok &= code != 0
    shutil.rmtree(SCRATCH)
    lines.append('scratch tree deleted: ' + str(not SCRATCH.exists()))
    lines.append('ALL MY MUTANTS CAUGHT, CONTROLS PASS' if ok else 'SOME MUTANT MISSED OR A CONTROL FAILED')
    print('\n'.join(lines))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
