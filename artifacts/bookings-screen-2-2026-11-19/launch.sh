set -u
P=~/FaultLab_Runs/2026-11-19/bookings-screen-2
R=/Users/shree/FaultLab/faultlab
MODEL=anthropic:claude-haiku-5-5
cd "$R" || exit 9
( cd "$P" && [ -s DECLARATION.json ] && shasum -a 256 -c DECLARATION.sha256 >/dev/null 2>&1 ) || { echo "STOP no valid declaration"; exit 5; }
case "$(cat "$P/pilot_cap" 2>/dev/null)" in ''|*[!0-9.]*) echo "STOP no numeric pilot cap"; exit 5;; esac
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
echo "$START_ID" > "$P/start_id"
run() { name=$1; .venv/bin/python -I "$P/run_stage.py" "$name" > "$P/$name.log" 2>&1; }
echo "$(date -u +%FT%TZ) preflight start (first drawn case x3; ledger rows after id $START_ID; process monthly cap $FAULTLAB_MONTHLY_DOLLAR_CAP)"
run preflight
code=$?
verdict=$(.venv/bin/python -I "$P/readout.py" "$P" "$START_ID" preflight)
echo "$(date -u +%FT%TZ) preflight exit $code: $verdict"
if billing "$P/preflight.log"; then echo "STOP billing message in preflight"; exit 4; fi
case "$verdict" in PASS*) ;; *) echo "STOP preflight failed"; exit 3;; esac
echo "$(date -u +%FT%TZ) rest start (15 cases x3)"
run rest
code=$?
echo "$(date -u +%FT%TZ) rest exit $code"
if billing "$P/rest.log"; then echo "STOP billing message in the run"; fi
echo "$(date -u +%FT%TZ) readout: $(.venv/bin/python -I "$P/readout.py" "$P" "$START_ID" final)"
