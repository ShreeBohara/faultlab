#!/bin/bash
# Independent verifier (discovery v4 review round, 2026-09-30): run ./scripts/test.sh once, all four stages, in the real
# working tree, default ports, under the verifier network guards (Python audit hook, Node require hook) and a socket
# sampler. Copied from the native v2b verifier's suite/run_test_sh.sh with only V changed.
V=/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-discovery-v4-2026-09-30/verify
L=$V/suite
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
: > $L/guard-python.jsonl; : > $L/guard-node.jsonl
date -u +%FT%TZ > $L/times.txt
lsof -nP -iTCP:8000 -iTCP:8001 -iTCP:5173 -sTCP:LISTEN > $L/ports-before.txt 2>&1
env -u WANDB_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_API_KEY PYTHONPATH=$V/guard VERIFY_GUARD_LOG=$L/guard-python.jsonl \
  NODE_OPTIONS="--require $V/guard/node-guard.cjs" VERIFY_NODE_GUARD_LOG=$L/guard-node.jsonl \
  ./scripts/test.sh > $L/test-sh.log 2>&1 &
PID=$!
$V/guard/sampler.sh $PID $L/sampler.txt &
wait $PID
echo "test.sh exit=$?" >> $L/test-sh.log
date -u +%FT%TZ >> $L/times.txt
sleep 2
lsof -nP -iTCP:8000 -iTCP:8001 -iTCP:5173 -sTCP:LISTEN > $L/ports-after.txt 2>&1
wait
