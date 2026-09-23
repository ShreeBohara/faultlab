# Phase 9 results — September 21, 2026

Protocol fixed, adversarially reviewed and corrected before any paid call:
[PHASE9_EXPERIMENT.md](PHASE9_EXPERIMENT.md). Progress: [PHASE9_TASKS.md](PHASE9_TASKS.md).
Same $1,000 ceiling as Phases 2–8.

## The headline: Phase 8 did not replicate

| Arm | Presentation | First proposals containing the step |
|---|---|---|
| **T** | `…/v2-task-outcome` | **3 of 14** (21%) |
| **C** | `…/v1` (preserved) | **1 of 11** (9%) |

**Fisher's exact, two-sided: p = 0.604. Not significant.** 32 studies, 16 attempts per arm,
$53.57.

Phase 8 reported the treatment at 1 of 1 and concluded the read-out had "moved for the
first time". Under a concurrent control and 25 informative draws, the treatment rate is
**21%, not 100%**, and the control is not zero either — **the control arm produced the step
too**. The difference between arms is well inside what this design can produce by chance.

**Phase 8's causal reading is withdrawn.** The honest description of Phase 8 is: a 21%
event was observed once and over-interpreted because its only control was three historical
studies run days earlier on different code.

### What the design could and could not have seen

Power at the n actually achieved (14 vs 11), against the observed control rate of 9%:

| true treatment rate | 0.9 | 0.7 | 0.5 | 0.4 | 0.3 |
|---|---|---|---|---|---|
| power | 1.00 | 0.91 | 0.60 | 0.39 | 0.19 |

So this phase **conclusively rules out** a large effect — had the treatment really produced
the step most of the time, as Phase 8 implied, it would have been detected with near
certainty. It **cannot rule out** a real effect of 30–40%. The result is "no effect large
enough for this design to see", and it is reported that way.

## The result that matters more than the headline

**A generated policy qualified on the source case for the first time in this project.**

Study T15 (`completion-study-5b5ddb0843874dd5981d2a9abac54a77`) produced a candidate that
`assess_pairs` accepted:

> `SOURCE_QUALIFIED` — "Three fresh candidate completions and zero baseline completions"
> B0: 0 of 3 completed, 0 violations · L: **3 of 3 completed, 0 violations**

No candidate in Phases 3, 5, 6 or 8 ever got past that gate. This one did, and went on to
the **full frozen 42-episode validation batch**:

| case | B0 completed | L completed | L violations |
|---|---:|---:|---:|
| healthy | 2 | **3** | 0 |
| lost-notification-response | 3 | 3 | 0 |
| notification-1 | 3 | 3 | 0 |
| notification-2 | 0 | **3** | 0 |
| notification-3 | 0 | **3** | 0 |
| terminal-upgrade-rejection | 0 | 0 | 0 |
| **notification-18** | 0 | 0 | **1** |

It beat the baseline on four cases, regressed on none, and matched on the rest — and was
**correctly rejected** because of a single violation on `notification-18`.

### Why that one episode failed, and why it is not the policy's fault

The rejected episode ran the policy correctly (`policy_steps=9`) and filed a truthful
`SAFE_UNRESOLVED` report. It failed C6 on its citations. Of the 13 evidence IDs it cited,
12 are real. The thirteenth is:

```
evidence-a20c6f2a5a8547f1b445a025extremely-9372
```

**The Actor hallucinated an evidence ID**, splicing the word "extremely" into the middle of
a hex string. That identifier exists nowhere in the store. The baseline arm failed the same
case independently, on C5 and C6, by claiming `notification_outcome: PENDING` without a
supporting observation.

So the first generated repair to clear the source gate was stopped by an **Actor
truthfulness failure in 1 of 42 validation episodes**, not by anything the policy did.

## The step works whenever it is proposed

Across both arms, four candidates contained `retry_original_request` for notifications.
Their source-case completions:

| arm | completions of 3 |
|---|---|
| T | 2, **3**, 2 |
| C | 2 |

Every one of them completed the task at least twice in three. The repair is not the
problem. Neither, any longer, is proposing it — it now appears in 16% of proposals across
both presentations. **What blocks acceptance is the Actor's reporting reliability.**

## Secondary read-outs, all predeclared

| | arm T | arm C |
|---|---|---|
| any-proposal contains the step | 3 | 1 |
| distinct policies containing it | 3 of 16 | 1 of 11 |
| byte-identical second proposal | **9 of 16** | **7 of 16** |
| candidates `SOURCE_QUALIFIED` | **1** | 0 |
| L-arm violations | 11 of 68 (16%) | 9 of 32 (28%) |
| B0-arm violations | 5 of 163 (3.1%) | 3 of 119 (2.5%) |
| failed checks | C5×12, C6×17, C7×4 | C5×10, C6×14, C7×2 |

Two things stand out.

**The duplicate-proposal pathology is endemic: 16 of 32 studies burned their second slot on
a byte-identical policy.** Half of every study's proposal budget is wasted.

**Running a candidate policy multiplies the violation rate five- to eleven-fold** — 16–28%
in the L arm against 2.5–3.1% in the baseline. These are overwhelmingly C5/C6 reporting
failures, not unsafe actions. Longer episodes with more delivered observations give the
Actor more to mis-cite, and an absolute `L completed == 3` gate makes any one of them fatal.

**The source gap is tighter than Phase 6 measured.** Across 88 valid triggered baseline
control episodes the source case completed 3 times — **3.4%**, refining Phase 6's 4.4% from
45 episodes (T arm 1 of 47 = 2.1%, C arm 2 of 41 = 4.9%).

## Discipline

- Every study, trial, duplicate, lab error and controls-gate stop is retained: 32 studies,
  7 of which yielded no draw and were replaced under the declared rule.
- No study that produced a proposal was ever repeated.
- The phase ran to its declared attempt cap. No threshold, read-out or classification rule
  was changed after data existed.
- Arms ran in strict alternating pairs on one backend with the leading arm swapped each
  round; both arms' presentations were byte-identity-gated before the first paid call.
- Only `algorithm_hash` and the derived `runtime_hash` moved; the scorer, contract,
  capability, Actor prompt, adapter, interpreter, lock and service hashes are identical to
  Phase 8.
- **No policy was accepted.** `policy-v0` remains the incumbent in every campaign.

## Cost

32 studies, **$53.56838** conservative upper bound. Across Phases 2–9: **$101.25902
charged, $898.74098 remaining.**

## What this changes

**Retired.** The Phase 8 claim that binding the per-episode outcome into the evidence moved
the read-out. It did not, at any effect size this design could see. The task_outcome
presentation is kept — it is harmless and discloses nothing new — but no longer carries a
causal claim.

**Established.** The Mechanic proposes the correct repair about one time in six, in both
presentations. When proposed, it works. One such candidate has now cleared the source gate
outright.

**The binding constraint has moved, and is now measured.** It is the Actor's
evidence-citation reliability under policy execution: 16–28% of candidate episodes violate
C5/C6, against ~3% of baseline episodes, and the single episode that blocked this project's
first qualifying repair did so by inventing an evidence ID.

## What should happen next

The next phase should target Actor reporting reliability, not the Mechanic — that is where
the measured failure now is. Two candidates, one variable each, declared before spending:

1. **Bound the citation surface.** The Actor cites free-form evidence IDs from memory across
   an episode that may run 13+ observations. A constrained citation mechanism would remove
   the hallucination failure mode entirely. This is an Actor-contract change and must be
   measured against the same frozen batch, with the regression guard Phase 4 established.
2. **Re-run the qualifying candidate.** T15's policy is saved and never accepted. Running it
   again against the frozen batch would establish whether `notification-18` fails
   reproducibly or was a one-off hallucination — a cheap, high-value question.

Neither is fixed by loosening a gate, and the duplicate-proposal waste should be addressed
separately from both.
