# FaultLab — current status

Updated **September 27, 2026**. This is the single current status and continuation page.
README, AGENTS, CLAUDE and memory entry points refer here. Historical reports describe
their own frozen experiments; their settings, budgets and next steps are not current instructions.

## Current work

The owner requested these steps in order. This is implementation and saved-evidence verification;
no new paid experiment, publication or deployment is part of this change.

- [x] Establish this status page and replace conflicting continuation pointers; preserve old notes.
- [x] Fix successful replay parsing and verify a real saved replay in the dashboard.
- [x] Decode Actor citations using the evidence available when the model was called, before report hooks.
- [x] Repair or correctly scope the two failing historical research tests.
- [x] Make normal app defaults use the tested model/context settings, preserving explicit historical versions.
- [x] Show development qualification, unseen-case results and the active policy separately.
- [x] Complete offline checks, manual saved-evidence verification and documentation of the new runtime.

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
| Phase 28, latest live experiment | **9 out of 49; eight distinct upgrade-side policies** | Development cases only; no unseen-case evaluation of these policies |
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

1. [Latest live result: Phase 28](docs/part2/PHASE28_RESULTS.md) and its
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

The idle backend was restarted to load these changes, and the dashboard was started for verification.
No fresh campaign or model call was made. Recheck running processes before changing them; saved prompts
do not authorize another paid run.

## Budget

The carried shared allowance is **$811.70 conservatively charged / $188.30 remaining of $1,000**.
It begins with Phase 2; changing accounts, agents or machines does not reset it. Actual provider-billed
dollars are unavailable. The detailed non-overlapping ledger sums to $811.39726; the carried figure
is conservatively higher due to a historical probe double-count and rounding. Do not silently reclaim it.
See the [preserved ledger](memory/history/2026-09-27-before-consolidation/memory/context/runtime-and-evidence.md).
This consolidation makes no paid calls and adds no experiment charge.

## Source and backups

At the September 27 audit, local `main` and GitHub `main` were at `cbbf957` (September 14).
Local `backup/part2-2026-09-22` was at `7c36110` (September 26), 22 commits ahead. All 585
files in that backup matched the working folder before Claude's later wording correction and this
implementation. Current edits are therefore additional local work; do not reset the working tree.
Recheck Git state before publishing. This work does not push or merge branches.

Ignored `artifacts/` contains roughly 4.5 GB of databases, worlds and evidence. A source clone does
not carry it. `/Users/shree/FaultLab_Backups/2026-09-26/lab-after-phase28.sqlite3` matches the
campaign, episode, policy, verdict and evidence records checked in the main store at audit time.
Keep local world files and frozen configurations with the database. The temporary Phase 28 worktree
is an older preparation copy; do not use it as the latest implementation.

## Verification and known issues

Audit baseline on September 27: **1,805 backend tests passed, 180 skipped, two failed**;
**124 frontend tests**, production build and **three browser fixture checks passed**.
The optional actual-server smoke was skipped.

**Final implementation verification:** all **2,071 currently collected backend cases** are accounted for
across the broad sweep and focused reruns: **1,891 passed, 180 existing skips**. The initial broad run
had 1,840 passes and three old-default assertion failures. Those assertions were corrected and both
whole test files rerun successfully (18 and 12 tests); the 46 new policy-status tests also passed.
This was not a second complete sweep after the test-only corrections. The local verification summary
records that distinction. No remaining failed current case is known.

**Frontend:** 166 tests, production build and three browser fixture checks passed. The optional automated
actual-server mutation test remains skipped; manual real-server checks covered the successful saved
replay, Phase 28 qualification, Phase 24 HARM, retained baseline policy, and displayed model/context defaults.
Read the [new verification note](docs/part2/STATUS_NOTES_2026-09-27.md).
Local proof: [dashboard screenshot](artifacts/verification-2026-09-27/unseen-result-and-active-policy.png) and
[verification summary](artifacts/verification-2026-09-27/verification-summary.json). These ignored local artifacts
are not included in a source clone. No new live experiment was performed for this runtime.

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
