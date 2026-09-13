# FaultLab live demo runbook

One new W&B project. One campaign. No extra smoke traces.

Run everything from this repository root.

Live profile: Actor = Llama 3.1 8B; Explorer and Mechanic = DeepSeek V4 Pro.

## 1. Point `.env` at the new W&B project

Create the empty W&B project in the UI, then edit `.env`.

Change **only** the project slug. Keep the same API key and entity:

```
WANDB_API_KEY=        # leave unchanged
WANDB_ENTITY=         # leave unchanged
WANDB_PROJECT=YOUR_NEW_PROJECT
```

Replace `YOUR_NEW_PROJECT` with the exact project slug from the W&B URL:

`https://wandb.ai/<WANDB_ENTITY>/<YOUR_NEW_PROJECT>`

Do not display this file during the demo. Do not copy old Weave traces; they belong to the previous project.

If a live backend is already running, stop it after this edit. It will keep using the old project until you restart it.

## 2. Set up the virtual environment

```sh
./scripts/setup.sh
source .venv/bin/activate
python --version
```

**What happens:** Setup creates `.venv` if needed and installs dependencies. Python must be 3.12. Project scripts already call `.venv/bin/python`, so activation is optional for those.

## 3. Start the Simulator

Terminal 1:

```sh
./scripts/start-simulator.sh
```

**What happens:** Mock order and notification APIs on `127.0.0.1:8001`.

## 4. Start the live backend

Terminal 2:

```sh
set -a
source .env
set +a
./scripts/start-live-backend.sh
```

Sourcing `.env` first makes the new `WANDB_PROJECT` win if the launcher has an old default.

**What happens:** Coordinator on `127.0.0.1:8000`. No model calls yet.

## 5. Start the frontend

Terminal 3:

```sh
./scripts/start-frontend.sh
```

**What happens:** Dashboard at `http://127.0.0.1:5173`. Confirm **Backend connected**.

Do not load an old campaign ID. Those records are local, but their Weave traces are in the previous W&B project.

## 6. Create Aria automation in the new project

Do this in W&B, on the **new** project. The old project's automation will not fire here.

1. Confirm team access, Smart features, and Ask Aria for this project.
2. Open **Automations** and create a run automation scoped to `WANDB_ENTITY/YOUR_NEW_PROJECT`.
3. Event: **Finished**.
4. Run-name filter: `^faultlab-campaign-.*`
5. Action: **Trigger ARIA**.
6. Prompt: paste the exact `ARIA_PROMPT` from `backend/app/telemetry/aria_bridge.py`. Do not edit it.

Copy the real automation ID and configuration URL from the UI. Save them as `artifacts/aria-setup.json` using the new project path:

```json
{
  "project": "WANDB_ENTITY/YOUR_NEW_PROJECT",
  "automation_id": "PASTE_FROM_UI",
  "team_confirmed": true,
  "smart_features_enabled": true,
  "ask_aria_observed": true,
  "event": "Finished",
  "run_name_filter": "^faultlab-campaign-.*",
  "action": "Trigger ARIA",
  "prompt": "PASTE_EXACT_ARIA_PROMPT",
  "configuration_url": "https://wandb.ai/WANDB_ENTITY/YOUR_NEW_PROJECT/...",
  "recorder": "YOUR_NAME",
  "observed_at": "2026-09-13T00:00:00Z"
}
```

`project` must be `entity/slug`, not the slug alone. `prompt` must match `ARIA_PROMPT` byte-for-byte. Use the real `observed_at` time in UTC.

Register it locally (no W&B call):

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli.sponsors register-automation \
  --record artifacts/aria-setup.json
```

**What happens:** FaultLab records which automation may analyze a finished campaign. It does not run Aria.

Skip any provider smoke check. That would write extra Weave traces before the demo campaign.

## 7. Create one live learning campaign

In the dashboard:

1. Select **Live · configured model**.
2. Select **Learn**.
3. Enter an order label.
4. Click **Create campaign**.

**What happens:** Freezes models, task, policy, prompts, contracts, and budgets. No model call.

## 8. Start the campaign

Click **Start campaign** once.

**What happens:** Paid model work begins. This is the only run that should appear in the new project's Weave traces.

The loop is:

- **Discover:** Explorer chooses a fault; Actor tries the task.
- **Check:** the fixed Referee compares the report with reality.
- **Reproduce:** the same failure must repeat in three fresh worlds.
- **Reduce:** FaultLab searches for a smaller repeatable failure.
- **Diagnose:** it tests whether the cause is a policy gap or evidence gap.
- **Propose:** Mechanic may create a candidate recovery policy.
- **Challenge:** new fault schedules try to break the candidate.
- **Promote:** fixed comparisons accept only measured improvement.

Stopping before later stages is valid when no qualifying failure is found.

## 9. Watch the evidence

- **Run summary:** reached stages vs not reached.
- **Evidence timeline:** observations, original report, Referee verdict.
- **Fault × policy ledger:** results across faults and policy versions.
- **Recovery policy:** proposed, rejected, and accepted versions.
- **Reproduce / Diagnosis / Challenge:** only for stages that ran.
- **Sponsor evidence:** verified Weave traces in the new project.

If the campaign reaches `WAITING_EVIDENCE`, click **Retry evidence sync**. That retries saved evidence only. It does not rerun the model.

## 10. Read the final result

- `COMPLETED`: the successful campaign path finished.
- `NO_CHANGE`: no recovery policy passed every gate.
- `WAITING_EVIDENCE`: remote evidence still needs verification.
- `STOPPED`: the operator stopped new work.
- `ERROR`: infrastructure prevented completion.

`NO_CHANGE` is an honest result, not a crash.

After a terminal result, W&B gets a Finished run named `faultlab-campaign-CAMPAIGN_ID` in the **new** project. The automation asks Aria for one advisory summary. Inspect that in W&B, then save the real run, automation, history, and output under **Sponsor evidence → Capture observed Aria evidence**.

## 11. Export the saved evidence

```sh
./scripts/export-evidence.sh \
  --campaign CAMPAIGN_ID \
  --output artifacts/demo-evidence.json
```

**What happens:** Exports local records only. No model or business calls.

## CLI alternative

Instead of steps 7 and 8 in the dashboard, run:

```sh
./scripts/run-demo.sh --mode learn --execute-live --wait
```

Use either the dashboard or this command for the one campaign, not both.

## Stop after the demo

Press `Ctrl+C` in the frontend, backend, and Simulator terminals.

## Short explanation to say aloud

“FaultLab tests whether an AI agent stays safe and truthful when APIs are unreliable. Llama 3.1 8B performs the task, while DeepSeek V4 Pro explores faults and proposes repairs. The fixed Referee checks the report against reality. Weave verifies eligible traces, and a Finished-run automation asks Aria for one advisory summary. FaultLab tests recovery policies; it does not train model weights.”
