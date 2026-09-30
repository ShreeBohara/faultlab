"""Verifier-2: flatten two gate_freeze JSONs and list every leaf that differs. Usage: compare.py a.json b.json"""
import json, sys
def flat(v, p=''):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items(): out.update(flat(x, f'{p}/{k}' if p else k))
        return out
    return {p: v}
a, b = (flat(json.load(open(x))) for x in sys.argv[1:3])
keys = sorted(set(a) | set(b))
diff = [k for k in keys if a.get(k) != b.get(k)]
print(f'# {sys.argv[1]} vs {sys.argv[2]}: {len(keys)} leaves, {len(diff)} differ')
for k in diff: print('DIFF', k, str(a.get(k))[:20], '->', str(b.get(k))[:20])
same_checks = [k for k in keys if 'checks.py' in k]
print('checks.py leaves:', {k: a.get(k) == b.get(k) for k in same_checks})
