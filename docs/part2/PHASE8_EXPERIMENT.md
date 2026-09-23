# Phase 8 protocol — make the task outcome legible per episode

Written **before** any Phase 8 paid call, after Phase 7's probes killed both remaining
hypotheses and produced a better-supported one. This is the predeclared plan. Results go in
`PHASE8_RESULTS.md`; progress in `PHASE8_TASKS.md`.

Phase 7 replaced guesswork with a measurement. Asked what happened to the notification
operation in the failing episodes, the V4 Mechanic answered:

> "The supplied development evidence contains **no failing episodes**. All checks in every
> check row have `passed: true`, and the `observed_outcomes` show `failed_checks: []` for
> both arms."

It is right about the checks and wrong about the task. A truthful `SAFE_UNRESOLVED` passes
all eight checks and still leaves the order unconfirmed. This phase changes one thing: it
makes the per-episode task outcome visible where the model is already looking.

## The hypothesis

**H5 — the failure is not represented as a failure.** The Mechanic's evidence presents each
episode as a row of passing checks. The adjudicated outcome exists in the context but only
as a *group* summary sitting beside `failed_checks: []`. Nothing binds "this episode" to
"this episode did not complete", so a check-centric reading concludes there is nothing to
repair.

## The change — one field, and nothing else

`summarize_evidence` in `backend/app/lab/diagnosis.py` gains an optional `outcomes`
argument. When the caller supplies it:

- every episode row gains `task_outcome`, the adjudicated public outcome of that episode;
- `format` becomes `faultlab-compact-evidence/v2-task-outcome`;
- the `interpretation` legend gains exactly one structural clause naming the new field and
  its provenance.

`backend/app/lab/completion_study.py` supplies that map from the trials it already holds.
**No other call site passes it**, so the Explorer's context, the Diagnostician's context and
every learning-loop context keep byte-identical `…/v1` output.

### Why this is presentation and not disclosure

This matters, so it is stated up front and is checkable against the saved contexts:

1. The adjudicated outcome **is already in the Mechanic's context**. The saved Phase 5
   proposal input contains `observed_outcomes` with `outcome: "SAFE_UNRESOLVED"` for the
   three failing B0 episodes. Phase 8 moves that same value next to each episode; it does
   not reveal a new one.
2. The **semantics are already in the brief.** `completion.md` line 1 says "SAFE_UNRESOLVED
   is safe but incomplete; it is not an invariant violation." The legend clause therefore
   does not re-teach it, and deliberately says nothing evaluative — no sentence telling the
   model that a passing check row is not a completion, and no hint about what to do.
3. Nothing private is touched. `task_outcome` is the same public verdict the dashboard
   shows; no simulator truth, no fault schedule and no protected state enters any model
   input.

The legend clause, in full, is the only prose added anywhere in this phase:

> `task_outcome` is the adjudicated public outcome of that episode, the same value grouped
> in `observed_outcomes`.

## What is deliberately not changed

The Actor prompt, the Mechanic brief, the policy grammar, the interpreter, the C1–C8
scorer, the nine-case manifest, the episode limits, `policy-v0`, the preserved
`faultlab-actor-context/v1`, and **`assess_pairs` and every other acceptance gate.** Phase 6
is the matched control and differs only by this field.

## Design

Two completion studies, one per Mechanic model — DeepSeek V4-Pro-0813 and a matched V3.1
control — identical to Phase 6 in every other respect: same manifest, three trials per case,
two proposal slots.

### Primary read-out, fixed here

**Of the proposals generated, how many contain a step with `op == "retry_original_request"`
and `service == "notifications"`?** Directly comparable to the running **0 of 6** across
Phases 5 and 6.

### Secondary read-outs, recorded but not gating

Fixed in advance so they cannot be scored loosely afterwards:

- **Legibility.** Each generated proposal's free text is classified
  `ACKNOWLEDGES_INCOMPLETION` if it states in any wording that the task, the confirmation or
  the notification did not complete or was not delivered in the failing episodes; otherwise
  `NOT`. **The exact quoted sentence behind every classification is pasted into the
  results**, so each call is checkable rather than asserted.
- **Recurrence of the Phase 7 error.** Whether any output repeats the "no failing episodes"
  reading.

These separate two very different outcomes: *still cannot see the failure* versus *sees the
failure and still will not act on it*. Phase 7 predicts the second, and the second would be
the more useful finding.

## The uninformative-stop rule, declared in advance

Phase 6 measured the declared source gap at **4.4% leaky**: the baseline completes the
source case in 2 of 45 valid triggered episodes. A three-trial zero-completion controls gate
therefore stops by chance roughly 13% of the time, and study 6B was lost exactly that way,
producing no proposal and no information about the read-out.

Adding trials does not help — against an absolute-zero gate, more trials can only make a
stop *more* likely. **The gate is not touched.** Instead, one repeat is permitted per model,
under four conditions fixed here:

1. It applies **only** to a study that stopped at the controls gate, which yields zero
   proposals and therefore zero information about the primary read-out.
2. A study that produced **any** proposal is never repeated, whatever the proposal said.
3. At most **one** repeat per model. Four studies maximum across the phase.
4. Every run is reported, including the stopped one, with its episode counts and cost.

This is not resampling: nothing is being re-rolled that bears on the measurement. If a
repeat also stops, the phase reports fewer than four proposals and says so.

## Limits

- At most 4 studies, 2 proposal slots each. **No second arm**, whatever the result.
- No post-hoc change to any threshold, read-out or classification rule.
- No edit to the grammar, interpreter, scorer, manifest, Actor prompt or acceptance gates.
- Every trial, invalid proposal, duplicate and stopped study is retained.
- Source frozen and the database snapshotted before the first study; hashes compared against
  Phase 6 to confirm that only the expected one moved.

## Honest prior

Phase 7's A2 handed the models a complete, correct diagnosis — strictly more than any
evidence-format change can deliver — and **0 of 4** emitted the step. Phase 8 delivers less
than that. It targets the one thing the probes actually implicated, and it may fail for the
same reason A2 failed. The secondary read-out is what makes a failure worth the money.

## Budget

Reserved worst case 484 calls per study: about $24.12 for a V4 study and $10.12 for a V3.1
study, **$68.48** if all four run to the reservation. Realistic expectation is far lower —
Phase 5 and Phase 6 studies actually cost $0.75 to $1.77 each — so roughly **$4 to $8**.
Against **$956.02474** remaining.
