"""Compare two gate_freeze outputs: files, functions, fingerprints."""
import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
print('top-level keys:', sorted(a))
for section in sorted(set(a) | set(b)):
    va, vb = a.get(section), b.get(section)
    if isinstance(va, dict) and isinstance(vb, dict):
        keys = sorted(set(va) | set(vb))
        same = [k for k in keys if va.get(k) == vb.get(k)]
        print(f'{section}: {len(same)}/{len(keys)} identical')
        for k in keys:
            if va.get(k) != vb.get(k):
                print(f'   CHANGED {k}: {json.dumps(va.get(k))[:80]} -> {json.dumps(vb.get(k))[:80]}')
    else:
        print(f'{section}: {"identical" if va == vb else "CHANGED"}')
