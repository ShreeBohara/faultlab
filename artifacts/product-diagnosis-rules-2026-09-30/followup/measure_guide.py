"""Follow-up stage ($0, offline): the restored checks_note's effect on the guide block, measured with the product's own code.

For each of the five saved probe inputs: first-turn input tokens (the frozen tokenizer) without the block, with this
build's block, and with the minimal design's prototype block; the declaration and block hashes. No store, no network.
"""
import hashlib, importlib.util, json
from pathlib import Path
from app.contracts.models import canonical_json, content_hash
from app.contracts.tokens import input_token_bound
from app.lab import diagnosis_guide

ROOT = Path('..').resolve()
INPUTS = ROOT / 'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
TASK = 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'
spec = importlib.util.spec_from_file_location('proto', ROOT / 'artifacts/analysis-diagnosis-2026-09-30/design-minimal/proposed_diagnosis_guide.py')
proto = importlib.util.module_from_spec(spec); spec.loader.exec_module(proto)
C6 = "C6 is the check of the report's citations: where C6 passed, that report's citations met it."
out = {'checks_note': diagnosis_guide.CHECKS_NOTE,
       'checks_note_equals_draft_minus_c6_sentence': proto.CHECKS_NOTE.replace(C6 + ' ', '') == diagnosis_guide.CHECKS_NOTE,
       'block_equals_draft_block_minus_c6_sentence': {**proto.block(TASK), 'checks_note': proto.CHECKS_NOTE.replace(C6 + ' ', '')} == diagnosis_guide.block(TASK),
       'declaration_hash': content_hash(diagnosis_guide.declaration()),
       'declaration_sha256_canonical': hashlib.sha256(canonical_json(diagnosis_guide.declaration()).encode()).hexdigest(),
       'block_sha256_canonical': hashlib.sha256(canonical_json(diagnosis_guide.block(TASK)).encode()).hexdigest(),
       'offered': diagnosis_guide.DIAGNOSIS_GUIDE_OFFERED, 'rows': []}
for name in ('v2d-dev5', 'v2e-dev5', 'v2f-dev5', 'v2g-dev5', 'v2g-dev6'):
    first = json.loads((INPUTS / f'{name}-diagnosis-request.json').read_text())['turns'][0]['messages']
    full = json.loads(first[1]['content'])
    count = lambda ctx: input_token_bound([first[0], {'role': 'user', 'content': canonical_json(ctx)}], MODEL)
    before = input_token_bound(first, MODEL)
    ours, theirs = count(diagnosis_guide.attach(full, task_text=TASK)), count(proto.attach(full, task_text=TASK))
    out['rows'].append({'request': name, 'first_turn_tokens': before, 'with_guide': ours, 'guide_delta': ours - before,
                        'prototype_delta': theirs - before})
print(json.dumps(out, indent=1))
