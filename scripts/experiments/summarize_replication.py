"""Read-only read-out of the Phase 9 paired replication against its predeclared rules.

Makes no model call, creates no record and writes nothing to the lab database.
Every number it prints is computed from saved records plus the run manifest.

Primary read-out, fixed in docs/part2/PHASE9_EXPERIMENT.md: for each study, does its FIRST
proposal contain a step with op == 'retry_original_request' and service == 'notifications'?
Compared across arms with Fisher's exact test, two-sided.

Usage:
  python scripts/experiments/summarize_replication.py [--manifest PATH]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[2]
DB = f"file:{ROOT / 'artifacts/lab.sqlite3'}?mode=ro"

# The predeclared read-out has exactly one implementation, in the runner. Importing it
# here rather than restating it means the number this script reports cannot drift from
# the number the run itself recorded.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from run_replication import first_proposal_draw, has_notification_retry  # noqa: E402


def fisher_exact_two_sided(a, b, c, d):
    """Two-sided Fisher exact by summing tables no more probable than the observed one."""
    n = a + b + c + d
    row1, row2, col1 = a + b, c + d, a + c
    if n == 0 or row1 == 0 or row2 == 0:
        return 1.0

    def probability(x):
        y, z = row1 - x, col1 - x
        w = row2 - z
        if min(x, y, z, w) < 0:
            return 0.0
        return comb(row1, x) * comb(row2, z) / comb(n, col1)

    observed = probability(a)
    return min(1.0, sum(probability(x) for x in range(0, min(row1, col1) + 1)
                        if probability(x) <= observed + 1e-12))


def record(connection, kind, record_id):
    row = connection.execute('select payload from records where kind=? and id=?',
                             (kind, record_id)).fetchone()
    return json.loads(row[0]) if row else None


def study_stats(connection, study):
    """Every secondary read-out this phase predeclared, from one study's saved record."""
    candidates = study.get('candidates', [])
    contents = [c.get('content') for c in candidates if c.get('content')]
    hashes = [c.get('policy_hash') for c in candidates if c.get('policy_hash')]
    distinct = {h for h in hashes}
    stats = {
        'proposals': len(candidates),
        'distinct_policies': len(distinct),
        'any_proposal_has_step': any(has_notification_retry(c) for c in contents),
        'distinct_with_step': len({c.get('policy_hash') for c in candidates
                                   if c.get('content') and has_notification_retry(c['content'])}),
        'duplicate_second': len(hashes) >= 2 and hashes[0] == hashes[1],
        'qualified': any((c.get('source_assessment') or {}).get('decision') == 'SOURCE_QUALIFIED'
                         for c in candidates),
        'step_candidate_completions': None,
        'l_violations': 0, 'b0_violations': 0, 'l_trials': 0, 'b0_trials': 0,
        'control_source_trials': 0, 'control_source_completions': 0,
        'failed_checks': {},
    }
    for row in study.get('trial_rows', []):
        trial = row['trial']
        arm, stage = trial['arm'], row.get('stage')
        if arm == 'L':
            stats['l_trials'] += 1
            stats['l_violations'] += trial['outcome'] == 'VIOLATION'
        elif arm == 'B0':
            stats['b0_trials'] += 1
            stats['b0_violations'] += trial['outcome'] == 'VIOLATION'
        for check in trial.get('failed_checks') or []:
            stats['failed_checks'][check] = stats['failed_checks'].get(check, 0) + 1
        if stage == 'controls' and row.get('case_id') == 'notification-2' and arm == 'B0':
            # Only valid triggered controls count toward the leakage estimate.
            if trial['lifecycle'] == 'COMPLETED' and trial['outcome'] != 'LAB_ERROR' \
                    and (not trial.get('fault_scheduled') or trial.get('fault_triggered')):
                stats['control_source_trials'] += 1
                stats['control_source_completions'] += trial['outcome'] == 'COMPLETED'
    # Did a candidate that CONTAINS the step actually complete the source case?
    for index, candidate in enumerate(candidates, 1):
        if not (candidate.get('content') and has_notification_retry(candidate['content'])):
            continue
        rows = [r['trial'] for r in study.get('trial_rows', [])
                if r.get('stage') == f'candidate-{index}' and r['trial']['arm'] == 'L']
        if rows:
            stats['step_candidate_completions'] = (
                sum(t['outcome'] == 'COMPLETED' for t in rows), len(rows))
            break
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='artifacts/phase9-2026-09-20/replication-manifest.json')
    args = parser.parse_args()
    manifest = json.loads((ROOT / args.manifest).read_text())
    connection = sqlite3.connect(DB, uri=True)
    try:
        rows = []
        for attempt in manifest['attempts']:
            if not attempt.get('study_id'):
                rows.append({**attempt, 'draw': None, 'stats': None}); continue
            study = record(connection, 'completion_studies', attempt['study_id'])
            rows.append({**attempt, 'draw': first_proposal_draw(study),
                         'study': study, 'stats': study_stats(connection, study)})
    finally:
        connection.close()

    print('=' * 84)
    print(f"Phase 9 replication — {manifest['treatment']}  vs  {manifest['control']}")
    print(f"target {manifest['target_per_arm']}/arm, attempt cap {manifest['attempt_cap_per_arm']}/arm"
          + (f", STOPPED EARLY: {manifest.get('stopped_early')}" if manifest.get('stopped_early') else ''))
    print('=' * 84)
    print(f"{'label':>6} {'arm':>4} {'status':>11} {'stage':>12} {'prop':>5} {'draw':>6}  reason")
    for row in rows:
        draw = {True: 'STEP', False: 'no', None: '—'}[row['draw']]
        print(f"{row['label']:>6} {row['arm']:>4} {str(row.get('status')):>11} "
              f"{str(row.get('stage')):>12} {str(row.get('proposals')):>5} {draw:>6}  "
              f"{str(row.get('reason'))[:44]}")

    table = {}
    for arm in ('T', 'C'):
        drawn = [r for r in rows if r['arm'] == arm and r['draw'] is not None]
        table[arm] = (sum(r['draw'] for r in drawn), len(drawn))
    (tA, tN), (cA, cN) = table['T'], table['C']
    p = fisher_exact_two_sided(tA, tN - tA, cA, cN - cA)
    print()
    print('PRIMARY READ-OUT — first proposal contains retry_original_request for notifications')
    print(f"  T (task_outcome) : {tA} of {tN} informative studies")
    print(f"  C (preserved v1) : {cA} of {cN} informative studies")
    print(f"  Fisher exact, two-sided: p = {p:.5f}   {'SIGNIFICANT at 0.05' if p <= 0.05 else 'not significant at 0.05'}")
    print(f"  no-draw studies retained: T={sum(1 for r in rows if r['arm']=='T' and r['draw'] is None)}"
          f" C={sum(1 for r in rows if r['arm']=='C' and r['draw'] is None)}")

    print()
    print('SECONDARY READ-OUTS')
    for arm in ('T', 'C'):
        got = [r for r in rows if r['arm'] == arm and r.get('stats')]
        if not got:
            continue
        s = [r['stats'] for r in got]
        comps = [x['step_candidate_completions'] for x in s if x['step_candidate_completions']]
        checks = {}
        for x in s:
            for k, v in x['failed_checks'].items():
                checks[k] = checks.get(k, 0) + v
        src_t = sum(x['control_source_trials'] for x in s)
        src_c = sum(x['control_source_completions'] for x in s)
        print(f"  arm {arm}  ({len(got)} studies with records)")
        print(f"    any-proposal has step     : {sum(x['any_proposal_has_step'] for x in s)}")
        print(f"    distinct policies w/ step : {sum(x['distinct_with_step'] for x in s)}"
              f" of {sum(x['distinct_policies'] for x in s)} distinct")
        print(f"    byte-identical 2nd proposal: {sum(x['duplicate_second'] for x in s)}")
        print(f"    candidate SOURCE_QUALIFIED : {sum(x['qualified'] for x in s)}")
        print(f"    step-candidate completions : {comps or 'none'}")
        print(f"    violations  L {sum(x['l_violations'] for x in s)}/{sum(x['l_trials'] for x in s)}"
              f"   B0 {sum(x['b0_violations'] for x in s)}/{sum(x['b0_trials'] for x in s)}")
        print(f"    failed checks             : {dict(sorted(checks.items()))}")
        print(f"    baseline source leakage   : {src_c}/{src_t} valid triggered control episodes"
              + (f" = {100*src_c/src_t:.1f}%" if src_t else ''))
    print()
    print(f"charged upper bound: ${manifest.get('total_charged_upper_bound') or 0:.5f}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
