# v2 environment kernel

Stage 1, phase 1.2. `faultlab/env/kernel` is the task-agnostic world kernel; `faultlab/packs/orders`
is the first `WorldHandler` on it. Both are new implementations beside `backend/app/simulator`,
which is left byte for byte as it is: its identity (`service_hash`) is pinned by every earlier
export and registration, and the legacy loop keeps using it until a later phase switches over
and records that identity change on purpose.

## What the kernel owns

- One SQLite file per world: an atomic `state` row, an append-only `events` table, and the
  history tables a handler declares (`projections` and `receipts` for orders), all protected by
  `UPDATE`/`DELETE` triggers. A world is reachable only with the capability returned at creation.
- Admission (`dispatch`): capability check, transport identities, the attempt and tick budgets,
  one tick per admitted request, the `http_attempt` and `request_rejected` events.
- Logical time: ticks advance only at admitted requests and explicit bounded waits; after `stop`,
  exactly one observer advance of `horizon_ticks`.
- Fault placement by `(tool, service, occurrence)`: F4 (transient failure before any effect) and
  F1 (reply lost after the effect committed) are placed by the kernel itself, in the legacy order
  (a transient failure prevents a lost reply on the same call; a lost reply triggers only when the
  handler reports a committed effect, otherwise it is recorded as prevented). F2 (asynchronous
  completion) and F3 (stale read) carry business meaning, so the handler places them from the
  matches the kernel hands it.
- The control API over loopback (`/control/worlds`, `/snapshot`, `/faults`, `/advance`, `/stop`),
  with a hook for pack-specific control routes (the orders diagnostic fixture).

## What a handler owns

`state["pack"]` and nothing else: the validated intent, the initial state of a fixture, which
schedules it can honour, how each tool performs (returning the HTTP status, the result and
whether an effect committed), what becomes due at a tick, which rows go to the history tables,
and the evaluator's snapshot. `faultlab/env/kernel/handler.py` is the interface; the orders
handler is a faithful port of the legacy `business.py`, `clock.py` and fixture rules.

## Evidence

- `backend/tests/v2/kernel/`: the legacy simulator's business-contract, socket-level fault and
  diagnostic-fixture tests (19 tests, 20 with the parametrized one) copied with their imports pointed
  at the kernel and one direct state mutation moved to `state["pack"]`; all pass.
- `test_generic_handler.py`: a two-tool ledger pack with its own service name, histories and
  limits runs on the same kernel: budgets, F4/F1 placement, idempotent replay and immutable
  histories hold without the kernel knowing what a ledger is.

Not done in this phase: the bookings pack (`taskpacks/bookings_move_with_hold`) still runs on its
own world; moving it onto the kernel is the abstraction test of a later phase, and the legacy
simulator is not yet replaced.
