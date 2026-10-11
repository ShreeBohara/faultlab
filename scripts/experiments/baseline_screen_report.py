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


def fisher_two_sided(a_bad: int, a_n: int, b_bad: int, b_n: int) -> float:
    """Two-sided Fisher exact p: the total probability of tables at most as likely as the observed one."""
    total_bad, total = a_bad + b_bad, a_n + b_n
    def p(k):
        return comb(total_bad, k) * comb(total - total_bad, a_n - k) / comb(total, a_n)
    observed = p(a_bad)
    return min(1.0, sum(p(k) for k in range(max(0, total_bad - (total - a_n)), min(a_n, total_bad) + 1) if p(k) <= observed * (1 + 1e-9)))


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


def pooled(runs: dict[str, dict], control_name: str) -> dict:
    """Pool every run of the same model (phase A folder plus b<round>-<folder>) and test against the control pool."""
    pools: dict[str, dict] = {}
    for name, run in runs.items():
        family = name.split("-", 1)[1] if name[:1] == "b" and name[1:2].isdigit() and "-" in name else name
        pool = pools.setdefault(family, {"model": run["model"], "runs": [], "live": 0, "violations": 0, "completed": 0, "safe": 0,
                                         "rejected": 0, "errors": 0, "faults_scheduled": 0, "faults_triggered": 0,
                                         "by_case": {case: {"n": 0, "violations": 0, "completed": 0, "untriggered": 0, "checks": {}} for case in CASES},
                                         "input_tokens": 0, "output_tokens": 0, "cost": 0.0})
        s = summarize(run["record"])
        pool["runs"].append(name)
        pool["live"] += s["live_trials"]; pool["violations"] += s["violations"]; pool["completed"] += s["completed"]
        pool["safe"] += s["safe_unresolved"]; pool["rejected"] += s["correctly_rejected"]; pool["errors"] += s["lab_errors"]
        pool["faults_scheduled"] += s["faults_scheduled"]; pool["faults_triggered"] += s["faults_triggered"]
        usage = s["usage"] or {}
        pool["input_tokens"] += usage.get("input_tokens", 0); pool["output_tokens"] += usage.get("output_tokens", 0)
        pool["cost"] += usage.get("cost_dollars") or 0.0
        case_of = {slot["episode_id"]: slot["case_id"] for slot in run["record"].get("slots", [])}
        for trial in run["record"].get("trials", []):
            if trial.get("arm") != "B0":
                continue
            case = pool["by_case"].setdefault(case_of.get(trial["episode_id"], "?"), {"n": 0, "violations": 0, "completed": 0, "untriggered": 0, "checks": {}})
            case["n"] += 1
            case["violations"] += int(trial.get("outcome") == "VIOLATION")
            case["completed"] += int(trial.get("outcome") == "COMPLETED")
            case["untriggered"] += int(bool(trial.get("fault_scheduled")) and not trial.get("fault_triggered"))
            for check in trial.get("failed_checks", []):
                case["checks"][check] = case["checks"].get(check, 0) + 1
    control = pools.get(control_name)
    for family, pool in pools.items():
        if control is not None and family != control_name and pool["live"]:
            pool["fisher_two_sided_vs_control"] = fisher_two_sided(pool["violations"], pool["live"], control["violations"], control["live"])
    return pools


def print_pooled(pools: dict, control_name: str) -> None:
    print(f"{'model (pooled)':30} {'runs':>4} {'live':>5} {'viol':>5} {'done':>5} {'safe':>5} {'rej':>4} {'err':>4} {'faults':>9} {'in_tok':>10} {'out_tok':>8} {'cost $':>7} {'p2 vs ctl':>9}")
    for family, pool in pools.items():
        p = pool.get("fisher_two_sided_vs_control")
        print(f"{pool['model']:30} {len(pool['runs']):4} {pool['live']:5} {pool['violations']:5} {pool['completed']:5} {pool['safe']:5} "
              f"{pool['rejected']:4} {pool['errors']:4} {pool['faults_triggered']:4}/{pool['faults_scheduled']:<4} {pool['input_tokens']:10,} "
              f"{pool['output_tokens']:8,} {pool['cost']:7.3f} {'   ctl   ' if family == control_name else (f'{p:9.3f}' if p is not None else '        -')}")
    print()
    for family, pool in pools.items():
        print(f"{pool['model']}:")
        for case in CASES:
            c = pool["by_case"].get(case)
            if c and c["n"]:
                print(f"   {case}: n={c['n']:2} violations={c['violations']:2} completed={c['completed']:2} untriggered={c['untriggered']:2} checks={c['checks']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("screen", type=Path)
    parser.add_argument("--control", default="deepseek-v3.1-control", help="run folder name of the control model")
    parser.add_argument("--json", type=Path, default=None, help="also write the summary as JSON")
    parser.add_argument("--pooled", action="store_true", help="pool phase A and every b<round>- folder per model; two-sided Fisher vs the control pool")
    args = parser.parse_args(argv)
    runs = load(args.screen.expanduser())
    if not runs:
        print("no baseline-study.json found")
        return 1
    if args.pooled:
        pools = pooled(runs, args.control)
        print_pooled(pools, args.control)
        if args.json:
            args.json.write_text(json.dumps(pools, indent=2))
        return 0
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
