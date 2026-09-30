"""Verifier identity snapshot ($0, offline) with the product's own functions, for ONE tree.

Usage: <venv python> -B identity.py <tree root>   (imports app.* from <tree root>/backend only)
No .env is read (Settings() is constructed directly; the guard refuses any .env open).
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vguard  # noqa: F401
root = os.path.abspath(sys.argv[1]); backend = os.path.join(root, 'backend')
os.chdir(backend); sys.path.insert(0, backend)
from app.config import Settings
from app.contracts.models import CampaignBudget, content_hash
import app.lab.configuration as configuration
assert configuration.__file__.startswith(backend), configuration.__file__
from app.lab.configuration import frozen_configuration, runtime_fingerprints
from app.integrations import registry
out = {'tree': root}
out.update(runtime_fingerprints())
config = frozen_configuration(Settings(), CampaignBudget(), 'offline-v1')
for key in ('service_hash', 'contract_hash', 'interpreter_hash', 'scorer_hash', 'capability_hash', 'adapter_hash', 'source_hash',
            'actor_prompt_hash'):
    out[('reference_' + key) if key in ('adapter_hash', 'source_hash', 'actor_prompt_hash') else key] = config.get(key)
out['native_v1_adapter_hash'] = registry.adapter_hash(registry.NATIVE_V1)
out['native_v1_prompt_hash'] = registry.native_prompt_hash(registry.NATIVE_V1)
out['native_v2_adapter_hash'] = registry.adapter_hash(registry.NATIVE_V2)
out['native_v2_prompt_hash'] = registry.native_prompt_hash(registry.NATIVE_V2)
from app.integrations.external_agent_v2 import PROTOCOL_VERSION, adapter_protocol
out['native_v2_adapter_protocol_version'] = PROTOCOL_VERSION
out['native_v2_adapter_protocol_hash'] = content_hash(adapter_protocol())
from app.agents import transport_retry as tr
out['transport_retry_v1_declaration_hash'] = content_hash(tr.declaration(8))
out['transport_retry_v2_declaration_hash'] = content_hash(tr.declaration_v2(8))
from app.lab import discovery_protocol as dp
decls = {}
for proto in (dp.DISCOVERY_V1, dp.DISCOVERY_V2, dp.DISCOVERY_V3, dp.DISCOVERY_V3_PRECHECK, dp.DISCOVERY_V4):
    try:
        decls[proto] = dp.declaration(proto, CampaignBudget())
    except Exception as error:  # recorded, never hidden
        decls[proto] = 'unavailable: ' + type(error).__name__
out['discovery_declarations'] = {k: (content_hash(v) if isinstance(v, dict) else v) for k, v in decls.items()}
try:
    from app.lab import loop_limits
    out['mechanic_context_v2_declaration_hash'] = content_hash(loop_limits.mechanic_context_declaration())
    out['challenge_selection_v2_declaration_hash'] = content_hash(loop_limits.challenge_selection_declaration())
except ImportError:
    out['mechanic_context_v2_declaration_hash'] = out['challenge_selection_v2_declaration_hash'] = 'absent (no loop_limits module)'
print(json.dumps(out, indent=1, sort_keys=True))
