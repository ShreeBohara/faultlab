_Saved by the PM from the agent's returned text; content unedited._

INDEPENDENT REVIEW OF THE FOLLOW-UP (PM decision F4 and pinned saved-store tests), September 30, 2026.
Cost $0. Everything ran offline under my own guard, which refused outbound network, .env, heldout2, audit/promotion.json, audit/final-audit*.json, any write into the real repo or saved stores, and any saved-store SQLite open without mode=ro. Result: 0 refusals in every run.
I changed nothing outside artifacts/product-diagnosis-rules-2026-09-30/followup-review/ (36 files, SHA256SUMS.followup-review.txt).
Per the harness rule against writing report .md files, this text is the report.

VERDICT: READY_WITH_NOTES.
The follow-up does what was asked. I found no loosened or deleted assertion, no C6 text anywhere, Rule 2 still not offered, and nothing changed outside the task. None of the notes below blocks a commit. Two need an action or decision before commit, or before the probe.

(1) THE PINNED TESTS STILL CHECK THE SAME FACTS AND STILL CATCH REGRESSIONS

Line-by-line comparison with 626bae4 (diffs were rebuilt independently):

test_history_fireability.py:
- Every original assertion is still present, unchanged:
  - 30 verified episodes and the composition 1/18/2/12;
  - V2B_TABLE;
  - the refused-target sentence;
  - validate_run_plan returns the same plan_hash;
  - 'explorer_selection' not in each older plan, the byte-for-byte SavedRunPlan round trip, and status PLANNED;
  - per pick: REFUSED exactly when every fault is on the status read, and no mixed pick;
  - counts (3, 7), 8 and 8;
  - test 3 is unchanged (2 replays, SKIPPED then SELECTED, 0/4).
- What changed:
  - the plan is built with store.max_record_rowid returning 6748;
  - the old "every plan except mine" loop became "the 5 plans at the snapshot", with the count now asserted. The unpinned loop would also have hit v2g's own plan, which declares the rule, so the new loop keeps the original meaning (plans saved before the rule);
  - selections are read at or below 6748.
- New checks, all stricter:
  - the "now" read happens exactly once;
  - record_cutoff is 6748 and the summary hash is d581867c…;
  - history, replay and table equal v2g's saved plan.

test_loop_limits_mechanic_context.py:
- Only the four list reads are bounded at 3022, plus a new assertion that v2d's campaign row is at or below 3022.
- Every assertion is unchanged, including 33,223, [33611, 28056, 21101], the omission statement, the block counts and the kept episodes.

test_diagnosis_rules T1 (a round file) reads plans at or below 8583 and asserts the exact six campaign ids.

Independent store read (scratch copy, read-only) confirms every pinned number:
- max row 8583, with no gaps;
- v2g's plan is at row 6751, froze at 6748, hash d581867c…, 30 episodes;
- v2e's plan froze at 3022, and v2d's own records end at row 3020;
- all three matching v2d challenge evaluations are at or below 3022 (rows 2367, 2552, 2802);
- 5 plans are at or below 6748 and 6 at or below 8583;
- the 26 model picks at or below 6748 = 3+7+8+8;
- plans and selections are immutable records.

E1 (my strongest check):
- The original 626bae4 test files, with not one line changed except the store path, pass 3 of 3 on a copy of the store truncated at row 6748.
- On today's store they fail with exactly "36 == 30" and "14 == 8".
- The original v2d test passes at 3022 and on today's store.
- So the old expected numbers are exactly the store at the pinned row.

E3 (growth control): I added 3 synthetic later-run records above row 8583: a copy of v2d's challenge evaluation, a mixed status-read pick, and a later plan with mechanic_diagnosis.
- The pinned tests pass: 3 fireability tests, the v2d test and T1.
- The unpinned originals fail: 36 == 30; True == False (the mixed pick); and the v2d rebuild pulls in the later campaign's evaluation.

E2 (my own 15 mutations, in a scratch copy, file restored and hash-checked after each; the control passed 116 before and after):
- 14 were caught:
  - store reads ignoring the cutoff;
  - Start re-checking history at today's row;
  - history dropping baseline-study episodes;
  - double-counted fired faults;
  - challenge picks never refused;
  - replay cap 1;
  - format-repair reserve −1000;
  - a second "now" read;
  - A1 to A6 below.
- The mixed-pick inversion is not observable on the snapshot, which has no mixed pick; the original test had the same limit. It is caught by 3 tests in test_history_fireability_review_fixes.py.

Other live-store readers: my own search agrees with the fixer's.
- The only tests reading /Users/shree/FaultLab_Runs are the five files above.
- test_citation_status's v2e/v2d rebuilds read only those finished campaigns' own records.
- Its new-plan test asserts nothing that depends on other records.
- The artifacts/lab.sqlite3 probe tests select by created_at/started_at cutoffs before Sep 24, by declared configurations or by explicit ids. That file is the default dashboard store, but its data file was last modified Sep 27.

(2) checks_note

- An AST comparison with the prototype shows the product CHECKS_NOTE equals the draft note minus exactly its one C6 sentence: 2 sentences, no C1-C8 id, no "citation".
- MEANING, KINDS, CONTRACT_NOTE, USE and HYPOTHESIS_LENGTH equal the draft.
- The C6 sentence appears nowhere in the module, the declaration, the block, or the 5 GUIDE requests of the new probe plan. Each of those requests carries exactly the product block.
- Numbers:
  - declaration hash def60594… (product function);
  - block sha256 dedf43f2…;
  - DIAGNOSIS_GUIDE_OFFERED = False;
  - interprets_checks is False.
- Token arithmetic holds: every GUIDE = CONTROL + 608 (the fixer's plan had +569, the version without the note).
- Plan diff against the fixer's plan: only the 5 GUIDE requests, the declaration hash, the tighter bound (2.903906 → 2.906461) and the plan hash differ. Plan hash 91ca47e4… is self-consistent. The harness sha is b1eb7cda… and matches the harness file (unchanged).
- Probe inputs: 5 of 5 OK.
- The template's plan_hash is 91ca47e4….
- Mutations caught:
  - A1: note loses its period;
  - A2: C6 sentence back;
  - A3: guide offered;
  - A4: block without the note;
  - A5: plan model accepts interprets_checks=True;
  - A6: FIXED_TEXT stops binding the note.

(3) NOTHING OUTSIDE THE TASK CHANGED

Against verify/COMMIT_LIST.txt:
- 13 of 21 product files are byte-equal.
- 8 changed, exactly the fixer's list: diagnosis_guide.py, run_plans.py, test_diagnosis_rules.py, test_diagnosis_probe.py, loopLimits.ts, diagnosis-rules.test.tsx, the doc and CURRENT_STATUS.md.
- 2 committed tests were added: test_history_fireability.py and test_loop_limits_mechanic_context.py.
- All 222 earlier evidence files verify.
- All 63 followup/ files verify.
- tree_vs_backup shows no other change.

The run_plans.py change is the one checks_note field, bound through FIXED_TEXT.

Code sha256 equals the pre-suite record, and every code file was last modified before the suite started.

The suite log confirms exit 0:
- backend 3,135 passed, 180 skipped;
- frontend 373 passed;
- build passed;
- browser 19 passed, 1 skipped;
- 1,113 monitor samples, 0 non-loopback.

Identity (re-run with the product's functions): equal to the fixer's identity-end.json.
- 5 changed from the verified round: runtime 1abba8a6…, algorithm 0b34473c…, guide declaration def60594…, and the two example configuration hashes.
- 45 unchanged, including native v1 prompt 22515428…, v2.1 prompt fff397c9…, scorer 19de811c… and Rule 1 998744f8…/c4dd868c….

gate_freeze (audit JSONs dropped): byte-identical to the fixer's current.json.
- Against the verified round: 20/20 files (checks.py included) and 30/30 functions identical; only the algorithm, runtime and tree_lab fingerprints changed.

Git and saved stores:
- HEAD cbbf957; backup 626bae4; the index sha is e253a478… and its time is unchanged; the refs hash is a9d3adeb…, identical to the fixer's end record.
- The 638 saved-store files are identical at my start and end, and identical to the fixer's after-suite record.

How I ran things:
- Scratch copies were under /Users/shree/FaultLab_Scratch/followup-review/, deleted afterwards.
- Plan-building tests in scratch used a stub (rstub.py). It supplies only the promotion manifest's three comparison facts, so audit/promotion.json was never opened. The unmutated scratch baseline passed 154 of 154 with it.
- I did not re-run test.sh or the frontend tests. I relied on the fixer's log plus the unchanged code hashes.

## Findings

- **N1 (LOW (action before commit))**: verify/COMMIT_LIST.txt is stale. 8 of its 21 product lines now have different sha256 values: diagnosis_guide.py, run_plans.py, test_diagnosis_rules.py, test_diagnosis_probe.py, loopLimits.ts, diagnosis-rules.test.tsx, the doc and CURRENT_STATUS.md. Two committed test files are modified but not listed at all: backend/tests/lab/test_history_fireability.py and backend/tests/lab/test_loop_limits_mechanic_context.py. The followup/ (63 files) and followup-review/ evidence folders are also missing from it. Fix: Regenerate the commit list with verify/commit_list/commit_list.py after this review, and run its secret scan. Include both modified committed tests. Force-add followup/ and followup-review/, since artifacts/ is git-ignored.
- **N2 (LOW (PM decision before the probe declaration is signed))**: The declaration's `rule` sentence lists what the block contains but does not mention the restored note on reading the checks. The dashboard line does mention it. The sentence is still true: it says the guide interprets no check. But it is part of the hashed Rule 2 declaration (def60594…), and the probe plan 91ca47e4… embeds that hash. The fixer flagged this as its own choice. Fix: PM confirms keeping the sentence as it is. If the PM wants the note listed, change RULE now. Then regenerate the declaration hash, the probe dry run and DECLARATION.template.json before anyone approves the probe. The GUIDE request bytes would not change.
- **N3 (INFO)**: The new assertion `now.call_count == 1` in saved_v4_plan fails if a future product change reads max_record_rowid a second time while preparing a plan, even a harmless read. My mutation B9 failed 3 tests with 'assert 2 == 1'. This is stricter than before, not weaker, and it fails loudly. Fix: No change needed. Anyone who adds a second 'now' read to plan preparation must revisit the pin.
- **N4 (INFO)**: The snapshot fixes a set of row numbers, not the rows' contents. Some rows at or below the cutoff are mutable (for example 204 episodes, 14 evaluations and some counterexamples), so they could in principle be edited in place later. The pins already guard this: the history summary hash is pinned, plans and selections are immutable records, and an edit to v2d's records would fail the exact 33,223 and [33611, 28056, 21101] assertions loudly rather than pass silently. Fix: No change needed.
- **N5 (INFO)**: Inverting the mixed-pick rule (refuse a pick when ANY fault targets a REFUSED row) cannot be seen on the pinned snapshot, because it has no mixed pick and the test asserts that. So the saved-store tests do not catch that mutation. The original 626bae4 test had the same limit. test_history_fireability_review_fixes.py catches it with 3 failing tests. Fix: No change needed.
- **N6 (INFO (report wording))**: The report says 'Only run_plans.py and test_history_fireability.py differ from the verified state'. That is true only within the byte-identity file list. In total, 10 files differ from the verified state (8 round files and 2 committed tests), which the report lists correctly elsewhere. Fix: Reword it in any summary as 'of the files in the byte-identity list'.
- **N7 (INFO)**: Git's empty-blob object (e69de29…, 0 bytes) had its file time refreshed at 21:30:26Z. That object is one inode, hard-linked between .git/objects and artifacts/product-dependability-2026-09-29/clone/.git. The refresh came after the fixer's end record (21:29:01Z) and 10 s before this review started; it was most likely a git operation by the host app. The content is fixed by its hash, and the index and refs are unchanged. Fix: No action.
- **N8 (INFO (method))**: The fixer's scratch runs symlinked the whole audit/ folder, so product tests read audit/promotion.json through the link, as scripts/test.sh does in the real tree. The verifier and this review kept that file unreadable in scratch. For plan-building tests I used a stub that supplies only the manifest's hash, case count and trials per case. The unmutated baseline passed 154 of 154 with the stub. Fix: Optional: future stages could reuse followup-review/rstub.py so that scratch runs never open promotion.json.
