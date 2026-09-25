# Phase 26 results: second completion gap probe. September 25, 2026

- **Protocol:** `PHASE26_EXPERIMENT.md`. Reviewed in rounds 1–3; the round-3 fix aligned the
  paid-run guard. Approved by Claude as PM, delegated by the project owner
  (`artifacts/phase26-2026-09-24/review.json`).
- **Runner:** `run_gap_probe.py`, sha `5d8e1690…`.
- **Evidence:** `artifacts/phase26-2026-09-24/`.
- **Run:**
  - **21 of 21 cases, 63 of 63 pairs, 126 development episodes, complete**;
  - **$17.05 conservatively charged** against the $25 cap.
- **Lab integrity:**
  - 0 tick drift, 0 count drift, 0 masked F1, 0 missing worlds, 0 untriggered faults; the
    runner's check and the manual re-run agree;
  - the read-out reproduces (only the worlds path differs, relative against absolute);
  - store backed up (`quick_check` ok);
  - backend stopped during the run and restored after; dashboard closed; loop latency p99
    5.6 ms.

## Declared read-outs: **both families `mr_completes_more`** (Holm, family-wise α 0.05)

| family | MR (manual-reference policy) | B0 (baseline) | exact one-sided p | reading |
|---|---|---|---|---|
| **F4: transient upgrade failures** (counts 2, 3, 4) | **18 of 18** [82%, 100%] | 1 of 18 [1%, 26%] | 8.9 × 10⁻⁹ | **MR completes more** |
| **F2: long upgrade delays** (d8, d12, d17) | **18 of 18** [82%, 100%] | 0 of 18 [0%, 18%] | 1.3 × 10⁻⁹ | **MR completes more** |

- Both replicas agree in both families.
- MR also completed the d5 boundary delay 6 of 6 (B0 0 of 6) and the healthy case 3 of 3 (B0
  2 of 3).
- **Safety: 0 C1–C8 failures in any arm** (B0, MR and L).

**How MR completes (from the event log):**
- **On transient upgrade failures,** its `after_upgrade_response` rule waits one tick, then
  **re-sends the original upgrade request** (`retry_original_request`). The receipt arrives at
  tick 5 in every trial, and the Actor then sends the confirmation.
- **The baseline Actor almost never re-sends** the upgrade itself.
- **On long delays,** MR waits and re-reads until the operation settles, within the tick and
  wait budgets.

**MR is a manual-reference policy.** It is labelled as such. It is never entered as a
candidate, never shown to a Mechanic, never certified and never promoted. It shows what a
**legal** policy can achieve; it is not a repair the loop produced.

## The certified repair on the same faults (descriptive; label `pattern_replicated`)

- **The result:** `711bddb6…` (Phase 23's routed repair, run on development cases now that its
  held-out verdict exists) completed **0 of 18** F4 trials. The baseline trials paired with it
  completed **4 of 18** (p = 0.03, descriptive).
- **This is the fourth data set with the same pattern.**

  | phase | policy | repair | baseline |
  |---|---|---|---|
  | Phase 18 | `dd62c857…` | 0 of 3 | 1 of 3 |
  | Phase 20 | `dd62c857…` | 0 of 27 | 2 of 27 |
  | Phase 24 | `711bddb6…` | 0 of 15 | 2 of 15 |
  | Phase 26 | `711bddb6…` | 0 of 18 | 4 of 18 |

  - **Pooled:** 0 of 63 against 9 of 63 (the pooling is post hoc).
  - **Why the repairs fail here:** their upgrade-side rule reads and waits, **but never re-sends
    the upgrade**. Where the baseline Actor sometimes re-sends it, the repairs' reads seem to
    stop it.
- **Unpaired descriptive comparison, MR against L on F4:** 18 of 18 against 0 of 18.

## What this establishes, and what it does not

**Establishes:**
- **A second completion gap exists, and it is closable by a legal policy.** On transient
  upgrade failures and long upgrade delays, the baseline completes 1 of 36. A manual-reference
  policy that waits and re-sends or re-reads the upgrade completes **36 of 36**, with 0 safety
  failures.
- **The loop's certified repairs do not close this gap, and may make it slightly worse.**
  They never re-send the upgrade. This is now seen in four data sets and two policies,
  descriptive in each.

**Does not establish:**
- **That the loop can learn this repair.** The Mechanic would need an upgrade-side source case
  and would have to write `retry_original_request` for orders. It did so once in Phase 25's T
  arm (`orders_retry: 1`).
- **Anything held-out:** these are development schedules only.
- **That MR is safe beyond these 21 cases.**

**Next, if pursued:** a declared loop run whose source case is an upgrade-side gap (F4 on
`update_order`, or a long F2 delay), to see whether the Mechanic writes the upgrade retry. It
would need its own declaration and review.

## Budget

$613.61 + $17.05 = **$630.66 conservatively charged, $369.34 remaining** of the shared $1,000.
