#!/usr/bin/env bash
# Verifier: git blob hash of named working files vs backup/part2-2026-09-22 (read-only; GIT_OPTIONAL_LOCKS=0).
# checks.py is NOT in this list (compared only through gate_freeze).
export GIT_OPTIONAL_LOCKS=0
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
for f in backend/app/lab/challenge.py backend/app/lab/promotion.py backend/app/lab/evaluation.py backend/app/lab/diagnosis.py \
         backend/app/lab/reproduction.py backend/app/lab/reachability.py backend/app/lab/loop_limits.py backend/app/lab/policies.py \
         backend/app/agents/mechanic.py backend/app/agents/explorer.py backend/app/agents/actor.py backend/app/agents/prompts/actor.md \
         backend/app/agents/prompts/mechanic.md backend/app/agents/prompts/explorer.md \
         backend/app/integrations/external_agent.py backend/app/integrations/external_agent_v2.py backend/app/integrations/registry.py \
         backend/app/lab/discovery_protocol.py backend/app/contracts/tokens.py backend/app/lab/policy_interpreter.py \
         backend/tests/integrations/test_native_adapter_v1_golden.py; do
  b=$(git rev-parse "backup/part2-2026-09-22:$f" 2>/dev/null || echo ABSENT)
  w=$(git hash-object --no-filters "$f" 2>/dev/null || echo ABSENT)
  [ "$b" = "$w" ] && echo "IDENTICAL $b $f" || echo "DIFFERENT backup=$b work=$w $f"
done
for d in backend/app/referee backend/app/simulator contracts backend/app/contracts; do
  n=0; diff=0
  while read -r mode type blob path; do
    [ "$path" = "backend/app/referee/checks.py" ] && continue
    n=$((n+1)); w=$(git hash-object --no-filters "$path" 2>/dev/null || echo ABSENT); [ "$w" = "$blob" ] || { diff=$((diff+1)); echo "  DIFF $path"; }
  done < <(git ls-tree -r backup/part2-2026-09-22 -- "$d" | tr '\t' ' ')
  # files in the working folder (not ignored) that are absent from the backup tree (main's index is not the base)
  extra=$(comm -23 <(git ls-files --cached --others --exclude-standard -- "$d" | while read -r p; do [ -f "$p" ] && echo "$p"; done | sort) \
                   <(git ls-tree -r --name-only backup/part2-2026-09-22 -- "$d" | sort) | wc -l | tr -d ' ')
  echo "DIR $d: $n backup files compared (checks.py excluded), $diff differ, $extra working files absent from the backup"
done
