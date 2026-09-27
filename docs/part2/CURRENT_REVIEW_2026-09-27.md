# September 27 independent review and live compatibility results

This note adds current findings without rewriting closed historical experiments.
The continuation entry point is [CURRENT_STATUS](../../CURRENT_STATUS.md).

## Decisions and why

The consolidation changes were checked against source, original saved evidence, simulator worlds
and actual dashboard behavior. The replay fix, request-boundary citation fix, tested defaults and
separate qualification/unseen/active status display are retained. The scoring code, `assess_pairs`,
policy interpreter and Actor system prompt are unchanged. Historical evidence is not rescored.

An immediate “Phase 28 unseen-case check” would be misleading. The Phase 28 declaration explicitly
prohibits routing its policies into a held-out request. Also, the older partition generator excludes
notification development cases but does not exclude all public upgrade cases. Changing a seed does
not make an already-known fault unseen. The existing unseen API has weaker admission than the
strong qualification display and does not enforce all of these historical/runtime restrictions.
No call was made through that route.

Instead, the lead declared a small compatibility check of one fixed, already-qualified policy on
seven already-public cases under the corrected application runtime. This checks whether the saved
repair still works; it cannot establish that FaultLab learned a new repair or that a repair generalizes.
A useful product needs both honest qualification and evidence beyond familiar cases.

## First public compatibility check — closed INCOMPLETE

[Declaration](CURRENT_RUNTIME_REPLICATION_2026-09-27.md). The runner selected the first strong
Phase 28 qualification by its original attempt order: attempt 5, policy
`04721232187d99677e698ce59b45ccd76ad2cb7c43854eff4c6a1e46163c548c`.
It compared that unchanged policy with the empty baseline. Neither arm changed historical records.

- Planned: seven public upgrade cases × three paired repetitions = 42 episodes.
- Attempted: 16 episodes; 15 completed with successful Weave readbacks; 26 never attempted.
- Stop: the sixteenth episode received W&B HTTP 503 before a report could be generated.
  Its lifecycle is `LAB_ERROR`, not a scored agent safety failure.
- Observed among the 15 completed episodes: 11 completed tasks and four truthful unresolved reports;
  all C1–C8 checks passed. Both arms completed all three healthy tasks. The repair completed all
  five attempted transient-upgrade tasks; baseline transient attempts remained unresolved.
- Charged: 81 model requests, $1.6929 conservative upper bound, carried upward as $1.70.
- Active policy: baseline `policy-v0`; copied repair remains `PROPOSED`, never `ACCEPTED`.

These partial results are not a full comparison and are not pooled with any later execution.
The failed episode and original outputs remain preserved. The raw evaluation batch is an initial
`INCOMPLETE` placeholder because its wrapper stopped before finalization; the 16 individual trial
records and `result.json` are the authoritative record of actual attempts.

Independent manual verification reconstructed all 16 world databases, 87 business HTTP attempts,
26 operation journals and all 15 original submitted reports. Reports were decoded from the exact
observation list delivered for each request, and cited success receipts matched actual operations.
All 11 completed tasks produced one upgrade and one confirmation after it; four unresolved tasks
produced neither. Five policy-driven retries preserved the original request identities. There were
no mismatched attempts, detected clock drift or missing worlds. The audit compared the 15 saved
remote readbacks with local evidence; it did not make another network readback request.

The partial run reached no lost-response case and no `before_final_report` policy hook. Zero masked
faults therefore supplies no lost-response coverage, and this run does not live-exercise the late-hook
citation regression. Controlled regression checks cover that branch separately.

Local evidence (ignored; not included in a source clone):

- `artifacts/runtime-replication-2026-09-27/result.json`, `plan.json`, `lab.sqlite3`.
- `artifacts/verification-2026-09-27/runtime-replication-independent-audit.json`.
- `artifacts/verification-2026-09-27/runtime-replication-freeze.json`.

## Bounded service-reliability improvement and follow-up

W&B documents HTTP 503 as temporary service unavailability and recommends retrying after a short
wait ([official guidance](https://docs.wandb.ai/support/inference/articles/api-error-code-503-the-engine-is-current)).
The saved diagnostics establish status 503, not the provider's exact internal cause.

The Actor now allows one retry after a cancellable one-second delay for HTTP 503 **only when no
model generation was returned**. It shares the existing two-attempt limit per turn, eight-turn limit,
90-second episode deadline and charged campaign limits. Returned answers are never re-rolled.
Repeated 503s stop normally; other HTTP statuses gain no retry. The outer episode deadline can
cancel the wait, with the existing deadline classification. No scoring rule or policy changed.

Focused checks exercise the actual Actor, RuntimeProvider error classification and real ledger with
an offline SDK boundary, including identical requests, final-turn retry, repeated failure, returned
content, elapsed time, stop, cancellation and every budget limit. Independent source review checked
the error path rather than relying on test assertions alone.

A [separate declaration](SERVICE_RELIABILITY_CHECK_2026-09-27.md) fixes the same policy and 42 public
slots on the new runtime in a new store. The first runner is preserved byte-for-byte; a new entry point
differs only in its fixed output directory. Shared admission/integrity checks exercise both entry points.
This follow-up is not yet executed. Its result and verification will be added here after execution.

## Exact-model pricing and admission

The configured Actor is `deepseek-ai/DeepSeek-V3.1`; Explorer and Mechanic are configured as
`deepseek-ai/DeepSeek-V4-Pro-0813`. A live catalog read confirmed both without requesting a generation.
Published rates verified on September 27, 2026, per million tokens:

| Role model | Input | Output | Official source |
|---|---:|---:|---|
| DeepSeek V3.1 | $0.55 | $1.65 | [W&B model page](https://wandb.ai/site/inference-model/deepseek-v3-1/) |
| DeepSeek V4-Pro-0813 | $1.31 | $3.96 | [W&B model page](https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/) |

Rates are model-specific, with no cache discount assumed. The compatibility checks dispatch Actor
calls only. Their maximum 672 requests reserve 22,848,000 tokens and $14.0448, inside a $20 phase cap.
Actual billed dollars are unavailable; measured tokens and conservative admission charges are separate.

The root `.env` was not edited. Normal startup remains offline. Live execution uses a non-secret
process profile with the confirmed entity `shreetbohara-quinstreet`, capitalized project `Faultlab`,
live-enabled flag, matching Actor/context models, confirmed entity, and both role pricing groups.
Each pricing group needs its exact model ID, input and output rates and a true verified flag.
The live launcher's refusal without those settings is intentional. Never copy historical prices
as verified without checking the current provider information. Secrets stay in the existing `.env`.

## Verification discipline and remaining work

Closing the dashboard and idle backend removes avoidable polling load during live experiments.
It is not proof against clock drift. The runner checks actual lab/world attempt identities, decision
clocks, fault delivery and nonzero world coverage after execution. Main-store polling, tests and
UI navigation are not run concurrently with paid episodes.

Fingerprints must use the project Python. During this review, system Python 3.8 and project Python
3.12 produced different AST serializations for identical files. File hashes and runtime identities
agreed; recomputing with project Python matched the sealed gate record. This was a comparison-tool
version difference, not a source change. Original records remain intact.

The next meaningful learning experiment needs a genuinely new partition sealed before candidate
generation, exclusion of previously used scenarios and materially equivalent variants, and a clear split between
public qualification and unseen evaluation. Generate fresh repairs under that same runtime, route
by predeclared criteria, and preserve negative results. That is separate from activating a policy.
Do not add another environment or a larger feature surface before resolving this evidence gap.
