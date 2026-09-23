# Next phase: after Phase 18 (2026-09-23)

Read `docs/part2/PHASE18_RESULTS.md` first, then `PHASE17_RESULTS.md`.

## Where things are

**Phase 17** certified a completion repair on development cases:
- policy `dd62c857…`, attempt 9 of 9;
- it is **not ACCEPTED**.

**Phase 18** ran that policy once on the private promotion partition (6 unseen cases × 3
trials × 2 arms):
- **Verdict: HARM** (rule `check_failure`). It is **final**, and this policy cannot be
  re-checked here.
- **The batch:** 18 of 18 pairs valid; 0 untriggered faults; 0 baseline check failures.
- **The one failure:** a candidate episode on the delayed-confirmation case failed C5, C6
  and C8. Its report was true about the world.
- **Cost:** $4.22 bound.

**The post-verdict investigation** ($0, read-only, not declared in advance; see
`PHASE18_RESULTS.md`):
- **The mechanism:** the failure matches a **lab clock-accounting defect**.
  - `send_confirmation` times out, and the lab automatically re-sends the same `call_id`.
  - The simulator never records that re-send, but the lab still advances its tick.
  - Every later observation is therefore stamped one tick past the world's decision tick,
    so any citation of it fails C6.
- **Store-wide:** 4 of 4,791 scored episodes show this drift, and all 4 are C6 violations.
  **Two of the four are baseline episodes with no policy at all.**
- **The timing:** it first appeared on September 22; 0 drifts in the 1,655 earlier
  episodes that had a re-send.
- Phase 17's nine attempts contain none of the four.

## Recommended Phase 19: find and fix the clock drift ($0 to diagnose)

**Why first:** this is a flaw in the measurement itself. In rare cases it turns a truthful
report into a violation in **either** arm. Any future gate run, and any demo, inherits it.
It is also the honest last word on Phase 18's failure.

1. **Reproduce without models.**
   - Drive episodes with the handwritten reference actor on a development case with an F1
     delay on `send_confirmation` longer than the client's tool timeout.
   - Compare the lab's dispatch log with the world's `http_attempt` log.
   - No provider calls, so $0.
2. **Find why the world misses the re-send.**
   - Candidates include: the re-send queued behind the delayed first request, the client
     timing out and disconnecting before the handler records anything, or an idempotency
     path that answers without logging.
   - Establish which one; do not guess.
3. **Find what changed on September 22** (0 of 1,655 before, 4 of 1,002 after).
   - Candidates: the delay-fault cases in use, settings, or connection lifetime.
4. **Fix at the source, so that one clock numbers every tick** (world and lab never
   disagree). Do not loosen C6 or touch `checks.py`.
   - `scorer_hash` must stay unchanged.
   - Add a regression test that fails on the old code.
5. **Verify only on development cases.** The promotion partition is spent for this. Never
   re-run Phase 18 on it.

## Then Phase 20: the event write-up and demo (free)

The honest story, in order:
1. The loop generated a repair, and the unchanged gate certified it.
2. The gate also rejected a harmful repair in the same run.
3. The held-out check flagged a failure.
4. The investigation traced that failure to a measurement defect that also hits the
   baseline, and the defect was fixed.

The last step can only be told once Phase 19 has actually fixed and verified it. Never
claim held-out safety for `dd62c857…`: it is **unshown**.

## Later candidates

- **Fix the Actor lapse** (it polls an unsent confirmation, then quits). It causes every
  untriggered fault.
- **Mechanic brief quality:** retries gated on PENDING that can never fire, and duplicate
  slot-2 proposals at temperature 0.
- **A new held-out check** needs a **new policy** and a **fresh partition or a declared
  re-use rule**. This partition is spent for anything Phase 18 could inform.

**Pooling rule:** any further certified-repair run quotes its attempts pooled with Phase
17's 9.

## Budget

**$465.24 conservatively charged, $534.76 remaining** of the shared $1,000.
