# v2g: history-replay Learn campaign on native adapter v2.1 with history fireability (declared before any paid call)

Written 2026-09-30 ~16:25 UTC by Claude (PM, delegated by the owner). Runtime `49958e71…` (backup commit `661e2d0`).

A new declared run on a new build, not a restart of v2f (`53db7476`, STOPPED; its result stands). Since v2f two
declared rules were built, reviewed twice, fixed and verified at $0:
- `faultlab-explorer-selection/v3-history-fireability`: a per-target fired table, frozen at plan creation from this
  agent's verified starting-policy history only (candidate-independent). A challenge or discovery Explorer pick is
  refused before any episode runs **only when every one of its faults is on a target with at least 3 verified history
  episodes and a fired share below 1/2**; the Explorer then gets one re-plan within its existing budget.
  **Residual bias, stated plainly:** a lone orders status-read fault can no longer be a challenge schedule. That read
  is a step the generated guardrails add. A status-read failure combined with a fireable fault (for example during a
  pending upgrade) still runs and can still find a counterexample. Signed off by the PM (delegated).
- `faultlab-evidence-retry/v3`: the same per-wait retries, per-campaign cap 24 instead of 6.

Everything else is as in `../native-v2f-run/PLAN.md` (sha `0ac8ff3f…`): discovery `faultlab-discovery/v4-history-replay`,
v2b store, v2.1 agent registered again, history frozen at plan creation, frozen replay list, replay sources reported as
history replays; bounded Mechanic context; citation status; lab-role backoff retry; ledger ceiling (4,936 requests,
about $106.87); watcher `watch_learn_v3.py` (> 8 selections; before any counterexample used_calls > 144 or charged >
$3.47; disk < 2 GiB; 10 hours; at most 3 operator evidence retries). Never restart, replace or reroll.

Pre-registered read-outs (descriptive only; no concurrent control):
1. Furthest stage and each decision; each candidate's source validation, challenge (schedules, triggered pairs, failed
   checks) and decision; promotion and its decision if reached.
2. Did any Explorer pick get refused by the fireability rule, and did the re-plan run; did any challenge reach 4
   complete schedules; did any challenge schedule fault the orders status read (alone or combined).
3. Automatic evidence retries used, operator retries used.
4. `check_evidence_gap_misreading_v2.py --read-out pre-registered` on the export.
5. Integrity: clock drift (both checks), world integrity, evidence.
ACCEPTED would be the project's first generated-policy acceptance, for this one declared agent build, from a replay of
a known failing development recipe, with the challenge bias above, conditional on the integrity checks; not discovery,
transfer or held-out safety.
