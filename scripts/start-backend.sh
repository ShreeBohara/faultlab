#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Port: FAULTLAB_BACKEND_PORT (default 8000). FAULTLAB_SIMULATOR_PORT, when set, also selects the
# simulator this backend uses (unless FAULTLAB_SIMULATOR_URL is set). See scripts/lib/ports.sh.
source "$ROOT/scripts/lib/ports.sh"
listen_port="$(faultlab_port FAULTLAB_BACKEND_PORT 8000)"
faultlab_export_simulator_url
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$listen_port" --reload
