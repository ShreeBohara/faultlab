# Phase 11 progress

Protocol: [PHASE11_EXPERIMENT.md](PHASE11_EXPERIMENT.md). Results: [PHASE11_RESULTS.md](PHASE11_RESULTS.md).
Checked means done and verified, not planned.

## Design

- [x] Ran a five-proposal design panel under seven hard constraints, each proposal judged by three independent lenses (constraint compliance, adversarial actor, engineering cost).
- [x] Selected the design that tied highest (8.0, 3 of 3 ship votes) and, unlike the runner-up, does **not** move `scorer_hash`.
- [x] Acted on the judges' strongest objection — that cheap labels make blanket citation free — by removing the proposed paste-ready `citable_evidence_ids` list and declaring citation breadth as a measured read-out instead of arguing about it.
- [x] Quantified the mechanism from retained data for $0 first: corruption is flat (~2.5%) below 12 citations and jumps to **30%** at ≥12, and every episode in that regime is `notification-18`.

## The change

- [x] `faultlab-actor-context/v4-indexed-evidence`: observations shown as `obs-1 … obs-n`; no 32-hex identifier reaches the Actor.
- [x] Decode is total, exact-match only, and passes unmatched tokens through verbatim so they still fail C6.
- [x] **`checks.py` never opened; `scorer_hash` verified unchanged.** `actor_prompt_hash`, `adapter_hash`, `interpreter_hash`, `contract_hash`, `capability_hash` and `dependency_lock_hash` all identical to Phase 10.
- [x] Descriptor hashes of v1, v2 and v3 verified **byte-identical** to those frozen in the store.
- [x] Tested through the real scorer: labels give an identical verdict; `obs-99`, a fabricated hex identifier, an empty list and `obs-1extremely` all still produce `VIOLATION`.
- [x] 566 backend, 124 frontend, build and 3 browser fixtures green.

## Abandoned before spending

- [x] Established from retained data that a **context study cannot measure this change**: zero corrupted citations across all 120 Phase 4 context-study episodes, maximum 8 citations where corruption needs ≥12, because context studies run `policy-v0` and long citation lists require a policy to be executing. Recorded in the protocol rather than quietly dropped.
- [x] Also recorded that the context-study decision rule returns `REGRESSION` on any single violation in 30 episodes, which at the measured baseline fires ~64% of the time regardless of the change.

## The run

- [x] Stage A, one replay as a declared validity check: `OBSERVED_IMPROVEMENT`, $4.45, with `notification-18` citing 13/14/13 identifiers and **zero fabrications across all 42 episodes**.
- [x] Pooling rule for Stage A fixed **before** Stage B ran.
- [x] Stage B, 12 attempts, 6 scored, 6 unscored and replaced, $35.32.
- [x] **Declared primary read-out: 2 of 6, Fisher p = 0.088 — reported as not significant.** Pooled 3 of 7, p = 0.031, reported alongside rather than instead.

## Findings recorded

- [x] **370 episodes under v4, zero fabricated identifiers** (v1 baseline 3.43%); the ≥12-citation regime went 30% → **0 of 14**.
- [x] **C1–C8 violation rate 6% → 0%.**
- [x] **Quality rejections 8 of 13 → 0 of 7, p = 0.015.** Every Phase 11 non-pass was batch fragility, not policy quality.
- [x] **Phase 4 regression guard passes**: no case lost its target outcome, no case gained a violation; `notification-18` went 66% → 92% with its 12 violations eliminated. The two dips are noise (p = 0.51, p = 0.36) with benign `SAFE_UNRESOLVED` outcomes.
- [x] Checked for side effects: fault triggering unchanged (97.5% → 97.4%), actor calls 5.42 → 5.14, HTTP attempts 6.00 → 5.92, COMPLETED identical at 59%.
- [x] **A pre-registered concern came out backwards and is recorded as such**: citation breadth *fell* (0.887 → 0.735; 100%-citers 72% → 42%). The Actor became more selective, which is the harder direction, since C6's sub-clauses require the supporting receipt to be cited.
- [x] Reconciled cost and updated results, limitations, memory and the central checklist.
