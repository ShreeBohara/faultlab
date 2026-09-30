"""Review check 2 ($0, offline): replay the five saved native-v2 diagnoses through the product's Rule 1 code.

Independent of the builder's saved_store_check.py: the diagnosis context is taken straight from the pinned probe-inputs
copy of investigation A's rebuilt request (not rebuilt again), and every answer, diagnostic and intervention comes from a
scratch copy of the saved native-v2b store. Run from faultlab/backend:
  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/review-product/review_replay_saved_diagnoses.py

The original store is opened only through sqlite's backup API with mode=ro&immutable=1; its sha256 is recorded before and
after; the copy lives under /Users/shree/FaultLab_Scratch/product-diagnosis-rules/review-product/ and is deleted.
"""
import asyncio
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402,F401

FAULTLAB = HERE.parents[2]
SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/product-diagnosis-rules/review-product')
INPUTS = FAULTLAB / 'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs'
INV_A = FAULTLAB / 'artifacts/analysis-diagnosis-2026-09-30/inv-a'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
MEMO = {'v2d-dev5': 'VALID_REQUESTED', 'v2e-dev5': 'VALID_NO_REQUEST', 'v2f-dev5': 'VALID_REQUESTED',
        'v2g-dev5': 'INVALID_OUTPUT', 'v2g-dev6': 'VALID_REQUESTED'}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
    from app.contracts.models import content_hash
    from app.lab import diagnosis_protocol
    from app.lab.storage import LabStore, ReadOnlyLabStore
    out = {'saved_store': str(SAVED), 'sha256_before': sha(SAVED)}
    # The inputs the probe and the tests use are byte copies of inv-a's files.
    out['probe_inputs_equal_inv_a'] = {n: sha(INPUTS / f'{n}-diagnosis-request.json') == sha(INV_A / f'{n}-diagnosis-request.json') for n in MEMO}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    copy = SCRATCH / 'lab-copy.sqlite3'
    src = sqlite3.connect(f'file:{SAVED}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy)
    try:
        src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst.close(); src.close()
    index = json.loads((INV_A / 'rebuild-index.json').read_text())
    store = ReadOnlyLabStore(copy)
    rows = {}
    try:
        for name in MEMO:
            saved = json.loads((INPUTS / f'{name}-diagnosis-request.json').read_text())
            first = saved['turns'][0]['messages']
            context = {k: v for k, v in json.loads(first[1]['content']).items() if k != 'output_schema'}
            refs = index[name]['mechanic_output_record_ids']
            outputs = [store.get_record('mechanic_outputs', ref) for ref in refs]
            raws = [o['raw'] for o in outputs]
            diagnostic_saved = store.get_record('diagnostics', index[name]['recorded_diagnostic_id'])
            experiments_saved = [store.get_record('interventions', i) for i in diagnostic_saved['intervention_ids']]
            row = {'saved_attempts': len(raws), 'saved_request_ids': sorted({o['request_id'] for o in outputs}),
                   'saved_attempt_numbers': [o['attempt'] for o in outputs],
                   'saved_hypothesis_lengths': [len((json.loads(r) if r.strip().startswith('{') else {}).get('hypothesis') or '') for r in raws],
                   'saved_kind': diagnostic_saved['kind'], 'saved_proposed_kind': diagnostic_saved['proposed_kind'],
                   'saved_intervention_results': [e['result'] for e in experiments_saved],
                   'saved_intervention_change_field': [e['change'] for e in experiments_saved]}
            if len(raws) == 2:
                row['saved_attempt_raws_byte_identical'] = raws[0] == raws[1]
            for flag in (False, True):
                capture, scratch = Capture(raws), LabStore(':memory:')
                mechanic = Mechanic(capture, scratch, Ledger())
                chain = mechanic
                if flag:
                    mechanic.diagnosis_protocol = diagnosis_protocol.declaration()
                    chain = diagnosis_protocol.RecordingDiagnosisMechanic(mechanic, mechanic)
                ref, proposal, got = await chain.diagnose(context)
                key = 'on' if flag else 'off'
                row[f'rule_{key}_turns'] = len(capture.requests)
                row[f'rule_{key}_first_turn_equals_saved'] = capture.requests[0] == first
                if len(capture.requests) == 2:
                    saved_repair = saved['turns'][1]['messages']
                    row[f'rule_{key}_repair_equals_saved'] = capture.requests[1] == saved_repair
                    row[f'rule_{key}_repair_first_three_messages_equal_saved'] = capture.requests[1][:3] == saved_repair[:3]
                    if flag:
                        row['rule_on_repair_message'] = json.loads(capture.requests[1][3]['content'])
                row[f'rule_{key}_valid'] = proposal is not None
                if flag:
                    counter = SimpleNamespace(counterexample_id=saved['counterexample_id'], target_invariant=context['target_invariant'])
                    diagnostic = SimpleNamespace(diagnostic_id=diagnostic_saved['diagnostic_id'], proposed_kind=diagnostic_saved['proposed_kind'],
                                                 kind=diagnostic_saved['kind'])
                    experiments = [SimpleNamespace(intervention_id=e['intervention_id'], result=e['result'], trial_pairs=e['trial_pairs'],
                                                   limitations=e['limitations']) for e in experiments_saved]
                    record = diagnosis_protocol.build_record(SimpleNamespace(campaign_id=saved['campaign_id']), counter, diagnostic,
                                                             SimpleNamespace(experiments=experiments, trials=[]), chain)
                    row['record'] = {k: record[k] for k in ('proposal_status', 'recorded_proposed_kind', 'recorded_proposed_kind_source',
                                                           'requested_intervention_id', 'requested_change', 'intervention_ran', 'verdict',
                                                           'last_raw_unvalidated', 'statement')}
                    row['record']['attempt_errors'] = [a['validation_errors'] for a in record['attempts']]
                    row['record']['options'] = [(o['intervention_id'], o['change']) for o in record['options']]
                    row['record_first_turn_hash_is_saved_first_turn'] = record['first_turn_hash'] == content_hash(first)
                    row['checks'] = {
                        'status_as_memo_predicted': record['proposal_status'] == MEMO[name],
                        'attempt_count_equals_saved': len(record['attempts']) == len(raws),
                        'requested_id_ran_equals_saved_interventions': ([record['requested_intervention_id']] if record['intervention_ran'] else [])
                                                                     == diagnostic_saved['intervention_ids'],
                        'verdict_equals_saved': record['verdict'] == diagnostic_saved['kind'],
                        'kind_source_consistent': (record['recorded_proposed_kind_source'] == 'code_default') == (record['proposal_status'] == 'INVALID_OUTPUT'),
                    }
                scratch.close()
            rows[name] = row
    finally:
        store.close()
        for suffix in ('', '-wal', '-shm', '-journal'):
            Path(str(copy) + suffix).unlink(missing_ok=True)
    out['diagnoses'] = rows
    out['scratch_copy_deleted'] = not any(Path(str(copy) + s).exists() for s in ('', '-wal', '-shm', '-journal'))
    out['sha256_after'] = sha(SAVED)
    out['saved_store_unchanged'] = out['sha256_before'] == out['sha256_after']
    out['summary'] = {name: (r['record']['proposal_status'], r['record']['recorded_proposed_kind_source'], len(r['record']['attempt_errors']),
                             all(r['checks'].values()), r['rule_off_first_turn_equals_saved'] and r['rule_on_first_turn_equals_saved'])
                      for name, r in rows.items()}
    print(json.dumps(out, indent=1, sort_keys=True, default=str))


if __name__ == '__main__':
    asyncio.run(main())
