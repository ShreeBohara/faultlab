#!/usr/bin/env bash
set -euo pipefail
backend_only=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-only) backend_only=true ;;
    -h|--help)
      printf '%s\n' 'Usage: ./scripts/setup.sh [--backend-only]' \
        '  --backend-only  Install locked Python dependencies without Node or .env creation.' \
        'Dependency installation requires access to the configured package indexes.'
      exit 0
      ;;
    *) printf 'Unknown setup option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  "${FAULTLAB_PYTHON:-python3.12}" -m venv .venv
fi
.venv/bin/python -c 'import sys; sys.exit("FaultLab requires Python 3.12; recreate .venv with python3.12.") if sys.version_info[:2] != (3, 12) else None'
if [[ "$backend_only" == false && ! -e .env ]]; then
  (umask 077; cp .env.example .env)
fi
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r backend/requirements.lock
if [[ "$backend_only" == true ]]; then
  printf '%s\n' 'Backend setup complete. See docs/offline-regression.md for the offline example.'
else
  npm --prefix frontend ci --cache "$ROOT/frontend/.npm-cache"
  printf '%s\n' 'Setup complete. See README.md for local start commands.'
fi
