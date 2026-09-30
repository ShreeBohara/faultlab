"""Read-only fingerprint of the acceptance gate and everything it depends on.

Stdlib only; never imports the app, never opens .env, never touches the store.
Run it before and after a change and diff the two JSON files: every value not
declared as changing must be byte-identical.

  function text_sha256 = sha256(ast.get_source_segment(src, node) + '\\n')
      (reproduces Phase 15's recorded assess_pairs value 783e8e58..., which was
       this hash truncated to 40 hex characters; the full 64 are stored here)
  function ast_sha256  = sha256(ast.dump(node))  (ignores comments and layout)
  file sha256          = sha256(file bytes)
  config fingerprints  = mirror of backend/app/lab/configuration.py

Usage: python scripts/experiments/gate_freeze.py [--root DIR] > out.json
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

# The gate (assess_pairs), what it calls, what builds its inputs, what the
# Mechanic reads, and what judges each episode. 'Class.method' is allowed.
FUNCTIONS = {
    'backend/app/lab/completion_study.py': [
        'assess_pairs', 'case_manifest', 'planned_slots', 'queue_completion_study', '_execute'],
    'backend/app/lab/reproduction.py': ['valid_trial'],
    'backend/app/lab/baseline_study.py': ['summarize'],
    'backend/app/lab/evaluation.py': ['aggregate_usage', 'paired_complete'],
    'backend/app/lab/promotion.py': ['promotion_decision', 'commit_promotion'],
    'backend/app/lab/runner.py': ['EpisodeRunner.run'],
    'backend/app/lab/evidence.py': ['EvidenceGateway.authorize', 'EvidenceGateway.get', 'EvidenceGateway.retry'],
    'backend/app/lab/diagnosis.py': ['runtime_contract', 'trial_outcomes', 'summarize_evidence'],
    'backend/app/agents/mechanic.py': ['Mechanic'],
    'backend/app/contracts/models.py': [
        'canonical_json', 'content_hash', 'TrialResult', 'Usage', 'PolicyVersion', 'EvidenceBundle'],
    'backend/app/referee/checks.py': ['score', 'scorer_hash'],
    'backend/app/referee/manifests.py': ['load_manifest', 'manifest_hash'],
    'backend/app/telemetry/worker.py': ['WeaveWorker'],
}
FILES = [
    'backend/app/lab/completion_study.py', 'backend/app/lab/reproduction.py',
    'backend/app/lab/baseline_study.py', 'backend/app/lab/evaluation.py',
    'backend/app/lab/promotion.py', 'backend/app/lab/runner.py', 'backend/app/lab/evidence.py',
    'backend/app/lab/diagnosis.py', 'backend/app/lab/policies.py',
    'backend/app/agents/mechanic.py', 'backend/app/agents/actor.py', 'backend/app/agents/progress.py',
    'backend/app/agents/prompts/completion.md', 'backend/app/agents/prompts/actor.md',
    'backend/app/referee/checks.py', 'backend/app/referee/manifests.py',
    'backend/app/telemetry/weave_reader.py', 'backend/app/telemetry/worker.py',
    'backend/app/telemetry/tracing.py',
    'audit/development.json', 'audit/promotion.json', 'audit/final-audit.json',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def content_hash(value):
    return sha(canonical_json(value).encode('utf-8'))


def file_hash(path):
    return sha(Path(path).read_bytes())


def tree_hash(path):
    path = Path(path)
    return content_hash({str(p.relative_to(path)): file_hash(p) for p in sorted(path.rglob('*'))
                         if p.is_file() and p.suffix in ('.py', '.md') and '__pycache__' not in str(p)})


def find(tree, dotted):
    body = tree.body
    node = None
    for part in dotted.split('.'):
        node = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and n.name == part), None)
        if node is None:
            return None
        body = node.body
    return node


def fingerprints(root):
    app = root / 'backend/app'
    service = tree_hash(app / 'simulator')
    locks = [root / 'requirements.txt', root / 'backend/requirements.txt',
             root / 'requirements.lock', root / 'backend/requirements.lock']
    return {
        'algorithm_hash': content_hash({n: tree_hash(app / n) for n in ('lab', 'referee')}),
        'runtime_hash': tree_hash(app),
        'adapter_hash': tree_hash(app / 'adapters'),
        'source_hash': tree_hash(app / 'agents'),
        'scorer_hash': file_hash(app / 'referee/checks.py'),
        'interpreter_hash': content_hash({n: file_hash(app / 'lab' / n)
                                          for n in ('policy_interpreter.py', 'policy_state.py', 'budgets.py')}),
        'service_hash': service,
        'contract_hash': content_hash({'schemas': {p.name: file_hash(p) for p in sorted((root / 'contracts').glob('*.schema.json'))},
                                       'service_hash': service}),
        'dependency_lock_hash': content_hash({str(p.relative_to(root)): file_hash(p) for p in locks if p.exists()}),
        'actor_prompt_hash': content_hash((app / 'agents/prompts/actor.md').read_text()),
        'tree_lab': tree_hash(app / 'lab'),
        'tree_referee': tree_hash(app / 'referee'),
        'tree_telemetry': tree_hash(app / 'telemetry'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[2]))
    root = Path(parser.parse_args().root)
    out = {'schema_version': 'faultlab-gate-freeze/v1', 'functions': {}, 'files': {},
           'fingerprints': fingerprints(root)}
    for rel, names in FUNCTIONS.items():
        src = (root / rel).read_text(encoding='utf-8')
        tree = ast.parse(src)
        for name in names:
            node = find(tree, name)
            key = f'{rel}::{name}'
            if node is None:
                out['functions'][key] = {'missing': True}
                continue
            segment = ast.get_source_segment(src, node)
            out['functions'][key] = {
                'text_sha256': sha((segment + '\n').encode('utf-8')),
                'ast_sha256': sha(ast.dump(node).encode('utf-8')),
                'lines': f'{node.lineno}-{node.end_lineno}'}
    for rel in FILES:
        out['files'][rel] = file_hash(root / rel)
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
