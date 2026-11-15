#!/bin/bash
# Final-turn development check: the L3 rule on dev-5 with a 5-call budget, 24 trials with advice as an expectation (E), then 24 as a requirement (Q).
set -u
P=~/FaultLab_Runs/2026-11-15/advice-final-turn-dev-2
R=/Users/shree/FaultLab/faultlab
cd "$R" || exit 9
( cd "$P" && [ -s DECLARATION.json ] && shasum -a 256 -c DECLARATION.sha256 >/dev/null 2>&1 ) || { echo "STOP no valid declaration"; exit 5; }
case "$(cat "$P/pilot_cap" 2>/dev/null)" in ''|*[!0-9.]*) echo "STOP no numeric pilot cap"; exit 5;; esac
[ -s "$P/policy-L3.json" ] || { echo "STOP no rule"; exit 5; }
export FAULTLAB_ACTOR_MODEL=anthropic:claude-haiku-5-5
export FAULTLAB_MONTHLY_DOLLAR_CAP="$(cat "$P/pilot_cap")"
for ARM in E Q; do
  if [ "$ARM" = E ]; then PRES=expectation; else PRES=requirement; fi
  echo "$(date -u +%FT%TZ) arm $ARM ($PRES) start (monthly cap for this process: $FAULTLAB_MONTHLY_DOLLAR_CAP)"
  .venv/bin/python -m faultlab run --store "$P/$ARM.sqlite3" --pack orders.upgrade_then_confirm/v1 --adapter model-actor \
    --model anthropic:claude-haiku-5-5 --execute-live --dollars 0.034 --model-calls 5 --http-attempts 18 --wall-seconds 90 \
    --scenario dev-5 --k 24 --referee legacy --rule-policy "$P/policy-L3.json" --advice-presentation "$PRES" --worlds "$P/worlds-$ARM" \
    --bundle "$P/bundle-$ARM.zip" --name "advice-final-turn-dev-2-$ARM" > "$P/run-$ARM.log" 2>&1
  code=$?
  echo "$(date -u +%FT%TZ) arm $ARM exit $code"
  if grep -q -i -E '(^|[^0-9a-z])402([^0-9a-z]|$)|insufficient credit|credit balance|billing' "$P/run-$ARM.log"; then echo "STOP billing message in arm $ARM"; exit 4; fi
  if grep -q '"INFRA_ERROR"' "$P/run-$ARM.log" || [ $code -ne 0 ]; then echo "STOP arm $ARM had an infrastructure error or exit $code"; exit 3; fi
done
.venv/bin/python -I "$P/readouts.py" "$P"
echo "$(date -u +%FT%TZ) done"
