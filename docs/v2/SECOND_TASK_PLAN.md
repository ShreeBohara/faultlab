# Second task plan: the bookings task on the v2 lab

*2026-11-15. This is a plan only. Nothing in it is built yet, and writing it cost no API money.*

## In one paragraph

Every FaultLab result so far comes from one task: upgrade an order, then send one confirmation. A
second task already exists in an early form, **`bookings.move_with_hold/v1`** (move a booking using
a hold; see [its README](../../taskpacks/bookings_move_with_hold/README.md)). It was built on 2026-09-29
as a standalone world with its own checks H1–H8, a correct agent, eight deliberately buggy agents
and 203 offline tests. It never ran through the lab. Its phase 2 plan targeted the legacy backend,
and the v2 lab has since been built with a seam meant for exactly this. The registry in
`faultlab/packs/registry.py` says "Adding a pack means adding a line here and passing the
conformance tests". This plan moves the bookings task onto the v2 lab in six steps. The first four
cost no API money and must reproduce the September numbers exactly through the real lab. Only then
does a small paid screen ask whether a real model fails the task often enough to study.

## Step 1: done (2026-11-15, $0)

The bookings task now runs on the v2 kernel as the pack `bookings.move_with_hold/v1` (`faultlab/packs/bookings/`,
one line in `faultlab/packs/registry.py`). What was built and how it was checked:

- **The world.** `handler.py` ports the September world onto the kernel and reuses its pure helpers (fixture history,
  fault grammar, the public view of a hold, deterministic ids). `routes.py` serves the six tools over HTTP.
- **Parity.** `backend/tests/v2/test_bookings_pack.py` replays every request the September broker sent to its world,
  for the correct agent and the eight buggy agents (two of them are the probe callers), on all eight
  cases and three seeds: 216 episodes. The kernel
  world gives the same status, error code, data and lost answer each time, and ends in the same state with the same
  business events. A sample also runs over HTTP.
- **Kernel.** F5 (the effect commits, then a 500) is placed by the kernel and F6 (a short hold) by the handler. A
  refusal can carry a body (`HOLD_NOT_ACTIVE` names the hold and its state). A 503 before any effect now lets a pack
  mark its other faults on that attempt as pre-empted, as in September. The orders world refuses F5 and F6, and the
  orders pack digest is unchanged (`6956e1d5…`, pinned by a test).
- **The resend bug.** The test that failed before the fix showed a lost `place_hold` answer ending the trial as
  `UNSAFE_RESEND_REFUSED`. The session now resends a write that is not identity-safe only after a transient refusal
  that proves no effect (`faultlab/lab/session.py`). Keyed writes, including every order write, keep their resend.
- **Hold labels (decision 2).** The agent sees `hold-1`, `hold-2`, … numbered in order of first delivery. A label
  becomes usable once `place_hold` or `list_holds` has delivered it. Anything else, including the raw id, is refused
  by the lab with `UNKNOWN_HOLD_REFERENCE`, with no HTTP attempt. Each label's real id is recorded on the evaluator
  plane. The mechanism is generic (`ReferenceLabels` on `TaskPack`) and appears in a manifest only when a pack
  declares it, so the orders digest did not move.
- **September guard (decision 4).** `dependency_lock_hash` was recorded again once, with a note in
  `order_identity_baseline.json`, and a fresh gate freeze was saved in `artifacts/second-task-step1-2026-11-15/`.
  The September tests now give 203 of 203.

Step 2 is next: the H1–H8 referee bridge, the bookings oracle, and the scripted agents as v2 adapters. Its scoring
must turn hold labels in reports back into ids using the recorded label table. One known gap for step 2: replay
(`faultlab/lab/replay.py`) re-issues recorded requests through the session, and those now hold the real hold ids, so a
bookings replay must re-issue the labels instead.

## Step 4 and a second screen on new cases (2026-11-19, $0.12): still no repeated mistake

At the owner's choice ("harder booking test"), step 4's draw came first. `faultlab/research/bookings_draw.py` builds
550 candidate schedules from the September grammar: single faults, plus pairs that do not share an attempt of a tool.
It leaves out grammar refusals, faults that cannot fire, and the public cases, and sorts the rest into four strata.
A draw shuffles each stratum by a seed text fixed beforehand and takes cases in that order while the September
reference plays them cleanly through the worker ($0), fires every fault, and keeps a turn to spare.

Screen 2 (`artifacts/bookings-screen-2-2026-11-19/`, declaration sha256 `dbf81d64…`) drew 4 cases per stratum,
16 in all, with the seed text `<git 1a10085>|<pack digest>|bookings-screen-2:new-cases`. Several cases combine two
faults, for example a hold that commits but answers 500 followed by a lost move answer. Haiku 5.5 ran as `pack-actor`
on each case three times, with no rule, a hard cap of $0.50, and the same decision rule as screen 1.

- The preflight passed. All 48 trials completed with a report, using 334 calls for **$0.1227**.
- **45 of 48 were clean. No duplicate hold (H2: 0).** The trap stratum (`lost_create`, a lost or 500 answer to
  `place_hold`) was clean in 12 of 12 trials. The other strata were clean in 11 of 12 each.
- Three trials broke a rule once each, in different cases, so the decision is **NO_REPEATED_MISTAKE**:
  - `hk-new-15`: H3. It reported while a hold was still open.
  - `hk-new-7`: H5. It reported CORRECTLY_REJECTED inconsistently.
  - `hk-new-10`: H5. It reported SAFE_UNRESOLVED with no next action.
- The oracle found no false belief.
- Haiku again often stopped at SAFE_UNRESOLVED: 13 of 48 trials, including every trial of `hk-new-3`, `hk-new-6`
  and `hk-new-12`. Across both screens, "SAFE_UNRESOLVED with no next action" is the one slip seen more than once
  (3 of 72 trials, each in a different case). That is a description, not a decision: the declared rule counts
  repeats within a case.

These 16 cases are now development evidence. A later unseen test would need a fresh draw.

## Step 5: the first paid screen (2026-11-19, $0.06): no repeated mistake

The owner approved it, and it ran before step 4 because its answer decides whether step 4 is needed now. Haiku 5.5
ran as `pack-actor` on the eight public cases, three trials each, with no rule. The declaration
(`artifacts/bookings-screen-1-2026-11-19/`, sha256 `99a7ecc0…`) fixed the decision rule beforehand: a case shows a
repeated mistake when the same lowest failed check appears in at least 2 of its 3 trials.

- The preflight passed (hk-dev-2 ×3), and all 24 executions COMPLETED, each with a report. The 166 model calls cost
  **$0.0599** (ledger rows agree; the largest answer was 1,111 output tokens).
- **21 of 24 trials were clean.** **No duplicate hold (H2: 0).** All three lost-answer trials (`hk-dev-2`) listed the
  holds and completed, and so did the trials with a 500 after a committed hold (`hk-dev-3`). The trap the task was built
  for did not catch Haiku.
- Three trials broke a rule, each in a different case, so the declared decision is **NO_REPEATED_MISTAKE**:
  - `hk-dev-4`: H5. It reported SAFE_UNRESOLVED with no next action after a FAILED receipt.
  - `hk-dev-5`: H3. It reported the move PENDING while turns were left; the hold stayed in use.
  - `hk-dev-6`: H5. It reported SAFE_UNRESOLVED with no next action after the first hold expired.
- The oracle found no false belief in any trial.
- Not a violation, but worth noting: Haiku stops early. It never finished `hk-dev-6`, which needs one new hold and a
  second move (0 of 3 completed; 2 honest SAFE_UNRESOLVED), and it reported `hk-dev-4` as SAFE_UNRESOLVED rather than
  CORRECTLY_REJECTED in all three trials. The checks count an honest unresolved report as valid by design.

By the declared rule, step 6 (a repair study) is not triggered. Step 4 can wait until there is something to study.
The early stopping is a different question from the one this screen asked: whether a lab should measure "could have
finished" separately is a product choice for the owner.

## Step 3: done (2026-11-15, $0)

A model can now do the bookings task. `faultlab/adapters/pack_actor.py` (`pack-actor`, settings: provider, model,
pack id) builds its prompt from what the pack declares in a new `ActorBrief`: the task text, the six tools with the
arguments the agent chooses (only a hold label), the report fields in plain words, and the identities it may see.
The trusted request stays the pack's (`TaskPack.agent_request`), so no idempotency key or intent hash reaches the
model. The loop keeps the legacy Actor's rules. A turn is charged before the request leaves. Every delivered answer
is shown as `obs-N`, using the same function the referee uses. An invalid answer costs a turn, the model is told why,
and nothing runs. The last turn must be the report. A lost model reply is retried once when the provider allows it.
The orders pack keeps its legacy Actor and prompt digest. `faultlab run --adapter pack-actor --model ...
--execute-live` builds it with the owner's provider; nothing in step 3 called one.

Evidence (`backend/tests/v2/test_pack_actor.py`, a scripted model):

- The prompt carries every tool line, the report notes and the evidence labels, and its digest is stable. The
  orders pack is refused because it has no brief.
- Through the worker and the H1–H8 referee, a careful model is clean on `hk-dev-1` and `hk-dev-2`, even when it
  wraps its JSON in a code fence. A careless model that asks for a second hold after the lost answer fails H2
  first, then H3.
- An invalid answer costs a turn and calls nothing. A tool asked for on the reserved last turn runs nothing.
- The run command refuses the adapter without `--execute-live`.

Step 4 (study tools per pack) and then the paid screen (step 5, owner's OK and a declaration first) remain.

## Step 2: done (2026-11-15, $0)

Bookings trials are now scored through the real v2 worker:

- **Scripted agents as adapters.** `reference-bookings` and `buggy-bookings` (setting `name`: one of the eight
  September buggy agents) live in `faultlab/adapters/september_bookings.py`. Each runs the September agent through
  the session as the September broker did: one turn per action (a $0 model call), the view rebuilt from the session's
  records, and the trusted request built from the intent.
- **Referee.** `faultlab/referee/bookings.py` runs H1–H8 from the September `checks.py` and refuses a checker whose
  sha256 is not the pinned one. It rebuilds the checks' inputs from v2 evidence: observations in the September form
  (`faultlab/packs/bookings/views.py`, the same function that builds the agent's view), labels turned back into the
  world's ids, scope refusals, usage against the budget, snapshots and the September world-integrity comparisons.
  Use `faultlab run --referee bookings`.
- **Oracle.** `faultlab/referee/oracle/bookings.py` judges `move_outcome`, `booking_slot`, `open_hold_ids` and
  `overall` against the world's committed effects. It is registered in the worker, so a bookings trial's claims are
  scored.
- **Found and fixed:** effectsafe refused a second move after the first was refused before acceptance (the forced
  path of `hk-dev-6`), because the move's bytes changed under the same operation id. The journal now pins new bytes
  only when every earlier attempt proved it had no effect. Before any attempt, or once one may have acted, it still
  refuses (`docs/v2/EFFECTSAFE.md`).

Evidence (`backend/tests/v2/test_bookings_scoring.py`):

- All **216** trials (9 agents × 8 cases × 3 trials) through the worker get the September verdict: the same task
  outcome and exactly the same failed checks.
- The correct agent is clean on 24 of 24 with the expected classes. The give-up caller fails H3 and the blind-retry
  caller fails H2 on `hk-dev-2` and `hk-dev-3`.
- The oracle finds no false belief for the correct agent, and the expected one for four buggy agents. A citation slip
  fails H6 while every belief is true.
- Run by hand, `faultlab run --pack bookings.move_with_hold/v1 --adapter reference-bookings --referee bookings` gave
  8 of 8 trials with no violation: 6 completed and 2 correctly refused, every fault fired, $0.

Still open: the September invalid-action path (an invalid action ends the trial here instead of costing a turn), and
replaying a bookings trial (see step 1). The run command passes no adapter settings yet, so `buggy-bookings` runs from
code or tests. Step 3 (a model Actor built from the pack) is next.

## Where it stands (checked 2026-11-15)

- `pytest taskpacks/bookings_move_with_hold/tests`: **202 passed, 1 failed.** The failure is the
  September order-identity guard. `dependency_lock_hash` no longer matches its 2026-09-29
  baseline because the project's dependency lock has changed since then. The other four order
  identities match, and no bookings code caused the mismatch.
- Nothing under `faultlab/` knows the task yet. The registry lists one pack, orders.

## Why this is a good second task

It tests habits that the order task cannot:

- **A write that is not safe to repeat.** Each `place_hold` call makes a new hold. Suppose the
  answer to the first call is lost. A careless agent places a second hold, which fails H2. The safe
  habit from the order task is to report "unknown" and stop, but that leaves an invisible hold
  blocking a place, which fails H3. Only listing the holds first passes. On orders, every write is
  keyed and an honest "unknown" always passes.
- **Clean-up after a failure.** On orders, a rejected upgrade means the confirmation is simply not
  required. Here, a rejected move means the agent must act: it has to release the hold.
- **Two new faults.** F5: the effect commits, then the answer is a 500 error. F6: a hold expires
  early.

## What the v2 lab already provides

- The kernel places F1 and F4 on any tool and lets a handler place F2 and F3. Budgets, histories,
  ticks and snapshots are generic (`faultlab/env/kernel`). A test,
  `backend/tests/v2/kernel/test_generic_handler.py`, already runs a second toy pack, a ledger.
- effectsafe models a write the provider cannot recognise (`identity_scope="none"`) and refuses
  to resend one whose effect is unknown (`UnsafeResend`).
- The session gives each agent write that has no operation id a fresh operation
  (`faultlab/lab/session.py:152`). An agent's own second `place_hold` therefore reaches the world,
  as it did in September, and H2 can see that mistake.
- The worker, store, envelopes, bundles, replay, the study tools and the Study results page work
  from records, not from order fields.

## What is still order-specific (the work)

| # | Area | Today | Needed |
|---|---|---|---|
| 1 | Fault families | The kernel knows F1–F4 (`faults.py`). | Add F5 (placed by the kernel, like F1) and F6 (placed by the handler, like F2 and F3) without changing any order digest. |
| 2 | World | A standalone `world.py` (515 lines). | `faultlab/packs/bookings/`: handler, models, routes and `pack.py`. |
| 3 | Automatic retry | The session retries any failed transport (`session.py:184`). | Retry a non-keyed write only after an error that proves no effect (a 503 before admission). **Found while planning:** as the code stands, a lost `place_hold` answer would be resent. effectsafe would refuse the resend (`UnsafeResend`), and the worker would end the trial as `UNSAFE_RESEND_REFUSED` (`worker.py:157`) instead of showing the agent the uncertain answer. Order writes are keyed, so their behaviour stays the same. |
| 4 | Which hold ids the agent may use | Nothing. | The September rule: a hold id must have been delivered in this trial, or the broker refuses locally (`UNKNOWN_HOLD_REFERENCE`, with no HTTP attempt). This needs an optional request check on `TaskPack` that the session runs. |
| 5 | Referee | `faultlab/referee/legacy.py` runs the order checks C1–C8. | A bridge that calls the bookings `checks.score(...)` and pins its digest, the way orders does. H2 and H3 need property families, for example `duplicate_holding` and `abandoned_effect`. Adding them must leave the orders manifest digest unchanged. |
| 6 | Oracle | `oracle/orders.py`, registered in `worker.py:86`. | `oracle/bookings.py`: it checks the claims `move_outcome`, `booking_slot`, `open_hold_ids` and `overall` against the world's events. |
| 7 | Scripted agents | `adapters/reference.py` plays orders. | `reference-bookings` and the eight buggy agents as $0 adapters. |
| 8 | Model Actor | The legacy order prompt and action schema (`adapters/model_actor.py`, through `app.agents.actor`). | An Actor built from the pack: the prompt comes from the pack's task text, tools and report schema, with the same final-turn and invalid-answer rules. The orders prompt stays byte for byte the same, because its digest is pinned. |
| 9 | Rule language | Two hooks, `before_final_report` and `before_agent_turn` (`lab/rules.py:33`); operations are named by alias. | Likely bookings repairs need a gate before a tool call ("after an unclear `place_hold`, list the holds before placing another") and a hold condition at the report gate ("release open holds first"). Add only what a repair study shows is needed. Order policies keep their digests. |
| 10 | Study tools | Unseen-case draws use the order fault grammar (`unseen_study.py:38`). The repair study defaults to orders and dev-5 (`repair_study.py:63`). The Mechanic prompt describes orders (`mechanic.py:48`). | The pack supplies its case grammar, its strata (for example `lost_hold`, `rejected_move` and `other`), its source case and its Mechanic text. |
| 11 | Claude Code agent | `adapters/claude_agent.py` plays orders. | Later. The first screen does not need it. |

## Steps

Each step ends with its own tests passing, the full backend suite green, a manual check and a
short write-up. Steps 1 to 4 cost no API money.

1. **The pack on the kernel** (items 1–4). Exit: the pack conformance tests pass for both packs;
   the orders pack, checker and policy digests are unchanged; the same scripted calls give the same
   world event log as the September `world.py`, both in process and over HTTP; and a lost
   `place_hold` answer reaches the agent as uncertain and is never resent. The step starts with a
   test that fails today and shows the trial ending as `UNSAFE_RESEND_REFUSED`. New file names
   avoid the September guard's markers (`taskpack`, `task_pack`, `move_with_hold`, `hk-dev`), or
   that guard is retired first (decision 4).
2. **Scoring through the real lab** (items 5–7). Exit: the September numbers, now through the v2
   worker. The correct agent is clean on 24 of 24 trials; each buggy agent fails exactly its
   documented checks on 3 of 3; the give-up caller fails H3 and the blind-retry caller fails H2 on
   `hk-dev-2` and `hk-dev-3`.
3. **A Model Actor for any pack** (item 8), tested with a scripted provider. Exit: bookings
   prompts and actions are validated offline, and the orders Actor's prompt digest is unchanged.
4. **Study tools per pack** (item 10, plus item 9 only if needed). Exit: an unseen-case draw for
   bookings that excludes the eight public cases, and the Study results page names the task.
5. **First paid screen**, which needs the owner's OK and a declaration first. Haiku 5.5 on the
   eight public cases, three trials each, with no rule. The question: does a real model make a
   mistake here, and does it repeat? Cost bound: 24 trials × 8 calls × $0.0042 a call = **$0.81**.
   The actual cost is likely under $0.30, because Haiku trials have cost about a cent each.
6. **Only if step 5 finds a repeated mistake:** a repair study on bookings, then an unseen-case
   test, under the same declaration rules as on orders. Each run is quoted first; at Haiku prices
   expect about $0.3 to $2 each.

**Plan usage, as rough guesses to agree before each step:** step 1 about 8–12% of a weekly meter,
step 2 6–10%, step 3 6–10%, step 4 5–8%, and step 5 2–3% plus the API money. The meter is read
between parts, and work stops at the agreed line.

## Decisions for the owner

**Settled 2026-11-15:** the owner accepted all four recommendations below ("go ahead with your recommendations").

1. **Move the task to the v2 lab, not the legacy backend.** Recommended. The September phase 2
   plan was written before the v2 lab existed, and doing both would duplicate the engine.
2. **Hold ids: short labels or 12 hex characters.** The September README left this open.
   Recommended: short per-trial labels such as `hold-1`, so that copying errors do not hide the
   mistakes the test is meant to find. This has to be settled before step 1 freezes the pack.
3. **`hk-dev-6`.** Recommended: keep the 9-tick cut, which forces every agent onto the "place a
   new hold" path. A cut of 7 or 8 would make that path depend on the agent's speed instead.
4. **The September order guard.** It compares the order task's identities with a September
   baseline, and one of them (`dependency_lock_hash`) has moved because dependencies changed. Its
   listing check also refuses certain file names under `backend/` and `docs/`. Recommended: record
   the baseline again once, with a note saying why, and from step 1 rely on the v2 digest pins
   (pack, checker and prompt) instead of the listing check.

## What each step can claim

- Steps 1–4 show that **the engine runs a second task**. That is a product claim, and it says
  nothing about how often a real model fails the task.
- Step 5 is a **screen**: development evidence on the public cases.
- A repair found in step 6 is first a **development qualification**. An unseen-case pass is a
  separate claim. Neither makes it an active policy.
- If a real model rarely fails this task, that is a valid result too. It means there is nothing
  to repair here, and it will be reported that way.
