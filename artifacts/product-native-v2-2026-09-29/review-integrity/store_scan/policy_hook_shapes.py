"""Read-only: how many saved policies (all five run stores) contain a before_confirmation rule with a read step."""
import json, sqlite3, glob
READS = {'read_current_operation', 'read_notification_operation', 'read_order'}
for path in sorted(glob.glob('/Users/shree/FaultLab_Runs/*/*/lab.sqlite3')):
    db = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True); db.execute('PRAGMA query_only=ON')
    total = hit = 0
    for (p,) in db.execute("select payload from records where kind='policies'"):
        v = json.loads(p); content = v.get('content') or {}
        total += 1
        if any(r.get('hook') == 'before_confirmation' and any(s.get('op') in READS for s in r.get('steps', [])) for r in content.get('rules', [])):
            hit += 1
    print(path.split('FaultLab_Runs/')[1], f'policies {total}, with a before_confirmation read step {hit}')
