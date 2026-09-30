"""Independent verifier (discovery v4 review round): compare identity.json of the checkpoint (git archive of backup tip
4d1c21b) and the working tree, then the fixer's reported values (fixer/identity-after.json and identity-final.json)."""
import json, os
w = json.load(open('worktree.json')); c = json.load(open('checkpoint.json'))
def flat(d, pre=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flat(v, pre + k + '.'))
        else: out[pre + k] = v
    return out
W, C = flat(w), flat(c)
print('identity: checkpoint 4d1c21b -> working tree')
for k in sorted(set(W) | set(C)):
    if k == 'root': continue
    print(('same   ' if W.get(k) == C.get(k) else 'CHANGED'), k, ':', C.get(k), '->', W.get(k) if W.get(k) != C.get(k) else '')
alias = {'native_v1_adapter_hash': 'explicit_v1.adapter_hash', 'native_v1_prompt_hash': 'explicit_v1.native_prompt_hash',
         'json_object_response_format_hash': 'response_format_default_hash', 'reference_adapter_hash': 'frozen_config[offline-v1].adapter_hash',
         'reference_source_hash': 'frozen_config[offline-v1].source_hash', 'reference_actor_prompt_hash': 'reference_actor_prompt_hash',
         'capability_hash': 'frozen_config[offline-v1].capability_hash', 'native_v2_adapter_protocol_version': 'native_v2_protocol_version'}
for name in ('identity-after.json', 'identity-final.json'):
    path = '../../fixer/' + name
    if not os.path.exists(path): continue
    f = json.load(open(path)); bad = 0; n = 0
    print(f'\nfixer {name} vs my working-tree values:')
    for k, v in sorted(flat(f).items()):
        mine = W.get(alias.get(k, k), W.get(k))
        if mine is None: print('not-in-mine', k); continue
        n += 1; ok = mine == v; bad += not ok
        if not ok: print('MISMATCH', k, f'fixer={v} mine={mine}')
    print(f'compared {n}, mismatches {bad}')
