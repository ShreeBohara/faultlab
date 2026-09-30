"""Reviewer: on the PRIVATE COPY of the first live v2 run's store (ReadOnlyLabStore), compute the discovery v3 agent history
(the product's own compute_history) for (a) the first v2 build's identity and (b) the same identity with only the prompt
hash changed to the v2.1 build's (fff397c9...), which is the only identity field this round changes for v2 in the same
setup. Shows whether v2.1 would pool the first build's episodes. Offline, $0."""
import json, os, sys
from pathlib import Path
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'backend'))
from app.contracts.models import content_hash
from app.integrations.registry import NATIVE_V2, native_prompt_hash
from app.lab.agent_history import compute_history, target_identity
from app.lab.storage import ReadOnlyLabStore
store = ReadOnlyLabStore(HERE / 'store-copy' / 'lab.sqlite3')
registration = store.get_record('agent_registrations', 'smolagents-1.26.0-adapter-v2-e5bfdfc21e5c56a4')
configuration = store.get_record('configurations', registration['configuration_hash'])
first = target_identity(registration, configuration)
policy = next(p for p in store.list_records('policies') if p['version'] == 'policy-v0')
cutoff = store.max_record_rowid()
v21 = {**first, 'prompt_hash': native_prompt_hash(NATIVE_V2)}
out = {}
for name, identity in (('first_v2_build', first), ('v2.1_same_setup', v21)):
    history = compute_history(store, identity=identity, policy_hash=policy['policy_hash'], cutoff=cutoff)
    summary = history.get('summary') or {}
    out[name] = {'identity_hash': content_hash(identity), 'prompt_hash': identity['prompt_hash'], 'status': history.get('status'),
                 'verified_episodes': summary.get('verified_episodes'),
                 'recipes': [(r.get('development_case_id'), r.get('verified_episodes')) for r in summary.get('recipes', [])]}
out['identity_fields_that_differ'] = sorted(k for k in set(first) | set(v21) if first.get(k) != v21.get(k))
print(json.dumps(out, indent=1, default=str))
store.close()
