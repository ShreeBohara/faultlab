_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

BUILDER REPORT: discovery protocol v4 (history replay), September 30, 2026
Cost: $0. No provider, model, W&B, Weave or network call. The manual checks ran with a socket guard and recorded 0 refused connections. Not reviewed, not committed, not run live.

1. WHAT WAS BUILT
The new protocol id is 'faultlab-discovery/v4-history-replay'. It is opt-in; v1 stays the default.

v4 is exactly v3-history plus a frozen replay list:
- It uses v3's same-agent history unchanged: same code, eligibility, exclusions, summary hash, record cutoff and Start-time check.
- Its Explorer slots use v1 dispatch, v1 schedule identity (for the duplicate rule) and v1 budget: 8 slots, 8 Explorer requests, 8 transport retries, 8 Actor episodes, no re-plans. The plan validator requires exactly these numbers.

The replay list is computed once, at plan creation, from the frozen history summary. It is a pure function in backend/app/lab/history_replay.py, and it is frozen into the plan as discovery.replay (schema faultlab-history-replay/v1).
- Eligible rows: at least one scheduled fault (no-fault rows are never replayed), at least 2 verified episodes, every verified episode fired every scheduled fault, and a violation share of at least 2/3.
- Order: share (highest first), then verified count (most first), then row order. At most 3 rows.
- For each replayed row the plan records: the history row number, the development case, the recipe (in words and as the exact fault recipe), its order-aware schedule identity, verified episodes, violations and share, every-fault-fired count, outcomes, failed checks and sources.
- It also records the rule text, the thresholds and the summary hash it was computed from.
- An empty list gets status EMPTY and one of two plain statements: no prior history, or no eligible row.
- The recipe is the same schedule as the row under v2-order-aware: a development case's public recipe, otherwise the listed faults with seed 0. The seed never changes behaviour.

How discovery runs:
- Replay slots run first (backend/app/lab/learning.py). Each saves a selection record with provenance 'history_replay', 0 model calls, empty answer text, and a SELECTED decision that carries history_replay {replay, history_row, development_case_id}. It also gets a 'history_replay' block: label 'history replay', the row and counts, the episode id, and explorer_request false.
- Each replay then runs one Actor episode through the unchanged runner, and everything after that is the unchanged loop. A replay becomes a source only by the existing rule: COMPLETED, every fault fired, VIOLATION.
- The remaining slots are v3-history's Explorer slots. The Explorer gets the same frozen agent_history and its v1 search ledger, which now lists the replays as prior selections (with their results under tested_schedules). The duplicate rule applies to them.
- When the list is non-empty, one short prompt section is appended after v3's section (explorer_discovery_v4_history_replay.md). v3's text says history recipes are "not duplicates", which is no longer true for the replayed ones.
- When the list is empty, no v4 section is sent. The Explorer's messages then equal v3-history's except the discovery_protocol value (pinned by a test).

Checks:
- verify_plan_history also recomputes the replay list from the verified history and refuses any difference. It runs at plan save, Start and IDLE re-validation, and again before the first replay or Explorer request.
- A changed history refuses Start: 409 at Start, or AGENT_HISTORY_CHANGED with the plain reason after Start.
- A saved list the installed rule would not produce is refused the same way.
- The "Check against the store now" button covers the list.

Labels. Every replay is called "history replay" with its row in:
- the selection record;
- the Explorer ledger entry;
- the search-attempts API and fault-search panel ("Selection 1 · History replay 1 of N · agent history row R (dev-5) · no Explorer request", a sentence saying it is never independent discovery, a link to the replay episode, and a "History replays · no Explorer request" count);
- the experiments API and source panel ("Found by: History replay …"; an Explorer pick in a v4 campaign says "not a history replay slot");
- the campaign recording, and therefore the regression bundles' evidence.json: selections keep history_replay, discovery_history_matches.sources[*].history_replay is added, and a discovery_history_replays block holds the frozen list, the replay slots that ran, sources_found_by_replay and the claim rule.

Dashboard:
- The chooser offers "v4 · history replay first" with one sentence: "Before the Explorer picks anything, re-runs up to 3 recipes from this agent's frozen history that fired every fault and failed in at least 2 of every 3 verified episodes (one agent episode each, no Explorer request); the remaining slots are exactly v3 · agent history."
- The saved-plan view shows "History replay list · runs first" before the frozen history, or the plain empty statement.

Scope and old plans:
- v4 is available for the reference Actor and for native adapters v1 and v2. It is not combined with the reachability pre-check.
- Old plans never get a 'replay' key, so their bytes are unchanged.

2. WHAT WAS NOT CHANGED
Byte-compared against backup/part2-2026-09-22 (4d1c21b) with git hash-object:
- Nothing under backend/app/referee, backend/app/simulator or contracts/ changed.
- promotion.py, challenge.py, evaluation.py, reproduction.py and diagnosis.py (including summarize_evidence) are unchanged.
- The Mechanic, actor.py and prompts/actor.md are unchanged.
- external_agent.py (native v1), external_agent_v2.py and registry.py are unchanged.

The repo's gate_freeze.py (protected audit files dropped from its list; checks.py only hashed by it) shows only the runtime, algorithm, source and lab-tree fingerprints changed. assess_pairs, the scorer, summarize_evidence, promotion_decision and every guarded file are identical.

tree_compare: 14 files changed, 5 added in code/tests, plus 3 docs changed or added.

Git: HEAD is still cbbf957, the index still equals HEAD, and the backup branch is still 4d1c21b. No commit, reset, checkout or stash.

3. IDENTITIES (product functions; identity-before/after.json)
- Runtime 4553ebe7… → 2a1815399697a774597c1d485f605dccc9e4e57cddee9899a5b577c35ad1514d.
- Algorithm b2575eb2… → f66ae8bb570dffb9e5c7b3e26792c4bd9e9433e82994781cdd6ffc6b53b03bb3.
- Reference source hash (the backend/app/agents tree) 142a9ebc… → 2597bffb…. It is not part of the same-agent identity.
- The example configuration hashes changed, because they embed the runtime.

Unchanged:
- simulator service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…, capability 8e8e04af…;
- reference Actor prompt 12eabe7f…;
- native v1 adapter 6f303264… and prompt 22515428…;
- native v2.1 adapter dfd41b33… and prompt fff397c9…;
- the response-format hashes.

Every agent must be registered again before a live run. Histories are unaffected, because the same-agent identity does not use the runtime.

4. TESTS AND CHECKS
a) New backend tests: 23, in backend/tests/lab/test_discovery_v4_replay.py.
- Plan freezing and ordering: share, then count, then row order; ties; the cap of 3; an exact 2/3 share is eligible.
- Ineligible rows: fewer than 2 verified, share 1/2, an unfired fault, a no-fault row with violations.
- Empty history and no-eligible statements; case recipe versus seed 0; rule text recorded and re-checked; the saved-plan models refuse inconsistent blocks.
- The product plan path for reference, native v1 and native v2: history equals v3's, budget equals v3's.
- The loop:
  - replay slot 0 has no Explorer request, 0 model calls and the dev-5 recipe, and the Explorer continues with 7 requests;
  - the first request's ledger lists the replay and its result, with the v3 and v4 prompt sections;
  - the duplicate rule applies to the replayed recipe;
  - a replay VIOLATION becomes a source through the unchanged rule and is labelled in the record, search-attempts API, source projection and recording (an Explorer-pick source is labelled null);
  - a non-violating replay only uses its slot;
  - at most 3 replays, then 5 Explorer requests.
- Empty list: v4 messages equal v3-history's except the protocol id, in both the no-history and no-eligible-row cases.
- Start refuses a changed history, via validate_run_plan (409) and via the coordinator (ERROR, AGENT_HISTORY_CHANGED, no replay, no selection, no request).
- Start refuses a list that the installed rule would not produce.
- The history-check button covers the list.
- v3 records and projections never carry replay fields.

b) Frontend: 6 unit tests and 1 browser test.
- Options validation: v4 is never the default, carries no frozen list in options, and has v3's budget.
- Saved-plan validation: the list must be bound to the history hash; share, fired count, verified count, row/case consistency, numbering and the cap of 3 are checked; v3 never carries a list.
- Plan panel and empty statement; chooser sentence and create request.
- Replay rows validated: 0 model calls, no answer text, no retry, same row on record and decision. Panel labels checked.
- Source "Found by" label.

c) Negative controls (mutation_checks.py, scratch copies outside the Desktop, deleted after): 21 of 21 mutations caught; both unmutated controls pass. Mutations included:
- restoring the pre-round files;
- replays never run;
- no every-fault-fired check;
- a 1/2 threshold;
- a cap of 4;
- no verified-count tie-break;
- no-fault rows allowed;
- a replay hidden from the ledger;
- a replay claiming a model call;
- the prompt section always sent, or never sent;
- each API and recording label dropped;
- Start not recomputing the list;
- the plan not freezing the list;
- 5 frontend mutants.

d) Manual offline check through the product API (manual_check.py): scripted native transport, in-process simulator, local Weave double, socket guard. The scripted outcomes are fixture behaviour, not model evidence.
- Product baseline study, then a v4 plan via POST /api/planned-campaigns. Replay list: dev-3 (row 3) then dev-5 (row 5), both the fixture's 3/3 rows. dev-1 (no fault) was not replayed.
- The v4 history equals a v3 plan's (except cutoff) and the budget equals v3's; the v1 plan has neither field.
- Check button: CURRENT.
- Start via the API: 2 replay slots (0 model calls each), then 6 Explorer requests. The first request carried the frozen summary, both replays as prior selections with their VIOLATION results, and the v4 section. Labels were correct in the search-attempts, experiments and recording responses. The run ended NO_CHANGE.
- Declared manual shortcut: in this run, reproduction was the tests' stub, which records the source and reports "not reproduced", so no Mechanic request was reached.
- A changed counted record gave CHANGED; Start was refused with 409 and the plain message, with 0 new selections.
- Run B used the real Reproducer. The replay source reproduced 3 of 3 (C3) and was labelled a history replay. It was stopped at reduction by a declared stop point, so no Mechanic, challenge or protected promotion case was reached. The campaign then ended NO_CHANGE with the stop point's reason (existing coordinator behaviour when StopRequested is raised without an operator stop).
- Honest note: my first manual run ended ERROR (PROVIDER_ERROR) at the first Explorer request (kept as manual_check_first_run.json). The cause was the test fixture: PricedNativeInputs labels every reply with the Actor's model, and the Explorer's frozen-model check correctly refused it. I fixed the fixture wrapper in the check script, not the product.

e) API contract check (api_contract_check.py): the real plan, search-attempts and experiments JSON from an offline v4 run pass the dashboard's own validators. This found a real bug in my first frontend build: the backend sends transport_retries: [] on every search-attempts row, but my replay validator required the field to be absent, so the dashboard would have refused real replay rows. My unit fixture had the wrong shape. Fixed in src/searchAttempts.ts, the fixture was corrected, and a negative control shows the check fails with the old line restored.

f) Full suite: one scripts/test.sh after the last code edit, all 4 stages PASSED.
- Backend 2,905 passed, 180 skipped, 0 failed (was 2,882).
- Frontend 345 (was 339).
- Build passed.
- Browser 18 passed, 1 opt-in skip (was 17).
- sha256 of all 19 changed code and test files matched before and after the run.

5. WHAT v4 WOULD REPLAY IN THE SAVED STORES (read-only)
Method: readonly_replay.py, opening every store only with mode=ro&immutable=1; all 11 store files kept their size and modification time.
- 2026-09-30/native-v2b: adapter v2.1, prompt fff397c9, the same identity as a fresh v2.1 registration. Replay 1 = dev-5 (row 5), 3/3, C3 3 and C5 3. Replay 2 = dev-6 (row 6), 2/3, C4 2 and C5 2.
- 2026-09-30/native-v2: first v2 build, a different agent. dev-5 3/3, then dev-6 3/4.
- 2026-09-29/native-learn-v3: native v1. dev-5 3/3 only.
- 2026-09-28/native-probe: dev-3 3/3, then dev-5 3/3.
- 2026-09-29/native-learn: native v1, empty list (each row has 1 verified episode).
- The reference-only and empty stores: empty lists.

6. LIMITS AND OPEN ITEMS FOR THE PM
- Nothing has run live. v4 only decides which recipes run first; every gate after that is unchanged. Whether a live dev-5 replay survives reduction, and what the Mechanic diagnoses, is unmeasured.
- Replay episodes enter later histories under the existing 'learn_discovery' path, whose v3 description says "chosen by the Explorer". That is not true for a replay. I did not change the history format: doing so would change every v3 summary hash and break saved v3 plans. Each campaign's recording names its replays. Decide whether a later round should relabel or exclude replay episodes under a new history schema version.
- In the native-v2b store, replay 2 would be dev-6, the flaky C4 failure (2/3 there). Under the rule as specified it qualifies, and it may use a replay episode plus up to 3 reproduction episodes without surviving.
- The operator still chooses the store, and under v4 the history now decides the first slots outright. Name the store, the history's composition and the frozen summary hash with any result.
- Minor limits:
  - Only the (at most 24) listed history rows are considered.
  - Two rows that differ only in the order of overlapping same-kind faults share one v1 identity. Both would still replay.
  - With an empty list, v4 is v3-history except for the protocol id. Report it as v4 with an empty list, not pooled with v1 or v2.
- Next steps: two $0 reviews; commit (owner's OK); register the agents again; then a declared live v4 Learn run in the native-v2b store.

Docs: new docs/DISCOVERY_V4_HISTORY_REPLAY_2026-09-30.md; a paragraph in docs/user-guide.md; a CURRENT_STATUS.md "Current runtime" section marked not committed, not reviewed, not run live. The status header also notes that 4553ebe7 is committed locally as 78878bb and that commit 4d1c21b recorded the ledger at $898.58. All evidence is in /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-discovery-v4-2026-09-30/builder/. The scratch folders under /Users/shree/FaultLab_Scratch/ were deleted.
