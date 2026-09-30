#!/usr/bin/env python3
"""Fixer (v2b): compare the working tree with backup/part2-2026-09-22 by git blob hash, read-only ($0, offline).

Never hashes or reads: .env / .env.* (except .env.example), audit/promotion.json, audit/final-audit*,
artifacts/heldout2/, backend/app/referee/checks.py (checks.py is compared only through gate_freeze).
Lists every file tracked on the branch that is CHANGED or MISSING in the working tree, and every working-tree file
(tracked by HEAD or untracked and not ignored) that is ADDED (absent from the branch). Addresses review finding LOW-3:
the listing covers untracked files and is regenerated after the last edit.
Run from faultlab/:  python3 -B artifacts/product-native-v2b-2026-09-30/fixer/tree_compare.py > OUT
"""
import fnmatch
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
REF = sys.argv[1] if len(sys.argv) > 1 else 'backup/part2-2026-09-22'
SKIP = ['.env', '.env.*', 'audit/promotion.json', 'audit/final-audit*', 'artifacts/heldout2/*', 'backend/app/referee/checks.py']


def skip(path):
    if path == '.env.example':
        return False
    return any(fnmatch.fnmatch(path, pattern) for pattern in SKIP) or os.path.basename(path).startswith('.env')


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


ref_blobs = {}
for line in git('ls-tree', '-r', REF).splitlines():
    meta, path = line.split('\t', 1)
    ref_blobs[path] = meta.split()[2]
paths = sorted(p for p in ref_blobs if not skip(p))
skipped = sorted(p for p in ref_blobs if skip(p))
existing = [p for p in paths if os.path.lexists(os.path.join(ROOT, p))]
missing = [p for p in paths if not os.path.lexists(os.path.join(ROOT, p))]
hashes = subprocess.run(['git', 'hash-object', '--no-filters', '--stdin-paths'], cwd=ROOT, input='\n'.join(existing) + '\n',
                        capture_output=True, text=True, check=True).stdout.split()
changed = [p for p, h in zip(existing, hashes) if h != ref_blobs[p]]
worktree = set(git('ls-files', '--cached', '--others', '--exclude-standard').splitlines())
added = sorted(p for p in worktree if p not in ref_blobs and not skip(p) and os.path.exists(os.path.join(ROOT, p)))
print(f'REF {REF} = {git("rev-parse", REF).strip()}   HEAD = {git("rev-parse", "HEAD").strip()}')
for p in skipped:
    print('SKIPPED', p)
for p in changed:
    print('CHANGED', p)
for p in missing:
    print('MISSING', p)
for p in added:
    print('ADDED', p)
print(f'TOTAL changed {len(changed)} missing {len(missing)} added {len(added)} skipped {len(skipped)}')
