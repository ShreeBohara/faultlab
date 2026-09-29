"""Declared step-1 -> step-2 decision for the native adapter v2 run (PLAN.md section 3). Reads study-final.json only.
GO iff: study COMPLETED; 0 lab errors/interruptions; 0 B1 control deviations; dev-5 C3 in >= 2 of 3 B0 trials (the
repairable target is still exposed); C5 in <= 2 of the 15 B0 trials outside dev-5 (the report fix is working;
native v1 had 4 of 15 in the 2026-09-29 baseline). Everything else in the output is descriptive."""
import json, sys, pathlib, collections
R = pathlib.Path(sys.argv[1]); st = json.loads((R / 'study-final.json').read_text())
EXPECT = {'dev-1': 'COMPLETED', 'dev-2': 'COMPLETED', 'dev-3': 'COMPLETED', 'dev-4': 'COMPLETED', 'dev-5': 'CORRECTLY_REJECTED', 'dev-6': 'COMPLETED'}
trials = {t['episode_id']: t for t in st['trials']}
rows = []
for s in st['slots']:
    t = trials.get(s['episode_id'], {})
    rows.append({'case': s['case_id'], 'arm': s['arm'], 'lifecycle': t.get('lifecycle'), 'outcome': t.get('outcome'),
                 'failed_checks': t.get('failed_checks', []), 'reason': t.get('reason'), 'actor_calls': (t.get('usage') or {}).get('actor_calls')})
b0 = [r for r in rows if r['arm'] == 'B0']; b1 = [r for r in rows if r['arm'] == 'B1']
lab = [r for r in rows if r['lifecycle'] != 'COMPLETED' or r['outcome'] in (None, 'LAB_ERROR')]
b1_dev = [r for r in b1 if r['outcome'] != EXPECT[r['case']]]
dev5_c3 = sum('C3' in r['failed_checks'] for r in b0 if r['case'] == 'dev-5')
c5_out = sum('C5' in r['failed_checks'] for r in b0 if r['case'] != 'dev-5')
n_out = sum(1 for r in b0 if r['case'] != 'dev-5')
go = st['status'] == 'COMPLETED' and not lab and not b1_dev and dev5_c3 >= 2 and c5_out <= 2 and len(b0) == 18
per_case = collections.defaultdict(list)
for r in b0: per_case[r['case']].append({'outcome': r['outcome'], 'failed': r['failed_checks'], 'reason': r['reason']})
out = {'decision': 'GO' if go else 'NO_GO', 'study_status': st['status'], 'lab_errors': len(lab), 'b1_deviations': len(b1_dev),
       'dev5_c3': f'{dev5_c3} of 3', 'c5_outside_dev5': f'{c5_out} of {n_out}',
       'b0_violated': f"{sum(r['outcome'] == 'VIOLATION' for r in b0)} of {len(b0)}",
       'b0_c5_total': sum('C5' in r['failed_checks'] for r in b0),
       'reference_v1': 'native v1: 8/18 violated (2026-09-28 probe), 7/18 (2026-09-29 baseline, 4 of 15 C5 outside dev-5, dev-5 C3 3/3)',
       'per_case_b0': per_case}
(R / 'go-decision.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
