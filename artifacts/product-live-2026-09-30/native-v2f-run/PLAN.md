# v2f: history-replay Learn campaign on native adapter v2.1 with citation status for the Mechanic (declared before any paid call)

Written 2026-09-30 ~12:35 UTC by Claude (PM, delegated by the owner). Runtime `95042e4d…` (backup commit `47b8f69`).

A new declared run on a new build, not a restart of v2e (`37e66b6c`, NO_CHANGE), whose result stands. Since v2e one
change was built and verified at $0: `faultlab-mechanic-evidence/v2-native-citation-status` gives the Mechanic (and
the challenge Explorer), for native v2 plans only, each episode's recorded citation outcome (cited tokens, how many
decoded to delivered evidence, undecoded tokens). In v2d and v2e the Mechanic falsely claimed the agent cited unshown
labels; in v2e that ended the source at an INCONCLUSIVE diagnosis.

Everything else is as in `../native-v2e-run/PLAN.md` (sha `9cc72fac…`): discovery `faultlab-discovery/v4-history-replay`,
v2b store, v2.1 agent registered again, history frozen at plan creation, frozen replay list recorded before Start,
replay sources reported as history replays; bounded Mechanic context; lab-role backoff retry; automatic evidence retry;
ledger ceiling (4,936 requests, about $106.87); watcher `watch_learn_v3.py` (> 8 selections; before any counterexample
used_calls > 144 or charged > $3.47; disk < 2 GiB; 10 hours; at most 3 operator evidence retries). Never restart,
replace or reroll.

Pre-registered read-outs (descriptive only: there is no concurrent control, so one run cannot show the change caused
any difference):
1. Furthest stage and each decision; each candidate's source validation, challenge (schedules, triggered pairs,
   failed checks) and decision; promotion if reached.
2. `check_evidence_gap_misreading_v2.py --read-out PRE_REGISTERED` (sha recorded in DECLARATION.json) on the export:
   each diagnosis MISREADING / SUPPORTED / NOT_CHECKED, plus a human check of each CHECKED verdict.
3. Integrity: clock drift (both checks), world integrity, evidence.
ACCEPTED would be the project's first generated-policy acceptance, for this one declared agent build, from a replay of
a known failing development recipe, conditional on the integrity checks; not discovery, transfer or held-out safety.
