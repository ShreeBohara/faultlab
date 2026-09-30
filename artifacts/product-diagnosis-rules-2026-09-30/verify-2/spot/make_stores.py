#!/usr/bin/env python3
"""Verifier-2 ($0, offline, stdlib): build scratch store variants from the verifier's own scratch COPY of the saved
native-v2b store (the original under /Users/shree/FaultLab_Runs is never opened here).
  lab-upto-6748.sqlite3 / lab-upto-3022.sqlite3: records above the cutoff deleted (plus orphaned episode rows, and the
      active-policy pointer of a campaign whose record is gone);
  lab-grown.sqlite3: today's store plus synthetic records a later live run could write, all above row 8583:
      G1 a copy of v2d's first matching challenge evaluation under a new id, its trials under new episode ids, with
         copies of those episodes' evidence records (so the unpinned v2d rebuild would pull it in);
      G2 a copy of every Explorer selection at or below row 6748 under a new id (so unpinned pick counts would change);
      G3 a copy of v2g's saved plan under a new campaign id that also declares mechanic_diagnosis (plan hash recomputed).
Prints what was written."""
import hashlib, json, shutil, sqlite3
D = '/Users/shree/FaultLab_Scratch/verify-2/store'
SRC = f'{D}/lab.sqlite3'
def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
def chash(v): return hashlib.sha256(canonical(v).encode('utf-8')).hexdigest()
for cut in (6748, 3022):
    dst = f'{D}/lab-upto-{cut}.sqlite3'; shutil.copyfile(SRC, dst); d = sqlite3.connect(dst)
    removed = d.execute('DELETE FROM records WHERE rowid>?', (cut,)).rowcount
    orphan = "SELECT id FROM episode_registry WHERE id NOT IN (SELECT id FROM records WHERE kind='episodes')"
    ev = d.execute(f'DELETE FROM events WHERE episode_id IN ({orphan})').rowcount
    ik = d.execute(f'DELETE FROM ingestion_keys WHERE episode_id IN ({orphan})').rowcount
    er = d.execute(f'DELETE FROM episode_registry WHERE id IN ({orphan})').rowcount
    pt = d.execute("DELETE FROM pointers WHERE substr(name, 15) NOT IN (SELECT id FROM records WHERE kind='campaigns')").rowcount
    d.commit(); mx = d.execute('SELECT MAX(rowid) FROM records').fetchone()[0]; d.execute('VACUUM'); d.close()
    print(f'upto {cut}: removed records {removed}, events {ev}, ingestion_keys {ik}, episode_registry {er}, pointers {pt}; max row now {mx}')
dst = f'{D}/lab-grown.sqlite3'; shutil.copyfile(SRC, dst); d = sqlite3.connect(dst)
put = lambda kind, ident, payload, imm=0: d.execute('INSERT INTO records(kind,id,payload,immutable) VALUES (?,?,?,?)', (kind, ident, canonical(payload), imm))
V2D = 'campaign-ea66672d7a904bd8a011d6922790c963'
qual = next(json.loads(p) for (p,) in d.execute("SELECT payload FROM records WHERE kind='candidate_qualifications' ORDER BY rowid") if json.loads(p)['campaign_id'] == V2D)
chal = json.loads(d.execute("SELECT payload FROM records WHERE kind='challenges' AND id=?", (qual['challenge_ref'],)).fetchone()[0])
rowid, raw = next((r, json.loads(p)) for r, p in d.execute("SELECT rowid, payload FROM records WHERE kind='evaluations' ORDER BY rowid")
                  if json.loads(p).get('purpose') == 'challenge' and (json.loads(p)['candidate_hash'], json.loads(p)['incumbent_hash']) == (chal['candidate_hash'], chal['incumbent_hash']))
text = canonical(raw); new_ids = {}
for t in raw['trials']:
    new_ids[t['episode_id']] = t['episode_id'] + 'g'
for old, new in new_ids.items():
    text = text.replace(old, new)
clone = json.loads(text); clone['batch_id'] = raw.get('batch_id', 'x') + '-grown' if 'batch_id' in raw else raw.get('batch_id')
eval_id = d.execute("SELECT id FROM records WHERE kind='evaluations' AND rowid=?", (rowid,)).fetchone()[0]
put('evaluations', eval_id + '-grown', clone)
copied_evidence = 0
for old, new in new_ids.items():
    row = d.execute("SELECT payload, immutable FROM records WHERE kind='evidence' AND id=?", (old,)).fetchone()
    if row:
        put('evidence', new, json.loads(row[0].replace(old, new)), row[1]); copied_evidence += 1
print(f'G1: copied evaluation at row {rowid} ({len(new_ids)} trials) and {copied_evidence} evidence records')
sels = d.execute("SELECT id, payload, immutable FROM records WHERE kind='selections' AND rowid<=6748 ORDER BY rowid").fetchall()
for ident, payload, imm in sels:
    put('selections', ident + '-grown', json.loads(payload), imm)
print(f'G2: copied {len(sels)} selections')
v2g = json.loads(d.execute("SELECT payload FROM records WHERE kind='campaign_plans' AND id='campaign-d8d1e8cc0ea34feb92dbd8c22c264530'").fetchone()[0])
later = dict(v2g); later['campaign_id'] = 'campaign-00000000000000000000000000000abc'
later['mechanic_diagnosis'] = {'protocol': 'faultlab-mechanic-diagnosis/v1-repair-and-record'}
later['plan_hash'] = chash({k: v for k, v in later.items() if k != 'plan_hash'})
put('campaign_plans', later['campaign_id'], later, 1)
print('G3: later plan', later['campaign_id'])
d.commit(); print('grown: rows', d.execute('SELECT MIN(rowid) FROM records WHERE id LIKE ? OR id LIKE ?', ('%-grown', '%g')).fetchone(),
                  'max row', d.execute('SELECT MAX(rowid) FROM records').fetchone()[0]); d.close()
