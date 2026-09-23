# Recommended next phase — Phase 17: the first full-loop run on the fixed setup

Written after Phase 16 (2026-09-22). The declared protocol is
`docs/part2/PHASE17_EXPERIMENT.md`. What Phase 16 found and built is in
`docs/part2/PHASE16_RESULTS.md`. **Read both before doing anything.**

## Status

**Declared and reviewed twice. Awaiting the user's approval to spend.** Nothing has been run.
The user approves each paid phase separately, and a checkpoint after 12 attempts needs a
second approval.

## What Phase 17 is

- Up to 60 fresh, full completion studies: controls → Mechanic → source gate → validation.
- Actor context v4 (the citation fix), the unchanged gate.
- It stops at the first **certified completion repair**:
  - `OBSERVED_IMPROVEMENT` under the unchanged `assess_pairs`; **and**
  - `L − B0 ≥ 2` completions on one validation case other than `notification-2` and
    `healthy`.
- Spend guard $150 at the conservative bound (~$139 last start). Breaker at 5 consecutive
  infrastructure deaths.
- Expected: ~4% per study, ~25 studies, ~$55 at the bound, if the v1-era step rate holds on
  v4 — which is unmeasured.

**It never writes ACCEPTED.**
- Completion studies cannot, by design.
- The spec says a completion-only source does not qualify for promotion.
- ACCEPTED here means source + active challenge + promotion-partition batch.

A route from a certified repair to ACCEPTED would be a separate, separately declared phase.

## Why not the old recommendation

The old plan was "run full completion studies until one is ACCEPTED, 4–14 studies, $15–50".
It could not work:
- a completion study cannot write ACCEPTED;
- the default launcher runs the v1 Actor context, which is exactly what killed 4 of 5 step
  candidates;
- the Mechanic's second slot is a duplicate 20 of 25 times at temperature 0;
- validation is single-shot and passes a working policy ~1 time in 3.

## Operator procedure

Follow `PHASE17_EXPERIMENT.md` "Operator procedure" exactly:
1. Restart both services deliberately, with the frozen settings file, without reload and
   detached.
2. Run the free ingestion health check.
3. Check the runner's sha.
4. Run `run_full_loop.py` with every pin and `--stop-after 12`.
5. Reconcile, then report to the user.

The runner refuses to start on any code, settings, configuration or process mismatch.

## After Phase 17

- **If certified:**
  - report it with its denominator, S4 and the funnel;
  - the next decision is whether to design an honest completion → ACCEPTED route (held-out
    promotion partition, perhaps a challenge), declared before its data exists.
- **If step candidates keep qualifying but validation keeps dying:** the constraint is batch
  fragility. The Actor lapse behind 73 of 73 untriggered faults is the next target, never the
  gate.
- **If the step rate collapses on v4:** report it as a spend decision, not as proof the rate
  fell.
- **Pooling rule:** any later run whose success is a certified completion repair must quote
  its attempts pooled with Phase 17's.

## Budget

**$436.73 conservatively charged, $563.27 remaining** of the shared $1,000. Phase 16 cost $0.
Every figure is a per-call upper bound. Token counts suggest the real bill is ~10× lower
(unverified; the W&B billing page is the only proof).
