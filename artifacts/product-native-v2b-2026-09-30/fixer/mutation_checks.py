"""Fixer (v2b): negative controls for the review fixes ($0, offline, network-silent like the suite itself).

Each check builds a scratch copy (backend/ or frontend/ source; the working tree is never modified), applies ONE
mutation -- either the PRE-FIX file saved in fixer/before/ (the unfixed code) or a one-line mutant of the new code --
and runs the named tests there. A check is CAUGHT when the tests FAIL on the mutated code; the CONTROL line shows the
same tests PASS on an unmutated copy. Sibling folders the backend tests read (contracts, audit, taskpacks, scripts,
docs) and backend/app/referee are symlinked, never copied or read here; frontend/node_modules is symlinked. No .env
exists in the scratch root. The doc-only fixes are checked by doc_checks.py on fixer/before/ (fails) and on the
repo (passes).

Run from faultlab/:  .venv/bin/python -B artifacts/product-native-v2b-2026-09-30/fixer/mutation_checks.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BEFORE = OUT / 'before'
SCRATCH = OUT / 'mutation-tree'
PYTHON = ROOT / '.venv' / 'bin' / 'python'

REGISTRATION = ['tests/lab/test_native_adapter_v2_product.py::test_v2_registration_records_the_installed_label_protocol']
REVIEW_FIXES = ['tests/agents/test_lab_backoff_review_fixes.py']
CAMPAIGN_BUDGET = ['tests/lab/test_lab_backoff_campaign.py::test_a_retry_the_budget_cannot_cover_ends_the_campaign_error_without_waiting']
GRID = ['tests/agents/test_lab_backoff_review_fixes.py::test_the_read_only_check_agrees_with_real_admission_on_every_state']
UNDECODED_VIEW = ['tests/lab/test_native_v2_label_views.py::test_an_undecoded_token_reaches_the_evidence_summary_as_written']
FRONT_BOUND = ['tests/transport-backoff.test.tsx']
FRONT_SETUP = ['tests/native-adapter-v2.test.tsx']
BACKEND_ALL = REGISTRATION + REVIEW_FIXES + CAMPAIGN_BUDGET + UNDECODED_VIEW
FRONTEND_ALL = FRONT_BOUND + FRONT_SETUP


def mutant(path, before, after):
    def apply(root):
        text = (root / path).read_text()
        assert text.count(before) == 1, (path, before)
        (root / path).write_text(text.replace(before, after))
    return apply


def restore(*paths):
    """Put back the pre-fix copy saved in fixer/before/ (the unfixed code)."""
    def apply(root):
        for path in paths:
            shutil.copyfile(BEFORE / path, root / path)
    return apply


FITS = 'backend/app/agents/transport_retry.py'
BACKEND_CHECKS = [
    ('P-2 unfixed: registry.py before the fix (journal-label limitation text)',
     restore('backend/app/integrations/registry.py'), REGISTRATION),
    ('LOW-2/P-4 unfixed: transport_retry.py, explorer.py and mechanic.py before the fix',
     restore('backend/app/agents/transport_retry.py', 'backend/app/agents/explorer.py', 'backend/app/agents/mechanic.py'),
     REVIEW_FIXES + CAMPAIGN_BUDGET),
    ('LOW-2/P-4 unfixed, campaign level only (this test imports only names the unfixed code has, so it runs)',
     restore('backend/app/agents/transport_retry.py', 'backend/app/agents/explorer.py', 'backend/app/agents/mechanic.py'),
     CAMPAIGN_BUDGET),
    ('P-4 mutant: the zero-retry case says "after 0 transport retries" again',
     mutant(FITS, '    if not tried:\n        # Review finding P-4', '    if False:\n        # Review finding P-4'),
     REVIEW_FIXES + CAMPAIGN_BUDGET),
    ('LOW-2 mutant: no budget check before the wait',
     mutant(FITS, 'if reason is None and fits is not None and not session.stopped() and not fits():', 'if False:'),
     REVIEW_FIXES + CAMPAIGN_BUDGET),
    ('LOW-2 mutant: the Explorer does not pass the budget check',
     mutant('backend/app/agents/explorer.py', "fits=lambda:ledger_retry_fits(self.ledger,'explorer'))", 'fits=None)'),
     REVIEW_FIXES + CAMPAIGN_BUDGET),
    ('LOW-2 mutant: the Mechanic does not pass the budget check',
     mutant('backend/app/agents/mechanic.py', "fits=lambda:ledger_retry_fits(self.ledger,'mechanic'))", 'fits=None)'),
     REVIEW_FIXES),
    ('LOW-2 mutant: the read-only check ignores Stop',
     mutant(FITS, "        if ledger.stopped or role not in ('actor', 'explorer', 'mechanic'):", "        if role not in ('actor', 'explorer', 'mechanic'):"),
     GRID),
    ('LOW-2 mutant: the read-only check ignores the dollar bound',
     mutant(FITS, '        if (role_bound is not None\n                and ledger.used_dollar_upper_bound', '        if (False\n                and ledger.used_dollar_upper_bound'),
     GRID),
    ('LOW-2 mutant: the read-only check ignores reserved calls',
     mutant(FITS, '        if (ledger.used_calls + 1 + protected_calls > ledger.caps.model_calls', '        if (ledger.used_calls + 1 > ledger.caps.model_calls'),
     GRID),
    ('LOW-2 mutant: the read-only check ignores the token cap',
     mutant(FITS, '                or ledger.used_tokens + ledger.tokens_per_call + protected_tokens > ledger.caps.tokens):', '                or False):'),
     GRID),
    ('LOW-2 mutant: the read-only check ignores measured cost',
     mutant(FITS, '        if ledger.used_cost is not None and ledger.used_cost >= ledger.caps.dollars:', '        if False:'),
     GRID),
    ('LOW-2 mutant: the read-only check charges the ledger (it must not)',
     mutant(FITS, "    if not isinstance(ledger, CampaignLedger):\n        return True\n",
            "    if not isinstance(ledger, CampaignLedger):\n        return True\n    return charge_ledger_retry(ledger, role)\n"),
     GRID),
    ('LOW-1 sensitivity (not a fix; summarize_evidence is frozen): an undecoded token would be dropped from the view',
     mutant('backend/app/lab/diagnosis.py', "if field in ('evidence_id','evidence_ids') and value in evidence: return evidence[value]",
            "if field in ('evidence_id','evidence_ids'): return evidence.get(value,'o?')"),
     UNDECODED_VIEW),
]
FRONTEND_CHECKS = [
    ('P-6 unfixed: DiscoveryProtocol.tsx before the fix ("at most 16" under rule v2)',
     restore('frontend/src/components/DiscoveryProtocol.tsx'), FRONT_BOUND),
    ('P-6 mutant: the campaign cap is ignored in the discovery bound',
     mutant('frontend/src/components/DiscoveryProtocol.tsx', '${Math.min(declared, cap)}', '${declared}'), FRONT_BOUND),
    ('P-2 unfixed: RunSetup.tsx before the fix (v2 description without shown-order labels)',
     restore('frontend/src/components/RunSetup.tsx'), FRONT_SETUP),
]


def build_backend():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir()
    def ignore(directory, names):
        skip = {'__pycache__', '.pytest_cache'}
        if Path(directory) == ROOT / 'backend' / 'app':
            skip.add('referee')   # the gates are symlinked, not copied, so their files are not read here
        return [name for name in names if name in skip]
    shutil.copytree(ROOT / 'backend', SCRATCH / 'backend', ignore=ignore)
    (SCRATCH / 'backend' / 'app' / 'referee').symlink_to(ROOT / 'backend' / 'app' / 'referee')
    for name in ('contracts', 'audit', 'taskpacks', 'scripts', 'docs'):
        (SCRATCH / name).symlink_to(ROOT / name)


def build_frontend():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    (SCRATCH / 'frontend').mkdir(parents=True)
    for name in ('src', 'tests'):
        shutil.copytree(ROOT / 'frontend' / name, SCRATCH / 'frontend' / name)
    for name in ('package.json', 'tsconfig.json', 'vite.config.ts', 'local-ports.ts', 'index.html'):
        shutil.copyfile(ROOT / 'frontend' / name, SCRATCH / 'frontend' / name)
    (SCRATCH / 'frontend' / 'node_modules').symlink_to(ROOT / 'frontend' / 'node_modules')
    for name in ('audit', 'contracts'):   # tests/run-fixtures.ts reads audit/development.json; src reads contracts/wire-types
        (SCRATCH / name).symlink_to(ROOT / name)


def run_backend(tests):
    result = subprocess.run([str(PYTHON), '-B', '-m', 'pytest', '-q', '-rfE', '-p', 'no:cacheprovider', *tests],
                            cwd=SCRATCH / 'backend', capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    return summarize(result)


def run_frontend(tests):
    npx = shutil.which('npx')
    result = subprocess.run([npx, 'vitest', 'run', *tests], cwd=SCRATCH / 'frontend', capture_output=True, text=True)
    return summarize(result, frontend=True)


def summarize(result, frontend=False):
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    if frontend:
        keep = [line.strip() for line in lines if line.strip().startswith(('Tests ', 'Test Files ', '×', 'FAIL'))]
        return result.returncode, ' | '.join(keep[:6]) or (lines[-1] if lines else '(no output)')
    failed = [line.split(' - ')[0] for line in lines if line.startswith(('FAILED ', 'ERROR '))]
    tail = next((line for line in reversed(lines) if ' passed' in line or ' failed' in line or ' error' in line), lines[-1] if lines else '(no output)')
    return result.returncode, tail + ''.join(f'\n      {name}' for name in failed)


def main():
    lines, ok = [], True
    build_backend()
    code, summary = run_backend(BACKEND_ALL)
    lines.append(f'CONTROL backend (unmutated copy): exit {code}: {summary}')
    ok &= code == 0
    for name, apply, tests in BACKEND_CHECKS:
        build_backend(); apply(SCRATCH)
        code, summary = run_backend(tests)
        caught = code != 0; ok &= caught
        lines.append(f'{"CAUGHT " if caught else "MISSED "} {name}: exit {code}: {summary}')
    build_frontend()
    code, summary = run_frontend(FRONTEND_ALL)
    lines.append(f'CONTROL frontend (unmutated copy): exit {code}: {summary}')
    ok &= code == 0
    for name, apply, tests in FRONTEND_CHECKS:
        build_frontend(); apply(SCRATCH)
        code, summary = run_frontend(tests)
        caught = code != 0; ok &= caught
        lines.append(f'{"CAUGHT " if caught else "MISSED "} {name}: exit {code}: {summary}')
    shutil.rmtree(SCRATCH)
    doc_fixed = subprocess.run([sys.executable, '-B', str(OUT / 'doc_checks.py'), str(ROOT)], capture_output=True, text=True)
    doc_before = subprocess.run([sys.executable, '-B', str(OUT / 'doc_checks.py'), str(BEFORE)], capture_output=True, text=True)
    lines.append(f'CONTROL doc_checks.py on the repo (fixed docs and names): exit {doc_fixed.returncode}: {doc_fixed.stdout.strip().splitlines()[-1]}')
    lines.append(f'{"CAUGHT " if doc_before.returncode else "MISSED "} doc_checks.py on fixer/before/ (pre-fix docs and names): '
                 f'exit {doc_before.returncode}: {doc_before.stdout.strip().splitlines()[-1]}')
    ok &= doc_fixed.returncode == 0 and doc_before.returncode != 0
    lines.append('ALL MUTATIONS CAUGHT' if ok else 'SOME MUTATION NOT CAUGHT OR A CONTROL FAILED')
    print('\n'.join(lines))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
