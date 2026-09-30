#!/usr/bin/env python3
"""Integrity reviewer: compare working tree with backup/part2-2026-09-22 (by blob hash), read-only.
Skips forbidden paths (never hashed, never read): .env*, audit/promotion.json, audit/final-audit*, artifacts/heldout2/,
backend/app/referee/checks.py.  Lists tracked-in-backup files CHANGED/MISSING, and files present in the working tree
(tracked or untracked, not ignored) that are ABSENT from the backup tree."""
import subprocess, sys, os, fnmatch
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
REF = sys.argv[1] if len(sys.argv) > 1 else 'backup/part2-2026-09-22'
SKIP = ['.env', '.env.*', 'audit/promotion.json', 'audit/final-audit*', 'artifacts/heldout2/*', 'backend/app/referee/checks.py']
def skip(p):
    if p == '.env.example':
        return False
    return any(fnmatch.fnmatch(p, s) for s in SKIP) or os.path.basename(p) == '.env'
def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout
ref_blobs = {}
for line in git('ls-tree', '-r', REF).splitlines():
    meta, path = line.split('\t', 1)
    ref_blobs[path] = meta.split()[2]
changed, missing, skipped = [], [], []
paths = sorted(p for p in ref_blobs if not skip(p))
skipped = sorted(p for p in ref_blobs if skip(p))
# batch hash
existing = [p for p in paths if os.path.lexists(os.path.join(ROOT, p))]
missing = [p for p in paths if not os.path.lexists(os.path.join(ROOT, p))]
out = subprocess.run(['git', 'hash-object', '--no-filters', '--stdin-paths'], cwd=ROOT, input='\n'.join(existing) + '\n',
                     capture_output=True, text=True, check=True).stdout.split()
for p, h in zip(existing, out):
    if h != ref_blobs[p]:
        changed.append(p)
# working tree files not in ref (tracked by HEAD or untracked-not-ignored)
wt = set(git('ls-files', '--cached', '--others', '--exclude-standard').splitlines())
added = sorted(p for p in wt if p not in ref_blobs and not skip(p) and os.path.exists(os.path.join(ROOT, p)))
print(f'REF {REF} = {git("rev-parse", REF).strip()}')
for p in skipped: print('SKIPPED', p)
for p in changed: print('CHANGED', p)
for p in missing: print('MISSING', p)
for p in added: print('ADDED', p)
