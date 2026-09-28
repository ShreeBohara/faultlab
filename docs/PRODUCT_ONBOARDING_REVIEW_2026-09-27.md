# Reviewed campaign setup and selected-agent execution — September 27, 2026

Implementation and verification are complete for this increment; CURRENT_STATUS.md remains the entry point.
Final runtime: `d1845765fa1c120ad4afd936461ddb4e4d909972209b160d6eebd63d6b3c64fb`. The earlier durability
checkpoint and every closed experiment retain their original source identities and results.

## What the workflow review found

The old ordinary campaign flow always rebuilt the reference agent. A user could inspect an external
agent registration without that agent actually owning every learning phase. The task text also looked
more general than the one implemented order workflow, and selecting a reproducible public fault case
required research code. Finally, a run that found no repair lacked an obvious complete recording download.

The new flow is: inspect the local setup, explicitly register a reviewed agent for live work, choose the
supported task and mode, save an idle immutable plan, review it, then start. Baseline selects one of six
public development cases. Learn uses the bounded development search. Compare needs an accepted policy
for the exact selected configuration. Creation, registration, history and plan previews make no model
calls. Native and reference agents share the same task, tools, fixed scorer and episode limits.

One central execution resolver now keeps the selected actor in discovery, reproduction, reduction,
diagnosis, repair validation, challenge and promotion. The handwritten B1 reference remains a separate
control with its own execution identity. The native package still owns its reasoning, memory and parser;
FaultLab does not repair a bad native answer or secretly substitute a reference answer. Reference-only
research studies fail before native execution. Native audit freezing validates the saved plan; independent
portability requires a different reviewed implementation, before creating a study or reserving work.

## Integrity and accounting

The API-local plan schema leaves the exported task contracts unchanged. Each plan binds task/order,
configuration/registration, case recipe and fixture (or search/partition identity), initial policy,
episode/campaign limits and a content digest. Provenance binds that plan. Tampering or losing a marked
plan blocks execution. Old unmarked campaigns keep their legacy behavior; archive reads verify saved
bindings without demanding today's source identity. Setup and registration are checked before writer
construction, then checked again in the create transaction. Slow setup reads cannot block Stop.

Provider-integrity negatives found FaultLab defects: a native response from the wrong model was not
rejected before tool dispatch; the native library could swallow a transport failure; and partial known
costs could be displayed as a complete cost after an unknown or cancelled request. These are now typed
lab failures with retained usage and no extra provider attempt or world action. Unknown cost stays
unknown. The provider request protocol, prompts, package, report, scorer and limits are unchanged.

## Manual evidence

The actual dashboard registered both sources without provider calls, then created and separately started
six offline reference campaigns in `/Users/shree/FaultLab_Runs/2026-09-27/product-onboarding/offline-01`.
These cases ran under runtime `763b80d636b82e48b98f73aba038a8a8ea90da154aa20ee172725eae04952856`.
Five tasks completed; the rejected upgrade was correctly reported and sent no confirmation. All five
scheduled fault recipes fired. These are deterministic smoke measurements, not live model performance.
Each case used its saved recipe and fixture, including the historical order's version-four start.

An actual browser JSON download exactly matched the public API recording. The browser tool's download
wait timed out even though the file was saved; the real downloaded file was independently read and
verified. A real process stop/restart preserved all six recordings, 138 records, 64 events and six policy
pointers exactly, with six worlds and zero model calls. Manual testing exposed a stale history status;
the current campaign now updates its matching history row without losing pagination or adding polling.

Fresh native scripted-provider fixtures cover the complete original flow: an accepted case plus fresh
comparison (124 worlds), a rejected repair (28), and an interrupted run (one). Independent raw SQL audit
passed 2,324 comparisons across all 153 worlds. The accepted candidate had 45 completed tasks and six
correct rejections; baseline and rejected-candidate C3 failures matched actual premature confirmations.
Stopped work retained the delayed upgrade and did not send a notification or invent a report. All
clock records were valid, original submitted reports were preserved and the audit changed no files.
These fixtures establish the wiring and gates. Their scripted repair is not a generated accepted policy.

## Verification and remaining limits

Focused API/plan/archive checks passed 55 tests. Selected-agent, provider and legacy-loop checks passed
48 tests, and native provider/package contract checks passed 30 (overlapping groups). Frontend passed
219 unit tests, production build and ten browser fixtures, with one opt-in actual-backend test skipped.
The roughly 502 kB minified / 119 kB gzip bundle produces Vite's size advisory. No dependency was changed.

The first full suite in the isolated checkout was stopped after missing archived settings and freeze
records caused environment errors. Five old context-selection test stubs were made into valid Campaign
objects; every early-rejection/no-world assertion remains. The final full run used the original checkout,
where preserved historical assets are available: **2,224 passed, 180 existing skips, zero failures** in
791.81 seconds. Two warnings: Starlette's deprecated alias and the explicit fork ownership test. Source
fingerprints were unchanged before/after. Native freeze/independence/operator/recovery checks also passed
66 focused tests; the valid operator fixture now uses real reference→native registration.

Independent actual-manual audit passed 160 checks. B1's handwritten report is persisted directly, with
no model answer or separate report_submitted event; the audit verifies its physical effects, receipts and
citations. A final d184 dashboard run passed 13 direct checks, audit freezing performed no execution, and
archive mode opened the older 763b plans without changing seven DB hashes or modification times. All
31 historical result documents, the 901 MB main store and eight closed live DBs remain unchanged. Services
are stopped. The local source/evidence recovery checkpoint is recorded in
`artifacts/product-onboarding-2026-09-27/final-checkpoint.json`; external copy:
`/Users/shree/FaultLab_Backups/2026-09-27/product-onboarding/`.

This remains one synthetic task and two reviewed agents. Source conformance does not establish model
quality or provider access. A public recording is an evidence archive, separate from an executable
regression bundle. No new live inference, generated-policy acceptance, unseen-case success or accepted
policy transfer is claimed. Existing public cases cannot become unseen simply by changing their seed.
Aria remains deferred. The closed live original campaign remains NO_CHANGE and has not been resumed.

New provider requests and cost: **zero**. Carried conservative spending: **$856.96**; provider-billed
historical dollars remain unavailable. All prior source, stores, failed results and secrets are preserved.
No GitHub push or deployment.
