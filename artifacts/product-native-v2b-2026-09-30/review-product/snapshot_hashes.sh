#!/bin/bash
# Blob hashes of every tracked-or-untracked non-ignored file outside artifacts/ (skips forbidden paths), sorted.
cd "$(dirname "$0")/../../.."
{ git ls-files; git ls-files --others --exclude-standard; } | sort -u | grep -v '^artifacts/' | while read -r p; do
  case "$p" in audit/promotion.json|audit/final-audit*|backend/app/referee/checks.py|.env) continue;; esac
  [ -f "$p" ] && echo "$(git hash-object --no-filters "$p") $p"
done
