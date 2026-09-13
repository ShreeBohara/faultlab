#!/usr/bin/env bash
# Explicit live-ready launch; starting the server never starts a campaign.
# Rates verified 2026-09-13: https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/
# Credentials remain in the existing root .env, which this script never edits.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export WANDB_MODEL="${WANDB_MODEL:-deepseek-ai/DeepSeek-V4-Pro-0813}"
export WANDB_PROJECT="${WANDB_PROJECT:-Faultlab}"
export FAULTLAB_LIVE_ENABLED=true
export FAULTLAB_CONFIRMED_ENTITY="${FAULTLAB_CONFIRMED_ENTITY:-shreetbohara-quinstreet}"
export FAULTLAB_MODEL_CALL_CAP="${FAULTLAB_MODEL_CALL_CAP:-6000}"
export FAULTLAB_TOKEN_CAP="${FAULTLAB_TOKEN_CAP:-204000000}"
export FAULTLAB_DOLLAR_CAP="${FAULTLAB_DOLLAR_CAP:-100}"
export FAULTLAB_INPUT_DOLLARS_PER_MILLION="${FAULTLAB_INPUT_DOLLARS_PER_MILLION:-1.31}"
export FAULTLAB_OUTPUT_DOLLARS_PER_MILLION="${FAULTLAB_OUTPUT_DOLLARS_PER_MILLION:-3.96}"
export FAULTLAB_PRICING_MODEL="${FAULTLAB_PRICING_MODEL:-deepseek-ai/DeepSeek-V4-Pro-0813}"
export FAULTLAB_PRICING_VERIFIED=true
# Live campaigns use frozen code/configuration and must not be interrupted by a
# development file watcher. Stop and restart deliberately after making changes.
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
