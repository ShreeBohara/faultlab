_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FaultLab independent verifier report: history fireability for Explorer picks (faultlab-explorer-selection/v3-history-fireability) and evidence retry v3, after the fixer. September 30, 2026.

VERDICT: READY_WITH_NOTES. I checked the fixer's claims against the code and evidence, and every one I checked holds. The rule change from "any fault" to "every fault" is in the code, the saved-plan model, the dashboard validator, the rule text and all the docs, and they all agree. The gates are unchanged. The one full offline suite passed, with exactly the fixer's counts. My own 23 negative controls were all caught. Nothing I found blocks a commit. The main note is a decision, not a defect: the owner must sign off on the any→every change, because it departs from the task's wording.

Cost: $0.
- No provider, model, W&B, Weave or other network call was made.
- Every verifier Python script ran under my guard (verify/vguard.py). It refuses non-loopback connects and name lookups, and refuses opens of .env, audit/promotion.json, audit/final-audit*.json and artifacts/heldout2/. Every guard line reads 0 / 0 / 0.
- During scripts/test.sh, an lsof monitor took 1,076 one-second samples and saw 0 non-loopback connections (verify/net-monitor.log is empty).

I wrote no REPORT.md. This text is the report. Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-fireability-2026-09-30/verify/

==================================================
1. GIT STATE AND THE TEST SUITE
==================================================
Git state is the same at start, after the suite and at the end (verify/git-state-start.txt, -after-suite.txt, -end.txt):
- HEAD is main at cbbf957.
- backup/part2-2026-09-22 is at 432e54b.
- .git/index sha256 is e253a478… (unchanged; mtime still 2026-09-27 15:18:04).
- 0 stash entries, and the hash over all refs is unchanged (984ec87c…).
- 0 files are staged. I used only read-only git with GIT_OPTIONAL_LOCKS=0.

Working tree against 432e54b, by blob hash (verify/tree_vs_backup.py):
- 25 files changed, 8 added, 0 missing: exactly the fixer's set.
- The tree was identical at start, at suite start, after the suite and at the end.
- I re-hashed all 591 paths in fixer/source-sha256-after-suite.txt (checks.py left out). All are identical to the fixer's end state.

scripts/test.sh ran once, 15:46:44Z to 16:06:10Z, exit 0 (verify/full-test-sh.log, .start, .end). scripts/test.sh is byte-identical to the backup.
- **Backend:** 3,038 passed, 180 skipped, 0 failed, with the 2 known warnings (the starlette BlockingPortal alias and os.fork in test_ownership). This equals the fixer's count.
  - test_history_fireability.py: 22 of 22, none skipped, so the saved-store tests ran;
  - test_history_fireability_review_fixes.py: 11 of 11;
  - test_evidence_retry_v3.py: 5 of 5;
  - test_evidence_wait.py: 24; test_discovery_v3_flow.py: 15;
  - test_native_adapter_v1_golden.py: 4 of 4.
- **Frontend unit:** 368 passed, in 28 files.
- **Build:** passed; the only message is the chunk-size advisory. I also ran a full no-cache type check (tsc --noEmit --incremental false) in the scratch tree: exit 0 (verify/spot/frontend-tsc-nocache.log).
- **Browser:** 19 passed, 1 opt-in skip.

Saved stores: all 564 store files under /Users/shree/FaultLab_Runs (lab stores with -wal/-shm, plus world stores) are unchanged from start to end. native-v2b lab.sqlite3 is still cc2da5ef…, and its -shm and -wal are unchanged.

==================================================
2. IDENTITIES AND PROTECTED FILES
==================================================
I computed identities with the product's own functions on two trees (verify/identity/identity.py, backup.json, current.json, compare.txt):
- a git-archive checkpoint of 432e54b outside the Desktop, archived with audit/promotion.json and audit/final-audit.json excluded, so they were never extracted;
- the working tree.

Changed from the backup:
- runtime 95042e4d… → 49958e716f0b08aacb9db5d6ddf99620451f949a901aa35cca979918c1df6b6e;
- algorithm 4e5a8f90… → 7a56afed3dfe4d3236a4b01fe08bafe915c810d7a6ad653971bea0e911401a13;
- the reference Actor source hash fb5e1894… → 7f78de28…. This is a tree hash over backend/app/agents, which holds the builder's explorer.py change. actor.py, reference.py and every prompt file are byte-identical.
- both example configuration hashes (v1 616014f7…, v2 3f626e5f…);
- new: fireability declaration ae56a27a…, evidence retry v3 declaration b76d6d5c….

Unchanged:
- service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…, capability 8e8e04af…
- native v1 adapter 6f303264… and prompt 2251542869cf3e0fb841e536f56c8d2780f77e852d91ae30e12d4edf3e4c4989
- native v2.1 adapter dfd41b33…, prompt fff397c9282b10c108c1df65aef9090c53b40c20973698888152519757264e1c, and protocol 01366047… (v2.1-shown-order-labels)
- native source 2867b3fb…
- reference Actor prompt 12eabe7f… and adapter 0cd810b7…
- evidence retry v2 declaration 3d849893… (it equals the backup's only declaration)
- both transport-retry declarations, mechanic-context v2, challenge-selection v2, citation-status b84f55db…, and V2_MEMORY
- all discovery declarations (v1, v3, v4 hashes identical; v2 and v3-precheck raise the same error in both trees)
- the Explorer's prompt constants (hash 3bb87d64… in both trees): the system prompts did not change.

Other identity checks:
- All 28 keys I share with the fixer's identity-final.json are equal (identity/compare-with-fixer.txt).
- Identity recomputed at the end equals the start: 38 of 38 keys (identity/end-check.txt).

Byte-identical to 432e54b by git blob (verify/protected/byte-identity.txt):
- lab: challenge.py, promotion.py, evaluation.py, diagnosis.py, reproduction.py, reachability.py, loop_limits.py, policies.py, policy_interpreter.py, discovery_protocol.py, completion_study.py, baseline_study.py, history_replay.py, storage.py, runner.py, evidence.py, citation_status.py and configuration.py;
- agents: actor.py, reference.py, mechanic.py, transport_retry.py and all 10 prompt files (actor.md included);
- the three integrations files and contracts/tokens.py;
- the v1 golden test, scripts/test.sh and gate_freeze.py.

Whole folders are identical, with 0 extra working files:
- backend/app/referee (6 files; checks.py only through gate_freeze);
- backend/app/simulator (8), contracts/ (100), backend/app/contracts (5), backend/app/integrations (7) and backend/app/telemetry (9).

The only changed file under backend/app/agents is explorer.py: the builder's fireability hook, which the fixer did not touch.

Old plans behave as before:
- I re-ran the builder's history differential under my guard (spot/history_differential_verifier.py). On every saved store, 35 of 35 history computations are equal between the backup's agent_history.py and the refactored one. used_episodes matches 35 of 35, and 6 of 6 saved-plan verifications agree. The output equals the builder's, apart from the path of the backup module.
- On the native-v2b copy, no saved plan carries the new block (old_plans_have_block = false).
- The pinned v1/v2 Explorer digests in test_discovery_v3_flow.py are unchanged lines and pass.
- The edits to two existing tests change only new-plan assertions:
  - test_evidence_wait.py: new plans declare v3, and the flaky-batch test now runs on a v2 plan;
  - test_discovery_v3_flow.py: the fireability keys are stripped before the v1-equivalence comparison, and their presence is asserted only for v3-history.

==================================================
3. GATE FREEZE (scripts/experiments/gate_freeze.py)
==================================================
I ran the repo's gate_freeze.py, loaded from the checkpoint copy (byte-identical to the working copy), on the 432e54b checkpoint and on the working tree. promotion.json and final-audit.json were dropped from its file list (verify/gate_freeze/compare.txt).
- Files: 20 of 20 identical.
- Functions: 30 of 30 identical. These include summarize_evidence, trial_outcomes, assess_pairs, promotion_decision, paired_complete, valid_trial and checks.score.
- Fingerprints: only algorithm_hash, runtime_hash, source_hash and tree_lab changed.
- Unchanged fingerprints: actor_prompt, adapter, contract, dependency_lock, interpreter, scorer, service, tree_referee and tree_telemetry.
- My working-tree output is identical to fixer/gate_freeze/after-fix.json.

gates_unchanged = true.

==================================================
4. SPOT-CHECKS OF THE FIXED FINDINGS, AND THE RULE'S FINAL STATUS
==================================================
**Final status: SHIPPED, with the fixer's change.** Code, model, dashboard and docs agree:
- fireability.decide refuses a pick only when every distinct target is REFUSED.
- The declaration carries pick_refused_when: every_fault_on_a_refused_target.
- ExplorerSelectionPlan accepts only that literal, and Start refuses any other frozen rule.
- The frontend validator accepts only that value, rejects a refusal that has a non-REFUSED target, and accepts an allowed pick beside a REFUSED target only with a reason.
- RULE, MEANING, REPLAN_INSTRUCTION and EXPLORER_NOTE, the design note (status line, sections 2.2, 5 and 8), CURRENT_STATUS, the user guide and the v2 run note all say "every".
- The rule is frozen only into new Learn plans with discovery v3-history or v4-history-replay.
- CURRENT_STATUS and the design note both say it is not committed, not run live, and needs the owner's sign-off.

**MEDIUM-1 / F1: FIXED.** My own probe (spot/rule_probe.py, rule-probe.json, 36 of 36 checks passed) uses a synthetic table with two REFUSED rows. For both challenge and discovery:

| pick | decision |
|---|---|
| lone status read | REFUSED |
| pending upgrade + status read (either order) | ALLOWED, with a reason naming the REFUSED row |
| two faults on two different REFUSED targets | REFUSED |
| two faults on the same REFUSED target | REFUSED |
| REFUSED target + a target not in the table | ALLOWED |
| allowed target only, or target not in the table only | ALLOWED, no reason |
| invalid answer | INVALID_OUTPUT, never guessed |

The probe also confirmed:
- A refused challenge pick makes the next request its re-plan (slot_request 2, replan_of set).
- A refused re-plan gets no further re-plan.
- A second challenge in the same Session starts clean.
- The model and fireability.verify refuse "any_fault_on_a_refused_target", a missing field, and other values.
- RULE is 2,225 characters (the model limit is 2,400) and MEANING is 587 (limit 800).

The integrity reviewer's demo, rerun on the fixed code under my guard (spot/demo_rerun_verifier.py, demo-rerun-verifier.json), gives output identical to fixer/demo-rerun-after-fix.log:
- Scenario A, pending upgrade + status read: COUNTEREXAMPLE_FOUND (C4, 1 schedule, 6 episodes), both with and without the rule. The builder's rule gave PASSED_OBSERVED here.
- Scenario B, lone status read: INCONCLUSIVE without the rule. With it, the pick is refused, then 4 allowed picks run, and the challenge ends PASSED_OBSERVED (4 schedules, 24 episodes, 5 requests).

**Saved store: CONFIRMED.** I re-ran the saved-store check under my guard, with a synthetic promotion-manifest stand-in so audit/promotion.json was never opened (spot/saved-store-check-verifier.json, saved-store-compare.txt).
- The table is identical to the fixer's, including its hash ee7cfed0…. F4 on the orders get_operation_status read is 0 of 4 and REFUSED; every other row fired in all its episodes.
- The 4 history episodes behind that row are identical to the fixer's.
- 3 of 11 challenge picks and 7 of 15 discovery picks are refused, and every decision is equal by selection id.
- Every saved pick has a single fault, so 0 saved picks mix the status read with another target.
- A v3-history plan freezes the same rows.
- The store is unchanged, and the scratch copy was deleted.

**F2: FIXED.**
- Every request under the rule carries history_fireability.note (probe; mutation M4).
- The budget and dispatch texts say "one re-plan per pick refused by history fireability" (FM5).
- The system prompts are unchanged (identity).

**F3: FIXED.**
- campaign_decisions reads selections through record_fields_upto (three fields) and then only the matching ids. It reads this campaign's challenges through challenge_campaigns, and its slots are filtered in SQLite.
- The experiments endpoint reads the plan with no counterexample only if the saved plan record has explorer_selection. The plan serializer omits the key for every other plan, so the check is sound.
- Mutations M5 and M6 are caught.

**F4: FIXED.** "Re-plan." prefix (FM4), the REFUSED row highlighted (FM8), and the rule id beside the cap (FM7). The pinned texts in evidence-wait.test.tsx changed only by adding "under rule …".

**LOW-2: FIXED.** R4, R15 and R16 are pinned by tests (my M7, M8 and M9 are caught).

**LOW-1, LOW-3 and F5 (docs): FIXED as described.**
- The design note, CURRENT_STATUS and the user guide state the "not neutral" limit and how a refused row can change.
- They state the v2f waits exactly and say "the same rows" with a different cutoff and hash.
- The 19-of-19 pending-upgrade status reads match review-integrity/status-read-exposure.json.

**The fixer's own evidence is consistent:**
- tests-before-fix.log shows 7 failed, 25 passed, and the 7 are exactly the named tests.
- frontend-tests-before-fix.log shows 6 of 6 failed.
- mutation-checks.log shows 18 of 18 caught, all restored.

**My own negative controls** (spot/mutations.py, mutations.log) are written from the claims, not copied from the fixer. They ran only in a scratch tree: 432e54b plus the 33 files, with a private copy of node_modules. The unmutated runs passed before and after (77 backend, 18 frontend). Every file was restored with a sha256 check (33 of 33 OK). **23 of 23 caught:**
- M1: the "any" rule restored.
- M2: the declaration field removed.
- M3: the model accepts any string.
- M4: the note dropped.
- M5: full selection scan.
- M6: plan validated on every poll.
- M7: ids-hash binding removed.
- M8: challenge state never reset.
- M9: a missing execution counts as fired.
- M10: a refused re-plan gets another re-plan.
- M11: challenge picks unchecked.
- M12: v4 plans don't freeze the rule.
- M13: threshold 1/3.
- M14: new plans declare evidence retry v2.
- M15: the evidence cap read from the constant instead of the plan.
- FM1–FM8: the frontend validator in both directions, pick_refused_when, "Re-plan.", "no re-plans", the refused-alone paragraph, the rule id beside the cap, and the row highlight.

==================================================
5. NEW TESTS AND GIT-IGNORED FILES
==================================================
**Backend: no ignored or untracked file is needed.** In the scratch tree (432e54b tracked files plus the 33 files, no audit/promotion.json or final-audit.json, and the vstub stand-in for the promotion manifest), these ran together: test_history_fireability.py, test_history_fireability_review_fixes.py, test_evidence_retry_v3.py, test_evidence_wait.py, test_discovery_v3_flow.py and the v1 golden test. **81 passed, 0 skipped.**

An audit hook recorded every opened path (ignored_deps/backend-opens-classified.txt):
- 13 of the 33 files;
- 206 tracked 432e54b files;
- 0 opened tree files matching a .gitignore pattern;
- the .venv, the Python install, and pytest temp folders;
- 131 relative dir_fd names from temp cleanup;
- no Desktop path other than the hook's own output file.

The saved-store tests open /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 through SQLite, outside the repo. They copy it with mode=ro&immutable=1 and skip if it is absent.

**Frontend: no ignored files.** history-fireability.test.tsx, history-fireability-fixes.test.tsx and evidence-wait.test.tsx passed 18 of 18 in the scratch tree. Every source and fixture they import is tracked in 432e54b or is one of the 8 new files, and none is git-ignored.

==================================================
6. COMMIT LIST
==================================================
Files:
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-fireability-2026-09-30/verify/COMMIT_LIST.txt (285 lines, '<sha256>  <path>')
- COMMIT_LIST_NOTES.txt
- COMMIT_LIST.json

Contents and base:
- **Base:** backup/part2-2026-09-22 at 432e54b. Commit on top of it, not on main (cbbf957).
- **33 product files:** 25 modified, 8 new, 0 deleted, 0 mode changes. The new files are not git-ignored. The product lines are identical in pass 1 and the final pass.
- **252 evidence files:** everything under artifacts/product-fireability-2026-09-30/ (builder, review-integrity, review-product, fixer, verify). They are git-ignored and need `git add -f`.
- **Excluded, as in earlier rounds:**
  - review-product/api-differential/backup.json and build.json, each 7.9 MB (over the 5 MB rule);
  - COMMIT_LIST.txt and .json themselves;
  - secret_scan_final.txt and shasum-check.txt, written after the final pass.
  - There are no symlinks, caches, SQLite files or tree copies in the folder.
- **Protected paths** were never read by the list script; only their size and mtime were recorded.

Checks on the list:
- `shasum -a 256 -c` gives 285 of 285 OK.
- Credential scan, pass 1: 0 hits in 273 files. Final: 1 hit in 285 files. That hit is the scanner's own self-test output (commit_list/secret_scan_selftest.txt), which quotes the masked known dummy key from backend/tests/test_providers.py. It is not a credential.
- Conflict copies: 0 conflict-like names outside artifacts/. The only hits in this round's folder are my conflict_scan.py and conflict-scan.txt.
- The scratch folder /Users/shree/FaultLab_Scratch/verify-fireability was deleted, and /Users/shree/FaultLab_Scratch is empty.

==================================================
7. NOTES (why READY_WITH_NOTES)
==================================================
1. **Owner decision, needed before commit.** The shipped rule refuses a pick only when every fault is on a REFUSED target. This departs from the task's "if any of its primitives targets…". The change is well-founded, because the "any" form hid a real counterexample (Scenario A). It is implemented and documented consistently.
2. **Remaining limits** (disclosed in design note section 5):
   - A lone pick on a REFUSED target never runs, so a mistake only such a pick could show is tested only if the Explorer pairs the target with another fault.
   - Mixed picks can still be untriggered and end INCONCLUSIVE.
   - The Explorer's precedence note is in the request context, not the system prompt, and is untested live.
   - The table is candidate-independent but not neutral.
   - Evidence retry v3's cap of 24 re-admits the 18-retry flaky-batch case.
   - The F3 poll still extracts three fields from every selection row. Keep the dashboard closed during paid runs.
3. **Register every agent again** before a live run: the runtime, the example configuration hashes and the reference Actor source tree hash changed. The actor code and prompts did not change.
4. **Cosmetic.** For a v1 evidence-retry plan the plan text now reads "(no campaign limit: an earlier rule that Start now refuses) under rule faultlab-evidence-retry/v1 (after …)", which is two parentheticals in a row.
5. **Procedural disclosures.**
   a. The builder's and fixer's source-sha256 lists include a plain sha256 of backend/app/referee/checks.py, made by their own hashing rather than the repo's identity or gate_freeze code. Its content was never shown. gate_freeze separately shows it is unchanged.
   b. I ran one recursive `grep -rn` over backend/app to find storage helper definitions. That read the bytes of checks.py, but only storage.py lines were printed and nothing from checks.py was shown. Later searches excluded it.
   c. scripts/test.sh, the product's own suite, loads the promotion manifest through product code as it always does. My own scripts used a synthetic stand-in (spot/vstub.py) and never opened audit/promotion.json, final-audit*.json or artifacts/heldout2.
6. **Next steps:**
   - the owner signs off on any→every;
   - commit on top of 432e54b using COMMIT_LIST.txt, with the owner's OK;
   - register every agent again;
   - run the declared live Learn run (native v2, v4 history replay, native-v2b), with the read-out in design note section 7. That read-out must list the refused targets and every refused pick, and say whether any challenge schedule faulted the orders status read.
