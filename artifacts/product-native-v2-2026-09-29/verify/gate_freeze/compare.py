"""Compare gate_freeze output: checkpoint fca3502 (git archive copy) vs current working tree, plus earlier records."""
import json
cur = json.load(open('current.json')); tip = json.load(open('checkpoint.json'))
p28 = json.load(open('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/phase28-2026-09-26/gate-freeze-after.json'))
dep = json.load(open('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-dependability-2026-09-29/verify/gate_freeze/current.json'))
def flat(d, pre=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flat(v, pre + k + '/'))
        else: out[pre + k] = v
    return out
a, b = flat(tip), flat(cur)
print('gate_freeze differences, checkpoint fca3502 (runtime 5583dcad) -> current working tree:')
for k in sorted(set(a) | set(b)):
    if a.get(k) != b.get(k): print(' ', k, str(a.get(k))[:16], '->', str(b.get(k))[:16])
ap = 'backend/app/lab/completion_study.py::assess_pairs'
ck = 'backend/app/referee/checks.py'
print('scorer_hash (sha256 of checks.py) equal to checkpoint:', cur['fingerprints']['scorer_hash'] == tip['fingerprints']['scorer_hash'], cur['fingerprints']['scorer_hash'][:16])
print('checks.py file hash equal to checkpoint:', cur['files'][ck] == tip['files'][ck])
print('checks.py::score and ::scorer_hash functions equal:', all(cur['functions'][f'{ck}::{n}'] == tip['functions'][f'{ck}::{n}'] for n in ('score', 'scorer_hash')))
print('assess_pairs text equal:', cur['functions'][ap]['text_sha256'] == tip['functions'][ap]['text_sha256'], ' ast equal:', cur['functions'][ap]['ast_sha256'] == tip['functions'][ap]['ast_sha256'], ' lines', cur['functions'][ap]['lines'])
for f in ('backend/app/lab/promotion.py', 'backend/app/lab/evaluation.py', 'backend/app/agents/actor.py', 'backend/app/agents/prompts/actor.md', 'backend/app/referee/manifests.py'):
    print(f, 'file equal to checkpoint:', cur['files'][f] == tip['files'][f])
print('vs phase28 gate-freeze-after.json: scorer', cur['fingerprints']['scorer_hash'] == p28['fingerprints']['scorer_hash'],
      '| assess_pairs text', cur['functions'][ap]['text_sha256'] == p28['functions'][ap]['text_sha256'],
      '| ast', cur['functions'][ap]['ast_sha256'] == p28['functions'][ap]['ast_sha256'],
      '| checks.py file', cur['files'][ck] == p28['files'][ck])
print('checkpoint copy vs dependability verifier record of 5583dcad tree (same commit): fingerprints equal:', tip['fingerprints'] == dep['fingerprints'],
      '| functions equal:', tip['functions'] == dep['functions'], '| files equal:', tip['files'] == dep['files'])
print('assess_pairs text sha first 40 =', cur['functions'][ap]['text_sha256'][:40], '(Phase 15 recorded 783e8e58...)')
same = [k for k in cur['functions'] if cur['functions'][k] == tip['functions'].get(k)]
print('functions identical (text, ast, lines) to checkpoint:', len(same), 'of', len(cur['functions']))
for k in cur['functions']:
    if cur['functions'][k] != tip['functions'].get(k):
        c, t = cur['functions'][k], tip['functions'].get(k) or {}
        print('   changed function:', k, '| text', c.get('text_sha256') == t.get('text_sha256'), '| ast', c.get('ast_sha256') == t.get('ast_sha256'), '| lines', t.get('lines'), '->', c.get('lines'))
print('files identical to checkpoint:', sum(cur['files'][k] == tip['files'][k] for k in cur['files']), 'of', len(cur['files']), '(audit/promotion.json and audit/final-audit.json not read; git compares them)')
for k in cur['files']:
    if cur['files'][k] != tip['files'][k]: print('   changed file:', k)
print('current fingerprints: runtime', cur['fingerprints']['runtime_hash'], 'algorithm', cur['fingerprints']['algorithm_hash'])
print('                      service', cur['fingerprints']['service_hash'][:16], 'contract', cur['fingerprints']['contract_hash'][:16], 'interpreter', cur['fingerprints']['interpreter_hash'][:16])
