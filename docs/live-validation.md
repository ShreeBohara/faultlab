# Live validation sequence

Run commands from `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab` with the simulator and live backend running. The beginner walkthrough is `docs/user-guide.md`. `./scripts/start-live-backend.sh` preserves the existing `.env` and supplies the verified model, canonical project, rates and caps. Live commands below consume credits; read-only status, export and freeze commands do not call models.

The current authorized scope is one full learning cycle with Inference and Weave, up to $100. Model discovery and a completed connection trace succeeded; see `docs/sponsor-results.md`. Aria setup is explicitly deferred and is not needed to start this walkthrough. The sequence below also covers broader acceptance studies, which remain separate from the current single-campaign test.

The $100 setting is **per campaign**, not a shared session or account cap. The baseline study, learning and a separately imported regression can create different campaigns. Track total spending across them; do not assume several $100 campaign ceilings add up to a $100 overall ceiling.

## 1 Verify the account

The user confirmed the credited project. W&B returns its canonical name as `shreetbohara-quinstreet/Faultlab`. Run model discovery and an explicitly bounded check:

```sh
./scripts/check-provider.sh wandb --list-models --confirm-entity shreetbohara-quinstreet
WANDB_PROJECT=Faultlab WANDB_MODEL='openai/gpt-oss-120b' \
  ./scripts/smoke-sponsors.sh --confirm-entity shreetbohara-quinstreet \
  --max-output-tokens 2000
```

The default smoke check caps output at 32 tokens. The explicit 2,000-token override above accommodates GPT-OSS reasoning and matches the existing campaign ceiling. It still makes only one generation with a 20-second timeout and no SDK automatic retry. It also verifies a completed Weave call. This is a connection check, not full T088 campaign acceptance.

## 2 Measure the original agent for T039

```sh
./scripts/run-baseline-study.sh --execute-live --wait
```

This creates an independent live baseline campaign and runs six frozen development cases with three fresh pairs of B0 (model, empty policy) and B1 (handwritten reference): 36 episodes. It reserves up to 144 B0 actor calls while protecting later-study capacity. It never generates or promotes a policy. Save the returned campaign/study IDs and results, including failures and inconclusive runs.

Read status later without execution:

```sh
./scripts/run-baseline-study.sh --status STUDY_ID
```

The dashboard's **Run baseline** button runs one healthy smoke episode; it does not replace this study. Full baseline-study counts appear in the CLI/status JSON, separately from the ordinary campaign matrix. Record results in `docs/baseline-results.md`.

## 3 Attempt learning for T065

```sh
./scripts/run-demo.sh --mode learn --execute-live --wait
```

Load the campaign ID in the dashboard. The loop finds a failure, repeats it three times, tries smaller fault schedules, tests a diagnosis, proposes a policy, challenges it on four schedules with three paired trials each, and uses fixed promotion cases to decide whether to keep it. No change, rejected repair and insufficient evidence are valid recorded outcomes. Claim improvement only if the measured results support it.

Use **Retry evidence sync** for saved trace outages; it does not repeat completed business calls, but verified evidence can resume the already-authorized learning loop and future model calls. Save the original proposal, source/reduction/diagnosis/challenge results and accepted or rejected decision in `docs/learning-results.md`.

## 4 Complete sponsor evidence for T088

Aria is deferred for the current walkthrough. To complete this gate later, set up the reviewed W&B Finished-run automation before a future development campaign finishes. Verify actual Weave roots/tools, fixed-score evaluation and versioned regression dataset, then the finished W&B campaign run and automatically triggered Aria history/output. The **Sponsor evidence** form records observed output and source links. A manually started Aria conversation does not satisfy automatic invocation. Record references in `docs/sponsor-results.md`.

## 5 Freeze the learned policy for T097

After a completed campaign with an accepted policy, freeze its exact policy, model, prompt, budgets, source, scorer and sealed manifests:

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli.freeze --campaign CAMPAIGN_ID
```

Freeze is a local bookkeeping operation. The final/external studies reject a missing or mismatched freeze. If there is no accepted policy, record the missing learned arm; do not substitute an empty baseline. Do not tune the policy after reading final or external results.

## 6 Validate reuse and search for T100

Export a generated regression, inspect it without effects, then explicitly run three new trials on a registered target. The external target is the reviewed native Hugging Face smolagents adapter.

```sh
./scripts/run-regression.sh export --regression REGRESSION_ID --output artifacts/my-bundle
./scripts/run-regression.sh validate --bundle artifacts/my-bundle
./scripts/run-regression.sh register --agent smolagents
./scripts/run-regression.sh execute --bundle artifacts/my-bundle \
  --agent REGISTRATION_ID --profile sandbox-v1 --execute-live
./scripts/run-portability.sh --campaign CAMPAIGN_ID \
  --agent REGISTRATION_ID --execute-live
./scripts/compare-selectors.sh --campaign CAMPAIGN_ID --execute-live
```

Replace every uppercase placeholder with its returned ID. Run one fresh activity at a time. External transfer uses six cases with three B0/L pairs each (36 episodes), keeping the accepted policy unchanged. Selector comparison uses eight selection slots per method and three trials per valid selected scenario; retain invalid/duplicate selections and report actual trial denominators.

Fresh regression execution returns an execution ID. External/selector requests return queued request IDs; they do not wait for completion. Inspect results in the dashboard/API and record them in `docs/portability-results.md` and `docs/search-comparison-results.md`. An unavailable result remains pending; the command's acceptance is not completion.

## 7 Run the sealed audit for T102

```sh
./scripts/run-audit.sh --campaign CAMPAIGN_ID --execute-live
```

This queues eight frozen cases with three trials each for B0, B1 and L: 72 episodes. It requires the accepted policy and matching freeze. Save the returned batch ID; read `/api/audit-results/BATCH_ID` for persisted status. Retain all outcomes and report denominators, uncertainty and overhead in `docs/final-results.md`. Do not rerun until results look favorable or use audit feedback to repair this frozen policy.

Finally, export the campaign's saved evidence and update the six task checkboxes only when their actual required evidence is present. An empty dashboard panel or a passing offline test is not a substitute for a completed live experiment.
