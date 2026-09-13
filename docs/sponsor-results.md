# Connected sponsor results

Current status: real Inference, completed campaign root/tool readbacks and a full 36-case baseline Weave evaluation are VERIFIED. DeepSeek V4 Pro-0813 with thinking disabled is the current selected model. Regression dataset and automatic Aria evidence remain pending; Aria is explicitly deferred. Historical checks are preserved below. T088 remains open.

The user authorized model discovery and a bounded smoke check for `shreetbohara-quinstreet/faultlab`, then one full learning cycle up to $100. W&B returns the canonical project as `shreetbohara-quinstreet/Faultlab`; the live launcher supplies that exact case without editing the existing `.env`.

## Actual checks on 2026-09-12 Pacific

- Model listing succeeded and included `openai/gpt-oss-120b`.
- Initial smoke failed before generation because Weave's log-level environment value was lowercased. This SDK configuration bug is fixed and covered by a real installed-SDK regression test.
- The next 32-token smoke made one generation attempt and retained a failed response check. Its completed trace has ID `01a0984b-370b-7424-aded-2252d32f2368`; a project-case mismatch also prevented the original CLI from accepting its readback. No usable answer or successful inference was claimed. Exact returned usage was not retained by that old check; the response failure reason cannot be reconstructed from the sanitized trace.
- A single explicit readiness generation at the existing campaign ceiling of 2,000 output tokens succeeded. W&B returned model `openai/gpt-oss-120b`, `finish_reason=stop`, 78 input tokens, 78 output tokens and valid JSON. The completed trace was read back successfully: [verified connection trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a0984d-b15c-7f42-9537-675e866d1883). Local machine-readable record: `artifacts/live-runtime-readiness.json`.

GPT-OSS is available in W&B's [current model catalog](https://docs.wandb.ai/inference/models). W&B's [token pricing](https://wandb.ai/site/pricing/tokens/) listed $0.03 per million input tokens and $0.17 per million output tokens when verified. The campaign reserves at most $0.00058 for each 8,000-input/2,000-output-token call. This is a conservative inference admission charge, not a billing receipt or a limit on unrelated account costs. Rates must be rechecked when changing the model or repeating this later.

## Software fixes and remaining evidence

The pinned Weave SDK's actual evaluation summary envelope and dictionary/list wrappers are now handled, with offline regression coverage. SDK initialization and exact existing-call retrieval have succeeded remotely. These facts alone do not establish a real campaign evaluation or dataset upload.

The first live campaign was stopped after two early infrastructure errors; all records remain in `artifacts/live-attempt-1-evidence.json`. A third interrupted episode reached the mock APIs. Diagnosis and subsequent execution are recorded in `docs/learning-results.md`.

Aria setup, Finished-run publication and automatic analysis remain pending by explicit user choice. Without registered observed automation setup, the completion bridge does not publish a Finished run. Weave remains enabled independently.

## Final campaign trace readback

The corrected campaign finished NO_CHANGE. Both eligible completed-lifecycle episodes were verified through the actual SDK worker and evidence gateway, including exact project/campaign identities, tool hierarchy and equality with saved observations/reports. Seven calls were retrieved: two roots plus five tool children. The successful order [trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/d49c1470-7ef1-433d-a581-5cd0668a7e3e) and C5 violation [trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/6daec6dd-2846-45f9-8587-f346b24aa8fb) remain distinct. The bulk SDK query returned duplicate rows; reading the bounded exact inventory resolved verification while preserving strict comparison. This does not establish a campaign evaluation, dataset or Aria analysis, so T088 remains open.

Final handover verification: evidence retry `evidence-retry-16ab70b2c38b49a0bbc526880b8b2f93` completed with two VERIFIED episodes and six SKIPPED_INELIGIBLE episodes. Matching saved calls were reused; no inference or business rerun occurred. Final evidence export: `artifacts/live-end-to-end-final.json`. The final telemetry suite passed 68 tests; T116 is checked, for 110/116 tasks complete. Aria remains awaiting setup as requested.


## Live validation on 2026-09-13

The Llama baseline study completed all 36 predeclared trials with no infrastructure errors. The actual [Weave evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a09b7b-1890-78da-b9f9-1d7c162daf23) was read back and matched fixed local scores. All 18 real model episode roots were verified. This completes T039; it does not replace the separate generated-policy dataset or Aria requirements.

After comparative request checks, the default switched to `deepseek-ai/DeepSeek-V3.1`. Its healthy campaign passed C1-C8 and its [actual root/tool trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/c34e9ec6-8016-499b-8d8d-9c2bac5184f1) was verified. The current learning result and subsequent sponsor evidence are recorded in `docs/learning-results.md`.


The exact DeepSeek smoke command in the updated quick start also passed, returning “FaultLab connection OK” and a [verified completed connection trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a09b93-a428-7fdd-aaf6-a6a3e8aac193). This was a separate explicit connection request, not a learning trial.


The V3.1 learning campaign completed with all 119 episode trace bundles verified and no provider errors. Its four controlled diagnoses were inconclusive; no regression dataset was eligible. V4 Pro’s exact quick-start connection command passed with [verified Weave readback](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a09bb0-f093-7152-b0c7-350facb29a2f). Final V4 results are recorded in `docs/learning-results.md`: 44 model calls, no provider errors, eight verified episode traces, and NO_CHANGE with no qualified repair.

The V4 healthy order has a [verified completed root/tool trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/9f61ce4d-410c-4a4e-b4e2-b8e856e398fc). The final V4 campaign preserved all eight verified traces; no generated-policy evaluation/dataset or Aria pass is claimed.


## Aria automation: registered, fired automatically, analysis observed (2026-09-13)

The Aria gate moved from "deferred" to an automatic invocation that is verified against W&B's own API. It is
not yet a complete T088 pass; the remaining gap is stated at the end of this section.

**Observed automation.** `Test-final`, automation id `VHJpZ2dlcjo5MTQ5`, project-scoped to
`shreetbohara-quinstreet/Faultlab`, enabled, created by Shree Bohara in the W&B UI. Event: run status change
restricted to `FINISHED`, with the run-name filter `^faultlab-campaign-.*`. Action: `Trigger ARIA`. The stored
prompt was read back through the W&B GraphQL API and compared byte-for-byte against `ARIA_PROMPT` in
`backend/app/telemetry/aria_bridge.py`; it matches exactly (1,266 characters). The run-name filter, the
`FINISHED` state and the enabled flag were verified the same way. Readback: `artifacts/aria-automation-readback.json`.

The W&B SDK (0.30.0) cannot see project-scoped ARIA automations: `Api.automations()` returns zero for every
call form, and there is no executable GraphQL client on that build. Verification therefore used direct HTTPS
GraphQL calls. Registration was recorded with `python -m app.cli.sponsors register-automation`, which returned
`observed_setup_recorded` with `invocation_performed: false` and `remote_verification: false`.

**Published Finished run.** `faultlab-campaign-campaign-63933675566f49a994eb3e5bb6145434`, run id
`fl825f412b6fa2d6ae35550b786c35e5`, published 2026-09-13T19:50:39.986811Z and confirmed in state `finished`:
[run](https://wandb.ai/shreetbohara-quinstreet/Faultlab/runs/fl825f412b6fa2d6ae35550b786c35e5). It carries the
18 verified development Weave links and the evidence table for campaign
`campaign-63933675566f49a994eb3e5bb6145434`.

**Automatic invocation, verified.** Trigger execution `VHJpZ2dlckV4ZWN1dGlvbjo2NzQwMjI=` (decoded
`TriggerExecution:674022`), state `FINISHED`, `actionStartedAt` 2026-09-13T19:50:40Z, action duration 485 ms,
`triggerID` `VHJpZ2dlcjo5MTQ5`. The event payload records `eventType: RUN_STATE`, `entityName:
shreetbohara-quinstreet`, `projectName: Faultlab`, `runName: fl825f412b6fa2d6ae35550b786c35e5`,
`newRunState: FINISHED`. The action payload shows the prompt with `${run_name}`, `${entity_name}` and
`${project_name}` resolved to the real run and project. Aria replied HTTP 202 `Accepted` with
`thread_id` and `turn_id` `01a09c52-640e-7590-b61e-49b2c3a1657a`. Readback: `artifacts/aria-execution-readback.json`.

The 202 and the 485 ms duration are a dispatch, not an analysis. Automatic invocation is therefore established
by these records; Aria producing useful output is established separately by operator observation below.

**Observed Aria output, and its measured inaccuracy.** The operator read the resulting Aria conversation in the
W&B UI. Aria produced a substantive analysis: it reported 13 completed, 3 correctly rejected and 2
checker-level violations, declined to credit any successful repair because the adversarial challenge batch was
incomplete, and questioned records carrying `PROTOTYPE_EXCEPTION`.

Checked against saved records, Aria's denominators are wrong for this campaign. The campaign holds **36**
discovery episodes: 28 COMPLETED, 6 CORRECTLY_REJECTED and 2 VIOLATION, with **zero** LAB_ERROR lifecycles and
zero `run_episode` traces carrying a LAB_ERROR terminal status. Aria's counts match the 18 published Weave
links rather than the episode set, so it analysed roughly half the campaign. Both violations are genuine, each
with a delivered report whose own `overall` was `SAFE_UNRESOLVED`. Aria's advisory output changed no policy,
checker rule, budget or promotion decision, as required.

**What is still open for T088.** The attributed Aria capture (`POST /api/campaigns/{id}/aria-evidence`) needs
the conversation output URL and an operator summary before `status: COMPLETED` is permitted; until then no
completed automatic analysis is claimed. Publication was operator-initiated (`artifacts/publish_campaign_run.py`)
rather than produced by the coordinator's end-of-campaign hook, and `aria_bindings` was written manually to
mirror the coordinator's own binding step. Both deviations are recorded here rather than implied away.
