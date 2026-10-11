"""Aggregate trial envelopes into a leaderboard: outcomes, exposure, beliefs and conformance per model.

Input: directories of legacy stores (projected on the fly) or envelope bundles. Output: one JSON
document and one Markdown table. Every rate carries a 95 percent Wilson interval and its n;
nothing is ranked, because the point of the bench is to show what each agent did under each
fault, with the uncertainty, not to hide it behind a single number.

  python -m bench.harness.leaderboard <screen dir> [--out leaderboard.json] [--markdown leaderboard.md]
"""

from __future__ import annotations

import argparse
import json
from math import sqrt
from pathlib import Path
import re

from faultlab.core.errors import IntegrityError
from faultlab.evidence.bundles import read_bundle
from faultlab.evidence.legacy import LegacyStore, load_episode_facts, project_episode
from faultlab.evidence.models import TrialEnvelope
from faultlab.referee.oracle.orders import score

BENCH_VERSION = "faultlab-bench-leaderboard/v1"


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    """(point, low, high) for a binomial proportion; (0, 0, 1) when n = 0."""
    if n == 0:
        return 0.0, 0.0, 1.0
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return p, max(0.0, centre - half), min(1.0, centre + half)


def _rate(successes: int, n: int) -> dict:
    point, low, high = wilson(successes, n)
    return {"count": successes, "n": n, "rate": round(point, 4), "wilson95": [round(low, 4), round(high, 4)]}


def load_envelopes(root: Path) -> list[tuple[str, TrialEnvelope]]:
    """Every (source name, envelope) under ``root``: ``*/lab.sqlite3`` stores and ``*.zip`` bundles."""
    found = []
    for store_path in sorted(root.glob("*/lab.sqlite3")):
        with LegacyStore(store_path) as store:
            for episode_id in store.episode_ids():
                try:
                    found.append((store_path.parent.name, project_episode(load_episode_facts(store, episode_id), store_identity=store.identity())))
                except IntegrityError:
                    continue
    for bundle_path in sorted(root.glob("*.zip")):
        try:
            _, envelopes = read_bundle(bundle_path)
        except IntegrityError:
            continue
        found.extend((bundle_path.stem, envelope) for envelope in envelopes)
    return found


def aggregate(items: list[tuple[str, TrialEnvelope]], *, live_only: bool = True) -> dict:
    """Group by (model, adapter) and by scenario; count outcomes, exposure, beliefs and conformance."""
    rows: dict[str, dict] = {}
    for source, envelope in items:
        if live_only and envelope.plan.repetition.pairing not in (None, "B0"):
            continue
        # Legacy registration ids end in a per-store hash; the adapter family is what the board groups by.
        adapter = re.sub(r"-[0-9a-f]{16}$", "", envelope.plan.agent.adapter_id)
        key = f"{envelope.plan.agent.model} | {adapter}"
        row = rows.setdefault(key, {"model": envelope.plan.agent.model, "adapter": adapter,
                                    "sources": set(), "n": 0, "executions": {}, "tasks": {}, "violations": 0,
                                    "faults_configured": 0, "faults_triggered": 0, "faults_unreachable": 0,
                                    "beliefs": {"BELIEFS_TRUE": 0, "FALSE_BELIEF": 0, "UNDETERMINED": 0, "NO_REPORT": 0},
                                    "conformance_violations": 0, "conformance_envelopes": 0, "conformance_rules": {}, "scenarios": {},
                                    "input_tokens": 0, "output_tokens": 0, "dollars_measured": 0.0, "dollars_known": True})
        row["sources"].add(source)
        row["n"] += 1
        outcome = envelope.outcome
        row["executions"][outcome.execution] = row["executions"].get(outcome.execution, 0) + 1
        task = outcome.task or "NONE"
        row["tasks"][task] = row["tasks"].get(task, 0) + 1
        if task == "VIOLATION":
            row["violations"] += 1
        for fault in outcome.exposure.faults:
            row["faults_configured"] += int(fault.configured)
            row["faults_triggered"] += int(bool(fault.triggered))
            if fault.triggered is False:
                row["faults_unreachable"] += 1
        oracle = score(envelope) if envelope.plan.pack_id == "orders.upgrade_then_confirm/v1" else None
        if oracle is not None:
            row["beliefs"][oracle.summary] += 1
            row["conformance_violations"] += oracle.conformance_violations
            row["conformance_envelopes"] += int(oracle.conformance_violations > 0)
            for finding in oracle.conformance:
                if finding.severity == "violation":
                    row["conformance_rules"][finding.rule] = row["conformance_rules"].get(finding.rule, 0) + 1
        scenario = row["scenarios"].setdefault(envelope.plan.scenario_id[:12], {"n": 0, "violations": 0, "completed": 0, "untriggered": 0,
                                                                                 "families": sorted({p.family for p in envelope.plan.schedule.placements})})
        scenario["n"] += 1
        scenario["violations"] += int(task == "VIOLATION")
        scenario["completed"] += int(task == "COMPLETED")
        scenario["untriggered"] += sum(1 for fault in outcome.exposure.faults if fault.triggered is False)
        row["input_tokens"] += outcome.cost.input_tokens
        row["output_tokens"] += outcome.cost.output_tokens
        if outcome.cost.dollars_measured is None:
            row["dollars_known"] = False
        else:
            row["dollars_measured"] += outcome.cost.dollars_measured
    board = []
    for row in rows.values():
        n = row["n"]
        board.append({
            "model": row["model"], "adapter": row["adapter"], "sources": sorted(row["sources"]), "n": n,
            "executions": row["executions"], "tasks": row["tasks"],
            "violation_rate": _rate(row["violations"], n),
            "completion_rate": _rate(row["tasks"].get("COMPLETED", 0), n),
            "false_belief_rate": _rate(row["beliefs"]["FALSE_BELIEF"], n),
            "conformance_violation_rate": _rate(row["conformance_envelopes"], n),
            "beliefs": row["beliefs"], "conformance_rules": row["conformance_rules"],
            "fault_exposure": {"configured": row["faults_configured"], "triggered": row["faults_triggered"],
                               "unreachable": row["faults_unreachable"],
                               "triggered_rate": _rate(row["faults_triggered"], row["faults_configured"])},
            "scenarios": row["scenarios"],
            "cost": {"input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"],
                     "dollars_measured": round(row["dollars_measured"], 4) if row["dollars_known"] else None},
        })
    board.sort(key=lambda row: (row["model"], row["adapter"]))
    return {"bench_version": BENCH_VERSION, "live_only": live_only, "rows": board}


def markdown(board: dict) -> str:
    lines = ["| model | adapter | n | violations | completed | false beliefs | conformance | faults fired | input tok | output tok | measured $ |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in board["rows"]:
        def cell(rate):
            return f"{rate['count']}/{rate['n']} ({rate['rate']:.0%}, {rate['wilson95'][0]:.0%} to {rate['wilson95'][1]:.0%})"
        exposure = row["fault_exposure"]
        cost = row["cost"]
        lines.append(f"| {row['model']} | {row['adapter']} | {row['n']} | {cell(row['violation_rate'])} | {cell(row['completion_rate'])} | "
                     f"{cell(row['false_belief_rate'])} | {cell(row['conformance_violation_rate'])} | "
                     f"{exposure['triggered']}/{exposure['configured']} | {cost['input_tokens']:,} | {cost['output_tokens']:,} | "
                     f"{'unknown' if cost['dollars_measured'] is None else f'{cost['dollars_measured']:.3f}'} |")
    lines.append("")
    lines.append("Rates carry 95% Wilson intervals. Nothing is ranked.")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("root", type=Path, help="directory holding run stores (<name>/lab.sqlite3) and/or envelope bundles (*.zip)")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--all-arms", action="store_true", help="include offline reference arms (default: live arm only)")
    args = parser.parse_args(argv)
    board = aggregate(load_envelopes(args.root.expanduser()), live_only=not args.all_arms)
    text = markdown(board)
    print(text)
    if args.out:
        args.out.write_text(json.dumps(board, indent=2))
    if args.markdown:
        args.markdown.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
