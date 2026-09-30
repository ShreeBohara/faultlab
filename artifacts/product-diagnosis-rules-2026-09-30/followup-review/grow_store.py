#!/usr/bin/env python3
"""Reviewer E3 ($0, offline): a scratch copy of today's native-v2b store grown by records a later live run could add.

Source: the reviewer's own scratch copy (made read-only from the saved store). Appends, above today's last row (8583):
  1. a copy of v2d's first matching challenge evaluation (rowid 2367) under a new batch id, with every trial's
     episode_id suffixed, as a later campaign challenging the same candidate against the same incumbent would write
     (the v2d rebuild matches challenge evaluations by candidate and incumbent hash, not by campaign);
  2. a discovery pick (selections) whose fault_spec mixes the orders status read with an orders update_order fault;
  3. a copy of v2g's plan under a new campaign id that also declares a mechanic_diagnosis key (a plan this build saves).
Nothing in the saved store is written; the grown copy lives under /Users/shree/FaultLab_Scratch/followup-review/store/.
"""
import copy, json, shutil, sqlite3
SRC = '/Users/shree/FaultLab_Scratch/followup-review/store/lab.sqlite3'
DST = '/Users/shree/FaultLab_Scratch/followup-review/store/lab-grown.sqlite3'
shutil.copyfile(SRC, DST)
d = sqlite3.connect(DST)
get = lambda rowid: d.execute('SELECT kind,id,payload FROM records WHERE rowid=?', (rowid,)).fetchone()
put = lambda kind, ident, payload: d.execute('INSERT INTO records(kind,id,payload,immutable) VALUES(?,?,?,1)',
                                             (kind, ident, json.dumps(payload, sort_keys=True, separators=(',', ':'))))
kind, ident, raw = get(2367)
assert kind == 'evaluations'
ev = json.loads(raw)
new = copy.deepcopy(ev)
for key in ('batch_id',):
    if key in new: new[key] = new[key] + '-grown'
for t in new['trials']:
    t['episode_id'] = t['episode_id'] + '-grown'
put('evaluations', ident + '-grown', new)
# 2. a mixed discovery pick, from the first model discovery pick at or below 6748 on the status read
sel = None
for rowid, raw in d.execute("SELECT rowid,payload FROM records WHERE kind='selections' AND rowid<=6748 ORDER BY rowid"):
    p = json.loads(raw); spec = (p.get('output') or {}).get('fault_spec')
    if spec and p.get('provenance') != 'history_replay' and not p.get('challenge') and all(
            q['target_tool'] == 'get_operation_status' for q in spec['primitives']):
        sel = p; break
assert sel is not None
other = None
for rowid, raw in d.execute("SELECT rowid,payload FROM records WHERE kind='selections' AND rowid<=6748 ORDER BY rowid"):
    spec = (json.loads(raw).get('output') or {}).get('fault_spec')
    for q in (spec or {}).get('primitives', []):
        if q['target_tool'] == 'update_order' and q['target_service'] == 'orders':
            other = copy.deepcopy(q); break
    if other: break
assert other is not None
mixed = copy.deepcopy(sel)
mixed['selection_id'] = sel['selection_id'] + '-grown'
mixed['output']['fault_spec']['primitives'].append(other)   # a real saved update_order primitive, beside the status read
put('selections', mixed['selection_id'], mixed)
# 3. a later plan that declares mechanic_diagnosis
kind, ident, raw = d.execute("SELECT kind,id,payload FROM records WHERE kind='campaign_plans' AND id='campaign-d8d1e8cc0ea34feb92dbd8c22c264530'").fetchone()
plan = json.loads(raw); plan['campaign_id'] = 'campaign-00000000000000000000000000grown'; plan['mechanic_diagnosis'] = {'synthetic': True}
put('campaign_plans', plan['campaign_id'], plan)
d.commit()
print('grown: max rowid', d.execute('SELECT MAX(rowid) FROM records').fetchone()[0],
      '| new rows', [r for r in d.execute('SELECT rowid,kind,id FROM records WHERE rowid>8583')])
d.close()
