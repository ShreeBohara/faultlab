#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" check_provider.py "$@"
