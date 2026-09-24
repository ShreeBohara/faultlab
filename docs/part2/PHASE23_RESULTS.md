# Phase 23 results: fixed-N full loop, 30 attempts. September 24, 2026

- **Protocol:** `PHASE23_EXPERIMENT.md`, frozen in Phase 22, sha `b5bd3726…`. Approved by
  Claude as PM, delegated by the project owner (`artifacts/phase23-2026-09-24/review.json`).
- **Runner:** `run_full_loop_fixed_n.py`, sha `95ef698d…`.
- **Configuration:** `2cf63e93…`; code freeze `8994e962…`.
- **Evidence:** `artifacts/phase23-2026-09-24/`: manifest, runner log, reconcile, drift checks
  and every runbook record.
- **Run:** 2026-09-24 04:03–05:49 UTC. **Stop: `fixed_n`**: all 30 attempts, as declared.
  **$77.30 conservatively charged** against the $150 guard; the expected range was $78–95.
- **Lab integrity:**
  - **0 clock drift, 0 masked faults, 0 missing world files** in 613 scored episodes; the
    runner's check and the manual re-run agree;
  - **reconcile: 0 discrepancies, 0 untracked full studies**;
  - backend restarted on the frozen code; dashboard closed; loop latency p99 6.2 ms.

## Primary (declared wording)

> **3 of 30 attempts produced a certified completion repair (Wilson 95% [0.035, 0.256]).**

Beside it, as the protocol requires:

- **Cumulative (Phase 17's pooling rule):** 4 certifications in 39 attempts across Phases 17
  and 23. Pooled share 10.3% [4.1%, 23.6%]. *Phase 17 stopped at its first success (attempt 9
  of 9), so its share is biased upward.*
- **Distinct certified policies: 3**, one per certified attempt:

  | attempt | certified policy |
  |---|---|
  | 2 | `711bddb6…` |
  | 21 | `5735a918…` |
  | 24 | `d4bc993e…` |

  None is `dd62c857…`.
- **Untriggered-fault rate (the nuisance):** 8 of 489 fault-bearing episodes = **1.6%** [0.8%,
  3.2%]. References: Phase 17 0.65%; Phase 15 2.64%.

## The funnel (declared)

| stage | count |
|---|---|
| attempts / studies started | 30 / 30 |
| infrastructure deaths | 1 (attempt 25: `EvidenceDenied` at controls) |
| controls stops (the source gap did not reproduce) | 3 |
| first proposals drawn | 26 |
| **S1: first proposals containing the step** | **7 of 26 (27%)**; Phase 17 reference 3 of 7 |
| candidates with a policy / with the step | 47 / 9 |
| step tested at the source / **step fired** (the policy itself dispatched `send_confirmation`) | 8 / **8** (0 never fired) |
| **S2: source gate given the step** | **6 of 6** complete step candidates qualified; 0 qualified without the step |
| validation reached / assessed | 6 / 6 |
| clean batches / dirty batches | 4 / 2 |
| **accepted on clean** | **3 of 4**; accepted on dirty 0, by construction |
| `OBSERVED_IMPROVEMENT` without a fresh gain | 0 |
| **certified** | **3** |

## Distinct hashes (declared)

- **Totals:** 47 draws, 30 distinct policies, 25 distinct first proposals, 8 distinct step
  policies.
- **Within-study duplicates:** slot 2 repeated slot 1 in **16** studies. This is the known
  temperature-0 duplicate problem, still present.
- **Re-drawn across attempts:** one policy (`89027787…`, attempts 20 and 29).
- **The Phase 17 policy `dd62c857…`** was re-drawn once:
  - attempt 22, slot 1;
  - it qualified at the source, and its validation was INCOMPLETE;
  - it is never routed (its Phase 18 verdict is final).

## Routing (declared; the only link to Phase 24)

- **Routed:** the first certified attempt by order, excluding `dd62c857…`. That is **attempt
  2, policy `711bddb68697e52dcd9b0d5b428fa96d7ec1fe0e95559d9a892b4a7772ac738e`**.
- **Details:** study `completion-study-cbb2f82f…`; post-checks passed; `routable: true` (the
  run is final).
- **The other two** certified policies are reported and are **never** checked on heldout-2.

## Also reported

- **Evidence:**
  - 612 reads;
  - **1 in-study re-read, verified.** This is the first time the Phase 16 re-read was ever
    needed, and it worked;
  - 1 study still died on `EvidenceDenied` (attempt 25).
- **Cost:**
  - $77.30 total and $2.58 per attempt, at the conservative bound;
  - **$25.77 per certification**;
  - the token-priced cost (≈10× lower) is unverified.

## What this establishes, and what it does not

**Establishes:**
- **On the fixed lab, the full loop certifies a completion repair in about 1 attempt in 10.**
  The interval is 3.5% to 25.6%, and it did so three times with three different policies. It
  is not a one-off. At this n it separates "happens" from "rare below 11%"; it cannot pin the
  rate within a factor of two.
- **Once the Mechanic writes the step, the rest of the pipeline works:**
  - the step fired in 8 of 8 candidates tested;
  - 6 of 6 complete step candidates passed the source gate;
  - 3 of 4 clean validation batches were accepted.
- **The binding constraint is the Mechanic writing the step** (7 of 26 first proposals) and
  the slot-2 duplicates (16 studies).

**Does not establish:**
- **That any of these repairs is safe on unseen cases.** That is Phase 24's single check, on
  the routed policy only.
- **ACCEPTED.** It remains unreachable in this configuration (Phase 20).
- **A difference from Phase 17.** No test between the two phases was declared.

## Budget

$506.23 + $77.30 = **$583.53 conservatively charged, $416.47 remaining** of the shared
$1,000.
