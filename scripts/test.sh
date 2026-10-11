#!/usr/bin/env bash
# Offline checks, no provider calls: backend tests, frontend unit tests, production build and browser tests.
# Every stage runs even when an earlier one fails; a summary lists each stage's result, and the exit
# status is non-zero if any stage failed. Name stages to run a subset, e.g. ./scripts/test.sh backend
# (CI runs the backend and the three frontend stages as separate jobs).
# The browser stage starts its own dashboard on FAULTLAB_DASHBOARD_PORT (default 5173).
# Ctrl+C stops the whole run at once (exit 130); later stages do not start.
set -uo pipefail
trap 'printf "\nInterrupted; later stages not run.\n" >&2; exit 130' INT
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ALL_STAGES="backend frontend build browser"

# Not in ALL_STAGES: the research experiment tests (tests/experiments) run only when named.
OPTIONAL_STAGES="experiments"
run_backend() { cd "$ROOT/backend" && "$ROOT/.venv/bin/python" -m pytest; }
run_experiments() { cd "$ROOT/backend" && "$ROOT/.venv/bin/python" -m pytest -m experiment tests/experiments; }
run_frontend() { cd "$ROOT/frontend" && npm test; }
run_build() { cd "$ROOT/frontend" && npm run build; }
run_browser() { cd "$ROOT/frontend" && npm run test:browser; }

stages=("$@")
if [[ ${#stages[@]} -eq 0 ]]; then
  # shellcheck disable=SC2206
  stages=($ALL_STAGES)
fi
for stage in "${stages[@]}"; do
  case " $ALL_STAGES $OPTIONAL_STAGES " in
    *" $stage "*) ;;
    *) printf 'Unknown stage %s. Stages: %s (optional: %s)\n' "$stage" "$ALL_STAGES" "$OPTIONAL_STAGES" >&2; exit 2 ;;
  esac
done

summary=()
failed=0
for stage in "${stages[@]}"; do
  printf '\n==> %s\n' "$stage"
  started=$SECONDS
  # A subshell keeps each stage's directory change to itself.
  if ( "run_$stage" ); then
    summary+=("PASSED  $stage ($((SECONDS - started)) s)")
  else
    code=$?
    summary+=("FAILED  $stage (exit $code, $((SECONDS - started)) s)")
    failed=1
  fi
done

printf '\nOffline check summary:\n'
for line in "${summary[@]}"; do
  printf '  %s\n' "$line"
done
if [[ $failed -ne 0 ]]; then
  printf 'At least one stage failed; see its output above.\n'
fi
exit "$failed"
