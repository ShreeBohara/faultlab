"""Review identity check ($0, offline, guarded): recompute the build's identity values with the product's own functions
(the builder's identity_snapshot.py, executed unchanged under THIS review's guard) and compare with builder/identity-after.json.
Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/review-product/review_identity.py
"""
import contextlib
import io
import json
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402,F401

buffer = io.StringIO()
with contextlib.redirect_stdout(buffer):
    runpy.run_path(str(HERE.parent / 'builder' / 'identity_snapshot.py'), run_name='__main__')
ours = json.loads(buffer.getvalue())
from app.contracts.models import content_hash  # noqa: E402
from app.lab import diagnosis_guide, diagnosis_protocol  # noqa: E402
from app.agents.explorer import PUBLIC_INVARIANTS  # noqa: E402
from app.referee.diagnostics import PROTOCOL_HASH  # noqa: E402
from app.integrations import registry  # noqa: E402
ours.update({'mechanic_diagnosis_v1_declaration_hash': content_hash(diagnosis_protocol.declaration()),
             'mechanic_diagnosis_v1_semantics_hash': diagnosis_protocol.semantics_hash(),
             'diagnosis_guide_v1_declaration_hash': content_hash(diagnosis_guide.declaration()),
             'diagnosis_guide_v1_offered': diagnosis_guide.DIAGNOSIS_GUIDE_OFFERED,
             'public_invariants_hash': content_hash(PUBLIC_INVARIANTS), 'diagnostics_PROTOCOL_HASH': PROTOCOL_HASH})
builder = {}
text = (HERE.parent / 'builder' / 'identity-after.json').read_text()
decoder = json.JSONDecoder(); index = 0
while index < len(text):
    while index < len(text) and text[index].isspace(): index += 1
    if index >= len(text): break
    value, index = decoder.raw_decode(text, index); builder.update(value)
compared = {k: (ours[k] == builder[k]) for k in ours if k in builder}
print(json.dumps({'review_values': ours, 'equal_to_builder_identity_after': compared,
                  'all_shared_values_equal': all(compared.values()), 'only_in_review': sorted(set(ours) - set(builder))}, indent=1, sort_keys=True))
