#!/bin/bash
# Phase B loop: nine rounds of four studies, round-robin; stops on a driver error or an unexpected status.
set -u
cd /Users/shree/FaultLab/faultlab
SCREEN=/Users/shree/FaultLab_Runs/2026-10-11/claude-actor-screen
SHA=e56521f9fc4c6bc64979410f77faf7ecc4f4b0b6582f08843d28395689af6286
for round in 1 2 3 4 5 6 7 8 9; do
  for spec in "deepseek-ai/DeepSeek-V3.1:60:deepseek-v3.1-control" "anthropic:claude-haiku-5-5:60:claude-haiku-5-5" "anthropic:claude-sonnet-5-5:120:claude-sonnet-5-5" "anthropic:claude-opus-5-5:250:claude-opus-5-5"; do
    model="${spec%%:*}"; rest="${spec#*:}"
    if [[ "$model" == "anthropic" ]]; then model="anthropic:${rest%%:*}"; rest="${rest#*:}"; fi
    cap="${rest%%:*}"; name="${rest#*:}"
    dir="$SCREEN/b$round-$name"
    echo "=== round $round $model cap $cap -> $dir" | tee -a "$SCREEN/phase_b.log"
    ./.venv/bin/python scripts/experiments/baseline_screen.py --model "$model" --data-dir "$dir" --declaration "$SCREEN/DECLARATION.phase-b.json" --declaration-sha256 "$SHA" --dollar-cap "$cap" --monthly-cap 400 --settle-seconds 30 >> "$SCREEN/phase_b.log" 2>&1
    status=$(python3 -c "import json,sys; d=json.load(open('$dir/RESULT.json')); print('error' if d.get('error') else d.get('summary',{}).get('status'))" 2>/dev/null)
    cost=$(python3 -c "import json; d=json.load(open('$dir/RESULT.json')); print(((d.get('summary') or {}).get('usage') or {}).get('cost_dollars') or 0)" 2>/dev/null)
    case "$name" in deepseek-v3.1-control) limit=0.65;; claude-haiku-5-5) limit=0.21;; claude-sonnet-5-5) limit=3.6;; claude-opus-5-5) limit=6.4;; esac
    echo "    status: $status measured_cost: $cost (runaway limit $limit)" | tee -a "$SCREEN/phase_b.log"
    if python3 -c "import sys; sys.exit(0 if float('$cost' or 0) > float('$limit') else 1)"; then echo "STOPPING LOOP: measured cost $cost exceeds 4x phase-A cost" | tee -a "$SCREEN/phase_b.log"; exit 1; fi
    if [[ "$status" != "COMPLETED" && "$status" != "INCOMPLETE" ]]; then echo "STOPPING LOOP: $status" | tee -a "$SCREEN/phase_b.log"; exit 1; fi
  done
done
echo "PHASE B LOOP DONE" | tee -a "$SCREEN/phase_b.log"
