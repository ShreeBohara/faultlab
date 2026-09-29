# Original loop, live, against the native smolagents agent. Result: NO_CHANGE after two reproduced sources and two INCONCLUSIVE diagnoses

- **Run:** 2026-09-29, 07:09–07:17 UTC.
- **Campaign:** `campaign-7ee35abe…`, in Learn mode running the original loop with discovery v1 (v2 refuses a
  native agent). The Actor was the native smolagents agent on DeepSeek-V3.1, registration
  `smolagents-1.26.0-819f4d1f…`; the Explorer and Mechanic were V4-Pro-0813.
- **Runtime:** `c9af0a47…`. It includes the bounded transport retry and the native report-tick fix.
- **Store:** a new store at `/Users/shree/FaultLab_Runs/2026-09-29/native-learn/`.
- **Plan, review and declaration:** `artifacts/product-live-2026-09-28/plans/native-learn/PLAN.md`,
  `REVIEW.md` (all 5 blockers resolved before Start, as recorded in the declaration), and
  `artifacts/product-live-2026-09-29/native-learn-run/DECLARATION.json` (sha256 `ece36a73…`).

## What happened (from the product's own records)

| stage | what the loop did |
|---|---|
| Discovery | 8 Explorer picks; 8 native episodes |
| Source 1 | A discovery episode broke **C5** (no truthful final report). **Reproduced 3 of 3.** Reduced. **Diagnosis: INCONCLUSIVE.** The Mechanic said that in the reduction trials no intervention removed the violation, so a policy gap could not be told apart from an evidence gap. |
| Source 2 | A later discovery episode broke **C5** again. **Reproduced 3 of 3.** Reduced. The Mechanic proposed **CONTRACT_EVIDENCE_GAP**: the delayed SUCCEEDED receipt arrives only after the agent has used its polling turns and reserved report turn, so it cannot cite a terminal receipt. The declared intervention ran. **Diagnosis: INCONCLUSIVE** ("evidence incomplete or contradictory"). |
| End | Discovery slots were exhausted, and no diagnosis was POLICY_GAP. **No candidate was proposed.** The campaign ended **NO_CHANGE** and the active policy stayed `policy-v0`. |

- **This is the first live campaign in which the original loop reproduced, reduced and diagnosed a real
  source.** The earlier live original-loop run (c701e850, reference Actor) found nothing to reproduce.
- **The stages below diagnosis did not run:** Mechanic candidate, source validation, challenge and
  promotion. They still have no live evidence.

## Why no repair: the loop behaved correctly

- **Both sources were C5.** The native agent failed to file a truthful report, which Phase 1 and yesterday's
  probe also showed (6 of 6 on delayed upgrades).
- **No hook policy can write a report.** The diagnosis stage refused to label the gap POLICY_GAP, so it did
  not spend candidate slots on an unfixable source. This is the declared expectation (PLAN §12: "most likely
  NO_CHANGE").
- **The one repairable failure never came up.** That failure is C3, a confirmation sent after a *rejected*
  upgrade (6 of 6 in the probes), which a `before_confirmation` receipt rule can block. It was never exposed,
  because **the Explorer never picked a rejected-upgrade recipe**. Its 8 picks were:
  - F3 stale read
  - F1 confirmation delay
  - F2 successful upgrade delayed 16 ticks
  - F4 on a status read
  - F2 delayed 3 ticks
  - F4 on the confirmation send
  - F2 delayed 12 ticks
  - F2 delayed 8 ticks plus F1

  Four of the eight were delayed-success upgrades, as the plan warned. Discovery v2's pre-check cannot guide
  a native agent. This is an Explorer search limitation, not an agent or scoring defect.

## Integrity and cost

**Integrity:**
- 50 episodes, all with world integrity VALID.
- Clock-drift check: 0 drifted, 0 masked, 0 missing worlds. The new native report tick removed the tick-0
  false flags.
- 0 transport retries were needed.

**Cost:**
- 346 requests, $7.5208 conservative. Measured tokens were 1,484,323 in and 18,231 out, about $0.95 at
  token prices (mostly native V3.1 turns).
- One call has unknown tokens.
- The expected cost was declared as about $8. The ceiling of $106.87 was never approached.

## What it shows, and what it does not

**It shows:**
- **Live, the original loop discovered, reproduced (3 of 3, twice), reduced and diagnosed rule violations
  by an agent that genuinely breaks rules.**
- **It correctly declined to generate repairs for failures a policy cannot fix.**
- All stop rules and budgets held, and the product's records reconcile.

**It does not show:**
- A generated repair.
- Source validation, challenge or promotion live.
- ACCEPTED.
- Anything about C3, which was never exposed.

## Next, if pursued

The most direct way to exercise the rest of the loop live, without weakening anything, is to point discovery
at the repairable C3 failure:
- **(a) Honest option:** give the Explorer the saved per-recipe history of the registered agent (the plan's
  "give the Explorer the agent's baseline history" idea), declared and reviewed.
- **(b) Declared and reproducible option:** a native pre-check with a caller modelled on this agent.

Either needs its own build and review. **Never** hand-pick the source outside the product's discovery path.

## Budget

$861.60 + $7.53 (rounded up from $7.5208) = **$869.13 conservatively charged**.
