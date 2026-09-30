_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

INTEGRITY REVIEW: native citation status (faultlab-mechanic-evidence/v2-native-citation-status). September 30, 2026. $0 and offline. I made no provider, W&B, Weave or network calls and made no git writes. I did not open .env, backend/app/referee/checks.py, artifacts/heldout2/, audit/promotion.json or audit/final-audit*.json. I did not open the control-capability file in the native-v2b folder. I wrote no .md report file; this text is the report.
Evidence: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/review-integrity/

VERDICT
- Pass with notes. The build does what the brief asks and breaks none of the hard rules I could test.
- There is one MEDIUM finding, about the measuring tool planned for the next live run, not about the product.
- There are four LOW findings.

(1) THE BLOCK CARRIES ONLY RECORDED ADAPTER FACTS, NOTHING FROM SCORING
- Code (citation_status.py):
  - It reads only the last public report_submitted event with role 'actor'.
  - store.events drops PRIVATE_EVALUATOR events by default (storage.py line 223).
  - From that event it uses only these fields: cited_evidence_tokens, labels_shown_to_agent, decoded_evidence_ids, evidence_labels and cited_tokens_not_decoded.
  - It reads no trial, check, finding or verdict.
  - Every one of those fields is written by the native adapter v2.1 (external_agent_v2.py lines 272-286).
- Independent recompute on a scratch copy of the native-v2b store (review_saved_store.py, review-saved-store.json). I recomputed each row with raw SQL over the events table, without using citation_status:
  - v2e: 5/5, 5/5, 6/6, 6/6, with 0 undecoded;
  - v2d: 5/5, 6/6, 6/6, 5/5, with 0 undecoded;
  - all 8 rows match the block exactly;
  - the adapter's own undecoded list equals the recomputed one;
  - every decoded ID is a delivered observation in that episode's saved evidence record;
  - no private report events were involved.
- Across all 99 native v2.1 reports in that store, 0 have any undecoded token. The undecoded-token case is therefore tested only with made-up test data.
- Wrapped versus plain request, compared key by key: only two things differ, the native_citation_status key and runtime_contract.actor_contract.memory (the old v2 text plus the pointer sentence).
- Nothing new about checks: the plain request already contains the failed-check rows. Each of the 8 diagnosed episodes already shows 2 failed findings, and both live hypotheses name "C5 truthful_report". The block's meaning sentence and the pointer contain no check, failure, verdict or score words.
- One point I weighed and accepted: the unchanged V2_MEMORY already says a token kept as written "fails the evidence check". So an undecoded list lets the Mechanic link a token to that check. That link comes from the adapter's public rule ("scored as written"), not from scoring output. It says nothing about which check failed or how to pass.

(2) GATES AND OLDER BEHAVIOUR UNCHANGED
- gate_freeze, run on backup/part2-2026-09-22 (unpacked with the three forbidden files and artifacts/ left out) and on the working tree, with the builder's runner that drops the two audit files:
  - 121 values are identical;
  - only algorithm_hash, runtime_hash and tree_lab differ (gate-freeze-*.json).
- My own file-by-file tree comparison, which also sees gitignored files in source folders:
  - 10 files changed, 7 added, 0 missing, the same list as the builder's;
  - no referee, simulator, contracts, promotion, challenge, evaluation, reproduction, diagnosis, mechanic, explorer, actor, prompt or adapter file changed;
  - the other added files are old W&B and npm cache files from September 13.
- All 1,420 tracked artifact files (artifacts/heldout2/ left out) are identical to backup.
- Identity, recomputed separately in both trees under the builder's guard (identity-compare-review.txt):
  - these match the builder exactly: runtime f058c03c → c4195af1, algorithm a08a8d61 → ea1ed613, declaration 163c1a4c, memory-with-pointer 75241be8;
  - these are unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, native v1 adapter 6f303264 and prompt 22515428, native v2 adapter dfd41b33, prompt fff397c9 and protocol 0136604, reference source fb5e1894, v2-bounded declaration 11bf9e32, V2_MEMORY 6cbe23d4.
- learning.py diff: with no rule, challenge_explorer is the same explorer object, and the wrapper and attach are never reached.
- Differential check: I read builder/differential_requests.py and I think it is sound. One limit: it replaces 64-hex hashes by position. Both runs share one tree and one process, so that is acceptable.
- Saved plans: all 19 plans in 11 saved stores produce the same output under the backup model and under the new one (saved-plans-dump-*.json). None declares mechanic_evidence. All 6 native v2 plans read back byte-identical, with a valid plan_hash. The 13 older reference/v1 plans already differ from their stored bytes under the backup model (the older evidence_retry, transport_retry and discovery fields). That difference predates this build.
- Challenge selection records now save the challenge context with the block. Every discovery reader of those records skips challenge selections, so discovery is unaffected.

(3) THE SIZE RULE STILL HOLDS
- The block is attached before fit_request in both places:
  - diagnosis: CitationStatusMechanic wraps BoundedMechanic;
  - candidate: attach runs before loop_limits.fit_request.
- The size rule only ever shortens the evidence tables (observations, development_evidence, challenge_counterexamples[i].evidence). It never touches the block.
- The Mechanic's own input check (validate_model_input) is unchanged, so nothing over the limit can be sent. The Explorer has its own check too.
- My recompute of v2d's refused candidate request (review-v2d-candidate.json):
  - 33,223 → 34,796 tokens;
  - stages 35,184 → 29,629 → 22,674, fitting at stage 3;
  - the block is identical after compaction, with all 34 rows (10 episodes kept in full), in first-listing order;
  - the block costs about 45 tokens per row;
  - 5,326 tokens of headroom remain at stage 3.

(4) CHECKER v2
- Version 1 has sha256 70c4eeda in all 5 copies (fixer folder and the v2b, v2c, v2d and v2e run folders), unchanged from backup.
- Version 2 differs from v1 only in its phrase list, the output fields and the self-tests.
- Self-test: PASSED.
- My re-runs match the builder's outputs exactly:
  - v2d: MISREADING (phrases "cannot be decoded", "never shown"); v1 NOT_CHECKED;
  - v2e: MISREADING ("never shown"); v1 NOT_CHECKED.
- I read both hypotheses. They really do make the claim, so these post-hoc results are correct detections.
- The docs, CURRENT_STATUS and the v2e write-up all say POST-HOC and keep the pre-registered NOT_CHECKED.
- One problem remains, MEDIUM-1 below.

(5) TESTS, NETWORK AND .env
- conftest.py blocks the network for every test and refuses any open of the real .env.
- My targeted run: 180 passed, 0 failed, 0 skipped (targeted-pytest.log). It covered test_citation_status (including its 4 saved-store tests, which really ran), the checker v2 tests, the native v1 golden test, native v2, the loop-limits tests, run_plans and the discovery v2/v3/v4 tests.
- The builder's single scripts/test.sh log shows: backend 2,970 passed, 180 skipped, 0 failed; frontend 356; build passed; browser 19 passed, 1 skipped.
- All 579 source files it hashed at suite start still match now.
- The guard refused 0 outbound connections in each of my scripts.
- There is no .env, credential or store copy in the builder's evidence.
- HEAD is still cbbf957, and the .git/index sha is unchanged (e253a478).
- The saved stores' sha256 values were the same at the start and end of my review.
- Scratch copies went to /Users/shree/FaultLab_Scratch/review-integrity/ and were deleted.

WHAT I DID NOT DO
- I did not re-run the full scripts/test.sh or the frontend and browser suites.
- I ran no mutation tests of my own. I read the builder's 17 of 17.

FINDINGS
- MEDIUM-1: checker v2 reads denials and block-echoing text as claims (details in findings).
- LOW-1: the post-hoc label is only in the output file names.
- LOW-2: the size rule's recorded reasons do not mention the block.
- LOW-3: nothing saved shows that a live Mechanic request carried the block.
- LOW-4: the meaning sentence's null clause is slightly narrower than the code.

## Findings (structured)

- **MEDIUM-1 (MEDIUM)** `scripts/experiments/check_evidence_gap_misreading_v2.py`: Checker v2 counts denials, and sentences that repeat the block's own field names, as claims of unshown citations. The new block puts the word 'undecoded' (and 'kept exactly as written') into every native v2 Mechanic request, so this mistake becomes more likely in exactly the run it is meant to measure: CURRENT_STATUS plans the next live Learn run's read-out with checker v2. All data so far show 0 undecoded tokens (99 of 99 v2.1 reports in native-v2b), so any CONTRACT_EVIDENCE_GAP hypothesis the checker marks as a claim is scored MISREADING. A false MISREADING would therefore look like 'the block did not help'. Evidence: review-integrity/checker-v2-negation-probe.txt: 8 of 10 denying or block-echoing sentences are read as claims, including 'undecoded: [] in all four episodes', 'The native_citation_status block shows undecoded is empty for every episode, ...', 'No cited label was not shown to the agent.', 'None of the citations were not decoded.', '0 tokens undecoded', 'nothing is outside the shown labels' and 'no token was never shown'. Only '0 undecoded' and 'no undecoded tokens' are correctly ignored. The self-tests cover denial only for 'undecoded' right after 0, no, zero or without. The v2d and v2e post-hoc results are not affected: both hypotheses really make the claim. Fix: Before declaring checker v2 as the next run's read-out: (a) add these sentences as must-not-match self-tests, and handle denials or remove the bare words 'undecoded' and 'not decoded', since the Mechanic will now see them as field names; and/or (b) declare in advance that every CHECKED verdict is printed with the exact sentence that matched and counts only after a person confirms it is a real claim. Keep v1, and keep v2's post-hoc results on v2d and v2e.
- **LOW-1 (LOW)** `scripts/experiments/check_evidence_gap_misreading_v2.py`: The POST-HOC label on the v2d and v2e results exists only in the file names (builder/checker-v2/*-POSTHOC.json) and in the docs. The JSON itself does not say it. check() copies into its 'rule' field only the docstring text after 'Rule (...):', which leaves out the POST-HOC paragraph. A copied or renamed output therefore loses the label. Evidence: My re-runs (review-integrity/checker-v2-rerun/v2d-v2.json, v2e-v2.json) contain only the keys campaign_id, checker_version, claim_pattern, diagnostics, rule and summary, with no post-hoc marker. The builder's files have the same keys and differ only in their names. Fix: Add an explicit field to the stored v2d and v2e outputs, e.g. 'read_out_status': 'POST_HOC (phrase list widened after reading these hypotheses; pre-registered v1 read-out NOT_CHECKED)', or write a small sidecar file saying so in builder/checker-v2/.
- **LOW-2 (LOW)** `backend/app/lab/loop_limits.py`: Under the rule, the citation block is never compacted and keeps a row (about 45 tokens) for each omitted episode too. But the size rule's recorded SEARCH_ENDED reason (UNFIT_REASON) and its compaction statement list the parts that are never omitted without naming the block. If the block ever tips a stage-3 request over the 28,000-token target, the recorded reason would not show that it contributed. Evidence: review-v2d-candidate.json: at stage 3 the block is 1,526 tokens for 34 rows (24 of them omitted episodes), leaving 5,326 tokens of headroom. So this is unlikely at today's sizes, and there is still no over-limit send in any case. Fix: No gate change is needed. State in the citation-status note (section 4) that the block also counts toward, and is never omitted from, the target. Optionally add a test showing how many extra episodes the block allows before a v2d-shaped request stops fitting. Changing UNFIT_REASON would change the frozen v2-bounded declaration (11bf9e32), so leave it.
- **LOW-3 (LOW)** `backend/app/lab/citation_status.py`: No saved record shows that a live Mechanic diagnosis or candidate request actually carried the block, or which rows it held. mechanic.py saves only the raw outputs, and the size-rule record is written only when a request is over the limit. Challenge selections do save their context. The planned read-out (does the Mechanic still claim unshown citations?) depends first on confirming the block was present. Evidence: mechanic.py _generate saves 'mechanic_outputs' with the raw output and usage but not the messages. The span inputs hold only evidence_ids and parent_version. The block can be rebuilt deterministically from saved events and the plan's frozen declaration (the builder's rebuild_requests.py and citation_status_saved.py do this). Fix: Declare in advance, as the first read-out step, an offline rebuild of each live diagnosis and candidate request, reporting that the block was present and its rows. A saved record written by the wrapper (block hash and rows) would be a product change needing review, so keep it out of this build.
- **LOW-4 (LOW)** `backend/app/lab/citation_status.py`: The meaning sentence sent to the Mechanic says all three values are null 'when no submitted report was recorded'. citation_row also returns nulls when a report WAS recorded but carries no v2.1 citation record or has an inconsistent shape. In that case the Mechanic would read a false statement next to original_report_present=true in the evidence. Evidence: citation_status.py lines 45-48 (MEANING) against lines 116-126 (citation_row returns the empty row when citation_protocol differs or a list is malformed). In native v2 plans every report carries the v2.1 record (99 of 99 in the native-v2b store), so today this cannot happen. The docs describe it correctly: 'no report, or another adapter'. Fix: Before commit, reword the clause to e.g. '(all three are null when no native adapter v2.1 citation record was recorded for that episode)'. This changes the declaration hash (163c1a4c), which is acceptable because nothing is committed or run yet. Update identity and docs to match.
