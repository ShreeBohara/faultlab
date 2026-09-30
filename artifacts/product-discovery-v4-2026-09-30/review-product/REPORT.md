_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

PRODUCT REVIEW: discovery protocol v4 (history replay), September 30, 2026

Cost was $0. I made no provider, model, W&B, Weave or network call. Both of my socket guards recorded 0 refused connections. The browser ran with the repo's own isolation settings and logged 0 requests to any other website.

I changed no product file, and git is unchanged: HEAD is cbbf957, the index hash is the same, and the backup branch is still 4d1c21b. The sha256 of all 1,154 files under backend, frontend, contracts, scripts, docs, taskpacks and CURRENT_STATUS.md was the same at the end as at the start.

The saved store /Users/shree/FaultLab_Runs/2026-09-30/native-v2b was only copied. Its three files kept the same size, modification time and sha256.

My scratch folder was /Users/shree/FaultLab_Scratch/review-product-v4. It held the store copy, the dashboard's scratch store and the Playwright output, and I deleted it at the end.

Evidence is in faultlab/artifacts/product-discovery-v4-2026-09-30/review-product/:
- serve_offline.py and saved_store_v4_plan.py;
- scripts/;
- evidence/ (JSON files and logs);
- screenshots/ (12 PNGs);
- identity-check.txt;
- the git and tree snapshots from the start.

The scripted answers below are fixture behaviour, not model evidence.

HOW I TESTED
I used the real backend over HTTP on a loopback port, the real Vite dev server, and real Chrome driven by Playwright. Everything was real except:
- the model replies were scripted:
  - Actor: the tests' native reply script, which confirms before the upgrade finishes;
  - Explorer: its first discovery request re-picks dev-5 with seed 999, and every later request picks a 4-tick delayed upgrade;
  - Mechanic: a diagnosis that asks for the first offered intervention, then a deliberately weak candidate or NO_CHANGE;
- Weave was the tests' local double;
- the simulator ran in-process.

I also set a stop point before the protected promotion comparison. It was never reached.

1. THE OPERATOR FLOW, END TO END
a) Registration. I registered native adapter v2 in the dashboard with "Register configured agent". The registration is smolagents-1.26.0-adapter-v2-cb877c16b3fd785f. The page said "No agent execution or provider call was made".

b) Chooser. It lists v1 (marked default), v2, v3, v3 plus pre-check, and "v4 · history replay first".
- v1 stays selected by default.
- Choosing v4 shows the one sentence: "Before the Explorer picks anything, re-runs up to 3 recipes from this agent's frozen history that fired every fault and failed in at least 2 of every 3 verified episodes (one agent episode each, no Explorer request); the remaining slots are exactly v3 · agent history."
- Before any plan exists it shows "The replay list is computed from this agent history and frozen into the plan when you create the campaign…".
- Screenshot: 01.

c) Empty history. Before any baseline, I created a v4 plan (E4) and a v3 plan (E3) through the dashboard.
- The v4 plan says "Replay list empty: this store has no prior history for this agent, so nothing is replayed. Discovery runs exactly as v3 · agent history."
- It also says "This is still a discovery v4 run with nothing to replay…".
- Screenshot: 02.

d) Baseline study. I ran a scripted baseline study through the API: 36 slots, COMPLETED, evidence Weave-verified through the double. The B0 arm gave:
- dev-3: 3/3 VIOLATION (C3);
- dev-5: 3/3 VIOLATION (C3);
- dev-6: 3 SAFE_UNRESOLVED;
- dev-1, dev-2, dev-4: COMPLETED.

e) The v4 plan through the dashboard (campaign M4, campaign-96127d6e…).
- The saved plan shows "History replay list · runs first", placed before the frozen history.
- Replay 1 is agent history row 3 (dev-3). Replay 2 is row 5 (dev-5). Each shows "violated in 3/3 verified episodes · every fault fired 3 of 3 · failed checks C3 … 3 (baseline study)", then "2 slots … · 2 agent episodes · no Explorer request", the frozen-from hash, the claim sentence and the rule.
- dev-1 (no fault) was not replayed.
- "Check against the store now" said: Current.
- Screenshots: 03 and 04.

f) Start from the dashboard.
- Slots 1 and 2 were history replays. Each had provenance history_replay, 0 model calls, empty answer text, transport_retries [] and a SELECTED decision carrying {replay, history_row, development_case_id}.
- Both replay episodes ended in VIOLATION and became sources through the unchanged rule.
- Each source then went through the unchanged loop:
  - reproduction reproduced it 3/3;
  - reduction ended LOCALLY_MINIMAL (shown as FINITE_NEIGHBORHOOD_EXHAUSTED);
  - diagnosis found POLICY_GAP, with 1 intervention;
  - the weak candidate was REJECTED at source validation (CANDIDATE_FAILED), then the Mechanic said NO_CHANGE.
- That used the campaign's 4 candidate requests, so the unchanged rule `if candidate_count>=campaign.caps.candidates: break` ended discovery. The campaign ended NO_CHANGE with 0 Explorer requests. This is pre-existing behaviour; see finding F2.
- The ledger shows 218 scripted model calls and $0.134. That is ledger arithmetic on the fixture's declared token counts, not money spent.

g) Second v4 plan (campaign M4b, campaign-3255a398…), with the Mechanic set to NO_CHANGE first.
- The new plan's history now counts M4's replay episodes: dev-3 and dev-5 are each 4/4, from "baseline study, learn discovery". See finding F3.
- The replays ran first, with 0 model calls. Then the Explorer made 6 requests.
- Its first request (slot 3) carried:
  - discovery_protocol = v4;
  - agent_history byte-equal to the plan's summary;
  - the v3 and v4 prompt sections;
  - both replays as prior selections marked history_replay, with their VIOLATION results under tested_schedules;
  - no replay_prompt key in the context.
- That request re-picked dev-5 with seed 999 and was SKIPPED_DUPLICATE (DUPLICATE_DISCOVERY_SCHEDULE). It pointed to the replay's selection and episode, so the duplicate rule applies to replays.
- Slot 4 (the 4-tick delayed upgrade) was SELECTED and became a third source. Slots 5-8 were duplicates.

h) Labels, as seen through the API and the real dashboard:
- Selection records and the recording: provenance history_replay, label "history replay", the row, 0 model calls.
- Search-attempts API and panel: "Selection 1 · History replay 1 of 2 · agent history row 3 (dev-3) · no Explorer request", the full "never independent discovery" sentence, a link to the replay episode, and a "History replays · no Explorer request" count.
- Experiments API and the "Reproduce & reduce" panel:
  - each replay source shows "Found by: History replay … never independent discovery";
  - the Explorer-pick source shows "An Explorer pick in this discovery v4 campaign, not a history replay slot."
- Recording (API, and the file downloaded from the dashboard): the discovery_history_replays block (frozen list, replay slots, sources_found_by_replay, claim rule), and sources[*].history_replay.
- Regression bundle ZIPs downloaded via /api/regressions/{id}/download: every incident bundle's evidence.json carries the same blocks.
- A v4 dev-5 bundle re-imported through POST /api/bundle-imports was accepted (201).
- Screenshots: m4-*, m4b-*.

i) Empty history behaves as v3. I started the E4 (v4, EMPTY) and E3 (v3) plans; both checks said CURRENT first.
- Both made 8 Explorer requests, and the system prompts were identical: no v4 section.
- Request 1 was identical after replacing only the campaign id and the protocol id.
- Later requests differ only in run-specific ids and the order of short evidence labels (o1/o2/o3).
- The decision sequence was identical: 2 SELECTED, then 6 duplicates.
- The v4 sources were labelled "not a history replay slot". The v3 plan, projections and recording carry no replay fields.

j) A changed history refuses Start. I made a new v4 plan, then changed one counted B0 evidence record in the scratch store.
- The check button said "Changed: Start will be refused. The store's prior history … changed …; create a new plan."
- Pressing Start showed the same message as an alert.
- The campaign stayed IDLE with 0 selections and 0 model calls.
- Screenshots: 07 and 08.

The dashboard showed no page errors and made no off-site requests in any step.

2. THE SAVED native-v2b STORE (copy outside the Desktop; the original was untouched)
I registered native adapter v2 again through the API: smolagents-1.26.0-adapter-v2-cb877c16b3fd785f, prompt fff397c9…, adapter dfd41b33…. The saved registration had been …3b1fa31a84aa2a65. Then I created a v4 Learn plan through POST /api/planned-campaigns.

The frozen history is AVAILABLE:
- 25 verified episodes: 1 baseline study (18 episodes) and 1 learn campaign (7 episodes);
- summary hash d45adfdeef3c…;
- record cutoff 1537.

The replay list is exactly:
- Replay 1: agent history row 5, dev-5.
  - "F2 on update_order:orders attempt 1: the accepted upgrade stays PENDING for 2 ticks, then FAILED (UPGRADE_REJECTED)", seed 105.
  - 3/3 VIOLATION, every fault fired 3/3, failed checks C3 3 and C5 3, source: baseline study.
- Replay 2: agent history row 6, dev-6.
  - "F4 on send_confirmation:notifications attempts 1-2: transient 503 before the request is accepted", seed 106.
  - 2/3 (VIOLATION 2, SAFE_UNRESOLVED 1), every fault fired 3/3, C4 2 and C5 2, source: baseline study.
- There is no third row. dev-3 is 1/3, and the Explorer-pick rows have 1 verified episode each.

The v4 history equals a v3 plan's except for the cutoff, the budget equals v3's, and the check said CURRENT for both. This matches the builder's read-only result.

3. BOUNDARIES AND TESTS
I compared 137 protected files with the backup branch using git hash-object:
- referee (checks.py excluded), simulator, contracts;
- promotion, challenge, evaluation, reproduction, diagnosis;
- actor, mechanic and their prompts;
- external_agent.py, external_agent_v2.py, registry.py;
- policy_interpreter, agent_history, reachability, the v3/v2 Explorer prompt sections, budgets, runner, coordinator, evidence and regressions.
All 137 are identical, and there are no new untracked files in referee, simulator or contracts. external_agent.py has sha256 6c0909bf…, the value the native v1 check pins.

Identities, computed with the product's own code under the test .env guard:
- runtime 2a181539…, algorithm f66ae8bb…;
- unchanged: simulator service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, capability 8e8e04af, Actor prompt 12eabe7f, native v1 adapter/prompt 6f303264/22515428, native v2 adapter/prompt dfd41b33/fff397c9.

Tests I ran myself:
- 9 discovery, history, native v2 and run-plan test files: 135 passed.
- Full backend suite: 2,905 passed, 180 skipped, 0 failed, 2 known warnings, in 1,092 s. The native v1 golden test ran as part of it.
- Frontend unit tests: 345 passed.
- Browser suite on a private port (18433): 18 passed, 1 opt-in skip.
- I did NOT run the production build stage, because it writes frontend/dist.

4. FINDINGS (all LOW; details in the findings list)
- F1: the fault-search panel says "the Explorer chose the remaining slots" even when no Explorer slot ran (M4).
- F2: replay sources can use the whole 4-request candidate budget and end discovery before any Explorer slot, or before replay 2. The loop rule is unchanged, but the chooser, plan and docs do not say so.
- F3 (the builder already disclosed this): replay episodes feed back into later histories as "learn discovery", described as Explorer picks. The list is self-reinforcing across v4 runs in one store: 3/3 became 4/4 after one run.
- F4: a v4 recording still carries v3's claim text ("Results of a discovery v3 campaign…"). This is cosmetic.

5. HONEST NOTES
- I stopped my own Vite server with a broad `pkill -f vite` for my user. No other listener existed before or after (only an unrelated python process on 127.0.0.1:7373). But if another session had a Vite or vitest process running at that exact moment, it would also have been stopped.
- To exercise a changed history, I edited one evidence record directly in my scratch store (SQLite UPDATE). That store was a scratch copy only.
- These were not exercised at product level:
  - v4 for the reference Actor or native v1 (unit tests only);
  - the "no eligible row" empty statement (unit tests and the builder's read-only check);
  - challenge, promotion or a live run.
- Nothing here measures model behaviour. Whether a live dev-5 replay survives reduction is still unmeasured.
- The review had no .md report file written; the PM should save this text.

## Findings (structured)

- **F1 (LOW)** `frontend/src/components/SearchAttemptsPanel.tsx`: The fault-search panel always says 'the Explorer chose the remaining slots' once any replay exists. That is false when discovery ended before any Explorer slot ran. Evidence: Offline v4 run M4 (campaign-96127d6e…): 2 replay slots, then the campaign ended NO_CHANGE with 0 Explorer requests. The panel shows 'Recorded selection responses 0' next to 'Discovery protocol v4: the first 2 slots were history replays … with no Explorer request; the Explorer chose the remaining slots.' Screenshot: review-product/screenshots/m4-search-attempts.png. Code is line 51. Fix: Make the sentence depend on the rows. If there are no non-replay rows, say that no Explorer slot ran because discovery ended after the replays, and point to the campaign's end reason. Otherwise say 'the Explorer chose the next N slots'.
- **F2 (LOW)** `backend/app/lab/run_plans.py`: Replay sources go through the unchanged loop, and its campaign-wide limit of 4 candidate requests (learning.py:311, `if candidate_count>=campaign.caps.candidates: break`) can end discovery right after the replays. Then no Explorer slot, and possibly not even replay 2, ever runs. The chooser sentence (REPLAY_DESCRIPTION, line 474), the saved plan, docs/DISCOVERY_V4_HISTORY_REPLAY_2026-09-30.md and the user guide all say 'the remaining slots are exactly v3 · agent history' and do not mention this. Evidence: M4: dev-3 and dev-5 replays each reproduced 3/3, reduced, got POLICY_GAP, then a rejected candidate plus NO_CHANGE. That is 4 candidate requests, after which the campaign ended NO_CHANGE with 0 Explorer requests and slots 3-8 unused (evidence/m4.json). In native-v2b, if the dev-5 replay reaches candidates and the Mechanic makes 4 proposals, the dev-6 replay and every Explorer slot never run. This is existing loop behaviour, not a v4 code defect. Fix: Add one plain clause to the chooser, plan and docs: replay sources go through the normal loop first, and once the campaign's candidate requests are used up, discovery ends and later replays and Explorer slots do not run. The PM should expect no Explorer-slot data from a v4 run in which dev-5 reaches the candidate stage.
- **F3 (LOW)** `backend/app/lab/agent_history.py`: Replay episodes enter later v3/v4 histories as 'learn_discovery'. That source is described as 'a learn campaign's own discovery pick (chosen by the Explorer)' (line 42), and the history's scope says 'learn campaigns' own discovery picks'. So later plans, and the Explorer, see replays counted as Explorer picks. The replay list also becomes self-reinforcing across v4 runs in one store. For rows with no development case, the dashboard's replay list labels the row '(Explorer pick)'. The builder disclosed this and left the history format alone to keep v3 summary hashes stable. Evidence: In the offline store, the second v4 plan (M4b) showed dev-3 and dev-5 as '4/4 … (baseline study, learn discovery)'. The extra episode each was M4's replay, not an Explorer pick (evidence/step3.json; screenshots/05-v4b-plan-replay-list.png). Fix: PM decision before running v4 more than once in the same store. Either a new history schema version that labels or excludes replay episodes (v3 plans keep the current version), or at minimum name the history's composition and replays with every result.
- **F4 (LOW)** `backend/app/lab/exports.py`: In a v4 campaign's recording and bundle evidence.json, discovery_history_matches.claim_rule still reads 'Results of a discovery v3 campaign are history-informed…'. It sits next to the correct v4 discovery_history_replays block. This is cosmetic but could confuse a reader of the export. Evidence: evidence/m4.json recording.v3_claim_rule in the v4 campaign campaign-96127d6e…; the code is at line 100. Fix: Use protocol-neutral wording ('a discovery v3 or v4 campaign') or pick the text by protocol. v3 recordings' bytes must stay unchanged if that is required.
