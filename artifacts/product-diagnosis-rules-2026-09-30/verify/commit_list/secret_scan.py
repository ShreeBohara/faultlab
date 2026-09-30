"""Independent verifier (copied unchanged from the fireability verifier, which copied it from the citation-status verifier, which copied it from the loop-limits and native v2b verifiers): credential-pattern scan of every file named in a commit-list output
('<sha256>  <path>' lines). Prints per-file hit counts and, for each hit, the pattern name and a MASKED excerpt
(the matched value is cut to its first 6 characters). Never opens .env or a protected path (the list holds none)."""
import re, sys
from pathlib import Path
ROOT = Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab')
PATTERNS = {
    'wandb_key_assignment': re.compile(r'WANDB_API_KEY\s*[=:]\s*["\']?([A-Za-z0-9_\-]{12,})'),
    'wandb_v1_token': re.compile(r'(wandb_v1_[A-Za-z0-9_\-]{10,})'),
    'sk_token': re.compile(r'\b(sk-[A-Za-z0-9_\-]{16,})'),
    'hf_token': re.compile(r'\b(hf_[A-Za-z0-9]{20,})'),
    'bearer': re.compile(r'Bearer\s+([A-Za-z0-9_\-\.=]{16,})'),
    'private_key': re.compile(r'(-----BEGIN [A-Z ]*PRIVATE KEY-----)'),
    'github_token': re.compile(r'\b(gh[pousr]_[A-Za-z0-9]{20,})'),
    'aws_key': re.compile(r'\b(AKIA[0-9A-Z]{16})\b'),
    'api_key_literal': re.compile(r'api_key\s*[=:]\s*["\']([^"\']{16,})["\']', re.I),
}
lst = sys.argv[1]
hits = {}
for line in open(lst):
    sha, path = line.rstrip('\n').split('  ', 1)
    if sha == '(deleted)':
        continue
    p = ROOT / path
    base = p.name
    if base == '.env' or (base.startswith('.env') and base != '.env.example'):
        raise SystemExit('refusing env path ' + path)
    try:
        text = p.read_bytes().decode('utf-8', errors='replace')
    except OSError as error:
        print('UNREADABLE', path, error); continue
    for name, rx in PATTERNS.items():
        for m in rx.finditer(text):
            value = m.group(1)
            start = max(0, m.start() - 30)
            ctx = text[start:m.start(1)] + value[:6] + '...'
            hits.setdefault(path, []).append((name, ctx.replace('\n', ' ')[-70:]))
print('files scanned:', sum(1 for _ in open(lst)))
print('files with a hit:', len(hits))
for path, rows in sorted(hits.items()):
    print(f'{path}: {len(rows)}')
    for name, ctx in rows[:3]:
        print(f'   {name}: ...{ctx}')
