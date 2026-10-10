# Native smolagents integration: verification record

October 9, 2026. This record covers the explicitly selected local constructor
interface, `build_agent(model, tools)`. See the [guide](native-agent.md) for commands
and the [architecture decision](ADR_NATIVE_AGENT_2026-10-09.md) for scope and tradeoffs.

## Outcome

A separately supplied Python constructor runs through the real pinned smolagents
`ToolCallingAgent.run` loop. FaultLab owns the synthetic world, public observations,
faults, budgets and fixed checks. Candidate source and the complete native execution
identity are frozen before execution. Each trial starts a fresh worker and memory.

The same deterministic model double proposes the unsafe action for both candidates.
The author's tool wrapper is the correction. Disabling it reproduces confirmation
after rejection; enabling it prevents that action and preserves healthy completion.
The double does not read the candidate flag, source, private world or expected verdict.

| Separate-installation acceptance | Observed result |
| --- | --- |
| Read-only scenario inspection | Exit 0; no candidate execution |
| Unsafe constructor | Exit 1; 3/3 C3+C5 violations; each world has 0 upgrades and 1 confirmation |
| Corrected constructor | Exit 0; 3/3 passes; each world has 0 upgrades and 0 confirmations |
| Healthy corrected constructor | Exit 0; 1 pass; exactly 1 upgrade and 1 confirmation |
| Exported pytest with unsafe constructor | Exit 1; fresh behavioral check fails |
| Exported pytest with corrected constructor | Exit 0; fresh behavioral check passes |
| Exported pytest without explicit constructor | Exit 1; selection is required |
| Constructor exits with code 71 during shutdown | CLI exit 2; INCOMPLETE after 1 of 3 trials; actual confirmation retained; provisional report WITHHELD; no retry |

The unsafe, safe and shutdown-crash trials each made six double calls; the healthy
trial made four. These are synthetic responses, not provider requests. A completed
protocol and a truthful passing report are different requirements: the unsafe agent
completed its native execution but failed fixed task checks.

## Verification

The final full backend suite passed **3,177 tests**, with 234 existing
skips and 2 deprecation warnings, in **20 minutes 6 seconds** (1206.01 seconds).
The resumed suite ran against the complete frozen candidate in the separate installation.
It includes all 36 native-agent tests. No source or test edits occurred during the run.

Before the import-boundary extension, the native, local callback and example suites
passed **81 tests** in 39.09 seconds. The added boundary checks and transport suite
then passed **36 tests** in 11.32 seconds. The final 36 native tests comprise 8 consumer,
16 registration and 12 transport checks. They cover the correction workflow; native memory and tool history; source
replacement after snapshotting; portable data-only imports and explicit selection;
admission before world creation; marker removal or conflicting identity; repeated
trials; malformed and oversized messages; constructor misuse; timeouts; and repeated
cancellation during process creation with actual worker adoption and cleanup.

Frontend: **373 tests in 29 files**, production build, **19 browser fixture checks**
and **one real-backend browser check** passed. One opt-in browser fixture was skipped.
The real backend completed a fresh offline campaign with zero managed model calls
and zero tokens. The build retains its existing advisory warning for a JavaScript
chunk over 500 kB. All temporary verification services were stopped.

An independent checker used standard-library read-only SQLite queries, without
FaultLab helpers or the scorer, to examine **8 unique worlds, episodes and tasks**
and **13 operation identities**. It matched actual effects, operation receipts,
fault timing, delivered observations, report events, RPC frame hashes, source and
framework identities, registration/configuration/plan bindings and worker cleanup.
The late crash had no submitted Episode report; its original report remained in
the execution record with `WITHHELD` status.

Manual browser review opened all four HTML reports, expanded first-trial evidence,
and inspected native execution details for the passing and interrupted cases. The
unsafe report visibly showed rejection before the confirmation and the resulting
C3+C5 failures. The safe report showed no confirmation. The healthy report showed
one successful upgrade and confirmation. The interrupted report showed INCOMPLETE,
1 of 3 trials, the retained confirmation and the withheld provisional report.

The acceptance constructor lived outside both checkouts. Commands used a fresh
Python environment and copied scenario data from the earlier portable milestone.
Parent-process guards refused network access, credential-file reads and access to
the prior milestone directories during execution. All eight guard receipts confirm
activation. Separate worker tests exercised its accidental-access restrictions.
The receiving workspace did not need the historical lab database or world stores.

## Review findings and corrected attempts

The first full suite finished with **1 failure, 3,161 passes, 234 skips and 2 warnings**
in 1,305.53 seconds. Its import-boundary scanner only recognized the older adapter's
dotenv guard and rejected the three imports in the new worker. Review confirmed that
the worker already unconditionally disables both loaders immediately before those
imports. The scanner was extended to recognize only that exact guarded block in
that specific worker. Fourteen scanner cases cover the valid pattern and rejected
missing, late, partial, restored and conditional guards. A real-worker test uses a
harmless text sentinel to prove both loaders return false and leave the environment
unchanged. **Only two test files changed; application bytes did not.** The final full
suite uses that revised frozen test candidate. The first log and both test versions
are preserved; no failed application run was retried until it happened to pass.

The user subsequently requested a pause during the revised candidate's full suite.
That run stopped with **2,028 passes, 234 skips and 1 warning** after **463.93 seconds**;
its `KeyboardInterrupt` summary is an incomplete run, not a full-suite pass. Its
original `backend-release-verification-v2.log`, process-stop receipt and source
checkpoint remain preserved. On explicit user resume, all 825 candidate files
matched in the development and separate-installation checkouts; the original
807-file baseline, Git HEAD and index were unchanged, and the checkpoint archive
hash was verified. The complete suite was started again in the new
`backend-release-verification-resumed.log`. No application or test changes were
made between the interrupted and resumed runs. Only the completed resumed run can
provide the final full-suite result above.

- The registration review added native-marker checks before the legacy plan fallback,
  so partial or downgraded native registrations cannot silently run another actor.
- The transport review separated native requests from completed model-double calls
  and strengthened persisted execution/report correspondence checks.
- Persisted JSON sorts object keys. The validator now checks the explicit ordered
  evidence-label list and mapping membership, rather than treating dictionary order
  as delivery order. Canonical round-trip and reordered-map cases are covered.
- The first consumer run had 7 passes and one failure while registration source was
  being edited concurrently. The source-identity guard refused the later trial.
  After freezing source, all 8 consumer tests passed; no candidate-pinning assertion
  was removed. The first log and its explanation remain saved.
- An early registration test expected the wrong exception family; its assertion was
  corrected to the existing conflict contract. An early transport test counted an
  unrelated AnyIO task as a worker leak; it was narrowed to the owned child lifecycle.
  Runtime checks were not weakened.
- A dependency setup command was initially issued in the development checkout. It
  found all requirements already satisfied and installed nothing. That log is marked
  as a recheck, not fresh-install evidence. The independent fresh installation was
  then completed in the intended checkout.
- The independent world's first checker assumed the shutdown-crash case was a healthy
  control. The declared acceptance command actually used the rejection regression.
  The checker expectation was corrected; its first log is preserved. Application
  source and acceptance runs were unchanged.

## Source and evidence identity

| Identity | SHA-256 |
| --- | --- |
| runtime_hash | `274c0830b03338dc6a9dc4f4ed06f6306a5f1cc3327e986886c5fe35947bf3df` |
| algorithm_hash | `75a6b29b258347700165db23bab258f1b27dad2a155ca4cce31b67485ee165cc` |
| service_hash | `3ce5bcd25af4b37ec908f8699de2de31684a585c54346e4fff4b85396438f2c3` |
| contract_hash | `6f9d778323a4efc227c721a1844cafce751752f92c1bdcb2cf3ee45929e54727` |
| scorer_hash | `19de811c96473eb47d41974c881df06d8dca5191df4e7e0b17cbab2b421f8c2e` |
| interpreter_hash | `6da0714adef40c0268ce65c1d9b1d4a17f829ff04b8dbc6a7059f24f03e6622a` |
| capability_hash | `8e8e04afb34f894316b2e7cc129fba02a405f066d442bd799f7fc2fbdc652289` |
| dependency_lock_hash | `dc19e8608e601200380593bcfef7d5bd1cca2546b2252370403734deb5a902fb` |
| fixture_source_sha256 | `22b3ea5d49057bf19f5b6637e530a457243a5014f1fccd4b7623f7f10b229290` |


Runtime and algorithm identities changed because the registered native execution
path was added to the lab runner. The simulator service, public contract, fixed
scorer, policy interpreter, capability contract and dependency lock retain their
previous identities. The earlier rejected-upgrade fixture and local callback worker
are byte-identical. No policy gate or acceptance threshold was changed.

The original safe-source baseline contained 807 files. The frozen candidate contained
825 files. The first candidate had a 22-path delta; the precise test-boundary
correction adds one existing test path, producing a 23-path tested delta. Final
documentation adds the current status update and this record, producing a 25-path
transfer and 826 safe source files.
Only finishing documentation differs from the tested candidate. The guarded transfer
checks every original baseline hash and mode, preserves replaced files, verifies all
copied bytes, and preserves Git HEAD and index. No checkout, commit or push is part
of this milestone.

Local evidence is under `/Users/shree/FaultLab_Scratch/2026-10-09-native-agent/`:

| Evidence | Purpose |
| --- | --- |
| `candidate-v2-files.json`, `candidate-v2-delta.json` | Final frozen source and explicit tested delta |
| `backend-first-run-failure.json`, `backend-release-verification.log`, `pre-boundary-tests/` | Preserved first full-suite failure and original test bytes |
| `fresh-install.log`, `install-frontend.log` | Independent dependency installations |
| `combined-focused.log`, `boundary-fix-focused.log` | Focused backend checks |
| `backend-release-verification-v2.log`, `pause-process-receipt.json` | User-interrupted revised-candidate run; not a full-suite pass |
| `pause-checkpoint.json`, `pause-source-checkpoint.zip`, `resume-checkpoint.json` | Preserved source checkpoint, interruption details and verified explicit resume |
| `backend-release-verification-resumed.log` | Final complete backend check, required before finalizing this record |
| `frontend-verification.json`, `browser-health-verification.json` | Frontend/build/browser results and log hashes |
| `acceptance/verification.json` | Eight operator CLI and portable CI outcomes |
| `acceptance/{unsafe,safe,healthy,late-crash}/` | Saved summaries, reports and new databases |
| `manual-world-crosscheck.json`, `manual_world_check.py` | Independent persisted-evidence audit and checker |
| `manual-browser-verification.json` | Manual report review observations and HTML hashes |
| `final-identity.json`, `release-verification.json` | Frozen semantic identity and combined release receipt |
| `sync-receipt.json`, `pre-change-files/`, `original-final-identity.json` | Verified transfer, preserved files and final original-checkout identity |
| `original-installation/verification.json` | Additional inspect and healthy checks using the original checkout's own interpreter after transfer |

These local verification artifacts are not part of a fresh public clone. The runnable
guide and tests are included in source; the historical evidence is not relabeled as
new evidence. Earlier failed attempts remain distinguishable from the final candidate.

## Limits and next decision

This is native integration and authored-tool-guard conformance for one synthetic
orders scenario under a deterministic model double. It is not a production-model
reliability result, generated repair, ACCEPTED policy or customer-adoption result.
Only the pinned `ToolCallingAgent` and supplied tool/model contract are supported.
The worker is for trusted local code; it is not an operating-system security sandbox.
FaultLab-managed provider calls and new provider spend are zero. Arbitrary user-code
activity is unmetered. Carried conservative spend remains $937.99, not a billing query.

Rule 2 remains deferred research. The next useful milestone is an independently
authored workflow: reproduce its owner's incident, verify their correction, and
measure integration effort and repeat use. More adapters, hosted execution and
generated repairs should follow that evidence and its concrete requirements.
