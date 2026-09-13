# Sponsor readiness

The selected model is `deepseek-ai/DeepSeek-V4-Pro-0813`; W&B's canonical project is `shreetbohara-quinstreet/Faultlab`. Its action, report, Explorer and diagnosis response checks passed with thinking disabled; its final learning campaign finished NO_CHANGE with no provider errors and all eight traces verified; repair/challenge/promotion remain unverified live. Earlier DeepSeek V3.1 runs verified a healthy order and 119 campaign episode traces but ended without a qualified repair. The user authorized a full learning cycle up to $100 and explicitly deferred Aria. Actual evidence and retained failures are in `docs/sponsor-results.md` and `docs/learning-results.md`.

Keep credentials in the existing root `.env`. Do not copy it into chat, frontend variables or tracked configuration. Installed pins are openai 3.13.0, weave 0.53.9, wandb 0.30.0 and pydantic 2.13.5. `./scripts/check-provider.sh preflight` checks SDK compatibility without contacting providers.

## Start the configured live profile

Use `./scripts/start-live-backend.sh` instead of the ordinary backend launcher. Stop and restart any existing backend to load the current model and code. It supplies non-secret process settings and leaves `.env` unchanged. It also disables automatic reloads so editing files does not silently interrupt a live campaign. Startup, health, dashboard reads and default tests make no provider calls.

The launcher selects these values:

| Setting | Value |
|---|---|
| WANDB_MODEL | deepseek-ai/DeepSeek-V4-Pro-0813 |
| WANDB_PROJECT | Faultlab |
| FAULTLAB_LIVE_ENABLED | true |
| FAULTLAB_CONFIRMED_ENTITY | shreetbohara-quinstreet |
| FAULTLAB_MODEL_CALL_CAP | 6000 |
| FAULTLAB_TOKEN_CAP | 204000000 |
| FAULTLAB_DOLLAR_CAP | 100 |
| FAULTLAB_INPUT_DOLLARS_PER_MILLION | 1.31 |
| FAULTLAB_OUTPUT_DOLLARS_PER_MILLION | 3.96 |
| FAULTLAB_PRICING_MODEL | deepseek-ai/DeepSeek-V4-Pro-0813 |
| FAULTLAB_PRICING_VERIFIED | true |

Rates were checked against [W&B's V4 Pro 0813 pricing](https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/). The scheduler reserves the maximum 32,000 input and 2,000 output tokens at these rates before each model dispatch: $0.04984 per call. Its 1,064 protected calls reserve $53.02976 within the $100 campaign cap. Actual returned usage is recorded separately; missing billing metadata stays unknown. The dollar cap is per campaign, not a shared account or session limit.

Campaign requests use JSON mode, temperature 0, a 20-second timeout and no automatic retries. Both smoke and campaign requests send `extra_body={"chat_template_kwargs":{"enable_thinking":false}}` for this model, using the [documented W&B reasoning control](https://docs.wandb.ai/inference/response-settings/reasoning). The default-thinking diagnosis probe returned no final answer after 4,000 output tokens; the disabled-thinking probe returned a valid answer using 240 output tokens. These are connection/format observations, not proof of a correct diagnosis or repair.

A model change requires current model availability, matching verified input/output rates and a new frozen campaign. Launcher environment overrides are supported; overriding only the model deliberately fails price-model matching. Do not change the selected model, prices, prompts or source during an active campaign.

## Explicit connection check

After your deliberate request, run:

```sh
./scripts/check-provider.sh wandb --list-models --confirm-entity shreetbohara-quinstreet
WANDB_PROJECT=Faultlab WANDB_MODEL='deepseek-ai/DeepSeek-V4-Pro-0813' \
  ./scripts/smoke-sponsors.sh --confirm-entity shreetbohara-quinstreet \
  --max-output-tokens 2000
```

The smoke check defaults to 32 output tokens. This explicit override uses the same 2,000-token ceiling as the configured V4 runtime. There is one generation, a 20-second timeout and no automatic generation retry. It verifies the completed call by reading it back from Weave; flush alone is insufficient. The setting overrides apply only to this command and do not edit credentials.

## Learning and evidence

With simulator, live backend and frontend running, follow `docs/user-guide.md` or run `./scripts/run-demo.sh --mode learn --execute-live --wait`. Opening the dashboard or creating an idle campaign makes no model calls; Start begins execution. Keep the same campaign ID to view its outcomes.

Weave is initialized in a bounded child process. Trace inputs contain approved public evidence, not client/settings/credential objects. Original results are saved locally before synchronization. If a campaign is waiting for remote evidence, Retry evidence sync resends saved evidence and can resume its already-authorized learning loop; it does not repeat completed business calls.

A real connection trace does not by itself satisfy full sponsor acceptance. Campaign root/tool readback, a real fixed-score evaluation and versioned regression dataset require their corresponding stages to execute. A valid no-change or inconclusive learning result may never reach those later stages.

## Aria setup is deferred

No automation is being configured for this walkthrough. Without registered observed setup, FaultLab leaves Aria pending and does not publish a Finished campaign run. This does not disable Weave.

For a later explicitly requested Aria validation, verify team access, Smart features and Ask Aria in W&B. In the project UI, create a Finished-run automation with name filter `^faultlab-campaign-.*` and action Trigger Aria. Use the exact reviewed `ARIA_PROMPT` from `backend/app/telemetry/aria_bridge.py` (also described in the specification's sponsor integration contract). Record the actual automation ID, configuration URL and observations; never invent values.

Save the observed setup through:

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli.sponsors register-automation \
  --record /absolute/path/to/observed-setup.json
```

The JSON must contain the exact fields validated by `validate_automation_setup` in `backend/app/telemetry/aria_bridge.py`: project, automation_id, team_confirmed, smart_features_enabled, ask_aria_observed, event, run_name_filter, action, prompt, configuration_url, recorder and observed_at. All observations must come from the account UI. Registration records setup; it does not itself invoke or remotely verify Aria.

After a future completed campaign triggers the automation, record actual automation history, execution/thread IDs, observed UTC time, attributed analysis and HTTPS source links in the dashboard's Sponsor evidence form. Keep capture method `manual_ui_capture` separate from invocation `automatic`. A manually started chat or pasted URL alone does not satisfy automatic analysis. Missing access/output keeps T088 open.
