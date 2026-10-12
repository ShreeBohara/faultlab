#!/bin/bash
# Phase C loop: nine rounds of two studies (DeepSeek V3.1 control, Claude Fable 5.1), round-robin; stops on a driver error or an unexpected status.
set -u
cd /Users/shree/FaultLab/faultlab
SCREEN=/Users/shree/FaultLab_Runs/2026-10-12/claude-actor-screen-phase-c
SHA=0e8227d4ed71959fef7b8058ad44b8463149c452aa6dfc1dabbaaacafe1c67b4
for round in 1 2 3 4 5 6 7 8 9; do
  for spec in "deepseek-ai/DeepSeek-V3.1:60:deepseek-v3.1-control" "anthropic:claude-fable-5-1:500:claude-fable-5-1"; do
    model="${spec%%:*}"; rest="${spec#*:}"
    if [[ "$model" == "anthropic" ]]; then model="anthropic:${rest%%:*}"; rest="${rest#*:}"; fi
    cap="${rest%%:*}"; name="${rest#*:}"
    dir="$SCREEN/c$round-$name"
    echo "=== round $round $model cap $cap -> $dir" | tee -a "$SCREEN/phase_c.log"
    ./.venv/bin/python scripts/experiments/baseline_screen.py --model "$model" --data-dir "$dir" --declaration "$SCREEN/DECLARATION.phase-c.json" --declaration-sha256 "$SHA" --dollar-cap "$cap" --monthly-cap 400 --settle-seconds 30 >> "$SCREEN/phase_c.log" 2>&1
    status=$(python3 -c "import json,sys; d=json.load(open('$dir/RESULT.json')); print('error' if d.get('error') else d.get('summary',{}).get('status'))" 2>/dev/null)
    cost=$(python3 -c "import json; d=json.load(open('$dir/RESULT.json')); print(((d.get('summary') or {}).get('usage') or {}).get('cost_dollars') or 0)" 2>/dev/null)
    case "$name" in deepseek-v3.1-control) limit=0.65;; claude-fable-5-1) limit=16.0;; esac
    echo "    status: $status measured_cost: $cost (runaway limit $limit)" | tee -a "$SCREEN/phase_c.log"
    if python3 -c "import sys; sys.exit(0 if float('$cost' or 0) > float('$limit') else 1)"; then echo "STOPPING LOOP: measured cost $cost exceeds the runaway limit $limit" | tee -a "$SCREEN/phase_c.log"; exit 1; fi
    if [[ "$status" != "COMPLETED" && "$status" != "INCOMPLETE" ]]; then echo "STOPPING LOOP: $status" | tee -a "$SCREEN/phase_c.log"; exit 1; fi
  done
done
echo "PHASE C LOOP DONE" | tee -a "$SCREEN/phase_c.log"
