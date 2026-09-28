# Supported campaign onboarding — September 27, 2026

Read CURRENT_STATUS.md first. Source is integrated in the original checkout:
`/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`.
Runtime `d1845765fa1c120ad4afd936461ddb4e4d909972209b160d6eebd63d6b3c64fb`, algorithm
`17ebd3e6e1adfea5dcb43616e2ce402d20d1429a4403e3b0414f73866a4a1881`, trace contract 2.
All 49 changed source/test files were checked against the saved before-source hashes before copying.
Main remains cbbf957e6e1cb19e1dcc2f87f24a33101859bbbe; logical index hash remains
34a77879bf2b787ace8cfc9cccf85972552028f4c617db4ad216072b16e9062f. No push.
The reused isolated checkout retains all its work; do not reset or delete it.

## Implementation and contracts

API-local RunPlanRequest/SavedRunPlan in app/lab/run_plans.py; exported task/scorer/service/capability
and dependency identities remain unchanged. GET /api/run-options reads settings and an optional
read-only snapshot, without coordinator construction, DB initialization, registration or providers.
Explicit registration, POST /api/planned-campaigns, GET /campaigns/{id}/plan and separate Start implement
reviewed setup. Store/setup/current registration/Compare eligibility are checked before lazy writer
construction and again inside the create transaction. Heavy setup work stays off the scheduler loop.

Plans bind task/order/instructions, selected configuration and registration, recipe/fixture or search/
partition identity, initial policy, limits and digest. Provenance marks the plan. Missing/corrupt marked
plans fail closed; completely unmarked campaigns retain legacy behavior. Archive reads check saved
bindings, not today's installed source. B0/L use the selected reviewed native/reference actor throughout
the original loop. B1 is explicitly a deterministic reference control, never a mislabeled native trial.
Bound regression/portability targets and declared reference-context study overrides have narrow paths.
Native reference-only context/completion/dependent heldout studies are refused before execution.

Native source conformance is not behavioral proof. Wrong returned models, swallowed provider errors,
unknown costs and charged-but-cancelled requests now preserve honest infrastructure status/accounting.
No native prompt, package, report repair, inference retry, scorer or budget change. Internal
EpisodeRunner(offline_fixture=True) supports honest scripted-provider integration fixtures; production
coordinator/API never enable it. Native audit-freeze validates its plan; same-implementation portability
fails before freezing/reservation/world dispatch. Import execution remains a separate target execution
with a legacy reference budget-owner campaign; do not present that owner as the native trial identity.

Dashboard: explicit agent/task/public case choices, registration, Create→frozen plan→Start, legacy plan
explanation, public recording download (including NO_CHANGE), and live current status overlay for the
matching history entry. Pagination/manual refresh are preserved. Public recordings include campaign,
configuration, registration, plan and development evidence; protected trials/private worlds are excluded.

## Verification and evidence

Full backend final invocation in original PASSED: 2,224 passed, 180 existing skips, zero failures,
2 warnings,791.81 seconds. See artifacts/product-onboarding-2026-09-27/full-backend-final.log.
Runtime identity is unchanged before/after the complete invocation. Warnings are the existing
Starlette alias and explicit POSIX fork ownership test.
Focused: 55 API/plan/archive, 48 selected/native/legacy-loop, 30 native provider/package and 66 freeze/
portability/operator/recovery tests pass (groups overlap). Actor-context fixture 21 pass.
Frontend 219 unit tests, production build and 10 browser fixtures pass; one actual-backend opt-in skipped.
Original checkout build also passes; size advisory 502.10 kB minified / 118.64 kB gzip, no dependency changes.

The isolated full attempt was interrupted after missing historical fixture/settings/freeze files caused
errors. Its log is isolated-full-backend-incomplete.log. Five context tests used invalid Campaign stubs;
replaced with real Campaign objects, preserving all early/no-world assertions. The new independence
guard exposed an old positive portability fixture that used the same source/target; its target is now
the real reviewed smolagents registration. Original failures remain in diagnostic logs.

Fresh native scripted fixtures at 763b80d636b82e48b98f73aba038a8a8ea90da154aa20ee172725eae04952856:
153 worlds, 2,324 independent raw SQL comparisons passed, unchanged files. Accepted plus comparison 124 worlds,
rejected 28, interrupted 1. Candidate 45 COMPLETED + 6 CORRECTLY_REJECTED; baseline/rejected C3 failures match
actual premature notifications. No lab discrepancy. This is scripted plumbing, not generated acceptance.
Earlier306e and 22360 fixture identities remain separate and unmodified. Final source differs from 763b
only by reviewed native freeze/independence guards, with dedicated positives and negatives.

Actual UI created/reviewed IDLE/started all six public cases in
/Users/shree/FaultLab_Runs/2026-09-27/product-onboarding/offline-01 (763b runtime). Five completed, dev-5
correctly rejected; all five scheduled recipes fired. Independent manual 160 checks passed. B1 returns its
TaskReport directly and has no model/report_submitted event; physical effects, receipts and exact
citations establish this deterministic control's report truth. Initial audit's wrong event assumption
is preserved and explained. Real process restart preserved 138 records, 64 events, six pointers and six recordings.
Actual browser-downloaded JSON equals public API recording; CUA download wait timed out despite file
creation (tool observation issue). No data was rerun to improve a result.

Final integrated d184 source manually created and ran campaign85a1e48f1b7d4392bdd5e3d5876374bd in
/Users/shree/FaultLab_Runs/2026-09-27/product-onboarding/final-runtime-01. Dev6 completed, two transient
notification failures, one upgrade and one confirmation, zero model calls.13 direct checks passed;
CLI audit freeze succeeded without execution. Archive under final source opened all older six-case
plans; recording identical, Start returned 409 READ_ONLY_ARCHIVE, seven DB hashes/mtimes unchanged.
Screenshots final-runtime-summary.png and final-archive.png show actual app results.
Owned backend/simulator/Vite services stopped and temporary browser tab closed; ports 8000/8001/5173 free.

## Preservation, spending and continuation

All 31 historical result reports, 901 MB main DB and eight closed live databases match the completed durability
checkpoint. Original runtime history and secrets are untouched. Evidence copied from isolated with
1,689 verified files / 151,267,249 bytes, excluding capabilities/pycache/SQLite sidecars. Final source/evidence
checkpoint helper is artifacts/product-onboarding-2026-09-27/checkpoint.py. The complete passing suite, final documents and source identity are verified; the helper creates the
local source/evidence checkpoint. It uses the explicit-path backup
helper, preserves main/index and creates /Users/shree/FaultLab_Backups/2026-09-27/product-onboarding/.
Read final-checkpoint.json for actual source commit and backup manifest; do not print its full file list.
Prior durable recovery remains /Users/shree/FaultLab_Backups/2026-09-27/product-durability/ at 63543ee….

New provider requests / cost: zero; conservative carried spending: $856.96. Provider-billed historical amount
unknown. Closed live original campaign c701e850… remains NO_CHANGE at 60f27623…; never resume/repin it.
This remains one synthetic task and two reviewed agents. Broader import UI/task extension, generated
original-loop acceptance, unseen success and accepted-policy transfer are not established by these
fixtures. Do not rerun old partitions or weaken gates to manufacture success. Continue from actual
code/evidence, keep status current, preserve all histories and never push without owner's OK.
