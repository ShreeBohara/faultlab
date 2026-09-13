# Sponsor readiness

The configured live profile uses `meta-llama/Llama-3.1-8B-Instruct` as the task Actor and `deepseek-ai/DeepSeek-V4-Pro-0813` as the Explorer and Mechanic. The credited entity and project come from the root `.env`. Earlier single-model campaigns remain preserved evidence; new split-role campaigns receive a new configuration hash.

Keep credentials in the existing root `.env`. Do not copy it into chat, frontend variables or tracked configuration. Installed pins are openai 3.13.0, weave 0.53.9, wandb 0.30.0 and pydantic 2.13.5. `./scripts/check-provider.sh preflight` checks SDK compatibility without contacting providers.

## Start the configured live profile

Use `./scripts/start-live-backend.sh` instead of the ordinary backend launcher. Stop and restart any existing backend to load the current model and code. It supplies non-secret process settings and leaves `.env` unchanged. It also disables automatic reloads so editing files does not silently interrupt a live campaign. Startup, health, dashboard reads and default tests make no provider calls.

The launcher selects these values:

| Setting | Value |
|---|---|
| WANDB_MODEL | meta-llama/Llama-3.1-8B-Instruct |
| WANDB_EXPLORER_MODEL | deepseek-ai/DeepSeek-V4-Pro-0813 |
| WANDB_MECHANIC_MODEL | deepseek-ai/DeepSeek-V4-Pro-0813 |
| WANDB_PROJECT | exact project slug from `.env` |
| FAULTLAB_LIVE_ENABLED | true |
| FAULTLAB_CONFIRMED_ENTITY | exact `WANDB_ENTITY` from `.env` |
| FAULTLAB_MODEL_CALL_CAP | 6000 |
| FAULTLAB_TOKEN_CAP | 204000000 |
| FAULTLAB_DOLLAR_CAP | 100 |
| FAULTLAB_INPUT_DOLLARS_PER_MILLION | 0.22 |
| FAULTLAB_OUTPUT_DOLLARS_PER_MILLION | 0.22 |
| FAULTLAB_PRICING_MODEL | meta-llama/Llama-3.1-8B-Instruct |
| FAULTLAB_PRICING_VERIFIED | true |
| FAULTLAB_REASONING_INPUT_DOLLARS_PER_MILLION | 1.31 |
| FAULTLAB_REASONING_OUTPUT_DOLLARS_PER_MILLION | 3.96 |
| FAULTLAB_REASONING_PRICING_MODEL | deepseek-ai/DeepSeek-V4-Pro-0813 |
| FAULTLAB_REASONING_PRICING_VERIFIED | true |

Rates were checked against [W&B's Llama 3.1 8B pricing](https://wandb.ai/site/inference-model/meta-llama-3-1-8b/) and [V4 Pro 0813 pricing](https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/). Actor calls reserve the Llama rate; Explorer and Mechanic calls reserve the DeepSeek rate. Protected future batches use the larger bound. Actual returned usage is recorded separately; missing billing metadata stays unknown. The $100 cap remains a hard per-campaign limit.

Campaign requests use JSON mode, temperature 0, a 20-second timeout and no automatic retries. DeepSeek Explorer and Mechanic requests disable thinking using the [documented W&B reasoning control](https://docs.wandb.ai/inference/response-settings/reasoning). These request settings and every role model are frozen with the campaign.

A model change requires current model availability, matching verified input/output rates and a new frozen campaign. Launcher environment overrides are supported; overriding only the model deliberately fails price-model matching. Do not change the selected model, prices, prompts or source during an active campaign.

## Explicit connection check

After your deliberate request, run:

```sh
set -a
source .env
set +a
export WANDB_MODEL="${WANDB_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"
./scripts/check-provider.sh wandb --list-models --confirm-entity "$WANDB_ENTITY"
./scripts/smoke-sponsors.sh --confirm-entity "$WANDB_ENTITY"
```

The smoke check uses the Actor model and its built-in bounded output limit. There is one generation, a 20-second timeout and no automatic generation retry. It verifies the completed call by reading it back from Weave; flush alone is insufficient.

## Learning and evidence

With simulator, live backend and frontend running, follow `docs/user-guide.md` or run `./scripts/run-demo.sh --mode learn --execute-live --wait`. Opening the dashboard or creating an idle campaign makes no model calls; Start begins execution. Keep the same campaign ID to view its outcomes.

Weave is initialized in a bounded child process. Trace inputs contain approved public evidence, not client/settings/credential objects. Original results are saved locally before synchronization. If a campaign is waiting for remote evidence, Retry evidence sync resends saved evidence and can resume its already-authorized learning loop; it does not repeat completed business calls.

A real connection trace does not by itself satisfy full sponsor acceptance. Campaign root/tool readback, a real fixed-score evaluation and versioned regression dataset require their corresponding stages to execute. A valid no-change or inconclusive learning result may never reach those later stages.

## Minimal Aria setup

Verify team access, Smart features and Ask Aria in W&B. In the project UI, create a Finished-run automation with name filter `^faultlab-campaign-.*` and action **Trigger ARIA**. Use the exact reviewed `ARIA_PROMPT` from `backend/app/telemetry/aria_bridge.py`. Record the actual automation ID, configuration URL and observations; never invent values.

Save the observed setup through:

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli.sponsors register-automation \
  --record /absolute/path/to/observed-setup.json
```

The JSON must contain the exact fields validated by `validate_automation_setup` in `backend/app/telemetry/aria_bridge.py`: project, automation_id, team_confirmed, smart_features_enabled, ask_aria_observed, event, run_name_filter, action, prompt, configuration_url, recorder and observed_at. All observations must come from the account UI. Registration records setup; it does not itself invoke or remotely verify Aria.

After a future completed campaign triggers the automation, record actual automation history, execution/thread IDs, observed UTC time, attributed analysis and HTTPS source links in the dashboard's Sponsor evidence form. Keep capture method `manual_ui_capture` separate from invocation `automatic`. A manually started chat or pasted URL alone does not satisfy automatic analysis. Missing access/output keeps T088 open.
