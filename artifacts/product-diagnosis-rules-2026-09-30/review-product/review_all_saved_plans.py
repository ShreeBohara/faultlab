"""Review check ($0, offline): every saved plan in every saved lab store re-reads byte for byte under this build, and every
planned campaign's development recording is byte-identical under this build's exports.py and the backup tip's.

Wider than the builder's check (native-v2b only). Each original store is opened only by sqlite's backup API with
mode=ro&immutable=1 (its -wal file is checked to be empty first); sha256 before and after; the scratch copy lives under
/Users/shree/FaultLab_Scratch/product-diagnosis-rules/review-product/ and is deleted. Run from faultlab/backend:
  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/review-product/review_all_saved_plans.py
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402,F401

FAULTLAB = HERE.parents[2]
RUNS = Path('/Users/shree/FaultLab_Runs')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/product-diagnosis-rules/review-product')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    from app.contracts.models import canonical_json, content_hash
    from app.lab import diagnosis_guide, diagnosis_protocol
    from app.lab.exports import development_recording
    from app.lab.run_plans import SavedRunPlan, read_run_plan
    from app.lab.storage import ReadOnlyLabStore
    old_source = subprocess.run(['git', 'show', '626bae4:backend/app/lab/exports.py'], cwd=FAULTLAB, check=True,
                                capture_output=True, text=True).stdout
    old = types.ModuleType('exports_626bae4'); exec(compile(old_source, 'exports_626bae4.py', 'exec'), old.__dict__)
    stores = sorted(p for p in RUNS.glob('*/*/lab.sqlite3')) + sorted(p for p in RUNS.glob('*/*/*/lab.sqlite3'))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    report = []
    for saved in stores:
        wal = Path(str(saved) + '-wal')
        row = {'store': str(saved), 'sha256_before': sha(saved), 'wal_bytes': wal.stat().st_size if wal.exists() else None}
        copy = SCRATCH / 'plans-copy.sqlite3'
        src = sqlite3.connect(f'file:{saved}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy)
        try:
            src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
        finally:
            dst.close(); src.close()
        store = ReadOnlyLabStore(copy)
        try:
            plans = store.list_records('campaign_plans')
            checks = []
            for raw in plans:
                read = read_run_plan(store, raw['campaign_id'])['plan']
                campaign = types.SimpleNamespace(campaign_id=raw['campaign_id'])
                new_rec = canonical_json(development_recording(store, raw['campaign_id']))
                old_rec = canonical_json(old.development_recording(store, raw['campaign_id']))
                checks.append({'campaign_id': raw['campaign_id'], 'mode': raw.get('mode'), 'agent': raw.get('agent'),
                               'reads_byte_for_byte': canonical_json(read) == canonical_json(raw),
                               'reserializes': SavedRunPlan.model_validate(raw).model_dump(mode='json') == raw,
                               'plan_hash_ok': raw['plan_hash'] == content_hash({k: v for k, v in raw.items() if k != 'plan_hash'}),
                               'declares_a_rule': bool({'mechanic_diagnosis', 'diagnosis_guide'} & set(read))
                                                  or diagnosis_protocol.campaign_rule(store, campaign) is not None
                                                  or diagnosis_guide.campaign_rule(store, campaign) is not None,
                               'recording_identical_old_vs_new': new_rec == old_rec})
            row['plans'] = len(plans)
            row['all_ok'] = all(c['reads_byte_for_byte'] and c['reserializes'] and c['plan_hash_ok'] and not c['declares_a_rule']
                                and c['recording_identical_old_vs_new'] for c in checks)
            row['failures'] = [c for c in checks if not (c['reads_byte_for_byte'] and c['reserializes'] and c['plan_hash_ok']
                                                          and not c['declares_a_rule'] and c['recording_identical_old_vs_new'])]
        except Exception as error:  # recorded, never hidden
            row['error'] = f'{type(error).__name__}: {error}'
        finally:
            store.close()
            for suffix in ('', '-wal', '-shm', '-journal'):
                Path(str(copy) + suffix).unlink(missing_ok=True)
        row['sha256_after'] = sha(saved)
        row['unchanged'] = row['sha256_before'] == row['sha256_after']
        report.append(row)
    print(json.dumps({'stores': report, 'summary': {'stores': len(report), 'plans': sum(r.get('plans', 0) for r in report),
                                                    'all_ok': all(r.get('all_ok') for r in report),
                                                    'all_unchanged': all(r['unchanged'] for r in report),
                                                    'errors': [r['store'] for r in report if 'error' in r]}}, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
