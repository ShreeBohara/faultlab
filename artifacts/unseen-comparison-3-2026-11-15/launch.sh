#!/bin/bash
# Unseen comparison 3 (late evidence): preflight trial, then the L3 rule study with advice as an expectation (E), then as a requirement (Q), on the four late cases.
set -u
P=~/FaultLab_Runs/2026-11-15/unseen-comparison-3
R=/Users/shree/FaultLab/faultlab
cd "$R" || exit 9
( cd "$P" && [ -s DECLARATION.json ] && shasum -a 256 -c DECLARATION.sha256 >/dev/null 2>&1 ) || { echo "STOP no valid declaration"; exit 5; }
case "$(cat "$P/pilot_cap" 2>/dev/null)" in ''|*[!0-9.]*) echo "STOP no numeric pilot cap"; exit 5;; esac
[ -s "$P/sealed/cases.json" ] && [ -s "$P/policy-L3.json" ] || { echo "STOP no cases or rule"; exit 5; }
export FAULTLAB_ACTOR_MODEL=anthropic:claude-haiku-5-5
export FAULTLAB_MONTHLY_DOLLAR_CAP="$(cat "$P/pilot_cap")"
echo "$(date -u +%FT%TZ) preflight start (monthly cap for this process: $FAULTLAB_MONTHLY_DOLLAR_CAP)"
.venv/bin/python -m faultlab run --store "$P/preflight.sqlite3" --pack orders.upgrade_then_confirm/v1 --adapter model-actor \
  --model anthropic:claude-haiku-5-5 --execute-live --dollars 0.034 --scenario dev-5 --k 1 --referee legacy \
  --worlds "$P/preflight-worlds" --name unseen-comparison-3-preflight > "$P/preflight.log" 2>&1
code=$?
verdict=$(.venv/bin/python -I - "$P/preflight.sqlite3" <<'PYV'
import json, sqlite3, sys
try:
    rows = sqlite3.connect(sys.argv[1]).execute("select value from envelopes").fetchall()
except Exception as error:
    print(f"FAIL no store: {error}"); raise SystemExit
if len(rows) != 1:
    print(f"FAIL envelopes {len(rows)}"); raise SystemExit
e = json.loads(rows[0][0]); o = e["outcome"]
ok = o["execution"] == "COMPLETED" and o["cost"]["model_calls"] >= 1 and o["cost"]["dollars_measured"] is not None
print(("PASS" if ok else "FAIL"), json.dumps({"execution": o["execution"], "task": o["task"], "calls": o["cost"]["model_calls"], "dollars": o["cost"]["dollars_measured"]}))
PYV
)
echo "$(date -u +%FT%TZ) preflight exit $code: $verdict"
if grep -q -i -E '(^|[^0-9a-z])402([^0-9a-z]|$)|insufficient credit|credit balance|billing' "$P/preflight.log"; then echo "STOP billing message in preflight"; exit 4; fi
case "$verdict" in PASS*) ;; *) echo "STOP preflight failed"; exit 3;; esac
for ARM in E Q; do
  if [ "$ARM" = E ]; then PRES=expectation; else PRES=requirement; fi
  echo "$(date -u +%FT%TZ) study $ARM ($PRES) start"
  .venv/bin/python -m faultlab study unseen --store "$P/$ARM/trials.sqlite3" --out "$P/$ARM" --name "unseen-comparison-3-$ARM-2026-11-15" \
    --cases "$P/sealed/cases.json" --policy "$P/policy-L3.json" --advice-presentation "$PRES" --adapter model-actor --model anthropic:claude-haiku-5-5 \
    --execute-live --dollars 0.034 --study-dollars 6.53 --pairs 24 --gap 6 --model-calls 8 --http-attempts 18 --wall-seconds 90 \
    --worlds "$P/$ARM/worlds" --declaration "$P/DECLARATION.json" --note "unseen comparison 3 (late evidence), L3 with advice as $PRES" > "$P/run-$ARM.log" 2>&1
  echo "$(date -u +%FT%TZ) study $ARM exit $?"
done
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
echo "$(date -u +%FT%TZ) done"
