"""Verifier negative controls, run ONLY in the scratch tree /Users/shree/FaultLab_Scratch/verify-citations/tree
(backup d38c0b8 plus the 17 working files). Each mutation undoes or breaks one claimed fix; the new tests must fail.
Every mutated file is restored and its sha256 checked. The working tree is never touched. $0, offline (vguard)."""
import hashlib, os, subprocess, sys
TREE = '/Users/shree/FaultLab_Scratch/verify-citations/tree'
R = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
V = R + '/artifacts/product-mechanic-citations-2026-09-30/verify'
PY = R + '/.venv/bin/python'
CK = 'scripts/experiments/check_evidence_gap_misreading_v2.py'
CS = 'backend/app/lab/citation_status.py'
TESTS = ['tests/experiments/test_check_evidence_gap_misreading_v2.py', 'tests/lab/test_citation_status.py']
MUTATIONS = [
    ('V1 LOW-4: builder null clause restored', CS,
     "'not decoded and was kept exactly as written (all three are null when no complete native adapter v2.1 citation '\n           'record was recorded for that episode).')",
     "'not decoded and was kept exactly as written (all three are null when no submitted report was recorded).')"),
    ('V2 MEDIUM-1: bare "undecoded" counts again', CK,
     "CLAIM = re.compile(CLAIM_V1 + '|' + CLAIM_V2_ADDED, re.IGNORECASE)",
     "CLAIM = re.compile(CLAIM_V1 + '|' + CLAIM_V2_ADDED + r'|undecoded', re.IGNORECASE)"),
    ('V3 MEDIUM-1: bare "not decoded" counts again', CK,
     "CLAIM = re.compile(CLAIM_V1 + '|' + CLAIM_V2_ADDED, re.IGNORECASE)",
     "CLAIM = re.compile(CLAIM_V1 + '|' + CLAIM_V2_ADDED + r'|not\\s+decoded', re.IGNORECASE)"),
    ('V4 MEDIUM-1: denial rule never matches', CK,
     'DENIAL = re.compile(r"\\b(?:no|none|nothing|neither|nor|never|not|zero|without)\\b|n\'t\\b|(?<![\\w.-])0(?![\\w.-])", re.IGNORECASE)',
     "DENIAL = re.compile(r'(?!x)x')"),
    ('V5 MEDIUM-1: clause boundaries removed (denial word anywhere before the match)', CK,
     "        for end in CLAUSE_END.finditer(text, 0, match.start()):\n            clause_start = end.end()",
     "        pass"),
    ('V6 MEDIUM-1: denied matches are counted in the verdict', CK,
     "        matched = sorted({row['phrase'] for row in counted})",
     "        matched = sorted({row['phrase'] for row in counted + denied})"),
    ('V7 MEDIUM-1: human_confirmation_required dropped', CK,
     "            'human_confirmation_required': True,", "            'human_confirmation_required': False,"),
    ('V8 LOW-1: --read-out optional (defaults to post-hoc)', CK,
     "    parser.add_argument('--read-out', required=True, choices=sorted(READ_OUT),",
     "    parser.add_argument('--read-out', default='post-hoc', choices=sorted(READ_OUT),"),
    ('V9 LOW-1: read_out_status not written', CK,
     "    result.update({'read_out_status': status, 'read_out_note': note, 'checker_sha256': _own_sha256()})",
     "    result.update({'read_out_note': note, 'checker_sha256': _own_sha256()})"),
    ('V10 LOW-1: wrong checker sha256 written (hash of the export instead)', CK,
     "    result.update({'read_out_status': status, 'read_out_note': note, 'checker_sha256': _own_sha256()})",
     "    result.update({'read_out_status': status, 'read_out_note': note, 'checker_sha256': hashlib.sha256(open(args.export, 'rb').read()).hexdigest()})"),
    ('V11 claim shape: "was/were not decoded" branch removed', CK,
     "                  r'\\b' + _AMOUNT + r'\\s+(?:cited\\s+)?' + _ITEMS + r'\\s+(?:was|were)\\s+not\\s+decoded|'\n", ""),
    ('V12 coverage probe (beyond the fixer claim): citation_row ignores the length check of decoded IDs', CS,
     "            and isinstance(undecoded, list) and len(decoded_ids) == len(cited)):",
     "            and isinstance(undecoded, list)):"),
    ('V13 coverage probe (beyond the fixer claim): "no" removed from the denial words', CK,
     'DENIAL = re.compile(r"\\b(?:no|none|', 'DENIAL = re.compile(r"\\b(?:none|'),
]


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def run_tests():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=f'{V}:{V}/spot')
    p = subprocess.run([PY, '-B', '-m', 'pytest', '-p', 'vguard', '-p', 'vstub', '-p', 'no:cacheprovider', '-q', *TESTS],
                       cwd=TREE + '/backend', capture_output=True, text=True, env=env)
    tail = [l for l in p.stdout.splitlines() if ' passed' in l or ' failed' in l or ' error' in l]
    return p.returncode, (tail[-1] if tail else p.stdout[-300:])


code, summary = run_tests()
print(f'UNMUTATED: exit {code} | {summary}')
assert code == 0, 'unmutated run must pass'
caught = 0
for name, rel, old, new in MUTATIONS:
    path = f'{TREE}/{rel}'
    before = sha(path)
    text = open(path).read()
    assert text.count(old) == 1, f'{name}: anchor not found exactly once'
    open(path, 'w').write(text.replace(old, new))
    try:
        code, summary = run_tests()
    finally:
        open(path, 'w').write(text)
    restored = sha(path) == before
    status = 'CAUGHT' if code != 0 else 'NOT CAUGHT'
    caught += code != 0
    print(f'{status:10} {name} | restored={restored} | {summary}')
    assert restored
print(f'caught {caught}/{len(MUTATIONS)}')
code, summary = run_tests()
print(f'UNMUTATED AFTER: exit {code} | {summary}')
