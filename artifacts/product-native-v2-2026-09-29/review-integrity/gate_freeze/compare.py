"""Compare gate_freeze output: checkpoint backup/part2-2026-09-22 (extracted with git archive) vs current working tree.
checks.py is hashed/AST-parsed by gate_freeze itself; its content is never displayed."""
import json
ck = json.load(open('checkpoint.json')); cur = json.load(open('current.json'))
def flat(d, pre=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flat(v, pre + k + '/'))
        else: out[pre + k] = v
    return out
a, b = flat(ck), flat(cur)
diff = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
print('gate_freeze differences, checkpoint backup/part2-2026-09-22 -> working tree:', len(diff))
for k in diff: print(' ', k, str(a.get(k))[:16], '->', str(b.get(k))[:16])
ap = 'backend/app/lab/completion_study.py::assess_pairs'; ckp = 'backend/app/referee/checks.py'
print('scorer_hash equal:', cur['fingerprints']['scorer_hash'] == ck['fingerprints']['scorer_hash'], cur['fingerprints']['scorer_hash'][:16])
print('checks.py file hash equal:', cur['files'][ckp] == ck['files'][ckp])
print('checks.py::score, ::scorer_hash equal:', all(cur['functions'][f'{ckp}::{n}'] == ck['functions'][f'{ckp}::{n}'] for n in ('score','scorer_hash')))
print('assess_pairs text equal:', cur['functions'][ap]['text_sha256'] == ck['functions'][ap]['text_sha256'], 'ast equal:', cur['functions'][ap]['ast_sha256'] == ck['functions'][ap]['ast_sha256'], 'text sha', cur['functions'][ap]['text_sha256'][:40])
same = [k for k in cur['functions'] if cur['functions'][k] == ck['functions'].get(k)]
print('functions identical (text, ast, lines):', len(same), 'of', len(cur['functions']))
print('files identical:', sum(cur['files'][k] == ck['files'][k] for k in cur['files']), 'of', len(cur['files']), '(audit/promotion.json, audit/final-audit.json dropped, never read)')
f = cur['fingerprints']
print('current: service', f['service_hash'][:8], 'contract', f['contract_hash'][:8], 'interpreter', f['interpreter_hash'][:8], 'runtime', f['runtime_hash'][:8], 'algorithm', f['algorithm_hash'][:8])
f = ck['fingerprints']
print('checkpoint: service', f['service_hash'][:8], 'contract', f['contract_hash'][:8], 'interpreter', f['interpreter_hash'][:8], 'runtime', f['runtime_hash'][:8], 'algorithm', f['algorithm_hash'][:8])
