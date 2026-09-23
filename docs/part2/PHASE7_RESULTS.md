# Phase 7 results — September 20, 2026

Protocol fixed before any paid call: [PHASE7_EXPERIMENT.md](PHASE7_EXPERIMENT.md).
Progress: [PHASE7_TASKS.md](PHASE7_TASKS.md). Same $1,000 ceiling as Phases 2–6.

## Part A — both probes failed, and that is the finding

Eight non-scoring requests, two models × two probes × two repeats, replaying the exact
saved Phase 5 proposal contexts. No campaign, no study, no trial, no policy record.
Outputs in `artifacts/phase7-2026-09-20/`, fed into nothing.

| Probe | Question | Result |
|---|---|---|
| **A1** | Was the notification operation ever accepted, and what did the responses say? | **0 of 4 pass** |
| **A2** | Given a purely descriptive diagnosis, does it emit the policy step? | **0 of 4 pass** |

### A1 — the error code is visible; the *failure* is not

All four responses found and quoted `TRANSIENT_UNAVAILABLE`. **None could say the operation
was never accepted.** Three answered `UNCLEAR`. The fourth is the most informative single
response this project has produced:

> V4-Pro, repeat 1: "**The supplied development evidence contains no failing episodes.** All
> checks in every check row have `passed: true`, and the `observed_outcomes` show
> `failed_checks: []` for both arms."

The model read the C1–C8 check rows, saw every check passing, and concluded nothing had
gone wrong. It is not wrong about the checks — a truthful `SAFE_UNRESOLVED` passes all
eight. It is wrong about the task, which did not complete. V3.1 made a related error in the
other direction, reporting the operation as accepted "in episodes where a SUCCEEDED status
was delivered" — the *healthy control* episodes, conflated with the failing ones.

So the interning is not the binding problem. The error code was retrieved every time. What
the evidence does not let the model establish is **non-acceptance**, and its check-centric
presentation actively suggests there is nothing to repair.

### A2 — a correct diagnosis is not sufficient

Handed a plain-language diagnosis containing only facts already in the evidence — *"the
service never recorded the notification operation, so no receipt exists"* — **not one of
four responses emitted `retry_original_request`.** V4 restated the diagnosis accurately in
its own explanation, "a notification write that returned TRANSIENT_UNAVAILABLE twice and
left no receipt", and then proposed wait, read, wait, read, defer. V3.1 proposed wait and
read.

A2's outputs are **not candidates**. They were never scored against a world, never given a
policy version and never entered a study. They answer one question, and the answer is no.

Probe cost: 8 requests, 66,072 input and 4,587 output tokens, **$0.28296** conservative,
$0.07384 known-token estimate. Running total across Phases 2–7 Part A: 2,057 requests,
$43.97526 charged, **$956.02474 remaining.**

## The rule fired cleanly, and it selected an intervention the probe just undermined

Unlike Phase 6, the predeclared rule is unambiguous here. Branch 1 — "A1 mostly fails
(fewer than half state non-acceptance *and* quote the error code)" — fires on 0 of 4, and
neither other branch fires. **The rule selects H2**, whose declared intervention is:

> `summarize_evidence` stops interning observation result rows and inlines them, so every
> delivered `error_code` appears in full at every occurrence.

That intervention was written before the probe ran, on the theory that the error code was
buried. **The probe found the error code four times out of four.** De-interning addresses a
retrieval problem that does not exist, and A2 independently shows that even a perfect
diagnosis — a strictly stronger fix than any evidence-format change could deliver — does
not produce the step.

This is a methodological result in its own right: **the intervention was declared before
the hypothesis was tested, and testing the hypothesis invalidated the intervention.** The
honest options are to run the declared arm for completeness, or to declare a new phase
aimed at what the probe actually found. Choosing the second without saying so would be
selecting an intervention on the data, which this project does not do quietly.

## The fork was resolved: a new phase, and the declared arm was not run

The choice was put to the user with both options and their costs. **They chose to declare a
new phase.** So, for the record:

- **The declared H2 arm was not run.** Part B made no study, no trial and no paid call.
  Phase 7's entire spend is the 8 probe requests above.
- H2 is not "deferred for later". The probe refuted its premise, and this project does not
  keep a refuted arm on a shelf to look thorough.
- The replacement is [PHASE8_EXPERIMENT.md](PHASE8_EXPERIMENT.md), written before any Phase 8
  paid call and aimed at the thing A1 actually implicated: the per-episode task outcome is
  not legible in the evidence the Mechanic reads.
- Selecting a new intervention after seeing probe data is legitimate **only** because it is
  declared in the open, with its read-out fixed in advance and this paragraph recording that
  the previously declared arm was dropped rather than quietly replaced. Phase 8's result is
  not evidence about H2, and will not be reported as if it were.

An honest caveat carried into Phase 8: A2 shows that even a complete, correct diagnosis
handed to the model did not produce the step. Phase 8 delivers strictly less than that. It
targets the one thing the probe implicated, and it may well fail for the same reason.

## What Phase 7 establishes regardless

- **H2 as originally framed is dead.** The delivered error code is legible; retrieval is
  not the blocker.
- **H4 is dead too.** Supplying the diagnosis, which is what any successful
  evidence-format change would amount to, produces the step 0 times in 4.
- **A new and better-supported explanation.** The models do not represent "the task did not
  complete" as a failure at all. One explicitly equated "all C1–C8 checks passed" with "no
  failing episodes". The completion study's entire premise — that a safe unresolved task is
  a gap worth repairing — is stated in the brief but is not legible in the evidence the
  Mechanic reads.
- Cumulative across Phases 5–7: **0 of 6 study proposals and 0 of 4 probe proposals**
  contain the step, across two models, two briefs, and with the diagnosis handed over.
