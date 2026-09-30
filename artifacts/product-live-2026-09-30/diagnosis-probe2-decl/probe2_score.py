"""Diagnosis probe 2: declared primary measure P1b (written 2026-09-30 before any probe-2 call).

Probe 1's P1 was UNINFORMATIVE because its premise counted CONTROL rows only when the narrow checker-v2 phrase list AND a
person both flagged them. P1b uses the blind person-majority marks (three independent markers, frozen rubric sha
0fbe2556...) in both arms. Thresholds are probe 1's, unchanged. Inputs: the probe-2 --out folder (review-key.json,
scoring.json) and the probe-2 majority marks (JSON list of {id, blames_citations_labels_or_evidence_ids, ...}).
PASS iff CONTROL dev-5 Y >= 20 of 40 AND GUIDE dev-5 Y <= 4 of 40. CONTROL < 20 of 40 -> UNINFORMATIVE.
Decision: Rule 2 ships iff P1b PASS and the harness's P2 PASS. Everything else is descriptive."""
import json, sys, pathlib
out, marks_file = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
key = json.loads((out / 'review-key.json').read_text())['key']
marks = {m['id']: m for m in json.loads(marks_file.read_text())}
counts = {'CONTROL': [0, 0], 'GUIDE': [0, 0]}
for rid, meta in key.items():
    if not meta['request'].endswith('dev5') or meta['arm'] not in counts or rid not in marks:
        continue  # post-run bug fix: undelivered rows have no marks (rule unchanged)
    counts[meta['arm']][1] += 1
    counts[meta['arm']][0] += marks[rid]['blames_citations_labels_or_evidence_ids'] == 'Y'
c, g = counts['CONTROL'], counts['GUIDE']
p1b = 'UNINFORMATIVE' if c[0] < 20 else ('PASS' if g[0] <= 4 else 'FAIL')
p2 = json.loads((out / 'scoring.json').read_text())['P2']['status']
result = {'P1b': {'CONTROL_Y': f'{c[0]}/{c[1]}', 'GUIDE_Y': f'{g[0]}/{g[1]}', 'status': p1b}, 'P2': p2,
          'rule2_ships': p1b == 'PASS' and p2 == 'PASS'}
print(json.dumps(result, indent=1))
if len(sys.argv) > 3: pathlib.Path(sys.argv[3]).write_text(json.dumps(result, indent=1))
