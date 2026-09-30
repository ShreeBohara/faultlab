# v2d: Learn campaign with history replay on native adapter v2.1 (declared before any paid call)

Written 2026-09-30 ~06:35 UTC by Claude (PM, delegated by the owner). Runtime `ee2d1df9…` (backup commit `814a6e3`).

## Question
With discovery protocol `faultlab-discovery/v4-history-replay` (built and verified at $0 today), the loop first
replays this same agent's verified, consistently failing development recipes, then lets the Explorer search. **Does
the original loop, given the agent's reliable repairable failure (dev-5: a rejected upgrade, after which the agent
sends the confirmation anyway, C3; 6 of 6 on v2/v2.1, 9 of 9 on v1), get through reproduction, reduction,
diagnosis, a generated candidate, source validation, challenge and promotion?** Earlier runs never reached a
candidate on v2.x because discovery never picked this failure (v2c) or a network blip ended the run (b05ac280).

## What runs
One Learn campaign in the v2b store (`/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/`), for the v2.1 agent
(prompt `fff397c9…`) registered again under this runtime. History = v2.1's own verified development outcomes in this
store (the 18 v2b baseline episodes plus v2c's Explorer picks), frozen at plan creation with its hash and cutoff.
The frozen replay list is recorded in `DECLARATION.json` before Start. Replay sources are reported as **history
replays of known failing development recipes, never as independent discovery**.

Lab roles use `faultlab-transport-retry/v2-lab-backoff`; evidence waits use `faultlab-evidence-retry/v2`.

Bounds and stop rules as in the earlier plans: product ledger ceiling (4,936 requests, about $106.87); watcher
`watch_learn_v3.py`: > 8 discovery selections; before any counterexample used_calls > 144 or charged > $3.47;
disk < 2 GiB; 10 hours; at most 3 operator evidence retries, 10 minutes apart. Operator stops only for world-integrity
failure, two consecutive LAB_ERROR, or auth/config/frozen-model failure. Never restart, replace or reroll.

## Pre-registered read-outs
1. The furthest stage reached and the decision at each; the source's provenance (replay row or Explorer pick).
2. `check_evidence_gap_misreading.py` (sha `70c4eeda…`) on the export: every CONTRACT_EVIDENCE_GAP diagnosis
   classified MISREADING / SUPPORTED / NOT_CHECKED.
3. Integrity: clock drift (both checks), world integrity, evidence verification.

## Meanings
- ACCEPTED would be the project's first generated-policy acceptance, for this one declared agent build, conditional on
  the integrity checks; the source would be a replay of a public development recipe, so it would show that the loop
  can repair a known failure of an external agent — not that it discovered one, not transfer, not held-out safety.
- REJECTED (with the stage and reason), NO_CHANGE, STOPPED and ERROR are reported as they are.
