import json
a = json.load(open('v1_checkpoint.json')); b = json.load(open('v1_worktree.json'))
print('checkpoint modules:', a['module_files']['app.integrations.external_agent'])
print('worktree modules:  ', b['module_files']['app.integrations.external_agent'])
skip = {'label', 'root', 'module_files', 'v1_adapter_hash_informational'}
for k in sorted(set(a) | set(b)):
    if k in skip or k == 'episodes': continue
    print(f'{k}: identical={a.get(k) == b.get(k)}', (str(a.get(k))[:70] if k.endswith('hash') else ''))
for name in a['episodes']:
    ea, eb = a['episodes'][name], b['episodes'][name]
    bytes_equal = [json.dumps(x['messages'], ensure_ascii=False, sort_keys=True) == json.dumps(y['messages'], ensure_ascii=False, sort_keys=True) for x, y in zip(ea['requests'], eb['requests'])]
    print(f"episode {name}: requests {len(ea['requests'])}/{len(eb['requests'])}, messages byte-identical {all(bytes_equal) and len(ea['requests'])==len(eb['requests'])}, "
          f"kwargs identical {[r['kwargs'] for r in ea['requests']] == [r['kwargs'] for r in eb['requests']]}, whole episode record identical {ea == eb}, "
          f"any response_contract kwarg {any('response_contract' in r['kwargs'] for r in eb['requests'])}, outcome {str(eb['outcome'])[:60]}")
print('v1 adapter_hash (informational; expected to differ because registry.py changed):', a['v1_adapter_hash_informational'][:16], '->', b['v1_adapter_hash_informational'][:16])
g = json.load(open('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/fixtures/native_v1_golden_requests.json'))
for name in ('success', 'no_report'):
    print(f'builder golden fixture {name}: messages equal to reviewer checkpoint capture:',
          [r['messages'] for r in g[name]['requests']] == [r['messages'] for r in a['episodes'][name]['requests']],
          'kwargs equal:', [r['kwargs'] for r in g[name]['requests']] == [r['kwargs'] for r in a['episodes'][name]['requests']])
