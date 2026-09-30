"""Verifier-2 (diagnosis rules + follow-up, 2026-09-30; copied from verify/commit_list/commit_list.py, changes marked V2): exact list of files that differ from the tip of
backup/part2-2026-09-22 (626bae4), by raw bytes. Copied from artifacts/product-fireability-2026-09-30/verify/
commit_list/commit_list.py with only TIP, EVID and this docstring changed. This round's checkpoint and scratch trees live
OUTSIDE the Desktop (/Users/shree/FaultLab_Scratch/verify-diagnosis-rules).

Method (the real .git/index is never written; GIT_OPTIONAL_LOCKS=0):
  * every path tracked in the tip: its blob bytes (git cat-file --batch) are compared with the working file bytes and
    executable bit; a missing working file is DELETED;
  * every working file git would offer for a commit (not ignored; `git ls-files --cached --others --exclude-standard`
    against a throwaway index built from the tip) that is not in the tip is NEW;
  * PLUS the git-ignored evidence folder artifacts/product-native-v2b-2026-09-30/ (it must be force-added), walked
    directly, with these exclusions (listed in COMMIT_LIST_NOTES.txt): caches (__pycache__, *.pyc, .pytest_cache,
    .DS_Store), scratch SQLite worlds written by probes (*.sqlite3, *.db, *-wal, *-shm), any file over 5 MB,
    review-integrity/checkpoint-tree/ and verify/checkpoint/tree/ (`git archive` copies of the checkpoint commit: already
    in git history and they hold a copy of the protected checks.py), and verify/COMMIT_LIST.txt and verify/COMMIT_LIST.json (the list and its detail cannot contain their own hashes).
  * .env (any name starting with .env except .env.example) is never opened; protected paths
    (backend/app/referee/checks.py, audit/promotion.json, final-audit*, heldout2/) are never read by this script.
    REVISION 2 (v2b verifier, after pass 1): the copied script let `git hash-object` hash the protected paths; that is
    removed. Now only their size and mtime are recorded (protected_not_read in the .json); checks.py equality comes
    from gate_freeze (the repo's own code), and the audit JSONs are not compared by content at all.
Output: '<sha256>  <path>' lines sorted by path (sha256 of working bytes), plus <out>.json with status per path.
"""
import hashlib, json, os, subprocess, sys
ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
TIP = '626bae4afba9e160397e3f55b0ce9f5663e48d48'
EVID = 'artifacts/product-diagnosis-rules-2026-09-30'
IDX, OUT = sys.argv[1], sys.argv[2]
MAX = 5 * 1024 * 1024

def git(*a, env=None, inp=None):
    return subprocess.run(['git', '-C', ROOT, *a], capture_output=True, check=True, env=env, input=inp).stdout

def protected(p):
    return (p == 'backend/app/referee/checks.py' or p.endswith('/checks.py') and '/referee/' in p
            or p.endswith('audit/promotion.json') or 'final-audit' in p or 'heldout2/' in p)

def is_env(p):
    b = os.path.basename(p)
    return (b == '.env' or b.startswith('.env.') or b.endswith('.env')) and b != '.env.example'

env = dict(os.environ, GIT_INDEX_FILE=IDX, GIT_OPTIONAL_LOCKS='0')
if os.path.exists(IDX):
    os.remove(IDX)
git('read-tree', TIP, env=env)
tip = {}
for line in git('ls-tree', '-r', '-z', TIP).split(b'\0'):
    if line:
        meta, path = line.split(b'\t', 1)
        mode, typ, oid = meta.split()
        tip[path.decode()] = (mode.decode(), typ.decode(), oid.decode())
cands = set(p.decode() for p in git('ls-files', '-z', '--cached', '--others', '--exclude-standard', env=env).split(b'\0') if p)
os.remove(IDX)
excluded = []
for dp, dns, fns in os.walk(os.path.join(ROOT, EVID)):
    rel_dir = os.path.relpath(dp, ROOT)
    keep = []
    for d in dns:
        rd = os.path.join(rel_dir, d)
        if d in ('__pycache__', '.pytest_cache', 'node_modules', '.venv', 'dist'):  # V2: + dist
            excluded.append((rd + '/', 'directory: cache'))
        elif os.path.exists(os.path.join(ROOT, rd, 'backend', 'app', 'referee')):
            excluded.append((rd + '/', 'directory: a tree copy that holds a copy of the protected referee (never listed)'))
        else:
            keep.append(d)
    dns[:] = keep
    for f in fns:
        rp = os.path.join(rel_dir, f)
        full = os.path.join(ROOT, rp)
        if protected(rp) or is_env(rp):
            excluded.append((rp, 'protected or env name, never read')); continue
        if os.path.islink(full):  # V2: symlinks are never followed or listed
            excluded.append((rp, 'symlink, not listed')); continue
        if f == 'checks.py':  # V2: any checks.py copy, wherever it sits, is never read or listed
            excluded.append((rp, 'a checks.py copy, never read')); continue
        if f == '.DS_Store' or f.endswith('.pyc'):
            excluded.append((rp, 'cache')); continue
        if f.endswith(('.sqlite3', '.sqlite', '.db', '-wal', '-shm', '.sqlite3-journal')):
            excluded.append((rp, 'scratch SQLite written by a probe')); continue
        if rp in (EVID + '/verify-2/COMMIT_LIST.txt', EVID + '/verify-2/COMMIT_LIST.json'):  # V2: this stage's list
            excluded.append((rp, 'the list itself (and its per-path detail); a file cannot contain its own hash')); continue
        if os.path.getsize(full) > MAX:
            excluded.append((rp, 'over 5 MB (%d bytes)' % os.path.getsize(full))); continue
        cands.add(rp)
paths = sorted(set(tip) | cands)
oids = [tip[p][2] for p in paths if p in tip and tip[p][1] == 'blob' and not protected(p) and not is_env(p)]
proc = subprocess.run(['git', '-C', ROOT, 'cat-file', '--batch'], input=('\n'.join(oids) + '\n').encode(), capture_output=True, check=True)
buf = proc.stdout; blobs = {}; i = 0
while i < len(buf):
    nl = buf.index(b'\n', i); hdr = buf[i:nl].split(); oid, size = hdr[0].decode(), int(hdr[2])
    blobs[oid] = buf[nl + 1: nl + 1 + size]; i = nl + 1 + size + 1
result = {}
not_read = []
for p in paths:
    full = os.path.join(ROOT, p)
    if is_env(p):
        raise SystemExit('refusing env-named path ' + p)
    if protected(p):
        # Revision 2 (after pass 1): protected paths are never read or hashed here, not even by git. Only their
        # metadata (existence, size, mtime) is recorded; checks.py equality is established by gate_freeze instead.
        st = os.lstat(full) if os.path.lexists(full) else None
        not_read.append({'path': p, 'in_tip': p in tip, 'exists': st is not None,
                         'size': st.st_size if st else None, 'mtime_utc': __import__('time').strftime('%Y-%m-%dT%H:%M:%SZ', __import__('time').gmtime(st.st_mtime)) if st else None})
        if p in tip and st is None:
            result[p] = {'status': 'DELETED'}
        continue
    if p in tip:
        mode, typ, oid = tip[p]
        if typ != 'blob':
            result[p] = {'status': 'NON_BLOB_' + typ}; continue
        if not os.path.lexists(full):
            result[p] = {'status': 'DELETED', 'tip_sha256': hashlib.sha256(blobs[oid]).hexdigest()}; continue
        data = open(full, 'rb').read() if not os.path.islink(full) else os.readlink(full).encode()
        exe_now = os.access(full, os.X_OK) and not os.path.islink(full)
        if data != blobs[oid]:
            result[p] = {'status': 'MODIFIED', 'sha256': hashlib.sha256(data).hexdigest(), 'tip_sha256': hashlib.sha256(blobs[oid]).hexdigest()}
        elif exe_now != (mode == '100755'):
            result[p] = {'status': 'MODE_CHANGED', 'sha256': hashlib.sha256(data).hexdigest(), 'tip_mode': mode}
    else:
        data = open(full, 'rb').read()
        ignored = subprocess.run(['git', '-C', ROOT, 'check-ignore', '-q', '--', p]).returncode == 0
        result[p] = {'status': 'NEW', 'sha256': hashlib.sha256(data).hexdigest(), 'mode': oct(os.stat(full).st_mode & 0o777),
                     'ignored_needs_force_add': ignored, 'size': len(data)}
json.dump({'tip': TIP, 'tip_files': len(tip), 'candidates_checked': len(paths), 'differences': result, 'protected_not_read': not_read,
           'excluded_evidence': excluded}, open(OUT + '.json', 'w'), indent=1, sort_keys=True)
with open(OUT, 'w') as fh:
    for p in sorted(result):
        fh.write(f"{result[p].get('sha256', '(deleted)')}  {p}\n")
counts = {}
for p, r in result.items():
    k = r['status'] + ('_evidence' if p.startswith(EVID + '/') else '')
    counts[k] = counts.get(k, 0) + 1
print('tip files', len(tip), 'paths checked', len(paths), 'differences', len(result), counts, 'excluded evidence entries', len(excluded))
