#!/bin/bash
# Unattended wrap-up of piece D (the Claude lab-loop probe: five completion studies, Sonnet Actor, Opus Mechanic), 2026-10-12.
# The phase B/C wrap-up adapted to completion-study records: waits for the loop to end, runs the deterministic after-run steps,
# copies the read-outs into the repo under artifacts/claude-lab-loop-probe-2026-10/piece-d/ through a temporary worktree on
# GitHub main, secret-scans them, commits and pushes. No model is called and nothing is judged here: the write-up happens later.
#   WAIT=0      do not wait for the loop marker (dry runs)
#   PUBLISH=0   skip the git worktree/commit/push
#   STUDIES=... space-separated study folder names to limit the per-study checks (dry runs)
set -u
SCREEN=/Users/shree/FaultLab_Runs/2026-10-12/claude-lab-loop-probe-piece-d
REPO=/Users/shree/FaultLab/faultlab
PY="$REPO/.venv/bin/python"
GITHUB=git@github.com:ShreeBohara/faultlab.git
OUT="${OUT:-$SCREEN/wrapup}"
ART_REL=artifacts/claude-lab-loop-probe-2026-10/piece-d
LOG="$SCREEN/piece_d_wrapup.log"
WAIT="${WAIT:-1}"; PUBLISH="${PUBLISH:-1}"
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=30"
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$LOG"; }
mkdir -p "$OUT"
log "wrap-up started (WAIT=$WAIT PUBLISH=$PUBLISH OUT=$OUT)"

# 1. Wait for the loop to end: its marker, or the loop process gone for more than five minutes without one.
if [[ "$WAIT" == "1" ]]; then
  missing=0
  until grep -q "PIECE D LOOP DONE\|STOPPING LOOP" "$SCREEN/piece_d.log" 2>/dev/null; do
    if pgrep -f "piece_d_loop.sh" >/dev/null; then missing=0; else missing=$((missing+1)); fi
    if (( missing >= 5 )); then log "LOOP PROCESS GONE without a marker: wrapping up what exists"; echo "LOOP_VANISHED $(date -u +%FT%TZ)" >> "$SCREEN/piece_d.log"; break; fi
    sleep 60
  done
  log "loop ended: $(grep -E 'PIECE D LOOP DONE|STOPPING LOOP|LOOP_VANISHED' "$SCREEN/piece_d.log" | tail -1)"
  sleep 20   # let the last driver settle its files
fi

# 2. Per-study after-run checks (read-only on the stores).
cd "$REPO" || exit 1
if [[ -n "${STUDIES:-}" ]]; then dirs=$STUDIES; else dirs=$(cd "$SCREEN" && ls -d d*-* 2>/dev/null); fi
echo "{" > "$OUT/clock-drift.json"; first=1
for name in $dirs; do
  d="$SCREEN/$name"
  [[ -f "$d/lab.sqlite3" ]] || { log "skip $name (no store)"; continue; }
  "$PY" scripts/experiments/check_clock_drift.py --store "$d/lab.sqlite3" --worlds --worlds-dir "$d/worlds" > "$OUT/clock-drift-$name.txt" 2>&1; rc1=$?
  "$PY" scripts/experiments/check_clock_drift_native.py --store "$d/lab.sqlite3" --worlds --worlds-dir "$d/worlds" > "$OUT/clock-drift-native-$name.txt" 2>&1; rc2=$?
  status=$("$PY" -c "import json; d=json.load(open('$d/RESULT.json')); print('error' if d.get('error') else d.get('summary',{}).get('status'))" 2>/dev/null)
  decision=$("$PY" -c "import json; d=json.load(open('$d/RESULT.json')); print((d.get('summary') or {}).get('decision'))" 2>/dev/null)
  cost=$("$PY" -c "import json; d=json.load(open('$d/RESULT.json')); print(((d.get('summary') or {}).get('usage') or {}).get('cost_dollars') or 0)" 2>/dev/null)
  [[ $first == 1 ]] || echo "," >> "$OUT/clock-drift.json"; first=0
  printf '  "%s": {"status": "%s", "decision": "%s", "measured_cost": %s, "clock_drift_exit": %s, "clock_drift_native_exit": %s, "drifted_line": "%s"}' \
    "$name" "$status" "$decision" "${cost:-0}" "$rc1" "$rc2" "$(grep -m1 '^drifted:' "$OUT/clock-drift-$name.txt" | tr -d '"')" >> "$OUT/clock-drift.json"
  log "$name status=$status decision=$decision cost=$cost drift_exit=$rc1/$rc2 $(grep -m1 '^drifted:' "$OUT/clock-drift-$name.txt")"
done
echo "" >> "$OUT/clock-drift.json"; echo "}" >> "$OUT/clock-drift.json"

# 3. Leaderboard over the stores (per-trial C1 to C8 outcomes, Wilson intervals, no ranking) and the completion read-outs.
"$PY" -m bench.harness.leaderboard "$SCREEN" --out "$OUT/leaderboard.json" --markdown "$OUT/leaderboard.md" > "$OUT/leaderboard.log" 2>&1; log "leaderboard exit=$?"
grep -v "sk-ant" "$SCREEN/piece_d.log" | grep -E "^=== study|status:|STOPPING|DONE|LOOP_VANISHED" > "$OUT/piece_d.progress.txt"
cp "$SCREEN/DECLARATION.piece-d.json" "$SCREEN/DECLARATION.piece-d.sha256" "$SCREEN/DECLARATION.piece-d.v1.json" "$SCREEN/DECLARATION.piece-d.v1.sha256" "$OUT/" 2>/dev/null
cp "$SCREEN/piece_d_loop.sh" "$SCREEN/piece_d_loop.v1.sh" "$SCREEN/piece_d_wrapup.sh" "$OUT/" 2>/dev/null
"$PY" - "$SCREEN" "$OUT" <<'PYEOF'
import json, sys, pathlib
screen, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
total = 0.0; rows = {}; readouts = {}
for d in sorted(screen.glob("d*-*")):
    r = d / "RESULT.json"
    if not r.exists(): continue
    j = json.loads(r.read_text()); s = j.get("summary") or {}
    cost = float(((s.get("usage") or {}).get("cost_dollars")) or 0); total += cost
    rows[d.name] = {"status": s.get("status"), "decision": s.get("decision"), "measured_cost": cost, "error": bool(j.get("error"))}
    rec_path = d / "completion-study.json"
    rec = json.loads(rec_path.read_text()) if rec_path.exists() else {}
    by_stage = {}
    for slot in rec.get("slots") or []:
        key = f"{slot.get('stage')}:{slot.get('arm')}:{slot.get('status')}"
        by_stage[key] = by_stage.get(key, 0) + 1
    candidates = []
    for c in rec.get("candidates") or []:
        if isinstance(c, dict):
            candidates.append({"decision": c.get("decision"), "reason": c.get("reason"),
                               "source_assessment": (c.get("source_assessment") or {}).get("decision") if isinstance(c.get("source_assessment"), dict) else None})
        else:
            candidates.append(str(c)[:200])
    va = rec.get("validation_assessment") if isinstance(rec.get("validation_assessment"), dict) else None
    readouts[d.name] = {
        "status": rec.get("status", s.get("status")), "decision": rec.get("decision", s.get("decision")),
        "reason": rec.get("reason", s.get("reason")), "stage": rec.get("stage", s.get("stage")),
        "stopped_by_rule": j.get("stopped_by_rule"), "error": j.get("error"),
        "evidence_protocol": rec.get("evidence_protocol"), "actor_context_protocol": rec.get("actor_context_protocol"),
        "manifest_hash": rec.get("manifest_hash"), "charged_model_calls": rec.get("charged_model_calls", s.get("charged_model_calls")),
        "measured_cost": cost, "slots_by_stage_arm_status": by_stage, "candidates": candidates,
        "validation_assessment": {"decision": va.get("decision"), "reason": va.get("reason")} if va else None,
        "reached_validation": any(str(k).startswith("validation:") for k in by_stage)}
(out / "LEDGER.piece-d.auto.json").write_text(json.dumps({"studies": rows, "measured_total_usd": round(total, 4),
    "note": "measured provider cost per study from RESULT.json; reserved bounds are in DECLARATION.piece-d.json"}, indent=2))
(out / "completion-readouts.json").write_text(json.dumps(readouts, indent=2))
print("measured total", round(total, 4), "over", len(rows), "studies;", sum(1 for v in readouts.values() if v["reached_validation"]), "reached validation")
PYEOF
mkdir -p "$OUT/studies"
for name in $dirs; do
  d="$SCREEN/$name"; mkdir -p "$OUT/studies/$name"
  for f in RESULT.json completion-study.json budget.json campaign.json; do [[ -f "$d/$f" ]] && cp "$d/$f" "$OUT/studies/$name/$f"; done
done

# 4. Secret scan of everything that will be committed.
if grep -rIlE --exclude=piece_d_wrapup.sh "sk-ant-|sk-[A-Za-z0-9_-]{20,}|ANTHROPIC_API_KEY=|WANDB_API_KEY=|OPENAI_API_KEY=|OPENROUTER_API_KEY=|Bearer [A-Za-z0-9]" "$OUT" > "$OUT/SECRET_SCAN_HITS.txt"; then
  log "SECRET SCAN HIT: not publishing. See $OUT/SECRET_SCAN_HITS.txt"; PUBLISH=0
else rm -f "$OUT/SECRET_SCAN_HITS.txt"; log "secret scan clean"; fi

# 5. Backup of the whole run folder.
mkdir -p /Users/shree/FaultLab_Backups/2026-10-12 && rsync -a --exclude 'lab.sqlite3-wal' --exclude 'lab.sqlite3-shm' "$SCREEN/" /Users/shree/FaultLab_Backups/2026-10-12/claude-lab-loop-probe-piece-d/ && log "backup done"

# 6. Publish through a temporary worktree on GitHub main (the local branch is never switched); nothing to publish without a study record.
if ! ls "$SCREEN"/d*-*/completion-study.json >/dev/null 2>&1; then log "NO STUDY RECORD: not publishing"; PUBLISH=0; fi
if [[ "$PUBLISH" == "1" ]]; then
  WT=/Users/shree/FaultLab/wt-piece-d-results
  git -C "$REPO" worktree remove --force "$WT" 2>/dev/null
  for attempt in 1 2 3; do
    git -C "$REPO" fetch "$GITHUB" main:refs/remotes/github/main >> "$LOG" 2>&1 || { log "fetch failed (attempt $attempt)"; sleep 60; continue; }
    git -C "$REPO" worktree add --detach "$WT" refs/remotes/github/main >> "$LOG" 2>&1 || { log "worktree add failed"; break; }
    mkdir -p "$WT/$ART_REL" && rsync -a --exclude '*.log' "$OUT/" "$WT/$ART_REL/"
    git -C "$WT" add -f "$ART_REL" && git -C "$WT" -c user.name="Claude (unattended wrap-up)" -c user.email="noreply@anthropic.com" commit -q -m "Claude lab-loop probe piece D: read-outs, leaderboard, clock-drift checks (unattended wrap-up)

Deterministic after-run outputs of the piece D loop declared in DECLARATION.piece-d.json: per-study status,
decision and measured cost, both clock-drift checks per store, the leaderboard over all stores (Wilson
intervals, no ranking), the completion read-outs extracted from each study record (decision and reason, slot
counts by stage, proposals and their source-gate decisions, the validation assessment), and the per-study
RESULT/completion-study/budget/campaign files. No findings are stated here; the write-up follows.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" >> "$LOG" 2>&1
    if git -C "$WT" push "$GITHUB" HEAD:main >> "$LOG" 2>&1; then log "PUBLISHED to GitHub main: $(git -C "$WT" rev-parse --short HEAD)"; git -C "$REPO" worktree remove --force "$WT"; break; fi
    log "push failed (attempt $attempt), retrying after a fresh fetch"; git -C "$REPO" worktree remove --force "$WT"; sleep 60
  done
fi
log "wrap-up finished"
