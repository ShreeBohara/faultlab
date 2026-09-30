# v2e: history-replay Learn campaign on native adapter v2.1, bounded Mechanic context (declared before any paid call)

Written 2026-09-30 ~10:15 UTC by Claude (PM, delegated by the owner). Runtime `f058c03c…` (backup commit `884de24`).

A **new declared run on a new build**, not a restart of v2d (`ea66672d`, ERROR on the Mechanic input limit), whose
result stands. Since v2d, one FaultLab defect was fixed and verified at $0: the Mechanic's candidate/diagnosis
context is bounded by `faultlab-mechanic-context/v2-bounded` (deterministic compaction stated in the request; a
request that still cannot fit ends that source's candidate search with a plain reason, never ERROR, never sent over
the limit). The challenge candidate-reach rule built in the same round was **withdrawn** after review (it weakened the
challenge) and is not used. The challenge is unchanged; an untriggered challenge pair still makes it INCONCLUSIVE.

Everything else is as in `../native-v2d-run/PLAN.md` (sha `24153493…`): one Learn campaign, discovery
`faultlab-discovery/v4-history-replay`, v2b store, v2.1 agent registered again under this runtime, history frozen at
plan creation (replay episodes never enter later histories), frozen replay list recorded before Start; replay sources
reported as history replays, never independent discovery. Lab-role backoff retry and automatic evidence retry as
frozen in the plan. Bounds: product ledger ceiling (4,936 requests, about $106.87); watcher `watch_learn_v3.py`
(> 8 selections; before any counterexample used_calls > 144 or charged > $3.47; disk < 2 GiB; 10 hours; at most 3
operator evidence retries, 10 minutes apart). Never restart, replace or reroll.

Pre-registered read-outs: furthest stage and each decision; each candidate's source validation, challenge (schedules,
triggered pairs, failed checks) and decision; any Mechanic context compaction or size-limit ending;
`check_evidence_gap_misreading.py` (sha `70c4eeda…`); integrity (clock drift both checks, world integrity, evidence).
ACCEPTED would be the project's first generated-policy acceptance, for this one declared agent build, from a replay
of a known failing development recipe, conditional on the integrity checks; it would not show discovery, transfer or
held-out safety.
