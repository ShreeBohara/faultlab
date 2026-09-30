"""Challenge trials of a campaign straight from the scratch store (read-only): arm, outcome, failed checks, fault fired, who called what."""
import json, sqlite3, sys
cid = sys.argv[1]
db = sqlite3.connect('file:/Users/shree/FaultLab_Scratch/review-product/ui/lab/lab.sqlite3?mode=ro', uri=True)
rows = lambda kind: [json.loads(p) for (p,) in db.execute('select payload from records where kind=?', (kind,))]
calls = {}
for c in rows('tool_calls'): calls.setdefault(c['episode_id'], []).append(f"{c.get('caller')}:{c['tool']}x{len(c['attempt_ids'])}")
out = []
for ch in rows('challenges'):
    link = [x for x in rows('challenge_campaigns') if x['challenge_id'] == ch['challenge_id']]
    if not link or link[0]['campaign_id'] != cid: continue
    for sel in ch['selection_refs']:
        s = db.execute("select payload from records where kind='selections' and id=?", (sel,)).fetchone()
        s = json.loads(s[0]) if s else {}
        out.append({'selection': sel[-8:], 'reach': (s.get('challenge_reach') or {}).get('status'), 'pick': [(p['kind'], p['target_tool'], p['target_service']) for p in ((s.get('output') or {}).get('fault_spec') or {}).get('primitives', [])]})
    for a, b in ch['trial_pairs']:
        for e in (a, b):
            t = json.loads(db.execute("select payload from records where kind='trials' and id=?", (e,)).fetchone()[0])
            out.append({'episode': e[-8:], 'arm': t['arm'], 'outcome': t['outcome'], 'failed': t['failed_checks'], 'scheduled': t['fault_scheduled'], 'triggered': t['fault_triggered'], 'calls': calls.get(e, [])})
    out.append({'challenge': ch['challenge_id'], 'status': ch['status'], 'reason': ch['stopping_reason']})
print(json.dumps(out, indent=0))
