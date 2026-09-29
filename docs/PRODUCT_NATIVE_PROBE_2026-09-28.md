# Native smolagents baseline probe: result

- **Run:** 2026-09-29 03:53–03:57 UTC (2026-09-28 local).
- **Plan and declaration:** `artifacts/product-live-2026-09-28/plans/native/PLAN.md`, and
  `artifacts/product-live-2026-09-28/native-probe/DECLARATION.json` (sha256 `ef9cf93a…`). Both were
  written before any paid call.
- **Product path:** the planned live baseline campaign `campaign-e5b01658…` names the native registration
  `smolagents-1.26.0-d72de2e0…`. The product's baseline study `baseline-study-9a64322d…` runs 6 development
  cases × 3 trials × 2 arms: B0 is the native agent (live) and B1 the handwritten reference control (no
  model calls).
- **Runtime:** `c0a8aad7…` (source commit `e7340c9`).
- **Agent inputs are unchanged from Phase 1** (2026-09-20): native prompt `2251542869cf…`, smolagents source
  `2867b3fb…`, scorer `19de811c…`.
- **Store:** a separate, new store at `/Users/shree/FaultLab_Runs/2026-09-28/native-probe/`.

## Result: COMPLETED, 36 of 36 trials, no stop rule fired

**Integrity:**
- 0 lab errors, 0 interrupted episodes.
- B1 controls exactly as expected: 15 COMPLETED and 3 CORRECTLY_REJECTED.
- 36 of 36 trials verified in Weave.
- Clock check:
  - The checker flagged 13 B0 rows. All are explained by the declared native rule: report tick 0, lab and
    world attempt counts equal, and `private_world_integrity` VALID (36 of 36).
  - Real drift 0, masked faults 0, missing worlds 0.

**Cost:**
- 102 model calls, $2.1318 conservative charge (limit 144 / $3.01).
- Measured tokens: 405,434 in and 6,340 out, which is about $0.23 at token prices.

| case | fault | Phase 1 (2026-09-20) | today |
|---|---|---|---|
| dev-1 | none | 0/3 violated | **1/3** violated: no valid report (C5, C6, C7) |
| dev-2 | lost upgrade response | 0/3 | 0/3 |
| dev-3 | upgrade pending 3 ticks, then succeeds | **3/3, no report** | **3/3, no report** (C5, C6, C7, 8 calls each) |
| dev-4 | stale order read | 1/3 | 0/3 |
| dev-5 | upgrade rejected | **3/3 C3** | **3/3 C3** (C5 in all three; one also had no report) |
| dev-6 | first two confirmation sends fail | 1/3 (C7), 2 safe-unresolved | 1/3 (C4, C5), 2 safe-unresolved |
| **total** | | **8/18** | **8/18** |

## What it means

**These are all agent mistakes, not FaultLab errors.**
- Every B1 control behaved correctly.
- World integrity is VALID for every episode.
- The failing reasons are the agent's own: "External agent produced no valid original final report", or a
  confirmation sent after a FAILED upgrade receipt.

**The native agent still breaks rules reliably, unlike the reference Actor.**
- It sent a false confirmation after a rejected upgrade in 6 of 6 runs across two days.
- It fails to file any report on a delayed upgrade in 6 of 6.
- Its driver never received the reference Actor's later fixes (a reserved report turn with a strict format,
  and obs-N citation labels).

**For the original learn loop:**
- A rejected-upgrade recipe is a plausible 13-in-a-row source.
- A hook policy can block C3 (the confirmation after a FAILED receipt).
- No hook can write a missing report. A source whose lowest failed check is C5 ("no report") cannot be
  repaired by a policy, and would end correctly as REJECTED or NO_CHANGE.
- **With 3 trials per case this is a screen, not a rate estimate** (3/3 against 0/3 gives Fisher p = 0.10).

## Budget

$856.96 + $2.14 (rounded up from $2.1318) = **$859.10 conservatively charged**. The owner added funds on
2026-09-28, so the old $1,000 cap no longer binds. Spending is still declared and capped per run.
