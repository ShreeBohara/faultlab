"""Independent verifier (native adapter v2): code identities computed by the PRODUCT's own functions in the tree
given as argv[1] (sys.path points only there). No Settings.from_env, no .env, no store, no network.
checks.py is hashed by the product's own code (tree_hash / scorer_hash) and never displayed."""
import json, os, sys
root = sys.argv[1]
sys.path.insert(0, root + '/backend')
os.chdir(root + '/backend')
from app.lab.configuration import runtime_fingerprints, tree_hash, file_hash, ROOT
from app.contracts.models import content_hash
assert str(ROOT) == root, (str(ROOT), root)
import app
assert app.__file__.startswith(root + '/backend/'), app.__file__
service = tree_hash(ROOT / 'backend/app/simulator')
schemas = {p.name: file_hash(p) for p in sorted((ROOT / 'contracts').glob('*.schema.json'))}
lab = ROOT / 'backend/app/lab'
out = {**runtime_fingerprints(), 'service_hash': service,
       'contract_hash': content_hash({'schemas': schemas, 'service_hash': service}),
       'interpreter_hash': content_hash({n: file_hash(lab / n) for n in ('policy_interpreter.py', 'policy_state.py', 'budgets.py')}),
       'root': root}
from app.referee.checks import scorer_hash
out['scorer_hash'] = scorer_hash()
from app.agents.actor import ACTOR_PROMPT_HASH
out['reference_actor_prompt_hash'] = ACTOR_PROMPT_HASH
from app.integrations import registry
from app.integrations import external_agent as ea
# v1: called with no argument (the checkpoint signature) = v1 in both trees
out['native_v1_prompt_hash'] = registry.native_prompt_hash()
out['native_v1_adapter_hash'] = registry.adapter_hash()
out['native_source_hash'] = registry.verify_native_source()
out['v1_parts'] = {
    'TASK_CONTRACT_sha': content_hash(ea.TASK_CONTRACT),
    'TRANSPORT_CONTRACT_sha': content_hash(ea.TRANSPORT_CONTRACT),
    'native_template_sha': content_hash(registry.NATIVE_FILES['prompts/toolcalling_agent.yaml']),
    'external_agent.py_file_sha': file_hash(ROOT / 'backend/app/integrations/external_agent.py'),
}
from app.providers import runtime as rt
out['response_format_default_hash'] = content_hash(rt.response_format_for())
out['actor_final_report_response_format_hash'] = content_hash(rt.response_format_for(response_contract='actor_final_report'))
out['actor_response_protocol_hash'] = content_hash(rt.actor_response_protocol())
if hasattr(registry, 'NATIVE_V2'):
    out['explicit_v1'] = {'native_prompt_hash': registry.native_prompt_hash(registry.NATIVE_V1),
                          'adapter_hash': registry.adapter_hash(registry.NATIVE_V1)}
    out['native_v2_prompt_hash'] = registry.native_prompt_hash(registry.NATIVE_V2)
    out['native_v2_adapter_hash'] = registry.adapter_hash(registry.NATIVE_V2)
    from app.integrations.external_agent_v2 import adapter_protocol, PROTOCOL_VERSION
    out['native_v2_adapter_protocol_hash'] = content_hash(adapter_protocol())
    out['native_v2_protocol_version'] = PROTOCOL_VERSION
    out['native_final_answer_response_format_hash'] = content_hash(rt.response_format_for(response_contract='native_final_answer'))
print(json.dumps(out, indent=1, sort_keys=True))
