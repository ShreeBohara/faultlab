"""For each saved plan, the canonical dump under the model importable from the current working directory's app package
(run once from the Desktop backend, once from the scratch backup backend) -- prints a hash per plan so the two builds can
be compared. Read-only (mode=ro&immutable=1). $0."""
import glob, json, sqlite3, sys
sys.path.insert(0, '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/builder')
import guard  # noqa
import app
from app.contracts.models import canonical_json, content_hash
from app.lab.run_plans import SavedRunPlan
res = {'app_file': app.__file__, 'plans': {}}
for path in sorted(glob.glob('/Users/shree/FaultLab_Runs/**/lab.sqlite3', recursive=True)):
    db = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True)
    try: rows = db.execute("SELECT id,payload FROM records WHERE kind='campaign_plans'").fetchall()
    except sqlite3.OperationalError: rows = []
    for ident, payload in rows:
        record = json.loads(payload)
        try:
            dumped = SavedRunPlan.model_validate_json(canonical_json(record)).model_dump(mode='json')
            extra = sorted(set(dumped) - set(record)); missing = sorted(set(record) - set(dumped))
            changed = sorted(k for k in set(dumped) & set(record) if dumped[k] != record[k])
            res['plans'][ident] = {'dump_hash': content_hash(dumped), 'added_keys': extra, 'dropped_keys': missing, 'changed_keys': changed}
        except Exception as error:
            res['plans'][ident] = {'error': type(error).__name__}
    db.close()
open(sys.argv[1], 'w').write(json.dumps(res, indent=1, sort_keys=True) + '\n')
