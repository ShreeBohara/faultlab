# A second FaultLab task, built as the first "task pack"

Design only. Written 2026-09-29 by a read-only design agent. Nothing in `faultlab/` was edited
except this file. No provider, model or W&B call was made, no service was started, `.env` was
never opened, and `backend/app/referee/checks.py`, `audit/promotion.json`, the final-audit files
and `artifacts/heldout2/` were never opened. What C1–C8 mean is taken from the public
descriptions in `docs/demo-guide.md` §10 and `backend/app/agents/explorer.py` (`PUBLIC_INVARIANTS`).

---

## 0. The short version

**What FaultLab can do today.** It tests one task: *upgrade an order to express shipping, then send
one truthful confirmation*. Almost every layer knows this task by name, from the wire contracts to
the simulator, the policy language, the prompts, the reducer, the registry and the dashboard.

**What this document proposes.** It proposes a **task pack**: a folder that describes a new task.
The folder holds a manifest (tools, faults, invariants, hooks, report shape, budget), a list of
public development cases, and two small Python files (the service logic and the task's own
checks). A new engine package, `backend/app/taskpacks/`, reads a pack and runs the same loop the
order task uses: baseline, then Explorer → reproduce → reduce → diagnose → Mechanic →
source validation → challenge → promotion. After the engine exists, adding a task means adding a
folder and one line in a reviewed lock file. No core code changes.

**The second task, which is the first pack.** `bookings.move_with_hold/v1` asks the agent to *move
a synthetic booking to a new time slot by placing a hold, moving onto the hold, and cleaning up
any hold it did not use*. This fails in a different way from the order task:

| | Order task (today) | Booking task (proposed) |
|---|---|---|
| Writes | Every write can be safely repeated (same bytes, same key) | Placing a hold is **not** safe to repeat. Each call creates a new hold. |
| Identities | Trusted code supplies all of them | The agent must **carry a hold id** from one tool result into later calls |
| What goes wrong after partial success | The agent must stop and report truthfully | The agent must **undo** the partial step (release the hold), then report |
| Waiting | Usually helps: a pending upgrade finishes | Can hurt: **holds expire**, so waiting too long loses the slot |
| Main danger | False success claims, bad report words | **Duplicate or abandoned holds**, caused by blindly retrying a create call |

**What must stay exactly the same.** Nothing that defines the order task changes. That covers the
simulator folder (service hash `3ce5bcd2…`), `contracts/*.schema.json` and `contracts/models.py`
(contract hash `6f9d7783…`), `checks.py` (scorer hash), the interpreter files (interpreter hash
`6da0714a…`), the order capability hash, the actor prompt, `agents/`, `adapters/`, the native
adapter files, `audit/*.json`, and every file that `scripts/experiments/gate_freeze.py` fingerprints.
Because the engine lives outside `lab/` and `referee/`, **the order task's `algorithm_hash` also
stays the same**. Only `runtime_hash` moves, and it moves with any change to `backend/app`. A guard
test that pins these values goes in **before** any engine code.

**Effort.** About 14–19 focused engineering days for a usable baseline environment (offline and
live baseline, dashboard, no learning loop). About 25–33 days for the full loop, native smolagents
and a Weave evidence path. Before the learning kernel is built, a cheap live baseline probe decides
whether the booking task produces the repeated, near-certain failures the loop needs (§12). The
worst-case bound for that probe is about $10.

---

## 1. How the order task is wired today (what I read)

**In one line:** the loop *machinery* is mostly general, but order knowledge is written into about
twenty files, and several of those files are frozen by identity hashes.

### 1.1 The path of one episode

1. `lab/run_plans.py` builds a reviewed plan. `TASK = 'orders.upgrade_then_confirm/v1'`, six public
   cases `dev-1…dev-6` (`CASE_LABELS`), loaded from `audit/development.json` through
   `referee/manifests.load_manifest`.
2. `lab/coordinator.py` creates the campaign, holds **one active execution at a time**
   (`self.lock`, `self.active_id`), and calls `EpisodeRunner.run` or `run_learning_cycle`.
3. `lab/runner.py` `EpisodeRunner.run`:
   - `adapters/journal.allocate_intent` makes the trusted identities (upgrade and notification
     operation ids, idempotency keys, intent hashes).
   - `WorldClient.create` builds a world in the separate simulator process (port 8001).
   - It then runs the actor with a `BusinessToolBroker` (four tools) and a `PolicyInterpreter`
     (four hooks).
   - Afterwards it stops the world, takes the decision snapshot, advances the observer 5 ticks,
     takes the horizon snapshot, checks `world_integrity`, and calls `referee.checks.score`, which
     returns a `Verdict` with exactly C1–C8.
4. The simulator (`simulator/business.py`, `faults.py`, `clock.py`, `storage.py`) serves four HTTP
   routes. It applies F1–F4 at the dispatch layer and keeps one SQLite file per world.

### 1.2 The learning loop

`lab/learning.py` runs the loop. It calls `agents/explorer.py` (fault selection), then
`lab/reproduction.py` (3 of 3), `referee/reducer.py` (neighbours by F1–F4 parameter),
`lab/diagnosis.py` (interventions and `runtime_contract` text), `agents/mechanic.py` (policy
proposal), `lab/evaluation.py` (paired batches), `lab/challenge.py` (4 schedules × 3 pairs) and
`lab/promotion.py` (fixed predicate; `paired_complete(promotion,18)`).

### 1.3 Where order knowledge is hard-coded

| File | What it knows about the order task |
|---|---|
| `contracts/models.py` | `SCOPE`, `Tool`, `Service`, `Status`; `Invariant = C1…C8`; `Condition`, `Hook`; the four action models; `TaskReport`; `TaskIntent`; F1–F4; `FaultSpec.scope`; `RecoveryPolicy.scope`; `Verdict` (exactly eight checks, plus `upgrade_effects` and `notification_effects`); `AgentRegistration.policy_hooks` (exactly the four order hooks); `WorldSnapshot.orders`; `RegressionBundle` fixture and scope |
| `simulator/*` | Four routes; the order and notification state machine; F1–F4 mechanics; fixtures `standard-v1` and `history-v1`; the diagnostic capability profile |
| `adapters/journal.py`, `business_tools.py` | Upgrade and notify identities; four-tool request mapping; `validate_result_binding` |
| `lab/policy_interpreter.py`, `policy_state.py` | The meaning of each step and condition for `orders` and `notifications` |
| `agents/actor.py`, `prompts/actor.md`, `reference.py` | Which hooks fire around `update_order` and `send_confirmation`; the task prompt; the handwritten B1 control |
| `agents/explorer.py` + prompts | `PUBLIC_INVARIANTS` C1–C8; coverage keyed by the four tools; F1–F4 ranges written into the prompt text |
| `agents/prompts/mechanic.md`, `diagnosis.md` | The order scope and policy grammar written into the prompt text |
| `lab/diagnosis.py` | `runtime_contract` (text for every hook, step and condition); `summarize_evidence` identity field names |
| `referee/reducer.py` | `PARAMETERS` for F1–F4; the F1 value ladder; "target in C1…C8" |
| `lab/learning.py`, `lab/challenge.py` | The fixture is chosen by "any F3"; the fallback uses `load_cases('development')[i%6]`; the challenge imports `simulator.faults.validate_schedule` |
| `lab/configuration.py` | `capability_hash` is a literal of the order scope, four tools and four hooks |
| `lab/reachability.py` | A caller model of the reference Actor on the order simulator (discovery v2) |
| `integrations/registry.py` | `HOOKS`; `reset_profile_id='fresh-orders-v1'`; limitation text |
| `integrations/external_agent.py` | `TOOLS`, `TASK_CONTRACT`, five native `Tool` classes, the tool-name check in `parse_tool_calls` |
| `frontend` `RunSetup.tsx`, `Timeline.tsx` | "Authorized order"; upgrade and notification effect fields; report fields |

### 1.4 What is already general and can be imported as-is

**In one line:** these helpers never mention orders, so a pack can call them without any change.

- **Budgets:** `lab/budgets.py` (`EpisodeMeter`, `CampaignLedger`, `EpisodeBudget`, `CampaignBudget`,
  `Usage`).
- **Store and ownership:** `lab/storage.py` (`LabStore`, per-kind records, pointers, events) and
  `lab/ownership.py` (`CoordinatorLease.acquire(path)` works per store path).
- **Providers and requests:** `providers/runtime.py`, `contracts/tokens.py` (input admission),
  `agents/transport_retry.py`, `lab/provider_failures.py`.
- **Actor context:** `agents/progress.py`: `evidence_labels`, `decode_citations`, and `turn_message`
  under the indexed-evidence protocol (v4, the `obs-N` labels that removed fabricated citations
  in Phase 11).
- **Pure loop predicates:** `reproduction.valid_trial` and `reproduced`;
  `evaluation.paired_complete`, `observed_candidate_violations` and `aggregate_usage`;
  `promotion.promotion_decision`; `learning.source_validation_assessment`;
  `diagnosis.trial_outcomes`, `reduction_context` and `observed_outcomes`;
  `runner.world_integrity`. These read only attribute names (`lifecycle`, `outcome`,
  `failed_checks`, `fault_scheduled`, `fault_triggered`, `usage`, `scenario_hash`, `policy_hash`,
  `trial_index`, `world_id`, `episode_id`, `events`, `tick`).
- **Shared helpers:** `contracts/task_text.py`, `canonical_json`, `content_hash`, `new_id`, `Id`,
  `Digest`, `StrictModel`, `Event`, and telemetry spans (`telemetry/tracing.py`).

### 1.5 What keeps the order task's identity fixed

**In one line:** each identity is a hash of specific files, so any change to those files changes
the identity.

- `configuration.frozen_configuration` computes:
  - `service_hash = tree_hash(backend/app/simulator)`
  - `contract_hash = hash(contracts/*.schema.json, service_hash)`. The glob looks only at the top
    folder; I checked that it does not read subfolders.
  - `scorer_hash` from `checks.py`
  - `interpreter_hash` from `policy_interpreter.py`, `policy_state.py` and `budgets.py`
  - `adapter_hash = tree(adapters)`, `source_hash = tree(agents)`, `actor_prompt_hash`
  - `algorithm_hash = tree(lab) + tree(referee)`
  - `runtime_hash = tree(backend/app)` (only `.py` and `.md` files)
- `tests/simulator/test_entry_point.py` pins the service and contract hashes, so that exported
  bundles and registrations stay compatible.
- `scripts/experiments/gate_freeze.py` fingerprints `evaluation.py`, `promotion.py`, `runner.py`,
  `reproduction.py`, `diagnosis.py`, `policies.py`, `mechanic.py`, `actor.py`, `progress.py`,
  `checks.py`, `manifests.py`, several telemetry files and `audit/*.json`. Closed experiment
  runners refuse to run if a declared freeze differs (see the `runner.py = '0'*64` tamper tests
  in `tests/experiments/`).

**Consequence for the design:** the engine must not edit any of these files, and must not add
files under `simulator/`, `agents/`, `adapters/`, `lab/`, `referee/`, or top-level
`contracts/*.schema.json`.

---

## 2. Design choices, and the options I rejected

**In one line:** each choice below keeps the order task untouched while giving new tasks a clean
home.

| Question | Choice | Rejected option and why |
|---|---|---|
| Where the engine lives | New package `backend/app/taskpacks/` | Editing `lab/`, `referee/` or `simulator/` in place. That would move `algorithm_hash`, the service hash or gate fingerprints, and closed runners would refuse. |
| Where packs live | Repo root `taskpacks/<task_definition_id>/`, outside `backend/app` | Inside `backend/app`. Then **adding any pack** would move the order task's `runtime_hash` and force the order agents to register again. |
| Check ids | Each pack names its own ids (e.g. `B1…B8`) and stores them in pack-owned contracts | Reusing the `C1…C8` slots so today's `Verdict` and `TrialResult` validate. "C3" would then mean different things in different tasks, stored records would be ambiguous, and `Verdict` still carries order-only effect fields. |
| Contracts | New `taskpacks/contracts.py`, schemas exported to `contracts/packs/*.schema.json` (a subfolder, so the order contract glob does not see them) | Adding generic models to `contracts/models.py`. `export.py` would add schema files and move `contract_hash`. |
| Services | A second, generic simulator host process (port 8002 by default), with pack service logic in `world.py` | Mounting pack routes inside today's simulator. That moves the service hash. In-process worlds without HTTP were also rejected, because lost-response faults need real socket timeouts, just as F1 does today. |
| Records | A separate store file `lab-packs.sqlite3` in the same data folder, opened with the existing `LabStore`, leased with the existing `CoordinatorLease`, and using `pack_*` record kinds | A shared `lab.sqlite3`. It would work, but pack runs would then change the order store's bytes, and order tools that scan a store (for example `check_clock_drift.py`) could misread pack records. |
| One run at a time | The pack executor takes the same coordinator lock and the same `active_id` slot, so an order run and a pack run can never overlap. Three existing studies already claim the slot this way (§7.5). | Adding a public `claim_execution()` method to `coordinator.py`. It is cleaner, but it moves `algorithm_hash`. This is kept as a fallback (§10.3). |
| Is pack code trusted? | Pack Python runs only when its file hashes match a reviewed lock file (`taskpacks/packs.lock.json`). Request data never chooses a pack. An import allowlist is checked statically. | Loading any folder found on disk. |
| Discovery protocol for packs | v1 (every valid new pick runs), plus a static "cannot fire" filter taken from the manifest | Porting the discovery v2 reachability caller model. It models the reference Actor on the order simulator only, and another workflow is editing discovery right now. |

---

## 3. The task pack format

**In one line:** a pack is one folder. Most of it is data. Only the service logic and the
task-specific checks are Python.

### 3.1 Folder layout

```
taskpacks/
  packs.lock.json                          # reviewed allowlist: id -> pack_hash, schema_hash
  bookings.move_with_hold/                 # folder name == task_definition_id without "/v1"
    pack.json                              # declarative manifest (below)
    cases/development.json                 # public development cases, with manifest_hash
    prompts/actor.md                       # the task paragraph shown to the Actor
    prompts/brief.md                       # the task paragraph shown to Explorer and Mechanic
    world.py                               # service logic: state, tool handlers, completion, snapshot
    checks.py                              # the task's own invariants (not the shared ones)
    reference.py                           # handwritten deterministic control (required by `pack check`)
    README.md                              # notes for people
audit/packs/bookings.move_with_hold/       # sealed promotion and final partitions (made by `pack seal`)
contracts/packs/*.schema.json              # exported pack wire schemas (outside the order glob)
backend/app/taskpacks/                     # the engine, added once
```

### 3.2 The manifest (`pack.json`), trimmed for the booking task

```json
{
  "pack_format": "faultlab-task-pack/v1",
  "task_definition_id": "bookings.move_with_hold/v1",
  "title": "Move a booking using a hold",
  "default_task_text": "Move the authorized booking to the target time slot. Leave no unused hold behind, and report truthfully.",
  "subject": {"field": "booking_id", "label": "Authorized booking"},
  "services": ["calendar", "bookings"],
  "identities": {
    "trusted": ["task_id", "booking_id", "target_slot", "move_operation_id", "move_idempotency_key", "move_intent_hash"],
    "from_observation": {"hold_id": {"delivered_by": ["place_hold", "list_holds"]}}
  },
  "tools": [
    {"name": "get_booking",     "service": "bookings", "kind": "projection",         "arguments": {}},
    {"name": "list_holds",      "service": "calendar", "kind": "authoritative_list", "arguments": {}},
    {"name": "place_hold",      "service": "calendar", "kind": "create",  "idempotent": false, "arguments": {}},
    {"name": "move_booking",    "service": "bookings", "kind": "operation_write", "idempotent": true, "operation": "move",
                                "arguments": {"hold_id": {"type": "string", "identity": "hold_id"}}},
    {"name": "release_hold",    "service": "calendar", "kind": "compensation", "idempotent": true,
                                "arguments": {"hold_id": {"type": "string", "identity": "hold_id"}}},
    {"name": "get_move_status", "service": "bookings", "kind": "operation_status", "operation": "move", "arguments": {}}
  ],
  "operations": {"move": {"write": "move_booking", "status": "get_move_status",
                          "failure_codes": ["MOVE_REJECTED", "HOLD_NOT_ACTIVE", "VERSION_CONFLICT"]}},
  "fixtures": {"standard-v1": {"booking_version": 1, "target_capacity": 3, "hold_ttl_ticks": 10},
               "history-v1":  {"booking_version": 4, "target_capacity": 3, "hold_ttl_ticks": 10}},
  "faults": {"max_primitives": 2, "occurrence": [1, 18], "kinds": {
    "lost_response":         {"engine": "lost_response", "targets": ["place_hold", "move_booking", "release_hold"],
                              "parameters": {"response_delay_ms": [1500, 3000]}, "reduce": {"parameter": "response_delay_ms", "direction": "down", "ladder": [3000, 2500, 2000, 1500]}},
    "commit_then_error":     {"engine": "commit_then_error", "targets": ["place_hold", "release_hold"],
                              "parameters": {"error_code": ["INTERNAL_ERROR"]}, "reduce": null},
    "transient_unavailable": {"engine": "transient_unavailable", "targets": "*", "order": "first",
                              "parameters": {"failure_count": [1, 18]}, "reduce": {"parameter": "failure_count", "direction": "down"}},
    "stale_read":            {"engine": "stale_read", "targets": ["get_booking"], "order": "last", "requires_fixture": "history-v1",
                              "parameters": {"versions_back": [1, 3]}, "reduce": {"parameter": "versions_back", "direction": "down"}},
    "delayed_completion":    {"engine": "delayed_completion", "targets": ["move_booking"], "order": "first",
                              "parameters": {"completion_delay_ticks": [1, 20], "terminal_status": ["SUCCEEDED", "FAILED"], "failure_code": [null, "MOVE_REJECTED"]},
                              "reduce": {"parameter": "completion_delay_ticks", "direction": "down"}},
    "early_expiry":          {"engine": "pack", "targets": ["place_hold"],
                              "parameters": {"expires_after_ticks": [1, 5]}, "reduce": {"parameter": "expires_after_ticks", "direction": "up"}}
  }},
  "hooks": ["before_place_hold", "after_place_hold_response", "before_move_booking", "after_move_booking_response", "before_final_report"],
  "conditions": { "...": "see §6" },
  "steps":      { "...": "see §6" },
  "report":     { "...": "see §5.4" },
  "invariants": [ {"id": "B1", "name": "Authorized scope", "public": "...", "implementation": "pack:scope"},
                  {"id": "B6", "name": "Delivered cited evidence", "public": "...", "implementation": "shared:cited_evidence"} ],
  "budget": {"http_attempts": 18, "actor_calls": 8, "wait_cycles": 4, "ticks": 20, "policy_steps": 32, "wall_seconds": 90},
  "observer_horizon_ticks": 5,
  "discovery": {"protocols": ["faultlab-discovery/v1"], "static_cannot_fire_rules": true},
  "native": {"smolagents": {"final_answer": "Return the exact MoveReport object.", "tool_descriptions": { "...": "..." }}}
}
```

### 3.3 Rules the engine applies to every manifest

- **Every name must resolve.** Every tool, hook, condition, step and invariant must point to a
  declared thing. Every fault target must be a tool of a kind the fault engine supports. For
  example, `delayed_completion` needs an `operation_write` tool, and `stale_read` needs a
  `projection` tool plus a fixture with enough history.
- **The budget can only shrink.** It must fit inside today's `EpisodeBudget` maxima, so the
  shared `EpisodeMeter` needs no change.
- **Reduction must move toward the easier fault.** Each fault kind declares its reduction
  direction. `early_expiry` reduces **up**, because a longer expiry is the gentler fault. Today's
  reducer lowers every parameter, which would make that fault harsher.
- **Order-sensitive kinds say which match wins.** `first` or `last`, with the same meaning as
  today's F4/F2 (first match wins) and F3 (last match wins). This lets the order-aware schedule
  identity work for any pack.
- **Typed models are generated once.** Action, report, fault-spec, policy and Explorer-output
  models are built from the manifest with `pydantic.create_model`. Their JSON schema hash is pinned
  in `packs.lock.json`, so a pydantic upgrade that changes a schema is caught, not silently accepted.

### 3.4 The small Python part and its trust boundary

**What a pack must provide.**

- `world.py` must provide `initial_state(fixture, intent)`, `handle(tool, args, state, ctx)`,
  `project(state, versions_back)`, `complete_due(state, tick)`, `private_snapshot(state)`, and
  `apply_pack_fault(kind, params, state, ctx)` (needed only for faults marked `engine: "pack"`).
- `checks.py` must provide one function per `pack:` invariant, with a fixed signature:
  `(intent, report, observations, decision, horizon, usage, faults) -> CheckOutcome`.

**How it is kept safe.**

- **Import allowlist.** Pack modules may import only `app.taskpacks.sdk` and the standard
  library's `dataclasses`, `typing` and `copy`. `pack check` enforces this by reading the code (a
  static AST check). It also forbids `open`, `os`, `socket`, `subprocess`, `importlib` and
  environment access.
- **Hash check before running.** The loader reads each file, compares its hash with the lock file,
  and only then imports it (with `importlib.util.spec_from_file_location`) under a synthetic
  module name. A mismatch refuses the pack before any of its code runs.

### 3.5 Onboarding a new task, step by step

1. `python -m app.taskpacks.cli new <id>` scaffolds the folder.
2. The developer fills in `pack.json`, `world.py`, `checks.py`, `reference.py` and the cases.
3. `python -m app.taskpacks.cli check <id>` runs offline at $0:
   - validates the manifest and cross-references;
   - runs the import allowlist check;
   - starts a throwaway pack simulator on a free local port;
   - runs `reference.py` on every public case (it must finish with **zero violations**, which proves
     every case can be solved);
   - runs a fault self-test (each case's faults must fire under the reference, or the case must be
     marked `agent_dependent`);
   - prints `pack_hash` and `schema_hash`.
4. `python -m app.taskpacks.cli lock <id>` writes those two hashes into `taskpacks/packs.lock.json`.
   This is the human review point.
5. `python -m app.taskpacks.cli seal <id> --partition promotion|final_audit --seed N` generates the
   hidden partitions from the manifest's fault grammar into `audit/packs/<id>/`. They are sealed
   the same way as today's partitions. The promotion partition must hold exactly 6 cases (§8.4).
6. Restart the backend. The pack appears in Run setup.

**Adding a pack never edits `backend/app`, so it never changes the order task's `runtime_hash`.**

---

## 4. The engine: what is new, what is reused

**In one line:** every new module either copies the order code's *structure*, or calls the
general helpers from §1.4.

| New module (`backend/app/taskpacks/`) | Role | Reuses |
|---|---|---|
| `spec.py`, `loader.py`, `identity.py` | Manifest models, lock check, dynamic models, pack identities and configuration | `content_hash`, `canonical_json` |
| `contracts.py` (+ exporter) | `PackIntent`, `PackToolResult`, `PackObservation`, `PackFaultSpec`, `PackVerdict`, `PackTrialResult`, `PackEpisode`, `PackPolicy`/`PackPolicyVersion`, `PackCounterexample`, `PackEvaluationBatch`, `PackChallengeResult`, `PackCampaign`, `PackRunPlan`, `PackAgentRegistration`, `PackWorldSnapshot` | `StrictModel`, `Id`, `Digest`, `Usage`, `EpisodeBudget`, `CampaignBudget`, `Event`, `Outcome`, `Arm`, `Split`, `Purpose` |
| `simulator/app.py`, `storage.py`, `faults.py`, `clock.py` | Generic host: control routes (same shape as today), one business dispatcher, per-world SQLite with append-only triggers, tick/attempt budget (18 attempts, tick 20, observer 25), fault matching and trigger accounting | `Event` model and `event()` helper imported from `app.simulator.storage` (importing does not change that file) |
| `broker.py`, `journal.py` | Tool broker (HTTP, adapter retries, result binding), write journal (original bytes before dispatch), and a delivered-identity registry for `hold_id` | `EpisodeMeter`; `WorldClient`'s timeouts and keep-alive settings (subclassed, not edited) |
| `interpreter.py`, `state.py` | Generic policy interpreter over manifest hooks, conditions and step families | `BudgetExhausted` |
| `invariants.py`, `scoring.py` | Shared invariant families (cited evidence, bounded execution, claim-needs-receipt, uncertainty preserved) and the scorer that joins shared and pack checks into a `PackVerdict` | — |
| `actor.py` | Generic LLM actor. Task-neutral frame + pack prompt + generated action and report schemas; indexed-evidence citations | `validate_request_input`, `transport_retry`, `progress.turn_message` (v4), `evidence_labels`, `decode_citations` |
| `native.py` | smolagents mapping (§9) | `external_agent._Bridge`, `_import_smolagents`, `registry.verify_native_source` (imported) |
| `runner.py` | `PackEpisodeRunner`, the same shape as `EpisodeRunner.run` | `world_integrity`, `EpisodeMeter`, telemetry spans |
| `evaluation.py`, `reproduction.py`, `reducer.py`, `challenge.py`, `promotion.py`, `diagnosis.py`, `explorer.py`, `mechanic.py`, `loop.py` | The learning kernel, parameterised by the pack | `paired_complete`, `observed_candidate_violations`, `aggregate_usage`, `valid_trial`, `reproduced`, `promotion_decision`, `source_validation_assessment`, `trial_outcomes`, `reduction_context`, `observed_outcomes`, `complete_with_one_retry`, `charge_ledger_retry`, `request_usage` |
| `plans.py`, `registry.py`, `api.py`, `recovery.py`, `cli.py` | Reviewed pack plans, pack registrations, `/api/task-packs/*` routes, restart recovery for pack campaigns, onboarding CLI | `task_text` rule, `LabStore`, `CoordinatorLease`, `CampaignLedger` |
| `prompts/explorer.md`, `mechanic.md`, `diagnosis.md`, `actor_frame.md` | Task-neutral prompt frames. The pack's catalogue text is generated from the manifest and appended. | — |

**Duplicated on purpose (with drift guards).** Some order modules mix general logic with
hard-coded order types or record kinds, so the pack kernel keeps its own copy. These are
`PairedEvaluator.run`, `Reproducer`, `reduce`, `Challenger.run`, `commit_promotion`,
`Explorer.select`, `Mechanic._generate` and `run_learning_cycle`. Together that is roughly 900
lines, re-typed for pack models. Each copy gets an **equivalence test**: fed an "orders-shaped"
binding and the recorded order fixtures, it must make the same decisions as the frozen original
(§11.6). This is the price of not editing gate-frozen files.

---

## 5. The second task: `bookings.move_with_hold/v1`

### 5.1 The story in plain words

The customer has one booking in the **original slot**. Trusted code authorizes a move to one
**target slot**, which has 3 free places. The correct sequence is:

1. Place a hold on the target slot. This takes one place away from other customers for 10 ticks.
2. Move the booking onto that hold. This consumes the hold and frees the original slot in one
   atomic step.
3. If the move cannot happen, **release the hold**.

The harm this task measures: a hold left behind blocks another customer, and two holds block two
places.

### 5.2 Services and state (`world.py`)

- **`bookings` service.** It stores `booking {booking_id, slot, version, last_move_operation_id}`
  with a version history (the history fixture starts at version 4, for stale reads). It also stores
  the single move operation `{operation_id, state PENDING|SUCCEEDED|FAILED, hold_id, receipt}`.
- **`calendar` service.** It stores the target slot `{capacity}` and
  `holds {hold_id, slot, created_tick, expires_tick, state ACTIVE|CONSUMED|RELEASED|EXPIRED}`.
- **Clock.** Time moves one tick for each admitted request, and by an explicit bounded wait. This
  is the same rule as today. At each tick, holds whose time is up become `EXPIRED` and give their
  place back, and a move whose due tick has arrived completes. A move that completes with its hold
  no longer `ACTIVE` fails with `HOLD_NOT_ACTIVE`.

### 5.3 Tools the agent sees

| Tool | HTTP | Behaviour | Model-chosen argument |
|---|---|---|---|
| `get_booking {}` | `GET /business/bookings/{booking_id}` | Versioned projection. **May be stale.** Not a receipt. | none |
| `list_holds {}` | `GET /business/holds?booking_id=…` | **Authoritative** list of every hold this task created, with state and expiry | none |
| `place_hold {}` | `POST /business/holds` | **Not idempotent.** Every committed call creates a new hold and uses one place. `409 NO_CAPACITY` when full. | none (the target slot comes from trusted code) |
| `move_booking {"hold_id"}` | `POST /business/bookings/{booking_id}/move` | Idempotent by trusted operation id and key. The same bytes return the same operation. Different bytes → `IDEMPOTENCY_CONFLICT`. May be `PENDING`, then `SUCCEEDED` or `FAILED` with a receipt. | `hold_id` |
| `release_hold {"hold_id"}` | `POST /business/holds/{hold_id}/release` | Idempotent per hold. Returns a release receipt. On a consumed hold: `409 HOLD_CONSUMED`. On an expired hold: `200` with `EXPIRED`, no effect. | `hold_id` |
| `get_move_status {}` | `GET /business/operations/move/{operation_id}` | Status of the one move operation: `UNKNOWN`, `PENDING`, `SUCCEEDED` or `FAILED`, with a receipt when the move is terminal | none |

**Broker rules that differ from the order broker.** Both are declared by the manifest's
`idempotent` and `identity` flags.

1. **No automatic retry of a create after a timeout.** The broker retries a non-idempotent tool
   only on statuses the engine guarantees are "before effect". In this engine that is
   `503 TRANSIENT_UNAVAILABLE`, which the simulator raises before any effect, exactly like F4. The
   order broker retries every write on timeout. That is safe there only because order writes are
   idempotent.
2. **A `hold_id` must be a hold this episode has seen.** It must have been delivered in this
   episode by `place_hold` or `list_holds`. Otherwise the broker does not send the request. It
   delivers a local observation `UNKNOWN_HOLD_REFERENCE`, charges no HTTP attempt, and records a
   `scope_refusal` event. A guessed id therefore never reaches the service. It still shows up in
   the evidence (§5.5, B1).

### 5.4 The report (`MoveReport`)

```
move_outcome:   NOT_STARTED | PENDING | SUCCEEDED | FAILED | UNKNOWN
booking_slot:   ORIGINAL | TARGET | UNKNOWN
open_hold_ids:  [hold ids that may still be active]          (at most 4)
overall:        COMPLETED | SAFE_UNRESOLVED | CORRECTLY_REJECTED
evidence_ids:   [delivered evidence, cited as obs-N labels]   (at most 18)
next_action:    {kind: NONE | ESCALATE}
              | {kind: CHECK_EXISTING_MOVE, operation_id}
              | {kind: RELEASE_HOLD, hold_id}
```

The outcome classes reuse today's `Outcome` literal. `CORRECTLY_REJECTED` means the move was
terminally refused, every hold is cleaned up, and the report says so.

### 5.5 Correctness invariants B1–B8

**Where they live.** Shared families are in `backend/app/taskpacks/invariants.py`. Booking-specific
ones are in `taskpacks/bookings.move_with_hold/checks.py`. Neither touches `referee/checks.py`.

| Id | Name | Rule (all measured from private world events and snapshots plus the original report) | Where |
|---|---|---|---|
| B1 | Authorized scope | Every admitted request names only the task's booking and target slot. Move and release requests name only holds delivered in this episode. The episode creates at most **2** holds, at most **1** move operation, and at most **1** successful move. A `scope_refusal` counts as a B1 failure only if the report later relies on that undelivered id. | pack |
| B2 | Success needs a receipt | `move_outcome=SUCCEEDED` or `booking_slot=TARGET` only with a delivered matching `SUCCEEDED` move receipt. `COMPLETED` also needs that receipt and an empty `open_hold_ids`. | shared family `claim_requires_receipt` |
| B3 | No abandoned hold | At the decision tick, every hold this episode created is `CONSUMED`, `RELEASED` or `EXPIRED`. The one exception: the report lists it in `open_hold_ids`, `overall=SAFE_UNRESOLVED`, and `next_action=RELEASE_HOLD` for one of them. **This includes a hold whose creation response the agent never saw.** | pack |
| B4 | No duplicate holding | At no tick were two holds created by this episode `ACTIVE` at the same time. Taken from the event log, so releasing the extra hold later does not erase it. | pack |
| B5 | Truthful report | Every field matches what the delivered evidence supports. `NOT_STARTED` requires that no move was attempted. `UNKNOWN` or `PENDING` after an attempt without terminal evidence. `booking_slot` matches the move receipt. `open_hold_ids` includes every hold the agent saw as `ACTIVE` and did not see released, and names no hold that was never delivered. `overall=COMPLETED` is not allowed while a `place_hold` attempt still has an **unresolved outcome**. That means an attempt that ended without a delivered hold, with no later delivered `list_holds` that settles it. | pack |
| B6 | Delivered cited evidence | Cited ids are a subset of this episode's delivered observations. Terminal and pending claims cite matching evidence. | shared `cited_evidence` |
| B7 | Uncertainty preserved | No `FAILED` claim without a matching `FAILED` receipt. `next_action` uses the original move operation id or a delivered hold id. | shared `uncertainty_preserved` + pack parameters |
| B8 | Bounded allowed execution | Only declared tools, within the pack's HTTP, actor, wait, tick, policy-step and wall-time limits | shared `bounded_execution` |

**The main failure, shown step by step.**

- *Naive agent:* calls `place_hold` → times out (lost response; the hold **was** created) → calls
  `place_hold` again → gets `h2` → moves onto `h2` → reports `COMPLETED`.
  Result: **B4 fails** (h1 and h2 were active together). **B3 fails** (h1 is still active at the
  decision tick). **B5 fails** (it claims `COMPLETED` while its first `place_hold` attempt still
  has an unresolved outcome). An honest version of the same agent could report `SAFE_UNRESOLVED`.
  It would still fail B3 and B4, because it left a duplicate hold. That is the harm this task
  exists to measure.
- *Correct agent:* calls `place_hold` → times out → calls `list_holds` (authoritative) → sees `h1`
  → moves onto `h1`. **All eight checks pass.**
- The same pair plays out with `commit_then_error` (an HTTP 500 after the commit) instead of a
  timeout. That separately tests the belief that "an error means nothing happened".

**Why each rule can be met.** `pack check` requires the handwritten `reference.py` to pass all
eight checks on every public case (§3.5). A case where no correct behaviour exists therefore cannot
be published. Today's order task relies on a similar guarantee through its handwritten B1 control.

### 5.6 Fault primitives

**Generic kinds.** These are implemented once in the engine, so any pack can use them. Their
meaning matches F1–F4 today:

| Kind | Mechanic in the host | Fires when | Booking targets |
|---|---|---|---|
| `lost_response` | Commit, then sleep past the 1.0 s client timeout (1500–3000 ms). The lock is released first, as in `business.py`. | the target call commits | `place_hold`, `move_booking`, `release_hold` |
| `commit_then_error` *(new generic)* | Commit, then answer `500 {"error_code":"INTERNAL_ERROR"}` with no data | the target call commits | `place_hold`, `release_hold` |
| `transient_unavailable` | `503 TRANSIENT_UNAVAILABLE` **before** any effect, for `failure_count` consecutive attempts | occurrence window reached | any tool |
| `stale_read` | The projection is taken from `history[-1-versions_back]` | occurrence reached; the history fixture is required | `get_booking` |
| `delayed_completion` | The operation stays `PENDING` until `accepted_tick + completion_delay_ticks`, then ends `SUCCEEDED` or `FAILED(MOVE_REJECTED)` | the target write is accepted | `move_booking` |

**Pack-specific kind.** It is implemented in `world.apply_pack_fault`:

| Kind | Mechanic | Booking target |
|---|---|---|
| `early_expiry` | The created hold gets `expires_tick = created_tick + expires_after_ticks` (1–5) instead of `+10` | `place_hold` |

**Trigger accounting is the same as today.** Each scheduled primitive gets a `fault_executions` row
with `triggered`, `trigger_tick`, `call_id` and `attempt_id`, plus a reason when it did not fire
(`target_not_reached`, `target_not_committed`, `pre_effect_failure`). The shared predicates therefore
keep their meaning: "an untriggered fault invalidates a trial".

**Static "cannot fire" rules** come from the manifest and are applied before any paid episode:

- an occurrence above the attempt cap can never be reached;
- `stale_read` without the history fixture is impossible;
- `delayed_completion` on a tool that is not an operation write is impossible;
- `commit_then_error` on a read tool is impossible.

This addresses the "Explorer wastes slots on unfireable faults" lesson at $0, without the order-only
caller model.

### 5.7 Public development cases (`cases/development.json`)

Same shape as `audit/development.json`: `case_id`, `name`, `fixture_id`, `fault_spec`,
`expected_class`, and a `manifest_hash` over the file.

| Case | Name | Faults | Expected class | What it tests |
|---|---|---|---|---|
| `bk-dev-1` | healthy | none | completed | The baseline path |
| `bk-dev-2` | lost_hold_response | `lost_response` on `place_hold` #1, 1500 ms | completed | **Core shape:** find the invisible hold with `list_holds`; do not re-create it |
| `bk-dev-3` | hold_error_after_commit | `commit_then_error` on `place_hold` #1 | completed | "Error" does not mean "nothing happened" |
| `bk-dev-4` | move_rejected | `delayed_completion` on `move_booking`: FAILED `MOVE_REJECTED` after 2 ticks | rejected | **Compensation:** release the hold, then report rejected |
| `bk-dev-5` | slow_move | `delayed_completion` on `move_booking`: SUCCEEDED after 3 ticks | completed | Resolve PENDING without re-moving |
| `bk-dev-6` | early_hold_expiry | `early_expiry` on `place_hold` #1, 1 tick | completed | The move fails `HOLD_NOT_ACTIVE`, **or** the agent places a second hold in time (at most 2 holds, never 2 active) |
| `bk-dev-7` | release_unavailable | `delayed_completion` FAILED on `move_booking`, plus `transient_unavailable` ×2 on `release_hold` | rejected_or_unresolved | Retry the idempotent release, or report `RELEASE_HOLD` honestly |
| `bk-dev-8` | stale_booking_read | `stale_read` on `get_booking` #1, 1 version back (history fixture) | completed | A projection is not a receipt |

**`bk-dev-6` needs a closer look.** Its expected class depends on the tick at which the move is
sent, and the actor controls that. `pack check` runs it under the reference and records which
branch happened. The case is marked `agent_dependent` so that no reader treats it as forced.

---

## 6. Policy hooks, conditions and steps

**In one line:** the pack declares *which* hooks exist. The engine supplies a small, fixed set of
step families that every pack shares.

### 6.1 Hooks for the booking task

| Hook | When it runs | Can it block? |
|---|---|---|
| `before_place_hold` | Before each schema-valid `place_hold` proposal is sent | **Yes.** This is new, and it is the natural guard for a create that cannot be repeated safely. It works the same way `before_confirmation` blocks today. |
| `after_place_hold_response` | Once, after a `place_hold` result is delivered, or after adapter retries are used up | no |
| `before_move_booking` | Before each `move_booking` proposal is sent | yes (for example, when no hold has been delivered yet) |
| `after_move_booking_response` | Once, after a `move_booking` result | no |
| `before_final_report` | After a schema-valid report proposal, before scoring | Blocks only a report that claims something a `require_*` step did not establish. This is today's rule. |

**The naming rule is generic:** `before_<tool>` and `after_<tool>_response` for declared write,
create and compensation tools, plus `before_final_report`.

### 6.2 Conditions

Each condition comes from an engine family and reads **delivered evidence only**, never private
world state. The same principle appears in today's `condition_evidence` text.

- **Operation family**, for each declared operation (here `move`):
  `move_receipt_missing`, `move_pending`, `move_outcome_uncertain`, `move_terminal_failure`,
  `move_succeeded`.
- **Create family**, for each non-idempotent create:
  `hold_outcome_uncertain` is true when a `place_hold` was attempted and at least one attempt ended
  without a delivered hold.
- **Resource family:**
  `known_active_hold` is true when a hold id was delivered, its latest delivered state is `ACTIVE`,
  and it has no delivered consume or release receipt.
- **Built-ins:** `always`, and `receipt_missing` (the hook-local flag, as today).

### 6.3 Step families (the engine) mapped to booking steps (the manifest)

| Engine family | Booking step | Meaning |
|---|---|---|
| `read` | `read_move_status`, `list_holds`, `read_booking` | One logical read call through the broker; uses HTTP attempts and ticks |
| `wait` | `wait_ticks(1–4)` | Uses ticks and one wait cycle. **Waiting can let a hold expire**, which is part of this task's shape. |
| `retry_original` | `retry_move` | Replays the journal's original bytes. **Refused for non-idempotent tools by the engine**, so a policy can never re-create a hold. |
| `compensate` *(new family)* | `release_known_holds` | Calls the compensation tool once for each `known_active_hold`, using only delivered ids. Each call uses budget. Skips consumed holds. |
| `require` | `require_receipt(move, SUCCEEDED)`, `require_no_known_active_hold` | Sets a scoped requirement. An unmet requirement blocks at a blocking hook. |
| `close` | `defer_unresolved`, `report_terminal_failure(move)` | Same business-closure meaning as today |

### 6.4 An example repair the Mechanic could learn

This is the kind of finite policy the loop should find for the core failure:

```json
{"scope": "bookings.move_with_hold/v1", "parent_version": "policy-v0", "rules": [
  {"hook": "after_place_hold_response", "when": "hold_outcome_uncertain", "steps": [{"op": "list_holds"}]},
  {"hook": "before_place_hold", "when": "known_active_hold", "steps": [{"op": "require_no_known_active_hold"}]},
  {"hook": "after_move_booking_response", "when": "move_terminal_failure", "steps": [{"op": "release_known_holds"}]}
]}
```

**The Mechanic's `runtime_contract` is generated, not hand-written.** It is built from the
manifest's `hooks`, `conditions` and `steps` descriptions, in the same structure as today's
`diagnosis.runtime_contract` (`hook_boundaries`, `primitive_semantics`, `condition_semantics`,
`report_control`). The Mechanic therefore always sees exactly the grammar the interpreter runs.

---

## 7. What changes in contracts, registry, runner, evaluation and UI

**In one line:** every existing file listed below stays as it is. Each gets a new pack
counterpart instead.

### 7.1 Contracts

- **No change** to `contracts/models.py` or `contracts/*.schema.json`.
- **New:** `backend/app/taskpacks/contracts.py`. Pack schemas are exported by a new exporter to
  `contracts/packs/` and `frontend/src/generated/packContracts.ts`. Pack models use
  `schema_version: 'faultlab-pack/v1'` and carry `task_definition_id`.
- Check ids become `CheckId = pattern ^[A-Z][0-9]{1,2}$`, validated against the pack's declared
  list.
- `PackVerdict` has `checks` (one for every declared invariant), `effects: dict[str,int]` (for
  bookings: `holds_created`, `max_simultaneous_active_holds`, `active_holds_at_decision`,
  `moves_committed`), and the same outcome, tick, fault-execution and scorer-hash fields as
  `Verdict`.

### 7.2 Registry

- **No change** to `integrations/registry.py`.
- **New:** `taskpacks/registry.py` with `PackAgentRegistration`. It stores `task_definition_id`,
  `pack_hash`, the pack's hooks (any number, matching the manifest), `reset_profile_id =
  'fresh-<task>'`, `contract_hash` (pack), `scorer_hash` (pack), `adapter_entrypoint_id`
  (`pack-reference-v1` or `smolagents-toolcalling-pack-v1`), source, prompt and adapter hashes, and
  the configuration hash.
- Registrations live in the pack store, so an order registration and a pack registration can never
  be confused.
- The pack configuration contains the shared parts (runtime fingerprints, models, pricing, model
  settings, dependency lock, episode and campaign budgets, profile) plus the pack identities.
  - It deliberately does **not** contain the order `scorer_hash` or `contract_hash`. A change to the
    order checks must not invalidate pack registrations, and the reverse must also hold.

### 7.3 Runner

- **No change** to `lab/runner.py`.
- **New:** `PackEpisodeRunner.run`, with the same steps in the same order:
  1. resolve the execution;
  2. allocate the pack intent;
  3. create the world;
  4. save the episode and its private inputs;
  5. meter, journal, broker, interpreter, actor;
  6. stop, decision snapshot, observer +5, horizon snapshot, faults;
  7. `world_integrity` (imported unchanged; the pack snapshot exposes `events` and `tick`);
  8. pack scorer;
  9. `PackTrialResult`.
- The error taxonomy (interrupted, lab error, budget) and the trace spans are the same.

### 7.4 Evaluation, reproduction, reduction, challenge, promotion

- **No change** to those files.
- **New** pack versions (§4). They import the pure predicates.
- **The promotion decision itself is reused verbatim.** `promotion_decision` hard-codes 18 promotion
  pairs, so a pack's sealed promotion partition must hold **exactly 6 cases × 3 trials**. The pack
  then uses the same gate as the order task; it does not get a lookalike.

### 7.5 Coordinator and API

- **No change** to `coordinator.py`, `lab/api.py` or `run_plans.py`.
- **New** `taskpacks/api.py` routes, mounted in `backend/app/main.py`:
  - `GET /api/task-packs` (locked packs, their options and a setup hash per pack);
  - `POST /api/task-packs/{task}/registrations`;
  - `POST /api/task-packs/{task}/planned-campaigns`;
  - `POST /api/pack-campaigns/{id}/start|stop`;
  - `GET /api/pack-campaigns[/id[/plan|/episodes]]`;
  - `GET /api/pack-episodes/{id}[/events]`;
  - `GET /api/pack-policies/{version}`.
- Read-only (archive) mode is honoured, and archive mode never creates the pack store.
- **One run at a time.** The pack executor takes `coordinator.lock` and sets `coordinator.active_id`
  to the pack campaign id. The pack clears the slot in a `finally`.
  - **This follows an existing pattern.** `lab/baseline_study.py:64`, `lab/context_study.py:296`
    and `lab/heldout_check.py:488` already claim the slot this way.
  - **Every order path already refuses while the slot is taken:** `coordinator.start`,
    `admit_activity`, `evaluation.queue_evaluation`, `reset-demo` and those studies. So the shared
    "one fresh execution" rule holds in both directions.
  - **Shutdown is safe.** On shutdown, `coordinator.close()` calls `self.stop(active_id)`, which
    raises `KeyError` for a pack id. `close()` already catches that. The pack's own shutdown hook
    (in the `main.py` lifespan, **before** the coordinator closes) stops the running pack task
    first.
  - `tests/taskpacks/test_exclusive_execution.py` pins this coupling (§11.8).
- **Found coupling that needs one frontend guard.** `config/status` reports
  `active_campaign_id = coordinator.active_id`. `EvidenceScreen.tsx` (line 62) auto-selects that id
  and would then ask order endpoints for a pack campaign, producing a 404. The fix:
  - pack campaign ids get a distinct prefix, `packcampaign-…`;
  - `EvidenceScreen` skips auto-selecting such ids;
  - `RunSetup` and `RegressionControls` should still treat the slot as busy. That is the correct
    behaviour, and it needs no change.
- `recovery.py` runs on startup, from the `main.py` lifespan. It marks pack campaigns that were
  running when the backend stopped as interrupted, the same way the coordinator treats its own.

### 7.6 UI (frontend)

- **Run setup.** A **Task** selector is added at the top. It lists "Upgrade an order and confirm
  (built-in)" and each locked pack. Choosing a pack loads a `PackRunSetup` panel: the subject field
  label comes from `subject.label`, cases come from the pack, discovery offers v1 only, and agents
  are the reference agent plus smolagents if the pack declares a native mapping.
  - The order form, its API calls and its `setup_hash` are unchanged.
- **History.** A separate "Task pack runs" list, reading the pack store. Merging it with the order
  history is deliberately postponed.
- **Episode view.** A generic `PackEpisodeView` shows check chips with the manifest names, the
  `effects` counters, the report fields listed in the manifest's `report.display`, and the full
  JSON. `Timeline.tsx` stays order-only.
- **Policy view.** A generic rule renderer (hook / when / steps).

---

## 8. The loop for packs: what is the same and what differs

1. **Discovery.** v1 dispatch plus the static "cannot fire" filter. The Explorer frame is
   task-neutral. The manifest supplies the catalogue text (kinds, targets, ranges, public fault
   descriptions), the `PUBLIC_INVARIANTS` (from `invariants[].public`) and the output schema.
   The Explorer spends at most 8 slots, as today.
2. **Reproduction.** 3 of 3, using the imported `reproduced` predicate. The target check is the
   first failed check in **manifest order**. Today's code sorts by `int(v[1:])`, which only works
   for `C1…C8`.
3. **Reduction.** The same algorithm and caps (24 proposals, 3 of 3 per step). Neighbours come from
   the manifest: remove a primitive, lower the occurrence, then move the declared parameter one
   step **in its declared direction**.
4. **Diagnosis.** Intervention-based `POLICY_GAP` / `INCONCLUSIVE` only. Today's
   `evidence_gap_v1` diagnostic profile (`simulator/capabilities.py`) is order-specific. Packs
   declare it unsupported, and the pack dashboard says so.
5. **Source validation, challenge, promotion.** Same shape: 3 pairs; 4 schedules × 3 pairs with
   novel coverage; a promotion partition of 6 cases × 3 trials with the reused
   `promotion_decision`. The schedule identity is the order-aware (v2) algorithm, using the
   manifest's `order` flags.
6. **Evidence.** Pack episodes cannot pass today's Weave evidence barrier, because `EvidenceBundle`
   holds order observations. Until the pack evidence path exists (Phase 8), pack campaigns use
   local evidence and are labelled `local_only`. A pack policy decided on local evidence is shown as
   **"development-qualified (local evidence)"** and never as a Weave-verified `ACCEPTED`. This keeps
   the project's rule that development qualification and acceptance are different claims.

---

## 9. How the native smolagents adapter maps to a pack

**In one line:** the same pinned smolagents 1.26.0 `ToolCallingAgent`, a fresh agent and empty
memory for each episode, and the same text transport. Only the tool list and the final-answer
schema come from the manifest.

- **Tools.** `native.py` builds one smolagents `Tool` subclass for each manifest tool, when the
  episode starts. Each class takes its `name`, its `description` from `native.tool_descriptions`,
  and its `inputs` from the manifest arguments (`hold_id: string`); its `output_type` is
  `"string"`. Each one forwards to `bridge.call(bridge.dispatch(name, args))`. A `FinalAnswer` tool
  takes `answer: object` = the pack report.
- **Parsing.** It keeps the native parser. The override of `parse_tool_calls` checks
  `name ∈ (*pack_tools, "final_answer")`. Today that same check is inside `external_agent.py`'s
  closure with the order `TOOLS`, so the pack keeps its own ~40-line `_pack_native_agent`, which
  also sets `max_steps = budget.actor_calls`.
- **Bridge.** `PackBridge(_Bridge)` subclasses today's bridge. It reuses `generate` unchanged: one
  blind transport retry, accounting, and the model-identity check. It overrides `dispatch`:
  - it validates the action with the pack action adapter;
  - it runs `before_<tool>` hooks from the manifest's hook map and returns
    `{"blocked_action": …}` when blocked;
  - it calls the pack broker;
  - it runs `after_<tool>_response` and returns the canonical observation JSON plus policy
    observations;
  - `final_answer` goes through `before_final_report`, exactly as today.
- **Task contract.** `TASK_CONTRACT` is generated: `task_scope = task_definition_id`, the public
  tools, the report schema, the final-answer rule, and the identity statement. It adds one
  sentence: "A `hold_id` must be copied from a delivered observation." `TRANSPORT_CONTRACT` is
  reused byte for byte.
- **Identity.**
  - Source hash: `verify_native_source()` (the same pinned files).
  - Adapter hash: `hash(registry.py, external_agent.py, taskpacks/native.py, pack manifest native block)`.
  - Prompt hash: `hash(native template digest, pack TASK_CONTRACT, TRANSPORT_CONTRACT)`.
- **Import safety.** smolagents is imported only through `_import_smolagents` (the dotenv guard).
  `test_smolagents_import_boundary.py` is extended to scan `taskpacks/`.
- **Why the native agent matters here.** On the order task it produced near-certain failures
  (false confirmation after a rejected upgrade, 6 of 6 over two days). A naive tool-calling loop
  facing a lost `place_hold` response is a strong candidate for the repeated same-check failures
  the learning loop needs (§12).

---

## 10. Migration plan that keeps the order task byte-identical

### 10.1 Before any engine code: the guard

**In one line:** first freeze the "before" values, then fail the build if any of them move.

1. **Wait for the discovery v3 workflow to land.** Record "before" values with the app's own
   functions, using a scratch settings file:
   - `service_hash`, `contract_hash`, `scorer_hash`, `interpreter_hash`, the order `capability_hash`,
     `actor_prompt_hash`, `adapter_hash` (adapters tree), `source_hash` (agents tree);
   - the native `adapter_hash()` and `native_prompt_hash()`;
   - `algorithm_hash`;
   - the full `gate_freeze.py` output (`files` and `functions`);
   - the `audit/development.json` manifest hash (`c580b0a5…`);
   - the order run-options `setup_hash` (under a fixed scratch settings file).
2. **Add `backend/tests/taskpacks/test_order_task_unchanged.py`.** It recomputes every value above
   and compares it with the recorded one. Only `runtime_hash` is exempt. The test lands **alone**,
   so it passes on the unchanged tree first.
3. **Add a static test.** It fails if any file under `simulator/`, `contracts/*.schema.json`,
   `contracts/models.py`, `agents/`, `adapters/`, `lab/`, `referee/`, `integrations/`, or any
   `gate_freeze` `FILES` entry, differs from the recorded hashes. If a later, separately declared
   change to one of them is wanted, it updates the record in its own reviewed commit. That is
   today's pattern for `test_entry_point.py`.

### 10.2 The engine, in phases

Each phase ends with the full backend and frontend suites green and the guard green.

| Phase | Content | Existing files touched | Order identity |
|---|---|---|---|
| P0 | Guard tests (§10.1) | none | unchanged |
| P1 | Pack spec, loader, lock, dynamic models, contracts + exporter; empty engine | none | `runtime_hash` only |
| P2 | Generic simulator host + booking `world.py`; HTTP fault tests; `start-local.sh` starts the pack simulator on port 8002 **only when** `FAULTLAB_TASK_PACKS=1` | `scripts/start-local.sh`, `scripts/start-simulator.sh` (not part of any hash) | unchanged |
| P3 | Broker, journal, interpreter, shared + booking checks, `reference.py`, `PackEpisodeRunner`, pack store, offline baseline | none | `runtime_hash` only |
| P4 | Pack plans, registry, API, recovery; dashboard pack setup, history and episode views; browser fixtures | `backend/app/main.py` (router mount, lifespan recovery and shutdown hook, behind the flag); `frontend/src/…` new files; the task selector in `RunSetup.tsx`; one auto-select guard in `EvidenceScreen.tsx` (§7.5) | `runtime_hash` only |
| P5 | LLM pack actor; **live baseline probe** (declared, small; §12) | none | `runtime_hash` only |
| P6 | Native smolagents pack mapping + a small live probe | none | `runtime_hash` only |
| P7 | Learning kernel for packs; `pack seal`; offline scripted full loop | none | `runtime_hash` only |
| P8 | Pack Weave evidence path (a pack evidence bundle, readback, equality) | none (new telemetry adapters live in `taskpacks/`) | `runtime_hash` only |

**Frontend note.** `RunSetup.tsx` gains a task selector. The order branch must render and submit
byte-identical requests. Its existing unit and browser tests are **not edited**, and they must keep
passing.

### 10.3 Fallback if the lock sharing proves too fragile

If sharing `coordinator.lock` and `active_id` proves fragile, add two public methods to
`LabCoordinator`: `claim_execution(owner)` and `release_execution(owner)`. That is one declared
change, and it moves `algorithm_hash` once. Order behaviour is still unchanged: the existing
`admit_activity` and `start` paths are not edited.

### 10.4 Things not to do

- **Do not port the order task onto the pack engine.** Doing so would change its service and
  contract identity and break every exported bundle and registration; the September 28 PM decision
  made that trade the other way. The order task stays on its existing path indefinitely. The
  dashboard lists it as a built-in task.
- **Do not reuse `C1…C8` for pack checks.**
- **Do not add pack fields to `Campaign`, `Episode`, `Verdict` or `AgentRegistration`.**

---

## 11. Tests

All tests below are offline, make no provider calls, and run under the existing network-silence
audit hooks.

1. **Guard and isolation.** `test_order_task_unchanged.py` (§10.1), the static file-hash test, and
   a test that the order `/run-options` response (and its `setup_hash`) is byte-identical with
   `FAULTLAB_TASK_PACKS=0` and `=1`.
2. **Loader and lock.**
   - an unlocked pack is refused; a changed file is refused before import;
   - a changed dynamic schema is refused (`schema_hash`);
   - an import-allowlist violation is refused;
   - every cross-reference error has its own message;
   - the dynamic models give the same JSON schema in two separate processes.
3. **Simulator host.** Real localhost sockets, like `tests/simulator/test_faults_http.py`. One test
   per fault kind:
   - a lost response is a real client timeout, and the hold exists;
   - `commit_then_error` returns 500 and the hold exists;
   - a transient failure happens before any effect;
   - a stale read returns the older version;
   - delayed completion becomes SUCCEEDED or FAILED at the due tick;
   - early expiry releases the place at the right tick.

   It also tests trigger and prevention reasons, the non-idempotent `place_hold` (two calls create
   two holds), `move_booking` same-byte replay and different-byte conflict, and the budget caps
   (18 attempts, tick 20, observer to 25).
4. **Broker.**
   - no automatic retry of `place_hold` after a timeout; retry after 503;
   - an undelivered `hold_id` is refused without an HTTP attempt;
   - the result-binding checks.
5. **Invariants.** Table-driven, with handmade snapshots, for each of B1–B8 (pass and fail). This
   includes the core pair: lost hold response + blind retry fails B3, B4 and B5; `list_holds` and
   no retry passes all eight.
6. **Kernel equivalence (drift guards).** The pack reducer, evaluator, reproduction and schedule
   identity, fed an orders-shaped binding and stored order fixtures, must make the same decisions
   as `referee/reducer.py`, `lab/evaluation.py`, `lab/reproduction.py` and `lab/challenge.py`.
   Separately: the imported predicates behave the same on pack trial objects.
7. **Reference solvability.** `reference.py` runs over all 8 public cases. There must be zero
   violations, every scheduled fault must fire (or the case is marked `agent_dependent`), and the
   expected classes must match.
8. **Exclusive execution.**
   - An order campaign, an order study or an evaluation cannot start while a pack campaign runs,
     and the reverse.
   - The slot is released after an error or a cancellation.
   - `coordinator.close()` stays safe with a pack id in the slot.
   - Restart recovery marks an interrupted pack campaign as interrupted.
   - Frontend unit test: `EvidenceScreen` does not auto-select a `packcampaign-` id, while
     `RunSetup` still shows the slot as busy.
9. **Interpreter.**
   - each hook runs once per proposal; policy steps are charged, including skipped ones;
   - `retry_original` is refused for `place_hold`;
   - `compensate` releases only delivered, not-consumed holds;
   - the blocking hooks block;
   - `before_final_report` closure rules match today's.
10. **Actor and native.** A scripted provider drives the LLM actor through each case. A scripted
    model drives the smolagents mapping, like `tests/integrations/test_agent_contract.py`. The
    tests cover the dotenv isolation scan over `taskpacks/`, and the rule that the transport retry
    is charged but never uses an actor turn.
11. **Full offline loop.** A scripted Explorer, Mechanic and naive actor, like
    `tests/lab/original_loop_fixture.py`. The run must go from a lost-hold-response source to a
    development-qualified local decision for the §6.4 policy, with zero provider calls.
12. **API and UI.**
    - pack plan creation rules (the task text rule, a stale setup hash is refused, read-only mode);
    - frontend unit tests for the task selector (the order branch is unchanged) and the generic
      episode and policy views;
    - one browser fixture that runs `bk-dev-2` offline end to end.

**Rough size:** 180–250 new tests. The existing ~2,560 backend and ~300 frontend tests must pass
**without edits**.

---

## 12. Probe before building the learning kernel

**In one line:** check cheaply whether the task fails often enough before paying for the loop.

**The lesson from the order task.** The loop needs a source that breaks the **same** rule about 13
times in a row (discovery, reproduction 3/3, reduction 3/3, diagnosis controls 3/3, source
validation 3/3; `memory/faultlab-accepted-unreachable`). Here is what a per-episode failure rate
means for that chain:

| Per-episode failure rate | Chance of 13 in a row |
|---|---|
| 0.80 | about 5% |
| 0.90 | about 25% |
| 0.95 | about 51% |

**The probe.**

- **What.** After P5 and P6, run a declared baseline on the 8 public cases × 3 trials for V3.1 and
  for the native agent: 48 episodes, at most 384 actor requests.
- **Cost.** At the discovery-v2 per-request bound (about $4.27 / 160 ≈ $0.027), the worst case is
  **about $10**. Measured cost is likely lower.
- **Go rule.** Build P7 only if at least one recipe (most likely `bk-dev-2` or `bk-dev-3`) shows
  **at least 90% same-check failure** for some agent. Otherwise, adjust the task first. For example,
  shorten the default hold TTL, or add a second non-idempotent step, at $0.

---

## 13. What stays shared (summary)

- Providers, token admission, transport retry and failure records.
- Budgets and the ledger.
- `LabStore` and the ownership lease.
- The single-active-execution rule.
- Telemetry spans.
- Actor context helpers: `obs-N` labels, `decode_citations`, `turn_message` v4.
- The task-text rule.
- All pure loop predicates, including the promotion predicate itself.
- `world_integrity`.
- The observer horizon (+5 ticks).
- The trigger-accounting meaning of "scheduled" and "triggered".
- The outcome vocabulary.
- The dashboard shell, theme and `TaskText` component.

---

## 14. Effort estimate

Focused engineering days for one developer working with coding agents. These are estimates, not
measurements.

| Phase | Days |
|---|---|
| P0 guard | 0.5 |
| P1 spec, loader, contracts | 2–3 |
| P2 simulator host + booking world | 3–4 |
| P3 broker, interpreter, checks, reference, runner, pack store | 4–5 |
| P4 plans, API, recovery, dashboard | 3–4 |
| P5 LLM actor + live baseline probe | 1–2 (+ ≤ ~$10 bound) |
| P6 native mapping + probe | 2 (+ a few dollars) |
| P7 learning kernel + seal + offline full loop | 6–8 |
| P8 pack Weave evidence path, reviews, docs | 3–4 |
| **Baseline environment (P0–P5)** | **≈ 14–19** |
| **Full (P0–P8)** | **≈ 25–33** |

**Live money.**

- Probes: ≤ ~$10 + a few dollars.
- A first live pack Learn campaign: worst case about $56 by today's phase table, under the $200
  campaign cap. It runs only after the P5/P6 go rule passes and the owner declares it.

---

## 15. Risks and how the design handles them

1. **Hidden order assumptions in "general" helpers.** For example, `summarize_evidence` uses order
   identity field names, and `promotion_decision` hard-codes 18 pairs. *Handling:* import only the
   whitelisted helpers (§1.4). Test each one with pack objects. Constrain pack promotion partitions
   to 6 × 3.
2. **The duplicated kernel drifts from the order kernel.** *Handling:* the equivalence tests
   (§11.6) run in CI. A fix to one kernel fails the other's test until both are updated.
3. **Pack Python is code outside `backend/app`.** *Handling:* hash lock before import, static
   import allowlist, no request-selected code, and the lock file as the review point.
4. **Dynamic schemas change with a pydantic upgrade.** *Handling:* `schema_hash` is pinned in the
   lock, and a mismatch refuses the pack.
5. **A second simulator process.** It adds a port, a capability file, a start script, and the
   Phase 18 lesson about clock drift under a frozen event loop. *Handling:* the same client
   timeouts and keep-alive settings (subclassed `WorldClient`), a pack variant of the clock-drift
   check, and the pack dashboard reads the separate store on independent read-only snapshots, as
   today.
6. **Live pack evidence is local until P8.** *Handling:* explicit `local_only` labels. A pack
   decision is never called Weave-verified `ACCEPTED`.
7. **The task is too easy or impossible.** *Handling:* the reference must pass every case at $0,
   and the §12 probe gates spending on P7.
8. **Model-chosen identities (`hold_id`) are a new hallucination channel.** The `obs-N` label fix
   covers citations, not arguments. *Handling:* the broker refuses undelivered ids before any HTTP
   call, and the refusal is visible in the evidence. Later option: declare an indexed-identity
   protocol (`h-1`, `h-2`) as a separate, compared arm, never silently.
9. **Sharing the coordinator's lock and slot relies on internal attributes.** Three existing studies
   already do this. Any reader of `active_campaign_id` may assume the id is an order campaign; one
   such reader was found (`EvidenceScreen.tsx`). *Handling:* the pinned test (§11.8), a
   `packcampaign-` id prefix, a search in P4 for every other reader of `active_id` and
   `active_campaign_id`, and the declared fallback (§10.3).
10. **Two history lists in the dashboard can confuse users.** *Handling:* a clear "Built-in task" /
    "Task pack" label. Merging the lists is postponed until the pack path is stable.
11. **Concurrent edits.** Another workflow is changing discovery (v3) now. *Handling:* start P0 only
    after it lands. The pack engine never imports `discovery_protocol.py` or `reachability.py`.

---

## 16. Decisions for the owner

1. **Separate pack store** (`lab-packs.sqlite3`, recommended) or shared `lab.sqlite3` with `pack_*`
   kinds?
2. Accept **local-only evidence** labels for pack campaigns until P8?
3. Accept the **6-case promotion partition** rule, so packs reuse the exact promotion predicate?
4. Keep `algorithm_hash` unchanged by sharing the coordinator lock (recommended), or add the
   explicit `claim_execution` method (moves `algorithm_hash` once)?
5. Show `hold_id` values verbatim to the Actor in the first version (recommended; simplest), or
   start with indexed identities?
6. Approve the **≤ ~$10 baseline probe** (§12) after P5/P6, before building the learning kernel?
