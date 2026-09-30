"""Verifier's own negative controls ($0, offline), in the scratch tree OUTSIDE the Desktop
(/Users/shree/FaultLab_Scratch/verify-diagnosis-rules/tree = git archive of 626bae4 without the two audit JSONs + the 21
product files + probe-inputs). Each mutation breaks one property the builder or fixer claims; it is applied alone, the
relevant new tests run, and the file is restored byte for byte (sha256 checked). Different from the fixer's 17 where
possible. The unmutated tree is run first and must pass.
Backend: <venv python> -B -m pytest (conftest blocks the network; vguard is also loaded), -p no:cacheprovider, basetemp in
the scratch folder. Frontend: npx vitest run tests/diagnosis-rules.test.tsx in the scratch tree's frontend.

REVISION 2 (after the first run, kept as mutations-first-run-exit-code-only.*): the scratch tree has no audit/promotion.json
(the verifier may not copy it), so 10 of the 97 new backend tests (every one that builds a run plan: T1 x6, T7, T8, the
LOW-4 loop test x2) fail in the UNMUTATED tree too. The first run judged "caught" by exit code, which is wrong here. Now a
mutation counts as caught only when a test OUTSIDE the unmutated tree's failing set fails. A mutation whose only catching
tests are among those 10 is reported UNDECIDABLE-IN-SCRATCH. Two mutations were replaced because they were equivalent or
defended twice (P2: the used-folder check exists in both verify_declaration and execute, so both are removed now; P4: a
hypothesis over 600 characters can never be schema-valid, so the extra length bound was dead; now the P4 bar 9 -> 8).
Every P-mutation is also run through the verifier's own probe_harness_probe.py pointed at the scratch tree (PROBE_ROOT),
and B8 through a direct check of diagnosis_protocol.campaign_records on a seeded scratch store.
"""
import hashlib, json, os, subprocess, sys, time
from pathlib import Path

TREE = Path('/Users/shree/FaultLab_Scratch/verify-diagnosis-rules/tree')
PY = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python'
VERIFY = Path(__file__).resolve().parents[1]
BASETEMP = Path('/Users/shree/FaultLab_Scratch/verify-diagnosis-rules/pytest-tmp')
NEW_BACKEND = ['tests/lab/test_diagnosis_rules.py', 'tests/lab/test_diagnosis_rules_loop.py', 'tests/experiments/test_diagnosis_probe.py']

MUTATIONS = [
    ('B1 repair turn under-counts the answer length by one', 'backend/app/lab/diagnosis_protocol.py',
     "item['your_characters'] = len(value)", "item['your_characters'] = len(value) - 1", 'backend'),
    ('B2 the declared repair turn drops the appended sentence', 'backend/app/lab/diagnosis_protocol.py',
     "REPAIR_INSTRUCTION = FORMAT_REPAIR_INSTRUCTION + ' ' + REPAIR_SENTENCE", "REPAIR_INSTRUCTION = FORMAT_REPAIR_INSTRUCTION", 'backend'),
    ('B3 the rule-off Mechanic also sends the limit fields (flag-off bytes change)', 'backend/app/agents/mechanic.py',
     "                if recording:\n                    errors=diagnosis_protocol.repair_errors(error)",
     "                if True:\n                    from app.lab import diagnosis_protocol\n                    errors=diagnosis_protocol.repair_errors(error)", 'backend'),
    ('B4 run options offer the guide although it is not offered', 'backend/app/lab/run_plans.py',
     "**({'diagnosis_guide': diagnosis_guide_declaration()} if DIAGNOSIS_GUIDE_OFFERED else {})",
     "**({'diagnosis_guide': diagnosis_guide_declaration()})", 'backend'),
    ('B5 a code-default kind is recorded as the model\'s', 'backend/app/lab/diagnosis_protocol.py',
     "status, source = 'INVALID_OUTPUT', 'code_default'", "status, source = 'INVALID_OUTPUT', 'model'", 'backend'),
    ('B6 early_end is never recorded', 'backend/app/lab/diagnosis_protocol.py',
     "        if isinstance(item, str) and item.split(':', 1)[0] in EARLY_END_REASONS:\n            return item",
     "        if False:\n            return item", 'backend'),
    ('B7 Start no longer compares a declared Rule 1 with the installed one', 'backend/app/lab/run_plans.py',
     "if plan.get('mechanic_diagnosis') is not None and plan['mechanic_diagnosis'] != mechanic_diagnosis_declaration():",
     "if False:", 'backend'),
    ('B8 the export embeds only the last attempt', 'backend/app/lab/diagnosis_protocol.py',
     "for ref in value.get('output_refs') or []:", "for ref in (value.get('output_refs') or [])[-1:]:", 'backend'),
    ('P1 the probe premise also counts CONTROL rows only the person flagged', 'scripts/experiments/diagnosis_probe.py',
     "    elif control['confirmed'] < 20:", "    elif control['confirmed'] + control['person_flagged_without_auto_match'] < 20:", 'backend'),
    ('P2 the probe accepts a used output folder (both checks removed)', 'scripts/experiments/diagnosis_probe.py',
     "    if out.exists() and any(out.iterdir()):\n        raise ProbeRefused('The output folder is not empty; a probe run is never repeated into it')\n",
     "", 'backend'),
    ('P3 the probe sends before it charges the ledger', 'scripts/experiments/diagnosis_probe.py',
     "                try:\n                    ledger.consume_call(reservation=RESERVATION, role='mechanic')\n                except (BudgetExhausted, StopRequested) as error:\n                    stop_reason = f'LEDGER_REFUSED: {error}'\n                    break\n",
     "", 'backend'),
    ('P4 the P4 pass bar drops from 9 of 10 to 8 of 10', 'scripts/experiments/diagnosis_probe.py',
     "status = 'PASS' if all(s['valid_within_600'] >= 9 for s in new) else 'FAIL'",
     "status = 'PASS' if all(s['valid_within_600'] >= 8 for s in new) else 'FAIL'", 'backend'),
    ('F1 the frontend accepts a Rule 1 declaration that says the first turn changed', 'frontend/src/loopLimits.ts',
     "&& value.record_written_before_gate === true && value.reads_scoring === false && value.verdict_code_changed === false && digest(value.semantics_hash)",
     "&& value.record_written_before_gate === true && value.reads_scoring === false && value.verdict_code_changed === false && digest(value.semantics_hash) || (object(value) && value.first_turn_changed === true)",
     'frontend'),
]


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


UNDECIDABLE_TESTS_NOTE = 'tests that build a run plan need audit/promotion.json, absent from the scratch tree'
EXPECTED = {'P2 the probe accepts a used output folder (both checks removed)': 2}   # anchors expected more than once


def run(kind):
    t = time.time()
    if kind == 'backend':
        BASETEMP.mkdir(parents=True, exist_ok=True)
        code = ('import sys; sys.path.insert(0, %r); import vguard; import pytest; '
                'sys.exit(pytest.main(%r))') % (str(VERIFY), ['-q', '-rf', '-p', 'no:cacheprovider', '--basetemp', str(BASETEMP), *NEW_BACKEND])
        proc = subprocess.run([PY, '-B', '-c', code], cwd=TREE / 'backend', capture_output=True, text=True,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    else:
        proc = subprocess.run(['npx', 'vitest', 'run', 'tests/diagnosis-rules.test.tsx'], cwd=TREE / 'frontend', capture_output=True, text=True)
    lines = [l for l in (proc.stdout + proc.stderr).splitlines() if l.strip()]
    summary = next((l for l in reversed(lines) if ' passed' in l or ' failed' in l or 'Tests ' in l), lines[-1] if lines else '')
    if kind == 'backend':
        failing = sorted({l.split(' ')[1] for l in lines if l.startswith('FAILED ')})
    else:
        failing = sorted({l.strip() for l in lines if l.strip().startswith('×') or l.strip().startswith('FAIL ')})
    return proc.returncode, summary.strip(), round(time.time() - t, 1), failing


def harness_probe():
    """The verifier's own probe_harness_probe.py against the scratch tree's harness (PROBE_ROOT)."""
    proc = subprocess.run([PY, '-B', str(VERIFY / 'spot' / 'probe_harness_probe.py')], cwd='/Users/shree/FaultLab_Scratch/verify-diagnosis-rules',
                          capture_output=True, text=True, env={**os.environ, 'PROBE_ROOT': str(TREE), 'PYTHONDONTWRITEBYTECODE': '1'})
    try:
        out = json.loads(proc.stdout)
        return {'passed': out['passed'], 'total': out['total'], 'failed': [f[0] for f in out['failed']]}
    except Exception as error:
        return {'error': f'{type(error).__name__}: {error}', 'stderr_tail': proc.stderr[-600:]}


def campaign_records_direct():
    """B8 direct check: seed a scratch LabStore with one record naming two attempts; campaign_records must embed both."""
    code = r"""
import sys, json, tempfile, os
sys.path.insert(0, %r); import vguard
from app.lab.storage import LabStore
from app.lab import diagnosis_protocol as d
tmp = tempfile.mkdtemp(dir='/Users/shree/FaultLab_Scratch/verify-diagnosis-rules')
store = LabStore(os.path.join(tmp, 'x.db'))
store.put_record('mechanic_outputs', 'm0', {'attempt': 0, 'raw': 'a'}, immutable=True)
store.put_record('mechanic_outputs', 'm1', {'attempt': 1, 'raw': 'b'}, immutable=True)
store.put_record('diagnosis_requests', 'dg', {'campaign_id': 'c', 'output_refs': ['m0', 'm1']}, immutable=True)
rows = d.campaign_records(store, 'c'); store.close()
import shutil; shutil.rmtree(tmp)
print(json.dumps([o['output_ref'] for o in rows[0]['attempt_outputs']]))
""" % str(VERIFY)
    proc = subprocess.run([PY, '-B', '-c', code], cwd=TREE / 'backend', capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    return proc.stdout.strip() or proc.stderr[-400:]


log = []
baseline = {}
for kind in ('backend', 'frontend'):
    rc, summary, secs, failing = run(kind)
    baseline[kind] = set(failing)
    log.append({'mutation': f'UNMUTATED {kind}', 'exit': rc, 'summary': summary, 'seconds': secs, 'failing': failing})
    print(f'UNMUTATED {kind}: exit {rc}: {summary}; failing {len(failing)} ({UNDECIDABLE_TESTS_NOTE})' if failing else f'UNMUTATED {kind}: exit {rc}: {summary}', flush=True)
hp = harness_probe(); log.append({'mutation': 'UNMUTATED verifier harness probe', **hp}); print('UNMUTATED verifier harness probe:', hp, flush=True)
cr = campaign_records_direct(); log.append({'mutation': 'UNMUTATED verifier campaign_records check', 'result': cr}); print('UNMUTATED campaign_records check:', cr, flush=True)
counts = {'CAUGHT': 0, 'NOT CAUGHT': 0, 'UNDECIDABLE-IN-SCRATCH': 0}
for name, rel, old, new, kind in MUTATIONS:
    path = TREE / rel
    original = path.read_bytes(); before = sha(path)
    text = original.decode()
    count = text.count(old)
    if count != EXPECTED.get(name, 1):
        log.append({'mutation': name, 'error': f'anchor found {count} times'}); print(f'SKIPPED {name}: anchor found {count} times', flush=True); continue
    path.write_text(text.replace(old, new))
    extra = {}
    try:
        rc, summary, secs, failing = run(kind)
        if name.startswith('P'): extra['verifier_harness_probe'] = harness_probe()
        if name.startswith('B8'): extra['verifier_campaign_records_check'] = campaign_records_direct()
    finally:
        path.write_bytes(original)
    restored = sha(path) == before
    new_failures = sorted(set(failing) - baseline[kind])
    verdict = 'CAUGHT' if new_failures else ('UNDECIDABLE-IN-SCRATCH' if kind == 'backend' and baseline[kind] else 'NOT CAUGHT')
    counts[verdict] += 1
    log.append({'mutation': name, 'file': rel, 'exit': rc, 'verdict': verdict, 'summary': summary, 'seconds': secs, 'restored': restored,
                'new_failures': new_failures, **extra})
    print(f'{verdict}: {name}: {summary}; new failures outside the unmutated set: {len(new_failures)} {new_failures[:3]} (restored {restored}) {extra if extra else ""}', flush=True)
print(f'repo tests: {counts}', flush=True)
json.dump(log, open(VERIFY / 'spot' / 'mutations.json', 'w'), indent=1)
