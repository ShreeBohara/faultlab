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

## Recommended Phase 20: the event write-up and demo (free)

The event is roughly 20 days from 2026-09-22. The honest story, in order:

1. **The lab** injects faults into a tool-using agent's task. A fixed referee scores eight
   checks.
2. **The loop** generated a repair, and the unchanged gate certified it on development
   cases (Phase 17).
3. **In the same run,** the gate rejected a harmful repair (attempt 4 broke refusal
   handling).
4. **A held-out check** on unseen cases flagged one failure (Phase 18, HARM).
5. **The investigation** traced that failure to the lab's own measurement:
   - a request lost unsent during a loop freeze caused by the dashboard;
   - the same defect had failed baseline runs too.

   It was reproduced, fixed, and swept across 4,791 stored episodes (Phase 19).
6. **What is still not shown:** that the repair is safe on unseen cases. A new held-out
   check needs a new partition or a declared re-use rule.

Deliverables to decide in Phase 20: a short write-up page, a 3-minute demo script, and
dashboard screenshots with the fixed backend. **Never claim held-out safety.**

## Later candidates

- **A fresh held-out check** on a **new** partition, with a declared construction rule.
  Paid, small.
- **Structural hardening:** stop counting an attempt the lab knows was never sent
  (`ConnectError` / `ConnectTimeout`), or cross-check the lab's and the world's ticks at
  the end of every episode.
- **The remaining ~0.13 s stalls** every ~7 s on the fixed backend. They are harmless at
  today's budgets, but unexplained.
- **The Actor lapse,** the cause of every untriggered fault.
- **Mechanic brief quality:** retries gated on PENDING, and duplicate slot-2 proposals.

**Pooling rule:** any further certified-repair run quotes its attempts pooled with Phase
17's 9.

## Budget

**$465.24 conservatively charged, $534.76 remaining** of the shared $1,000.
