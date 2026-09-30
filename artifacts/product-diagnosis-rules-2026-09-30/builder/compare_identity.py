"""Compare identity-before.json with identity-after.json and gate_freeze/before.json with after.json (stdlib only)."""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


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


a, b = parse(HERE / 'identity-before.json'), parse(HERE / 'identity-after.json')
lines = [f'CHANGED {k}: {a.get(k)} -> {b.get(k)}' for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
lines.append(f'unchanged: {sum(1 for k in set(a) & set(b) if a[k] == b[k])} of {len(set(a) | set(b))} keys')
(HERE / 'identity-compare.txt').write_text('\n'.join(lines) + '\n'); print('\n'.join(lines))
ga, gb = flat(json.loads((HERE / 'gate_freeze/before.json').read_text())), flat(json.loads((HERE / 'gate_freeze/after.json').read_text()))
changed = [k for k in sorted(set(ga) | set(gb)) if ga.get(k) != gb.get(k)]
text = f'{len(ga)} values compared; {len(changed)} changed:\n' + '\n'.join(changed) + '\n'
(HERE / 'gate_freeze/compare.txt').write_text(text); print(text)
