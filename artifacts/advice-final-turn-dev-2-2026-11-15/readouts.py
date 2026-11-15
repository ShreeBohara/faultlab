"""The declared read-outs of the final-turn development check, from the two stores; offline."""
import json, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab"); d = Path(sys.argv[1])
sys.path[:0] = [str(R / "backend"), str(R)]
from faultlab.lab import TrialStore
from faultlab.lab.rules import ADVICE_HOOK
from faultlab.research.compare import describe_p, fisher_exact, rule_rows
from faultlab.research.repair_study import summarize_trial
CAP, TRIALS = 5, 24
arms = {}
for arm in ("E", "Q"):
    with TrialStore(d / f"{arm}.sqlite3") as store:
        envelopes = store.envelopes()
    rows, first = [], []
    for e in envelopes:
        rows.append(summarize_trial(e, expected_class="rejected", target_rule="notification_label_after_rejection", arm="L"))
        turns = [ev.payload["turn"] for ev in e.events if ev.kind == "rule_step" and isinstance(ev.payload, dict)
                 and ev.payload.get("hook") == ADVICE_HOOK and ev.payload.get("advice")]
        first.append(min(turns) if turns else None)
    arms[arm] = {"envelopes": len(envelopes), "executions": sorted({e.outcome.execution for e in envelopes}), **rule_rows(rows, CAP),
                 "first_advice_turn": {str(k): first.count(k) for k in sorted({t for t in first if t is not None})} | {"none": first.count(None)},
                 "first_advice_on_last_call": sum(1 for t in first if t == CAP),
                 "side_effects_with_first_advice_on_last_call": sum(1 for t, r in zip(first, rows) if t == CAP and (r["rule_acted"] or r["blocked_proposals"])
                                                                     and (r["conformance"] or r["violations"] or r["false_beliefs"] or r["report"] != "DELIVERED")),
                 "dollars": round(sum(r["dollars"] or 0.0 for r in rows), 6)}
e, q = arms["E"], arms["Q"]
p = fisher_exact(e["side_effect_trials"], e["trials"] - e["side_effect_trials"], q["side_effect_trials"], q["trials"] - q["side_effect_trials"])
complete = e["trials"] == TRIALS and q["trials"] == TRIALS
if not complete:
    decision = "INCOMPLETE"
elif e["side_effect_trials"] < 4:
    decision = "INCONCLUSIVE"
elif q["side_effect_trials"] * 4 <= e["side_effect_trials"] and q["slips"] == 0:
    decision = "PROCEED"
else:
    decision = "STOP"
out = {"arms": arms, "side_effect_trials": {"E": [e["side_effect_trials"], e["trials"]], "Q": [q["side_effect_trials"], q["trials"]],
       "fisher_two_sided_p": describe_p(p)}, "decision": decision}
(d / "readouts.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps(out, indent=2, sort_keys=True))
