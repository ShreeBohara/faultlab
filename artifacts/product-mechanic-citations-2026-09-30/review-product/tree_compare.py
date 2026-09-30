"""Reviewer's independent tree compare: working tree vs backup d38c0b8 (git ls-tree + hash-object).
Skips forbidden files without opening them."""
import subprocess, os, sys
ROOT = "/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab"
REF = "d38c0b8dd0ca2d1b76f487cd3a19f13e6216adf3"
SKIP_PREFIX = ("artifacts/", "audit/final-audit", ".env")
SKIP_EXACT = {"backend/app/referee/checks.py", "audit/promotion.json"}
def run(*a):
    return subprocess.run(a, cwd=ROOT, check=True, capture_output=True, text=True).stdout
ref = {}
for line in run("git", "ls-tree", "-r", REF).splitlines():
    meta, path = line.split("\t", 1)
    ref[path] = meta.split()[2]
# tracked+untracked (excluding ignored)
files = set(run("git", "ls-files", "-co", "--exclude-standard").splitlines())
def skip(p):
    return p in SKIP_EXACT or p.startswith(SKIP_PREFIX) or os.path.basename(p).startswith(".env")
changed, added, missing, skipped = [], [], [], []
paths = sorted(set(ref) | files)
to_hash = [p for p in paths if p in files and not skip(p) and os.path.isfile(os.path.join(ROOT, p))]
hashes = {}
chunk = 500
for i in range(0, len(to_hash), chunk):
    part = to_hash[i:i+chunk]
    out = run("git", "hash-object", "--", *part).splitlines()
    hashes.update(dict(zip(part, out)))
for p in paths:
    if skip(p):
        skipped.append(p); continue
    if p in ref and p not in hashes:
        if not os.path.exists(os.path.join(ROOT, p)):
            missing.append(p)
        continue
    if p not in ref:
        added.append(p); continue
    if hashes[p] != ref[p]:
        changed.append(p)
for p in changed: print("CHANGED", p)
for p in added: print("ADDED", p)
for p in missing: print("MISSING", p)
print("TOTAL changed", len(changed), "added", len(added), "missing", len(missing), "skipped(not opened)", len(skipped))
