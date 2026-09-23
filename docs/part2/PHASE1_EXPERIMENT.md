# Phase 1 experiment declaration

Declared September 20, 2026, before new model generations. This declaration governs the first integrated Phase 1 runs. Append amendments with their reason before any affected follow-up; preserve all earlier results.

## Question

Does the corrected repair workflow produce distinct, evidence-informed policies, classify failures truthfully, export useful incidents, and complete its live stages under the original acceptance checks? A promoted policy is a desired research outcome, not a guaranteed result.

## Frozen comparison

- Actor: `deepseek-ai/DeepSeek-V3.1`. It has prior healthy execution and a promising but insufficient candidate comparison. Choosing it preserves continuity rather than selecting an agent for dramatic failures.
- Explorer and Mechanic: `deepseek-ai/DeepSeek-V4-Pro-0813`, documented thinking disabled.
- Existing Actor prompt, original reports, tool identities, four fault primitives, fixed C1–C8 and original promotion predicate remain unchanged.
- Existing episode limits: eight Actor turns, 18 HTTP attempts, four wait cycles, 20 ticks, 32 policy steps, 90 seconds. Existing per-call input/output bounds remain 32,000/2,000 tokens.
- Record actual role models, code/configuration hashes and campaign provenance with each run. Do not modify runtime code while a run is active.
- Provider model discovery verified that both exact models are available on the confirmed account.
- Confirmed project: `shreetbohara-quinstreet/Faultlab`.
- Inference and Weave are enabled for this experiment. Automatic Aria publication is explicitly deferred; the existing remote automation is not changed.

## Sequence and stopping rules

1. Run full offline checks and verify local service readiness. Restart the old backend and simulator deliberately after integration.
2. Run the existing fixed baseline study: six development cases, three repeats, model B0 and handwritten reference B1 (36 total episodes). This measures healthy competence, fault triggers and errors before new learning. It is not a learned-policy comparison.
3. If all three healthy B0 trials fail due to protocol errors, stop and diagnose compatibility. If a provider or local execution problem affects the study, retain it and fix that problem before proceeding. Do not silently replace failed trials.
4. Run one corrected learning campaign: existing cap of eight discovery selections, four proposals, fresh reproduction/reduction/intervention, paired source validation, mandatory challenge, and independent promotion when eligible.
5. Inspect all unique proposals, duplicates, source flakiness, original reports, fault triggers and trace classifications. Stop immediately on evidence of a privacy/identity bug or changed runtime identity. A no-change result alone is not grounds to rerun the same experiment until it passes.
6. Validate and freshly execute an exported real incident using the reviewed runner. Label a rejected-policy comparison accurately; execution does not convert rejection into acceptance.
7. If a policy qualifies, verify unchanged-policy restart reuse and broader healthy/fault checks. If it does not qualify, use observed failure evidence to declare at most one initial follow-up learning campaign or a broader development comparison. Any changed model, prompt, hook surface or budget requires a new configuration and explicit result label.

## Spending and accounting

The total Phase 1 ceiling is $100 across these actions, not $100 for each campaign. Before starting each new campaign, subtract the conservative charged upper bounds of prior Phase 1 requests from this ceiling and set the new campaign cap no higher than the remainder. Campaign budget protection remains enabled. A paused or uncertain in-flight request retains its full bound.

The model API does not currently return billed dollar cost. Report measured input/output tokens, the rate-derived estimate, and the conservative admitted upper bound separately. Unknown usage is not free. Standalone model-list requests are not generations; any standalone generation must be entered in the same ledger before dispatch.

Rates verified from [W&B token pricing](https://wandb.ai/site/pricing/tokens/) on September 20, 2026: V3.1 input/output $0.55/$1.65 per million tokens; V4 Pro 0813 $1.31/$3.96. Do not assume cache discounts. Maximum request bounds at 32K input/2K output: V3.1 $0.02090; V4 Pro $0.04984.

## Reporting

Report planned and attempted counts, all errors, completed/violation/safe-unresolved/correct-rejection outcomes, reached and triggered faults, unique candidates and duplicate proposals, source/challenge/promotion results, complete export validation, fresh regression outcomes and actual Weave readback.

Preserve original five hackathon gates until their specific evidence exists. Source repair success on development cases does not establish held-out generalization or independent-agent transfer. No new final-audit cases will be inspected by the repair model.

## Amendment 1 — interrupted infrastructure attempt

At 16:57:58 UTC, learning campaign `campaign-0ff8bbf4a8104e4ca07d8d7ad5fda345` stopped on Explorer `APIConnectionError` after six completed discovery episodes. All six traces were verified; one rule violation had an untriggered schedule and was correctly not eligible for reproduction. No repair was proposed. Its $0.99678 admitted bound remains charged, including one request with unknown usage.

A fresh model-list request succeeded afterward with both declared models available. No persistent configuration or code fault was identified. Start one replacement learning attempt under identical source/model/protocol/gates, with only the cumulative remaining cap changed to $96.90. Keep and report the interrupted attempt. This replaces an incomplete infrastructure attempt; it is not a hidden repeat of a completed negative learning result. If connection failures recur, stop and investigate before additional learning runs.

## Amendment 2 — registered-agent trace correction and planner follow-up

The V4 Mechanic run finished NO_CHANGE: one unique candidate failed all three source pairs; three later outputs were semantic duplicates and received no further qualification trials. Later prose claimed edits not present in returned JSON. Full feedback was present below the token bound. No change to the task agent, scorer or qualification rule is justified by those results.

Fresh execution of its exported incident completed three distinct worlds, each reproducing C5. It exposed a reference-registry integration bug: the factory returned the raw Actor rather than the existing traced prototype wrapper. Seven tool spans were saved per episode but no parent episode span, so remote verification cannot establish those original runs. Correct the factory to reuse its existing wrapper, test reference and native paths, then freeze a new runtime. Do not reconstruct missing historical root spans. Native already has a wrapper and must not be wrapped twice.

After the fix, run one declared planner follow-up with only the Mechanic model changed to `deepseek-ai/DeepSeek-V3.1` (both diagnosis and proposal share that role). Actor remains V3.1, Explorer remains V4 Pro 0813; prompts, gates, input/output/time bounds and no-generation-retry policy are unchanged. This is an alternate planner experiment, not a claim that V3.1 is superior. Existing tokenizer/pricing support makes it a minimal compatible change. Record the new runtime/configuration and preserve both earlier campaigns. Do not claim causal model comparison from separately discovered scenarios. Start under at most the remaining total allowance; reserve room for native baseline and fresh regression verification.

Run the native baseline as a separate experiment using `scripts/experiments/native_baseline.py`: six development cases, three fresh trials each, unchanged empty policy, native smolagents original reports and separate configuration/store/ledger. It requires the dashboard backend to be stopped and holds its port to prevent concurrent paid dispatch. Keep simulator running. This is agent baseline/conformance, not transfer of an accepted learned policy. Preserve all 18 slots, including invalid or unattempted ones; stop on infrastructure error instead of replacing a failed trial. Current Phase 1 $100 cumulative ceiling still applies across both stores.


Execution identities for Amendment 2:

- Corrected runtime hash: `97c91555efd5319b4f9c2cdf57db4e80f83be1bf0b947f57a5ae91f0c3813322`; algorithm hash unchanged. `frozen-source-v2.json` and `frozen-runtime-v2.zip` preserve it locally.
- Native baseline: `campaign-9581a7e140474e0889bb789c93b02f7d`, separate store, completed 18/18 planned slots. Its executed tracked harness is also copied beside the results.
- Alternate-Mechanic learning: `campaign-9e7f10cd29ea4eb2b41ad158e262ec5c`, configuration `abd6b5f985660bc263e65cc2308e0e457b605d7b5517212d532a66c58e08fd58`, started 17:19:37 UTC. Campaign cap $88.32 after prior admitted bounds of $11.67026. Order label `order-1`; source discovery is independent, so these runs are not a paired comparison of Mechanic models.
- Its reduced incident `regression-ca8303126316441099c9dde0f590f13c` is the planned fresh-regression verification target after the campaign finishes. Read-only export/compatibility validation passed while learning continued; no overlapping model run was started.
