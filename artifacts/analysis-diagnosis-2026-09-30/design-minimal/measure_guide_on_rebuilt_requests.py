"""Offline, $0: add the PROPOSED diagnosis_guide block to the five rebuilt native-v2 diagnosis requests and measure it.

Run from faultlab/backend with the project .venv:
  .venv/bin/python -B ../artifacts/analysis-diagnosis-2026-09-30/design-minimal/measure_guide_on_rebuilt_requests.py

Inputs (read only): inv-a's rebuilt requests (../inv-a/*-diagnosis-request.json). No store is opened, no provider or
network call is made (the fixer guard refuses the real .env and every non-loopback connection), nothing in the repo
outside this folder is written.

Checks per request:
  * the rebuilt user message is canonical JSON of its context (so adding a key and re-encoding changes nothing else);
  * after attach(): exactly one new key, every other key byte-identical, system prompt byte-identical;
  * where the block sorts in the canonical user message (keys are sorted);
  * frozen-tokenizer token count before and after, first turn and (where rebuilt) format-repair turn.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAULTLAB = HERE.parents[2]
sys.path.insert(0, str(FAULTLAB / 'artifacts' / 'product-mechanic-citations-2026-09-30' / 'fixer'))
import guard  # noqa: E402,F401

from app.contracts.models import canonical_json  # noqa: E402
from app.contracts.tokens import input_token_bound  # noqa: E402
from app.lab.loop_limits import COMPACTION_TARGET_TOKENS  # noqa: E402

spec = importlib.util.spec_from_file_location('proposed_diagnosis_guide', HERE / 'proposed_diagnosis_guide.py')
guide = importlib.util.module_from_spec(spec); spec.loader.exec_module(guide)

TASK_TEXT = 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'  # all four exports
NAMES = ['v2d-dev5', 'v2e-dev5', 'v2f-dev5', 'v2g-dev5', 'v2g-dev6']


def sha(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()


rows = []
for name in NAMES:
    saved = json.loads((HERE.parent / 'inv-a' / f'{name}-diagnosis-request.json').read_text())
    model = saved['mechanic_model']
    first = saved['turns'][0]['messages']
    system, user = first[0], first[1]
    context = json.loads(user['content'])
    assert canonical_json(context) == user['content'], name  # rebuilt user message is canonical JSON of its context
    guided = guide.attach(context, task_text=TASK_TEXT)
    assert set(guided) - set(context) == {guide.BLOCK}, name
    assert all(canonical_json(guided[k]) == canonical_json(context[k]) for k in context), name
    new_first = [system, {'role': 'user', 'content': canonical_json(guided)}]
    keys = sorted(guided)
    row = {'diagnosis': name, 'model': model, 'system_prompt_sha256': sha(system['content']),
           'block_key_position': keys.index(guide.BLOCK) + 1, 'keys_in_order': keys,
           'first_turn_tokens_before': input_token_bound(first, model),
           'first_turn_tokens_after': input_token_bound(new_first, model)}
    row['first_turn_tokens_added'] = row['first_turn_tokens_after'] - row['first_turn_tokens_before']
    row['after_below_compaction_target'] = row['first_turn_tokens_after'] <= COMPACTION_TARGET_TOKENS
    if len(saved['turns']) == 2:
        repair = saved['turns'][1]['messages']
        assert repair[:2] == first, name  # the repair turn repeats the first turn, then the answer and the error message
        new_repair = new_first + repair[2:]
        row['repair_turn_tokens_before'] = input_token_bound(repair, model)
        row['repair_turn_tokens_after'] = input_token_bound(new_repair, model)
        row['repair_turn_carries_block'] = guide.BLOCK in json.loads(new_repair[1]['content'])
        row['repair_turn_user_message'] = repair[3]['content']
    rows.append(row)

block_json = canonical_json(guide.block(TASK_TEXT))
summary = {
    'proposal': guide.DIAGNOSIS_GUIDE_V1,
    'block_characters': len(block_json),
    'block_sha256': sha(block_json),
    'declaration_sha256': sha(canonical_json(guide.declaration())),
    'system_prompts_identical_across_requests': len({r['system_prompt_sha256'] for r in rows}) == 1,
    'tokens_added_first_turn': sorted({r['first_turn_tokens_added'] for r in rows}),
    'max_first_turn_after': max(r['first_turn_tokens_after'] for r in rows),
    'compaction_target_tokens': COMPACTION_TARGET_TOKENS,
    'rows': rows,
    'block': guide.block(TASK_TEXT),
    'provider_calls': 0,
}
out = HERE / 'guide-measurement.json'
out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k not in ('rows', 'block')}, indent=2))
for r in rows:
    print(r['diagnosis'], 'pos', r['block_key_position'], 'first', r['first_turn_tokens_before'], '->',
          r['first_turn_tokens_after'], '(+%d)' % r['first_turn_tokens_added'],
          'repair', r.get('repair_turn_tokens_before'), '->', r.get('repair_turn_tokens_after'))
