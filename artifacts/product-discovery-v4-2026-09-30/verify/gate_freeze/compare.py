"""Independent verifier: compare gate_freeze output of the checkpoint (backup tip 4d1c21b) and the working tree, and my
working-tree record with the fixer's after.json."""
import json
c = json.load(open('checkpoint.json')); w = json.load(open('current.json')); f = json.load(open('../../fixer/gate_freeze/after.json'))
def flat(d, pre=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flat(v, pre + k + '/'))
        else: out[pre + k] = v
    return out
C, W, F = flat(c), flat(w), flat(f)
print('gate_freeze (script loaded from the checkpoint copy; audit/promotion.json and final-audit.json dropped from FILES)')
print('checkpoint 4d1c21b -> working tree:')
for k in sorted(set(C) | set(W)):
    if C.get(k) != W.get(k): print('CHANGED', k, ':', str(C.get(k))[:20], '->', str(W.get(k))[:20])
# Revision 2: gate_freeze keys are 'path::name' (functions) and 'path' (files); compare whole values, no flattening.
same_fn = sum(c['functions'][k] == w['functions'].get(k) for k in c['functions'])
same_fl = sum(c['files'][k] == w['files'].get(k) for k in c['files'])
print(f"functions identical: {same_fn} of {len(c['functions'])} (keys equal: {set(c['functions']) == set(w['functions'])}); files identical: {same_fl} of {len(c['files'])} (keys equal: {set(c['files']) == set(w['files'])})")
for k in sorted(c['functions']):
    if c['functions'][k] != w['functions'].get(k): print('FUNCTION CHANGED', k)
print('protected entries: checks.py file', 'same' if c['files'].get('backend/app/referee/checks.py') == w['files'].get('backend/app/referee/checks.py') else 'CHANGED',
      '| checks.py::score', 'same' if c['functions'].get('backend/app/referee/checks.py::score') == w['functions'].get('backend/app/referee/checks.py::score') else 'CHANGED',
      '| checks.py::scorer_hash', 'same' if c['functions'].get('backend/app/referee/checks.py::scorer_hash') == w['functions'].get('backend/app/referee/checks.py::scorer_hash') else 'CHANGED',
      '| completion_study.py::assess_pairs', 'same' if c['functions'].get('backend/app/lab/completion_study.py::assess_pairs') == w['functions'].get('backend/app/lab/completion_study.py::assess_pairs') else 'CHANGED')
print('assess_pairs text sha256 prefix:', str(c['functions'].get('backend/app/lab/completion_study.py::assess_pairs'))[:80])
print('my working-tree record equals the fixer after.json:', W == F, '(differences:', [k for k in set(W) | set(F) if W.get(k) != F.get(k)], ')')
