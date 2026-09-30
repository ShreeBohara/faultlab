"""Compare the builder's identity and gate-freeze values (builder/identity-after.json, builder/gate_freeze/after.json) with
the fixer's (fixer/identity-after.json, fixer/gate_freeze/after.json), and the fixer's gate freeze with the builder's
before.json (the 626bae4 baseline). Stdlib only; reads only these JSON files."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILDER = HERE.parent / 'builder'


def parse(path):
    text, out, decoder, i = path.read_text(), {}, json.JSONDecoder(), 0
    while i < len(text):
        while i < len(text) and text[i].isspace(): i += 1
        if i >= len(text): break
        value, i = decoder.raw_decode(text, i); out.update(value)
    return out


def flat(d, prefix=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flat(v, prefix + k + '/'))
        else: out[prefix + k] = v
    return out


a, b = parse(BUILDER / 'identity-after.json'), parse(HERE / 'identity-after.json')
lines = ['identity: builder (after) -> fixer (after)']
lines += [f'CHANGED {k}: {a.get(k)} -> {b.get(k)}' for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
lines.append(f'unchanged: {sum(1 for k in set(a) & set(b) if a[k] == b[k])} of {len(set(a) | set(b))} keys')
for label, base in (('builder after', BUILDER / 'gate_freeze/after.json'), ('626bae4 baseline (builder before)', BUILDER / 'gate_freeze/before.json')):
    ga, gb = flat(json.loads(base.read_text())), flat(json.loads((HERE / 'gate_freeze/after.json').read_text()))
    changed = [k for k in sorted(set(ga) | set(gb)) if ga.get(k) != gb.get(k)]
    lines.append(f'gate freeze, {label} -> fixer: {len(ga)} values compared; {len(changed)} changed:')
    lines += ['  ' + k for k in changed]
(HERE / 'identity-compare.txt').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
