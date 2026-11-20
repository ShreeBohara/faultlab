"""Readouts of bookings screen 1 from its trial stores (and the ledger rows it added), as declared."""
import json, sqlite3, sys
from collections import Counter
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab")
sys.path[:0] = [str(R), str(R / "backend")]
from app.config import Settings

d, start, mode = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
MODEL = "anthropic:claude-haiku-5-5"
trials = []
for name in ("preflight", "rest"):
    store = d / f"{name}.sqlite3"
    if not store.exists():
        continue
    for (value,) in sqlite3.connect(store).execute("select value from envelopes"):
        e = json.loads(value)
        out = e["outcome"]
        failed = [f["property_id"] for f in out.get("findings", []) if f["result"] == "VIOLATION"]
        beliefs = {k: v.get("belief") for k, v in (out.get("claims", {}).get("claims") or {}).items()}
        trials.append({"case": e["plan"]["scenario_id"], "stage": name, "execution": out["execution"], "task": out["task"],
                       "failed": failed, "lowest": failed[0] if failed else None, "report": e["report"]["status"],
                       "false_beliefs": sorted(k for k, v in beliefs.items() if v == "FALSE"), "calls": out["cost"]["model_calls"],
                       "dollars": out["cost"]["dollars_measured"], "wall": round(out["cost"]["wall_seconds"], 1),
                       "output_tokens": out["cost"]["output_tokens"], "reason": e["attempt"].get("terminal_reason")})
charges = sqlite3.connect(Settings.from_env().spend_ledger_path).execute(
    "select model, output_tokens, actual_usd from charges where id > ?", (start,)).fetchall()
ledger = {"rows": len(charges), "models": sorted({c[0] for c in charges}), "max_output_tokens": max((c[1] or 0 for c in charges), default=0),
          "dollars": round(sum(c[2] or 0.0 for c in charges), 6)}
if mode == "preflight":
    pre = [t for t in trials if t["stage"] == "preflight"]
    problems = [f"envelopes {len(pre)}"] if len(pre) != 3 else []
    problems += [f"trial {t}" for t in pre if t["execution"] != "COMPLETED" or t["dollars"] is None or t["wall"] >= 80]
    if not charges or ledger["models"] != [MODEL]:
        problems.append(f"ledger models {ledger['models']}")
    if ledger["max_output_tokens"] >= 1900:
        problems.append(f"max output tokens {ledger['max_output_tokens']}")
    mean = sum(t["dollars"] or 0.0 for t in pre) / max(1, len(pre))
    if mean >= 0.03:
        problems.append(f"mean dollars {mean:.4f}")
    print(("PASS" if not problems else "FAIL " + "; ".join(problems)), json.dumps({"trials": pre, "ledger": ledger}))
    raise SystemExit
cases = {}
for t in trials:
    cases.setdefault(t["case"], []).append(t)
per_case = {}
for case, rows in sorted(cases.items()):
    lowest = Counter(t["lowest"] for t in rows if t["lowest"])
    repeated = sorted(check for check, n in lowest.items() if n >= 2)
    per_case[case] = {"trials": len(rows), "clean": sum(1 for t in rows if not t["failed"]), "lowest_failed": [t["lowest"] for t in rows],
                      "failed": [t["failed"] for t in rows], "tasks": [t["task"] for t in rows], "no_report": sum(1 for t in rows if t["report"] != "DELIVERED"),
                      "false_beliefs": [t["false_beliefs"] for t in rows], "repeated_mistake": repeated}
repeated = {case: c["repeated_mistake"] for case, c in per_case.items() if c["repeated_mistake"]}
summary = {"declaration_sha256": (d / "DECLARATION.sha256").read_text().split()[0], "trials": len(trials),
           "executions": dict(Counter(t["execution"] for t in trials)), "clean_trials": sum(1 for t in trials if not t["failed"]),
           "h2_trials": sum(1 for t in trials if "H2" in t["failed"]), "h3_trials": sum(1 for t in trials if "H3" in t["failed"]),
           "no_report_trials": sum(1 for t in trials if t["report"] != "DELIVERED"),
           "lowest_failed_counts": dict(Counter(t["lowest"] for t in trials if t["lowest"])),
           "false_belief_counts": dict(Counter(b for t in trials for b in t["false_beliefs"])),
           "measured_dollars": round(sum(t["dollars"] or 0.0 for t in trials), 6), "model_calls": sum(t["calls"] for t in trials),
           "ledger": ledger, "repeated_mistakes": repeated,
           "decision": ("REPEATED_MISTAKE_FOUND" if repeated else "NO_REPEATED_MISTAKE") if len(trials) == 24 else "INCOMPLETE"}
(d / "screen.json").write_text(json.dumps({"summary": summary, "per_case": per_case, "trials": trials}, indent=2, sort_keys=True))
print(json.dumps(summary))
