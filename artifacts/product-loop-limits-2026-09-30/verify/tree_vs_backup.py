#!/usr/bin/env python3
"""Verifier: compare the working tree with backup/part2-2026-09-22 by git blob hash (read-only, offline, $0).

Never reads or hashes: .env / .env.* (except .env.example), audit/promotion.json, audit/final-audit*,
artifacts/heldout2/, backend/app/referee/checks.py (that one is compared only through gate_freeze).
GIT_OPTIONAL_LOCKS=0 so no git command can rewrite the index.
Output: CHANGED / MISSING / ADDED lines with the working-tree sha256 of each file.
"""
import fnmatch, hashlib, os, subprocess, sys

ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
REF = sys.argv[1] if len(sys.argv) > 1 else 'backup/part2-2026-09-22'
SKIP = ['.env', '.env.*', 'audit/promotion.json', 'audit/final-audit*', 'artifacts/heldout2/*', 'artifacts/heldout2',
        'backend/app/referee/checks.py']
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0')


def skip(path):
    if path == '.env.example' or path.endswith('/.env.example'):
        return False
    return any(fnmatch.fnmatch(path, p) for p in SKIP) or os.path.basename(path).startswith('.env')


def git(*args, inp=None):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True, input=inp, env=ENV).stdout


def sha(path):
    h = hashlib.sha256()
    with open(os.path.join(ROOT, path), 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


ref = {}
for line in git('ls-tree', '-r', REF).splitlines():
    meta, path = line.split('\t', 1)
    ref[path] = meta.split()[2]
paths = sorted(p for p in ref if not skip(p))
existing = [p for p in paths if os.path.lexists(os.path.join(ROOT, p))]
missing = [p for p in paths if not os.path.lexists(os.path.join(ROOT, p))]
hashes = git('hash-object', '--no-filters', '--stdin-paths', inp='\n'.join(existing) + '\n').split()
changed = [p for p, h in zip(existing, hashes) if h != ref[p]]
worktree = set(git('ls-files', '--cached', '--others', '--exclude-standard').splitlines())
added = sorted(p for p in worktree if p not in ref and not skip(p) and os.path.isfile(os.path.join(ROOT, p)))
print(f'REF {REF} = {git("rev-parse", REF).strip()}   HEAD = {git("rev-parse", "HEAD").strip()}')
for p in changed:
    print('CHANGED', sha(p), p)
for p in missing:
    print('MISSING', '-', p)
for p in added:
    print('ADDED', sha(p), p)
print(f'TOTAL changed {len(changed)} missing {len(missing)} added {len(added)}')
