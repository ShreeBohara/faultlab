"""Fixer: compare two identity outputs (each two concatenated JSON objects from identity.py). Usage: identity_compare.py A B"""
import json
import sys


def load(path):
    text, dec, out, i = open(path).read(), json.JSONDecoder(), {}, 0
    while True:
        rest = text[i:].lstrip()
        if not rest:
            return out
        obj, n = dec.raw_decode(rest)
        out.update(obj)
        i = len(text) - len(rest) + n


a, b = load(sys.argv[1]), load(sys.argv[2])
for key in sorted(set(a) | set(b)):
    if a.get(key) != b.get(key):
        print(f'CHANGED  {key}: {a.get(key)} -> {b.get(key)}')
print(f'UNCHANGED {sum(1 for k in a if a.get(k) == b.get(k))} of {len(a)} keys:')
for key in sorted(k for k in a if a.get(k) == b.get(k)):
    print(f'  {key}: {a[key]}')
