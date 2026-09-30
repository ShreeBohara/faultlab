import json, sqlite3
db = sqlite3.connect('/Users/shree/FaultLab_Scratch/review-product-v4/ui/lab/lab.sqlite3', timeout=30)
study = next(json.loads(p) for (p,) in db.execute("select payload from records where kind='baseline_studies'"))
b0 = [t['episode_id'] for t in study['trials'] if t['arm'] == 'B0']
target = b0[0]
row = db.execute("select payload from records where kind='evidence' and id=?", (target,)).fetchone()
payload = json.loads(row[0]); before = payload.get('source'); payload['source'] = 'local_only'
db.execute("update records set payload=? where kind='evidence' and id=?", (json.dumps(payload), target)); db.commit()
print(json.dumps({'episode_id': target, 'evidence_source_before': before, 'after': 'local_only'}))
