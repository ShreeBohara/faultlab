"""Compare identity.json of the checkpoint (git archive of backup tip 2c178a7) and the working tree, plus the fixer's claims."""
import json
w = json.load(open('worktree.json')); c = json.load(open('checkpoint.json'))
f = json.load(open('../../fixer/identity-after.json'))
def flat(d, pre=''):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(flat(v, pre + k + '.'))
        else: out[pre + k] = v
    return out
W, C = flat(w), flat(c)
print('identity: checkpoint 2c178a7 -> working tree')
for k in sorted(set(W) | set(C)):
    if k == 'root': continue
    print(('same   ' if W.get(k) == C.get(k) else 'CHANGED'), k, ':', C.get(k), '->', W.get(k) if W.get(k) != C.get(k) else '')
print()
print('fixer identity-after.json vs my working-tree values (keys in both):')
alias = {'native_v1_adapter_hash': 'explicit_v1.adapter_hash', 'native_v1_prompt_hash': 'explicit_v1.native_prompt_hash',
         'json_object_response_format_hash': 'response_format_default_hash', 'reference_adapter_hash': 'frozen_config[offline-v1].adapter_hash',
         'reference_source_hash': 'frozen_config[offline-v1].source_hash', 'reference_actor_prompt_hash': 'reference_actor_prompt_hash',
         'capability_hash': 'frozen_config[offline-v1].capability_hash', 'native_v2_adapter_protocol_version': 'native_v2_protocol_version'}
bad = 0
for k, v in sorted(f.items()):
    mine = W.get(alias.get(k, k))
    ok = mine == v
    bad += not ok
    print(('match   ' if ok else 'MISMATCH'), k, v if ok else f'fixer={v} mine={mine}')
print('mismatches:', bad)
