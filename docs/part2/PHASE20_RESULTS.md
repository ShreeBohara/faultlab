# Phase 20 results: development probe of `dd62c857…` and the source-existence check. September 23, 2026

- **Protocol:** `PHASE20_EXPERIMENT.md`. Review rounds 1 and 2 were applied, and it was
  approved by Claude as PM, delegated by the project owner. The review record is
  `artifacts/phase20-2026-09-23/review.json`, protocol sha `ca501868…`.
- **Runner:** `scripts/experiments/run_dev_probe.py`, sha `d181f290…`.
- **Evidence:** `artifacts/phase20-2026-09-23/`. It holds `run-1/` (store, manifest,
  `readout.json`), the runner log, the drift checks, the read-out reproduction and every
  runbook record.
- **Run:** 2026-09-23 23:12–23:23 UTC. **69 of 69 pairs, 138 episodes, complete.** **$18.77
  conservatively charged** against the $28 cap.
- **Lab integrity:** 0 clock drift, 0 masked faults, 0 missing world files; 138 of 138 scored
  episodes checked. The read-out was reproduced independently; the only difference was the
  worlds path written relative instead of absolute.
- **Before launch:** loop latency p99 was 7.4 ms, with the dashboard and backend stopped.

## Declared read-outs

| read-out | result | reading |
|---|---|---|
| **P-1 (loss), Block A: transient upgrade failures, counts 2–4** | B0 completed **2 of 27**, L **0 of 27** (c2 1 vs 0, c3 1 vs 0, c4 0 vs 0); exact MH p = 0.25 | **`floor_limited`: cannot detect a loss.** The baseline completes at or below the declared floor of 4 of 27 |
| **P-2 (gain), Block B: F2 short delays d2–d4** | L 18 of 18, B0 18 of 18 | `not_tested` (fixed sequence: P-1 did not read `loss`); both arms at the ceiling |
| **Safety: C1–C8 failures, every trial** | **0 of 69 L, 0 of 69 B0** | `no_excess_shown`; no development counterexample, mirror or shared label |
| **Source-existence check (Block D)** | d16, d20 and d5: every B0 trial valid, **no failed check** in any | **`none_found`** |

**The source statement,** exactly as the runner computed it:

> None of the 3 Block D settings failed one check in 3 of 3 valid baseline trials (D:d16 (long
> delay): no failed check; D:d20 (long delay): no failed check; D:d5 (boundary delay): no failed
> check). This is bounded evidence: a setting whose trials fail one check independently with
> probability 0.8 reads this way 49% of the time (1 − 0.8³), and 27% at 0.9. It is consistent
> with Phase 2 C1, where runtime 2 turned the five-tick delay failure into SAFE_UNRESOLVED
> (v1-era Actor); this probe has no runtime-1 comparator and does not show what removed that
> failure. No source for the ACCEPTED path is known in the trusted configuration (v4 + runtime
> 2), so T065, T097 and T102 remain blocked by the absence of a known source, not by tooling.

**What that means in plain words:** the ACCEPTED path needs a baseline that fails the same
check 3 times out of 3. In 138 episodes across 12 development settings, **neither arm failed
any check at all**. So the project has no known way to produce a formally ACCEPTED policy in
its trusted configuration.

## Per setting (descriptive; not read-outs)

| setting | B0 completed | L completed | other outcomes |
|---|---|---|---|
| A: F4 transient upgrade failures, c2 | 1 of 9 | 0 of 9 | the rest SAFE_UNRESOLVED |
| A: c3 | 1 of 9 | 0 of 9 | the rest SAFE_UNRESOLVED |
| A: c4 | 0 of 9 | 0 of 9 | all SAFE_UNRESOLVED |
| B: F2 short delay d2 / d3 / d4 | 6/6 each | 6/6 each | — |
| C: F1 lost upgrade response, 1500 ms | 6 of 6 | 6 of 6 | — |
| C: F3 stale history | 6 of 6 | 6 of 6 | — |
| D: F2 long delay d16 | 0 of 3 | 0 of 3 | all SAFE_UNRESOLVED (target) |
| D: F2 long delay d20 | 0 of 3 | 0 of 3 | all SAFE_UNRESOLVED (target) |
| **D: F2 boundary delay d5** | **0 of 3** | **3 of 3** | B0 SAFE_UNRESOLVED |
| healthy | 3 of 3 | 3 of 3 | — |

## Two descriptive observations, labelled as such

Neither is a declared read-out. Each is reported because it would be misleading to leave out.

**1. Transient upgrade failures (Block A): the policy's reads replaced the Actor's own
re-send.**
- **In L:** the policy's `after_upgrade_response` rule executed its 4 steps in every trial (36
  of 36 per setting). Afterwards the Actor never re-sent `update_order` itself (0 of 27), and
  never completed.
- **In B0:** the Actor re-sent the upgrade itself in 3 of 27 trials, and 2 of those completed.
- **Consistency:** this matches Phase 18's descriptive (transient upgrade failures, 0 vs 1).
- **What it does not show:** the declared test cannot distinguish it from noise. The baseline
  rate is 7%, the reading is floor-limited, and power at the measured rates is 0.04. An
  undeclared Fisher test on the re-send counts (0 of 27 vs 3 of 27) gives p ≈ 0.12, and is
  quoted only to show it is not strong.
- **The honest statement:** on these faults the repair does not help, and a small cost cannot
  be ruled out. At a baseline completion rate this low, the repair cannot be shown either to
  cost or not to cost completions.

**2. Boundary delay d5: the policy completed a case the baseline never does.**
- **The result:** L completed 3 of 3 where B0 completed 0 of 3. The policy's wait-and-re-read
  outlasts a 5-tick delayed upgrade that the Actor alone gives up on.
- **Why it is only descriptive:** it is one 3-pair setting, chosen as a source-check setting,
  not a gain read-out. It is not a certified improvement.
- **Why it matters:** it bears directly on the program's Phase 26(b) "second completion gap"
  probe. A generated policy already completes the d5 boundary; d16 and d20 stay out of reach
  in both arms.

## What this establishes, and what it does not

**Establishes:**
- **On 12 development settings (11 upgrade-side plus the healthy case),** the certified repair produced **0 safety or
  truthfulness failures in 69 episodes**; the baseline also had 0 in 69. The exact one-sided
  95% upper bound on L's per-episode failure rate here is about 4.3% (the two-sided Wilson
  upper bound is 5.3%).
- **It kept every completion** the baseline achieved on short delays, lost upgrade responses,
  stale history and the healthy case: 33 of 33 in L against 33 of 33 in B0.
- **The ACCEPTED path has no known source** in the trusted configuration. T065, T097 and T102
  are blocked by that absence, not by tooling. This is bounded evidence (see the statement).

**Does not establish:**
- **Anything about held-out safety.** These are development cases, and the Phase 18 verdict
  (HARM) is final.
- **A loss on transient upgrade failures:** the reading is floor-limited.
- **A certified gain on d5:** it is descriptive.
- **That runtime 2 removed the old failure:** there is no runtime-1 comparator.

## Budget

$465.24 + $18.77 = **$484.01 conservatively charged, $515.99 remaining** of the shared
$1,000.
