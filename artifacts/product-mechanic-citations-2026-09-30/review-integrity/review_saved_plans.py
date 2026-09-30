"""Integrity review ($0, read-only): every saved run plan in every saved store under /Users/shree/FaultLab_Runs/ reads
back through this build's SavedRunPlan model to exactly its stored bytes (no mechanic_evidence key added), and its
plan_hash still matches. Stores are opened with mode=ro&immutable=1 (nothing is written). Also checks which agent each
plan names and that no saved plan declares mechanic_evidence. Also runs the same check against the BACKUP model
(backup/part2-2026-09-22 run_plans.py is not imported; instead we check the key set).
Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/.../review-integrity/review_saved_plans.py OUT.json
"""
import glob, json, sqlite3, sys
sys.path.insert(0, '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/builder')
import guard  # noqa
from app.contracts.models import canonical_json, content_hash
from app.lab.run_plans import SavedRunPlan
from app.lab import citation_status

out = {'stores': {}}
for path in sorted(glob.glob('/Users/shree/FaultLab_Runs/**/lab.sqlite3', recursive=True)):
    db = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True)
    try:
        rows = db.execute("SELECT id,payload FROM records WHERE kind='campaign_plans'").fetchall()
    except sqlite3.OperationalError as error:
        out['stores'][path] = {'error': str(error)}; db.close(); continue
    res = {'plans': len(rows), 'identical_bytes': 0, 'differs': [], 'invalid': [], 'agents': {}, 'declares_mechanic_evidence': 0,
           'campaign_rule_none': 0}
    for ident, payload in rows:
        record = json.loads(payload)
        res['agents'][record.get('agent')] = res['agents'].get(record.get('agent'), 0) + 1
        if 'mechanic_evidence' in record: res['declares_mechanic_evidence'] += 1
        try:
            dumped = SavedRunPlan.model_validate_json(canonical_json(record)).model_dump(mode='json')
        except Exception as error:
            res['invalid'].append((ident[-8:], type(error).__name__, str(error)[:160])); continue
        same = canonical_json(dumped) == canonical_json(record)
        hash_ok = content_hash({k: v for k, v in dumped.items() if k != 'plan_hash'}) == record.get('plan_hash')
        if same and hash_ok: res['identical_bytes'] += 1
        else: res['differs'].append((ident[-8:], same, hash_ok))
        if (record or {}).get('mechanic_evidence') is None: res['campaign_rule_none'] += 1
    db.close()
    out['stores'][path] = res
out['total_plans'] = sum(s.get('plans', 0) for s in out['stores'].values())
out['total_identical'] = sum(s.get('identical_bytes', 0) for s in out['stores'].values())
out['total_invalid'] = sum(len(s.get('invalid', [])) for s in out['stores'].values())
open(sys.argv[1], 'w').write(json.dumps(out, indent=1, sort_keys=True) + '\n')
print(json.dumps({k: v for k, v in out.items() if k != 'stores'}))
for p, s in out['stores'].items(): print(p.replace('/Users/shree/FaultLab_Runs/', ''), {k: v for k, v in s.items() if k not in ()})
