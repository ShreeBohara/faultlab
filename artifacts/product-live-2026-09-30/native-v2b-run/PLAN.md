# Native adapter v2.1, live: plan (declared before any paid call)

Written 2026-09-30 ~03:15 UTC by Claude (PM, delegated by the owner). Runtime `4553ebe7…` (backup commit `78878bb`).

This is a **new declared run on a new build**, not a restart of campaign `b05ac280`. That run's result (ERROR on an
Explorer connection blip, after three C4 sources) stands and is written up in
`docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md`. Since then two FaultLab defects were fixed and verified ($0):
lab-role transport retry with backoff (`faultlab-transport-retry/v2-lab-backoff`: Explorer and Mechanic, waits
5/20/60 s, at most 12 per campaign, charged before sending, Stop-cancellable) and contiguous shown-order labels in
native adapter v2.1 (prompt `fff397c9…`). v2.1 is a new agent identity: its history starts empty and is never pooled
with the first v2 build's.

Everything else is the same as `artifacts/product-live-2026-09-30/native-v2-run/PLAN.md` (sha `037aa6fb…`):
- **Step 1** baseline study: 6 public development cases × 3 × 2 arms; bound 288 calls / $6.02 conservative; stop
  on any LAB_ERROR/INTERRUPTED, any B1 deviation, INCOMPLETE, > 288 calls, 45 minutes.
- **Decision** (`compute_go.py`, byte-identical copy, sha `5145f28c…`): GO iff COMPLETED, 0 lab errors, 0 B1
  deviations, dev-5 C3 ≥ 2 of 3, C5 ≤ 2 of the 15 trials outside dev-5.
- **Step 2** (only on GO): one Learn campaign, discovery `faultlab-discovery/v3-history`, same store; ledger ceiling
  (4,936 requests, about $106.87); watcher `watch_learn_v3.py`: > 8 selections; before any counterexample,
  used_calls > 144 or charged > $3.47; disk < 2 GiB; 10 hours; at most 3 operator evidence retries, 10 minutes apart.
  Never restart, replace or reroll.

**New pre-registered check** (review finding P-1, deferred by the PM instead of changing the Mechanic's frozen
evidence view): after the run, `check_evidence_gap_misreading.py` (copy of
`artifacts/product-native-v2b-2026-09-30/fixer/`, self-tested 5/5; it scores the 2026-09-29 diagnosis MISREADING)
classifies every diagnosis. If any v2.1 diagnosis is a MISREADING, the next build adds a declared compact-evidence
format that marks rows the agent was not shown.

Meanings are unchanged: ACCEPTED would be the project's first generated-policy acceptance for this one declared
agent build, conditional on the integrity checks; REJECTED, NO_CHANGE, STOPPED and ERROR are reported as they are.
