# Phase 5 results — September 20, 2026

**Two models were asked for a repair. Neither proposed one, and both repeated themselves.**
The experiment Phase 3 B2 died before reaching has now run: the DeepSeek V4-Pro-0813
Mechanic was asked for a completion-recovery policy, twice, on a gap that reproduces. It
did not propose the one step that would fix it. A matched V3.1 control did not either.
Both studies end **NO_CHANGE**. No policy was accepted or activated, and `policy-v0`
remains active everywhere.

Protocol fixed before any paid call: [PHASE5_EXPERIMENT.md](PHASE5_EXPERIMENT.md).
Progress: [PHASE5_TASKS.md](PHASE5_TASKS.md). Same $1,000 ceiling as Phases 2–4.

## The predeclared read-out

> Of the proposals each study generates, how many contain a step with
> `op == "retry_original_request"` and `service == "notifications"`?

**Zero of four.** Two models, two proposals each, none containing the step.

| Study | Mechanic | Proposals | Containing a notification retry | Decision |
|---|---|---|---:|---|
| 5A | `deepseek-ai/DeepSeek-V4-Pro-0813` | 2 | **0** | NO_CHANGE |
| 5B | `deepseek-ai/DeepSeek-V3.1` | 2 | **0** | NO_CHANGE |

Study 5A: campaign `campaign-578537fb59d54f468e16dcdf64d1df87`, study
`completion-study-889f75d6d170418e9ff654f409a1952b`, 12 episodes, 12/12 verified Weave
traces, 81 model calls. Study 5B: campaign `campaign-d89e955f66854979bff23bd03d32aa21`,
study `completion-study-122d93e0dfa94c7484a46dd65b83aab2`, 12 episodes, 12/12 verified,
85 model calls.

Both studies passed their declared controls cleanly — 3 of 3 valid source controls with
zero completions, 3 of 3 valid healthy controls completing — so both reached the Mechanic.
Neither retained an invalid trial. The blocking fix made before this phase was therefore
not exercised, but it was also not needed to be: the risk it removes is probabilistic.

## What each model proposed

**V4-Pro-0813** proposed reads and receipt requirements at four hooks and said so plainly:

> "It never performs first writes **or retries**, preserving operation identities and
> authorization."

Its candidate completed 0 of 3 source trials against a baseline that also completed 0 of
3, so it did not qualify. Asked a second time, with the first candidate's content and its
zero-completion assessment supplied, it returned a policy whose content hash is
**identical** (`08084f7135c3…`) while asserting:

> "This policy is **materially different** from the prior candidate…"

The deduplication rule consumed the slot without granting fresh trials, which is what it
exists for.

**V3.1** proposed `wait_ticks` + `read_notification_operation` at the notification hook and
a receipt requirement before the report — the same shape as its Phase 3 B proposals. Its
candidate also completed 0 of 3. Its second proposal is likewise byte-identical
(`337e60e2f335…`), and its explanation is the most striking artefact of this phase:

> "This policy adds a **retry mechanism** for transient notification failures **by retrying
> the original `send_confirmation` request** after a wait period when outcome is
> uncertain…"

The policy it actually emitted contains no `retry_original_request` step. The model
described the correct repair in prose and did not encode it.

## What this establishes, and what it does not

**Established.** On this task, with this prompt, this evidence format and two proposal
slots, neither model produces the available repair. That is now measured rather than
assumed, and for V4 it is measured for the first time — Phase 3 B2 charged 33 Actor calls
and never reached a Mechanic request. Both models also failed the weaker test of producing
a *different* second proposal after being shown that the first completed nothing.

**Not established.** Nothing here shows the models *cannot* find it. The sample is two
proposals per model at temperature 0, and no reasoning trace is retained, so the cause is
not recoverable from the record. Three hypotheses are now on the table, each with evidence
and none tested:

1. **The brief may read as forbidding it.** `completion.md` says "no … new tools or first
   writes from a recovery hook". A retry of an already-dispatched write is not a first
   write, and the supplied runtime contract says so explicitly. But V4 volunteered "it
   never performs first writes or retries" as a *safety* property, which is what that
   sentence would produce if the qualifier "first" were dropped.
2. **The failure may be hard to see in the evidence.** `summarize_evidence` interns
   repeated observation rows, so in the real Phase 3 B proposal input the string
   `TRANSIENT_UNAVAILABLE` appears **twice in 23,901 bytes**, reachable only by
   dereferencing a table index.
3. **The step may simply not be reached for.** V3.1 named the right repair in prose while
   emitting the wrong steps, which looks less like a missing concept than a failure to map
   it onto the grammar.

These are three different experiments. None of them was run here, and folding any of them
into this comparison would have confounded it.

**Still unproven.** No generated policy has ever been accepted. T065, T088, T097, T100 and
T102 remain open.

## Context that makes the negative result sharp

The repair is available and the engine executes it. One rule suffices:

```json
{"hook": "after_notification_response",
 "when": "notification_outcome_uncertain",
 "steps": [{"op": "retry_original_request", "service": "notifications", "only_if": "always"}]}
```

Every element is legal at that hook, and the identical runtime path is proven live: the
handwritten B1 reference actor calls the same `broker.retry_original(...,
hook='after_notification_response')`, and **9 of 9** of its `notification-2` trials in the
database completed with one notification effect. The condition is also the one both V3.1
proposals already chose — `notification_outcome_uncertain` is true after a pre-acceptance
rejection, which was verified directly against `PolicyState`. Only the step is wrong.

And the models have produced the missing half before. In the older invariant-repair
campaigns the same model family did propose `retry_original_request` for notifications at
the correct hook — three of those policies gated it on `notification_operation_pending`, a
condition provably false here because the observed status is `UNKNOWN`, not `PENDING`. So
across the archive each half of the correct rule has been generated, never both together
under this objective.

## Cost

| Study | Episodes | Model requests | Conservative charge bound |
|---|---|---:|---:|
| 5A (V4 Mechanic) | 12 | 81 | $1.75078 |
| 5B (V3.1 Mechanic) | 12 | 85 | $1.77650 |
| Phase 5 total | 24 | 166 | **$3.52728** |

Recorded tokens 596,646 input and 10,549 output, zero unknown-usage requests;
known-token estimate **$0.34556115**. Both studies ended early and cheaply because the
duplicate second proposals consumed their slots without earning fresh trials.

Across Phases 2–5: **1,928 requests, $40.98976 conservatively charged, $959.01024
remaining.** Actual billed dollars are unavailable. No deployment, paid overage or Aria
call.

## What should happen next

Hypothesis 1 is the cheapest and most likely to be decisive, and it is a one-word change
to a prompt rather than a change to any gate: state explicitly that replaying an
already-dispatched write with its original bytes is permitted at the response hooks and is
not a first write. That is a real experiment with a real risk of leading the model, so it
must be declared as such, run against the same fixed cases, and reported as prompt
engineering rather than as a model capability result. Hypothesis 2 — inlining the delivered
error codes instead of interning them — is the natural second arm.

Neither is authorized by this document.
