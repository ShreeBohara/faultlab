# Dashboard import and rerun — implementation review

Status (September 28): implemented in the main folder, reviewed by three independent $0 reviews, and every
review finding fixed (see *Review fixes* below). Not yet committed; the declared paid validation has not run.
This is a product increment, not a claim of whole-product completion.

## What was missing

The dashboard could download existing regression bundles but could not bring them into another local
workspace. The CLI upload combined import with a paid execution, leaving no saved review stage. Imported
policy versions could collide with local names. A technical reference campaign held execution budgets,
although the actual selected target could be the native adapter; that ownership must not be presented
as the actor identity.

## Chosen behavior

A downloaded regression ZIP is saved as immutable imported data after bounded structural validation.
The app executes none of its Python or supplied paths. Review shows the exact task and order the rerun
will send (and whether the bundle recorded them), how the source trials were produced, policy, trials and
original public evidence, labeled historical and not independently verified locally. Import never
activates a policy. Imported records can be reopened without selecting a campaign, including in archive
mode. Development recording JSON remains a different, non-runnable artifact.

The operator separately selects a locally reviewed registration and requests a fresh regression.
The server rechecks source, store and target identities, reserves a bounded run, and records a durable
request identity. Repeating that same request returns the same execution; it cannot launch another
paid run after a lost response. An intentional new run gets a new request identity and fresh worlds.
The actual target model/configuration is shown separately from the campaign holding its budget.

Imported policies receive distinct local IDs at execution time, retaining their exact content/hash and
source decision. Historical ACCEPTED never becomes local acceptance; existing active-policy pointers
remain untouched. Local episodes resolve their actual executed policy, not a foreign same-name policy.

## Acceptance evidence to collect

- Actual browser import of a saved ZIP, source/report review, reload and reimport without duplicate data.
- Clear rejection of development recording JSON, tampered files and unsupported/oversized ZIP contents.
- Provider-free import/review, readable archive, explicit fresh execution only after current target review.
- Missing/stale identities and duplicate/retried execution requests fail closed or return the same run.
- Independent reconstruction of saved episodes, worlds, effects, reports, fault exposure and charges.
- Focused negative-path tests, complete backend suite, frontend tests/build/browser fixtures.
- Immutable historical reports/databases, unchanged main/index, explicit local backup; no push.

## Review fixes — September 28, 2026

Three independent $0 reviews (security, semantics, first-time use) returned READY_WITH_CHANGES. All findings
were fixed; none was declined. Evidence: `/private/tmp/…/scratchpad/import-0928/fixer/` (session scratch).

- **The review did not show the task the paid run sends.** The rerun used `execution_task` from the bundle
  while the screen showed a fixed "Supported task" label, so a bundle could put any instruction into every
  Actor prompt unseen. Now the review and the run button show the exact task, order and origin (bundled
  or FaultLab default); the run needs a separate confirmation that repeats target, task and spending
  bound. Import refuses a malformed task (not 1–2,000 non-blank characters, or an order that is not an ID).
- **Unchecked evidence fields.** A non-ID source registration (number, empty, object) was saved and made
  the whole saved-imports list unreadable; a string `agent_registration` caused a misleading 503. Import
  now refuses both as *Contents do not match*; older malformed summaries are shown as "not recorded", and
  the dashboard skips (and counts) any unreadable summary instead of hiding every import.
- **The accounting owner admitted other paid work.** Baseline, completion, context and held-out studies
  set the active campaign directly and skipped the owner check. One shared guard now refuses the owner
  before any write on every admission path (studies, held-out check, search comparison, comparisons,
  final audit, portability, freeze-and-portability, CLI freeze, ordinary regression rerun). The earlier
  claim that the owner "cannot be started" was true only for Start; it is now true for all work.
- **The ordinary regression route wrote before refusing an owner** (an export directory and a VALIDATE_ONLY
  record). It now refuses owners, and reviewed-import aliases, before exporting or validating anything.
- **Usage after a crash mid-trial read zero.** Recovery now reports at least the owner ledger's charges,
  and every fresh result shows *Charged to its accounting ledger* (complete, including retries).
- **An infrastructure failure inside the trial loop left no error record.** The fixed runner now saves a
  classified error (code, class, code location; never raw text), shown as an infrastructure error.
- **The 24-call reservation did not bound transport retries.** One reference-agent run can make 24 actor
  turns plus at most 24 charged retries; a hard ceiling of 48 requests per execution is now enforced in
  the owner's ledger (budgets.py is part of the frozen interpreter fingerprint and was left unchanged).
- **Older CLI imports without a policy marker** are now recognized (read only) by every local acceptance gate.
- **Any Host header was accepted.** The backend now answers only `localhost`, `127.0.0.1` and `[::1]`, and
  refuses writes from a foreign browser Origin (DNS rebinding, cross-site pages).
- **First-time use.** Source trials are labeled (for example *Offline scripted fixture, no model calls*);
  refusals appear directly under the file chooser and start with *Import refused; nothing was saved.*;
  the Save hint appears only for an acceptable file; a disabled run lists each actual blocker and what to
  do; the offline smoke registration is no longer offered as a target, and stale targets say why; cancel
  and re-save confirm what happened; trial tables stack at phone width; each fresh result has a plain
  verdict for its artifact kind; the owner's Run desk receipt shows this execution's budget.

Verification after the fixes (runtime `cfe5ac07…`, $0, no provider calls): 44 new backend tests (40 of them
fail on the pre-fix code), full backend 2,363 passed / 180 existing skips / zero failures; 12 new frontend
unit tests and one new browser test; frontend 254 unit tests, production build and 13 browser fixtures
passed. A manual scratch-store check repeated import → review → confirmed fresh rerun (scripted native
target), the refusals, the owner refusals over the API, archive reopening and the local-host guard.

## Later runtime changes and a second review — September 28, 2026 (addendum)

The verification above is for runtime `cfe5ac07…` and is **historical**. Later the same day the hardening
work (runtime `bb87c764…`) changed the simulator identity — service `3ce5bcd2…` → `f70c8fb1…`, contract
`6f9d7783…` → `1099eda7…` — then discovery v2 (`9f53eb8c…`) and the review fixes (`c9b1b7e6…`;
simulator and contract unchanged) followed.

**PM decision, later on September 28: that simulator identity change is reverted.** Compatibility of
previously exported bundles and existing registrations matters more than a control-capability file
created at import time, so `backend/app/simulator/main.py` was restored to its checkpoint (`8e497da`)
bytes. Current runtime **`c0a8aad7…`**; simulator service `3ce5bcd2…` and contract `6f9d7783…`, the
checkpoint values again. Therefore:

* bundles exported under the checkpoint simulator (contract `6f9d7783…`) can be rerun again. Checked in the
  real dashboard at $0 (scratch store, scripted native target): the restored download was reviewed as
  eligible, its target as compatible, and a confirmed fresh rerun COMPLETED with 3 of 3 valid trials;
* a bundle made by the reverted build (contract `1099eda7…`; the only known one is the test fixture
  `exported-regression-other-simulator.zip`, sha256 `f2ac6a60…`) stays reviewable and is refused for
  rerun, at bundle level and per target, naming both contract identities (the message says "an earlier or
  different simulator build");
* the paid validation below uses the restored `frontend/tests/fixtures/exported-regression.zip`
  (sha256 `14e53310cde9a3f6f985eb6bc4ac9fa0393a2155effd518953f39699a4ecb6df`, its `8e497da` bytes, contract
  `6f9d7783…`). The earlier `exported-regression-earlier-simulator.zip` was byte-identical to it and was
  moved out of the fixtures (to the git-ignored evidence folder `artifacts/product-discovery-2026-09-28/fixer3-0928/moved/`);
* both targets must still be **registered again** under the current runtime: a registration records the
  whole-backend `runtime_hash`, and that changed after every earlier registration (discovery v2 and the
  review fixes changed `backend/app`), even though the simulator and contract part matches again.

A second $0 security review found one FaultLab display bug here: variation selectors (U+FE00–FE0F,
U+E0100–E01EF), U+034F and other invisible combining characters in a task were shown as ordinary text with
no marker, warning or escaped copy, and hidden characters on collapsed blank lines vanished from the
display and the count. The dashboard now marks every default-ignorable character (one emoji presentation
selector directly after a visible character excepted), counts every hidden character on collapsed blank
lines, and shows the warning and escaped copy whenever any are present, in the review, the paid-run
confirmation and the saved plan. The builders' claim that "every character is shown" was overstated
before this fix. See `CURRENT_STATUS.md` for the current verification counts.

## Prospective live verification

After source freeze and offline checks, use the saved compatible scripted C3 incident fixture on each
supported real-model target (reference, then native smolagents), three fresh trials per target. Worst
case per run: 24 actor turns, plus up to 24 charged transport retries for the reference agent only (the
enforced per-execution ceiling is 48; native smolagents makes no retries), so 72 requests across both
targets. To hold the earlier 48-request total instead, the declaration must set FAULTLAB_MODEL_CALL_CAP=24
and a matching dollar cap for each execution; retries are then refused and a transport failure ends that
run INCOMPLETE. The owner chooses before dispatch. This validates importing and rerunning a declared known case. It is neither
unseen-case evaluation nor accepted-policy transfer, and the source fixture remains explicitly scripted.
Stop on infrastructure failure; preserve failed/partial attempts. Do not repeat to seek a favorable result.
Exact source, artifact, target, settings and budgets will be declared before dispatch.

Provider readiness: one non-generating model-list request confirmed DeepSeek V3.1 availability.
[W&B pricing](https://wandb.ai/site/pricing/inference/?q=tables), checked September 27, 2026, lists
$0.55 input / $1.65 output per million tokens; no cache discount assumed. Actual billed costs remain
unknown. Current new generation requests: zero. Historical conservative carried cost: $856.96.
