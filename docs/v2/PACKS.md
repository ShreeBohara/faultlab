# v2 task packs

Stage 1, phase 1.3. A task pack is the unit the lab tests, the bench ranks and effectsafe enforces:
one workflow, declared once, with its world handler, tools, hooks, fixtures, scenarios and
properties. `faultlab/packs/base.py` is the interface; `faultlab/packs/orders/pack.py` is the first
instance; `faultlab/packs/registry.py` names the reviewed packs; `python -m faultlab packs` lists
them and prints a manifest.

## What a pack declares

| Part | Type | What it is |
|---|---|---|
| `pack_id`, `version`, `description` | strings | the identity every plan and result carries |
| `handler_factory` | `() -> WorldHandler` | the business semantics the kernel hosts (phase 1.2) |
| `business_router` | `(store, limits) -> APIRouter` | the pack's HTTP routes over the kernel's dispatch |
| `intent_model`, `report_model` | strict models | what a trial starts from and what the agent hands back |
| `allocate_intent` | `(fixture_id, namespace) -> dict` | an intent the handler accepts for the fixture, every identity derived from the namespace (the worker passes the attempt id; `example_intent` uses `"example"`) |
| `service_of` | `(tool, request) -> str` | the kernel service a call is dispatched on (orders: the status read names its service) |
| `tools` | effectsafe `ToolContract` per tool | read or write, identity scope, commit boundary, status lookup, errors proving no effect |
| `hooks` | names | where a recovery rule may run |
| `fixtures` | names | the initial worlds the handler knows |
| `scenarios` | `Scenario` | a fixture, a kernel-form fault spec, and the class of outcome the scenario is meant to produce |
| `properties` | `PropertySet` | the fixed-code properties (id, title, family, severity) pinned to the sha256 of their checker file |
| `diagnostics` | JSON | optional pack-specific diagnostic profiles and their recorded hashes |

A pack refuses an inconsistent declaration when it is constructed: duplicate names, a scenario on
an unknown fixture, a fault placed on an undeclared tool, or a keyed write without a read tool for
its status.

- `manifest()` is the declaration as plain JSON (contracts with their set-valued fields sorted, each
  scenario with its derived v2 `FaultSchedule`, the intent and report JSON schemas, the properties
  and their checker digest). `digest()` is the content hash of that manifest and becomes
  `TrialPlan.pack_digest`.
- `plan(scenario_id, agent=..., environment=..., protocol_version=..., caps=...)` fixes one scenario
  into a `TrialPlan` before admission, with the pack digest and the properties digest on it.
- `app(database_dir=..., control_token=...)` hosts the pack on the kernel.
- A scenario's `schedule()` uses the placement mapping of the legacy projection
  (`faultlab/evidence/legacy.py`, unchanged), so a planned fault and a projected one are spelled
  the same way. The kernel itself numbers executions `fault-1`, `fault-2`; reconciling those two
  spellings is part of the trial worker (phase 1.5).

## The orders pack

`orders.upgrade_then_confirm/v1`, version 1, declared from public and already-recorded sources:

- Tools: `get_order` and `get_operation_status` are reads. `update_order` is a keyed write (client
  key in the payload, a different payload under the same key is a conflict, the commit is
  asynchronous and `get_operation_status` reports it; `VERSION_CONFLICT`, `IDENTITY_CONFLICT` and
  the kernel's refusals before admission such as `TRANSIENT_UNAVAILABLE` prove no effect).
  `send_confirmation` is a keyed write committed on its acknowledgement.
- Hooks: the legacy four. Fixtures: `standard-v1`, `history-v1`.
- Scenarios: the six cases of the public development split (`audit/development.json`), copied
  case for case. The promotion and final-audit partitions stay out of the pack.
- Properties: C1 to C8 with the public one-liners the Explorer prompt shows, the family and
  severity of the legacy projection, and the sha256 of `backend/app/referee/checks.py` pinned as a
  constant. The checker is never read; a change to its bytes fails the conformance test.

## Evidence

`backend/tests/v2/test_pack_conformance.py`, parameterized over the registry: the manifest is
canonical JSON with a stable digest; the handler's pack id and fixtures agree with the pack; names
are unique and consistent; every scenario's fixture, fault spec and intent create a world on the
kernel; `plan()` yields a valid plan; the pack hosts a kernel service; inconsistent declarations are
refused; the CLI lists and prints. Orders parity: scenarios equal the legacy development manifest
(and their schedules equal the legacy projection's placements), hooks equal the legacy `HOOKS`,
tools equal the legacy `Tool` literal, the intent and report models' JSON schemas equal the legacy
`TaskIntent` and `TaskReport` schemas, and the properties digest equals the sha256 of the checker
computed in the test.

Not in this phase: moving the orders checks themselves out of `backend/app/referee` (the legacy
scorer stays the authority and its digest is what the pack pins), the bookings pack, and the trial
worker that runs a plan (1.5).
