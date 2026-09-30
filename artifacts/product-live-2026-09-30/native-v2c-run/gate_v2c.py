"""Corrected report-plumbing gate (declared 2026-09-30 ~03:20 UTC, computed on data ALREADY collected, before any new
paid call). The v2 and v2b probes' rule counted every C5; every C5 in them co-occurred with a submitted report and C3 or
C4 (untruthful content, the behaviour a policy should repair), so that rule measured the wrong thing. This gate asks the
question the old one was meant to ask: does the report-fixed agent file a valid report? PASS iff, over all B0 (agent)
episodes of both baseline studies, 0 episodes have C5 without a submitted report, and 0 have C5 without C3 or C4."""
import sqlite3, json, sys
STORES = {'v2 (first build) baseline+learn': '/Users/shree/FaultLab_Runs/2026-09-30/native-v2/lab.sqlite3',
          'v2.1 baseline (v2b probe, NO_GO)': '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'}
out = {}; ok = True
for label, path in STORES.items():
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    trials = {json.loads(p)['episode_id']: json.loads(p) for (p,) in db.execute("select payload from records where kind='trials'")}
    reported = {eid for (eid, p) in db.execute("select episode_id,payload from events") if json.loads(p).get('type') == 'report_submitted'}
    agent = [t for t in trials.values() if t.get('arm') != 'B1']
    c5 = [t for t in agent if 'C5' in (t.get('failed_checks') or [])]
    no_report = [t['episode_id'] for t in c5 if t['episode_id'] not in reported]
    alone = [t['episode_id'] for t in c5 if not set(t.get('failed_checks') or []) & {'C3', 'C4'}]
    out[label] = {'agent_episodes': len(agent), 'c5': len(c5), 'c5_without_submitted_report': len(no_report), 'c5_without_c3_or_c4': len(alone)}
    ok = ok and not no_report and not alone
out['gate'] = 'PASS' if ok else 'FAIL'
print(json.dumps(out, indent=1)); open(sys.argv[1], 'w').write(json.dumps(out, indent=1))
