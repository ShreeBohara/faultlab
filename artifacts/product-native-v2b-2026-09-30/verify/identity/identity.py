"""Independent verifier (native v2b, 2026-09-30): code identities computed by the PRODUCT's own functions in the tree
given as argv[1] (sys.path points only there). Based on artifacts/product-native-v2-2026-09-29/verify/identity/identity.py,
plus: reference configuration hashes via frozen_configuration(Settings(), ...) (Settings() is a plain dataclass; only
Settings.from_env reads .env, and it is never called), the example DeepSeek-V3.1 configuration hashes for v1/v2 and the
frozen transport-retry declaration hashes. No .env, no store, no network (run under verify/guard/sitecustomize.py).
checks.py is hashed by the product's own code (tree_hash / scorer_hash) and never displayed."""
import json, os, sys
root = sys.argv[1]
sys.path.insert(0, root + '/backend')
os.chdir(root + '/backend')
from app.lab.configuration import runtime_fingerprints, tree_hash, file_hash, ROOT, frozen_configuration
from app.contracts.models import content_hash, CampaignBudget
from app.config import Settings
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
out['actor_md_file_hash'] = file_hash(ROOT / 'backend/app/agents/prompts/actor.md')
config = frozen_configuration(Settings(), CampaignBudget(), 'offline-v1')
for key in ('service_hash', 'contract_hash', 'interpreter_hash', 'scorer_hash', 'capability_hash', 'adapter_hash', 'source_hash', 'actor_prompt_hash'):
    out['frozen_config[offline-v1].' + key] = config.get(key)
from app.integrations import registry
from app.integrations import external_agent as ea
out['native_v1_prompt_hash_default_call'] = registry.native_prompt_hash()
out['native_v1_adapter_hash_default_call'] = registry.adapter_hash()
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
out['native_final_answer_response_format_hash'] = content_hash(rt.response_format_for(response_contract='native_final_answer'))
out['explicit_v1'] = {'native_prompt_hash': registry.native_prompt_hash(registry.NATIVE_V1),
                      'adapter_hash': registry.adapter_hash(registry.NATIVE_V1)}
out['native_v2_prompt_hash'] = registry.native_prompt_hash(registry.NATIVE_V2)
out['native_v2_adapter_hash'] = registry.adapter_hash(registry.NATIVE_V2)
from app.integrations.external_agent_v2 import adapter_protocol, PROTOCOL_VERSION
out['native_v2_adapter_protocol_hash'] = content_hash(adapter_protocol())
out['native_v2_protocol_version'] = PROTOCOL_VERSION
live = frozen_configuration(Settings(wandb_model='deepseek-ai/DeepSeek-V3.1'), CampaignBudget(), 'live-v1')
for entry in (registry.NATIVE_V1, registry.NATIVE_V2):
    target = registry.freeze_target_configuration(live, 'deepseek-ai/DeepSeek-V3.1', entry)
    out[f'example_configuration_hash[{entry}, deepseek-ai/DeepSeek-V3.1, default caps]'] = content_hash(target)
from app.agents import transport_retry as tr
out['transport_retry_v1_declaration_hash'] = content_hash(tr.declaration(8))
out['transport_retry_v2_declaration_hash'] = content_hash(tr.declaration_v2(8)) if hasattr(tr, 'declaration_v2') else 'absent'
print(json.dumps(out, indent=1, sort_keys=True))
