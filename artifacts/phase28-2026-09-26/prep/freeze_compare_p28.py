#!/usr/bin/env python3
"""Phase 28 freeze step F4: accept the new gate freeze only if exactly the declared entries moved, and moved
to exactly the reviewed values.

Compares a gate-freeze JSON against Phase 22's (artifacts/phase22-2026-09-24/gate-freeze-after.json,
sha256 8994e962...). Rule (PHASE28_EXPERIMENT.md sections 3.4 and 9 F4):
  1. The ONLY differing entries are
       files:        backend/app/lab/completion_study.py
       functions:    completion_study.py::queue_completion_study, completion_study.py::_execute
                     (whole entries: text, AST and lines)
       fingerprints: tree_lab, algorithm_hash, runtime_hash
     and each of those DOES differ; every other function, file and fingerprint entry is byte-equal as a
     whole, including 'lines'. assess_pairs, case_manifest and planned_slots are re-checked explicitly.
  2. (Review round 1.) Each of the six moved entries equals the value of the REVIEWED build, whole: the
     gate freeze of the worktree the round-1 reviewers checked (sha256 bb0b19a9..., regenerated
     independently by the backend reviewer). A value that moved anywhere else, say an edit between the
     last review and the freeze, is refused, however it moved.
  3. (Review round 1.) --new-function-hashes names the saved output of new_function_hashes.py: it must
     say ok, come from Python 3.12.8, describe the reviewed completion_study.py (file sha), and carry the
     reviewed text and AST sha of all seven new definitions.
REVIEWED and REVIEWED_NEW change only as part of a review round's fixes, and are reviewed with them. Review round 2
changed no backend file, so they are round 1's values. The output records this script's own sha256 (review round 2,
WB-4), so freeze-compare.txt shows which version accepted the freeze; landing_check_p28.py checks it at F0.
Stdlib only; JSON comparison only. Exit 0 = accepted.

Usage (from the repository root, with the venv interpreter):
  ./.venv/bin/python artifacts/phase28-<date>/prep/freeze_compare_p28.py NEW.json \\
      --new-function-hashes artifacts/phase28-<date>/new-function-hashes.json [--old OLD.json]
"""
import argparse
import hashlib
import json
import pathlib
import sys

OLD_SHA = '8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1'
CS = 'backend/app/lab/completion_study.py'
DECLARED = {('files', CS), ('functions', f'{CS}::queue_completion_study'), ('functions', f'{CS}::_execute'),
            ('fingerprints', 'tree_lab'), ('fingerprints', 'algorithm_hash'), ('fingerprints', 'runtime_hash')}
PINNED = {f'{CS}::assess_pairs': '783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2',
          f'{CS}::case_manifest': '0a5346c86561a032f26b837e5d63a2aefadfa7a43be00ad2f9539b0b2ea3e8e1',
          f'{CS}::planned_slots': '495f60fc5110326c13fcded6431d47f19c1d4117ecb4b6e3cc14f76a20dae64d'}
REVIEWED_ROUND = 'after review round 2 (the backend values are unchanged since review round 1)'
# The reviewed build (review round 1): the worktree's gate freeze, sha256
# bb0b19a9e7988884efaecec5ada22405bb520d58c16b3bdfae8c66206f6e0e8e (p30-28/p28-build/gate-freeze-worktree-final.json,
# equal to the backend reviewer's own regeneration r28-backend-review/gate-freeze-worktree-reviewer.json).
REVIEWED = {
    ('files', CS): '03e3d8bed4cbcc117ffdbb9f552f254cd33234d177e6b58254aba3f398a1b9c4',
    ('functions', f'{CS}::queue_completion_study'): {
        'ast_sha256': 'a1f3331527b9c3b75fd598298eca1480f6e38846b19e3c103c485726ce1e5583', 'lines': '150-222',
        'text_sha256': 'e6d34aecb56577922acbb650166a30ed6cdf54a4b71fd03b9b62f1b1f4275fa9'},
    ('functions', f'{CS}::_execute'): {
        'ast_sha256': '6cef98939c03386ebd670dbf920292f359f01582cc00b335301bca31c4db190d', 'lines': '225-485',
        'text_sha256': '1f0a4bf6bb25de19ae1c7c3b697db1edc634fbaaf4c065f57253db127b553fb8'},
    ('fingerprints', 'tree_lab'): 'f4305dbcd38720993b7bb9dde060a0af082d7c9fbfd3b3c6f2c053ca516645ad',
    ('fingerprints', 'algorithm_hash'): '88eb5b77b51ce53b22e5b50b6f0e355c883a25f3c741a9ef51797766d9c6ec1d',
    ('fingerprints', 'runtime_hash'): '18332ec3b3b32f4cb6aa97ea320c67ab9afb079e75c9f52af923b8981705ef51',
}
# new_function_hashes.py on the reviewed completion_study.py with Python 3.12.8 (review round 1).
REVIEWED_PYTHON = '3.12.8'
REVIEWED_NEW = {
    f'{CS}::upgrade_case_manifest': ('db52a8054061e30946756b2ce1681b6849438f605cb91b1821be29c4129e4592',
                                     'fd77006c3c04d773481bf67a5f9f0fc2ee45813a9ccc3764aa0dd86b9056ae04'),
    f'{CS}::CASE_MANIFESTS': ('196327a2b9c83951d893c65025d0c2bf0fc8dccac18a5d81954eac8ae9d26467',
                              'c1a3248afecf9b08059e49f0db483fe9a383887475f49260ebee655656ff27c3'),
    f'{CS}::DEFAULT_CASE_MANIFEST': ('5adef5e2bd7a4f930af30a27b0ee81856ef882f9f33dd39b825626201dd2d265',
                                     'a064c48ec6683fc153116089dc3e0a535e15fdff14ca9f5d78c4917b7c0ff7fa'),
    f'{CS}::build_case_manifest': ('3220e7e912dc0e9991cdc5e281d85ca460b59be72203b204e3e9ccc17fce08a5',
                                   'c5df4b7969ac77cca5f065a199e75d6c575f3bd1d23e01c599cdc26971a15ac3'),
    f'{CS}::SOURCE_CLAUSE_OUTCOMES': ('fb2a8d3622a4da6062b6a95fc42eaebf874804c60cb2a3d349149efde17a3332',
                                      '2755d2b9998c03adc7ad6cec5a643f998d41771646fe3fceae3af546eb8b25be'),
    f'{CS}::SOURCE_CLAUSE_REOPENS': ('555796149da78128f156077dd0238f6db4e29c4a4e1c96672bf345013ccf4a7e',
                                     '74874e9a5723a81f6873f2404e08a738fba1aa2f0f7e2c2307b082d00536165c'),
    f'{CS}::source_clause': ('4f3468cd4a904aa567e74201f68a9579c09f9f28e1557e32b0fb8db6ec78f4b9',
                             '51d5b4c394a788127968e5d8e6d9ce3a488775bcf1ff0852542cbf4d1402c42e'),
}


def function_hash_problems(path):
    try:
        text = pathlib.Path(path).read_text(encoding='utf-8')
        # The saved output may carry a stderr line before it or an "exit N" line after it.
        record = json.loads(text[text.index('{'):text.rindex('}') + 1])
    except (OSError, ValueError):
        return [f'--new-function-hashes {path} is missing or not new_function_hashes.py output']
    problems = []
    if record.get('ok') is not True:
        problems.append('new_function_hashes.py did not report ok')
    if record.get('python_version') != REVIEWED_PYTHON:
        problems.append(f"new_function_hashes.py ran under Python {record.get('python_version')!r}; the reviewed AST "
                        f'hashes were taken with {REVIEWED_PYTHON} (./.venv/bin/python)')
    if record.get('file_sha256') != REVIEWED[('files', CS)]:
        problems.append('new_function_hashes.py describes a completion_study.py other than the reviewed one')
    found = record.get('new') or {}
    if set(found) != set(REVIEWED_NEW):
        problems.append(f'new definitions listed {sorted(found)} are not the reviewed seven')
    for key, (text_sha, ast_sha) in REVIEWED_NEW.items():
        entry = found.get(key) or {}
        if (entry.get('text_sha256'), entry.get('ast_sha256')) != (text_sha, ast_sha):
            problems.append(f'{key} is not the reviewed definition (text/AST)')
    return problems


def main(argv=None):
    root = pathlib.Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument('new')
    parser.add_argument('--old', default=str(root / 'artifacts/phase22-2026-09-24/gate-freeze-after.json'))
    parser.add_argument('--new-function-hashes', required=True,
                        help="the saved output of new_function_hashes.py (run with ./.venv/bin/python)")
    args = parser.parse_args(argv)
    old_bytes = pathlib.Path(args.old).read_bytes()
    old, new = json.loads(old_bytes), json.loads(pathlib.Path(args.new).read_text())
    problems = []
    if hashlib.sha256(old_bytes).hexdigest() != OLD_SHA:
        problems.append('the comparison freeze is not the Phase 22 freeze (8994e962...)')
    if old.get('schema_version') != new.get('schema_version'):
        problems.append('schema_version differs')
    if set(new) != set(old):
        problems.append(f'top-level keys differ: {sorted(set(new) ^ set(old))}')
    moved = set()
    for section in ('functions', 'files', 'fingerprints'):
        a, b = old.get(section) or {}, new.get(section) or {}
        if set(a) != set(b):
            problems.append(f'{section}: keys differ {sorted(set(a) ^ set(b))}')
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                moved.add((section, key))
    undeclared = sorted(moved - DECLARED)
    unmoved = sorted(DECLARED - moved)
    if undeclared:
        problems.append(f'undeclared entries moved: {undeclared}')
    if unmoved:
        problems.append(f'declared entries did not move: {unmoved}')
    for key, text in PINNED.items():
        if (new.get('functions') or {}).get(key) != (old.get('functions') or {}).get(key) or \
                (new.get('functions') or {}).get(key, {}).get('text_sha256') != text:
            problems.append(f'{key} is not the unchanged entry')
    for (section, key), value in sorted(REVIEWED.items()):
        if (new.get(section) or {}).get(key) != value:
            problems.append(f'{section}:{key} is not the reviewed value')
    problems += function_hash_problems(args.new_function_hashes)
    print(json.dumps({'moved': [f'{s}:{k}' for s, k in sorted(moved)], 'problems': problems,
                      'script_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
                      'reviewed': REVIEWED_ROUND, 'accepted': not problems}, indent=1))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
