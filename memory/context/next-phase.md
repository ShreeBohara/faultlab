# Next phase — after Phase 17 (2026-09-23)

Read `docs/part2/PHASE17_RESULTS.md` first, then `PHASE17_EXPERIMENT.md` and
`PHASE16_RESULTS.md`.

## Where things are

**Phase 17 produced the project's first certified completion repair.**
- The loop ran fresh, with no human selection.
- **Attempt 9:** a new policy (`dd62c857…`, not T15's) passed the unchanged `assess_pairs`
  on a validation batch with no violation and no untriggered fault. It repaired the source
  case (0 → 3) and the sibling case `notification-3` (0 → 3).
- **Attempt 4:** a different generated repair fixed the target but broke correct refusal
  handling; the gate rightly rejected it.
- **Cost:** $24.29 at the conservative bound (≈ $2.28 token-priced, unverified).
- **Phase 17 is closed.** A certified stop is final.

It is **not ACCEPTED**, not SC-003, and not a rate. The policy has never seen the promotion
partition or an active challenge.

## Candidates for Phase 18 (the user decides)

1. **Stress-test the certified policy on held-out cases** (small, paid, declared first).
   - Run it once against the promotion partition, single-shot, never seen during
     development, judged by a no-harm rule declared in advance.
   - This is what would turn "certified on development cases" into "safe on unseen cases".
   - It needs a small new code path, because `queue_evaluation` accepts only ACCEPTED or
     BASELINE policies. It must never touch the sealed final-audit partition.
2. **Write up and demo the result for the event** (free).
   - The dashboard or README story: the loop found a repair; the gate certified it; the gate
     rejected a harmful one in the same run.
3. **Fix the Actor lapse.** It causes every untriggered fault and controls stop (poll an
   unsent confirmation, then quit). This is product quality.
4. **Mechanic brief quality.** Two of four step policies gated the retry on PENDING and could
   never fire, and slot 2 duplicates at temperature 0. Any change here is a declared change
   to the Mechanic's input.

**Pooling rule:** any further run whose success is a certified completion repair quotes its
attempts pooled with Phase 17's 9.

## Budget

**$461.02 conservatively charged, $538.98 remaining** of the shared $1,000.
