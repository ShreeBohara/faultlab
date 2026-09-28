# Product durability review — September 27, 2026

FaultLab now prevents a second backend from interrupting the first backend's jobs. Saved experiments
can be opened as read-only archives, and a fresh local run can be stopped and reopened without replaying
effects or losing its saved evidence. These are product reliability changes, not new repair results.

## Findings and changes

The audit followed the dashboard and CLI into the coordinator, job scheduler, SQLite store, simulator,
budget ledger and restart recovery. The important gaps were:

| Gap | Resulting behavior |
| --- | --- |
| A second coordinator could run recovery on another process's active work. | A local OS lease is acquired before writable database opening, policy initialization or recovery. Constructor failures and store close release ownership. A second owner gets `STORE_IN_USE`. |
| Browsing an old store could initialize policies or mark old jobs interrupted. | Archive mode uses an existing database read-only, with no coordinator, recovery, simulator or provider call. Mutation routes return `READ_ONLY_ARCHIVE`; the dashboard shows the data location and disables writes. |
| Moving dashboard queries to threads still shared the scheduler connection lock. | Each file-backed GET uses its own read-only SQLite snapshot, including related records read during that request. |
| A terminal result and its budget release could be persisted separately. | Study, comparison, audit, search, regression and portability completion persist their terminal records and exact reservation releases in one transaction. Nested writes use savepoints. A failed finalization retains a prospective recovery marker without rewriting historical terminal records. |
| Some queued/partially completed jobs were not recoverable. | Queued requests have durable identities. Restart retains charges, partial worlds and trials, records interruption and releases only abandoned owned reservations. It never retries uncertain effects or re-rolls returned answers. |
| CLI writers bypassed the running backend and ownership rule. | Normal operator workflows send bounded registration, bundle execution and portability preparation to the owning backend. Offline writers acquire the same lease. Validation, playback and exports use saved read-only input. Registration falls back offline only on actual connection refusal. |
| Separate service commands could silently select different data locations. | `scripts/start-local.sh` requires a data directory and starts matching local services. Offline is the default; archive and live modes are explicit. Occupied ports fail before startup. Ctrl+C stops only owned processes in dependency order. |
| A stale saved ID caused repeated 404 requests, and fault exposure was ambiguous. | One actionable recovery state replaces missing-campaign polling. Outcomes distinguish full, partial and absent faults. Seven verified source traces are separate from the campaign telemetry status. |

No scorer, promotion threshold, Actor prompt, turn cap, price or historical protocol was relaxed.
The local launcher also reports a model input limit before dispatch without exposing prompt contents.

## Verification

Frozen runtime: `7dfdfe29fd210c70b5b83915f0cd47b144e03d49ffe172a9dfa722c50bd523f0`.
Algorithm: `9f82231e413124482ab8c07ffa6c2c322dee46e3343ee100c891f77eb2dcfbc4`.
Trace contract remains version 2. The original checkout and isolated implementation matched across
all 59 explicitly integrated files; the pre-existing working tree and real Git index were preserved.

- Full backend suite: **2,123 passed, 180 existing skips, zero failures**, 727.37 seconds. Two warnings:
  the existing Starlette deprecation and the explicit fork ownership test in a multithreaded test process.
  The first full invocation had 2,120 passing tests and
  three old restart fixtures opening a second coordinator before closing the first. The ownership
  guard correctly refused them. Only those fixtures changed: explicit close/reopen boundaries and
  final cleanup, with every recovery assertion preserved. All 155 affected heldout/ownership/recovery
  tests then passed. The first log is retained separately.
- Lifecycle group: 94 focused tests passed; ten frozen identity-sensitive workflow tests passed,
  including all five original-loop cases. The restart fixture now actually closes/reopens the store.
- Operator/CLI group: 75 focused tests passed. Independent storage, archive, launcher, input-limit
  and ownership checks also passed. Focused totals overlap the full suite and are not additive.
- Frontend: 206 tests, production build and eight intercepted browser fixtures passed. One actual
  server test was explicitly skipped; the actual manual checks below cover the running app separately.

Actual archive browsing used the closed live campaign's original store. The dashboard showed seven
completed tasks, baseline active, 39 existing requests, seven verified source traces and exposure of
four full recipes, one partial and two absent. Mutation attempts were refused. A nonexistent ID showed
one recovery action; selecting the real campaign restored saved evidence. The hashes and modification
times of all eight live database/world files were unchanged after closing the archive.

A fresh offline dashboard run used the new paired launcher and a separate directory:
`/Users/shree/FaultLab_Runs/2026-09-27/product-durability/offline-01`.
Campaign `campaign-c664e786d0094561b0de8508bbd975c2` completed with one upgrade, one truthful
confirmation and eight passing checks. A separate auditor read the raw world and original report,
confirming ten facts, including two successful receipts, decision/horizon ticks and zero model calls.
After a real process restart, all 23 records, eight events and the baseline pointer had identical
semantic hashes. No new world or model request appeared. A second coordinator was refused before
recovery, and reference-agent registration succeeded through the owning backend. Both launcher runs
shut down cleanly; the test servers are stopped.

The manual auditor initially used nonexistent report field names; it was corrected to the actual
`upgrade_outcome` and `notification_outcome` fields. That was an audit-script mistake, not a product
failure. Earlier source-identity test failures during concurrent edits are retained in the logs; the
same tests passed after source freeze. An initial launcher probe exposed a TIME_WAIT port-check false
positive; matching the server's address reuse behavior fixed it before the frozen verification.

Evidence: `artifacts/product-durability-2026-09-27/`, including the integration manifest,
full backend log, focused results, frontend build/browser logs and actual manual screenshots/audits.
The preceding original learning fixture and live results remain under `artifacts/product-loop-2026-09-27/`.
The verified source/evidence recovery checkpoint is recorded in `final-checkpoint.json`; the external
copy is `/Users/shree/FaultLab_Backups/2026-09-27/product-durability/`. Main and the real Git index remain
unchanged. All 31 historical result reports, the 901 MB main store and eight closed live databases
retain their original hashes.

## Remaining product work and limits

The ordinary campaign still selects the reference Actor internally. The existing reviewed native
smolagents implementation can be registered and used for saved regressions/portability, but exposing
it as a campaign choice requires carrying its immutable configuration and actual actor factory into
every original-loop phase. A label or dropdown alone would misattribute the reference Actor's work.

Task wording does not define an arbitrary task: the current environment, tools and fixed checks
support express upgrade followed by confirmation. The next increment should state that scope clearly,
show a frozen plan and named public development cases, and make the existing campaign-recording
download accessible even for `NO_CHANGE`. Bundle preview/import and a separately versioned second task
remain useful later milestones. Generated-policy acceptance, unseen validation and accepted-policy
transfer are still unproven; the manual reference fixtures do not establish them.

This is a local, single-writer POSIX application. The lease is not a distributed lock and does not make
network filesystems or multiple users supported. Six historical research scripts retain direct writable
`LabStore` use; they are frozen experiment programs, not concurrent product entrypoints. Internal test
and library callers can still instantiate `LabStore` directly. Do not claim every possible Python writer
is guarded. The observed SQLite 3.51.0 runtime also warrants a local dependency upgrade before expanding
writer concurrency; no corruption was found. Follow [local operation](local-operation.md) for startup,
archive, recovery and backup behavior.

No inference or publication was performed for durability. New provider cost: **$0**. Carried conservative
total remains **$856.96**; provider billing is still unknown. Historical reports, databases and active
pointers retain their original meaning. Nothing was pushed to GitHub.
