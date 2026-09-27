# Final-report handling — September 27 follow-up

The final-report defect is fixed and has been reconstructed offline using the original model
answers. This is a software correction, not a new live repair result. The latest reserved
evaluation remains **INCOMPLETE**, and `policy-v0` remains active.

## The defect and the change

A rejected development policy first requested a safe unresolved answer with `defer_unresolved`.
That closed further business actions. The model then returned a real report, but the policy's
`before_final_report` hook attempted another status read. The business meter rejected the read,
and the report never reached the Referee. The runner's generic missing-report message obscured
what happened. The model had not returned an empty answer.

When business work is already closed, a final-report hook now skips its business reads, waits
and retries. It still charges each reached policy step and evaluates applicable receipt guards.
It does not reopen business work, add time or model calls, or rewrite an answer. An unsupported
success claim remains blocked. Hooks outside final reporting retain their existing behavior.

Other exhausted report-hook limits now retain an explicit failure reason and the original
Actor output. A report blocked on the final available turn also gets a precise reason. Stop
requests and cancellation still propagate. The fixed Referee remains responsible for judging
the submitted report and actual effects.

Changed runtime files: `backend/app/agents/actor.py` and
`backend/app/lab/policy_interpreter.py`. The scorer, `assess_pairs`, promotion rules, contracts,
Actor prompt, context protocol, business broker, budgets and runner are unchanged.

## Independent reconstruction, outside the test suite

The captured source is development episode
`episode-b83c6a5aa0024791a4974e084da8f516`, policy
`56802093fbaf200616435dc845f6b5ca81228f414290ec2f60d45cafb609ef11`.
Its recipe and three original answers were checked against the closed evidence backup.

Two fresh simulator worlds replayed those answers: one with the two original implementation
modules from source checkpoint `5f6f151`, and one with the corrected modules. Only the allocated
operation ID in the third answer was substituted for the new world. No model generated an answer.

| Observation | Original modules | Corrected modules |
|---|---|---|
| Original final answer retained locally | Yes | Yes |
| Final report submitted | No | Yes, original emitted fields preserved |
| Fixed verdict | VIOLATION: C5, C6, C7 | SAFE_UNRESOLVED; all eight checks pass |
| Actor answers / HTTP attempts / ticks | 3 / 6 / 7 | 3 / 6 / 7 |
| Charged policy steps | 9 | 10, including skipped read and evaluated guard |
| Upgrade effects / confirmation effects | 0 / 0 | 0 / 0 |
| Active policy | `policy-v0` | `policy-v0` |

The corrected result is honest non-completion, not a completed customer task. These are
isolated diagnostic records, not replacement historical trials. Their campaign metadata is
created by the current application; the before/after comparison explicitly substitutes the
two modules. It must not be presented as an execution of an old frozen live campaign.

Local proof is in `artifacts/phase31-followup-2026-09-27/`: `manual_reconstruction.py`,
`manual-comparison.json`, and both `manual-before/` and `manual-after/` directories, including
fresh world databases, event records, snapshots and original answers. The regression fixture
and tests are source-controlled; local databases are not part of a normal Git clone.

## Verification

The 32 new parameterized regression cases cover all five business I/O operations, both receipt
guards in either order, honest and unsupported reports, false conditions, open hooks, other
hooks, policy-step exhaustion, deadline expiry, stop, cancellation, the eight-turn ceiling and
the captured failure through the real runner, broker, simulator and scorer.

- Focused suite: **45 passed**, including existing citation-boundary and interpreter cases.
- Independent source review: no blocking findings; the reviewer also verified the saved fixture
  against the original evidence and ten unchanged surrounding runtime files.
- Full backend result after database hydration: **1,952 passed, 180 existing skips, zero failures**,
  one dependency deprecation warning, in **697.17 seconds**, from one complete invocation.
  Local log: `full-backend-hydrated.log` in the follow-up evidence directory.
- Frontend: 166 tests and production build passed after restoring the same locked dependencies.
- Manual dashboard rehearsal: loaded the real successful development study, checked its
  qualification and active baseline, and opened the original baseline/repair trial pair.
  The baseline showed zero effects and SAFE_UNRESOLVED; the repair showed one upgrade,
  one confirmation and COMPLETED. Both displayed all eight passing checks.

The demo used a disposable copy of attempt 10's verified backup, live calls disabled, no loaded
credentials and a middleware guard rejecting writes. A direct write probe returned 405
`SAVED_EVIDENCE_ONLY`; copied records remained identical to the source. No simulator or model
service was needed to display saved results. See the [demo guide](PHASE31_DEMO_GUIDE.md).

Manual inspection also found a misleading sentence in the main-loop summary: it said no candidate
had been generated anywhere in the campaign while a separate completion study had generated one.
The sentence now explicitly says no **main-loop** candidate is recorded and points to the separate
study panel. This changes explanatory text, not stored records or qualification decisions.

Some Desktop files and dependencies were iCloud placeholders. Requests for native downloads
restored runtime dependencies and the main database. The first full-suite invocation ended with
1,943 passed, 180 skipped, three failed and six setup errors: all nine affected tests could not read
the same cloud-placeholder main database. An unchanged historical-data check then passed against
the downloaded original, and the complete suite then passed. No test was weakened or newly skipped
for that condition. The failed invocation remains preserved in `full-backend.log`.
The frontend's ignored dependencies were restored from its unchanged lockfile. The source
backup and original evidence were never overwritten with substitutes.

All 619 previously saved source files were compared: six intended existing files changed and
the other 613 matched, including all historical reports. New tests, their captured fixture and
the four new documents are additional files. All 241,000 records and 142,417 events in the main
store match its preserved backup, and all eleven closed experiment backup stores remain
byte-identical. Local source/evidence backup details are in `CURRENT_STATUS.md`; nothing was pushed.

## Runtime and evidence boundaries

New runtime:
`b9410f5e77f2b98e6a621ee5adabc20c7ac65ea042f8a9d7049dedadaec7d719`.

The last live experiment used:
`3da193e30a71ea4aebc8309580548c09ece3fb31d4ccd8a8529112b8f8b9a9d8`.

The freeze comparison confirms all measured gate functions are unchanged. Runtime, interpreter,
agent-source and lab-tree identities change as expected. Future paid experiments must explicitly
freeze and evaluate this new version. Historical experiments cannot be resumed or repinned to it.

This follow-up makes **zero paid model calls**. The carried shared charge stays **$855.91**,
with **$144.09** remaining under the existing $1,000 accounting ceiling. This is conservative
local accounting, not a current account balance or provider invoice.

## Next decision

The [Phase 31 write-up](PHASE31_WRITEUP.md) and demo now describe the evidence actually obtained.
Repeated polling of a never-started notification remains a separate Actor problem. Earlier v2/v3
progress hints already produced reporting regressions; adding them to v4 is not an established
solution. The [notification review](NOTIFICATION_PROGRESS_REVIEW_2026-09-27.md) lays out a narrower
future experiment with an explicit write-attempt record, reporting guards, all-attempt accounting
and declared handling of missed fault exposure. That experiment is not implemented or launched here.

No generated policy is accepted or activated. Original learning-loop promotion, accepted-repair
transfer, Aria and the final product acceptance audit remain separate open requirements.
