# Phase 7 progress

Protocol: [PHASE7_EXPERIMENT.md](PHASE7_EXPERIMENT.md). Results: [PHASE7_RESULTS.md](PHASE7_RESULTS.md).
Checked means done and verified, not planned.

## Part A — two discriminating probes

- [x] Declared both probes, the 2x2x2 design, both read-outs and the three-branch Part B selection rule before any paid call.
- [x] Built `scripts/experiments/locate_loss_probe.py`: dry by default, requires `--execute-live` and a matching `--confirm-entity`, reads the saved proposal inputs read-only, creates no campaign/study/trial/policy, asserts the mechanic role resolves to the requested model and that the provider returned it.
- [x] Fixed two defects in that script before spending: it resolved the model from settings rather than the flag, and it referenced a prompt module that does not exist. A2 now appends the real `MechanicOutput` JSON schema, so the only difference from a live proposal request is the diagnosis line.
- [x] Ran 8 requests, 2 models x 2 probes x 2 repeats, replaying the exact saved Phase 5 first-slot proposal contexts.
- [x] **A1: 0 of 4.** Every response quoted `TRANSIENT_UNAVAILABLE`; none stated the operation was never accepted. Three answered `UNCLEAR`.
- [x] **A2: 0 of 4.** Handed a purely descriptive diagnosis, no response emitted `retry_original_request`.
- [x] Recorded that A2's outputs are not candidates: never scored, never versioned, never entered into a study.
- [x] Reconciled probe cost: 8 requests, 66,072 in / 4,587 out, $0.28296 conservative.

## Part B — not run

- [x] Applied the predeclared rule honestly: branch 1 fired on 0 of 4 and selected H2.
- [x] Recorded, before deciding anything, that the probe had invalidated H2's declared intervention — the error code was retrieved 4 times out of 4, so de-interning targets a retrieval problem that does not exist.
- [x] Raised the fork explicitly rather than silently substituting a better arm. Options put to the user: run the declared H2 arm for completeness, or declare a new phase aimed at what the probe found.
- [x] **Resolved: declare a new phase.** The declared H2 arm was **not run**. No study, no trial and no paid call was made in Part B. See [PHASE8_EXPERIMENT.md](PHASE8_EXPERIMENT.md).
- [x] No resampling, no post-hoc threshold change, no edit to the grammar, interpreter, scorer, manifest, Actor prompt or any acceptance gate.

## Findings recorded

- [x] H2 as framed is dead: the delivered error code is legible; retrieval is not the blocker.
- [x] H4 is dead: supplying the diagnosis outright produces the step 0 times in 4.
- [x] New and better-supported explanation: the models do not represent "the task did not complete" as a failure at all. One equated "all C1-C8 checks passed" with "no failing episodes".
- [x] Cumulative across Phases 5-7: **0 of 6 study proposals and 0 of 4 probe proposals** contain the step.
- [x] Updated results, memory and the central checklist; carried the finding into the Phase 8 protocol.
