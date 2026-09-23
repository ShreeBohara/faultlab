#!/usr/bin/env bash
# Explicit live comparison or read-only --status; no startup-side model calls.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m app.cli.client context-study "$@"
