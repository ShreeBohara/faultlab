"""Non-scoring probes for Phase 7 Part A: where does the repair get lost?

Replays a saved completion-proposal context and asks two questions that
discriminate visibility (H2) from the single-shot hand-off (H4).

  A1  Can the model see the failure at all? Names no op and no remedy.
  A2  Given a purely descriptive diagnosis built only from facts already in that
      evidence, does it emit the policy step?

Creates no campaign, no study, no trial, no world and no policy record. Nothing it
returns is ever entered into a study, scored against a world, given a policy
version, or cited as evidence that a repair works. A2's output in particular is
NOT a candidate.

Dry by default. `--execute-live` plus a matching `--confirm-entity` is required
for any model call.

Usage:
  python scripts/experiments/locate_loss_probe.py --plan
  python scripts/experiments/locate_loss_probe.py --execute-live \\
      --confirm-entity ENTITY --model deepseek-ai/DeepSeek-V3.1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.config import Settings                                  # noqa: E402
from app.contracts.models import canonical_json, content_hash    # noqa: E402
from app.contracts.tokens import input_token_bound               # noqa: E402
from app.providers.runtime import RuntimeProvider                # noqa: E402

SAVED_CONTEXT = {
    'deepseek-ai/DeepSeek-V4-Pro-0813': 'completion-study-889f75d6d170418e9ff654f409a1952b-1',
    'deepseek-ai/DeepSeek-V3.1': 'completion-study-122d93e0dfa94c7484a46dd65b83aab2-1',
}
REPEATS = 2

A1_SYSTEM = (
    'You are reading the exact reviewed development evidence a FaultLab completion-policy '
    'proposer receives. This is a comprehension check, not a proposal request. Do NOT '
    'propose, design or output a policy. Answer only from the supplied material and quote '
    'what you rely on. Return JSON exactly of the form '
    '{"accepted_by_service": "YES"|"NO"|"UNCLEAR", "error_codes": [...], '
    '"per_episode": [...], "explanation": string}.'
)
A1_QUESTION = (
    'For each failing episode in the supplied development evidence, state what happened to '
    'the notifications operation: was it ever accepted by the service, and what did the '
    'delivered responses say? Quote the error codes you find.'
)

# Purely descriptive. Every clause restates a fact already present in the supplied
# evidence. It names no op, no remedy and no desired behaviour.
A2_DIAGNOSIS = (
    'In the three failing episodes the actor dispatched one send_confirmation whose two '
    'transport attempts each returned a delivered TRANSIENT_UNAVAILABLE error. The service '
    'never recorded the notification operation, so no receipt exists. The actor then read '
    'the notification status repeatedly and reported truthfully that the outcome was '
    'unknown.'
)


def load_context(record_id: str) -> dict:
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


def messages_for(probe: str, context: dict) -> list[dict]:
    if probe == 'A1':
        payload = {'supplied_material': context, 'question': A1_QUESTION}
        return [{'role': 'system', 'content': A1_SYSTEM},
                {'role': 'user', 'content': canonical_json(payload)}]
    # A2 reproduces a real proposal request exactly - same brief, same context, same
    # output_schema the Mechanic appends (mechanic.py:15) - so the ONLY difference is
    # the descriptive diagnosis.
    from pydantic import TypeAdapter
    from app.contracts.models import MechanicOutput
    brief = (ROOT / 'backend/app/agents/prompts/completion.md').read_text()
    payload = {**context, 'observed_diagnosis': A2_DIAGNOSIS,
               'output_schema': TypeAdapter(MechanicOutput).json_schema()}
    return [{'role': 'system', 'content': brief},
            {'role': 'user', 'content': canonical_json(payload)}]


def plan_for(model: str, context: dict) -> list[dict]:
    plan = []
    for probe in ('A1', 'A2'):
        messages = messages_for(probe, context)
        for repeat in range(REPEATS):
            plan.append({'model': model, 'probe': probe, 'repeat': repeat, 'messages': messages,
                         'input_token_bound': input_token_bound(messages, model),
                         'messages_hash': content_hash(messages)})
    return plan


async def run(plan: list[dict], settings: Settings, out: pathlib.Path) -> int:
    results = []
    async with RuntimeProvider(settings, live_authorized=True) as provider:
        for index, item in enumerate(plan, 1):
            record = {k: item[k] for k in
                      ('model', 'probe', 'repeat', 'input_token_bound', 'messages_hash')}
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
            print(f"  [{index}/{len(plan)}] {item['probe']} r{item['repeat']} -> "
                  f"{'ok' if record.get('raw') else record['error']}", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    target = out / ('locate-' + plan[0]['model'].split('/')[-1] + '.json')
    target.write_text(json.dumps(
        {'schema_version': 'faultlab-locate-loss-probe/v1',
         'scoring': 'NON_SCORING_NEVER_FED_BACK',
         'a2_note': 'A2 output is not a candidate; it was never scored against a world.',
         'a1_question': A1_QUESTION, 'a2_diagnosis': A2_DIAGNOSIS,
         'results': results}, indent=2) + '\n')
    print(f'saved {target} | tokens '
          f"{sum(r.get('input_tokens') or 0 for r in results)} in / "
          f"{sum(r.get('output_tokens') or 0 for r in results)} out")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='deepseek-ai/DeepSeek-V3.1')
    parser.add_argument('--settings',
                        default='artifacts/phase5-2026-09-20/settings-5a-mechanic-v4.json')
    parser.add_argument('--out', default='artifacts/phase7-2026-09-20')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    args = parser.parse_args()

    record_id = SAVED_CONTEXT.get(args.model)
    if not record_id:
        raise SystemExit(f'No saved proposal context recorded for {args.model}')
    plan = plan_for(args.model, load_context(record_id))
    print(f'model {args.model} | saved context {record_id} | {len(plan)} requests')
    for item in plan:
        print(f"  {item['probe']} repeat={item['repeat']} "
              f"admitted_input_tokens={item['input_token_bound']}")
    if args.plan or not args.execute_live:
        print('Dry plan only. Pass --execute-live --confirm-entity ENTITY to make model calls.')
        return 0

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
