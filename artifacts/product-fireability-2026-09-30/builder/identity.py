"""Runtime/algorithm and component identities with the product's own functions, under the guard ($0, no .env).

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/builder/identity.py > out.json
Executes identity_snapshot.py (copied unchanged from the citation-status builder) after installing guard.py (copied
unchanged from the citation-status builder), then adds the declaration hashes of the loop-limit, citation-status,
evidence-retry and (when this build has it) history-fireability rules.
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

runpy.run_path(str(HERE / 'identity_snapshot.py'), run_name='__main__')
import json  # noqa: E402
from app.contracts.models import content_hash  # noqa: E402
from app.lab import loop_limits, diagnosis, citation_status, evidence_wait  # noqa: E402
extra = {'mechanic_context_v2_declaration_hash': content_hash(loop_limits.mechanic_context_declaration()),
         'challenge_selection_v2_declaration_hash': content_hash(loop_limits.challenge_selection_declaration()),
         'v2_memory_text_hash': content_hash(diagnosis.V2_MEMORY),
         'mechanic_evidence_v2_native_citation_status_declaration_hash': content_hash(citation_status.declaration()),
         'v2_memory_with_citation_pointer_text_hash': content_hash(citation_status.V2_MEMORY_WITH_CITATION_STATUS),
         'evidence_retry_new_plan_declaration_hash': content_hash(evidence_wait.declaration()),
         'evidence_retry_new_plan_protocol': evidence_wait.declaration()['protocol']}
if hasattr(evidence_wait, 'declaration_v2'):
    extra['evidence_retry_v2_declaration_hash'] = content_hash(evidence_wait.declaration_v2())
else:
    extra['evidence_retry_v2_declaration_hash'] = content_hash(evidence_wait.declaration())
try:
    from app.lab import fireability
    extra['explorer_selection_v3_rule_declaration_hash'] = content_hash(fireability.declaration())
except ImportError as error:
    extra['fireability'] = f'not in this build ({type(error).__name__})'
print(json.dumps(extra, indent=2, sort_keys=True))
