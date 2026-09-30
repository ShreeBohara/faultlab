"""Verifier identity snapshot ($0, offline) with the product's own functions, for ONE tree.

Usage: <venv python> -B identity.py <tree root>   (imports app.* from <tree root>/backend only)
Copied from the citation-status verifier's identity.py, plus (fireability round): the history fireability declaration hash,
the evidence retry v2 / v3 declaration hashes, and the challenge selection prompt digest when the tree has them.
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
out['native_source_hash'] = registry.verify_native_source()
from app.integrations.external_agent_v2 import PROTOCOL_VERSION, adapter_protocol
out['native_v2_adapter_protocol_version'] = PROTOCOL_VERSION
out['native_v2_adapter_protocol_hash'] = content_hash(adapter_protocol())
from app.integrations.registry import freeze_target_configuration
live = frozen_configuration(Settings(wandb_model='deepseek-ai/DeepSeek-V3.1'), CampaignBudget(), 'live-v1')
for entry in (registry.NATIVE_V1, registry.NATIVE_V2):
    target = freeze_target_configuration(live, 'deepseek-ai/DeepSeek-V3.1', entry)
    out[f'example_configuration_hash[{entry}]'] = content_hash(target)
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
from app.lab import loop_limits, diagnosis
out['mechanic_context_v2_declaration_hash'] = content_hash(loop_limits.mechanic_context_declaration())
out['challenge_selection_v2_declaration_hash'] = content_hash(loop_limits.challenge_selection_declaration())
out['v2_memory_text_hash'] = content_hash(diagnosis.V2_MEMORY)
try:
    from app.lab import citation_status
    out['citation_status_declaration_hash'] = content_hash(citation_status.declaration())
    out['v2_memory_with_citation_pointer_text_hash'] = content_hash(citation_status.V2_MEMORY_WITH_CITATION_STATUS)
except ImportError as error:
    out['citation_status_declaration_hash'] = out['v2_memory_with_citation_pointer_text_hash'] = f'absent ({type(error).__name__})'

from app.lab import evidence_wait as ew
if hasattr(ew, 'declaration_v2'):
    out['evidence_retry_v2_declaration_hash'] = content_hash(ew.declaration_v2())
    out['evidence_retry_v3_declaration_hash'] = content_hash(ew.declaration())
else:
    d = ew.declaration()
    out['evidence_retry_' + d['protocol'].rsplit('/', 1)[1] + '_declaration_hash'] = content_hash(d)
try:
    from app.lab import fireability
    out['explorer_selection_v3_declaration_hash'] = content_hash(fireability.declaration())
except ImportError as error:
    out['explorer_selection_v3_declaration_hash'] = f'absent ({type(error).__name__})'
from app.agents import explorer as ex
out['explorer_prompt_texts_hash'] = content_hash({k: getattr(ex, k) for k in sorted(dir(ex)) if k.isupper() and isinstance(getattr(ex, k), str)})
import hashlib
for rel in ('backend/app/agents/prompts/actor.md', 'backend/app/agents/actor.py', 'backend/app/lab/challenge.py',
            'backend/app/lab/promotion.py', 'backend/app/lab/evaluation.py'):
    out['sha256[' + rel + ']'] = hashlib.sha256(open(os.path.join(root, rel), 'rb').read()).hexdigest()
print(json.dumps(out, indent=1, sort_keys=True))
