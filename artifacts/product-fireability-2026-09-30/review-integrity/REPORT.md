_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

INTEGRITY REVIEW: history fireability for Explorer picks (faultlab-explorer-selection/v3-history-fireability) and evidence retry v3. September 30, 2026. $0 and offline.

Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-fireability-2026-09-30/review-integrity/
I wrote no REPORT.md, because my instructions forbid report .md files. This text is the report.

BOTTOM LINE
- Every mechanical claim I checked holds:
  - the table reads only the frozen starting-policy history;
  - gates, challenge.py, the completeness rule, pair counts and scoring are unchanged;
  - saved plans read and behave as before;
  - evidence retry v3 changes only the per-campaign cap (6 to 24), and only for new plans;
  - the tests make no outside connection.
- The rule can make a challenge easier for a candidate, and in this store it lands in an unlucky place.
  - The one refused target, F4 on orders get_operation_status, is the exact call every generated guardrail in native-v2b adds.
  - Because the rule is per target, it also refuses a status-read failure during a pending upgrade. That recipe fires, and it is the natural test of that step.
  - The PM should decide before the live run: accept this bias and say so plainly, or narrow the rule.

CHECK 1: IS THE RULE CANDIDATE-INDEPENDENT? YES.
- Code reading:
  - fireability.compute_table reads only agent_history.used_episodes. That is the same generator the history uses (_in_scope).
  - It is filtered to: development split; discovery purpose (in SQL and again in Python); not B1; the plan's starting-policy hash; a baseline-study B0 slot or a Learn campaign's own discovery pick; the same agent identity; not a history replay; completed and Weave-verified.
  - The table's ids must hash to the history's episode_ids_hash.
  - The table is frozen into an immutable plan record with its hash. It is re-verified at Start and before the first Explorer request.
  - During the campaign, the Session holds only that frozen block. Challenge state (refused picks, the pending re-plan) is keyed by campaign, candidate hash and incumbent hash, and reset at proposal 0.
  - Nothing outside explorer.py, learning.py, run_plans.py, api.py and exports.py reads the rule. The Mechanic never sees the table.
- Differential (the builder's script, rerun by me against my own extraction of the backup module):
  - 35 of 35 history computations are equal on all 11 saved stores;
  - used_episodes matches 35 of 35;
  - 6 of 6 saved history plans verify the same way (history-differential-rerun.json).
- Independent mutations (review_mutations.py and review-mutations.log). I ran them on a scratch copy outside the Desktop, never on the working tree. Every file was restored with the same sha256, and 0 outbound connections were made.
  - Caught, 15 of 21:
    - the table or history reading candidate-policy episodes (R1);
    - reading every purpose, meaning challenge, source validation, reproduction and reduction, with the SQL filter also widened (R2b);
    - counting unverified or lab-error episodes (R3);
    - counting history replays (R5);
    - counting other agents (R7);
    - challenge picks not checked (R8);
    - the loop never setting the rule (R9);
    - both thresholds (R10, R11);
    - the re-verification ignoring the table (R12);
    - the re-plan budget and the one-re-plan limit (R13, R14);
    - E1 to E3, the evidence caps.
  - Survived, 6:
    - R2, the Python purpose check alone: equivalent, because the SQL filter still applies.
    - R6, the B1 check alone: equivalent in practice, because B1 controls have their own registration and model.
    - R16, a missing fault execution counted as fired: near-equivalent, because the simulator always writes one entry per fault.
    - R4, R15 and R17: real test gaps (LOW-2).
  - The builder's own 26 mutations (M1 to M3 cover the candidate, challenge and replay reads) remain valid.

CHECK 2: CAN THE RULE MAKE A CHALLENGE EASIER FOR A CANDIDATE? YES. THE STRONGEST CASE:
- All 4 generated candidate policies in native-v2b use read_current_operation 3 times each.
  - That step is get_operation_status on orders, called by the policy (policy_interpreter.py:46-47).
  - It runs after an uncertain upgrade, before confirmation and before the final report.
  - Evidence: challenge-picks-and-candidate-status-steps.txt.
- The challenge Explorer was targeting that step.
  - Its hypotheses for the refused picks say so (selection-49a45d29 in v2d; selection-6ff309e4 and selection-a0075acf in v2f). For example: "The candidate waits one tick and then reads current operation after an uncertain upgrade response. If the first orders get_operation_status attempt fails transiently...".
  - It chose the lone form, which seldom fires because with a healthy upgrade no one reads the status.
- A form that does fire exists: a pending upgrade (F2 delay on update_order) plus F4 on the orders status read.
  - In the saved store, the starting-policy agent read the orders status in 19 of 19 F2-delay discovery episodes and 9 of 9 F2 challenge incumbent episodes.
  - The candidates' policy step read it in 9 of 9 F2 challenge episodes (status-read-exposure.json).
  - docs/DISCOVERY_V2_2026-09-28.md lists this as action-space family A4 and labels it FORCED; a real-socket run confirmed it fires for the reference Actor.
  - Honest limit: the saved store has no combined status episode for the native agent, so for that agent this is an inference from the 19 of 19, not a measurement.
- The frozen table cannot see this.
  - Its REFUSED row is built from 4 lone picks only.
  - Because the rule is per target, the combined recipe is refused too, in both challenge and discovery.
- Offline demo (demo_fireability_hides_counterexample.py and its .log).
  - Setup: the REAL table a new v4 plan freezes on native-v2b (table_hash 8e791c77…), the real explorer.py and the unchanged challenge.py.
  - The runner is a scripted stand-in, not model evidence. Its candidate fails C4 only when its status read is faulted during a pending upgrade. Both arms fire.
  - Scenario A, first pick = the combined recipe:
    - without the rule: COUNTEREXAMPLE_FOUND (C4, 1 schedule, 6 episodes);
    - with the rule: that pick is REFUSED_LOW_FIRED_SHARE, 4 other picks run, and the result is PASSED_OBSERVED (24 episodes).
  - Scenario B, first pick = the v2d/v2f lone status read:
    - without the rule: INCONCLUSIVE;
    - with the rule: PASSED_OBSERVED. This is the intended effect.
- Residual bias, stated plainly:
  - Under a new plan on native-v2b, no challenge can inject any fault into the orders status read, whether alone or beside a pending upgrade.
  - That read is the new step every current guardrail depends on.
  - A guardrail that mishandles a failed status read can therefore pass the challenge. Before the rule, the same pick could have produced a counterexample.
  - Nothing in the past runs was actually hidden: no combined status pick was ever made, and the refused lone picks had 0 failed checks.
  - The refused row also cannot correct itself under rule-bearing plans (LOW-3).
  - The unchanged promotion gate may or may not test status-read failures; I did not inspect protected data.
- Comparison with the withdrawn candidate-reach rule:
  - That rule's refusals came from each candidate's own source-validation calls. In v2d it refused 3 of the 9 fault targets. A candidate could shrink the challenge by doing less.
  - This rule's basis is frozen before any candidate exists, refuses 1 target here, is identical for every candidate, and no candidate can steer it. Mutations confirm this.
  - Both share one flaw: a hidden weakness on a refused target can turn COUNTEREXAMPLE_FOUND into PASSED_OBSERVED.
  - "The same for every candidate" is true, but it is not neutral: repairs add calls exactly where the starting policy seldom reached, which is where this rule refuses.

CHECK 3: GATES AND CHALLENGE UNCHANGED. YES.
- gate_freeze was run on a git-archive extraction of backup/part2-2026-09-22 (432e54b) and on the working tree, with the promotion and final-audit manifests dropped from its file list:
  - files: 20 of 20 identical;
  - functions: 30 of 30 identical;
  - fingerprints: only algorithm_hash, runtime_hash, source_hash and tree_lab changed (gate-freeze-compare.txt).
- challenge.py has the same blob as the backup (7326c0ea).
- The tree listing against the backup shows no change under backend/app/referee, simulator, contracts, promotion.py, evaluation.py, reproduction.py, diagnosis.py or prompts/actor.md.
- A refused challenge pick reaches challenge.py as output=None. It uses one of the unchanged 8 proposals: `if output is None: continue`.
- The rules are unchanged:
  - pairs: 3;
  - both arms must fire: paired_complete with valid_trial;
  - violation rule: observed_candidate_violations;
  - novelty requirement.

CHECK 4: EVIDENCE RETRY V3. CLEAN.
- Everything from campaign_rule onward in evidence_wait.py, including the whole EvidenceWait class and its telemetry-only retry path, is byte-identical to the backup.
- declaration_v2() equals the backup's declaration() byte for byte (hash 3d849893…).
- v3 differs from v2 only in:
  - the protocol name;
  - the cap (24 instead of 6);
  - the rule text, where only the number changes.
- The declaration still says: repeats_model_requests False, repeats_business_actions False, charged_model_calls 0.
- The cap is read from each plan. Start accepts exactly v2 or v3.
- All 20 saved plans in all saved stores parse to identical results under the backup and this build. None declares explorer_selection, and the v2 ones keep 6 (saved-plans-roundtrip*.json).
  - Older plans that do not re-serialise byte for byte already behaved that way on the backup. That is not a regression.
- The disclosed trade-off stands: the flaky six-episode batch again takes 18 retries before "needs operator".

CHECK 5: NO NETWORK, NO .ENV. YES.
- 231 related backend tests passed under the network guard, with 0 refused connections and the conftest .env guard active (targeted-tests.log). They included the flaky-suspect test_discovery_v3_baseline_history.
- All my scripts reported 0 outbound connections.

ALSO VERIFIED
- The builder's counts: 3027 passed / 180 skipped, compared with 3000 before; frontend 362; browser 19.
- The saved-store table and pick counts: my own read-only count matches 2 of 14 and 1 of 9.
- The CURRENT_STATUS correction about 47b8f69 and v2f.
- 588 source files are identical to the builder's after-suite hashes. checks.py was compared only through gate_freeze.
- Note, not a finding: the reference Actor's source hash changes because it is a tree hash over backend/app/agents, which holds explorer.py. actor.py and prompts/actor.md are unchanged, and earlier accepted builds (884de24, 814a6e3) did the same. Every agent must be registered again before the live run.

HARD RULES IN THIS REVIEW
- $0, with no provider, W&B or network calls.
- I never opened .env, credentials, checks.py, artifacts/heldout2 or the audit promotion/final-audit files.
  - Disclosure: in the scratch mutation tree, audit/promotion.json and audit/final-audit.json were symlinks, so the product's own run-plan code could read them during tests, exactly as it does in the working tree. I did not open or copy them.
- The saved store was read only through mode=ro&immutable=1 or the product's own copy fixture. Its sha256, size and mtime are identical at start and end.
- No git write: HEAD is still main at cbbf957 and the backup is still at 432e54b.
- The working tree is unchanged.
- The scratch trees under /Users/shree/FaultLab_Scratch/review-integrity-fireability were deleted.

## Findings (structured)

- **MEDIUM-1 (MEDIUM)** `backend/app/lab/fireability.py`: The rule refuses per target, not per recipe (check_targets and decide, lines 250-298). So it refuses every fault on F4 orders get_operation_status: the seldom-firing lone pick it was built for, and also a status-read failure during a pending upgrade. That second recipe fires in both arms and is documented as family A4. In native-v2b, that status read is exactly the step every generated guardrail adds (read_current_operation). A challenge under a new plan therefore cannot test the candidate's own new step when it fails, and a candidate that mishandles it can reach PASSED_OBSERVED. The table is candidate-independent, but the bias is not neutral: repairs add calls where the starting policy seldom reached, which is where the rule refuses. Evidence: The 4 of 4 candidate policies use read_current_operation 3x each, and the interpreter maps it to get_operation_status on orders (policy_interpreter.py:46-47); see challenge-picks-and-candidate-status-steps.txt. The v2d/v2f challenge Explorer hypotheses explicitly target this step. The starting-policy agent read the orders status in 19/19 F2-delay discovery episodes and 9/9 F2 challenge incumbent episodes; the candidates' policy step read it in 9/9 F2 challenge episodes (status-read-exposure.json). docs/DISCOVERY_V2_2026-09-28.md labels A4 FORCED and confirms it fires with a real socket. The table's REFUSED row comes from 4 lone picks only. Demo with the real frozen table, real explorer.py and unchanged challenge.py (demo-fireability-hides-counterexample.log): the combined pick gives COUNTEREXAMPLE_FOUND (C4) without the rule, and PASSED_OBSERVED with it, after the pick is REFUSED_LOW_FIRED_SHARE and 4 other schedules run. Fix: PM decision before the live Learn run. Option (a): key refusals on the pick's full target signature (the set of kind/service/tool in the pick), so the lone status read (0/4) stays refused and a pick that also delays the upgrade is allowed. Option (b), nearly equivalent: refuse only when every target of the pick is REFUSED; this is mutation R17, which no current test pins. Option (c): keep the rule as declared, but state in the frozen RULE text, the doc and CURRENT_STATUS that status-read failures, including during a pending upgrade, are never tested by the challenge under this plan. Whichever is chosen, add a test pinning it, including the combined-recipe case. Require the live read-out to list the refused targets and every refused pick with its recipe, and never to describe a PASSED_OBSERVED challenge as having tested the guardrail's status step.
- **LOW-1 (LOW)** `docs/PRODUCT_HISTORY_FIREABILITY_2026-09-30.md`: The disclosure understates the bias. Section 5 item 1, CURRENT_STATUS line 95 and fireability.RULE say the narrowing is 'the same for every candidate' and mention a delayed upgrade only in passing. They do not say that the refused target is the step every current generated guardrail adds, or that the refused combined recipe is a documented, fireable family (A4). Evidence: docs/PRODUCT_HISTORY_FIREABILITY_2026-09-30.md:170-173 ('The narrowing is the same for every candidate'); CURRENT_STATUS.md:83 and :95; fireability.py:92-95. Fix: Add plain sentences to the doc, CURRENT_STATUS and, if the rule is changed before any plan freezes it, the RULE text. Say that in native-v2b the refused target is the orders status read that all 4 generated guardrails add. Say that a pending-upgrade status failure (A4), which fires in both arms, is refused too. Say that a challenge under this plan therefore cannot test that step failing.
- **LOW-2 (LOW)** `backend/tests/lab/test_history_fireability.py`: Test gaps from independent mutations. R4: compute_table's HistoryChanged branch (ids-hash binding) is never exercised. R15: no test runs two challenges in one Session, so a regression that carries one candidate's refused picks and pending re-plan into the next candidate's challenge would pass. R17: no test pins that a two-fault pick is refused when only ONE target is REFUSED. Also, test_the_rule_never_reads_candidate_or_challenge_episodes builds the Session from a fixed block, so it cannot detect a store-reading regression; the real protection is test_the_table_counts_only_the_eligible_starting_policy_history. Evidence: review-mutations.log: R4, R15 and R17 SURVIVED (22 passed each). R2, R6 and R16 also survived but are equivalent or near-equivalent: the SQL purpose filter, B1's separate registration, and the simulator always writing one execution per fault. Fix: Add: (1) a compute_table call with a history block whose episode_ids_hash is altered, expecting HistoryChanged; (2) two consecutive challenges for two candidate hashes in one Session, asserting that the second's first request has slot_request 1, no replan_of and an empty refused_picks list; (3) a challenge and a discovery pick [DELAYED(3), STATUS] asserted according to whatever MEDIUM-1 decides. Rename or rewrite the misnamed test so it goes through prepare_run_plan after seeding candidate and challenge episodes.
- **LOW-3 (LOW)** `backend/app/lab/fireability.py`: A REFUSED row cannot correct itself under plans that carry the rule. Refused picks run nothing, and baseline studies use fixed development cases that never schedule the status read. So for this agent identity and starting policy the row stays at 0/4, and it only changes if an operator runs a Learn plan without the rule (v1, v2 or v3-reachability) that happens to pick that target. The limits list does not state this. Evidence: discovery_slot and decide never produce an episode for a refused pick. agent_history._provenance admits only B0 baseline-study slots (fixed dev cases) and Learn discovery picks. The native-v2b table has no dev-case row on get_operation_status (V2B_TABLE in the tests). Fix: State it in the doc's limits and in CURRENT_STATUS. Optionally have the read-out note, for each refused target, that the refusal rests on the listed episodes and will not be re-tested by rule-bearing plans.
