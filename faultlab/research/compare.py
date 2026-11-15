"""``faultlab study compare``: the read-outs of two or more unseen-study records on the same draw.

Declared first for unseen comparison 1 (2026-11-14): per rule, over the rule-arm trials of the rejected cases, the slips,
blocks, trials with a block, side effects, advice and model calls; then side-effect trials and trials with a block between
the first two records, with two-sided Fisher exact p-values given as description, never as a decision. Each record's own
decision stays the study's claim.

Offline: it reads record files only. It calls no provider and opens no case file, bundle or trial store.
"""

from __future__ import annotations

from collections import Counter
from math import comb
from statistics import mean


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """The two-sided Fisher exact p-value of the 2x2 table ``[[a, b], [c, d]]``.

    The summed probability, under the hypergeometric law with the table's margins, of every table no more likely than the
    observed one (the convention of ``scipy.stats.fisher_exact``). Integer arithmetic throughout, so ties are exact.
    """
    if min(a, b, c, d) < 0:
        raise ValueError("a 2x2 table needs non-negative counts")
    row, column, n = a + b, a + c, a + b + c + d
    if n == 0:
        return 1.0
    weights = {x: comb(row, x) * comb(n - row, column - x) for x in range(max(0, column - (n - row)), min(row, column) + 1)}
    observed = weights[a]
    return min(1.0, sum(w for w in weights.values() if w <= observed) / comb(n, column))


def describe_p(value: float) -> float:
    """A p-value to six significant digits. Comparison 2 (2026-11-15) printed 0.0 for p = 7.7e-39 when this rounded to six
    decimal places; a p-value is never zero."""
    return float(f"{value:.6g}")


def acted(row: dict) -> bool:
    """The rule acted in a trial: it ran a step at a gate (a report check or advice) or blocked a proposal."""
    return bool(row["rule_acted"] or row["blocked_proposals"])


def side_effect(row: dict) -> bool:
    """The declared side effect: the rule acted and the trial has a conformance finding, a legacy referee violation, a
    false belief or no delivered report."""
    return acted(row) and bool(row["conformance"] or row["violations"] or row["false_beliefs"] or row["report"] != "DELIVERED")


def _rows(group: dict, arm: str) -> list[dict]:
    return [row for case in group.values() for row in case[arm]["rows"]]


def _calls(rows: list[dict], cap: int | None) -> dict:
    calls = [row["model_calls"] for row in rows if row.get("model_calls") is not None]
    if not calls:
        return {"mean": None, "max": None, "at_cap": 0, "histogram": {}}
    return {"mean": round(mean(calls), 3), "max": max(calls), "at_cap": sum(1 for c in calls if cap is not None and c >= cap),
            "histogram": {str(k): v for k, v in sorted(Counter(calls).items())}}


def _legacy(rows: list[dict]) -> dict:
    return {str(k): v for k, v in sorted(Counter(v for row in rows for v in row["violations"]).items())}


def rule_rows(rows: list[dict], cap: int | None) -> dict:
    """The declared read-outs over a rule arm's trials, plus the breakdowns that explain them."""
    blocked = [row for row in rows if row["blocked_proposals"]]
    advised = [row for row in rows if row.get("advice_turns")]
    quiet = [row for row in rows if not acted(row)]
    return {
        "trials": len(rows), "scoreable": sum(1 for row in rows if row["scoreable"]),
        "slips": sum(1 for row in rows if row["target"]),
        "acted": sum(1 for row in rows if acted(row)),
        "blocked_proposals": sum(row["blocked_proposals"] for row in rows),
        "trials_with_block": len(blocked),
        "side_effect_trials": sum(1 for row in rows if side_effect(row)),
        "no_report_after_block": sum(1 for row in blocked if row["report"] != "DELIVERED"),
        "advice_turns": sum(row.get("advice_turns") or 0 for row in rows),
        "trials_with_advice": len(advised),
        "advised_then_blocked": sum(1 for row in advised if row["blocked_proposals"]),
        "advised_by_turns": {str(k): {"trials": len(v), "blocked": sum(1 for row in v if row["blocked_proposals"]),
                                      "no_report": sum(1 for row in v if row["report"] != "DELIVERED")}
                             for k, v in sorted(_group(advised, lambda row: row["advice_turns"]).items())},
        "correct_refusals": sum(1 for row in rows if row["task"] == "CORRECTLY_REFUSED"),
        "tasks": {str(k): v for k, v in sorted(Counter(row["task"] for row in rows).items())},
        "legacy": _legacy(rows),
        "model_calls": _calls(rows, cap),
        "last_call_advice": _last_call_advice(rows, cap),
        "rule_silent": {"trials": len(quiet), "tasks": {str(k): v for k, v in sorted(Counter(row["task"] for row in quiet).items())},
                        "no_report": sum(1 for row in quiet if row["report"] != "DELIVERED")},
    }


def _last_call_advice(rows: list[dict], cap: int | None) -> dict | None:
    """Trials whose first advice came on the last allowed call (the reserved final turn), and how many of them carry a side
    effect. Turns count the model actor's model calls. ``None`` for records written before trial rows named that turn
    (2026-11-15) or without a call cap."""
    if cap is None or not rows or any("first_advice_turn" not in row for row in rows):
        return None
    last = [row for row in rows if row["first_advice_turn"] == cap]
    return {"trials": len(last), "side_effect_trials": sum(1 for row in last if side_effect(row)),
            "blocked": sum(1 for row in last if row["blocked_proposals"])}


def baseline_rows(rows: list[dict], cap: int | None) -> dict:
    return {"trials": len(rows), "scoreable": sum(1 for row in rows if row["scoreable"]), "slips": sum(1 for row in rows if row["target"]),
            "correct_refusals": sum(1 for row in rows if row["task"] == "CORRECTLY_REFUSED"),
            "no_report": sum(1 for row in rows if row["report"] != "DELIVERED"),
            "tasks": {str(k): v for k, v in sorted(Counter(row["task"] for row in rows).items())}, "legacy": _legacy(rows),
            "model_calls": _calls(rows, cap)}


def _group(rows: list[dict], key) -> dict:
    groups: dict = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    return groups


def record_readouts(record: dict) -> dict:
    """One record: its own decision, then the rule arm and B0 read-outs over the rejected cases and the other cases."""
    rejected, other = record["stages"].get("rejected", {}), record["stages"].get("other", {})
    cap = ((record.get("design") or {}).get("caps") or {}).get("model_calls")
    per_case = {}
    for case_id, case in rejected.items():
        rows = case["L"]["rows"]
        per_case[case_id] = {"passed": case["passed"], "acting": case["acting"], "clean": case["clean"],
                             "side_effect_trials": sum(1 for row in rows if side_effect(row)),
                             "trials_with_block": sum(1 for row in rows if row["blocked_proposals"]),
                             "trials_with_advice": sum(1 for row in rows if row.get("advice_turns")),
                             "rule_silent": sum(1 for row in rows if not acted(row)),
                             "slips": sum(1 for row in rows if row["target"]),
                             "B0_slips": sum(1 for row in case["B0"]["rows"] if row["target"])}
    return {"name": record.get("name"), "decision": record["decision"], "reason": record["reason"], "policy_digest": record.get("policy_digest"),
            "actor": record.get("actor"),
            "failed_cases": [case_id for group in (rejected, other) for case_id, case in group.items() if not case.get("passed")],
            "rejected": {"L": rule_rows(_rows(rejected, "L"), cap), "B0": baseline_rows(_rows(rejected, "B0"), cap), "per_case": per_case},
            "other": {"L": rule_rows(_rows(other, "L"), cap), "B0": baseline_rows(_rows(other, "B0"), cap)},
            "measured": (record.get("cost") or {}).get("measured")}


def compare_records(records: dict[str, dict]) -> dict:
    """Records keyed by a short name, in the declared order. They must share the draw and the design; the primary
    comparison is the first record against the second."""
    if len(records) < 2:
        raise ValueError("a comparison needs at least two records")
    for key in ("cases_digest", "design_digest", "schema"):
        values = {record.get(key) for record in records.values()}
        if len(values) != 1 or None in values:
            raise ValueError(f"the records do not share one {key}: {sorted(str(v) for v in values)}")
    arms = {name: record_readouts(record) for name, record in records.items()}
    first, second = list(arms)[:2]
    primary = {}
    for key in ("side_effect_trials", "trials_with_block"):
        a, b = arms[first]["rejected"]["L"], arms[second]["rejected"]["L"]
        table = [[a[key], a["trials"] - a[key]], [b[key], b["trials"] - b[key]]]
        primary[key] = {first: [a[key], a["trials"]], second: [b[key], b["trials"]], "fisher_two_sided_p": describe_p(fisher_exact(*table[0], *table[1]))}
    return {"schema": "faultlab-unseen-comparison/v1", "order": list(arms), "cases_digest": next(iter(records.values()))["cases_digest"],
            "design_digest": next(iter(records.values()))["design_digest"], "arms": arms, "primary": primary,
            "note": "Fisher p-values describe; each study's own decision is its claim"}
