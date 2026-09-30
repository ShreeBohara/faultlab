#!/usr/bin/env python3
"""Integrity review: independent compare of the working tree with backup/part2-2026-09-22 (read-only, $0).
Walks the filesystem (so ignored files in source dirs are seen too), skipping forbidden paths and caches.
Never reads .env*, audit/promotion.json, audit/final-audit*, artifacts/heldout2/, backend/app/referee/checks.py.
"""
import fnmatch, os, subprocess, sys
ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
REF = 'backup/part2-2026-09-22'
SKIP_FILES = ['audit/promotion.json', 'audit/final-audit*', 'backend/app/referee/checks.py']
PRUNE_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'dist', '.results', 'artifacts'}
def skip(p):
    b = os.path.basename(p)
    if b.startswith('.env') and b != '.env.example':
        return True
    return any(fnmatch.fnmatch(p, s) for s in SKIP_FILES)
def git(*a, inp=None):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True, check=True, input=inp).stdout
ref = {}
for line in git('ls-tree', '-r', REF).splitlines():
    meta, path = line.split('\t', 1)
    ref[path] = meta.split()[2]
fs = []
for d, dirs, files in os.walk(ROOT):
    rel = os.path.relpath(d, ROOT)
    dirs[:] = [x for x in dirs if x not in PRUNE_DIRS]
    for f in files:
        p = os.path.normpath(os.path.join(rel, f)) if rel != '.' else f
        if skip(p) or f.endswith(('.pyc', '.sqlite3', '.db')) or f == '.DS_Store':
            continue
        fs.append(p)
fsset = set(fs)
tracked_ref = [p for p in ref if not skip(p) and not p.startswith('artifacts/')]
existing = [p for p in tracked_ref if p in fsset]
missing = sorted(p for p in tracked_ref if p not in fsset and not os.path.lexists(os.path.join(ROOT, p)))
hs = git('hash-object', '--no-filters', '--stdin-paths', inp='\n'.join(existing) + '\n').split()
changed = sorted(p for p, h in zip(existing, hs) if h != ref[p])
added = sorted(p for p in fsset if p not in ref)
print('REF', REF, git('rev-parse', REF).strip(), 'HEAD', git('rev-parse', 'HEAD').strip(), 'branch', git('branch', '--show-current').strip())
for p in changed: print('CHANGED', p)
for p in missing: print('MISSING', p)
for p in added: print('ADDED', p)
print('TOTAL changed', len(changed), 'missing', len(missing), 'added(untracked-in-ref, incl. ignored, excl. artifacts/caches/dist)', len(added))
