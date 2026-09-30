"""Verifier check ($0, offline): every plan saved in every saved lab store under /Users/shree/FaultLab_Runs re-reads byte
for byte under the final code (fixer end state), keeps its plan_hash, gains no key, declares neither diagnosis rule, and
every such campaign's development recording is byte-identical under the final exports.py and the backup tip's (626bae4).

Each original store is opened only through sqlite's backup API with file:...?mode=ro&immutable=1 (its -wal size is
recorded first; immutable=1 would not see a non-empty WAL, so such a store is reported, not silently read). The copy lives
under /Users/shree/FaultLab_Scratch/verify-diagnosis-rules/saved-plans/ and is deleted after each store; sha256 of each
original before and after. Run from faultlab/backend with ../.venv/bin/python -B.
"""
import hashlib, json, sqlite3, subprocess, sys, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import vguard  # noqa: E402,F401
sys.path.insert(0, '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend')
FAULTLAB = Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab')
RUNS = Path('/Users/shree/FaultLab_Runs')
SCRATCH = Path('/Users/shree/FaultLab_Scratch/verify-diagnosis-rules/saved-plans')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


from app.contracts.models import canonical_json, content_hash  # noqa: E402
from app.lab import diagnosis_guide, diagnosis_protocol  # noqa: E402
from app.lab.exports import development_recording  # noqa: E402
from app.lab.run_plans import SavedRunPlan, read_run_plan  # noqa: E402
from app.lab.storage import ReadOnlyLabStore  # noqa: E402

old_src = subprocess.run(['git', 'show', '626bae4:backend/app/lab/exports.py'], cwd=FAULTLAB, check=True, capture_output=True, text=True,
                         env={'GIT_OPTIONAL_LOCKS': '0', 'PATH': '/usr/bin:/bin'}).stdout
old = types.ModuleType('exports_626bae4'); exec(compile(old_src, 'exports_626bae4.py', 'exec'), old.__dict__)
stores = sorted(set(RUNS.glob('*/*/lab.sqlite3')) | set(RUNS.glob('*/*/*/lab.sqlite3')))
SCRATCH.mkdir(parents=True, exist_ok=True)
report, total_plans, bad = [], 0, 0
for saved in stores:
    wal = Path(str(saved) + '-wal')
    row = {'store': str(saved), 'sha256_before': sha(saved), 'wal_bytes': wal.stat().st_size if wal.exists() else None}
    copy = SCRATCH / 'copy.sqlite3'
    src = sqlite3.connect(f'file:{saved}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy)
    try:
        src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst.close(); src.close()
    store = ReadOnlyLabStore(copy)
    try:
        plans = store.list_records('campaign_plans'); fails = []
        for raw in plans:
            read = read_run_plan(store, raw['campaign_id'])['plan']
            ns = types.SimpleNamespace(campaign_id=raw['campaign_id'])
            ok = {'bytes': canonical_json(read) == canonical_json(raw),
                  'reserializes': SavedRunPlan.model_validate(raw).model_dump(mode='json') == raw,
                  'plan_hash': raw['plan_hash'] == content_hash({k: v for k, v in raw.items() if k != 'plan_hash'}),
                  'no_rule': not ({'mechanic_diagnosis', 'diagnosis_guide'} & set(read)) and diagnosis_protocol.campaign_rule(store, ns) is None
                             and diagnosis_guide.campaign_rule(store, ns) is None,
                  'recording_same': canonical_json(development_recording(store, raw['campaign_id'])) == canonical_json(old.development_recording(store, raw['campaign_id']))}
            if not all(ok.values()): fails.append({'campaign_id': raw['campaign_id'], **ok})
        row.update(plans=len(plans), failures=fails); total_plans += len(plans); bad += len(fails)
    except Exception as error:  # recorded, never hidden
        row['error'] = f'{type(error).__name__}: {error}'; bad += 1
    finally:
        store.close()
        for suffix in ('', '-wal', '-shm', '-journal'):
            Path(str(copy) + suffix).unlink(missing_ok=True)
    row['sha256_after'] = sha(saved); row['unchanged'] = row['sha256_before'] == row['sha256_after']
    report.append(row)
SCRATCH.rmdir()
summary = {'stores': len(report), 'plans': total_plans, 'plans_or_stores_failing': bad, 'all_stores_unchanged': all(r['unchanged'] for r in report),
           'stores_with_nonempty_wal': [r['store'] for r in report if r['wal_bytes']], 'scratch_deleted': not SCRATCH.exists()}
print(json.dumps({'summary': summary, 'stores': report}, indent=1))
print('[saved_plans_check]', json.dumps(summary), file=sys.stderr)
