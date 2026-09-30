_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

PRODUCT REVIEW: history fireability (faultlab-explorer-selection/v3-history-fireability) and evidence retry v3. September 30, 2026. $0 and offline. I changed no product file.

VERDICT
- Ready with changes.
- I found no correctness bug. Both rules behave as the task asked, on a scratch copy of the saved native-v2b store, through the real learning loop.
- Old plans and old stores read exactly as before.
- Two things should be settled before the live run:
  - F1, a design decision for the PM;
  - F2, a wording fix in the dashboard.

HOW I WORKED ($0)
- Every script imported my own guard, review-product/review_guard.py. It refuses any `.env`, `artifacts/heldout2` and `audit/final-audit*` open, and any non-loopback socket.
- The guard counted 0 refused sockets and 0 refused protected opens in every run.
- One thing to disclose: the product's own plan-creation code read `audit/promotion.json` to hash it, through `load_manifest`, exactly as the test suite does. The guard counted those opens: 25, 12 and 16 in three scripts. I never printed that file.
- I blocked the learning loop's promotion stage before it could load any case. The block raises an error, so scripted campaign A1 ends in ERROR on purpose.
- I never opened `checks.py`. I only hashed it with `git hash-object`.
- The saved store was read only through `mode=ro&immutable=1`. Its sha256 matches the builder's start hash (cc2da5ef…, and the -shm/-wal files too).
- The scratch copies and the backup tree were under `/Users/shree/FaultLab_Scratch/review-product-fireability`. That folder has been deleted.
- There was no git write: HEAD is still cbbf957 and nothing is staged.

CHECK 1: the frozen table on the saved store (scripted/scripted-campaigns.json)
- I registered native adapter v2 under this runtime. A new v4 Learn plan then froze a history of 30 verified episodes and this table:

  | target | verified | fired | status |
  |---|---|---|---|
  | F1 update_order (orders) | 4 | 4 | ALLOWED |
  | F2 update_order (orders) | 10 | 10 | ALLOWED |
  | F3 get_order (orders) | 4 | 4 | ALLOWED |
  | F4 send_confirmation (notifications) | 4 | 4 | ALLOWED |
  | **F4 get_operation_status (orders)** | **4** | **0** | **REFUSED** |
  | F4 get_order (orders) | 1 | 1 | ALLOWED_FEWER_THAN_3 |

- The plan's refused-target text reads: "fired in 0 of 4 verified history episodes".
- A new v3-history plan has the same rows. Only `record_cutoff` and the table hash differ.
- A new v1 plan has no block.
- Start's plan check (`validate_run_plan`) accepts the new plans.
- The 5 older saved plans are unchanged, round-trip byte for byte and have no block.
- With an empty history (NO_PRIOR_HISTORY), v3 and v4 plans for the reference agent and for native v2 get an empty table and Start accepts them.
- I counted the saved Explorer picks myself; the counts match the builder's:
  - challenge: 3 of 11 target the status read (v2d 1, v2f 2);
  - discovery: 7 of 15 (v2c 3, v2e 3, v2f 1).
  All of them are lone status-read picks.

CHECK 2: scripted campaigns through the real loop
These ran through `coordinator._execute`, with the real Explorer answered by a script, the real fireability session, the real Challenger and the real PairedEvaluator. The Actor runner, Weave, reproduction, diagnosis and the Mechanic were test doubles. As in live runs, a lone status-read fault was made not to fire.

- **A1, new v4 plan, challenge.**
  - Request 1 was the lone status read: REFUSED_LOW_FIRED_SHARE, and no pair ran.
  - Request 2 was the re-plan (`slot_request` 2, with `replan_of` and `slot_feedback`): F2 delayed upgrade, allowed.
  - Requests 3 to 5 were allowed.
  - The challenge reached PASSED_OBSERVED: 4 schedules, 12 pairs, 0 failed checks, 5 of its 8 requests, 5 ledger calls.
  - All 5 requests carried the rule and the table. The system prompt was unchanged.
- **A0, the same answers under a v4 plan saved without the rule.** The status pick ran, its pair was untriggered, and the challenge ended INCONCLUSIVE after 1 schedule. That is the v2d/v2f failure, reproduced.
- **B1, new v4 plan, discovery.** 2 replays, then:
  - slot 3: refused, then its re-plan ran;
  - slot 4 (send_confirmation, a fine target): ran as today;
  - slot 5: refused, and its re-plan was refused too, with no third request;
  - slot 6: a duplicate, handled by the unchanged duplicate rule, with no re-plan;
  - slot 7: a mixed recipe (a delayed upgrade plus the status read) was refused, then its re-plan ran;
  - slot 8: no request, recorded as NO_EXPLORER_REQUEST (8 of 8 requests used).
  - Totals: 8 requests, 8 ledger calls, 5 Actor episodes.
  - The search decisions for allowed picks have the same keys as v1.
- **B0, the same answers under a plan without the rule.** Every pick ran: 6 requests, 8 episodes, and no rule keys in any request.

CHECK 3: evidence retry in long campaigns (evidence-retry/evidence-retry.json)
Each scenario is a campaign with 8 separate evidence waits.
- **S1, v3 plan, each wait clears on its first retry.** 8 automatic retries (more than 6). No "needs operator". The cap shown is 24.
- **S2, v2 plan saved before v3.** Start accepts it. Exactly 6 retries, then the 7th wait shows NEEDS_OPERATOR (PER_CAMPAIGN), with the API saying 6 of 6.
- **S3, v3 plan, each wait needs all 3 of its retries.** 24 retries (the cap), 3,600 declared seconds, all waits resolved and no "needs operator".
- Hashes, recomputed:
  - v2's declaration hash is still 3d849893… (the backup's value);
  - v3's is b76d6d5c…;
  - runtime 95042e4d (backup) → 07b8ccc4 (build), algorithm bc544604.

CHECK 4: dashboard, saved plan, recording, docs, and old stores
- **API comparison with the old code.** I ran `git archive` of `backup/part2-2026-09-22` into scratch. Its runtime reproduces 95042e4d.
  - I fetched 83 read-only views (plan, history check, experiments, search attempts, evidence wait, recording and so on) for every saved campaign, challenge and study, from each tree's own API over its own copy of the store.
  - 82 of 83 are byte-identical. The only difference is a random `request_id` on a 404 that both trees return.
- **Browser check.** I served the built `frontend/dist` and this build's API on 127.0.0.1 and opened it in a local browser (screenshots in review-product/dashboard/).
  - The saved v4 plan shows the rule and the frozen table, with the status read Refused and "24 per campaign".
  - The setup form shows the rule only for v3/v4; with v1 it is hidden.
  - The fault-search panel shows the refusals, the re-plans and "Selection 8 · no Explorer request".
  - The challenge panel shows 5 picks checked, 1 refused, and the re-plan.
  - The old v2f plan says "Not declared … Every valid Explorer pick runs, as before" and "6 per campaign".
  - No "Malformed" message appeared.
  - The recording carries `explorer_selection_rule` (7 picks checked, 4 refused, 1 slot without a request), and its `run_plan` has evidence retry v3 with a cap of 24.
- **Docs.** The user guide, the design note and CURRENT_STATUS ("not yet committed") are accurate, apart from the small F5 points.

OTHER CHECKS
- 145 related backend tests pass (fireability, evidence retry v3/v2, discovery v3/v4, agent history, citation status, loop limits). I ran them with no cache or bytecode writes.
- 142 protected files match the backup by git blob hash: the referee including `checks.py`, the simulator, `challenge.py`, `evaluation.py`, `promotion.py`, `diagnosis.py`, `reproduction.py`, the prompts, the integrations, `discovery_protocol.py`, `loop_limits.py`, `citation_status.py`, the policy interpreter and the contracts.
- The 588 files in the builder's final hash list are unchanged.
- Explorer request size is not a problem:
  - the added block is about 0.9k to 2k tokens, plus about 270 per refused pick;
  - the largest saved Explorer requests were 16.8k tokens (discovery) and 8.1k (challenge);
  - both stay well under the 32k limit.

FINDINGS
1. **F1 (MEDIUM, a PM decision before the live run).** The rule stops the challenge from putting a fault on the guardrails' own status reads.
   - Every generated candidate in this store (c65cc08e, 93ca3d35, 13f01971, 070968ee) has `read_current_operation` steps. Each one calls orders `get_operation_status` when the upgrade outcome is uncertain or its receipt is missing.
   - The table comes only from policy-v0 history and is per target. So the schedule that tests those steps under failure (an uncertain or pending upgrade plus a 503 on the status read) is refused for every candidate.
   - I saw exactly this in B1: a delayed upgrade plus the status read was refused.
   - As a result, a challenge can pass without any schedule reaching that guardrail step under a fault.
   - The builder disclosed "per target, not per recipe". What it did not connect is that the refused tool is the one these candidates add calls to.
2. **F2 (MEDIUM, wording).** The saved plan and the setup preview contradict the rule.
   - They print "no re-plans" and "every valid Explorer pick … runs one Actor episode; nothing is pre-checked" directly under the new rule. That text comes from the frozen v1/v4 discovery block and from `discoveryBudget()`.
   - The model sees a milder version of the same conflict: its system prompts say "changes nothing else" and "every valid schedule is tested", while the request context now refuses some picks.
3. **F3 (LOW).** The experiments endpoint, which the dashboard polls every few seconds, now scans every selection and challenge record on each poll for campaigns under the rule. It also reads the plan for campaigns with no counterexample. That is about 8 to 16 ms per poll on this store (1.8 MB of selection records), and it grows with the store. Phase 18 showed that heavy dashboard polling during paid runs can freeze the lab loop.
4. **F4 (LOW).** Small display issues:
   - the panels print "Refused: Refused before any episode ran";
   - the Refused row in the table is not highlighted;
   - the plan view shows the cap (24 or 6) but never names `faultlab-evidence-retry/v3` or `v2`.
5. **F5 (LOW, docs).**
   - "A new v3-history plan freezes the same table": the rows are the same, but the cutoff and the hash differ.
   - "v2f's 10 waits each cleared on their first retry": in the store, 6 waits cleared on their first automatic retry, 3 cleared on a manual retry after the cap, and the 10th ended STOPPED.

LIMITS OF THIS REVIEW
- The Actor, Weave, reproduction, diagnosis and Mechanic were doubles. A lone status fault was made not to fire by my harness, not by the simulator.
- A1 ended in ERROR because of my promotion block, not because of the product.
- A1's challenge card is not on the dashboard because the reproduction double saved no counterexample. Its fireability list is shown.
- I did not re-run the frontend unit tests, because vitest writes a cache inside `frontend/`. I checked the built dashboard in a browser instead.
- An integrity reviewer was working at the same time, writing only in its own folder. The source hashes were unchanged at the end of my review.

EVIDENCE
Everything is in `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-fireability-2026-09-30/review-product/`:
- `review_guard.py`, the guard every script imported;
- `review_scripted_campaigns.py` and `scripted/` (A0/A1/B0/B1 API and recording JSON, `scripted-campaigns.json`);
- `review_evidence_retry.py` and `evidence-retry/`;
- `review_api_differential.py` and `api-differential/` (`backup.json`, `build.json`, `compare.txt`);
- `review_dashboard_server.py` and `dashboard/` (6 screenshots, `dashboard-text.txt`);
- `pytest-related.log`.

## Findings (structured)

- **F1 (MEDIUM)** `backend/app/lab/fireability.py`: The table is per target and comes only from policy-v0 history, so status-read faults are refused for every candidate. But every generated candidate in native-v2b adds its own status read: a read_current_operation step that calls orders get_operation_status when the upgrade outcome is uncertain or its receipt is missing. The schedules that test those steps under failure (an uncertain or pending upgrade plus a 503 on the status read) are now refused, so a challenge can reach PASSED_OBSERVED and promotion without any schedule faulting that guardrail step. The builder disclosed 'per target, not per recipe' but not that the refused tool is the one the candidates add calls to. Evidence: Saved policies c65cc08e, 93ca3d35, 13f01971 and 070968ee each have read_current_operation steps under upgrade_outcome_uncertain and upgrade_receipt_missing. In the policy interpreter (lines 46-47), read_current_operation calls broker.call('get_operation_status', service orders). decide() refuses a pick if any of its faults hits a REFUSED row. In scripted campaign B1, slot 7's pick [F2 pending 3 ticks + F4 get_operation_status] was refused (SKIPPED_UNFIREABLE). In A1 the challenge reached PASSED_OBSERVED with 4 schedules, none touching the status read. See review-product/scripted/scripted-campaigns.json. Fix: PM decision before the live run; no gate change is needed. Options: (a) refuse only picks whose every fault is on a REFUSED target, which is the v2d/v2f lone-pick failure, and allow mixed recipes; this differs from the task's 'any primitive' wording, so it needs sign-off. (b) Never refuse a target that the frozen candidate's declared policy steps call (read_current_operation -> orders get_operation_status, read_notification_operation -> notifications get_operation_status, read_order -> orders get_order). This only ever allows more picks, unlike the withdrawn candidate-reach rule. (c) At minimum, record per challenge which REFUSED targets the candidate's own steps call, and make the live read-out state that those steps were never faulted.
- **F2 (MEDIUM)** `frontend/src/components/DiscoveryProtocol.tsx`: The saved plan and the setup form's plan preview contradict the new rule. Directly under 'History fireability … 1 re-plan per refused pick' they print 'no re-plans' and 'every valid Explorer pick that is not an exact duplicate … runs one Actor episode; nothing is pre-checked'. That text comes from the frozen discovery block (replans_per_slot 0, V1/V4 dispatch rule). The model sees a milder version of the same conflict: the v3 prompt says the protocol 'changes nothing else' and the challenger prompt says 'every valid schedule is tested in three fresh paired trials', while the request context now refuses some valid picks. Evidence: discoveryBudget() (DiscoveryProtocol.tsx line 38-39) prints 'no re-plans' when replans_per_slot is 0. discovery_protocol.py line 62 (V1_DISPATCH_RULE) and line 87 (replans_per_slot 0) are frozen into v3 and v4 blocks. Browser screenshots review-product/dashboard/02-saved-v4-plan-discovery-budget-says-no-replans.jpg and 03-setup-form-v4-rule-shown-preview-says-no-replans.jpg. Fix: Frontend only. When plan.explorer_selection is present, or the offered rule applies to the chosen protocol, make the budget line read 'one re-plan per pick refused by history fireability, within the same 8 requests', and add one qualifying sentence after the dispatch text. The frozen discovery block can stay as it is. Optionally, append a short Explorer prompt section only for plans that declare the rule, as CHALLENGE_REACH_PROMPT did, so prompts for older plans stay byte-identical.
- **F3 (LOW)** `backend/app/lab/api.py`: The experiments endpoint, which the dashboard polls every few seconds, now runs fireability.campaign_summary for campaigns under the rule. That scans every 'selections' and 'challenges' record in the store on each poll. It also calls read_run_plan for every campaign that has no counterexample. The cost grows with the store; Phase 18 showed that dashboard polling during paid runs can freeze the lab loop. Evidence: On the scratch store (59 selections, 1.8 MB of JSON), campaign_summary took about 8-16 ms per call. The browser's network log shows experiments requested repeatedly for an idle, finished campaign. Fix: Filter the selections by campaign in the store query, or cache the summary per campaign state, and read the plan once. Otherwise, keep the standing advice to close the dashboard during paid runs.
- **F4 (LOW)** `frontend/src/historyFireability.ts`: Small display issues. decisionText() produces 'Refused: Refused before any episode ran…' in the fault-search and challenge panels. The REFUSED row of the frozen table looks the same as the allowed rows. The saved plan names the evidence-retry cap (24 or 6) but not the rule id (faultlab-evidence-retry/v3 or v2), which appears only in the collapsed JSON. Evidence: historyFireability.ts line 117 plus the backend reason, which already starts 'Refused before any episode ran'. See screenshots 05 and 06 and dashboard-text.txt. Fix: Drop the duplicated word, highlight the REFUSED row, and name the rule id next to the cap.
- **F5 (LOW)** `docs/PRODUCT_HISTORY_FIREABILITY_2026-09-30.md`: Two imprecise statements. 'A new v3-history plan freezes the same table': the rows are the same, but record_cutoff and table_hash differ. 'v2f's 10 waits each cleared on their first retry': in the store, 6 waits cleared on their first automatic retry, 3 cleared on a manual retry after the cap, and the 10th ended STOPPED. Evidence: scripted-campaigns.json: v3 and v4 tables differ only in record_cutoff (6748 vs 6752). The saved store's v2f evidence_waits hold 10 records with automatic attempts [1,1,1,1,1,1,0,0,0,0]; 3 manual retries; the last wait's status is STOPPED. Fix: Change the wording to 'the same rows' and state the v2f waits precisely.
