#!/usr/bin/env bash
# Follow-up stage: read-only git state snapshot (GIT_OPTIONAL_LOCKS=0; never writes the index). Copied from verify/git_state.sh.
set -u
export GIT_OPTIONAL_LOCKS=0
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
date -u '+%Y-%m-%dT%H:%M:%SZ'
echo "HEAD $(git rev-parse HEAD)"
echo "branch $(git branch --show-current)"
echo "backup/part2-2026-09-22 $(git rev-parse backup/part2-2026-09-22)"
echo "main $(git rev-parse main)"
echo "index mtime $(stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' .git/index) size $(stat -f '%z' .git/index)"
echo "index sha256 $(shasum -a 256 .git/index | cut -d' ' -f1)"
echo "stash entries $(git stash list | wc -l | tr -d ' ')"
echo "all refs sha256 $(git for-each-ref --format='%(refname) %(objectname)' | shasum -a 256 | cut -d' ' -f1)"
