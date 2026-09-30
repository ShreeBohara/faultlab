"""Builder check on a scratch copy of the saved native-v2b store ($0, offline, read-only original).

Run from faultlab/backend:
  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/builder/saved_store_check.py > saved-store-check.json

What it checks, with the product code as built (the diagnosis rules installed):
  T1  every saved plan (runs v2b-v2g) re-reads byte for byte with its plan_hash, gains no key, declares neither rule;
  T7  every saved campaign's development recording is byte-identical under this build's exports.py and under the backup
      tip's exports.py (git show 626bae4:backend/app/lab/exports.py, loaded as a separate module);
  T2  the five native-v2 diagnosis requests, rebuilt from the store with investigation A's own rebuild code and sent
      through the real Mechanic (rule off) to a capture provider that answers with the store's saved raw answers, are
      byte-identical, turn for turn, with inv-a's saved request files;
  1b  with the rule on, the same five saved diagnoses replayed through the real Mechanic and the recording wrapper give
      the records the memo predicted (VALID_REQUESTED, VALID_NO_REQUEST, VALID_REQUESTED with attempt 0 rejected at 743
      characters, INVALID_OUTPUT/code_default, VALID_REQUESTED).
The original store is opened only by sqlite's backup API with mode=ro&immutable=1; its sha256 is recorded before and
after; the copy lives under /Users/shree/FaultLab_Scratch/ and is deleted at the end. The fixer guard (imported by the
rebuild module) refuses the real .env and every non-loopback connection.
"""
import asyncio
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAULTLAB = HERE.parents[2]
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/product-diagnosis-rules/builder')
INV_A = FAULTLAB / 'artifacts/analysis-diagnosis-2026-09-30/inv-a'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
EXPECTED_STATUS = {'v2d-dev5': ('VALID_REQUESTED', 'model', 1), 'v2e-dev5': ('VALID_NO_REQUEST', 'model', 1),
                   'v2f-dev5': ('VALID_REQUESTED', 'model', 2), 'v2g-dev5': ('INVALID_OUTPUT', 'code_default', 2),
                   'v2g-dev6': ('VALID_REQUESTED', 'model', 1)}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class Capture:
    def __init__(self, answers): self.answers = list(answers); self.requests = []
    def role_model(self, role): return MODEL
    async def complete(self, messages, **kwargs):
        from app.providers.runtime import RuntimeGeneration
        self.requests.append(json.loads(json.dumps(messages)))
        return RuntimeGeneration(self.answers.pop(0), MODEL)


class Ledger:
    def consume_call(self, **kwargs): pass
    def reconcile(self, generation): pass


async def main():
    from app.agents.mechanic import Mechanic
    from app.contracts.models import canonical_json, content_hash
    from app.lab import diagnosis_guide, diagnosis_protocol
    from app.lab.exports import development_recording
    from app.lab.run_plans import SavedRunPlan, read_run_plan
    from app.lab.storage import LabStore, ReadOnlyLabStore
    rebuild = load(INV_A / 'rebuild_diagnosis_requests.py', 'inv_a_rebuild')
    out = {'saved_store': str(SAVED), 'saved_store_sha256_before': sha256(SAVED)}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    copy = SCRATCH / 'lab-copy.sqlite3'
    src = sqlite3.connect(f'file:{SAVED}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy)
    try:
        src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst.close(); src.close()
    old_exports_source = subprocess.run(['git', 'show', '626bae4:backend/app/lab/exports.py'], cwd=FAULTLAB, check=True,
                                        capture_output=True, text=True).stdout
    old_exports = types.ModuleType('exports_at_626bae4')
    exec(compile(old_exports_source, 'exports_at_626bae4.py', 'exec'), old_exports.__dict__)
    out['exports_626bae4_sha256'] = hashlib.sha256(old_exports_source.encode()).hexdigest()
    store = ReadOnlyLabStore(copy)
    try:
        plans = []
        for raw in store.list_records('campaign_plans'):
            read = read_run_plan(store, raw['campaign_id'])['plan']
            campaign = types.SimpleNamespace(campaign_id=raw['campaign_id'])
            plans.append({'campaign_id': raw['campaign_id'], 'mode': raw['mode'], 'agent': raw['agent'],
                          'reads_byte_for_byte': read == raw and canonical_json(read) == canonical_json(raw),
                          'reserializes_byte_for_byte': SavedRunPlan.model_validate(raw).model_dump(mode='json') == raw,
                          'plan_hash_unchanged': raw['plan_hash'] == content_hash({k: v for k, v in raw.items() if k != 'plan_hash'}),
                          'declares_mechanic_diagnosis': 'mechanic_diagnosis' in read, 'declares_diagnosis_guide': 'diagnosis_guide' in read,
                          'rule_1_for_campaign': diagnosis_protocol.campaign_rule(store, campaign),
                          'rule_2_for_campaign': diagnosis_guide.campaign_rule(store, campaign)})
        out['plans'] = plans
        exports = []
        for row in plans:
            new = canonical_json(development_recording(store, row['campaign_id']))
            old = canonical_json(old_exports.development_recording(store, row['campaign_id']))
            exports.append({'campaign_id': row['campaign_id'], 'byte_identical': new == old,
                            'sha256': hashlib.sha256(new.encode()).hexdigest(), 'has_diagnosis_requests': '"diagnosis_requests"' in new})
        out['exports'] = exports
        index = json.loads((INV_A / 'rebuild-index.json').read_text())
        diagnoses = {}
        for name, run, campaign_id, counterexample_id in rebuild.DIAGNOSES:
            counter, context, wrappers, _ = await rebuild.rebuild(store, campaign_id, counterexample_id)
            saved_request = json.loads((INV_A / f'{name}-diagnosis-request.json').read_text())
            raws = [store.get_record('mechanic_outputs', ref)['raw'] for ref in index[name]['mechanic_output_record_ids']]
            result = {'wrappers': wrappers, 'saved_answers': len(raws)}
            for flag in (False, True):
                capture = Capture(raws)
                scratch_store = LabStore(':memory:')
                mechanic = Mechanic(capture, scratch_store, Ledger())
                chain = mechanic
                if flag:
                    mechanic.diagnosis_protocol = diagnosis_protocol.declaration()
                    chain = diagnosis_protocol.RecordingDiagnosisMechanic(mechanic, mechanic)
                ref, proposal, got = await chain.diagnose(context)
                label = 'rule_on' if flag else 'rule_off'
                result[label] = {'turns_sent': len(capture.requests),
                                 'turns_equal_saved': [sent == turn['messages'] for sent, turn in zip(capture.requests, saved_request['turns'])],
                                 'raws_verbatim': got == raws[:len(got)], 'valid_answer': proposal is not None}
                if flag:
                    recorded = store.get_record('diagnostics', index[name]['recorded_diagnostic_id'])
                    experiments = [types.SimpleNamespace(intervention_id=e['intervention_id'], result=e['result'], trial_pairs=e['trial_pairs'],
                                                         limitations=e['limitations'])
                                   for e in (store.get_record('interventions', i) for i in recorded['intervention_ids'])]
                    diagnostic = types.SimpleNamespace(diagnostic_id=recorded['diagnostic_id'], proposed_kind=recorded['proposed_kind'],
                                                       kind=recorded['kind'])
                    record = diagnosis_protocol.build_record(types.SimpleNamespace(campaign_id=campaign_id), counter, diagnostic,
                                                             types.SimpleNamespace(experiments=experiments, trials=[]), chain)
                    result['record'] = {k: record[k] for k in ('proposal_status', 'recorded_proposed_kind', 'recorded_proposed_kind_source',
                                                               'requested_intervention_id', 'requested_change', 'intervention_ran', 'verdict',
                                                               'last_raw_unvalidated', 'statement')}
                    result['record']['attempt_errors'] = [a['validation_errors'] for a in record['attempts']]
                    status, source, attempts = EXPECTED_STATUS[name]
                    result['record_as_predicted'] = (record['proposal_status'] == status and record['recorded_proposed_kind_source'] == source
                                                     and len(record['attempts']) == attempts)
                    if len(capture.requests) == 2:
                        result['rule_on']['repair_message'] = json.loads(capture.requests[1][3]['content'])
                        result['rule_on']['repair_turn_equals_saved'] = capture.requests[1] == saved_request['turns'][1]['messages']
                    result['rule_on']['first_turn_equals_saved'] = capture.requests[0] == saved_request['turns'][0]['messages']
                scratch_store.close()
            diagnoses[name] = result
        out['diagnoses'] = diagnoses
    finally:
        store.close()
        for suffix in ('', '-wal', '-shm', '-journal'):
            Path(str(copy) + suffix).unlink(missing_ok=True)
    out['scratch_copy_deleted'] = not any(Path(str(copy) + s).exists() for s in ('', '-wal', '-shm', '-journal'))
    out['saved_store_sha256_after'] = sha256(SAVED)
    out['saved_store_unchanged'] = out['saved_store_sha256_before'] == out['saved_store_sha256_after']
    out['summary'] = {
        'plans': len(out['plans']),
        'plans_all_read_and_reserialize_byte_for_byte': all(p['reads_byte_for_byte'] and p['reserializes_byte_for_byte'] and p['plan_hash_unchanged'] for p in out['plans']),
        'plans_declaring_either_rule': sum(p['declares_mechanic_diagnosis'] or p['declares_diagnosis_guide'] or p['rule_1_for_campaign'] is not None
                                           or p['rule_2_for_campaign'] is not None for p in out['plans']),
        'exports_byte_identical_old_vs_new': f"{sum(e['byte_identical'] for e in out['exports'])}/{len(out['exports'])}",
        'diagnosis_requests_rule_off_equal_saved': all(all(d['rule_off']['turns_equal_saved']) and d['rule_off']['turns_sent'] == len(d['rule_off']['turns_equal_saved'])
                                                       for d in out['diagnoses'].values()),
        'rule_on_first_turn_equal_saved': all(d['rule_on']['first_turn_equals_saved'] for d in out['diagnoses'].values()),
        'records_as_predicted': {name: d['record_as_predicted'] for name, d in out['diagnoses'].items()},
        'saved_store_unchanged': out['saved_store_unchanged'], 'scratch_copy_deleted': out['scratch_copy_deleted']}
    print(json.dumps(out, indent=1, sort_keys=True, default=str))


if __name__ == '__main__':
    asyncio.run(main())
