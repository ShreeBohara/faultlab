"""Fixer negative-control mutations ($0, offline): each one undoes one fixer change (review findings MEDIUM-1, LOW-1,
LOW-4); the tests must fail on it. Every file is restored and its sha256 checked after each mutation. The tests run with
the suite's own conftest (network refused, the real .env refused).

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/fixer/mutation_checks.py
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path.cwd()
PY = str(BACKEND.parent / '.venv/bin/python')
CHECKER = '../scripts/experiments/check_evidence_gap_misreading_v2.py'
CHECKER_TESTS = ['tests/experiments/test_check_evidence_gap_misreading_v2.py']
CITATION_TESTS = ['tests/lab/test_citation_status.py']

MUTATIONS = [
    ('F1 MEDIUM-1: bare "undecoded" counts again', CHECKER,
     "CLAIM_V2_ADDED = (r'never\\s+(?:been\\s+)?shown|", "CLAIM_V2_ADDED = (r'undecoded|never\\s+(?:been\\s+)?shown|", CHECKER_TESTS),
    ('F2 MEDIUM-1: bare "not decoded" counts again', CHECKER,
     "CLAIM_V2_ADDED = (r'never\\s+(?:been\\s+)?shown|", "CLAIM_V2_ADDED = (r'not\\s+(?:been\\s+)?decoded|never\\s+(?:been\\s+)?shown|", CHECKER_TESTS),
    ('F3 MEDIUM-1: denial rule off', CHECKER,
     "        denial = DENIAL.search(text[clause_start:match.start()])", "        denial = None", CHECKER_TESTS),
    ('F4 MEDIUM-1: denial rule reads the whole text before the match (no clause boundary)', CHECKER,
     "            clause_start = end.end()\n", "            clause_start = 0\n", CHECKER_TESTS),
    ('F5 MEDIUM-1: a count of 0 is a claim amount', CHECKER,
     "_AMOUNT = r'(?:[1-9]\\d*|", "_AMOUNT = r'(?:\\d+|", CHECKER_TESTS),
    ('F6 MEDIUM-1: "no" is not a denial word', CHECKER,
     'DENIAL = re.compile(r"\\b(?:no|none|', 'DENIAL = re.compile(r"\\b(?:none|', CHECKER_TESTS),
    ('F7 MEDIUM-1: the verdict counts denied matches too', CHECKER,
     "        matched = sorted({row['phrase'] for row in counted})",
     "        matched = sorted({row['phrase'] for row in counted + denied})", CHECKER_TESTS),
    ('F8 MEDIUM-1 (human check): matches not reported with their sentences', CHECKER,
     "                        'claim_matches': counted, 'denied_matches': denied, 'hypotheses': texts,",
     "                        'hypotheses': texts,", CHECKER_TESTS),
    ('F9 LOW-1: an output without a read-out status is allowed', CHECKER,
     "    parser.add_argument('--read-out', required=True, choices=sorted(READ_OUT),",
     "    parser.add_argument('--read-out', default='post-hoc', choices=sorted(READ_OUT),", CHECKER_TESTS),
    ('F10 LOW-1: the read-out status and sha256 are not written into the output', CHECKER,
     "    result.update({'read_out_status': status, 'read_out_note': note, 'checker_sha256': _own_sha256()})",
     "    pass", CHECKER_TESTS),
    ('F11 LOW-4: the null clause says "no submitted report was recorded" again', 'app/lab/citation_status.py',
     "(all three are null when no complete native adapter v2.1 citation '\n           'record was recorded for that episode).')",
     "(all three are null when no submitted report was recorded).')", CITATION_TESTS),
]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    caught = 0
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    for name, rel, old, new, tests in MUTATIONS:
        path = (BACKEND / rel).resolve()
        original = path.read_bytes(); before = sha(path)
        text = original.decode()
        if text.count(old) != 1:
            print(f'{name}: MUTATION TEXT NOT FOUND EXACTLY ONCE ({text.count(old)})'); sys.exit(2)
        path.write_text(text.replace(old, new))
        try:
            result = subprocess.run([PY, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *tests], cwd=BACKEND, env=env,
                                    capture_output=True, text=True, timeout=900)
        finally:
            path.write_bytes(original)
        restored = sha(path) == before
        failed = result.returncode != 0
        caught += failed
        last = [line for line in result.stdout.splitlines() if line.strip()][-1:] or ['']
        failures = [line.split(' - ')[0] for line in result.stdout.splitlines() if line.startswith('FAILED')]
        print(f'{"CAUGHT " if failed else "MISSED "} {name} | restored={restored} | {last[0]}')
        for line in failures[:4]: print(f'           {line}')
        if len(failures) > 4: print(f'           ... and {len(failures) - 4} more')
        if not restored: sys.exit(3)
    print(f'caught {caught}/{len(MUTATIONS)}')
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == '__main__':
    sys.exit(main())
