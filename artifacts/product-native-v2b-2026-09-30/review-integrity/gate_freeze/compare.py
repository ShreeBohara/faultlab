"""Compare gate_freeze: checkpoint backup/part2 2c178a7 (git archive copy) vs current working tree, plus earlier verifier records."""
import json
base = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/'
cur = json.load(open('current.json')); tip = json.load(open('checkpoint_2c178a7.json'))
nv2 = json.load(open(base + 'product-native-v2-2026-09-29/verify/gate_freeze/current.json'))
dep = json.load(open(base + 'product-dependability-2026-09-29/verify/gate_freeze/current.json'))
p28 = json.load(open(base + 'phase28-2026-09-26/gate-freeze-after.json'))
def flat(d, pre=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flat(v, pre + k + '/'))
        else: out[pre + k] = v
    return out
a, b = flat(tip), flat(cur)
print('gate_freeze differences, checkpoint 2c178a7 (backup/part2) -> current working tree:')
for k in sorted(set(a) | set(b)):
    if a.get(k) != b.get(k): print(' ', k, str(a.get(k))[:16], '->', str(b.get(k))[:16])
ap = 'backend/app/lab/completion_study.py::assess_pairs'; ck = 'backend/app/referee/checks.py'
print()
print('checkpoint 2c178a7 record == previous native-v2 verifier record of ac7a12d2 working tree (fingerprints/functions/files):',
      tip['fingerprints'] == nv2['fingerprints'], tip['functions'] == nv2['functions'], tip['files'] == nv2['files'])
print('scorer_hash equal to checkpoint:', cur['fingerprints']['scorer_hash'] == tip['fingerprints']['scorer_hash'], cur['fingerprints']['scorer_hash'][:16],
      '| equal to dependability record:', cur['fingerprints']['scorer_hash'] == dep['fingerprints']['scorer_hash'],
      '| equal to phase28:', cur['fingerprints']['scorer_hash'] == p28['fingerprints']['scorer_hash'])
print('checks.py file hash equal to checkpoint:', cur['files'][ck] == tip['files'][ck])
print('checks.py::score and ::scorer_hash functions equal:', all(cur['functions'][f'{ck}::{n}'] == tip['functions'][f'{ck}::{n}'] for n in ('score', 'scorer_hash')))
print('assess_pairs text/ast/lines equal to checkpoint:', cur['functions'][ap] == tip['functions'][ap], '| text sha[:40]', cur['functions'][ap]['text_sha256'][:40], '(Phase 15: 783e8e58...)')
print('tree_referee equal:', cur['fingerprints']['tree_referee'] == tip['fingerprints']['tree_referee'])
for f in ('backend/app/lab/promotion.py', 'backend/app/lab/evaluation.py', 'backend/app/agents/actor.py', 'backend/app/agents/progress.py',
          'backend/app/agents/prompts/actor.md', 'backend/app/referee/manifests.py', 'audit/development.json', 'backend/app/lab/runner.py',
          'backend/app/lab/completion_study.py', 'backend/app/lab/reproduction.py', 'backend/app/lab/evidence.py', 'backend/app/lab/policies.py'):
    print(f, 'file equal to checkpoint:', cur['files'][f] == tip['files'][f])
for key in ('service_hash', 'contract_hash', 'interpreter_hash', 'scorer_hash', 'adapter_hash', 'actor_prompt_hash', 'dependency_lock_hash', 'tree_telemetry'):
    print(f'{key}: equal={cur["fingerprints"][key] == tip["fingerprints"][key]} {cur["fingerprints"][key][:16]}')
print('changed functions:')
for k in cur['functions']:
    if cur['functions'][k] != tip['functions'].get(k):
        c, t = cur['functions'][k], tip['functions'].get(k) or {}
        print('   ', k, '| text equal', c.get('text_sha256') == t.get('text_sha256'), '| ast equal', c.get('ast_sha256') == t.get('ast_sha256'), '| lines', t.get('lines'), '->', c.get('lines'))
print('files identical to checkpoint:', sum(cur['files'][k] == tip['files'][k] for k in cur['files']), 'of', len(cur['files']))
for k in cur['files']:
    if cur['files'][k] != tip['files'][k]: print('   changed file:', k)
print('current fingerprints: runtime', cur['fingerprints']['runtime_hash'], '\n  algorithm', cur['fingerprints']['algorithm_hash'], '\n  source', cur['fingerprints']['source_hash'])
