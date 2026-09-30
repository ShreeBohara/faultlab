# History fireability and evidence retry v3 (September 30, 2026)

**Status: built offline by the builder, $0. Not yet reviewed, not yet committed, not run live.**
Runtime `07b8ccc430f7eb40ab2e42c568fcde466273484af73d87d093f631cc5b2e11c9` (algorithm `bc544604…`), built on `95042e4d…`
(the working tree = `backup/part2-2026-09-22` at `432e54b`). Evidence: `artifacts/product-fireability-2026-09-30/builder/`.

Two declared rules, both frozen only into **new** Learn plans. Every plan saved before them keeps its bytes and its behaviour.

| rule | plan field | frozen into | in one line |
|---|---|---|---|
| `faultlab-explorer-selection/v3-history-fireability` | `explorer_selection` | new Learn plans with discovery `v3-history` or `v4-history-replay` | a discovery or challenge pick with a fault on a target that seldom fired in this agent's frozen history is refused before any episode, with one re-plan |
| `faultlab-evidence-retry/v3` | `evidence_retry` | every new Learn plan | the same per-wait retry rule, but 24 automatic retries per campaign instead of 6 |

## 1. Why

Live runs v2d and v2f ([write-up](PRODUCT_NATIVE_V2_RUN_2026-09-29.md)) produced generated guardrails that passed source
validation and ran full challenges with 0 failed checks. Every one of those challenges still ended INCONCLUSIVE, for one
reason. The challenge Explorer picked a schedule with a lone F4 fault on the orders `get_operation_status` read
(failure_count 1). With a healthy upgrade, neither arm needs to read the status, so the fault seldom fires. The pair is
then untriggered, and the challenge's completeness rule (a gate, unchanged) ends the challenge. Discovery picks in v2c,
v2e and v2f spent slots on the same target.

An earlier fix judged picks by what the *candidate's* agent did in source validation. It was withdrawn after review
because it weakened the challenge in a candidate-dependent way
(`artifacts/product-loop-limits-2026-09-30/review-integrity/REPORT.md`). This design does not do that. Its basis is
fixed before any candidate exists.

v2f also stopped for a second reason. It had 10 evidence waits and used up the product's cap of 6 automatic evidence
retries per campaign, so the PM stopped it early.

## 2. Rule 1: history fireability

### 2.1 The table (computed when the plan is saved)

When a new v3-history or v4 Learn plan is saved, its frozen agent history is computed as before
(`app.lab.agent_history`). Then `app.lab.fireability.compute_table` builds a table from **exactly the episodes that
history uses**.

* **Shared eligibility code.** `agent_history._in_scope` is now the one generator both the history and the table read.
  It covers:
  * this agent's identity and the starting policy;
  * development discovery episodes, from a baseline study B0 slot or from a Learn campaign's own discovery pick;
  * completed and Weave-verified episodes only;
  * the same exclusions as the history.
* **Bound to the history.** The table's episode ids must hash to the history's `episode_ids_hash`, otherwise the table
  is refused.
* **What is never read.** Candidate, challenge, source-validation, reproduction, reduction and intervention episodes;
  B1 controls; other agents; other policies; history replay slots; protected data.

For each (fault kind, target service, target tool), the table records:

| field | meaning |
|---|---|
| `verified_episodes` | verified history episodes that scheduled at least one fault on that target |
| `fired_episodes` | how many of those episodes fired **every** fault on that target (its `fault_executions` entry, matched by position, says `triggered: true`) |
| `fired_share` | `fired/verified` |
| `status` | `REFUSED` if at least 3 verified episodes and fired share below 1/2; `ALLOWED` if at least 3 and at least 1/2; `ALLOWED_FEWER_THAN_3` otherwise |

The table is frozen into the plan with its hash. It is recomputed from the store at the history's record cutoff at two
points: at Start (`validate_run_plan`) and before the first Explorer request (`learning.discovery_history`, through
`run_plans.verify_plan_history`). Any difference refuses with AGENT_HISTORY_CHANGED, so no request is sent. The
dashboard's "Check against the store now" button checks it too.

### 2.2 The rule (applied before any episode runs)

* **Which picks are checked.** Every Explorer pick:
  * a discovery slot's pick, including the fixed fallback after an invalid answer;
  * each challenge pick.
  A discovery v4 replay slot is FaultLab's own pick, so it is not checked. Replays fired every fault in every verified
  episode anyway.
* **When a pick is refused.** If any of its faults targets a row marked `REFUSED`. No episode runs.
* **What the refusal records.** It is saved on the selection record, in the field `fireability`, together with the table
  row. A refused discovery pick's `search_decision` is `SKIPPED_UNFIREABLE`, with reason `HISTORY_FIRED_SHARE_BELOW_HALF`.
* **Re-plans.** The Explorer gets **one re-plan** for that slot, told why. A refused re-plan gets none.
* **Budget, unchanged.** Each request is charged exactly as before.
  * **Challenge.** A re-plan is one of the challenge's existing 8 Explorer requests. `app/lab/challenge.py` is
    unchanged.
  * **Discovery.** A re-plan is one of the plan's declared `explorer_requests_max` discovery requests (8), and v4 replay
    slots use none. So under v3-history a re-plan leaves the **last** slot without a request. That slot is recorded
    (`explorer_selection_slots`) and shown in the fault-search panel.
* **Duplicates.** Discovery's duplicate rule runs first, unchanged; a duplicate gets no re-plan.
* **What the Explorer is told.** Each discovery and challenge request states the rule and carries the frozen table, as
  information, under the context keys `explorer_selection_protocol` and `history_fireability`. That block also lists
  this campaign's (or this challenge's) refused picks. A challenge re-plan also gets `slot_request`, `replan_of` and
  `slot_feedback`, the same keys discovery v2 re-plans use. System prompts are unchanged.

### 2.3 What does not change

* **Checks and gates.** Gates, the referee, the simulator, the C1–C8 contracts, `challenge.py` (4 schedules, 3 fresh
  pairs each, every pair must fire, any candidate violation is a counterexample), `evaluation.py`, `promotion.py`,
  reproduction, reduction, `diagnosis.py` and the verdict logic are unchanged. `gate_freeze.py` shows 20/20 files and
  30/30 functions identical.
* **Frozen hashes.** Service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer `19de811c…`, both
  native adapters and prompt v2.1 `fff397c9…`, and the reference Actor prompt `12eabe7f…` are unchanged.
* **Other plans.** Discovery v1, v2 and v3-history-reachability plans are unchanged, and so are baseline and compare
  plans. The pinned v1/v2 Explorer message digests (`test_discovery_v3_flow.py`) still match.
* **Pre-check plans.** v3-history-reachability is deliberately **not** covered. Its reachability pre-check already
  refuses picks whose faults are not forced for the reference Actor, and the task named v3-history and v4 only.

### 2.4 Changed files

`backend/app/lab/fireability.py` (new), `agent_history.py` (the shared generator, output byte-identical),
`agents/explorer.py` (a `fireability` attribute and the decision before the immutable record), `learning.py`,
`run_plans.py`, `api.py` (search attempts carry `fireability`; experiments carry `explorer_fireability`), `exports.py`
(recording). Frontend: `src/historyFireability.ts` (new), `runPlans.ts`, `searchAttempts.ts`, `experiments.ts`,
`components/LoopLimits.tsx`, `CampaignPlan.tsx`, `RunSetup.tsx`, `SearchAttemptsPanel.tsx`, `ChallengePanel.tsx`,
`EvidenceScreen.tsx`, `styles.css`.

The reference Actor **source** hash changes (`fb5e1894…` → `7f78de28…`) because it is a tree hash over
`backend/app/agents`, which holds `explorer.py`. The runtime changes too. **Register every agent again before a live run.**

## 3. Measured on a scratch copy of the saved native-v2b store

`builder/saved_store_check.py` → `builder/saved-store-check.json`. The saved store was read only through a
`mode=ro&immutable=1` connection and its sha256 is unchanged; the scratch copy was outside the Desktop and deleted.
Native adapter v2 was registered again under this runtime; the history identity is the same.

A **new v4 plan** froze a history of 30 verified episodes:
* one baseline study (18 episodes);
* 2 Learn campaigns' discovery picks (12 episodes).

Its table:

| target | verified | fired | status |
|---|---|---|---|
| F1 on update_order (orders) | 4 | 4 | ALLOWED |
| F2 on update_order (orders) | 10 | 10 | ALLOWED |
| F3 on get_order (orders) | 4 | 4 | ALLOWED |
| F4 on send_confirmation (notifications) | 4 | 4 | ALLOWED |
| **F4 on get_operation_status (orders)** | **4** | **0** | **REFUSED** |
| F4 on get_order (orders) | 1 | 1 | ALLOWED_FEWER_THAN_3 |

**Where the 4 episodes behind the refused row come from.** They are discovery picks of v2c (`077b8434`, 2 episodes) and
v2e (`37e66b6c`, 2 episodes). Each was either failure_count 1 or failure_count 2, and all 4 have `target_not_reached`. A
new v3-history plan freezes the same table.

**Reconciling with the task statement.** Counted over *every* stored completed episode, the same target fired in:
* 2 of 14 policy-v0 episodes (5 discovery, 9 challenge incumbent);
* 1 of 9 candidate challenge episodes.
The rule never reads those; the frozen history holds only 4 of them. The fifth discovery episode is v2f's Explorer pick,
whose evidence was never verified.

**Every Explorer pick saved in the store**, checked against the new table:
* challenge: 11 picks, **3 refused** (v2d 1, v2f 2), each the lone status-read pick;
* discovery: 15 picks, **7 refused** (v2c 3, v2e 3, v2f 1), each a lone status-read pick;
* every other pick is allowed, including v2f's F1/F2/F3 on orders and F1/F4 on `send_confirmation`.

**Through the real learning loop on the scratch copy** (test
`test_through_the_real_loop_on_the_saved_store_a_status_pick_is_refused_and_replanned`): the two replay slots ran
first, then the status pick was refused with its row `0/4`, and its re-plan ran.

## 4. Rule 2: evidence retry v3

* **What changed.** `faultlab-evidence-retry/v3` keeps the per-wait rule: at most 3 automatic, telemetry-only retries per
  wait, at 30 s, 120 s and 300 s. It raises the campaign cap from 6 to **24**.
* **Which plans get it.** Every new Learn plan freezes v3. A plan saved under v2 still starts, and keeps its cap of 6:
  `EvidenceWait` reads the cap from the plan. Start accepts exactly the installed v2 and v3 declarations; v2's
  declaration hash is unchanged (`3d849893…`). v1, never run live, is still refused.
* **Trade-off, stated plainly.** v2's cap was added after a review found that a flaky six-episode batch could take 18
  retries and 45 declared minutes without ever showing "needs operator". Under v3 that same batch again takes 18 retries,
  shown in `test_under_v3_the_flaky_batch_that_stopped_v2_at_six_keeps_retrying`. "Needs operator" now appears after
  either:
  * 3 retries in one wait, still about 7.5 declared minutes; or
  * 24 retries in the campaign, about 60 declared minutes of waiting in all.
  Each retry is telemetry only: nothing is charged and nothing is re-run. v2f's 10 waits each cleared on their first
  retry.

## 5. Limits and risks (for review)

1. **Per target, not per recipe.** A fault on a refused target is refused even inside a recipe where another fault (for
   example a delayed upgrade) would make the status read fire. In native-v2b the only refused target is the orders
   status read, so the Explorer can no longer test status-read failures at all under this plan. That narrows the
   challenge and discovery. The narrowing is the same for every candidate.
2. **A refused pick can hide a violation.** A candidate violation counts even in an untriggered pair
   (`observed_candidate_violations`). A seldom-firing pick is effectively a healthy run, and it could in principle
   expose a candidate mistake. In v2d and v2f all such pairs had 0 failed checks.
3. **Discovery under v3-history.** Each re-plan costs the last discovery slot, because the declared requests are not
   raised. Under v4, the replay slots leave that many spare requests.
4. **Fewer than 3 verified episodes is allowed.** A target the history barely covers is never refused. Examples are F1
   on `send_confirmation`, or F4 on `get_order` (1 episode).
5. **Frozen at plan time.** Picks refused during this campaign never enter the table. A later plan's history includes
   this campaign's discovery episodes only if they ran and were verified; refused picks run nothing.
6. **Not reviewed.** No $0 review has read this build yet.

## 6. Checks ($0, offline)

* **Backend tests.**
  * `tests/lab/test_history_fireability.py`: 22 tests, 3 of them on the saved-store copy.
  * `tests/lab/test_evidence_retry_v3.py`: 5 tests.
  * Updated for the intended new-plan behaviour: `test_discovery_v3_flow.py` (new v3-history requests carry the rule's
    keys) and `test_evidence_wait.py` (new plans declare v3; the flaky-batch test now runs a v2 plan).
* **Frontend.** `tests/history-fireability.test.tsx`: 6 tests.
* **Differential** (`builder/history_differential.py`). The refactored history equals the backup's on every saved store:
  35/35 computations. All 6 saved history plans verify with both versions.
* **Real API responses** (`builder/api_contract_check.py`). Run options, four plans, search attempts, experiments and the
  recording all pass the dashboard validators. A tampered plan is rejected.
* **Negative controls** (`builder/mutation_checks.py`). 26/26 mutations caught, every file restored. The first run missed
  one frontend mutation because the test case was also rejected by a second check. A status-only case was added, and the
  log of that first run is kept (`mutation-checks-first-run.log`).
* **Full suite.** The final `scripts/test.sh` is `builder/full-test-sh.log`.

## 7. Next

A $0 integrity and product review, then the fixer; commit (owner's OK); register every agent again; then a declared
live Learn run (native adapter v2, v4 history replay, `native-v2b` store). Its read-out must be descriptive:
* did the challenge Explorer re-plan away from the status read;
* did a challenge reach 4 complete schedules;
* how many automatic evidence retries were used.
