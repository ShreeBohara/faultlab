#!/usr/bin/env bash
# Verifier: run scripts/test.sh once ($0, offline) and sample the suite's process tree for any
# non-loopback network connection once per second (lsof). Writes full-test-sh.log, net-monitor.log.
set -u
V=/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-loop-limits-2026-09-30/verify
ROOT=/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$V/full-test-sh.start"
"$ROOT/scripts/test.sh" > "$V/full-test-sh.log" 2>&1 &
SUITE=$!
: > "$V/net-monitor.log"
samples=0
descendants() { local p=$1; echo "$p"; for c in $(pgrep -P "$p" 2>/dev/null); do descendants "$c"; done; }
while kill -0 "$SUITE" 2>/dev/null; do
  pids=$(descendants "$SUITE" | paste -sd, -)
  if [ -n "$pids" ]; then
    lsof -nP -a -i -p "$pids" 2>/dev/null | awk 'NR>1' | grep -vE '127\.0\.0\.1|\[::1\]|localhost|\*:[0-9]+ \(LISTEN\)|->127\.|::1' >> "$V/net-monitor.log"
    samples=$((samples+1))
  fi
  sleep 1
done
wait "$SUITE"; code=$?
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$V/full-test-sh.end"
echo "exit $code" >> "$V/full-test-sh.end"
echo "samples $samples; non-loopback lines $(wc -l < "$V/net-monitor.log" | tr -d ' ')" >> "$V/full-test-sh.end"
