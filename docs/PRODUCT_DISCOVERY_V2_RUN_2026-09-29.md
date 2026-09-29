# Discovery protocol v2: complete live run. Result: 8 of 8 slots fully fired (v1 baseline: 4 of 8)

- **Run:** 2026-09-29, 07:05–07:07 UTC.
- **Campaign:** `campaign-17d60a9e…`.
- **Setup:** Learn mode with discovery protocol v2. The Actor was the reference V3.1 agent under policy-v0;
  the Explorer and Mechanic were V4-Pro-0813.
- **Runtime:** `c9af0a47…` (commit `291324d`). This runtime includes the new bounded transport retry for the
  Explorer, Mechanic and native agent.
- **Store:** a new store at `/Users/shree/FaultLab_Runs/2026-09-29/discovery-v2b/`.
- **Relation to the earlier run:** this is a new, separately declared run replacing the INCOMPLETE
  `campaign-a301846e…` (`PRODUCT_DISCOVERY_V2_RUN_2026-09-28.md`). The results are never merged.
- **Declaration:** `artifacts/product-live-2026-09-29/discovery-v2b-run/DECLARATION.json` (sha256
  `7947fdd5…`), written before Start. Its dollar figures were re-read before it was hashed.
- **Readings:** declared in `plans/discovery-v2/PLAN.md` §9.

## Primary (declared): fully-fired discovery slots, out of 8 — **8 of 8**

This was computed by the pre-declared `compute_primary.py` (sha256 `9b5b7ba9…`), which returned `valid: true`
with no problems.

| slot | result | Actor outcome |
|---|---|---|
| 0 | fully fired | SAFE_UNRESOLVED |
| 1 | fully fired | SAFE_UNRESOLVED |
| 2 | fully fired | COMPLETED |
| 3 | fully fired | COMPLETED |
| 4 | fully fired, after one re-plan | COMPLETED |
| 5 | fully fired | COMPLETED |
| 6 | fully fired | COMPLETED |
| 7 | fully fired | SAFE_UNRESOLVED |

**Declared reading for 8 of 8:** the strongest outcome. Against c701e850's 4 of 8 the one-sided Fisher p is
0.038. The wording is "**consistent with v2 raising fault exposure in this setup**", not "proven". This is
one campaign against an earlier one, not a concurrent control. The runtime, the Explorer's context and model
randomness all differ, and the 8 slots are not independent.

**Mechanism checks:**
- **The pre-check refused one pick,** with reason `N2_UNNEEDED_STATUS_CHECK`: a fault on a status check this
  Actor would never make. That is exactly the kind of pick that never fired in c701e850 (its slots 2 and 5).
  The single re-plan ran and fully fired.
- **FORCED faults fired 8 of 8.** There were 0 duplicates, 0 fallbacks and 0 slots without an episode.
- **Diversity was good:** six distinct targets fully fired.
  - F1, F2 and F4 on `orders.update_order`
  - F3 and F4 on `orders.get_order`
  - F4 on `notifications.send_confirmation`

  The incomplete run on 2026-09-28 targeted `update_order` only. There were no multi-fault or deeper-attempt
  picks.
- **Explorer requests:** 9 out of the 16 allowed. No transport retry was needed.

**No source.** The Actor finished 5 runs COMPLETED and 3 SAFE_UNRESOLVED, with no rule broken, so the
campaign ended NO_CHANGE: "No verified strict improvement within declared development bounds; all outcomes
retained". This was the declared expectation for this Actor ("ACCEPTED unreachable", `CURRENT_STATUS.md`).

**What this shows, and what it does not:**
- **It shows** that the pre-check turns paid discovery budget into fully exercised fault schedules, that a
  refused pick is recovered by one re-plan, and that FORCED labels held live (8 of 8).
- **It does not show** that ACCEPTED is reachable, that more exposure finds more bugs, or anything about
  repair quality or the native agent.

## Integrity and cost

- **Clock-drift check:** 8 of 8 episodes, 0 drifted, 0 masked, 0 missing worlds.
- **Source drift:** none. The reference agent's configuration hash equals the campaign's (`4c46925c…`).
- **Cost:** 57 requests, $1.4518 conservative. Measured tokens were 257,268 in and 3,043 out, about $0.24 at
  token prices.

## Budget

$860.14 + $1.46 (rounded up from $1.4518) = **$861.60 conservatively charged**.
