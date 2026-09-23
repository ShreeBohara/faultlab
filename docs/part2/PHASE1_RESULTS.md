# Phase 1 results — September 20, 2026

Status: Phase 1 implementation and bounded end-to-end validation completed. The testing, evidence and incident-rerun workflow is verified. **No learned policy was accepted.** The original measured promotion, audit and transfer gates remain open.

## What changed

The repair model now receives the actual timing and limits of its hooks, previous candidate contents and hashes, and cumulative source/challenge results. Repeating an identical candidate under the same source context does not buy another qualification attempt. A flaky original failure is recorded separately from a failed candidate.

Experiments now fingerprint the learning/evaluation code and the full backend runtime. Each campaign also records its Git revision and whether executable source differs from that revision. Report exhaustion and deadlines have matching terminal classifications locally and in Weave. Startup readiness can check the simulator without model calls, and unexpected errors retain a safe cause.

A reproduced failure can become an incident bundle before promotion. A failed challenge can become a candidate comparison. Archives contain public timelines, original reports, related proposals and exact configuration identities; private and protected cases stay outside them. Trusted execution can rerun the exact rejected candidate without accepting it. Older bundle hashes remain valid.

## Verification

- 422 backend tests passed.
- 34 frontend tests passed; production build passed.
- Three browser tests passed. The optional actual-server automated smoke was skipped in that suite; the actual dashboard workflow was subsequently checked through the browser: create/run one offline baseline, reload, read-only playback, inspect an incident, select the exact registration/policy, and execute three live regression trials.
- A copied historical campaign exported all 143 public episodes, 2,086 events, three attributable proposals and four policies. Its source and failed-challenge archives passed integrity inspection. This was read-only validation, not new execution.
- V1 source fingerprints and a code/schema archive are saved in `artifacts/phase1-2026-09-20/frozen-source.json` and `frozen-runtime.zip`. The later trace-factory fix is preserved as `frozen-source-v2.json` / `frozen-runtime-v2.zip`. Runtime V2 remained unchanged throughout its live experiments.

## Fixed live baseline

Campaign: `campaign-ccb81465bd8b46a098c178afd55d98b1`.
Study: `baseline-study-5cb59c29c888476b89a2356189cea72f`.
Configuration: `f22aab0be282e5e556e947b403b99129e108dcf09da22d259fbf1705ad773126`.

Six predeclared development cases, three repeats per arm; all 36 trials were valid and all 30 scheduled faults triggered.

| Arm | Trials | Completed task | Correct rejection | Rule violation | Infrastructure error |
|---|---:|---:|---:|---:|---:|
| V3.1 task agent, empty policy | 18 | 10 | 3 | 5 | 0 |
| Handwritten reference | 18 | 15 | 3 | 0 | 0 |

All five model violations had no final report after eight Actor calls, failing C5/C6/C7. Two followed delayed upgrades; three followed temporary notification failures. All three healthy model trials completed. These results measure this fixed development study; they are not a learned-repair effect or general accuracy estimate.

All 18 model traces and the [B0 evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a0bfbb-de9d-77df-8e02-4eeaf16db059) were verified through remote readback. The handwritten arm is explicitly local/offline.

100 model requests. Measured usage: 309,922 input and 6,050 output tokens. Rate-derived estimate: $0.18044. Conservative admitted request bound: $2.09. Actual billed dollars were not returned by the provider.

## Interrupted learning attempt

Campaign `campaign-0ff8bbf4a8104e4ca07d8d7ad5fda345` completed six discovery episodes with verified traces, then stopped on an Explorer `APIConnectionError`. No repair was proposed. Its one rule-breaking episode had an untriggered schedule and was correctly ineligible for reproduction. The interrupted attempt and one request with unknown usage remain recorded and charged conservatively: $0.99678 admitted bound.

The model-list connection succeeded afterward. Amendment 1 in [the experiment declaration](PHASE1_EXPERIMENT.md) authorized a separately recorded replacement under the same runtime/models/gates and a smaller remaining campaign cap. No successful outcome is inferred for the interrupted attempt.

## Corrected learning and follow-up

Campaign `campaign-2fdef056b7604ba0bc91a33a656595d1` finished NO_CHANGE after 38 learning episodes and 271 model requests. All 38 learning traces were verified after an explicit saved-evidence sync. One C5 source reproduced three of three times and was reduced; a controlled intervention supported POLICY_GAP. One unique generated policy then failed all three source pairs. Three later proposals returned the same policy hash and were saved as duplicates without more qualification trials. Challenge and promotion were correctly not reached.

The proposed policy put its recovery steps on hooks that the Actor never reached before exhausting its turns. The only executed policy step checked for a receipt; it did not recover or close the episode. The later explanations claimed nonexistent edits. Cumulative feedback reached the model within the token limit; no evidence supports silently repairing the generated JSON.

The new incident bundle passed integrity inspection and its 22 public source/reduction trials were published as a verified Weave dataset. A fresh trusted regression completed three distinct worlds and reproduced C5 three of three times with 24 calls. It also exposed a missing parent trace in the registered-reference factory, so those three historical reruns cannot be verified in Weave. The factory has been corrected to reuse the existing traced prototype entrypoint; native tracing already used the wrapper. Neither original reports nor historical spans were rewritten.

Learning alone charged a $5.86648 admitted bound; the fresh regression added $0.50160. The separately declared alternate-Mechanic experiment and native baseline used the corrected V2 runtime; their results follow below.

The execution checklist is [PHASE1_TASKS.md](PHASE1_TASKS.md). The original five measured hackathon gates remain separate and are not closed merely because software tests pass.

## Independent native smolagents baseline

Campaign `campaign-9581a7e140474e0889bb789c93b02f7d`, configuration `6fed89323aea3bf52e0d7d143c4af4fe86e4d6b38e2542dfd92802b458d61358`. Native smolagents 1.26.0, V3.1 model, unchanged empty policy, six public development cases with three trials each. Original reports were retained.

All 18 planned trials ran: eight completed, eight violated rules, two were safe-unresolved. All three healthy cases passed and all 15 scheduled fault cases triggered; no infrastructure errors occurred. All 18 episode traces and the [native evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a0bfcf-38bd-74b2-941b-ac3b7a682ca4) were verified. This establishes a working independent-agent baseline, not transfer of an accepted repair.

106 model calls, 424,709 measured input tokens, 6,213 output tokens; $0.2438414 token-price estimate and $2.2154 conservative admitted bound. The first setup attempt failed provider-free readiness before creating a trial because the separate artifact directory changed the control-capability location. The harness now resolves the existing simulator capability before changing its output location. Both attempt directories remain saved; the rejected preflight made zero model calls.

The exact executed harness and complete records are saved under `artifacts/phase1-2026-09-20/native-baseline-2/`. CI now runs the existing full offline checks without credentials; the workflow has not yet run on GitHub.

## Alternate Mechanic follow-up

Campaign `campaign-9e7f10cd29ea4eb2b41ad158e262ec5c`, configuration `abd6b5f985660bc263e65cc2308e0e457b605d7b5517212d532a66c58e08fd58`. Actor and Mechanic: V3.1; Explorer: V4 Pro 0813. Source, episode limits and qualification rules remained fixed.

The learning portion made 837 model calls and recorded 121 trials: 56 completed tasks, 64 rule violations and one provider timeout marked LAB_ERROR. Five of eight discovery slots ran before budget admission stopped further work; all attempts remain recorded. Four failures reproduced and were exported as incident fixtures with verified Weave datasets. Three diagnoses were inconclusive because fresh controls or treatments varied; the fourth supported POLICY_GAP.

No policy proposal ran in this follow-up. At that point, the existing protected studies and full candidate batch required $79.84368 in reservation headroom, in addition to $17.638 already charged conservatively. The required $97.48168 exceeded this campaign's remaining-allocation cap of $88.32. The system stopped NO_CHANGE before dispatching the proposal. The known-token estimate for learning was about $1.57, with one request's usage unknown; this was a conservative admission limit, not proof that those dollars were billed or that account credit was exhausted.

All 120 eligible completed learning episodes were verified in Weave. The timeout remains an invalid trial and is ineligible for optimization evidence. This experiment does not compare the two Mechanic models' repair quality: it used independently discovered cases, and the alternate model never reached policy generation. Full diagnosis and budget details are in [PHASE1_FOLLOWUP.md](PHASE1_FOLLOWUP.md).

## Final fresh regression and actual dashboard check

Using the dashboard, selected incident `regression-ca8303126316441099c9dde0f590f13c`, registration `orders-v1-abd6b5f985660bc2` and unchanged `policy-v0`. Execution `execution-ff9805b8329542aba6c030fe09a4d75f` completed three fresh worlds with 24 model calls and 21 HTTP attempts. **Two trials reproduced C5 violations and one completed successfully.** All three corrected parent traces and their tool evidence were verified. Fresh execution does not imply a repair; the different outcome confirms observed variability.

The incident archive has nine files, passes integrity/target compatibility checks, and matches the dashboard download. Manifest hash: `41a598e99d056468f37af08fe6bb146ba73d331e84c149310fcfb722c26f9c21`. Its ZIP is `artifacts/phase1-2026-09-20/followup-source-incident.zip` (55,322 bytes; SHA-256 `8c5d2d9ec3dc5d4ba5f828247f7b7266d7b44168f13d8a090d97dcb456698ef9`). It can be copied to another machine and inspected with the trusted runner; execution requires the reviewed runtime and configured access. Local artifact folders are ignored by Git and do not automatically accompany a clone.

The actual browser smoke campaign `campaign-81c9cd7e7b9e41819abe6f3711079c9a` completed one offline trial in a fresh world with zero model calls. Reload and read-only playback preserved the same campaign/world and disabled execution controls. The new registration labels expose model and registration ID so the user can distinguish historical configurations. The completed fresh-regression panel was left open in the dashboard.

## Total accounting and evidence

Across all Phase 1 stores: **226 recorded episodes**, including 19 explicitly offline/reference episodes; **1,400 model requests**; **203 verified model episode traces**. The four remaining model episodes are three preserved V1 regressions with no parent span and the one ineligible provider timeout. Two failed requests have unknown token usage: the interrupted Explorer call and the Actor timeout. None were silently discarded or charged as free.

- Cumulative conservative bound for dispatched requests: **$29.80986**, within the declared $100 ceiling.
- Price estimate from known measured token usage: **$2.780649**; incomplete for the two failed requests.
- Actual provider-billed dollars: **unavailable**.
- Baseline evaluations and five newly exported incident datasets were verified. Aria publication was explicitly deferred.

The retry of the entire 121-trial campaign hit its existing 60-second job deadline after rereading 25 already verified episodes. A targeted retry of the four still-unverified completed episodes (including the three fresh regressions) completed successfully. This readback made no new model or business calls; the timed-out retry remains recorded.

## What remains and what to do next

The implementation is ready for the next phase; reliable automatic improvement is still unproven. T065, T088, T097, T100 and T102 remain open in the original specification. No promotion, accepted-policy restart, protected final audit, unchanged-policy external transfer or equal-budget search advantage is claimed.

The next repair experiment should first measure repeatability on fixed public delay cases across fresh worlds/identities. Then test report completion and the allowed repair interface under a separately versioned baseline/candidate comparison. Preserve the current results and the untouched evaluation cases. Do not keep rerunning the same failed candidate until a lucky batch passes.

Before another large campaign, plan reservation headroom explicitly. The current ledger reserves every future request at the most expensive role rate, which can block development early. Any more precise role-specific reservation design needs its own budget-safety checks; increasing the spend ceiling is a separate decision.

Other follow-up work: make large evidence retries skip verified records or continue from pending ones; retain invalid native model attempts safely; add native-agent selection and baseline-study summaries to the main dashboard; carry a reviewed sample archive in releases; execute the added CI workflow on GitHub. Historical Aria publication-intent recovery remains unresolved and was not exercised in Phase 1. The current UI and local API remain a localhost tool, not a shared hosted execution service.

## Where to look

- [Current checklist](PHASE1_TASKS.md)
- [Experiment declaration and amendments](PHASE1_EXPERIMENT.md)
- [Native agent results](PHASE1_NATIVE.md)
- [Follow-up diagnosis and budget analysis](PHASE1_FOLLOWUP.md)
- [Updated quick start](../user-guide.md) and [trusted regression commands](../regression-runner.md)

All original records were retained. The final local artifact folder contains the source snapshots, before/after databases, complete public recordings, incident ZIP, trial/trace proof and cumulative accounting. The changes are local; no new GitHub push or deployment was performed for this phase.
