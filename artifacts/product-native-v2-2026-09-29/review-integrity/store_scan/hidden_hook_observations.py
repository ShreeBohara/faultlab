"""Read-only scan (SQLite URI mode=ro&immutable=1; nothing written under /Users/shree/FaultLab_Runs/).
Counts native episodes in which a before_confirmation policy hook delivered an observation (policy read) and the
confirmation then went ahead (next actor dispatch is send_confirmation), so v1 never showed that observation to the
agent; under v2 it would still receive a journal label (obs-N) that the decoder accepts. Also lists the registration
entrypoints in each store. Note: immutable=1 ignores any un-checkpointed -wal content."""
import json, sqlite3, collections
from pathlib import Path
STORES = {'native-probe': '/Users/shree/FaultLab_Runs/2026-09-28/native-probe/lab.sqlite3',
          'native-learn': '/Users/shree/FaultLab_Runs/2026-09-29/native-learn/lab.sqlite3',
          'native-learn-v3': '/Users/shree/FaultLab_Runs/2026-09-29/native-learn-v3/lab.sqlite3'}
for name, path in STORES.items():
    db = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True); db.execute('PRAGMA query_only=ON')
    entries = collections.Counter(json.loads(p).get('adapter_entrypoint_id') for (p,) in db.execute("select payload from records where kind='agent_registrations'"))
    purposes = {i: json.loads(p).get('purpose') for i, p in db.execute("select id,payload from records where kind='episodes'")}
    by_ep = collections.defaultdict(list)
    for eid, seq, payload in db.execute('select episode_id,seq,payload from events order by episode_id,seq'):
        by_ep[eid].append(json.loads(payload))
    hidden_eps, hidden_obs, bc_eps = [], 0, 0
    for eid, evs in by_ep.items():
        dispatches = [e for e in evs if e['type'] == 'tool_dispatched']
        found = 0
        if any(d['payload'].get('hook') == 'before_confirmation' for d in dispatches): bc_eps += 1
        for i, d in enumerate(dispatches):
            if d['payload'].get('hook') != 'before_confirmation':
                continue
            nxt = next((x for x in dispatches[i + 1:] if x['payload'].get('hook') != 'before_confirmation'), None)
            if nxt and nxt['payload'].get('caller') == 'actor' and nxt['payload'].get('tool') == 'send_confirmation':
                found += 1
        if found:
            hidden_eps.append((eid, purposes.get(eid))); hidden_obs += found
    print(f'{name}: registrations {dict(entries)}; episodes {len(by_ep)}; episodes with a before_confirmation hook read: {bc_eps}; '
          f'episodes with a hook read the agent never saw (confirmation went ahead): {len(hidden_eps)} ({hidden_obs} observations); '
          f'by purpose {dict(collections.Counter(p for _, p in hidden_eps))}')
