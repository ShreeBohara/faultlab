# Native adapter v2, live: plan (declared before any paid call)

Written 2026-09-29 ~23:45 UTC by Claude (PM, delegated by the owner). Runtime `ac7a12d2…` (backup commit `c9db705`).

## 1. Question
The native smolagents agent (DeepSeek-V3.1) failed mostly by not filing a valid report (C5), which no runtime
policy can fix, and that blocked every repair on 2026-09-29. Adapter v2 gives it the reference Actor's two report
fixes (short obs-N evidence labels; a strict final-report turn). **Does v2 stop the report failures while the
repairable failure (a confirmation sent after a rejected upgrade, C3 on dev-5) remains, and can the original loop
then learn and promote a policy for it?**

## 2. Step 1: baseline study (probe)
Product path, same as the 2026-09-29 v3 run: register `smolagents-v2` in a new store, plan a baseline campaign,
`POST /baseline-study {"execute_live":true}`: 6 public development cases × 3 trials × 2 arms (B0 = native v2 with
the empty policy; B1 = handwritten control, 0 model calls). No hand-picked cases.
- Bound: 144 reserved actor calls + at most 144 charged transport retries = 288 calls, $6.02 conservative max
  (288 × $0.0209). Expected about $2.35 conservative.
- Stop rules (watcher `monitor_step1.py`): any LAB_ERROR/INTERRUPTED; any B1 control deviation; INCOMPLETE; > 288
  calls; 45 minutes.

## 3. Declared decision (computed by `compute_go.py`, self-tested: native v1's 2026-09-28 data gives NO_GO)
**GO to step 2** only if all hold: study COMPLETED; 0 lab errors; 0 B1 deviations; dev-5 C3 in ≥ 2 of 3 B0 trials;
C5 in ≤ 2 of the 15 B0 trials outside dev-5 (v1: 4 of 15 on 2026-09-29, 5 of 15 on 2026-09-28).
Otherwise **NO_GO**: write up, no step 2. If dev-5 C3 disappears, that is itself the finding (v2 removed the target).

## 4. Step 2 (only on GO): one Learn campaign, discovery `faultlab-discovery/v3-history`, same store
History = v2's own step-1 results, frozen at plan creation (hash and cutoff recorded before Start). The Explorer
chooses freely; a re-pick of a history row is allowed and reported as history-informed, never as independent discovery.
- Bounds: the product ledger (4,936 requests, about $106.87 conservative ceiling); discovery before any
  counterexample at most 144 requests / $3.47 (watcher). Expected $8–40 conservative.
- Stop rules (watcher `watch_learn_v3.py`): > 8 discovery selections; before any counterexample, used_calls > 144 or
  charged > $3.47; disk < 2 GiB; 10 hours. Evidence waits: the product retries by itself (3 per wait, 6 per campaign);
  when it asks for an operator, the watcher applies at most 3 telemetry-only retries, 10 minutes apart.
- Operator stops: world-integrity failure; two consecutive LAB_ERROR; auth/config/frozen-model failure. Never restart,
  replace or reroll.

## 5. What results would mean
- ACCEPTED: the project's first generated-policy acceptance, for this one declared agent version, conditional on
  post-run integrity checks (clock drift, world integrity, evidence). Not transfer, not held-out safety, not generality.
- REJECTED/NO_CHANGE: honest outcomes; the write-up says at which stage and why.
- v2 is a declared change to the agent under test (its integration boundary), not to FaultLab's gates; v1 and v2
  results are never pooled.

## 6. Checks before Start
AC power; no FaultLab services; dashboard closed; new data dir `/Users/shree/FaultLab_Runs/2026-09-30/native-v2/`;
prices checked (price-check.json, unchanged); readiness ready with provider_calls 0; registration prompt hash =
v2's (`cee3aeda…`), scorer `19de811c…`. After: `check_clock_drift.py` and `check_clock_drift_native.py`; ledger update.
