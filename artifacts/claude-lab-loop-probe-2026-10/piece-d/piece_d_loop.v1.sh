#!/bin/bash
# Piece D loop: five completion studies in sequence (Actor Claude Sonnet 5.5; Explorer and Mechanic Claude Opus 5.5) under
# DECLARATION.piece-d.json. Stops on a driver error or an unexpected status, a runaway measured cost, a provider error naming
# credit or billing, or the month's Anthropic settled total passing the credit. Same shape as the phase B/C loop.
set -u
cd /Users/shree/FaultLab/faultlab
SCREEN=/Users/shree/FaultLab_Runs/2026-10-12/claude-lab-loop-probe-piece-d
SHA=f18eb9a3af1ee02977cc162b4fa21c7273c8be1759d40881bde40c0d9731190e
ACTOR=anthropic:claude-sonnet-5-5
LAB=anthropic:claude-opus-5-5
LEDGER=/Users/shree/.faultlab/spend-ledger.sqlite3
for n in 1 2 3 4 5; do
  dir="$SCREEN/d$n-sonnet-actor-opus-mechanic"
  echo "=== study $n actor $ACTOR lab $LAB cap 300 -> $dir" | tee -a "$SCREEN/piece_d.log"
  ./.venv/bin/python scripts/experiments/baseline_screen.py --study completion --model "$ACTOR" --lab-model "$LAB" --evidence-protocol faultlab-compact-evidence/v2-task-outcome --data-dir "$dir" --declaration "$SCREEN/DECLARATION.piece-d.json" --declaration-sha256 "$SHA" --dollar-cap 300 --monthly-cap 400 --settle-seconds 30 >> "$SCREEN/piece_d.log" 2>&1
  status=$(python3 -c "import json,sys; d=json.load(open('$dir/RESULT.json')); print('error' if d.get('error') else d.get('summary',{}).get('status'))" 2>/dev/null)
  decision=$(python3 -c "import json; d=json.load(open('$dir/RESULT.json')); print((d.get('summary') or {}).get('decision'))" 2>/dev/null)
  cost=$(python3 -c "import json; d=json.load(open('$dir/RESULT.json')); print(((d.get('summary') or {}).get('usage') or {}).get('cost_dollars') or 0)" 2>/dev/null)
  limit=80
  anthropic=$(sqlite3 "$LEDGER" "select coalesce(sum(actual_usd),0) from charges where month='2026-10' and provider='anthropic'" 2>/dev/null || echo 0)
  echo "    status: $status decision: $decision measured_cost: $cost (runaway limit $limit) anthropic settled this month: $anthropic" | tee -a "$SCREEN/piece_d.log"
  if python3 -c "import sys; sys.exit(0 if float('$cost' or 0) > float('$limit') else 1)"; then echo "STOPPING LOOP: measured cost $cost exceeds the runaway limit $limit" | tee -a "$SCREEN/piece_d.log"; exit 1; fi
  if grep -qiE "HTTP 402|insufficient[ _-]?credit|billing" "$dir/driver.log" "$dir/RESULT.json" "$dir/export.json" 2>/dev/null; then echo "STOPPING LOOP: provider error naming credit or billing (see $dir)" | tee -a "$SCREEN/piece_d.log"; exit 1; fi
  if python3 -c "import sys; sys.exit(0 if float('$anthropic' or 0) > 200 else 1)"; then echo "STOPPING LOOP: Anthropic settled total $anthropic exceeds the credit of 200" | tee -a "$SCREEN/piece_d.log"; exit 1; fi
  if [[ "$status" != "COMPLETED" && "$status" != "INCOMPLETE" ]]; then echo "STOPPING LOOP: $status" | tee -a "$SCREEN/piece_d.log"; exit 1; fi
done
echo "PIECE D LOOP DONE" | tee -a "$SCREEN/piece_d.log"
