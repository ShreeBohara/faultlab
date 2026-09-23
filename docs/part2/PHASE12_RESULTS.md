# Phase 12 results — September 21, 2026

Protocol fixed before any paid call: [PHASE12_EXPERIMENT.md](PHASE12_EXPERIMENT.md).

## The run aborted on an external dependency, and measured nothing

**28 attempts, 0 scored replays, $8.15.** Every attempt died the same way, and it was not
the experiment and not the code change.

| | episodes ingested by Weave | retryable ingestion errors |
|---|---|---|
| Phase 11 (~15:00) | 323 of 326 — **99.1%** | 3 |
| **Phase 12 (~19:00–22:00)** | 63 of 91 — **69%** | **28** (19 `DEADLINE`, 9 `TRANSPORT`) |

W&B Weave trace ingestion degraded from a 0.9% per-episode failure rate to **31%** between
the two runs. A validation batch needs all 42 episodes verified, so at that rate the
probability any batch completes is effectively zero — which is exactly the 0 of 28 observed.
The evidence reader's deadline is capped at 60 seconds by design; during the degradation the
traces did not land inside it.

## A correction

On first seeing 28 failures I said this was "a regression I introduced". **It was not**, and
the evidence is unambiguous:

- **0 `LAB_ERROR` episodes** across all 91 Phase 12 episodes.
- **0 new provider failures** — the retry this phase added never fired once.
- Every episode ran to `COMPLETED`; the failure is entirely downstream, in evidence
  verification.

The change shipped in this phase is therefore **built and tested but unmeasured**.

## What was built, and is ready

A bounded, blind retry of the Actor's model call on `CONNECTION_ERROR` and `REQUEST_TIMEOUT`
only — the two codes that mean no generation arrived, so nothing was observed and nothing
can be selected on. `EMPTY_FINAL_RESPONSE` is deliberately excluded, because a response that
did arrive is a generation and retrying it would be a re-roll.

- 573 backend tests, 124 frontend tests, build and 3 browser fixtures green.
- Tests prove exactly one retry (never two), that the retry is metered and recorded, and
  that four delivered-response codes are **never** retried.
- `scorer_hash`, `actor_prompt_hash` and `adapter_hash` all verified unchanged; exactly one
  source file differs from the Phase 11 freeze.

Its target — 22 of 29 historical `LAB_ERROR`s being pure transport failures — is unchanged
and still worth measuring when the dependency recovers.

## What this run did change: a circuit breaker

The runner spent 28 attempts failing identically. It should have stopped after a handful.
It now aborts when **4 consecutive attempts produce no validation assessment**, naming
evidence-ingestion health as the thing to check. That is a harness safety fix, not a gate
change, and it would have capped this run's loss at about $1.

## A pre-flight check, and a bug found in it

`scripts/experiments/check_ingestion_health.py` (read-only, no model call) reads the most
recent ingestion records and refuses to bless a run when the failure rate is materially
above the ~1% healthy baseline. Run against the current store it reports:

```
last 120 ingestion records
  states      : {'RETRYABLE_ERROR': 28, 'INGESTED': 92}
  error codes : {'TRANSPORT': 9, 'DEADLINE': 19}
  failure rate: 23.3%   (Phase 11 healthy baseline 0.9%)
  => P(a 42-episode batch fully verifies) = 0.0%
DEGRADED: ... A paid run would very likely produce no scored result. Wait.
```

**The first version of this tool was wrong and said "HEALTHY".** It selected records with a
SQL query carrying no `ORDER BY` and then sliced the resulting list, so "the last 120" were
not the last 120. A guard that gives false confidence is worse than no guard, so it is
recorded here rather than quietly corrected: the query now orders by `rowid desc` explicitly.

## Discipline

- The spend guard and attempt cap worked: the loss was **$8.15** against a $160 guard.
- Every attempt, ingestion record and error code is retained.
- No policy was accepted; the replayed policy is still `REJECTED`.
- Nothing about Phase 11's result is revised by this run, which measured nothing.

## Cost

Phase 12: **$8.15**. Across Phases 2–12: **$243.00 charged, $757.00 remaining.**

## What should happen next

1. **Do not re-run while ingestion is degraded.** Check the recent `ingestions` records
   first: if the `RETRYABLE_ERROR` share is materially above the ~1% seen in Phase 11, any
   run will fail the same way. The circuit breaker now enforces this cheaply, but checking
   first is cheaper still.
2. **Then re-run Phase 12's measurement unchanged** — 20 scored replays, the retry fix
   included — to get the properly powered gate pass rate that Phase 11 left at 2 of 6
   (p = 0.088).
3. The untriggered-fault channel (2.5% per episode, ~35–45% of batches) remains unfixed and
   must stay fatal, as declared.
