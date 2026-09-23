"""Read-only: is Weave trace ingestion healthy enough to start a paid run?

Phase 12 burned 28 attempts and $8.15 while ingestion was degraded (31% of episodes failed
to verify, against 0.9% during Phase 11). A validation batch needs all 42 episodes verified,
so at that rate no batch can complete. Run this before spending.

Usage: python scripts/experiments/check_ingestion_health.py [--recent N] [--max-failure-pct P]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
DB = f"file:{ROOT / 'artifacts/lab.sqlite3'}?mode=ro"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recent', type=int, default=120)
    parser.add_argument('--max-failure-pct', type=float, default=5.0)
    parser.add_argument('--batch-size', type=int, default=42)
    args = parser.parse_args()

    connection = sqlite3.connect(DB, uri=True)
    try:
        # rowid DESC is insertion order. An unordered scan is NOT, and slicing one gave a
        # false "healthy" reading the first time this tool was written.
        recent = [json.loads(p) for _, p in connection.execute(
            "select id,payload from records where kind='ingestions' order by rowid desc limit ?",
            (args.recent,))]
        # Since Phase 16 a completion study re-reads a lost trace once, and a successful
        # re-read overwrites the ingestion row with INGESTED in place (same rowid). The
        # first failure survives only in the study's evidence_rereads list; count it,
        # or this guard would report a healthy channel that is actually failing.
        rereads = {}
        for (payload,) in connection.execute(
                "select payload from records where kind='completion_studies'"):
            for entry in json.loads(payload).get('evidence_rereads') or []:
                rereads[entry['episode_id']] = entry
    finally:
        connection.close()
    if not recent:
        print('no ingestion records'); return 1
    states = Counter(r.get('state') for r in recent)
    codes = Counter(r.get('error_code') for r in recent if r.get('error_code'))
    # Every episode whose FIRST read failed counts once, whatever the re-read did: a
    # VERIFIED re-read and a DENIED one (the mismatch is found after the row is already
    # overwritten with INGESTED) both leave an INGESTED row behind.
    state = {r.get('episode_id'): r.get('state') for r in recent}
    reread_here = {eid: e for eid, e in rereads.items() if eid in state}
    recovered = [e for e in reread_here.values() if e.get('result') == 'VERIFIED']
    failed = sum(1 for eid, s in state.items() if s != 'INGESTED' or eid in reread_here)
    rate = failed / len(state)

    print(f'last {len(recent)} ingestion records')
    print(f'  states      : {dict(states)}')
    print(f'  error codes : {dict(codes) or "none"}')
    print(f'  in-study re-reads in this window: {len(reread_here)} ({len(recovered)} recovered); '
          f'all counted as first-read failures below')
    print(f'  first-read failure rate: {100 * rate:.1f}%   (Phase 11 healthy baseline 0.9%)')
    survive = (1 - rate) ** args.batch_size
    print(f'  => P(a {args.batch_size}-episode batch fully verifies) = {100 * survive:.1f}%')
    if 100 * rate > args.max_failure_pct:
        print(f'\nDEGRADED: failure rate exceeds {args.max_failure_pct}%. '
              f'A paid run would very likely produce no scored result. Wait.')
        return 2
    print('\nHEALTHY enough to start a paid run.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
