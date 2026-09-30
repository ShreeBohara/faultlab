_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

BUILDER REPORT: history fireability for Explorer picks, and evidence retry v3. September 30, 2026. $0 and offline. Built only: not reviewed, not committed, not run live.

I did not write a REPORT.md, because my instructions forbid report .md files. This text is the builder report.

RESULT
- Both rules are built. They are frozen into NEW Learn plans only.
- The one final scripts/test.sh passed every stage (log: artifacts/product-fireability-2026-09-30/builder/full-test-sh.log, 13:56:37Z to 14:15:55Z):
  - backend: 3,027 passed, 180 skipped, 0 failed, with the 2 known warnings;
  - frontend: 362 passed;
  - build: passed;
  - browser: 19 passed, 1 opt-in skip.
- The previous build's final run had 3,000 passed and 180 skipped. The 27 extra tests are exactly my 22 + 5 new backend tests.
- The 589 source, test and doc files were hashed before and after the suite and did not change. The only difference was the browser stage's own output file under frontend/tests/.results.

WHAT WAS BUILT

1. faultlab-explorer-selection/v3-history-fireability (plan field explorer_selection)
- Where it applies: new Learn plans with discovery v3-history or v4-history-replay.
- The table (computed when the plan is saved):
  - It counts, for each (fault kind, service, tool), how many verified history episodes scheduled a fault there, and in how many of them every such fault fired. Firing is read from verdict.fault_executions, matched by position.
  - It uses exactly the frozen history's own episodes. I split the history's eligibility loop into one generator, agent_history._in_scope, which both the history and the table read.
  - The table's episode ids must hash to the history's episode_ids_hash, or the table is refused.
  - It never reads candidate, challenge, source-validation, reproduction, reduction or intervention episodes, B1 controls, other agents, other policies, replay slots or protected data.
  - It is frozen into the plan with its hash. It is recomputed at the history's cutoff at Start, before the first Explorer request, and by the "Check against the store now" button. Any difference refuses with AGENT_HISTORY_CHANGED.
- The rule:
  - Before any episode runs, a discovery pick or a challenge pick is refused if any of its faults targets a row with at least 3 verified episodes and a fired share below 1/2. The discovery pick includes the fixed fallback after an invalid answer.
  - The refusal is saved on the selection record (field fireability), with the table row. A refused discovery pick's search_decision is SKIPPED_UNFIREABLE, reason HISTORY_FIRED_SHARE_BELOW_HALF.
  - The Explorer gets one re-plan for that slot, told why. A refused re-plan gets no second one.
  - Targets with fewer than 3 verified episodes, and targets not in the table, are allowed.
  - Discovery's duplicate rule runs first and is unchanged.
- Budget, charged and bounded as today:
  - challenge: a re-plan is one of the challenge's existing 8 Explorer requests. challenge.py is unchanged.
  - discovery: a re-plan is one of the plan's declared 8 discovery Explorer requests. v4 replay slots use none.
- Under v3-history, a re-plan leaves the last discovery slot with no request. That slot is recorded (record kind explorer_selection_slots) and shown in the fault-search panel.
- What the Explorer sees: each discovery and challenge request states the rule and carries the table as information, under the context keys explorer_selection_protocol and history_fireability. A challenge re-plan also gets slot_request, replan_of and slot_feedback. System prompts are unchanged.
- Where it is shown:
  - the saved plan: the rule and the table;
  - the Learn setup form: only when v3-history or v4 is chosen;
  - the fault-search panel: each discovery pick's check, and any slot left with no request;
  - the Adversarial challenge panel: each challenge pick's check;
  - the APIs: search-attempts rows carry fireability, and experiments carries explorer_fireability only for plans that declare the rule;
  - the recording: explorer_selection_rule, plus fireability on each selection;
  - the docs.

2. faultlab-evidence-retry/v3 (plan field evidence_retry)
- The same per-wait rule: 3 automatic retries at 30, 120 and 300 s.
- The per-campaign cap is 24 instead of 6.
- Every new Learn plan freezes v3.
- A saved v2 plan still starts and keeps its cap of 6. EvidenceWait already reads the cap from the plan.
- Start accepts exactly the installed v2 and v3 declarations. v2's declaration hash is unchanged: 3d849893…. v1 is still refused.

DESIGN DECISIONS I MADE (please review)
- Scope: I applied rule 1 to v3-history and v4-history-replay only, as the task listed. v3-history-reachability does not get it, because its reachability pre-check already refuses picks that are not forced.
- I edited explorer.py rather than wrapping it. The refusal has to be decided before the immutable selection record is written; a wrapper would have left records saying SELECTED for picks that never ran. As a result, the reference Actor SOURCE hash changes, from fb5e1894… to 7f78de28…. The runtime changes anyway, so register every agent again before a live run.
- "Fired" for a target means every fault on that target fired in that episode. A recipe with two faults on one target counts once.

EXACT COUNTS, FROM A SCRATCH COPY OF /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3
Script: builder/saved_store_check.py, output builder/saved-store-check.json.
- I registered native adapter v2 again under this runtime; the agent identity is the same.
- A new v4 plan froze a history of 30 verified episodes: 18 from one baseline study and 12 from two Learn campaigns' discovery picks.
- Its table:

  | target | verified | fired | status |
  |---|---|---|---|
  | F1 update_order (orders) | 4 | 4 | ALLOWED |
  | F2 update_order (orders) | 10 | 10 | ALLOWED |
  | F3 get_order (orders) | 4 | 4 | ALLOWED |
  | F4 send_confirmation (notifications) | 4 | 4 | ALLOWED |
  | **F4 get_operation_status (orders)** | **4** | **0** | **REFUSED** |
  | F4 get_order (orders) | 1 | 1 | ALLOWED_FEWER_THAN_3 |

- The 4 episodes behind the refused row are discovery picks from v2c (077b8434, 2 episodes) and v2e (37e66b6c, 2 episodes), with failure_count 1 or 2. All 4 recorded target_not_reached.
- A new v3-history plan freezes the same table.
- How this matches the task's numbers. Over every stored completed episode (the rule reads none of these), the target fired in:
  - 2 of 14 policy-v0 episodes: 5 discovery and 9 challenge incumbent;
  - 1 of 9 candidate challenge episodes.
  That matches the task's figures. The fifth policy-v0 discovery episode is v2f's own pick, whose evidence was never verified, so the history excludes it.
- Every Explorer pick saved in the store, checked against the new table:
  - challenge: 3 of 11 refused (v2d 1, v2f 2);
  - discovery: 7 of 15 refused (v2c 3, v2e 3, v2f 1).
  Every refused pick is the lone status-read pick. Every other pick is allowed, including v2f's F1/F2/F3 on orders and F1/F4 on send_confirmation.
- The saved store's sha256 is identical before and after (saved-store-sha256-start/end.txt). It was read only through mode=ro&immutable=1. The scratch copies were under /Users/shree/FaultLab_Scratch and have been deleted.

TESTS (all offline)
backend/tests/lab/test_history_fireability.py, 22 tests:
- the table counts only eligible starting-policy history. Candidate, challenge, source-validation, reproduction, reduction, intervention, B1, other-agent, unverified, lab-error, single-case-baseline and replay episodes are all seeded with the target firing, and none of them change the table;
- the thresholds;
- two faults in one recipe;
- plan freezing (v3-history, v4), and no block in v1, v2, v3-history-reachability or baseline plans;
- Start refuses a changed rule, and refuses a table-only store change while the history still verifies;
- the plan models reject inconsistent tables;
- discovery through the real learning loop: refusal, one re-plan within 8 requests, and the last slot recorded as having no request;
- under v4, the replays leave room for re-plans;
- a refused re-plan gets no third request;
- duplicates are unchanged, and the invalid-answer fallback is checked;
- a plan saved before the rule behaves as today (no keys in requests or records);
- challenge: refusal plus re-plan inside the 8 requests; an 8-request bound with 0 episodes; other targets run the same as without the rule;
- candidate independence: the store is filled with fired candidate and challenge episodes, and no decision changes;
- API and recording, and campaigns without the rule keep their exact fields;
- 3 saved-store tests:
  - a new v4 plan's table, with the exact counts above, while all five saved plans still read byte for byte;
  - every saved pick checked;
  - the real loop on the copy: 2 replays, then the status pick is refused and its re-plan runs.

backend/tests/lab/test_evidence_retry_v3.py, 5 tests:
- new plans declare v3 with a cap of 24, and v2 is byte-identical;
- a v2 plan starts and keeps 6;
- the cap comes from the plan: 23 or 24 retries under v3, 5 or 6 under v2;
- the flaky six-episode batch that v2 stopped at 6 retries now clears all 6 waits with 18 retries.

Updated for the intended new-plan behaviour:
- test_discovery_v3_flow.py: new v3-history requests also carry the rule's keys. The pinned v1/v2 message digests still match.
- test_evidence_wait.py: new plans declare v3; the flaky-batch cap test now runs a v2 plan.

Frontend: frontend/tests/history-fireability.test.tsx, 6 tests covering the validators, the saved plan, the setup form, the fault-search panel, the challenge panel, and evidence retry v3/v2.

OTHER CHECKS ($0)
- Differential (builder/history_differential.py). The refactored agent history equals the backup's on all 11 saved stores: 35 of 35 computations. All 6 saved history plans verify with both the old and the new code.
- Real API responses (builder/api_contract_check.py). run-options, four plans, search-attempts, experiments and the recording all pass the dashboard's own validators. A negative control is rejected: a plan whose table is bound to another history.
- Negative-control mutations (builder/mutation_checks.py): 26 of 26 caught, every file restored with identical sha256. This includes mutations that make the table read candidate-policy episodes, or challenge and reproduction episodes.
  - The first run caught 24 of 25. It missed F2, a frontend row-status check, because my test case was also rejected by a second check.
  - I added a status-only case in both frontend and backend, plus mutation M22. The first log is kept as mutation-checks-first-run.log.
- Identity (builder/identity-compare.txt):
  - runtime: 95042e4d… → 07b8ccc430f7eb40ab2e42c568fcde466273484af73d87d093f631cc5b2e11c9;
  - algorithm: 4e5a8f90… → bc544604fce420a3e3da2c4c42409d8227d5cddcc21639ffe7392649ea49c9d9;
  - reference Actor source hash: fb5e1894… → 7f78de2861a1….
  These are the same after the suite (identity-final.json).
- Unchanged: service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…, native v1 adapter 6f303264…, native v2 adapter dfd41b33…, native v2.1 prompt fff397c9…, reference Actor prompt 12eabe7f….
- gate_freeze.py: 20 of 20 files and 30 of 30 functions identical. Only algorithm, runtime, source_hash and tree_lab changed.
- Nothing under backend/app/referee, the simulator, challenge.py, evaluation.py, promotion.py, diagnosis.py or prompts/actor.md changed.

LIMITS AND RISKS, stated for the reviewers
1. The table is per target, not per recipe. A fault on a refused target is refused even beside a delayed upgrade that would make the status read fire. In native-v2b this means status-read failures can no longer be tested at all under a new plan. That narrows the search, but the narrowing is the same for every candidate.
2. A candidate violation counts even in an untriggered pair. A refused, seldom-firing pick is effectively a healthy run, and in principle it could have exposed a candidate mistake. In v2d and v2f all such pairs had 0 failed checks.
3. Under v3-history, each discovery re-plan costs the last slot, because the declared number of requests was not raised.
4. v3's cap of 24 brings back the scenario v2's cap of 6 was added for: a flaky six-episode batch now takes 18 retries and about 45 declared minutes before it clears, and "needs operator" appears only after 24 retries in the campaign. Each wait still stops after 3.
5. One backend test, test_discovery_v3_baseline_history (a 36-episode baseline study with an in-process simulator), failed once during an earlier batch run of related tests and passed when run alone. It passed in the final suite. It touches no code I changed; I think it is timing-sensitive, but I have not proven that.
6. Nothing in this build has been reviewed.

HARD RULES
- No provider, model, W&B or network call. The guard refused 0 outbound connections.
- .env, credentials, checks.py, artifacts/heldout2 and the audit promotion/final-audit files were never opened.
- No git write: HEAD is still main at cbbf957, the backup is still at 432e54b, and git ran only with --no-optional-locks.
- CURRENT_STATUS has a new "Newest build" paragraph marked not yet reviewed, not yet committed, not run live.
- I also corrected a stale CURRENT_STATUS line: 95042e4d was committed locally as 47b8f69 and run live once (v2f), but the header still said "not yet committed, not run live".

Evidence is in /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-fireability-2026-09-30/builder/. The design note is /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/docs/PRODUCT_HISTORY_FIREABILITY_2026-09-30.md.

NEXT: two $0 reviews and a fixer; commit (owner's OK); register every agent again; then a declared live Learn run (native adapter v2, v4 history replay, native-v2b store) with a descriptive read-out:
- did the challenge Explorer re-plan away from the status read;
- did a challenge reach 4 complete schedules;
- how many automatic evidence retries were used.
