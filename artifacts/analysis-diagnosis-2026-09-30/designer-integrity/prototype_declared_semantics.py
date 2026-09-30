"""Offline prototype of faultlab-mechanic-diagnosis/v2-declared-semantics (designer-integrity, $0, read-only).

Reads only files already written by investigation A (inv-a/*-diagnosis-request.json, inv-a/mechanic-outputs.json) and
the four run exports (task_text). No store, no provider, no network. Run from faultlab/backend with the project venv and
-B (no bytecode written into the repo):

  cd faultlab/backend && ../.venv/bin/python -B ../artifacts/analysis-diagnosis-2026-09-30/designer-integrity/prototype_declared_semantics.py

It checks, for each of the five rebuilt diagnosis requests:
  1. adding the diagnosis_semantics block leaves every existing request key byte-identical (the protocol is additive);
  2. the size added (frozen DeepSeek-V4 tokenizer) and that the request stays far below 32,000 input tokens;
  3. what the new repair turn would have told v2g (limit and length) and its size;
  4. what the proposed diagnosis_requests sidecar record would have recorded for each diagnosis.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # faultlab/
sys.path.insert(0, str(ROOT / 'backend'))

from app.contracts.models import canonical_json, DiagnosticProposal  # noqa: E402
from app.contracts.tokens import input_token_bound  # noqa: E402
from app.agents.explorer import PUBLIC_INVARIANTS  # noqa: E402
from pydantic import TypeAdapter, ValidationError  # noqa: E402

PROTOCOL = 'faultlab-mechanic-diagnosis/v2-declared-semantics'
BLOCK = 'diagnosis_semantics'
MEANING = ('Fixed facts for reading this request; they add, remove or re-score no observation. task_text is the task '
           'instruction the agent under test was given. public_invariants are the public meanings of the check IDs in '
           'failed_checks and in the checks table; a check row with passed true means fixed code found that invariant '
           'satisfied in that episode. kinds defines each proposed_kind. verdict_rule says what fixed code does with each '
           'field of your output. output_limits are the output_schema limits in plain words.')
KINDS = {
    'POLICY_GAP': ('The evidence delivered to the agent was enough to act and report correctly, and under this fault the '
                   'agent did not; different recovery behaviour could have avoided the target violation.'),
    'CONTRACT_EVIDENCE_GAP': ('The public API could not deliver evidence that distinguishes the underlying outcome within '
                              'the deadline, so no recovery behaviour could act correctly. It concerns evidence the API '
                              'makes available to the agent, not how the agent cited evidence it did receive (that is '
                              'invariant C6). Fixed code establishes this kind only with a separate evidence-gap fixture '
                              'that this request does not run.'),
    'INCONCLUSIVE': ('The supplied observations and offered interventions cannot distinguish the explanations you '
                     'consider.'),
}
VERDICT_RULE = ('Fixed code, not your output, assigns the diagnostic kind. It reads only the three fresh reproduction '
                'trials and the fresh trials of the one intervention you request: POLICY_GAP when all three reproduction '
                'trials show the target violation and the requested intervention is SUPPORTED (the target violation in 3 '
                'of 3 fresh control trials and in 0 of 3 fresh treatment trials, every trial valid); otherwise '
                'INCONCLUSIVE. It cannot assign CONTRACT_EVIDENCE_GAP in this step. proposed_kind, hypothesis and '
                'evidence_ids are recorded as your proposal and are not scored. Requesting an intervention is not a claim '
                'that it will be SUPPORTED. If you request null, no intervention runs and fixed code records INCONCLUSIVE; '
                'an output that still fails output_schema after one format repair is treated the same way.')
OUTPUT_LIMITS = {'hypothesis_max_characters': 600,
                 'note': ('Characters, not words: 600 characters is about 90 English words. A longer hypothesis fails '
                          'output_schema.')}
REPAIR_SENTENCE = ('A string_too_long error gives max_characters and your_characters: rewrite that same field in at most '
                   'max_characters characters, keeping its meaning and adding no new claim.')
TODAY_REPAIR_INSTRUCTION = ('Your response failed output_schema or its supplied evidence/choice bindings. Correct '
                            'formatting only. Copy cited IDs exactly from the supplied allowed lists; cite only the '
                            'evidence needed. Do not add authority, a new hypothesis, or a replacement canned solution.')
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
RUNS = {'v2d-dev5': 'native-v2d-run', 'v2e-dev5': 'native-v2e-run', 'v2f-dev5': 'native-v2f-run',
        'v2g-dev5': 'native-v2g-run', 'v2g-dev6': 'native-v2g-run'}


def semantics_block(task_text):
    return {'protocol': PROTOCOL, 'meaning': MEANING, 'task_text': task_text,
            'public_invariants': dict(PUBLIC_INVARIANTS), 'kinds': KINDS, 'verdict_rule': VERDICT_RULE,
            'output_limits': OUTPUT_LIMITS}


def repair_errors(raw):
    """The proposed repair-turn error list: today's {location,type} plus, for string_too_long, the limit and length."""
    try:
        TypeAdapter(DiagnosticProposal).validate_json(raw)
        return []
    except ValidationError as error:
        parsed = json.loads(raw)
        out = []
        for issue in error.errors(include_input=False, include_context=True, include_url=False):
            item = {'location': list(issue['loc']), 'type': issue['type']}
            if issue['type'] == 'string_too_long':
                value = parsed
                for key in issue['loc']: value = value[key]
                item |= {'max_characters': issue['ctx']['max_length'], 'your_characters': len(value)}
            out.append(item)
        return out


def main():
    exports = {}
    report = {'protocol': PROTOCOL, 'model_tokenizer': MODEL, 'diagnoses': {}}
    outputs = json.loads((HERE.parent / 'inv-a' / 'mechanic-outputs.json').read_text())
    for name, run in RUNS.items():
        if run not in exports:
            exports[run] = json.loads((ROOT / 'artifacts/product-live-2026-09-30' / run / 'export.json').read_text())
        task_text = exports[run]['campaign']['task_text']
        request = json.loads((HERE.parent / 'inv-a' / f'{name}-diagnosis-request.json').read_text())
        first = request['turns'][0]['messages']
        context = json.loads(first[1]['content'])
        new_context = {**context, BLOCK: semantics_block(task_text)}
        unchanged = all(canonical_json(context[k]) == canonical_json(new_context[k]) for k in context)
        new_first = [first[0], {'role': 'user', 'content': canonical_json(new_context)}]
        before, after = input_token_bound(first, MODEL), input_token_bound(new_first, MODEL)
        block_tokens = input_token_bound([{'role': 'user', 'content': canonical_json(semantics_block(task_text))}], MODEL)
        entry = {'task_text': task_text, 'existing_keys_byte_identical': unchanged,
                 'first_turn_tokens_before': before, 'first_turn_tokens_after': after, 'added_tokens': after - before,
                 'block_alone_tokens': block_tokens}
        # Sidecar (diagnosis_requests) as it would have been recorded, from the saved raw answers only.
        answers = outputs[name]['answers']
        per_attempt = [{'mechanic_outputs_record': a['mechanic_outputs_record'], 'attempt': a['attempt'],
                        'validation_errors': a.get('validation_errors') or []} for a in answers]
        valid = [a for a in answers if not a.get('validation_errors')]
        if valid:
            final = valid[-1]
            status = 'VALID_REQUESTED' if final.get('requested_intervention_id') else 'VALID_NO_REQUEST'
            kind_source = 'model'
        else:
            final = answers[-1]
            status = 'INVALID_OUTPUT'
            kind_source = 'code_default'
        entry['sidecar'] = {'proposal_status': status, 'recorded_proposed_kind_source': kind_source,
                            'attempts': per_attempt,
                            'last_raw_unvalidated': {'proposed_kind': final.get('proposed_kind'),
                                                     'requested_intervention_id': final.get('requested_intervention_id')}}
        if len(request['turns']) > 1:
            repair = request['turns'][1]['messages']
            raw0 = repair[2]['content']
            errors = repair_errors(raw0)
            today = repair[3]['content']
            assert json.loads(today)['instruction'] == TODAY_REPAIR_INSTRUCTION
            proposed = canonical_json({'validation_errors': errors,
                                       'instruction': TODAY_REPAIR_INSTRUCTION + ' ' + REPAIR_SENTENCE})
            entry['repair_turn'] = {'today': json.loads(today), 'proposed': json.loads(proposed),
                                    'today_turn_tokens': input_token_bound(repair, MODEL),
                                    'proposed_turn_tokens_without_block': input_token_bound(repair[:3] + [{'role': 'user', 'content': proposed}], MODEL)}
        report['diagnoses'][name] = entry
    out = HERE / 'prototype-results.json'
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    print(json.dumps({k: {x: v[x] for x in ('existing_keys_byte_identical', 'first_turn_tokens_before',
                                             'first_turn_tokens_after', 'added_tokens')} | {'status': v['sidecar']['proposal_status']}
                      for k, v in report['diagnoses'].items()}, indent=1))
    for k, v in report['diagnoses'].items():
        if 'repair_turn' in v: print(k, 'repair errors proposed:', v['repair_turn']['proposed']['validation_errors'])


if __name__ == '__main__':
    main()
