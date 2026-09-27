# FaultLab — current status

Updated **September 27, 2026**. This is the single current status and continuation page.
README, AGENTS, CLAUDE and memory entry points refer here. Historical reports describe
their own frozen experiments; their settings, budgets and next steps are not current instructions.

## Current work

The implementation and saved-evidence verification below are complete. On September 27 the owner
then authorized the lead to independently review the follow-ups and perform justified bounded work.
GitHub publication remains pending explicit approval.

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
- [ ] Complete the full backend suite again on this new runtime, then seal and execute the
  [separately declared service-reliability check](docs/part2/SERVICE_RELIABILITY_CHECK_2026-09-27.md).
  It compares the same fixed policy against the empty baseline on the same seven public cases,
  in 42 fresh worlds and a separate store. No pooling, whole-episode retry or policy activation.
- [ ] Independently verify the new run's reports, shop effects, trace readbacks and clock/attempt
  identities; publish both results separately, update the ledger and save the final local checkpoint.

**Decision:** do not perform the suggested immediate “Phase 28 unseen-case check.” The frozen Phase 28
protocol explicitly disallows that routing. The old unseen-case generator also excludes notification
development cases but not `upgrade-v1`, so a different seed could repeat known upgrade faults. Instead,
the new measurement compares the first strongly qualified Phase 28 policy and the empty baseline on
the seven already-public upgrade cases: 21 pairs / 42 episodes, under the corrected runtime, with a
$20 cap. It cannot establish new learning, unseen generalization, certification or policy acceptance.
A later learned-repair/unseen-case claim requires a separate prospective design: seal a genuinely new
partition before generating new candidates, then qualify and route under one frozen runtime.

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
| Phase 28, latest repair-generation experiment | **9 out of 49; eight distinct upgrade-side policies** | Development cases only; no unseen-case evaluation of these policies |
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
storage work. A second task environment, general agent onboarding, successful independent repair
validation and a shared hosted product are not established.

## Evidence and reading order

1. [Latest repair-generation result: Phase 28](docs/part2/PHASE28_RESULTS.md) and its
   [declared protocol](docs/part2/PHASE28_EXPERIMENT.md).
2. [Phase 24 unseen-case result](docs/part2/PHASE24_RESULTS.md).
3. [Phase 30 narrow reporting probe](docs/part2/PHASE30_RESULTS.md): recommended for a later experiment,
   not adopted and not an end-to-end result.
4. [Phase 1 results](docs/part2/PHASE1_RESULTS.md): native agent, incident export and regression evidence.
5. [Original month plan](docs/part2/PLAN.md): a historical roadmap, not a completed-feature list.
6. [Preserved handoff notes](memory/history/2026-09-27-before-consolidation/README.md) for detailed history.

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
this follow-up. The simulator remains available. A live model-catalog check verified both selected IDs
without generation. The prospective compatibility run uses its own store and explicitly declares its
new runtime; historical campaigns are read-only. Recheck processes before starting or stopping services.

## Budget

The carried shared allowance is **$813.40 conservatively charged / $186.60 remaining of $1,000**.
It begins with Phase 2; changing accounts, agents or machines does not reset it. Actual provider-billed
dollars are unavailable. The detailed non-overlapping ledger sums to $811.39726; the carried figure
is conservatively higher due to a historical probe double-count and rounding. Do not silently reclaim it.
See the [preserved ledger](memory/history/2026-09-27-before-consolidation/memory/context/runtime-and-evidence.md).
The original consolidation made no paid calls. The first separate compatibility check charged
81 model requests, conservatively $1.6929, carried upward as $1.70. The new reliability check is
not yet executed. Provider-billed cost remains unavailable.
The owner subsequently reported adding more than $1,000 to the account and authorized further work;
this is not a verified provider balance and does not erase prior charges. The next compatibility
measurement fits within the existing remaining allowance, so it needs no budget reset or increase.

## Source and backups

At the September 27 audit, local `main` and GitHub `main` were at `cbbf957` (September 14).
Local `backup/part2-2026-09-22` was at `7c36110` (September 26), 22 commits ahead. All 585
files in that backup matched the working folder before Claude's later wording correction and this
implementation. Current edits are therefore additional local work; do not reset the working tree.
Recheck Git state before publishing. This work does not push or merge branches.
The September 27 consolidation is saved on that local backup branch at `52ee801`; the reviewed
replication runner and declaration are saved at `deff0b1`. `main` and GitHub were not moved.

Ignored `artifacts/` contains roughly 4.5 GB of databases, worlds and evidence. A source clone does
not carry it. `/Users/shree/FaultLab_Backups/2026-09-26/lab-after-phase28.sqlite3` matches the
campaign, episode, policy, verdict and evidence records checked in the main store at audit time.
Keep local world files and frozen configurations with the database. The temporary Phase 28 worktree
is an older preparation copy; do not use it as the latest implementation.

## Verification and known issues

Audit baseline on September 27: **1,805 backend tests passed, 180 skipped, two failed**;
**124 frontend tests**, production build and **three browser fixture checks passed**.
The optional actual-server smoke was skipped.

**Full-suite verification, September 27 follow-up:** one complete backend run finished with
**1,891 passed, 180 existing skips, zero failures**, one dependency warning, in 712.56 seconds.
All 2,071 cases were collected and run in that invocation after the test-only corrections. Evidence:
[full log](artifacts/verification-2026-09-27/backend-clean-full-sweep.log) and
[machine-readable result](artifacts/verification-2026-09-27/backend-clean-full-sweep.json).
The earlier combined-run verification record is retained as history; the clean full run supersedes it.

**Frontend:** 166 tests, production build and three browser fixture checks passed. The optional automated
actual-server mutation test remains skipped; manual real-server checks covered the successful saved
replay, Phase 28 qualification, Phase 24 HARM, retained baseline policy, and displayed model/context defaults.
Read the [new verification note](docs/part2/STATUS_NOTES_2026-09-27.md).
Local proof: [dashboard screenshot](artifacts/verification-2026-09-27/unseen-result-and-active-policy.png) and
[verification summary](artifacts/verification-2026-09-27/verification-summary.json). These ignored local artifacts
are not included in a source clone. Those original implementation checks used saved data only;
the separately declared live compatibility follow-up is tracked above.

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
- All **37 historical result files** match the pre-change hashes, including Claude's already-corrected
  Phase 28 report. The scorer, interpreter and Actor system prompt remain unchanged by this work.

Preserve original reports, failed trials and evaluation partitions. Do not weaken C1–C8, qualifying
thresholds or gates, substitute a corrected model answer, or present a replay as fresh execution.
