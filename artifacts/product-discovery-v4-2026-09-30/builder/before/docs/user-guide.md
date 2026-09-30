# FaultLab quick start guide

For a new workspace, use `./scripts/start-local.sh --data-dir /absolute/local/data-directory`.
It starts all three services with the same selected directory and live execution disabled.
Install and test first with [Setup](setup.md#install-and-test-start-here), which also explains how to
choose other ports.
Use `--archive` to inspect an existing store without recovery, execution or writes.
See [local operation and recovery](local-operation.md) for the complete commands and data guidance.
The dashboard displays the selected store; existing historical directories are never moved.

## Create a reviewed campaign

In **Run desk → New campaign**, choose **Offline reference smoke** for a provider-free first run.
Choose one of the six **Public development case** options, review the task and authorized order,
then click **Create campaign**. This saves an idle campaign; it does not execute the agent.
Read the **Frozen campaign plan**, then click **Start campaign**. Changing the setup form afterward
does not change that saved plan. A changed runtime or model requires a new plan; old evidence remains
readable. The supported task is express shipping upgrade followed by a truthful confirmation.
The instructions field does not define new tools, arbitrary tasks or a new scoring contract.

For configured paid work, choose **Live reviewed agent**, select **FaultLab reference Actor**,
**smolagents ToolCallingAgent 1.26.0** (native adapter v1) or **smolagents ToolCallingAgent - adapter v2
(short evidence labels, strict final report turn)**, then **Register configured agent**. The two smolagents
choices run the same unmodified agent through different declared adapters; they are separate agents whose
results are never pooled ([adapter v2](external-agent-setup.md#native-adapter-v2-first-build-run-live-september-29-2026-v21-labels-not-yet-run-live)). Registration checks installed
source and the adapter contract; it makes no provider call and does not establish agent quality or
provider access. Baseline runs use the chosen public case. **Learn** uses the bounded development
search; **Compare** requires an accepted policy for the exact selected configuration. Every original
learning stage uses the selected agent, while the B1 handwritten control is labeled separately.
Reference-only context, completion and dependent heldout research studies are unavailable for native
campaigns. Independent portability requires a different reviewed implementation; rerunning the same
native agent is a regression measurement, not independent validation.

**Lost model requests in a Learn campaign.** A new Learn plan freezes the model transport retry rule v2
(`faultlab-transport-retry/v2-lab-backoff`). When an Explorer or Mechanic request gets no answer (connection error,
timeout, HTTP 503), FaultLab waits 5 s, 20 s and then 60 s and sends the identical request again, at most 3 times per
request and 12 times per campaign. Each retry is charged before it is sent; a retry the campaign's unreserved budget
cannot cover is refused at once, without waiting. A discovery selection's retries are listed on that selection in the
fault-search panel; a challenge selection's or a Mechanic request's retries appear only in the campaign recording and
in the budget counts. While FaultLab waits, the campaign simply stays in its current state (for example SELECTING or
DIAGNOSING); nothing on the dashboard shows the wait until the retry is sent. **Stop** during such a wait ends the
campaign STOPPED within about half a second. If every allowed retry fails, the campaign ends ERROR and says how many
retries were tried (or, if none could be sent, why not). The agent itself keeps one retry per request. Plans saved earlier, and
baseline or compare plans, keep one retry per request ([details](PRODUCT_TRANSPORT_RETRY_2026-09-29.md#12-rule-v2-faultlabs-own-lab-roles-back-off-september-30-0-not-yet-run-live)).

Use **Download campaign recording** to save the plan, configuration, registration and public
development evidence, including failed attempts and `NO_CHANGE` runs. The JSON download makes no
provider call. Protected trials and private simulator state are excluded. This recording is an
evidence archive; the separately validated regression bundle is the executable test artifact.

Current product navigation: use **Campaign history → Saved campaigns → Open selected campaign**
to browse saved runs. **Load older campaigns** reads the next page; **Refresh history** returns to
newest-created runs. The pasted-ID field remains available. Opening history never starts or resumes
execution. A saved campaign's Stop button is enabled only when that exact campaign owns active work;
use **Open active campaign** to switch to the running one.

In **Portable regression**, inspect the saved bundle, then use its **Saved executions** selector to
open a previous run. The list is restricted to that exact bundle and manifest. An interrupted run
keeps its recorded INCOMPLETE status and stop reason. **Run fresh regression** remains a separate
explicit action that creates new worlds and may spend provider credits.

## Import, review and rerun a regression

The **Imported regressions** panel works without opening a campaign. Choose a regression ZIP downloaded
from **Portable regression** (up to 24 MiB), then select **Save imported bundle**. Saving checks the file
and stores it as read-only data: no model calls, no fresh trials, no campaign and no policy change.
Saving the same ZIP again returns the same saved import without duplicating anything, and the panel says
so. A refusal appears directly under the file chooser; nothing is saved and you choose the file again.

The ZIP is checked before anything is saved and its contents are never run. It must contain exactly the
reviewed bundle files as regular files (no folders, links, encryption or unusual compression), stay within
the size limits, match every digest in its manifest, and carry a runner file byte-identical to the one
installed here. The fields the importer copies or later uses — the recorded task and order, and the source
agent registration — must also be well formed. Every refusal starts with *Import refused; nothing was
saved.* and names the reason without echoing file contents:

- **Not a ZIP archive** — for example a campaign recording JSON. That file is an evidence archive, not a
  runnable bundle.
- **Structure or size** — unexpected names, links, folders, encryption or oversized entries.
- **Unsupported version** — an older FaultLab schema, runner or execution profile. Keep that file and
  inspect it with the runtime that produced it.
- **Contents do not match** — the bundle was edited or is incomplete, or a recorded field such as the
  task, order or source registration is malformed.
- **Private content** — private evaluator fields or a configured credential value.

**Review** shows the original policy and its hash, fault recipe, source model and configuration, trial
outcomes, fault exposure and bundled reports. **How source trials were produced** says whether the
source trials were an *offline scripted fixture (no model calls)*, a *live model run*, recorded playback
or a mix; the saved-imports list shows the same. A scripted fixture's violations are scripted answers,
not failures of the named source model. All of it is labeled *imported historical observations;
not verified locally*.

**The rerun uses the bundle's recorded instructions.** Review shows the **exact task sent to the
agent**, its **authorized order**, and where they came from: recorded in the bundle by its source
campaign, or — only for a bundle that records no task — the FaultLab default task. Every fresh trial
sends exactly that text, so read it before running; a bundle from someone else can carry any
instruction up to 2,000 characters. The same task is repeated next to the run button. A source decision of ACCEPTED stays a historical label: it never becomes an
accepted or active policy here. Saved imports and their runs stay readable after restart and in archive
mode; archive mode disables upload, execution and cancellation.

**Fresh rerun (separate, may spend credits).** The **Run imported regression in fresh worlds** button
works only when the backend was started with live execution configured and the simulator is ready.
While it is disabled, the panel lists each actual reason and what to do: live execution off (configure
the live settings, then restart with `./scripts/start-local.sh --live --data-dir …`), named missing
settings, simulator not ready, read-only archive, no compatible target selected, another campaign
active, or an unresolved earlier request. To run: in **Run desk**, choose **Live reviewed agent**,
register the agent you want to test, return to the import and select **Refresh import review**, choose
that **Fresh target registration** (the built-in offline smoke agent is not offered: it cannot run
imported regressions), and read the task and limits. Selecting the button opens a confirmation that
repeats the target, the task and the spending bound; only **Confirm billable fresh run** sends it.

**Spending bound.** One run reserves 24 actor turns (3 trials × 8 turns). The reference agent may
resend a request once when its transport fails before any answer arrives; such retries are charged, so
one run can make at most 48 billable model requests, and FaultLab enforces that ceiling. Both native
smolagents adapters (v1 and v2) follow the same rule: at most one charged transport retry per turn, so the
worst case is also 48. The configured campaign call and dollar caps also
still apply. The backend rechecks the store, the bundle manifest and the target registration against
current settings, then runs the exact bundled policy and task for three trials in new synthetic worlds.
It stops early (INCOMPLETE) if a trial is invalid, interrupted or its scheduled fault never fires.

Each run gets its own request identity. Retrying or checking that same request after a timeout returns
the same run; it cannot start a second one. Selecting the button again later is an intentional new run:
it gets a new identity and new worlds. **Cancel unadmitted request** records a durable cancellation and confirms that nothing ran; if
the request had already started, the dashboard says so and opens that run instead of stopping it. To stop a run in
progress, open its accounting campaign (**Open active campaign**, or a fresh trial link) and use **Stop**;
recorded trials and charges are kept, the run is marked INCOMPLETE and nothing is replayed.

Results show the **actual target** (agent, model, registration and configuration), fault exposure and
effects for every fresh trial, and one plain verdict for the artifact kind: for an incident fixture,
*Incident reproduced as expected* means the regression still catches the failure; for a policy bundle,
*did not prevent the violation* is the bad outcome. **Charged to its accounting ledger** is the complete
charge, including transport retries and calls made during a trial that was cut off by a crash. If
FaultLab itself fails mid-run (for example the simulator becomes unreachable), the result shows a
classified infrastructure error, separate from any agent mistake. A small accounting campaign holds
each run's budget and evidence; it is not the tested agent, is hidden from Campaign history, and
refuses every other kind of work — ordinary Start, studies, comparisons, audits, portability, freezes
and the Portable regression rerun. Its Run desk receipt shows this one execution's budget. The
bundled policy runs under a separate local ID (`imported-…`) with the exact same content and hash; the
**Recovery policy** panel marks it *imported historical decision*. It cannot be used for comparisons,
final audits, portability or freezes. Use **Download fresh execution recording** to keep the run's
public evidence; it names the actual target separately from the accounting campaign. Original imported
evidence and fresh results always stay separate.

The Run desk's **Run readiness** check separates backend connectivity, simulator readiness and
live configuration. It makes no model calls and does not verify provider account access. Offline
reference runs need the simulator but no provider credentials. Live configuration errors name the
missing settings; never paste secrets into the dashboard.

The [September 27 product review](PRODUCT_CORE_REVIEW_2026-09-27.md) records current reliability
changes and verification. Earlier examples below retain their historical settings and results.


FaultLab tests an AI agent that upgrades a mock order to express shipping and sends a truthful confirmation. It deliberately makes the mock APIs fail, repeats failures, and asks a model to propose recovery rules. It keeps a rule only when repeated checks show improvement without breaking healthy behavior. Orders and notifications are synthetic; live model requests use your W&B credits.

Start with [current status](../CURRENT_STATUS.md) for the latest results and remaining budget. This guide explains how to inspect saved evidence and start a new campaign. Learning changes a small recovery policy around the agent; it does not train model weights. No generated policy has been accepted through the original promotion gates. Aria remains deferred.

## Read the three result indicators

Load a saved campaign using **Open saved campaign → Load recording**. This only reads evidence.

- **Development qualified**: the saved generated candidate met the displayed development requirements. A replay is identified separately; it is not a new generated repair.
- **Unseen-case result**: a separate evaluation of that exact candidate. “Not run” means there is no matching saved check. A completed check can still say HARM.
- **Active policy**: the policy the selected campaign actually uses. Development qualification and unseen-case checks never activate a policy by themselves.

To see them, open a saved learning campaign from **Campaign history**. A fresh install starts with
**No saved campaigns yet**, so run a campaign first or select a data folder that already holds some.
The team's own examples live only in its local stores: a Phase 28 development success, a later
unseen-case HARM result from a different policy, and a saved replay with 42 recorded validation
trials. Their campaign IDs are listed in [the September 27 status notes](part2/STATUS_NOTES_2026-09-27.md).
Opening a saved campaign never runs a new test.

## Search attempts and completion recovery

**Search attempts** shows what the Explorer asked to test. A changed seed alone is not a new fault schedule. If it repeats a schedule, the attempt is saved as a duplicate and no additional agent trial is run for it. An attempt, an executed trial and a triggered fault are different counts. Expand a selection to inspect its actual schedule and original model answer.

The main-loop ledger distinguishes fully triggered recipes, partially triggered recipes and recipes
with no triggered faults. A successful task with an unreached fault is still a successful task;
it does not establish that the agent handled that fault. These labels are derived from the saved
verdict and do not change qualification gates or historical outcomes.

**Completion recovery** asks a separate question: can a generated recovery rule finish a task that the agent truthfully left unfinished? It shows the original agent and the candidate side by side for each condition. A completed experiment does not mean every task succeeded. The ordinary safety checks still apply, and this experiment never activates a policy.

1. **Inspect saved work first.** Open a campaign that ran a completion study with **Open saved campaign → Load recording** (or from **Campaign history**). The frontend reads saved study rows from the backend; this makes no model calls. Expand **Completion recovery**, then open an episode to see its original report and Referee verdict. The main-loop matrix excludes these separate study trials deliberately. The team's saved study (in its local store only; IDs in [Phase 3 results](part2/PHASE3_RESULTS.md)) ended NO_CHANGE: both generated rules completed zero of three source tasks. Its follow-up stopped INCOMPLETE before any repair proposal because the agent never called the tool where a fault was scheduled. Later trace synchronization did not resume it.
2. **To run a new experiment, first start the services and confirm live settings as described below.** This makes the selected models, credits and simulator available. The completion command uses the running backend's settings; it does not change `.env`.
3. **Start only when you want fresh paid work:** run `./scripts/run-completion-study.sh --execute-live --wait` from the repository root. The backend saves a fixed plan before calling models: three failure cases and three healthy controls, at most two generated proposals, paired source checks, and—only if a proposal qualifies—42 further validation trials. Each trial gets a fresh shop. The maximum reservation is 484 model calls, plus the campaign's existing protected reserve.
4. **Read the saved result.** Use `./scripts/run-completion-study.sh --status STUDY_ID`, or load its campaign ID in the dashboard. These are read-only. `OBSERVED_IMPROVEMENT` means a completion gain on the declared development cases, not a promoted policy. `NO_CHANGE` means the experiment did not establish that gain. `INCOMPLETE` means execution or evidence stopped; original attempts remain saved and are not automatically replayed.

## Historical attempt-context comparison

**Attempt-context study** asks a different question again: does the agent do better if it is told, each turn, what it has already tried? Both sides run the same model, the same tools, the same empty policy and the same checks. Only the per-turn message differs. It never proposes or activates a policy.

1. **Inspect the saved work first.** Open a campaign that ran an attempt-context study with **Open saved campaign → Load recording** and expand **Attempt-context study**. The team's saved study (in its local store only; IDs in [Phase 4 results](part2/PHASE4_RESULTS.md)) has sixty trials, thirty per side. The result is `regression`: the changed side finished one transient-notification case the control never finished, and it also broke the terminally-rejected-upgrade report three times out of three by writing `NOT_STARTED` where the contract requires `NOT_REQUIRED`. A second campaign holds the one declared follow-up, which did not fix it. **Nothing from either study was adopted.**
2. **To run a new comparison** you need a new declared protocol in `backend/app/agents/progress.py`, then `./scripts/run-context-study.sh --execute-live --changed-protocol NAME --wait`. The plan is saved before any model call: ten public cases, three fresh shops per case per side, 480 reserved model calls on top of the campaign's protected reserve.
3. **Read the saved result** with `./scripts/run-context-study.sh --status STUDY_ID`, or `python scripts/experiments/summarize_context_study.py STUDY_ID` for the tables. Both are read-only. `OBSERVED_IMPROVEMENT` needs a completion gain *and* no failed check and no case going backwards. `REGRESSION` means the changed side broke something. A case whose trials were invalid is named and left out of the decision rather than rerun.

## What the parts do

| Part | Its job |
|---|---|
| Frontend | The browser dashboard. Sends commands and displays saved progress and evidence. Never receives your API key. |
| Backend | Coordinates experiments, calls the model, enforces budgets and saves results locally. |
| Simulator | Local mock order APIs. Creates fresh test worlds and injects timeouts, delayed operations, stale reads or temporary failures. |
| W&B Inference | Runs the selected model as the task agent, fault Explorer and policy Mechanic in separate roles. |
| Weave | Stores model/tool traces and evaluation evidence. FaultLab reads evidence back before using it to justify a repair. |
| Fixed Referee | Checks the original report against actual simulator outcomes using eight fixed rules. The model cannot change these rules. |

## Older examples: saved Phase 2 results

These examples are in the team's local store only; a fresh install does not have them. Their campaign,
execution and study IDs are recorded in [Phase 2 results](part2/PHASE2_RESULTS.md), and the two saved
regression IDs in [this note](part2/PHASE2_REGRESSION_IDS_2026-09-29.md). To open any
saved campaign, paste its ID into **Open saved campaign** and click **Load recording**, or pick it from
**Campaign history**. This reads saved evidence and makes no model calls. It does not restart the campaign.

| Record | What it shows |
|---|---|
| C2 | Runtime 2 learning ended `NO_CHANGE`: eight episodes, six completed tasks, two safe unresolved and zero violations. Only five of eight scheduled faults triggered. No repair was proposed or accepted; this is not proof that all faults were handled. |
| B | The earlier reproduced failure, a failed repair proposal and its exported incident. Use **Reproduce & reduce**, **Recovery policy** and **Portable regression** to inspect them. |
| C3 | Its saved campaign evidence. The separate 36-trial comparison is summarized below and in its saved baseline-study record (`/api/baseline-studies/STUDY_ID` on the backend); it is excluded from the dashboard’s main-loop counts. |

The same saved B incident was also tested in three fresh runtime 2 worlds, as a regression execution in a new campaign: two safe unresolved results and one incorrect-citation violation (C6). The original missing-report failure (C5) reproduced **zero of three** times. All three Weave traces were verified. This tested the empty baseline policy; it did not demonstrate a learned repair. The saved execution record (`/api/regression-executions/EXECUTION_ID` on the backend) lists the three episode IDs. Regression execution has its own status; an idle campaign is not its result.

To inspect a saved regression execution in the dashboard:

1. Load the campaign that ran it.
2. In **Portable regression → Saved regression**, select the regression, then click **Inspect saved bundle**.
3. Paste the execution ID into **Saved execution ID**, then click **Open saved execution**.
4. Check the recorded trials and model calls. Click an episode to read its original report and failed checks. (For the B incident: three trials, 24 model calls, and the third episode failed C6.)

These steps only read saved records; they do not start or resume a run. **Run fresh regression** is a different, paid action.

C3's live model completed 12 tasks, correctly rejected three, safely left two unresolved and violated the fixed checks once. The handwritten reference completed 15 and correctly rejected three, with no violations. All 18 live traces and the evaluation were verified. The arms have separate denominators; this compares a model with a handwritten reference, not a learned repair. The one failure did not meet the repeated-failure gate for another learning attempt.

## 1 Start the application

**Do this.** In a terminal, select a fresh directory for new work:

```sh
cd path/to/faultlab
./scripts/start-local.sh --data-dir "$HOME/FaultLab_Runs/my-workspace"
```

Use any folder outside the repository; it is created if needed.

This starts the simulator, backend and dashboard together with live execution disabled. Keep the
terminal open; Ctrl+C stops the services it started. The launcher refuses occupied ports before opening
stores. Stop an existing launcher before switching workspaces. Existing data is never moved automatically.
For a fresh installation, run `./scripts/setup.sh` once first; reuse an existing installed environment.
The services use ports 8001 (simulator), 8000 (backend) and 5173 (dashboard). If those are taken, export
`FAULTLAB_SIMULATOR_PORT`, `FAULTLAB_BACKEND_PORT` and `FAULTLAB_DASHBOARD_PORT` in every terminal you use
for FaultLab, then start again; the addresses below change to match.

To inspect existing history, select its directory explicitly with `--archive`. This starts a read-only
backend and dashboard without a simulator. See [local operation](local-operation.md) for independent
service commands and recovery behavior.

**Why.** Selecting the directory makes clear which saved experiments are being read and where new
worlds will be written. The simulator is needed only when executing a fresh task.

**Backend.** The launchers use the same application defaults: DeepSeek V3.1 for the Actor, DeepSeek V4 Pro 0813 for Explorer and Mechanic, and v4 indexed evidence for the reference Actor. Explicit process settings override `.env`; nonempty `.env` model values override defaults. Empty model placeholders from older `.env` templates use the tested defaults; an explicitly blank process model override still takes precedence. Existing `.env` files are never edited. Aria is off by default. Old frozen records keep their original configuration. The Phase 30 reporting hint is not included.

**Frontend.** Open `http://127.0.0.1:5173`. Look for **Backend connected** and **Current setup for new campaigns**. This configuration is separate from the selected saved campaign’s model. Loading the page makes no model calls.

**Local-only access.** The backend answers only requests addressed to `localhost`, `127.0.0.1` or `[::1]`, and accepts changes (uploads, runs, registrations) only from a page on one of those hosts. Other host names get HTTP 403, which stops a web page on another site from reading this store or starting a paid run through DNS tricks. If you deliberately use another local name, list it in the `FAULTLAB_ALLOWED_HOSTS` process variable (comma-separated) before starting the backend.

**Before a new paid run.** Confirm the remaining shared allowance in [current status](../CURRENT_STATUS.md), configure the chosen W&B entity/project and current verified prices in your private environment, then start the paired launcher with `--live` and the same explicit `--data-dir`. The live launcher uses a stable backend and permits live admission; it does not dispatch a campaign, supply old price assertions, or increase your allowance. The default per-campaign cap is $100. The verified-rate fields and exact pricing model IDs are listed in `.env.example`; they must match every configured role model. Use your own W&B entity and project (`WANDB_ENTITY`, `WANDB_PROJECT`), spelled exactly as in W&B; the project name is case-sensitive.

Older `.env` files with empty model placeholders now select the tested defaults without rewriting the file. If you choose a different model, set its name explicitly and check the displayed setup before creating a campaign. Never paste your key into the frontend or documentation. `/api/readiness` lists missing configuration names without contacting the provider.

## 2 Check the model connection

**Do this.** In a fourth terminal in the same application folder, run:

Replace `YOUR_WANDB_ENTITY` and `YOUR_WANDB_PROJECT` with your own W&B entity and project:

```sh
WANDB_ENTITY=YOUR_WANDB_ENTITY WANDB_PROJECT=YOUR_WANDB_PROJECT WANDB_MODEL='deepseek-ai/DeepSeek-V3.1' \
  ./scripts/smoke-sponsors.sh \
  --confirm-entity YOUR_WANDB_ENTITY \
  --max-output-tokens 2000
```

**Why.** This catches account and trace-connection problems before a longer experiment. It checks the same V3.1 task model selected above. The separate V4 Pro discovery role uses the documented thinking-disabled setting. The explicit limit matches the campaign's existing per-call ceiling. This is a paid connection check; the saved Phase 2 results already include successful live calls, so it is optional when your settings have not changed.

**Backend.** Verifies the model ID, makes one generation with a 20-second timeout and no automatic retry, then reads back its completed Weave trace. Success prints a response and actual trace link. Keys stay server-side.

**Frontend.** The result appears in Terminal. The dashboard does not create or start a campaign from this command.

**Check the ordinary order workflow.** Before fault testing, run:

```sh
./scripts/run-demo.sh --mode baseline --execute-live --wait
```

This checks whether the whole product can upgrade and confirm an order without injected faults. The backend calls the real model and local mock APIs, checks the final report and verifies its Weave trace. In the frontend, paste the printed campaign ID into **Open saved campaign** and click **Load recording**. A successful task has a `COMPLETED` outcome and eight passing checks; keep the actual result even if it differs. This is one healthy episode; the 36-trial research baseline is separate.

Model discovery is available with `./scripts/check-provider.sh wandb --list-models --confirm-entity YOUR_WANDB_ENTITY`. To switch models, also update matching verified prices and create a new campaign. Per-campaign caps are not an account-wide limiter: include all previous charges and the next planned batch in the shared allowance shown in [current status](../CURRENT_STATUS.md). Do not change source, settings or budgets during an experiment, or weaken compatibility checks to reuse a historical policy.

## 3 Create and start one learning run

**Do this in the dashboard.** In **Run desk**, choose **Execution profile → Live reviewed agent**, select and register the reviewed agent, then choose **Campaign mode → Learn**. Keep the supplied task and enter an order label such as `order-live-demo`. If playback is active, click **Exit playback**. Click **Create campaign**. Review the frozen plan, model and budget, then click **Start campaign** once.

**Why.** Create fixes what you are testing. Start explicitly begins the paid experiment. The supported task is order upgrade and confirmation; free text does not define arbitrary new tools or workflows.

**Backend.** Create saves the task, configuration, policy and limits. Start begins bounded model calls in fresh simulated worlds. Changing dropdowns later does not change that saved campaign. Each episode has limits including eight model turns and 90 seconds.

Runtime 2 asks for a strict final-report structure when the agent reaches its reserved report turn or has finished the business actions. The original and repaired agents use the same protocol and limits. FaultLab saves the model's original answer; it does not rewrite a bad answer into a good one. A correctly shaped answer can still fail if it cites evidence the agent never received.

**Frontend.** The campaign receipt shows recorded settings. Its state and reason change as work proceeds, and the evidence panels fill with saved results.

**Terminal reference alternative.** This legacy command creates and starts a reference-agent learning run. Use the dashboard's reviewed plan flow to select the native agent or a named baseline case:

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
| Propose | Mechanic receives the actual hook rules and prior candidate results, then proposes a constrained recovery policy or says no change. Duplicate candidates are saved without repeating their qualification. |
| Challenge | Attempts to break the candidate on four meaningful schedules with repeated paired runs. A failed candidate can feed another attempt. |
| Promote | Compares the candidate with the original policy on fixed cases. Acceptance requires sufficient improvement and preserved healthy behavior. |
| Save evidence | Saves outcomes and policy decisions. Reproduced incidents and failed challenges can become downloadable regression bundles before any policy is accepted. Eligible evidence is checked in Weave. |

**Frontend.** Watch **Fault × policy ledger**. Click an episode ID to open its original observations, report and **Fixed Referee verdict** in **Evidence timeline**. Use **Reproduce & reduce**, **Tested diagnosis** and **Adversarial challenge** to inspect the evidence behind a proposal. After selecting an older episode, reload the campaign with **Load recording** to follow its latest episode again.

**If the state is WAITING_EVIDENCE.** A Learn plan saved since September 29 declares an automatic evidence retry (rule `faultlab-evidence-retry/v2`). FaultLab retries the saved evidence by itself: at most 3 times per wait (30 s, 120 s and 300 s apart) and at most 6 times per campaign. These retries are telemetry only: no episode, business call or model request is repeated, and nothing is charged. When a limit is reached, the Run desk shows **Needs operator**. Its **Retry evidence sync now** button retries only the episodes that wait needs, blocked episode first. Older plans keep manual retry only: use **Retry evidence sync** for the campaign. Once the evidence is verified, the already-authorized learning loop may resume and make further model calls. **Stop** works at any time and ends the campaign as STOPPED. The terminal wait command returns at this state; continue watching the dashboard.

**If you need to stop.** Load the active campaign and click **Stop**. This prevents new work and preserves evidence. An already-dispatched request may have committed. **Recorded playback** changes how you view the record; it does not stop a running campaign.

## 5 Read the result and save it

**Do this.** Wait for the learning attempt to finish, then inspect the state and reason. `COMPLETED` and `NO_CHANGE` are final outcomes. Let the terminal wait finish or wait until Create campaign becomes available again. `REJECTED` and `PROMOTED` can be intermediate states while work continues. An infrastructure error is a test limitation, not evidence of improvement.

**Why.** A proposed rule, a passing example and an accepted policy are different outcomes. Saved comparisons establish which outcome you have.

**Backend.** Keeps every attempt, including rejected candidates and inconclusive results. The active recovery policy changes only after the promotion checks pass.

**Frontend.** The **Before and after · promotion evidence** panel compares only exact linked promotion pairs. Campaign totals also include discovery and diagnosis, so they cannot show repair gains. An incomplete comparison stays unavailable. In **Recovery policy → Immutable version**, select the relevant version. If a proposal exists, use **Read original model proposal** and **Policy content and complete provenance** to inspect its decision. Under **Sponsor evidence → Weave**, use **Open Weave trace** for a recorded remote trace. Aria remains pending in this walkthrough.

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

The backend reads saved records into JSON; the frontend continues displaying the same campaign. Export, reload and playback make no new model calls. If a regression exists, **Portable regression → Saved regression → Inspect saved bundle** opens it; **Download regression** saves its ZIP. **Run fresh regression** is a separate execution action. An **incident fixture** saves a failure; a **candidate comparison** saves a tested proposal; an **accepted policy bundle** means the promotion gate passed. A fresh run does not change a rejected policy into an accepted one. See [the regression guide](regression-runner.md).

## Historical Phase 2 incident commands

For read-only inspection today, open the saved Phase 2 campaign or execution ID in the dashboard. The commands below preserve the earlier runtime 2 procedure. The current Phase 3 runtime has a new configuration and contract identity, so reusing that old registration for fresh execution can correctly fail compatibility checks. Use a newly compatible export and registration for new execution; do not weaken those checks.

The commands need a saved regression bundle, the registration it was validated against and the
non-secret settings file of the backend that ran it. Replace `BUNDLE_DIR`, `REGISTRATION_ID`,
`REGRESSION_ID` and `SETTINGS_JSON` with your own. The team's runtime 2 registration is named in
[the Phase 2 experiment](part2/PHASE2_EXPERIMENT.md). Its incident B export and settings file are in the
team's git-ignored `artifacts/phase2-2026-09-20/` folder, which a fresh Git clone does not supply.

**Load the same settings in your command terminal.** Backend launch settings do not automatically carry into another terminal. From the repository root, define this helper once:

```sh
phase2() {
  .venv/bin/python -c \
    'import json,os,sys; os.environ.update(json.load(open(sys.argv[1]))); os.execvp(sys.argv[2],sys.argv[2:])' \
    SETTINGS_JSON "$@"
}
```

It loads only the saved non-secret settings for the command you supply. Credentials remain in the existing `.env`; the helper does not print or change them. It does not start any experiment by itself.

**1. Check the package.** This verifies the files, hashes and compatible registered agent. It makes no provider calls, but saves a local validation record.

```sh
phase2 ./scripts/run-regression.sh validate \
  --bundle BUNDLE_DIR \
  --agent REGISTRATION_ID
```

**2. Read the old trials.** This prints the archived results. It makes no provider or business calls and creates no fresh test world. Archive playback is not evidence that today's agent reproduces the old failure.

```sh
phase2 ./scripts/run-regression.sh playback \
  --bundle BUNDLE_DIR \
  --agent REGISTRATION_ID
```

**Optional: make another export copy.** This packages the same saved incident without running it. Choose an output directory that does not already exist:

```sh
phase2 ./scripts/run-regression.sh export \
  --regression REGRESSION_ID \
  --output artifacts/my-b-incident
```

**3. Only if you want another paid experiment, run three fresh trials.** The three-trial result above is already saved; this command starts an additional experiment. Wait until the backend has no active experiment, keep the simulator running, and check the remaining shared budget first.

```sh
phase2 ./scripts/run-regression.sh execute \
  --bundle BUNDLE_DIR \
  --agent REGISTRATION_ID \
  --profile sandbox-v1 --execute-live
```

The backend validates and imports the bundle as data, creates a separate baseline campaign and ledger, and runs the exact bundled empty policy in three new worlds. It preserves B's original record. It reserves 24 Actor turns, a $0.5016 conservative dispatched bound at the frozen V3.1 rates; a charged transport retry (at most one per turn) can add up to 24 more requests, so the worst case is 48 requests ($1.0032). Admission also preserves capacity for protected studies. This checks whether the incident happens again. It cannot promote a policy or prove a learned improvement.

The command returns a new execution ID. Read `http://127.0.0.1:8000/api/regression-executions/EXECUTION_ID` (use your `FAULTLAB_BACKEND_PORT` if you changed it) for its status and episode IDs, and keep every result. A completed execution does not itself prove remote trace verification. The targeted evidence-sync command below can verify its completed episodes in their new campaign. Add this campaign's charged bound to the Phase 2 total; do not count playback records as new model trials.

## After the first run

The walkthrough covers one learning campaign with Inference and Weave. Broader validation is tracked in `FaultLab_Specs/specs/001-faultlab-loop/tasks.md`, a folder beside the repository on the team's machine (not part of this repository):

| Task | Required evidence |
|---|---|
| T039 baseline study done | Runtime 2 C3 completed 36 B0/B1 trials with DeepSeek V3.1 and the handwritten reference; all live traces and the evaluation verified in Weave. |
| T065 learning | Repeated failure, tested diagnosis, generated repair, challenge and promotion evidence. Improvement must be measured. |
| T088 sponsors | Real Inference, Weave evaluation/dataset and automatic Aria analysis. Aria is deferred. |
| T097 freeze | Save the accepted policy and exact configuration before protected studies. Requires an accepted learned policy. |
| T100 external studies | Run exported failures on the independent agent; measure transfer and equal-budget fault selection. |
| T102 final audit | Run the sealed 72-episode comparison and retain all results. Do not tune the policy from audit results. |

**Historical verification: September 20, runtime 2.** 471 backend tests, 61 frontend tests, the production build and three browser fixture tests passed. Manual inspection of the actual dashboard after restart verified the saved-execution workflow above; the opt-in automated actual-server smoke was skipped. C2, C3 and the fresh B incident are complete; no learned repair was accepted. Phase 2 retained 149 episodes (131 live and 18 offline), 886 model calls including four schema probes, and 131 verified live episode traces. Its conservative dispatched bound is $18.92256; the estimate from known token usage is $1.77596. Actual billed dollars are unavailable. See [Phase 2 results](part2/PHASE2_RESULTS.md) for experiment IDs and remaining gates. These are separate from the preserved [Phase 1 results](part2/PHASE1_RESULTS.md).

The startup example uses the frozen Phase 2 model roles, not a claim that they are the best available models. An accepted learned policy is still required before its restart persistence, protected final evaluation or independent-agent transfer can be demonstrated. The native smolagents baseline is already recorded in Phase 1; a baseline alone does not establish transfer.

**Large evidence histories.** A campaign-wide retry currently has a 60-second deadline and can spend it rereading already-verified traces. If that happens, use the API's targeted retry with only the missing completed episode IDs; it does not rerun business actions. For example, replace the placeholders (and port 8000, if you set `FAULTLAB_BACKEND_PORT`) and send:

```sh
curl -s -X POST http://127.0.0.1:8000/api/campaigns/CAMPAIGN_ID/retry-evidence \
  -H 'Content-Type: application/json' \
  -d '{"episode_ids":["MISSING_EPISODE_ID"]}'
```

The returned request ID can be checked at `http://127.0.0.1:8000/api/evidence-retries/REQUEST_ID`. Do not count a queued retry as verified. Larger batches can be split; do not include invalid/ineligible trials as proof of a repair.

The older [learning results](learning-results.md) and [sponsor results](sponsor-results.md) remain historical records. Stop service terminals with Ctrl+C when finished; local history remains saved.
