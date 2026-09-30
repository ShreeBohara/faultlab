"""Compare two identity JSON files key by key; also compare the working tree's values with the fixer's identity-end.json."""
import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
for k in sorted(set(a) | set(b)):
    if k == 'tree':
        continue
    va, vb = a.get(k, '<absent>'), b.get(k, '<absent>')
    print(('same   ' if va == vb else 'CHANGED'), k, ':', json.dumps(va), '->', json.dumps(vb))
if len(sys.argv) > 3:
    text, f, dec, i = open(sys.argv[3]).read(), {}, json.JSONDecoder(), 0
    while i < len(text):  # the fixer's file holds two JSON objects one after the other
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        obj, i = dec.raw_decode(text, i); f.update(obj)
    alias = {'mechanic_evidence_v2_native_citation_status_declaration_hash': 'citation_status_declaration_hash'}
    print('\nworking tree vs fixer identity-end.json (shared keys):')
    n = bad = 0
    for k, v in f.items():
        kk = alias.get(k, k)
        if kk.startswith('example_configuration_hash['):
            kk = kk.split(',')[0] + ']'
        if kk in b:
            n += 1
            if b[kk] != v:
                bad += 1; print('  DIFFER', k, v, b[kk])
    print(f'  {n} shared keys, {bad} differ')
