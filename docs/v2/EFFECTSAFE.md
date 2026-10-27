# effectsafe 0.1 (alpha): the runtime action layer

Stage 1, phase 1.4, first cut. `effectsafe/` is a separate package at the repository root; it
never imports `faultlab` (the lab imports it). It is the legacy broker
(`backend/app/adapters/journal.py`, `business_tools.py`) and the policy interpreter
(`app/lab/policy_interpreter.py`, `policy_state.py`) extracted and made task-agnostic.

## Four pieces

- **`intent`**: an operation is `(operation_id, action, scope, payload)` with a digest over
  action, scope and payload (`intent_hash`), canonical bytes identical to the lab's, and a
  deterministic idempotency key derived from the intent and a namespace (same intent, same run,
  same key; a different payload is a different intent).
- **`contract`**: `ToolContract`, what a connector promises about a tool: whether it keys the
  operation (`identity_scope`), what a replay does, where the commit boundary is, which errors
  prove no effect. Shared object with the lab's packs and the future connector profiles.
- **`journal`**: SQLite, append-only. `prepare` pins the exact bytes (a change is refused; a
  client key the caller already placed in the payload is kept, otherwise one is derived);
  `dispatch` records the attempt before the request leaves and returns the bytes to send;
  `deliver` folds evidence into the outcome; `observe` folds what a status read reported into
  the write it reports on (only a pending or terminal state word moves the outcome, so a status
  read can never invent an attempt). A resend is only ever the pinned bytes, and a write
  the provider cannot recognise (`identity_scope == "none"`) is refused while any attempt's
  effect is unknown (`UnsafeResend`). That one refusal is how a duplicate hold or payment is
  prevented.
- **`outcome`**: the lattice `NOT_STARTED → UNKNOWN → PENDING → SUCCEEDED | FAILED`, plus
  `CONFLICT` for contradicting terminals. `UNKNOWN` and `PENDING` never decay to `NOT_STARTED`; a
  terminal never reverts; only an error the contract says happens before admission returns a
  write to `NOT_STARTED`.
- **`rules`**: the recovery-rule language (hooks, conditions, steps) and its interpreter, generic
  over operation and hook names. Conditions read the journal only, never the agent's beliefs;
  steps are bounded (read a status, wait, resend the pinned bytes, require a receipt or a report
  label, end unresolved or with a terminal failure); a hook never re-enters for the same proposal.
  `require_label` (added 2026-10-26 for the repair study) blocks, at a `report` gate, a report whose
  label for one claim is not among the expected ones; the agent is told why and may report again.
  It never rewrites a label, a `write` gate ignores it, and a missing label never passes
  ([VIOLATION_GAP_DESIGN_2026-10-25.md](../VIOLATION_GAP_DESIGN_2026-10-25.md), option B.1).

## Evidence

`backend/tests/v2/test_effectsafe.py`: identity equals the lab's; pinned bytes; journal before
the wire; the lattice (lost reply stays `UNKNOWN`, acceptance to `PENDING`, receipt to
`SUCCEEDED`, contradiction to `CONFLICT`); the non-idempotent create refused while unknown and
allowed after a pre-admission error; reads always resendable; rules reading, waiting, blocking a
dependent write without a receipt, the step budget, and `require_label` (blocks only at the report gate,
only when its condition holds, never on a write gate; shape errors refused).

Not done: receipts (signed, hash-chained), approvals, connector profiles, the transports and the
framework integrations; and the lab's broker still runs its own copy of this logic until a later
phase switches it over (parity with the 19 adapter tests is that phase's exit evidence).
