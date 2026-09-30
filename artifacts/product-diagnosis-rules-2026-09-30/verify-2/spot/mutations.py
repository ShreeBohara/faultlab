#!/usr/bin/env python3
"""Verifier-2 negative controls ($0, offline): each mutation edits ONE file of the scratch current tree
(/Users/shree/FaultLab_Scratch/verify-2/current, outside the Desktop), runs the named tests under -p vplug, records the
result, then restores the file and checks its sha256. The real tree is never edited."""
import hashlib, os, re, subprocess, sys
S = '/Users/shree/FaultLab_Scratch/verify-2'; T = f'{S}/current'; PY = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python'
C6 = "C6 is the check of the report's citations: where C6 passed, that report's citations met it. "
TESTS_A = ['tests/lab/test_diagnosis_rules.py', 'tests/experiments/test_diagnosis_probe.py']
TESTS_B = ['tests/lab/test_history_fireability.py', 'tests/lab/test_loop_limits_mechanic_context.py', 'tests/lab/test_diagnosis_rules.py']
M = [
 ('A1 C6 sentence restored in CHECKS_NOTE', 'backend/app/lab/diagnosis_guide.py',
  "check\\'s public meaning. Explain each", "check\\'s public meaning. " + C6.replace("'", "\\'") + "Explain each", TESTS_A),
 ('A2 block() leaves out checks_note', 'backend/app/lab/diagnosis_guide.py',
  "'checks': dict(rule['checks']), 'checks_note': rule['checks_note'], ", "'checks': dict(rule['checks']), ", TESTS_A),
 ('A3 FIXED_TEXT stops binding checks_note', 'backend/app/lab/diagnosis_guide.py',
  "FIXED_TEXT = {'meaning': MEANING, 'kinds': KINDS, 'checks_note': CHECKS_NOTE, ", "FIXED_TEXT = {'meaning': MEANING, 'kinds': KINDS, ", TESTS_A),
 ('A4 guide offered', 'backend/app/lab/diagnosis_guide.py', 'DIAGNOSIS_GUIDE_OFFERED = False', 'DIAGNOSIS_GUIDE_OFFERED = True', TESTS_A),
 ('B1 agent history reads episodes past its record cutoff', 'backend/app/lab/agent_history.py',
  "candidates = store.records_upto('episodes', cutoff, ", "candidates = store.records_upto('episodes', 10**9, ", TESTS_B),
 ('B1b agent history ignores its cutoff everywhere (episode list AND record lookups)', 'backend/app/lab/agent_history.py',
  "    return store.get_record(kind, ident) if rowid is not None and rowid <= cutoff else None",
  "    return store.get_record(kind, ident) if rowid is not None else None", TESTS_B),
 ('B2 fireability fired-share bar 1/2 -> 0 (nothing refused)', 'backend/app/lab/fireability.py',
  'MIN_FIRED_SHARE = Fraction(1, 2)', 'MIN_FIRED_SHARE = Fraction(0, 1)', TESTS_B),
 ('B3 v2d rebuild helper: the test module reads evaluations past its cutoff', 'backend/tests/lab/test_loop_limits_mechanic_context.py',
  "for raw in upto('evaluations'):", "for raw in store.list_records('evaluations'):", TESTS_B),
]
def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
def run(tests):
    r = subprocess.run([PY, '-B', '-m', 'pytest', '-p', 'vplug', '-p', 'no:cacheprovider', '-q', '-x', *tests], cwd=f'{T}/backend',
                       env=dict(os.environ, PYTHONPATH=f'{S}/plug', PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True)
    out = r.stdout + r.stderr
    summary = [l for l in out.splitlines() if re.search(r'\d+ (passed|failed)', l)]
    fails = [l for l in out.splitlines() if l.startswith(('FAILED', 'E  '))][:4]
    return r.returncode, (summary[-1] if summary else '?'), fails
which = sys.argv[1:] or [m[0].split()[0] for m in M]
for name, rel, old, new, tests in M:
    if name.split()[0] not in which: continue
    path = f'{T}/{rel}'; before = sha(path); src = open(path).read()
    if old is None:
        print(f'== {name}: SKIPPED (edit chosen at run time; see below)'); continue
    assert src.count(old) == 1, (name, src.count(old))
    mutated = src.replace(old, new)
    if name.startswith('B1b'):  # plus B1's edit
        mutated = mutated.replace("candidates = store.records_upto('episodes', cutoff, ", "candidates = store.records_upto('episodes', 10**9, ")
        assert mutated.count('10**9') == 1
    open(path, 'w').write(mutated)
    try:
        code, summary, fails = run(tests)
    finally:
        open(path, 'w').write(src)
    assert sha(path) == before
    print(f'== {name}: {"CAUGHT" if code != 0 else "NOT CAUGHT"} (exit {code}; {summary.strip()}; -x stops at first failure)')
    for f in fails: print('   ', f[:200])
print('baseline after restores:', run(TESTS_A + ['tests/lab/test_history_fireability.py', 'tests/lab/test_loop_limits_mechanic_context.py'])[1])
