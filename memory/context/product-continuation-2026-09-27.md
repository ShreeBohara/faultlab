# FaultLab product continuation — September 27, 2026

This is a dated handoff snapshot and reasoning record. [CURRENT_STATUS.md](../../CURRENT_STATUS.md)
remains the single current status page. New user instructions and verified new evidence take precedence
over this snapshot. Historical reports describe their frozen experiments, not instructions to rerun them.

## What the owner wants

The owner is Shree; their teammate is Aryan. They want a complete, dependable FaultLab product and
have asked the lead agent to own architecture, implementation, verification and improvement. They
prefer simple English, concrete progress and independent judgment. They explicitly distrust relying
only on the test suite: inspect code, original model answers, actual simulator effects and the UI.

An important misunderstanding was corrected: the owner meant **enhance**, not **announce**. We
prematurely treated the Phase 31 write-up/demo as the next goal. Those assets are now saved, but the
owner does not regard a presentation, a passing suite or completion of numbered research phases as
completion of the product. Do not steer the work back toward presentation polish as the main goal.

They accepted a broad sequence: complete the core workflow; improve repair quality; make it usable
by another developer; prove reuse with another agent and task; make operation dependable. This is a
starting hypothesis. Challenge it, change it when justified and explain why. Do not merely execute
Claude's or Codex's old phase list. Do not restart the project from scratch either.

Their latest request was **save context and provide a prompt for a fresh chat**. This handoff adds
documentation only. No new implementation phase or paid experiment was launched during it.

## Product and evidence in plain terms

FaultLab is a test track for tool-using agents. It makes a controlled service misbehave, observes how
an agent handles it, checks fixed rules and attempts bounded recovery policies. Models propose;
fixed code checks evidence and decides. The current implemented task is upgrading a shop order and
sending one truthful confirmation. The shop and its task-specific rules were written by hand.
FaultLab does not automatically build an environment or correctness rules for any arbitrary agent.

There are two different execution paths:

- **Original learning workflow:** Explorer/discovery, reproduction/reduction, diagnosis, Mechanic,
  challenge, promotion and regression. Code exists for these stages; a successful generated-policy
  acceptance through the whole original workflow is not established.
- **Completion study:** starts with a chosen case, measures baseline controls, asks the Mechanic for
  a policy and runs source/development validation. It does not use the Explorer, generated challenges
  or original promotion, and cannot activate a policy. Phase 28 and the latest repair studies used it.

Keep three UI/evidence claims separate: **development qualified**, **unseen-case result**, and
**active policy**. Also distinguish (1) bugs in FaultLab, (2) mistakes made by the agent being tested,
and (3) whether a generated repair helps. An honest rejected repair can be a valid completed lab run.
Reliable acceptance/rejection plumbing and convincing useful repair results are separate goals.

## Where the implementation stopped

The last completed code work fixed a report-finalization edge case, independently reviewed it,
manually reconstructed before/after worlds and rehearsed saved results in the dashboard. The full
backend suite then passed **1,952 tests, 180 existing skips, zero failures** in one invocation;
frontend **166 tests and production build passed**. No paid calls were made for that offline fix.

The current app runtime is:

`b9410f5e77f2b98e6a621ee5adabc20c7ac65ea042f8a9d7049dedadaec7d719`

The most recent live results belong to the previous runtime:

`3da193e30a71ea4aebc8309580548c09ece3fb31d4ccd8a8529112b8f8b9a9d8`

Do not present live results from the latter as live verification of the former. New runtime changes
need new identities and separately declared experiments; never repin a closed study to current code.

### Last fix and its limits

In `backend/app/lab/policy_interpreter.py`, once business operations are closed, the
`before_final_report` hook skips business I/O steps but still charges reached policy steps, checks
stop/deadline conditions and evaluates applicable receipt guards in order. Other hooks are unchanged.
The change does not reopen the business budget or rewrite an answer.

In `backend/app/agents/actor.py`, hook-specific budget failures receive precise diagnostics. The
original returned answer is retained, guards that cannot finish do not silently permit submission,
and cancellation/stop conditions propagate. The earlier citation fix still decodes indexed labels
using the evidence list actually sent with that model request, before hooks append observations.

An offline comparison reused the same three captured answers in fresh worlds, substituting only the
fresh operation identity. Old behavior lost the report and produced C5/C6/C7 violations. Corrected
behavior filed the original SAFE_UNRESOLVED report and passed all eight checks. Both had six HTTP
attempts, seven ticks, zero upgrades and zero notifications. Policy steps increased from nine to ten.
**This is a reporting correction, not task-completion gain or fresh model-generated evidence.** The
diagnostic comparison changed the relevant module; it was not a complete historical-runtime replay.

The three historical missing reports were preserved. Referee scoring, `assess_pairs`, promotion
criteria, Actor prompt/context and the original reports were not weakened or rewritten.

The dashboard sentence denying any candidate was corrected to distinguish a main-loop candidate
from separate completion-study candidates. No policy activation behavior changed.

Read [the fix and verification report](../../docs/part2/REPORT_FINALIZATION_FIX_2026-09-27.md).
Tests: `backend/tests/agents/test_report_hook_closure.py`; fixture:
`backend/tests/fixtures/report_hook_closed_business.json`.

## Latest live results — do not overstate them

The latest prospective experiment ran ten development studies, 162 development episodes. The tenth
study produced the first strongly development-qualified new policy. Its validation completed **15/21
tasks versus 9/21 for the baseline**, with zero rule violations. This first-success search is not an
unbiased repair-rate estimate.

The frozen policy was then evaluated once on three newly reserved fault combinations and three
known guard cases: **156 episodes, 78 per arm**. Formal result: **INCOMPLETE**. One baseline never
attempted its notification, so one scheduled fault could not trigger. Candidate: zero violations;
baseline: one C5 report-label violation. Coverage was 239/240 scheduled faults, with 77 fully valid
pairs. This is not a NO_HARM pass or evidence of policy acceptance. The partition is now spent.

All 318 development/evaluation worlds, 2,544 checks, 1,996 HTTP attempts, 452 operation journals,
315 filed reports and 318 saved Weave readbacks were independently reconstructed. There were no
empty Actor answers or lab errors in that experiment. Its 1,783 requests carried a conservative
$37.68 cost. All active policies remained `policy-v0`.

Useful exact identifiers for saved evidence:

- Campaign: `campaign-d51aee5097b24bfd917bb5378408505c`.
- Study: `completion-study-6b9d3ac2e6d84bc1b06b3eb05cfe693e`.
- Selected policy: `6399b3ed170917de49092152e872fb940cc9e7d9b7034335441b29aec3912129`.
- Frozen configuration: `88e97d68d77d641851dfac9404771be88785eb7ba624a90e0d058cb309a48ea0`.
- Notification-polling baseline: `episode-cd05edbe0ec54cd3884845ea96a2c6b4`.
- Offline hook-failure source: `episode-b83c6a5aa0024791a4974e084da8f516`.

Earlier Phase 28 produced 9/49 development-qualified attempts, eight distinct upgrade policies.
Its primary report's Explorer overstatement was corrected by Claude before the consolidation;
preserve that correction and all historical files. Earlier unseen-case HARM verdicts also stand.
A separate 42-episode September 27 compatibility run measured a saved policy's 15/21 versus 9/21
on known cases. It was not fresh learning or unseen validation.

There are **zero generated ACCEPTED policies** through original promotion. A native smolagents live
baseline was already completed in Phase 1; transfer of an accepted repair remains unproven. Do not
say independent-agent support has never been tested, or that accepted repair transfer is finished.

Primary record: [prospective results](../../docs/part2/PROSPECTIVE_REPAIR_RESULTS_2026-09-27.md).

## How to begin the next product phase

First inspect the current tree and trace one campaign through the real app/API, using saved evidence
and offline/reference cases initially. Build a short acceptance checklist describing observable user
actions and outcomes. Mark each stage as present, connected, manually verified, or missing. Review
negative paths too: no failure found, no useful repair, rejected candidate, interrupted run and bad
provider response. Then implement the most important gaps. Do not stop after producing another plan.

The recommended product milestones live in CURRENT_STATUS.md. Treat them as proposals, and consider
these acceptance questions while refining them:

- Can another developer connect a supported agent/task and run the actual workflow without editing
  research scripts or guessing record IDs? Check what already works before adding controls.
- Can discovery reach a meaningful source, reproduce it, diagnose it, propose a bounded repair and
  challenge it? Can the app explain every stop or rejection with the original evidence?
- Can a valid policy pass the unchanged decision path and become active, and can an invalid one be
  rejected? Handwritten reference policies may validate plumbing, clearly labeled as reference work;
  only genuine new model proposals can support learned-repair claims.
- Can the user inspect original reports, actual service effects, before/after results and fault
  exposure, export a regression and run it again in fresh worlds?
- Can the same engine support a second agent/task without embedding that task's answer in the
  evaluator or pretending the new environment and rules were generated automatically?
- Can a run stop/restart safely, keep durable records, isolate concurrent work and install elsewhere?

Do not define success as guaranteeing that every generated repair works. Track task completion,
fixed-rule violations and fault exposure separately, over all declared attempts. An agent that omits
an action should not disappear from the completion denominator; its untriggered fault also cannot
be counted as a passing fault test. Do not force a tool call solely to make coverage look complete.

### Notification research is one option, not the automatic next phase

One baseline upgraded the order and polled five times without sending confirmation, then truthfully
reported SAFE_UNRESOLVED. The model's internal cause is unknown. This is distinct from the fixed
report-hook bug. Earlier progress summaries v2/v3 already regressed live: C5 report failures increased.
Current Actor context remains v4 indexed evidence; Phase 30's report hint is a separate unadopted
probe. Do not reintroduce failed summaries under a new version without studying that evidence.

A more explicit write-attempt record could be tested, but the owner's latest direction is to complete
the core product first. Read [the notification review](../../docs/part2/NOTIFICATION_PROGRESS_REVIEW_2026-09-27.md)
before proposing an intervention. Fresh comparisons need new reserved cases and a declared treatment
of agent-caused missing exposure. Never repair the historical INCOMPLETE verdict retrospectively.

## Code map for the next lead

| Area | Start here, relative to the app root |
|---|---|
| Campaign/API and main workflow | `backend/app/lab/api.py`, `coordinator.py`, `learning.py`, `runner.py` |
| Reproduction and causal checks | `backend/app/lab/reproduction.py`, `diagnosis.py`, `evaluation.py` |
| Challenges and decisions | `backend/app/lab/challenge.py`, `promotion.py`, `policies.py`, `policy_state.py` |
| Separate research paths | `backend/app/lab/completion_study.py`, `context_study.py`, `heldout_check.py` |
| Policy execution and Actor | `backend/app/lab/policy_interpreter.py`, `backend/app/agents/actor.py` |
| Model proposals and observations | `backend/app/agents/mechanic.py`, `explorer.py`, `progress.py`, `prompts/` |
| Evidence, costs and storage | `backend/app/lab/evidence.py`, `storage.py`, `budgets.py`, `configuration.py` |
| Task effects and checks | `backend/app/simulator/`, `backend/app/referee/`, `backend/app/adapters/` |
| Portability and reruns | `backend/app/integrations/registry.py`, `external_agent.py`, `regression_runner.py`; `backend/app/lab/exports.py`, `regression_executions.py` |
| Dashboard | `frontend/src/components/EvidenceScreen.tsx`, `RunControls.tsx`, `RunSummary.tsx`, `PolicyStatusPanel.tsx`, `CompletionStudyPanel.tsx` |
| Saved replay decoding | `frontend/src/completion.ts` |
| Experimental entry points | `scripts/experiments/`; read each declaration before using its runner |

The sibling original specification is `../FaultLab_Specs/specs/001-faultlab-loop/tasks.md`.
It has 234/239 checked, which is not a product completion percentage. Open items T065, T088, T097,
T100 and T102 concern learning/promotion evidence, sponsor/Aria walkthrough, final freeze,
independent transfer/selector acceptance and final audit. Judge their actual acceptance criteria;
completion studies do not substitute for original-loop evidence.

Claude's historical experiment program is `docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md`.
The broader original roadmap is `docs/part2/PLAN.md`. Neither is a binding next-step instruction.
Research new technical choices using primary documentation when helpful; no need to redo the entire
historical literature review before fixing a demonstrated product gap.

## Runtime, resources and permissions

- App root: `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`.
- Use the existing `.venv/bin/python` (3.12.8). The system Python is not equivalent for fingerprints.
- Actor: `deepseek-ai/DeepSeek-V3.1`; Mechanic/configured Explorer:
  `deepseek-ai/DeepSeek-V4-Pro-0813`.
- Actor context: `faultlab-actor-context/v4-indexed-evidence`; completion evidence summary v2.
- Confirmed destination: `shreetbohara-quinstreet/Faultlab` (capital F). Do not ask the owner to
  reconfirm it without a genuine reason. Keep credentials in the existing `.env`; do not print,
  overwrite, copy into memory/backups or commit them.
- Startup, tests, health checks and saved-evidence browsing must remain provider-free.
- Before a future paid experiment: verify current exact model availability/pricing, declare its
  budget, runtime and evidence partition, and monitor it. Existing published prices are dated,
  not perpetual truth. The user has already authorized sensible live work; avoid ritual reapproval.
- Historical carried charge is $855.91. The $144.09 remainder belongs to the old $1,000 allowance,
  not a fresh constraint after the owner's expanded authorization. Actual balance is unknown.
  Preserve all spending, including failed runs. Never reset it when switching agents/accounts.
- Close the dashboard and stop its server before paid experiments until clock isolation is verified.
  Earlier Phase 18 observer interaction corrupted experiment timing. Inspect actual processes rather
  than killing unrelated services. At handoff, ports 8000, 8001 and 5173 had no listeners.
- Aria remains deferred by the owner's earlier choice; do not imply it is verified. TypeSafe has no
  established integration contract. These should not drive unnecessary work ahead of core usability.
- No GitHub push without the owner's OK. No deployment or paid-overage setup is authorized by the
  handoff itself. Routine reversible implementation and local backup are already within scope.

Full backend check used after the last runtime change:

```sh
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.venv/bin/python -m pytest -p anyio.pytest_plugin
```

The clean full log is `artifacts/phase31-followup-2026-09-27/full-backend-hydrated.log`.
Tests are evidence, not a substitute for actual-world and UI inspection. No suite rerun was needed
for this documentation-only handoff; the quoted numbers are from the preceding completed change.

## Git and recovery — do not lose the work

The working checkout is deliberately still `main` at
`cbbf957e6e1cb19e1dcc2f87f24a33101859bbbe` (old September 14 source).
The latest implementation before this handoff is saved on local `backup/part2-2026-09-22` at
`32645edd30a01b7d7b3108db9703fd97b1a804cc`; the preceding runtime fix is `0eb7da7`.
All 625 saved source files were verified against the working folder at that checkpoint.
This handoff's documentation checkpoint is recorded separately in
`artifacts/product-continuation-2026-09-27/final-checkpoint.json` and the external backup manifest.
Recheck the branch rather than assuming this dated hash stays current.

Many Part 2 files are modified or untracked relative to old main, while already saved on the backup
branch. A naive diff can misleadingly show thousands of deletions for files main's index does not
track. **Do not reset, clean, check out the backup branch, stage everything or overwrite files.**
Preserve the real index. Its logical `git ls-files -s` SHA-256 before the handoff is
`34a77879bf2b787ace8cfc9cccf85972552028f4c617db4ad216072b16e9062f`.

Safe local checkpoint helper, with explicit repository-relative file paths only:

```sh
artifacts/phase22-2026-09-24/prep/commit_to_backup.sh "Descriptive message" path/to/file another/file
```

It uses a temporary index and guarded backup-ref update, verifies that HEAD and the real index did
not move, and does not push. Inspect it before use. The app source clone does not include roughly
4.5 GB of ignored experimental stores/worlds. Do not confuse a source backup with an evidence backup.

Verified recovery folders outside iCloud-backed Desktop:

- `/Users/shree/FaultLab_Backups/2026-09-27/product-continuation/`: this handoff's source bundle,
  current entry points, detailed notes and verification manifest.
- `/Users/shree/FaultLab_Backups/2026-09-27/phase31-followup/`: source through 32645ed, both offline
  diagnostic worlds, reviews, logs and the saved dashboard screenshot; 63-file manifest.
- `/Users/shree/FaultLab_Backups/2026-09-27/prospective-repair/`: all 318 worlds, 11 closed stores,
  declarations, audits and source bundle; 380-file evidence backup.
- `/Users/shree/FaultLab_Backups/2026-09-27/followup-verification/`: the earlier two experiment stores
  and 58 episode worlds.
- `/Users/shree/FaultLab_Backups/2026-09-26/lab-after-phase28.sqlite3`: preserved main store.
- `/Users/shree/FaultLab_Backups/2026-09-27/phase31-source-inspection.git`: bare local inspection
  repository used for bundled source verification, not a working checkout or upstream remote.

Desktop source, Git objects, dependencies and SQLite files previously became iCloud `dataless`
placeholders. This produced nine false suite failures/errors reading the main database. Native
download restored the files; the same tests then passed, without weakening/skipping them. All 241,000
main records and 142,417 events matched the preserved backup; the 11 closed experiment stores were
byte-identical. The frontend was restored from its existing lockfile, with no version changes.

If a file exists but cannot be read, check local availability (`ls -lO` may show `dataless`) before
declaring corruption. Do not overwrite originals from backup or change global iCloud settings as a
first response. Consider durable non-cloud runtime storage as product work, with a deliberate,
verified migration. Do not blindly move this whole workspace or lose ignored evidence.

## Handoff contract

Keep historical results and failed attempts unchanged; append corrections as new notes. Preserve
all local work, keys and backups. Verify source fingerprints under the right interpreter. Report
what was observed separately from inference and what remains unproven. Keep CURRENT_STATUS.md
current so the next user update does not require reconstructing thirty phases again.

Use judgment. The goal is a useful and trustworthy product, not obedience to this document.
