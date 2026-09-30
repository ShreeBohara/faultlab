#!/bin/bash
# Compare tracked files of backup/part2-2026-09-22 with the working tree by blob hash (read-only git plumbing).
# Skips paths this round must not read: audit/promotion.json, audit/final-audit*.json, artifacts/heldout2/,
# and backend/app/referee/checks.py (the referee is compared via the product's own gate-freeze code instead).
cd "$(dirname "$0")/../../.."
git ls-tree -r backup/part2-2026-09-22 | while read -r mode type blob path; do
  case "$path" in
    audit/promotion.json|audit/final-audit*|artifacts/heldout2/*|backend/app/referee/checks.py) echo "SKIPPED $path"; continue;;
  esac
  if [ ! -e "$path" ]; then echo "MISSING $path"; continue; fi
  now=$(git hash-object --no-filters "$path")
  [ "$now" != "$blob" ] && echo "CHANGED $path"
done
exit 0
