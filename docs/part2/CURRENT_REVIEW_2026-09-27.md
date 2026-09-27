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
The follow-up completed once, in 296.99 seconds, with **42/42 episodes**, **21 complete pairs**,
**36/36 scheduled faults triggered**, **42 verified Weave readbacks**, and no detected clock drift,
missing worlds or failed C1–C8 checks.

| Public case (three repetitions per arm) | Empty baseline | Saved repair |
|---|---|---|
| Healthy service | 3 completed | 3 completed |
| Three temporary upgrade failures | 3 safely unresolved | 3 completed |
| Two temporary upgrade failures | 3 safely unresolved | 3 completed |
| Delayed upgrade completion | 3 completed | 3 completed |
| Repeated outage beyond the episode limit | 3 safely unresolved | 3 safely unresolved |
| Lost upgrade response | 3 completed | 3 completed |
| Explicit upgrade rejection | 3 correctly rejected | 3 correctly rejected |

The saved repair completed **15/21 tasks**, compared with **9/21** for the baseline: six extra
completions, all on the two transient-failure cases. Both arms handled the intentionally unfinished
or rejected tasks truthfully. These are descriptive results from three paired repetitions per case,
not a general accuracy estimate, a new repair-generation result or evidence about unseen scenarios.

The evaluator's raw decision is `NO_CHANGE`, with reason “Complete repeated evidence; fixed
promotion predicate still required.” The experiment itself is `COMPLETED`. Those statements are
consistent: this comparison finished, but it did not run the original promotion workflow or activate
a policy. The candidate remains `PROPOSED`; the active policy is `policy-v0`.

Manual inspection distinguishes the causes of recovery:

- Temporary failures: the learned rule resubmitted the original upgrade request with the same
  operation and idempotency identity; the shop applied one upgrade and sent one confirmation.
- Lost response: both arms recovered through the adapter's existing same-request transport retry.
  The learned policy did not execute steps in these six episodes. This is not new learned recovery.
- Delayed success: the learned rule retried accepted work while the last delivered status was still
  PENDING. The operation completed as that request arrived; service de-duplication returned the
  existing receipt. This redundant resubmission is safe in this shop, not evidence that arbitrary
  external services tolerate it.
- Explicit rejection: rule conditions enabled retry steps, but the interpreter's FAILED-receipt
  precondition prevented any retry HTTP request. A `policy_step.executed` event means its condition
  passed, not necessarily that a business request was sent. Actual dispatches and receipts matter.
- Repeated outage: three policy episodes invoked final-report hooks and appended an observation
  after the final Actor answer. Original citations were decoded against the earlier request evidence,
  as intended; newly added evidence was not used to validate those original labels.

No real model HTTP 503 occurred in this second run. The new retry branch was verified with controlled
SDK failures and independent code inspection; this live run verifies integration of the new runtime,
not a live recovery from another provider 503. The malicious future-label citation case is likewise
a controlled regression check; the live run covers genuine hook execution and valid original labels.

The independent audit reconstructed all **42 worlds, 42 original reports, 42 saved remote readbacks,
262 business HTTP attempt identities, 66 operation journals and 336 fixed rule checks**, with no
unresolved mismatches. The initial audit mistakenly equated condition-true retry steps with actual
HTTP dispatches and flagged three rejection episodes. Manual review of the interpreter, FAILED
receipts and tool journals resolved those false flags. The original audit output is preserved as
`service-reliability-independent-audit-first-pass.json`; only the independent checker was corrected,
not the application, score or saved results.

The run charged **231 model requests, $4.8279 conservative upper bound**, carried as **$4.83**.
Both follow-ups together used **312 requests / $6.5208**, carried as **$6.53**. Shared carried spending
is now **$818.23 / $1,000**, leaving **$181.77**. Added funds were not needed; actual provider billing
remains unknown. No historical charge was reset or reclaimed.

Identities and local evidence:

- Runtime: `3da193e30a71ea4aebc8309580548c09ece3fb31d4ccd8a8529112b8f8b9a9d8`.
- Configuration: `1fbaa792db504d5b0c142ea60af759ab2b417a1e83983f4d34959fa967048921`.
- Campaign: `campaign-4bd4ae80445044689cd087aaad14cfa9`.
- `artifacts/service-reliability-2026-09-27/{result.json,plan.json,lab.sqlite3}`.
- `artifacts/verification-2026-09-27/service-reliability-freeze.json` and
  `service-reliability-independent-audit.json`.
- `artifacts/verification-2026-09-27/followup-budget-ledger.json` and
  `followup-preservation-final.json`.

The live store is deliberately separate from the main dashboard's historical store. It is not silently
merged into historical studies. All 37 historical reports and the main store's campaign, episode,
policy, completion-study, unseen-check, evidence and ingestion payloads remain unchanged.

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

## Verification results

- Full backend suite before the service change: **1,891 passed, 180 skipped, zero failures**,
  712.56 seconds. This provided the requested clean number after the original two test corrections.
- Full backend suite after the service change: **1,920 passed, 180 skipped, zero failures**,
  702.49 seconds, one existing dependency deprecation warning. The new result supersedes the earlier
  one for the current runtime; it is a single complete invocation, not combined partial counts.
- Focused Actor/provider checks: **66 passed**. Separate runner checks covering both fixed entry
  points: **74 passed**. Their initial single-runner 37-test result is retained as historical evidence.
- Frontend from the consolidation: **166 tests**, production build and three browser fixture checks
  passed. Manual real-server verification opened an actual saved 42-trial replay and checked the
  separate development, unseen and active-policy display. No frontend code changed in this follow-up.
- Current live evidence and manual post-run reconstruction are described above. Neither passing
  software tests nor an all-green dashboard substitutes for those original reports and world effects.

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

A focused next-study design, not a sealed execution protocol:

1. Freeze the corrected runtime, full pre-existing policy-hash inventory and verified prices.
2. Reserve one healthy guard, two known-family guards and three previously unexposed combinations
   of two existing faults before any Mechanic call. Check against all previously exposed scenarios;
   stop if the construction cannot produce valid reserved combinations. New counts or seeds alone
   are not new mechanisms. Do not expose evaluation traces to candidate generation.
3. Run at most ten fresh generation attempts on the existing development manifest, with a spending
   stop declared in advance. Route the first previously unseen exact policy hash meeting the full
   strong qualification rule. Record rediscoveries and failures. If none qualifies, stop honestly.
4. Evaluate that one policy against the baseline: three paired healthy repetitions and fifteen pairs
   for each of the other five cases, 156 episodes total. No whole-pair retries or second candidate.
   Actor-only worst-case cost at the verified rate is $52.1664; generation cost requires a separate
   full-path bound including proposal/correction calls and transport retries before admission.
5. Report completion, violations and fault triggering by case, separately for familiar guards and
   reserved combinations. A no-harm decision is a sample result, not proof of safety or equivalence.
   Keep baseline active; original promotion is a different workflow.

This is a bounded search followed by evaluation, not a fixed-sample estimate of repair yield. A
new experiment wrapper must enforce strong qualification, source/current runtime equality, exact
policy identity and the partition commitment made before generation. This design is not part of
either compatibility-run declaration and has not been launched.

## Local preservation

All source and current documentation are saved on the local `backup/part2-2026-09-22` branch.
The checked-out main branch and real index were preserved, and no GitHub push was made. `.env`
remains untracked and unchanged. Dashboard, backend and owned simulator are stopped after verification.

Both isolated experiment stores, all 58 new world databases and their verification files were copied
to `/Users/shree/FaultLab_Backups/2026-09-27/followup-verification/` and checked byte for byte.
`MANIFEST.json` there contains hashes and sizes. Credentials were not copied. The historical main-store
backup remains separate; this small follow-up backup does not pretend to contain the whole project.
