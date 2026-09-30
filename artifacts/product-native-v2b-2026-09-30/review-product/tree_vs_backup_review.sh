#!/bin/bash
# Reviewer copy: compare working tree with backup/part2-2026-09-22 by blob hash (read-only plumbing).
# Skips forbidden paths. Also lists files present in the working tree (non-ignored) that are not in the backup tree.
cd "$(dirname "$0")/../../.."
BR=backup/part2-2026-09-22
echo "backup tip: $(git rev-parse $BR)"
git ls-tree -r $BR | while read -r mode type blob path; do
  case "$path" in
    audit/promotion.json|audit/final-audit*|artifacts/heldout2/*|backend/app/referee/checks.py) continue;;
  esac
  if [ ! -e "$path" ]; then echo "MISSING $path"; continue; fi
  now=$(git hash-object --no-filters "$path")
  [ "$now" != "$blob" ] && echo "CHANGED $path"
done
# new files not in backup (excluding artifacts/ and ignored files)
{ git ls-files; git ls-files --others --exclude-standard; } | sort -u | grep -v '^artifacts/' > "$PWD/artifacts/product-native-v2b-2026-09-30/review-product/.wt_paths.txt"
git ls-tree -r --name-only $BR | sort -u > "$PWD/artifacts/product-native-v2b-2026-09-30/review-product/.bk_paths.txt"
comm -23 "$PWD/artifacts/product-native-v2b-2026-09-30/review-product/.wt_paths.txt" "$PWD/artifacts/product-native-v2b-2026-09-30/review-product/.bk_paths.txt" | while read -r p; do [ -e "$p" ] && echo "NEW $p"; done
exit 0
