# Product core review — September 27, 2026

Status: core fixes implemented and verified; broader product milestones remain open. This is a new product review, not a
correction to closed experiment results. No paid provider calls have been made; carried
historical accounting remains $855.91. No GitHub push.

## Core workflow traced

| User action / engine stage | Actual path | Acceptance evidence and remaining gap |
|---|---|---|
| Connect task/agent | Registered order task, frozen campaign configuration and reviewed agent registry | Shop task is implemented; task text does not install arbitrary tools or a new task. Native smolagents has historical live baseline evidence; repaired-policy transfer is unproven. |
| Create and start | Dashboard → campaign API → coordinator admission → fresh world and Actor | Local and live modes are explicit. Creation freezes models, source, budgets and context. Final-runtime dashboard smoke and direct world reconstruction passed; this is reference plumbing. |
| Find a failure | Explorer → bounded fault proposal → Actor → unchanged C1–C8 Referee | No violation or an untriggered fault cannot become a repair target. A failed local transport can desynchronize clocks; new integrity guard classifies it LAB_ERROR, retaining the original report/effects. |
| Reproduce and reduce | Three fresh source trials → fixed finite reducer | Uses the same violated rule, retains attempts and reduction scope. Flaky or incomplete reduction does not qualify. |
| Diagnose | Mechanic chooses a declared intervention → fresh control/treatment → fixed classification | Policy gap, evidence gap and inconclusive remain distinct. No model explanation alone qualifies. |
| Propose and qualify | Bounded JSON policy → repeated source pairs | Fixed: all retained scored candidate violations veto qualification, including attempts from replaced pairs. |
| Challenge and decide | Fresh challenge pairs → independent fixed promotion → atomic pointer update | Same retained-failure rule now applies at challenge and promotion. Generated accepted policy still not established; positive fixture decisions are plumbing evidence only. |
| Inspect and stop | Dashboard timeline, world-derived verdicts, before/after comparison, Stop | Fixed: Stop targets owned active work; passive reads and encoding run in workers. |
| Reopen and export | Campaign ID, saved recording, incident bundle/download | New bounded campaign and regression-execution selectors replace routine ID copying; manual IDs remain available. |
| Fresh regression | Reviewed registry/bundle → explicit fresh execution → new worlds | Distinct from playback; transferred immutable identity is checked. Historical live baseline regression exists; accepted-repair transfer remains unproven. |
| Restart | Interrupt unfinished work; preserve policy and uncertain effects | Incremental batch/request records, bounded cleanup and interrupted-job recovery preserve effects/charges. No automatic replay or resumption. |

## Decisions

Fix evidence integrity before buying more experiments. A tested agent's real, scored violation
must remain a veto even when the opposite arm needs an infrastructure retry. Conversely, a lab
clock/admission discrepancy cannot be treated as an agent mistake. Keep the original report,
effects and charged attempts, flag the infrastructure failure, and exclude that trial from
qualification. Do not change the scorer, force a tool call or rewrite an answer.

Make routine navigation possible without research-script IDs. List saved campaigns with a
bounded stable cursor, retain manual ID loading, and make Stop apply only to owned active work.
Move passive saved-record reads and their serialization to worker threads so they do not block
the scheduler event loop. This is a specific isolation improvement, not a claim of unlimited
load capacity or support for multiple backend writers.

## Further integrity and lifecycle decisions

New heldout plans freeze `world_integrity_protocol: faultlab-world-integrity/v1`. The unchanged
legacy no-harm calculation is retained as diagnostic data when a verified invalid world exists.
Invalid worlds in either arm prevent NO_HARM; their unreliable check failures alone do not establish
HARM. Genuine candidate check failures from other worlds still count, including previously supported
world-state failures on interrupted or infrastructure-error trials. Both ordinary finalization and
restart apply the same boundary. Plans without this marker keep the historical interpretation.
Completion studies already require complete valid pairs before assessing candidate checks.

Each evaluation now persists a returned trial before another action or telemetry call. Queued
comparisons retain their job and batch IDs even when initialization fails. Errors/cancellation keep
partial batches INCOMPLETE. Regression interruption keeps saved world/episode links, and restart
releases only the abandoned reservation, retaining charged usage. Resource-close failures cannot
strand active admission or overwrite a prior STOPPED result. Interrupted original-loop campaigns
release known ephemeral reservations and close unresolved qualifications; protected reserves,
unknown reservation names, and terminal historical runs remain unchanged.

## Verification record

The final full backend check passed. Evidence is saved to `artifacts/product-core-2026-09-27/` in fresh isolated
stores and worlds. `before.json` records the original runtime, main commit, index digest,
local backup checkpoint and hashes of 31 historical result documents before edits.

Tests, offline/reference executions and real model experiments will be listed separately.
No offline fixture will be reported as a generated accepted repair or remote Weave verification.


Read-only historical audit (`historical-candidate-audit.json`): 241,000 main-store records and
142,417 events. Thirteen original-loop batches (12 source validation, one challenge), 78 trials,
39 candidate attempts and 21 scored candidate violations. No candidate violation was outside its
retained pair. Two other promotion-purpose batches belong to separate heldout checks; no original
promotion batch or ACCEPTED policy exists. All 294 active pointers remain baseline. The latent gate
bug was demonstrated with controlled offline fixtures, not an observed historical bad acceptance.

Manual real TCP clock evidence lives in `clock-audit/`: six fresh worlds across before/after healthy,
refused-connection and F1 response-loss cases. Before/after tests substitute the runner module only,
not a complete historical runtime. The original and corrected reports both truthfully describe one
upgrade and one notification. Genuine F1 and healthy runs remain COMPLETED; a deliberately incorrect
agent ordering still fails C3. New paid requests: zero.

Real dashboard/API verification uses separate `manual-local/` storage and no credentials. A fresh
reference run produced one upgrade and one confirmation; direct SQLite reconstruction agrees with
the displayed report, 3 decision ticks, 8 horizon ticks and all eight passing checks. Campaign history
loaded 20 then 22 rows without new episodes. Provider-free readiness reported simulator ready and
missing live settings. A selective read-only copy of one historical regression is used only to
verify the saved-execution picker; copied history is never counted as new execution.

## Final-runtime manual checks

Runtime: `58cd13b6f966d5b1c789fde7de9ca4bbdf744b2335bca25d9f3930e57e14f357`.
`manual-final-verification.json` records campaign `campaign-f06692f76bb64ba9b0f49fdef2929849`,
episode `episode-d7e38b38813844cfba44cc9fb2159132` and world
`world-8b12df68660e4af58d66f427364127e6`. This fresh run was created and started through the real UI.
The world contains exactly one upgrade and one notification, three admitted HTTP attempts, decision
clock 3 and observer horizon 8. Its original report says COMPLETED; all eight unchanged checks pass
and the new integrity record is VALID. Zero model calls. Screenshot: `manual-final-run.png`.

The saved regression picker loaded five exact-bundle executions and opened
`execution-dcf7936ab295477fb7588f38584f8bbe`: three original trials and 24 historical model calls.
Those calls were not made again. Original trial evidence was reachable through its episode button.
All 25 copied payload entries still match their original hashes; browsing created no worlds or
executions. The isolated store contains two new reference worlds total, one during development
and one under the final runtime. It also contains copied history, clearly excluded from new counts.

Frontend final verification: **192 tests passed**, build passed; **six browser checks passed**,
one opt-in real-server check skipped. The manual real-server check above ran separately. Focused
heldout/world verification: **104 passed**. Lifecycle/gate verification: **69 passed**. These focused
counts overlap the full backend suite and must not be added to its total.

## Remaining product work

The next priority is a declared end-to-end original learning run that tests useful repair quality
under this corrected runtime, with fresh evidence and explicit spending/exposure accounting. A
rejected or incomplete repair is a valid result; it cannot be relabeled acceptance. Existing live
results belong to older runtimes. Before paying, review why the existing source qualification rejects
repairs and the known notification/reporting evidence; do not simply repeat spent partitions.

A second task and accepted-repair transfer to an independent agent remain unproven. General task
onboarding needs a real tool/referee contract, not just editable task text. Keep the local product
single-backend: threadpool reads improve responsiveness, but a shared SQLite lock, startup scans and
multi-process ownership still need an operational boundary. Durable non-cloud storage should be
introduced through a verified migration, preserving the existing evidence and recovery copies.
Selector-search request history also still lacks a durable initial QUEUED record. None of these
remaining items is concealed by passing tests or the saved demo.

## Complete verification and recovery

One frozen-source backend invocation: **2,010 passed, 180 existing skips, zero failures, one existing
dependency warning in 714.97 seconds**. Full log: `full-backend.log`; machine-readable result:
`full-backend-result.json`. No extra skip or weakened historical predicate was used to obtain the pass.
Runtime was checked again after the suite and matches the fresh manual campaign's frozen configuration.

`preservation-verification.json` verifies all 31 prior result documents, the main database's complete
SHA-256, old main commit and real index. `spending.json`: zero new provider requests/$0, carried
historical $855.91; actual provider balance is unknown. The 24 saved regression calls shown in the UI
were not made or charged again. Temporary backend/simulator/Vite processes and browser tab are closed.

The local backup branch checkpoint and complete source-tree comparison are recorded in
`final-checkpoint.json`. External recovery copy:
`/Users/shree/FaultLab_Backups/2026-09-27/product-core/`, containing a self-contained Git bundle,
new offline stores/worlds, logs, screenshots, current notes and a verified manifest. Existing backups
were preserved. No secret file was copied and no GitHub push was made.
