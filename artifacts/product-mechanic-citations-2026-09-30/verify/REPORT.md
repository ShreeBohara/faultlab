_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FaultLab independent verifier report: native citation status (faultlab-mechanic-evidence/v2-native-citation-status), after the fixer. September 30, 2026.

VERDICT: READY_WITH_NOTES. Every fixer claim I checked holds. The 3 code fixes work, and my own negative controls catch each of them. The gates are unchanged, and the full offline suite passes. Nothing I found blocks a commit.

The notes are:
- a coverage gap in the misreading checker v2.1 (it misses real claims worded in the block's own "not decoded" vocabulary);
- one untested completeness check in the builder's code;
- one overstated sentence in CURRENT_STATUS;
- my own procedural disclosures.

Cost: $0.
- No provider, model, W&B, Weave or other network call was made.
- Every verifier Python script ran under my guard (verify/vguard.py). It refuses non-loopback connects and name lookups, and refuses opens of .env, audit/promotion.json, audit/final-audit*.json and artifacts/heldout2/.
- Every guard line reads 0 refused connects, 0 refused lookups and 0 refused protected opens.
- During scripts/test.sh, a one-second lsof monitor of the suite's process tree took 1,026 samples and saw 0 non-loopback connections (verify/net-monitor.log is empty).

I wrote no report .md file. This text is the report. Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/verify/

==================================================
1. GIT STATE AND THE TEST SUITE
==================================================
Git state is the same at start, after the suite and at the end (verify/git-state-start.txt, -after-suite.txt, -end.txt):
- HEAD is main at cbbf957e6e1c.
- backup/part2-2026-09-22 is at d38c0b8dd0ca.
- .git/index sha256 is e253a478… (unchanged), and its mtime is still 2026-09-27 15:18:04.
- There are 0 stash entries, and the hash over all refs is unchanged.

I used only read-only git commands, with GIT_OPTIONAL_LOCKS=0. The commit-list script used a throwaway index outside the Desktop and deleted it.

Working tree against the backup tip d38c0b8, compared by blob hash (verify/tree_vs_backup.py):
- 10 files changed, 7 added, 0 missing.
- The tree was identical at start, at suite start, after the suite and at the end.
- All 17 files have exactly the sha256 the fixer recorded (fixer/source-sha256-at-suite-start.txt).
- Against the builder's recorded state, exactly the 8 files the fixer named differ (verify/spot/builder-vs-fixer-files.txt).
- For citation_status.py I put the builder's null clause back into the current file and hashed it. That gives exactly the builder's sha256 (6c9c47e1…), so the fixer changed only MEANING there.

Saved stores:
- 43 files (11 lab stores, each with its -wal and -shm files) under /Users/shree/FaultLab_Runs are unchanged from start to end.
- My start hashes also equal the fixer's end hashes.

scripts/test.sh ran once, 12:04:08Z to 12:22:39Z (verify/full-test-sh.log, .start, .end). Its sha256 equals the backup's copy. It exited 0, and all four stages PASSED:
- **Backend:** 3,000 passed, 180 skipped, 0 failed, 1,072 s. There were 2 known warnings: the starlette BlockingPortal alias, and os.fork in test_ownership.
  - This is exactly the fixer's count.
  - test_citation_status.py passed 18 of 18. None were skipped, so the saved-store tests ran.
  - test_check_evidence_gap_misreading_v2.py passed 33 of 33.
  - test_native_adapter_v1_golden.py passed 4 of 4.
  - The loop-limits and native v2 test files passed.
- **Frontend unit:** 356 passed, in 26 files.
- **Build:** passed. The only message was the chunk-size advisory. tsc -b uses a build-info cache, so I also ran a full type check without the cache (tsc --noEmit --incremental false) in a scratch copy of the frontend: exit 0, 0 errors (verify/spot/frontend-tsc-nocache.log). The real tsbuildinfo was not written.
- **Browser:** 19 passed, 1 opt-in skip.

==================================================
2. IDENTITIES AND PROTECTED FILES
==================================================
I computed identities with the product's own functions on two trees: a git-archive checkpoint of d38c0b8 kept outside the Desktop, and the working tree. Files: verify/identity/identity.py, backup.json, current.json, compare.txt.

Changed from the backup:
- runtime: f058c03c… → 95042e4d9a67c739387a3841152bd7c23448f89cd5271ca32806552d6f3fc36c
- algorithm: a08a8d61… → 4e5a8f90cd97d33cc1b70560350dab023b052f8b0bab6b43c478054fdc345b6b
- new: citation-status declaration b84f55db3c3f52209c085dda799cdbd9edeef88f90ddced535afb1140828ca72
- new: memory text with the pointer, 75241be8…
- both example configuration hashes (v1: c1d533a9…, v2: ef89145f…). **Register every agent again** before a live run.

Unchanged:
- service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…, capability 8e8e04af…
- native v1 adapter 6f303264… and prompt 2251542869cf3e0fb841e536f56c8d2780f77e852d91ae30e12d4edf3e4c4989
- native v2.1 adapter dfd41b33…, prompt fff397c9282b10c108c1df65aef9090c53b40c20973698888152519757264e1c, and protocol 0136604… (v2.1-shown-order-labels)
- native source 2867b3fb…
- reference Actor source fb5e1894…, prompt 12eabe7f… and adapter 0cd810b7…
- V2_MEMORY 6cbe23d4… and v2-bounded 11bf9e32…
- challenge-selection 802e3954…
- both transport-retry declarations
- the discovery declarations: v1, v3 and v4 hashes are identical; v2 and v3-precheck raise the same error in both trees with default caps.

Other identity checks:
- My working-tree values equal the fixer's identity-end.json on all 27 shared keys.
- Identity recomputed at the end is identical to the start (identity/end-check.txt).

Byte-identical to the backup by git blob hash (verify/protected/byte-identity.txt):
- lab: challenge.py, promotion.py, evaluation.py, diagnosis.py, reproduction.py, reachability.py, loop_limits.py, policies.py, policy_interpreter.py and discovery_protocol.py;
- agents: mechanic.py, explorer.py and actor.py, and prompts/actor.md, mechanic.md and explorer.md;
- integrations: external_agent.py (native v1), external_agent_v2.py and registry.py;
- contracts/tokens.py;
- the v1 golden test.

Whole folders are identical too, with 0 working files absent from the backup:
- backend/app/referee (6 files; checks.py is compared only through gate_freeze);
- backend/app/simulator (8 files);
- contracts/ (100 files);
- backend/app/contracts (5 files).

Gate-frozen functions, compared by source text and by ast.dump (verify/protected/frozen-functions.txt): diagnosis.summarize_evidence, diagnosis.trial_outcomes and referee/diagnostics.classify_policy_gap are all identical.

Native v1 byte-identity: the golden test passes, and the v1 adapter and prompt hashes are unchanged.

Reference-agent and native-v1 Mechanic and Explorer views: I re-ran the builder's differential check under my guard (verify/spot/differential_requests_verifier.py). For the reference Actor, native v1, and a native v2 plan saved before the rule:
- every Mechanic request and every Explorer context is byte-identical after ID normalisation between the backup's learning.py and this tree's (6 of 6 scenarios);
- the positive control differs;
- the output equals the builder's recorded JSON exactly.

==================================================
3. GATE FREEZE (the repo's scripts/experiments/gate_freeze.py)
==================================================
I loaded gate_freeze.py from the checkpoint copy, which is byte-identical to the working copy. audit/promotion.json and audit/final-audit.json were dropped from its file list, so neither was opened. I ran it on the backup checkpoint and on the working tree (verify/gate_freeze/compare.txt):
- Files: 20 of 20 identical.
- Functions: 30 of 30 identical.
- Fingerprints: only algorithm_hash, runtime_hash and tree_lab changed.
- Unchanged fingerprints: actor_prompt, adapter, contract, dependency_lock, interpreter, scorer, service, source, tree_referee and tree_telemetry.

gates_unchanged = true.

==================================================
4. SPOT-CHECKS OF THE FIXED FINDINGS
==================================================
**MEDIUM-1 (checker v2.1): FIXED as described** (verify/spot/checker_probe.py, checker-probe.json).
- The script's sha256 is 11920882f8c7e9885242e455b7c37e3e8f8649d3bb1c86b927d6da5c07be3b7b, and its version string is v2.1-claim-shapes-and-denials.
- The self-test passes, with 50 phrase cases and 0 failures.
- All 20 review wordings, read verbatim from the reviewers' files, now score NOT_CHECKED.
- The reviewers' contract-gap-for-another-reason hypothesis scores NOT_CHECKED.
- The block's MEANING and MEMORY_POINTER sentences, read from citation_status.py by AST, are not claims.
- The CLAIM pattern still starts with v1's phrases.
- v1 has sha256 70c4eeda… in all five copies (v2b fixer, and the v2b, v2c, v2d and v2e run folders).

**LOW-1 (read-out labels): FIXED.**
- Without --read-out, the CLI exits 2 and writes no file. An invalid value also exits 2 and writes no file.
- With --read-out pre-registered, the output carries PRE_REGISTERED; with post-hoc, it carries POST_HOC.
- Every output carries read_out_note, checker_sha256 = 11920882… and human_confirmation_required = true.
- My re-run on the v2d and v2e exports is byte-identical (as JSON) to the fixer's two *-v2.1-POSTHOC.json files.
  - v2d: MISREADING on "cannot be decoded" and "never shown".
  - v2e: MISREADING on "never shown".
  - Each read 4 episodes, with 0 report IDs not recorded, 0 tokens not decoded and no denied matches.
- I read the three counted sentences myself. Each is a real claim of unshown or undecodable citations.

**LOW-4 (null clause): FIXED.**
- MEANING now ends "(all three are null when no complete native adapter v2.1 citation record was recorded for that episode)".
- That matches the code: citation_row returns nulls when there is no v2.1 protocol, when a list is missing, or when the lengths differ.
- The declaration hash is b84f55db….
- The dashboard's one-line text (loopLimits.mechanicEvidenceText) carries no null clause, so it needed no change.

**Re-measured sizes: CONFIRMED** (verify/spot/rebuild_requests_verifier.py, rebuild-requests.json, rebuild-compare.txt). I re-ran the fixer's rebuild under my guard on a read-only scratch copy of the native-v2b store. The copy was deleted afterwards. All 49 of the fixer's values are identical:
- **v2e diagnosis:** 9,088 → 9,434 tokens (+346); rows 5/5, 5/5, 6/6, 6/6.
- **v2d diagnosis:** 8,990 → 9,331 tokens (+341); rows 5/5, 6/6, 6/6, 5/5.
- **Both diagnoses:** 0 undecoded, and every other field unchanged.
- **v2d candidate request:** 33,223 → 34,806 tokens.
  - Compaction stages with the block: 35,194 → 29,639 → 22,684 (fits); without the block: 33,611 → 28,056 → 21,101.
  - The block is unchanged by compaction and keeps all 34 rows.
- **Provider counts:** I read the provider-reported input tokens from the copy's mechanic_outputs records instead of typing them in: 8,952 (v2e) and 8,854 (v2d). Both equal the fixer's typed values, so rebuilt − reported = 136 for both.
- **Excerpt:** the fake-ID excerpt is identical to the fixer's.

**Doc findings: FIXED as described.** These were LOW-2 (integrity), LOW-1 (product) and LOW-3 (product), plus the section 8 read-out steps for the deferred LOW-3 (integrity) = LOW-2 (product).
- CURRENT_STATUS states the builder's counts inline, the stale 2,965 line is gone, and "builder report" no longer appears.
- Note sections 4, 5 and 6–9 match the code and the evidence.
- UNFIT_REASON in the unchanged loop_limits.py lists the never-omitted parts without naming the block, as section 4 says.
- The two older docs only gain appended paragraphs; their original text is unchanged.

**Negative controls** (verify/spot/mutations.py, mutations.log). All ran in a scratch tree: the d38c0b8 checkpoint plus the 17 working files. The working tree was never mutated. The unmutated run passed 51 of 51 before and after, and every file was restored with a sha256 check. 12 of 13 were caught:
- V1: the builder's null clause restored;
- V2: bare "undecoded" counts again;
- V3: bare "not decoded" counts again;
- V4: denial rule off;
- V5: no clause boundaries;
- V6: denied matches counted in the verdict;
- V7: human_confirmation_required false;
- V8: --read-out optional;
- V9: read_out_status not written;
- V10: a wrong checker sha256 written;
- V11: the "were not decoded" claim-shape branch removed;
- V13: "no" dropped from the denial words.

The one not caught is V12, a coverage probe beyond the fixer's claim (note 2).

**Deferred items:** these are correctly marked DEFERRED, with read-out steps in note section 8:
- a product record that a Mechanic request carried the block;
- the frozen UNFIT_REASON wording;
- the paid paired probe.

==================================================
5. NEW TESTS AND GIT-IGNORED FILES
==================================================
**Backend: no untracked git-ignored file is needed.** In the scratch tree, which holds only backup-tip files plus the 17 files, test_citation_status.py, test_check_evidence_gap_misreading_v2.py and the v1 golden test passed 55 of 55. An audit hook recorded every opened path (verify/ignored_deps/backend-opens-classified.txt, opens-raw.txt):
- 7 opens of the 17 changed files;
- 213 opens of backup-tip tracked files;
- the .venv, the Python install, and pytest temp folders;
- 242 names that do not exist in the tree: relative dir_fd opens made while pytest cleans its temp folders, plus .pyc cache lookups;
- nothing else in the repo, and no other Desktop path.

The only artifacts/ files the tests read are:
- product-live-2026-09-30/native-v2d-run/export.json and native-v2e-run/export.json;
- the two v1 checker copies in those same folders.

Those paths match .gitignore, but they are TRACKED in d38c0b8 (force-added earlier), so a clean checkout has them. The tests skip if those files are absent. The saved-store tests read /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3, which is outside the repo. They copy it with mode=ro&immutable=1 into pytest's temp folder and skip if it is absent.

**Frontend: no ignored files.**
- citation-status.test.tsx imports only tracked, non-ignored sources: src/runPlans.ts, src/loopLimits.ts, src/components/CampaignPlan.tsx and RunSetup.tsx, tests/fixtures.ts and tests/run-fixtures.ts.
- Their own imports are also tracked and not ignored: src/generated/contracts.ts and validate.ts, and audit/development.json.

==================================================
6. COMMIT LIST
==================================================
Files, all in the verify folder:
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/verify/COMMIT_LIST.txt ('<sha256>  <path>', 233 lines)
- COMMIT_LIST_NOTES.txt
- COMMIT_LIST.json (per-path status, backup sha256, ignored flag)

Contents and base:
- **Base:** backup/part2-2026-09-22 at d38c0b8. Commit on top of it, not on main (cbbf957).
- **17 product files:** 10 modified, 7 new, none deleted, no mode changes. The new files are not git-ignored.
  - Modified: CURRENT_STATUS.md; backend/app/lab/learning.py and run_plans.py; docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md and docs/user-guide.md; frontend/src/components/CampaignPlan.tsx, LoopLimits.tsx and RunSetup.tsx; frontend/src/loopLimits.ts and runPlans.ts.
  - New: backend/app/lab/citation_status.py; backend/tests/experiments/test_check_evidence_gap_misreading_v2.py; backend/tests/lab/citation_status_saved.py and test_citation_status.py; docs/PRODUCT_MECHANIC_CITATION_STATUS_2026-09-30.md; frontend/tests/citation-status.test.tsx; scripts/experiments/check_evidence_gap_misreading_v2.py.
- **216 evidence files:** everything under artifacts/product-mechanic-citations-2026-09-30/ (builder, review-integrity, review-product, fixer and verify). They are git-ignored and need `git add -f`.
- **Excluded:** nothing inside the evidence folder needed excluding: no caches, SQLite files, files over 5 MB, symlinks, tree copies, protected copies or .env names. The list's own two files are left out, and so are the two files written after the final pass (secret_scan_final.txt and shasum-check.txt).
- **Protected paths** were never read by the list script; only their size and mtime were recorded.

Checks on the list:
- The 17 product lines are identical in pass 1 and the final pass.
- `shasum -a 256 -c` gives 233 of 233 OK.
- Credential scan: 0 hits in 233 files. The scanner is self-tested: it flags the known dummy key in backend/tests/test_providers.py, masked.
- Conflict copies: 0 conflict-like names outside artifacts/. The scan prunes artifacts/heldout2. The only hits in this round's folder are my own conflict_scan.py and conflict-scan.txt.

==================================================
7. NOTES (why READY_WITH_NOTES)
==================================================
1. **Checker v2.1 misses some real claims, and the human check cannot catch misses.** I tried my own 16 real-claim wordings (verify/spot/checker-probe.json):
   - 8 are counted;
   - 1 is set aside by the denial rule, which is the disclosed limit ("The report is not truthful as it cites labels never shown");
   - 7 match nothing.

   Four of those seven use the block's own "not decoded" vocabulary: "The report cites a token that was not decoded.", "…include tokens that were not decoded…", "Some of the cited tokens were not decoded." and "The report's citations were not decoded." The builder's bare "not decoded" phrase counted these. The fixer's claim shape needs a nonzero amount directly before the noun.

   The trade-off is defensible, because a broader shape would count the block's own MEANING sentence. But the required human check reads only claim_matches (and denied_matches). A miss becomes a silent NOT_CHECKED. Note section 7 states only in general terms that a hypothesis could word the claim differently.

   Recommendation for the declared read-out: a person reads every CONTRACT_EVIDENCE_GAP diagnosis hypothesis in full (there is one per diagnosed source), not only the matched sentences. Say this in note section 8, step 3.

   Also as expected, 5 of my 10 non-claim wordings are counted: refutations, a conditional, and the V2_MEMORY rule text. The required human check exists to catch exactly these.
2. **Test-coverage gap in the builder's code (the code is correct).** citation_row nulls a record whose decoded_evidence_ids length differs from cited_evidence_tokens. No test fails if that length check is removed (mutation V12). The adapter records equal lengths by construction, so the risk is low. A one-line test would close the gap.
3. **Wording.** CURRENT_STATUS says the fixer "made it safe to use after this build". Given note 1, "safer to use" or "no longer counts echoes or denials" would be more accurate.
4. **My own procedural disclosures.**
   a. To locate classify_policy_gap, I ran `grep -rl` over backend/app/. That recursive search read the bytes of backend/app/referee/checks.py. Only filenames were printed, checks.py was not among them, and its content was never displayed. Later greps excluded checks.py. gate_freeze separately confirms scorer_hash and tree_referee are unchanged.
   b. The checkpoint (git archive of d38c0b8, outside the Desktop) and the scratch test tree held the backup's checks.py blob. The new tests imported it, as the real suite does. audit/promotion.json and audit/final-audit.json were deleted from the checkpoint unread. In the scratch runs a synthetic stand-in manifest (spot/vstub.py) answered load_manifest('promotion').
   c. All scratch folders are deleted: /Users/shree/FaultLab_Scratch/verify-citations, the rebuild copy and the differential scratch. /Users/shree/FaultLab_Scratch is empty.
5. **Open decisions** (owner or PM):
   - the paid paired probe (note section 8, step 4);
   - whether to add a product record of the block beside mechanic_outputs (deferred).

**Next steps:** commit on top of d38c0b8 using COMMIT_LIST.txt, with the owner's OK. Then register every agent again, because the runtime and the example configuration hashes changed. Then run the declared, descriptive-only live Learn run, with checker sha256 11920882… frozen in the declaration, `--read-out pre-registered`, and a human reading of the full hypothesis (note 1).
