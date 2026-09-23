"""Read-only summary of a saved context study. Makes no model or provider call.

Usage: python scripts/experiments/summarize_context_study.py STUDY_ID [--json OUT]
Reads the local backend's read-only API only.
"""
import argparse, collections, json, sys, urllib.request

BASE = 'http://127.0.0.1:8000'


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('study_id')
    parser.add_argument('--json', dest='out')
    args = parser.parse_args()
    study = get('/api/context-studies/' + args.study_id)
    arms = study['arms']
    rows = study['trial_rows']
    by_case = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    usage = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    checks = collections.defaultdict(collections.Counter)
    for row in rows:
        trial = row['trial']; arm = trial['arm']; case = row['case_id']
        key = trial['outcome'] if trial['lifecycle'] == 'COMPLETED' else trial['lifecycle']
        by_case[case][arm][key] += 1
        usage[case][arm]['actor_calls'] += trial['usage']['actor_calls']
        usage[case][arm]['http_attempts'] += trial['usage']['http_attempts']
        usage[case][arm]['trials'] += 1
        for check in trial['failed_checks'] or []:
            checks[arm][check] += 1
    print(f"study {study['study_id']} status {study['status']} decision {study['decision']}")
    print(study['reason'])
    print(f"charged model calls {study['charged_model_calls']} of {study['reserved_model_calls']} reserved; "
          f"conservative bound ${study.get('conservative_charge_bound')}")
    print(f"evidence: {collections.Counter(study['evidence'].values())}")
    target = {case['case_id']: case['target_outcome'] for case in study['manifest']['cases']}
    width = max(len(name) for name in target)
    print()
    print(f"{'case'.ljust(width)}  target               " + '  '.join(arm.ljust(34) for arm in arms))
    for case in target:
        cells = []
        for arm in arms:
            counts = by_case[case][arm]
            cells.append(('  '.join(f'{k.lower()}={v}' for k, v in sorted(counts.items())) or '-').ljust(34))
        print(f'{case.ljust(width)}  {target[case].ljust(20)} ' + '  '.join(cells))
    print()
    print('model turns / HTTP attempts per case')
    for case in target:
        parts = []
        for arm in arms:
            u = usage[case][arm]
            parts.append(f"{arm} {u['actor_calls']}/{u['http_attempts']} over {u['trials']} trials")
        print(f'  {case.ljust(width)}  ' + '   '.join(parts))
    print()
    print('failed checks by arm:', {arm: dict(checks[arm]) for arm in arms})
    totals = study.get('action_profile_totals') or {}
    if totals:
        print()
        print('public action totals')
        for arm in arms:
            for service, counts in (totals.get(arm) or {}).items():
                print(f'  {arm} {service}: ' + '  '.join(f'{k}={v}' for k, v in sorted(counts.items())))
    assessment = study.get('assessment') or {}
    if assessment:
        print()
        print('primary completions', assessment.get('primary_completions'),
              'of', assessment.get('primary_denominator'),
              'on', assessment.get('primary_case_ids'))
        print('violations', assessment.get('violations'),
              'regressed', assessment.get('regressed_case_ids'),
              'incomplete', assessment.get('incomplete_case_ids'))
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as file:
            json.dump({'study': study, 'by_case': {c: {a: dict(by_case[c][a]) for a in arms} for c in target},
                       'usage': {c: {a: dict(usage[c][a]) for a in arms} for c in target},
                       'failed_checks': {a: dict(checks[a]) for a in arms}}, file, indent=2)
        print('\nsaved', args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
