#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.simulator.main:app --host 127.0.0.1 --port 8001
