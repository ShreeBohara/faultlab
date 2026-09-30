"""Integrity reviewer: dump what the Mechanic/Explorer read as the actor contract (runtime_contract) for the reference
Actor, native v1 and native v2 campaigns, plus the fixed prompt texts, under whichever tree is first on sys.path.
Run once with the checkpoint tree (backup/part2 2c178a7) and once with the working tree; diff the outputs.
Guards: refuses any .env open and any non-loopback socket."""
import os, sys, json
backend = sys.argv[1]; out_path = sys.argv[2]
REAL_ENV = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.env'
def guard(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)) and os.path.basename(os.fsdecode(args[0])) == '.env':
        raise PermissionError('reviewer guard: .env must not be read')
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise PermissionError('reviewer guard: network')
sys.addaudithook(guard)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, backend)
from types import SimpleNamespace
import app.lab.runner as runner
import app.integrations.registry as registry
from app.lab import diagnosis
from app.contracts.models import canonical_json, content_hash
assert os.path.dirname(diagnosis.__file__).startswith(backend), diagnosis.__file__
registry.AgentRegistry.get = lambda self, rid: SimpleNamespace(prompt_hash='PROMPT', source_hash='SOURCE')
views = {}
for agent in ('reference', 'smolagents', 'smolagents-v2'):
    runner.campaign_run_plan = lambda store, campaign, agent=agent: {'agent': agent, 'agent_registration_id': 'reg'}
    views[agent] = diagnosis.runtime_contract(store=object(), campaign=object())
views['no_store'] = diagnosis.runtime_contract()
prompts = {}
base = os.path.join(backend, 'app/agents/prompts')
for name in sorted(os.listdir(base)):
    prompts[name] = content_hash(open(os.path.join(base, name)).read())
json.dump({'views': views, 'view_hashes': {k: content_hash(v) for k, v in views.items()}, 'prompt_hashes': prompts,
           'ACTOR_PROMPT_hash': content_hash(diagnosis.ACTOR_PROMPT)}, open(out_path, 'w'), indent=1, sort_keys=True)
print(json.dumps({k: content_hash(v)[:16] for k, v in views.items()}))
