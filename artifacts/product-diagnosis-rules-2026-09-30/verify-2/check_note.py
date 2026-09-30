#!/usr/bin/env python3
"""Verifier-2: product CHECKS_NOTE vs the draft (AST only, no imports). $0, offline."""
import ast, re
ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/'
def consts(path):
    out = {}
    for node in ast.parse(open(ROOT + path).read()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try: out[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception: pass
    return out
d = consts('artifacts/analysis-diagnosis-2026-09-30/design-minimal/proposed_diagnosis_guide.py')
p = consts('backend/app/lab/diagnosis_guide.py')
dn = d['CHECKS_NOTE']
c6 = "C6 is the check of the report's citations: where C6 passed, that report's citations met it. "
assert dn.count(c6) == 1, 'C6 sentence not found exactly once in the draft'
expected = dn.replace(c6, '')
print('draft note        :', repr(dn))
print('product note      :', repr(p['CHECKS_NOTE']))
print('product == draft with the C6 sentence (and its trailing space) removed:', p['CHECKS_NOTE'] == expected)
src = open(ROOT + 'backend/app/lab/diagnosis_guide.py').read()
print('C6 sentence fragments in product module:', {f: f in src for f in ("citations met it", "where C6 passed", "C6 is the check")})
print('check ids C1-C8 in the product note:', re.findall(r'\bC[1-8]\b', p['CHECKS_NOTE']))
for k in ('MEANING', 'KINDS', 'CONTRACT_NOTE', 'USE'):
    print(f'{k} equal to draft:', p[k] == d[k])
print('HYPOTHESIS_LENGTH equal to draft LENGTH:', p['HYPOTHESIS_LENGTH'] == d['LENGTH'])
print('DIAGNOSIS_GUIDE_OFFERED:', p['DIAGNOSIS_GUIDE_OFFERED'])
print('product RULE mentions a note on reading checks:', 'note on reading' in p['RULE'] or 'checks_note' in p['RULE'])
print('draft RULE mentions a note on reading checks:', 'note on reading' in d['RULE'] or 'checks_note' in d['RULE'])
