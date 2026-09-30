_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

BUILDER REPORT: native citation status in Mechanic requests (faultlab-mechanic-evidence/v2-native-citation-status). September 30, 2026. $0 and offline. Not reviewed, NOT YET COMMITTED, not run live.

This file is the builder report: I wrote no REPORT.md, because my instructions forbid report .md files. CURRENT_STATUS says the final test result "is in the builder report", meaning this text.

RESULT
- The build is done.
- The one final scripts/test.sh passed every stage (log: artifacts/product-mechanic-citations-2026-09-30/builder/full-test-sh.log, 10:52:37Z to 11:11:04Z):
  - backend: 2,970 passed, 180 skipped, 0 failed, 2 known warnings (starlette BlockingPortal, fork);
  - frontend: 356 unit tests;
  - build: passed;
  - browser: 19 passed, 1 opt-in skip.
- The 579 source, test and doc files were hashed before and after the run and did not change during it.

WHAT WAS BUILT
1. A new block, native_citation_status. Every new Learn plan whose agent is native adapter v2 (smolagents-v2) freezes the rule in plan field mechanic_evidence. Under it, these requests get the block when they carry evidence of at least one episode:
   - each Mechanic diagnosis request;
   - each Mechanic candidate request;
   - each challenge Explorer request.
   The block holds the protocol id, one plain sentence saying what it means, and one row per episode, in the order the request's evidence first lists it:
   - cited: how many tokens the report cited;
   - decoded: cited tokens that are labels the agent had been shown, where the event's own label map gives the decoded ID recorded at that position;
   - undecoded: the event's cited_tokens_not_decoded list.
   Rows come only from the episode's last public report_submitted event, and only when it carries the v2.1 record. No check, verdict, trial or finding is read. Without a v2.1 record, cited, decoded and undecoded are all null.
2. The memory pointer. Mechanic requests that carry the block have one sentence appended to runtime_contract.actor_contract.memory, pointing to the block.
   - It is applied where the block is added, not in diagnosis.py. diagnosis.py is a gate-freeze file (runtime_contract is a frozen function), so V2_MEMORY there is unchanged.
   - As a result, discovery Explorer requests keep the old text byte for byte.
3. Checker v2, with self-tests. v1 is untouched.
4. Tests, docs and CURRENT_STATUS.

FILE BY FILE
- backend/app/lab/citation_status.py (new, 184 lines):
  - the declaration(), frozen in the plan;
  - campaign_rule();
  - episode_ids(), submitted_report() (public events, paged) and citation_row();
  - block() and attach(), which refuses any memory text other than V2_MEMORY with a RuntimeError;
  - two thin wrappers: CitationStatusMechanic, used for diagnosis, and CitationStatusExplorer, which adds the block only when challenge=True.
- backend/app/lab/learning.py (+11/-1):
  - reads citation_rule once;
  - wraps the diagnosis Mechanic around BoundedMechanic, so the block is added first and the size rule counts it;
  - calls citation_status.attach on the candidate proposal_context before loop_limits.fit_request;
  - passes challenge_explorer (the wrapper, or the plain explorer when there is no rule) to the Challenger.
  With no rule nothing changes: the same objects and the same contexts are used.
- backend/app/lab/run_plans.py (+44/-2):
  - MechanicEvidencePlan model, with exact lists and Literal fields;
  - SavedRunPlan.mechanic_evidence, omitted when absent so older plans keep their bytes;
  - prepare_run_plan freezes it only for agent 'smolagents-v2' in Learn mode;
  - _bindings refuses it for any other agent or mode;
  - validate_run_plan (Start) refuses a declaration that differs from the installed rule;
  - run options learn block shows the declaration.
- Frontend (loopLimits.ts +16, runPlans.ts +10/-3, LoopLimits.tsx +16/-9, CampaignPlan.tsx and RunSetup.tsx 1 line each):
  - type and validator for the declaration;
  - the saved plan shows "Native citation status" for native v2 plans only. An older v2 plan reads "Not declared: … saved before the rule". Other agents show nothing;
  - the Learn setup form shows it only when native adapter v2 is chosen.
- scripts/experiments/check_evidence_gap_misreading_v2.py (new): a copy of v1 with only the claim phrase list widened, plus --self-test (30 phrase cases and 7 verdict cases).
- Tests (new):
  - backend/tests/lab/test_citation_status.py: 17 tests;
  - backend/tests/lab/citation_status_saved.py: read-only rebuild helpers, not collected as tests;
  - backend/tests/experiments/test_check_evidence_gap_misreading_v2.py: 4 tests;
  - frontend/tests/citation-status.test.tsx: 3 tests.
- Docs:
  - new docs/PRODUCT_MECHANIC_CITATION_STATUS_2026-09-30.md;
  - follow-up paragraph at the end of docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md (v2e section);
  - one section in docs/user-guide.md;
  - CURRENT_STATUS.md: new "Newest build" paragraph marked "Not yet committed, not run live", a post-hoc note on the v2e table row, and a correction. The status had still called f058c03c "not yet committed, not run live". It was committed as 884de24 and run live once (v2e), and the status now says so.

UNCHANGED (verified)
- gate_freeze.py (run on the tree before and after): 30/30 gate functions and 20/20 gate files identical. Only the runtime_hash, algorithm_hash and tree_lab fingerprints changed.
- These files are byte-identical to backup d38c0b8: diagnosis.py (summarize_evidence, trial_outcomes, runtime_contract, V2_MEMORY), mechanic.py, explorer.py, challenge.py, promotion.py, evaluation.py, the referee, the simulator, prompts/actor.md, external_agent.py and external_agent_v2.py.
- Nothing in backend/app/agents changed, so the reference Actor source hash fb5e1894… is unchanged.

IDENTITIES (builder/identity-compare.txt)
- runtime: f058c03c… → c4195af104fbc90f2b2ba2b8fa2aad3ca17a3f74dd47b36612efcacc6f19c60c.
- algorithm: a08a8d61… → ea1ed61350257afe69d63198a615477654677148c509d74353ea5260942608e5.
- Same as before:
  - service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…, capability 8e8e04af…;
  - native v1 adapter 6f303264… and prompt 22515428…;
  - native v2 adapter dfd41b33…, prompt fff397c9… and adapter protocol 0136604…;
  - reference actor prompt 12eabe7f…;
  - mechanic_context v2-bounded declaration 11bf9e32…;
  - v2 memory text 6cbe23d4….
- New:
  - declaration hash 163c1a4caa54204762c733914398e119cd845ee98187c6bcbac23dddcebb40f9;
  - memory-with-pointer text hash 75241be81cd30ae6bc910640b7bb60573e48004f6b92f10c1c9c9ce31bd6cf11.
- The example configuration hashes changed (they include the runtime). Register every agent again before a live run.

BEFORE/AFTER: THE v2e DIAGNOSIS REQUEST
Rebuilt from a scratch copy of /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 by the real Diagnostician, with a capture Mechanic that raises before anything is sent or saved. IDs are faked; the full excerpt is builder/v2e-diagnosis-request-excerpt.json.
BEFORE: no native_citation_status key. runtime_contract.actor_contract.memory = "<V2_MEMORY, ending: '…so it can differ from the agent's obs-N.'>"
AFTER:
  "native_citation_status": {"protocol": "faultlab-mechanic-evidence/v2-native-citation-status",
    "meaning": "Each row is what the native adapter recorded when that episode's agent submitted its report: cited is how many evidence tokens the report cited, decoded is how many of them were obs-N labels the agent had been shown and so were decoded to the evidence ID of an observation delivered to it, and undecoded lists every cited token that was not decoded and was kept exactly as written (all three are null when no submitted report was recorded).",
    "episodes": [{"episode_id":"episode-FAKE01","cited":5,"decoded":5,"undecoded":[]}, {"episode_id":"episode-FAKE02","cited":5,"decoded":5,"undecoded":[]}, {"episode_id":"episode-FAKE03","cited":6,"decoded":6,"undecoded":[]}, {"episode_id":"episode-FAKE04","cited":6,"decoded":6,"undecoded":[]}]}
  runtime_contract.actor_contract.memory = "<same V2_MEMORY> This request's native_citation_status block lists, for each episode in its evidence, the adapter's recorded outcome of that decoding: how many tokens the report cited, how many decoded to delivered evidence, and any token kept as written."
Every other field is identical (checked).

SIZES (the Mechanic's own admission count and frozen tokenizer; builder/rebuild-requests.json)
- v2e diagnosis: 9,088 → 9,424 (+336; the block alone is 429 tokens as its own message). The provider reported 8,952; the local count adds the same 136 tokens of framing seen for v2d's first candidate request, so the rebuild is exact.
- v2d diagnosis: 8,990 → 9,321 (+331; the provider reported 8,854).
- v2d's refused candidate request (34 episodes): 33,223 → 34,796 (+1,573, about 46 tokens per episode including the sentence).
  - Compaction stages give 35,184 → 29,629 → 22,674. It fits at stage 3, within the 28,000 target. Without the block: 33,611 → 28,056 → 21,101, also stage 3.
  - After compaction the block is identical and keeps all 34 rows. All 34 show 0 undecoded, with every cited token decoded.

DESIGN CHOICES TO REVIEW
- Episodes the size rule omits keep their rows in the block. The block is never compacted: it is added before fit_request, and loop_limits compacts only evidence tables. This costs roughly 40 tokens per omitted episode.
- Discovery Explorer requests do not get the block. The brief named only Mechanic and challenge Explorer requests, and the discovery protocols must stay unchanged.
- The unchanged V2_MEMORY still contains its old sentence "a token kept as written … fails the evidence check". This build added no scoring statement; the new sentences are checked by a test for check, fail or verdict words.

TESTS AND CHECKS
- test_citation_status.py (17 tests; 4 use the saved store and skip where it is absent):
  - rows come from the event only; an undecoded token is shown; no record gives nulls;
  - scoring records and private events change nothing; the last report is used across pages;
  - each request kind gets the block in evidence order; only Mechanic requests get the pointer; a request with no evidence is unchanged; another memory text is refused;
  - the wrappers pass discovery requests through as the same object;
  - plans: only a new native v2 Learn plan declares the rule; an older v2 plan keeps its bytes and starts; Start refuses another rule text; other agents and modes cannot declare it; the model is exact;
  - the declared source protocol equals the adapter's PROTOCOL_VERSION;
  - learning loop: candidate and challenge requests carry the block and discovery requests do not; the diagnosis request carries it; the size rule's recorded full size includes the block for both diagnosis and candidate requests; with no rule, no citation code runs at all.
- Saved-store tests:
  - a new native v2 plan made in the copy (register, prepare_run_plan with v4 history replay, create) gives v2e's diagnosis context 4 rows (5/5, 5/5, 6/6, 6/6) with 0 undecoded, while v2e's own older plan gets none;
  - the v2e and v2d diagnosis requests rebuild at provider count + 136, and all 8 diagnosed episodes decoded every citation;
  - v2d's candidate request with the block fits after compaction and keeps every row.
- Differential check (builder/differential-requests.json): the backup learning.py and this one ran the same scripted loops for plans without the rule. Contracts: reference, native v1 and older native v2. Parts: candidate plus challenge, and diagnosis. All 6 scenarios were byte-identical after positional ID and hash normalisation, with no block anywhere. A positive control with the rule declared differs, and shows the block and the pointer.
- Mutation checks (builder/mutation-checks.log): 17 of 17 negative-control mutations caught; every file restored and sha256-checked.
- API contract (builder/api-contract-check.log): real run-options, plan and recording responses pass the dashboard's own validators.

MISREADING CHECKER v2: POST-HOC RESULTS (not the pre-registered read-out)
- Phrase list: a superset of v1. It adds "never (been) shown", "was/were not shown", "has/have/had not been shown", "cannot/could not/can't be decoded", "not decodable", "undecodable", "not (been) decoded", "undecoded" (not right after "0", "no", "zero" or "without"), and "outside (of) the shown (labels)" / "outside the labels (it was) shown".
- Everything else is unchanged. v1 keeps sha256 70c4eeda… in all three copies.
- Self-test PASSED.

| run | v1, re-run now (pre-registered) | v2 (POST-HOC) | phrases matched | episodes read |
|---|---|---|---|---|
| v2d (diagnostic-57fa14bc…) | NOT_CHECKED | MISREADING | "cannot be decoded", "never shown" | 4 |
| v2e (diagnostic-b0eeb89d…) | NOT_CHECKED | MISREADING | "never shown" | 4 |

In all 8 episodes read, 0 report IDs were not recorded and 0 tokens were not decoded. Outputs are in builder/checker-v2/.

WHAT THIS DOES NOT SHOW
- Nothing ran live. Whether the Mechanic stops claiming unshown citations once it sees the block is unmeasured.
- The block states no cause; the real C5 cause is an untruthful report after a confirmation the agent should not have sent.
- Checker v2 is a phrase heuristic.

NEXT
Two $0 reviews and a fixer, then commit (needs the owner's OK), register every agent again, then a declared live Learn run: v2 agent, v4 history replay, native-v2b store, read out with checker v2.

EVIDENCE: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/builder/
- scripts: guard.py, identity.py, identity_snapshot.py, tree_compare.py, gate_freeze/run_gate_freeze.py, rebuild_requests.py, differential_requests.py, api_contract_check.py, mutation_checks.py;
- identity and gate freeze: identity-before/after.json, identity-compare.txt, gate_freeze/before.json, after.json and compare.txt;
- tree compares: tree-vs-backup-before.txt and tree-vs-backup-end.txt (10 changed, 7 added, 0 missing);
- saved stores: saved-stores-sha256-start.txt and saved-stores-sha256-end.txt (identical);
- test run: source-sha256-at-suite-start.txt, source-sha256-after-suite-check.txt, git-state-at-suite-start.txt, full-test-sh.log, full-test-sh.start, full-test-sh.end;
- results: rebuild-requests.json, v2e-diagnosis-request-excerpt.json, differential-requests.json, api-contract-check.log, mutation-checks.log, checker-v2/.
