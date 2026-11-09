#!/bin/bash
# The unseen-case test: preflight trial, then the study. Run from the launcher command under caffeinate.
set -u
P=~/FaultLab_Runs/2026-11-08/unseen-study-1
R=/Users/shree/FaultLab/faultlab
cd "$R" || exit 9
( cd "$P" && [ -s DECLARATION.json ] && shasum -a 256 -c DECLARATION.sha256 >/dev/null 2>&1 ) || { echo "STOP no valid declaration"; exit 5; }
case "$(cat "$P/pilot_cap" 2>/dev/null)" in ''|*[!0-9.]*) echo "STOP no numeric pilot cap"; exit 5;; esac
[ -s "$P/sealed/cases.json" ] && [ -s "$P/policy.json" ] || { echo "STOP no cases or rule"; exit 5; }
export FAULTLAB_ACTOR_MODEL=anthropic:claude-haiku-5-5
export FAULTLAB_MONTHLY_DOLLAR_CAP="$(cat "$P/pilot_cap")"
echo "$(date -u +%FT%TZ) preflight start (monthly cap for this process: $FAULTLAB_MONTHLY_DOLLAR_CAP)"
.venv/bin/python -m faultlab run --store "$P/preflight.sqlite3" --pack orders.upgrade_then_confirm/v1 --adapter model-actor \
  --model anthropic:claude-haiku-5-5 --execute-live --dollars 0.034 --scenario dev-5 --k 1 --referee legacy \
  --worlds "$P/preflight-worlds" --name unseen-study-1-preflight > "$P/preflight.log" 2>&1
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
if grep -q -i -E "402|insufficient credit|billing" "$P/preflight.log"; then echo "STOP billing message in preflight"; exit 4; fi
case "$verdict" in PASS*) ;; *) echo "STOP preflight failed"; exit 3;; esac
echo "$(date -u +%FT%TZ) study start"
.venv/bin/python -m faultlab study unseen --store "$P/trials.sqlite3" --out "$P" --name unseen-study-1-2026-11-08 --cases "$P/sealed/cases.json" --policy "$P/policy.json" \
  --adapter model-actor --model anthropic:claude-haiku-5-5 --execute-live --dollars 0.0504 --study-dollars 4.84 --pairs 6 --gap 6 \
  --worlds "$P/worlds" --declaration "$P/DECLARATION.json" \
  --note "first unseen-case test; Actor on the Anthropic API (real money); rule frozen from the second API pilot; no Mechanic" > "$P/run.log" 2>&1
echo "$(date -u +%FT%TZ) study exit $?"
