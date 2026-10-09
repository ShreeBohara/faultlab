#!/bin/bash
# Phase 22 (PHASE22_EXPERIMENT.md section 7.4 S2 and S5, section 8 F6 and F11): commit files to the
# LOCAL backup branch without touching main, HEAD, the working tree or the real index.
#
#   Never `git commit` on main. Never check out the backup branch (the working tree holds
#   uncommitted Part 2 work). This script writes through a temporary index and moves the branch
#   with update-ref's old-value guard, so a concurrent change to the branch makes it fail, not race.
#
# Usage (from the repository root; paths are repository-relative files):
#   artifacts/phase22-2026-09-24/prep/commit_to_backup.sh "<commit message>" <path> [<path> ...]
# It prints the old and new branch commits and the new commit's file list. Nothing is pushed.
set -euo pipefail
BRANCH=refs/heads/backup/part2-2026-09-22
if [ $# -lt 2 ]; then
  echo 'usage: commit_to_backup.sh "<message>" <repository-relative file> [...]' >&2
  exit 2
fi
MESSAGE=$1; shift
cd "$(git rev-parse --show-toplevel)"
HEAD_BEFORE=$(git symbolic-ref -q HEAD || git rev-parse HEAD)
INDEX_BEFORE=$(git ls-files -s | git hash-object --stdin)
OLD=$(git rev-parse --verify "$BRANCH^{commit}")
TMP=$(mktemp -d "${TMPDIR:-/tmp}/faultlab-backup-index.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
export GIT_INDEX_FILE="$TMP/index"
git read-tree "$OLD"
for path in "$@"; do
  case "$path" in
    /*|../*|*/../*|./*) echo "not a plain repository-relative path: $path" >&2; exit 2 ;;
  esac
  if [ ! -f "$path" ] || [ -L "$path" ]; then echo "not a regular file: $path" >&2; exit 2; fi
  blob=$(git hash-object -w -- "$path")
  mode=100644; if [ -x "$path" ]; then mode=100755; fi
  git update-index --add --cacheinfo "$mode,$blob,$path"
done
TREE=$(git write-tree)
NEW=$(git commit-tree "$TREE" -p "$OLD" -m "$MESSAGE")
unset GIT_INDEX_FILE
git update-ref -m "phase22 backup commit" "$BRANCH" "$NEW" "$OLD"
if [ "$(git symbolic-ref -q HEAD || git rev-parse HEAD)" != "$HEAD_BEFORE" ]; then echo 'HEAD moved' >&2; exit 1; fi
if [ "$(git ls-files -s | git hash-object --stdin)" != "$INDEX_BEFORE" ]; then echo 'the real index changed' >&2; exit 1; fi
echo "backup branch ${BRANCH#refs/heads/}: $OLD -> $NEW (HEAD and the real index unchanged)"
git show --stat --format='commit %H%nauthor-date %ad%n%n    %s%n' "$NEW"
