"""The declared read-outs of the advice-presentation development check, from the two stores; offline."""
import json, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab"); d = Path(sys.argv[1])
sys.path[:0] = [str(R / "backend"), str(R)]
from faultlab.lab import TrialStore
from faultlab.research.compare import fisher_exact, rule_rows
from faultlab.research.repair_study import summarize_trial
arms = {}
for arm in ("E", "Q"):
    with TrialStore(d / f"{arm}.sqlite3") as store:
        envelopes = store.envelopes()
    rows = [summarize_trial(e, expected_class="rejected", target_rule="notification_label_after_rejection", arm="L") for e in envelopes]
    arms[arm] = {"envelopes": len(envelopes), "executions": sorted({e.outcome.execution for e in envelopes}), **rule_rows(rows, 8),
                 "dollars": round(sum(r["dollars"] or 0.0 for r in rows), 6)}
e, q = arms["E"], arms["Q"]
p = fisher_exact(q["trials_with_block"], q["trials"] - q["trials_with_block"], e["trials_with_block"], e["trials"] - e["trials_with_block"])
proceed = (q["trials_with_block"] * 2 <= e["trials_with_block"] and q["slips"] == 0 and q["side_effect_trials"] <= e["side_effect_trials"]
           and q["trials"] == 12 and e["trials"] == 12)
out = {"arms": arms, "trials_with_block": {"E": [e["trials_with_block"], e["trials"]], "Q": [q["trials_with_block"], q["trials"]], "fisher_two_sided_p": round(p, 6)},
       "decision": "PROCEED" if proceed else "STOP"}
(d / "readouts.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps(out, indent=2, sort_keys=True))
