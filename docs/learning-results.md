# Generated learning results

Status: the authorized live learning attempt is COMPLETE with NO_CHANGE. Inference, one successful order workflow and completed campaign trace readback are verified. Measured learning acceptance remains PENDING; no accepted learned policy is claimed.

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
