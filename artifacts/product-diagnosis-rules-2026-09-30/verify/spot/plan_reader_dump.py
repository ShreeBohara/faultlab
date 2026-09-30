"""Verifier ($0, offline): for ONE code tree, read every saved plan in every saved store with that tree's read_run_plan and
SavedRunPlan, and print, per plan, the sha256 of the canonical read, of the canonical re-serialization and of the raw row,
the keys the read adds or drops versus the raw row, and whether the raw plan_hash is valid. Run it once with the backup
tip checkpoint (626bae4, extracted outside the Desktop) and once with the working tree, then compare the two outputs: equal
outputs mean the final code reads every saved plan exactly as the backup tip did.
Usage: <venv python> -B plan_reader_dump.py <tree root>   (stores copied via sqlite backup from file:...?mode=ro&immutable=1)
"""
import hashlib, json, os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vguard  # noqa: E402,F401
root = Path(sys.argv[1]).resolve(); backend = root / 'backend'
os.chdir(backend); sys.path.insert(0, str(backend))
from app.contracts.models import canonical_json, content_hash  # noqa: E402
import app.lab.run_plans as rp  # noqa: E402
assert rp.__file__.startswith(str(backend)), rp.__file__
from app.lab.storage import ReadOnlyLabStore  # noqa: E402
SCR = Path('/Users/shree/FaultLab_Scratch/verify-diagnosis-rules/plan-reader-' + ('checkpoint' if 'FaultLab_Scratch' in str(root) else 'work'))
SCR.mkdir(parents=True, exist_ok=True)
h = lambda s: hashlib.sha256(s.encode()).hexdigest()
out = {'tree': str(root), 'plans': {}}
runs = Path('/Users/shree/FaultLab_Runs')
for saved in sorted(set(runs.glob('*/*/lab.sqlite3')) | set(runs.glob('*/*/*/lab.sqlite3'))):
    copy = SCR / 'copy.sqlite3'
    src = sqlite3.connect(f'file:{saved}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(copy)
    src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE'); dst.close(); src.close()
    store = ReadOnlyLabStore(copy)
    try:
        for raw in store.list_records('campaign_plans'):
            read = rp.read_run_plan(store, raw['campaign_id'])['plan']
            ser = rp.SavedRunPlan.model_validate(raw).model_dump(mode='json')
            out['plans'][str(saved).replace(str(runs) + '/', '') + '#' + raw['campaign_id']] = {
                'raw_sha256': h(canonical_json(raw)), 'read_sha256': h(canonical_json(read)), 'serialized_sha256': h(canonical_json(ser)),
                'raw_plan_hash_valid': raw['plan_hash'] == content_hash({k: v for k, v in raw.items() if k != 'plan_hash'}),
                'read_added_keys': sorted(set(read) - set(raw)), 'read_dropped_keys': sorted(set(raw) - set(read)),
                'read_added_non_null': sorted(k for k in set(read) - set(raw) if read[k] is not None),
                'changed_existing_keys': sorted(k for k in set(raw) & set(read) if canonical_json(raw[k]) != canonical_json(read[k]))}
    finally:
        store.close()
        for suffix in ('', '-wal', '-shm', '-journal'):
            Path(str(copy) + suffix).unlink(missing_ok=True)
SCR.rmdir()
print(json.dumps(out, indent=1, sort_keys=True))
