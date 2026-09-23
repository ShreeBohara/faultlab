# Phase 13 checklist — September 21, 2026

Results: [PHASE13_RESULTS.md](PHASE13_RESULTS.md). Protocol: [PHASE13_EXPERIMENT.md](PHASE13_EXPERIMENT.md).

## Run

- [x] Confirm the Phase 12 ingestion degradation had cleared before spending
      (`check_ingestion_health.py`, then a $4.70 single-replay probe under
      `artifacts/phase13-probe/`).
- [x] Freeze the declaration in the manifest before the first paid call: 20 scored, cap 30,
      spend guard $170, `v4-indexed-evidence`, replay-only.
- [x] Execute 30 attempts, 849 episodes, $91.42. No abort; the attempt cap ended the run.
- [x] Preserve the manifest, runner log and settings under `artifacts/phase13-2026-09-21/`.

## Read-outs, reported as declared

- [x] **Primary: 5 of 13 scored replays `OBSERVED_IMPROVEMENT`**, Wilson [0.177, 0.645];
      vs Phase 10's 0 of 13, Fisher two-sided **p = 0.039**.
- [x] **Report the shortfall as a shortfall**: the declared target was 20 scored and the run
      reached 13 at the attempt cap. The read-out was not re-declared after the fact.
- [x] Decompose the scored non-passes: 8 `INCOMPLETE`, **0 `NO_CHANGE`**. Zero quality
      rejections; pooled with Phase 11 that is 0 of 20.
- [x] **Secondary: yield is a null.** 13/30 = 0.433 against an all-prior 20/39 = 0.513 and a
      predicted ~0.6; Fisher **p = 0.63**. Phase 12's declared objective is unmet — recorded
      as unmet, not reframed.
- [x] Confirm the evidence channel was healthy: 5 `RETRYABLE_ERROR` of 848 episodes (0.6%,
      all `TRANSPORT`), mapping one-to-one onto the 5 `WaitingEvidence` deaths.

## Corrections made to my own earlier statements

- [x] **"The retry never fired — 0 events — that's a bug in my change."** Wrong. It fired 4
      times. My query searched `records` for events that live in the separate `events`
      table. The code was correct; the diagnostic was not.
- [x] **"The 17 unscored attempts died in the runner's own HTTP polling, not episode
      execution."** Wrong. `error_type` is written by `completion_study._execute`'s handler
      around `execute_slots`, so the failures are inside episode execution.
- [x] Recheck the Phase 12 write-up's claim that the retry is "unmeasured". It is measured
      now, by Phase 13, and it works: 4 of 4 retried failures survived against 0 of 10
      historically, Fisher **p = 0.0037** — flagged as a historical, not concurrent, control.

## Code changed this phase

- [x] `EpisodeMeter.transport_retry()` in `backend/app/lab/budgets.py` — admits a blind
      retry without spending an actor turn, charges the ledger and `model_calls`, and
      returns False rather than raising so a retry never replaces the transport failure
      that caused it.
- [x] `backend/app/agents/actor.py` — `model_call()` now fires only on the first attempt;
      the final-turn suppression is gone. The `actor_calls` contract bound (`le=8`) is
      unchanged and unraised; it still bounds generations.
- [x] `WorldControlError` in `backend/app/adapters/business_tools.py` — names the failing
      control operation. Subclasses `httpx.TransportError` so readiness probing and
      `execution_failure()` classify it exactly as before. **Instrumentation only; retries
      nothing.**
- [x] `backend/app/lab/completion_study.py` — an aborted study records `control_operation`
      and the wrapped cause class alongside `error_type`. Still never persists raw
      exception strings.
- [x] `checks.py` not opened; `scorer_hash` unchanged.

## Tests

- [x] A transport failure on the **final allowed turn** is retried and the episode survives
      (both `CONNECTION_ERROR` and `REQUEST_TIMEOUT`) — the case Phase 13 lost a batch to.
- [x] A retry that cannot be admitted re-raises the original transport failure and logs no
      retry event.
- [x] A failed control call names its operation for all four wrapped operations, stays an
      `httpx.TransportError`, and does not leak the underlying socket message.
- [x] A rejected control request (HTTP 403) is **not** wrapped and keeps `HTTPStatusError`.
- [x] The pre-existing assertion `actor_calls == len(requests) + 1` was changed to
      `actor_calls == len(requests) == 8`. **Recorded as a deliberate semantic change, not
      a weakened test** — it had been pinning the bug (a retry cost the episode a turn).
- [x] Existing guarantees still pinned: exactly one retry per turn, never two; the four
      delivered-response codes are never retried.
- [x] Full verification re-run green on this checkout: **581 backend tests** (573 + 8
      added here), **124 frontend tests**, production build.
- [ ] **Not green unconditionally.** The intermittent
      `test_failed_attempt_retained_without_replacement_and_reservation_released[untriggered]`
      failure (~1 in 8 full runs, pre-existing, investigated in Phase 10) is still
      unexplained. Never report the suite as unconditionally green.

## Open, and explicitly not done

- [ ] **Which control operation raises the `ReadError`.** 11 of 30 attempts (37%) died this
      way and Phase 13 cannot say whether it was `advance`, `create`, `snapshot`, `faults`
      or `stop`. The instrumentation to answer it ships here unused.
- [ ] **Whether a control call may be retried at all.** `advance()` and `create()` are not
      idempotent; replaying an `advance` whose response was lost could double-advance the
      world. `snapshot()` and `faults()` are read-only and look safe. This needs a design
      decision before any code, not a blind retry.
- [ ] **Measure the final-turn retry fix.** Built and tested, unmeasured — Phase 12's
      position exactly, and labelled the same way.
- [ ] Reach the declared 20 scored replays.
- [ ] The untriggered-fault channel stays fatal by design. Not a defect to fix.
- [ ] T065/T088/T097/T100/T102 in the sibling checklist. Phase 13 closes none of them.
