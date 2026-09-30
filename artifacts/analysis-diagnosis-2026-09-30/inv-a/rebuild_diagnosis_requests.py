"""Investigation A ($0, offline, read-only): rebuild the exact Mechanic diagnosis request of every native-v2
diagnosis in live runs v2d, v2e, v2f and v2g (5 diagnoses), with the product's own request-building code.

Run from faultlab/backend with the project .venv:
  ../.venv/bin/python -B ../artifacts/analysis-diagnosis-2026-09-30/inv-a/rebuild_diagnosis_requests.py

How:
* The saved store is copied (opened mode=ro&immutable=1) to /Users/shree/FaultLab_Scratch/inv-a/rebuild/, the copy is
  opened with the product's ReadOnlyLabStore, and the copy is deleted at the end.
* For each diagnosis, the learning loop's arguments to Diagnostician.run are read from saved records only
  (counterexample, retained recipe, reproduction trials, source+reproduction evidence bundles, and the reduction
  summary built with diagnosis.reduction_context from the reduction record, its trials in the reducer's execution
  order, and their evidence bundles).
* The real Diagnostician builds the context. The Mechanic is a capture that raises before anything is sent or saved.
  It is wrapped exactly as app/lab/learning.py (lines 243-244) wraps it for that campaign's saved plan:
  loop_limits.BoundedMechanic when the plan declares mechanic_context, then citation_status.CitationStatusMechanic
  when the plan declares mechanic_evidence.
* The request is then built exactly as app/agents/mechanic.py _generate builds it (lines 21-22): system = the text of
  prompts/diagnosis.md, user = canonical_json({**context, 'output_schema': DiagnosticProposal JSON schema}).
* For a diagnosis whose saved Mechanic output has an attempt-1 record, the format-repair turn is rebuilt too
  (mechanic.py lines 65-73), using the saved attempt-0 raw answer and the real schema/binding validation.
* Token counts use the Mechanic's own admission count (loop_limits.mechanic_request_bound, frozen tokenizer) and are
  compared with the provider-reported input_tokens saved in each mechanic_outputs record.
The fixer guard (refuses the real .env and every non-loopback connection) is imported first.
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
FAULTLAB = HERE.parents[2]
sys.path.insert(0, str(FAULTLAB / 'artifacts' / 'product-mechanic-citations-2026-09-30' / 'fixer'))
import guard  # noqa: E402,F401

from pydantic import TypeAdapter, ValidationError  # noqa: E402
from app.contracts.models import (Campaign, Counterexample, DiagnosticProposal, EvidenceBundle, FaultSpec,  # noqa: E402
                                  PolicyVersion, ReductionResult, TrialResult, canonical_json, content_hash)
from app.lab import citation_status, loop_limits  # noqa: E402
from app.lab.diagnosis import Diagnostician, reduction_context  # noqa: E402
from app.lab.runner import campaign_run_plan  # noqa: E402
from app.lab.storage import ReadOnlyLabStore  # noqa: E402
from app.agents.mechanic import PROMPTS  # noqa: E402

SAVED_STORE = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
SCRATCH = Path('/Users/shree/FaultLab_Scratch/inv-a/rebuild')
OUT = HERE
MECHANIC_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'

DIAGNOSES = [  # (name, run, campaign, counterexample) in store order
    ('v2d-dev5', 'v2d', 'campaign-ea66672d7a904bd8a011d6922790c963', 'counterexample-b5ad7261afb4478f95d36530642000d6'),
    ('v2e-dev5', 'v2e', 'campaign-37e66b6c3a544a4d9bde4161db6bf0aa', 'counterexample-466a973d90f341b79b1fe05ed3632bfd'),
    ('v2f-dev5', 'v2f', 'campaign-53db74766f4d4635b94a0de89e492577', 'counterexample-c26c27511e0044bba306085f1816b105'),
    ('v2g-dev5', 'v2g', 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530', 'counterexample-c8e897379e0b461491a3c256ceea4f30'),
    ('v2g-dev6', 'v2g', 'campaign-d8d1e8cc0ea34feb92dbd8c22c264530', 'counterexample-913db40010c446a0aa370d6a2e0a0a93'),
]


class Captured(Exception):
    pass


class CaptureMechanic:
    """Keeps the request and raises before anything is sent or saved. provider.role_model gives the Mechanic model,
    so BoundedMechanic's size check counts with the same tokenizer resolution as the live Mechanic."""
    def __init__(self):
        self.contexts = []
        self.provider = SimpleNamespace(role_model=lambda role: MECHANIC_MODEL)
        self.metadata = None
    async def diagnose(self, context, *, reservation=None):
        self.contexts.append(context)
        raise Captured()


def model(store, kind, ident, cls):
    return cls.model_validate_json(canonical_json(store.get_record(kind, ident)))


def evidence(store, episode_ids):
    missing = [e for e in episode_ids if store.get_record('evidence', e) is None]
    if missing: raise RuntimeError(f'missing evidence records: {missing}')
    return [model(store, 'evidence', e, EvidenceBundle) for e in episode_ids]


def reduction_trials(store, campaign_id, reduction):
    """The reducer's trials in execution order: the original recipe's three (not listed in attempts), then each
    attempt's trial_ids in attempt order (app/referee/reducer.py run_three / attempts)."""
    attempt_ids = [e for a in reduction.attempts for e in a.trial_ids]
    rows = [r for r in store.list_records('episodes') if r['campaign_id'] == campaign_id and r['experiment_purpose'] == 'reduction']
    originals = []
    for row in rows:
        if row['episode_id'] in attempt_ids: continue
        trial = model(store, 'trials', row['episode_id'], TrialResult)
        if trial.scenario_hash == reduction.original_recipe_hash: originals.append(trial)
    originals.sort(key=lambda t: t.trial_index)
    if [t.trial_index for t in originals] != [0, 1, 2]:
        raise RuntimeError(f'original reduction trials not found cleanly: {[t.trial_index for t in originals]}')
    return originals + [model(store, 'trials', e, TrialResult) for e in attempt_ids]


def inputs(store, campaign_id, counterexample_id):
    campaign = store.get_model('campaigns', campaign_id, Campaign)
    counter = model(store, 'counterexamples', counterexample_id, Counterexample)
    incumbent = model(store, 'policies', 'policy-v0', PolicyVersion)
    reduction = model(store, 'reductions', counterexample_id, ReductionResult)
    reduced = reduction_trials(store, campaign_id, reduction)
    summary = reduction_context(reduction, reduced, evidence(store, [t.episode_id for t in reduced if t.lifecycle == 'COMPLETED']))
    retained_raw = store.get_record('retained_recipes', counterexample_id)['retained_recipe']
    retained = FaultSpec.model_validate(retained_raw)
    if content_hash(retained) != reduction.retained_recipe_hash: raise RuntimeError('retained recipe hash mismatch')
    reproduction = [model(store, 'trials', e, TrialResult) for e in counter.reproduction_trial_ids]
    bundles = evidence(store, [counter.source_episode_id, *counter.reproduction_trial_ids])
    return campaign, counter, retained, incumbent, reproduction, bundles, summary, reduced


async def rebuild(store, campaign_id, counterexample_id):
    campaign, counter, retained, incumbent, reproduction, bundles, summary, reduced = inputs(store, campaign_id, counterexample_id)
    plan = campaign_run_plan(store, campaign) or {}
    capture = CaptureMechanic()
    mechanic = capture
    wrappers = []
    if plan.get('mechanic_context') is not None:
        mechanic = loop_limits.BoundedMechanic(mechanic, store, campaign_id=campaign_id, counterexample=counter); wrappers.append('BoundedMechanic')
    if plan.get('mechanic_evidence') is not None:
        mechanic = citation_status.CitationStatusMechanic(mechanic, store); wrappers.append('CitationStatusMechanic')
    try:
        await Diagnostician(store, None, None, mechanic).run(campaign, counter, retained, incumbent, reproduction,
                                                             evidence=bundles, reduction=summary)
    except Captured:
        pass
    context, = capture.contexts
    return counter, context, wrappers, [t.episode_id for t in reduced]


def messages_for(context):
    adapter = TypeAdapter(DiagnosticProposal)
    full = {**context, 'output_schema': adapter.json_schema()}
    return [{'role': 'system', 'content': (PROMPTS / 'diagnosis.md').read_text()}, {'role': 'user', 'content': canonical_json(full)}]


def validate(context, raw):
    """mechanic.py lines 65-70 and 76-84: schema validation, then evidence and intervention bindings."""
    adapter = TypeAdapter(DiagnosticProposal)
    try:
        result = adapter.validate_json(raw)
    except ValidationError as error:
        return [{'location': list(issue['loc']), 'type': issue['type']}
                for issue in error.errors(include_input=False, include_context=False, include_url=False)]
    errors = []
    if not set(result.evidence_ids) <= set(context.get('evidence_ids', [])):
        errors.append({'location': ['evidence_ids'], 'type': 'unknown_evidence_reference'})
    if result.requested_intervention_id is not None and result.requested_intervention_id not in set(context.get('intervention_ids', [])):
        errors.append({'location': ['requested_intervention_id'], 'type': 'unknown_intervention_reference'})
    return errors


REPAIR_INSTRUCTION = ('Your response failed output_schema or its supplied evidence/choice bindings. Correct formatting only. '
                      'Copy cited IDs exactly from the supplied allowed lists; cite only the evidence needed. Do not add '
                      'authority, a new hypothesis, or a replacement canned solution.')


def token_bound(msgs):
    from app.contracts.tokens import input_token_bound
    return input_token_bound(msgs, MECHANIC_MODEL)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


async def main():
    import sqlite3
    SCRATCH.mkdir(parents=True, exist_ok=True)
    copy = SCRATCH / 'lab-copy.sqlite3'
    src = sqlite3.connect(f'file:{SAVED_STORE}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy)
    try:
        src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst.close(); src.close()
    index = {}
    try:
        store = ReadOnlyLabStore(copy)
        try:
            outputs = [r for r in store.list_records('mechanic_outputs') if r.get('prompt') == 'diagnosis.md']
            for name, run, campaign_id, counterexample_id in DIAGNOSES:
                counter, context, wrappers, reduction_ids = await rebuild(store, campaign_id, counterexample_id)
                msgs = messages_for(context)
                diag_link = next(r for r in store.list_records('diagnostic_campaigns') if r['counterexample_id'] == counterexample_id)
                diagnostic = store.get_record('diagnostics', diag_link['diagnostic_id'])
                # This diagnosis' saved Mechanic answers: same campaign, diagnosis.md; matched to this request by the
                # first-turn input token count ordering (store order) and checked by validating against this context.
                mine = [r for r in outputs if r['campaign_id'] == campaign_id]
                requests = []
                for r in mine:
                    if r['request_id'] not in requests: requests.append(r['request_id'])
                position = [d[3] for d in DIAGNOSES if d[2] == campaign_id].index(counterexample_id)
                request_id = requests[position]
                answers = sorted([r for r in mine if r['request_id'] == request_id], key=lambda r: r['attempt'])
                answer_ids = [ref for ref, rec in ((store.db.execute("SELECT id FROM records WHERE kind='mechanic_outputs' AND json_extract(payload,'$.request_id')=? AND json_extract(payload,'$.attempt')=?", (request_id, a['attempt'])).fetchone()[0], a) for a in answers)]
                turns = [{'attempt': 0, 'messages': msgs}]
                validation = []
                for a in answers:
                    errors = validate(context, a['raw'])
                    validation.append({'attempt': a['attempt'], 'errors': errors, 'provider_input_tokens': a['usage']['input_tokens'],
                                       'provider_output_tokens': a['usage']['output_tokens']})
                if len(answers) == 2:
                    repair = msgs + [{'role': 'assistant', 'content': answers[0]['raw']},
                                     {'role': 'user', 'content': canonical_json({'validation_errors': validation[0]['errors'], 'instruction': REPAIR_INSTRUCTION})}]
                    turns.append({'attempt': 1, 'messages': repair})
                final = answers[-1]
                final_errors = validation[-1]['errors']
                parsed = json.loads(final['raw'])
                request_file = OUT / f'{name}-diagnosis-request.json'
                request_file.write_text(json.dumps({'diagnosis': name, 'campaign_id': campaign_id, 'counterexample_id': counterexample_id,
                                                    'mechanic_model': MECHANIC_MODEL, 'request_id': request_id,
                                                    'wrappers_applied': wrappers, 'turns': turns}, indent=1) + '\n')
                context_file = OUT / f'{name}-diagnosis-context.json'
                context_file.write_text(json.dumps(json.loads(msgs[1]['content']), indent=1, sort_keys=True) + '\n')
                index[name] = {
                    'run': run, 'campaign_id': campaign_id, 'counterexample_id': counterexample_id,
                    'target_invariant': counter.target_invariant, 'source_episode_id': counter.source_episode_id,
                    'reproduction_trial_ids': counter.reproduction_trial_ids, 'reduction_trial_ids_in_order': reduction_ids,
                    'wrappers_applied': wrappers, 'request_file': request_file.name, 'context_file': context_file.name,
                    'user_message_sha256': sha(msgs[1]['content']), 'system_message_sha256': sha(msgs[0]['content']),
                    'user_message_chars': len(msgs[1]['content']),
                    'rebuilt_first_turn_tokens_frozen_tokenizer': token_bound(msgs),
                    'rebuilt_repair_turn_tokens_frozen_tokenizer': token_bound(turns[1]['messages']) if len(turns) == 2 else None,
                    'mechanic_output_record_ids': answer_ids,
                    'validation_by_attempt': validation,
                    'final_answer_valid': not final_errors,
                    'final_answer': parsed,
                    'recorded_diagnostic_id': diag_link['diagnostic_id'],
                    'recorded_proposed_kind': diagnostic['proposed_kind'], 'recorded_kind': diagnostic['kind'],
                    'recorded_intervention_ids': diagnostic['intervention_ids'],
                    'context_fields': sorted(context.keys()),
                    'intervention_options': context['intervention_ids'],
                }
        finally:
            store.close()
    finally:
        for suffix in ('', '-wal', '-shm', '-journal'):
            Path(str(copy) + suffix).unlink(missing_ok=True)
        index['_scratch_copy_deleted'] = not any(Path(str(copy) + s).exists() for s in ('', '-wal', '-shm', '-journal'))
    (OUT / 'rebuild-index.json').write_text(json.dumps(index, indent=1, sort_keys=True) + '\n')
    print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk not in ('final_answer', 'reduction_trial_ids_in_order', 'reproduction_trial_ids', 'context_fields')} if isinstance(v, dict) else v) for k, v in index.items()}, indent=1, sort_keys=True))


if __name__ == '__main__':
    asyncio.run(main())
