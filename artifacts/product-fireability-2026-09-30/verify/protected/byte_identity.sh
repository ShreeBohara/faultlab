#!/usr/bin/env bash
# Verifier (fireability round): git blob hash of named working files vs backup/part2-2026-09-22 (read-only; GIT_OPTIONAL_LOCKS=0).
# checks.py is NOT in this list (compared only through gate_freeze). Copied from the citation-status verifier, list extended.
export GIT_OPTIONAL_LOCKS=0
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
for f in backend/app/lab/challenge.py backend/app/lab/promotion.py backend/app/lab/evaluation.py backend/app/lab/diagnosis.py \
         backend/app/lab/reproduction.py backend/app/lab/reachability.py backend/app/lab/loop_limits.py backend/app/lab/policies.py \
         backend/app/lab/completion_study.py backend/app/lab/baseline_study.py backend/app/lab/history_replay.py backend/app/lab/storage.py \
         backend/app/lab/runner.py backend/app/lab/evidence.py backend/app/lab/citation_status.py backend/app/lab/configuration.py \
         backend/app/agents/mechanic.py backend/app/agents/explorer.py backend/app/agents/actor.py backend/app/agents/reference.py \
         backend/app/agents/transport_retry.py backend/app/agents/progress.py backend/app/agents/__init__.py \
         backend/app/agents/prompts/actor.md backend/app/agents/prompts/challenger.md backend/app/agents/prompts/challenger_candidate_reach_v2.md \
         backend/app/agents/prompts/completion.md backend/app/agents/prompts/diagnosis.md backend/app/agents/prompts/explorer.md \
         backend/app/agents/prompts/explorer_discovery_v2.md backend/app/agents/prompts/explorer_discovery_v3_history.md \
         backend/app/agents/prompts/explorer_discovery_v4_history_replay.md backend/app/agents/prompts/mechanic.md \
         backend/app/integrations/external_agent.py backend/app/integrations/external_agent_v2.py backend/app/integrations/registry.py \
         backend/app/lab/discovery_protocol.py backend/app/contracts/tokens.py backend/app/lab/policy_interpreter.py \
         backend/tests/integrations/test_native_adapter_v1_golden.py scripts/test.sh scripts/experiments/gate_freeze.py; do
  b=$(git rev-parse "backup/part2-2026-09-22:$f" 2>/dev/null || echo ABSENT)
  w=$(git hash-object --no-filters "$f" 2>/dev/null || echo ABSENT)
  [ "$b" = "$w" ] && echo "IDENTICAL $b $f" || echo "DIFFERENT backup=$b work=$w $f"
done
for d in backend/app/referee backend/app/simulator contracts backend/app/contracts backend/app/integrations backend/app/telemetry; do
  n=0; diff=0
  while read -r mode type blob path; do
    [ "$path" = "backend/app/referee/checks.py" ] && continue
    n=$((n+1)); w=$(git hash-object --no-filters "$path" 2>/dev/null || echo ABSENT); [ "$w" = "$blob" ] || { diff=$((diff+1)); echo "  DIFF $path"; }
  done < <(git ls-tree -r backup/part2-2026-09-22 -- "$d" | tr '\t' ' ')
  extra=$(comm -23 <(git ls-files --cached --others --exclude-standard -- "$d" | while read -r p; do [ -f "$p" ] && echo "$p"; done | sort) \
                   <(git ls-tree -r --name-only backup/part2-2026-09-22 -- "$d" | sort) | wc -l | tr -d ' ')
  echo "DIR $d: $n backup files compared (checks.py excluded), $diff differ, $extra working files absent from the backup"
done
