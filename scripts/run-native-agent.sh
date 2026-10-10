#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  printf 'Install the backend first: %s/scripts/setup.sh --backend-only\n' "$ROOT" >&2
  exit 2
fi
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
export PYTHON_DOTENV_DISABLED=1
exec "$ROOT/.venv/bin/python" -m app.cli.native_agent "$@"
