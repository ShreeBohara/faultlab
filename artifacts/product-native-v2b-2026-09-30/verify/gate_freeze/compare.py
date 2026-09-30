"""Compare gate_freeze output: checkpoint = git archive of backup tip 2c178a7 (runtime ac7a12d2) vs current working tree;
plus the fixer's record, the previous verifier's record of the v2 tree, and Phase 28's record."""
import json
cur = json.load(open('current.json')); tip = json.load(open('checkpoint.json'))
base = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/'
fixer = json.load(open(base + 'product-native-v2b-2026-09-30/fixer/gate_freeze/current.json'))
prev = json.load(open(base + 'product-native-v2-2026-09-29/verify/gate_freeze/current.json'))
p28 = json.load(open(base + 'phase28-2026-09-26/gate-freeze-after.json'))
def flat(d, pre=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flat(v, pre + k + '/'))
        else: out[pre + k] = v
    return out
a, b = flat(tip), flat(cur)
print('gate_freeze differences, checkpoint 2c178a7 (runtime ac7a12d2) -> current working tree:')
for k in sorted(set(a) | set(b)):
    if a.get(k) != b.get(k): print(' ', k, str(a.get(k))[:16], '->', str(b.get(k))[:16])
ap = 'backend/app/lab/completion_study.py::assess_pairs'
ck = 'backend/app/referee/checks.py'
print()
print('scorer_hash (sha256 of checks.py) equal to checkpoint:', cur['fingerprints']['scorer_hash'] == tip['fingerprints']['scorer_hash'], cur['fingerprints']['scorer_hash'][:16])
print('checks.py file hash equal to checkpoint:', cur['files'][ck] == tip['files'][ck])
print('checks.py::score and ::scorer_hash functions equal:', all(cur['functions'][f'{ck}::{n}'] == tip['functions'][f'{ck}::{n}'] for n in ('score', 'scorer_hash')))
print('assess_pairs text equal:', cur['functions'][ap]['text_sha256'] == tip['functions'][ap]['text_sha256'], ' ast equal:', cur['functions'][ap]['ast_sha256'] == tip['functions'][ap]['ast_sha256'], ' lines', cur['functions'][ap]['lines'])
print('assess_pairs text sha first 40 =', cur['functions'][ap]['text_sha256'][:40], '(Phase 15 recorded 783e8e58...)')
for f in ('backend/app/lab/promotion.py', 'backend/app/lab/evaluation.py', 'backend/app/agents/actor.py', 'backend/app/agents/prompts/actor.md', 'backend/app/referee/manifests.py', 'backend/app/lab/diagnosis.py', 'backend/app/lab/runner.py', 'backend/app/lab/evidence.py', 'backend/app/lab/reproduction.py'):
    print(f, 'file equal to checkpoint:', cur['files'][f] == tip['files'][f])
print('vs phase28 gate-freeze-after.json: scorer', cur['fingerprints']['scorer_hash'] == p28['fingerprints']['scorer_hash'],
      '| assess_pairs text', cur['functions'][ap]['text_sha256'] == p28['functions'][ap]['text_sha256'],
      '| ast', cur['functions'][ap]['ast_sha256'] == p28['functions'][ap]['ast_sha256'],
      '| checks.py file', cur['files'][ck] == p28['files'][ck])
print('my checkpoint copy vs previous verifier record of the v2 tree (runtime ac7a12d2): fingerprints equal:', tip['fingerprints'] == prev['fingerprints'],
      '| functions equal:', tip['functions'] == prev['functions'], '| files equal:', tip['files'] == prev['files'])
print('my current vs fixer gate_freeze/current.json: fingerprints equal:', cur['fingerprints'] == fixer['fingerprints'],
      '| functions equal:', cur['functions'] == fixer['functions'], '| files equal:', cur['files'] == fixer['files'])
same = [k for k in cur['functions'] if cur['functions'][k] == tip['functions'].get(k)]
print('functions identical (text, ast, lines) to checkpoint:', len(same), 'of', len(cur['functions']))
for k in cur['functions']:
    if cur['functions'][k] != tip['functions'].get(k):
        c, t = cur['functions'][k], tip['functions'].get(k) or {}
        print('   changed function:', k, '| text', c.get('text_sha256') == t.get('text_sha256'), '| ast', c.get('ast_sha256') == t.get('ast_sha256'), '| lines', t.get('lines'), '->', c.get('lines'))
print('files identical to checkpoint:', sum(cur['files'][k] == tip['files'][k] for k in cur['files']), 'of', len(cur['files']), '(audit/promotion.json and audit/final-audit.json dropped from FILES; not read)')
for k in cur['files']:
    if cur['files'][k] != tip['files'][k]: print('   changed file:', k)
print('current fingerprints: runtime', cur['fingerprints']['runtime_hash'], 'algorithm', cur['fingerprints']['algorithm_hash'])
print('                      service', cur['fingerprints']['service_hash'][:16], 'contract', cur['fingerprints']['contract_hash'][:16], 'interpreter', cur['fingerprints']['interpreter_hash'][:16])
