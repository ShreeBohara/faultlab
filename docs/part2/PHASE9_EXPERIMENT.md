# Phase 9 protocol — does the Phase 8 result replicate?

Written **before** any paid call. This is the predeclared plan. Results go in
`PHASE9_RESULTS.md`; progress in `PHASE9_TASKS.md`.

Phase 8 moved the read-out from 0 of 6 to 2 of 4 by binding the adjudicated per-episode
outcome into the evidence the Mechanic reads. That rests on **one distinct policy from one
model**, compared against historical controls run days earlier under different code. This
phase asks the only question that matters next: **does it replicate, and is it the field?**

This is a power problem, not a design problem. Nothing about the treatment changes.

## The design: paired, interleaved, concurrent control

Two arms differing in exactly one thing — the declared presentation of the reviewed
evidence:

| Arm | Protocol | What it reproduces |
|---|---|---|
| **T** | `faultlab-compact-evidence/v2-task-outcome` | Phase 8 |
| **C** | `faultlab-compact-evidence/v1` | Phases 5 and 6 |

Three deliberate improvements over Phase 8's comparison, all of which remove confounds
rather than add variables:

1. **Concurrent, not historical.** Phase 8's control was Phase 5/6, run earlier on
   different code. Here both arms run today, on identical code.
2. **Strict alternating pairs on one backend process**, with the leading arm swapped each
   round. Phase 8 restarted the backend between arms and ran them back to back, so any
   provider drift over the session was confounded with the arm. Pairing removes that, and
   swapping the lead removes any residual ordering effect within a round.
3. **Powered.** Fourteen informative studies per arm instead of one each.

Everything else is byte-identical to Phase 8: same nine-case manifest, three trials per
case, `PROPOSAL_SLOTS = 2`, unchanged `policy-v0`, preserved `faultlab-actor-context/v1`,
unchanged C1–C8 scorer, unchanged episode limits, and **no change to `assess_pairs` or any
acceptance gate.** The Mechanic is DeepSeek V4-Pro-0813 in both arms; the Actor is V3.1, as
always.

**V3.1 as Mechanic is not run in this phase.** Phase 8 showed it reproduces its Phase 5
output byte for byte. Re-measuring a byte-identical null is a poor use of the budget next to
powering the arm that actually moved; that is stated here rather than discovered later.

## The one code change, and why it is not a second variable

`queue_completion_study` accepts a declared `evidence_protocol`, validated against an
allowlist that lives with the protocols in `diagnosis.py`, recorded in the study record and
selectable from the API and CLI. This is the **mechanism that makes the control runnable**,
exactly as Phase 4's `actor_context_protocol` was. The default is Phase 8's treatment, so an
unqualified study behaves exactly as Phase 8's did.

**Both arms are gated on byte-identity before the phase runs**, not just the treatment:

- arm T's `format` and `interpretation` are diffed against Phase 8's saved
  `proposal-context-8a-1.json`;
- arm C's are diffed against Phase 6's saved proposal context, and its episode rows must
  carry no `task_outcome` key.

Both checks passed before any paid call. They are gates on running the phase, not
footnotes.

**Pre-flight checks the runner enforces on every round:** the backend is live-enabled, its
Mechanic role resolves to the model this protocol declares, no other execution is active,
and the confirmed W&B entity matches the configured one. A mismatch aborts rather than
silently running the wrong experiment.

## Primary read-out, fixed here

**Of each study, does its FIRST proposal contain a step with
`op == "retry_original_request"` and `service == "notifications"`?**

One independent draw per study. First proposal, not any proposal: Phases 5, 6 and 8 each
produced a byte-identical second proposal, so an any-proposal read-out double-counts a
single decision.

**Every resolved Mechanic answer is a draw.** A first proposal that is a policy without the
step, a well-formed refusal (`MechanicNoChange`), or an output rejected as invalid all count
as draws that do not contain the step. Exactly two cases yield no draw, both of them cases
where no answer was ever established: the study recorded **no candidate at all** (a
controls-gate stop, or a lab error before any Mechanic call), or its only candidate is still
**unresolved** because the study died between the Mechanic call and the parse. This is stated precisely
because the natural implementation gets it wrong: treating a refusal as "no draw" would
silently discard and resample a real answer, which is both selection on the outcome and a
violation of the never-repeat rule below.

**Test declared in advance:** Fisher's exact, two-sided, on the 2×2 table of arm against
draw. α = 0.05. The exact p-value and the raw counts are reported whatever they are, and
**no interim result stops the run.**

**Power, computed rather than hoped.** With 14 informative studies per arm against a
control rate of 0, exact power at α = 0.05 is:

| true treatment rate | 0.8 | 0.7 | 0.6 | 0.5 | 0.4 | 0.3 |
|---|---|---|---|---|---|---|
| power at n = 10 | 0.99 | 0.95 | 0.83 | 0.62 | 0.37 | 0.15 |
| **power at n = 14** | **1.00** | **1.00** | **0.98** | **0.91** | **0.72** | **0.42** |

The smallest significant split is 5 of 14 against 0 of 14 (p = 0.041). n was raised from 10
to 14 precisely because at n = 10 the design had 0.37 power against a plausible modest
effect, which is not enough to support the "T ≈ C, both low → Phase 8 was luck" conclusion
this protocol commits to drawing. **Even at n = 14, a true rate below about 0.4 is not
reliably detectable**, so a null result is reported as "no effect large enough for this
design to see", never as "no effect".

Phase 8's own numbers under this read-out, stated symmetrically:

| | V4 Mechanic | V3.1 Mechanic | total |
|---|---|---|---|
| treatment (`v2`) | 8A: **1 of 1** | 8B: 0 of 1 | **1 of 2** |
| control (`v1`) | 5A, 6A: 0 of 2 | 5B: 0 of 1 (6B produced no proposal) | **0 of 3** |

An earlier draft of this protocol reported the treatment side as "1 of 1" while counting
V3.1's *control* study in the control side — asymmetric inclusion that flattered the
treatment. The table above is the corrected version. These are context; they are **not**
part of Phase 9's table, and Phase 9 runs V4 only.

## Secondary read-outs, recorded but not gating

Fixed here so they cannot be chosen afterwards:

- Any-proposal and **distinct-policy** counts per arm, alongside the primary.
- Rate of byte-identical second proposals per arm.
- Candidate qualification rate (`SOURCE_QUALIFIED`) per arm.
- For candidates containing the step: how many of three source trials completed. This asks
  whether the repair *works*, separately from whether it is *proposed*.
- C5/C6 violation counts in the L and B0 arms. Phase 8 saw an Actor-citation failure in
  both, and this is the first dataset large enough to estimate that rate.
- Baseline completions of the source case across every control trial, which sharpens the
  4.4% leakage figure measured in Phase 6 on 45 episodes.
- Legibility of each first proposal's explanation, under Phase 8's rule, with the quote.

## Stopping, replacement and spend rules, declared in advance

- **Target 14 informative studies per arm.** A study is informative if it recorded any
  first candidate — including a refusal.
- A study that recorded **no candidate at all** yields no draw. It is **retained and
  reported**, and replaced. **A study that produced any proposal is never repeated**,
  whatever it said.
- **Strict alternating pairs.** Each round runs exactly one study per arm, and the leading
  arm swaps every round. **The phase ends as soon as either arm reaches its target or its
  attempt cap**, so every study in the analysis has a temporal partner in the other arm. An
  arm is never left running solo after the other finishes — that would reintroduce exactly
  the drift confound this design exists to remove.
- **Attempt cap 18 per arm.** If an arm exhausts its cap without reaching 14, the phase
  reports the smaller number and says so.
- **Spend guard $150**, checked against the charged upper bound before every study with
  **$12 of headroom** — more than one qualifying study, which runs 54 episodes rather than
  12 and is the most expensive thing the phase can do. The guard is a **safety stop, not a
  planned one**: tripping it aborts the phase and is reported as an abort, because a spend
  cap that binds is an outcome-correlated stopping rule (qualifying studies cost more, so a
  binding cap would preferentially truncate whichever arm qualifies more). Realistic
  expectation is far below it: Phase 8's V4 study cost $1.60, so ~32 studies is roughly
  **$50 to $70** with a few qualifying runs.
- **A budget read that fails aborts the phase.** The runner never treats an unreadable
  budget as $0.
- **A study that outlives its watch aborts the phase** unless the backend returns to idle,
  because an orphaned study holds the coordinator and every later attempt would fail
  instantly, burning the attempt cap in seconds while appearing to run.
- **No interim peeking changes anything.** The run continues to its declared end regardless
  of how the counts look partway.

## Limits

- No change to the grammar, interpreter, scorer, manifest, Actor prompt, proposal slots or
  any acceptance gate.
- The read-out has **one implementation**, in the runner; the analysis script imports it
  rather than restating it, so the reported number cannot drift from the recorded one.
- No second intervention arm. If the replication fails, the next phase is designed from it,
  not patched on top of it.
- Every study, trial, invalid proposal, duplicate, lab error and stopped run is retained.
- Source frozen and the database snapshotted before the first study; hashes compared before
  and after, and only `algorithm_hash` and the derived `runtime_hash` may move.

## What each outcome would mean

- **T clearly above C.** The Phase 8 effect is real for this model. The field, not luck.
- **T ≈ C, both low.** Phase 8 was luck. That is a genuine finding and it retires the
  hypothesis honestly.
- **T ≈ C, both high.** Something other than the field changed between Phases 5/6 and now —
  most likely the provider. That would invalidate Phase 8's causal reading and is worth
  knowing more than a confirmation would be.

The third outcome is the one a historical control could never have detected, and it is the
reason this phase runs a concurrent one.

## This protocol was adversarially reviewed before any paid call

Six independent reviewers — experimental design, statistics, single-variable integrity,
runner correctness, test adequacy and house-rule compliance — read this document and the
code. They raised 47 findings; an adversarial refutation pass confirmed 30 and refuted the
rest. The confirmed findings are fixed here, and the ones that changed the science are
listed because a protocol that quietly absorbs its own review is not reviewable:

- **A Mechanic refusal was scored as "no draw" and the study resampled.** Six lenses found
  this independently. It would have discarded real answers and biased the primary read-out
  in whichever arm refuses more. The read-out rule above is the corrected one.
- **The historical Phase 8 tally was asymmetric in the treatment's favour** — V3.1's
  control study was counted while V3.1's treatment study was not. Corrected to 1 of 2.
- **n = 10 could not support the conclusions this protocol commits to drawing.** Raised to
  14, with the power table stated.
- **The terminal-status set omitted `INTERRUPTED`**, the one non-happy status the study
  engine actually emits, so a stopped study would have hung the runner until its timeout.
- **A failed study's campaign was dropped from spend accounting**, so real money would have
  been invisible to the guard, and an orphaned study would have silently burned the whole
  attempt cap in seconds.
- **An unreadable budget was treated as $0**; **`--confirm-entity` was never compared to
  anything**; **the declared Mechanic model was printed but never checked**.
- **Interleaving was abandoned exactly when the arms diverged**, letting the surviving arm
  run solo and reintroducing the drift confound.

Two findings were refuted and are recorded as such: the claim that the study timeout was
outcome-correlated at its original value, and the claim that arm C's presentation was never
gated — it was, against Phase 6's saved context.

