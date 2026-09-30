"""Verifier: look for sync-client conflict copies anywhere in the faultlab tree (read-only, names only).
Patterns: a name ending in ' <n>' before its extension or at the end ('file 2.py', 'docs 2'), '(conflicted copy)',
'conflict', '-Mac.', '.icloud'. Skips .git, node_modules, .venv, __pycache__. Prints every hit with whether it is under
artifacts/.
Verifier change (citation-status round): artifacts/heldout2/ is pruned (its entries are never listed)."""
import os, re, sys
ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
PAT = re.compile(r'( \d+(\.[^/]*)?$)|(conflicted copy)|(conflict)|(-Mac\.)|(\.icloud$)', re.I)
hits = []
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in ('.git', 'node_modules', '.venv', '__pycache__', '.pytest_cache')
              and not (d == 'heldout2' and os.path.relpath(dp, ROOT) == 'artifacts')]
    for name in dns + fns:
        if PAT.search(name):
            rel = os.path.relpath(os.path.join(dp, name), ROOT)
            hits.append(rel)
outside = [h for h in hits if not h.startswith('artifacts/')]
print('conflict-like names found:', len(hits), '| outside artifacts/:', len(outside))
for h in hits: print(('OUTSIDE ' if not h.startswith('artifacts/') else 'artifacts ') + h)
