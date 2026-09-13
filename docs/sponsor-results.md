# Connected sponsor results

Status: Inference, connection trace and both completed campaign root/tool trace readbacks VERIFIED. Live evaluation and regression dataset were not reached because no source qualified for repair. Aria automation and analysis are explicitly deferred by the user. T088 remains open.

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
