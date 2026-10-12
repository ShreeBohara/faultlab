#!/bin/bash
# Unattended wrap-up of the Phase B screen (written 2026-10-11 before this Claude session moved to the cloud).
# Waits for the loop to end, runs the deterministic after-run steps, copies the read-outs into the repo under
# artifacts/claude-actor-screen-2026-10-11/phase-b/ through a temporary worktree on GitHub main, secret-scans them,
# commits and pushes. No model is called and nothing is judged here: the findings write-up happens later.
#   WAIT=0      do not wait for the loop marker (dry runs)
#   PUBLISH=0   skip the git worktree/commit/push
#   STUDIES=... space-separated study folder names to limit the per-study checks (dry runs)
set -u
SCREEN=/Users/shree/FaultLab_Runs/2026-10-11/claude-actor-screen
REPO=/Users/shree/FaultLab/faultlab
PY="$REPO/.venv/bin/python"
GITHUB=git@github.com:ShreeBohara/faultlab.git
OUT="${OUT:-$SCREEN/wrapup}"
ART_REL=artifacts/claude-actor-screen-2026-10-11/phase-b
LOG="$SCREEN/phase_b_wrapup.log"
WAIT="${WAIT:-1}"; PUBLISH="${PUBLISH:-1}"
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=30"
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$LOG"; }
mkdir -p "$OUT"
log "wrap-up started (WAIT=$WAIT PUBLISH=$PUBLISH OUT=$OUT)"

# 1. Wait for the loop to end: its marker, or the loop process gone for more than five minutes without one.
if [[ "$WAIT" == "1" ]]; then
  missing=0
  until grep -q "PHASE B LOOP DONE\|STOPPING LOOP" "$SCREEN/phase_b.log"; do
    if pgrep -f "phase_b_loop.sh" >/dev/null; then missing=0; else missing=$((missing+1)); fi
    if (( missing >= 5 )); then log "LOOP PROCESS GONE without a marker: wrapping up what exists"; echo "LOOP_VANISHED $(date -u +%FT%TZ)" >> "$SCREEN/phase_b.log"; break; fi
    sleep 60
  done
  log "loop ended: $(grep -E 'PHASE B LOOP DONE|STOPPING LOOP|LOOP_VANISHED' "$SCREEN/phase_b.log" | tail -1)"
  sleep 20   # let the last driver settle its files
fi

# 2. Per-study after-run checks (read-only on the stores).
cd "$REPO" || exit 1
if [[ -n "${STUDIES:-}" ]]; then dirs=$STUDIES; else dirs=$(cd "$SCREEN" && ls -d b*-* 2>/dev/null); fi
echo "{" > "$OUT/clock-drift.json"; first=1
for name in $dirs; do
  d="$SCREEN/$name"
  [[ -f "$d/lab.sqlite3" ]] || { log "skip $name (no store)"; continue; }
  "$PY" scripts/experiments/check_clock_drift.py --store "$d/lab.sqlite3" --worlds --worlds-dir "$d/worlds" > "$OUT/clock-drift-$name.txt" 2>&1; rc1=$?
  "$PY" scripts/experiments/check_clock_drift_native.py --store "$d/lab.sqlite3" --worlds --worlds-dir "$d/worlds" > "$OUT/clock-drift-native-$name.txt" 2>&1; rc2=$?
  status=$("$PY" -c "import json; d=json.load(open('$d/RESULT.json')); print('error' if d.get('error') else d.get('summary',{}).get('status'))" 2>/dev/null)
  cost=$("$PY" -c "import json; d=json.load(open('$d/RESULT.json')); print(((d.get('summary') or {}).get('usage') or {}).get('cost_dollars') or 0)" 2>/dev/null)
  [[ $first == 1 ]] || echo "," >> "$OUT/clock-drift.json"; first=0
  printf '  "%s": {"status": "%s", "measured_cost": %s, "clock_drift_exit": %s, "clock_drift_native_exit": %s, "drifted_line": "%s"}' \
    "$name" "$status" "${cost:-0}" "$rc1" "$rc2" "$(grep -m1 '^drifted:' "$OUT/clock-drift-$name.txt" | tr -d '"')" >> "$OUT/clock-drift.json"
  log "$name status=$status cost=$cost drift_exit=$rc1/$rc2 $(grep -m1 '^drifted:' "$OUT/clock-drift-$name.txt")"
done
echo "" >> "$OUT/clock-drift.json"; echo "}" >> "$OUT/clock-drift.json"

# 3. Leaderboard and reports over the whole screen directory (phase A folders included).
"$PY" -m bench.harness.leaderboard "$SCREEN" --out "$OUT/leaderboard.json" --markdown "$OUT/leaderboard.md" > "$OUT/leaderboard.log" 2>&1; log "leaderboard exit=$?"
"$PY" scripts/experiments/baseline_screen_report.py "$SCREEN" --json "$OUT/report.json" > "$OUT/report.txt" 2>&1; log "report exit=$?"
"$PY" scripts/experiments/baseline_screen_report.py "$SCREEN" --pooled --json "$OUT/pooled.json" > "$OUT/pooled.txt" 2>&1; log "pooled report exit=$?"
grep -v "sk-ant" "$SCREEN/phase_b.log" | grep -E "^=== round|status:|STOPPING|DONE|LOOP_VANISHED" > "$OUT/phase_b.progress.txt"
cp "$SCREEN/DECLARATION.phase-b.json" "$SCREEN/DECLARATION.phase-b.sha256" "$OUT/" 2>/dev/null
cp "$SCREEN/phase_b_loop.sh" "$SCREEN/phase_b_wrapup.sh" "$OUT/" 2>/dev/null
"$PY" - "$SCREEN" "$OUT" <<'PYEOF'
import json, sys, pathlib
screen, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
total = 0.0; rows = {}
for d in sorted(screen.glob("b*-*")):
    r = d / "RESULT.json"
    if not r.exists(): continue
    j = json.loads(r.read_text()); s = j.get("summary") or {}
    cost = float(((s.get("usage") or {}).get("cost_dollars")) or 0); total += cost
    rows[d.name] = {"status": s.get("status"), "measured_cost": cost, "error": bool(j.get("error"))}
(out / "LEDGER.phase-b.auto.json").write_text(json.dumps({"studies": rows, "measured_total_usd": round(total, 4),
    "note": "measured provider cost per study from RESULT.json; reserved bounds are in DECLARATION.phase-b.json"}, indent=2))
print("measured total", round(total, 4), "over", len(rows), "studies")
PYEOF
mkdir -p "$OUT/studies"
for name in $dirs; do
  d="$SCREEN/$name"; mkdir -p "$OUT/studies/$name"
  for f in RESULT.json baseline-study.json budget.json; do [[ -f "$d/$f" ]] && cp "$d/$f" "$OUT/studies/$name/$f"; done
done

# 4. Secret scan of everything that will be committed.
if grep -rIlE --exclude=phase_b_wrapup.sh "sk-ant-|sk-[A-Za-z0-9_-]{20,}|ANTHROPIC_API_KEY=|WANDB_API_KEY=|OPENAI_API_KEY=|OPENROUTER_API_KEY=|Bearer [A-Za-z0-9]" "$OUT" > "$OUT/SECRET_SCAN_HITS.txt"; then
  log "SECRET SCAN HIT: not publishing. See $OUT/SECRET_SCAN_HITS.txt"; PUBLISH=0
else rm -f "$OUT/SECRET_SCAN_HITS.txt"; log "secret scan clean"; fi

# 5. Backup of the whole run folder.
mkdir -p /Users/shree/FaultLab_Backups/2026-10-11 && rsync -a --exclude 'lab.sqlite3-wal' --exclude 'lab.sqlite3-shm' "$SCREEN/" /Users/shree/FaultLab_Backups/2026-10-11/claude-actor-screen-phase-b/ && log "backup done"

# 6. Publish through a temporary worktree on GitHub main (the local branch is never switched).
if [[ "$PUBLISH" == "1" ]]; then
  WT=/Users/shree/FaultLab/wt-phase-b-results
  git -C "$REPO" worktree remove --force "$WT" 2>/dev/null
  for attempt in 1 2 3; do
    git -C "$REPO" fetch "$GITHUB" main:refs/remotes/github/main >> "$LOG" 2>&1 || { log "fetch failed (attempt $attempt)"; sleep 60; continue; }
    git -C "$REPO" worktree add --detach "$WT" refs/remotes/github/main >> "$LOG" 2>&1 || { log "worktree add failed"; break; }
    mkdir -p "$WT/$ART_REL" && rsync -a --exclude '*.log' "$OUT/" "$WT/$ART_REL/"
    git -C "$WT" add "$ART_REL" && git -C "$WT" -c user.name="Claude (unattended wrap-up)" -c user.email="noreply@anthropic.com" commit -q -m "Claude Actor screen phase B: read-outs, leaderboard, clock-drift checks (unattended wrap-up)

Deterministic after-run outputs of the phase B loop declared in DECLARATION.phase-b.json: per-study status
and measured cost, both clock-drift checks per store, the leaderboard over all studies (Wilson intervals,
no ranking), the per-run and pooled reports (two-sided Fisher against the pooled control), and the
per-study RESULT/baseline-study/budget files. No findings are stated here; the write-up follows.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" >> "$LOG" 2>&1
    if git -C "$WT" push "$GITHUB" HEAD:main >> "$LOG" 2>&1; then log "PUBLISHED to GitHub main: $(git -C "$WT" rev-parse --short HEAD)"; git -C "$REPO" worktree remove --force "$WT"; break; fi
    log "push failed (attempt $attempt), retrying after a fresh fetch"; git -C "$REPO" worktree remove --force "$WT"; sleep 60
  done
fi
log "wrap-up finished"
