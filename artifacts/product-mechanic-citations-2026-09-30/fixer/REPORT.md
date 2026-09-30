_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FIXER REPORT: native citation status (faultlab-mechanic-evidence/v2-native-citation-status), September 30, 2026.
This fix round cost $0 and ran offline.
- No provider, W&B, Weave or network calls were made. The guard refused 0 outbound connections in each script.
- There were no git writes. HEAD is still cbbf957 and the .git/index sha256 is unchanged (e253a478…).
- I did not open .env, backend/app/referee/checks.py, artifacts/heldout2/, audit/promotion.json or audit/final-audit*.json.
- I changed no gate or scoring code.
- Status: NOT YET COMMITTED, not run live.
- This text is the report. I wrote no report .md file.

RESULT
- All 9 finding entries were checked. Two entries are the same finding reported by both reviewers, so there are 7 distinct findings (1 MEDIUM, 6 LOW). None of them is a defect in the product code.
- 3 are fixed with code, and each fix has a test that failed first and passes now: MEDIUM-1, LOW-1 (integrity) and LOW-4.
- 3 are fixed in the docs: LOW-2 (integrity), LOW-1 (product) and LOW-3 (product).
- 1 is deferred, with a step added to the planned read-out instead: LOW-3 (integrity), which is the same as LOW-2 (product).
- The single final scripts/test.sh, run after my last edit, passed every stage (fixer/full-test-sh.log, 11:43:09Z to 12:01:30Z):
  - backend: 3,000 passed, 180 skipped, 0 failed, with the 2 known warnings (starlette BlockingPortal, fork);
  - frontend: 356 passed;
  - build: passed;
  - browser: 19 passed, 1 opt-in skip.
- The backend count is the builder's 2,970 plus my 30 new tests.
- The 579 source, test and doc files hashed at the start of the suite did not change during it.

WHAT I VERIFIED FIRST
Each finding was confirmed before any fix:
- **MEDIUM-1.** New tests run on the builder's code: 17 of the reviews' 20 wordings were read as claims, the synthetic contract-gap hypothesis was scored MISREADING, and the block's own meaning sentence counted as a claim. Result: 27 failed (fixer/tests-before-fix.log).
- **LOW-1 (integrity).** The builder's output JSON has no post-hoc key.
- **LOW-4.** A report without the v2.1 record, and an incomplete v2.1 record, both give null rows even though a report was recorded.
- **LOW-2 (integrity).** UNFIT_REASON in loop_limits.py lists the parts that are never omitted and does not name the block.
- **LOW-3 (integrity) / LOW-2 (product).** mechanic.py saves only the raw output and usage to mechanic_outputs, not the request.
- **LOW-1 (product).** CURRENT_STATUS said the result was "in the builder report", which is not a file, and still showed the stale figure of 2,965.
- **LOW-3 (product).** run_plans freezes the rule for every smolagents-v2 Learn plan, with no way to opt out.

FIXES
1. **Checker v2 (MEDIUM-1).** File: scripts/experiments/check_evidence_gap_misreading_v2.py. Version string faultlab-misreading-check/v2.1-claim-shapes-and-denials, sha256 11920882f8c7e9885242e455b7c37e3e8f8649d3bb1c86b927d6da5c07be3b7b (the builder's was bd508a79…).
   - The bare words "undecoded" and "not decoded" no longer count as a claim. Only claim shapes count:
     - a nonzero amount, or a verb of having or citing, before "undecoded token/label/citation" (for example "1 undecoded token" or "has undecoded tokens");
     - a nonzero amount of tokens, labels or citations that "were not decoded".
   - A match does not count when its own clause, before the match, contains a denial word: no, none, nothing, neither, nor, never, not, n't, zero, 0 or without.
     - A clause ends at . ; : ! ? , a dash, and at the words and, but, yet, so, because, since, while, although, though, whereas and however.
   - Every output now lists claim_matches (each counted match with its sentence) and denied_matches (each match the denial rule set aside), and says human_confirmation_required=true.
   - The rule text says that a CHECKED verdict counts only after a person confirms each claim_matches sentence.
   - Everything else is unchanged:
     - the CLAIM pattern still begins with v1's phrases;
     - v1 still has sha256 70c4eeda in all five copies (the v2b fixer folder and the v2b, v2c, v2d and v2e run folders).
   - Results:
     - all 20 review wordings now score NOT_CHECKED;
     - the block's meaning sentence and memory pointer are not claims;
     - both live hypotheses still match exactly as before.
   - Known limit, stated in the docs: the unchanged V2_MEMORY sentences "an observation it was never shown…" and "…one the agent was never shown as a label" still count as "never shown". A Mechanic that repeats that rule text counts as a match, and only the human check catches it (fixer/checker-v2/probe.json).
2. **Output labels (LOW-1, integrity).**
   - --read-out {pre-registered,post-hoc} is now required. Without it the script refuses to run (exit 2) and writes no output file.
   - Every output carries read_out_status (POST_HOC or PRE_REGISTERED), a read_out_note and the script's own checker_sha256.
   - I re-made the v2d and v2e outputs in fixer/checker-v2/ as *-v2.1-POSTHOC.json, with "read_out_status": "POST_HOC" inside each file.
   - The builder's builder/checker-v2/ outputs are kept unchanged as its record.
3. **The null clause (LOW-4).**
   - The meaning sentence now ends "(all three are null when no complete native adapter v2.1 citation record was recorded for that episode)".
   - The declaration hash changes from 163c1a4c… to b84f55db3c3f52209c085dda799cdbd9edeef88f90ddced535afb1140828ca72. That is acceptable because nothing is committed yet.
   - The memory pointer is unchanged (75241be8).
   - The new wording adds 10 tokens per block.
4. **Docs.** docs/PRODUCT_MECHANIC_CITATION_STATUS_2026-09-30.md:
   - status line and evidence folders updated;
   - section 2: the new sentence, and the corrected "No guessing" bullet;
   - section 4, for LOW-2:
     - the block counts toward the 28,000-token target and is never omitted from it;
     - UNFIT_REASON and the compaction statement do not name the block, and are left unchanged because they belong to the frozen v2-bounded declaration (11bf9e32);
     - the re-measured sizes are in the table;
   - section 5: the builder's final counts stated inline, for LOW-1 (product);
   - section 6: the checker revision, the human check and the known limit;
   - section 7: the new limits (undecoded case tested only with made-up data; no per-request record);
   - new section 8, the read-out plan, covering LOW-3 (product) and LOW-3 (integrity) / LOW-2 (product):
     - the live read-out is descriptive only, with no causal claim, because there is no concurrent control without the block;
     - first rebuild each live diagnosis and candidate request offline, and check provider tokens = rebuilt local count − 136;
     - freeze the checker's sha256 in the declaration and run it with --read-out pre-registered, with a human check of every counted sentence;
     - optionally, a small paid paired probe with and without the block, if the owner decides;
   - new section 9: the findings table and the fixer's identities.
   - Other files updated:
     - CURRENT_STATUS.md: header and "Newest build" paragraph (runtime 95042e4d…, builder counts inline, stale 2,965 line removed, reviews and fixer summary, next steps);
     - docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md: follow-up paragraph;
     - docs/user-guide.md: status wording;
     - the checker test's docstring.

RE-MEASURED WITH THE NEW WORDING
Measured on a read-only scratch copy of native-v2b, with the builder's rebuild script (only the scratch path changed). The copy was deleted afterwards. Output: fixer/rebuild-requests.json.

| request | before | after | added |
|---|---|---|---|
| v2e diagnosis | 9,088 | 9,434 | 346 |
| v2d diagnosis | 8,990 | 9,331 | 341 |
| v2d refused candidate request (34 episodes) | 33,223 | 34,806 | 1,583 |

- Compaction stages for the candidate request: 35,194 → 29,639 → 22,684. It fits at stage 3, with 5,316 tokens of headroom. The block keeps all 34 rows.
- Every block row is still 5/5, 5/5, 6/6, 6/6 (v2e) and 5/5, 6/6, 6/6, 5/5 (v2d), with 0 undecoded.
- Every other request field is unchanged.
- The excerpt with fake IDs is in fixer/v2e-diagnosis-request-excerpt.json.

POST-HOC CHECKER RESULTS (not the pre-registered read-out, which stays NOT_CHECKED)

| run | v1 (pre-registered) | v2 builder version | v2 fixer version (POST_HOC) | counted phrases | episodes read |
|---|---|---|---|---|---|
| v2d | NOT_CHECKED | MISREADING | MISREADING | "cannot be decoded", "never shown" | 4 (0 report IDs not recorded, 0 tokens not decoded) |
| v2e | NOT_CHECKED | MISREADING | MISREADING | "never shown" | 4 (same) |

I read the three counted sentences myself, as the new human check requires. Each is a real claim of unshown or undecodable citations. No match was set aside as denied.

TABLE
| id | verdict | change | test |
|---|---|---|---|
| MEDIUM-1 (integrity and product) | FIXED | claim shapes replace bare "undecoded" and "not decoded"; clause denial rule; claim_matches and denied_matches; human check required | 29 new pytest cases (20 review wordings, the synthetic hypothesis, the block's own sentences, 5 claim cases, a denied-match case), plus 20 new self-test phrase cases and 2 verdict cases; they failed first and pass now; mutations F1–F8 caught |
| LOW-1 (integrity) | FIXED | required --read-out; read_out_status, note and the script's sha256 in every output; v2d and v2e outputs re-made in fixer/checker-v2 | test_every_output_states_its_read_out_status_and_the_checkers_own_sha256 failed first, passes now; mutations F9 and F10 caught |
| LOW-4 (integrity) | FIXED | null clause reworded; declaration 163c1a4c → b84f55db | test_the_meaning_sentence_describes_every_null_row failed first, passes now; mutation F11 caught |
| LOW-2 (integrity) | FIXED (docs); record wording DEFERRED | note section 4 states the block counts toward and is never omitted from the target; UNFIT_REASON is frozen with v2-bounded (11bf9e32), so it is not changed | docs only |
| LOW-3 (integrity) = LOW-2 (product) | DEFERRED (product record); read-out step added | note section 8, step 2: offline rebuild plus the provider = local − 136 check. A saved block record beside mechanic_outputs would be a product change needing review | docs only |
| LOW-1 (product) | FIXED | builder's final counts inline in CURRENT_STATUS and note section 5; stale 2,965 removed; the fixer's counts are in this report and the log (a document cannot quote a run that must follow its own last edit) | docs only |
| LOW-3 (product) | FIXED (docs); paired probe DEFERRED (costs money; owner's decision) | note section 8, steps 1 and 4: descriptive-only read-out, plus the optional concurrent paired probe | docs only |

MUTATIONS
- 11 of 11 caught (fixer/mutation-checks.log, which also records the failing-first run and the passing run after the fix).
- Every file was restored, and its sha256 checked afterwards.
- The mutations:
  - F1: bare "undecoded" counts again;
  - F2: bare "not decoded" counts again;
  - F3: denial rule turned off;
  - F4: no clause boundary. The v2d test caught this, because "not because" appears earlier in that hypothesis;
  - F5: 0 accepted as a claim amount;
  - F6: "no" removed from the denial words;
  - F7: the verdict counts denied matches too;
  - F8: matches no longer reported with their sentences;
  - F9: --read-out not required;
  - F10: labels not written into the output;
  - F11: old null clause restored.
- Targeted backend run after the fixes: 185 passed (fixer/targeted-tests-after-fix.log). It covered:
  - citation status and checker v2;
  - the native v1 golden test, native v2 and v2 label views;
  - loop-limits context and plans;
  - discovery v2 and v4;
  - learning qualification and diagnosis context.

IDENTITY (fixer/identity-compare.txt, against the builder's identity-after.json)
- Changed:
  - runtime c4195af1… → 95042e4d9a67c739387a3841152bd7c23448f89cd5271ca32806552d6f3fc36c;
  - algorithm ea1ed613… → 4e5a8f90cd97d33cc1b70560350dab023b052f8b0bab6b43c478054fdc345b6b;
  - declaration 163c1a4c… → b84f55db…;
  - both example configuration hashes. Register every agent again before a live run.
- Unchanged:
  - service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, capability 8e8e04af;
  - native v1 adapter 6f303264 and prompt 22515428;
  - native v2 adapter dfd41b33, prompt fff397c9 and protocol 0136604;
  - reference source fb5e1894 and prompt 12eabe7f;
  - v2-bounded 11bf9e32;
  - V2_MEMORY 6cbe23d4;
  - memory with pointer 75241be8;
  - the transport-retry and challenge-selection declarations.
- gate_freeze.py (fixer/gate_freeze/compare.txt), against the backup d38c0b8 and against the builder tree: 20/20 files and 30/30 functions identical. Only the algorithm_hash, runtime_hash and tree_lab fingerprints changed.
- Identity was recomputed after the suite and is identical (identity-end.json).

SCOPE AND INTEGRITY
- The tree against backup d38c0b8 is 10 changed, 7 added, 0 missing, the same list as at the builder's end (tree-vs-backup-start/end.txt).
- I edited only these files:
  - backend/app/lab/citation_status.py (MEANING only);
  - scripts/experiments/check_evidence_gap_misreading_v2.py;
  - backend/tests/lab/test_citation_status.py (+1 test);
  - backend/tests/experiments/test_check_evidence_gap_misreading_v2.py (+29 cases);
  - CURRENT_STATUS.md;
  - docs/PRODUCT_MECHANIC_CITATION_STATUS_2026-09-30.md;
  - docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md;
  - docs/user-guide.md.
- Nothing under referee, simulator, contracts, promotion, challenge, evaluation, diagnosis, loop_limits, mechanic, explorer, the adapters or prompts changed.
- All 43 lab.sqlite3* files under /Users/shree/FaultLab_Runs hash the same at start and end. The 31 the builder hashed match its end hashes.
- The scratch folder /Users/shree/FaultLab_Scratch/fixer was deleted.
- A credential scan of the fixer evidence found nothing.

WHAT THIS DOES NOT SHOW
- Nothing ran live. Whether the Mechanic stops claiming unshown citations once it sees the block is unmeasured.
- The checker is still a phrase heuristic, and can err both ways:
  - it can miss a real claim that follows a denial word in the same clause;
  - it counts an echo of V2_MEMORY's "never shown" rule.
  That is why every counted sentence now needs a human check.
- The undecoded-token path has been tested only with made-up data: 99 of 99 v2.1 reports in native-v2b have 0 undecoded tokens.

NEXT
1. Commit, with the owner's OK.
2. Register every agent again.
3. Run the declared live Learn run (v2 agent, v4 history replay, native-v2b store), with the descriptive read-out from note section 8, the frozen checker sha256 11920882… and the human check. Optionally run the paired probe first, if the owner decides.

EVIDENCE: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/fixer/
- test runs: tests-before-fix.log, targeted-tests-after-fix.log, mutation_checks.py, mutation-run.txt, mutation-checks.log, full-test-sh.log (with .start and .end);
- checker-v2/: self-test.json, run.log, the two POSTHOC outputs, sha256.txt, probe.json, product-echo-probe-rerun.json;
- checker_v2_probe.py;
- request rebuild: rebuild_requests.py, rebuild-requests.json, v2e-diagnosis-request-excerpt.json;
- identity: identity.py, identity_snapshot.py, guard.py, identity-after.json, identity-end.json, identity-compare.txt;
- gate_freeze/: after.json, compare.txt;
- tree and store checks: tree_compare.py, tree-vs-backup-start/before-suite/end.txt, saved-stores-sha256-start/end.txt, source-sha256-at-suite-start.txt, source-sha256-after-suite-check.txt, git-state-start.txt, git-state-at-suite-start.txt.
