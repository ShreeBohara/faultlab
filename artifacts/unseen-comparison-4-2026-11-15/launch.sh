#!/bin/bash
# Unseen comparison 4 (a stronger Actor, Sonnet 5.5): a four-trial preflight on dev-5 with a gate, then the L3 rule study with advice as a
# requirement (Q), then, if the money left allows, as an expectation (E), on one fresh draw.
set -u
P=~/FaultLab_Runs/2026-11-15/unseen-comparison-4
R=/Users/shree/FaultLab/faultlab
MODEL=anthropic:claude-sonnet-5-5
cd "$R" || exit 9
( cd "$P" && [ -s DECLARATION.json ] && shasum -a 256 -c DECLARATION.sha256 >/dev/null 2>&1 ) || { echo "STOP no valid declaration"; exit 5; }
case "$(cat "$P/pilot_cap" 2>/dev/null)" in ''|*[!0-9.]*) echo "STOP no numeric pilot cap"; exit 5;; esac
[ -s "$P/sealed/cases.json" ] && [ -s "$P/policy-L3.json" ] || { echo "STOP no cases or rule"; exit 5; }
export FAULTLAB_ACTOR_MODEL="$MODEL"
export FAULTLAB_MONTHLY_DOLLAR_CAP="$(cat "$P/pilot_cap")"
billing() { grep -q -i -E '(^|[^0-9a-z])402([^0-9a-z]|$)|insufficient credit|credit balance|billing' "$1"; }
START_ID=$(.venv/bin/python -I - <<'PYI'
import sys
sys.path[:0] = ["/Users/shree/FaultLab/faultlab/backend"]
import sqlite3
from app.config import Settings
print(sqlite3.connect(Settings.from_env().spend_ledger_path).execute("select coalesce(max(id), 0) from charges").fetchone()[0])
PYI
)
case "$START_ID" in ''|*[!0-9]*) echo "STOP cannot read the ledger"; exit 5;; esac
echo "$(date -u +%FT%TZ) preflight start (4 dev-5 trials; ledger rows after id $START_ID; monthly cap for this process: $FAULTLAB_MONTHLY_DOLLAR_CAP)"
.venv/bin/python -m faultlab run --store "$P/preflight.sqlite3" --pack orders.upgrade_then_confirm/v1 --adapter model-actor \
  --model "$MODEL" --execute-live --dollars 0.672 --model-calls 8 --http-attempts 18 --wall-seconds 90 --scenario dev-5 --k 4 --referee legacy \
  --rule-policy "$P/policy-L3.json" --advice-presentation requirement --worlds "$P/preflight-worlds" --name unseen-comparison-4-preflight > "$P/preflight.log" 2>&1
code=$?
verdict=$(.venv/bin/python -I - "$P/preflight.sqlite3" "$START_ID" "$MODEL" <<'PYV'
import json, sqlite3, sys
sys.path[:0] = ["/Users/shree/FaultLab/faultlab/backend"]
from app.config import Settings
store, start, model = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    rows = [json.loads(r[0]) for r in sqlite3.connect(store).execute("select value from envelopes").fetchall()]
except Exception as error:
    print(f"FAIL no store: {error}"); raise SystemExit
charges = sqlite3.connect(Settings.from_env().spend_ledger_path).execute(
    "select model, output_tokens, actual_usd from charges where id > ?", (start,)).fetchall()
trials = [{"execution": e["outcome"]["execution"], "task": e["outcome"]["task"], "report": bool(e.get("report")),
           "calls": e["outcome"]["cost"]["model_calls"], "dollars": e["outcome"]["cost"]["dollars_measured"],
           "wall": round(e["outcome"]["cost"]["wall_seconds"], 1), "output_tokens": e["outcome"]["cost"]["output_tokens"]} for e in rows]
problems = []
if len(trials) != 4:
    problems.append(f"envelopes {len(trials)}")
for t in trials:
    if t["execution"] != "COMPLETED" or not t["report"] or t["dollars"] is None or t["wall"] >= 80:
        problems.append(f"trial {t}")
if not charges or any(c[0] != model for c in charges):
    problems.append(f"ledger models {sorted({c[0] for c in charges})}")
max_out = max((c[1] or 0 for c in charges), default=0)
if max_out >= 1900:
    problems.append(f"max output tokens {max_out}")
mean = sum(t["dollars"] or 0.0 for t in trials) / max(1, len(trials))
if mean > 0.12:
    problems.append(f"mean dollars {mean:.4f}")
print(("PASS" if not problems else "FAIL " + "; ".join(problems)), json.dumps({"trials": trials, "ledger_rows": len(charges), "max_output_tokens": max_out,
      "mean_dollars": round(mean, 5), "ledger_dollars": round(sum(c[2] or 0.0 for c in charges), 5)}))
PYV
)
echo "$(date -u +%FT%TZ) preflight exit $code: $verdict"
if billing "$P/preflight.log"; then echo "STOP billing message in preflight"; exit 4; fi
case "$verdict" in PASS*) ;; *) echo "STOP preflight failed"; exit 3;; esac
run_study() {
  local ARM=$1 PRES=$2
  echo "$(date -u +%FT%TZ) study $ARM ($PRES) start"
  .venv/bin/python -m faultlab study unseen --store "$P/$ARM/trials.sqlite3" --out "$P/$ARM" --name "unseen-comparison-4-$ARM-2026-11-15" \
    --cases "$P/sealed/cases.json" --policy "$P/policy-L3.json" --advice-presentation "$PRES" --adapter model-actor --model "$MODEL" \
    --execute-live --dollars 0.672 --study-dollars 56.45 --pairs 6 --other-pairs 3 --gap 6 --model-calls 8 --http-attempts 18 --wall-seconds 90 \
    --worlds "$P/$ARM/worlds" --declaration "$P/DECLARATION.json" --note "unseen comparison 4 (stronger Actor: Sonnet 5.5), L3 with advice as $PRES" > "$P/run-$ARM.log" 2>&1
  echo "$(date -u +%FT%TZ) study $ARM exit $?"
}
run_study Q requirement
if billing "$P/run-Q.log"; then echo "STOP billing message in study Q"; exit 4; fi
gate=$(.venv/bin/python -I - "$P" <<'PYC'
import json, sys
from pathlib import Path
sys.path[:0] = ["/Users/shree/FaultLab/faultlab/backend"]
from app.config import Settings
from app.providers.spend import SpendLedger
d = Path(sys.argv[1])
cap = float((d / "pilot_cap").read_text())
try:
    q = json.loads((d / "Q/unseen-study.json").read_text())
    spent = q["cost"]["measured"]["dollars"] or 0.0
except Exception as error:
    print(f"NO no Q record or cost: {error}"); raise SystemExit
left = cap - SpendLedger(Settings.from_env().spend_ledger_path).summary().committed
need = 1.2 * spent + 0.30
print(("YES" if q["decision"] != "INCOMPLETE" and left >= need else "NO"),
      json.dumps({"q_decision": q["decision"], "q_dollars": round(spent, 4), "left": round(left, 4), "need": round(need, 4)}))
PYC
)
echo "$(date -u +%FT%TZ) E gate: $gate"
case "$gate" in YES*) run_study E expectation;; *) echo "$(date -u +%FT%TZ) study E not started";; esac
if [ -s "$P/E/unseen-study.json" ]; then
  .venv/bin/python -m faultlab study compare --record "E=$P/E/unseen-study.json" --record "Q=$P/Q/unseen-study.json" --out "$P/comparison.json" > /dev/null \
    && .venv/bin/python -I - "$P/comparison.json" <<'PYS'
import json, sys
c = json.load(open(sys.argv[1]))
print("primary", json.dumps(c["primary"], sort_keys=True))
for name in c["order"]:
    a = c["arms"][name]; L = a["rejected"]["L"]; B = a["rejected"]["B0"]
    print(name, a["decision"], "failed", a["failed_cases"])
    print("  L", json.dumps({k: L[k] for k in ("trials", "slips", "acted", "trials_with_block", "side_effect_trials", "trials_with_advice", "advice_turns",
                                              "advised_then_blocked", "correct_refusals", "tasks", "legacy")}, sort_keys=True))
    print("  L calls", json.dumps(L["model_calls"], sort_keys=True), "silent", json.dumps(L["rule_silent"], sort_keys=True))
    print("  L last-call advice", json.dumps(L["last_call_advice"], sort_keys=True))
    print("  B0", json.dumps({k: B[k] for k in ("trials", "slips", "correct_refusals", "no_report", "tasks")}, sort_keys=True))
    print("  measured", json.dumps(a["measured"], sort_keys=True))
PYS
else
  .venv/bin/python -I -c "import json,sys; r=json.load(open(sys.argv[1])); print('Q', r['decision'], r['reason']); print('cost', json.dumps(r['cost']))" "$P/Q/unseen-study.json"
fi
echo "$(date -u +%FT%TZ) done"
