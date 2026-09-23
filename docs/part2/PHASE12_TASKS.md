# Phase 12 progress

Protocol: [PHASE12_EXPERIMENT.md](PHASE12_EXPERIMENT.md). Results: [PHASE12_RESULTS.md](PHASE12_RESULTS.md).
Checked means done and verified, not planned.

## Analysis before any paid call

- [x] Corrected an earlier recommendation after reading `assess_pairs` properly: it requires **all 42 trials valid** with no per-case exclusion, so "retain and continue past a lab error" would have run the full batch and still returned `INCOMPLETE` — more money, same non-result.
- [x] Measured where attempts actually die, across all 39 prior replay attempts: **19 of 39 (49%) to infrastructure**, the largest channel being 13 `EvidenceDenied` downstream of a `LAB_ERROR`.
- [x] Measured that **22 of 29 `LAB_ERROR` episodes are pure transport failures** (18 `CONNECTION_ERROR`, 4 `REQUEST_TIMEOUT`).
- [x] Measured the untriggered-fault channel and decided **not** to fix it: 2.5% of episodes never fire their fault, all 24 are `SAFE_UNRESOLVED` with 8.0 actor calls against 5.5 for triggered ones. Replacing those trials would be selection, which Phase 6 forbade, so they stay fatal.

## The change

- [x] Bounded, blind retry of the Actor's model call on `CONNECTION_ERROR` and `REQUEST_TIMEOUT` only — codes that mean no generation arrived, so nothing was observed and nothing can be selected on.
- [x] `EMPTY_FINAL_RESPONSE` deliberately **not** retried: a response that arrived is a generation, and retrying it would be a re-roll.
- [x] The retry consumes a metered model call and is recorded as an `actor_transport_retry` event.
- [x] Tests: exactly one retry never two; the retry is metered and recorded; four delivered-response codes are proven never to retry; no raw SDK text persisted.
- [x] 573 backend tests, 124 frontend tests, build and 3 browser fixtures green. `scorer_hash`, `actor_prompt_hash` and `adapter_hash` verified unchanged; exactly one source file differs from the Phase 11 freeze.

## The run, and why it measured nothing

- [x] 28 attempts, **0 scored**, $8.15, aborted at the attempt cap.
- [x] Diagnosed: **W&B Weave ingestion degraded from a 0.9% to a 31% per-episode failure rate** between Phase 11 and Phase 12 (19 `DEADLINE`, 9 `TRANSPORT`). A batch needs all 42 episodes verified, so no batch could complete.
- [x] **Corrected an incorrect first call.** On seeing the failures I said it was "a regression I introduced". It was not: **0 `LAB_ERROR` episodes in 91**, **0 new provider failures**, and the retry never fired once. Every episode ran to `COMPLETED`; the failure was entirely downstream.
- [x] Confirmed the 28 failures never recovered — the evidence bundles for those episodes still do not exist.

## Harness fixes made in response

- [x] **Circuit breaker** in the runner: abort after 4 consecutive attempts produce no validation assessment, naming ingestion health as the thing to check. Would have capped this run's loss at about $1.
- [x] **`check_ingestion_health.py`**, a read-only pre-flight guard that refuses to bless a run when the ingestion failure rate is materially above baseline, and reports the implied probability that a 42-episode batch completes.
- [x] **Recorded a bug found in that guard**: its first version reported "HEALTHY" because it ordered records with no `ORDER BY` and then sliced. A guard giving false confidence is worse than no guard.

## State

- [x] The retry fix is **built, tested and unmeasured**. Its target is unchanged and still worth measuring when the dependency recovers.
- [x] No policy accepted; the replayed policy is still `REJECTED`. Phase 11's result is not revised by a run that measured nothing.
- [x] Cost $8.15 against a $160 guard. Across Phases 2–12: $243.00 charged, $757.00 remaining.
