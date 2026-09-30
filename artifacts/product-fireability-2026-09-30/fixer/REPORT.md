_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FIXER REPORT: history fireability for Explorer picks (faultlab-explorer-selection/v3-history-fireability) and evidence retry v3. September 30, 2026. $0 and offline. Not committed, not run live.

I did not write a REPORT.md, because my instructions forbid report .md files. This text is the fixer report. Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-fireability-2026-09-30/fixer/

BOTTOM LINE
- The rule is SHIPPED with a change. It is not withdrawn.
- Both reviews were right about one thing. The builder's rule refused a pick if ANY of its faults was on a refused target. That also refused a status-read failure DURING A PENDING UPGRADE. That recipe does fire, and in native-v2b the refused status read is exactly the step every generated guardrail adds.
- I changed one decision: a pick is now refused only when EVERY one of its faults is on a refused target. That is the lone status-read pick from v2d/v2f. Nothing else about the table changed: not its basis, not its thresholds, not its candidate independence.
- This departs from the task's wording ("if any of its primitives targets..."). The owner should confirm it before commit.
- Every other finding is fixed.
- The one final scripts/test.sh passed every stage (fixer/full-test-sh.log, 15:24:00Z to 15:43:40Z):
  - backend: 3,038 passed, 180 skipped, 0 failed, with the 2 known warnings;
  - frontend: 368 passed;
  - build: passed;
  - browser: 19 passed, 1 opt-in skip.
  The builder's run had 3,027 backend and 362 frontend tests. The difference is exactly my 11 new backend tests and 6 new frontend tests.
- New runtime: 49958e716f0b08aacb9db5d6ddf99620451f949a901aa35cca979918c1df6b6e (algorithm 7a56afed…). The builder's 07b8ccc4… is superseded.

WHY FIX RATHER THAN WITHDRAW
My instructions said: withdraw the rule if it weakens the challenge in a way that cannot be fixed cleanly. The weakening came from the single "any fault" choice. With "every fault":
- The rule is still candidate-independent. Its only basis is the frozen starting-policy history, and no candidate can change what is refused.
- No target becomes untestable. A refused target can always run beside a fault on another target.
- The integrity reviewer's own demo, rerun unchanged on the fixed code (fixer/demo-rerun-after-fix.log), with the real native-v2b table, real explorer.py and unchanged challenge.py:
  - Scenario A, the pending upgrade plus the status read: COUNTEREXAMPLE_FOUND (C4, 1 schedule, 6 episodes) WITH the rule, the same as without it. Under the builder's rule this was PASSED_OBSERVED.
  - Scenario B, the lone status read: still refused. The challenge then completes PASSED_OBSERVED instead of INCONCLUSIVE, which is the intended effect.
- Every saved Explorer pick in native-v2b gets the same decision as under the builder's rule: 3 of 11 challenge picks and 7 of 15 discovery picks refused, all of them lone status reads. No saved pick mixes the status read with another target. Source: fixer/saved-store-check-after-fix.json, from the builder's script rerun with only the scratch path changed.
- What remains, stated in the docs: a lone pick on a refused target never runs. So a candidate mistake that only such a pick could show (for example, a repair that reads the status on every run and mishandles a failure) is tested only if the Explorer pairs that target with another fault. The Explorer's re-plan instruction says it may do so.

TABLE
| id | outcome | change | test |
|---|---|---|---|
| MEDIUM-1 (integrity) | FIXED | fireability.decide refuses a pick only when every distinct target is REFUSED. The declaration and the saved plan model now carry pick_refused_when: every_fault_on_a_refused_target, and any other value is rejected. RULE, MEANING and the re-plan instruction say this. An allowed pick with a REFUSED target lists that target under targets, with a reason. | test_history_fireability_review_fixes.py: test_a_pick_is_refused_only_when_every_fault_targets_a_refused_row; test_the_rule_no_longer_hides_a_counterexample_on_the_guardrails_status_read (the integrity scenario A and B); test_a_discovery_pick_beside_a_pending_upgrade_runs_and_a_lone_one_is_still_refused (real learning loop); test_saved_plans_declare_the_every_fault_rule_and_the_model_refuses_another. The saved-store test now asserts the exact counts (3/7 refused, 8/8 allowed) and that no saved pick is mixed. |
| F1 (product) | FIXED | The same change (the product review's option (a)). The challenge panel now lists the targets refused on their own, and says a passed challenge tested one of them failing only if a listed pick paired it with another fault. The read-out requirements are in the docs. | The tests above; frontend history-fireability-fixes.test.tsx ("the challenge panel lists an allowed pick beside a REFUSED target...") |
| LOW-1 | FIXED (docs and RULE text) | RULE now says the table is "not neutral". The design note (section 5, items 2-4), CURRENT_STATUS and the user guide say the refused target is the orders status read that every native-v2b guardrail adds. | text only |
| LOW-2 | FIXED | New tests:<br>- R4, the ids-hash binding: test_compute_table_refuses_a_history_whose_episodes_are_not_the_stores<br>- R15, two challenges in one Session: test_two_challenges_in_one_session_never_share_refusals_or_a_pending_replan<br>- R17, mixed picks: now the rule, pinned by the MEDIUM-1 tests<br>- R16 (near-equivalent), pinned anyway: test_a_fault_without_a_recorded_execution_never_counts_as_fired<br>The misnamed test was renamed test_challenge_decisions_come_only_from_the_sessions_frozen_block, with its assertions kept. test_a_plan_saved_after_fired_candidate_and_challenge_episodes_freezes_the_same_table goes through prepare_run_plan. | These tests. Each one catches its mutation (mutation-checks.log). |
| LOW-3 | FIXED (docs) | Design note section 5, item 7, and CURRENT_STATUS: a refused row changes only through mixed discovery picks that run and enter a later history, or through a plan without the rule. Lone picks never run. | text only |
| F2 (product) | FIXED | Under the rule, the saved plan and the setup preview now read "one re-plan per pick refused by history fireability, inside the same 8 Explorer requests", not "no re-plans". The v1 dispatch text gets one qualifying sentence. Each Explorer request under the rule carries history_fireability.note: the rule takes precedence over "every valid pick runs / every valid schedule is tested". System prompts are unchanged, so older plans' requests stay byte-identical. | Frontend: 3 tests in history-fireability-fixes.test.tsx (saved plan, setup preview under v4 and v3). Backend: test_the_request_says_the_rule_qualifies_every_valid_pick_runs. |
| F3 (product) | FIXED | campaign_decisions now reads only this campaign's records:<br>- selections: SQLite extracts selection_id, context.campaign_id and fireability.status, then only matching rows are parsed;<br>- challenges: only this campaign's, via challenge_campaigns;<br>- unrequested slots: filtered by campaign_id in SQLite.<br>The experiments endpoint validates the plan of a campaign with no counterexample only if its saved record names the rule. On a copy of native-v2b the poll cost went from a 4.54 ms median (13.5 ms max) to 0.87 ms (1.1 ms max) (fixer/poll-cost-check.log). | test_the_experiments_poll_reads_only_this_campaigns_selections_challenges_and_slots (a full scan now fails the test, and the output equals the builder's algorithm); test_the_experiments_poll_does_not_validate_the_plan_of_a_campaign_without_the_rule |
| F4 (product) | FIXED | No more "Refused: Refused". Re-plans read "Re-plan. <reason>". The REFUSED row is highlighted (class fireability-refused, bold status). The plan names the rule id beside the cap, for example "24 per campaign under rule faultlab-evidence-retry/v3". | Frontend: history-fireability-fixes.test.tsx. The pinned text in evidence-wait.test.tsx and history-fireability.test.tsx was updated; exact equality is still asserted. |
| F5 (product) | FIXED (docs) | "The same rows" (the cutoff and hash differ). The v2f waits are now stated exactly, verified read-only from the saved store: the first 6 each used one automatic retry and resolved as verified; the next 3 hit the cap and resolved after one manual retry each; the 10th hit the cap and ended STOPPED. | text only |

FAILING, THEN PASSING
- Before any source edit, on the builder's code:
  - 7 of the 10 new backend tests failed (fixer/tests-before-fix.log). The other 3 are test-gap tests, which pass there by design because they pin code that was already right. An 11th of that kind (R16) was added afterwards.
  - All 6 new frontend tests failed (fixer/frontend-tests-before-fix.log).
- Negative-control mutations (fixer/mutation_checks.py and fixer/mutation-checks.log): 18 of 18 caught. Each one either puts back one piece of the builder's behaviour or re-applies a reviewer's surviving mutation:
  - backend X1-X7: "any" rule, missing declaration field, missing Explorer note, the three full scans, plan validated on every poll;
  - R4, R15, R16;
  - frontend FX1-FX8.
- They ran in a scratch tree at /Users/shree/FaultLab_Scratch/fixer/mut-tree. The baselines passed first. Every file was restored with an identical sha256, and the scratch tree was deleted.
- R2 and R6 were not re-run: the reviewer showed them equivalent (the SQL purpose filter, and B1's separate registration).

OTHER CHECKS ($0)
- 271 related backend tests passed under the network guard, with 0 refused connections (fixer/tests-after-fix-related.log). They cover fireability, agent history, discovery v2/v3/v4, evidence retry, loop limits, run plans, exports, citation status and role transport retry.
- The builder's API contract check, rerun with slot 2 changed to a mixed pick (fixer/api-contract-check-rerun.log): real run-options, plan, search-attempts, experiments and recording responses pass the dashboard's validators. The mixed pick is ALLOWED, with targets [ALLOWED, REFUSED] and its reason. The negative control is still rejected.
- Identity (fixer/identity-compare-final.txt):
  - changed: runtime, algorithm, the fireability declaration hash (838cf343… → ae56a27a…) and the two example configuration hashes, which include the runtime;
  - unchanged: service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…, native v1/v2 adapters, native v2.1 prompt fff397c9…, reference Actor prompt 12eabe7f… and reference Actor source 7f78de28… (I did not touch backend/app/agents), evidence retry v2 3d849893… and v3 b76d6d5c….
  - The identity after the suite equals the identity after the fix (35/35 keys).
- gate_freeze (fixer/gate_freeze/compare.txt): 20/20 files and 30/30 functions identical to backup 432e54b. promotion and final-audit were dropped from its file list.
- Tree against the backup (fixer/tree-vs-backup-end.txt): nothing changed under the referee, the simulator, contracts, challenge.py, evaluation.py, promotion.py, diagnosis.py, reproduction.py or prompts/actor.md. explorer.py is unchanged since the builder. checks.py was compared only through gate_freeze.
- Saved-store table (fixer/saved-store-check-after-fix.json): same rows as the builder's. The table hash is now ee7cfed0… (was 8e791c77…), because the table's meaning text changed with the rule.

FILES CHANGED BY THE FIXER
Diffs are in fixer/diffs/, with pre-edit copies in fixer/before/.
- Backend: backend/app/lab/fireability.py, backend/app/lab/run_plans.py (one field in ExplorerSelectionPlan) and backend/app/lab/api.py (the experiments poll).
- Frontend: frontend/src/historyFireability.ts, components/DiscoveryProtocol.tsx, CampaignPlan.tsx, RunSetup.tsx, LoopLimits.tsx, SearchAttemptsPanel.tsx and styles.css.
- Tests:
  - new: backend/tests/lab/test_history_fireability_review_fixes.py and frontend/tests/history-fireability-fixes.test.tsx;
  - edited: backend/tests/lab/test_history_fireability.py (saved-store test made exact for the new rule; misnamed test renamed), frontend/tests/history-fireability.test.tsx (declaration field; the "Refused: Refused" text) and frontend/tests/evidence-wait.test.tsx (rule id in the pinned text).
- Docs:
  - docs/PRODUCT_HISTORY_FIREABILITY_2026-09-30.md: status, rule, sections 3-5 and 7, and a new section 8 with this table;
  - CURRENT_STATUS.md: header, and the newest-build paragraph marked "not yet committed, not run live";
  - docs/user-guide.md and docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md.
  The two docs I edited without a copy were reconstructed exactly: their pre-edit sha256 matches the builder's recorded hashes.

RISKS AND LIMITS, FOR THE OWNER
1. The rule change (any → every) departs from the task's wording and needs sign-off before commit.
2. A lone pick on a refused target never runs. A mistake only such a pick could show is tested only when the Explorer pairs the target with another fault. No current native-v2b guardrail reads the status on a healthy upgrade.
3. A mixed pick whose other fault does not make the refused target reached is untriggered and can still end a challenge INCONCLUSIVE, as before the rule.
4. The live read-out must state:
   - the refused targets;
   - every refused pick with its recipe;
   - whether any challenge schedule faulted the orders status read.
   If none did, a PASSED_OBSERVED must not be described as testing the guardrail's status step.
5. The Explorer note is in the request context, not the system prompt. Whether the model follows it is untested live.
6. Evidence retry v3 is unchanged: its cap of 24 re-admits the 18-retry flaky-batch case. That trade-off was disclosed and accepted.
7. F3: SQLite still extracts three small fields from every selection row on each poll. That is cheaper, not zero. The advice to close the dashboard during paid runs stands.
8. Nothing here has been run live. Register every agent again before the live run.

HARD RULES
- $0. There was no provider, model, W&B, Weave or network call; every guarded script reported 0 refused outbound connections.
- I never opened .env, credentials, checks.py, artifacts/heldout2, audit/promotion.json or audit/final-audit*.json.
  - Disclosure: the mutation scratch tree had audit/promotion.json and audit/final-audit.json as SYMLINKS, created without opening them. The product's own plan code under test could then read the promotion manifest, exactly as the test suite does in the working tree.
  - The scratch frontend used the real node_modules through a symlink.
- The saved native-v2b store was read only through mode=ro&immutable=1 or the suite's copy helper. Its sha256 is unchanged (cc2da5ef…), and so are the -shm and -wal files. Every scratch copy was outside the Desktop and has been deleted.
- No git write: HEAD is still main at cbbf957, the backup is still at 432e54b, and 0 files are staged. I ran git only with --no-optional-locks.
- 591 source, test and doc files were unchanged during the final suite. The only difference was the browser stage's own frontend/tests/.results output.
