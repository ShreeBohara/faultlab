#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
"$ROOT/.venv/bin/python" -m pytest
cd "$ROOT/frontend"
npm run build
