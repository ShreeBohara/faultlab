#!/usr/bin/env bash
# Verifier (diagnosis-rules round): git blob hash of named working files vs backup/part2-2026-09-22 (626bae4)
# (read-only; GIT_OPTIONAL_LOCKS=0). checks.py is NOT hashed here (compared only through gate_freeze).
# Adapted from the fireability verifier's byte_identity.sh; list extended for this round's protected set.
export GIT_OPTIONAL_LOCKS=0
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
REF=backup/part2-2026-09-22
echo "REF $REF = $(git rev-parse $REF)"
for f in backend/app/referee/__init__.py backend/app/referee/diagnostics.py backend/app/referee/reducer.py \
         backend/app/referee/freeze.py backend/app/referee/manifests.py backend/app/referee/observer.py \
         backend/app/lab/diagnosis.py backend/app/agents/prompts/diagnosis.md backend/app/contracts/models.py \
         backend/app/lab/challenge.py backend/app/lab/promotion.py backend/app/lab/evaluation.py \
         backend/app/lab/completion_study.py backend/app/lab/reproduction.py backend/app/lab/reachability.py \
         backend/app/lab/citation_status.py backend/app/lab/loop_limits.py backend/app/lab/evidence_wait.py \
         backend/app/lab/fireability.py backend/app/lab/policies.py backend/app/lab/policy_interpreter.py \
         backend/app/lab/configuration.py backend/app/lab/storage.py backend/app/lab/runner.py backend/app/lab/evidence.py \
         backend/app/lab/discovery_protocol.py backend/app/lab/coordinator.py backend/app/lab/api.py \
         backend/app/agents/actor.py backend/app/agents/reference.py backend/app/agents/explorer.py \
         backend/app/agents/transport_retry.py backend/app/agents/prompts/actor.md backend/app/agents/prompts/mechanic.md \
         backend/app/integrations/external_agent.py backend/app/integrations/external_agent_v2.py backend/app/integrations/registry.py \
         backend/app/providers/runtime.py backend/app/contracts/tokens.py \
         backend/tests/integrations/test_native_adapter_v1_golden.py scripts/test.sh scripts/experiments/gate_freeze.py \
         backend/tests/lab/test_history_fireability.py \
         backend/app/agents/mechanic.py backend/app/lab/learning.py backend/app/lab/run_plans.py backend/app/lab/exports.py; do
  b=$(git rev-parse "$REF:$f" 2>/dev/null || echo ABSENT)
  w=$(git hash-object --no-filters "$f" 2>/dev/null || echo ABSENT)
  [ "$b" = "$w" ] && echo "IDENTICAL $b $f" || echo "DIFFERENT backup=$b work=$w $f"
done
for d in backend/app/referee backend/app/simulator contracts backend/app/contracts backend/app/integrations backend/app/telemetry \
         backend/app/agents/prompts backend/app/providers; do
  n=0; diff=0
  while read -r mode type blob path; do
    [ "$path" = "backend/app/referee/checks.py" ] && continue
    n=$((n+1)); w=$(git hash-object --no-filters "$path" 2>/dev/null || echo ABSENT); [ "$w" = "$blob" ] || { diff=$((diff+1)); echo "  DIFF $path"; }
  done < <(git ls-tree -r $REF -- "$d" | tr '\t' ' ')
  extra=$(comm -23 <(git ls-files --cached --others --exclude-standard -- "$d" | while read -r p; do [ -f "$p" ] && echo "$p"; done | sort) \
                   <(git ls-tree -r --name-only $REF -- "$d" | sort) | wc -l | tr -d ' ')
  echo "DIR $d: $n backup files compared (checks.py excluded), $diff differ, $extra working files absent from the backup"
done
