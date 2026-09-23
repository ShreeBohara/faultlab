# Phase 4 progress

Protocol: [PHASE4_EXPERIMENT.md](PHASE4_EXPERIMENT.md). Results: [PHASE4_RESULTS.md](PHASE4_RESULTS.md).
Checked here means done and verified, not planned.

## Evidence review

- [x] Reconstructed the three named Phase 3 episodes turn by turn from the saved database.
- [x] Measured the baseline behaviour across all 18 source-case episodes: one `send_confirmation` call, never a second, 0 completions, 7–10 of 18 HTTP attempts used.
- [x] Confirmed the mechanism in code: `get_operation_status` targets the pre-allocated operation id, so a never-submitted operation answers `UNKNOWN` exactly like a rejected one.

## Implementation

- [x] `backend/app/agents/progress.py`: two versioned context protocols, the attempted-write summary and a pure protocol registry.
- [x] `backend/app/agents/actor.py`: select the protocol per episode; v1 rebuilds the preserved message byte for byte; stamp protocol and digest into every `actor_output` event.
- [x] `backend/app/adapters/prototype.py`, `backend/app/lab/runner.py`: carry the protocol into the episode context without a second Actor entry point, so both arms keep one traced `run_episode` root.
- [x] `backend/app/lab/configuration.py` + `backend/app/integrations/registry.py`: freeze the protocol registry once and bind the reference registration to it.
- [x] `backend/app/contracts/models.py`: arm `P1`, purpose `context_study`; contracts, manifest and wire types regenerated.
- [x] `backend/app/telemetry/safety.py`: allow trace capture for the new purpose.
- [x] `backend/app/lab/context_study.py`: predeclared slots, immutable plan, per-slot integrity checks, retained invalid trials, action profiles, fixed decision rule.
- [x] `backend/app/lab/api.py`, `coordinator.py`, `exports.py`, `cli/client.py`, `scripts/run-context-study.sh`: routes, restart sweep, recording export and operator entry point.
- [x] Frontend `contextStudy.ts`, `ContextStudyPanel.tsx`, `EvidenceScreen.tsx`, arm allowlist and matrix label.

## Tests

- [x] `backend/tests/agents/test_actor_progress.py` — 15 cases: never-attempted vs attempted-unresolved, documented pre-acceptance rejection, adapter-synthesised failures excluded, stale reads against a terminal receipt, matching failed receipt, foreign receipt rejected, cross-episode identity, private-canary isolation, identical public history, non-mirror behaviour, v1 byte identity, protocol digests, worst-case admission.
- [x] `backend/tests/lab/test_context_study.py` — 6 cases: predeclared slots, decision rule including REGRESSION and INCOMPLETE, full offline run with verified evidence, no-change run, action profiles, refusal to restart or run concurrently.
- [x] `backend/tests/lab/test_configuration.py` — registration binds the exact protocol registry.
- [x] `frontend/tests/context-study.test.tsx` — grouping, 16 rejection cases, read-only render, incomplete-case notice, campaign switch, empty state.
- [x] Full `./scripts/test.sh` green on the frozen source: 544 backend, 121 frontend, build, 3 browser fixtures.
- [x] `backend/tests/lab/test_context_study.py` extended for the alternate protocol and its separate manifest identity.
- [x] `backend/tests/agents/test_actor_progress.py` extended: v3 withholds the block only on report-required turns.

## Live execution

- [x] Shared allowance reconciled against the saved budget records before dispatch: 1,109 requests and $23.81478 charged, $976.18522 remaining. Phase 1 campaigns confirmed to belong to the older separate allowance.
- [x] Source frozen (175 files), database snapshotted, backend restarted on the frozen source with the recorded live settings, for each study separately.
- [x] Study 1 `context-study-0aeffe8cdf1d4a0cbcca48f90dbc8a67` dispatched and finished: 60 trials, REGRESSION.
- [x] Predeclared follow-up written before any further paid call; study 2 `context-study-0fb80165ac9547e8b3836476081a3288` finished: 60 trials, REGRESSION.
- [x] Every attempted trial retained, including two untriggered ones. Nothing replayed or resampled.
- [x] Weave evidence verified for 120 of 120 episodes.
- [x] Frozen source re-hashed after each run: 0 of 175 files changed.

## Manual verification

- [x] Rebuilt the per-turn requests of sampled episodes in both arms from saved records; every turn reproduced the recorded `messages_hash`.
- [x] Read the raw turn-by-turn action history of the decisive episodes in both arms, including the untriggered control trial, the live `PENDING` invention and all five terminal-rejection violations.
- [x] Measured that the Actor reports before the reserved turn in most episodes, which is why the follow-up mitigation could not work.
- [x] Checked the dashboard panel, the campaign switch and the outcome matrix in a real browser.
- [x] Recorded results, cost, limitations and the exact remaining blocker in `PHASE4_RESULTS.md`.
- [x] Updated `memory/`, `CLAUDE.md` and this checklist.
