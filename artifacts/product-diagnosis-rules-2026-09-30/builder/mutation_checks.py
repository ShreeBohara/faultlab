"""Negative controls ($0, offline): each mutation of this build, applied in a scratch copy outside the Desktop, must make
the new tests fail; the unmutated copy must pass.

Run from faultlab/:  .venv/bin/python -B artifacts/product-diagnosis-rules-2026-09-30/builder/mutation_checks.py
The scratch tree is /Users/shree/FaultLab_Scratch/product-diagnosis-rules/mutations/ (backend, contracts, the two scripts,
the artifact files the tests read, and a symlink to audit/ so nothing protected is copied); it is deleted at the end.
Each run uses pytest's own network block (conftest) and PYTHONDONTWRITEBYTECODE.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

FAULTLAB = Path(__file__).resolve().parents[3]
SCRATCH = Path('/Users/shree/FaultLab_Scratch/product-diagnosis-rules/mutations')
PYTHON = FAULTLAB / '.venv/bin/python'
TESTS = ['tests/lab/test_diagnosis_rules.py', 'tests/lab/test_diagnosis_rules_loop.py', 'tests/experiments/test_diagnosis_probe.py']
COPY = ['backend', 'contracts', 'scripts/experiments/diagnosis_probe.py', 'scripts/experiments/check_evidence_gap_misreading_v2.py',
        'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs', 'artifacts/analysis-diagnosis-2026-09-30/inv-a',
        'artifacts/analysis-diagnosis-2026-09-30/design-minimal', 'artifacts/analysis-diagnosis-2026-09-30/designer-integrity',
        *[f'artifacts/product-live-2026-09-30/native-v2{r}-run/export.json' for r in 'defg']]
MUTATIONS = [
    ('1a dropped: the flag-on diagnosis repair turn sends today\'s message', 'backend/app/agents/mechanic.py',
     "{'role':'user','content':diagnosis_protocol.repair_message(errors)}",
     "{'role':'user','content':canonical_json({'validation_errors':errors,'instruction':FORMAT_REPAIR_INSTRUCTION})}"),
    ('flag-off errors carry the limit too (golden bytes broken)', 'backend/app/agents/mechanic.py',
     "                if recording:\n                    errors=diagnosis_protocol.repair_errors(error)",
     "                if True:\n                    from app.lab import diagnosis_protocol\n                    errors=diagnosis_protocol.repair_errors(error)"),
    ('the record calls a declined answer VALID_REQUESTED', 'backend/app/lab/diagnosis_protocol.py',
     "status = 'VALID_REQUESTED' if proposal.requested_intervention_id is not None else 'VALID_NO_REQUEST'",
     "status = 'VALID_REQUESTED'"),
    ('the record labels a code default as the model\'s', 'backend/app/lab/diagnosis_protocol.py',
     "status, source = 'INVALID_OUTPUT', 'code_default'", "status, source = 'INVALID_OUTPUT', 'model'"),
    ('the record is written after the POLICY_GAP gate', 'backend/app/lab/learning.py',
     "            if diagnosis_rule is not None: diagnosis_protocol.record(store,current,counter,diagnostic,interventions,diagnosis_mechanic)  # before the gate\n            intervention_evidence=await evidence_for([t for t in interventions.trials if t.lifecycle=='COMPLETED'])\n            if diagnostic.kind!='POLICY_GAP': continue\n",
     "            intervention_evidence=await evidence_for([t for t in interventions.trials if t.lifecycle=='COMPLETED'])\n            if diagnostic.kind!='POLICY_GAP': continue\n            if diagnosis_rule is not None: diagnosis_protocol.record(store,current,counter,diagnostic,interventions,diagnosis_mechanic)  # before the gate\n"),
    ('the guide is offered', 'backend/app/lab/diagnosis_guide.py', 'DIAGNOSIS_GUIDE_OFFERED = False', 'DIAGNOSIS_GUIDE_OFFERED = True'),
    ('the interpretive C6 note comes back', 'backend/app/lab/diagnosis_guide.py',
     "            'hypothesis_length': rule['hypothesis_length']}",
     "            'hypothesis_length': rule['hypothesis_length'], 'checks_note': 'C6 is the check of the report\\'s citations.'}"),
    ('the guide sits inside the size rule (not counted)', 'backend/app/lab/learning.py',
     "            diagnosis_mechanic=mechanic if context_rule is None else loop_limits.BoundedMechanic(mechanic,store,campaign_id=id,counterexample=counter)\n",
     "            diagnosis_mechanic=mechanic if context_rule is None else loop_limits.BoundedMechanic(diagnosis_guide.DiagnosisGuideMechanic(mechanic,task_text=current.task_text) if guide_rule is not None else mechanic,store,campaign_id=id,counterexample=counter)\n            guide_rule_inner,guide_rule=guide_rule,None\n"),
    ('older plans re-serialize with a null key', 'backend/app/lab/run_plans.py',
     "'explorer_selection', 'mechanic_diagnosis',\n                    'diagnosis_guide'):", "'explorer_selection',\n                    'diagnosis_guide'):"),
    ('Start does not compare the declared guide with the installed one', 'backend/app/lab/run_plans.py',
     "    if plan.get('diagnosis_guide') is not None and plan['diagnosis_guide'] != diagnosis_guide_declaration():",
     "    if False:"),
    ('the export drops the rejected first attempt', 'backend/app/lab/diagnosis_protocol.py',
     "        for ref in value.get('output_refs') or []:", "        for ref in (value.get('output_refs') or [])[-1:]:"),
    ('the probe sends without charging the ledger first', 'scripts/experiments/diagnosis_probe.py',
     "                    ledger.consume_call(reservation=RESERVATION, role='mechanic')", "                    pass"),
    ('the probe runs live without a declaration', 'scripts/experiments/diagnosis_probe.py',
     "        declaration = verify_declaration(args.declaration, args.declaration_sha256, plan, args.out)",
     "        declaration = {'spend_cap_dollars': HARD_SPEND_CAP}"),
    ('the probe cap is $9', 'scripts/experiments/diagnosis_probe.py', 'HARD_SPEND_CAP = 8.0', 'HARD_SPEND_CAP = 9.0'),
]


def run_tests():
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1'}
    result = subprocess.run([str(PYTHON), '-B', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', '-x', *TESTS], cwd=SCRATCH / 'backend',
                            capture_output=True, text=True, env=env)
    tail = [line for line in result.stdout.splitlines() if line.strip()][-1:] or ['(no output)']
    return result.returncode, tail[0]


def main():
    if SCRATCH.exists(): shutil.rmtree(SCRATCH)
    for relative in COPY:
        source, target = FAULTLAB / relative, SCRATCH / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__')) if source.is_dir() else shutil.copyfile(source, target))
    (SCRATCH / 'audit').symlink_to(FAULTLAB / 'audit')
    results = []
    try:
        code, tail = run_tests()
        results.append(('UNMUTATED', code, tail))
        print(f'unmutated copy: exit {code}: {tail}', flush=True)
        for label, relative, old, new in MUTATIONS:
            path = SCRATCH / relative
            original = path.read_text()
            if original.count(old) != 1:
                results.append((label, 'NOT_APPLIED', f'pattern found {original.count(old)} times')); print(f'NOT APPLIED: {label}'); continue
            path.write_text(original.replace(old, new))
            try:
                code, tail = run_tests()
            finally:
                path.write_text(original)
            caught = code != 0
            results.append((label, 'CAUGHT' if caught else 'MISSED', tail))
            print(f'{"CAUGHT" if caught else "MISSED"}: {label}: {tail}', flush=True)
    finally:
        shutil.rmtree(SCRATCH)
    print(f'scratch deleted: {not SCRATCH.exists()}')
    missed = [r for r in results[1:] if r[1] != 'CAUGHT']
    print(f'{len(results) - 1 - len(missed)} of {len(results) - 1} mutations caught; unmutated exit {results[0][1]}')
    sys.exit(1 if missed or results[0][1] != 0 else 0)


if __name__ == '__main__':
    main()
