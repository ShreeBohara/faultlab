"""Non-scoring comprehension probe for Phase 6 Part A.

Replays a saved completion-proposal context to a model and asks what the supplied
material permits. It creates no campaign, no study, no trial, no world and no
policy, and its output is never fed into any study, proposal context or evidence
bundle. It exists only to discriminate "the model does not know the op exists"
from "the model believes the brief forbids it".

The probe asks TWO questions. Q1 is open and mentions neither retries nor
notifications. Q2 names the behaviour directly and is therefore leading by
construction: the probe can report what a model knows and believes, never what it
would choose to propose.

Dry by default. `--execute-live` is required for any model call, and the caller
must pass `--confirm-entity` matching the configured W&B entity.

Usage:
  python scripts/experiments/comprehension_probe.py --plan
  python scripts/experiments/comprehension_probe.py --execute-live \\
      --confirm-entity ENTITY --model deepseek-ai/DeepSeek-V3.1 --out DIR
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.config import Settings                      # noqa: E402
from app.contracts.models import canonical_json, content_hash  # noqa: E402
from app.contracts.tokens import input_token_bound   # noqa: E402
from app.providers.runtime import RuntimeProvider    # noqa: E402

PROBE_SYSTEM = (
    'You are reading the exact reviewed material a FaultLab completion-policy proposer '
    'receives. This is a comprehension check, not a proposal request. Do NOT propose, '
    'design or output a policy, and do not use the policy output schema. Answer the two '
    'questions from the supplied material only. Quote the supplied text you rely on. '
    'Return JSON exactly of the form {"q1_ops": [...], "q1_explanation": string, '
    '"q2_permitted": "PERMITTED"|"FORBIDDEN"|"UNCLEAR", "q2_quote": string, '
    '"q2_explanation": string}.'
)

Q1 = ('Q1. Considering only the ops declared in the supplied output_schema, list every op '
      'that can cause the service to record a new operation, a new effect or a new receipt. '
      'For each one, state the hooks at which the supplied runtime_contract permits it.')
Q2 = ('Q2. Is a policy permitted to replay a write that the actor already dispatched in this '
      'episode? Quote the supplied text that settles it.')

# Phase 5 first-slot proposal inputs, by Mechanic model.
SAVED_CONTEXT = {
    'deepseek-ai/DeepSeek-V4-Pro-0813': 'completion-study-889f75d6d170418e9ff654f409a1952b-1',
    'deepseek-ai/DeepSeek-V3.1': 'completion-study-122d93e0dfa94c7484a46dd65b83aab2-1',
}
REPEATS = 2


def load_context(record_id: str) -> dict:
    """Read the saved proposal input read-only; never write to the store."""
    connection = sqlite3.connect(f"file:{ROOT / 'artifacts/lab.sqlite3'}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "select payload from records where kind='completion_proposal_inputs' and id=?",
            (record_id,)).fetchone()
    finally:
        connection.close()
    if not row:
        raise SystemExit(f'Saved proposal context {record_id} not found')
    return json.loads(row[0])


def build_messages(context: dict, *, with_brief: bool) -> list[dict]:
    from app.agents.mechanic import Mechanic  # noqa: F401  (import proves the path exists)
    brief = (ROOT / 'backend/app/agents/prompts/completion.md').read_text()
    payload = {'supplied_material': context, 'questions': [Q1, Q2]}
    if with_brief:
        payload['proposer_brief'] = brief
    return [{'role': 'system', 'content': PROBE_SYSTEM},
            {'role': 'user', 'content': canonical_json(payload)}]


def conditions(model: str, context: dict) -> list[dict]:
    plan = []
    for with_brief in (True, False):
        messages = build_messages(context, with_brief=with_brief)
        for repeat in range(REPEATS):
            plan.append({'model': model, 'with_brief': with_brief, 'repeat': repeat,
                         'messages': messages,
                         'input_token_bound': input_token_bound(messages, model),
                         'messages_hash': content_hash(messages)})
    return plan


async def run(plan: list[dict], settings: Settings, out: pathlib.Path) -> int:
    results = []
    async with RuntimeProvider(settings, live_authorized=True) as provider:
        for index, item in enumerate(plan, 1):
            record = {k: item[k] for k in
                      ('model', 'with_brief', 'repeat', 'input_token_bound', 'messages_hash')}
            try:
                generation = await provider.complete(
                    item['messages'], role='mechanic', max_output_tokens=2000, timeout_seconds=20)
                if generation.model_id != item['model']:
                    raise RuntimeError('Provider returned a different model')
                record.update(raw=generation.content, model_id=generation.model_id,
                              input_tokens=generation.input_tokens,
                              output_tokens=generation.output_tokens, error=None)
            except Exception as error:  # noqa: BLE001 - recorded, never silently dropped
                record.update(raw=None, error=type(error).__name__)
            results.append(record)
            brief = 'with-brief' if item['with_brief'] else 'no-brief'
            print(f"  [{index}/{len(plan)}] {item['model']} {brief} r{item['repeat']} "
                  f"-> {'ok' if record.get('raw') else record['error']}", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    target = out / ('probe-' + plan[0]['model'].split('/')[-1] + '.json')
    target.write_text(json.dumps({'schema_version': 'faultlab-comprehension-probe/v1',
                                  'scoring': 'NON_SCORING_NEVER_FED_BACK',
                                  'questions': [Q1, Q2], 'probe_system': PROBE_SYSTEM,
                                  'results': results}, indent=2) + '\n')
    used = sum(1 for r in results if r.get('raw') or r.get('error'))
    tokens_in = sum(r.get('input_tokens') or 0 for r in results)
    tokens_out = sum(r.get('output_tokens') or 0 for r in results)
    print(f'saved {target} | requests {used} | tokens {tokens_in} in / {tokens_out} out')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='deepseek-ai/DeepSeek-V3.1')
    parser.add_argument('--settings', default='artifacts/phase5-2026-09-20/settings-5a-mechanic-v4.json',
                        help='Non-secret override file; credentials still come from the root .env')
    parser.add_argument('--out', default='artifacts/phase6-2026-09-20')
    parser.add_argument('--plan', action='store_true', help='Print the plan and exit')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    args = parser.parse_args()

    record_id = SAVED_CONTEXT.get(args.model)
    if not record_id:
        raise SystemExit(f'No saved Phase 5 proposal context recorded for {args.model}')
    context = load_context(record_id)
    plan = conditions(args.model, context)
    print(f'model {args.model} | saved context {record_id} | {len(plan)} requests')
    for item in plan:
        print(f"  with_brief={item['with_brief']} repeat={item['repeat']} "
              f"admitted_input_tokens={item['input_token_bound']}")
    if args.plan or not args.execute_live:
        print('Dry plan only. Pass --execute-live --confirm-entity ENTITY to make model calls.')
        return 0

    # Apply the same non-secret overrides the live backend uses, then pin the
    # Mechanic role to the model under probe. Credentials stay in the root .env.
    import os
    overrides = json.loads((ROOT / args.settings).read_text())
    overrides['WANDB_MECHANIC_MODEL'] = args.model
    os.environ.update(overrides)
    settings = Settings.from_env()
    settings.require_wandb(require_model=True)
    if settings.model_for_role('mechanic') != args.model:
        raise SystemExit('Mechanic role does not resolve to the requested probe model')
    if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
        raise SystemExit('--confirm-entity must match the configured W&B entity')
    if any(item['input_token_bound'] > 32000 for item in plan):
        raise SystemExit('A probe request exceeds the frozen input bound')
    return asyncio.run(run(plan, settings, ROOT / args.out))


if __name__ == '__main__':
    raise SystemExit(main())
