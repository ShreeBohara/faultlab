#!/usr/bin/env python3
"""Reviewer: compare the product CHECKS_NOTE (and the other fixed text) with the prototype draft by AST, no imports. $0, offline."""
import ast, re, sys
ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/'
def consts(path):
    out = {}
    for node in ast.parse(open(ROOT + path).read()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception:
                pass
    return out
draft = consts('artifacts/analysis-diagnosis-2026-09-30/design-minimal/proposed_diagnosis_guide.py')
prod = consts('backend/app/lab/diagnosis_guide.py')
d, p = draft['CHECKS_NOTE'], prod['CHECKS_NOTE']
# split draft into sentences on '. ' boundaries
sents = re.split(r'(?<=\.) ', d)
print('draft sentences:', len(sents))
for i, s in enumerate(sents):
    print(f'  [{i}] {s!r}')
c6 = [s for s in sents if 'C6' in s]
print('C6 sentences in draft:', len(c6))
expected = ' '.join(s for s in sents if 'C6' not in s)
print('product note:', repr(p))
print('product == draft minus C6 sentence:', p == expected)
print('product contains "C6":', 'C6' in p, '| contains "citation":', 'citation' in p.lower())
print('product note mentions any check id C1-C8:', bool(re.search(r'\bC[1-8]\b', p)))
print('product sentences:', len(re.split(r'(?<=\.) ', p)))
for k in ('MEANING', 'KINDS', 'CONTRACT_NOTE', 'USE'):
    print(f'{k} equal to draft:', prod.get(k) == draft.get(k))
print('HYPOTHESIS_LENGTH == draft LENGTH:', prod.get('HYPOTHESIS_LENGTH') == draft.get('LENGTH'))
print('RULE equal to draft RULE:', prod.get('RULE') == draft.get('RULE'))
print('draft RULE mentions note on checks:', 'note on' in draft.get('RULE', '') or 'checks_note' in draft.get('RULE', ''))
print('product RULE mentions note on checks:', 'note on reading' in prod['RULE'] or 'checks_note' in prod['RULE'])
print('DIAGNOSIS_GUIDE_OFFERED =', prod.get('DIAGNOSIS_GUIDE_OFFERED'))
# any other place in product C6 interpretation text
src = open(ROOT + 'backend/app/lab/diagnosis_guide.py').read()
print('C6 sentence text anywhere in product module:', "where C6 passed" in src)
