#!/usr/bin/env python3
"""Pre-registered request-only diagnosis probe (artifacts/analysis-diagnosis-2026-09-30/RECOMMENDATION.md, section 7).

Purpose. Measure, before any live episode is spent, whether the diagnosis guide block (Rule 2,
faultlab-diagnosis-guide/v1-kinds-and-checks, built but NOT offered) and the limit-stating repair turn (Rule 1 part 1a,
faultlab-mechanic-diagnosis/v1-repair-and-record) change the diagnosis Mechanic's answers. No episode runs, no store is
opened, no verdict is produced.

Inputs (pinned by sha256; read only):
  * the five rebuilt diagnosis requests of live runs v2d, v2e, v2f and v2g (dev-5 x4, dev-6 x1), exact bytes, copied from
    artifacts/analysis-diagnosis-2026-09-30/inv-a/ into artifacts/product-diagnosis-rules-2026-09-30/probe-inputs/;
  * each run's saved export (its frozen plan's task_text); run v2g's saved plan and configuration also give the frozen
    Mechanic model, sampling settings and per-call dollar bound (checked equal to the installed product's settings);
  * scripts/experiments/check_evidence_gap_misreading_v2.py (claim matches for P1).

Arms (K=10 per request per arm, interleaved; 140 calls in all):
  * CONTROL: each request's first turn exactly as sent;
  * GUIDE: the same first turn plus the Rule 2 block (app.lab.diagnosis_guide.attach, the campaign's own task text);
    every other key byte-identical;
  * repair sub-probe (v2f dev-5: its 743-character answer; v2g dev-5: its 614-character answer, each replayed as the
    assistant turn after the CONTROL first turn), then either today's repair message (REPAIR_TODAY, the saved bytes) or
    the Rule 1 message (REPAIR_RULE1, built with app.lab.diagnosis_protocol, exactly as the Mechanic builds it).
  Order: in round k (0..9) the 10 first-turn calls, then the 4 repair calls; within a round each pair of arms alternates
  its order (k + request index even: CONTROL first), so neither arm always goes first.

Charging. Every call goes through the product's own provider and ledger path: app.providers.runtime.RuntimeProvider
(role mechanic, max_output_tokens 2000, timeout 20 s, the product's frozen request settings), admitted and charged
BEFORE it is sent on an app.lab.budgets.CampaignLedger saved under the output folder, with the saved plan's per-call
dollar bound for the Mechanic (0.04984 $: 32,000 input + 2,000 output tokens at the frozen rates) and a hard cap of $8.
The 140 planned calls are reserved first (140 x 0.04984 = 6.9776 $); the product's one blind transport retry
(app.agents.transport_retry, connection error / timeout / HTTP 503 only) is charged from the rest of the cap only.

Modes:
  default (dry run)   builds every request, checks every pin, counts tokens with the frozen tokenizer and prints the
                      maximum charge. No network call, no provider, no .env read. --write-plan DIR writes the plan, the
                      exact request messages and a declaration template there.
  --execute-live      refuses unless --declaration FILE and --declaration-sha256 HEX are given, the file's sha256 is HEX,
                      and the declaration names this harness's sha256, the dry-run plan hash, the model, a cap of at most
                      $8, the approver, exactly this harness's pre-registered outcomes (the text declaration_template()
                      writes, so the hashed declaration states every counting rule below), the frozen temperature and how
                      repeated answers will be read, the checked preconditions (ledger checked, dashboard closed, no other
                      paid run, clock drift checked) and exactly the --out folder (which must be new or empty). Only then
                      are settings read and the provider built.
  --score DIR         (re)scores a live output folder; --review CSV adds the person's columns.

Outputs, written only under the output folder: plan.json, requests.json (the exact messages), answers.jsonl (every raw
answer, verbatim, with the model id the product's provider path returns: RuntimeProvider echoes the requested model, it
does not read a served-model field), probe-ledger.sqlite3, manifest.json, scoring.json, review-blinded.csv (blind to arm,
and without checker output or hints, so the person judges each hypothesis on its own) and review-key.json (arm labels).
The probe's ledger is its own: its charge is in no product campaign ledger or dashboard total, so the manifest's
charged_dollar_upper_bound must be added to the project's carried total by hand (manifest project_ledger_note).

Sampling. The frozen request settings send temperature 0; the declaration cannot change it (a different temperature needs a
reviewed harness change, a new harness sha256 and plan hash, and departs from the product's request path). Ten repeats of an
identical request may return identical answers, so scoring reports distinct raw answers and hypotheses per request key.

Scoring (section 7, written before any run; the counting choices this harness makes are stated here and in the
declaration's pre-registered outcomes):
  P1 (Rule 2 primary): on the four dev-5 requests, the share of first-turn hypotheses that blame citations, labels or
     evidence ids. A person marks every delivered row Y or N in review-blinded.csv without seeing the checker or the arm.
     Confirmed = a checker v2 claim match (counted, not denied) AND the person's Y. Pass: CONTROL confirmed >= 20 of 40
     AND GUIDE confirmed plus GUIDE rows the person marked Y without a checker match <= 4 of 40 (review finding MEDIUM-2:
     a rewording the checker misses counts against the GUIDE bar); CONTROL confirmed < 20 of 40 means the premise failed
     and the result is UNINFORMATIVE.
  P2 (Rule 2 guard): dev-5 first-attempt validity (the Mechanic's own schema and binding checks) in GUIDE is not lower
     than CONTROL by more than 5 of 40, and the over-600-character count is not higher by more than 5 of 40.
  P3 (Rule 2 secondary, counts and a one-sided Fisher test, no pass bar): dev-5 valid non-null requests GUIDE vs
     CONTROL; hypotheses naming confirmation-after-FAILED (C3) and the report inconsistency (C5) by the written rubric;
     dev-6 naming C4 rather than the unlabelled o3 (person-scored columns; automatic hints are only hints).
  P4 (Part 1a): share of repair turns returning a valid answer whose hypothesis has at most 600 characters. Pass: at
     least 9 of 10 on each setup with the Rule 1 message; today's message is measured alongside as the baseline. 'Worse'
     in the decision rule means the Rule 1 message's valid-within-600 total over both setups (of 20) is lower than
     today's total.
  proposed_kind is reported descriptively only.
Decision rule: Rule 1 ships after its offline tests unless P4 shows the new message is worse than today's; Rule 2 ships
only if P1 and P2 pass. If P1 fails, the next design trims the label text from diagnosis requests only. If P1 passes but
P3 shows declines unchanged, the Mechanic's veto persists and the gate question goes to the owner separately.

Usage (from the repository root, with the project venv and -B):
  .venv/bin/python -B scripts/experiments/diagnosis_probe.py
  .venv/bin/python -B scripts/experiments/diagnosis_probe.py --write-plan artifacts/<topic>/probe-plan
  .venv/bin/python -B scripts/experiments/diagnosis_probe.py --execute-live --out artifacts/<topic>/probe-live \\
      --declaration artifacts/<topic>/DECLARATION.json --declaration-sha256 HEX
  .venv/bin/python -B scripts/experiments/diagnosis_probe.py --score artifacts/<topic>/probe-live [--review CSV]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.util
import json
import math
import pathlib
import random
import re
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

SCHEMA = 'faultlab-diagnosis-probe/v1'
PLAN_SCHEMA = 'faultlab-diagnosis-probe-plan/v1'
DECLARATION_SCHEMA = 'faultlab-diagnosis-probe-declaration/v1'
SCORING_SCHEMA = 'faultlab-diagnosis-probe-scoring/v1'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
HARD_SPEND_CAP = 8.0
K = 10
MAX_OUTPUT_TOKENS = 2000        # the Mechanic's own call (app/agents/mechanic.py)
TIMEOUT_SECONDS = 20
LEDGER_ID = 'diagnosis-probe'
RESERVATION = 'probe-calls'

INPUT_DIR = 'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs'
INPUTS = {  # name -> sha256 of the rebuilt request file (identical to inv-a's copy)
    'v2d-dev5': '7cb9ac8c3338d49b59cde38b8cc58747e18a3073a56426b78b8a48228296d03d',
    'v2e-dev5': '905228fbdda067b467a8e1b0e9bf2807854c44720b4e4d1362eb718c53e6f655',
    'v2f-dev5': '4ab16a7e3665209fd015255c47a955e17a708e62c6fc3791f7f259fb72011672',
    'v2g-dev5': '098c2cda59979cd60e7f86b4dc41cc4382b787886e9e817447756167ac97e13b',
    'v2g-dev6': 'd76f2e4ad3f7ce7918b5a9b05cebfb62849281902a60962ca6fd530514fe287e',
}
REQUEST_RUN = {'v2d-dev5': 'v2d', 'v2e-dev5': 'v2e', 'v2f-dev5': 'v2f', 'v2g-dev5': 'v2g', 'v2g-dev6': 'v2g'}
EXPORTS = {  # run -> (saved export, sha256)
    'v2d': ('artifacts/product-live-2026-09-30/native-v2d-run/export.json', '6f83806413c934a1c869f1995cff87ff5aef0daf331a35e34a37de0b0893d0c8'),
    'v2e': ('artifacts/product-live-2026-09-30/native-v2e-run/export.json', '25d48347de9ad13281b6ec025ca58648c4836d091678be3d6fab9fe7b8ab163e'),
    'v2f': ('artifacts/product-live-2026-09-30/native-v2f-run/export.json', '77f223988079df99cb2f9f4ad65a12403ce2fe6dc805eef514861867d72a891d'),
    'v2g': ('artifacts/product-live-2026-09-30/native-v2g-run/export.json', 'b0b4db320908afb7d61d0c00fdc48d960cf3f3a002451f9ecc90e99acac397fc'),
}
SAMPLING_RUN = 'v2g'            # the last live run's saved plan gives the frozen Mechanic settings
DIAGNOSIS_PROMPT_SHA256 = '5488c7f5b1736002003d8dff9ba1774bbfd814572daa49de9dd222fea701a4e5'
CHECKER = ('scripts/experiments/check_evidence_gap_misreading_v2.py',
           '11920882f8c7e9885242e455b7c37e3e8f8649d3bb1c86b927d6da5c07be3b7b')
DEV5 = ('v2d-dev5', 'v2e-dev5', 'v2f-dev5', 'v2g-dev5')
DEV6 = ('v2g-dev6',)
FIRST_TURN_REQUESTS = DEV5 + DEV6
REPAIR_SETUPS = {'v2f-dev5': 743, 'v2g-dev5': 614}   # the saved attempt-0 hypothesis length of each
ARMS = ('CONTROL', 'GUIDE')
REPAIR_ARMS = ('REPAIR_TODAY', 'REPAIR_RULE1')
HYPOTHESIS_LIMIT = 600


class ProbeRefused(RuntimeError):
    """The probe refuses to plan or to run; nothing was sent."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def harness_sha256():
    return sha256_bytes(pathlib.Path(__file__).read_bytes())


def _pinned(root, relative, digest):
    path = pathlib.Path(root) / relative
    data = path.read_bytes()
    if sha256_bytes(data) != digest:
        raise ProbeRefused(f'{relative} is not the pinned file (sha256 {digest}); the probe refuses')
    return data


def load_checker(root=ROOT):
    """The misreading checker v2, run only if its bytes are the pinned ones (stdlib only; no app import)."""
    data = _pinned(root, *CHECKER)
    spec = importlib.util.spec_from_loader('faultlab_probe_misreading_checker_v2', loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(data, str(pathlib.Path(root) / CHECKER[0]), 'exec'), module.__dict__)
    return module


# ------------------------------------------------------------------------------------------------ validation (Mechanic)

def _bindings(result, context):
    """app/agents/mechanic.py Mechanic.diagnose validate_bindings, restated (a test checks it against the real Mechanic)."""
    errors = []
    if not set(result.evidence_ids) <= set(context.get('evidence_ids', [])):
        errors.append({'location': ['evidence_ids'], 'type': 'unknown_evidence_reference'})
    if result.requested_intervention_id is not None and result.requested_intervention_id not in set(context.get('intervention_ids', [])):
        errors.append({'location': ['requested_intervention_id'], 'type': 'unknown_intervention_reference'})
    return errors


def mechanic_errors(raw, context, *, rule1):
    """The errors the Mechanic computes for one answer (schema first, then bindings), today's form or Rule 1's."""
    from pydantic import TypeAdapter, ValidationError
    from app.contracts.models import DiagnosticProposal
    from app.lab import diagnosis_protocol
    try:
        result = TypeAdapter(DiagnosticProposal).validate_json(raw)
    except ValidationError as error:
        if rule1:
            return diagnosis_protocol.repair_errors(error)
        return [{'location': list(issue['loc']), 'type': issue['type']}
                for issue in error.errors(include_input=False, include_context=False, include_url=False)]
    return _bindings(result, context)


def parsed_answer(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


# ------------------------------------------------------------------------------------------------ the plan

def load_inputs(root=ROOT):
    return {name: json.loads(_pinned(root, f'{INPUT_DIR}/{name}-diagnosis-request.json', digest)) for name, digest in INPUTS.items()}


def load_exports(root=ROOT):
    return {run: json.loads(_pinned(root, path, digest)) for run, (path, digest) in EXPORTS.items()}


def frozen_sampling(export):
    """The Mechanic's model, request settings and per-call bound, read from a saved plan's frozen configuration."""
    from app.contracts.models import MODEL_INPUT_TOKEN_LIMIT, MODEL_OUTPUT_TOKEN_LIMIT, content_hash
    from app.providers.runtime import model_request_settings
    plan = export['run_plan']['plan']
    configuration = export['configuration']
    if content_hash(configuration) != plan['configuration_hash']:
        raise ProbeRefused('The saved configuration does not hash to its plan\'s configuration_hash')
    if configuration['models']['mechanic'] != MODEL or configuration['pricing']['mechanic']['model'] != MODEL:
        raise ProbeRefused('The saved plan\'s Mechanic model is not ' + MODEL)
    settings = configuration['model_settings_by_role']['mechanic']
    if settings != model_request_settings(MODEL):
        raise ProbeRefused('The installed product\'s request settings for the Mechanic model differ from the saved plan\'s')
    if settings['max_output_tokens'] != MAX_OUTPUT_TOKENS or settings['timeout_seconds'] != TIMEOUT_SECONDS:
        raise ProbeRefused('The saved plan\'s output or timeout limit differs from the Mechanic\'s call')
    pricing = configuration['pricing']['mechanic']
    bound = pricing['per_call_dollar_upper_bound']
    worst = (MODEL_INPUT_TOKEN_LIMIT * pricing['input_dollars_per_million'] + MODEL_OUTPUT_TOKEN_LIMIT * pricing['output_dollars_per_million']) / 1e6
    if not (isinstance(bound, (int, float)) and bound > 0 and bound + 1e-12 >= worst):
        raise ProbeRefused('The saved per-call bound does not cover a maximal Mechanic call')
    return {'source_run': SAMPLING_RUN, 'campaign_id': export['campaign_id'], 'plan_hash': plan['plan_hash'],
            'configuration_hash': plan['configuration_hash'], 'model': MODEL, 'request_settings': settings,
            'per_call_dollar_upper_bound': bound, 'input_dollars_per_million': pricing['input_dollars_per_million'],
            'output_dollars_per_million': pricing['output_dollars_per_million'], 'maximal_call_dollars': worst}


def build_messages(inputs, exports):
    """Every distinct request of the probe: {request_key: messages}, with its facts. Raises ProbeRefused on any mismatch."""
    from app.agents.mechanic import FORMAT_REPAIR_INSTRUCTION, PROMPTS
    from app.contracts.models import canonical_json
    from app.lab import diagnosis_guide, diagnosis_protocol
    prompt = (PROMPTS / 'diagnosis.md').read_text()
    if sha256_bytes(prompt.encode('utf-8')) != DIAGNOSIS_PROMPT_SHA256:
        raise ProbeRefused('prompts/diagnosis.md is not the prompt the saved requests were sent with')
    messages, facts = {}, {}
    for name in FIRST_TURN_REQUESTS:
        saved = inputs[name]
        if saved['mechanic_model'] != MODEL:
            raise ProbeRefused(f'{name}: saved Mechanic model differs')
        first = saved['turns'][0]['messages']
        system, user = first
        if system != {'role': 'system', 'content': prompt} or user['role'] != 'user':
            raise ProbeRefused(f'{name}: the saved first turn is not the diagnosis prompt plus one user message')
        context = json.loads(user['content'])
        if canonical_json(context) != user['content']:
            raise ProbeRefused(f'{name}: the saved user message is not canonical JSON')
        task_text = exports[REQUEST_RUN[name]]['run_plan']['plan']['task_text']
        guided = diagnosis_guide.attach(context, task_text=task_text)
        if set(guided) - set(context) != {diagnosis_guide.BLOCK} or any(canonical_json(guided[k]) != canonical_json(context[k]) for k in context):
            raise ProbeRefused(f'{name}: the guide changed more than one key')
        messages[f'{name}/CONTROL'] = first
        messages[f'{name}/GUIDE'] = [system, {'role': 'user', 'content': canonical_json(guided)}]
        facts[name] = {'task_text': task_text, 'campaign_id': saved['campaign_id'], 'request_id': saved['request_id']}
        if name in REPAIR_SETUPS:
            repair = saved['turns'][1]['messages']
            if repair[:2] != first or repair[2]['role'] != 'assistant':
                raise ProbeRefused(f'{name}: the saved repair turn does not start with the first turn and the answer')
            raw = repair[2]['content']
            hypothesis = (parsed_answer(raw) or {}).get('hypothesis')
            if not isinstance(hypothesis, str) or len(hypothesis) != REPAIR_SETUPS[name]:
                raise ProbeRefused(f'{name}: the replayed answer is not the {REPAIR_SETUPS[name]}-character one')
            today = first + [repair[2], {'role': 'user', 'content': canonical_json(
                {'validation_errors': mechanic_errors(raw, context, rule1=False), 'instruction': FORMAT_REPAIR_INSTRUCTION})}]
            if today != repair:
                raise ProbeRefused(f'{name}: today\'s repair turn, rebuilt, differs from the saved bytes')
            rule1 = first + [repair[2], {'role': 'user', 'content': diagnosis_protocol.repair_message(mechanic_errors(raw, context, rule1=True))}]
            messages[f'{name}/REPAIR_TODAY'] = repair
            messages[f'{name}/REPAIR_RULE1'] = rule1
            facts[name]['replayed_hypothesis_characters'] = len(hypothesis)
    return messages, facts


def schedule():
    """The 140 calls in order: per round, 10 first-turn calls then 4 repair calls, with alternating arm order."""
    calls = []
    for round_index in range(K):
        for index, name in enumerate(FIRST_TURN_REQUESTS):
            for arm in (ARMS if (round_index + index) % 2 == 0 else tuple(reversed(ARMS))):
                calls.append({'round': round_index, 'turn': 'first', 'request': name, 'arm': arm, 'request_key': f'{name}/{arm}'})
        for index, name in enumerate(REPAIR_SETUPS):
            for arm in (REPAIR_ARMS if (round_index + index) % 2 == 0 else tuple(reversed(REPAIR_ARMS))):
                calls.append({'round': round_index, 'turn': 'repair', 'request': name, 'arm': arm, 'request_key': f'{name}/{arm}'})
    for index, call in enumerate(calls):
        call['call_index'] = index
    return calls


def build_plan(root=ROOT):
    """(plan, messages): every request built and checked, token counts and the maximum charge. No network, no store."""
    from app.contracts.models import MODEL_INPUT_TOKEN_LIMIT, content_hash
    from app.contracts.tokens import input_token_bound
    from app.lab import diagnosis_guide, diagnosis_protocol
    inputs, exports = load_inputs(root), load_exports(root)
    sampling = frozen_sampling(exports[SAMPLING_RUN])
    messages, facts = build_messages(inputs, exports)
    requests = {}
    for key, value in messages.items():
        name, arm = key.split('/')
        tokens = input_token_bound(value, MODEL)
        if tokens > MODEL_INPUT_TOKEN_LIMIT:
            raise ProbeRefused(f'{key}: {tokens} input tokens exceed the {MODEL_INPUT_TOKEN_LIMIT} limit')
        requests[key] = {'request': name, 'arm': arm, 'turn': 'repair' if arm.startswith('REPAIR') else 'first',
                         'messages_sha256': content_hash(value), 'input_tokens': tokens, 'messages': len(value)}
    calls = schedule()
    bound = sampling['per_call_dollar_upper_bound']
    planned = len(calls)
    tighter = sum(requests[c['request_key']]['input_tokens'] * sampling['input_dollars_per_million']
                  + MAX_OUTPUT_TOKENS * sampling['output_dollars_per_million'] for c in calls) / 1e6
    counts = {'first_turn_calls': sum(c['turn'] == 'first' for c in calls), 'repair_calls': sum(c['turn'] == 'repair' for c in calls),
              'total_calls': planned, 'per_request_per_arm': K}
    by_key = {}
    for c in calls: by_key[c['request_key']] = by_key.get(c['request_key'], 0) + 1
    counts['calls_per_request_key'] = by_key
    plan = {'schema_version': PLAN_SCHEMA, 'harness': 'scripts/experiments/diagnosis_probe.py', 'harness_sha256': harness_sha256(),
            'model': MODEL, 'sampling': sampling, 'k': K,
            'inputs': {name: {'file': f'{INPUT_DIR}/{name}-diagnosis-request.json', 'sha256': digest, **facts[name]}
                       for name, digest in INPUTS.items()},
            'exports': {run: {'file': path, 'sha256': digest} for run, (path, digest) in EXPORTS.items()},
            'checker': {'file': CHECKER[0], 'sha256': CHECKER[1]}, 'diagnosis_prompt_sha256': DIAGNOSIS_PROMPT_SHA256,
            'diagnosis_guide': {'protocol': diagnosis_guide.DIAGNOSIS_GUIDE_V1, 'declaration_hash': content_hash(diagnosis_guide.declaration()),
                                'offered': diagnosis_guide.DIAGNOSIS_GUIDE_OFFERED},
            'mechanic_diagnosis': {'protocol': diagnosis_protocol.MECHANIC_DIAGNOSIS_V1,
                                   'declaration_hash': content_hash(diagnosis_protocol.declaration()),
                                   'semantics_hash': diagnosis_protocol.semantics_hash()},
            'requests': requests, 'schedule': calls, 'counts': counts,
            'charge': {'path': 'app.providers.runtime.RuntimeProvider + app.lab.budgets.CampaignLedger (admitted before sending)',
                       'per_call_dollar_upper_bound': bound, 'planned_calls': planned,
                       'max_charge_dollars': round(planned * bound, 6), 'hard_spend_cap_dollars': HARD_SPEND_CAP,
                       'tighter_bound_dollars': round(tighter, 6),
                       'retry_rule': 'app.agents.transport_retry v1: at most one blind retry per call, only after a connection '
                                     'error, a timeout or HTTP 503, charged before it is sent from the cap left after the '
                                     'planned calls are reserved'},
            'network_calls': 0}
    plan['plan_hash'] = content_hash({k: v for k, v in plan.items() if k != 'plan_hash'})
    if plan['charge']['max_charge_dollars'] > HARD_SPEND_CAP:
        raise ProbeRefused('The planned calls exceed the hard cap at the per-call bound')
    return plan, messages


def check_budget(plan, spend_cap):
    if not (type(spend_cap) in (int, float) and math.isfinite(spend_cap) and 0 < spend_cap <= HARD_SPEND_CAP):
        raise ProbeRefused(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    if plan['charge']['planned_calls'] * plan['charge']['per_call_dollar_upper_bound'] > spend_cap + 1e-9:
        raise ProbeRefused(f'{plan["charge"]["planned_calls"]} planned calls exceed the ${spend_cap:.2f} cap at the per-call bound')


# The pre-registered outcomes exactly as this harness scores them (review findings F5 and MEDIUM-2, fixer). A declaration must
# carry this text unchanged, so the hashed declaration states every counting rule; another rule needs a harness change.
PRE_REGISTERED_OUTCOMES = {
    'P1': ('dev-5 first-turn hypotheses that blame citations, labels or evidence ids. A person marks every delivered dev-5 row '
           'Y or N in review-blinded.csv without seeing the checker or the arm. Confirmed = a checker v2 claim match AND the '
           'person\'s Y. Pass if CONTROL confirmed >= 20 of 40 AND GUIDE confirmed plus GUIDE rows the person marked Y '
           'without a checker match (these are counted against the GUIDE bar) <= 4 of 40; CONTROL confirmed < 20 of 40 is '
           'UNINFORMATIVE (the premise failed).'),
    'P2': ('dev-5 first-attempt validity in GUIDE not lower than CONTROL by more than 5 of 40; over-600 count not higher by '
           'more than 5 of 40.'),
    'P3': ('counts and a one-sided Fisher test, no pass bar: valid non-null requests; C3 and C5 naming by the written rubric '
           '(person-scored); dev-6 naming C4 rather than o3.'),
    'P4': ('repair turns returning a valid answer with a hypothesis of at most 600 characters: pass if at least 9 of 10 on '
           'each setup with the Rule 1 message; today\'s message measured as the baseline. For the decision rule, \'worse\' '
           'means the Rule 1 message\'s valid-within-600 total over both setups (of 20) is lower than today\'s total.'),
    'repeats': ('The frozen temperature is 0. Scoring reports, per request key, the delivered answers, the distinct raw answers '
                'and the distinct hypotheses; the declaration\'s sampling.repeats_reading says how repeated answers are read.'),
    'decision_rule': ('Rule 1 ships after its offline tests unless P4 shows the new message is worse than today\'s. Rule 2 ships '
                      'only if P1 and P2 pass. If P1 fails, the next design trims the label text from diagnosis requests '
                      'only. If P1 passes but P3 shows declines unchanged, the Mechanic\'s veto persists and the gate question '
                      'goes to the owner separately.'),
}
PRECONDITIONS = ('ledger_checked', 'dashboard_closed', 'no_other_paid_run', 'clock_drift_checked')
AFTER_RUN = ('Add manifest.json ledger.charged_dollar_upper_bound (the conservative figure) and '
             'estimated_actual_dollars_from_reported_tokens to the project ledger\'s carried total; the probe\'s own ledger '
             '(probe-ledger.sqlite3) is in no product campaign ledger or dashboard total.')


def frozen_temperature(plan):
    return plan['sampling']['request_settings']['temperature']


def declaration_template(plan, out_folder='<the --out folder, resolved>'):
    return {'schema_version': DECLARATION_SCHEMA, 'harness_sha256': plan['harness_sha256'], 'plan_hash': plan['plan_hash'],
            'model': MODEL, 'spend_cap_dollars': HARD_SPEND_CAP, 'output_folder': out_folder, 'approved_by': '',
            'pre_registered_outcomes': dict(PRE_REGISTERED_OUTCOMES),
            # The harness sends the frozen temperature; the declaration only confirms it and says how repeats are read.
            'sampling': {'temperature': frozen_temperature(plan), 'repeats_reading': ''},
            'preconditions': {name: False for name in PRECONDITIONS},
            'after_run': AFTER_RUN}


def verify_declaration(path, expected_sha256, plan, out):
    """The parsed declaration, or ProbeRefused. Nothing is read from settings and nothing is sent before this passes."""
    if not path or not expected_sha256:
        raise ProbeRefused('--execute-live needs --declaration FILE and --declaration-sha256 HEX')
    path = pathlib.Path(path)
    if not path.is_file():
        raise ProbeRefused(f'No declaration file at {path}')
    data = path.read_bytes()
    if sha256_bytes(data) != str(expected_sha256).lower():
        raise ProbeRefused('The declaration\'s sha256 differs from --declaration-sha256')
    try:
        value = json.loads(data)
    except ValueError:
        raise ProbeRefused('The declaration is not JSON') from None
    if not isinstance(value, dict) or value.get('schema_version') != DECLARATION_SCHEMA:
        raise ProbeRefused('The declaration is not a ' + DECLARATION_SCHEMA + ' object')
    if value.get('harness_sha256') != plan['harness_sha256'] or value.get('plan_hash') != plan['plan_hash'] or value.get('model') != MODEL:
        raise ProbeRefused('The declaration names another harness, plan or model')
    cap = value.get('spend_cap_dollars')
    check_budget(plan, cap)
    if value.get('output_folder') != str(pathlib.Path(out).resolve()):
        raise ProbeRefused('The declaration names another output folder')
    if not isinstance(value.get('approved_by'), str) or not value['approved_by'].strip():
        raise ProbeRefused('The declaration names no approver')
    outcomes = value.get('pre_registered_outcomes')
    if outcomes != PRE_REGISTERED_OUTCOMES:
        raise ProbeRefused('The declaration does not state exactly this harness\'s pre-registered outcomes P1-P4, the repeats '
                           'report and the decision rule (copy them from the template)')
    sampling = value.get('sampling')
    if not isinstance(sampling, dict) or type(sampling.get('temperature')) not in (int, float) or sampling['temperature'] != frozen_temperature(plan):
        raise ProbeRefused(f'The declaration must name the temperature the harness sends ({frozen_temperature(plan)}, frozen from the saved plan)')
    if not isinstance(sampling.get('repeats_reading'), str) or not sampling['repeats_reading'].strip():
        raise ProbeRefused('The declaration does not say how repeated answers will be read (sampling.repeats_reading)')
    preconditions = value.get('preconditions')
    if not isinstance(preconditions, dict) or not all(preconditions.get(k) is True for k in PRECONDITIONS):
        raise ProbeRefused('The declaration does not confirm the preconditions (ledger checked, dashboard closed, no other paid '
                           'run, clock drift checked)')
    out = pathlib.Path(out)
    if out.exists() and any(out.iterdir()):
        raise ProbeRefused('The output folder is not empty; a probe run is never repeated into it')
    return value


# ------------------------------------------------------------------------------------------------ the live run

def _now():
    return datetime.now(timezone.utc).isoformat()


def _write_json(path, value):
    pathlib.Path(path).write_text(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + '\n')


async def execute(plan, messages, out, provider, *, spend_cap=HARD_SPEND_CAP, declaration_sha256=None):
    """Send the planned calls through the product's provider and ledger path; returns the manifest.

    Every call is admitted and charged on the ledger before it is sent; a refused admission stops the run. Every answer
    is appended verbatim to answers.jsonl as soon as it arrives. Writes only under out.
    """
    from app.agents.transport_retry import charge_ledger_retry, complete_with_one_retry, retry_payload
    from app.contracts.models import CampaignBudget, MODEL_INPUT_TOKEN_LIMIT, MODEL_OUTPUT_TOKEN_LIMIT, content_hash
    from app.contracts.tokens import validate_model_input
    from app.lab.budgets import BudgetExhausted, CampaignLedger, StopRequested
    from app.lab.storage import LabStore
    from app.providers.runtime import RuntimeProviderError
    check_budget(plan, spend_cap)
    out = pathlib.Path(out)
    if out.exists() and any(out.iterdir()):
        raise ProbeRefused('The output folder is not empty; a probe run is never repeated into it')
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / 'plan.json', plan)
    _write_json(out / 'requests.json', messages)      # the exact messages, so a later --score needs no rebuild
    bound = plan['charge']['per_call_dollar_upper_bound']
    planned = len(plan['schedule'])
    retries_allowed = int((spend_cap - planned * bound + 1e-9) // bound)
    calls_cap = planned + retries_allowed
    store = LabStore(out / 'probe-ledger.sqlite3')
    manifest = {'schema_version': SCHEMA, 'status': 'RUNNING', 'started_at': _now(), 'plan_hash': plan['plan_hash'],
                'harness_sha256': plan['harness_sha256'], 'declaration_sha256': declaration_sha256, 'model': MODEL,
                'spend_cap_dollars': spend_cap, 'per_call_dollar_upper_bound': bound, 'planned_calls': planned,
                'retry_calls_allowed_by_cap': retries_allowed, 'project_ledger_note': AFTER_RUN.replace('manifest.json ', '')}
    _write_json(out / 'manifest.json', manifest)
    ledger = None
    delivered = failed_calls = 0
    stop_reason = None
    try:
        ledger = CampaignLedger(store, LEDGER_ID, CampaignBudget(model_calls=calls_cap, tokens=calls_cap * (MODEL_INPUT_TOKEN_LIMIT + MODEL_OUTPUT_TOKEN_LIMIT),
                                                                 dollars=spend_cap),
                                dollar_bounds={'actor': bound, 'explorer': bound, 'mechanic': bound})
        for name in list(ledger.reservations):   # a probe has no protected campaign work (final audit, portability, ...)
            ledger.release(name)
        ledger.reserve(RESERVATION, planned)
        with open(out / 'answers.jsonl', 'a', encoding='utf-8') as answers:
            for call in plan['schedule']:
                request = plan['requests'][call['request_key']]
                sent = messages[call['request_key']]
                if content_hash(sent) != request['messages_sha256']:
                    raise ProbeRefused(f'{call["request_key"]}: messages differ from the plan')
                validate_model_input(sent, MODEL)
                try:
                    ledger.consume_call(reservation=RESERVATION, role='mechanic')
                except (BudgetExhausted, StopRequested) as error:
                    stop_reason = f'LEDGER_REFUSED: {error}'
                    break
                failures = []

                async def send(retry, sent=sent):
                    return await provider.complete(sent, role='mechanic', max_output_tokens=MAX_OUTPUT_TOKENS, timeout_seconds=TIMEOUT_SECONDS)

                def failed(error):
                    if error.generation is not None:
                        ledger.reconcile(error.generation)
                    failures.append(error.diagnostics)
                    return f'failure-{call["call_index"]}-{len(failures)}'

                def record(error, failure_id):
                    return {'failure_id': failure_id, **retry_payload(error)}

                row = {**call, 'request_messages_sha256': request['messages_sha256'], 'sent_at': _now()}
                try:
                    generation, retries = await complete_with_one_retry(
                        send, failed=failed, admit=lambda: charge_ledger_retry(ledger, 'mechanic'), record=record)
                except RuntimeProviderError as error:
                    failed_calls += 1
                    answers.write(json.dumps({**row, 'delivered': False, 'error': error.diagnostics, 'failures': failures,
                                              'finished_at': _now()}, sort_keys=True, ensure_ascii=False) + '\n')
                    answers.flush()
                    continue
                ledger.reconcile(generation)
                # model_id: what the product's provider path returns (RuntimeProvider echoes the requested model; it does not
                # read a served-model field from the response), as the Mechanic's own mechanic_outputs records it.
                answers.write(json.dumps({**row, 'delivered': True, 'raw': generation.content, 'model_id': generation.model_id,
                                          'input_tokens': generation.input_tokens, 'output_tokens': generation.output_tokens,
                                          'transport_retries': retries, 'failures': failures, 'finished_at': _now()},
                                         sort_keys=True, ensure_ascii=False) + '\n')
                answers.flush()
                delivered += 1
                if generation.model_id != MODEL:
                    stop_reason = 'MODEL_ID_DIFFERS'
                    break
        manifest['status'] = 'COMPLETED' if stop_reason is None else 'STOPPED'
    except BaseException as error:
        manifest['status'] = 'ABORTED'
        manifest['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        manifest['stop_reason'] = stop_reason
        manifest['finished_at'] = _now()
        manifest['delivered_answers'] = delivered
        manifest['failed_calls'] = failed_calls
        if ledger is not None:
            manifest['ledger'] = {'charged_calls': ledger.used_calls, 'charged_dollar_upper_bound': round(ledger.used_dollar_upper_bound, 6),
                                  'measured_input_tokens': ledger.measured_input, 'measured_output_tokens': ledger.measured_output}
            sampling = plan['sampling']
            manifest['estimated_actual_dollars_from_reported_tokens'] = round(
                (ledger.measured_input * sampling['input_dollars_per_million'] + ledger.measured_output * sampling['output_dollars_per_million']) / 1e6, 6)
        store.close()
        _write_json(out / 'manifest.json', manifest)
    return manifest


# ------------------------------------------------------------------------------------------------ scoring

RUBRIC = {
    'c3_confirmation_after_failed': 'Names, as a cause, that the agent sent or recorded a confirmation although the upgrade '
                                    'had failed or been rejected (a delivered FAILED receipt): check C3.',
    'c5_report_inconsistency': 'Names, as a cause, that the final report is inconsistent with or untruthful about the '
                               'delivered evidence (for example it claims a success or an outcome the receipts contradict): C5.',
    'dev6_names_c4': 'dev-6 only: names more than one confirmation effect (a duplicate or second confirmation) as the failure: C4.',
    'dev6_blames_o3': 'dev-6 only: blames the unlabelled observation o3 (the hidden first attempt, or citing an unshown row).',
}
HINTS = {
    'c3_confirmation_after_failed': re.compile(r'\bC3\b|confirm\w*[^.]{0,80}(?:fail|reject)|(?:fail|reject)\w*[^.]{0,80}confirm', re.I),
    'c5_report_inconsistency': re.compile(r'\bC5\b|report[^.]{0,80}(?:inconsisten|untruth|contradict|misreport|false)', re.I),
    'dev6_names_c4': re.compile(r'\bC4\b|duplicate|second confirmation|two confirmations|more than one confirmation', re.I),
    'dev6_blames_o3': re.compile(r'\bo3\b', re.I),
}
# The person's review file: blind to arm, and without the checker's matches or the automatic hints (review finding MEDIUM-2,
# fixer), so a Y or N is the person's own reading; the checker's matches and the hints are in scoring.json only.
REVIEW_COLUMNS = ('blinded_id', 'request', 'hypothesis', 'human_blames_citations_labels_or_evidence_ids',
                  'human_c3_confirmation_after_failed', 'human_c5_report_inconsistency', 'human_dev6_names_c4',
                  'human_dev6_blames_o3')


def fisher_one_sided_greater(a, n1, c, n2):
    """P(X >= a) for the first row's successes under the hypergeometric null (one-sided Fisher exact test)."""
    total, successes = n1 + n2, a + c
    if total == 0 or n1 == 0:
        return None
    denominator = math.comb(total, successes)
    top = min(n1, successes)
    return sum(math.comb(n1, x) * math.comb(n2, successes - x) for x in range(a, top + 1)) / denominator


def _answers(out):
    path = pathlib.Path(out) / 'answers.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []


def _contexts(messages):
    return {key: json.loads(value[1]['content']) for key, value in messages.items()}


def score(out, *, plan=None, messages=None, review=None, root=ROOT):
    """Write scoring.json (and, once, review-blinded.csv and review-key.json) under out; returns the scoring."""
    out = pathlib.Path(out)
    plan = plan or json.loads((out / 'plan.json').read_text())
    if messages is None and (out / 'requests.json').exists():
        from app.contracts.models import content_hash
        messages = json.loads((out / 'requests.json').read_text())
        if any(content_hash(messages.get(key)) != request['messages_sha256'] for key, request in plan['requests'].items()):
            raise ProbeRefused('requests.json does not match the plan that was sent')
    if messages is None:
        rebuilt, messages = build_plan(root)
        if rebuilt['plan_hash'] != plan['plan_hash']:
            raise ProbeRefused('The installed code rebuilds another plan; score with the plan and messages that were sent')
    checker = load_checker(root)
    contexts = _contexts(messages)
    rows = []
    for answer in _answers(out):
        context = contexts[answer['request_key']]
        row = {key: answer[key] for key in ('call_index', 'round', 'turn', 'request', 'arm', 'request_key', 'delivered')}
        if answer['delivered']:
            raw = answer['raw']
            row['raw'] = raw
            errors = mechanic_errors(raw, context, rule1=False)
            parsed = parsed_answer(raw) or {}
            hypothesis = checker._hypothesis(raw)
            counted, denied = checker.claim_matches(hypothesis)
            row.update(valid=not errors, validation_errors=errors, hypothesis=hypothesis,
                       hypothesis_characters=len(parsed['hypothesis']) if isinstance(parsed.get('hypothesis'), str) else None,
                       proposed_kind=parsed.get('proposed_kind'), requested_intervention_id=parsed.get('requested_intervention_id'),
                       auto_claim_matches=counted, auto_denied_matches=denied,
                       hints={name: bool(pattern.search(hypothesis)) for name, pattern in HINTS.items()})
            row['over_limit'] = row['hypothesis_characters'] is not None and row['hypothesis_characters'] > HYPOTHESIS_LIMIT
        rows.append(row)
    first = [r for r in rows if r['turn'] == 'first']
    rng = random.Random(int(plan['plan_hash'][:16], 16))
    order = list(range(len(first)))
    rng.shuffle(order)
    blinded = {first[i]['call_index']: f'h{position + 1:03d}' for position, i in enumerate(order)}
    human = _read_review(review) if review else {}
    for row in first:
        row['blinded_id'] = blinded[row['call_index']]
        row['human'] = human.get(row['blinded_id'], {})
    review_path, key_path = out / 'review-blinded.csv', out / 'review-key.json'
    if not review_path.exists():
        with open(review_path, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
            writer.writeheader()
            for position in order:
                row = first[position]
                if not row['delivered']: continue
                writer.writerow({'blinded_id': row['blinded_id'], 'request': row['request'], 'hypothesis': row['hypothesis']})
    if not key_path.exists():
        _write_json(key_path, {'plan_hash': plan['plan_hash'], 'seed': plan['plan_hash'][:16],
                               'key': {row['blinded_id']: {'arm': row['arm'], 'request': row['request'], 'call_index': row['call_index']} for row in first}})
    scoring = {'schema_version': SCORING_SCHEMA, 'plan_hash': plan['plan_hash'], 'checker_version': checker.CHECKER_VERSION,
               'rubric': RUBRIC, 'human_review_file': review_path.name, 'human_review_applied': bool(review),
               'answers': len(rows), 'delivered': sum(r['delivered'] for r in rows),
               'repeats': _repeats(rows, plan),
               'P1': _p1(first), 'P2': _p2(first), 'P3': _p3(first), 'P4': _p4([r for r in rows if r['turn'] == 'repair']),
               'proposed_kind_descriptive': _kinds(first),
               'decision_rule': PRE_REGISTERED_OUTCOMES['decision_rule'],
               'rows': rows}
    _write_json(out / 'scoring.json', scoring)
    return scoring


def _read_review(path):
    with open(path, newline='', encoding='utf-8') as handle:
        return {row['blinded_id']: {k: (row.get(k) or '').strip().upper() for k in REVIEW_COLUMNS if k.startswith('human_')}
                for row in csv.DictReader(handle)}


def _dev5(rows, arm):
    return [r for r in rows if r['request'] in DEV5 and r['arm'] == arm]


def _distinct(rows, field):
    return len({r[field] for r in rows if r['delivered']})


def _repeats(rows, plan):
    """Distinct answers per request key (review finding MEDIUM-3 / F1): at temperature 0, ten repeats may be one answer."""
    table = {}
    for key in plan['requests']:
        keyed = [r for r in rows if r['request_key'] == key]
        table[key] = {'delivered': sum(r['delivered'] for r in keyed), 'distinct_raw_answers': _distinct(keyed, 'raw'),
                      'distinct_hypotheses': _distinct(keyed, 'hypothesis')}
    single = sum(1 for row in table.values() if row['delivered'] and row['distinct_raw_answers'] == 1)
    return {'temperature': frozen_temperature(plan), 'by_request_key': table, 'keys_with_one_distinct_answer': single,
            'request_keys': len(table),
            'note': ('A request key whose delivered answers are all identical is one sample repeated, not ten independent '
                     'samples; read the P1-P4 counts with the distinct counts beside them.')}


def _p1(first):
    result = {'measure': 'dev-5 first-turn hypotheses with a checker v2 claim match confirmed by a person (Y)', 'arms': {}}
    complete = True
    for arm in ARMS:
        rows = _dev5(first, arm)
        delivered = [r for r in rows if r['delivered']]
        matched = [r for r in delivered if r['auto_claim_matches']]
        reviewed = [r for r in delivered if r['human'].get('human_blames_citations_labels_or_evidence_ids') in ('Y', 'N')]
        confirmed = [r for r in matched if r['human'].get('human_blames_citations_labels_or_evidence_ids') == 'Y']
        person_only = [r for r in delivered if not r['auto_claim_matches'] and r['human'].get('human_blames_citations_labels_or_evidence_ids') == 'Y']
        # GUIDE: a row the person flags without a checker match counts against the bar (review finding MEDIUM-2, fixer);
        # CONTROL's premise counts confirmed rows only. Both choices make a PASS harder, never easier.
        counted = len(confirmed) + (len(person_only) if arm == 'GUIDE' else 0)
        result['arms'][arm] = {'planned': len(rows), 'delivered': len(delivered), 'auto_matched': len(matched),
                               'person_reviewed': len(reviewed), 'confirmed': len(confirmed),
                               'person_flagged_without_auto_match': len(person_only), 'counted_against_bar': counted,
                               'distinct_hypotheses': _distinct(rows, 'hypothesis') if delivered else 0}
        complete = complete and len(delivered) == 40 and len(reviewed) == len(delivered)
    control, guide = result['arms']['CONTROL'], result['arms']['GUIDE']
    result['rule'] = PRE_REGISTERED_OUTCOMES['P1']
    if not complete:
        result['status'] = 'PENDING_HUMAN_CONFIRMATION' if control['delivered'] == guide['delivered'] == 40 else 'INCOMPLETE'
        result['provisional_from_auto_matches'] = {'guide_at_most_4': guide['auto_matched'] <= 4, 'control_at_least_20': control['auto_matched'] >= 20}
    elif control['confirmed'] < 20:
        result['status'] = 'UNINFORMATIVE'
    else:
        result['status'] = 'PASS' if guide['counted_against_bar'] <= 4 else 'FAIL'
    return result


def _p2(first):
    result = {'measure': 'dev-5 first-attempt validity and over-600 counts', 'arms': {}}
    for arm in ARMS:
        delivered = [r for r in _dev5(first, arm) if r['delivered']]
        result['arms'][arm] = {'delivered': len(delivered), 'valid': sum(r['valid'] for r in delivered),
                               'over_600': sum(r['over_limit'] for r in delivered),
                               'distinct_raw_answers': _distinct(delivered, 'raw') if delivered else 0}
    control, guide = result['arms']['CONTROL'], result['arms']['GUIDE']
    if control['delivered'] != 40 or guide['delivered'] != 40:
        result['status'] = 'INCOMPLETE'
    else:
        result['status'] = 'PASS' if guide['valid'] >= control['valid'] - 5 and guide['over_600'] <= control['over_600'] + 5 else 'FAIL'
    return result


def _p3(first):
    arms = {}
    for arm in ARMS:
        delivered = [r for r in _dev5(first, arm) if r['delivered']]
        dev6 = [r for r in first if r['request'] in DEV6 and r['arm'] == arm and r['delivered']]
        arms[arm] = {'dev5_delivered': len(delivered),
                     'dev5_valid_requested': sum(r['valid'] and r['requested_intervention_id'] is not None for r in delivered),
                     'dev5_parsed_non_null_request': sum(r['requested_intervention_id'] is not None for r in delivered),
                     'dev5_person_c3': sum(r['human'].get('human_c3_confirmation_after_failed') == 'Y' for r in delivered),
                     'dev5_person_c5': sum(r['human'].get('human_c5_report_inconsistency') == 'Y' for r in delivered),
                     'dev5_hint_c3': sum(r['hints']['c3_confirmation_after_failed'] for r in delivered),
                     'dev5_hint_c5': sum(r['hints']['c5_report_inconsistency'] for r in delivered),
                     'dev6_delivered': len(dev6),
                     'dev6_person_names_c4': sum(r['human'].get('human_dev6_names_c4') == 'Y' for r in dev6),
                     'dev6_person_blames_o3': sum(r['human'].get('human_dev6_blames_o3') == 'Y' for r in dev6),
                     'dev6_hint_c4': sum(r['hints']['dev6_names_c4'] for r in dev6),
                     'dev6_hint_o3': sum(r['hints']['dev6_blames_o3'] for r in dev6)}
    control, guide = arms['CONTROL'], arms['GUIDE']
    tests = {}
    for measure in ('dev5_valid_requested', 'dev5_person_c3', 'dev5_person_c5'):
        tests[measure] = {'guide': f'{guide[measure]}/{guide["dev5_delivered"]}', 'control': f'{control[measure]}/{control["dev5_delivered"]}',
                          'one_sided_fisher_p_guide_greater': fisher_one_sided_greater(guide[measure], guide['dev5_delivered'],
                                                                                       control[measure], control['dev5_delivered'])}
    for measure in ('dev6_person_names_c4',):
        tests[measure] = {'guide': f'{guide[measure]}/{guide["dev6_delivered"]}', 'control': f'{control[measure]}/{control["dev6_delivered"]}',
                          'one_sided_fisher_p_guide_greater': fisher_one_sided_greater(guide[measure], guide['dev6_delivered'],
                                                                                       control[measure], control['dev6_delivered'])}
    return {'measure': 'secondary, counts and one-sided Fisher tests, no pass bar; person columns need the review file',
            'arms': arms, 'tests': tests}


def _p4(repair):
    setups = {}
    for name in REPAIR_SETUPS:
        for arm in REPAIR_ARMS:
            rows = [r for r in repair if r['request'] == name and r['arm'] == arm]
            delivered = [r for r in rows if r['delivered']]
            ok = [r for r in delivered if r['valid'] and r['hypothesis_characters'] is not None and r['hypothesis_characters'] <= HYPOTHESIS_LIMIT]
            setups[f'{name}/{arm}'] = {'planned': len(rows), 'delivered': len(delivered), 'valid_within_600': len(ok),
                                       'hypothesis_characters': [r['hypothesis_characters'] for r in delivered],
                                       'distinct_raw_answers': _distinct(delivered, 'raw') if delivered else 0}
    new = [setups[f'{name}/REPAIR_RULE1'] for name in REPAIR_SETUPS]
    today = [setups[f'{name}/REPAIR_TODAY'] for name in REPAIR_SETUPS]
    if any(s['delivered'] != K for s in new + today):
        status = 'INCOMPLETE'
    else:
        status = 'PASS' if all(s['valid_within_600'] >= 9 for s in new) else 'FAIL'
    worse = sum(s['valid_within_600'] for s in new) < sum(s['valid_within_600'] for s in today)
    return {'measure': 'repair turns returning a valid answer with hypothesis <= 600 characters', 'setups': setups,
            'status': status, 'rule1_worse_than_today_in_total': worse,
            'worse_means': 'the Rule 1 message\'s valid-within-600 total over both setups is lower than today\'s total'}


def _kinds(first):
    table = {}
    for row in first:
        if not row['delivered']: continue
        key = f'{row["request"]}/{row["arm"]}'
        kind = str(row.get('proposed_kind'))
        table.setdefault(key, {})
        table[key][kind] = table[key].get(kind, 0) + 1
    return table


# ------------------------------------------------------------------------------------------------ command line

def _summary(plan):
    lines = [f'diagnosis probe dry run: plan {plan["plan_hash"]}', f'harness sha256 {plan["harness_sha256"]}',
             f'model {plan["model"]}; settings from saved plan {plan["sampling"]["plan_hash"][:12]} (campaign {plan["sampling"]["campaign_id"]})',
             f'calls: {plan["counts"]["first_turn_calls"]} first-turn + {plan["counts"]["repair_calls"]} repair = {plan["counts"]["total_calls"]}',
             'input tokens per request (frozen tokenizer):']
    for key, request in sorted(plan['requests'].items()):
        lines.append(f'  {key:<24} {request["input_tokens"]:>6}  x{plan["counts"]["calls_per_request_key"][key]}')
    charge = plan['charge']
    lines += [f'maximum charge: {charge["planned_calls"]} x ${charge["per_call_dollar_upper_bound"]} = ${charge["max_charge_dollars"]:.4f} '
              f'(hard cap ${charge["hard_spend_cap_dollars"]:.2f}); tighter bound with these inputs and 2,000 output tokens each: '
              f'${charge["tighter_bound_dollars"]:.4f}',
              f'sampling: temperature {frozen_temperature(plan)}, frozen from the saved plan; the declaration cannot change it. '
              f'Ten repeats of one request may return the same answer; scoring reports distinct answers per request key.',
              'network calls: 0']
    return '\n'.join(lines)


def _repeats_line(scoring):
    repeats = scoring['repeats']
    return (f'repeats: {repeats["keys_with_one_distinct_answer"]} of {repeats["request_keys"]} request keys got one distinct answer '
            f'(temperature {repeats["temperature"]}); see scoring.json repeats')


def main(argv=None, *, provider_factory=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='the default: build, check, count and print; no network')
    parser.add_argument('--write-plan', help='with the dry run: write plan.json, requests.json and a declaration template here')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--declaration')
    parser.add_argument('--declaration-sha256')
    parser.add_argument('--out')
    parser.add_argument('--score')
    parser.add_argument('--review')
    args = parser.parse_args(argv)
    try:
        if args.score:
            scoring = score(args.score, review=args.review)
            print(json.dumps({k: scoring[k] for k in ('P1', 'P2', 'P4')}, indent=1, sort_keys=True))
            print(_repeats_line(scoring))
            return 0
        plan, messages = build_plan()
        if not args.execute_live:
            print(_summary(plan))
            if args.write_plan:
                folder = pathlib.Path(args.write_plan)
                folder.mkdir(parents=True, exist_ok=True)
                _write_json(folder / 'plan.json', plan)
                _write_json(folder / 'requests.json', messages)
                _write_json(folder / 'DECLARATION.template.json', declaration_template(plan))
                print(f'wrote plan.json, requests.json and DECLARATION.template.json under {folder}')
            return 0
        if not args.out:
            raise ProbeRefused('--execute-live needs --out')
        declaration = verify_declaration(args.declaration, args.declaration_sha256, plan, args.out)
        if provider_factory is None:
            from app.config import Settings
            from app.providers.runtime import RuntimeProvider
            settings = Settings.from_env()
            if settings.model_for_role('mechanic') != MODEL:
                raise ProbeRefused('The configured Mechanic model is not ' + MODEL)
            provider_factory = lambda: RuntimeProvider(settings, live_authorized=True)  # noqa: E731
        provider = provider_factory()

        async def run():
            try:
                return await execute(plan, messages, args.out, provider, spend_cap=declaration['spend_cap_dollars'],
                                     declaration_sha256=args.declaration_sha256)
            finally:
                close = getattr(provider, 'close', None)
                if close is not None:
                    await close()
        manifest = asyncio.run(run())
        scoring = score(args.out, plan=plan, messages=messages)
        print(json.dumps({k: manifest.get(k) for k in ('status', 'delivered_answers', 'failed_calls', 'ledger', 'stop_reason')}, indent=1))
        print(_repeats_line(scoring))
        print(manifest['project_ledger_note'])
        return 0 if manifest['status'] == 'COMPLETED' else 1
    except ProbeRefused as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
