"""Review check ($0, offline): for every saved plan in every saved store, this build's read_run_plan and SavedRunPlan give
exactly what the backup tip's (626bae4, loaded from git show as a separate module) give. Shows that the older plans which
re-read with extra null keys (evidence_retry, transport_retry, ...) did so before this build too.
Run from faultlab/backend with the project venv and -B.
"""
import hashlib, json, sqlite3, subprocess, sys, types
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402,F401
from app.contracts.models import canonical_json  # noqa: E402
from app.lab import run_plans as new  # noqa: E402
from app.lab.storage import ReadOnlyLabStore  # noqa: E402
FAULTLAB = HERE.parents[2]
source = subprocess.run(['git', 'show', '626bae4:backend/app/lab/run_plans.py'], cwd=FAULTLAB, check=True, capture_output=True, text=True).stdout
old = types.ModuleType('app.lab.run_plans_626bae4'); old.__dict__['__name__'] = 'app.lab.run_plans_626bae4'
sys.modules['app.lab.run_plans_626bae4'] = old
exec(compile(source, 'run_plans_626bae4.py', 'exec'), old.__dict__)
SCRATCH = Path('/Users/shree/FaultLab_Scratch/product-diagnosis-rules/review-product'); SCRATCH.mkdir(parents=True, exist_ok=True)
out = []
for saved in sorted(Path('/Users/shree/FaultLab_Runs').glob('*/*/lab.sqlite3')) + sorted(Path('/Users/shree/FaultLab_Runs').glob('*/*/*/lab.sqlite3')):
    before = hashlib.sha256(saved.read_bytes()).hexdigest()
    copy = SCRATCH / 'reader-copy.sqlite3'
    src = sqlite3.connect(f'file:{saved}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy)
    src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE'); dst.close(); src.close()
    store = ReadOnlyLabStore(copy)
    try:
        for raw in store.list_records('campaign_plans'):
            a = canonical_json(new.read_run_plan(store, raw['campaign_id']))
            b = canonical_json(old.read_run_plan(store, raw['campaign_id']))
            c = canonical_json(new.SavedRunPlan.model_validate(raw).model_dump(mode='json'))
            d = canonical_json(old.SavedRunPlan.model_validate(raw).model_dump(mode='json'))
            out.append({'store': str(saved).replace('/Users/shree/FaultLab_Runs/', ''), 'campaign_id': raw['campaign_id'],
                        'read_identical_old_vs_new': a == b, 'serialize_identical_old_vs_new': c == d})
    finally:
        store.close()
        for s in ('', '-wal', '-shm', '-journal'): Path(str(copy) + s).unlink(missing_ok=True)
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == before
print(json.dumps({'plans': len(out), 'all_identical': all(r['read_identical_old_vs_new'] and r['serialize_identical_old_vs_new'] for r in out),
                  'rows': out}, indent=1))
