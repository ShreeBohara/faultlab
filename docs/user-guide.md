# FaultLab quick start guide

FaultLab tests an AI agent that upgrades a mock order to express shipping and sends a truthful confirmation. It deliberately makes the mock APIs fail, repeats failures, and asks a model to propose recovery rules. It keeps a rule only when repeated checks show improvement without breaking healthy behavior. Orders and notifications are synthetic; live model requests use your W&B credits.

This guide walks through one live learning campaign and explains each step. Learning changes a small recovery policy around the agent; it does not train the model's weights. A valid run may finish without an accepted repair. Aria setup is deferred for this walkthrough.

## What the parts do

| Part | Its job |
|---|---|
| Frontend | The browser dashboard. Sends commands and displays saved progress and evidence. Never receives your API key. |
| Backend | Coordinates experiments, calls the model, enforces budgets and saves results locally. |
| Simulator | Local mock order APIs. Creates fresh test worlds and injects timeouts, delayed operations, stale reads or temporary failures. |
| W&B Inference | Runs the selected model as the task agent, fault Explorer and policy Mechanic in separate roles. |
| Weave | Stores model/tool traces and evaluation evidence. FaultLab reads evidence back before using it to justify a repair. |
| Fixed Referee | Checks the original report against actual simulator outcomes using eight fixed rules. The model cannot change these rules. |

## 1 Start the application

**Do this.** Open three Terminal windows. In each, run:

```sh
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
```

Run one service in each window and leave it running:

```sh
# Terminal 1
./scripts/start-simulator.sh
# Terminal 2
./scripts/start-live-backend.sh
# Terminal 3
./scripts/start-frontend.sh
```

For a fresh installation, run `./scripts/setup.sh` once first. If an ordinary backend already uses port 8000, stop that backend with Ctrl+C before starting the live backend. Keep an already-running simulator or frontend; do not launch duplicate copies.

**Why.** The dashboard needs a coordinator and a mock service to perform the experiment.

**Backend.** The live launcher preserves your existing `.env`. It selects `openai/gpt-oss-120b` and W&B's canonical project `shreetbohara-quinstreet/Faultlab`. It sets ceilings of 6,000 calls, 60 million tokens and $100 per campaign, with verified model rates. Starting services makes no model calls. Keep settings and source unchanged during a campaign; the live launcher disables automatic reloads.

**Frontend.** Open `http://127.0.0.1:5173` and look for **Backend connected**. The page reads health and configuration; it has not started a run. If disconnected, check the backend terminal and click **Check again**.

## 2 Check the model connection

**Do this.** In a fourth terminal in the same application folder, run:

```sh
WANDB_PROJECT=Faultlab WANDB_MODEL='openai/gpt-oss-120b' \
  ./scripts/smoke-sponsors.sh \
  --confirm-entity shreetbohara-quinstreet \
  --max-output-tokens 2000
```

**Why.** This catches account and trace-connection problems before a longer experiment. GPT-OSS uses reasoning tokens; the default 32-token smoke limit can end before it returns a final answer. This explicit limit matches the campaign's existing per-call ceiling.

**Backend.** Verifies the model ID, makes one generation with a 20-second timeout and no automatic retry, then reads back its completed Weave trace. Success prints a response and actual trace link. Keys stay server-side.

**Frontend.** The result appears in Terminal. The dashboard does not create or start a campaign from this command.

Model discovery is available with `./scripts/check-provider.sh wandb --list-models --confirm-entity shreetbohara-quinstreet`. To switch models, also update matching verified prices and create a new campaign. The live launcher records its pricing source. Its $100 cap applies to one campaign, not every campaign on the account combined.

## 3 Create and start one learning run

**Do this in the dashboard.** In **Run desk**, choose **Execution profile → Live · configured model**, then **Campaign mode → Learn**. Keep the supplied task and enter an order label such as `order-live-demo`. Click **Create campaign**. Review the campaign ID, model and budget, then click **Start campaign** once.

**Why.** Create fixes what you are testing. Start explicitly begins the paid experiment. The supported task is order upgrade and confirmation; free text does not define arbitrary new tools or workflows.

**Backend.** Create saves the task, configuration, policy and limits. Start begins bounded model calls in fresh simulated worlds. Changing dropdowns later does not change that saved campaign. Each episode has limits including eight model turns and 90 seconds.

**Frontend.** The campaign receipt shows recorded settings. Its state and reason change as work proceeds, and the evidence panels fill with saved results.

**Terminal alternative.** This creates and starts the same kind of learning run. Use either this command or the dashboard sequence for a single campaign:

```sh
./scripts/run-demo.sh --mode learn --execute-live --wait
```

Copy the printed campaign ID into **Open saved campaign**, then click **Load recording** to follow it. Loading does not start another run. Leave all three service terminals open.

## 4 Follow the learning process

You do not need to click through these stages. The backend advances automatically and the frontend shows evidence as it arrives. Later stages may remain unreached; missing remote evidence can pause the run at WAITING_EVIDENCE.

| Stage | Why it runs and what it does |
|---|---|
| Discover | Explorer selects a fault schedule. The task agent attempts the order and the Referee checks the result, looking for consequential failures. |
| Reproduce | Repeats the failure in three fresh worlds to check that it is repeatable. |
| Reduce | Tries smaller fault schedules; keeps only changes that still fail three times. This makes the failure easier to understand. |
| Diagnose | Tests explanations with controlled changes, separating a recovery weakness from missing evidence or an inconclusive explanation. |
| Propose | Mechanic returns a constrained recovery policy or says no change. Its original proposal is saved, not automatically accepted. |
| Challenge | Attempts to break the candidate on four meaningful schedules with repeated paired runs. A failed candidate can feed another attempt. |
| Promote | Compares the candidate with the original policy on fixed cases. Acceptance requires sufficient improvement and preserved healthy behavior. |
| Save evidence | Saves outcomes, policy decisions and any regression tests, and synchronizes eligible evidence with Weave. |

**Frontend.** Watch **Fault × policy ledger**. Click an episode ID to open its original observations, report and **Fixed Referee verdict** in **Evidence timeline**. Use **Reproduce & reduce**, **Tested diagnosis** and **Adversarial challenge** to inspect the evidence behind a proposal. After selecting an older episode, reload the campaign with **Load recording** to follow its latest episode again.

**If the state is WAITING_EVIDENCE.** Use **Retry evidence sync** for this campaign. It retries saved evidence without repeating completed business calls. Once verified, the already-authorized learning loop may resume and make further model calls. The terminal wait command returns at this state; continue watching the dashboard.

**If you need to stop.** Load the active campaign and click **Stop**. This prevents new work and preserves evidence. An already-dispatched request may have committed. **Recorded playback** changes how you view the record; it does not stop a running campaign.

## 5 Read the result and save it

**Do this.** Wait for the learning attempt to finish, then inspect the state and reason. `COMPLETED` and `NO_CHANGE` are final outcomes. Let the terminal wait finish or wait until Create campaign becomes available again. `REJECTED` and `PROMOTED` can be intermediate states while work continues. An infrastructure error is a test limitation, not evidence of improvement.

**Why.** A proposed rule, a passing example and an accepted policy are different outcomes. Saved comparisons establish which outcome you have.

**Backend.** Keeps every attempt, including rejected candidates and inconclusive results. The active recovery policy changes only after the promotion checks pass.

**Frontend.** In **Recovery policy → Immutable version**, select the relevant version. If a proposal exists, use **Read original model proposal** and **Policy content and complete provenance** to inspect its decision. No proposal was generated in the recorded NO_CHANGE run. Under **Sponsor evidence → Weave**, use **Open Weave trace** for a recorded remote trace. Aria remains pending in this walkthrough.

| Result | Meaning |
|---|---|
| B0 / B1 / L | Model with an empty policy / handwritten reference / model with a recovery policy. |
| Completed | The episode's success claim is supported by the fixed checks. |
| Safe unresolved | The agent preserved uncertainty instead of claiming unsupported success. |
| Correctly rejected | A real rejection was reported truthfully. |
| Violation | At least one fixed check failed. |
| Lab error / Interrupted | Infrastructure failed / execution stopped. Neither establishes a successful repair. |
| NO_CHANGE | The learning campaign did not promote a policy. |

**Save the campaign.** Replace `CAMPAIGN_ID` and choose a new output filename:

```sh
./scripts/export-evidence.sh --campaign CAMPAIGN_ID \
  --output artifacts/my-live-evidence.json
```

The backend reads saved records into JSON; the frontend continues displaying the same campaign. Export, reload and playback make no new model calls. If a regression exists, **Portable regression → Saved regression → Inspect saved bundle** opens it; **Download regression** saves its ZIP. **Run fresh regression** is a separate execution action.

## After the first run

The walkthrough covers one learning campaign with Inference and Weave. Broader validation is tracked in the sibling `FaultLab_Specs/specs/001-faultlab-loop/tasks.md`:

| Task | Required evidence |
|---|---|
| T039 baseline study | Six development cases with three B0/B1 pairs each. The command is in `docs/live-validation.md`; Run baseline runs only one healthy episode. |
| T065 learning | Repeated failure, tested diagnosis, generated repair, challenge and promotion evidence. Improvement must be measured. |
| T088 sponsors | Real Inference, Weave evaluation/dataset and automatic Aria analysis. Aria is deferred. |
| T097 freeze | Save the accepted policy and exact configuration before protected studies. Requires an accepted learned policy. |
| T100 external studies | Run exported failures on the independent agent; measure transfer and equal-budget fault selection. |
| T102 final audit | Run the sealed 72-episode comparison and retain all results. Do not tune the policy from audit results. |

**Observed live result.** The tested campaign finished NO_CHANGE: one order completed, one trial violated a check, and six trials received no usable final model answer. Repair stages were not reached. See `docs/learning-results.md` and `docs/sponsor-results.md` for exact evidence. Additional studies have separate campaign budgets. Stop service terminals with Ctrl+C when finished; local history remains saved.
