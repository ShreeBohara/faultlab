"""Print FaultLab identity values with the product's own functions ($0, offline, no .env read).

Run from faultlab/backend with the project .venv:  ../.venv/bin/python ../artifacts/product-native-v2-2026-09-29/builder/identity_snapshot.py
"""
import json, os, sys
os.environ.setdefault('PYTHON_DOTENV_DISABLED', '1')
sys.path.insert(0, os.getcwd())
from app.config import Settings
from app.contracts.models import CampaignBudget, content_hash
from app.lab.configuration import frozen_configuration, runtime_fingerprints
from app.integrations import registry
from app.providers.runtime import actor_response_protocol, response_format_for

out = {}
out.update(runtime_fingerprints())
config = frozen_configuration(Settings(), CampaignBudget(), 'offline-v1')
for key in ('service_hash', 'contract_hash', 'interpreter_hash', 'scorer_hash', 'capability_hash', 'adapter_hash', 'source_hash', 'actor_prompt_hash'):
    out['reference_' + key if key in ('adapter_hash', 'source_hash', 'actor_prompt_hash') else key] = config[key]
out['native_v1_adapter_hash'] = registry.adapter_hash()
out['native_v1_prompt_hash'] = registry.native_prompt_hash()
out['native_source_hash'] = registry.verify_native_source()
out['actor_response_protocol_hash'] = content_hash(actor_response_protocol())
out['actor_final_report_response_format_hash'] = content_hash(response_format_for(response_contract='actor_final_report'))
out['json_object_response_format_hash'] = content_hash(response_format_for())
if hasattr(registry, 'NATIVE_V2'):
    out['native_v1_adapter_hash'] = registry.adapter_hash(registry.NATIVE_V1)
    out['native_v1_prompt_hash'] = registry.native_prompt_hash(registry.NATIVE_V1)
    out['native_v2_adapter_hash'] = registry.adapter_hash(registry.NATIVE_V2)
    out['native_v2_prompt_hash'] = registry.native_prompt_hash(registry.NATIVE_V2)
    from app.integrations.external_agent_v2 import adapter_protocol
    out['native_v2_adapter_protocol_hash'] = content_hash(adapter_protocol())
    # Configuration and registration identity for a fixed example model (no settings file is read).
    from app.integrations.registry import freeze_target_configuration
    live = frozen_configuration(Settings(wandb_model='deepseek-ai/DeepSeek-V3.1'), CampaignBudget(), 'live-v1')
    for entry in (registry.NATIVE_V1, registry.NATIVE_V2):
        target = freeze_target_configuration(live, 'deepseek-ai/DeepSeek-V3.1', entry)
        out[f'example_configuration_hash[{entry}, deepseek-ai/DeepSeek-V3.1, default caps]'] = content_hash(target)
try:
    out['native_final_answer_response_format_hash'] = content_hash(response_format_for(response_contract='native_final_answer'))
except Exception as error:
    out['native_final_answer_response_format_hash'] = f'unavailable ({type(error).__name__})'
print(json.dumps(out, indent=2, sort_keys=True))
