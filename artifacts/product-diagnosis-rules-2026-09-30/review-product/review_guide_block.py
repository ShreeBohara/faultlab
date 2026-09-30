"""Review check 3 ($0, offline): the Rule 2 block's content and size on the five saved requests.

Run from faultlab/backend:
  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/review-product/review_guide_block.py
"""
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402,F401

FAULTLAB = HERE.parents[2]
INPUTS = FAULTLAB / 'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs'
DRAFT = FAULTLAB / 'artifacts/analysis-diagnosis-2026-09-30/design-minimal/proposed_diagnosis_guide.py'
MEASURED = FAULTLAB / 'artifacts/analysis-diagnosis-2026-09-30/design-minimal/guide-measurement.json'
EXPORTS = {'v2d': 'native-v2d-run', 'v2e': 'native-v2e-run', 'v2f': 'native-v2f-run', 'v2g': 'native-v2g-run'}
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
NAMES = ('v2d-dev5', 'v2e-dev5', 'v2f-dev5', 'v2g-dev5', 'v2g-dev6')


def main():
    from app.agents.explorer import PUBLIC_INVARIANTS
    from app.contracts.models import canonical_json, content_hash
    from app.contracts.tokens import input_token_bound
    from app.lab import diagnosis_guide
    spec = importlib.util.spec_from_file_location('draft_guide', DRAFT)
    draft = importlib.util.module_from_spec(spec); spec.loader.exec_module(draft)
    measured = json.loads(MEASURED.read_text())
    out = {'draft_sha256': hashlib.sha256(DRAFT.read_bytes()).hexdigest()}
    task_texts = {}
    for run, folder in EXPORTS.items():
        export = json.loads((FAULTLAB / f'artifacts/product-live-2026-09-30/{folder}/export.json').read_text())
        task_texts[run] = {'plan_task_text': export['run_plan']['plan']['task_text'], 'campaign_task_text': export['campaign']['task_text']}
    out['task_texts'] = task_texts
    out['task_text_plan_equals_campaign'] = all(v['plan_task_text'] == v['campaign_task_text'] for v in task_texts.values())
    task = task_texts['v2g']['plan_task_text']
    ours, theirs = diagnosis_guide.block(task), draft.block(task)
    out['block_keys'] = list(ours)
    out['draft_block_keys'] = list(theirs)
    out['product_block_equals_draft_minus_checks_note'] = {k: v for k, v in theirs.items() if k != 'checks_note'} == ours
    out['draft_block_sha256_matches_saved_measurement'] = hashlib.sha256(canonical_json(theirs).encode()).hexdigest() == measured['block_sha256']
    out['checks_verbatim_public_invariants'] = ours['checks'] == dict(PUBLIC_INVARIANTS)
    declaration = diagnosis_guide.declaration()
    out['checks_hash_frozen'] = declaration['checks_hash'] == content_hash(PUBLIC_INVARIANTS) == content_hash(declaration['checks'])
    out['checks_hash'] = declaration['checks_hash']
    out['offered'] = diagnosis_guide.DIAGNOSIS_GUIDE_OFFERED
    out['dropped_checks_note_text'] = draft.CHECKS_NOTE
    # Which fixed sentences name a check id or talk about citations/labels (the verbatim C1-C8 meanings excluded).
    fixed = {'meaning': ours['meaning'], **{f'kinds.{k}': v for k, v in ours['kinds'].items()}, 'contract_note': ours['contract_note'],
             'use': ours['use'], 'hypothesis_length': ours['hypothesis_length']}
    out['fixed_text_naming_a_check'] = {k: v for k, v in fixed.items() if re.search(r'\bC[1-8]\b', v)}
    out['fixed_text_mentioning_citations_or_labels'] = {k: v for k, v in fixed.items() if re.search(r'citation|cite|label', v, re.I)}
    out['fixed_text_equals_memo_draft'] = {'meaning': ours['meaning'] == draft.MEANING, 'kinds': ours['kinds'] == draft.KINDS,
                                           'contract_note': ours['contract_note'] == draft.CONTRACT_NOTE, 'use': ours['use'] == draft.USE,
                                           'hypothesis_length': ours['hypothesis_length'] == draft.LENGTH}
    rows = {}
    for name in NAMES:
        saved = json.loads((INPUTS / f'{name}-diagnosis-request.json').read_text())
        first = saved['turns'][0]['messages']
        context = json.loads(first[1]['content'])
        run_task = task_texts[name.split('-')[0]]['plan_task_text']
        guided = diagnosis_guide.attach(context, task_text=run_task)
        with_draft = draft.attach(context, task_text=run_task)
        before = input_token_bound(first, MODEL)
        after = input_token_bound([first[0], {'role': 'user', 'content': canonical_json(guided)}], MODEL)
        draft_after = input_token_bound([first[0], {'role': 'user', 'content': canonical_json(with_draft)}], MODEL)
        rows[name] = {'before': before, 'product_after': after, 'product_added': after - before, 'draft_added': draft_after - before,
                      'checks_note_tokens': draft_after - after, 'only_one_key_added': set(guided) - set(context) == {'diagnosis_guide'},
                      'other_keys_byte_identical': all(canonical_json(guided[k]) == canonical_json(context[k]) for k in context),
                      'task_in_block': guided['diagnosis_guide']['task'], 'block_characters': len(canonical_json(guided['diagnosis_guide']))}
    out['rows'] = rows
    out['summary'] = {'product_added_tokens': sorted({r['product_added'] for r in rows.values()}),
                      'draft_added_tokens': sorted({r['draft_added'] for r in rows.values()}),
                      'checks_note_tokens': sorted({r['checks_note_tokens'] for r in rows.values()}),
                      'max_first_turn_with_guide': max(r['product_after'] for r in rows.values())}
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
