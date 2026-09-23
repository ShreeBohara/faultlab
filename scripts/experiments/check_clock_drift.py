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

--worlds-dir names the simulator's worlds directory when the store is not the one beside
it (for example an in-process run's separate output store); by default it is the store's
sibling 'worlds' directory, as before.

--require-worlds (implies --worlds) makes the check refuse to pass without looking: exit
status 2 if any scored episode's world file is missing (a wrong or empty worlds directory
would otherwise skip the attempt-count and masked-fault checks and still exit 0). Drift or
a masked fault still exits 1 first. Without it the behaviour is unchanged.

scan() returns the same result as a dictionary, with per-episode flags, for callers that
need them (the Phase 20 read-out); main() prints exactly what it always printed.

Usage: python scripts/experiments/check_clock_drift.py [--store PATH] [--since YYYY-MM-DD] [--worlds]
       [--worlds-dir DIR] [--require-worlds]
"""
import argparse
import collections
import json
import os
import sqlite3
import sys


def scan(store, *, since='', worlds=False, worlds_dir=''):
    """The whole check as data. Every episode entry says whether its world file was read."""
    worlds_dir = worlds_dir or os.path.join(os.path.dirname(store), 'worlds')
    db = sqlite3.connect(f'file:{store}?mode=ro', uri=True)
    scored = 0; drifted = []; by_day = collections.Counter(); missing_worlds = 0; masked = []
    episodes = {}
    try:
        for (raw,) in db.execute("SELECT payload FROM records WHERE kind='episodes' ORDER BY rowid"):
            e = json.loads(raw); verdict = e.get('verdict') or {}
            if verdict.get('decision_tick') is None or (e.get('started_at') or '') < since: continue
            scored += 1
            events = [json.loads(p) for (p,) in db.execute('SELECT payload FROM events WHERE episode_id=? ORDER BY seq', (e['episode_id'],))]
            report = next((x['tick'] for x in events if x['type'] == 'report_submitted'), None)
            lab_attempts = sum(1 for x in events if x['type'] == 'tool_dispatched')
            world_attempts = None
            world_file = None
            masked_faults = []
            if worlds:
                path = os.path.join(worlds_dir, f"{e.get('world_id')}.sqlite3")
                if os.path.exists(path):
                    world_file = 'present'
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
                                    masked_faults.append(f['fault_id'])
                else:
                    world_file = 'missing'
                    missing_worlds += 1
            tick_drift = report is not None and report != verdict['decision_tick']
            count_drift = world_attempts is not None and world_attempts != lab_attempts
            if tick_drift or count_drift:
                failed = [c['check_id'] for c in verdict.get('checks', []) if not c['passed']]
                drifted.append((e['episode_id'], (e.get('started_at') or '')[:19], e.get('arm'), report, verdict['decision_tick'], lab_attempts, world_attempts, verdict.get('outcome'), failed))
                by_day[(e.get('started_at') or '')[:10]] += 1
            episodes[e['episode_id']] = {'report_tick': report, 'decision_tick': verdict['decision_tick'],
                                         'lab_attempts': lab_attempts, 'world_attempts': world_attempts,
                                         'tick_drift': tick_drift, 'count_drift': count_drift,
                                         'world_file': world_file, 'masked_faults': masked_faults}
    finally:
        db.close()
    return {'scored': scored, 'since': since, 'worlds': worlds, 'worlds_dir': worlds_dir, 'drifted': drifted,
            'by_day': dict(by_day), 'missing_worlds': missing_worlds, 'masked': masked, 'episodes': episodes}


def render(result, *, worlds_dir_given=False):
    """The lines main() has always printed, in the same order."""
    lines = [f"scored episodes checked: {result['scored']}" + (f" since {result['since']}" if result['since'] else '')]
    if result['worlds'] and worlds_dir_given: lines.append(f"worlds directory: {result['worlds_dir']}")
    if result['worlds']: lines.append(f"world files missing: {result['missing_worlds']}")
    lines.append(f"drifted: {len(result['drifted'])}")
    for row in result['drifted']:
        lines.append('  {} {} arm={} report_tick={} decision_tick={} lab_attempts={} world_attempts={} {} failed={}'.format(*row))
    for day, n in sorted(result['by_day'].items()): lines.append(f'  {day}: {n}')
    if result['worlds']:
        lines.append(f"masked response-delay faults: {len(result['masked'])}")
        for row in result['masked']: lines.append('  {} {} arm={} {}'.format(*row))
    return lines


def exit_status(result, *, require_worlds=False):
    if result['drifted'] or result['masked']:
        return 1
    if require_worlds and result['missing_worlds']:
        return 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', default='artifacts/lab.sqlite3')
    parser.add_argument('--since', default='')
    parser.add_argument('--worlds', action='store_true', help='also count world http_attempt events (slower)')
    parser.add_argument('--worlds-dir', default='', help="the simulator's worlds directory (default: the store's sibling 'worlds')")
    parser.add_argument('--require-worlds', action='store_true',
                        help='implies --worlds; exit 2 if any scored episode has no world file')
    args = parser.parse_args(argv)
    worlds = args.worlds or args.require_worlds
    result = scan(args.store, since=args.since, worlds=worlds, worlds_dir=args.worlds_dir)
    for line in render(result, worlds_dir_given=bool(args.worlds_dir)):
        print(line)
    status = exit_status(result, require_worlds=args.require_worlds)
    if status == 2:
        print('refused: world files are missing, so the attempt-count and masked-fault checks did not run for them')
    return status


if __name__ == '__main__':
    sys.exit(main())
