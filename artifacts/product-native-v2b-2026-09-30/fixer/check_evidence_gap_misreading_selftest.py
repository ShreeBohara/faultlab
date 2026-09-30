#!/usr/bin/env python3
"""Self-test (negative controls) for check_evidence_gap_misreading.py on the September 29 export ($0, stdlib only).
1. unchanged export -> MISREADING (the reviewers' manual finding);
2. one episode read cites an ID that is not a recorded observation -> SUPPORTED;
3. one episode read has an adapter-recorded undecoded token -> SUPPORTED;
4. the hypothesis makes no undelivered-citation claim -> NOT_CHECKED;
5. proposed_kind POLICY_GAP -> NOT_CHECKED."""
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_evidence_gap_misreading import check
export = json.loads((Path(__file__).resolve().parents[2] / 'product-live-2026-09-30/native-v2-run/export.json').read_text())
EP = 'episode-40130001730c4d8a920380407672a97c'
def verdict(data): return check(data)['diagnostics'][0]['verdict']
results = {'1-unchanged': verdict(export)}
data = copy.deepcopy(export)
next(e for e in data['episodes'] if e['episode_id'] == EP)['report']['evidence_ids'].append('obs-6')
results['2-unrecorded-id'] = verdict(data)
data = copy.deepcopy(export)
for event in data['events'][EP]:
    if event['type'] == 'report_submitted': event['payload']['cited_unshown_labels'] = ['obs-6']
results['3-adapter-undecoded'] = verdict(data)
data = copy.deepcopy(export)
for row in data['mechanic_outputs']:
    row['raw'] = json.dumps({'proposed_kind': 'CONTRACT_EVIDENCE_GAP', 'hypothesis': 'The notification status endpoint is missing from the contract.'})
results['4-no-claim'] = verdict(data)
data = copy.deepcopy(export)
data['diagnostics'][0]['proposed_kind'] = 'POLICY_GAP'
results['5-policy-gap'] = verdict(data)
expected = {'1-unchanged': 'MISREADING', '2-unrecorded-id': 'SUPPORTED', '3-adapter-undecoded': 'SUPPORTED',
            '4-no-claim': 'NOT_CHECKED', '5-policy-gap': 'NOT_CHECKED'}
for key in expected: print(('OK  ' if results[key] == expected[key] else 'FAIL'), key, results[key])
sys.exit(0 if results == expected else 1)
