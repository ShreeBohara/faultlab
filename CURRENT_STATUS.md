# FaultLab — current status

Updated **September 29, 2026 (UTC)**. This is the single current status and continuation page.
README, AGENTS, CLAUDE and memory entry points refer here. Historical reports describe
their own frozen experiments; their settings, budgets and next steps are not current instructions.

## Current work

**Current priority: complete and improve a dependable product.** The owner clarified that they meant
“enhance,” not “announce.” The completed Phase 31 write-up/demo is a saved asset, not the end of the
project. Finishing Claude's experiment program did not establish full product acceptance.

**Current runtime: `c9af0a47013a1140ed9ccce80a26e6912de1f86e89cfd73ae9c1881cf8f49775`** (algorithm
`6d6433df…`), local and uncommitted, on top of checkpoint commit `e7340c9` (runtime `c0a8aad7…`); simulator
service **`3ce5bcd2…`**, contract **`6f9d7783…`** and interpreter hash `6da0714a…` unchanged, so checkpoint
bundles stay rerunnable; every agent must be registered again. Chain: `cfe5ac07` → `bb87c764` → `9f53eb8c`
(discovery v2) → `c9b1b7e6` → `c0a8aad7` (simulator revert, committed as `e7340c9`) → `debc86f3` (transport
retry, below) → **`c9af0a47`** (its review fixes, below).

**September 29 (builder, $0): one bounded transport retry for every model role, and fixes.** Details:
[transport retry note](docs/PRODUCT_TRANSPORT_RETRY_2026-09-29.md); evidence `artifacts/product-retry-2026-09-29/builder/`.
Two independent $0 reviews (accounting READY, correctness READY_WITH_CHANGES) found no accounting bug and six small
items; **all six are handled** (runtime `debc86f3` → `c9af0a47`; evidence `…/fixer/`, note section 11):
- **Cost and token figures after a retry (documented; one convention now in code):** per record, tokens are the
  answered request's only and the cost is unknown (`cost_dollars: null`) for a retried selection or Mechanic output
  and for an Actor or native episode after any lost request (the Actor now matches the native bridge). For the
  campaign, every attempt is charged its full call, token and dollar bound, but after the first retry the budget
  shows usage as not fully known (`usage_metadata_known: false`, `actual_cost_dollars: null`) for the rest of that
  campaign. Conservative and honest; not an accounting error. Live runs already had null costs (the provider reports none).
- **Mechanic retry labels:** `mechanic_diagnosis` / `mechanic_proposal` / `mechanic_completion` (was `mechanic_mechanic`).
- **Retry bounds are discovery-only:** the 8/16 Explorer retry bound and the 160-request / $4.27 worst case cover
  **discovery**; later Explorer (challenge, selection comparison) and all Mechanic retries have no separate count and
  are bounded by one retry per request and the campaign caps. The dashboard now says "during discovery" plus one line.
- **Task display, digits:** a U+FE0E/U+FE0F after a digit, `#` or `*` is now marked unless it is inside a keycap
  (1️⃣); plain only after a pictograph (❤️). The builder's rule had left one hidden bit per digit.
- **Native drift companion** lists why each native tick-0 row stays drift. **Imports list re-check:** no change
  (measured 0.32 s for 100 items; not polled), as the reviewer advised.
- **FaultLab bug fixed:** campaign `a301846e` ended ERROR after one Explorer `APIConnectionError`. The Explorer,
  the Mechanic and the native smolagents transport now follow the Actor's exact rule (one shared module): one
  blind retry of the identical request, only when no answer arrived (connection error, timeout, HTTP 503 after
  1 s; never after any answer, never other statuses/auth/config/model mismatch), charged on the ledger before it is
  sent from unreserved capacity (refused → the original failure stands), recorded, and a second failure ends the
  campaign as before. Native: the retry sits inside `_Bridge.generate`, so smolagents sees one step and the same
  messages; it is charged as a model call, never an actor turn (≤ 8 generations + ≤ 8 retries per episode).
- **Discovery budget decision:** a retry is **not** one of v2's 16 Explorer requests; it is declared separately as
  `explorer_transport_retries_max` (8 v1 / 16 v2, **discovery requests only**) and every new plan freezes the rule as
  `transport_retry` (dashboard plan text shows both). v2 **discovery-phase** worst case is now 160 requests / about
  $4.27 (was 144 / $3.47); later-phase retries are bounded per request and by the campaign caps.
- **Native report tick fixed** (real tick), so new native stores pass `check_clock_drift.py` as is. For old native
  stores use `scripts/experiments/check_clock_drift_native.py` (same scan, plus the declared rule: tick 0 + equal
  attempt counts + integrity VALID). `check_clock_drift.py` stays byte-identical because closed runners pin its
  sha256 (editing it failed 78 pin tests). On a read-only copy of the native-probe store: drifted 0, 13 cleared.
- **Verification LOW issues 2–5 fixed:** presentation selector unmarked only after a pictograph or inside a keycap
  (review fix; the builder's "emoji base" rule still let digits through); Run desk
  "Recorded task" and history "Saved task" use `TaskText`; the imports list agrees with the detail view on
  `runnable`; a capability directory raises `ConfigurationError` and closes its descriptor. Issue 1 (caller gate
  counts B1 controls) is still open.
- **Manual $0 check:** the full offline original loop under a v2 plan, with lost Explorer, Mechanic (connection and
  503) and Actor requests, reached the same COMPLETED result and accepted-policy content as a clean run, with exactly
  4 retries recorded and 4 extra requests charged.
- **Found, not fixed (LOW, pre-existing):** selection records keep `input_tokens: null` when a provider returns no
  usage; the dashboard's Usage contract rejects null and the fault-search panel then refuses the whole list.
- **Next:** register the agents again under `c9af0a47`, then a new, separately declared 8-slot v2 campaign
  (never merged with `a301846e`'s partial 5 of 8).

**PM decision (September 28): the simulator identity change is reverted.** Compatibility of previously
exported bundles and existing registrations matters more than a control-capability file created at import
time, so `backend/app/simulator/main.py` is back to its `8e497da` bytes (it builds the server app when
imported, as before). Nothing else changed in that step. Consequences:
1. Bundles exported under the checkpoint simulator (contract `6f9d7783…`) can be **rerun again** (checked in
   the real dashboard at $0: reviewed as eligible, target compatible, confirmed fresh rerun COMPLETED,
   3 of 3 valid trials). A bundle made by the reverted build (contract `1099eda7…`; the only known one is
   the test fixture `exported-regression-other-simulator.zip`, sha256 `f2ac6a60…`) stays reviewable and is
   refused for rerun, naming both identities and "an earlier or different simulator build".
2. Every agent must still be **registered again** before any live run: a registration records the
   whole-backend `runtime_hash`, which differs from every earlier registration's (discovery v2 and the
   review fixes changed `backend/app`), even though its simulator and contract part matches again.
3. The planned paid import validation uses the **restored** fixture `frontend/tests/fixtures/exported-regression.zip`,
   sha256 `14e53310cde9a3f6f985eb6bc4ac9fa0393a2155effd518953f39699a4ecb6df` (its `8e497da` bytes, contract
   `6f9d7783…`). The old `exported-regression-earlier-simulator.zip` was byte-identical to it and was moved
   to `artifacts/product-discovery-2026-09-28/fixer3-0928/moved/`, with the lazy `main.py` and its test.
4. Accepted trade-off: outside tests, importing `app.simulator.main` reads settings (from `.env`) and
   creates or reuses `artifacts/control-capability` (0600), exactly as at the checkpoint. The test suite
   imports it once with an empty scratch settings file and a scratch artifact directory (root
   `backend/tests/conftest.py`), so tests still never read `.env`; `tests/simulator/test_entry_point.py` pins
   the simulator identity to the checkpoint values and checks the entry point's capability and authorization.

Verification of `c0a8aad7` is recorded under *Verification and known issues*.

**Independent verification of `c0a8aad7` (September 28, verifier4; $0, no provider/model/W&B call; evidence
`artifacts/product-discovery-2026-09-28/verifier4-0928/`, git-ignored).** Nothing was taken from earlier reports.
- **Identities** (the app's own functions): runtime `c0a8aad7…`, algorithm `e5dce72c…`; simulator service
  `3ce5bcd2…` and contract `6f9d7783…` equal `8e497da` (`simulator/` and `contracts/` byte-identical; the
  checkpoint tree recomputes to `cfe5ac07…`). `gate_freeze.py`: `checks.py` hash and `assess_pairs` text/AST
  unchanged against `8e497da` and the Phase 28 record (`783e8e58…`).
- **Suites, one clean run each:** backend **2,562 passed, 180 skipped, 0 failed**, 2 known warnings, 929.09 s;
  frontend **303 unit tests** (17 files), build (size advisory), **15 browser tests passed, 1 opt-in skipped**.
  **0 outside connections or lookups**: audit hooks in every Python and Node process refused and logged none, and
  a process-tree socket sampler saw none. The only real-`.env` events were the 3 synthetic ones in `test_env_guard.py`.
- **A bundle exported before today reruns:** `native-offline-incident-bundle-96f072.zip` (exported September 27,
  contract `6f9d7783…`, the same bytes as the restored fixture), through the real backend API and a real simulator
  on 127.0.0.1, a scratch data folder and the tests' scripted provider-free agent: reviewed as runnable, fresh rerun
  **COMPLETED, 3 of 3 valid trials**, incident reproduced (C3), not provider-backed, $0. The other-simulator bundle is
  refused (409, both identities named). A September 20 bundle (contract `6265eadc…`) is refused at upload.
- **Every review finding re-tried and holds.** The six re-send picks the review named are now NOT_FORCED (N3). Caller
  gate PASS (3,337 episodes, 124 points, lowest 83.3%); it fails both controls (caller v1: 20 of 134; no 3-check cap: 3).
  Back-test re-derived: IMPOSSIBLE fired **0 of 6**; the 58 FORCED misses are 47 skipped calls + 11 early ends, 0
  reached-but-not-fired (3,402 episodes; the lost script's 3,447 / FORCED-fired 3,370 differ only in that cell).
  New adversarial sweep: **1,540 rule-IMPOSSIBLE faults, 1,500 recipes, 29,620 runs, 0 fired** (raw attempts, adapter
  calls, control-plane waits; other faults fired in 19,913 of 27,680 runs). Task display: all 4,174 default-ignorable
  and 58,390 other non-visible code points are marked; 2,000 random mixes hide nothing. The dotenv guard makes 0 `.env`
  opens (also with `PYTHON_DOTENV_DISABLED=0`). Capability files with mode 0644/0640/0604, symlinks or FIFOs are refused.
- **v1 unchanged by default:** checkpoint and current code, fed the 8 saved c701e850 Explorer outputs through the real
  loop, send byte-identical Explorer messages (8 of 8) and store identical selection records. 115 real plans saved on
  September 27, before the `discovery` field existed, still verify and read as v1.
- **Historical data unchanged:** the 31 result documents and all other tracked files not in the commit list match
  `8e497da`. All 8,863 `.sqlite3` and `-wal` files keep their hashes, sizes and mtimes. Only the 3 known `-shm` timestamps
  moved, because older tests open those stores `mode=ro`. HEAD and index are unchanged.
- **New LOW FaultLab issues, not fixed:**
  1. The caller gate also counts 30 handwritten B1 control episodes (`source_mode` offline_fixture) as the real Actor.
     Without them it still passes. Fix: filter `source_mode == 'live'` in `load_rows`, before Run A.
  2. One U+FE0E/U+FE0F after every visible character stays unmarked, following the review's rule. That leaves a
     1-bit-per-letter hidden channel that raises no warning; only the character count shows it.
  3. `RunControls` "Recorded task" and `CampaignHistory` "Saved task" show a task raw. For an import, that is the
     bundle's task.
  4. The imports list still says `runnable: true` for an other-simulator bundle. Its detail view and execution refuse it.
  5. A capability path that is a directory fails with a raw `IsADirectoryError`.
- **For the PM commit:** 43 changed and 27 new files versus `8e497da`, none removed. The exact list with sha256 is in
  `verifier4-0928/COMMIT_LIST_vs_8e497da.txt`.

**Implemented offline, not yet committed or run live: discovery protocol v2 (reachability pre-check).**
A Learn plan can now explicitly declare `faultlab-discovery/v2-reachability` (default stays v1, today's
exact behaviour). Before a paid Actor episode, a free in-process replay labels each fault FORCED /
NOT_FORCED / IMPOSSIBLE for the reference Actor's real action space; only all-FORCED picks run, a refused
pick gets one re-plan, and the declared budget is 8 slots / 16 Explorer requests / 8 episodes. Native
agents cannot declare v2. The order-sensitive schedule-identity bug is fixed for new campaigns only.
Read-only back-test on 3,447 stored episodes: 0 of 6 stored IMPOSSIBLE faults fired (the wider evidence
is a 35,976-run adversarial sweep with 0 fired); all 58 unfired FORCED faults were the Actor skipping a
call or an episode ending early; that FORCED-miss rate (1.5% for V3.1) covers attempt-1 faults only.
**Review fix (FaultLab modelling bug):** the first caller model assumed the Actor re-sends a write after
UNKNOWN; stored DeepSeek-V3.1 almost never does, so re-send-dependent faults were wrongly FORCED. Caller v2
never re-sends and makes at most 3 status checks after a write failed on both attempts; a new $0 gate
(`scripts/experiments/check_reachability_caller.py`) checks every modelled attempt against 3,337 stored
episodes and passes (124 points, lowest 83%); the old model fails it. **Corrected Run A bound:** discovery
at most **144 requests / about $3.47** (the earlier 80 / $2.14 left out the charged Actor transport retry);
campaign worst case about $56 by the plan's phase table, $200 cap. Runtimes `9f53eb8c…`, `c9b1b7e6…`, now
`c0a8aad7…` (the simulator revert; no discovery code changed); $0. The gate was re-run under `c0a8aad7`: PASS.
See [the discovery v2 note](docs/DISCOVERY_V2_2026-09-28.md), which also lists the completion-gap families
a wait/retry policy could recover but policy-v0 cannot.

**Implemented and reviewed, not yet committed: dashboard bundle import, review and a separate fresh
rerun.** The whole feature is now in this main folder (the product worktree copies are stale). A saved
regression ZIP is checked and stored as data with no provider calls; the review shows the source trials,
how they were produced, and the exact task and order the rerun will send; a fresh rerun is a separate,
confirmed, bounded action whose accounting campaign refuses all other work. Three independent $0 reviews
(September 28) found real gaps — the task sent to the agent was not shown, the accounting campaign admitted
paid studies, malformed bundle fields could break the imports list, and the backend accepted any Host
header — and every finding was fixed with tests; see *Review fixes* in the
[import review](docs/PRODUCT_IMPORT_REVIEW_2026-09-27.md).
*Historical:* the import increment was verified under runtime `cfe5ac07c6ef571f7be5f57cc8f56cbce4084496c3d157d3b222c0e9bb0f6738` (full backend 2,363 passed, 180 skips; frontend 254 unit tests, build and 13 browser fixtures). Those counts and that runtime are **not current**; see *Current runtime* above. Provider calls 0, cost $0; main HEAD/index unchanged; no push.
A second $0 review (September 28) found that the task display let variation selectors, U+034F and other
invisible combining characters through unmarked, and that hidden characters on collapsed blank lines
vanished; fixed in the dashboard (every default-ignorable character is marked except one emoji
presentation selector after a visible character; collapsed lines count every hidden character; the warning
and escaped copy appear whenever any are present). It also found tests that read the real `.env` through
the simulator's `create_app`; they now pass explicit settings and the test process refuses any open of it.
Smaller hardening from the same review: an existing control-capability file readable by group/others, owned
by another user, or not a regular file is now refused; importing the backend sets `PYTHON_DOTENV_DISABLED=1`
by default (an explicit operator value is kept); a static test fails if any module imports smolagents outside
the adapter's dotenv guard; a bundle from an earlier or different simulator build is marked not runnable at bundle level.
**Next:** the PM commits, then the owner declares the bounded real-model validation (worst case 72
requests across the two targets, or cap each execution at 24; see the review doc) **under the current
runtime, after registering the targets again and using the restored fixture above**. Original historical
stores remain untouched. See [current increment memory](memory/context/product-import-2026-09-27.md).
Of the five LOW issues from the independent verification (above), issues 2–5 were fixed on September 29 (runtime
`debc86f3`; the task-display rule was tightened for digits in `c9af0a47`); issue 1 (caller-gate scope) is still open.

**Reviewed campaign setup and native-agent execution are implemented, verified and saved locally.**
The dashboard now offers reference/native selection, explicit registration, six public cases, an immutable
saved plan and a separate Start action. Every original learning phase uses the selected agent. Native
provider-identity/accounting failures are classified as lab errors; native audit freezing and a guard
against calling same-implementation reruns independent portability are implemented. Public recordings
include unsuccessful runs and the plan. Current campaign state also keeps history labels up to date.

Onboarding runtime: `d1845765fa1c120ad4afd936461ddb4e4d909972209b160d6eebd63d6b3c64fb`.
**Full backend: 2,224 passed, 180 existing skips, zero failures**, two warnings, 791.81 seconds.
**Frontend: 219 tests, production build and ten browser fixtures passed**; one opt-in actual-backend check
was skipped. Actual UI checks ran all six public cases, verified a real recording download, and preserved
138 records / 64 events / six policy pointers across restart. Independent manual audit passed 160 checks;
153 scripted-native worlds passed 2,324 independent comparisons. A further final-source dashboard run,
CLI audit freeze and archive check passed; all old database hashes/mtimes stayed unchanged. These
checks establish execution and evidence integrity, not new live learning or generated-policy acceptance.
[Onboarding review](docs/PRODUCT_ONBOARDING_REVIEW_2026-09-27.md) and
[implementation memory](memory/context/product-onboarding-2026-09-27.md) contain the details.
The exact source checkpoint and verified recovery manifest are recorded in
`artifacts/product-onboarding-2026-09-27/final-checkpoint.json`; external backup:
`/Users/shree/FaultLab_Backups/2026-09-27/product-onboarding/`. Main/index/history/secrets are preserved.
All temporary services and browser tabs are closed. No GitHub push.

**Durability increment completed and verified.** The original learning workflow was
exercised end to end, then the app's ownership, recovery and local operation were hardened. One writable
coordinator now owns each store before recovery; archive mode never initializes or recovers records;
dashboard queries use independent read-only snapshots; job finalization and reservation release are atomic.
CLI registration, import/execution and portability preparation now use the owning backend. A paired local
launcher makes the data directory explicit. The dashboard handles missing saved IDs without repeated
requests and distinguishes full, partial and absent fault exposure.

Durability runtime: `7dfdfe29fd210c70b5b83915f0cd47b144e03d49ffe172a9dfa722c50bd523f0`.
The complete backend suite passed on this frozen source: **2,123 passed, 180 existing skips, zero failures**,
two warnings (Starlette deprecation and the explicit fork ownership test), 727.37 seconds. Three old restart
fixtures were corrected to close the first store; all recovery assertions stayed intact. Frontend:
**206 tests, production build and eight browser fixtures passed** (one opt-in actual-backend test skipped).
Actual manual checks used both the archive and a fresh offline store: one upgrade, one confirmation,
all eight fixed checks, zero model calls. A real process restart preserved all 23 records, eight events
and the policy pointer exactly. A second coordinator was refused before recovery. All eight closed live
SQLite files retained their hashes and modification times after archive browsing.
[Durability review](docs/PRODUCT_DURABILITY_REVIEW_2026-09-27.md) and
[current implementation memory](memory/context/product-durability-2026-09-27.md) record the evidence.

**The latest live original campaign is closed NO_CHANGE.**
[Declared run](docs/PRODUCT_LOOP_RUN_2026-09-27.md) `c701e850…`, frozen runtime `60f27623…`,
completed seven tasks with zero violations and seven verified traces. Eight Explorer requests included
one correctly declined duplicate. Exposure was four full recipes, one partial and two absent; the
status-read faults were not reached because the Actor already had terminal receipts. This is an Explorer
planning limitation, not an Actor mistake or FaultLab dispatch failure. No source candidate qualified;
baseline remains active. Independent audit passed 188 checks, including 34 read-only Weave readbacks.
[Closed result](docs/PRODUCT_LOOP_RESULTS_2026-09-27.md). No repeat campaign is planned merely to seek success.

**Spending:** $1.04662 conservative bound for those 39 live requests ($1.05 carried); measured token-priced
estimate $0.15324862, provider-billed cost unavailable. **Carried total $856.96. Durability and onboarding work: $0 in
provider calls.** All historical evidence is preserved. No GitHub push.

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

**That completed core increment spent $0; prior historical accounting was $855.91.** No GitHub push. No historical verdict,
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

**Current carried accounting: $860.14 conservatively charged** = $856.96 below + $2.14 for the September 28 native
baseline probe ([result](docs/PRODUCT_NATIVE_PROBE_2026-09-28.md)) + $1.04 for the INCOMPLETE discovery-v2 run
`a301846e` ([result](docs/PRODUCT_DISCOVERY_V2_RUN_2026-09-28.md)). The September 29 transport-retry work made no
provider call ($0).

The previous carried accounting was **$856.96 conservatively charged**: the previous $855.91 plus
$1.05 for the completed original-workflow campaign (39 requests, exact bound $1.04662).
Its token-priced estimate is $0.15324862; provider billing is unknown. The independent audit and
current durability implementation made zero new inference calls. The owner has repeatedly authorized
further work with generous resources; the old $1,000 allowance is historical. The actual provider balance and billed cost are unavailable;
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

Latest verified source is saved on local `backup/part2-2026-09-22`; exact commit and unchanged main/index
are in `artifacts/product-onboarding-2026-09-27/final-checkpoint.json`. Its external `product-onboarding/`
copy includes source, test/native-fixture evidence and both actual manual workspaces. The earlier `product-core/` recovery copy
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

**Current runtime `c9af0a47…` (September 29, review fixes; evidence `artifacts/product-retry-2026-09-29/fixer/`):**
one clean run of each suite after the last code edit. Full backend **2,651 passed, 180 existing skips, 0 failed**, the
2 known warnings, 932.61 s; audit hook: **0 outside connections or lookups**, `.env` touched only by the 3 synthetic
events in `test_env_guard.py`. Frontend **312 unit tests** (18 files), production build (size advisory only), **15
browser tests passed, 1 opt-in skipped**; Node guard logged nothing. New or changed tests cover the Mechanic request
kinds, unknown cost after a retry (Explorer, Mechanic, Actor; loss-free controls keep the known cost), the checker's
reasons, digit/keycap/pictograph task display (unit, component and random-mix oracle), and the "during discovery"
text. Negative control on a scratch copy whose reverted files equal the builder's: backend 12 and frontend 7 of the
new or changed tests fail; the rest check unchanged behaviour. Manual $0: the real dashboard marks a selector after
each digit in the Run desk, saved plan and history, and keeps keycaps and pictographs plain; the companion checker
reads the native-probe store as before (0 drifted, 13 cleared) and gives the Phase 1 store's reason per row. The
console 404 on first load is Chrome's `/favicon.ico` request (no icon shipped), not an API call. Historical stores:
9,409 files, no content or size change, only the 3 known `-shm` timestamps moved. HEAD `cbbf957`, backup branch and
index unchanged; nothing committed. Identities: runtime `c9af0a47…`, algorithm `6d6433df…`, service `3ce5bcd2…`,
contract `6f9d7783…`, interpreter `6da0714a…`, `check_clock_drift.py` `fa25ab9d…`.

**Previous runtime `debc86f3…` (September 29, builder; since reviewed twice, see *Current work*):** one clean run of each
suite after the last code edit. Full backend **2,642 passed, 180 existing skips, 0 failed**, the 2 known warnings,
950.60 s; audit hook: **0 outside connections or lookups**, `.env` touched only by the 3 synthetic events in
`test_env_guard.py`. Frontend **310 unit tests** (18 files), production build (size advisory only), **15 browser
tests passed, 1 opt-in skipped**; Node guard logged nothing. New tests: `tests/agents/test_role_transport_retry.py`,
`tests/lab/test_campaign_transport_retry.py`, `tests/lab/test_native_transport_retry.py`,
`tests/lab/test_transport_retry_plans.py`, additions to `test_bundle_import_boundaries.py` and `test_config.py`;
frontend `transport-retry.test.tsx` plus task-text and discovery additions. Negative control: run on the checkpoint `e7340c9`
code, the new tests fail (backend 14 of 17, frontend all 8 new or changed; the 3 backend passes assert behaviour
that did not change, e.g. a retry the budget refuses). That control predates the checker companion.
A first full run failed 78 closed-runner pin tests because `check_clock_drift.py` had been edited; it was restored to
its pinned bytes (see above). Historical `.sqlite3`/`-wal` files: 9,176 checked, hashes unchanged; only the 3 known
`-shm` timestamps moved. HEAD `cbbf957` and the real index unchanged; nothing committed. Evidence:
`artifacts/product-retry-2026-09-29/builder/` (`suites/`, `negative-controls/`, `checker-native-probe/`, `manual/`).

*Independently re-verified by verifier4 (September 28): every count below was reproduced exactly (backend 2,562 /
180 skipped / 0 failed; frontend 303, build, 15 + 1 opt-in skip); see* Independent verification *under* Current work.

**Current runtime `c0a8aad7…` (September 28, after the PM's simulator revert):** one clean invocation of
each suite after the last source/test edit. Full backend **2,562 passed, 180 existing skips, zero failures**,
two known warnings (Starlette alias, explicit fork test), 928.94 s; a log-only audit plugin recorded **0
non-loopback connects or name lookups** and no `.env` open attempt other than the three intentional
synthetic audit events in `tests/test_env_guard.py`. Frontend **303 unit tests** (17 files), production
build (bundle-size advisory only) and **15 browser fixtures passed**; one opt-in actual-backend check
skipped. New tests: `tests/simulator/test_entry_point.py` (simulator identity pinned to the checkpoint and
matching the restored download; import builds the entry point with a 0600 capability, 403 without or with a
wrong token, 200 with it; a restart reuses the capability; the test process's import-time app lives in
scratch, not `artifacts/`) and a plan-record test in `tests/lab/test_discovery_v2_flow.py` (new records carry
`discovery`, `null` for baseline; a record saved before the field still verifies and reads as v1).
Caller gate re-run: **PASS** (3,337 stored V3.1 episodes, 124 checked points, lowest 83.3%); its control with
caller v1's re-send patched in a scratch process **FAILS** on 20 of 134 points, the review's figure.
**Manual real-dashboard check** ($0; real backend API and simulator on 127.0.0.1 over a scratch store; the
tests' scripted, provider-free native agent; `.env` and outside network refused by an audit hook, neither
attempted): the restored checkpoint download was reviewed as eligible and its target compatible, and a
confirmed fresh rerun COMPLETED (3 of 3 valid trials, incident reproduced, not provider-backed, $0); the
other-simulator download was refused, naming `bundle 1099eda7…, installed 6f9d7783…`, with Run disabled; a
correctly hashed bundle whose task hides a sentence in 38 variation selectors plus 4 on a blank line showed
"42 invisible characters", 38 markers and `⟨5 blank lines, 4 invisible characters⟩` in the review and 38
markers in the confirmation box, and its escaped copy decodes to the exact task. Historical `.sqlite3` and
`-wal` files unchanged (only the three known `-shm` timestamps moved); the real control-capability file is
unchanged (0600, September 12); provider calls 0, cost $0; HEAD and index unchanged. Evidence (durable,
git-ignored): `artifacts/product-discovery-2026-09-28/fixer3-0928/` (`suites/`, `gate/`, `manual/`, `moved/`).
*Scratch evidence lost:* a macOS update restart wiped `/private/tmp`; the scratchpad folders cited for
earlier runtimes (`fixer-0928/`, `fixer2-0928/`, `discovery-v2/`, `review-disc-v2/`, `secops-review-0928/`) no
longer exist. Their figures remain as recorded.

*Superseded:* **runtime `c9b1b7e6…` (September 28, after the discovery-v2 and security/import reviews):**
Full backend **2,558 passed, 180 existing skips, zero failures**, two known warnings (Starlette alias,
explicit fork test), 864.82 s, in one clean invocation after the last source/test edit. A log-only audit
plugin recorded **0 non-loopback connects or name lookups** and no attempt to open the real `.env` other than
the three intentional synthetic audit events in `tests/test_env_guard.py`, which the conftest guard refused.
Frontend **303 unit tests** (17 files), production build (bundle-size advisory only) and **15 browser
fixtures passed**; one opt-in actual-backend check skipped. Caller gate
`scripts/experiments/check_reachability_caller.py`: **PASS** on 3,337 stored DeepSeek-V3.1 episodes, 124
checked points, none below 80% (lowest 83.3%). A new invariant test runs every shared task-text case and 400
seeded random mixes: no hidden character appears as plain text, the count covers every default-ignorable
character, the warning and escaped copy appear, and the escaped copy decodes back to the exact text. The
pre-fix display fails it on 364 of 428 texts. Historical `.sqlite3` and `-wal` files kept their sizes and
modification times; provider calls 0, cost $0; HEAD and index unchanged. Evidence: scratchpad `fixer-0928/`
(the fixes) and `fixer2-0928/` (that verification), both lost.
Intermediate runtimes, superseded: `bb87c764…` (hardening; backend 2,402 passed / 180 skips, frontend 286,
build, 15 browser + 1 opt-in skip) and `9f53eb8c…` (discovery v2; backend 2,490 passed / 180 skips, frontend
295, build, 15 browser + 1 opt-in skip, as re-run by the reviewer).

*Historical —* **Import increment runtime `cfe5ac07…` (September 28, after review fixes):** Full backend **2,363 passed, 180 existing skips, zero failures** (two known warnings); frontend **254 unit tests, production build and 13 browser fixtures passed** (one opt-in actual-backend check skipped).
Manual $0 check: import → review → confirmed fresh rerun with the scripted native target, archive reopen,
refusals and the local-host guard, on a scratch store and non-default ports.

**Onboarding runtime `d1845765…`:** full backend 2,224 passed / 180 existing skips / zero failures, 791.81 seconds;
219 frontend tests / build / ten browser fixtures pass. Two backend warnings: upstream Starlette alias and
the explicit POSIX fork ownership test. Vite bundle 502.10 kB minified / 118.64 kB gzip produces a size advisory.
Actual setup/six cases/download/restart/final-source freeze/archive and independent raw audits passed.
[Full log](artifacts/product-onboarding-2026-09-27/full-backend-final.log),
[review](docs/PRODUCT_ONBOARDING_REVIEW_2026-09-27.md). The incomplete isolated suite is preserved;
missing historical fixtures and invalid old test doubles were diagnosed, not silently skipped.

**Previous core runtime `58cd13b6…`:** one complete backend invocation passed **2,010 tests**, with
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

The core path, local durability and reviewed two-agent setup have now been implemented and checked.
Dashboard bundle import with a review before a separate, confirmed fresh execution is now implemented
and reviewed (September 28); it awaits the PM commit and the owner's bounded real-model validation, which
must use the current runtime, fresh registrations and the restored fixture (see *Current runtime*). Repair effectiveness, a separately versioned second
task and clean-machine/hosted deployment acceptance remain separate open milestones. A new live native
check should be prospectively declared, bounded and interpreted honestly; do not reuse a closed partition.

The owner accepted the following broader direction; revise it using actual evidence:

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
