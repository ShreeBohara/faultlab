"""Reviewer identity check ($0, offline, no .env): the product's own identity functions on this tree."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rguard  # noqa: F401
from app.config import Settings
from app.contracts.models import CampaignBudget, content_hash
from app.lab.configuration import frozen_configuration, runtime_fingerprints
from app.integrations import registry
from app.integrations.external_agent_v2 import adapter_protocol, PROTOCOL_VERSION
from app.lab import citation_status, diagnosis, loop_limits
out = dict(runtime_fingerprints())
config = frozen_configuration(Settings(), CampaignBudget(), 'offline-v1')
for key in ('service_hash', 'contract_hash', 'interpreter_hash', 'scorer_hash', 'capability_hash', 'source_hash', 'actor_prompt_hash'):
    out[key] = config[key]
out['native_v1_adapter_hash'] = registry.adapter_hash(registry.NATIVE_V1)
out['native_v1_prompt_hash'] = registry.native_prompt_hash(registry.NATIVE_V1)
out['native_v2_adapter_hash'] = registry.adapter_hash(registry.NATIVE_V2)
out['native_v2_prompt_hash'] = registry.native_prompt_hash(registry.NATIVE_V2)
out['native_v2_adapter_protocol_hash'] = content_hash(adapter_protocol())
out['native_v2_protocol_version'] = PROTOCOL_VERSION
out['mechanic_context_v2_declaration_hash'] = content_hash(loop_limits.mechanic_context_declaration())
out['v2_memory_text_hash'] = content_hash(diagnosis.V2_MEMORY)
out['citation_status_declaration_hash'] = content_hash(citation_status.declaration())
out['v2_memory_with_pointer_hash'] = content_hash(citation_status.V2_MEMORY_WITH_CITATION_STATUS)
print(json.dumps(out, indent=1, sort_keys=True))
