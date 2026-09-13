#!/usr/bin/env bash
# Explicit live-ready launch; starting the server never starts a campaign.
# Rates verified 2026-09-13:
# https://wandb.ai/site/inference-model/meta-llama-3-1-8b/
# https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/
# Credentials remain in the existing root .env, which this script never edits.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export WANDB_MODEL="${WANDB_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"
export WANDB_EXPLORER_MODEL="${WANDB_EXPLORER_MODEL:-deepseek-ai/DeepSeek-V4-Pro-0813}"
export WANDB_MECHANIC_MODEL="${WANDB_MECHANIC_MODEL:-deepseek-ai/DeepSeek-V4-Pro-0813}"
export FAULTLAB_LIVE_ENABLED=true
if [[ -z "${FAULTLAB_CONFIRMED_ENTITY:-}" ]]; then
  FAULTLAB_CONFIRMED_ENTITY="${WANDB_ENTITY:-}"
  if [[ -z "$FAULTLAB_CONFIRMED_ENTITY" && -f "$ROOT/.env" ]]; then
    FAULTLAB_CONFIRMED_ENTITY="$("$ROOT/.venv/bin/python" -c 'from dotenv import dotenv_values; import sys; print((dotenv_values(sys.argv[1],interpolate=False).get("WANDB_ENTITY") or "").strip())' "$ROOT/.env")"
  fi
fi
export FAULTLAB_CONFIRMED_ENTITY
export FAULTLAB_MODEL_CALL_CAP="${FAULTLAB_MODEL_CALL_CAP:-6000}"
export FAULTLAB_TOKEN_CAP="${FAULTLAB_TOKEN_CAP:-204000000}"
export FAULTLAB_DOLLAR_CAP="${FAULTLAB_DOLLAR_CAP:-100}"
export FAULTLAB_INPUT_DOLLARS_PER_MILLION="${FAULTLAB_INPUT_DOLLARS_PER_MILLION:-0.22}"
export FAULTLAB_OUTPUT_DOLLARS_PER_MILLION="${FAULTLAB_OUTPUT_DOLLARS_PER_MILLION:-0.22}"
export FAULTLAB_PRICING_MODEL="${FAULTLAB_PRICING_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"
export FAULTLAB_PRICING_VERIFIED=true
export FAULTLAB_REASONING_INPUT_DOLLARS_PER_MILLION="${FAULTLAB_REASONING_INPUT_DOLLARS_PER_MILLION:-1.31}"
export FAULTLAB_REASONING_OUTPUT_DOLLARS_PER_MILLION="${FAULTLAB_REASONING_OUTPUT_DOLLARS_PER_MILLION:-3.96}"
export FAULTLAB_REASONING_PRICING_MODEL="${FAULTLAB_REASONING_PRICING_MODEL:-deepseek-ai/DeepSeek-V4-Pro-0813}"
export FAULTLAB_REASONING_PRICING_VERIFIED=true
export FAULTLAB_LAB_MODEL="${FAULTLAB_LAB_MODEL:-$WANDB_EXPLORER_MODEL}"
export FAULTLAB_LAB_PRICING_MODEL="${FAULTLAB_LAB_PRICING_MODEL:-$FAULTLAB_REASONING_PRICING_MODEL}"
export FAULTLAB_LAB_INPUT_DOLLARS_PER_MILLION="${FAULTLAB_LAB_INPUT_DOLLARS_PER_MILLION:-$FAULTLAB_REASONING_INPUT_DOLLARS_PER_MILLION}"
export FAULTLAB_LAB_OUTPUT_DOLLARS_PER_MILLION="${FAULTLAB_LAB_OUTPUT_DOLLARS_PER_MILLION:-$FAULTLAB_REASONING_OUTPUT_DOLLARS_PER_MILLION}"
# Live campaigns use frozen code/configuration and must not be interrupted by a
# development file watcher. Stop and restart deliberately after making changes.
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
