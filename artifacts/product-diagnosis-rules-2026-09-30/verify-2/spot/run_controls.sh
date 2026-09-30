#!/usr/bin/env bash
# Verifier-2 ($0, offline): saved-store snapshot controls in scratch trees outside the Desktop.
#   checkpoint = git archive of 626bae4 (no audit/promotion.json, final-audit, heldout2, .env)
#   current    = checkpoint + the 23 changed product files (sha256 checked equal to the working tree)
# Each run copies ONE test file into <tree>/backend/tests/lab/test_zv2_<label>.py with the saved-store path replaced by a
# scratch store variant, runs only the saved-store tests (-k), under -p vplug (guard + promotion stub), then deletes it.
set -u
S=/Users/shree/FaultLab_Scratch/verify-2
PY=/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python
ORIG=/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3
run() {  # label tree source-test-file store-variant -k-expression
  local label=$1 tree=$2 src=$3 store=$4 k=$5
  local dst="$S/$tree/backend/tests/lab/test_zv2_${label}.py"
  sed "s#$ORIG#$S/store/$store#g" "$src" > "$dst"
  grep -q "$S/store/$store" "$dst" || { echo "!! path not replaced in $label"; rm -f "$dst"; return; }
  echo "== $label: tree=$tree test=$(basename $src) store=$store -k '$k'"
  (cd "$S/$tree/backend" && PYTHONPATH="$S/plug" PYTHONDONTWRITEBYTECODE=1 "$PY" -B -m pytest -p vplug -p no:cacheprovider -q -k "$k" \
     "tests/lab/test_zv2_${label}.py" 2>&1 | grep -E "^(E  +assert|E  +[A-Za-z]*Error|FAILED|ERROR|[0-9]+ (passed|failed)|.*(passed|failed|error).* in |\[verifier guard\])" | head -20)
  rm -f "$dst"
}
FIRE='saved_store or saved_stores'
V2D='refused_v2d_request'
T1='every_saved_native_v2b_plan'
CKP=$S/checkpoint/backend/tests/lab; CUR=$S/current/backend/tests/lab
# E1: the original 626bae4 tests, unchanged except the store path
run orig_fire_6748   checkpoint $CKP/test_history_fireability.py         lab-upto-6748.sqlite3 "$FIRE"
run orig_fire_today  checkpoint $CKP/test_history_fireability.py         lab.sqlite3           "$FIRE"
run orig_v2d_3022    checkpoint $CKP/test_loop_limits_mechanic_context.py lab-upto-3022.sqlite3 "$V2D"
run orig_v2d_today   checkpoint $CKP/test_loop_limits_mechanic_context.py lab.sqlite3           "$V2D"
run orig_v2d_grown   checkpoint $CKP/test_loop_limits_mechanic_context.py lab-grown.sqlite3     "$V2D"
run orig_fire_grown  checkpoint $CKP/test_history_fireability.py         lab-grown.sqlite3     "$FIRE"
# The pinned tests of this follow-up
run pin_fire_today   current $CUR/test_history_fireability.py            lab.sqlite3           "$FIRE"
run pin_fire_grown   current $CUR/test_history_fireability.py            lab-grown.sqlite3     "$FIRE"
run pin_fire_6748    current $CUR/test_history_fireability.py            lab-upto-6748.sqlite3 "$FIRE"
run pin_v2d_grown    current $CUR/test_loop_limits_mechanic_context.py   lab-grown.sqlite3     "$V2D"
run pin_v2d_3022     current $CUR/test_loop_limits_mechanic_context.py   lab-upto-3022.sqlite3 "$V2D"
run pin_T1_today     current $CUR/test_diagnosis_rules.py                lab.sqlite3           "$T1"
run pin_T1_grown     current $CUR/test_diagnosis_rules.py                lab-grown.sqlite3     "$T1"
