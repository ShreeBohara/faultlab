# Phase 12 protocol — stop losing half of every run to transient network errors

Written **before** any paid call. Results go in `PHASE12_RESULTS.md`; progress in
`PHASE12_TASKS.md`.

Phase 11 fixed the citation failure that was making the gate reject working repairs, but
left the declared read-out at **2 of 6, p = 0.088 — not significant**, because it could not
afford enough scored replays. The reason it could not afford them is measured:

> **19 of the 39 replay attempts ever run (49%) died to infrastructure, not to the
> experiment.**

| cause | attempts | |
|---|---:|---|
| `EvidenceDenied`, downstream of a `LAB_ERROR` | 13 | **this phase targets these** |
| `WaitingEvidence` | 3 | out of scope |
| `ReadError` in the runner's own HTTP poll | 3 | out of scope |
| scored (a real result) | 20 | — |

And across the whole store, **22 of 29 `LAB_ERROR` episodes are pure transport failures**:
18 `CONNECTION_ERROR`, 4 `REQUEST_TIMEOUT`. One of them makes one episode a lab error, the
evidence gateway refuses that episode as ineligible, and the entire 42-episode batch dies.

## The change: a bounded, blind retry of the Actor's model call

On a `RuntimeProviderError` whose code is **`CONNECTION_ERROR` or `REQUEST_TIMEOUT`**, the
Actor retries its model call **once**. Everything else re-raises exactly as today.

### Why this is not resampling

This project forbids replacing a trial, because choosing again after seeing an unfavourable
result is selection. Phase 6 established that and it still holds.

**A transport failure is different in kind: no generation was received.** There is nothing
to look at, so there is nothing to select on. The retry is *blind* — it cannot prefer one
outcome over another, because no outcome existed. That is the whole argument, and it is why
the retry is restricted to codes that mean "no response arrived".

### What is deliberately NOT retried

- **`EMPTY_FINAL_RESPONSE` (6 occurrences).** A response *did* arrive; it was empty. That
  may be model behaviour rather than transport, and retrying it would re-roll a generation
  the model actually produced. Excluded, and the 6 cases are accepted as losses.
- Schema failures, a provider returning a different frozen model, budget exhaustion, content
  refusals — all re-raise unchanged.
- The Mechanic and Explorer roles. The Actor accounts for 24 of 28 recorded provider
  failures, and replays make **no** Mechanic call at all, so Actor-only keeps this a single
  change. The Mechanic is named as out of scope rather than silently skipped.

### Accounting and visibility

- The retry **consumes a model call** through the ordinary meter and campaign ledger. It is
  not free and is not hidden from the budget.
- The failed attempt is already written to `provider_failures`; the retry is additionally
  recorded on the episode so every retried episode is identifiable afterwards.
- If the retry also fails, the episode becomes `LAB_ERROR` exactly as today.

### What this does not touch

`checks.py`, `assess_pairs`, the manifest, the policy grammar, the interpreter, the Actor
prompt, the scorer. No gate is loosened. `scorer_hash` must not move.

## A loss channel this phase does NOT fix, and will not

**Untriggered faults stay fatal, by design.** Measured across 970 scheduled, completed
episodes: **2.5% never trigger their fault** (24 of 970). Every one of those 24 is
`SAFE_UNRESOLVED` with **8.0 actor calls against 5.5 for triggered episodes** — the Actor
burns its entire turn budget without ever reaching `send_confirmation`, so the fault never
fires and the episode never tested what it was supposed to test.

`assess_pairs` correctly refuses to judge such a batch. **Replacing those trials would be
selection** — it would bias toward runs where the Actor happened to behave — so they remain
fatal. At 2.5% per episode across the 36 fault-bearing episodes of a validation batch,
roughly **35–45% of batches will still die this way after this phase**, and that is
expected, not a failure.

Reducing it means changing Actor behaviour, which is a separate phase with its own
regression guard.

## Read-outs, fixed here

**Primary (harness):** the proportion of attempts that yield a scored validation assessment.
Baseline across all 39 prior attempts: **20 of 39 = 51%**. Reported with a Wilson interval
and compared by Fisher's exact, two-sided.

**Secondary, and the reason the fix is worth making:** with more scored replays affordable,
the gate pass rate under the Phase 11 citation protocol, against **Phase 10's 0 of 13**
baseline. Phase 11 reached 2 of 6 (p = 0.088); this phase targets **20 scored replays**,
which at the observed rate would settle it either way.

**Also recorded:** how many episodes retried and succeeded; how many retried and still
failed; the untriggered-fault rate, to confirm this change did not alter it; and the
citation-corruption and violation rates, to confirm Phase 11's result holds.

## Limits

- One retry. Never two.
- Two error codes. No others, whatever the run shows.
- **20 scored replays, attempt cap 28, spend guard $160.** Stop at the cap and report a
  shortfall rather than extending it.
- Every attempt, retry, lab error and incomplete batch retained and reported.
- The replayed policy stays `REJECTED`; no replay can accept anything.
- Source frozen and the database snapshotted first; only `source_hash` and the derived
  hashes may move, and **never `scorer_hash`**.
- The change is testable offline at $0 and will be proven there before any paid call.

## Expected effect, stated in advance so it can be wrong

Retrying should take the infrastructure-death rate from ~49% of attempts to roughly the
residual `WaitingEvidence` + `ReadError` rate (~15%). Combined with the untriggered-fault
rate that remains, the expected yield is **~0.6 scored assessments per attempt**, against
0.51 today — so ~28 attempts to reach 20 scored, at roughly **$95 and 3–4 hours**.

If the retry does not move the yield, that is reported as a null and the residual causes are
named.
