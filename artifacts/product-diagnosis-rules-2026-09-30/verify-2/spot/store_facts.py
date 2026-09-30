"""Verifier-2: read facts the pinned saved-store tests depend on, from a scratch COPY of the native-v2b store
(opened mode=ro&immutable=1; the original is never opened). $0, offline, stdlib only."""
import json, sqlite3, sys
db = sqlite3.connect('file:/Users/shree/FaultLab_Scratch/verify-2/store/lab.sqlite3?mode=ro&immutable=1', uri=True)
print('records table:', db.execute("select sql from sqlite_master where name='records'").fetchone()[0])
mx = db.execute('select max(rowid), count(*) from records').fetchone()
print('max rowid, count:', mx)
plans = db.execute("select rowid, id, payload from records where kind='campaign_plans' order by rowid").fetchall()
for rowid, ident, payload in plans:
    p = json.loads(payload); h = (p.get('discovery') or {}).get('history') or {}
    print(f'plan row {rowid} {ident} mode={p.get("mode")} protocol={(p.get("discovery") or {}).get("protocol")} '
          f'cutoff={h.get("record_cutoff")} summary={str(h.get("summary_hash"))[:8]} episodes={(h.get("summary") or {}).get("verified_episodes")} '
          f'keys_new={[k for k in ("explorer_selection","mechanic_diagnosis","diagnosis_guide") if k in p]}')
print('plans at or below 6748:', sum(1 for r in plans if r[0] <= 6748), '| at or below 8583:', sum(1 for r in plans if r[0] <= 8583))
v2d = 'campaign-ea66672d7a904bd8a011d6922790c963'
print('v2d campaign row:', db.execute("select rowid from records where kind='campaigns' and id=?", (v2d,)).fetchone())
rows = db.execute("select rowid from records where payload like ? order by rowid", (f'%{v2d}%',)).fetchall()
print('rows mentioning v2d: max', max(r[0] for r in rows), 'count', len(rows))
sel = db.execute("select rowid, payload from records where kind='selections' order by rowid").fetchall()
print('selections total', len(sel), '| at or below 6748:', sum(1 for r in sel if r[0] <= 6748))
print('selections above 6748:', [r[0] for r in sel if r[0] > 6748][:40])
print('rows above 6748 by kind:', dict(db.execute("select kind, count(*) from records where rowid>6748 group by kind").fetchall()))
print('gaps in rowid:', db.execute('select count(*) from records').fetchone()[0] != mx[0])
