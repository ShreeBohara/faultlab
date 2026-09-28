# Product durability continuation — September 27, 2026

Read CURRENT_STATUS.md first. This supersedes the in-progress durability section of product-loop memory;
closed experiment evidence and protocol declarations remain unchanged.

The owner wants a complete dependable product and has authorized implementation, manual verification
and thoughtful use of generous time/budget. No GitHub push without OK. Preserve original work, secrets,
reports and pointers; actual `.env` was not read into chat or modified. Use the local Python 3.12 venv.

## Current implementation

All 59 checked durability files were integrated from
`/Users/shree/FaultLab_Worktrees/product-durability-2026-09-27` into the original FaultLab checkout.
Runtime `7dfdfe29fd210c70b5b83915f0cd47b144e03d49ffe172a9dfa722c50bd523f0`, algorithm
`9f82231e413124482ab8c07ffa6c2c322dee46e3343ee100c891f77eb2dcfbc4`, trace contract 2.
Original source is frozen as the completed durability checkpoint. See the durability review for behavior and limits.

Changes: coordinator OS ownership before SQLite/recovery; independent read-only query snapshots;
true archive mode; atomic terminal records/reservation release and nested savepoints; recovery of
queued/partial auxiliary work; protected capacity preserved; bounded backend operator routes and CLI
ownership; typed pre-dispatch input-limit diagnostics; explicit local paired launcher; archive/missing-ID
UI and honest partial fault coverage/trace status. No oracle, prompt, threshold or cap relaxation.

Frontend 206 tests/build/eight browser fixtures passed, one opt-in actual-server test skipped. Lifecycle
94 focused plus ten frozen workflow tests passed; operator group 75 passed. The first full backend run had 2,120 passes and three old restart fixtures that left the first owner
open. Test-only close/reopen fixes retain all assertions; 155 affected tests passed. Final full rerun
passed **2,123 tests, 180 existing skips, zero failures**, two warnings, 727.37 seconds, in
`full-backend-final.log`; the runtime did not change.
Actual archive checks retained all eight closed live DB hashes/mtimes and all 39 paid request records.
Actual fresh offline dashboard/launcher campaign `campaign-c664e786d0094561b0de8508bbd975c2`
completed one upgrade and one notification, eight checks, zero model calls. Independent raw-world audit
passed ten facts. Real process restart kept all 23 records/eight events/one pointer identical; second
coordinator refused; backend-owned registration passed. Owned services stopped.

Artifacts are consolidated in `artifacts/product-durability-2026-09-27/`. Manual fresh data remains
`/Users/shree/FaultLab_Runs/2026-09-27/product-durability/offline-01`. No control capability or `.env`
belongs in backups. The source/evidence checkpoint is recorded in `artifacts/product-durability-2026-09-27/final-checkpoint.json`;
verified external recovery copy `/Users/shree/FaultLab_Backups/2026-09-27/product-durability/`.

## Prior live result and accounting

Original live campaign `c701e850…` under runtime `60f27623…` is closed `NO_CHANGE`: seven completed,
zero violations, four full fault recipes/one partial/two absent, one duplicate decline. Status-read
faults were planned after successful terminal receipts; this is Explorer planning, not Actor or broker
misbehavior. 188 independent checks, 34 read-only remote reads passed. No accepted candidate.
Its 39 requests cost $1.04662 conservative, $1.05 carried; token-priced estimate $0.15324862;
actual billing unknown. Carried total **$856.96**, durability $0. No new inference planned merely to
seek a successful repair. `docs/PRODUCT_LOOP_RESULTS_2026-09-27.md` is the closed result.

Prior checkpoint `e10113671919187edce88e6017b0de33fb349791`; external loop backup
`/Users/shree/FaultLab_Backups/2026-09-27/product-loop/` has 528 verified files and source bundle.
Main stays `cbbf957e6e1cb19e1dcc2f87f24a33101859bbbe`; logical index SHA256
`34a77879bf2b787ace8cfc9cccf85972552028f4c617db4ad216072b16e9062f`.
Use the existing temporary-index commit helper for explicit files on `backup/part2-2026-09-22`;
never stage all, move main, reset or push. Historical main DB SHA256 remains
`0cefee1595dd6d7e29ff6258b16cff6d9313198808f225e4a403d69a0721f0c7`.

## Next increment in progress in the isolated checkout

Make supported-agent selection real through ordinary campaigns and clearly state the one supported task.
The existing native smolagents adapter is reviewed/pinned and has earlier native baseline evidence;
it is not wired into ordinary Learn. Carry immutable registration and target configuration through every
phase, never merely relabel reference runs. Backend registration now exists, superseding those missing
registration claims in the earlier read-only onboarding-review artifact. Agent preview must be provider-free
and separate installed-source conformance from live access or measured success.

Expose express upgrade/confirmation as the supported task, label the instruction textbox accordingly,
allow named public development baseline cases without exposing protected plans, and freeze the previewed
plan at creation. Add campaign recording download for NO_CHANGE. A second task requires separate typed
semantics/tools/fault targets/private checks and scope compatibility, not a different textbox string.
Bundle preview/import can follow this small coherent onboarding increment.

Outstanding proof remains generated original acceptance, unseen validation and accepted-policy transfer.
Reference accepted/rejected/interrupted fixtures establish plumbing only. Current local operation is
single-writer POSIX, not multi-user/distributed. Six frozen historical scripts bypass the product lease;
do not use them concurrently on an active store. No global installs; investigate a project-local SQLite
upgrade separately if expanded concurrency needs it.

The isolated checkout is reused for onboarding only; do not overwrite the verified original source until
that increment is frozen/tested/integrated. A source baseline is saved at
`artifacts/product-onboarding-2026-09-27/before-source.json` there. New API-local RunPlanRequest keeps the
exported CampaignRequest and contract/scorer/capability hashes unchanged. Planned endpoints: GET run-options
without constructing a coordinator; POST planned-campaigns; GET campaigns/{id}/plan. WORLD owns plan
validation/catalog, LOOP owns real selected-actor dispatch/all phase attribution, UI owns setup/frozen
plan/recording download, lead owns API/main/exports/integration. No new paid calls.
