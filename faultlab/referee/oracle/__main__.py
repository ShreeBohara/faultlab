"""Score every episode of a legacy store with the oracle and compare with the recorded C5/C6 verdicts.

  python -m faultlab.referee.oracle <lab.sqlite3> [--limit N] [--json out.json]

Agreement is measured, never assumed: the oracle's conformance rules were written from the public
contract, not from the private checks, so disagreements are findings about one or the other.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from faultlab.core.errors import IntegrityError
from faultlab.evidence.legacy import LegacyStore, load_episode_facts, project_episode
from faultlab.referee.oracle.orders import score


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("store")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    summaries, beliefs, agreement = Counter(), Counter(), Counter()
    rows = []
    with LegacyStore(args.store) as store:
        ids = store.episode_ids()[: args.limit] if args.limit else store.episode_ids()
        for episode_id in ids:
            try:
                envelope = project_episode(load_episode_facts(store, episode_id), store_identity=store.identity())
            except IntegrityError as error:
                rows.append({"episode_id": episode_id, "error": str(error)[:200]})
                continue
            result = score(envelope)
            recorded = {finding.property_id: finding.result for finding in envelope.outcome.findings}
            oracle_c5 = any(f.legacy_check == "C5" and f.severity == "violation" for f in result.conformance)
            oracle_c6 = any(f.legacy_check == "C6" and f.severity == "violation" for f in result.conformance)
            for check, mine in (("C5", oracle_c5), ("C6", oracle_c6)):
                if check in recorded:
                    theirs = recorded[check] == "VIOLATION"
                    agreement[f"{check}:{'agree' if mine == theirs else 'oracle_only' if mine else 'recorded_only'}"] += 1
            summaries[result.summary] += 1
            for claim in result.claims:
                beliefs[f"{claim.claim}:{claim.belief}"] += 1
            rows.append({"episode_id": episode_id, "task": envelope.outcome.task, "summary": result.summary,
                         "false_beliefs": result.false_beliefs, "conformance": [f.rule for f in result.conformance],
                         "recorded_failed": [k for k, v in recorded.items() if v == "VIOLATION"]})
    report = {"store": args.store, "episodes": len(rows), "summaries": dict(summaries), "beliefs": dict(beliefs),
              "agreement_with_recorded_checks": dict(sorted(agreement.items())), "rows": rows}
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2, sort_keys=True))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
