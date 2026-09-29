#!/usr/bin/env bash
# Explicit live-ready launch; starting the server never starts a campaign.
# Model/context defaults come from Settings.from_env, also used by the normal server.
# Explicit process settings override .env; .env overrides application defaults.
# Configure current prices and confirmation in .env or the process before a paid run.
# This launcher never marks prices verified or changes the shared spending allowance.
# Credentials remain in the existing root .env, which this script never edits.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Port: FAULTLAB_BACKEND_PORT (default 8000). FAULTLAB_SIMULATOR_PORT, when set, also selects the
# simulator this backend uses (unless FAULTLAB_SIMULATOR_URL is set). See scripts/lib/ports.sh.
source "$ROOT/scripts/lib/ports.sh"
listen_port="$(faultlab_port FAULTLAB_BACKEND_PORT 8000)"
faultlab_export_simulator_url
export FAULTLAB_LIVE_ENABLED="${FAULTLAB_LIVE_ENABLED:-true}"
if [[ -z "${FAULTLAB_CONFIRMED_ENTITY:-}" ]]; then
  FAULTLAB_CONFIRMED_ENTITY="${WANDB_ENTITY:-}"
  if [[ -z "$FAULTLAB_CONFIRMED_ENTITY" && -f "$ROOT/.env" ]]; then
    FAULTLAB_CONFIRMED_ENTITY="$("$ROOT/.venv/bin/python" -c 'from dotenv import dotenv_values; import sys; print((dotenv_values(sys.argv[1],interpolate=False).get("WANDB_ENTITY") or "").strip())' "$ROOT/.env")"
  fi
fi
export FAULTLAB_CONFIRMED_ENTITY
# Live campaigns use frozen code/configuration and must not be interrupted by a
# development file watcher. Stop and restart deliberately after making changes.
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$listen_port"
