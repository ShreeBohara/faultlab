# Status clarifications — September 27, 2026

This is a new note, not a rewrite or rescore of historical experiments. Current work and verification
are tracked in [CURRENT_STATUS.md](../../CURRENT_STATUS.md).

- Phase 28 generated repairs for a fixed, human-selected source using controls, Mechanic proposals,
  source tests and validation. No Explorer discovery, generated challenge or original promotion ran.
  Claude corrected the Explorer wording in PHASE28_RESULTS.md before this consolidation; that
  already-corrected file is preserved unchanged by this work.
- The Phase 20 source probe found no qualifying invariant-failure source in its finite tested settings.
  It did not establish that no such source can exist.
- Phase 28's 9/49 and Phase 23's 3/30 are different experiments. They do not establish superiority
  or a pooled general success rate. “Certified” is a development-experiment label, not ACCEPTED.
- Phase 30 recommended a later live test of a narrow reporting hint. It did not adopt the hint or
  demonstrate its end-to-end benefit.
- Dated handoffs, CURRENT_STATE.md, old phase task lists and the original PLAN.md retain their
  historical meaning. Their “current”, “next” and budget statements do not supersede CURRENT_STATUS.md.
- The original checklist's 234/239 count ends at Phase 15 and is not a percentage of product readiness.

The September 27 code audit reproduced a successful-replay parsing defect and a post-report-hook
citation mapping defect. The latter was not observed in the 4,615 stored reports inspected. The fixes have a new runtime identity; no historical trial or qualification decision was rewritten.


## Implementation completed after the audit

- The root `CURRENT_STATUS.md` is the current entry point. README, AGENTS, CLAUDE and the
  active handoff/memory wrappers link there. Original notes and setup guides were copied to
  `memory/history/2026-09-27-before-consolidation/` before replacement.
- Successful replay validation now uses `replay_policy_hash`. The ordinary generated-candidate
  checks remain strict. Request-time observations now supply citation labels, decoding and Actor
  output metadata; a report hook cannot add a label to the request after the model answered.
- New app campaigns freeze v4 indexed evidence, with explicit overrides and absent-field historical
  v1 handling. Both launchers use V3.1 Actor / V4 Pro 0813 reasoning defaults through the same
  configuration loader. Actual configured values appear separately from saved campaign metadata.
- The status display checks the stronger saved development qualification, separately joins unseen
  checks by exact source study, policy version and hash, and reads the campaign's active pointer.
  It returns no private unseen-case recipes, trial IDs or reasons. It does not promote policies.
- The two original research test failures were repaired without blanket skips. The duplicate-policy
  rejection and cancelled-protocol rejection still have explicit tests. Three additional old-default
  assertions found during the broad check were updated to exercise the new v4 and Aria-off defaults,
  plus explicit v1 and Aria-enabled behavior. Scoring and acceptance requirements were not weakened.

## Manual verification

The actual dashboard and local backend were checked, with no new campaign or model call:

| Saved campaign | Verified display |
|---|---|
| `campaign-9a412c8862714aac89e6851e7d7706e1` | Successful replay opens; 42/42 saved traces verified; Replay only; unseen check not run; baseline active |
| `campaign-ba37f75678284372ad5dcc2b3635481e` | Development qualified; unseen check not run; baseline active |
| `campaign-9bc991df39ff4c61a2668f87fac5bac1` | Its exact source policy is development qualified; separate completed check is HARM; baseline active |

The saved-data projection matches all 88 Phase 17/23/28 attempts, including the distinction between
Phase 28's ten OBSERVED_IMPROVEMENT studies and nine stronger development qualifications. The
current source/configuration is new; these are historical results, not live validation of this revision.

All 37 historical result documents retain their pre-change hashes. Campaigns, episodes, policies,
completion studies, unseen checks, evidence and ingestion records match the September 26 backup.
Record counts remain unchanged. The fixed Referee source, policy interpreter/state and Actor system
prompt also match the pre-change source. Local verification artifacts are in
`artifacts/verification-2026-09-27/`; final test results are recorded in CURRENT_STATUS.md.
