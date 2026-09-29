"""The clock-drift check, reading old native smolagents stores with the declared rule ($0, no app import).

check_clock_drift.py is kept byte-identical on purpose: closed experiment runners
(run_upgrade_loop.py, run_full_loop_fixed_n.py) pin its sha256 in their declarations. This
companion runs that exact scan and then applies one declared rule, so it reports everything
the original check reports.

Why: native smolagents episodes recorded by runtime c0a8aad7 or earlier carry their
report_submitted event at tick 0 (external_agent.py passed no tick=; fixed in debc86f3, which
records the lab's real tick). The original check therefore flags every such native episode
that filed a report. Under the declared rule (native probe PLAN section 10, B3) a flagged row
is NOT drift only if all of these hold:
  1. the episode ran the native smolagents adapter (its execution record or registration says so);
  2. its report tick is 0;
  3. the lab's and the world's attempt counts are equal (so this needs --worlds; without the
     world file the row cannot be cleared and still counts as drift);
  4. its private_world_integrity record is VALID (a store without one, such as Phase 1's,
     cannot clear it).
Anything else still counts as drift, exactly as before. Cleared rows are listed separately,
and each native tick-0 row that stays drift is listed with the reason it could not be cleared.
New stores need no rule: their native reports carry the real tick.

Same options and exit status as check_clock_drift.py (1: drift or a masked fault; 2 with
--require-worlds: a world file is missing).

Usage: python scripts/experiments/check_clock_drift_native.py [--store PATH] [--since YYYY-MM-DD]
       [--worlds] [--worlds-dir DIR] [--require-worlds]
"""
import argparse
import collections
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_clock_drift as base  # noqa: E402  (the unchanged, pinned check)

NATIVE_ADAPTER = 'smolagents-toolcalling-v1'


def _record(db, kind, ident):
    row = db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, ident)).fetchone()
    return json.loads(row[0]) if row else None


def _native(db, episode_id):
    execution = _record(db, 'episode_executions', episode_id) or {}
    if execution.get('adapter_entrypoint_id') == NATIVE_ADAPTER:
        return True
    registration_id = (_record(db, 'episodes', episode_id) or {}).get('agent_registration_id')
    registration = _record(db, 'agent_registrations', registration_id) if isinstance(registration_id, str) else None
    return bool(registration and registration.get('adapter_entrypoint_id') == NATIVE_ADAPTER)


def _reasons(result, flags, world_attempts, lab_attempts, integrity):
    """Why a native report at tick 0 cannot be cleared (every rule condition that fails)."""
    reasons = []
    if not result['worlds']:
        reasons.append('no world attempt count (run with --worlds)')
    elif world_attempts is None:
        reasons.append('world file missing')
    elif flags['count_drift']:
        reasons.append(f'lab and world attempt counts differ ({lab_attempts} vs {world_attempts})')
    if integrity is None:
        reasons.append('no private_world_integrity record')
    elif integrity.get('status') != 'VALID':
        reasons.append(f"integrity {integrity.get('status')}, not VALID")
    return reasons


def scan(store, *, since='', worlds=False, worlds_dir=''):
    """base.scan's result, with rows cleared by the declared native rule moved out of 'drifted'."""
    result = base.scan(store, since=since, worlds=worlds, worlds_dir=worlds_dir)
    cleared = []; not_cleared = []; drifted = []; by_day = collections.Counter()
    db = sqlite3.connect(f'file:{store}?mode=ro', uri=True)
    try:
        for row in result['drifted']:
            episode_id, started, arm, report, decision, lab_attempts, world_attempts = row[:7]
            flags = result['episodes'][episode_id]
            tick0 = flags['tick_drift'] and report == 0 and _native(db, episode_id)
            integrity = _record(db, 'private_world_integrity', episode_id) if tick0 else None
            ok = (tick0 and not flags['count_drift'] and world_attempts is not None
                  and (integrity or {}).get('status') == 'VALID')
            flags.update(native_report_tick0=bool(tick0), native_report_tick0_cleared=bool(ok))
            if ok:
                flags['tick_drift'] = False
                cleared.append((episode_id, started, arm, report, decision, lab_attempts, world_attempts))
                continue
            if tick0:
                not_cleared.append((episode_id, started, arm, report, decision, lab_attempts, world_attempts,
                                    '; '.join(_reasons(result, flags, world_attempts, lab_attempts, integrity))))
            drifted.append(row); by_day[(started or '')[:10]] += 1
    finally:
        db.close()
    return {**result, 'drifted': drifted, 'by_day': dict(by_day),
            'native_report_tick0_cleared': cleared, 'native_report_tick0_not_cleared': len(not_cleared),
            'native_report_tick0_not_cleared_rows': not_cleared}


def render(result, *, worlds_dir_given=False):
    """The original lines, plus the native-rule lines before the masked-fault summary."""
    lines = base.render(result, worlds_dir_given=worlds_dir_given)
    cleared, uncleared = result['native_report_tick0_cleared'], result['native_report_tick0_not_cleared']
    extra = []
    if cleared or uncleared:
        extra.append(f'native reports at tick 0 (old adapter, declared rule): {len(cleared)} not drift, {uncleared} still counted as drift'
                     + ('' if result['worlds'] else ' (use --worlds: the rule needs the world attempt count)'))
        extra += ['  {} {} arm={} report_tick={} decision_tick={} lab_attempts={} world_attempts={} integrity=VALID'.format(*row)
                  for row in cleared]
        extra += ['  {} {} arm={} report_tick={} decision_tick={} lab_attempts={} world_attempts={} still drift: {}'.format(*row)
                  for row in result['native_report_tick0_not_cleared_rows']]
    at = next((i for i, line in enumerate(lines) if line.startswith('masked response-delay faults')), len(lines))
    return lines[:at] + extra + lines[at:]


exit_status = base.exit_status


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
