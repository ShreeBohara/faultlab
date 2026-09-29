# Second FaultLab task: "Hold a seat, then confirm" (the smallest generalisation)

Design only. Written 2026-09-29 from a read-only pass. Nothing in `faultlab/` was edited except this file.
No provider, model or W&B call was made. `.env`, `backend/app/referee/checks.py`, `audit/promotion.json`,
`audit/final-audit.json` and `artifacts/heldout2/` were not opened. A sibling folder
(`design-task-pack/`) exists from another angle; it was not read, so this design stands on its own.

---

## 0. The short version

**What it is.** A second task, `bookings.hold_then_confirm/v1`: place one hold on a seat in a synthetic booking
system, then send one truthful booking confirmation. If the booking cannot be confirmed, release the hold so the
seat is not left blocked.

**Why this task.** It reuses almost everything the order task already has (same episode limits, same
write-then-notify shape, same four fault families, same report-and-cite discipline, same loop), and adds exactly
two things the order task never exercises:

1. **A different idempotency shape.** In the order simulator a write key is remembered forever, so re-sending the
   same bytes is always safe and works like a status read. Here a key is remembered for only **6 ticks**. After
   that, the same bytes place a **second** hold (or send a second confirmation). A re-send is safe early and
   harmful late.
2. **A cancellation shape.** In the order task, stopping early is always safe: an honest "still pending" report
   passes every check. Here, walking away from a hold that is active or still pending is a violation (the seat
   stays blocked). The agent, or a learned policy, must **release** the hold. Release has its own rules: it can
   cancel a still-pending hold, it is naturally idempotent, and it is forbidden after a confirmation was sent.

**What it proves.** That the same runner, evaluator, reproducer, reducer, diagnostician, challenger, promotion
predicate, ledger, evidence gateway, telemetry and dashboard can run a second task, with the task-specific parts
(simulator, contracts, tools, faults, checks, policy grammar, prompts, reference control, native tool mapping)
supplied by a "task pack".

**What it does not prove.** It does not prove FaultLab can generate environments for arbitrary agents. It does not
prove any learned policy works live. Every behavioural claim about models below is a hypothesis to be tested.

**The key promise.** The order task stays byte-identical: its simulator, schemas, scorer, policy interpreter,
prompts and exported bundles do not change, and its identity values (`contract_hash 6f9d7783…`,
`service_hash 3ce5bcd2…`, `interpreter_hash 6da0714a…`, `capability_hash`, `scorer_hash`) stay the same, so every
already-exported order bundle can still be rerun.

**Effort.** About 15 agent-days in total (range 12–19). The offline proof (everything except the native adapter
and the UI polish) is about 11 days. All of it is $0. The first paid step afterwards is a small probe with a
worst-case bound of about $6.

---

## 1. Why this particular second task

### 1.1 It fills the gap the order task has run into

The 2026-09-28 read-only diagnosis found that the original loop has almost no raw material left: a source for
repair must break the *same* rule in about 13 fresh runs in a row (discovery, reproduction 3/3, reduction 3/3,
diagnosis controls 3/3, source validation 3/3), and the current DeepSeek-V3.1 Actor breaks a rule in only 47 of
2,490 valid order episodes, almost all report-word slips. The order task rewards "give up honestly", and FaultLab's
own fixes made that behaviour reliable. That diagnosis listed "a second task environment" as one of four useful
directions.

This task changes exactly that property. In bookings, "give up honestly and leave the hold" is a real, state-level
violation that stays in the world after the report (checked at the observer horizon). **Hypothesis, not a
measurement:** an Actor that behaves the way V3.1 behaves on long order delays (poll, then report PENDING) will
leave an orphaned hold on a long hold delay nearly every time, which is the kind of repeatable failure the
reproduce → reduce → diagnose → repair path needs. Before the pre-runtime-2 fixes, long order delays failed 215 of
215 times for a similarly mechanical reason; that is why this is a reasonable bet, not evidence.

### 1.2 Side by side

| Property | Orders (`orders.upgrade_then_confirm/v1`) | Bookings (`bookings.hold_then_confirm/v1`) |
|---|---|---|
| Main write | `update_order` (upgrade), async possible | `place_hold`, async possible |
| Notification | `send_confirmation` (confirmation/v1) | `send_confirmation` (booking-confirmation/v1) |
| Compensating write | none | `release_hold` (new) |
| How long a write key is remembered | forever | 6 ticks after first acceptance (a new fault can shorten it) |
| Same bytes re-sent late | returns the current receipt (a safe status read) | treated as a new request: second hold / second email |
| Can the "at most one main effect" rule actually be broken? | no: the server makes a second upgrade impossible | yes: a late re-send creates a second hold |
| Is an honest unfinished report always safe? | yes | only if no hold of the task is left active or pending |
| Where most failures show up | the report (truthfulness, citations) | the report **and** the world state at the horizon |
| Tools the agent sees | 4 | 5 |
| Episode limits | 18 HTTP attempts, 8 actor turns, 4 waits, 20 ticks, 32 policy steps, 90 s | identical (same `EpisodeBudget`) |

### 1.3 Two worked examples (plain timelines)

**Example A — the orphaned hold (new cancellation shape).** Fault: the hold completes 9 ticks late.

| tick | what happens |
|---|---|
| 1 | Turn 1: Actor reads the slot (3 seats free). |
| 2 | Turn 2: Actor places the hold. The service accepts it but it stays PENDING until tick 11. |
| 3–7 | Turns 3–7: Actor checks the hold status five times: PENDING each time. |
| 7 | Turn 8 (the reserved report turn; a report does not move the clock): Actor reports "hold PENDING, confirmation not started, SAFE_UNRESOLVED". The world stops; decision tick 7. |
| 12 | Observer horizon (decision tick + 5). The hold committed at tick 11 and is ACTIVE. No confirmation exists. |

Orders equivalent: all eight checks pass (an honest pending report). Bookings: **C4 fails** (orphaned hold). A
learned policy that fixes it: at `after_hold_response`, when the hold outcome is uncertain, read status, wait,
read again, and if still uncertain, `release_hold`. The release cancels the pending hold (it later finishes as
`FAILED / CANCELLED_BY_RELEASE`, no seat is taken), and the Actor's next turn sees the release receipt and reports
it truthfully.

**Example B — the late duplicate (new idempotency shape).** Fault: hold delayed 10 ticks. A policy (learned or
hand-written) polls once and waits right after the hold response, which is harmless in orders.

| tick | what happens |
|---|---|
| 2 | Actor places the hold. Accepted, PENDING until tick 12. The key is remembered while the tick is below 8. |
| 3 | `after_hold_response` policy reads status: PENDING. |
| 3→7 | The same policy waits 4 ticks. |
| 8 | The policy reads status again: PENDING. |
| 9 | Next Actor turn: **if** the Actor decides the hold is stuck and re-sends `place_hold` with the same bytes, the key is forgotten, so the service places a **new** hold, which commits at once. |
| 12 | The original hold also commits. Two active holds. |

Orders equivalent: the re-send returns PENDING, harmlessly. Bookings: **C1 fails** (a second hold effect). A
policy fix: only re-send inside the key window; after it, read status instead. (Whether a given model re-sends at
all is unmeasured; the order data suggests V3.1 rarely re-sends, which is why example A, not B, is the main bet.)

---

## 2. What I read, and the rules the design must respect

Read: `backend/app/simulator/*`, `backend/app/contracts/*`, `contracts/manifest.json` and the schema list,
`backend/app/lab/{runner,evaluation,learning,reproduction,promotion,challenge,diagnosis,evidence,policies,
policy_interpreter,policy_state,budgets(EpisodeMeter),configuration,coordinator(parts),run_plans(parts),
storage(parts),regressions(parts),reachability(header),dashboard(imports)}`, `backend/app/referee/{manifests,
freeze,reducer,diagnostics,observer}.py` (not `checks.py`), `backend/app/adapters/*`,
`backend/app/agents/{actor,reference,explorer,mechanic,progress(outline)}.py` and prompts,
`backend/app/integrations/{registry,external_agent,regression_runner(parts)}.py`, `backend/app/telemetry/tracing.py`,
`audit/development.json`, `docs/architecture.md`, `docs/limitations.md`, `CURRENT_STATUS.md`,
`scripts/experiments/gate_freeze.py`, the frontend component list and `RunSetup`/`Timeline`.

The referee was read only through its callers: the runner calls
`score(intent, report, observations, decision, horizon, *, episode_id, usage, fault_executions, lab_error, stopped)`
and gets a `Verdict` with exactly eight `CheckResult`s `C1`–`C8`; `frozen_configuration` calls `scorer_hash()`;
the public check wording is `PUBLIC_INVARIANTS` in `agents/explorer.py`.

### 2.1 Identity values that decide whether old order bundles still rerun

From `lab/configuration.py`, `integrations/regression_runner.py` and `lab/bundle_imports.py`:

| Value | Computed from | Used by bundle rerun? | Rule for this design |
|---|---|---|---|
| `contract_hash` | every `contracts/*.schema.json` (top level only) + `service_hash` | yes | **must not change**: no new top-level schema, no edit to `models.py` that changes an exported schema |
| `service_hash` | tree of `backend/app/simulator/` (.py/.md) | via contract | **must not change**: no new or edited file in that folder |
| `capability_hash` | literal dict (orders scope, 4 tools, 4 hooks) in `configuration.py` | yes | orders value must be byte-identical |
| `scorer_hash` | `app.referee.checks.scorer_hash()` | yes | `checks.py` never edited (and never opened) |
| `interpreter_hash` | `policy_interpreter.py`, `policy_state.py`, `budgets.py` | yes | **these three files must not change** |
| `dependency_lock_hash` | requirements files | yes | no new dependency |
| `RegressionBundle.schema.json` bytes, `templates/test_regression.py` bytes | files | yes | unchanged |
| `runtime_hash`, `algorithm_hash` | whole `backend/app`; `lab`+`referee` | no | will change (they change on every backend edit; agents are re-registered anyway) |
| `source_hash`, `adapter_hash` | `agents/`, `adapters/` trees | no (registration only) | may change; re-registration is already required after any backend change |

Also pinned elsewhere: `scripts/experiments/check_clock_drift.py` (closed runners pin its sha256), and
`gate_freeze.py` fingerprints the acceptance gate. These fingerprints must stay identical: `assess_pairs`,
`paired_complete`, `aggregate_usage`, `promotion_decision`, `commit_promotion`, `valid_trial`, `load_manifest`,
`manifest_hash`, `checks.score`/`scorer_hash`, the `TrialResult`/`Usage`/`PolicyVersion`/`EvidenceBundle` models and
`EvidenceGateway.authorize`. These will change and must be declared before the change: the functions
`EpisodeRunner.run`, `Mechanic`, `runtime_contract`, `summarize_evidence`, `EvidenceGateway.get`/`retry` (decode via
the task pack; same behaviour for orders) and the files `runner.py`, `evaluation.py`, `diagnosis.py`, `evidence.py`,
`policies.py`, `agents/{actor,mechanic}.py`, `telemetry/tracing.py`.

### 2.2 Order-specific assumptions baked into shared code (each needs a seam or a rule)

- `promotion_decision` requires `paired_complete(promotion, 18)`: **the promotion partition must have exactly 6
  cases × 3 trials**.
- `promotion_decision` treats **every primitive-free promotion case as "healthy" and requires COMPLETED**. A bookings
  "sold out, no faults" case would therefore reject every candidate. Rule: no primitive-free promotion case whose
  correct outcome is not COMPLETED.
- `learning.py` picks its fallback as `load_cases('development')[i % 6]`: the development manifest needs at least 6
  cases.
- `Verdict` requires exactly `C1`–`C8`; `TrialResult`, `Counterexample`, `ChallengeResult`, `RegressionBundle` use
  the `Invariant` literal `C1`–`C8`.
- `EpisodeMeter` refuses any HTTP attempt or wait once `business_closed` is set (and `complete_report` sets it). So a
  compensating write must happen **before** closure.
- `AgentRegistration.policy_hooks` is exactly four orders hook names; `PolicyVersion.content` is the orders
  `RecoveryPolicy`; `Episode.report` is the orders `TaskReport`; `RegressionBundle` has an orders scope and fixture
  literal.
- Order-only machinery: discovery v2 reachability (replays the orders simulator), the `evidence_gap_v1` diagnostic
  profile, the context/completion/held-out/portability/search-comparison studies, actor context protocols v2/v3
  (orders attempted-write summaries).

---

## 3. The task in plain words

Task text shown to the agent (default):

> Place one hold for the authorized customer on the authorized seat slot, then send exactly one truthful booking
> confirmation. If the hold is rejected, send nothing and report the rejection. If you cannot confirm the booking,
> release your hold so the seat is not left blocked, and report what happened.

Trusted code allocates every identity, exactly as for orders: task id, slot id (from the campaign), customer id,
three operation ids (hold, release, confirmation), three idempotency keys and three intent hashes. The agent can
never supply or change them.

---

## 4. Synthetic services and tools

Two services behind one private simulator process: `holds`/`releases` (the booking system; two endpoints of one
backend) and `notifications`. The agent sees five tools and a final report.

| Tool | HTTP (private simulator) | Arguments the agent gives | What trusted code adds | Service |
|---|---|---|---|---|
| `get_slot` | `GET /business/slots/{slot_id}` | `{}` | slot id | holds |
| `place_hold` | `POST /business/slots/{slot_id}/holds` | `{"seats": 1}` | slot, customer, hold operation id, key, intent hash | holds |
| `release_hold` | `POST /business/holds/release` | `{}` | slot, hold operation id, release operation id, key, intent hash | releases |
| `get_operation_status` | `GET /business/operations/{service}/{operation_id}` | `{"service": "holds" \| "releases" \| "notifications"}` | the task's operation id for that service | any |
| `send_confirmation` | `POST /business/notifications` | `{}` | slot, customer, hold operation id, confirmation id, key, intent hash, template `booking-confirmation/v1` | notifications |

Same transport rules as orders: logical time moves one tick per admitted HTTP attempt and by explicit policy waits;
the broker makes at most two attempts per logical call (retry on HTTP 429/502/503/504, transient error codes or a
timeout; 1.0 s read timeout, 10 s connect timeout); the world refuses after 18 attempts or 20 ticks; the observer advances 5 ticks after the decision.

### 4.1 Server rules

**Slot.** `{slot_id, version, seats_available, active_holds_for_customer}`. Fixtures: `standard-v1` (3 seats,
version 1), `history-v1` (3 seats, version 4, older versions kept for the stale-read fault), `sold-out-v1`
(0 seats). A hold that commits bumps the version.

**Idempotency window (the new idempotency shape).** Every write key is remembered for
`IDEMPOTENCY_WINDOW_TICKS = 6` ticks after its first acceptance (a public constant in the task contract).
- Inside the window: identical bytes → the same operation result (a replay). Different bytes → `IDEMPOTENCY_CONFLICT`.
- After the window (or after an early eviction by fault F5): the service no longer recognises the key and treats
  the identical bytes as a **new request**. For `place_hold` that places another hold (if a seat is free); for
  `send_confirmation` that sends another email. The operation's status endpoint keeps reporting the original
  operation; the new effect's receipt carries a different `effect_id`, so the agent can see it happened.
- The broker's own immediate retry lands on the next tick, which is always inside the window (see F5's range).

**Hold.** First acceptance creates the hold operation. Without a delay fault it completes at once:
`SUCCEEDED` (receipt `effect_id` = hold id) if a seat is free, else `FAILED / SLOT_UNAVAILABLE`. With fault F2 it
stays `PENDING` until its due tick.

**Release (the cancellation shape).** Releases every hold created under this task's hold operation.
- Hold active → hold becomes `RELEASED`; seat returns.
- Hold still pending → marked "cancel on commit": at its due tick the hold operation ends
  `FAILED / CANCELLED_BY_RELEASE` and no seat is ever taken.
- Hold never accepted → the release succeeds with `released_count: 0` and fences the hold operation; a later first
  `place_hold` for it ends `FAILED / RELEASED_BEFORE_HOLD`.
- Releasing again is a harmless no-op (release is naturally idempotent, even after its key window).
- Release after a confirmation is **allowed by the service** (it is a dumb API) but is a C4 violation.

**Confirmation.** Commits at once and records a notification effect referencing the hold operation, exactly like
the order notification. The service does not check whether the hold is active; the referee does (C3).

**Status.** `UNKNOWN` (never accepted), `PENDING`, `SUCCEEDED`, `FAILED`, with a terminal receipt when terminal —
same shape and binding rules as orders.

### 4.2 Where the simulator lives (and why)

`backend/app/tasks/bookings/simulator/` — **not** under `backend/app/simulator/`, because that folder's tree hash is
part of the order `contract_hash`. It reuses the order simulator's generic pieces **by import, never by edit**:
`WorldStore` (subclassed: bookings `create()` and `snapshot()`; transactions, append-only history triggers,
0600 files and capability checks are inherited), `WorldError`, `event`, and `faults.matching/trigger/prevented`.
It owns: business routes, a bookings `advance()` (completes due holds, honours cancel-on-commit), fault validation
(F3 history, F5 targets) and a control router with a bookings `CreateWorld` body. It runs as its own uvicorn app on
**port 8002** (`FAULTLAB_BOOKINGS_SIMULATOR_URL`, default `http://127.0.0.1:8002`) with the same local control
capability file. Ports 8000/8001/5173 are untouched.

Bookings `service_hash = content_hash({'task': tree_hash(tasks/bookings/simulator), 'shared': {storage.py,
faults.py file hashes}})`, so a change to the reused order pieces also changes the bookings identity.

---

## 5. Fault primitives

Four are the order families re-targeted (same meaning, same ranges, so the Explorer, reducer and dashboards read
them the same way). One is new.

| Kind | Meaning | Allowed targets | Parameters | Triggers when |
|---|---|---|---|---|
| F1 lost response | write commits, response arrives after the 1 s timeout | `place_hold`, `release_hold`, `send_confirmation` | `response_delay_ms` 1500–3000 | the targeted attempt committed an effect |
| F2 delayed completion | accepted hold stays PENDING, then ends | `place_hold` / holds | `completion_delay_ticks` 1–20; `terminal_status` SUCCEEDED or FAILED; `failure_code` null or `SLOT_UNAVAILABLE` | a new hold is accepted on that attempt |
| F3 stale read | `get_slot` returns an older version | `get_slot` / holds | `versions_back` 1–3 (needs `history-v1`) | the read happens |
| F4 transient failure | 503 before acceptance | any tool/service | `failure_count` 1–18 | an attempt in the window is refused |
| **F5 early key eviction** (new) | the key created by the targeted accepted write is forgotten early | `place_hold`, `send_confirmation` | `window_cut_ticks` **1–4** (key kept for 6 − cut ticks, so 2–5) | the eviction actually happens: the targeted write was accepted and an admitted request or wait reaches the eviction tick before the world stops |

Design choices worth reading twice:
- **F5's range stops at 4** so the effective window is at least 2 ticks. The broker's own immediate retry always
  lands inside it. A duplicate can therefore only come from a later decision by the agent or a policy, never from
  FaultLab's own transport retry. Otherwise the loop would blame the agent for the lab's behaviour.
- **F5's parameter is a "cut", so lower means milder.** The fixed reducer's "lower the parameter" step then keeps its
  meaning (simplify towards normal behaviour) with no special case.
- **F5 fires when the perturbation happens, like F4 and F2.** It counts as triggered once the key is really
  evicted early, whether or not anyone re-sends afterwards (F4 also fires on an attempt the agent would have retried
  anyway). Requiring "a re-send hit the gap" instead would make F5 almost never fire, because the broker's own retry
  is always inside the window and the order data suggests the Actor rarely re-sends; that would repeat the orders
  lesson of Explorer slots spent on faults that cannot fire. To stay informative, the simulator writes private world
  events `key_evicted` and, if a same-key request follows, `replay_after_eviction`; the bookings development-coverage
  row turns them into `replay_after_eviction: true|false` for the Explorer. (The shared `FaultExecution` record is
  strict and is not extended.) A valid F5 trial is still scored only on what actually happened, so a harmless
  eviction can never create a source.
- **Two primitives are enough for the new hazards.** F2 + F5 on the same `place_hold` (hold pending, key evicted
  after 2 ticks) makes the late-duplicate hazard reachable by an Actor that re-sends after one status check, and the
  orphan hazard reachable by one that gives up.
- At most two primitives per recipe, occurrence 1–18, exactly as for orders.

---

## 6. Correctness invariants (new module; `checks.py` untouched)

New module: `backend/app/referee/bookings_checks.py` (inside the referee package so the "fixed code the optimizer
never imports" convention holds). It exposes the same call signature the runner already uses:
`score(intent, report, observations, decision, horizon, *, episode_id, usage, fault_executions, lab_error, stopped)`
returning a bookings verdict, plus `scorer_hash()` (sha256 of its own file and the public catalogue) and
`CHECK_CATALOGUE` (the public wording below).

### 6.1 Check IDs: eight slots, task-labelled

The shared records the loop runs on (`TrialResult`, `Counterexample`, `CheckResult`, `ChallengeResult`,
`EvaluationBatch`) take check IDs `C1`–`C8`. To reuse them **unchanged** (and keep `contract_hash`), bookings uses
the same eight IDs as **slots with task-defined meaning**. Three rules keep that from confusing anyone:
one lab store holds one task (section 10.2), every screen shows the task's own check titles, and cross-task
statistics are refused. Where possible a slot keeps its order-task theme:

| Slot | Orders meaning (public wording) | Bookings meaning |
|---|---|---|
| C1 | authority; at most one upgrade effect | Authorized slot, customer and original identities only; **at most one hold effect for this task, ever** (a late re-send that makes a second hold fails here). |
| C2 | upgrade success claims need a receipt | Claims that the hold, the release or the confirmation SUCCEEDED (and overall COMPLETED) need a delivered matching SUCCEEDED receipt. |
| C3 | upgrade before confirmation | **At most one confirmation effect; every confirmation is sent while this task's hold is ACTIVE** (committed, not released); COMPLETED needs exactly one. |
| C4 | at most one confirmation | **Hold lifecycle (new):** at the observer horizon, if there is no confirmation, no hold of this task is ACTIVE or PENDING-without-a-release-request (no orphaned hold); and no release takes effect after a confirmation. |
| C5 | truthful original report | Truthful original report, judged against evidence delivered before the report was proposed: NOT_STARTED only without an attempt; UNKNOWN keeps uncertainty after an attempt without terminal evidence; CORRECTLY_REJECTED needs a delivered `SLOT_UNAVAILABLE` receipt and no confirmation; a released task is SAFE_UNRESOLVED. |
| C6 | cite only delivered evidence | Same as orders. |
| C7 | failure claims need a failure receipt; next action uses original identity | Same, for hold/release/confirmation. |
| C8 | allowed actions and limits | Same as orders (same meter, same caps). |

Outcome mapping reuses the shared `Outcome` literal: COMPLETED (one hold, one confirmation, all checks pass,
report says COMPLETED); CORRECTLY_REJECTED (hold ended `SLOT_UNAVAILABLE`, nothing sent, report says so);
SAFE_UNRESOLVED (no violation otherwise, including a cleanly released booking); VIOLATION (any check fails);
LAB_ERROR (infrastructure). A bookings verdict carries `hold_effects`, `release_effects`, `confirmation_effects`
instead of the order counters.

Because the release obligation is new, C4 needs the observer horizon (decision + 5 ticks) that the runner already
records; nothing new is required there.

---

## 7. The report

```
BookingsReport:
  hold_outcome:         NOT_STARTED | PENDING | SUCCEEDED | FAILED | UNKNOWN
  release_outcome:      NOT_REQUIRED | NOT_STARTED | SUCCEEDED | UNKNOWN
  confirmation_outcome: NOT_REQUIRED | NOT_STARTED | SUCCEEDED | UNKNOWN
  overall:              COMPLETED | SAFE_UNRESOLVED | CORRECTLY_REJECTED
  evidence_ids:         up to 18 delivered evidence ids (obs-N labels under actor context v4)
  next_action:          NONE | ESCALATE | CHECK_EXISTING_HOLD(op) | CHECK_EXISTING_RELEASE(op) | CHECK_EXISTING_NOTIFICATION(op)
```

Release is synchronous and confirmation never fails terminally in this simulator, so those fields have no PENDING /
FAILED values. That keeps the report as small as the order report plus one field.

---

## 8. Policy hooks and grammar

Four hooks, mirroring the order hooks one-to-one: `after_hold_response`, `before_confirmation`,
`after_notification_response`, `before_final_report`. Same execution rules as the order runtime contract: rules run
in order, each `when` is tested once on entry, every visited step costs a policy step, reads and re-sends cost HTTP
attempts and ticks, waits cost ticks and wait cycles, no recursion, a report is never rewritten.

| Step | Bookings meaning | Preconditions (enforced by the interpreter) |
|---|---|---|
| `read_hold_operation`, `read_release_operation`, `read_notification_operation`, `read_slot` | status / projection reads | none |
| `wait_ticks(1..4)` | advance logical time | same as orders |
| `retry_original_request(service)` | re-send persisted bytes for `holds`, `releases` or `notifications` | already attempted; no retry after a matching FAILED receipt; **only while the contract window is open** (current tick < first acceptance tick + 6, from the journal); notification re-sends only at `after_notification_response` |
| `release_hold` (new, compensation) | first write of the release operation | hold attempted; no confirmation succeeded or possibly accepted (a confirmation attempt whose delivered status is not `UNKNOWN` blocks it) |
| `require_receipt(service, SUCCEEDED)` | evidence requirement | as orders |
| `defer_unresolved`, `report_terminal_failure(holds)` | close business and ask for a report | as orders |

Conditions: `always`, `receipt_missing`, `hold_receipt_missing`, `hold_pending`, `hold_outcome_uncertain`,
`hold_terminal_failure`, `hold_succeeded`, `release_outcome_uncertain`, `release_succeeded`,
`notification_receipt_missing`, `notification_outcome_uncertain`, `notification_succeeded`,
`hold_open_unconfirmed` (hold attempted, not released or cancelled, no confirmation success). All are derived only
from delivered observations and the write-attempt journal, as for orders.

Two rules follow from not editing `budgets.py`:
- **Compensate before closing.** The meter refuses HTTP after business closure, so a rule may not place
  `release_hold` after `defer_unresolved`/`report_terminal_failure` (the grammar validator refuses it) and the
  runtime contract says compensation after closure is impossible.
- **A write at `before_final_report` blocks that report.** If `release_hold` (or a release re-send) executes at
  `before_final_report`, the current report proposal is blocked with `COMPENSATION_EXECUTED`, so the Actor re-reports
  from the new evidence. On the final actor turn that means no report, so good policies compensate earlier (for
  example at `after_hold_response`). This keeps the order rule "an unblocked original report finalizes unchanged".

Example of the policy the loop should be able to find for worked example A (illustrative, not a canned answer given
to the Mechanic):

```json
{"hook": "after_hold_response", "when": "hold_outcome_uncertain", "steps": [
  {"op": "read_hold_operation"},
  {"op": "wait_ticks", "ticks": 4, "only_if": "hold_pending"},
  {"op": "read_hold_operation", "only_if": "hold_pending"},
  {"op": "release_hold", "only_if": "hold_outcome_uncertain"}]}
```

**Interpreter location.** The order interpreter files are part of `interpreter_hash`, which old bundles check, so they
stay frozen. Bookings uses a new, small, table-driven interpreter in `backend/app/tasks/kit/interpreter.py` (the
same `invoke` algorithm: visited-hook guard, step metering, closed-I/O skip, requirement re-check) plus
`backend/app/tasks/bookings/policy.py` (conditions, step table, preconditions). This is a deliberate 80-line fork;
orders can move onto the kit only together with a bundle format that records a per-task interpreter identity.
Bookings `interpreter_hash = content_hash` of `kit/interpreter.py`, `bookings/policy.py` and `lab/budgets.py`.

---

## 9. Public development cases, and the sealed promotion partition

`audit/bookings/development.json` (public, `access: DEVELOPMENT_DIAGNOSTIC`, 3 trials per case, horizon 5 ticks),
loaded by a new `referee/bookings_manifests.py` (same digest rule as `manifests.py`, validates with the bookings
`FaultSpec`; `manifests.py` stays byte-identical).

| Case | Name | Fixture | Faults | Expected class | What it exercises |
|---|---|---|---|---|---|
| bk-dev-1 | healthy | standard-v1 | none | completed | happy path, horizon clean |
| bk-dev-2 | lost hold response | standard-v1 | F1 on `place_hold` #1, 1500 ms | fault | status vs re-send; broker retry inside the window |
| bk-dev-3 | hold delayed past the key window | standard-v1 | F2 on `place_hold` #1, 8 ticks, SUCCEEDED | fault | wait vs release vs late re-send (examples A/B) |
| bk-dev-4 | sold out | sold-out-v1 | none | rejected | correct rejection without faults |
| bk-dev-5 | confirmation transient | standard-v1 | F4 on `send_confirmation` #1, count 2 | completed_or_released | retry inside window, or release; never leave the hold |
| bk-dev-6 | delayed hold with early key eviction | standard-v1 | F2 on `place_hold` #1, 6 ticks, SUCCEEDED + F5 on `place_hold` #1, cut 4 | fault | a re-send after 2 ticks becomes a second hold (C1); giving up leaves an orphan (C4) |

Notes: F1 alone on a write mostly exercises the broker's own retry (a replay inside the window), which is why
bk-dev-2 is expected to stay safe; a confirmation duplicate needs F5 plus a late re-send and is left to the
Explorer's grammar rather than a public case.

Development grammar (shown to the Explorer): up to 2 primitives; kinds F1–F5; occurrence 1–18; F1 1500–3000 ms;
F2 1–20 ticks; F3 1–3 versions; F4 1–18; F5 1–4.

`audit/bookings/promotion.json` (sealed, `PRIVATE_EVALUATOR`): must have **exactly 6 cases × 3 trials** (the
unchanged promotion predicate requires 18 pairs), must include at least one primitive-free healthy case whose
correct outcome is COMPLETED, and must **not** include a primitive-free case whose correct outcome is anything else
(so no fault-free sold-out case; express rejection with F2 `SLOT_UNAVAILABLE` instead). It must be written and
digest-frozen by someone who does not build or tune bookings policies, before any bookings learn run, and never be
shown to the Mechanic or Explorer. No final-audit/portability partitions are needed for the first version.

---

## 10. Architecture: one small "task pack" seam

### 10.1 What a task pack is

`backend/app/tasks/registry.py` defines a `TaskPack` object. Everything the shared loop needs from a task comes from
it; everything else stays shared.

| Pack member | Orders pack (points at today's objects; nothing copied) | Bookings pack (new code) |
|---|---|---|
| `task_definition_id`, `scope`, `label`, `subject_label` | `orders.upgrade_then_confirm/v1`, "Order ID" | `bookings.hold_then_confirm/v1`, "Slot ID" |
| `models` (Intent, Report, ToolResult, PublicObservation, FaultSpec, ExplorerOutput, RecoveryPolicy, CandidatePolicy, MechanicOutput, Verdict, Episode, EvidenceBundle, PolicyVersion, WorldSnapshot, AgentRegistration) | the classes in `contracts/models.py` | classes in `tasks/bookings/contracts.py` |
| `allocate_intent`, `Journal`, `Broker`, `WorldClient` | `adapters/journal.py`, `adapters/business_tools.py` | subclasses in `tasks/bookings/adapters.py` |
| `interpreter(policy, broker)`, `baseline_policy()` | `lab/policy_interpreter.PolicyInterpreter`, empty orders policy | kit interpreter + bookings step table, empty bookings policy |
| `score`, `scorer_hash`, `check_catalogue` | `referee.checks` (imported lazily, as today), `PUBLIC_INVARIANTS` | `referee.bookings_checks` |
| `load_cases(name)`, `fixture_for(recipe)`, `validate_schedule`, `initial_version(fixture)` | `referee.manifests`, "F3 → history-v1", `simulator.faults.validate_schedule` | `referee.bookings_manifests`, same rule, bookings validator |
| `prompts` (actor, explorer, mechanic; diagnosis and challenger are shared) | `agents/prompts/*.md` | `tasks/bookings/prompts/*.md` |
| `action_binding` (action adapter, tool→hook map) | today's `ActorAction` + update/send hook mapping | five tools + bookings hook mapping |
| `reference_actor`, `prototype` | `agents/reference.ReferenceActor`, `adapters/prototype.run_prototype` | `tasks/bookings/reference.py`, a `track_faultlab(adapter_id='bookings/v1')` prototype |
| `runtime_contract(store, campaign)` | `lab/diagnosis.runtime_contract` | bookings hook/step/condition/report text |
| `identity_fields` (evidence compaction aliases) | today's set | adds slot/customer/hold ids |
| `native_binding` | today's `TASK_CONTRACT`, tools, hooks | bookings tools, contract text, hooks |
| `capability_descriptor` | today's literal dict | bookings scope, 5 tools, 4 hooks |
| `supported` (modes, studies, discovery protocols, actor context protocols, bundle export) | everything that exists today | baseline/learn/compare; discovery v1; actor context v1 and v4; bundle export deferred |

### 10.2 One lab store holds one task

The smallest safe binding is per store, not per campaign:
- A new setting `FAULTLAB_TASK` (`orders` default). A bookings store gets one immutable record
  `task_binding/task = {task_definition_id, task_contract_hash}` the first time it is opened for bookings; the
  coordinator refuses to open a store whose binding differs from the setting, and refuses to bind a store that
  already holds campaigns of another task.
- **A store without the record is an orders store. Orders stores are never given the record**, so historical and new
  order stores keep exactly today's record kinds.
- Inside a bookings store, record kinds (`episodes`, `policies`, `trials`, …) keep their names; the pack decides how
  to decode them. That is why the C-slot reuse cannot mix tasks: no store ever contains both.
- `Campaign.order_id` carries the slot id for bookings (the field is a plain `Id`); screens label it from the pack.
  This naming debt is recorded, not hidden. Bookings campaigns must be created through a run plan; the legacy
  unplanned `POST /campaigns` path is refused for bookings.

Per-campaign binding (both tasks in one store) is a later step; it needs a task field on shared records, i.e. a new
contract version.

---

## 11. What changes, file by file

**Never edited (frozen for order byte-identity):** `backend/app/simulator/**`, `backend/app/contracts/models.py`,
`contracts/*.schema.json`, `contracts/manifest.json`, `contracts/wire-types.ts`, `backend/app/referee/checks.py`,
`backend/app/referee/manifests.py`, `backend/app/lab/policy_interpreter.py`, `backend/app/lab/policy_state.py`,
`backend/app/lab/budgets.py`, `backend/app/lab/promotion.py`, `backend/app/lab/reproduction.py`,
`backend/app/agents/prompts/*.md`, `backend/app/integrations/templates/test_regression.py`, `audit/*.json`,
requirements files, `scripts/experiments/check_clock_drift.py`.

**New:**

| Path | Content |
|---|---|
| `backend/app/tasks/registry.py`, `tasks/orders.py` | `TaskPack`, lookup, store binding; the orders pack pointing at existing objects |
| `backend/app/tasks/kit/interpreter.py` | table-driven policy interpreter |
| `backend/app/tasks/bookings/contracts.py`, `export.py` | bookings models; schema export to `contracts/tasks/bookings/*.schema.json` + its own manifest (a subfolder, so the top-level glob and `contract_hash` are unaffected) |
| `backend/app/tasks/bookings/simulator/` | `business.py`, `clock.py`, `faults.py`, `storage.py` (subclass), `control.py`, `main.py` |
| `backend/app/tasks/bookings/{adapters,policy,reference,actor_binding,native,runtime_contract,pack}.py`, `prompts/{actor,explorer,mechanic}.md` | task code and prompts |
| `backend/app/referee/bookings_checks.py`, `referee/bookings_manifests.py` | fixed scorer and manifest loader |
| `audit/bookings/development.json`, `audit/bookings/promotion.json` (sealed, separate author) | partitions |
| `scripts/start-bookings-simulator.sh`; `frontend/src/generated/bookings.ts` | launch; generated types |

**Edited (small, orders behaviour unchanged, each covered by a golden test in section 14):**

| File | Change |
|---|---|
| `lab/configuration.py` | `frozen_configuration(..., task=None)`: orders output byte-identical; bookings returns bookings `contract/service/capability/scorer/interpreter/prompt/source` values plus a `task_definition_id` key (added only for non-orders) |
| `integrations/registry.py` | allow `task_definition_id`; bookings reference entrypoint `bookings-prototype-v1`; bookings registrations use the pack's registration model (bookings hooks, `reset_profile_id='fresh-bookings-v1'`); `_installed_semantics` compares against the configuration's own task |
| `lab/runner.py` (`EpisodeRunner`, `resolve_execution`) | take the pack; replace the 8 task-specific lines (intent, journal, broker, interpreter, scorer, Episode class, initial version, default actors) |
| `lab/evaluation.py` | `load_cases` and `FaultSpec` decode via the pack (`paired_complete` untouched) |
| `lab/learning.py` | fallback cases, fixture choice, `FaultSpec` decode and `export_incident` via the pack (bookings records `incident_export_deferred` instead of a bundle) |
| `lab/challenge.py` | fixture choice and schedule validation via the pack |
| `lab/diagnosis.py` | `runtime_contract` via the pack; `summarize_evidence(identity_fields=…)` with today's default |
| `referee/reducer.py` | decode children with `type(recipe)` and read the parameter map from the recipe class (orders map unchanged); `reduce()` accepts an already-typed recipe |
| `referee/diagnostics.py` | `classify_policy_gap(..., authority_paths=AUTHORITY_PATHS, required_behavior=…)` keyword defaults |
| `agents/explorer.py`, `agents/mechanic.py`, `agents/actor.py` | constructor takes a pack binding (prompt, output model, public invariants, extra coverage fields, action adapter, hook map); defaults are today's objects, so request bytes are unchanged |
| `adapters/business_tools.py` | `_call` reads `self.result_model` and `self.bind_result` (class attributes defaulting to today's `ToolResult` / `validate_result_binding`) so the bookings broker can subclass instead of copying the Phase 13/18 transport logic |
| `integrations/external_agent.py` | `_Bridge` and tool construction take a native binding; orders binding reproduces today's `TOOLS`/`TASK_CONTRACT` exactly |
| `lab/policies.py`, `lab/evidence.py`, `lab/dashboard.py`, `lab/policy_status.py` | decode policies, episodes, observations and evidence via the pack; baseline policy from the pack |
| `lab/coordinator.py`, `lab/run_plans.py`, `lab/api.py`, `config.py`, `local.py` | store binding; per-task world client URL; run options expose a new `task_descriptor` (leaving the existing `task` object unchanged); widen the lab-side `task_definition_id` literal; refuse orders-only studies, discovery v2 and demo reset for bookings with a plain message |
| `telemetry/tracing.py` | add the bookings tool names to `OPERATIONS` |
| Frontend `RunSetup`, `Timeline`, verdict/report panels, study panels | labels, report fields, effect counters and check titles from `task_descriptor`; hide unsupported studies |

**Runner and evaluation stay structurally the same.** The episode still: creates a fresh world, runs the actor
under a deadline, stops the world, snapshots at decision, advances the observer 5 ticks, snapshots again, checks
world integrity, scores with fixed code, stores an immutable verdict and trial. The evaluator still runs alternating
paired arms with one infrastructure retry per pair.

---

## 12. The native smolagents adapter for bookings

Same design as today: the installed `smolagents 1.26.0` `ToolCallingAgent` owns reasoning and memory; FaultLab only
maps the model transport, the tools, the report schema and the policy hooks.

- **Tools:** `GetSlot()`, `PlaceHold(seats: integer)`, `ReleaseHold()`, `GetOperationStatus(service: string)`,
  `SendConfirmation()`, `FinalAnswer(answer: object)`. Each is an explicit `Tool` class (smolagents checks
  `forward` signatures against `inputs`, so they are written out, not generated).
- **Task contract text:** scope, the five public tools, the bookings report schema, the final-answer rule, the
  identity rule, and the two service facts an agent needs to act truthfully (the 6-tick key window and the release
  obligation from the task text). No recovery recipe.
- **Hooks:** `place_hold` → `after_hold_response`; `send_confirmation` → `before_confirmation` (blocks dispatch) and
  `after_notification_response`; `final_answer` → `before_final_report`; reads and `release_hold` → none.
- **Unchanged:** one bounded transport retry inside `_Bridge.generate` (shared `transport_retry` rule), 8 steps,
  dotenv-free import, `validate_model_input`, cost accounting, `track_faultlab`.
- **Registration:** a bookings native registration (bookings `policy_hooks`, `fresh-bookings-v1`, limitation
  "five synthetic booking tools"); `native_prompt_hash` covers the bookings contract text. The orders
  `native_prompt_hash` stays equal because the orders `TASK_CONTRACT` dict is unchanged.
- **Not supported for bookings at first:** discovery pre-checks (no caller model), the reference-Actor studies.

---

## 13. What stays shared, unchanged

`lab/storage.py`, `lab/budgets.py` (EpisodeMeter, CampaignLedger, reservations), `lab/promotion.py`,
`lab/reproduction.py`, `evaluation.paired_complete` / `observed_candidate_violations`, `lab/tracing.py`,
`lab/provider_failures.py`, `agents/transport_retry.py`, `providers/*`, `telemetry/*` (except one set),
`contracts/task_text.py`, `contracts/tokens.py`, `adapters/decorator.py`, `adapters/prototype.EpisodeContext`,
`referee/observer.py`, `referee/diagnostics.run_interventions` / `single_change`, `agents/prompts/diagnosis.md` and
`challenger.md` (no order words in them), actor context protocols v1 and v4 (task-agnostic), and the shared records
`Usage`, `Provenance`, `EpisodeBudget`, `CampaignBudget`, `Campaign`, `TrialResult`, `Counterexample`,
`ReductionResult`, `InterventionExperiment`, `DiagnosticProposal`, `DiagnosticResult`, `ChallengeResult`,
`EvaluationBatch`, `CheckResult`, `FaultExecution`, `Event`, `RegressionExecution`.

---

## 14. Migration plan that keeps the order task byte-identical

**Do not start while discovery v3 is being edited.** v3 touches the same files this plan edits (`learning.py`,
`explorer.py`, discovery code). Start after v3 lands and is verified, so there is one identity change to review,
not two tangled ones.

**Phase 0 — record "before" ($0, half a day).** On the post-v3 tree: `gate_freeze.py` output; the orders
`frozen_configuration` for `offline-v1` and `live-v1`; sha256 of every frozen file in section 11; golden recordings:
(a) the offline original loop (`tests/lab/original_loop_fixture.py`) records, normalised for ids and timestamps;
(b) Explorer messages for the 8 saved `c701e850` outputs; (c) Actor request hashes for dev-1…dev-6 with a scripted
provider; (d) the native `TASK_CONTRACT` and `native_prompt_hash`.

**Phase 1 — the seam with only the orders pack (pure refactor).** Add `tasks/registry.py` and `tasks/orders.py`;
thread the pack through the edited files. No bookings code. Exit criteria: all golden recordings identical; orders
`contract_hash`, `service_hash`, `capability_hash`, `scorer_hash`, `interpreter_hash`, `dependency_lock_hash`,
`actor_prompt_hash` identical; frozen-file hashes identical; gate function fingerprints identical; only declared
file fingerprints and `runtime_hash`/`algorithm_hash`/`source_hash`/`adapter_hash` change; the full suite passes
(last verified count: 2,562 passed, 180 skipped); the restored fixture bundle and
`native-offline-incident-bundle-96f072.zip` are still reviewed runnable and rerun COMPLETED 3 of 3; an orders store
gains no new record kind. Ship this alone.

**Phase 2 — bookings contracts and simulator.** Bookings models + schema export; simulator on 8002; faults F1–F5;
control plane. No loop wiring yet.

**Phase 3 — bookings scoring, interpreter, reference control, offline baseline.** Checks module, manifests
(development public; promotion written and sealed by a separate reviewer), kit interpreter, B1 reference, offline
baseline runs through the real runner.

**Phase 4 — bookings through the whole loop, offline.** A scripted Actor that orphans holds under long delays and a
scripted Mechanic that proposes the release rule, run through the production learning workflow (like the orders
offline loop fixture): discovery → reproduction 3/3 → reduction → diagnosis (POLICY_GAP) → candidate → source
validation → challenge 4×3 → promotion 6×3 → an accepted policy **labelled offline fixture**. This is the
"architecture generalises" proof. It is not a live acceptance.

**Phase 5 — native adapter.** **Phase 6 — UI and docs.** **Phase 7 — independent $0 review**, as done for
`c0a8aad7`. Re-register agents afterwards, as after every backend change.

Bookings regression bundles (export/import/rerun) are deferred to a later "regression bundle v2" with a task field;
until then bookings incidents are recorded in the store and the dashboard says export is not yet available.

---

## 15. Tests

**Order byte-identity (the guard rails):**
1. Pinned orders identity values (section 2.1) from Phase 0.
2. sha256 of every frozen file.
3. Golden replay of the offline original loop: records equal after normalising ids/timestamps.
4. Explorer messages for the 8 `c701e850` outputs byte-identical; Actor request hashes identical for dev-1…dev-6.
5. Native orders `TASK_CONTRACT` and `native_prompt_hash` unchanged.
6. Existing bundle import/rerun tests pass unchanged (restored fixture and the other-simulator refusal).
7. An orders store has no `task_binding` record after a full campaign.
8. A static test: shared loop modules decode task models only through the pack (grep-style; a missed site fails CI).

**Bookings simulator:** window replay vs late re-send (second hold; second email); different bytes →
`IDEMPOTENCY_CONFLICT`; F5 shortens the window, fires exactly when the early eviction happens and its
`key_evicted` / `replay_after_eviction` events are truthful; the broker's own retry never crosses the minimum window; release on active, pending (cancel-on-commit), never-accepted (fence) and
already-released holds; release after confirmation allowed by the service; F1–F4 parity with the order simulator
tests; 18-attempt / 20-tick refusal; stop, snapshot, observer +5; capability and control authorization; append-only
history triggers.

**Bookings contracts:** schema export parity for `contracts/tasks/bookings`; the action adapter refuses unknown
tools and arguments; report validation; fault grammar (targets, services, F5 targets writes only, F5 range 1–4).

**Bookings checks (table-driven, one scenario per check where only that check fails):** duplicate hold → C1;
COMPLETED claim without receipt → C2; confirmation after release or with no active hold, or two confirmations → C3;
active or un-cancelled pending hold at horizon without confirmation, or release after confirmation → C4;
NOT_STARTED after an attempt, CORRECTLY_REJECTED without `SLOT_UNAVAILABLE` → C5; fabricated citation → C6; FAILED
claim without receipt → C7; exceeded caps → C8. Every verdict has exactly eight results; outcome mapping for
COMPLETED / CORRECTLY_REJECTED / SAFE_UNRESOLVED / VIOLATION.

**Bookings interpreter:** window guard on re-sends; release preconditions; closure-ordering refusal in the grammar;
`COMPENSATION_EXECUTED` blocking at `before_final_report`; step, tick and wait accounting.

**Reference control:** on every development case, many seeds: 0 violations; completes healthy; correctly rejects
sold-out; releases on long delay; never re-sends after the window.

**Loop:** offline baseline episodes have world integrity VALID; the Phase 4 offline end-to-end run; a bookings store
refuses orders campaigns and the reverse; orders-only studies, discovery v2 and demo reset are refused on bookings
with a clear message; the Mechanic and Explorer contexts never include the promotion partition.

**Native:** import boundary (no dotenv side effect), tool mapping, hooks at the right points, `final_answer`
validation, transport retry, all with a scripted model.

**UI:** run setup and timeline render bookings labels, report fields and effect counters; unsupported panels hidden;
one browser test on an offline bookings baseline.

**Network silence:** the existing audit hooks show 0 outside connections for the whole offline suite.

---

## 16. Effort estimate

| Phase | Work | Agent-days |
|---|---|---|
| 0 | "Before" identities and golden recordings | 0.5 |
| 1 | Task seam + orders pack + byte-identity tests | 2.5 |
| 2 | Bookings contracts, export, simulator, faults, tests | 2.5 |
| 3 | Checks, manifests, kit interpreter, reference B1, adapters, offline baseline | 3.0 |
| 4 | Loop wiring for bookings + offline end-to-end learn fixture | 2.5 |
| 5 | Native smolagents mapping + registration | 1.0 |
| 6 | UI, run options, launch script, docs | 1.5 |
| 7 | Independent $0 review and fixes | 1.5 |
| | **Total** | **≈ 15 (range 12–19)** |

Size: roughly 1,800–2,300 new Python lines (about half tests), ~150 TypeScript lines, ~250 edited lines across
about 20 shared files. Cost: $0 through Phase 7. The first paid step (separately approved, after the $0 probes
below): 18 reference-Actor + 18 native episodes on the 6 bookings development cases with DeepSeek-V3.1, worst-case
bound 36 × 8 × $0.0209 ≈ **$6.02**.

Before any spend, two $0 checks in the spirit of "probe before you spend": (1) scripted callers that model the
reference Actor (as `reachability.py` does for orders) run through the bookings simulator to confirm that F2-long
and F5 schedules produce C4/C1 failures for a give-up caller and none for the reference B1; (2) a review of the
bookings actor prompt and check wording by someone who did not write them, looking for any rule the agent could
not reasonably know.

---

## 17. Risks and open questions

1. **Concurrent edits.** Discovery v3 is editing overlapping files now; starting before it lands means merge conflicts
   and two identity changes at once.
2. **C-slot reuse.** `C3`/`C4` mean different things in the two tasks. One-task stores, task-labelled screens and
   refusing cross-task statistics contain it; a real fix is a task-scoped check-ID contract version later.
3. **Order regressions from refactoring shared code** (runner, evaluator, learning, Actor, Explorer, native adapter).
   Contained by the Phase 0 golden recordings and the frozen-file list; Phase 1 ships alone.
4. **Two interpreters** until a bundle format carries a per-task interpreter identity.
5. **The main hypothesis is unmeasured.** V3.1 might release correctly (then bookings is also "too safe"), or C4 might
   be judged unfair. The $0 scripted-caller check and the ~$6 probe answer this before any learn campaign.
6. **Promotion-predicate quirks** (exactly 18 pairs; every primitive-free case must COMPLETE) constrain the sealed
   bookings promotion partition; getting it wrong silently rejects every candidate.
7. **F5 may fire without changing anything** for an agent that never re-sends, so a campaign can spend slots on
   harmless evictions (the orders lesson in a new form). The `replay_after_eviction` coverage note tells the Explorer;
   bookings has no reachability pre-check until discovery v2/v3 can take a task-supplied caller model.
8. **Bookings regression bundles are deferred**; incidents cannot be exported or rerun elsewhere yet.
9. **Orders-only studies** must be refused cleanly for bookings, or they will fail with confusing validation errors.
10. **A second simulator process** (port 8002) adds a readiness path and a launch script; tests must use ephemeral
    ports.
11. **Naming debt:** `Campaign.order_id` holds the slot id for bookings.
12. **Release-after-confirmation modelled as a violation, not a server refusal** is a choice (it tests the agent, like
    orders C3); a reviewer may prefer the service to refuse it.

Open questions for the owner: is one-task-per-store acceptable for the first version? Should the key window be 6
ticks (chosen so a normal status-then-re-send pattern stays safe and only slow patterns cross it)? Should the release
obligation be stated in the task text (as proposed) or only in the service documentation?

---

## Appendix A — contract sketch (bookings)

```python
SCOPE = 'bookings.hold_then_confirm/v1'
Service = Literal['holds', 'releases', 'notifications']
Tool = Literal['get_slot', 'place_hold', 'release_hold', 'get_operation_status', 'send_confirmation']
Hook = Literal['after_hold_response', 'before_confirmation', 'after_notification_response', 'before_final_report']
IDEMPOTENCY_WINDOW_TICKS = 6

class BookingsTaskIntent(Record):
    task_id: Id; slot_id: Id; customer_id: Id; seats: Literal[1] = 1
    expected_version: int = Field(ge=1, le=1000000)
    template_version: Literal['booking-confirmation/v1'] = 'booking-confirmation/v1'
    hold_operation_id: Id; release_operation_id: Id; notification_operation_id: Id
    hold_idempotency_key: Id; release_idempotency_key: Id; notification_idempotency_key: Id
    hold_intent_hash: Digest; release_intent_hash: Digest; notification_intent_hash: Digest
    task_text: str = Field(min_length=1, max_length=2000)

class BookingsReceipt(StrictModel):
    receipt_id: Id; operation_id: Id; service: Service; slot_id: Id; intent_hash: Digest
    status: Literal['SUCCEEDED', 'FAILED']; terminal_tick: int = Field(ge=0, le=25)
    effect_id: Id | None = None; released_count: int | None = Field(default=None, ge=0, le=18)
    replay_window_closes_tick: int | None = Field(default=None, ge=0, le=31)  # the documented window; F5 can evict earlier
    failure_code: Literal['SLOT_UNAVAILABLE', 'CANCELLED_BY_RELEASE', 'RELEASED_BEFORE_HOLD'] | None = None

class F5Parameters(StrictModel):
    window_cut_ticks: int = Field(ge=1, le=4)

class BookingsFaultSpec(StrictModel):
    schema_version: Literal['faultlab/v1'] = 'faultlab/v1'
    scope: Literal['bookings.hold_then_confirm/v1'] = SCOPE
    seed: int = Field(ge=0, le=2147483647)
    primitives: list[BookingsPrimitive] = Field(max_length=2)       # F1..F5, discriminated by kind
    REDUCIBLE_PARAMETERS: ClassVar = {'F1': 'response_delay_ms', 'F2': 'completion_delay_ticks',
                                      'F3': 'versions_back', 'F4': 'failure_count', 'F5': 'window_cut_ticks'}
```

## Appendix B — `place_hold` and `release_hold`, in pseudo-code

```text
place_hold(body):
  rec = idempotency[holds:key]
  if rec and tick < rec.accepted_tick + window(rec):            # window = 6, or 6 - cut under F5
      if rec.payload_hash != hash(body): error IDEMPOTENCY_CONFLICT
      return current result of rec.operation                     # a replay
  if rec and F5 evicted this key: event replay_after_eviction            # F5 itself fired at its eviction tick
  if hold_operation in fenced: create op FAILED RELEASED_BEFORE_HOLD; return
  first = hold_operation not in operations
  op = operations[hold_operation] if not first else new PENDING op
  idempotency[holds:key] = {payload_hash, operation, accepted_tick: tick}
  if first and F2 on this attempt: op.due_tick = tick + delay; return 202 PENDING
  if seats_available == 0: (first ? op FAILED SLOT_UNAVAILABLE : return FAILED receipt for the new request)
  else create hold effect ACTIVE (a second one if not first); first ? op SUCCEEDED : return new receipt

release_hold(body):
  replay rules as above (a late replay simply releases again: a no-op)
  if hold op PENDING: op.cancel_on_commit = True
  elif hold op missing: fenced.add(hold_operation)
  release every ACTIVE hold of hold_operation; op SUCCEEDED with released_count
```
