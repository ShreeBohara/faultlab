# Local Python decision agent — October 8, 2026

Status: complete locally. The final backend suite passed **3,127 tests**, with 234 existing
skips and two deprecation warnings, in **20 minutes 15 seconds**. The separate-checkout
consumer workflow, manual report review and independent saved-world checks passed.

## Delivered workflow

A developer can select a self-contained Python file outside the checkout, run its
`decide(request)` callback through the existing orders Actor and tools, inspect the
result, change the file, and rerun the same scenario. The portable pytest test requires
the candidate path explicitly. An incident's contents never select executable code.

See [the runnable guide](local-agent.md) and [architecture decision](ADR_LOCAL_AGENT_2026-10-08.md).

| Candidate / control | Fresh trials | Observed result | Actual upgrades / confirmations per trial |
| --- | ---: | --- | --- |
| Outside file with faulty confirmation enabled | 3 | C3 and C5 violations in every trial | 0 / 1 |
| Corrected outside file, same scenario | 3 | PASS in every trial | 0 / 0 |
| Corrected file, healthy task | 1 | PASS; task completed | 1 / 1 |
| Healthy task followed by a shutdown crash | 1 | INCOMPLETE; final report withheld | 1 / 1 |

The unsafe and corrected files have distinct source hashes. The original scenario manifest
remains identical. The three fresh candidate trials are separate from the earlier scripted
source incident and its reproductions. This milestone does not discover a new fault or
establish a generated repair.

## Execution and evidence

The parent retains the existing Actor, tool broker, simulator, EpisodeRunner, baseline
policy, fixed checks and RegressionRunner. Only decisions come from the selected file.
Each trial gets a new child interpreter and working directory; module state can persist
within that episode but cannot carry into the next trial.

Source bytes are snapshotted before import, with source, bridge, interpreter and scenario
identities recorded. The scenario is copied and checked against its initially validated
manifest before creating any world or starting any child. Execution uses that snapshot;
the exported copy and saved execution must have the same manifest.

The worker receives serialized public Actor messages, including delivered observations and
turn limits. It receives no private world state, fault recipe, control token, store object
or evaluator object. The legacy reviewed-adapter registry remains closed to arbitrary source
selection. The separate local execution record identifies the user-supplied decision code.

Responses must satisfy strict JSON framing, request identity and the existing action schema.
Timeouts, malformed responses, extra output, crashes and cancellation are nonretryable local
execution failures. A provisional final report is delivered to the Actor only after a clean
exit and end of output. A late crash retains the validated action with `WITHHELD` status;
the run remains incomplete and already committed business effects remain visible. The
accepted original-report field is empty in that case; the raw withheld action is in the
local process evidence. Failure messages do not include raw child diagnostics.

The Python process uses a clean environment and `-I -S -B -u`. The audit guard catches common
accidental network, subprocess and filesystem escapes. It is not an operating-system
security sandbox. Only trusted, standard-library, single-file programs are supported.
FaultLab-managed provider calls and spend are zero; activity or spending inside arbitrary
user code is unknown and explicitly recorded as such.

## Verification

Evidence root: `/Users/shree/FaultLab_Scratch/2026-10-08-local-agent/`.

| Check | Saved result |
| --- | --- |
| Local-agent consumer, source, child-process and CLI tests | 29 passed; `local-agent-double-cancel-final.log` |
| Existing listener classification / program-label checks | 3 passed; `listener-case-normalization.log` |
| Independent locked backend installation | Python 3.12.8, backend-only setup; `fresh-install.log` |
| Copied scenario and separately supplied candidate | All 8 expected command outcomes; `acceptance-final/verification.json` |
| Frontend tests / production build | 373 passed / build passed; `frontend-verification.json` |
| Browser fixture checks | 19 passed, 1 opt-in skip; `frontend-verification.log` |
| Real-backend offline browser smoke | 1 passed, zero model calls; `browser-health-verification.json` |
| Full frozen backend suite | 3,127 passed, 234 skipped, 2 warnings; `backend-release-verification.log` |

The separate-checkout acceptance ran inspect, unsafe/safe checks, healthy completion,
unsafe/safe exported pytest, missing-candidate refusal, and the late-crash negative control.
The test intentionally fails for the unsafe candidate and passes after correction. Parent
network sockets, `.env` reads and original-store reads were refused during acceptance.
The actual child-process tests separately exercise its environment and audit guards.
No credentials or historical stores are needed; backend-only setup creates no `.env`.

Frontend and dashboard browser verification preceded the final worker cleanup correction;
their frontend sources and dashboard execution paths are unchanged. The final backend
suite and regenerated local-agent acceptance records verify the corrected worker separately.
The frontend build retains its existing advisory about a JavaScript chunk larger than
500 kB. No dependency versions changed.

The portable archive is `local-agent-regression.zip` (25,425 bytes, 11 entries), SHA-256
`179497c54a6e8a3a7cbdc62fd59ce9beaa4e12c50197c72156206a890891a5ee`.
Its bytes match the regenerated final export (`deliverable-archive-final-verification.json`).
It includes scenario data and the installed behavioral test; the candidate is supplied separately.

Manual browser review expanded the unsafe, corrected, healthy and late-crash reports.
The unsafe trace showed the delivered rejection before successful confirmation, while the
original report claimed confirmation was not required. The corrected trace had no
confirmation effect. The healthy trace completed both actions. The crash trace preserved
those effects while displaying INCOMPLETE. See `manual-browser-review-final.json`.

An independent read-only SQLite inspection checked all eight new acceptance worlds against
their summaries: order shipping/version, committed upgrade events, confirmation rows,
operation timing and identity, saved verdicts and child-process records. It verified that
the unsafe confirmation followed the delivered rejection, and that the crash retained
its business effects and withheld final action. All checks passed; see
`manual-acceptance-final-world-crosscheck.json` and `manual_acceptance_final_world_check.py`.

A later real-process probe exposed a cancellation race: cancelling twice while the OS
process handoff was pending could leave a child running despite a cleanup-complete record.
The transport now owns the creation task before awaiting it; cleanup adopts and reaps its
result, and passing evidence requires `process_creation_complete`. The same probe passes
and a durable regression verifies PID ownership, exit, and absence of surviving tasks.
See `double-cancel-spawn-probe.json`, `double-cancel-spawn-fixed.json`, and the final
local-agent test log. The probe itself reaped its child on the failing baseline.

The obsolete candidate's full suite was stopped for that correction. Its retained log also
showed an existing test's lowercase interpreter-name assumption: a macOS framework Python
reported `Python`. The test now checks the label case-insensitively, matching the existing
runtime classifier; no runtime classification or stop condition changed. The interrupted
run is not release evidence (`backend-interrupted-before-cancellation-fix.log` and
`backend-interrupted-note.json`). Acceptance outputs under `acceptance/` and the first
manual-check records belong to the earlier candidate; the final records use
`acceptance-final/` and explicitly named final check files.

The final suite's skips concern optional historical stores and frozen experiment trees;
this source-only run does not claim to rerun those historical experiments. Its two warnings
are the existing Starlette AnyIO alias deprecation and intentional fork-based ownership test.
The original scenario fixture and all gate-related identities remain unchanged. The completed
candidate's source and test hashes were checked again after the suite finished.

The first full-suite attempt stopped at collection because the new CLI test shared an
unpackaged module basename with an existing test. Renaming it to `test_local_agent_cli.py`
resolved the collision; 3,359 tests then collected; the two later cancellation-integrity cases brought the final total to 3,361. No application behavior changed for
that fix. The initial collection log remains as `backend-collection-collision.log`.

Two earlier focused-test failures were incorrect test expectations: an order identifier
is scoped to its fresh world, and a raw child response retains public `obs-N` labels before
the Actor maps them to journal identifiers. The tests now check the correct identities
and preserve the exact raw response. Initial logs remain; neither issue required weakening
an application check. Review also added pre-execution manifest binding and explicit clean
process-exit validation before the final candidate was frozen.

## Compatibility and remaining work

Runtime: `2d2a6ddb40b0f93b3c51daf122e57b1f7f623fa8edc5b76f0653da0e489ef0e6`.
The established offline fixture module retains SHA-256
`22b3ea5d49057bf19f5b6637e530a457243a5014f1fccd4b7623f7f10b229290`.
Algorithm, service, contract, scorer, interpreter, capability and dependency-lock hashes
match the previous milestone (`final-identity.json`). No gate or threshold changed.

This is a source-checkout interface for decision logic under FaultLab's orders protocol,
not an unchanged native-framework integration, general Python environment, installable SDK,
production service, or hosted execution sandbox. The reports concern one synthetic scenario.
No live-model improvement or ACCEPTED generated policy is established. Rule 2 remains
deferred research. Carried conservative spend remains $937.99, not a newly queried balance.

The next product decision is to connect one independently authored workflow and record the
integration effort and repeat use. Without a partner workflow, use a bounded local native
framework adapter exercise and label its limitations. Do not expand into a hosted platform
or add more repair experiments merely to increase scope. Preserve this working regression
as a compatibility case while developing the next integration.

Development and verification use isolated source checkouts. Transfer is restricted to this
milestone's explicit files, with saved originals, baseline hashes and preserved original
main HEAD/index. No commit, push, deployment or provider call is part of this milestone.
