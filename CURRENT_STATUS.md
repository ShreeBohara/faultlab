# FaultLab — current status

Updated **September 27, 2026**. This is the single current status and continuation page.
README, AGENTS, CLAUDE and memory entry points refer here. Historical reports describe
their own frozen experiments; their settings, budgets and next steps are not current instructions.

## Current work

**Current priority: complete and improve a dependable product.** The owner clarified that they meant
“enhance,” not “announce.” The completed Phase 31 write-up/demo is a saved asset, not the end of the
project. Finishing Claude's experiment program did not establish full product acceptance.

Continue to use the milestones below as hypotheses, not a fixed script. Exercise independent
architectural judgment and verify manually as well as with tests. Time and budget are generous;
the old allowance is historical accounting, not a renewed limit.

**Core reliability fixes are implemented.** The complete original workflow was traced in source.
Candidate violations now survive opposite-arm infrastructure retries; invalid simulator clocks are
classified as lab errors; new heldout plans apply the same boundary without rewriting old protocols.
Stop affects only owned active work, partial evaluations survive interruption, restart preserves
charges and releases abandoned reservations, and cleanup cannot strand the scheduler. Saved reads
run outside its event loop. Campaign and saved regression execution history now have bounded selectors;
provider-free readiness explains which local settings/services are missing.

Final verification passed against runtime
`58cd13b6f966d5b1c789fde7de9ca4bbdf744b2335bca25d9f3930e57e14f357`.
Frontend: **192 tests, production build and six browser checks passed** (one opt-in server test skipped).
Heldout/world integration: **104 passed**. A fresh dashboard reference run completed with one actual
upgrade, one confirmation, all eight checks and zero model calls; direct world reconstruction agrees.
The dashboard reopened five saved executions and an original trial from a read-only historical copy,
without executing anything. Full backend: **2,010 passed, 180 existing skips, zero failures**, one
dependency warning, in 714.97 seconds. The verified local source/evidence checkpoint is recorded in
`artifacts/product-core-2026-09-27/final-checkpoint.json`; its external recovery copy is
`/Users/shree/FaultLab_Backups/2026-09-27/product-core/`.

**New spending: $0; carried historical accounting: $855.91.** No GitHub push. No historical verdict,
active pointer or result report was changed. This work establishes specific product correctness and
usability improvements, not a generated accepted policy, successful unseen validation, repaired-policy
transfer or a second task. Those product milestones remain open.

The [product workflow audit](docs/PRODUCT_CORE_REVIEW_2026-09-27.md) records the trace, decisions and
verification. [Current implementation memory](memory/context/product-core-2026-09-27.md) supersedes
the earlier [continuation notes](memory/context/product-continuation-2026-09-27.md) for this work.

### Phase 31 and report-finalization follow-up

The owner authorized the recommended write-up/demo and focused offline follow-up. No new paid
experiment is planned in this round; the latest reserved result remains INCOMPLETE.

- [x] Prepare the [Phase 31 write-up](docs/part2/PHASE31_WRITEUP.md) and
  [four-minute demo guide](docs/part2/PHASE31_DEMO_GUIDE.md), with separate development,
  reserved-evaluation and active-policy claims.
- [x] Investigate repeated notification polling. [Review](docs/part2/NOTIFICATION_PROGRESS_REVIEW_2026-09-27.md)
  confirms the older v2/v3 progress summaries already regressed. Keep v4; do not add a duplicate v5.
- [x] Implement a narrow final-report hook fix and precise diagnostics; independently review guard,
  citation, stop and budget behavior. Preserve the captured original development failure as a fixture.
- [x] Verify the fix with 45 focused checks and a fresh offline world reconstruction, comparing the
  original and corrected modules with the same captured answers. The correct result is SAFE_UNRESOLVED,
  with no extra business effects. [Fix and evidence](docs/part2/REPORT_FINALIZATION_FIX_2026-09-27.md).
- [x] Rehearse the saved-evidence dashboard using an isolated copy; provider calls disabled and writes
  rejected. Verify the original trial pair, all eight checks and retained baseline. Clarify one misleading
  main-loop sentence; 166 frontend checks and the production build pass after that text change.
- [x] Record the new runtime and complete one clean backend invocation: **1,952 passed, 180 existing
  skips, zero failures**, one dependency warning, in 697.17 seconds. Preserve the earlier cloud-read
  failures separately. Save code, documents and diagnostic evidence on the local backup branch and
  in `/Users/shree/FaultLab_Backups/2026-09-27/phase31-followup/`; no push.

Runtime of that completed follow-up: `b9410f5e77f2b98e6a621ee5adabc20c7ac65ea042f8a9d7049dedadaec7d719`.
The quoted live results still use `3da193e3…`; this offline correction is not a new live result.
Some Desktop source/dependency files became iCloud placeholders. The runtime and main database
are now readable; all 241,000 main-store records and 142,417 events match the preserved backup.
Unavailable originals have not been replaced. The source/evidence backups outside Desktop remain
the recovery copies. Keep the project downloaded before using it; do not treat file existence alone
as evidence that a cloud-backed database or dependency can be read.

- [x] Establish this status page and replace conflicting continuation pointers; preserve old notes.
- [x] Fix successful replay parsing and verify a real saved replay in the dashboard.
- [x] Decode Actor citations using the evidence available when the model was called, before report hooks.
- [x] Repair or correctly scope the two failing historical research tests.
- [x] Make normal app defaults use the tested model/context settings, preserving explicit historical versions.
- [x] Show development qualification, unseen-case results and the active policy separately.
- [x] Complete offline checks, manual saved-evidence verification and documentation of the new runtime.

### September 27 follow-up

- [x] Save the consolidation and Claude's existing report correction on the local backup branch
  (`52ee801`); preserve `main`, the real index, historical evidence and `.env`.
- [x] Obtain one clean, complete backend-suite result after the test corrections:
  **1,891 passed, 180 skipped, zero failures** in 712.56 seconds.
- [x] Verify exact model availability and published prices; prepare non-secret process settings.
- [x] Close the dashboard and stop its server and the idle backend before paid execution.
- [x] Freeze and execute the first separate public compatibility check. It stopped on HTTP 503
  after 16 attempted episodes: 15 completed with verified traces, 26 never attempted. Its status
  remains **INCOMPLETE**; original protocol, sealed plan, results and costs remain preserved.
- [x] Independently reconstruct those 16 worlds, actual effects, original answers, request identities
  and the 15 saved Weave readbacks; no mismatches found. The baseline remains active.
- [x] Add one bounded, charged retry for HTTP 503 with no returned generation; 66 focused checks
  passed and independent code review cleared the change. Returned answers are never re-rolled.
- [x] Complete the full backend suite again: **1,920 passed, 180 skipped, zero failures**.
- [x] Execute the sealed [service-reliability check](docs/part2/SERVICE_RELIABILITY_CHECK_2026-09-27.md)
  once: **42/42 episodes**, **36/36 faults triggered**, **42 verified Weave readbacks**;
  the saved repair completed **15/21 tasks**, versus **9/21** for the baseline, with zero violations.
  New runtime `3da193e3…`; separate store, same fixed policy and known public cases.
- [x] Finish the independent post-run reconstruction: all 42 worlds/reports/readbacks, 262 HTTP
  attempt identities, 66 operation journals and 336 rule checks agree. Save the final local checkpoint.
  [Full current review and results](docs/part2/CURRENT_REVIEW_2026-09-27.md) records both executions
  separately, manual findings, pricing, current spending and the recommended next experiment.

### Fresh repair experiment — execution and verification finished

The owner authorized a fresh repair-generation experiment followed by one reserved-case
evaluation on September 27. [Prospective declaration](docs/part2/PROSPECTIVE_REPAIR_2026-09-27.md).
This extends the evidence beyond Claude's original Phase 31 write-up/demo; it does not
reopen Phase 28 or activate a policy. The sealed run finished and must not be resumed or
rerun. [Full result and manual findings](docs/part2/PROSPECTIVE_REPAIR_RESULTS_2026-09-27.md).

- [x] Declare up to ten development attempts; select the first strongly qualified new saved-policy hash.
- [x] Separate $100 generation and $60 evaluation pools, within the remaining $181.77.
- [x] Finish independent review and 102 offline checks; reserve three unexposed combinations and seal
  all inputs before generation. Frozen configuration `88e97d68…`; same tested application runtime.
- [x] Execute ten development studies / 162 episodes; the tenth produced the first new strongly
  qualified policy. Its development validation completed **15/21 versus 9/21**, with zero violations.
- [x] Execute all **156 reserved evaluation episodes** once. Formal result **INCOMPLETE**: one baseline
  episode never attempted its notification, so one scheduled fault could not fire. Candidate had
  **zero violations**, baseline one C5 report-label violation. No policy was activated.
- [x] Independently reconstruct all **318 worlds**, 2,544 checks, 1,996 HTTP attempts, 452 journals,
  315 filed reports and 318 saved readbacks; verify three episodes again directly in Weave.
- [x] Reconcile **1,783 requests / $37.68 carried cost**; preserve source, historical results,
  active baseline pointers and the main evidence store. Stop the simulator and other local servers.
- [x] Save all 318 worlds, all 11 stores, preparation/audit evidence and source locally; verify the backup manifest.

**Decision:** do not perform the suggested immediate “Phase 28 unseen-case check.” The frozen Phase 28
protocol explicitly disallows that routing. The old unseen-case generator also excludes notification
development cases but not `upgrade-v1`, so a different seed could repeat known upgrade faults. Instead,
the completed measurement compared the first strongly qualified Phase 28 policy and the empty baseline on
the seven already-public upgrade cases: 21 pairs / 42 episodes, under the corrected runtime, with a
$20 cap. It cannot establish new learning, unseen generalization, certification or policy acceptance.
The subsequent prospective experiment reserved new combinations before generating candidates,
then qualified and evaluated under one frozen runtime. Its coverage gate returned INCOMPLETE;
it does not establish an unseen-case pass. That partition is now spent.

Changes to runtime code produce a **new runtime identity**. They do not rewrite, resume or repin
closed Phase 17–30 experiments. The Phase 30 report-status hint remains experimental and is not adopted.

## What is established

FaultLab tests one task: upgrade an order in a synthetic shop and send one truthful confirmation.
The Actor performs the task; a Mechanic proposes bounded recovery rules; a fixed Referee checks
the outcome. The original discovery workflow also has an Explorer, reproduction, diagnosis,
challenge and promotion. A separate completion study uses a chosen failure case and never promotes.

| Evidence | Established result | Limit |
|---|---|---|
| Phase 17 | 1 development-certified repair attempt out of 9 | Separate completion experiment, not original promotion |
| Phase 23 | 3 out of 30, three notification-side policies | One routed policy subsequently failed its unseen-case check |
| Phase 28 | **9 out of 49; eight distinct upgrade-side policies** | Development cases only; no unseen-case evaluation of these policies |
| September 27 compatibility check | Saved repair **15/21 completed**, baseline **9/21**, zero violations across 42 episodes | One existing policy on known public cases; no new qualification or acceptance |
| September 27 fresh repair experiment | **1 of 10 studies qualified**; 15/21 versus 9/21 on development validation | Bounded first-success search; not an unbiased repair-rate estimate |
| September 27 reserved evaluation | All **156 episodes** ran; candidate zero violations, baseline one | **INCOMPLETE** because one baseline fault did not trigger; no NO_HARM claim |
| Original policy acceptance | **Zero generated ACCEPTED policies** | All recorded active pointers remain `policy-v0` |
| Native smolagents | Live independent-agent baseline already completed in Phase 1 | Same shop; accepted-repair transfer remains unproven |

Phase 28 retained **1,104 scored trials**, all 885 scheduled faults triggered, all 1,104 saved
Weave readbacks verified, and no detected clock drift or missing worlds. Its selected certified
policies had no failed checks in 216 trials. The whole experiment retained 22 violating trials
across baseline and unsuccessful candidates. It stopped normally at its spending guard after
49 of 50 planned attempts. Its success rate is a repair-attempt yield, not general agent accuracy.

The executed Phase 28 path was **chosen source → baseline controls → Mechanic proposal → source
tests → development validation**. It did not invoke the Explorer, generated challenges or original
promotion. The primary report's earlier Explorer wording was corrected by Claude before this work.
See the new [clarification note](docs/part2/STATUS_NOTES_2026-09-27.md); no historical results are
edited by this consolidation.

“Development qualified” means the stated development requirement passed. “Unseen-case result”
is a separate frozen-policy evaluation. “Active policy” is what the campaign actually uses.
None implies either of the others. Completion studies cannot activate a policy. Earlier unseen-case
checks returned HARM; the Phase 24 failure was an unsupported PENDING report after UNKNOWN
observations. That verdict stands; it does not by itself prove causal harm. Tested partitions are spent.

The shop, fixed checks, repeated trials, incident export, fresh regression execution and evidence
storage work. A second task environment, general agent onboarding, successful repair validation on reserved unseen cases and a shared hosted product are not established.

## Evidence and reading order

1. [Product workflow review](docs/PRODUCT_CORE_REVIEW_2026-09-27.md) and
   [current implementation memory](memory/context/product-core-2026-09-27.md): implemented core fixes,
   final verification and open product milestones. The original continuation notes remain historical context.
2. [Offline report-finalization correction](docs/part2/REPORT_FINALIZATION_FIX_2026-09-27.md).
3. [Latest fresh repair and reserved-case results](docs/part2/PROSPECTIVE_REPAIR_RESULTS_2026-09-27.md).
4. [September 27 earlier review and compatibility results](docs/part2/CURRENT_REVIEW_2026-09-27.md).
5. [Historical repair-generation result: Phase 28](docs/part2/PHASE28_RESULTS.md) and its
   [declared protocol](docs/part2/PHASE28_EXPERIMENT.md).
6. [Phase 24 unseen-case result](docs/part2/PHASE24_RESULTS.md).
7. [Phase 30 narrow reporting probe](docs/part2/PHASE30_RESULTS.md): recommended for a later experiment,
   not adopted and not an end-to-end result.
8. [Phase 1 results](docs/part2/PHASE1_RESULTS.md): native agent, incident export and regression evidence.
9. [Original month plan](docs/part2/PLAN.md): a historical roadmap, not a completed-feature list.
10. [Phase 31 write-up](docs/part2/PHASE31_WRITEUP.md) and [demo guide](docs/part2/PHASE31_DEMO_GUIDE.md):
    completed communication assets, not a declaration that the product is finished.
11. [Preserved handoff notes](memory/history/2026-09-27-before-consolidation/README.md) for detailed history.

The original [specification checklist](../FaultLab_Specs/specs/001-faultlab-loop/tasks.md)
ends at Phase 15: 234/239 checked. This is not a product completion percentage. T065, T088,
T097, T100 and T102 remain open: original learning/promotion evidence, complete sponsor/Aria
walkthrough, final freeze, independent transfer/selector acceptance, and the complete final audit.
Do not check those off because completion studies or software tests pass.

## Configuration and execution

- App root: `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`.
- Specs root: sibling `FaultLab_Specs/` (outside the application Git repository).
- Latest tested Actor: `deepseek-ai/DeepSeek-V3.1`.
- Latest tested Mechanic and configured Explorer: `deepseek-ai/DeepSeek-V4-Pro-0813`.
- Latest tested Actor context: `faultlab-actor-context/v4-indexed-evidence`.
- Confirmed W&B destination: `shreetbohara-quinstreet/Faultlab` (capital F).
- Credentials remain in the existing `.env`; do not print, copy into docs, overwrite or commit it.
- Aria remains deferred. Starting servers, viewing evidence and offline tests must not make provider calls.
- Both launchers use the same application model/context defaults. Nonempty `.env` values and explicit
  process overrides win; empty model placeholders in old `.env` templates adopt the defaults without
  editing the file. An explicitly blank process model override is still respected.
- New campaign configuration freezes the selected Actor context. Explicit study overrides remain valid;
  historical snapshots without that field retain v1. This does not bypass runtime compatibility checks.
- Startup remains offline by default and Aria is off. The live launcher does not supply historical prices
  or mark them verified; exact-model pricing must be configured before a paid campaign can be admitted.
- Completion studies already default to the tested v2 task-outcome evidence summary. Their ordinary
  case manifest remains `notification-v1`; Phase 28 explicitly chose `upgrade-v1`. Selecting the same
  models is not a replay of Phase 28 or evidence of a new successful experiment.
- Backend `http://127.0.0.1:8000`; simulator `http://127.0.0.1:8001`; dashboard
  `http://127.0.0.1:5173`. Open the dashboard URL, not `frontend/index.html` as a file.
- Start commands and offline verification: [setup](docs/setup.md) and [user guide](docs/user-guide.md).

The idle backend and dashboard were used for the saved-evidence verification, then stopped during
this follow-up. The owned simulator is also stopped after verification. A live model-catalog check verified both selected IDs
without generation. Both compatibility checks used their own stores and explicitly declared their
new runtimes; historical campaigns are read-only. Recheck processes before starting or stopping services.

## Budget

The carried historical accounting is **$855.91 conservatively charged**. Under the previously recorded
$1,000 allowance, that leaves **$144.09** mathematically. The owner has since reported adding more
than $1,000 and repeatedly authorized further work with generous resources: **$144.09 is not a newly
imposed limit for the remaining project**. The actual provider balance and billed cost are unavailable;
do not invent either, reset prior charges or interpret generous resources as permission for unbounded
unattended spending. Declare and monitor the next experiment's allocation and verify its exact prices.

The ledger begins with Phase 2; changing accounts, agents or machines does not reset it.
Before this follow-up, the non-overlapping historical ledger summed to $811.39726
and its carried figure was $811.70, conservatively higher due to an old probe double-count and rounding.
That difference was not reclaimed. See the
[preserved ledger](memory/history/2026-09-27-before-consolidation/memory/context/runtime-and-evidence.md).

The original consolidation made no paid calls. The first separate compatibility check charged
81 model requests / $1.6929 upper bound, carried as $1.70. The complete follow-up charged
231 requests / $4.8279 upper bound, carried as $4.83. Together: **312 requests / $6.5208**, carried as
**$6.53**. Both costs remain recorded separately; incomplete runs are not erased or refunded in this ledger.
That earlier machine-readable accounting remains at
`artifacts/verification-2026-09-27/followup-budget-ledger.json`.

The fresh repair experiment added **978 development requests / $20.84536** and **805 evaluation
requests / $16.82450**, conservatively carried as $20.85 + $16.83 = **$37.68**. Total new requests:
1,783. The current ledger is `artifacts/prospective-repair-prep-2026-09-27/final-budget-ledger.json`;
the independent accounting audit records all 11 stores. The INCOMPLETE evaluation is fully charged.

The owner reported adding more than $1,000 and authorized further work. This is not a verified provider
balance and does not erase prior charges. All three bounded experiments fit the existing allowance. Exact model
prices and the required non-secret process settings are documented in the
[current review](docs/part2/CURRENT_REVIEW_2026-09-27.md#exact-model-pricing-and-admission).

## Source and backups

Latest product reliability work is saved on local `backup/part2-2026-09-22`; exact commit, unchanged
main/index, and complete saved-tree verification are in
`artifacts/product-core-2026-09-27/final-checkpoint.json`. The external `product-core/` recovery copy
contains a self-contained source bundle, new diagnostic stores/worlds, manual screenshots, full check
logs, current notes and a verified hash manifest. Historical evidence backups below remain intact.
No GitHub push was made. Do not reset or stage everything relative to the intentionally old main.

At the September 27 audit, local `main` and GitHub `main` were at `cbbf957` (September 14).
Local `backup/part2-2026-09-22` was at `7c36110` (September 26), 22 commits ahead. All 585
files in that backup matched the working folder before Claude's later wording correction and this
implementation. Current edits are therefore additional local work; do not reset the working tree.
Recheck Git state before publishing. This work does not push or merge branches.
The September 27 consolidation is saved on that local backup branch at `52ee801`; the reviewed
replication runner and declaration are saved at `deff0b1`; the bounded 503 fix and follow-up declaration
are saved at `e38f7db`. The final results are saved on the same local backup branch. `main` and GitHub
were not moved.
The fresh experiment's sealed source and offline tests are saved at `7000ced`; its results and current
status are saved in the subsequent local checkpoint. No GitHub push was made.
The Phase 31 report-finalization code/tests and dashboard wording are saved locally at `0eb7da7`;
the completed write-up, demo and validation record are saved in the following checkpoint on the
same backup branch. `artifacts/phase31-followup-2026-09-27/final-checkpoint.json` records the exact
final commit and verifies every saved source file against the working folder. Main and its index
remain unchanged. The separate `phase31-followup/` backup contains a complete source bundle,
both diagnostic worlds, review records, logs, a demo screenshot and a verified file manifest.

Ignored `artifacts/` contains roughly 4.5 GB of databases, worlds and evidence. A source clone does
not carry it. `/Users/shree/FaultLab_Backups/2026-09-26/lab-after-phase28.sqlite3` matches the
campaign, episode, policy, verdict and evidence records checked in the main store at audit time.
Keep local world files and frozen configurations with the database. The temporary Phase 28 worktree
is an older preparation copy; do not use it as the latest implementation.
Both September 27 experiment stores, all 58 new world databases and their verification files have
byte-verified copies at `/Users/shree/FaultLab_Backups/2026-09-27/followup-verification/`.
Its `MANIFEST.json` records every copied file hash; it contains no credentials.
The fresh repair experiment has a separate verified backup at
`/Users/shree/FaultLab_Backups/2026-09-27/prospective-repair/`, including all 318 worlds, 11 stores,
commitments, independent audits, current reports and a self-contained source bundle.
Its manifests record copied file hashes; credentials and SQLite transient sidecars are excluded.

## Verification and known issues

**Current runtime `58cd13b6…`:** one complete backend invocation passed **2,010 tests**, with
**180 existing skips**, zero failures and one dependency deprecation warning, in 714.97 seconds.
[Full log](artifacts/product-core-2026-09-27/full-backend.log) and
[result](artifacts/product-core-2026-09-27/full-backend-result.json). Frontend **192 tests and build
passed**; **six browser checks passed**, one opt-in server check skipped. Manual real-server work ran
separately: fresh reference smoke, direct world reconstruction, bounded campaign navigation, readiness
and saved regression/trial reopening. All used isolated stores and zero provider calls.
[Product review](docs/PRODUCT_CORE_REVIEW_2026-09-27.md) distinguishes fixture gates, actual local worlds,
copied historical evidence and unproven live repair claims. All 31 historical result documents and
the main database's complete hash are unchanged. Temporary services are stopped.

**Previous offline runtime `b9410f5e…`:** one complete backend run passed **1,952 tests**, with **180 existing
skips**, zero failures and one dependency deprecation warning, in 697.17 seconds.
[Full log](artifacts/phase31-followup-2026-09-27/full-backend-hydrated.log).
Frontend **166 tests and production build passed** after the main-loop wording change. Manual
verification covered the original/corrected report-hook reconstruction, direct world-state inspection,
and the real saved dashboard trial pair. [Verification note](docs/part2/REPORT_FINALIZATION_FIX_2026-09-27.md).
The earlier invocation hit three failures and six setup errors reading the unhydrated main database;
its full log remains preserved. No test was changed or newly skipped to obtain the clean result.

Audit baseline on September 27: **1,805 backend tests passed, 180 skipped, two failed**;
**124 frontend tests**, production build and **three browser fixture checks passed**.
The optional actual-server smoke was skipped.

**Previous live runtime verification:** after the 503 fix, one complete backend invocation finished with
**1,920 passed, 180 existing skips, zero failures**, one dependency warning, in 702.49 seconds.
[Full log](artifacts/verification-2026-09-27/backend-full-after-service-retry.log) and
[result](artifacts/verification-2026-09-27/backend-full-after-service-retry.json).
The earlier clean 1,891-pass run and combined-run record remain preserved; the latest full run
supersedes them for runtime `3da193e3…`. Separate focused Actor/provider checks: 66 passed;
shared checks of both experiment entry points: 74 passed. Offline checks made no provider calls.

**Previous frontend verification:** 166 tests, production build and three browser fixture checks passed. The optional automated
actual-server mutation test remains skipped; manual real-server checks covered the successful saved
replay, Phase 28 qualification, Phase 24 HARM, retained baseline policy, and displayed model/context defaults.
Read the [new verification note](docs/part2/STATUS_NOTES_2026-09-27.md).
Local proof: [dashboard screenshot](artifacts/verification-2026-09-27/unseen-result-and-active-policy.png) and
[verification summary](artifacts/verification-2026-09-27/verification-summary.json). These ignored local artifacts
are not included in a source clone. Those original implementation checks used saved data only;
the separately declared live compatibility follow-up is tracked above.

- **Fixed:** one bounded, charged retry handles a model HTTP 503 with no returned generation.
  Controlled failure tests and code review verify the branch. No real 503 occurred in the complete
  live follow-up; that run verifies integration, not another provider-error recovery.
- **Fixed:** successful replays validate against their saved replay-policy hash. Ordinary generated-candidate
  validation remains strict. A real 42-trial successful replay now opens in the dashboard.
- **Fixed:** indexed citation decoding uses the observations sent to that model request, before report
  hooks can append new evidence. Hook-generated labels cannot validate a guessed citation. The audit
  found no affected citations in 4,615 inspected stored reports; no saved reports were rewritten.
- **Fixed tests:** historical policy records are checked by their original identities, and the cancelled
  protocol's approval rehearsal is isolated from its later cancellation. The original runtime rejection
  checks remain covered; the cancelled experiment remains cancelled.
- The new status display independently reads development evidence, matching unseen checks and the actual
  campaign active-policy pointer. Saved qualifications match Phase 17 **1/9**, Phase 23 **3/30** and Phase 28
  **9/49**, with zero mismatches across 88 attempts. It never promotes or activates a policy.
- All **37 historical result files** matched the consolidation's pre-change hashes, including Claude's
  already-corrected Phase 28 report. The scorer and Actor system prompt remain unchanged. The later
  report-finalization fix intentionally changes the interpreter under a new runtime identity.
- The prospective runner/partition passed **102 offline checks**. At completion of that live experiment,
  all 98 application files matched the pre-run source checkpoint; it did not change the runtime. All 318 worlds and
  saved readbacks were reconstructed; fresh exact-ID Weave reads verified three selected episodes.
- **Fixed offline under a new runtime:** a rejected generated policy used `defer_unresolved` then
  tried a business read in its report hook, preventing submission of a real answer. Finalization now
  skips closed business I/O while preserving applicable receipt guards and charged policy steps;
  other hook-budget failures get precise diagnostics. The three historical failures remain unchanged.
  The selected live repair does not use this sequence. This fix does not prove live completion gain.

Preserve original reports, failed trials and evaluation partitions. Do not weaken C1–C8, qualifying
thresholds or gates, substitute a corrected model answer, or present a replay as fresh execution.

## Next recommended work

Claude's original program ends at **Phase 31: the write-up and event demo**. That research-program
milestone is complete; the broader product goal is not. No paid run is active.

The owner accepted the following direction, while explicitly asking the next lead to question and
improve it based on actual evidence:

1. **Complete the core workflow.** Trace connecting an agent/task, fault discovery, reproduction,
   diagnosis, repair, challenge, acceptance/rejection and saved regression as one usable flow.
   Locate missing links and distinguish working modules from verified end-to-end behavior.
2. **Improve repair quality.** Investigate what information and actions the Mechanic needs, then
   compare repairs on fresh cases with honest completion, violation and fault-exposure accounting.
3. **Make it usable by another developer.** Improve agent setup, campaign history/progress,
   before/after evidence, export and rerun. Verify whether routine use still requires research scripts
   or manually pasted identifiers before deciding what to build.
4. **Prove reuse beyond the shop.** Complete independent-agent integration and choose a second
   meaningful workflow with its own environment and rules, reusing the same testing engine.
5. **Make operation dependable.** Verify persistence, restart, cancellation, isolation/concurrency,
   clean setup on another machine and security appropriate to the intended deployment.

Start by auditing and completing the core workflow, not by automatically starting another narrow
notification experiment. A write-attempt record remains one possible intervention; the
[notification review](docs/part2/NOTIFICATION_PROGRESS_REVIEW_2026-09-27.md) explains why simply
reintroducing the old v2/v3 summaries is not justified. Change the sequence when a concrete dependency
or new evidence warrants it, and explain why.

FaultLab can work correctly while rejecting an ineffective repair. Product reliability, the tested
agent's mistakes and learned-repair effectiveness are separate outcomes. Do not force the agent to
call a tool just to expose a scheduled fault, weaken the referee to create acceptance, or count an
untriggered fault as a passing fault test. Handwritten reference policies can check plumbing when
clearly labeled; they are not learned-repair evidence. Keep closed evaluations and their verdicts intact.

The next chat should take ownership of implementation and verification after a concise evidence-based
plan. Keep this page current; use the [saved starting prompt](NEW_CHAT_PROMPT.md) to continue.
