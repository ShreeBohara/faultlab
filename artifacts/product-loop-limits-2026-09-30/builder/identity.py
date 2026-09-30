"""Runtime/algorithm and component identities with the product's own functions, under the guard ($0, no .env).

Run from faultlab/backend:  ../.venv/bin/python ../artifacts/product-loop-limits-2026-09-30/builder/identity.py > out.json
Executes identity_snapshot.py (copied unchanged from the discovery v4 builder) after installing guard.py
(copied from the discovery v4 fixer), and adds this round's declaration hashes when the build has them.
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

runpy.run_path(str(HERE / 'identity_snapshot.py'), run_name='__main__')
try:
    import json
    from app.contracts.models import content_hash
    from app.lab import loop_limits
    print(json.dumps({'mechanic_context_v2_declaration_hash': content_hash(loop_limits.mechanic_context_declaration()),
                      'challenge_selection_v2_declaration_hash': content_hash(loop_limits.challenge_selection_declaration())},
                     indent=2, sort_keys=True))
except ImportError as error:
    print(json.dumps({'loop_limits': f'not in this build ({type(error).__name__})'}) if 'json' in dir() else '{}')
