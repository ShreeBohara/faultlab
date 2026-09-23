"""Read-only check that the lab's clock and each world's clock agree ($0, no app import).

Phase 18's only failure was a one-tick drift: a request the lab counted never reached the
simulator, so the lab stamped every later observation one tick past the world's decision
tick and a truthful citation failed C6. A scored episode has drifted when its
report_submitted event carries a different tick from its verdict's decision_tick (the
world's clock when the report stopped it). With --worlds, also compare the lab's
dispatched attempts with the world's recorded http_attempt events, and report MASKED
response-delay faults: an F1 the world marks triggered whose triggering attempt reached
the lab as transport 'ok' (a lab freeze across the read deadline let the delayed
response in first, so the Actor never saw the fault; not a drift, but the trial still
counts the fault as triggered).

Exit status 1 if any scored episode on or after --since drifted or had a masked fault.

Usage: python scripts/experiments/check_clock_drift.py [--store PATH] [--since YYYY-MM-DD] [--worlds]
"""
import argparse
import collections
import json
import os
import sqlite3
import sys


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', default='artifacts/lab.sqlite3')
    parser.add_argument('--since', default='')
    parser.add_argument('--worlds', action='store_true', help='also count world http_attempt events (slower)')
    args = parser.parse_args(argv)
    db = sqlite3.connect(f'file:{args.store}?mode=ro', uri=True)
    scored = 0; drifted = []; by_day = collections.Counter(); missing_worlds = 0; masked = []
    for (raw,) in db.execute("SELECT payload FROM records WHERE kind='episodes' ORDER BY rowid"):
        e = json.loads(raw); verdict = e.get('verdict') or {}
        if verdict.get('decision_tick') is None or (e.get('started_at') or '') < args.since: continue
        scored += 1
        events = [json.loads(p) for (p,) in db.execute('SELECT payload FROM events WHERE episode_id=? ORDER BY seq', (e['episode_id'],))]
        report = next((x['tick'] for x in events if x['type'] == 'report_submitted'), None)
        lab_attempts = sum(1 for x in events if x['type'] == 'tool_dispatched')
        world_attempts = None
        if args.worlds:
            path = os.path.join(os.path.dirname(args.store), 'worlds', f"{e.get('world_id')}.sqlite3")
            if os.path.exists(path):
                w = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
                world_attempts = sum(1 for (v,) in w.execute('SELECT value FROM events') if json.loads(v)['type'] == 'http_attempt')
                state = json.loads(w.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
                w.close()
                kinds = {f'fault-{n + 1}': p['kind'] for n, p in enumerate(state['fault_spec']['primitives'])}
                for f in state['fault_executions']:
                    if kinds.get(f['fault_id']) != 'F1' or not f['triggered']: continue
                    for i, x in enumerate(events):
                        if x['type'] == 'tool_dispatched' and x['payload'].get('attempt_id') == f['attempt_id']:
                            seen = next((y for y in events[i + 1:] if y['type'] == 'observation_delivered' and y.get('call_id') == x.get('call_id')), None)
                            if seen and seen['payload']['observation']['result'].get('transport') == 'ok':
                                masked.append((e['episode_id'], (e.get('started_at') or '')[:19], e.get('arm'), f['fault_id']))
            else:
                missing_worlds += 1
        tick_drift = report is not None and report != verdict['decision_tick']
        count_drift = world_attempts is not None and world_attempts != lab_attempts
        if tick_drift or count_drift:
            failed = [c['check_id'] for c in verdict.get('checks', []) if not c['passed']]
            drifted.append((e['episode_id'], (e.get('started_at') or '')[:19], e.get('arm'), report, verdict['decision_tick'], lab_attempts, world_attempts, verdict.get('outcome'), failed))
            by_day[(e.get('started_at') or '')[:10]] += 1
    print(f'scored episodes checked: {scored}' + (f' since {args.since}' if args.since else ''))
    if args.worlds: print(f'world files missing: {missing_worlds}')
    print(f'drifted: {len(drifted)}')
    for row in drifted:
        print('  {} {} arm={} report_tick={} decision_tick={} lab_attempts={} world_attempts={} {} failed={}'.format(*row))
    for day, n in sorted(by_day.items()): print(f'  {day}: {n}')
    if args.worlds:
        print(f'masked response-delay faults: {len(masked)}')
        for row in masked: print('  {} {} arm={} {}'.format(*row))
    return 1 if drifted or masked else 0


if __name__ == '__main__':
    sys.exit(main())
