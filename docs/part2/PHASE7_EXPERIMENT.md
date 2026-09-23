# Phase 7 protocol — where exactly does the repair get lost?

Written **before** any paid call, after Phase 6 refuted the brief-ambiguity hypothesis.
This is the predeclared plan. Results go in `PHASE7_RESULTS.md`; progress in
`PHASE7_TASKS.md`.

Across Phases 5 and 6, **0 of 6** generated proposals contained
`retry_original_request` for notifications. Phase 6 established that the models believe the
step is permitted, so the loss happens somewhere between reading the evidence and emitting
the policy. This phase locates it, cheaply, before spending on another study.

## The two remaining hypotheses

- **H2 — visibility.** The failure mode is not legible in the supplied evidence.
  `summarize_evidence` interns repeated observation rows, so `TRANSIENT_UNAVAILABLE`
  appears literally **twice in ~24,000 bytes**, reachable only by dereferencing a table
  index into a shared `results` array.
- **H4 — hand-off.** The failure *is* legible and the model can state it in prose, but it
  cannot carry that understanding into the structured policy in a single generation. Two
  observations support this: Phase 5's V3.1 wrote "adds a retry mechanism … by retrying the
  original `send_confirmation` request" and emitted a policy containing no retry step, and
  Phase 6's probe scored 6 of 8 on the direct question against 3 of 8 on the open one.

H1 (belief) is closed by Phase 6 and is not revisited. H3 as originally written — "does not
map the concept onto the grammar" — is refined into H4, which makes it testable.

## Part A — two discriminating probes (non-scoring)

Same discipline as Phase 6 Part A. **No campaign, no study, no trial, no world, no policy
record.** Outputs land in `artifacts/phase7-2026-09-20/` and are fed into nothing. Both
probes replay the **exact** saved Phase 5 first-slot proposal contexts
(`…889f75d6…-1` for V4, `…122d93e0…-1` for V3.1). 2 models × 2 probes × 2 repeats = **8
requests**.

### Probe A1 — can it see the failure?

Question, naming no op and no remedy:

> For each failing episode in the supplied development evidence, state what happened to the
> notifications operation: was it ever accepted by the service, and what did the delivered
> responses say? Quote the error codes you find.

**Read-out:** does the answer (a) state the notification operation was never accepted, and
(b) quote `TRANSIENT_UNAVAILABLE`?

### Probe A2 — given the diagnosis, can it emit the policy?

The model receives the same context plus a **purely descriptive** diagnosis containing only
facts already present in that evidence, naming no op, no remedy and no desired behaviour:

> In the three failing episodes the actor dispatched one `send_confirmation` whose two
> transport attempts each returned a delivered `TRANSIENT_UNAVAILABLE` error. The service
> never recorded the notification operation, so no receipt exists. The actor then read the
> notification status repeatedly and reported truthfully that the outcome was unknown.

It is then asked for a policy under the unchanged `completion.md` brief and output schema.

**Read-out:** does the returned policy contain a step with
`op == "retry_original_request"` and `service == "notifications"`?

**A2's output is not a candidate.** It is never entered into a study, never scored against
a world, never given a policy version, and never cited as evidence that a repair works. It
answers one question: whether a correct diagnosis is sufficient to produce the step.

## Predeclared selection rule for Part B

Fixed here, before either probe runs:

- **A1 mostly fails** (fewer than half the responses state non-acceptance *and* quote the
  error code) → **H2 selected.** Part B inlines the delivered error codes instead of
  interning them.
- **A1 mostly succeeds and A2 mostly succeeds** (at least half of each) → the diagnosis is
  available and sufficient, so the loss is the single-shot hand-off → **H4 selected.** Part
  B splits the Mechanic request into two: one call that returns a prose diagnosis, then one
  that returns the policy conditioned on the model's **own** diagnosis. No diagnosis
  written by me ever reaches the study.
- **A1 mostly succeeds and A2 mostly fails** → neither arm is indicated: the model can see
  the failure and still will not emit the step even when handed the diagnosis. **Part B is
  not run in this phase.** That result is reported as-is, and the next phase is designed
  around it rather than guessed at.

"Mostly" means at least half of the 4 responses for that probe, counted across both models,
with the per-model split reported separately.

## Part B — one single-variable study pair, if indicated

Two completion studies, one per Mechanic model, identical to Phase 6 in every other
respect: same nine-case manifest, three trials per case, two proposal slots, unchanged
`policy-v0`, preserved `faultlab-actor-context/v1`, unchanged C1–C8 scorer, unchanged
episode limits, **and no change to `assess_pairs` or any acceptance gate.** Phase 6's two
studies are the matched controls.

**Primary read-out, directly comparable to the running 0 of 6:** of the proposals
generated, how many contain `retry_original_request` for notifications.

## A known limitation this phase does not repair

Phase 6 measured the declared source gap at **4.4% leaky** — the baseline completes the
source case in 2 of 45 valid triggered episodes. The controls gate wants zero completions
in three trials and `assess_pairs` wants `B0 completed == 0` on the candidate pairs, so each
stage fails by chance roughly 13% of the time. Study 6B ended exactly that way.

**This phase does not touch either gate.** Making the acceptance threshold comparative
rather than absolute would change what "qualified" means in this project, and that is a
standards decision to be raised explicitly and separately, not folded into an experiment
whose result it would flatter. If a Part B stage stops on a baseline completion, that is
recorded as an uninformative stop, not as evidence about the candidate.

## Limits

- Part A: 8 probe requests, no trials. Part B: at most two studies, two proposal slots each.
- **No second Part B arm**, whatever the first shows. The other hypothesis stays open.
- No resampling, no replacement trial, no post-hoc change to any threshold or read-out, no
  edit to the policy grammar, the interpreter, the scorer, the manifest, the Actor prompt or
  any acceptance gate.
- Every probe response, trial, invalid proposal and duplicate is retained.

## Budget

Part A: 8 requests, worst case about **$0.40**. Part B, if indicated: 2 × 484 reserved,
worst case about **$22**. Total worst case **$22.40** against $956.30770 remaining.
