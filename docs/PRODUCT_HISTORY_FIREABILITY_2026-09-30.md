# History fireability and evidence retry v3 (September 30, 2026)

**Status: built offline by the builder, reviewed by two $0 reviews, fixed by the fixer; all $0 and offline. Not yet
committed, not run live.** Runtime `49958e716f0b08aacb9db5d6ddf99620451f949a901aa35cca979918c1df6b6e` (algorithm
`7a56afed…`), built on `95042e4d…` (the working tree = `backup/part2-2026-09-22` at `432e54b`). The builder's unreviewed
runtime `07b8ccc4…` is superseded. Evidence: `artifacts/product-fireability-2026-09-30/` (`builder/`, `review-integrity/`,
`review-product/`, `fixer/`).

**Changed after review (section 8).** Both reviews found that the builder's rule refused a pick if **any** of its faults
was on a refused target. That also refused a status-read failure *during a pending upgrade*, which fires in both arms, and
in native-v2b the refused status read is the very step every generated guardrail adds. The fixer changed the rule: a pick
is refused only when **every** one of its faults is on a refused target (the v2d/v2f lone status-read pick). This
departs from the task's wording ("any of its primitives"); it was signed off on 2026-09-30 by Claude as PM (decision authority delegated by the owner), with the residual bias stated in section 5: a lone status-read fault can no longer be a challenge schedule, while a status-read failure combined with a fireable fault (for example during a pending upgrade) still runs.

Two declared rules, both frozen only into **new** Learn plans. Every plan saved before them keeps its bytes and its behaviour.

| rule | plan field | frozen into | in one line |
|---|---|---|---|
| `faultlab-explorer-selection/v3-history-fireability` | `explorer_selection` | new Learn plans with discovery `v3-history` or `v4-history-replay` | a discovery or challenge pick whose **every** fault is on a target that seldom fired in this agent's frozen history is refused before any episode, with one re-plan; a pick with a fault on any other target runs |
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
* **When a pick is refused.** Only if **every one** of its faults targets a row marked `REFUSED` (declared in the plan as
  `pick_refused_when: every_fault_on_a_refused_target`). No episode runs. *(The builder's version refused a pick if any
  fault did; the fixer changed it after both reviews, section 8.)*
* **When a pick with a REFUSED target runs.** If at least one of its faults is on a target that is not REFUSED (in the
  table or not), the pick runs exactly as before. The history cannot say whether that other fault makes the REFUSED target
  reached: in native-v2b the starting-policy agent read the orders status in 19 of 19 discovery episodes with a pending
  upgrade (F2 delay on `update_order`; integrity review, `review-integrity/status-read-exposure.json`). Such a pick's check lists the REFUSED target in `targets` and says so in `reason`;
  its pairs still count only if every fault fires in both arms.
* **What the refusal records.** It is saved on the selection record, in the field `fireability`, together with the table
  rows. A refused discovery pick's `search_decision` is `SKIPPED_UNFIREABLE`, with reason `HISTORY_FIRED_SHARE_BELOW_HALF`.
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
  this campaign's (or this challenge's) refused picks, and a `note` saying that the rule takes precedence over the
  statements in the Explorer's instructions that every valid pick runs or every valid schedule is tested (review finding
  F2). A challenge re-plan also gets `slot_request`, `replan_of` and `slot_feedback`, the same keys discovery v2 re-plans
  use; its instruction says a REFUSED target may appear beside a fault on another target, but only where that other fault
  makes the agent reach it. System prompts are unchanged, so older plans' requests stay byte-identical.

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
new v3-history plan freezes the same rows; its record cutoff and table hash differ, because it is saved at a different
store row. *(Wording corrected by the fixer, review finding F5.)* The fixer's rerun of this check
(`fixer/saved-store-check-after-fix.json`) gives the same rows; the table hash is now `ee7cfed0…` (was `8e791c77…`)
because the table's `meaning` text changed with the rule.

**Reconciling with the task statement.** Counted over *every* stored completed episode, the same target fired in:
* 2 of 14 policy-v0 episodes (5 discovery, 9 challenge incumbent);
* 1 of 9 candidate challenge episodes.
The rule never reads those; the frozen history holds only 4 of them. The fifth discovery episode is v2f's Explorer pick,
whose evidence was never verified.

**Every Explorer pick saved in the store**, checked against the new table:
* challenge: 11 picks, **3 refused** (v2d 1, v2f 2), each the lone status-read pick;
* discovery: 15 picks, **7 refused** (v2c 3, v2e 3, v2f 1), each a lone status-read pick;
* every other pick is allowed, including v2f's F1/F2/F3 on orders and F1/F4 on `send_confirmation`.
* Under the fixer's rule the counts are the same, because no saved pick mixes the status read with another target (the
  saved-store test now asserts both the exact counts and that no saved pick is mixed).

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
  Each retry is telemetry only: nothing is charged and nothing is re-run. *(Corrected by the fixer, review finding F5;
  the builder wrote that v2f's 10 waits each cleared on their first retry.)* In the saved store, v2f had 10 evidence
  waits. The first 6 each used one automatic retry and then resolved as verified; that used the campaign cap of 6. The
  next 3 each showed "needs operator" (cap reached) and resolved after one manual retry. The 10th had also reached the
  cap and ended STOPPED when the PM stopped the campaign.

## 5. Limits and risks (for review)

1. **The table is per target; the refusal is per pick (changed by the fixer).** The builder's rule refused a fault on a
   refused target even beside a delayed upgrade that makes the status read fire, so under a new plan no challenge could
   fault the orders status read at all. Now only a pick made entirely of faults on refused targets is refused. Every
   target can still be tested, by pairing it with a fault on another target.
2. **The rule is the same for every candidate, but it is not neutral.** *(Stated more plainly after review finding
   LOW-1.)* In native-v2b the one refused target is the orders `get_operation_status` read. That is exactly the call every
   generated guardrail adds: all 4 saved candidate policies have `read_current_operation` steps, and the policy
   interpreter maps that step to this read. Repairs add calls where the starting policy seldom reached, which is where
   rows are refused.
3. **A refused pick can hide a violation.** A candidate violation counts even in an untriggered pair
   (`observed_candidate_violations`). A lone pick on a refused target is effectively a healthy run for the starting
   policy, but a candidate that newly calls that target on every run could fail there. Such a mistake is tested only if
   the Explorer pairs the refused target with a fault on another target. In v2d and v2f all refused-type pairs had 0
   failed checks, and none of the current guardrails reads the status on a healthy upgrade.
4. **A PASSED_OBSERVED challenge may not have tested the guardrail's own status step.** The rule no longer prevents it,
   but nothing makes the Explorer choose a pending-upgrade status failure either. A read-out must say whether any
   challenge schedule faulted the orders status read before describing a pass as covering that step.
5. **Discovery under v3-history.** Each re-plan costs the last discovery slot, because the declared requests are not
   raised. Under v4, the replay slots leave that many spare requests.
6. **Fewer than 3 verified episodes is allowed.** A target the history barely covers is never refused. Examples are F1
   on `send_confirmation`, or F4 on `get_order` (1 episode).
7. **A refused row changes slowly.** *(Added after review finding LOW-3.)* The table is frozen at plan time. A later
   plan's history includes this campaign's discovery episodes only if they ran and were verified. A lone pick on a
   refused target never runs under a plan with this rule, and baseline studies use fixed development cases that never
   schedule the status read. So a refused row changes only through discovery picks that pair the refused target with
   another fault (they run under the fixer's rule and can enter a later history), or through a plan without the rule.
8. **Mixed picks can still end a challenge INCONCLUSIVE.** A pick that pairs a refused target with a fault that does not
   make it reached (for example a notification failure beside the status read) is untriggered, as before the rule. That
   is not a weakening; it is the old behaviour for that pick.

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
* **Fixer.** The fixer's tests, mutation checks and final `scripts/test.sh` (`fixer/full-test-sh.log`) are in section 8.

## 7. Next

The fixer's rule change was signed off on 2026-09-30 by Claude as PM (decision authority delegated by the owner), with the residual bias stated in section 5: a lone status-read fault can no longer be a challenge schedule, while a status-read failure combined with a fireable fault (for example during a pending upgrade) still runs; it is committed to the local backup branch (no push); register every agent again; then a
declared live Learn run (native adapter v2, v4 history replay, `native-v2b` store). Its read-out must be descriptive:
* did the challenge Explorer re-plan away from the status read;
* did a challenge reach 4 complete schedules;
* how many automatic evidence retries were used;
* the refused targets, and every refused pick with its recipe (discovery and challenge);
* whether any challenge schedule faulted the orders status read (for example beside a pending upgrade). If none did, a
  PASSED_OBSERVED challenge must not be described as having tested the guardrail's status step.

## 8. Review findings and the fixer's changes (September 30, $0, offline)

Two $0 reviews read the builder's build: an integrity review (`review-integrity/`) and a product review
(`review-product/`). Both found no leak, no gate change and no correctness bug in what was built. Both found the same
design problem (integrity MEDIUM-1, product F1). The fixer's evidence is in `fixer/`.

**The decision on the rule: fixed, not withdrawn.** The task said to withdraw the rule for new plans if it weakens the
challenge in a way that cannot be fixed cleanly. The weakening came from one choice: refusing a pick if *any* fault is on
a refused target. With "every fault" instead:
* the table, its basis (the frozen starting-policy history only) and its thresholds are unchanged;
* the rule is still candidate-independent: no candidate can change what is refused;
* no target becomes untestable: a refused target can always run beside a fault on another target;
* the integrity review's own demo, rerun on the fixed code (`fixer/demo-rerun-after-fix.log`), now gives
  COUNTEREXAMPLE_FOUND (C4) for the pending-upgrade status failure with the rule, exactly as without it; the lone
  status-read pick is still refused and the challenge then completes (PASSED_OBSERVED), which is the intended effect;
* every saved pick in native-v2b gets the same decision as under the builder's rule (3 of 11 challenge picks and 7 of 15
  discovery picks refused, all lone status reads).

What remains, stated in section 5: a lone pick on a refused target never runs, so a mistake only that pick could show is
tested only if the Explorer pairs the target with another fault. **This departs from the task's wording ("any of its
primitives"); the owner should confirm it before commit.**

| id | outcome | change | test |
|---|---|---|---|
| MEDIUM-1 (integrity) | FIXED | `fireability.decide` refuses a pick only when every distinct target is REFUSED; the declaration and saved plan state `pick_refused_when: every_fault_on_a_refused_target`; RULE, MEANING and the re-plan instruction say so; an allowed pick beside a REFUSED target records it with a reason | `test_history_fireability_review_fixes.py`: `test_a_pick_is_refused_only_when_every_fault_targets_a_refused_row`, `test_the_rule_no_longer_hides_a_counterexample_on_the_guardrails_status_read`, `test_a_discovery_pick_beside_a_pending_upgrade_runs_and_a_lone_one_is_still_refused`, `test_saved_plans_declare_the_every_fault_rule_and_the_model_refuses_another`; saved-store test now asserts exact counts and that no saved pick is mixed |
| F1 (product) | FIXED | the same change (the product review's option (a)); the challenge panel now names the targets refused on their own and says a pass tested one of them failing only if a pick paired it | the tests above; frontend `history-fireability-fixes.test.tsx` |
| LOW-1 | FIXED (docs) | section 5 items 2-4, CURRENT_STATUS, the user guide and RULE text now say the refused target is the step every native-v2b guardrail adds, and that the rule is not neutral | none (text) |
| LOW-2 | FIXED | tests for the ids-hash binding (R4), two challenges in one Session (R15), mixed picks (R17, now the rule) and a missing fault execution (R16, near-equivalent, pinned anyway); the misnamed test is renamed and a new test goes through `prepare_run_plan` after fired candidate and challenge episodes | `test_compute_table_refuses_a_history_whose_episodes_are_not_the_stores`, `test_two_challenges_in_one_session_never_share_refusals_or_a_pending_replan`, `test_a_fault_without_a_recorded_execution_never_counts_as_fired`, `test_a_plan_saved_after_fired_candidate_and_challenge_episodes_freezes_the_same_table` |
| LOW-3 | FIXED (docs) | section 5 item 7: how a refused row can and cannot change | none (text) |
| F2 (product) | FIXED | the saved plan and setup preview say "one re-plan per pick refused by history fireability" instead of "no re-plans", and qualify the v1 dispatch text; each Explorer request under the rule carries a `note` that the rule takes precedence over "every valid pick runs" (system prompts unchanged) | frontend `history-fireability-fixes.test.tsx`; backend `test_the_request_says_the_rule_qualifies_every_valid_pick_runs` |
| F3 (product) | FIXED | `campaign_decisions` reads only this campaign's selections (SQLite extracts three fields, then only matching rows are parsed), its challenges (via `challenge_campaigns`) and its unrequested slots; the experiments endpoint validates a plan with no counterexample only when its saved record names the rule | `test_the_experiments_poll_reads_only_this_campaigns_selections_challenges_and_slots`, `test_the_experiments_poll_does_not_validate_the_plan_of_a_campaign_without_the_rule` |
| F4 (product) | FIXED | no "Refused: Refused"; the REFUSED row is highlighted; the plan names `faultlab-evidence-retry/v3` or `v2` beside the cap | frontend `history-fireability-fixes.test.tsx`; `evidence-wait.test.tsx` pinned text updated |
| F5 (product) | FIXED (docs) | "the same rows" (cutoff and hash differ); the v2f evidence waits stated exactly | none (text) |

**Failing, then passing.** Before any source edit, 7 of the 10 new backend tests then written failed on the builder's
code (`fixer/tests-before-fix.log`); the other 3 are test-gap tests, which pass there by design because they pin code that
was already right, and an 11th of that kind (R16) was added afterwards. The 6 new frontend tests failed 6 of 6
(`fixer/frontend-tests-before-fix.log`). After the fix, 18 of 18 negative-control
mutations in a scratch tree outside the Desktop were caught, each putting back one piece of the builder's behaviour or one
of the reviewers' surviving mutations, with every file restored (`fixer/mutation-checks.log`).

**Unchanged by the fixer.** The table's rows and basis, the evidence retry rule, `explorer.py`, the reference Actor
source hash `7f78de28…`, gates, the referee, the simulator, `challenge.py`, evaluation, promotion, reproduction,
diagnosis, service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer `19de811c…`, native v2.1 prompt
`fff397c9…` and the reference Actor prompt `12eabe7f…`. `gate_freeze.py`: 20/20 files and 30/30 functions identical to
the backup (`fixer/gate_freeze/compare.txt`). The saved native-v2b store's sha256 is unchanged (`fixer/saved-store-sha256-*`).
