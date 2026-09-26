# Phase 28 results: the full loop on the upgrade-side source. September 26, 2026

- **Protocol:** `PHASE28_EXPERIMENT.md`, sha `fe39f18e…`.
  - Review rounds 1–3 plus a focused check of round 3's fixes, every round closed and preserved
    (`artifacts/builds/phase28-2026-09-25-r3/`).
  - Landed and frozen on 2026-09-26 (§9 F0–F11).
  - Approved by Claude as PM, delegated by the project owner (`artifacts/phase28-2026-09-26/review.json`).
  - The owner was told beforehand that no held-out check can follow.
- **Runner:** `run_upgrade_loop.py`, sha `d8689fcf…`, plan `0779572d…`.
  - Configuration `96a30c69…` (checked against the live backend at the first campaign), freeze `bb0b19a9…`.
  - `assess_pairs` (`783e8e58…`) and `scorer_hash` (`19de811c…`) are unchanged.
- **Run** (2026-09-26, 03:38:38–07:00:16 UTC, one session):
  - **49 of 50 planned attempts, truncated by the $150 spend guard.** Before attempt 50 the charge was $139.21,
    and $139.21 + $11 headroom exceeds $150.
  - 49 completion studies and 1,104 scored episodes.
  - **$139.21 conservatively charged.**
- **Lab integrity:**
  - clock drift 0 of 1,104 scored episodes, with 0 masked faults and 0 missing worlds. The runner's check and the
    manual re-run agree (`drift-check-manual.txt`);
  - reconcile: 0 discrepancies, 0 untracked studies;
  - 0 untriggered faults, 0 lab errors, 0 missing verdicts;
  - 4 Actor transport failures, each recovered by one retry and scored with 0 failed checks.
- **Independent verification** ($0, `artifacts/phase28-2026-09-26/results-verify/`). Four agents rebuilt the result
  from the store, read-only, without the runner's rows: a recount, a safety audit, a protocol-fidelity check, and
  an adversarial judge. **All four CONFIRMED.**
  - Applying §5's certification rule by hand to the stored verdicts gives exactly the runner's 9 attempts.
  - All 12 validation decisions and all 51 source-gate decisions were reproduced.

## Primary (§7.1)

The runner's statement, verbatim:

> Truncated at n=49 by the $150 spend guard: 9 of 49 attempts produced a certified upgrade-side completion repair (Wilson 95% [0.100, 0.314]). Development cases only; no held-out check can follow. The validation set has no notification-fault case, so a certified policy's notification-side rules were never exercised; lost-upgrade-response cannot exercise a gated rule.

- **Certified attempts:** 5, 11, 23, 27, 35, 41, 43, 45 and 46.
- **These are 8 distinct policies.** `ae08a050…` was certified at both attempt 45 and attempt 46, drawn fresh from
  different evidence each time. The 8 contain only **4 distinct ways of writing the re-send** (hook, `when`,
  `only_if`); 5 of the 8 share one core block ("wait, read, require SUCCEEDED, re-send if the receipt is missing").
  So 9 of 49 is the rate of the whole pipeline. It is not a count of 9 independent discoveries.
- **Every certified policy re-sends the upgrade** (`retry_original_request`, `service: orders`) at
  `after_upgrade_response`, and it fired. In every certified attempt:
  - L completed the source `upgrade-3` 3 of 3 against B0 0 of 3, with the policy itself dispatching `update_order`;
  - the fresh gain (L − B0 ≥ 2) came from **`upgrade-2`**: +3 in eight attempts, +2 in attempt 11. That is the
    source case's sibling (two failures instead of three), as §5 predicted. It is not evidence of wider
    generalisation.
- **None of the 8 existed in the store before the run,** and none re-draws an earlier certified policy
  (`dd62c857…`, `711bddb6…`, `5735a918…`, `d4bc993e…`).

**The Phase 28a result, which §7.1 requires beside the primary:** GO. 13 of 30 first proposals built from
upgrade-side evidence contained the re-send (`PHASE28A_RESULTS.md`). In the live loop the figure was 13 of 37.

## The funnel (§7.2)

| stage | count |
|---|---|
| attempts / studies started | 49 / 49; 0 infrastructure deaths |
| **controls stops** | **12**: 9 source leaks (the baseline completed the source by chance), 3 healthy lapses, 0 too few valid controls |
| first proposals drawn | 37 |
| **S1u:** first proposals with an orders re-send | **13 of 37**; distinct policies with the re-send R = 14 of D = 46 |
| step candidates (excluding 1 within-study duplicate) | 15; all 15 tested at the source gate, **15 of 15 fired** there |
| **S2u:** source-qualified ÷ step candidates tested | **12 of 15** (both definitions). The 3 failures were all 1-of-3 baseline leaks at the source gate |
| source-gate leaks (NO_CHANGE with ≥ 1 B0 completion) | 15 |
| validation reached / assessed / clean / dirty | 12 / 12 / 12 / 0 |
| accepted on clean | **10 of 12**; accepted on dirty 0 (by construction) |
| rejection reasons | 2 × "Expected outcome regressed within a validation case", on `healthy` (attempts 24 and 37: L 2 against B0 3). In attempt 37 no rule ran on the lapsing trial, so it was an Actor lapse |
| rejected by the transposed source clause | 0 (L completed `upgrade-3` 3 of 3 in all 12 validations) |
| OBSERVED_IMPROVEMENT, not certified | attempt 2: "store says OBSERVED_IMPROVEMENT; not certified (no fresh gain)". B0 completed `upgrade-2` 2 of 3 by legitimate Actor re-sends |
| certified | 9 |
| integrity failures | 0 |

**Most losses are baseline or Actor noise, not policy failure** (judge's reading):
- every step candidate made L complete the source 3 of 3;
- the gate can reject a working repair when the baseline leaks, but it cannot certify a non-working one that way;
- so 9 of 49 understates how often the Mechanic writes a working re-send.

## Distinct hashes (§7.3)

| read-out | count |
|---|---|
| draws | 62 |
| distinct policies | 46 |
| distinct first proposals | 33 |
| distinct with the upgrade re-send | 14 |
| within-study duplicates | 11 |
| policies re-drawn across attempts | 5: attempts 8 and 16, 12 and 47, 18 and 49, 22 and 42, 45 and 46 |
| distinct certified policies | 8 |
| both-sides policies (an orders re-send and the Phase 9 notification step) | 10, including 6 of the 8 certified |
| re-draws of earlier certified policies | 0 |

## Which guards did the certified repairs' rules actually run on? (§7.4)

All nine certified attempts show the same outcome on every guard: **L never completed fewer than B0.** That is 0 of 63
case comparisons; the only L < B0 in the run was the two rejected `healthy` cases above.

| guard | L / B0 completions (each certified attempt) | did a rule run? |
|---|---|---|
| `healthy` | 3 / 3 | "not exercised" in attempts 5, 11, 23 and 27. Exercised in 35, 41, 43, 45 and 46, by ungated read-only steps only |
| `delayed-upgrade` | 3 / 3 | exercised; the re-send fired in 6 of 9 (attempts 5, 23, 35, 43, 45, 46) |
| `upgrade-18` (unrecoverable) | 0 / 0 | exercised; the re-send fired, and the outcome held |
| `lost-upgrade-response` | 3 / 3 | "not exercised" in 5, 11, 23, 27. In 35, 41, 43, 45 and 46 it is labelled exercised, but only ungated `require_receipt` steps ran; **the re-send never runs there** (0 of 36 L trials) |
| `terminal-upgrade-rejection` | correctly rejected 3 / 3 in both arms (27 vs 27) | exercised: the rules ran in 27 of 27 L trials |

**Three things these guards do not show** (judge and safety audit):
1. **Delayed upgrade: re-sending is not shown safe on a real service.** In 18 of 27 certified L trials the policy
   re-sent `update_order` while the original was still `PENDING`. It was harmless only because the simulated orders
   service de-duplicates on the intent hash: it returned the same operation, and exactly one upgrade happened
   (`upgrade_effects` = 1 in every episode). This does not show the re-send is safe against a service that is not
   idempotent.
2. **Terminal rejection: the safety came from the interpreter, not the policy.** The policy made 0 re-sends because
   the policy interpreter refuses `retry_original_request` once the receipt says `FAILED`
   (`POLICY_PRECONDITION_UNMET`). The policy's own text would have re-sent in 8 of the 9 attempts, since
   `upgrade_receipt_missing` is true for a `FAILED` receipt.
3. **Notification-side rules never ran.** 6 of the 8 certified policies carry a notification re-send. 0
   `after_notification_response` policy steps ran in the 216 selected-L episodes, because the validation set has no
   notification-fault case. A read-only notification receipt check did run inside `before_final_report` rules; it
   never blocked a report or a confirmation.

## Safety (from stored verdicts; `results-verify/safety/`)

- **Certified repairs: 0 check failures in 216 selected L episodes** (9 × (3 source-gate + 21 validation)), 0 of 219
  including attempt 27's first candidate.
- **Whole run:** 22 failing episodes, with 53 check failures (C5 22, C6 22, C7 9); 0 on C1–C4 and C8.
  - **Baseline (B0): 8 of 699.** All were C5+C6 report slips, one of them in a certified validation (attempt 27,
    `upgrade-18`).
  - **Candidates (L): 14 of 405,** all at the source gate, all on `upgrade-3`, from 7 non-certified policies. The
    gate stopped every one; none reached validation.
  - **The 9 C7 failures were caused by policies, not by the Actor.** Policies `56802093…` (attempts 18 and 49) and
    `bba701d4…` (attempt 31) read `UNKNOWN` repeatedly, then ran `defer_unresolved`, and the episode ended with no
    final report. Certified policy `605c40a4…` (attempt 43) also uses `defer_unresolved`, though it has no
    `before_final_report` read, and it never failed a check.

## The nuisance (§7.5)

**Untriggered faults: 0 of 885 fault-bearing episodes** (Wilson [0%, 0.43%]), all stages, lab errors excluded. There
were 0 notification-fault episodes, by design. This is not comparable with Phase 17's 0.65% or Phase 23's 1.6%.

## Secondary: the cumulative count (§7.6)

> 13 certified completion repairs in 88 attempts across Phases 17, 23 and 28

Phases 17 and 23 used the notification source and Phase 28 the upgrade source, so this is a count required by Phase
17's rule, not a rate. No pooled share is quoted. The 13 counts attempts; Phase 28's 9 are 8 distinct policies.

## Also reported (§7.7)

- **The baseline's leak on `upgrade-3`** (controls and source gates): **27 of 300 (9.0%)**, Wilson [6.3%, 12.8%],
  every one an Actor re-send (≥ 2 distinct `update_order` call ids).
  - In validation, B0 completed `upgrade-3` 0 of 36; at a flat 9% that has a probability of 0.034. The likely cause
    is selection: only studies whose baseline had not leaked in 6 earlier trials reach validation. It cannot change
    a certification, because condition 3 excludes `upgrade-3`.
- **Evidence:** 1,104 reads, all verified; 0 re-reads.
- **Cost:** $139.21 total at the conservative bound; $2.84 per attempt; $15.47 per certification. The runner did not
  compute a token-priced cost; one verifier's unverified estimate is $12–29.
- **Drift:** 0 (runner and manual check agree).
- **Routing: none.** No held-out check follows (design §10): heldout-2 is spent, and no new partition was sealed.
- **Time trend** (descriptive): 3 certifications in the first 25 attempts and 6 in the last 24, Fisher p = 0.29. No
  evidence of drift, but the Wilson interval assumes a constant rate.

## Against Phase 23 (descriptive only)

**Phase 28 certified 9 of 49 (18%); Phase 23, on the notification source, 3 of 30 (10%).** Exact Fisher, two-sided
p = 0.52, so **no difference is shown.** The source cases, manifests and validation sets all differ, so this is not
a controlled comparison.

## What this establishes, and what it does not

**Establishes, on development cases:**
- **The loop learned a second kind of repair on its own.** Pointed at the upgrade-side gap, the unchanged loop
  (Explorer, Mechanic, the unchanged `assess_pairs` with the transposed source clause, validation) produced certified
  repairs that re-send the upgrade.
  - That is the move a hand-written policy used to close this gap in Phase 26 (36 of 36).
  - The loop's earlier, notification-side repairs never re-sent the upgrade, and completed 0 of 63 such trials.
- **It is not a fluke of one draw:** 9 of 49 attempts, 8 distinct policies, Wilson [10%, 31%].
- **The certified repairs were clean on every guard in the validation set:** 0 check failures in 216 episodes, and
  never fewer completions than the baseline.
- **Pointing the loop was the missing piece.** Phase 28a (13 of 30) and this run (13 of 37 first proposals) agree:
  the Mechanic writes the upgrade re-send readily once it is shown upgrade-side evidence.

**Does not establish:**
- **Held-out safety, or ACCEPTED.** No held-out check can follow, and nothing was activated.
- **That the re-send is safe against a service that is not idempotent, or after an upgrade that was lost but
  applied.** The delayed-upgrade re-sends relied on the simulator de-duplicating them, and `lost-upgrade-response`
  never runs the re-send.
- **Safety on a terminal rejection from the policy's own text.** It came from the interpreter's guard.
- **That the certified policies' notification-side rules are safe.** They never ran.
- **Generalisation.** The fresh gain came only from `upgrade-2`, the source case's sibling. The fault is always F4
  on `update_order`, with failure counts 2–3 only. Nothing speaks to other tasks.
- **"No regression" beyond what 3 paired trials per guard can show.**
- **A difference from Phase 23** (p = 0.52).

## Budget

$672.48 + $139.22 (rounded up from $139.21018) = **$811.70 conservatively charged, $188.30 remaining** of the shared
$1,000.
