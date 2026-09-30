"""Negative controls for the fixer's changes ($0, offline): each fix, reverted on its own in a scratch copy outside the Desktop,
must make a test fail; the unreverted copy must pass.

Run from faultlab/:  .venv/bin/python -B artifacts/product-diagnosis-rules-2026-09-30/fixer/mutation_checks.py
The scratch tree is /Users/shree/FaultLab_Scratch/product-diagnosis-rules-fixer/mutations/: backend, contracts, the two probe
scripts, the artifact files the tests read, the frontend's sources, tests and config (node_modules is a symlink), and a
symlink to audit/ so nothing protected is copied. It is deleted at the end. Backend runs use pytest's own network block
(conftest) and PYTHONDONTWRITEBYTECODE; frontend runs use vitest with fetch stubbed by the tests (no network).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

FAULTLAB = Path(__file__).resolve().parents[3]
SCRATCH = Path('/Users/shree/FaultLab_Scratch/product-diagnosis-rules-fixer/mutations')
PYTHON = FAULTLAB / '.venv/bin/python'
BACKEND_TESTS = ['tests/lab/test_diagnosis_rules.py', 'tests/lab/test_diagnosis_rules_loop.py', 'tests/experiments/test_diagnosis_probe.py']
FRONTEND_TESTS = ['tests/diagnosis-rules.test.tsx']
COPY = ['backend', 'contracts', 'scripts/experiments/diagnosis_probe.py', 'scripts/experiments/check_evidence_gap_misreading_v2.py',
        'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs', 'artifacts/analysis-diagnosis-2026-09-30/inv-a',
        'artifacts/analysis-diagnosis-2026-09-30/design-minimal', 'artifacts/analysis-diagnosis-2026-09-30/designer-integrity',
        *[f'artifacts/product-live-2026-09-30/native-v2{r}-run/export.json' for r in 'defg'],
        'frontend/src', 'frontend/tests', 'frontend/index.html', 'frontend/local-ports.ts', 'frontend/package.json',
        'frontend/tsconfig.json', 'frontend/vite.config.ts']
PROTOCOL = 'backend/app/lab/diagnosis_protocol.py'
PROBE = 'scripts/experiments/diagnosis_probe.py'
# (finding, what the reverted fix does, stage, file, text of the fix, text restored[, only these backend tests])
MUTATIONS = [
    ('MEDIUM-1/F3', 'intervention_ran is again "an experiment was recorded"', 'backend', PROTOCOL,
     "'intervention_ran': len(run.trials) > 0,", "'intervention_ran': bool(run.experiments),"),
    ('MEDIUM-1/F3', 'the statement no longer names why an intervention ended early', 'backend', PROTOCOL,
     "    if row['early_end'] is None:\n        return text\n", "    if True:\n        return text\n"),
    ('LOW-4', 'a refused record no longer names the diagnosis', 'backend', PROTOCOL,
     "raise RuntimeError(f'No Mechanic attempt state for {which}; its diagnosis_requests record was not written')",
     "raise RuntimeError('No Mechanic attempt state for this diagnosis; its diagnosis_requests record was not written')"),
    ('LOW-4', 'trials without an experiment are recorded instead of refused', 'backend', PROTOCOL,
     "    if run.trials and not run.experiments:\n", "    if False:\n"),
    ('LOW-4', 'the loop skips the record when a diagnosis ran (the new evidence-wait loop test must see it)', 'backend',
     'backend/app/lab/learning.py',
     "            if diagnosis_rule is not None: diagnosis_protocol.record(store,current,counter,diagnostic,interventions,diagnosis_mechanic)  # before the gate\n",
     "            pass\n", ['tests/lab/test_diagnosis_rules_loop.py', '-k', 'evidence_waits']),
    ('MEDIUM-2/F5c', 'P1 counts only checker-confirmed GUIDE rows (person-only flags are descriptive again)', 'backend', PROBE,
     "result['status'] = 'PASS' if guide['counted_against_bar'] <= 4 else 'FAIL'", "result['status'] = 'PASS' if guide['confirmed'] <= 4 else 'FAIL'"),
    ('MEDIUM-2', 'the review file shows the checker\'s matches to the person again', 'backend', PROBE,
     "REVIEW_COLUMNS = ('blinded_id', 'request', 'hypothesis', 'human_blames_citations_labels_or_evidence_ids',",
     "REVIEW_COLUMNS = ('blinded_id', 'request', 'hypothesis', 'auto_claim_phrases', 'human_blames_citations_labels_or_evidence_ids',"),
    ('MEDIUM-3/F1', 'scoring no longer reports distinct answers per request key', 'backend', PROBE,
     "               'repeats': _repeats(rows, plan),\n", ""),
    ('MEDIUM-3/F1', 'the declaration may name another temperature than the harness sends', 'backend', PROBE,
     "or sampling['temperature'] != frozen_temperature(plan):", "or False:"),
    ('F5a/b', 'the declaration may carry any non-empty outcome text again', 'backend', PROBE,
     "    if outcomes != PRE_REGISTERED_OUTCOMES:\n",
     "    if not isinstance(outcomes, dict) or not all(isinstance(outcomes.get(k), str) and outcomes[k].strip() for k in ('P1', 'P2', 'P3', 'P4', 'decision_rule')):\n"),
    ('F5b', 'the pre-registered decision rule loses its last two clauses', 'backend', PROBE,
     "'only if P1 and P2 pass. If P1 fails, the next design trims the label text from diagnosis requests '\n                      'only. If P1 passes but P3 shows declines unchanged, the Mechanic\\'s veto persists and the gate question '\n                      'goes to the owner separately.'),",
     "'only if P1 and P2 pass.'),"),
    ('LOW-3', 'the clock-drift precondition is not required', 'backend', PROBE,
     "PRECONDITIONS = ('ledger_checked', 'dashboard_closed', 'no_other_paid_run', 'clock_drift_checked')",
     "PRECONDITIONS = ('ledger_checked', 'dashboard_closed', 'no_other_paid_run')"),
    ('LOW-3', 'answers call the echoed requested model a served model again', 'backend', PROBE,
     "'raw': generation.content, 'model_id': generation.model_id,", "'raw': generation.content, 'served_model': generation.model_id,"),
    ('F2/LOW-2', 'a saved plan no longer checks the repair-and-record rule', 'frontend', 'frontend/src/runPlans.ts',
     "(plan.mode === 'learn' && mechanicDiagnosisDeclaration(plan.mechanic_diagnosis))", "true"),
    ('F2/LOW-2', 'the saved plan no longer shows the rule', 'frontend', 'frontend/src/components/LoopLimits.tsx',
     "<Field name=\"Diagnosis repair and record\">{mechanicDiagnosisText(mechanicDiagnosis)}</Field>{diagnosisGuide &&", "{diagnosisGuide &&"),
    ('F2/LOW-2', 'the Learn setup form no longer shows the offered rule', 'frontend', 'frontend/src/components/RunSetup.tsx',
     " mechanicDiagnosis={value.learn.mechanic_diagnosis}", ""),
    ('F2', 'the diagnosis panel calls a code-default kind the model\'s again', 'frontend', 'frontend/src/components/DiagnosticPanel.tsx',
     '<Field name="Recorded proposed kind">', '<Field name="Model proposed kind">'),
]


def run(stage, only=None):
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1'}
    if stage == 'backend':
        command, cwd = [str(PYTHON), '-B', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', '-x', '-rf', *(only or BACKEND_TESTS)], SCRATCH / 'backend'
    else:
        command, cwd = ['npx', 'vitest', 'run', *FRONTEND_TESTS], SCRATCH / 'frontend'
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env=env)
    lines = [line.strip() for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    failed = next((line for line in lines if line.startswith('FAILED ') or line.startswith('FAIL ')), None)
    pytest_summary = [line for line in lines if re.match(r'^(\d+ (passed|failed)|=+ \d+ (passed|failed))', line)]
    vitest_summary = [line for line in lines if line.startswith('Tests ')]
    summary = (pytest_summary or vitest_summary or lines[-1:] or ['(no output)'])[-1]
    return result.returncode, failed, summary


def main():
    if SCRATCH.exists(): shutil.rmtree(SCRATCH)
    for relative in COPY:
        source, target = FAULTLAB / relative, SCRATCH / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache')) if source.is_dir()
         else shutil.copyfile(source, target))
    (SCRATCH / 'audit').symlink_to(FAULTLAB / 'audit')
    (SCRATCH / 'frontend/node_modules').symlink_to(FAULTLAB / 'frontend/node_modules')
    caught = 0
    try:
        for stage in ('backend', 'frontend'):
            code, failed, summary = run(stage)
            print(f'UNREVERTED {stage}: exit {code}: {summary}', flush=True)
            if code != 0: raise SystemExit('the unreverted copy must pass')
        for finding, label, stage, relative, fixed, reverted, *only in MUTATIONS:
            path = SCRATCH / relative
            original = path.read_text()
            assert original.count(fixed) == 1, (label, original.count(fixed))
            path.write_text(original.replace(fixed, reverted))
            try:
                code, failed, summary = run(stage, only[0] if only else None)
            finally:
                path.write_text(original)
            verdict = 'CAUGHT' if code != 0 else 'MISSED'
            caught += code != 0
            print(f'{verdict}: [{finding}] {label}: {summary}' + (f'\n    first failure: {failed}' if failed else ''), flush=True)
    finally:
        shutil.rmtree(SCRATCH)
        print(f'scratch deleted: {not SCRATCH.exists()}')
    print(f'{caught} of {len(MUTATIONS)} reverted fixes caught; the unreverted copy passes')


if __name__ == '__main__':
    main()
