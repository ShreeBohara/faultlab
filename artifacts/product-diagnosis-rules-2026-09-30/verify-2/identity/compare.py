"""Verifier-2: compare identity JSONs. Usage: compare.py a.json b.json [c.json] ; prints changed/unchanged keys."""
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
c = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
keys = sorted((set(a) | set(b)) - {'tree'})
ch = [k for k in keys if a.get(k) != b.get(k)]
un = [k for k in keys if a.get(k) == b.get(k)]
print(f'# {sys.argv[1]} vs {sys.argv[2]}: {len(ch)} changed, {len(un)} unchanged')
for k in ch:
    print('CHANGED', k, json.dumps(a.get(k))[:80], '->', json.dumps(b.get(k))[:80])
for k in un:
    print('same   ', k, json.dumps(a.get(k))[:80])
if c is not None:
    diff = [k for k in sorted(set(b) | set(c)) if k != 'tree' and b.get(k) != c.get(k)]
    print(f'# {sys.argv[2]} vs {sys.argv[3]}: {len(diff)} differ', diff)
