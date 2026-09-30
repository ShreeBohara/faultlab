#!/usr/bin/env python3
"""Reviewer's own mutation checks ($0, offline), chosen independently of the fixer's list.

Runs ONLY in the reviewer's scratch copy (/Users/shree/FaultLab_Scratch/followup-review/tree/faultlab); the real tree is
never edited (rguard refuses any write into it). Each mutation replaces one anchor that must occur exactly once, runs the
named tests with rguard + rstub, records pass/fail and the first assertion lines, then restores the file byte for byte
and checks its sha256. An unmutated control run comes first and last.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SC = Path('/Users/shree/FaultLab_Scratch/followup-review')
TREE = SC / 'tree/faultlab/backend'
REVIEW = Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-diagnosis-rules-2026-09-30/followup-review')
PY = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python'

FIRE = 'tests/lab/test_history_fireability.py::'
SAVED_B = [FIRE + 'test_a_new_v4_plan_on_the_saved_store_refuses_the_lone_status_read_target',
           FIRE + 'test_the_saved_stores_status_read_picks_are_refused_and_its_other_picks_are_allowed',
           FIRE + 'test_through_the_real_loop_on_the_saved_store_a_status_pick_is_refused_and_replanned',
           'tests/lab/test_loop_limits_mechanic_context.py::test_the_refused_v2d_request_rebuilds_exactly_and_fits_after_compaction_with_its_omission_statement',
           'tests/lab/test_citation_status.py::test_v2ds_refused_candidate_request_with_the_block_still_fits_after_compaction_and_keeps_every_row',
           'tests/lab/test_diagnosis_rules.py::test_T1_every_saved_native_v2b_plan_rereads_with_its_plan_hash_and_no_new_keys']
SET_A = ['tests/lab/test_diagnosis_rules.py', 'tests/experiments/test_diagnosis_probe.py']
C6 = "C6 is the check of the report's citations: where C6 passed, that report's citations met it."

MUTATIONS = [
    # ---- (B) saved-store tests: real regressions the pinned tests must still catch
    ('B1', 'store reads ignore the record cutoff (history leak)', 'app/lab/storage.py',
     "clauses, parameters = ['kind=?', 'rowid<=?'], [kind, int(cutoff)]",
     "clauses, parameters = ['kind=?', 'rowid<=?'], [kind, 10**12]", SAVED_B),
    ('B2', "Start re-checks the frozen history at today's row instead of the plan's cutoff", 'app/lab/agent_history.py',
     "current = compute_history(store, identity=identity, policy_hash=policy_hash, cutoff=block['record_cutoff'])",
     "current = compute_history(store, identity=identity, policy_hash=policy_hash, cutoff=store.max_record_rowid())", SAVED_B),
    ('B3', 'history drops baseline-study episodes', 'app/lab/agent_history.py',
     "        return 'baseline_study'\n", "        return None\n", SAVED_B),
    ('B4', 'history counts a fired fault twice', 'app/lab/agent_history.py',
     "row['every_fault_fired'] += 1", "row['every_fault_fired'] += 2", SAVED_B),
    ('B5', 'challenge picks are never refused', 'app/lab/fireability.py',
     "    if len(refused) < len(decision['targets']):", "    if challenge or len(refused) < len(decision['targets']):", SAVED_B),
    ('B6', 'a pick is refused when ANY fault targets a REFUSED row (mixed-pick rule inverted)', 'app/lab/fireability.py',
     "    if len(refused) < len(decision['targets']):", "    if not refused:", SAVED_B + [FIRE[:-2]]),
    ('B7', 'replay list capped at 1 instead of 3', 'app/lab/history_replay.py',
     'MAX_REPLAYS = 3', 'MAX_REPLAYS = 1', SAVED_B),
    ('B8', 'format-repair reserve 4000 -> 3000 (size-rule target +1000)', 'app/lab/loop_limits.py',
     'FORMAT_REPAIR_RESERVE_TOKENS = 4000', 'FORMAT_REPAIR_RESERVE_TOKENS = 3000', SAVED_B),
    ('B9', 'snapshot reads "now" twice (brittleness probe for the one-read assertion)', 'app/lab/agent_history.py',
     "    return compute_history(store, identity=identity, policy_hash=policy_hash, cutoff=store.max_record_rowid())",
     "    store.max_record_rowid()\n    return compute_history(store, identity=identity, policy_hash=policy_hash, cutoff=store.max_record_rowid())",
     SAVED_B[:3]),
    # ---- (A) the checks_note decision
    ('A1', 'checks_note loses its final period', 'app/lab/diagnosis_guide.py',
     "Explain each failed check from its own meaning.')", "Explain each failed check from its own meaning')", SET_A),
    ('A2', 'the C6 sentence is put back into checks_note', 'app/lab/diagnosis_guide.py',
     "check\\'s public meaning. Explain each", "check\\'s public meaning. " + C6.replace("'", "\\'") + " Explain each", SET_A),
    ('A3', 'Rule 2 offered (DIAGNOSIS_GUIDE_OFFERED = True)', 'app/lab/diagnosis_guide.py',
     'DIAGNOSIS_GUIDE_OFFERED = False', 'DIAGNOSIS_GUIDE_OFFERED = True', SET_A),
    ('A4', "the block sends no checks_note (declaration keeps it)", 'app/lab/diagnosis_guide.py',
     "'checks': dict(rule['checks']), 'checks_note': rule['checks_note'], 'contract_note'",
     "'checks': dict(rule['checks']), 'contract_note'", SET_A),
    ('A5', 'the plan model accepts interprets_checks=True', 'app/lab/run_plans.py',
     '    interprets_checks: Literal[False]\n', '    interprets_checks: bool\n', SET_A),
    ('A6', 'Start stops binding the note word for word (FIXED_TEXT without checks_note)', 'app/lab/diagnosis_guide.py',
     "FIXED_TEXT = {'meaning': MEANING, 'kinds': KINDS, 'checks_note': CHECKS_NOTE, 'contract_note': CONTRACT_NOTE,",
     "FIXED_TEXT = {'meaning': MEANING, 'kinds': KINDS, 'contract_note': CONTRACT_NOTE,", SET_A),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(tests):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHON_DOTENV_DISABLED='1', PYTHONPATH=str(REVIEW))
    base = SC / 'pytest-base'
    subprocess.run(['rm', '-rf', str(base)])
    proc = subprocess.run([PY, '-B', '-m', 'pytest', '-p', 'rguard', '-p', 'rstub', '-p', 'no:cacheprovider', '-q', '-rfE',
                           f'--basetemp={base}', *tests], cwd=TREE, env=env, capture_output=True, text=True, timeout=1800)
    out = proc.stdout + proc.stderr
    summary = next((line for line in reversed(out.splitlines()) if re.search(r'\d+ (passed|failed|error)', line)), '?')
    failed = sorted(set(re.findall(r'^(?:FAILED|ERROR) (\S+)', out, re.M)))
    asserts = [line.strip()[:160] for line in out.splitlines() if re.match(r'^E\s+(assert|AssertionError|.*Error)', line)][:4]
    guard = next((line for line in out.splitlines() if line.startswith('[reviewer guard]')), '')
    return {'exit': proc.returncode, 'summary': summary, 'failed': [f.split('::')[-1] for f in failed], 'first_errors': asserts,
            'guard': guard}


def main():
    results = []
    all_tests = sorted({t for m in MUTATIONS for t in m[5]})
    control = run(all_tests)
    results.append({'id': 'CONTROL-before', 'result': control})
    print('CONTROL-before', control['summary'], control['guard'], flush=True)
    for ident, what, rel, old, new, tests in MUTATIONS:
        path = TREE / rel
        before = path.read_bytes(); digest = sha(path)
        text = before.decode()
        count = text.count(old)
        if count != 1:
            results.append({'id': ident, 'what': what, 'error': f'anchor found {count} times'}); print(ident, 'ANCHOR', count); continue
        try:
            path.write_text(text.replace(old, new))
            result = run(tests)
        finally:
            path.write_bytes(before)
        assert sha(path) == digest, f'{rel} not restored'
        caught = result['exit'] != 0
        results.append({'id': ident, 'what': what, 'file': rel, 'tests_run': len(tests), 'caught': caught, 'result': result})
        print(ident, 'CAUGHT' if caught else 'NOT CAUGHT', '|', what, '|', result['summary'], '|', result['failed'][:6],
              '|', result['first_errors'][:2], flush=True)
    control = run(all_tests)
    results.append({'id': 'CONTROL-after', 'result': control})
    print('CONTROL-after', control['summary'], control['guard'], flush=True)
    (REVIEW / 'mutations.json').write_text(json.dumps(results, indent=1))


if __name__ == '__main__':
    main()
