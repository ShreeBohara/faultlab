"""Summarize the baseline-study runs of a screen directory into one table (and JSON).

Reads every ``<screen dir>/*/baseline-study.json`` written by ``baseline_screen.py``; reports the
live-arm (B0) outcomes per model and case, violations and completions out of 18, fault exposure,
measured usage and the declared bounds; and a one-sided Fisher exact test of violation counts
against the control model (``--control``). Descriptive by design: n = 18 per model.
"""

from __future__ import annotations

import argparse
import json
from math import comb
from pathlib import Path

CASES = ("dev-1", "dev-2", "dev-3", "dev-4", "dev-5", "dev-6")


def fisher_one_sided(a_bad: int, a_n: int, b_bad: int, b_n: int) -> float:
    """P(X >= a_bad) under the hypergeometric null: is arm A's bad count at least this large by chance?"""
    total_bad, total = a_bad + b_bad, a_n + b_n
    def p(k):
        return comb(total_bad, k) * comb(total - total_bad, a_n - k) / comb(total, a_n)
    return sum(p(k) for k in range(a_bad, min(a_n, total_bad) + 1))


def load(screen: Path) -> dict[str, dict]:
    runs = {}
    for record_path in sorted(screen.glob("*/baseline-study.json")):
        record = json.loads(record_path.read_text())
        result_path = record_path.with_name("RESULT.json")
        result = json.loads(result_path.read_text()) if result_path.exists() else {}
        runs[record_path.parent.name] = {"record": record, "result": result, "model": record.get("model") or result.get("model")}
    return runs


def summarize(record: dict) -> dict:
    case_of = {slot["episode_id"]: slot["case_id"] for slot in record.get("slots", [])}
    live = [t for t in record.get("trials", []) if t.get("arm") == "B0"]
    by_case = {case: [] for case in CASES}
    for trial in live:
        by_case.setdefault(case_of.get(trial["episode_id"], "?"), []).append(trial)
    outcomes = {}
    for trial in live:
        key = trial.get("outcome") or trial.get("lifecycle")
        outcomes[key] = outcomes.get(key, 0) + 1
    failed = {}
    for trial in live:
        for check in trial.get("failed_checks", []):
            failed[check] = failed.get(check, 0) + 1
    scheduled = sum(1 for t in live if t.get("fault_scheduled"))
    triggered = sum(1 for t in live if t.get("fault_triggered"))
    usage = record.get("usage") or {}
    return {"status": record.get("status"), "live_trials": len(live), "outcomes": outcomes, "failed_checks": failed,
            "violations": outcomes.get("VIOLATION", 0), "completed": outcomes.get("COMPLETED", 0),
            "safe_unresolved": outcomes.get("SAFE_UNRESOLVED", 0), "correctly_rejected": outcomes.get("CORRECTLY_REJECTED", 0),
            "lab_errors": sum(1 for t in live if t.get("lifecycle") == "LAB_ERROR"),
            "faults_scheduled": scheduled, "faults_triggered": triggered,
            "by_case": {case: [(t.get("outcome") or t.get("lifecycle"), ",".join(t.get("failed_checks", [])) or "-") for t in trials]
                        for case, trials in by_case.items()},
            "usage": usage, "charged_model_calls": record.get("charged_model_calls")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("screen", type=Path)
    parser.add_argument("--control", default="deepseek-v3.1-control", help="run folder name of the control model")
    parser.add_argument("--json", type=Path, default=None, help="also write the summary as JSON")
    args = parser.parse_args(argv)
    runs = load(args.screen.expanduser())
    if not runs:
        print("no baseline-study.json found")
        return 1
    summaries = {name: {"model": run["model"], **summarize(run["record"]),
                        "monthly_ledger": run["result"].get("monthly_ledger")} for name, run in runs.items()}
    control = summaries.get(args.control)
    print(f"{'run':34} {'status':10} {'live':>4} {'viol':>4} {'done':>4} {'safe':>4} {'rej':>4} {'err':>4} {'fault':>7} {'in_tok':>9} {'out_tok':>8} {'p vs ctl':>8}")
    for name, s in summaries.items():
        if control is not None and name != args.control:
            p = fisher_one_sided(s["violations"], s["live_trials"], control["violations"], control["live_trials"]) if s["live_trials"] else float("nan")
            s["fisher_one_sided_vs_control"] = p
            p_text = f"{p:8.3f}"
        else:
            p_text = "    ctl " if name == args.control else "       -"
        usage = s["usage"] or {}
        print(f"{name:34} {str(s['status']):10} {s['live_trials']:4} {s['violations']:4} {s['completed']:4} {s['safe_unresolved']:4} "
              f"{s['correctly_rejected']:4} {s['lab_errors']:4} {s['faults_triggered']:3}/{s['faults_scheduled']:<3} "
              f"{usage.get('input_tokens', 0):9} {usage.get('output_tokens', 0):8} {p_text}")
    print()
    for name, s in summaries.items():
        print(f"{name}: failed checks {s['failed_checks']}")
        for case in CASES:
            print(f"   {case}: " + "; ".join(f"{outcome} [{checks}]" for outcome, checks in s["by_case"].get(case, [])))
    if args.json:
        args.json.write_text(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
