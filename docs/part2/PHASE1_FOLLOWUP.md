# Phase 1 alternate-Mechanic follow-up — 2026-09-20

Campaign `campaign-9e7f10cd29ea4eb2b41ad158e262ec5c` finished **NO_CHANGE**. Its fourth diagnosis supported a policy hypothesis, but the frozen budget rejected the complete candidate reservation before any repair proposal was requested. This run therefore does not establish whether the alternate Mechanic can generate a successful repair.

This analysis uses the saved [before-regression recording](../../artifacts/phase1-2026-09-20/learning-v3-mechanic-before-regression.json) and its terminal budget record in `artifacts/lab.sqlite3`. Subsequent fresh regression execution is a separate experiment and is excluded from the counts below.

The frozen configuration used DeepSeek V3.1 for Actor and Mechanic, V4-Pro-0813 for Explorer, configuration `abd6b5f985660bc263e65cc2308e0e457b605d7b5517212d532a66c58e08fd58`, and runtime `97c91555efd5319b4f9c2cdf57db4e80f83be1bf0b947f57a5ae91f0c3813322`. There were 121 attempted episodes: 56 task completions, 64 violations and one infrastructure error. The 837 model calls comprise 828 Actor calls, five Explorer calls and four diagnosis calls. No candidate, source-validation, challenge or promotion batch ran.

## Four fresh diagnosis experiments

All tested the same fault family: delayed completion of the first `update_order` request. The table counts C5 failures in three fresh trials per arm. Every trial in these four interventions completed and triggered its scheduled fault; all observed failures also failed C6/C7 because the original final report was absent.

| Counterexample suffix | Original → retained delay | Retained control → treatment | Control failures | Treatment failures | Fixed result |
|---|---:|---:|---:|---:|---|
| `ee1298e5e03440d588cbb9ac1c07429d` | 12 → 4 ticks | 4 → 1 ticks | 1/3 | 0/3 | INCONCLUSIVE |
| `43b7c1685ac84ee795bc07a3e8cd9372` | 14 → 4 ticks | 4 → 1 ticks | 2/3 | 0/3 | INCONCLUSIVE |
| `5982567f7fba4e76ba88b895cb736ad2` | 16 → 5 ticks | 5 → 2 ticks | 3/3 | 1/3 | INCONCLUSIVE |
| `ab863aa3c67c41d4b42228ef15a3f9ea` | 20 → 5 ticks | 5 → 1 ticks | 3/3 | 0/3 | SUPPORTED / POLICY_GAP |

Each intervention's control hash exactly matches its retained reduction recipe. Those retained recipes previously failed 3/3 during reduction. The first two discrepancies are fresh control variability. The third is treatment variability: that identical two-tick treatment previously passed 3/3 in reduction, then failed once in the intervention. There is no observed control-recipe mismatch or infrastructure explanation for these three inconclusive results. The fixed gate correctly required three failing controls and zero failing treatments; it did not reuse earlier favorable trials.

Diagnosis outputs were not identical: the first two proposed POLICY_GAP and the same semantic delay reduction, the third proposed CONTRACT_EVIDENCE_GAP with a different treatment, and the fourth proposed POLICY_GAP. Their narrative explanations sometimes claimed premature success reports; the retained failed episodes actually have null reports. The deterministic verdict depends on recorded trials, not those model claims. The supported fourth intervention permits testing a candidate; it does not prove that a repair exists or improves performance.

## Timeout retained and excluded

`episode-1a0a80568ea94c368fdaf6e22c39449c` remains `LAB_ERROR`, reason `REQUEST_TIMEOUT`. It belongs to reproduction of the fourth discovery, `counterexample-d44a34e11cd4489ca18e52e4d48b1fb9`, whose delay was 18 ticks. Reproduction stopped with two attempts, one valid trial and one target violation; `reproduced=false`. This incident supplied no diagnosis or repair evidence. Its calls remain charged. The fifth discovery supplied the final supported diagnosis; it did not replace or erase the timed-out trial.

## Exact candidate admission arithmetic

The frozen campaign cap was **$88.32**. The ledger recorded **$17.638** as the charged upper bound, leaving **$70.682**. This is conservative accounting, not a provider invoice: billed cost was unavailable, and the timed-out call also lacked token usage metadata.

The existing admission rule uses the maximum role bound, **$0.04984 per call**, for complete reserved batches:

| Reservation | Calls | Dollar bound |
|---|---:|---:|
| Protected audit, portability and selection comparison | 1,064 | $53.02976 |
| Complete candidate path | 538 | $26.81392 |
| Total additional reservation | 1,602 | $79.84368 |

Admission required `$17.638 + $79.84368 = $97.48168`, exceeding the cap by **$9.16168**. The model-call and token limits were not the blocker: the same reservation would total 2,439 of 6,000 calls and 82,926,000 of 204,000,000 token units. The campaign's terminal reason, `Complete batch exceeds frozen dollar reservation`, accurately identifies this boundary. No candidate call or partial qualification was dispatched.

The relevant unchanged rules are [batch admission](../../backend/app/lab/budgets.py), [candidate reservation before proposal](../../backend/app/lab/learning.py), and [fresh intervention classification](../../backend/app/referee/diagnostics.py).

Before another paid repair campaign, predeclare a budget that preserves enough room for discovery and one complete candidate path, or implement and test role-specific conservative reservations under a new freeze. A separate fixed repeatability study would help quantify the variable report-closure behavior. Neither change should reuse favorable trials, relax promotion gates, alter original reports or turn these negative results into a repair-success claim.
