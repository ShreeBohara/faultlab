"""Verifier: compare the source text and ast.dump of the gate-frozen diagnosis functions (summarize_evidence,
trial_outcomes) and classify_policy_gap between the backup checkpoint and the working tree. Parses files; imports nothing."""
import ast, hashlib, sys
sys.path.insert(0, '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/verify')
import vguard  # noqa: F401
TREES = {'backup': '/Users/shree/FaultLab_Scratch/verify-citations/checkpoint', 'work': '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'}
WANT = {'backend/app/lab/diagnosis.py': ['summarize_evidence', 'trial_outcomes'], }
import subprocess
hits = subprocess.run(['grep', '-rl', 'def classify_policy_gap', TREES['work'] + '/backend/app'], capture_output=True, text=True).stdout.split()
for h in hits:
    WANT.setdefault(h.replace(TREES['work'] + '/', ''), []).append('classify_policy_gap')
for rel, names in WANT.items():
    for name in names:
        res = {}
        for label, root in TREES.items():
            src = open(f'{root}/{rel}').read()
            tree = ast.parse(src)
            node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
            text = ast.get_source_segment(src, node)
            res[label] = (hashlib.sha256(text.encode()).hexdigest(), hashlib.sha256(ast.dump(node).encode()).hexdigest())
        same = res['backup'] == res['work']
        print(f"{'SAME' if same else 'DIFFERENT'} {rel}::{name} text {res['work'][0][:16]} ast {res['work'][1][:16]} (backup text {res['backup'][0][:16]} ast {res['backup'][1][:16]})")
