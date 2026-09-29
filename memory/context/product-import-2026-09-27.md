# Product import continuation — September 27, 2026

## Later on September 28 (read this before the status below)

The runtime and test counts below are **historical**. Later work changed the runtime four times
(`cfe5ac07` → `bb87c764` hardening, which changed the simulator identity → `9f53eb8c` discovery v2 →
`c9b1b7e6` review fixes → `c0a8aad7`, the PM decision that restored `simulator/main.py` to its `8e497da`
bytes, so the simulator identity is the checkpoint's again: service `3ce5bcd2…`, contract `6f9d7783…`).
Before the paid validation: register the targets again under the current runtime (registrations record
the whole-backend runtime hash) and use the restored fixture `frontend/tests/fixtures/exported-regression.zip`
(sha256 `14e53310…`, its checkpoint bytes). The regenerated `f2ac6a60…` copy is now
`exported-regression-other-simulator.zip`, kept only to test the refusal of a different simulator build.
Current runtime, counts and consequences: `CURRENT_STATUS.md`, *Current runtime* and *Verification and
known issues*.

## Status on September 28, 2026 (read this first)

The feature is complete in the main folder (`faultlab/`), not only in the product worktree. Backend
(`backend/app/lab/bundle_imports.py` and admission guards) and frontend (`BundleImports.tsx`,
`ImportedTrialEvidence.tsx`, `bundleImports.ts`) were integrated on September 28, then reviewed by three
independent $0 reviews (security, semantics, first-time use). Every finding was fixed; see *Review fixes*
in `docs/PRODUCT_IMPORT_REVIEW_2026-09-27.md`. Runtime after the fixes: `cfe5ac07c6ef571f7be5f57cc8f56cbce4084496c3d157d3b222c0e9bb0f6738`. Tests after the fixes:
Full backend **2,363 passed, 180 existing skips, zero failures** (two known warnings); frontend **254 unit tests, production build and 13 browser fixtures passed** (one opt-in actual-backend check skipped). Nothing is committed yet (the PM commits); main HEAD and index unchanged; no push. Provider
calls: 0; cost $0. Remaining: the owner-declared paid validation (choose the 72-request worst case or
FAULTLAB_MODEL_CALL_CAP=24 per execution, see the review doc), then clean-install validation, a second task
and useful generated repair evidence. The worktree copies of the docs are stale; use the main folder.
The sections below are the September 27 working notes, kept as history.

User approved completing dashboard import → review → rerun, followed by carefully declared real-model
validation. Whole-product completion remains open: clean-install validation, a second task and useful
generated repair evidence are separate remaining milestones. No GitHub push without the owner’s OK.

Starting runtime: `d1845765fa1c120ad4afd936461ddb4e4d909972209b160d6eebd63d6b3c64fb`.
Prior source checkpoint: `5447816cea31fbf98e545147c32a0e3bd36c1fd6`.
Main HEAD and index unchanged. New source baseline (283 files, original/worktree bytes equal):
`artifacts/product-import-2026-09-27/before-source.json` in both trees.

Reuse `/Users/shree/FaultLab_Worktrees/product-durability-2026-09-27`; do not reset its earlier uncommitted
work. LOOP owns backend lab, UI owns frontend, WORLD audits independently. Original docs are current;
worktree docs are stale. Integrate only reviewed source using the saved baseline guard.

Observed gap: `/api/regressions/import-and-execute` is an atomic user action that validates/imports then
queues paid execution. Dashboard only loads existing campaign bundles. Existing downloadable bundles
are ZIP files containing a strict manifest and seven/eight payload files. Keep the trusted static runner;
never execute uploaded code. Existing development recordings are evidence JSON, not runnable bundles.
Imported historical evidence is not verified locally. Import must not activate policy. Fresh executions
must retain exact target registration/configuration, distinct from their legacy reference budget owner.

Current increment provider calls: 0; cost: $0. Historical carried conservative total: $856.96.
Closed live studies remain closed and all historical reports/databases/secrets must remain unchanged.

## Work in progress: independent audit

WORLD reproduced a fixed-runner bug in six coherent offline callback fixtures: a returned TrialResult
could contradict the saved Episode (lifecycle, outcome, checks, usage, scenario or private recipe), yet
RegressionRunner recorded COMPLETED/reproduced. LEAD strengthened the fixed runner to compare typed
saved episode/verdict/recipe/fixture/arm/index/model/fault exposure before interpreting the returned
summary. Contradictions stop after the retained first attempt and are lab integrity errors, never agent
violations. Replay cannot count as fresh. Charges remain conservative; known-cost fresh aggregation
starts from zero and unknown costs stay unknown. Existing minimal integration fixtures now save coherent
typed episodes instead of bypassing that boundary. Focused integrations: 23 passed; independent WORLD
suite: 15 passed (includes known/unknown cost, missing/partial fault ledger, replay and identity cases).
Runtime is not frozen yet; LOOP/UI still implementing.

New input ZIPs: `artifacts/product-import-2026-09-27/manual-inputs/` contains exact preserved native offline
incident bundle96f072 and incompatible old genuine live bundle, with source-provenance.json. Source bundle
has 16 scripted offline episodes, F2 update delay2 seed27, baseline C3 incident; it is not live evidence.
The original main store’s six old live bundles are incompatible schema/interpreter snapshots. Do not
rehash/relabel them. WORLD verified its SHA+mtime unchanged after read-only audit.

One read-only model-list request confirmed DeepSeek V3.1 availability. W&B official pricing was checked
at https://wandb.ai/site/pricing/inference/?q=tables ($0.55/$1.65 per million input/output tokens).
No generations yet. See `provider-readiness.json`. The live verification design in
`docs/PRODUCT_IMPORT_REVIEW_2026-09-27.md` is prospective only; exact freeze/declaration still required.
