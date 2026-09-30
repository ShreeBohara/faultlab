"""Runtime/algorithm and component identities with the product's own functions, under the guard ($0, no .env).

Run from faultlab/backend:  ../.venv/bin/python ../artifacts/product-mechanic-citations-2026-09-30/builder/identity.py > out.json
Executes identity_snapshot.py (copied unchanged from the loop-limits fixer) after installing guard.py (copied unchanged
from the loop-limits fixer), then adds the loop-limit declaration hashes and, when this build has it, the
native citation-status declaration hash and the two v2 memory-text hashes.
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
from app.lab import loop_limits  # noqa: E402
from app.lab import diagnosis  # noqa: E402
extra = {'mechanic_context_v2_declaration_hash': content_hash(loop_limits.mechanic_context_declaration()),
         'challenge_selection_v2_declaration_hash': content_hash(loop_limits.challenge_selection_declaration()),
         'v2_memory_text_hash': content_hash(diagnosis.V2_MEMORY)}
try:
    from app.lab import citation_status
    extra['mechanic_evidence_v2_native_citation_status_declaration_hash'] = content_hash(citation_status.declaration())
    extra['v2_memory_with_citation_pointer_text_hash'] = content_hash(citation_status.V2_MEMORY_WITH_CITATION_STATUS)
except ImportError as error:
    extra['citation_status'] = f'not in this build ({type(error).__name__})'
print(json.dumps(extra, indent=2, sort_keys=True))
