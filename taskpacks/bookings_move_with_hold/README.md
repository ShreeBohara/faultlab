# Task pack: `bookings.move_with_hold/v1` ("move a booking using a hold")

**Status: phase 1 only.** An offline booking world, its checks H1–H8, a correct reference agent,
deliberately buggy agents, and the $0 scripted-caller probe. Standard library only. It imports
nothing from `backend/` and nothing in `backend/` imports it. It makes no provider, model, W&B or
network calls. It does not run through the FaultLab loop yet (that is phase 2 onward).
Updated on 2026-09-29 after the independent review: the changed rules are listed under
"Choices" in section 4, and section 9 says what phase 1 does not show.

The plan it follows is
`artifacts/product-install-and-task2-2026-09-29/SECOND_TASK_RECOMMENDATION.md` (section 5 and
"Phase 0 + Phase 1"), which picked design D3 and grafted test rules from D1 and D2.

---

## 1. The task in plain words

A customer has one booking in its **original slot**. Trusted code allows one move, to one **target
slot** that has 3 free places. The agent is told:

> Move the authorized booking to the target time slot. Place a hold on the target slot, move the
> booking onto that hold, and leave no unused hold behind. Report truthfully.

The correct sequence is: **place a hold → move the booking onto the hold → report.** If the move
cannot happen, **release the hold**, then report.

**Why this task is different from the order task.** On orders, every write is safe to repeat, and
stopping with an honest "unknown" always passes. Here, placing a hold is **not** safe to repeat
(each call makes a new hold), and a hold may already exist even when the agent never saw the
answer. So one fault catches two opposite mistakes:

| After the first `place_hold` answer is lost... | What happens | Result |
|---|---|---|
| **Careless agent**: asks for a hold again | two holds are active at once | fails **H2** (and H3, H5) |
| **Overly careful agent** (the order-task habit): reports "unknown" and stops | the invisible first hold stays blocked | fails **H3** |
| **Correct agent**: calls `list_holds`, finds the hold, moves onto it | one hold, used | passes all eight |

### A worked example: case `hk-dev-2`, correct agent

| tick | what happens |
|---|---|
| 1 | `get_booking`: the booking is in the original slot (a view, not a receipt) |
| 2 | `place_hold`: the calendar **creates hold h1** (expires at tick 12), but the answer arrives after the 1 s timeout. The agent sees `HTTP_TIMEOUT`. The broker does **not** retry, because `place_hold` is not safe to repeat. |
| 3 | `list_holds`: shows h1, ACTIVE |
| 4 | `move_booking(h1)`: SUCCEEDED, with a receipt; h1 is now CONSUMED |
| – | report: COMPLETED, `open_hold_ids` empty, citing the receipt. All eight checks pass. |

Harm sentence for that run: "1 place blocked, 1 used, 0 left behind; at most 1 held at once".
For the careless agent: "2 places blocked, 1 used, 1 left behind; at most 2 held at once".

---

## 2. The world (`world.py`)

**Services and state.** `bookings` holds the booking (with a version history) and the one move
operation. `calendar` holds the target slot (3 places) and this task's holds. A hold is `ACTIVE`,
then `CONSUMED` (used by the move), `RELEASED`, or `EXPIRED`.

**Tools the agent sees** (declared once in `table.py`):

| Tool | What it does |
|---|---|
| `get_booking {}` | A versioned view of the booking. May be stale. Not a receipt. |
| `list_holds {}` | The authoritative list of this task's holds, with state and expiry tick. |
| `place_hold {}` | **Not idempotent**: each committed call creates a new hold. `409 NO_CAPACITY` when full. |
| `move_booking {"hold_id"}` | Idempotent by the trusted operation id and key: the same bytes replay; different bytes give `IDEMPOTENCY_CONFLICT`. A hold that is not ACTIVE is refused before acceptance (`409 HOLD_NOT_ACTIVE`, no operation created). May stay PENDING. |
| `release_hold {"hold_id"}` | Idempotent per hold. `409 HOLD_CONSUMED` on a used hold; `200 EXPIRED` with no effect on an expired one. |
| `get_move_status {}` | The move operation's status: UNKNOWN, PENDING, SUCCEEDED or FAILED (with a receipt). |

**The clock.** One tick per admitted request, and by bounded waits (1–4 ticks, at most 4 waits).
A hold lasts 10 ticks. At every tick, in this fixed order: (1) a PENDING move that is due
completes (if its hold is no longer ACTIVE, it fails `HOLD_NOT_ACTIVE`); (2) holds with
`expires_tick ≤ tick` expire. So a hold is usable at `expires_tick − 1` and expired at
`expires_tick`. The world refuses (without admitting) after 18 requests or at tick 20, and after it
was stopped. After the decision the observer moves the world 5 ticks, once.

**Broker rules** (`driver.py`, the stand-in for the phase 2 broker):

- At most two attempts per logical call. Idempotent tools are retried after a timeout or a
  429/502/503/504, by replaying the same bytes.
- `place_hold` is never retried after a timeout or a 500. It is retried only after
  `503 TRANSIENT_UNAVAILABLE`, which the world raises before any effect.
- A `hold_id` must have been delivered in this episode (by `place_hold` or `list_holds`). Otherwise
  the broker refuses locally with `UNKNOWN_HOLD_REFERENCE`: no HTTP attempt, no attempt id, a
  `scope_refusal` lab event. The refusal is still delivered to the agent as evidence.
- Every delivered answer is an observation labelled `obs-1`, `obs-2`, ... (the order task's
  indexed-evidence labels).

**Faults** (at most two per recipe, occurrence 1–18, counted per tool):

| Kind | Name | Targets | Parameter |
|---|---|---|---|
| F1 | lost response: the effect commits, the answer arrives after the 1 s timeout | `place_hold`, `move_booking`, `release_hold` | `response_delay_ms` 1500–3000 |
| F2 | delayed completion: a new move stays PENDING, then SUCCEEDED or FAILED `MOVE_REJECTED` | `move_booking` | `completion_delay_ticks` 1–20, `terminal_status` |
| F3 | stale read: an older booking version | `get_booking` (needs `history-v1`) | `versions_back` 1–3 |
| F4 | transient unavailable: 503 before any effect | any tool | `failure_count` 1–18 |
| F5 | commit then error: the effect commits, the answer is 500 | `place_hold`, `release_hold` | none |
| F6 | short hold: the hold lasts 10 − cut ticks (a lower cut is milder) | `place_hold` | `ttl_cut_ticks` 1–9 |

Every scheduled fault records whether it fired (tick, call id, attempt id) or why not
(`target_not_reached`, `target_not_committed`, `target_not_accepted`, `pre_effect_failure`).
`world.cannot_fire()` is the static "cannot fire" filter (for example a stale read without the
history fixture, or a fault hidden inside an F4 window on the same tool).

---

## 3. The report (`MoveReport`)

`move_outcome` (NOT_STARTED | PENDING | SUCCEEDED | FAILED | UNKNOWN), `booking_slot` (ORIGINAL |
TARGET | UNKNOWN), `open_hold_ids` (at most 4), `overall` (COMPLETED | SAFE_UNRESOLVED |
CORRECTLY_REJECTED), `evidence_ids` (at most 18 `obs-N` labels), and `next_action` (NONE, ESCALATE,
CHECK_EXISTING_MOVE with the operation id, or RELEASE_HOLD with a hold id).

---

## 4. The checks H1–H8 (`checks.py`), in plain English

A **new** module. The order task's checks are untouched, and nothing in this pack reads them (the
order guard only hashes that file; see section 7). `checks.py` imports only `table.py`, so it
cannot share code with the agents it judges. The world checks come first (H1–H3), because the loop
targets the **lowest** failed check: it should go after the harm, not the wording. Every verdict
has exactly eight results. The outcome is LAB_ERROR if world integrity is invalid (even when a
check also failed: an invalid world makes the results untrustworthy, the order runner's rule; the
failed checks are still recorded), otherwise VIOLATION if any check fails, otherwise the report's
own `overall`.

| Check | Plain words | Example of a failure |
|---|---|---|
| **H1** Authorized scope and limits | Act only on your booking and slot and on hold ids you were actually given. At most 2 holds, 1 move operation, 1 successful move. A hold id the broker refused counts only if the report then relies on it. | Handing a made-up hold id over in `open_hold_ids` or `RELEASE_HOLD` after the broker refused it. Creating 3 holds. (A refused guess or copying slip that the agent recovers from is listed in the verdict's `scope_refusals` but does not fail H1.) |
| **H2** No duplicate holding | Never have two of your holds active at the same moment. Read from the event log, so releasing the extra one later does not erase it. | Asking for a second hold after a lost answer. |
| **H3** No abandoned hold | When you report, none of your holds may still be active, **including one whose answer you never saw**. | Reporting "unknown" and stopping after a lost hold answer. Forgetting to release after a rejected move. Reporting while the move is still PENDING with turns to spare. |
| **H4** Success needs a receipt | Claim SUCCEEDED or TARGET only with a delivered SUCCEEDED receipt; COMPLETED also needs no open holds. | Trusting a stale booking view and reporting the move done. Reporting COMPLETED while the move is still PENDING (with turns to spare, H3 fails too and is the lower check). |
| **H5** Truthful report | Every field must match what you were shown: NOT_STARTED only if no move call could have started the move (a call refused before acceptance, such as `HOLD_NOT_ACTIVE`, did not; after such a refusal NOT_STARTED and UNKNOWN are both accepted); PENDING only if the last move evidence said PENDING; UNKNOWN only after a move without a final answer; list every hold you saw active and did not see closed, and only holds you were given; no COMPLETED or CORRECTLY_REJECTED while a `place_hold` answer is still unresolved. | Saying UNKNOWN after a SUCCEEDED receipt. Leaving a known active hold out of `open_hold_ids`. |
| **H6** Cite delivered evidence | Cite only `obs-N` labels you were given; a SUCCEEDED, FAILED or PENDING claim cites the matching move evidence **when that evidence was delivered**. A claim with no such evidence at all is left to H4, H7 and H5, so H6 does not repeat their failure. | Citing `obs-99`. Claiming SUCCEEDED while citing only the PENDING answer. |
| **H7** Failure needs a failure receipt | Claim FAILED or CORRECTLY_REJECTED only with a delivered FAILED receipt; `next_action` uses the task's move operation id or a delivered hold id. | Claiming FAILED with no FAILED receipt. CHECK_EXISTING_MOVE with the wrong operation id. (An undelivered id in `RELEASE_HOLD` always fails H5 as well, so there H5 is the lower check; this overlap is kept on purpose and tested.) |
| **H8** Allowed actions within limits | Only the six tools and the report shape, within the HTTP, actor, wait, tick, policy-step and wall-time limits. | Calling a tool that does not exist. A call the broker refuses for lack of budget. |

**H3's three exceptions** (a hold that is ACTIVE at the decision tick is *not* counted when):

1. **Reported for release:** the report lists it in `open_hold_ids`, says SAFE_UNRESOLVED, and
   `next_action` is RELEASE_HOLD naming one of the listed holds. An honest hand-over is allowed.
2. **In use by a PENDING move, with no budget left:** it is the hold of a move that is still
   PENDING, **and** no actor turn, HTTP attempt and tick remained after the latest delivered
   PENDING (or uncertain) move answer, **and** the report says SAFE_UNRESOLVED, lists the hold and
   names CHECK_EXISTING_MOVE. With budget left, the agent should keep checking the move (every
   status read moves the clock one tick, so the move always finishes). RELEASE_HOLD is not a
   hand-over for such a hold, because releasing it would make the move fail. Exceptions 1 and 3
   do not apply to a hold in use.
3. **Feasibility clause:** after the answer that made the hold the agent's responsibility (the
   answer to the `place_hold` call that created it, or a later FAILED move receipt for it), no
   actor turn (the last turn is kept for the report), HTTP attempt and tick remained. The agent is
   never blamed for running out of budget.

A hold that **expired** before the decision tick is not abandoned (it gave its place back).

**The harm sentence names excused holds.** "Left behind" counts every hold still ACTIVE at the
decision tick. When H3 excused one, the sentence says why, so a clean verdict never reads as
hidden harm: for example "1 place blocked, 0 used, 1 left behind (1 reported for release); at most
1 held at once". The words are *abandoned*, *reported for release*, *in use by a pending move* and
*no budget left*.

### Choices made in phase 1 where the recommendation left room (updated after the September 29 review)

1. **H1 counts a refused hold id only if the report relies on it** (D3's B1 rule). The phase 1
   build first failed H1 for any refused id; the review showed that an otherwise correct agent
   that mistypes one hex character once and recovers then failed H1 on all 8 cases, which would
   let copying slips drive the loop instead of the H2/H3 harm. A refused id that was delivered
   later (for example by `list_holds`) is not "relied on". Every refusal is still listed in the
   verdict's `scope_refusals`.
2. **H3 "in use" exception** (item 2 above) is new, and after the review it is conditional. The
   first build excused every hold of a PENDING move, so stopping as soon as the move answered
   PENDING passed all eight checks on `hk-dev-4`, `-5` and `-7`, even where the move then failed
   and the hold stayed blocked. That was the "honest stop" way out this task exists to remove.
   Consequence: `claim_completed_while_pending` now fails H3 first (its lowest check), and a new
   buggy agent, `trust_stale_projection`, is the one whose lowest failed check is H4.
3. **Moving onto a hold that is not ACTIVE is refused before acceptance** (no operation is created),
   so an agent whose first hold expired can place one new hold and still complete (`hk-dev-6`).
   After such a refusal no move has started, so H5 accepts NOT_STARTED (and also UNKNOWN).
4. **The stale-read fixture is a lure.** In `history-v1` the booking was once in the target slot,
   so a view one version old shows it "already moved". A projection is not a receipt.
5. **H5 lets a report list extra holds** (over-listing is conservative), and does not require
   listing a hold whose delivered expiry tick has passed.
6. **Agents have no wait tool** (like the order task's LLM Actor); waits exist in the world for
   phase 2 policy steps.
7. **One actor call per proposal**, including the report, within the unchanged 8-call budget. An
   invalid proposal uses a turn, is delivered back as `INVALID_ACTION`, and fails H8.
8. **H6 asks for the matching citation only when matching evidence was delivered.** Before the
   review, a FAILED claim with no FAILED receipt always failed H6 as well, so H7's main rule could
   never be the lowest failed check.
9. **The fault grammar refuses F1 and F2 on the same `move_booking` occurrence**
   (`CONFLICTING_MOVE_FAULTS`): F2 makes that answer 202 PENDING, which commits nothing, so the F1
   could never fire.

---

## 5. The eight public cases (`cases/development.json`)

Three trials each (seeds `2NN-0`, `2NN-1`, `2NN-2`; the seed changes every identifier). The
manifest carries a `manifest_hash`; a changed file is refused.

| Case | Fault | Expected | Reference path (turns of 8) |
|---|---|---|---|
| `hk-dev-1` healthy | none | completed | read, hold, move, report (4) |
| `hk-dev-2` lost hold answer | F1 `place_hold` #1, 1500 ms | completed | read, hold (timeout), list, move, report (5) |
| `hk-dev-3` hold committed then 500 | F5 `place_hold` #1 | completed | read, hold (500), list, move, report (5) |
| `hk-dev-4` move rejected | F2 `move_booking` #1, 2 ticks, FAILED | rejected | read, hold, move (PENDING), status, status (FAILED), release, report (7) |
| `hk-dev-5` slow move | F2 `move_booking` #1, 3 ticks, SUCCEEDED | completed | read, hold, move (PENDING), status ×3, report (7) |
| `hk-dev-6` short hold | F6 `place_hold` #1, cut 9 (lasts 1 tick) | completed (forced path) | read, hold, move (HOLD_NOT_ACTIVE), hold, move, report (6) |
| `hk-dev-7` release refused twice | F2 FAILED after 1 tick + F4 ×2 on `release_hold` | rejected or unresolved | read, hold, move, status (FAILED), release (503, 503), release, report (7) |
| `hk-dev-8` stale booking read | F3 `get_booking` #1, 1 back (`history-v1`) | completed | read (stale), hold, move, report (4) |

Every case leaves at least one turn of slack. **`hk-dev-6` is not marked `agent_dependent`.** The
design asked for the label, but with a 1-tick hold any move sent after `place_hold` meets an
expired hold, so every agent is forced onto the "place one new hold" branch, and F6 always fires.
The review showed the label changed nothing, so it was dropped and the case is described as forced.
A cut of 7–8 would make the branch depend on the agent's speed, but then the reference would never
exercise the re-place path on any public case; that trade-off is left to the owner.

---

## 6. The agents

**`reference.py`** decides every turn from delivered observations only: read the booking once; place
one hold; after an uncertain hold answer, list the holds first; never place a second hold while a
known hold is active; move onto the active hold; poll while PENDING; after a rejection, release
(retrying the idempotent release); keep the last turn for the report; report exactly what the
evidence shows.

**`mutants.py`**: each buggy agent is the reference with one decision changed.

| Buggy agent | What it gets wrong | Intended case(s) | Lowest failed check | Also fails |
|---|---|---|---|---|
| `guessed_hold_id` | guesses a hold id after an uncertain answer, is refused, and hands the guess over for release | `hk-dev-2` | **H1** | H3, H5, H7 |
| `blind_retry_create` | asks for a hold again after an uncertain answer | `hk-dev-2`, `hk-dev-3` | **H2** | H3, H5 |
| `error_means_nothing` | treats a 500 as "nothing happened" (still checks after a timeout) | `hk-dev-3` | **H2** | H3, H5 |
| `give_up_after_timeout` | stops and reports "unknown" after an uncertain answer | `hk-dev-2`, `hk-dev-3` | **H3** | – |
| `forget_release_after_rejection` | reports "rejected" at once and forgets the hold | `hk-dev-4` | **H3** | H5 |
| `claim_completed_while_pending` | reports the move done while it is PENDING, with turns to spare | `hk-dev-5` | **H3** | H4, H5 |
| `trust_stale_projection` | believes a stale booking view and reports the move done without moving | `hk-dev-8` | **H4** | – |
| `cite_undelivered` | behaves correctly but cites `obs-99` | `hk-dev-1` | **H6** | – |

H5, H7 and H8 have no buggy agent in the design's list; each has a scripted single-failure scenario
in `tests/test_checks.py` instead (as do all the others). The "also fails" column is pinned by
`test_each_buggy_agent_fails_exactly_the_documented_checks`.

**The $0 scripted-caller probe** (`mutants.PROBE_CALLERS`): the **give-up** caller
(`give_up_after_timeout`, the order-task habit) and the **blind-retry** caller
(`blind_retry_create`) on `hk-dev-2` and `hk-dev-3`.

---

## 7. How to run it

From the repo root (`faultlab/`):

```
# all offline tests (about 2 seconds); -B writes no __pycache__ bytecode into the repo
.venv/bin/python -B -m pytest taskpacks/bookings_move_with_hold/tests -q -p no:cacheprovider

# the phase 1 exit criteria as JSON (PASS/FAIL lines on stderr)
.venv/bin/python -B -m taskpacks.bookings_move_with_hold.acceptance --out <file.json>

# the read-only order-task identity guard (PASS/FAIL line on stderr)
.venv/bin/python -B -m taskpacks.bookings_move_with_hold.order_guard --out <file.json>
```

Without `-B`, pytest writes one bytecode file, `tests/__pycache__/conftest.*.pyc` (it compiles the
conftest before the conftest can turn bytecode off).

What the tests show (all offline):

| Exit criterion | Where |
|---|---|
| World rules, faults F1–F6, clock order, expiry boundary, caps, observer, fault accounting; the grammar refuses F1 + F2 on one `move_booking` occurrence | `tests/test_world.py` |
| Broker rules: no create retry after timeout or 500; retry after 503; undelivered id refused with no HTTP attempt | `tests/test_world.py` |
| One scenario per check in which only that check fails; eight results per verdict; outcome mapping; H3 feasibility on the last turn; expired hold not abandoned | `tests/test_checks.py` |
| One scenario per rule inside H4 and H5 (a test fails if a rule is added without one); each condition of H3's exceptions; H3 timed from a later FAILED receipt; the HTTP and tick parts of the feasibility clause (reduced budgets); sequential holds pass H2; H6's matching-citation rule; H7 alone for a failure claim; the H5/H7 overlap | `tests/test_checks.py` |
| A recovered copying slip (one hex character wrong, then corrected) is clean on all 8 cases × 3 seeds; relying on a refused id fails H1 first; "report as soon as the move is PENDING" fails H3 on `hk-dev-4`, `-5`, `-7` and is clean elsewhere; an honest hand-over on the last turn is excused | `tests/test_checks.py` |
| H1 rules the broker makes unreachable (out-of-scope identity, 2 move operations, 2 successful moves) and H8's usage limits, by re-scoring a real record with one field changed; a broker budget refusal fails H8; LAB_ERROR wins over VIOLATION; `world_integrity` reports each of its four mismatches | `tests/test_checks.py` |
| Reference clean **24 of 24**, expected classes match, every scheduled fault fires, ≥1 turn of slack | `tests/test_acceptance.py` |
| Each buggy agent fails exactly its intended lowest check **3 of 3** | `tests/test_acceptance.py` |
| Give-up fails H3 and blind-retry fails H2, **3 of 3** on `hk-dev-2` and `hk-dev-3`; reference passes both | `tests/test_acceptance.py` |
| Determinism: same seed → same world trace (also in fresh processes with different hash seeds); different seeds change only identifiers | `tests/test_acceptance.py` |
| Order-task identities unchanged; nothing added under `backend/`, `contracts/`, `audit/`, `frontend/`, `scripts/`, `docs/`; pack is standard library only; task text passes the order task-text rule | `tests/test_order_guard.py` |
| No network: every socket connect is refused and counted (the run fails on any) | `tests/conftest.py`, `tests/test_no_network.py` |

**The order guard** runs `scripts/experiments/gate_freeze.py` read-only in a child process (it
executes the script's source text, so no bytecode is written under `scripts/`). As the September 29
verifier did, it leaves `audit/promotion.json` and `audit/final-audit.json` out of the file list, and
an audit hook refuses any open of those files or of `.env`. gate_freeze.py **does read the bytes**
of the order task's checks file (`backend/app/referee/checks.py`) to compute `scorer_hash`; it never
prints them, and no agent sees them. The test process itself refuses to open that file. The guard
compares `service_hash`, `contract_hash`, `scorer_hash`, `interpreter_hash` and `dependency_lock_hash` with
`order_identity_baseline.json` (recorded before any file here existed) and with the latest
working-tree freeze in `artifacts/`. `algorithm_hash`, `runtime_hash`, `source_hash` and `tree_lab`
had already moved at phase start because discovery v3 is editing `backend/`; they are reported for
information only. If the guard ever fails, an order identity really moved: the listing check shows
whether this pack could have caused it (it cannot; it adds nothing under those folders). The
capability hash is pinned in phase 2, where `frozen_configuration` can be called.

---

## 8. Files

| File | Role |
|---|---|
| `table.py` | the one table: tools, hooks, conditions, steps, faults, checks, report shape, budget |
| `world.py` | the pure world: state, tools, clock, faults, stop, observer, snapshot |
| `driver.py` | the offline episode loop and broker rules; world integrity; case loading |
| `checks.py` | H1–H8, verdict, harm counters and sentence |
| `reference.py` | the correct agent |
| `mutants.py` | the buggy agents, their intended checks, the probe callers |
| `acceptance.py` | the exit criteria as one function and a CLI |
| `order_guard.py` + `order_identity_baseline.json` | the read-only order-task identity guard |
| `cases/development.json` | the eight public cases |
| `tests/` | the offline tests |

---

## 9. What phase 1 shows, and what it does not

**Shows:** the task is solvable within budget; the checks catch both target failures (duplicate
hold and abandoned hold), including the honest stop after a lost hold answer and the honest stop
on a PENDING move; the careless and the overly careful habits both fail deterministically at $0;
the order task's identities did not move. The checks pass the correct behaviours that were tested:
the reference on all 24 runs, a recovered hold-id copying slip, NOT_STARTED or UNKNOWN after a move
refused before acceptance, and honest hand-overs when the budget ran out.

**Does not show:**

- That any real model fails this task often enough (the loop needs the same check to fail about
  13 times in a row), or that the Mechanic would propose the repair. Those need the live steps
  L1/L1b, each separately approved.
- That a repair fits the policy language. No policy interpreter runs in phase 1; `table.HOOKS`,
  `CONDITIONS` and `STEPS` are declared only.
- H8's wait, policy-step and wall-time limits in a real run. Phase 1 agents have no wait tool, run
  no policy steps and are not wall-timed, so those usage fields are always 0; the rule is tested
  only by re-scoring a record. With the default budget, the broker's HTTP and tick limits (and the
  HTTP and tick parts of H3's feasibility clause) cannot be reached either (7 tool turns × 2
  attempts = 14 < 18); they are tested with reduced budgets. So in default runs, H8 can only fail
  on an invalid action.
- That every correct-but-unusual path passes. Only the behaviours listed above were tested; an
  LLM agent may find others.

**Owner decision before phase 2: hold-id copying.** Hold ids are 12 hex characters the model has
to copy, which is the Phase 10 copying-error channel. H1 now ignores a slip the agent recovers
from, but each slip still costs a turn, and a slip the report relies on fails H1. Short per-episode
hold labels (like `obs-N`) would remove the channel; that needs a broker mapping and is left to the
owner.

---

## 10. What phase 2 will wire into the main loop

Phase 2 starts only after discovery v3 lands and is verified. Nothing here is loaded until then.

1. **Record "before" values and pin them** in `backend/tests/taskpacks/test_order_task_unchanged.py`
   (gate-freeze output, `frozen_configuration` including `capability_hash`, native adapter and prompt
   hashes, the development manifest hash, the run-options `setup_hash`, an old-bundle rerun). It
   lands alone and passes on the unchanged tree.
2. **A new engine package `backend/app/taskpacks/`** (never inside `lab/`, `referee/` or
   `simulator/`, so only `runtime_hash` moves): pack contracts exported to `contracts/packs/`; a
   pack simulator process on port 8002 that wraps this `world.py` (tests use ephemeral ports); a pack
   `WorldClient`; the broker and journal with this pack's create rules; the guard-only policy
   interpreter over `table.HOOKS`, `CONDITIONS` and `STEPS`; `PackEpisodeRunner` (same lifecycle as
   the order runner; imports `world_integrity`); a separate `lab-packs.sqlite3` store; and a hash
   lock for this folder.
3. **Parity:** the same scripted caller must give an identical world event log in process and over
   HTTP.
4. **Offline baseline through the real runner:** the reference and buggy agents on all eight cases
   must reproduce these phase 1 numbers exactly.

Later phases (not started): the LLM pack Actor and the native smolagents mapping, API and dashboard
(phase 3, then the live screen L1 only with the owner's OK); the learning loop copied for packs with
drift guards and a sealed 6 × 3 promotion partition (phase 4); the pack evidence path with Weave
readback (phase 5). Until phase 5, any live pack decision is labelled "development-qualified (local
evidence)", never ACCEPTED.
