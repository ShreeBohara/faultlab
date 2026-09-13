#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -eq 0 ]]; then
  printf '%s\n' 'Usage: ./scripts/smoke-sponsors.sh --confirm-entity ACTUAL_ENTITY [--max-output-tokens 1..2000]' 'Explicitly performs the bounded configured-model + Weave readback check. Aria requires real UI automation/output evidence.' >&2
  exit 2
fi
exec "$ROOT/scripts/check-provider.sh" wandb --generate "$@"
