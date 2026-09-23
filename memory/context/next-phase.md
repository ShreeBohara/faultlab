# Next phase: after Phase 19 (2026-09-23)

Read `docs/part2/PHASE19_RESULTS.md` first, then `PHASE18_RESULTS.md` and
`PHASE17_RESULTS.md`.

## Where things are

- **Phase 17** certified a completion repair on development cases (`dd62c857…`). It is not
  ACCEPTED.
- **Phase 18** ran it once on the private promotion partition. **Verdict HARM**, final. The
  one failure is attributed to a lab measurement defect, not to the policy. Held-out safety
  is **unshown**, and the partition is spent for this policy.
- **Phase 19 ($0)** diagnosed that defect, reproduced it and fixed it:
  - **What happened:** a request that must open a new connection was lost unsent during a
    >1 s lab event-loop freeze, while its tick was still counted.
  - **The freezes:** an open dashboard tab was polling two endpoints that parsed the whole
    store once a second. This is supported, not proven, for the historical cases.
  - **The fix:** per-campaign reads, a 10 s connect budget, and the
    `check_clock_drift.py` detector.
  - **Store-wide:** 4 drifts and 6 masked F1 faults. No declared read-out of Phases 13, 15
    or 17 changed.

## Runbook for any future paid run (new since Phase 19)

1. **Start the simulator only with `scripts/start-simulator.sh`,** because it passes
   `--timeout-keep-alive 75`. The keep-alive race has only a ~3 s margin otherwise.
2. **Close the dashboard tab, or confirm the lab loop is responsive:**
   `artifacts/phase19-2026-09-23/diagnosis/loop_latency.py 20` should show p99 well under
   100 ms.
3. **Expected `configuration_hash`** for the Phase 17 settings on the Phase 19 code:
   `0a33aa51…`.
4. **After the run:** `scripts/experiments/check_clock_drift.py --worlds --since <start
   date>` must exit 0. Treat any drift or masked fault as a lab defect and report it.
5. **Also keep** the ingestion health check (`check_ingestion_health.py`), as before.

## The program: Phases 20–27 (adopted 2026-09-23)

The user wants to keep experimenting while time (~19 days) and budget remain. The
write-up is **Phase 27, the last phase, not the next**. The full program, its reviews and
its numbers are in `docs/part2/EXPERIMENT_PROGRAM_PHASES_20-27.md` (evidence in
`artifacts/program-2026-09-23/`).

| phase | what | cap |
|---|---|---|
| 20 | Development probe of `dd62c857…` on upgrade-side faults, plus a source-existence check (is ACCEPTED reachable at all?) | $28 |
| 21 | Actor replay probe: does telling the Actor "no confirmation requested yet" fix the lapse behind every untriggered fault? Also temperature-0 determinism | $25 |
| 22 | Build, two review rounds, one freeze: heldout-2 partition (declared generator and seed), predicate v2 (15 trials per case with Fisher), fixed-N loop runner. $0 validity soak | $0 |
| 23 | Fixed-N full loop: 30 attempts, no stop at success, so the certification rate gets an interval | $150 |
| 24 | One held-out check of the first new certified repair on heldout-2 | $87 |
| 25 | `dd62c857…` replays on the fixed lab, with a v4-vs-v5 lapse A/B if Phase 21 passed | $110 |
| 26 | Small probes: Explorer challenge, a second completion gap, Mechanic slot 2 | $23 |
| 27 | Event write-up and demo | $0 |

Caps total $423, leaving a reserve of $111.76. Every phase is declared, reviewed and
reported on its own.

**Done so far:**
- **Phase 20 ($18.77):** no source for ACCEPTED (`none_found`); 0 safety failures; P-1
  floor-limited.
- **Phase 21 ($22.22):** V5_NOT_ADOPTED. The lapse is a turn-3 chance draw that is absorbing
  at turn 4.
- **Consequences:**
  - Phase 22 proceeds **without** v5.
  - Phase 25 falls back to 12 v4 replays ($60), only after Phase 24.
  - Heldout-2's transient-upgrade case is low-rate: B0 completed 2 of 27 in Phase 20, and
    its verdict must say so.
- **Budget:** $506.23 charged, $493.77 remaining.

**Key facts the program established ($0):**
- Runtime 2's strict report schema removed the only failure a baseline ever repeated 3 of
  3, so ACCEPTED is very likely unreachable in the trusted configuration. Phase 20's
  source check tests that directly.
- Phase 18's HARM does not hinge on the defect (see the corrections).

## Budget

**$506.23 conservatively charged, $493.77 remaining** of the shared $1,000.
