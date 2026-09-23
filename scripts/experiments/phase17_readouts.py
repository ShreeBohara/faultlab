"""Read-only: compute Phase 17's declared secondary read-outs from the manifest and the store.

Written and declared before any Phase 17 data exists, so that no denominator can be chosen
after seeing the results (docs/part2/PHASE17_EXPERIMENT.md, "Secondary read-outs").

  S3  evidence: verified reads, re-reads by result, studies killed by evidence errors, and
      the first-read failure rate per episode whose evidence read was attempted.
  S4  untriggered-fault rate per fault-bearing episode, all stages (controls through
      validation), LAB_ERROR episodes excluded, with a Wilson 95% interval.
  S5  funnel extras: step candidates lost to an untriggered trial or to an infrastructure death.

S1, S2 and S6 are in the manifest's own `summary` (written by run_full_loop.py).

Usage: python scripts/experiments/phase17_readouts.py artifacts/phase17-DATE [--store PATH]
"""
import argparse
import json
import math
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[2]


def wilson(k, n, z=1.959964):
    if n == 0:
        return (None, None)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir')
    parser.add_argument('--store', default=str(ROOT / 'artifacts/lab.sqlite3'))
    args = parser.parse_args()
    manifest = json.loads((ROOT / args.run_dir / 'full-loop-manifest.json').read_text())
    ids = [r['study_id'] for r in manifest['attempts'] if r.get('study_id')]
    connection = sqlite3.connect(f'file:{args.store}?mode=ro', uri=True)
    try:
        studies = {sid: json.loads(p) for sid, p in connection.execute(
            f"select id,payload from records where kind='completion_studies' and id in ({','.join('?' * len(ids))})",
            ids)} if ids else {}
    finally:
        connection.close()

    fault_bearing = untriggered = 0
    verified = killed_by_evidence = 0
    rereads = {}
    lost_untriggered = lost_infrastructure = 0
    for sid in ids:
        study = studies[sid]
        for row in study.get('trial_rows') or []:
            trial = row['trial']
            if trial.get('lifecycle') == 'LAB_ERROR' or trial.get('outcome') == 'LAB_ERROR':
                continue
            if trial.get('fault_scheduled'):
                fault_bearing += 1
                untriggered += int(not trial.get('fault_triggered'))
        verified += sum(1 for v in (study.get('evidence') or {}).values() if v == 'weave_verified')
        for entry in study.get('evidence_rereads') or []:
            rereads[entry.get('result')] = rereads.get(entry.get('result'), 0) + 1
        if study.get('error_type') in ('WaitingEvidence', 'EvidenceDenied'):
            killed_by_evidence += 1
        for attempt in study.get('candidates') or []:
            content = attempt.get('content') or {}
            has_step = any(rule.get('hook') == 'after_notification_response' and any(
                s.get('op') == 'retry_original_request' and s.get('service') == 'notifications'
                for s in rule.get('steps') or []) for rule in content.get('rules') or [])
            if not has_step:
                continue
            source = (attempt.get('source_assessment') or {}).get('decision')
            if source == 'INCOMPLETE':
                lost_untriggered += 1
            elif source is None and study.get('status') == 'INCOMPLETE' and study.get('error_type'):
                lost_infrastructure += 1
    first_read_failures = sum(rereads.values()) + sum(
        1 for sid in ids if studies[sid].get('error_type') == 'WaitingEvidence'
        and not any(e.get('stage') == studies[sid].get('stage') and e.get('result') in ('FAILED', 'ERROR', 'DENIED')
                    for e in studies[sid].get('evidence_rereads') or []))
    reads_attempted = verified + killed_by_evidence
    out = {
        'S3': {'verified_reads': verified, 'rereads_by_result': rereads,
               'studies_killed_by_evidence': killed_by_evidence,
               'first_read_failures': first_read_failures, 'reads_attempted': reads_attempted,
               'first_read_failure_rate': first_read_failures / reads_attempted if reads_attempted else None,
               'wilson95': wilson(first_read_failures, reads_attempted)},
        'S4': {'fault_bearing_episodes': fault_bearing, 'untriggered': untriggered,
               'rate': untriggered / fault_bearing if fault_bearing else None,
               'wilson95': wilson(untriggered, fault_bearing),
               'reference': 'Phase 15 validation only: 20/759 = 2.64% [1.71%, 4.03%]'},
        'S5_step_candidates_lost': {'to_untriggered_trial': lost_untriggered,
                                    'to_infrastructure_death': lost_infrastructure},
    }
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
