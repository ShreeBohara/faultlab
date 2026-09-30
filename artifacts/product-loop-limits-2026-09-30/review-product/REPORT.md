_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

PRODUCT REVIEW: two Learn-loop limits after live run v2d (September 30, 2026)

Cost was $0. I made no provider, model, W&B, Weave or network call. My socket guards refused 0 connections, and the browser opened 0 outside connections.

I changed no product file.
- The CHANGED and ADDED files match backup/part2-2026-09-22 exactly as they did at the start: same file list, same sha256.
- HEAD is still cbbf957 and the backup ref is still 3b31b58. .git/index has the mtime it had on 2026-09-27.
- Both saved stores kept their sha256 (native-v2b 118b04a4…, native-learn-v3 e1b43edc…).
- My scratch folder /Users/shree/FaultLab_Scratch/review-product (store copies, harness store) is deleted.

Evidence is in artifacts/product-loop-limits-2026-09-30/review-product/:
- scripts;
- evidence/*.json;
- screenshots/ (23 PNGs);
- rebuild-v2d-independent.json;
- identity-review.json;
- test logs;
- tree and sha256 snapshots.

One disclosure. On the scratch copy of the v2d store, I sent one POST /start to the old ERROR campaign. It was refused with 409, so nothing ran. The saved store itself was never touched.

HOW I TESTED
The real backend ran over loopback HTTP, with the real Vite dashboard and headless Chrome (Playwright, with the repo's isolation flags). These parts were real:
- the learning loop, run plans and the Challenger;
- the real Mechanic and Explorer code, including their token counts;
- app.lab.loop_limits;
- native adapter v2 and the in-process simulator;
- a fresh scratch store.

These parts were scripted, so they show how the product behaves, not how a model behaves:
- the model replies;
- the Weave double;
- for two scenarios, extra synthetic event IDs added to check rows. They were added after the real evidence read, and the real 32,000-token limit was kept.

There was a stop point before the protected promotion comparison. The replay list was empty (I ran no baseline first), so discovery v4 ran exactly as v3.

CHECK 1: challenge refusal and re-plan, end to end
I used a new Learn plan with discovery v4 and native agent smolagents-v2. The plan froze both rules (campaign …ae381385, scenario "reach").
- Request 1 was an F4 fault on the notifications status read. It was refused before any pair ran.
- Request 2 was its re-plan (slot_request 2, replan_of set). It ran.
- Requests 3 to 5 ran. The challenge ended PASSED_OBSERVED: 4 schedules, 12 pairs, 5 Explorer requests, each charged.
- The Explorer saw the rule both in its prompt section and in a candidate_reach block. That was true for 19 of the 20 challenge requests; the one without it was in the "norule" run, which withheld the rule on purpose.

Second run, "policyread" (…481ef076):
- Request 1 was an F2 upgrade delay plus an F4 fault on the orders status read. It was refused, and the reason names the candidate policy's reads.
- Its re-plan made the same pick. That was refused too, with "no further re-plan".
- The challenge still passed, using 6 of the 8 requests.

CHECK 2: large Mechanic requests, end to end
Scenario "compact" (…a2e91e19):
- The challenge ended INCONCLUSIVE, as in v2d.
- The second candidate request was 61,595 tokens. Stage 3 brought it to 19,271, and it was sent.
- The statement inside the request is correct. It says 15 clean rows were omitted (6 of 16 development, 9 of 18 challenge), and it keeps every failing episode.
- The campaign ended NO_CHANGE.

Scenario "unfit" (…d968da83):
- The first candidate request was 79,000 tokens, and still 43,517 after all three stages.
- The result was SEARCH_ENDED BEFORE_SEND, and nothing was sent. The campaign ended NO_CHANGE with 0 execution errors.

Across all runs, the largest request sent was 21,818 tokens for the Mechanic and 15,142 for the Explorer. Nothing over the limit was ever sent.

CHECK 3: the refused v2d request, rebuilt independently
My script re-derives the request by reading learning.py and counts it with the real Mechanic's own admission check.
- Full request: exactly 33,223 tokens, the same number as the recorded ERROR.
- After compaction: 27,990 tokens (stage 2).
- I passed it through the real Mechanic.propose to a capturing stand-in. The first turn it would send was 27,990.
- All 10 failing episodes are kept, and so are the source and its 3 reproductions. Every field outside the evidence tables is unchanged.

A side result: my first route gave 32,877. It took the reduction trials from the reductions record, which lists only 6 of the 9 reduction trials. Using all 9, as the loop does, gives exactly 33,223. So the builder's rebuild is right.

Of the 15 omitted episodes, 13 differ from the episode named as their example (see finding LOW-1).

CHECK 4: dashboard, saved plan, recording and export
- The Learn setup form and the saved plan show both rules, and the exact rule text is available. The baseline form shows neither.
- The challenge panel lists every checked pick with its reason. The diagnosis panel lists the compaction and search-ended records.
- The recording downloaded from the dashboard has run_plan with both rules, mechanic_context_records, challenge_selection_rule and challenge_reach on each challenge selection.
- Regression bundles (evidence.json) carry the same fields.
- At 390 px phone width there is no horizontal overflow.
- The only console error is a favicon 404 that was already there.

Old stores:
- The saved v2d store, served from a copy, shows "Not declared … as before" for both rules. It has no new lists. Its API and recording keys are unchanged.
- All 5 campaigns in the v2d and v3 copies read in-process with no new keys, and both rule functions return None for them.

Tests and identity:
- 131 targeted backend tests passed. They include all 30 new tests and the saved-store rebuild test.
- All 353 frontend unit tests passed.
- The identity values match the builder's:
  - runtime 4d0d7914, algorithm 3bc86d57;
  - simulator service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c;
  - native adapter v1 6f303264 and v2.1 dfd41b33;
  - prompts 22515428, fff397c9 and 12eabe7f.

WHAT I FOUND ON RULE 2 (main product point)
A challenge pair counts only when its faults fire in both arms, the incumbent and the candidate.

1. Counting only the agent's own calls is the right choice, and the evidence is stronger than the builder's note says. In my "norule" run the rule was withheld. There, an F2 fault plus an F4 fault on the orders status read fired in the candidate arm 3 of 3 times, through the candidate policy's own read. It fired in the incumbent arm 0 of 3 times, so the challenge ended INCONCLUSIVE. So if the rule counted any caller, as the brief literally says, it would let through picks that can never complete. That answers the PM's decision 1.

2. Basing the rule on source validation is much too narrow. Source validation runs only the source's fault. For v2d's candidate, the rule would allow faults on only 2 of the 5 tool and service pairs (get_order and update_order). Yet in v2d's own challenge, the agents in both arms called the other targets:
   - the orders status read: in all 6 episodes of the F2 pick;
   - send_confirmation: in all 12 episodes of picks 1 and 3.

   So the rule would refuse "F2 on the upgrade plus F4 on the orders status read". Both arms would very likely fire that pick, and it aims straight at the candidate's new hook. The docs describe the narrowing as notifications only.

A narrower option worth putting to the PM (untested): refuse an unreached target only when the pick has no fault on a write tool (update_order or send_confirmation). On the saved picks it refuses v2d's pick 3. It still allows v2d's picks 1 and 2, v3's counterexample pick, F2 plus the status-read fault, and confirmation faults.

Other notes:
- The diagnosis compaction can never omit anything, because its evidence is always kept in full. The docs say so.
- v2d fits after stage 2 by only 10 tokens.

## Findings (structured)

- **HIGH-1 (HIGH)** `backend/app/lab/loop_limits.py`: Rule 2 (faultlab-challenge-selection/v2-candidate-reach) refuses far too much, because it bases its check on source-validation episodes, and those run only the source's fault. For v2d's own candidate, only faults on get_order and update_order (2 of the 5 tool and service pairs) would be allowed. It would refuse faults on the orders status read and on send_confirmation, even though the agents in both arms called those tools under other schedules in the same challenge. It would also refuse F2 plus F4 on the orders status read, the pick that attacks the candidate's new read-then-require-receipt hook. The docs (CURRENT_STATUS.md, the loop-limits note, user-guide.md) describe the narrowing as affecting only confirmation and notifications faults. Evidence: review-product/evidence/challenge-reach-both-arms.json runs the product's own candidate_reach and decide on a scratch copy of v2d. The rule's allowed list is ['get_order:orders','update_order:orders']. In the challenge's F2 pick, the agent called get_operation_status:orders in all 6 episodes (incumbent 3/3, candidate 3/3). In picks 1 and 3, the agent called send_confirmation in all 12 episodes. The incumbent arm's source validation called all 5 targets. In review-product/evidence/policyread.json, the combined F2 + F4 status pick was refused, and so was its re-plan. Fix: Treat this as a PM decision before any live run with rule 2. Put the measured scope (2 of 5 targets for v2d) in the docs. Consider a narrower rule: refuse an unreached target only when the pick has no fault on a write tool (update_order or send_confirmation). On the saved picks it still refuses v2d's pick 3 and still allows v2d picks 1-2, the v3 counterexample pick, F2 plus the status-read fault, and confirmation faults. The other option is to drop rule 2 and keep rule 1.
- **MED-1 (MEDIUM)** `docs/PRODUCT_LOOP_LIMITS_2026-09-30.md`: The docs give the wrong reason why v2d's third pick did not fire, and they frame PM decision 1 without the both-arms rule. The docstrings (loop_limits.py line 19, test_loop_limits_challenge_reach.py line 4) say the candidate policy 'reads the status itself'. In that pick, the candidate policy never read status: its read runs only after an uncertain upgrade. Nobody called status in 5 of the 6 episodes across both arms. The docs also leave out that a pair must fire in both arms, and the incumbent has no policy reads. That fact is what supports counting only the agent's own calls. Option (b), 'would not have changed the v2d pick', is wrong: under (b), pick 3 would have run, because the candidate arm's agents called the orders status read in 4 of the 6 candidate-arm episodes of picks 1-2. Evidence: Saved v2d store: in pick 3, the candidate arm's calls were get_order, update_order and send_confirmation, with no policy calls. The fault fired only in incumbent episode e4c7d7. review-product/evidence/norule-challenge-trials.json: a fault reached only through the candidate policy fired in the candidate arm 3 of 3 times and in the incumbent arm 0 of 3, and the challenge ended INCONCLUSIVE ('Incomplete or untriggered challenge pair'). challenge-reach-both-arms.json lists the candidate-arm calls in picks 1-2. Fix: Correct the cause in the docstrings, CURRENT_STATUS and the note. Nobody reads status when the upgrade is healthy, and the candidate's read depends on an uncertain upgrade. State the both-arms reason for counting only the agent's calls, both in the rule text and in challenger_candidate_reach_v2.md. Correct option (b): it would not fix v2d.
- **LOW-1 (LOW)** `backend/app/lab/loop_limits.py`: The stage-2 wording suggests that an omitted episode repeats the episode named as its example. The legend says omitted rows 'are not repeated here', and the field is called 'represented_by'. In fact, rows omitted at stage 2 can differ from that example in the agent's report and observations. The omission is stated, so nothing is hidden, but the Mechanic could read the omitted episodes as behaving the same. Evidence: review-product/rebuild-v2d-independent.json: 13 of the 15 omitted v2d episodes differ from their named example. 5 differ in the agent's report or observations: for example next_action NONE versus CHECK_EXISTING_UPGRADE, and 6 versus 4 observations. The legend text is at lines 206-209 and STAGE_TEXT at lines 42-47. Fix: Reword it along these lines: 'omitted; its rows can differ from the kept example, which shares only its recipe, arm and outcome'. Keep 'same_as' for stage 1, where the rows really are identical.
- **LOW-2 (LOW)** `frontend/src/loopLimits.ts`: A format-repair refusal is shown as 'Candidate request N: not sent', with the badge 'Search ended, not sent'. But the first turn was sent and charged, as the record's own reason says. A search that ended before sending also shows 'development_evidence: 7 of 10 episodes in full' for a request that never went out. There are small cosmetic problems too: 'refused, no pair ran. Refused before any pair ran:' repeats itself, and the 'selected' and 'invalid output' badges are in lower case. Evidence: loopLimits.ts line 88 (contextRecordText) and common.tsx line 8 (the SEARCH_ENDED label). The record text comes from REPAIR_REFUSED_REASON in loop_limits.py. Screenshots: 11-policyread-challenge-reach.png and 13-unfit-mechanic-size.png. Fix: Give stage FORMAT_REPAIR its own text, for example 'first turn sent; its format-repair turn was not sent'. Hide the 'in full' line when nothing was sent. Remove the repeated words.
- **LOW-3 (LOW)** `backend/app/lab/learning.py`: When the Mechanic refuses the format-repair turn under rule 1, the loop saves no campaign_proposals row for the first turn it sent. The ordinary invalid-output path saves a REJECTED INVALID_MECHANIC_OUTPUT proposal. So a charged candidate request is missing from the candidate history on the dashboard and in the recording. Only mechanic_outputs and the Mechanic request-size record show it. Evidence: In the 'except ModelInputLimit' branch after mechanic.propose, record_repair_refusal is followed by break, and save_proposal is never called. candidate_count stays counted, which is right because the request was sent. Fix: Save a proposal record for that attempt. It should carry a reason such as FORMAT_REPAIR_OVER_LIMIT and link to the Mechanic request-size record.
