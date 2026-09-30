_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FaultLab fixer report: the two Learn-loop limits after live run v2d (September 30, 2026)

Status: all 10 review findings verified and fixed offline at $0. Not committed, not run live. No provider, model, W&B, Weave or network call was made. Every fixer script ran under the socket and .env guard, and every guard line reads "refused outbound connections: 0". The backend suite ran under conftest's network ban.

Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-loop-limits-2026-09-30/fixer/
Design note (rewritten): /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/docs/PRODUCT_LOOP_LIMITS_2026-09-30.md

The main outcome in one line: rule 1 (Mechanic request size) is fixed and stays in every new Learn plan; rule 2 (challenge picks, v2-candidate-reach) is withdrawn, because both reviews were right that it can hide a counterexample. The PM still has to confirm what to do with rule 2 (section 4).

==================================================
1. STARTING STATE (checked)
==================================================
- HEAD is main at cbbf957 and backup/part2-2026-09-22 is at 3b31b58. .git/index mtime is still Sep 27 15:18:04, at the start and at the end. I ran one `git status --porcelain` at the start; it did not touch the index.
- Tree compared with the backup: 16 changed and 10 added files, the same list the integrity review ended with. All 26 files had the sha256 the product review recorded at its end, so nothing changed between the reviews and my start.
- All 8 saved stores had the same sha256 as at the end of the integrity review.

==================================================
2. FINDINGS TABLE
==================================================
Both reviews used some of the same IDs, so they are prefixed here: I- is integrity, P- is product.

| Finding | Verdict | Change | Test (failed before the fix, passes after) |
|---|---|---|---|
| I-HIGH-1: rule 2 can turn COUNTEREXAMPLE_FOUND into PASSED_OBSERVED | FIXED by withdrawal; choice of a new basis DEFERRED to the PM | run_plans.py: new Learn plans no longer freeze challenge_selection, and run options no longer offer it. New withdrawn_rule_problem() is checked in validate_run_plan, which both creation and Start run, so a plan that declares the rule cannot be created or started. It is deliberately NOT in _bindings, so such a saved plan still reads and displays. The rule's code is kept, unused. | test_under_a_new_learn_plan_a_pick_refusal_cannot_turn_a_counterexample_into_a_pass (the integrity scenario, run with the rule from a real new Learn plan. Before the fix: PASSED_OBSERVED. After: COUNTEREXAMPLE_FOUND ['C4']); test_a_plan_declaring_the_withdrawn_challenge_rule_cannot_be_created_or_started; test_run_options_and_every_new_learn_plan_declare_the_mechanic_rule_only_and_baseline_plans_neither |
| P-HIGH-1: rule 2 refuses far too much (for v2d only 2 of 5 targets are allowed) | FIXED by the same withdrawal; the measured scope is now in the docs | Same as I-HIGH-1. The docs now give the measured scope: 3 of 5 tool/service pairs refused for v2d's candidate. | Same tests |
| I-MEDIUM-2: the docs give the wrong premise for pick 3 and the wrong narrowing | FIXED | Corrected in the note (section 3), CURRENT_STATUS (the newest-build entry, plus a marked correction in the v2d table row), user-guide.md, the loop_limits.py docstring and both docstrings of the challenge-reach test. The v2d write-up gets a correction note; the original text is kept as first written. | Docs only. The claims were checked on a read-only store copy: fixer/verify-v2d-picks.json |
| P-MED-1: wrong cause, the both-arms reason missing, option (b) wrong | FIXED | Same docs corrections. The both-arms reason is added to the rule text (CHALLENGE_REACH_RULE) and to prompts/challenger_candidate_reach_v2.md. Option (b) is restated: it would not have fixed v2d. | Same as I-MEDIUM-2 |
| I-LOW-1: an episode with a VIOLATION outcome but no failed checks could be omitted | FIXED | _row_failed also counts outcome == 'VIOLATION'. The rule text, the always_kept list and the statement say so. | test_an_episode_whose_trial_outcome_is_violation_is_always_kept |
| I-LOW-2: the stage-2 group ignores policy (and purpose) | FIXED | _trial_facts adds policy_hash (from the trial) and experiment_purpose (from the episode record). Both the stage-1 key and the stage-2 key include them, and the rule text says "recipe, arm, policy, purpose and outcome". | test_stage_two_never_lets_one_policy_or_purpose_stand_for_another |
| I-LOW-3: NO_CHANGE hides a search cut short; FORMAT_REPAIR is assumed | FIXED | (a) The NO_CHANGE reason gets "; N candidate or diagnosis search(es) ended before it finished under faultlab-mechanic-context/v2-bounded (… record IDs)", at most 3 IDs so it stays under the 600-character limit. This applies only when a SEARCH_ENDED record exists; otherwise the reason is exactly today's text. (b) New record_refusal() replaces record_repair_refusal. It records FORMAT_REPAIR only when this request's first-turn answer is actually saved (found above a record-row cutoff taken before the request), and it links that answer (first_turn_output_ref). Otherwise it records BEFORE_SEND with "Nothing was sent", and the candidate request is not counted. The same applies to the diagnosis wrapper. | test_a_search_cut_short_by_the_size_rule_is_named_in_the_campaigns_final_reason (also checks that a finished campaign keeps today's exact reason); test_a_first_turn_the_mechanic_itself_refuses_is_recorded_as_never_sent[mechanic_proposal and mechanic_diagnosis] |
| P-LOW-1: the stage-2 wording implies omitted rows equal the example | FIXED | The field is renamed represented_by → group_example. The stage-2 text, the rule text, the statement and the block legend now say the omitted rows can differ from their group_example ("same recipe, arm, policy, purpose and outcome only"). same_as is kept for stage 1, where the rows really are identical. | test_stage_two_names_a_group_example_and_says_the_omitted_rows_can_differ_from_it; changed: test_an_outcome_that_differs_inside_a_recipe_keeps_its_own_full_example (the key name only) |
| P-LOW-2: dashboard texts | FIXED | loopLimits.ts / LoopLimits.tsx: FORMAT_REPAIR now reads "first turn sent (its answer is saved); its format-repair turn was not sent", with the badge "Search ended, repair turn not sent". The "in full" line shows only for a request that was actually sent. A refusal is stated once ("Explorer request 3: Refused before any pair ran: …"). Badges are capitalised: Selected / Invalid output / Not checked. The setup form lists only the rules offered ("this rule:"), and an undeclared challenge rule reads "Not declared: every valid challenge pick runs its pairs, as before." It no longer claims the plan was "saved before" the rule. | frontend/tests/loop-limits.test.tsx: 3 tests updated, all failed before the fix; browser test updated to what now ships |
| P-LOW-3: a refused format-repair turn leaves no candidate record | FIXED | learning.py: when the first turn was sent, the loop saves a REJECTED campaign_proposals row (reason FORMAT_REPAIR_OVER_LIMIT, raw_outputs = the first answer, mechanic_context_ref) and a rejected policy record via policies.rejected_raw, exactly as the invalid-answer path does. | test_a_refused_format_repair_turn_leaves_a_rejected_proposal_in_the_candidate_history |

Verified, not just accepted:
- I rebuilt v2d's challenge from a read-only copy of the store (fixer/verify-v2d-picks.json). Pick 3 was F4 on the orders status (attempt 1) and no other fault. It fired in 1 of 3 incumbent episodes and 0 of 3 candidate episodes, and the candidate policy made no reads in pick 3. The candidate policy reads the status only when the upgrade is uncertain or a receipt is missing. Under pick 2, the candidate's own agent read the orders status 3-4 times per episode.
- For v2d's candidate, the build's rule allowed only get_order and update_order. That confirms both HIGH findings and both MEDIUM findings.

==================================================
3. WHAT CHANGED FOR v2d (rule 1)
==================================================
- The refused request still rebuilds to exactly 33,223 tokens.
- With the corrected wording, the stages give: stage 1 = 33,611; stage 2 = 28,056 (56 over the 28,000 target); stage 3 = 21,101, which is sent.
- The builder's wording fitted at stage 2 by only 10 tokens. The clearer wording the reviews asked for adds 66 tokens at stage 2: 25 in the statement, 28 in the two block legends and 13 in the renamed field.
- So v2d now goes out at stage 3:
  - all 10 failing development episodes are kept in full;
  - the 6 clean development episodes and all 18 clean challenge episodes are named with their outcomes;
  - every trial_outcomes group is unchanged.
- Both stage results follow the declared rule. Whether stage 3 helps or hurts the next candidate is unmeasured.
- The saved-store test (test_the_refused_v2d_request_rebuilds_exactly_…) now expects [33611, 28056, 21101] and 10 kept episodes; before, it expected [33605, 27990] and 12. It still checks exact values. Evidence: fixer/rebuild-v2d-request.json and the two rebuilt-v2d-request-*.json files.

==================================================
4. RULE 2: WHY WITHDRAWN, AND THE PM DECISION
==================================================
- The brief says neither fix may relax a gate. As built, rule 2 relaxes the challenge:
  - it refuses picks based on what the candidate's own agent did in source validation;
  - so it removes the schedules that exercise paths that candidate never exercised;
  - with the real, unchanged challenge.py, the same Explorer answers give COUNTEREXAMPLE_FOUND without it and PASSED_OBSERVED with it.
- Withdrawing it restores today's challenge behaviour exactly.
- I did not invent a replacement rule; that is the PM's call. To inform it, I checked the existing candidate-independent tools (fixer/impossible-rules-v2d.json):
  - reachability.py's IMPOSSIBLE rules (S1-S4) flag none of v2d's three picks, pick 3 included;
  - its FORCED caller model covers only the reference Actor under policy-v0. It refuses a candidate policy (POLICY_RULES_UNSUPPORTED) and a native agent (NATIVE_AGENT_UNSUPPORTED).
  - So nothing in the product today gives a candidate-independent check that would have caught pick 3.
- The note restates options (a)-(f) with what each would do for v2d:
  - (b) would not have refused pick 3;
  - (c) refuses the same 3 targets as the build;
  - (e) is the product review's untested write-tool idea.
- My recommendation: keep rule 2 dropped for the next live run (option d in effect). An INCONCLUSIVE challenge is safe; the ERROR was the real blocker, and rule 1 fixes it.
- What stays in the product:
  - the rule's code (explorer.py hooks, loop_limits.decide, the prompt section);
  - the display of a plan that declares it (API challenge_reach list, recording, challenge panel).
  All of it is unreachable for new plans.

==================================================
5. CHECKS (all $0)
==================================================
- Failing-then-passing tests (fixer/mutation-checks.log):
  - Part 1 (RED, on the builder's code): 13 new or changed backend tests failed, each for the reason in its finding, and 3 frontend tests failed.
  - Part 2 (GREEN): 39 of 39 backend loop-limits tests pass (30 before), and 5 of 5 frontend.
- Negative controls (fixer/mutation_checks.py, part 3 of the log):
  - 17 of 17 mutations were caught; each one undoes a single fix and runs only the named tests;
  - every file was restored and checked by sha256;
  - the unmutated run passed.
- API contract (fixer/api-contract-check.log): the dashboard's own validators accept the real API responses:
  - run options without challenge_selection;
  - a new plan with the Mechanic rule only;
  - an older plan;
  - a plan that declares the withdrawn rule (Start refuses it, and its challenge_reach list still validates);
  - all four request-size record kinds: COMPACTED, BEFORE_SEND (unfit), FORMAT_REPAIR, and BEFORE_SEND (first turn refused).
- Gate freeze (fixer/gate_freeze/compare.txt):
  - functions 30/30 and files 20/20 identical to the backup-tree snapshot;
  - only algorithm_hash, runtime_hash, source_hash and tree_lab changed, the same four as in the builder's run;
  - I changed no protected file: referee, simulator, contracts, challenge.py, evaluation.py, promotion.py, mechanic.py, diagnosis.py, reachability.py, the discovery code, actor.py and prompts/actor.md are all untouched.
- scripts/test.sh, the final run after the last edit (fixer/full-test-sh.log, 09:25-09:44 UTC), all four stages PASSED, exit 0:

| Stage | Result |
|---|---|
| Backend | 2,949 passed, 180 skipped, 0 failed, 2 known warnings (starlette BlockingPortal alias and the os.fork note). That is the builder's 2,940 plus 9; the skip count is unchanged, so the saved-store v2d test ran. |
| Frontend unit | 353 passed |
| Build | passed (chunk-size advisory only) |
| Browser | 19 passed, 1 opt-in skip |

  - No code, test or doc file changed during the run (fixer/source-sha256-after-suite-check.txt: 26 of 26 OK).
- Honest note on the test runs: I ran scripts/test.sh twice. The first run (fixer/pass1-full-test-sh.log) gave the same counts. After it, I found that CURRENT_STATUS named an interim runtime hash (c67dfa08): two comment and docstring edits in learning.py and loop_limits.py had come after my interim identity. I corrected the docs and re-ran the whole suite, so the final run comes after the last edit.
- Identity (fixer/identity-final.json, fixer/identity-compare.txt; the same after the final run):
  - Changed:
    - runtime f058c03c53b6442cd1c3d308d46007af8b755af0478595d57b964261aa17677a;
    - algorithm a08a8d61…;
    - reference Actor source (a tree hash over backend/app/agents) fb5e1894…;
    - mechanic_context declaration 11bf9e32…;
    - challenge_selection declaration 802e3954… (withdrawn);
    - the example configuration hashes.
    The builder's runtime 4d0d7914 is superseded.
  - Unchanged: simulator service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, capability 8e8e04af, native v1 adapter 6f303264 and prompt 22515428, native v2.1 adapter dfd41b33 and prompt fff397c9, reference Actor prompt 12eabe7f, reference adapter 0cd810b7, both transport-retry declarations.
  - Register every agent again before a live run.
- Constraints kept:
  - The 8 saved stores are unchanged (fixer/saved-stores-sha256-start.txt equals -end.txt). They were opened only with mode=ro&immutable=1 and copied to /Users/shree/FaultLab_Scratch/fixer-loop-limits, which is now deleted.
  - I did not open .env, checks.py (hashed only by gate_freeze), artifacts/heldout2 or the protected audit files.
  - I used only read-only git commands; HEAD, the backup ref and the index mtime are unchanged. Nothing was committed.

==================================================
6. FILES CHANGED BY THE FIXER
==================================================
- Code: backend/app/lab/loop_limits.py, backend/app/lab/learning.py, backend/app/lab/run_plans.py, backend/app/agents/prompts/challenger_candidate_reach_v2.md, frontend/src/loopLimits.ts, frontend/src/components/LoopLimits.tsx, frontend/src/components/RunSetup.tsx.
- Tests: backend/tests/lab/test_loop_limits_mechanic_context.py, test_loop_limits_challenge_reach.py and test_loop_limits_plans.py; frontend/tests/loop-limits.test.tsx and loop-limits.browser.ts.
- Docs: docs/PRODUCT_LOOP_LIMITS_2026-09-30.md, CURRENT_STATUS.md (the newest build marked "Not yet committed"), docs/user-guide.md, docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md (a correction note; the original text is kept).
- Tests changed rather than added, none of them weakened:
  - the v2d numbers (see section 3);
  - the represented_by → group_example key;
  - the plan tests: new plans no longer carry challenge_selection, so the dashboard test now declares the rule explicitly through a bypass fixture, and the Start-refusal case expects the "withdrawn" message;
  - the frontend setup-form, saved-plan and panel texts.

==================================================
7. OPEN POINTS
==================================================
- PM decision on rule 2: keep it dropped (recommended), or commission a new design that does not depend on the candidate.
- Design choices for review:
  - An unsent request still does not use a candidate request (the builder's choice, kept, and now also applied when the Mechanic itself refuses a first turn).
  - A refused format-repair turn creates a rejected policy record, as an invalid answer does.
- Unmeasured:
  - whether the Mechanic proposes better candidates from a compacted request (v2d is now at stage 3);
  - with rule 2 gone, an unfired pick still ends a challenge INCONCLUSIVE, as in v2d. That is safe but can stop a good candidate.
- Next: the PM's decision, a commit (with the owner's OK), register every agent again, then a declared live Learn run.
