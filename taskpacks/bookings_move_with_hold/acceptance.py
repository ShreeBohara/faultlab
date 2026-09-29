"""Phase 1 exit criteria, computed offline at $0. Used by the tests and to write evidence files.

Run:  .venv/bin/python -B -m taskpacks.bookings_move_with_hold.acceptance [--out FILE]

Criteria (from SECOND_TASK_RECOMMENDATION.md, phase 1):

* reference: 8 cases x 3 seeds = 24 of 24 with zero failed checks, the expected class matches, every
  scheduled fault fires (unless the case is marked agent_dependent), and at least one turn of slack;
* buggy agents: each fails exactly its intended lowest check 3 of 3 on each intended case;
* $0 probe: give_up fails H3 and blind_retry fails H2, 3 of 3 on hk-dev-2 and hk-dev-3, and the
  reference passes both cases;
* determinism: the same case, agent and seed give the same world trace.
"""
import argparse
import json
import sys

from . import driver, mutants, table
from .reference import ReferenceAgent

TRIALS = 3


def summarize(record):
    verdict = record['verdict']
    return {'agent': record['agent'], 'case_id': record['case_id'], 'seed': record['seed'],
            'outcome': verdict['outcome'], 'failed_checks': verdict['failed_checks'],
            'lowest_failed_check': verdict['lowest_failed_check'], 'check_count': len(verdict['checks']),
            'turns_used': record['turns_used'], 'slack_turns': record['slack_turns'],
            'faults': [{k: f[k] for k in ('fault_id', 'kind', 'target_tool', 'triggered', 'reason')}
                       for f in record['fault_executions']],
            'effects': verdict['effects'], 'harm_sentence': verdict['harm_sentence'],
            'world_integrity': record['world_integrity']['status'], 'report_overall': (record['report'] or {}).get('overall'),
            'trace_hash': driver.trace_hash(record)}


def run(agent_cls, case, trials=TRIALS):
    return [summarize(driver.run_episode(agent_cls(), case, seed)) for seed in driver.trial_seeds(case, trials)]


def reference_criterion(cases):
    rows, problems = [], []
    for case in cases.values():
        allowed = table.EXPECTED_CLASSES[case['expected_class']]
        for row in run(ReferenceAgent, case):
            rows.append(row)
            where = f"{row['case_id']} seed {row['seed']}"
            if row['failed_checks']:
                problems.append(f"{where}: failed {row['failed_checks']}")
            if row['outcome'] not in allowed:
                problems.append(f"{where}: outcome {row['outcome']} not in {allowed}")
            if row['slack_turns'] < 1:
                problems.append(f"{where}: no turn of slack")
            if row['world_integrity'] != 'VALID':
                problems.append(f"{where}: world integrity {row['world_integrity']}")
            if not case['agent_dependent']:
                for f in row['faults']:
                    if not f['triggered']:
                        problems.append(f"{where}: {f['fault_id']} {f['kind']} did not fire ({f['reason']})")
    clean = sum(1 for r in rows if not r['failed_checks'])
    return {'name': 'reference 24 of 24 clean', 'passed': not problems and len(rows) == 24 and clean == 24,
            'clean': clean, 'total': len(rows), 'max_turns_used': max(r['turns_used'] for r in rows),
            'min_slack_turns': min(r['slack_turns'] for r in rows), 'problems': problems, 'rows': rows}


def mutant_criterion(cases):
    results, all_ok = [], True
    for name, (check, case_ids) in mutants.INTENDED.items():
        for case_id in case_ids:
            rows = run(mutants.MUTANTS[name], cases[case_id])
            hits = sum(1 for r in rows if r['lowest_failed_check'] == check)
            ok = hits == len(rows) == TRIALS
            all_ok &= ok
            results.append({'agent': name, 'case_id': case_id, 'intended_lowest_check': check, 'hits': hits,
                            'trials': len(rows), 'passed': ok,
                            'failed_checks_seen': sorted({tuple(r['failed_checks']) for r in rows}),
                            'harm_sentences': sorted({r['harm_sentence'] for r in rows})})
    return {'name': 'each buggy agent fails exactly its intended lowest check 3 of 3', 'passed': all_ok,
            'results': results}


def probe_criterion(cases):
    results, all_ok = [], True
    for case_id in mutants.PROBE_CASES:
        for caller, (cls, check) in mutants.PROBE_CALLERS.items():
            rows = run(cls, cases[case_id])
            hits = sum(1 for r in rows if r['lowest_failed_check'] == check)
            ok = hits == TRIALS
            all_ok &= ok
            results.append({'caller': caller, 'agent': cls.name, 'case_id': case_id, 'must_fail': check,
                            'hits': hits, 'trials': len(rows), 'passed': ok,
                            'harm_sentences': sorted({r['harm_sentence'] for r in rows})})
        rows = run(ReferenceAgent, cases[case_id])
        clean = sum(1 for r in rows if not r['failed_checks'])
        ok = clean == TRIALS
        all_ok &= ok
        results.append({'caller': 'reference', 'agent': 'reference', 'case_id': case_id, 'must_fail': None,
                        'clean': clean, 'trials': len(rows), 'passed': ok})
    return {'name': '$0 probe: give-up and blind-retry callers fail 3 of 3; reference passes', 'passed': all_ok,
            'results': results}


def determinism_criterion(cases):
    agents = [ReferenceAgent, *mutants.MUTANTS.values()]
    mismatches, pairs = [], 0
    for case in cases.values():
        seed = driver.trial_seeds(case, 1)[0]
        for cls in agents:
            first = driver.trace_hash(driver.run_episode(cls(), case, seed))
            second = driver.trace_hash(driver.run_episode(cls(), case, seed))
            pairs += 1
            if first != second:
                mismatches.append(f'{cls.name} {case["case_id"]}')
    # Different seeds change every identifier, so the traces differ.
    case = cases['hk-dev-2']
    a, b = (driver.trace_hash(driver.run_episode(ReferenceAgent(), case, s)) for s in driver.trial_seeds(case, 2))
    return {'name': 'same seed gives the same world trace', 'passed': not mismatches and a != b,
            'pairs_compared': pairs, 'mismatches': mismatches, 'different_seeds_differ': a != b}


def full_matrix(cases):
    """Every agent on every case, 3 seeds each. Evidence only; not an exit criterion."""
    rows = []
    for cls in (ReferenceAgent, *mutants.MUTANTS.values()):
        for case in cases.values():
            for row in run(cls, case):
                rows.append({k: row[k] for k in ('agent', 'case_id', 'seed', 'outcome', 'failed_checks',
                                                 'lowest_failed_check', 'turns_used', 'harm_sentence')})
    return rows


def exit_criteria():
    manifest = driver.load_manifest()
    cases = {c['case_id']: c for c in manifest['cases']}
    criteria = [reference_criterion(cases), mutant_criterion(cases), probe_criterion(cases),
                determinism_criterion(cases)]
    return {'schema_version': 'faultlab-pack-acceptance/v1', 'task_definition_id': table.TASK_DEFINITION_ID,
            'manifest_hash': manifest['manifest_hash'], 'all_passed': all(c['passed'] for c in criteria),
            'criteria': criteria, 'matrix': full_matrix(cases)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', help='also write the JSON result to this file')
    args = parser.parse_args(argv)
    result = exit_criteria()
    text = json.dumps(result, indent=1, sort_keys=True)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            handle.write(text + '\n')
    for c in result['criteria']:
        print(('PASS ' if c['passed'] else 'FAIL ') + c['name'], file=sys.stderr)
    print(text)
    return 0 if result['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
