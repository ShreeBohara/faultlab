_Saved by the PM from the agent's returned text; content unedited._

FOLLOW-UP REPORT: DIAGNOSIS RULES, PM DECISION F4 AND PINNED SAVED-STORE TESTS (September 30, 2026). Cost $0. Everything ran offline.

SHORT VERSION
- (A) Done. The guide block's checks_note now holds the draft's two neutral sentences, copied exactly. The C6 sentence stays out. The block adds +608 tokens to each first turn (it was +569). The Rule 2 declaration hash is now def60594…. The new probe plan hash is 91ca47e4…. The harness sha256 is unchanged (b1eb7cda…). Rule 2 is still NOT offered (DIAGNOSIS_GUIDE_OFFERED = False).
- (B) Done. The two failing tests now read the saved native-v2b store at a fixed, recorded point: record cutoff 6748. That is where live run v2g's own saved plan froze its history. At that point every old expected number holds (30 episodes; 3/7 refused and 8/8 allowed picks). The rebuilt plan's history, replay list and table are byte-equal to v2g's saved ones.
- I searched every test for this pattern. Two more tests read the live store the same way, and I pinned them too. Controls: all 8 saved-store tests pass on a store grown by a synthetic later run, and the unpinned versions fail on it. All 11 product mutations were caught.
- scripts/test.sh exited 0 for the first time this round:
  - backend: 3,135 passed, 180 skipped;
  - frontend: 373 passed;
  - build: passed;
  - browser: 19 passed, 1 skipped;
  - network: 0 non-loopback connections.
- New runtime: 1abba8a6810b6bd6b47dd5887c6305052ca87d48660977fb6277a3ff81462b2f (algorithm 0b34473c…).
- Nothing was committed, nothing ran live and no git write command was used. No .env, checks.py, heldout2 or audit JSON was opened by me. The saved stores are byte-unchanged.

Evidence: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-diagnosis-rules-2026-09-30/followup/ (63 files, 1.2 MB, SHA256SUMS.followup.txt). The report below is also the only report; I did not write a REPORT.md.

(A) PM DECISION ON F4: THE TWO NEUTRAL checks_note SENTENCES ARE BACK

The text is exactly the draft's note with its middle (C6) sentence removed. A check against the prototype confirms this: guide-measurement.json has checks_note_equals_draft_minus_c6_sentence = true and block_equals_draft_block_minus_c6_sentence = true. The text is:
"Each episode's checks row gives the fixed checks by check_id and category; the checks field gives each check's public meaning. Explain each failed check from its own meaning."

Changes:
- backend/app/lab/diagnosis_guide.py:
  - new CHECKS_NOTE constant;
  - added to FIXED_TEXT, declaration() and block();
  - docstring states both PM decisions.
- backend/app/lab/run_plans.py:
  - DiagnosisGuidePlan gains one field, checks_note;
  - it is bound word for word through FIXED_TEXT, so a declaration without the note, or with the C6 sentence back, is refused.
- frontend/src/loopLimits.ts:
  - the declaration type and validator carry checks_note;
  - the one-line display says the meanings come "with a short note on reading them".
- Tests:
  - backend/tests/lab/test_diagnosis_rules.py:
    - GUIDE_TOKENS = 608.
    - T3 checks the note text exactly, checks that the C6 sentence appears nowhere, and adds the note to the "names no check" scan.
    - T1 refuses 13 text changes, including the full draft note, plus a declaration missing the note.
    - T9 checks that the prototype block minus only the C6 sentence equals the product block, and that 631 − 608 = 23.
  - backend/tests/experiments/test_diagnosis_probe.py: expects +608.
  - frontend/tests/diagnosis-rules.test.tsx: the fixture carries the note, and an empty note is refused.
- Docs: docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md (sections 3, 5, 6, 8, 9 and a new section 11) and CURRENT_STATUS.md.
- Two choices I made (tell me if you want either changed):
  - The declaration's `rule` sentence is unchanged. The draft's rule sentence did not list the note either.
  - The protocol id stays v1. The guide was never offered, and no saved plan declares it (the verifier found 21 of 21 saved plans without it).
  - interprets_checks stays False, because neither sentence names or explains a check.

Measured with the product code (guide-measurement.json):
- Tokens: +608 on each first turn, giving 9,598 / 9,696 / 10,247 / 10,402 / 9,960. The prototype adds +631; the C6 sentence is 23 of those tokens.
- Rule 2 declaration: 36ca790f… → def60594d4677b89c2450079896a3f8c0433f50dbbc51693beeb934b5130c789.
- Block sha256: dedf43f2d162296a2af114f90264aeaa6825ab609d7ba8a5be3388952c66b51c.

New probe dry run (followup/probe-dry-run.txt; run under a guard that refuses the network, .env and protected paths; 0 socket connects):
- Plan hash: 91ca47e4aad3529605a68017a42789f80d4701ed62c6170993d56ae7bc4e5e57. This supersedes the fixer's e66a67b3… and the builder's 9d5d3bd6….
- Harness sha256: b1eb7cdaf1490a459c26d36d0b8c16a5a585c663fee671f6ba90bb05e56b86ff (unchanged; the harness file was not edited).
- Calls: 100 first-turn + 40 repair = 140 (K=10 on each of 14 request keys). Temperature is 0, frozen from v2g's saved plan.
- Input tokens per request:

| request | CONTROL | GUIDE | REPAIR_TODAY | REPAIR_RULE1 |
|---|---|---|---|---|
| v2d-dev5 | 8,990 | 9,598 | – | – |
| v2e-dev5 | 9,088 | 9,696 | – | – |
| v2f-dev5 | 9,639 | 10,247 | 10,030 | 10,077 |
| v2g-dev5 | 9,794 | 10,402 | 10,153 | 10,200 |
| v2g-dev6 | 9,352 | 9,960 | – | – |

- Charge: maximum 140 × $0.04984 = $6.9776 against the $8 cap. The tighter bound is $2.9065 (was $2.9039). Network calls: 0.
- Written files: followup/probe-plan/plan.json (83f338cc…), requests.json (fb84bfdc…) and DECLARATION.template.json (d9245c8d…, whose plan_hash field is now 91ca47e4…), with SHA256SUMS.txt.
- The probe inputs are unchanged (probe-inputs/SHA256SUMS: 5 of 5 OK).
- Compared with the fixer's plan, only these differ (followup/probe-plan-diff-vs-fixer.txt): the five GUIDE requests (only their checks_note, and so their tokens and sha256), the Rule 2 declaration hash, the tighter bound and the plan hash. CONTROL and all four repair requests are byte-identical.

(B) SAVED-STORE TESTS PINNED TO A FIXED SNAPSHOT

Why the tests broke:
- The store only grows, and each new record gets a higher row number (LabStore.max_record_rowid). So "rows at or below N" is a fixed snapshot.
- I read the store's own records (inspect-store.json, from a read-only scratch copy). Live run v2g's saved plan (campaign-d8d1e8cc…) froze its history at record_cutoff 6748.
- At that cutoff its history has 30 verified episodes and composition 1 study / 18 + 2 learn / 12. Its fireability table equals the old expected table exactly.
- So the old numbers are exactly "the store as v2b-v2f left it", and v2g's own plan records that point.

Changes to backend/tests/lab/test_history_fireability.py (all 3 saved-store tests):
- saved_v4_plan builds the plan with the product's normal path, with one exception. While the plan is made, the single "now" read (store.max_record_rowid) returns 6748.
  - The test asserts that this read happens exactly once.
  - It asserts the plan's history has record_cutoff 6748 and v2g's summary hash d581867c…. If any older record is ever edited, the test fails loudly.
- Test 1 keeps every assertion: 30 episodes, the composition, the table, the refused-target sentence, and Start accepting the plan. It adds two things:
  - the plan's history, replay list and table must equal v2g's saved ones;
  - the "plans saved before the rule" loop now reads the 5 plans at the snapshot (v2b-v2f) and asserts there are 5. The old loop would also have tripped on v2g's own plan, which declares the rule.
- Test 2 reads the selections at the snapshot and keeps all its counts: (3, 7) refused, 8 and 8 allowed, and no mixed pick.
- Test 3 (the real loop) now uses the pinned plan and keeps its numbers: 2 replays, SKIPPED then SELECTED, fired share 0/4.

Other tests that read the live store the same way. I searched every test file for saved-store paths:
- test_diagnosis_rules.py T1 ("every saved native-v2b plan re-reads with no new keys") read every plan. A plan saved by this build declares Rule 1, so it would have failed after the next live run. It now reads plans at the store's reviewed end (row 8583) and asserts exactly the six campaign ids (v2b study, v2c, v2d, v2e, v2f, v2g).
- test_loop_limits_mechanic_context.rebuild_v2d_request matched challenge evaluations by candidate and incumbent hash across the whole store. A later campaign challenging an identical candidate would have changed the 33,223-token request. Its list reads now stop at 3022, the cutoff where v2e's plan froze its history (the store as v2d left it). Two tests use it: that file's v2d test and test_citation_status's v2d candidate test.
- Not changed, with reasons:
  - test_citation_status's v2e/v2d rebuilds read only those finished campaigns' own records.
  - Its new-plan test asserts nothing that depends on other records.
  - The artifacts/lab.sqlite3 probe tests already select by id or by a started_at cutoff (STORE_CUTOFF), and that store has not changed since Sep 27.
  - The JSON fixtures are static.
  - No frontend test reads a saved store.
- citation_status_saved.py, test_citation_status.py and fireability.py are byte-identical to 626bae4. Diffs of the two changed committed test files are in followup/saved-store-tests-diff-vs-626bae4.txt.

CONTROLS AND MUTATION CHECKS (followup/mutation-checks.log)
Setup: a scratch copy outside the Desktop, with audit/ and node_modules as symlinks, deleted afterwards (scratch-deleted.txt).

Unmutated copy: 104 backend tests pass, including all 8 saved-store tests with none skipped. The 5 frontend tests pass.

Snapshot controls:

| control | setup | result |
|---|---|---|
| S1 | 626bae4's unpinned tests on today's store | 2 failed: "assert 36 == 30" and "assert 14 == 8" (the old problem) |
| S2 | pinned tests on a store grown by synthetic records for a later live run (grow_store.py) | 8 of 8 pass |
| S3 | unpinned versions on the grown store | 5 fail |
| S4 | pinned fireability tests with the cutoff moved to today's store end, 8583 | 3 of 3 fail (a different summary hash) |

- The grown store added these records, all above row 8583:
  - a valid copy of v2g's plan that also declares Rule 1 (it reads as PLANNED);
  - a pick that mixes the status read with an update_order fault;
  - a copy of one of v2d's challenge evaluations under new ids, with evidence.
- The S3 failures: 36 == 30; True == False (the mixed pick); a plan carrying mechanic_diagnosis; and 34572 == 33223 twice.
- S4 shows that the snapshot, not a looser assertion, is what makes the tests pass.

Product mutations: 11 of 11 caught.
- (A), 5 mutations:
  1. the C6 sentence restored: 9 tests fail;
  2. the note left out of the block: 8 fail;
  3. FIXED_TEXT no longer binds the note: T1 fails;
  4. the note shortened: 8 fail;
  5. the dashboard validator skips the note: the frontend test fails.
- (B), 6 mutations, each with the saved-store tests that fail:
  1. fireability minimum 3 → 5: 5 fail;
  2. fired-share bar 1/2 → 0: 4 fail, including "ALLOWED == REFUSED_LOW_FIRED_SHARE";
  3. the agent history ignores its cutoff: 3 fail. The one-read assertion catches it first; Start's history check would also catch it.
  4. replay minimum 2 → 4: 4 fail;
  5. older plans gain a null mechanic_diagnosis: T1 and test 1 fail;
  6. the size-rule target +1000: the v2d test fails ([33611, 28056] ≠ [33611, 28056, 21101]), plus 6 others.
- After restoring every file, all 104 tests pass again.

Honest notes on the harness runs:
- Earlier runs are kept as mutation-checks-first-run … fourth-run.log.
  - Run 1 printed no failure messages.
  - Runs 2-4 had an incomplete synthetic plan (provenance, registration, then policy pointer missing). The unpinned T1 still failed in those runs, but with StoreConflict instead of the meaningful "new key" reason.
- I fixed grow_store.py, and the final run shows the real reason.
- The product-mutation results were identical in every run.

scripts/test.sh (run once after the last code change; followup/full-test-sh.log, 21:08-21:28 UTC, with a once-a-second lsof monitor): EXIT 0.

| stage | result |
|---|---|
| backend | 3,135 passed, 180 skipped |
| frontend | 29 files, 373 tests passed |
| build | passed (tsc -b + vite) |
| browser | 19 passed, 1 skipped |
| network monitor | 1,113 samples, 0 non-loopback |

- The verifier's run had 2 failed, 3,133 passed; the total is the same 3,135.
- The 2 backend warnings are the same pre-existing deprecation warnings as in the verifier's run.
- The code files' sha256 were unchanged during the suite. Only the docs were edited while it ran, and no test reads them.

NEW IDENTITIES (the product's own functions under the guard; followup/identity-compare.txt against the verifier's end state; rechecked after the suite and identical)
- Changed:
  - runtime: c80d8632… → 1abba8a6810b6bd6b47dd5887c6305052ca87d48660977fb6277a3ff81462b2f;
  - algorithm: 743a1520… → 0b34473c4db55d9c82fdb9479d6d2ed8a560c4df1f97db08e320da7680cc80df;
  - Rule 2 declaration: 36ca790f… → def60594…;
  - both example native configuration hashes: v1 19871b77…, v2 919ac780…. They embed the runtime fingerprint, so every agent must be registered again before a live run, as was already required.
- Unchanged, 45 values in all. These include:
  - service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…;
  - native v1 prompt 2251542869cf… and native v2.1 prompt fff397c9…;
  - reference source eaffac74…;
  - Rule 1 998744f8… / c4dd868c…;
  - PROTOCOL_HASH bfefe69b…, C1-C8 e792e8f0…;
  - all protected-file sha256.
- gate_freeze (run with the audit JSONs left out): against the verified state, only the algorithm, runtime and tree_lab fingerprints changed. All 20 files, including checks.py (hashed by gate_freeze only), and all 30 functions are identical.
- Byte identity against 626bae4: the protected referee, simulator, contracts, prompts, integrations and providers are unchanged. Only run_plans.py and test_history_fireability.py differ from the verified state.

RULES KEPT / STATE
- Git: HEAD cbbf957 on main, backup 626bae4; the index sha256 and mtime are unchanged, and the refs hash is unchanged from start to end.
- One lapse: at the very start I ran `git status --short` once without GIT_OPTIONAL_LOCKS=0. I checked that the index was not rewritten (same sha256 e253a478… and mtime).
- Saved stores: the 638 non-credential files under /Users/shree/FaultLab_Runs have identical sha256 at the start, before the suite and after it.
- The 11 control-capability files were never opened; only their size and mtime were recorded, and those are unchanged.
- Credential scan of followup/: no hits.

WHAT NEEDS DOING BEFORE A COMMIT
- verify/COMMIT_LIST.txt is now stale. These files changed:
  - diagnosis_guide.py, run_plans.py;
  - test_diagnosis_rules.py, test_diagnosis_probe.py;
  - loopLimits.ts, diagnosis-rules.test.tsx;
  - the doc and CURRENT_STATUS.md.
- Two committed files are now modified and must be added: backend/tests/lab/test_history_fireability.py and backend/tests/lab/test_loop_limits_mechanic_context.py.
- The followup/ evidence folder must be added too.
- The list with before and after hashes is in followup/files-changed-by-followup.txt.
- This follow-up has not been reviewed independently. The temperature question in the doc's section 5 is still open for the PM.
