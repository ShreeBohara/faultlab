# Service-reliability follow-up — September 27, 2026

Declared before execution. This is one new public compatibility measurement after a specific
software fix. It cannot revise or complete an earlier experiment.

## Why this measurement exists

The first September 27 compatibility run stopped after 16 attempted episodes because W&B returned
HTTP 503 on a baseline `upgrade-2` model request. Fifteen episodes completed with verified trace
readbacks; 26 slots were never attempted. Its outcome remains **INCOMPLETE**. It charged 81 model
requests, conservatively $1.6929, carried upward as $1.70. Original files, protocol, plan and results
remain at `artifacts/runtime-replication-2026-09-27/` and the verification preparation directory.

W&B documents 503 as temporary service unavailability and recommends a short delay before retrying:
[official guidance](https://docs.wandb.ai/support/inference/articles/api-error-code-503-the-engine-is-current).
The observed diagnostics identify status 503; they do not identify the provider's exact internal cause.

The new implementation permits one blind retry after a one-second asynchronous delay, only on
HTTP 503 with no returned generation. It shares the existing two-attempt limit for each Actor turn.
The retry must pass the existing deadline, stop, model-call, token and dollar admission checks.
Repeated 503s, other HTTP statuses and any returned generation receive no additional retry under
this change. Existing connection/timeout retry behavior and bounded in-episode format feedback
remain as before. No model, prompt, tool, scoring rule, policy content or episode limit changes.

## Fixed design

- Use the same exact historically selected policy: Phase 28 attempt 5, study
  `completion-study-a0c535bb041c413da1d4b34fb513252c`, version
  `policy-f4c2ec3f3356401b818c68c97eb9f0f4`, hash
  `04721232187d99677e698ce59b45ccd76ad2cb7c43854eff4c6a1e46163c548c`.
  Selection remains the first strong historical qualification; no selection uses the partial run's outcomes.
- Compare with the unchanged empty baseline on all seven public `upgrade-v1` cases in their original
  order, three pairs each: **42 episodes in 42 new worlds**. The exact cases, seeds and alternating
  arm order are specified in the [first declaration](CURRENT_RUNTIME_REPLICATION_2026-09-27.md).
  Its case and source-identity definitions are reused; its closed execution is not resumed.
- Actor: `deepseek-ai/DeepSeek-V3.1`, indexed evidence context v4. Configured Explorer/Mechanic remain
  `deepseek-ai/DeepSeek-V4-Pro-0813`, with zero calls to either. Aria remains off. Destination:
  `shreetbohara-quinstreet/Faultlab`. The Phase 30 report hint remains unadopted.
- Keep the existing eight-turn, 90-second episode caps. Including blind retries, the maximum is
  42 × 8 × 2 = **672 charged model requests**, 22,848,000 conservatively reserved tokens, and
  **$14.0448** at the verified $0.55 input / $1.65 output per million tokens and 32,000/2,000 token caps.
  Phase spending cap: **$20**. No whole-pair or whole-episode retry; no fallback model or policy.
  The carried allowance is now **$813.40 / $1,000**, leaving $186.60; added account funds are not
  needed to admit this run. Preserve actual token measures separately from provider-billed cost.

## Admission, execution and inspection

Use `scripts/experiments/run_service_reliability.py` with this protocol and a new sealed plan.
It is an exact copy of the first reviewed runner with one literal change: `DEFAULT_OUTPUT` now
points to this experiment's fresh directory. All source selection, scoring, provider-role guards,
budget checks and integrity logic are identical. Its own file identity is frozen in the new plan.
The original runner remains unchanged at SHA256
`b6818a715b0e6f9b925d89cd837646258e4e1119e40c7aa37f3b939341c886ac`;
it deliberately refuses any other output directory and therefore cannot launch this follow-up.
Both entry points must pass the same offline admission/integrity tests. Preserve the original
37-test log and separately record the expanded two-entry-point suite.
Execution output must be the previously nonexistent
`artifacts/service-reliability-2026-09-27/` directory; preparation stays outside that directory.

Before execution, complete the focused retry tests, full backend suite and independent code review.
Freeze this protocol, the new entry point and unchanged helpers, the new runtime/configuration hashes, source
identity, exact prices, output path and tests in an external record. Use the project Python for all
fingerprints: system Python can emit a different AST representation for identical source files.
Restart the simulator on the new frozen checkout with the 75-second keep-alive. Keep the dashboard
and ordinary backend closed; the isolated runner reserves port 8000. Read historical records
read-only and write only to the new experiment store and new simulator worlds.

Run once. Preserve every attempted slot, provider failure, original answer, trial and budget debit.
Continue the fixed batch through scored agent failures and untriggered faults; the latter make the
comparison incomplete. Stop on unrecovered infrastructure error, lost integrity, cancellation,
changed source/pins or exhausted admission. Never retry a whole pair or resume this directory.
If this run is incomplete, finish its analysis; this declaration authorizes no further live retry.

Verify exact lab/world attempt identities, real shop effects, original model answers and citation
boundaries, policy-generated tool requests, fault triggering, clock alignment and Weave readbacks.
Require nonzero coverage and 42 complete paired episodes for a complete measurement. Report missing
slots and verification gaps explicitly. A real 503 need not occur: if none does, say the retry branch
was checked in controlled fault injection, while the live run verifies the updated integration only.

## Interpretation

This is one existing policy on known public cases, under a newly identified runtime. Report the
first incomplete run separately, with its cost. Do not pool it into the new outcome or replace its
failed request. Completed execution and successful task outcomes are separate facts. Neither run
provides new learned-repair yield, unseen generalization, policy certification or `ACCEPTED` evidence.
The baseline remains active. Shop de-duplication and absent notification-fault coverage remain limits.
