"""Diagnosis repair-and-record rule (declared September 30, 2026, after live runs v2d-v2g).

``faultlab-mechanic-diagnosis/v1-repair-and-record`` (``mechanic_diagnosis`` in the plan) is frozen into every new Learn
plan, for every agent. It is absent (not null) from every plan saved before it and from every baseline or compare plan,
so those plans keep their exact bytes, their plan_hash and today's behaviour.

Why (artifacts/analysis-diagnosis-2026-09-30/RECOMMENDATION.md, sections 1.2 and 1.5). In live run v2g the diagnosis
Mechanic requested the offered intervention twice, but both answers had a 614-character hypothesis against the
600-character limit. The format-repair message said only "string_too_long"; the model resent the same text, no
intervention ran, and fixed code stored proposed_kind INCONCLUSIVE as a code default. The saved diagnostic could not
tell "declined" from "invalid output" from "code default", and a run document then misstated what happened.

What. Two parts, both only for a Mechanic diagnosis request (prompts/diagnosis.md) of a plan that declares the rule:

  1a. The format-repair turn states the limit. Each string_too_long error in the repair message also carries
      max_characters (the schema's own limit, from pydantic's error context) and your_characters (the length of the
      answer's field). Today's instruction sentence is kept exactly and one sentence is appended (REPAIR_SENTENCE).
      The model's text is never truncated or edited, and the 600-character limit is unchanged.
  1b. A record of why an intervention did or did not run. After Diagnostician.run returns, and before the learning
      loop's POLICY_GAP gate, one immutable ``diagnosis_requests/<diagnostic_id>`` record is written for EVERY diagnosis
      (INCONCLUSIVE ones too). It names every Mechanic attempt by its mechanic_outputs id with its validation errors,
      says plainly whether the Mechanic requested an intervention (VALID_REQUESTED), declined (VALID_NO_REQUEST) or
      gave no valid answer (INVALID_OUTPUT), where the recorded proposed_kind came from (model or code_default), the
      offered options with their change strings, the requested id, and whether the requested intervention ran any fresh
      trial (and, when its experiment ended before its three trial pairs, why: preflight rejection, a Stop, a callback
      error or an invalid trial).

What does not change. The verdict still comes only from classify_policy_gap (referee/diagnostics.py, unchanged) fed by
fresh trials. The diagnosis prompt, output schema, options, context, V2_MEMORY, the null path, the code default, the
learning.py POLICY_GAP gate, reproduction, reduction, source validation, challenge and promotion are unchanged. The
first turn of every diagnosis request is byte-identical with or without the rule; only its repair turn differs.
"""
from __future__ import annotations

import json
from copy import deepcopy

from app.agents.mechanic import FORMAT_REPAIR_INSTRUCTION
from app.contracts.models import canonical_json, content_hash

MECHANIC_DIAGNOSIS_V1 = 'faultlab-mechanic-diagnosis/v1-repair-and-record'
PLAN_KEY = 'mechanic_diagnosis'
RECORD_KIND = 'diagnosis_requests'
APPLIES_TO = ('mechanic_diagnosis',)
PROPOSAL_STATUSES = ('VALID_REQUESTED', 'VALID_NO_REQUEST', 'INVALID_OUTPUT')
KIND_SOURCES = ('model', 'code_default')
STRING_TOO_LONG_FIELDS = ('max_characters', 'your_characters')
HYPOTHESIS_MAX_CHARACTERS = 600   # contracts/models.py Text; unchanged, stated here only so the plan names it

# FORMAT_REPAIR_INSTRUCTION (app/agents/mechanic.py) is the repair instruction every Mechanic request has sent since
# before this rule; it is kept exactly and this one sentence is appended.
REPAIR_SENTENCE = ('A string_too_long error gives max_characters and your_characters: rewrite that same field in at most '
                   'max_characters characters, keeping its meaning and adding no new claim.')
REPAIR_INSTRUCTION = FORMAT_REPAIR_INSTRUCTION + ' ' + REPAIR_SENTENCE

RULE = ('For a Learn plan that declares it, a Mechanic diagnosis request\'s one format-repair turn states the length limit: '
        'each string_too_long error also gives max_characters (the schema\'s limit) and your_characters (the length of '
        'that field in the answer), and one sentence is appended to the unchanged repair instruction. The model\'s text is '
        'never truncated or edited and the 600-character limit is unchanged. After every diagnosis, before the POLICY_GAP '
        'gate, FaultLab saves one immutable diagnosis_requests record: every Mechanic attempt by id with its validation '
        'errors; whether the Mechanic requested an offered intervention (VALID_REQUESTED), requested none '
        '(VALID_NO_REQUEST) or gave no valid answer after its repair turn (INVALID_OUTPUT); whether the recorded '
        'proposed_kind is the model\'s or a code default; the offered options with their change strings; the requested '
        'id; and whether the requested intervention ran any fresh trial and, when its experiment ended before its three '
        'trial pairs, why. The verdict code, the diagnosis prompt, its first turn, the options and every gate are '
        'unchanged.')

# How an intervention experiment can end before its three trial pairs (referee/diagnostics.py run_interventions, unchanged):
# its limitations then hold exactly one of these reason codes instead of the usual scope sentence. CALLBACK_ERROR carries the
# exception's class name after a colon. Review finding MEDIUM-1 / F3 (fixer, September 30): such an experiment may have run no
# fresh trial at all, so the record says so and names the reason in plain words.
EARLY_END_REASONS = {
    'PREFLIGHT_REJECTED': 'preflight rejected its recipes before any trial',
    'STOPPED': 'a Stop request stopped it',
    'CALLBACK_ERROR': 'a trial could not run',
    'INVALID_CALLBACK_RESULT': 'a trial returned an invalid result',
    'INVALID_OR_UNTRIGGERED_TRIAL': 'a trial was invalid or its fault did not fire',
}


def _semantics():
    return {'protocol': MECHANIC_DIAGNOSIS_V1, 'applies_to': list(APPLIES_TO), 'repair_instruction': REPAIR_INSTRUCTION,
            'repair_sentence': REPAIR_SENTENCE, 'string_too_long_fields': list(STRING_TOO_LONG_FIELDS),
            'hypothesis_max_characters': HYPOTHESIS_MAX_CHARACTERS, 'record_kind': RECORD_KIND,
            'proposal_statuses': list(PROPOSAL_STATUSES), 'kind_sources': list(KIND_SOURCES), 'rule': RULE}


def semantics_hash():
    """The content hash of the rule's fixed text and lists (frozen in the plan and checked before Start)."""
    return content_hash(_semantics())


def declaration():
    """The rule as frozen into a new Learn plan (run_plans.MechanicDiagnosisPlan)."""
    return {**_semantics(), 'first_turn_changed': False, 'model_text_edited': False, 'record_written_before_gate': True,
            'reads_scoring': False, 'verdict_code_changed': False, 'semantics_hash': semantics_hash()}


def campaign_rule(store, campaign):
    """The declared rule of this campaign's saved plan, or None (every other plan: today's requests and records)."""
    from app.lab.runner import campaign_run_plan
    return (campaign_run_plan(store, campaign) or {}).get(PLAN_KEY)


# ------------------------------------------------------------------------------------------------ 1a: the repair turn

def repair_errors(error):
    """The validation errors of one schema failure, as the declared repair turn states them.

    Each error is today's {location, type}; a string_too_long error also gets max_characters (pydantic's own ctx
    max_length) and your_characters (the length of the answer's field, as pydantic counted it). Nothing else is added.
    """
    errors = []
    for issue in error.errors(include_url=False):
        item = {'location': list(issue['loc']), 'type': issue['type']}
        if issue['type'] == 'string_too_long':
            limit, value = (issue.get('ctx') or {}).get('max_length'), issue.get('input')
            if isinstance(limit, int) and isinstance(value, str):
                item['max_characters'] = limit
                item['your_characters'] = len(value)
        errors.append(item)
    return errors


def repair_message(errors):
    """The user message of a declared diagnosis repair turn (the flag-off message is the same with FORMAT_REPAIR_INSTRUCTION)."""
    return canonical_json({'validation_errors': errors, 'instruction': REPAIR_INSTRUCTION})


# ------------------------------------------------------------------------------------------------ 1b: the record

class RecordingDiagnosisMechanic:
    """The outermost wrapper of the diagnosis Mechanic under the rule: it keeps what it passed through.

    It sees the Diagnostician's own context (before the guide, citation-status and size-rule wrappers add or fit
    anything), so the options it keeps are exactly the offered ones with their change strings. After the call it keeps
    the returned reference, proposal and raw answers, and the real Mechanic's last_diagnosis (request id, every attempt's
    output id and validation errors). It changes no request and no answer.
    """
    def __init__(self, mechanic, source):
        self.mechanic, self.source = mechanic, source
        self.last = None

    def __getattr__(self, name):
        return getattr(self.mechanic, name)

    async def diagnose(self, context, **kwargs):
        options = [{'intervention_id': item.get('id'), 'change': item.get('change'),
                    'observed_treatment_trials': deepcopy(item.get('observed_treatment_trials'))}
                   for item in context.get('interventions') or [] if isinstance(item, dict)]
        offered = list(context.get('intervention_ids') or [])
        self.last = None
        self.source.last_diagnosis = None
        ref, proposal, raws = await self.mechanic.diagnose(context, **kwargs)
        self.last = {'options': options, 'offered_ids': offered, 'ref': ref, 'proposal': proposal, 'raws': list(raws),
                     'attempts': deepcopy(self.source.last_diagnosis)}
        return ref, proposal, raws


def _unvalidated(raw):
    """The last answer's proposed_kind and requested id as parsed, never validated (INVALID_OUTPUT explains itself)."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {'validated': False, 'parsed_json_object': False, 'proposed_kind': None, 'requested_intervention_id': None}
    if not isinstance(value, dict):
        return {'validated': False, 'parsed_json_object': False, 'proposed_kind': None, 'requested_intervention_id': None}
    return {'validated': False, 'parsed_json_object': True, 'proposed_kind': value.get('proposed_kind'),
            'requested_intervention_id': value.get('requested_intervention_id')}


def early_end(limitations):
    """The reason code an intervention experiment ended before its three trial pairs (EARLY_END_REASONS), or None."""
    for item in limitations or []:
        if isinstance(item, str) and item.split(':', 1)[0] in EARLY_END_REASONS:
            return item
    return None


def _result_text(row):
    text = f'{row["intervention_id"]} {row["result"]} after {row["trial_pairs"]} of 3 trial pairs'
    if row['early_end'] is None:
        return text
    reason = EARLY_END_REASONS[row['early_end'].split(':', 1)[0]]
    return f'{text}; it ended early: {reason} ({row["early_end"]})'


def _statement(status, attempts, requested, change, results, kind, proposed_kind, source, unvalidated, trials):
    total = len(attempts)
    if status == 'INVALID_OUTPUT':
        errors = '; '.join(', '.join(f"{'.'.join(map(str, e['location']))} {e['type']}"
                                     + (f" ({e['your_characters']} of at most {e['max_characters']} characters)"
                                        if 'your_characters' in e else '') for e in a['validation_errors'])
                           for a in attempts)
        return (f'None of the Mechanic\'s {total} answer(s) passed validation ({errors}), so no intervention ran. Fixed code '
                f'recorded {kind}; the recorded proposed_kind {proposed_kind} is a code default, not the model\'s. Its last '
                f'answer, unvalidated, named proposed_kind {unvalidated["proposed_kind"]!r} and requested '
                f'{unvalidated["requested_intervention_id"]!r}.')
    valid_at = next(a['attempt'] for a in attempts if not a['validation_errors']) + 1
    head = f'The Mechanic gave a valid answer on attempt {valid_at} of {total}'
    if status == 'VALID_NO_REQUEST':
        return (f'{head} and requested no intervention (null), so none ran. Fixed code recorded {kind}; the recorded '
                f'proposed_kind {proposed_kind} is the model\'s.')
    ran = '; '.join(_result_text(r) for r in results) or 'no experiment was recorded'
    fresh = f'{trials} fresh intervention trial(s) ran' if trials else 'no fresh trial ran'
    return (f'{head} and requested {requested} ({change}). Intervention result: {ran}; {fresh}. Fixed code recorded {kind}; '
            f'the recorded proposed_kind {proposed_kind} is the model\'s.')


def build_record(campaign, counter, diagnostic, run, wrapper):
    """The diagnosis_requests record for one diagnosis (pure: it reads only what the wrapper and the run hold).

    Raises RuntimeError when the wrapper's state does not describe this diagnosis, so a false record is never saved.
    """
    # Every refusal names the diagnosis, so an operator can find it (review finding LOW-4, fixer).
    which = f'diagnosis {diagnostic.diagnostic_id} (counterexample {counter.counterexample_id})'
    last = getattr(wrapper, 'last', None)
    attempts_state = (last or {}).get('attempts')
    if not last or not attempts_state:
        raise RuntimeError(f'No Mechanic attempt state for {which}; its diagnosis_requests record was not written')
    refs, errors, raws = attempts_state['output_refs'], attempts_state['validation_errors'], last['raws']
    if not refs or refs[-1] != last['ref'] or len(refs) != len(raws) or len(errors) != len(raws):
        raise RuntimeError(f'The Mechanic attempt state does not match {which}; its record was not written')
    if run.trials and not run.experiments:
        raise RuntimeError(f'Fresh intervention trials without a recorded experiment cannot describe {which}; its record was not written')
    proposal = last['proposal']
    if proposal is None:
        status, source = 'INVALID_OUTPUT', 'code_default'
        if errors[-1] == [] or diagnostic.proposed_kind != 'INCONCLUSIVE':
            raise RuntimeError(f'An invalid diagnosis answer must end with validation errors and the code default ({which})')
    else:
        status = 'VALID_REQUESTED' if proposal.requested_intervention_id is not None else 'VALID_NO_REQUEST'
        source = 'model'
        if errors[-1] != [] or diagnostic.proposed_kind != proposal.proposed_kind:
            raise RuntimeError(f'A valid diagnosis answer must end without validation errors and carry the model\'s kind ({which})')
    requested = proposal.requested_intervention_id if proposal is not None else None
    options = last['options']
    change = next((o['change'] for o in options if o['intervention_id'] == requested), None)
    results = [{'intervention_id': e.intervention_id, 'result': e.result, 'trial_pairs': len(e.trial_pairs),
                'limitations': list(e.limitations), 'early_end': early_end(e.limitations)} for e in run.experiments]
    attempts = [{'attempt': index, 'output_ref': ref, 'validation_errors': deepcopy(error)}
                for index, (ref, error) in enumerate(zip(refs, errors))]
    unvalidated = _unvalidated(raws[-1])
    return {'protocol': MECHANIC_DIAGNOSIS_V1, 'campaign_id': campaign.campaign_id,
            'counterexample_id': counter.counterexample_id, 'diagnostic_id': diagnostic.diagnostic_id,
            'target_invariant': counter.target_invariant, 'request_id': attempts_state['request_id'],
            'first_turn_hash': attempts_state['first_turn_hash'], 'attempts': attempts, 'output_refs': list(refs),
            'proposal_status': status, 'recorded_proposed_kind': diagnostic.proposed_kind,
            'recorded_proposed_kind_source': source, 'last_raw_unvalidated': unvalidated,
            'options': deepcopy(options), 'requested_intervention_id': requested, 'requested_change': change,
            # intervention_ran: at least one fresh intervention trial ran (review finding MEDIUM-1 / F3, fixer). An experiment
            # rejected by preflight, or stopped or failed before its first trial, is recorded (intervention_experiment_recorded)
            # but ran nothing; each row's early_end and the statement say why.
            'intervention_ran': len(run.trials) > 0, 'intervention_experiment_recorded': bool(run.experiments),
            'interventions': results, 'fresh_intervention_trials': len(run.trials), 'verdict': diagnostic.kind,
            'statement': _statement(status, attempts, requested, change, results, diagnostic.kind, diagnostic.proposed_kind,
                                    source, unvalidated, len(run.trials))}


def record(store, campaign, counter, diagnostic, run, wrapper):
    """Save the immutable diagnosis_requests/<diagnostic_id> record; returns it."""
    value = build_record(campaign, counter, diagnostic, run, wrapper)
    store.put_record(RECORD_KIND, diagnostic.diagnostic_id, value, immutable=True)
    return value


def campaign_records(store, campaign_id):
    """This campaign's diagnosis_requests records in save order, each with every attempt's mechanic_outputs record
    embedded by id (attempt_outputs), including a first attempt that shares its request id with a later one."""
    out = []
    for value in store.list_records(RECORD_KIND):
        if value.get('campaign_id') != campaign_id: continue
        embedded = []
        for ref in value.get('output_refs') or []:
            output = store.get_record('mechanic_outputs', ref)
            embedded.append({'output_ref': ref, **(output or {'missing': True})})
        out.append({**value, 'attempt_outputs': embedded})
    return out
