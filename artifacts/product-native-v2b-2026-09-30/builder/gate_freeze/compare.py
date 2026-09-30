"""Compare this round's gate_freeze output with the previous verifier's record of the ac7a12d2 tree (== backup/part2-2026-09-22)."""
import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
before = json.loads((here.parents[2] / 'product-native-v2-2026-09-29/verify/gate_freeze/current.json').read_text())
after = json.loads((here / 'current.json').read_text())
def flat(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flat(item, f'{prefix}/{key}' if prefix else key)
    else:
        yield prefix, value
a, b = dict(flat(before)), dict(flat(after))
changed = sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))
print(f'gate_freeze differences, ac7a12d2 tree (previous verifier record) -> this working tree: {len(changed)}')
for key in changed:
    print(f'  {key}: {str(a.get(key))[:16]} -> {str(b.get(key))[:16]}')
for key in ('files/backend/app/referee/checks.py', 'files/backend/app/referee/manifests.py', 'files/backend/app/lab/promotion.py',
            'files/backend/app/lab/evaluation.py', 'files/backend/app/agents/actor.py', 'files/backend/app/agents/prompts/actor.md',
            'files/backend/app/agents/progress.py', 'files/audit/development.json'):
    print(f'{key} unchanged: {a.get(key) == b.get(key)}')
funcs = [k for k in a if k.startswith('functions/') and 'assess_pairs' in k]
print('assess_pairs unchanged (text, ast, lines):', all(a[k] == b.get(k) for k in funcs), len(funcs), 'fields')
