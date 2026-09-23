"""Read-only read-out of a completion study against the Phase 8 predeclared rules.

Makes no model call, creates no record and writes nothing to the lab database. The
primary read-out is fixed in docs/part2/PHASE8_EXPERIMENT.md: of the proposals
generated, how many contain a step with op == 'retry_original_request' and
service == 'notifications'.

Usage:
  python scripts/experiments/summarize_completion_study.py STUDY_ID [STUDY_ID ...]
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DB = f"file:{ROOT / 'artifacts/lab.sqlite3'}?mode=ro"


def record(connection, kind, record_id):
    row = connection.execute('select payload from records where kind=? and id=?',
                             (kind, record_id)).fetchone()
    return json.loads(row[0]) if row else None


def has_notification_retry(content):
    """The predeclared primary read-out, evaluated structurally, not by wording."""
    for rule in (content or {}).get('rules', []):
        for step in rule.get('steps', []):
            if step.get('op') == 'retry_original_request' and step.get('service') == 'notifications':
                return True
    return False


def summarize(connection, study_id):
    study = record(connection, 'completion_studies', study_id)
    if not study:
        print(f'{study_id}: not found'); return
    rows = study.get('trial_rows', [])
    print('=' * 78)
    print(f"{study_id}")
    print(f"  campaign      {study.get('campaign_id')}")
    print(f"  status        {study.get('status')} / {study.get('decision')} at stage {study.get('stage')}")
    print(f"  reason        {study.get('reason')}")
    control = study.get('control_assessment')
    if control:
        print(f"  controls      valid_source={control['valid_source']} "
              f"source_completions={control['source_completions']} "
              f"valid_healthy={control['valid_healthy']} "
              f"healthy_completions={control['healthy_completions']}")
    stages = {}
    for row in rows: stages[row.get('stage')] = stages.get(row.get('stage'), 0) + 1
    sources = study.get('evidence') or {}
    verified = sum(source == 'weave_verified' for source in sources.values())
    print(f"  trials        {len(rows)} {stages}")
    print(f"  verified      {verified}/{len(sources)} weave_verified episodes "
          f"{sorted(set(sources.values()))}")
    retained = study.get('retained_invalid_slots') or []
    if retained: print(f"  retained      {len(retained)} invalid slot(s) kept without replacement")

    # What the Mechanic was actually shown.
    for index in range(1, 9):
        supplied = record(connection, 'completion_proposal_inputs', f'{study_id}-{index}')
        if not supplied: break
        evidence = supplied['development_evidence']
        outcomes = [e.get('task_outcome') for e in evidence['episodes']]
        print(f"  context {index}     format={evidence['format']} episodes={len(evidence['episodes'])} "
              f"task_outcome={ {o: outcomes.count(o) for o in sorted(set(outcomes), key=str)} }")

    candidates = study.get('candidates', [])
    print(f"  proposals     {len(candidates)}")
    hits = 0
    for index, candidate in enumerate(candidates, 1):
        content = candidate.get('content')
        retry = has_notification_retry(content) if content else False
        hits += retry
        ops = [s.get('op') for r in (content or {}).get('rules', []) for s in r.get('steps', [])]
        print(f"    [{index}] decision={candidate.get('decision')} "
              f"policy={str(candidate.get('policy_hash'))[:12]} "
              f"RETRY_NOTIFICATIONS={'YES' if retry else 'no'}")
        if ops: print(f"        ops: {ops}")
        text = candidate.get('explanation') or candidate.get('reason') or ''
        if text: print(f'        text: {text.strip()[:600]}')
    print(f"  PRIMARY READ-OUT: {hits} of {len(candidates)} proposals contain "
          f"retry_original_request for notifications")
    return hits, len(candidates)


def main():
    if len(sys.argv) < 2: raise SystemExit(__doc__)
    connection = sqlite3.connect(DB, uri=True)
    try:
        totals = [summarize(connection, study_id) for study_id in sys.argv[1:]]
    finally:
        connection.close()
    scored = [t for t in totals if t]
    if len(scored) > 1:
        print('=' * 78)
        print(f'COMBINED: {sum(h for h, _ in scored)} of {sum(n for _, n in scored)} proposals')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
