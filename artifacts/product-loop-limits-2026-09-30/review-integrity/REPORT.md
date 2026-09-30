_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FaultLab integrity review: the two Learn-loop limits (September 30, 2026)
Reviewer: integrity. Cost $0. Every check ran offline: no provider, model, W&B, Weave or network call. Every reviewer script ran under the builder's socket and .env guard and logged 0 refused connections. The backend suite ran under conftest's automatic network ban and its .env block.
Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-loop-limits-2026-09-30/review-integrity/
(The harness forbids .md report files, so the full report is here.)

VERDICT
- Fix 1, faultlab-mechanic-context/v2-bounded: passes the integrity check, with 3 LOW notes.
- Fix 2, faultlab-challenge-selection/v2-candidate-reach: fails.
  - It leaves challenge.py and every gate function untouched.
  - But which picks it refuses depends on the candidate's own behaviour under the source fault. That shrinks the adversary for exactly the candidates that do less under that fault.
  - In an offline replay using the real, unchanged challenge.py, the same Explorer answers gave COUNTEREXAMPLE_FOUND without the rule and PASSED_OBSERVED with it.
  - The brief said neither fix may relax any gate. In effect, this one relaxes the challenge.
- Recommendation: do not freeze fix 2 into new Learn plans as built. Let the PM choose a basis that does not depend on the candidate, or drop fix 2 (the builder's option d). Fix 1 can go ahead.

STARTING STATE (checked)
- HEAD is main at cbbf957; backup/part2-2026-09-22 is at 3b31b58. The git index was not touched (its mtime is still 2026-09-27).
- The tree compared with the backup has 16 changed and 10 added files, identical to the builder's end list. It was identical at the start and at the end of my review (tree-vs-backup-review-start.txt, tree-vs-backup-review-end.txt).
- All 24 code, test and frontend files match the sha256 values the builder recorded at the start of its suite. The only files that differ are CURRENT_STATUS.md and the loop-limits note. The builder edited both at 01:07 and 01:08 local time, after its suite and before my review began.

(1) COMPACTION: SOURCE AND FAILURES KEPT, DETERMINISTIC, STATED, NEVER OVER THE LIMIT
- Exact rebuild:
  - I rebuilt the refused v2d request on my own read-only scratch copy, using a copy of the builder's script. Output: rebuild-v2d-request-reviewer.json.
  - It counts 33,223 tokens, the refused size.
  - The compaction goes 33,223 -> 33,605 (stage 1) -> 27,990 (stage 2, sent). Forcing stage 3 gives 21,095.
  - Both the full and the compacted request files are byte-identical to the builder's.
- Adversarial checks (compaction-adversarial-checks.txt):
  - Three runs give byte-identical output.
  - In each block, the kept episodes and the named omitted episodes together cover every episode exactly once.
  - Kept rows render exactly like the originals.
  - Stage-1 same_as rows are truly identical apart from their per-episode evidence IDs.
  - Every represented_by episode has the same arm, outcome, triggered flag, scenario and policy as its representative.
  - An episode that fails only in its trial record (failed_checks) is still kept at stage 3.
  - All 10 failing episodes are kept, plus the source and its 3 reproductions.
  - Contradictions stay visible. For example, in v2d pick 3 the incumbent-arm episode where the fault fired and the one where it did not are both kept, because they fall in different groups.
- Stated in the request: the request carries a context_compaction statement, each compacted block carries compaction.omitted, the legend is amended, and every trial_outcomes group is unchanged.
- No path sends a request over the limit:
  - fit_request returns a request unchanged only when it is 32,000 tokens or less. A compacted request is 28,000 or less. Otherwise nothing is sent.
  - The count is the same as the Mechanic's own. I compared mechanic.py _generate with loop_limits.mechanic_request_bound: same system prompt, same canonical_json of context plus output_schema, same model resolution, and the same limit test (count > 32,000 is refused).
  - The Mechanic's own unchanged check (tokens.validate_model_input) still runs before each turn, including the format-repair turn, and before any ledger charge.
  - Explorer requests keep their own unchanged check.
- Tests: the 30 new backend tests pass. The full backend suite passes: 2,940 passed, 180 skipped, 0 failed, 2 known warnings (backend-suite-reviewer.log). I did not re-run the frontend or browser stages.

(2) ENDING A CANDIDATE SEARCH ON THE SIZE LIMIT
- It cannot produce a promotion. I read the control flow in learning.py: promotion happens only inside the candidate loop, after a challenge ends PASSED_OBSERVED and promotion_decision runs. On the size-limit path the loop is left with break (or continue, for diagnosis) before any proposal exists.
- An earlier INCOMPLETE candidate stays INCOMPLETE. Nothing is promoted afterwards, and the campaign falls through to the existing NO_CHANGE.
- It cannot hide a counterexample. Counterexamples and challenge_counterexamples are saved before the next Mechanic request. Compaction never omits a failing episode.
- LOW-3 below: the NO_CHANGE reason text does not mention that a search was cut short.

(3) THE CHALLENGE RE-PLAN LEAVES THE CHALLENGE RULES THEMSELVES UNCHANGED
- Unchanged, confirmed against the backup:
  - challenge.py is byte-identical to the backup (git diff --no-index is empty).
  - evaluation.py (paired_complete and observed_candidate_violations) and promotion.py are also byte-identical; gate_freeze functions are 30/30 identical.
  - The rules are still: 4 schedules, 3 pairs, both arms must fire (valid_trial), and violations are checked before completeness.
- A refused pick:
  - selected becomes None, so challenge.py continues without running a batch: 0 episodes;
  - it cannot erase a violation, because failures are only added from batches that ran;
  - it still uses one of the 8 requests and is charged.
- The rule's basis is episodes of this campaign, with purpose source_validation, the candidate's policy hash and arm L. In v2d these are 3 episodes, all in the development split.
- These checks are about the challenge's own rules. The adversary it runs is narrowed, as (4) shows.

(4) BIAS TOWARD SCHEDULES THE CANDIDATE PASSES: YES, AND IT IS LARGER THAN DOCUMENTED
Evidence: reach-vs-challenge-calls.json and replan-options-check.txt. Both come from my script, which uses the repo's own loop_limits.candidate_reach, _call_targets and decide on read-only scratch copies.
- The rule's basis for v2d's candidate is only get_order and update_order, both on orders. The candidate policy says "report terminal failure" after the rejected upgrade, so under the source fault its agent stops early.
- In the same challenge, the candidate's agent itself called three targets the rule refuses:
  - get_operation_status on orders in 4 of 9 candidate episodes, 3 to 4 times in each pick-2 episode;
  - send_confirmation on notifications in 6 of 9;
  - get_operation_status on notifications in 1 of 9.
- Faults on these targets fire for this candidate, yet the rule refuses all of them.
- Of the grammar's 9 fault kind and target combinations, 4 are refused: F1 on send_confirmation, and F4 on the orders status, the notifications status and send_confirmation. What remains is the source schedule's own tools, where the candidate was just validated.
- The candidate's before_confirmation and before_final_report hooks were never exercised in source validation. They can never be stressed through status or confirmation faults.
- A refused pick also removes 3 candidate episodes. Today those episodes can reveal a violation even when the fault does not fire, because challenge.py checks violations before completeness.
- Direct demonstration (demo_rule2_hides_counterexample.py and demo-rule2-hides-counterexample.log):
  - It uses the builder's own offline harness with the real Explorer, the real unchanged challenge.py, and a scripted runner in which the candidate fails C4 whenever send_confirmation is faulted.
  - The same 5 Explorer answers give COUNTEREXAMPLE_FOUND (C4, 1 schedule, 6 episodes) without the rule.
  - With the rule they give PASSED_OBSERVED (first pick REFUSED_UNREACHED, then 4 reachable schedules, 24 episodes), which leads on to promotion.
- In a live run the Explorer is also told to avoid those targets, so it would try them even less.
- Residual safety:
  - a refused pick never counts as passed;
  - the challenge still needs 4 schedules where every pair fired;
  - the fixed promotion cases still run.
  I could not check whether the promotion cases cover the notifications path, because that needs audit/promotion.json, which is protected.
- The premise behind fix 2 is not supported by the saved evidence.
  - Pick 3 was an F4 on the orders status with occurrence 1 and no other fault, so the upgrade path is healthy.
  - In pick 3, neither the candidate's agent nor its policy read the status at all.
  - The incumbent arm also failed to fire in 2 of 3 pairs.
  - So pick 3 failed to fire because of the schedule: on a healthy upgrade path neither arm polls status. It was not because the candidate made the status call unnecessary.
  - The rule refuses pick 3 only because source validation happens to exclude the orders status.
  - Of the PM options: (c) refuses exactly the same 3 targets as the build does. (b) would not refuse pick 3 at all, because the candidate's agent had called the orders status in picks 1 and 2, so (b) would not have prevented v2d's INCONCLUSIVE either.
- Possible directions that do not depend on the candidate, for the PM to consider:
  - refuse only picks with a fault that the existing reachability labeller (app/lab/reachability.py) proves IMPOSSIBLE;
  - or a forced-fire pre-check per schedule, covering both arms;
  - or option (d), drop rule 2.

(5) GATES, SCORING, ADAPTERS AND DISCOVERY ARE UNCHANGED
- I ran gate_freeze.py through the builder's wrapper, which never reads promotion.json or final-audit.json, on two trees:
  - a git-archive export of backup/part2-2026-09-22 (backend/app, contracts, audit/development.json and the requirements files only), placed outside the Desktop;
  - the working tree.
- Results:
  - functions 30/30 and files 20/20 identical;
  - fingerprints: only runtime (ee2d1df9 -> 4d0d7914), algorithm (ab296a32 -> 3bc86d57), source (2597bffb -> abf010c4) and tree_lab changed;
  - unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, adapters 0cd810b7, actor prompt 12eabe7f, referee and telemetry trees, lock files;
  - my backup snapshot equals the builder's before.json, and my working-tree snapshot equals its after.json.
- None of the 26 changed or added files is protected. Under backend/app/integrations, the simulator, referee, contracts/*.schema.json, prompts/actor.md, actor.py, discovery_protocol.py, history_replay.py, agent_history.py, reachability.py and the discovery prompts, nothing differs from the backup.
- The explorer.py changes run only when challenge=True and the plan declares the rule. Discovery requests are unchanged by construction.

(6) OFFLINE TESTS, NO .env READ
- conftest.py has an automatic prohibit_network fixture (loopback only, and only for tests marked localhost_http) and an audit hook that blocks reading .env.
- The v2d rebuild test opens the saved store with mode=ro&immutable=1, backs it up into pytest's temp folder, and deletes the copy.
- The new browser test mocks /api/** with page.route.
- I did not open .env, checks.py, artifacts/heldout2, audit/promotion.json or audit/final-audit*.json. checks.py was only hashed by gate_freeze.
- The saved stores are unchanged; their sha256 values are in saved-stores-sha256-end.txt. The v2b store is still 118b04a4.
- My scratch copies under /Users/shree/FaultLab_Scratch/review-integrity are deleted.
- Git: I used read-only commands only.

WHAT I DID NOT DO
- No frontend or browser re-run.
- No live run.
- No check of the promotion-case coverage, which is protected.
- I changed no file outside review-integrity/.

FILES (all in review-integrity/)
- Tree and code: tree-vs-backup-review-start.txt, tree-vs-backup-review-end.txt, diff_*.txt
- Gate freeze: gate-freeze-backup.json, gate-freeze-now.json, gate-freeze-compare.txt
- v2d rebuild: rebuild-v2d-request-reviewer.json, rebuilt-v2d-request-full.json, rebuilt-v2d-request-compacted.json, compaction-adversarial-checks.txt
- Challenge rule: reach_vs_challenge_calls.py, reach-vs-challenge-calls.json, replan-options-check.txt, demo_rule2_hides_counterexample.py, demo-rule2-hides-counterexample.log
- Tests and stores: new-tests-run.log, backend-suite-reviewer.log, saved-stores-sha256-end.txt
- Helpers: guard.py and rebuild_v2d_request_copy.py are copies of the builder's scripts, run from this folder so the builder's files were not overwritten.

## Findings (structured)

- **HIGH-1 (HIGH)** `backend/app/lab/loop_limits.py`: Fix 2 (candidate reach, candidate_reach and decide) refuses challenge picks based on what the candidate's own agent called under the source fault only. That weakens the challenge for exactly the candidates that do less under that fault, and it can turn a challenge that finds a counterexample into one that passes. In effect this relaxes the challenge gate, which the brief forbids, even though challenge.py is unchanged. Evidence: v2d, from reach-vs-challenge-calls.json and replan-options-check.txt: the rule's basis is only get_order and update_order (orders). In the same challenge, the candidate's agent called get_operation_status on orders in 4 of 9 L episodes (3 to 4 times each in pick 2), send_confirmation on notifications in 6 of 9, and get_operation_status on notifications in 1 of 9. The rule refuses all three. That is 4 of the grammar's 9 fault kind/target combinations. The offline replay in demo-rule2-hides-counterexample.log uses the real, unchanged challenge.py and the same 5 Explorer answers: without the rule it gives COUNTEREXAMPLE_FOUND (C4); with the rule the first pick is REFUSED_UNREACHED and the result is PASSED_OBSERVED after 4 reachable schedules, which leads on to promotion. Fix: Do not freeze challenge_selection into new Learn plans as built (run_plans.prepare_run_plan and build_run_options) until the PM decides. The PM's options (b) and (c) do not remove the bias. (c) refuses the same 3 targets for v2d; (b) would not have refused pick 3. Use a basis that does not depend on the candidate: refuse only picks with a fault the existing reachability labeller proves IMPOSSIBLE, or use a forced-fire pre-check per schedule for both arms. Or drop rule 2 (option d). Add a test in which a refusal must not turn COUNTEREXAMPLE_FOUND into PASSED_OBSERVED.
- **MEDIUM-2 (MEDIUM)** `docs/PRODUCT_LOOP_LIMITS_2026-09-30.md`: The premise behind fix 2 and the description of how far it narrows the challenge do not match the saved evidence. The docs say pick 3 did not fire because the candidate made the status call unnecessary, and that only notifications faults are refused. In fact both arms missed the fault because the schedule leaves the upgrade healthy, and orders-status faults are refused too, although the candidate's agent calls that tool. Evidence: v2d pick 3 was an F4 on the orders status with occurrence 1 and no other fault, so the upgrade path is healthy. The fault fired in 1 of 3 incumbent (B0) episodes and 0 of 3 candidate (L) episodes. There were no policy reads in any pick-3 episode, and the incumbent's agent skipped status polling in 2 of 3. In pick 2, the candidate's agent itself polled the orders status 3 to 4 times per episode. CURRENT_STATUS.md, the note (section 3) and the test docstring all repeat the 'made unnecessary' premise and name only the notifications narrowing. Option (c) refuses exactly what the build refuses for v2d. Option (b) would not refuse pick 3. Fix: Correct CURRENT_STATUS.md, the note (section 3 and the PM options), the v2d write-up addition and the docstring of test_loop_limits_challenge_reach.py. Say that pick 3 missed in both arms because the upgrade path was healthy, and that the rule also refuses orders-status faults for v2d's candidate. Restate what options (b) and (c) would actually do.
- **LOW-1 (LOW)** `backend/app/lab/loop_limits.py`: The compaction's protection test (_row_failed) keeps an episode only if it has a failed check. The rest of the codebase counts a violation as failed checks OR outcome == 'VIOLATION' (promotion.py, evaluation.observed_candidate_violations, completion_study, heldout_check). An episode with outcome VIOLATION and no failed checks could therefore be omitted at stage 2 or 3. Evidence: compaction-adversarial-checks.txt check 5: an episode patched to outcome VIOLATION with empty failed_checks is not kept at stage 3. No such trial exists in the 414 trials of the 8 saved stores, so this is latent only. Fix: In _row_failed, also treat facts['outcome'] == 'VIOLATION' as a failure, and add a test for it.
- **LOW-2 (LOW)** `backend/app/lab/loop_limits.py`: The stage-2 grouping key (recipe, arm, lifecycle, outcome, failed_checks, fault_triggered) leaves out policy_hash. development_evidence collects every candidate's source-validation episodes. On a third or fourth candidate request, a clean episode of one candidate can therefore be listed as represented_by a clean episode of a different candidate policy. It is still named with its own outcome, so it is not silent, but the full rows shown belong to another policy. Evidence: _compact_block builds its group from facts['scenario_hash'] plus the outcome fields only. learning.py extends source_feedback_evidence with each candidate's source-validation evidence. On v2d there was only one candidate, so every representative had the same policy (compaction-adversarial-checks.txt). Fix: Add policy_hash (and the experiment purpose) to the stage-2 group key and to the rule text ('per recipe, arm, policy and outcome'), then update the declaration and its tests.
- **LOW-3 (LOW)** `backend/app/lab/learning.py`: When a candidate or diagnosis search ends on the request-size limit, the campaign still ends with the generic NO_CHANGE reason 'No verified strict improvement within declared development bounds'. Anyone reading only the campaign status cannot tell that a search was cut short rather than finished. Separately, every ModelInputLimit from mechanic.propose is recorded as FORMAT_REPAIR with the text 'the first turn was sent'. That is currently true only because the first-turn count matches the Mechanic's exactly. Evidence: learning.py ends with coordinator.transition(id,'NO_CHANGE', <generic reason>). The size-limit path only writes mechanic_context_records, which the dashboard panel shows. On the propose path, 'except ModelInputLimit' calls record_repair_refusal with no check that a first-turn output was actually saved. Fix: When any SEARCH_ENDED record exists for the campaign, say so in the NO_CHANGE reason (a display change only; no gate is touched). Before recording FORMAT_REPAIR, check that this request's first-turn mechanic_outputs row exists.
