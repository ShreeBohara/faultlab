# v2 lab runtime: store, scheduler, worker

Stage 1, phase 1.5. `faultlab/lab` runs a plan to a sealed envelope on the v2 pieces: the pack
(1.3) names the world and the tools, the kernel (1.2) hosts the world, effectsafe (1.4) keeps the
journal, the envelope (1.1) is what comes out, the oracle (1.9) scores the claims. It is the
legacy `EpisodeRunner`, `LabStore` and coordinator loop rebuilt small, with scoring kept apart.

## The typed store (`faultlab/lab/store.py`)

One SQLite file: `plans` (content-addressed, immutable), `batches`, `attempts` and `envelopes`
(written once, protected by triggers). Every record is a validated model in and out; an envelope is
re-validated (`validate_structure`) on every read. An attempt's lifecycle only moves forward
(CREATED, READY, RUNNING, SETTLING, TERMINAL) and its plan never changes. `claim` hands the first
READY attempt to one worker in one transaction; `recover` closes every RUNNING or SETTLING
attempt as TERMINAL with the reason and no envelope, so a dead worker's trials are visible as
interrupted and never invented. `spent` adds the measured cost of sealed envelopes (an envelope
without a measured cost counts at its reserved bound) to the bound of every open attempt.
`export_bundle` writes a batch as an envelope bundle (1.8).

## The scheduler (`faultlab/lab/scheduler.py`)

`schedule` expands plans by their repetition policy into READY attempts, repetition-major by
default (every scenario once before any scenario twice) or plan-major, and records the batch with
its caps. `Scheduler.next` claims the next attempt only if measured plus reserved plus the attempt's
own bound stays inside the batch caps; otherwise it raises `AdmissionRefused` and claims nothing. A
plan without a dollar bound cannot enter a dollar-capped batch. `run_batch` drives one worker
through a batch.

## The worker (`faultlab/lab/worker.py`)

`TrialWorker.run(plan, attempt, adapter)`:

1. loads the pack the plan names and refuses a plan whose pack digest it cannot reproduce or whose
   adapter id the adapter does not carry (sealed as `INFRA_ERROR`, evidence unavailable, before any
   world exists);
2. allocates the trial's intent from the pack (identities derived from the attempt id), creates the
   world on the kernel through the transport, lends the adapter a `TrialSession` and runs it under
   the plan's caps (`asyncio.timeout` for wall seconds; model calls, HTTP attempts and dollars in the
   session; ticks and waits in the kernel);
3. settles the world (stop, decision tick, the observer horizon), then seals: orchestrator events
   (started, stopped, refused), the session's agent-visible events (invoked, response delivered,
   waited, rule step, claim), the kernel's evaluator events, the report verbatim, fault exposure
   (the plan's placement ids, the kernel's trigger facts, the not-triggered reason), cost, and the
   execution identity (pack digest, kernel tree digest, adapter digest, configuration digest).

How a run ended is recorded on the attempt: a cap reached, the wall cap, a protocol error (an
undeclared tool), an unsafe resend the journal refused, a cancelled task (`STOPPED`), an adapter
exception (`INFRA_ERROR`). Each leaves a sealed envelope.

Scoring is separate. A `Referee` (`score(envelope, context) -> Verdict(task, findings)`) reads the
sealed draft plus a `ScoringContext` (the trial's intent, what the agent was shown, the world's
decision and horizon snapshots, the kernel's fault records, usage; the snapshots are private and
never enter the envelope) and the final seal carries its task outcome and findings. Without one,
the execution is `PENDING_EVIDENCE` with the note `TASK_OUTCOME_UNSCORED`, exactly what the legacy
projection says of an episode without a verdict; a referee that fails leaves the same pending
outcome with the failure noted. The belief-versus-effect oracle fills the claim score for packs
that have one (orders).

For orders, `faultlab/referee/legacy.py` (`LegacyOrdersReferee`) runs the fixed checks C1 to C8 of
`backend/app/referee/checks.py` as a black box on the v2 evidence: it is the one module in
`faultlab` that imports the legacy `app`, lazily and on purpose, and it refuses a checker whose
digest is not the one the plan pinned. Each finding carries the checker digest as its property
version and cites the delivery events of the evidence the check named. No fixed check is
re-implemented or weakened; moving the checks themselves is still the rest of phase 1.3.

## The session (`faultlab/lab/session.py`)

The broker rebuilt on effectsafe. `call(tool, request)` prepares the intent in the journal (bytes
pinned; a key the pack already allocated is kept), journals the dispatch, sends through the
transport, reconciles the reply into the operation's outcome, and records what the agent was shown.
A read that is a write's declared `status_lookup` folds its evidence into that write's outcome
(`Journal.observe`). A reply that does not bind to the trial's own identities (the pack's
`validate_result`, for orders the legacy broker's rule) is never shown as evidence: the agent sees
`INVALID_SERVICE_RESPONSE`, the envelope keeps the reply's digest and the reason, and the call is
not retried blindly. One logical call makes up to two transport attempts on a transient refusal or
a lost reply, as the legacy broker did; a write the provider cannot recognise is never resent while
its effect is unknown (`UnsafeResend` propagates to the adapter). `wait(ticks)` advances the world's
clock. `model_call()` charges a model call before it is made. `submit(report)` records the report
exactly once, verbatim.

## The transport (`faultlab/lab/transport.py`)

`KernelTransport` runs the world in-process on the kernel's `WorldStore` and `dispatch`. A lost
reply is decided, not raced: a reply delay the kernel declares beyond the session's timeout is a
timeout while the committed effect is already durable. The legacy lab's socket timeout against a
separate process, with its clock-drift checks, is what this replaces for simulator trials; an HTTP
transport to a running service is a later phase.

## Evidence

`backend/tests/v2/test_lab_worker.py`: a scripted orders agent runs all six development scenarios
through the worker and every envelope seals, scores `BELIEFS_TRUE` on the oracle, and reports every
scheduled fault as triggered; the lost reply (F1) is a timeout with one durable commit and a replay
on the resend; the transient refusal (F4) proves no effect twice and the third keyed send commits;
without a referee the execution is `PENDING_EVIDENCE`; a model-call cap, an adapter exception, a
silent adapter, an undeclared tool, a stale pack digest and a foreign adapter each end in a sealed
envelope with the reason; the store is typed, immutable and forward-only and recovers interrupted
attempts; a batch schedules in both orders, runs to envelopes, summarises and exports a bundle;
admission refuses the attempt that would exceed the batch's dollar cap and admits it again once the
earlier envelopes have measured their cost.

`backend/tests/v2/test_legacy_referee.py`: through the bridge, the scripted agent passes all eight
legacy checks on every development scenario (findings pinned to the checker digest, witnesses on
delivery events, oracle `BELIEFS_TRUE`); an agent that claims success after only a read is a
`VIOLATION` on the checks and a false belief on the oracle; the bridge refuses another pack, a
missing snapshot and a plan that pins a different checker.

`python -m faultlab store <trials.sqlite3> [--batch <id>]` prints a store's summary;
`python -m faultlab run` (see `ADAPTERS.md`) schedules and runs a batch for a registered adapter.
