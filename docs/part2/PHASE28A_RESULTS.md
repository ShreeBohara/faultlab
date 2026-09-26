# Phase 28a results: upgrade-side Mechanic probe (non-scoring go/no-go). September 26, 2026

- **Protocol:** `PHASE28A_EXPERIMENT.md`, sha `f07e393a…`.
  - Reviewed in rounds 1–4 (every harness change was followed by a focused check).
  - Closed on 2026-09-26.
  - Approved by Claude as PM, delegated by the project owner (`artifacts/phase28a-2026-09-25/review.json`).
  - Committed to the local backup branch before launch.
- **Harness:** `upgrade_mechanic_probe.py`, sha `3dacdbed…`, plan `a04d9319…`, configuration `2cf63e93…`.
- **Run** (2026-09-26, 00:30:28–00:32:09 UTC):
  - **30 of 30 first-proposal requests delivered.** There were 32 attempts: one needed a format repair, which
    succeeded.
  - All served by `DeepSeek-V4-Pro-0813`, the loop's Mechanic.
  - **$1.59 conservatively charged** against the $5 cap.
- **Read-outs:**
  - recomputed by the pinned harness and equal (`readouts-recheck.json`);
  - **recounted by separate code** that imports nothing from any harness
    (`results-verify/independent_count.out.json`): the same 13 request ids, all at the same hook, 12 distinct policies.
- **Launch-day checks:** `launch-day/checks-launchday.txt` (power, schedule, updates, backend, processes, ledger,
  dry run, 77 of 77 tests, pins).
- **Scope:** non-scoring. These are Mechanic requests built exactly like the loop's first proposal, from locally
  rebuilt development evidence. Nothing entered a study, and no campaign, policy or store row was created.

## Decision: **GO**

The runner's statement:

> GO: 13 of 30 first proposals (Wilson 95% [0.274, 0.608]) contain an orders re-send (retry_original_request, service orders) at some hook under some gate. Descriptive, from the static check of the declared transient-failure path: 13 can fire (13 at after_upgrade_response, where a re-send can complete the task, and 0 only at before_final_report, after the Actor has proposed its report), 0 cannot fire and 0 are unclear. 0 of the 30 draws were empty or unreadable outputs, which the loop would have recorded as an infrastructure death, not a proposal. This decides only that the Phase 28 build may start; it does not mean that a re-send works or that the loop will certify a repair. Development evidence only, rebuilt locally (every evidence row reads local_only), from episodes of several campaigns and stores; one draw per context at temperature 0; contexts share episodes, so the intervals understate the uncertainty.

| read-out | count |
|---|---|
| **draws containing an orders `retry_original_request`** (the decision) | **13 of 30** [27%, 61%] |
| of those, placed where they can fire after a transient upgrade failure (static, descriptive) | 13 of 13, all at `after_upgrade_response` |
| distinct policies among the 13 | 12 |
| valid policies (`CANDIDATE`) | 30 of 30; 0 invalid, 0 refusals |
| policies that also contain the notification-side repair step | 10 of 30 (all 10 fire; 0 flagged harmful or premature-defer) |
| distinct policies overall | 28 of 30 |

**How the re-sends are gated** (descriptive): each fires at `after_upgrade_response`.
- Most sit after a wait-and-read under `when: upgrade_outcome_uncertain`, `only_if: upgrade_receipt_missing`.
- The others are a rule with `when: upgrade_receipt_missing`, `only_if: always`.
- 12 have one re-send step and 1 has two.
- None is gated on `PENDING`, the pattern pitfall 77 records as unable to fire.

## What this establishes, and what it does not

**Establishes:**
- **Pointed at an upgrade-side gap, the Mechanic writes the upgrade re-send often.**
  - 13 of 30 first proposals contain it, all placed where the static check says it can fire.
  - Phase 26 showed this is the move a legal policy uses to complete 36 of 36 upgrade-gap cases.
  - The loop's certified repairs, all built from a notification-side source, never contained it (0 of 63 trials
    completed).
  - **So the missing re-send was plausibly about where the loop was pointed, not about what the Mechanic can
    write.** This is descriptive, not a controlled comparison.
- **For comparison only** (a different source and brief context; not a test): on the notification side, 7 of 26
  first proposals contained the working step in Phase 23, and 5 of 31 in Phase 16.
- **The design's gate is passed:** Phase 28's build and integration may proceed (design §9, §19 decision 4).

**Does not establish** (§14):
- **That a re-send works in a live episode, or completes the task.** The "can fire" label is a static check, and it
  has been validated against stored behaviour on one policy only (§8).
- **That the loop will certify an upgrade-side repair.** The source gate, validation and the certification rule
  (Phase 28) are the test.
- **That these policies are safe.** No episode was run.
- **Anything held-out.** No held-out check follows for Phase 28 (design §19 decision 7).

**Limits** (§15):
- **The draws are correlated.** 19 source episodes fill 90 evidence slots across the 30 contexts, so the interval
  understates the uncertainty. For example, one episode appears in 5 contexts, and 3 of those drew a re-send.
- **One draw per context, at temperature 0,** which is not deterministic.
- **Slot 1 only.** Slot 2, the source gate and validation are not modelled.
- **Five declared input differences from a live loop** (§6), with unmeasured effect. The two with a plausible
  direction (the `local_only` evidence labels and the split scenario hashes) lean toward NO_GO, and the result was
  GO anyway.

## Budget

$670.88 + $1.60 (rounded up from $1.59488) = **$672.48 conservatively charged, $327.52 remaining** of the shared
$1,000.

## Next

**Phase 28, the main run: a fixed-N loop of 50 attempts with an upgrade-side source, capped at $150.** Its backend
change was built and reviewed in a detached worktree. It must now be:
1. integrated into the main checkout;
2. frozen, with a new configuration pin;
3. reviewed on the integrated code, and closed;
4. launched with the Phase 19 lab checks (`start-simulator.sh`, dashboard closed, loop latency, clock drift
   afterwards).
