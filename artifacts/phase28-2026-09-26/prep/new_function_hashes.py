#!/usr/bin/env python3
"""Phase 28 freeze step F4: supplementary text/AST hashes of the new completion_study.py definitions.

gate_freeze.py (pinned, 5e21c0ec...) cannot list them, so they are recorded here by its method:
text_sha256 = sha256(ast.get_source_segment(src, node) + '\\n'), ast_sha256 = sha256(ast.dump(node)).
The seven are the four the design names (upgrade_case_manifest, the CASE_MANIFESTS assignment,
build_case_manifest, source_clause) and, since review round 1, the three module constants they read
(DEFAULT_CASE_MANIFEST, SOURCE_CLAUSE_OUTCOMES, SOURCE_CLAUSE_REOPENS). Also re-checks the three functions
declared unchanged (text sha and line range). Stdlib only.

ast.dump changes with the Python version (review round 1: 3.9.6 and 3.12.8 give different AST shas for the
same file), so the output records the interpreter, and the script refuses (exit 1) under any Python other
than the venv's 3.12.8, the interpreter the runner and gate_freeze.py run under. Exit 0 only if all seven
are found, the three are unchanged and the interpreter is 3.12.8. The output records this script's own sha256
(review round 2), so the saved record shows which version took the hashes.

Usage (from the repository root, with the venv interpreter, never /usr/bin/python3):
  ./.venv/bin/python artifacts/phase28-<date>/prep/new_function_hashes.py [--root DIR]
"""
import argparse
import ast
import hashlib
import json
import pathlib
import platform
import sys

FILE = 'backend/app/lab/completion_study.py'
NEW = ('upgrade_case_manifest', 'CASE_MANIFESTS', 'DEFAULT_CASE_MANIFEST', 'build_case_manifest',
       'SOURCE_CLAUSE_OUTCOMES', 'SOURCE_CLAUSE_REOPENS', 'source_clause')
UNCHANGED = {'assess_pairs': ('783e8e58f91992f36066a2c6a152c4fbd242bd7e3966320b18ce45d525074aa2', '106-147'),
             'case_manifest': ('0a5346c86561a032f26b837e5d63a2aefadfa7a43be00ad2f9539b0b2ea3e8e1', '43-83'),
             'planned_slots': ('495f60fc5110326c13fcded6431d47f19c1d4117ecb4b6e3cc14f76a20dae64d', '86-103')}
PYTHON = '3.12.8'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(pathlib.Path(__file__).resolve().parents[3]))
    root = pathlib.Path(parser.parse_args(argv).root)
    source = (root / FILE).read_text(encoding='utf-8')
    found = {}
    for node in ast.parse(source).body:
        names = [node.name] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else [
            t.id for t in getattr(node, 'targets', []) if isinstance(t, ast.Name)]
        segment = ast.get_source_segment(source, node)
        for name in names:
            found[name] = {'text_sha256': hashlib.sha256((segment + '\n').encode('utf-8')).hexdigest(),
                           'ast_sha256': hashlib.sha256(ast.dump(node).encode('utf-8')).hexdigest(),
                           'lines': f'{node.lineno}-{node.end_lineno}'}
    new = {f'{FILE}::{name}': found.get(name, {'missing': True}) for name in NEW}
    unchanged = {name: {'expected': list(value), 'found': [found.get(name, {}).get('text_sha256'),
                                                           found.get(name, {}).get('lines')]}
                 for name, value in UNCHANGED.items()}
    interpreter_ok = platform.python_version() == PYTHON
    ok = (all('missing' not in v for v in new.values()) and all(v['expected'] == v['found'] for v in unchanged.values())
          and interpreter_ok)
    print(json.dumps({'file_sha256': hashlib.sha256((root / FILE).read_bytes()).hexdigest(), 'new': new,
                      'script_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
                      'unchanged': unchanged, 'python_version': platform.python_version(), 'python_build': sys.version,
                      'python_required': PYTHON, 'ok': ok}, indent=1, sort_keys=True))
    if not interpreter_ok:
        print(f'refused: Python {platform.python_version()}; the AST hashes are taken with {PYTHON} '
              f'(./.venv/bin/python)', file=sys.stderr)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
