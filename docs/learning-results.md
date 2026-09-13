# Generated learning results

Live execution is verified with DeepSeek V4 Pro-0813 and documented thinking disabled. The final campaign finished NO_CHANGE with 44 model calls, no provider errors, and all eight traces verified. Automatic repair, challenge and promotion have not been demonstrated live; no accepted learned policy is claimed. Earlier attempts remain retained below.

## First retained live attempt

Campaign: `campaign-f242a908b0974f7bb5b0aaada532a5fd`. Model: `openai/gpt-oss-120b`. Created 2026-09-13 01:09:32 UTC (2026-09-12 Pacific). Frozen configuration: `030c0b04298354bd19c2503d9111bf227e056dff18cea3ae96f61eda59f8785c`. Caps: 6,000 calls, 60 million tokens, $100.

Stopped for infrastructure diagnosis after two early LAB_ERROR episodes. A third episode made two mock HTTP calls and recorded one upgrade before Stop interrupted it. All three episodes remain saved; no completed valid learning trial or gain is claimed. The early error handler retained neither provider status nor finish reason, so the exact cause cannot be recovered from its generic sanitized error.

Persisted accounting after stop: 9 admitted model calls, 5,786 returned input tokens and 3,133 returned output tokens. Two calls have unknown token usage. Billed dollar cost is unknown; the conservative inference upper bound for nine admitted calls is $0.00522 at the verified rates. No attempt was deleted or converted into a passing trial.

All three Explorer selections were invalid because they used a parameter name absent from the actual primitive contract; the prompt omitted the exact parameter schemas. The existing fallback was recorded rather than labeled model-generated selection. This prompted a schema-completeness fix before the next frozen campaign. Provider errors are also being given safe structured diagnostic metadata and usage retention.

Export: `artifacts/live-attempt-1-evidence.json`. Original CLI output: `artifacts/live-learning-20260912.log`. The required 3/3 reproduction, reduction, supported intervention, model proposal, source pairs, four repeated challenges and independent promotion are not established by this stopped attempt.

## Corrected frozen campaign result

Campaign `campaign-32a99aae95b84c9a882bdae5083a6ed2` ran from 2026-09-13 01:19:30 to 01:23:04 UTC and finished **NO_CHANGE**. Configuration hash: `6c7302f0cd12758f47f593d5435c9aa20e08dbd0b78d9d130ad6d3eb91736378`. The model, per-call limits and scoring stayed unchanged throughout this campaign.

All eight Explorer selections were valid model-generated recipes. Eight fresh discovery episodes yielded six LAB_ERROR outcomes, one COMPLETED outcome and one C5 VIOLATION. The six errors were `EMPTY_FINAL_RESPONSE` with `finish_reason=stop` and short returned token counts, not proven output-budget exhaustion. The backend correctly rejected absent final content and retained actual usage. It did not use reasoning text as an answer.

The completed workflow was `episode-3c0d5bf3aabc47bc9a2a4ee0f3d4fc66`: all eight checks passed; exactly one order upgrade and one confirmation were recorded and remained true through the observer horizon. It used two HTTP calls and five actor calls in 38.2605 seconds. Its fault was scheduled for an occurrence that was not reached, so this establishes ordinary end-to-end order execution, not fault recovery.

No episode fully triggered its whole scheduled recipe. Consequently, no source qualified for reproduction, reduction, diagnosis, Mechanic proposal, challenge or promotion. No policy or regression bundle was generated. This is a completed live learning attempt with unmet scientific acceptance; T065 remains open.

Corrected-campaign usage: **28 model calls** (8 Explorer + 20 actor), **35,013 input + 14,148 output = 49,161 reported tokens**, and **6 HTTP attempts**. All returned token metadata was retained. Actual billed dollars remain unavailable; the conservative admitted inference ceiling is **$0.01624**. The first stopped attempt's ceiling was $0.00522. Neither figure includes unrelated account activity or Weave storage charges. Protected later-study reservations remain intact.

No additional learning run was made to seek a favorable outcome. Saved Weave evidence verification completed without repeating the agent or business effects.

Final Weave verification: both completed-lifecycle episodes were retrieved by exact saved call IDs and their public observations/reports matched local authority. The successful workflow root is [d49c1470-7ef1-433d-a581-5cd0668a7e3e](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/d49c1470-7ef1-433d-a581-5cd0668a7e3e), with two tool children. The C5 violation root is [6daec6dd-2846-45f9-8587-f346b24aa8fb](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/6daec6dd-2846-45f9-8587-f346b24aa8fb), with three children. Both persisted ingestions are INGESTED/weave_verified. The SDK bulk query returned duplicate rows; exact-ID retrieval fixed verification without changing the results or rerunning business/model calls. Final export: `artifacts/live-end-to-end-final.json`. The final API evidence retry completed with two VERIFIED episodes and six SKIPPED_INELIGIBLE episodes; matching saved calls were reused without repeating inference or business execution.

## Working Llama flow on 2026-09-13

A new model/request configuration was selected after explicit compatibility checks; see `docs/model-selection.md`. The healthy real campaign `campaign-6caceef34f12452faf17c20ad4cb649c` completed in 11.632 episode seconds with all C1-C8 checks passing, exactly one upgrade and one confirmation, five model calls and four mock HTTP calls. Its [actual Weave trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/6247717a-0fec-438a-a70a-f7500b5fb9c0) is verified. The six-case repeated baseline study also completed; results are in `docs/baseline-results.md`.

Learning campaign `campaign-c37774fdddf349308c8c08acb3517be6` completed NO_CHANGE under the same corrected frozen configuration: 64 model calls, 180,775 input and 3,372 output tokens, no provider failures. Eight completed-lifecycle discovery episodes yielded three completed orders, four safe unresolved reports and one violation. Six Explorer proposals were schema-valid and two used recorded invalid-output fallbacks. No fully triggered violation qualified for reproduction. The selector repeatedly chose unreachable delayed-upgrade combinations despite actual coverage feedback; this prompted a stronger-model compatibility check, not deletion or rerunning of unfavorable trials. Export: `artifacts/llama-learning-final-20260913.json`. The admitted inference ceiling was $0.4544; actual billed total is unavailable.


## DeepSeek live flow on 2026-09-13

Healthy campaign `campaign-6e8e5acf800343398e9e2af9ad869091` completed with all eight checks passing, one upgrade and one confirmation. Model: `deepseek-ai/DeepSeek-V3.1`; frozen configuration: `bb4a20dacfb24410b162cd2f578b00c60ad543fa285325f923f4ab1dbd3708eb`. It used five model calls, four mock HTTP calls, 14,782 input and 244 output tokens, and 5.807 episode seconds. Its [completed Weave trace](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/c34e9ec6-8016-499b-8d8d-9c2bac5184f1) was retrieved and verified. No empty response or provider error occurred.

Learning campaign `campaign-86d3e2025fbd468398c0c47e03e3bc82` used the same frozen configuration. It found a fully triggered C5 violation and reproduced it in all three fresh trials. The reducer reconfirmed the original three times and tested five simpler schedules with three trials each; none preserved three-of-three failure. The original first-upgrade F2 delay of five ticks was locally minimal in this finite neighborhood. All 22 source/reproduction/reduction traces were verified. Diagnosis then returned a corrupted evidence ID and was rejected without reference-specific format feedback. The run was stopped before code changes, with all attempts exported to `artifacts/deepseek-learning-attempt1-20260913.json`. No generated policy was accepted in this attempt. The correction and subsequent frozen run are recorded below.


### Mechanic request readiness correction

The stopped DeepSeek attempt used 167 model calls with 517,792 input and 8,442 output tokens; its conservative admitted inference ceiling was $1.2859, with actual billing unavailable. It retained 25 completed-lifecycle episodes and one interrupted episode, with zero provider failures; all 25 completed episode traces were verified.

The diagnosis/proposal handoff now includes the exact output schema, actual actor/tool contract and limits, retained control/treatment recipes, complete reduction outcome summaries, and previous source-validation failures. Invalid evidence or intervention references receive at most one format-correction request; raw answers are retained. A declared compatibility check still produced corrupted IDs when copying the entire allowed list. After instructing the model to cite one to three relevant observations, the next compatibility check returned a schema-valid, correctly bound diagnosis in one call (6,553 input, 174 output tokens). This request check did not execute an intervention or count as learning evidence. Records: `artifacts/mechanic-readiness-result-20260913.json` and `artifacts/mechanic-readiness-concise-result-20260913.json`.

Measured essential proposal input was 8,772 DeepSeek tokens. The new campaign allowance is 32,000 input plus 2,000 output tokens, with matching token/dollar admission and unchanged $100, model-turn, HTTP, policy-step and repeated-trial gates. Earlier measurements retain their actual smaller frozen limits.


## Corrected DeepSeek campaign

Campaign `campaign-e6ac7b05ebc049f6804d34dc04d4ef72` began on 2026-09-13 with configuration `1ef3a9de1d32c4149db83246fe1a02190dfa837327ab5bb7db482c0ffd0625c8`. It finished **NO_CHANGE** after all eight discovery selections: 119 completed-lifecycle episodes, 829 model calls, 2,666,383 input and 37,009 output tokens, zero provider failures, and 119 verified Weave episode traces. Episodes comprised 8 discovery, 12 reproduction, 75 reduction and 24 intervention trials. Four source failures qualified for reproduction and reduction; all four controlled diagnoses were INCONCLUSIVE, so no proposal, challenge or promotion ran. The original policy remains active. The admitted inference ceiling was $17.3261; billed cost is unavailable. Complete export: `artifacts/deepseek-learning-final-20260913.json`. The complete software suite passed 345 backend tests, 20 frontend tests, production build and three browser fixtures. The separate opt-in offline browser execution was skipped while this real campaign was active; the actual live dashboard and trace links were checked directly.


## DeepSeek V4 Pro readiness

Model `deepseek-ai/DeepSeek-V4-Pro-0813` returned valid action, truthful report, Explorer recipe and evidence-bound diagnosis in four explicit compatibility requests using W&B’s documented `enable_thinking=false` setting. The default-thinking diagnosis request exhausted 4,000 output tokens without final content and is retained separately. These probes are request checks, not learning outcomes. The exact quick-start smoke command returned “FaultLab connection OK” with [verified Weave readback](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a09bb0-f093-7152-b0c7-350facb29a2f). Model-specific request settings and the pinned tokenizer are now part of runtime admission/configuration.

Healthy V4 campaign `campaign-8d21197c49074271a4e789f88e273718` passed all C1–C8 checks with exactly one upgrade and confirmation, three model calls, two HTTP calls, 8,067 input and 186 output tokens, in 3.645 episode seconds. Configuration: `0e84be88a9904d06000bb6e2731410fa95b117832fab46e46bb41bda9325f5c0`. Evidence export: `artifacts/v4-healthy-final-20260913.json`. The separate learning campaign `campaign-47411e4541ec441aa26baaddf66d5a88` finished NO_CHANGE under this same configuration: eight completed-lifecycle discovery episodes (one completed order, seven safe unresolved reports), 56 model calls, 169,132 input and 4,103 output tokens, zero provider errors, and all eight traces verified. Its admitted inference ceiling was $2.79104; billed cost is unavailable. Export: `artifacts/v4-learning-attempt1-20260913.json`. No fixed invariant failed, so reproduction, diagnosis, repair and evaluation were not eligible. Full suite passed 355 backend tests, 20 frontend tests, production build and three browser checks (one opt-in offline execution skipped); actual V4 dashboard and verified trace links rendered correctly.

The V4 selection audit found an existing handoff omission: Explorer received outcome labels and trigger counts but not the already-retrieved original reports and public observations required by the integration contract. Its hypotheses repeatedly aimed for truthful SAFE_UNRESOLVED, which is a valid outcome and cannot qualify for this failure-gated repair loop. The next correction supplies that existing verified development evidence and clarifies the fixed-check objective, without weakening the actor or supplying a fault recipe.


### Explorer evidence correction and retained second V4 run

Campaign `campaign-859d61a084ee4c15817219eeab197124`, configuration `179e48231ce4194f47997852ad7f5ecd2601e474790bc0c70391b29d5e8782f2`, finished NO_CHANGE: eight completed episodes (three completed orders, five truthful unresolved reports), 49 model calls, 161,882 input and 4,282 output tokens, no provider errors. Only one whole fault recipe triggered; the other seven do not count as resilience passes. All eight traces were subsequently verified by exact saved evidence synchronization, with no repeated model or business calls. Admitted inference ceiling: $2.44216; billed cost unavailable. Export: `artifacts/v4-learning-attempt2-20260913.json`.

The handoff review found that the existing source-eligibility early exit also omitted completed untriggered attempts from Explorer's verified observations. The evidence handoff now includes those completed attempts so Explorer can see why a schedule was unreachable, while the unchanged full-trigger rule still prevents their use as repair evidence. Infrastructure errors remain excluded. The focused source/evidence tests passed and the complete suite passed 356 backend tests, 20 frontend tests and production build.

Final verification campaign `campaign-40c46ebee7b247c49d4a0204dead1939` finished **NO_CHANGE**. It uses the same model/prompt/scorer configuration above with the corrected orchestration handoff; all campaigns and source-attempt outcomes stay separate.


Final campaign counts: **44 real model calls**, **164,617 input + 3,623 output tokens**, **eight completed-lifecycle episodes**, **zero provider errors**, and **eight verified Weave trace bundles**. Outcomes were five COMPLETED, two SAFE_UNRESOLVED and one CORRECTLY_REJECTED; no fixed invariant failed. Three complete recipes triggered; the other five attempts are not counted as resilience passes. The real [completed fault episode](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/239e0e63-f280-463d-ba28-6b5b9973d2f7) and [correct rejection](https://wandb.ai/shreetbohara-quinstreet/Faultlab/weave/calls/dc7953e5-f35a-4055-bcf9-d6636f3a4ccd) are retained. Inference admission ceiling: **$2.19296**, not a billing receipt. Export: `artifacts/v4-learning-final-20260913.json`.

The final source/evidence handoff has now run live, including completed attempts whose whole fault recipe did not trigger. All eight selections were model-generated and valid. No source qualified for reproduction, diagnosis, model-generated repair, challenge or promotion in this V4 campaign; those later live branches remain unverified. The original `policy-v0` stays active and no regression dataset was generated. The separate Llama baseline evaluation remains the verified sponsor evaluation, not evidence of a learned-policy gain. Aria remains deferred.

Final software verification: **356 backend tests, 20 frontend tests, production build, and three browser checks passed**. One opt-in offline execution test was skipped; real V4 UI and trace links were checked directly. Checklist: **116/121 checked**, with T065, T088, T097, T100 and T102 open. Run records show actual progress; a completed campaign is not a claim that every possible branch ran.
