_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

PRODUCT REVIEW: native citation status in Mechanic requests (faultlab-mechanic-evidence/v2-native-citation-status). September 30, 2026. $0 and offline. I changed no product file, made no commit, and did not touch the index or HEAD. This text is the report: I wrote no REPORT.md, because the subagent rules forbid report .md files.

VERDICT: READY_WITH_NOTES
- Every builder claim I could test offline reproduced exactly.
- I found no defect in the product code.
- There is one MEDIUM finding: checker v2 would misfire on a Mechanic that echoes the new block. It does not affect the v2d/v2e post-hoc results, but it should be fixed before checker v2 becomes the pre-registered read-out of the next live run.
- There are three LOW notes: two about the read-out and one about docs.

WHAT I CHECKED, AND WHAT I FOUND

0. Scope and freeze (independent)
- My own tree compare against backup d38c0b8 (git ls-tree plus hash-object; forbidden files never opened) matches the builder's list: 10 changed, 7 added, 0 missing. The tree was unchanged from the start to the end of my review.
- None of these changed: diagnosis.py, mechanic.py, explorer.py, challenge.py, promotion.py, evaluation.py, loop_limits.py, the referee, the simulator, prompts/actor.md, external_agent.py and external_agent_v2.py.
- I ran the repo's gate_freeze.py code myself, with the audit files dropped from its file list. Against the backup, only the runtime_hash, algorithm_hash and tree_lab fingerprints differ. My result is identical to the builder's after.json.
- Identities, recomputed with the product's own functions:
  - runtime c4195af104fbc90f…, algorithm ea1ed613…;
  - unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, capability 8e8e04af, reference source fb5e1894, reference prompt 12eabe7f, native v1 adapter 6f303264 and prompt 22515428, native v2 adapter dfd41b33, prompt fff397c9 and protocol 0136604, mechanic_context declaration 11bf9e32, V2_MEMORY 6cbe23d4;
  - new: declaration 163c1a4c…, memory with pointer 75241be8….
  All match the builder's report.
- HEAD is still cbbf957, and .git/index is unchanged (e253a478…, the same as at the builder's suite start).
- All saved stores under /Users/shree/FaultLab_Runs hash the same at my start and end. The 31 files the builder also hashed match its end hashes.

1. The code, read closely
- Rows are read only from each episode's last public report_submitted event with role 'actor'. store.events excludes PRIVATE_EVALUATOR events by default, and no check, verdict, trial or finding is read.
- The 'decoded' count is sound. The adapter (external_agent_v2) assigns exactly one obs-N label per delivered journal observation, so the builder's inversion of the label map is exact. TaskReport keeps evidence_ids in order, and the adapter decodes token by token, so the per-position comparison is valid.
- The real Mechanic and Explorer serialise the whole context (canonical_json), so the new key does reach the provider.
- runtime_contract() returns V2_MEMORY exactly when the plan's agent is smolagents-v2, and _bindings allows the rule only on such plans. So the RuntimeError guard in attach() cannot be reached for a valid plan.
- Every Mechanic and Explorer call in the Learn loop is covered. completion_study and search_benchmark are separate, non-Learn paths.
- The episode blocks the build reads mirror the ones loop_limits._blocks compacts.
- Omitted episodes stay named in compaction.omitted, so block rows for them do not dangle.

2. Check (1): the saved store (review_saved_store.py -> saved-store-check.json)
- I made a read-only scratch copy of native-v2b (mode=ro&immutable=1) in /Users/shree/FaultLab_Scratch/review-product, and deleted it afterwards.
- Independent raw SQL (no product code): for all 8 diagnosed episodes, v2e 5/5, 5/5, 6/6, 6/6 and v2d 5/5, 6/6, 6/6, 5/5:
  - one report each, protocol v2.1;
  - every cited label was shown and decoded;
  - every decoded ID appears in that episode's own observation_delivered events;
  - 0 undecoded.
- The product path gives the same answer. I registered the v2 agent and made a NEW Learn plan with v4 history replay in the copy: it declares the rule, and campaign_rule equals declaration(). The old v2d and v2e plans still read, declare nothing, and their campaign_rule is None.
- I rebuilt the v2e and v2d diagnosis requests through the real wrapping order, CitationStatusMechanic(BoundedMechanic(capture)):
  - the block rows equal my SQL numbers, in the order source then reproductions;
  - every other field is identical, and runtime_contract differs only in the memory text (V2_MEMORY becomes V2_MEMORY plus the pointer).
- Sizes with the Mechanic's frozen tokenizer, all matching the builder:
  - v2e diagnosis: 9,088 → 9,424 (+336);
  - v2d diagnosis: 8,990 → 9,321 (+331);
  - v2d refused candidate request: 33,223 → 34,796. Compaction stages give 35,184 / 29,629 / 22,674 (fits at stage 3, within the 28,000 target); without the block, 33,611 / 28,056 / 21,101. The block is unchanged by compaction: 34 rows, all 0 undecoded, cited = decoded.
- New (the builder did not measure this): v2d's three recorded challenge Explorer requests grow from 7,499 / 7,598 / 7,718 to 7,867 / 7,966 / 8,086 local tokens (+368 each; the provider reported 136 fewer). Each has 6 rows with 0 undecoded. They are far under the 32,000 limit, and nothing compacts them.

3. Check (2): a scripted v4 Learn campaign on a REAL saved plan (review_e2e_loop.py -> e2e-loop-check.json)
- Unlike the builder's loop tests, I did not monkeypatch campaign_rule or runtime_contract. The plan was made by register_agent, then prepare_run_plan with v4, then create. The real Explorer and the real Mechanic build every request; only the provider is scripted, and the guard counted 0 outbound connections.
- Native v2 plan, diagnosis scenario (real Diagnostician): 1 diagnosis request, with the block and the pointer. The first source cites a token it was never shown, and its row reads cited 2, decoded 1, undecoded ['obs-9'].
- Native v2 plan, candidate scenario:
  - both candidate requests carry the block and the pointer;
  - the challenge Explorer request carries the block (and no pointer, since it has no runtime_contract);
  - the persisted challenge selection record also carries the block;
  - block order equals first-listing order in every request.
- In both native v2 scenarios, all 8 discovery requests have no block and keep the plain V2_MEMORY.
- Native v1 plans (candidate and diagnosis) and a reference plan (candidate): no block anywhere.
- All five campaigns ended NO_CHANGE with no error.
- A first attempt stopped at slot 2 in every scenario, reference included. The cause was my harness: FakeRunner writes no 'episodes' records, which discovery needs. I fixed that as tests/lab/test_discovery_v2_flow does and reran.

4. Check (3): plan, dashboard, recording and docs
- Plan model: exact Literal fields. The key is absent (not null) in other plans. _bindings refuses the rule for any other agent or mode, and validate_run_plan refuses any other rule text.
- Dashboard:
  - the saved plan shows "Native citation status" only for a smolagents-v2 Learn plan;
  - an older v2 plan reads "Not declared: this native adapter v2 plan was saved before the rule…";
  - v1 and reference plans show nothing;
  - the setup form shows the rule only when v2 is chosen, and the wording is plain;
  - frontend/tests/citation-status.test.tsx covers all of this.
- The recording (/api/campaigns/{id}/recording) carries run_plan, including mechanic_evidence (builder's api-contract-check).
- The docs are consistent with the code and the measurements. The post-hoc results are labelled POST-HOC everywhere, and the pre-registered read-out stays NOT_CHECKED. The quoted v2e hypothesis text matches export.json. The claim that the old status called f058c03c "not yet committed" was a real error, and it is corrected correctly (committed as 884de24, run live once as v2e).

5. Check (4): checker v2
- v1 is untouched: all five copies (the v2b fixer, the v2b, v2c, v2d and v2e run folders) hash 70c4eeda…, equal to the blob committed in the backup.
- v2 differs from v1 only in the phrase list, the reported matched phrases and the self-tests.
- --self-test: PASSED (30 phrase cases, plus the verdict cases).
- My reruns are byte-identical to builder/checker-v2:
  - v2d: v1 NOT_CHECKED, v2 MISREADING on "cannot be decoded" and "never shown";
  - v2e: v1 NOT_CHECKED, v2 MISREADING on "never shown";
  - 4 episodes read each; 0 report IDs not recorded; 0 tokens not decoded.
- On substance, MISREADING is right for both. Each hypothesis does claim unshown or undecodable citations, and the data show none. The results are POST-HOC, as disclosed.

6. Tests
- The builder's full scripts/test.sh log shows: backend 2,970 passed, 180 skipped, 0 failed; frontend 356 passed; build passed; browser 19 passed, 1 skipped.
- The 17 new backend tests all ran; none skipped.
- The 579 files the builder hashed at its suite start, including all 17 changed or added files, are byte-identical now, so that run covers today's tree.
- My targeted rerun (test_citation_status, the misreading v2 tests, loop_limits mechanic context, discovery v2 flow, learning qualification): 65 passed.
- The mutation log shows 17 of 17 caught. The differential shows 6 of 6 scenarios identical, with a positive control that differs.
- I did not rerun the frontend or the browser stages myself. That would have written caches into the repo tree, and the builder's run already covers the current files.

FINDINGS
- MEDIUM-1 (checker v2 misfires on block echoes): see findings. Fix before the next read-out is declared.
- LOW-1 (docs point to a builder report that does not exist as a file): state the final test numbers inline.
- LOW-2 (no per-request record that Mechanic requests carried the block): add a rebuild and token-delta step to the live read-out.
- LOW-3 (no concurrent control for the next live read-out): phrase it descriptively, or first run a small paired probe with and without the block.

NOTES, NOT FINDINGS
- The block's "one plain sentence" is one sentence but 78 words long, with a parenthetical. It is accurate. Its reader is the model, not the owner.
- It says the fields are null "when no submitted report was recorded". They are also null for a report without a v2.1 record, but no v2 plan can produce that with the installed adapter.
- Two gitignored __pycache__ files (backend/app/lab/__pycache__/learning.cpython-312.pyc and a pytest-rewritten test_native_adapter_v2 .pyc) were written at 04:20:15 during my review. They are not mine: every process of mine ran with -B or PYTHONDONTWRITEBYTECODE=1, none touched tests/integrations, and the '-pytest-9.1.1' suffix shows a pytest process wrote them. The integrity reviewer was running concurrently.

WHAT THIS REVIEW DOES NOT SHOW
Nothing ran live. Whether the Mechanic stops claiming unshown citations once it sees the block is unmeasured. The block states no cause, by design.

EVIDENCE: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/review-product/
- rguard.py
- tree_compare.py, tree-vs-backup-review-start.txt, tree-vs-backup-review-end.txt
- review_saved_store.py, saved-store-check.json
- review_e2e_loop.py, e2e-loop-check.json
- checker-v2/ (self-test.json, v2d-v2.json, v2e-v2.json, v1 reruns, echo-probe.json) and checker_v2_echo_probe.py
- targeted-tests.log
- review_identity.py, identity-review.json
- gate_freeze/ (run_gate_freeze.py, review.json)
- saved-stores-sha256-start.txt, saved-stores-sha256-end.txt
Scratch (/Users/shree/FaultLab_Scratch/review-product) is deleted.

## Findings (structured)

- **MEDIUM-1 (MEDIUM)** `scripts/experiments/check_evidence_gap_misreading_v2.py`: Checker v2 counts the new block's own field name, the bare word "undecoded", as a claim. Only four preceding words are excluded ("0", "no", "zero", "without"). A Mechanic that reads the block correctly and echoes it will usually match as a claim. If that diagnosis still proposes CONTRACT_EVIDENCE_GAP for a different stated reason, checker v2 returns MISREADING. The builder's NEXT step plans to read the declared live run out with checker v2, and that run will be the first in which the Mechanic sees this block, so a false MISREADING is plausible. The v2d/v2e post-hoc results are unaffected: those requests had no block, and they matched "never shown" and "cannot be decoded". Evidence: review-product/checker-v2/echo-probe.json (produced by checker_v2_echo_probe.py, which imports the checker unchanged):
- 9 of 10 correct-reading wordings match as claims: "undecoded is empty for every episode", "an empty undecoded list", "none undecoded", "undecoded: [] in all four rows", "No token was left undecoded", "There were no tokens undecoded", "lists nothing as undecoded", "Nothing was undecoded" (all matched "undecoded"), and "no label was never shown" (matched "never shown"). Only "0 undecoded tokens" is excluded.
- A synthetic CONTRACT_EVIDENCE_GAP hypothesis, "Every row of native_citation_status has an empty undecoded list, so the citations were valid; the gap is that the cited FAILED receipt contradicts the report overall...", scores verdict MISREADING. Fix: Before checker v2 is pre-registered as a live read-out:
- drop the bare "undecoded" alternative, keeping "undecodable", "cannot/could not be decoded", "not decodable", "never shown" and "were not shown" (both live hypotheses still match), or restrict it to claim shapes such as a nonzero count before "undecoded token(s)/label(s)/citation(s)";
- add the block-echo wordings above as negative self-tests, plus a verdict case of CONTRACT_EVIDENCE_GAP with an empty-undecoded echo;
- freeze the checker's sha256 in the run's read-out declaration, and keep reporting the matched phrases for a human check.
This changes only the post-hoc script, not v1 and not any gate.
- **LOW-1 (LOW)** `CURRENT_STATUS.md`: The docs say the final scripts/test.sh result is "in the builder report", but there is no builder report file: the builder was forbidden to write one. A later reader of CURRENT_STATUS or the citation-status note cannot find the numbers except by opening the raw log. CURRENT_STATUS instead shows only a stale earlier backend count (2,965). Evidence: - CURRENT_STATUS.md, Newest build, Checks: "a backend run before the last test additions: 2,965 passed ... The one final scripts/test.sh is builder/full-test-sh.log; its result is in the builder report."
- docs/PRODUCT_MECHANIC_CITATION_STATUS_2026-09-30.md section 5: "See the builder report for exact counts and the final scripts/test.sh result."
- builder/full-test-sh.log: "2970 passed, 180 skipped"; frontend 356 passed; build; browser 19 passed, 1 skipped (10:52:37Z-11:11:04Z). Fix: State the final result inline in both files: backend 2,970 passed, 180 skipped, 0 failed (2 known warnings); frontend 356 passed; build passed; browser 19 passed, 1 opt-in skip; log builder/full-test-sh.log, 10:52:37Z to 11:11:04Z. Remove the stale 2,965 line, or mark it superseded.
- **LOW-2 (LOW)** `backend/app/lab/citation_status.py`: No record shows that a given Mechanic diagnosis or candidate request actually carried the block. The product does not persist Mechanic request contexts; this is pre-existing, and only challenge Explorer selection records store their context. After the live run, the only product evidence is the frozen plan declaration plus the provider-reported input tokens. The read-out would then rest on inference unless it adds a verification step. Evidence: - app/agents/mechanic.py saves mechanic_outputs with the raw output, request_id and usage only; not the context.
- In my end-to-end run (e2e-loop-check.json), the challenge selection records carry the block (1 of 1), but nothing stores the Mechanic requests.
- The expected token deltas are measured: diagnosis +331 to +336 (local count = provider count + 136). Fix: No code change is needed for this build. Add two steps to the declared live-run read-out:
- rebuild the diagnosis request offline from the run's store with the real wrapping order (as builder/rebuild_requests.py and review_saved_store.py do), and confirm the block and its rows;
- check that the provider-reported input tokens equal the rebuilt local count minus 136.
Optionally, a later build could record a hash or a row count of the block beside mechanic_outputs.
- **LOW-3 (LOW)** `docs/PRODUCT_MECHANIC_CITATION_STATUS_2026-09-30.md`: The rule is always on for every new native v2 Learn plan, and older plans cannot start under the new runtime. So the planned live Learn run has no concurrent control without the block. Its read-out (does the diagnosis still claim unshown citations?) would be a before/after comparison against v2d and v2e: two diagnoses, on a different runtime. The project's own history (Phase 8's claim withdrawn under Phase 9's concurrent control) shows how such comparisons mislead. Evidence: - run_plans.prepare_run_plan freezes mechanic_evidence for every smolagents-v2 Learn plan, with no opt-out.
- validate_run_plan refuses plans whose configuration hash predates the runtime change ("Register the agent again and create a new campaign").
- The doc's section 7 and the builder's NEXT step describe a single declared live run as the read-out. Fix: Either phrase the live read-out as descriptive only (the claim was or was not made, and the intervention was or was not requested), without causal attribution to the block, or run a small paired probe first. The v2e and v2d diagnosis requests are deterministic and rebuildable, so each could be sent k times with and without the block to the Mechanic model and scored by the fixed checker v2. That gives a concurrent comparison for a few dollars before the full Learn run.
