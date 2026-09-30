_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FaultLab independent verifier report: Learn-loop limits after live run v2d (September 30, 2026)

VERDICT: READY_WITH_NOTES. Every fixer claim I checked holds. All 10 findings are fixed as described, the gates are unchanged, and the full offline suite passes. Nothing I found blocks a commit. The notes are one open PM decision, two test-coverage gaps, two small wording or display points, and two procedural disclosures of my own.

Cost: $0. I made no provider, model, W&B, Weave or other network call. Every verifier script ran under my own guard (verify/vguard.py). It refuses non-loopback sockets and name lookups, and refuses opens of .env, audit/promotion.json, audit/final-audit*.json and artifacts/heldout2/. Every guard line reads 0 refused connects, 0 refused lookups and 0 refused protected opens. The only exception is the one intended refusal described in section 4. During scripts/test.sh, a one-second lsof monitor of the suite's process tree (1,020 samples) saw 0 non-loopback connections.

Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-loop-limits-2026-09-30/verify/

==================================================
1. GIT STATE AND TEST SUITE
==================================================
Git state is the same before, after the suite and at the end (git-state-start.txt, -after-suite.txt, -end.txt):
- HEAD is main at cbbf957e6e1c.
- backup/part2-2026-09-22 is at 3b31b583cc4b.
- .git/index mtime is 2026-09-27 15:18:04, and the index sha256 is unchanged.
- There are 0 stash entries, and the hash over all refs is unchanged.

I used only read-only git commands, with GIT_OPTIONAL_LOCKS=0. The commit-list script used a throwaway index outside the Desktop.

Working tree against the backup, compared by blob hash (tree_vs_backup.py):
- 16 files changed, 10 added, 0 missing.
- Every file has the sha256 the fixer recorded (fixer/source-sha256-at-suite-start.txt).
- The tree was the same at start, after the suite and at the end.

Saved stores:
- I found 11 lab stores under /Users/shree/FaultLab_Runs; the fixer tracked 8 of them.
- All 11, main file plus WAL, are unchanged from start to end (saved-stores-sha256-start.txt and -end.txt).

scripts/test.sh ran once, 09:46:51 to 10:05:17 UTC (full-test-sh.log). Exit 0, and all four stages PASSED:
- **Backend:** 2,949 passed, 180 skipped, 0 failed, 2 known warnings (the starlette BlockingPortal alias and the os.fork note in test_ownership), 1,069 s.
  - This is exactly the fixer's count.
  - The 39 loop-limit cases passed.
  - The saved-store v2d test ran; it was not skipped.
  - test_native_adapter_v1_golden.py passed (4 tests).
- **Frontend unit:** 353 passed (25 files).
- **Build:** passed. The only message was the chunk-size advisory.
  - tsc -b uses a build-info cache, so I also ran a full type check with no cache (tsc --noEmit --incremental false) in a scratch copy of the frontend: 0 errors.
- **Browser:** 19 passed, 1 opt-in skip. The loop-limits browser test passed.

==================================================
2. IDENTITIES AND PROTECTED FILES
==================================================
I computed identity with the product's own functions on two trees: the working tree, and a git-archive checkpoint of 3b31b58 kept outside the Desktop (identity/identity.py, backup.json, current.json, compare.txt).

Changed from the backup:
- runtime: ee2d1df9… → f058c03c53b6442cd1c3d308d46007af8b755af0478595d57b964261aa17677a
- algorithm: ab296a32… → a08a8d6186419dc288485db1509021d87ead43e785c5cd5b8dd5d64b4bb2ec8a
- reference Actor source (a tree hash over backend/app/agents): 2597bffb… → fb5e1894…
- new declarations: mechanic_context 11bf9e32… and challenge_selection 802e3954…

Unchanged:
- service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…, capability 8e8e04af…
- native v1 adapter 6f303264… and prompt 2251542869cf3e0fb841e536f56c8d2780f77e852d91ae30e12d4edf3e4c4989
- native v2.1 adapter dfd41b33…, prompt fff397c9282b10c108c1df65aef9090c53b40c20973698888152519757264e1c, and protocol v2.1-shown-order-labels
- reference Actor prompt 12eabe7f… and reference adapter 0cd810b7…
- both transport-retry declarations
- the discovery protocol declarations (v1, v3, v4 hashes identical; v2 and v3-precheck raise the same error in both trees with default caps)

My working-tree values equal the fixer's identity-final.json on all 21 shared keys.

Byte-identical to the backup (git blob hash):
- backend/app/lab/challenge.py, promotion.py, evaluation.py, diagnosis.py, reachability.py
- backend/app/agents/mechanic.py and prompts/actor.md
- backend/app/contracts/tokens.py
- backend/app/integrations/external_agent.py (native v1)
- By the tree comparison, every other file outside the 26 listed, including the simulator, contracts and discovery code.

==================================================
3. GATE FREEZE (the repo's own scripts/experiments/gate_freeze.py)
==================================================
I loaded gate_freeze.py from the checkpoint copy, which is byte-identical to the working copy. I dropped audit/promotion.json and audit/final-audit.json from its file list so neither was opened. I ran it on the backup checkpoint and on the working tree (gate_freeze/compare.txt).
- Functions: 30 of 30 identical.
- Files: 20 of 20 identical.
- Fingerprints: only algorithm_hash, runtime_hash, source_hash and tree_lab changed.
- tree_referee, scorer_hash, service, contract, interpreter, adapter, actor prompt, telemetry and dependency lock are identical.

gates_unchanged = true.

==================================================
4. SPOT-CHECKS OF EACH FIXED FINDING
==================================================
**Scratch method.** All my test runs, probes and negative controls used a scratch tree outside the Desktop: the 3b31b58 checkpoint plus the 26 working files, with backend files byte-compared to the working tree.
- So I never copied or modified the working checks.py or any product file.
- Tests that build run plans read audit/promotion.json through the product's own code. Under my guard in the scratch tree, those runs used a synthetic stand-in manifest (spot/vstub.py, spot/vstub_contract.py), so that file was never read.
- The real suite (section 1) used the real file, as it always does.
- The scratch folder is deleted.

**I-HIGH-1 and P-HIGH-1 (rule 2 withdrawn): FIXED.**
- New Learn plans and run options no longer carry challenge_selection.
- validate_run_plan refuses a plan that declares it. It runs at creation (inside the creation transaction, so a refused plan leaves nothing behind) and at Start.
- A saved plan that declares it still reads, because the check is not in _bindings.
- My probe A (spot/test_verifier_probes.py) runs the integrity scenario:
  - with the rule declared, the challenge ends PASSED_OBSERVED with no failed checks;
  - without it, COUNTEREXAMPLE_FOUND ['C4'].
  So the withdrawal is what restores detection.
- Probe D reads a new Learn plan back through the real API: Mechanic rule only.

**I-MEDIUM-2 and P-MED-1 (docs, cause, both-arms reason, option b): FIXED.** I checked the claims myself on a read-only copy of the v2d store (spot/v2d_store_check.py, v2d-store-check.json). All match the corrected docs:
- **Source-validation calls:** the agent called only get_order and update_order; the policy alone read the orders status. The rule would refuse 3 of 5 tool/service pairs.
- **Pick 3:** one F4 on the orders status and no other fault. It fired in 1 of 3 incumbent and 0 of 3 candidate episodes, with no candidate-policy reads, and the incumbent skipped the read in 2 of 3.
- **Pick 2:** the candidate's agent read the orders status 4, 4 and 3 times.
- **Across the 9 candidate episodes:** orders status in 4, send_confirmation in 6, notifications status in 1.
- **Tokens:** the request rebuilds to 33,223. The challenge evidence table adds 12,047 and development evidence 11,030. The challenge feedback adds 14,136 with the key removed (14,129 when set to an empty list).
- **Doc edits:** the v2d write-up only gains an appended correction; its original text is unchanged. CURRENT_STATUS marks its correction inline. The prompt section and the rule text give the both-arms reason. 814a6e3, named in CURRENT_STATUS, is an ancestor of the backup tip.

**I-LOW-1 (VIOLATION outcome kept): FIXED.** _row_failed counts outcome == 'VIOLATION'. Test present, and the mutation is caught.

**I-LOW-2 (policy and purpose in the grouping): FIXED.** _trial_facts adds policy_hash and experiment_purpose. Mutations removing either one are caught.

**I-LOW-3 (NO_CHANGE naming; FORMAT_REPAIR only when the first answer is saved): FIXED.**
- search_ended_note names at most 3 record IDs. Probe C: the longest reason, over 1 to 12 ended searches, is 390 characters, within the 600 limit and accepted by the Campaign model.
- record_refusal uses a record-row cutoff taken before the request.
- Probe B: an earlier request's two answers are saved, then a later first turn is refused. It is correctly recorded BEFORE_SEND, nothing extra is written, and it does not use a candidate request.

**P-LOW-1 (group_example and "can differ" wording): FIXED.** Mutations of the key and of the text are caught.

**P-LOW-2 (dashboard texts): FIXED.** 7 of 7 frontend negative controls caught (spot/frontend-mutations.log):
- the FORMAT_REPAIR text and its badge;
- badge capitalisation;
- the "in full" line appearing for an unsent request;
- a refusal stated twice;
- the setup form speaking about the rule that is not offered;
- the undeclared challenge rule claiming the plan was "saved before" it.

**P-LOW-3 (rejected candidate record for a refused repair turn): FIXED.** It mirrors the invalid-answer path: rejected_raw plus a REJECTED campaign_proposals row linking the saved first answer and the size record. Mutation caught.

**Rule 1 core.** An unfit request that raises instead of ending the search is caught. An older plan keeps ERROR(INPUT_LIMIT) (test present).

**Backend negative controls** (spot/mutations.py, mutations.log): 16 of 17 caught, every file restored with a sha256 check, and the unmutated run passed. The one not caught is gap b under open point 2 below, a coverage probe beyond the fixer's claim.

**API contract** (spot/api_contract_check_verifier.py, my adapted copy of the fixer's script, api-contract-check.log). The dashboard's own validators (vitest) accept the real API responses:
- run options without challenge_selection;
- a new plan with the Mechanic rule only;
- an older plan;
- a plan declaring the withdrawn rule (Start refuses it);
- all four request-size record kinds;
- an older campaign with no extra keys.
My first attempt got 403 HOST_NOT_ALLOWED on every route, because my guard did not set FAULTLAB_ALLOWED_HOSTS the way tests/conftest.py does. That is a harness difference, not a product problem. The log is kept as api-contract-check.run1-host-not-allowed.log, and the re-run passed.

==================================================
5. NEW TESTS AND GIT-IGNORED FILES
==================================================
**Backend: no git-ignored repo file is used.** The three new backend test files pass in the scratch tree (39 of 39), which holds only tracked backup files plus the 10 added files. The only git-ignored paths in the open log are .pyc cache lookups, which are not dependencies. Opens recorded during that run (ignored_deps/backend-opens-classified.txt):
- tracked files, including the tokenizer under contracts/tokenizer, and the added files;
- the .venv;
- pytest temp folders;
- the read-only v2d store under /Users/shree/FaultLab_Runs. That store is outside the repo, the test skips when it is absent, and it copies the store with mode=ro&immutable=1 into pytest's temp folder.

**Frontend: no ignored files.** The two new tests import only tracked sources and fixtures (src/*, tests/fixtures.ts, tests/run-fixtures.ts, src/generated/contracts.ts). The browser test's one readFile reads Playwright's downloaded recording from a temp path.

==================================================
6. COMMIT LIST
==================================================
Files, all in the verify folder:
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-loop-limits-2026-09-30/verify/COMMIT_LIST.txt ('<sha256>  <path>', 260 lines)
- COMMIT_LIST_NOTES.txt
- COMMIT_LIST.json (per-path status, backup sha256, ignored flag)

Contents and base:
- **Base:** backup/part2-2026-09-22 at 3b31b58. Commit on top of it, not on main (cbbf957).
- **26 product files:** 16 modified, 10 new, none deleted, no mode changes. The new files are not git-ignored.
- **234 evidence files:** everything under artifacts/product-loop-limits-2026-09-30/ (builder, review-integrity, review-product, fixer, verify). These are git-ignored and need `git add -f`.
- **Excluded:** nothing inside the evidence folder needed excluding (no caches, SQLite, files over 5 MB, symlinks, checks.py or protected copies, or .env names). The list's own files are left out.
- **Protected paths** were never read by the list script; only their size and mtime were recorded.

Checks on the list:
- The 26 product lines are identical in pass 1 (during the suite) and the final pass.
- `shasum -a 256 -c` gives 260 of 260 OK.
- Credential scan: 0 hits in 260 files. The scanner is self-tested; it flags the known dummy key in a test file.
- Conflict copies: 0 conflict-like names outside artifacts/. The only hits in this round's folder are my own conflict_scan.py and conflict-scan.txt, whose names contain "conflict".

==================================================
7. NOTES (why READY_WITH_NOTES)
==================================================
1. **Open PM decision:** keep rule 2 withdrawn (the fixer's recommendation), or ask for a design that does not depend on the candidate. Withdrawal restores today's challenge behaviour exactly, and its dormant code cannot run for any new or startable plan.
2. **Test-coverage gaps.** The code is correct in both cases:
   a. The record-row cutoff in loop_limits.first_turn_output. A mutation that ignores it passes both of the fixer's first-turn tests; only my probe B catches it. Consider adding probe B (spot/test_verifier_probes.py) as a product test.
   b. Stage 1's identity key includes the trial facts (arm, outcome, policy, purpose), but no test fails if they are removed from that key.
3. **Minor wording:** the one-line rule text on the setup form and saved plan (mechanicContextText) lists "every episode with a failed check" but not "or a VIOLATION outcome". The backend rule and the "Exact rule text" include it.
4. **Theoretical display point:** a COMPACTED record is saved with provider_dispatch true just before sending. If the Mechanic's own check then refused that first turn (possible only if the two token counts disagreed, and they are identical by construction), the panel would show "Compacted and sent" next to "not sent" for the same request.
5. **Store tracking:** the fixer tracked 8 saved stores; there are 11. All 11 are unchanged.
6. **My own procedural disclosures:**
   a. Once, I byte-compared the working backend/app/referee/checks.py with the backup checkpoint copy using `cmp`, which printed only "same bytes: yes". That opened the file outside the repo's own identity or gate-freeze code; its content was never displayed. gate_freeze separately confirms scorer_hash and tree_referee are unchanged.
   b. The checkpoint tree held the backup's checks.py blob, extracted with git archive. It was outside the Desktop and is deleted.
   c. My scratch folders under /Users/shree/FaultLab_Scratch are deleted, and real node_modules caches were not written.

**Next steps:** the PM decides on rule 2, then a commit with the owner's OK on top of 3b31b58 using COMMIT_LIST.txt. Register every agent again (the reference Actor source hash changed), then a declared live Learn run.
