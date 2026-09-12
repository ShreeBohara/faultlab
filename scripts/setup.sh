#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  "${FAULTLAB_PYTHON:-python3.12}" -m venv .venv
fi
.venv/bin/python -c 'import sys; sys.exit("FaultLab requires Python 3.12; recreate .venv with python3.12.") if sys.version_info[:2] != (3, 12) else None'
if [[ ! -e .env ]]; then
  (umask 077; cp .env.example .env)
fi
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r backend/requirements.lock
npm --prefix frontend ci --cache "$ROOT/frontend/.npm-cache"
printf '%s\n' 'Setup complete. See README.md for local start commands.'
