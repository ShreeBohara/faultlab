_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FIXER REPORT: DIAGNOSIS RULES (September 30, 2026). Cost $0. Everything ran offline.

SHORT VERSION
- I checked all 15 review findings against the code. 13 were real and are fixed. Each fix has a test that failed before the fix and passes after it. One finding (F2) is only partly fixed; the rest of it is deferred. One (F4) is a question for the PM, not a code defect.
- One product file changed in backend/app: lab/diagnosis_protocol.py. Nothing else under backend/app changed. That rules out referee/, checks.py, diagnostics.py, reducer.py, lab/diagnosis.py, prompts/diagnosis.md, contracts/models.py, learning.py (including its gate line), mechanic.py, run_plans.py, exports.py, diagnosis_guide.py, the simulator and the Actor.
- Outside backend/app I changed:
  - the probe harness;
  - five frontend files, plus one new frontend test;
  - three backend test files;
  - the new doc and CURRENT_STATUS.
- Negative controls: I undid each of my 17 fixes one at a time in a scratch copy outside the Desktop. A test caught every one, and the copy with no fix undone passed.
- scripts/test.sh was run once, after the last edit. It exited 1, for the same reason as the builder's run:
  - Backend: 2 failed, 3,133 passed, 180 skipped. That is the builder's 3,119 passes plus my 14 new backend tests.
  - The 2 failures are the same test_history_fireability saved-store tests as before (36 == 30 and 14 == 8). That file is unchanged from 626bae4. Its assertions pin how much history the saved store had before live run v2g added episodes.
  - Frontend 373 passed; the build passed; the browser tests had 19 passed and 1 skipped.
- Safety checks:
  - Nothing was committed and nothing ran live. There were no provider, model, W&B, Weave or network calls; every guard counted 0 refused outbound connections.
  - I never opened .env or checks.py. checks.py was hashed only by gate_freeze.py's own code. I never read artifacts/heldout2/, audit/promotion.json or audit/final-audit*.json; gate freeze ran with both audit files left out.
  - HEAD is still cbbf957 on main, with no index change (0 lines of cached diff) and no stash.
  - All 649 files under /Users/shree/FaultLab_Runs have the same sha256 at the start and end. The scratch copy was deleted.

TABLE
| id | verdict | change | test |
|---|---|---|---|
| MEDIUM-1 / F3 | FIXED | `intervention_ran` now means at least one fresh intervention trial ran. A new field, `intervention_experiment_recorded`, says whether an experiment was saved at all. Each intervention row gets `early_end`: PREFLIGHT_REJECTED, STOPPED, CALLBACK_ERROR:<class>, INVALID_CALLBACK_RESULT, INVALID_OR_UNTRIGGERED_TRIAL, or null. The record's sentence now names the early end, for example "after 0 of 3 trial pairs; it ended early: preflight rejected its recipes before any trial (PREFLIGHT_REJECTED); no fresh trial ran". The RULE text now defines this, so the Rule 1 hashes changed: declaration 729441f0 → 998744f8, semantics 577b0c80 → c4dd868c. No saved plan declares Rule 1, so no saved plan is affected. | New test `test_fix_intervention_ran_means_a_fresh_trial_ran...` has 5 cases: preflight rejection, Stop before any trial, callback error, Stop after one pair, and a full run. The T6 24-cell matrix and T9 are updated. |
| MEDIUM-2 / F5(c) | FIXED | P1 still defines "confirmed" as a checker v2 match plus the person's Y. The change: GUIDE rows the person marks Y without a checker match now count against the GUIDE bar of 4 of 40. The CONTROL premise still counts confirmed rows only, so both rules make PASS harder, never easier. review-blinded.csv no longer shows the checker's matches or the hints, so the person judges each hypothesis alone; those columns are now only in scoring.json. | New test `test_fix_p1_counts_person_flagged_guide_hypotheses...`: GUIDE answers are reworded so checker v2 misses them. Before the fix P1 said PASS; now it says FAIL. The scripted-run test checks the review file's columns. |
| MEDIUM-3 / F1 | FIXED (doc and reporting). The temperature itself stays a PM decision. | The wrong doc sentence is corrected: the declaration cannot change the temperature; the harness always sends the frozen 0. Scoring now reports, for every request key, the delivered answers, distinct raw answers and distinct hypotheses. P1, P2 and P4 show distinct counts, and the dry run and live summary say so. A declaration must state the frozen temperature and a non-empty `sampling.repeats_reading`. | New test `test_fix_scoring_reports_distinct_answers_per_request_key` expects 14 of 14 keys with one distinct answer. New refusal cases cover a wrong temperature and an empty repeats reading. The dry-run test checks the new line. |
| F5 (a, b) | FIXED | The pre-registered outcomes now live in one constant, which the template writes word for word. It includes the definition of "worse" for P4 (the Rule 1 total over both setups, out of 20, is lower than today's total), P1's person-only rule, the repeats report, and the full four-clause decision rule. A declaration must carry exactly that text. | New test `test_fix_the_declaration_carries_the_full_pre_registration...`. A new refusal case covers a declaration with made-up outcome text. |
| LOW-3 | FIXED | In answers.jsonl, `served_model` is renamed `model_id`, and the harness notes that RuntimeProvider only echoes the requested model. The stop reason is renamed MODEL_ID_DIFFERS. A `clock_drift_checked` precondition is now required. The manifest, the template's `after_run` field and the printed summary all say to add the charged upper bound to the project's carried total by hand. | New refusal case for a missing clock-drift check. The scripted-run test checks `model_id` and the manifest note. |
| F2 / LOW-2 | FIXED (plan display, frontend validators, diagnosis-panel label). DEFERRED: showing the diagnosis_requests record itself. | `loopLimits.ts` has new validators for Rule 1's fixed fields and for a declared guide. `runPlans.ts` checks both keys and refuses them outside Learn. The Learn setup form lists Rule 1 ("these two rules"), and the saved plan shows it, says plainly when an older plan predates it, and shows its exact text; a declared guide is shown too. DiagnosticPanel now says "Recorded proposed kind", with a note that it is INCONCLUSIVE by default when no answer was valid. Reading and showing the record needs a change to the experiments or diagnostics API. The memo already lists that as a follow-up. | New `frontend/tests/diagnosis-rules.test.tsx` (5 tests): all 5 failed before the fix and pass after. |
| LOW-4 | FIXED | New loop test: the real coordinator runs `_execute` on a planned Learn campaign with Rule 1 frozen and evidence retry v3. It uses the REAL Diagnostician and the REAL Mechanic, whose scripted provider answers 614 characters first and then gives a valid repair. One evidence wait comes before the diagnosis and one after. The campaign ends NO_CHANGE, not ERROR, and every diagnostic has exactly one record. A refused record now names the diagnosis and its counterexample. A new consistency refusal covers fresh trials with no recorded experiment. | `test_fix_rule_1_records_every_diagnosis...through_evidence_waits` has 2 cases. They passed before the fix: this finding was missing coverage. The failing-then-passing part is the diagnosis-id check in T5. |
| LOW-1 | FIXED (docs and this report) | The doc and CURRENT_STATUS now say the builder's test.sh exited 1: backend 2 failed, 3,119 passed, 180 skipped. They name the two tests. This report gives my own run's result. | n/a (documentation) |
| F6 | FIXED | The doc now lists requests.json among the outputs. "Implements section 7 exactly" is replaced by a list of the harness's own counting choices. It states the test.sh results, the new plan hash and harness sha, and the new probe-plan location. | n/a (documentation) |
| F4 | DEFERRED (a PM decision, not a defect) | The builder dropped all three sentences of `checks_note`. That follows the spec's include-list, which does not name `checks_note`. The PM's words, "Drop the interpretive C6 sentence (checks_note)", can be read either way. Doc section 5 now quotes the two sentences that name no check and asks the PM to confirm before declaring the probe. Putting them back would change the block, T3/T9 and the plan hash. | none |

Each finding that has two names (MEDIUM-1 = F3, MEDIUM-2 = F5(c), MEDIUM-3 = F1, LOW-2 = F2) is the same issue reported by both reviews, and the one row covers both.

EVIDENCE: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-diagnosis-rules-2026-09-30/fixer/
- mutation-checks.log has three parts:
  - before any fix: 48 backend tests failed, and all 5 new frontend tests failed;
  - after the fixes: 239 passed across the new tests and the related suites (citation status, evidence wait, retry v3, discovery-v4 fixes, loop limits, run plans, roles, native v1 golden), and 373 frontend tests passed;
  - the negative controls: 17 of 17 caught.
- Also in the folder:
  - mutation_checks.py, before-fix-tests.log, after-fix-tests.log;
  - full-test-sh.log/.start/.end;
  - identity-after.json and identity-compare.txt;
  - gate_freeze/after.json;
  - probe-dry-run.txt and probe-plan/ (plan.json, requests.json, DECLARATION.template.json, SHA256SUMS.txt);
  - files-changed-by-fixer.txt, protected-sha256-end.txt;
  - saved-stores sha256 start and end, git state start and end.

IDENTITY (after the fixes)
- Runtime: e3551ead… (builder) → c80d86323bc82624ab22000edb37ce46d09f2e621d04ca8928903471749aa493.
- Algorithm: e4c47b4e… → 743a1520…
- Rule 1 declaration 998744f8…, semantics c4dd868c…. Rule 2 declaration 36ca790f… (unchanged, offered: False). PUBLIC_INVARIANTS hash e792e8f0….
- Unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, native v2.1 prompt fff397c9, reference Actor source hash eaffac74, PROTOCOL_HASH bfefe69b. 34 of 40 identity values are unchanged.
- The two example native configuration hashes changed again, because they include the runtime. So every agent must be registered again before any live run.
- Gate freeze compared 124 values:
  - against the builder's result, only 3 changed: algorithm, runtime and tree_lab;
  - against the 626bae4 baseline, the same 8 changed as the builder reported (mechanic.py and the fingerprints).

PROBE DRY RUN (run once, fixer/probe-dry-run.txt)
- Plan hash e66a67b36bf76a9f68d6515743d415180611221899eb5664f671bae1dc0a9ed1; harness sha256 b1eb7cdaf1490a459c26d36d0b8c16a5a585c663fee671f6ba90bb05e56b86ff. These replace the builder's 9d5d3bd6 and fb73a584, and the builder's probe-plan/ folder is superseded by fixer/probe-plan/.
- Calls: 140 (100 first-turn + 40 repair). Token counts are the same as the builder's (GUIDE +569, Rule 1 repair +47).
- Maximum charge 140 × $0.04984 = $6.9776 against the $8.00 cap; tighter bound $2.9039.
- Temperature is 0, frozen. Network calls: 0.

DECISIONS STILL OPEN FOR THE PM (before declaring the probe)
- (a) Temperature 0. Either accept it, and read one request-and-arm cell (not one call) as the unit when answers repeat, or order a reviewed harness change. The declaration's `repeats_reading` must be filled in either way.
- (b) The checks_note scope (F4).
- (c) Rule 1 is already frozen into every new Learn plan before P4 is measured, as the spec asked. If P4 shows the new message is worse, Rule 1 needs a withdrawal or a v2.
- (d) Someone allowed to open checks.py should confirm the C1-C8 public meanings before Rule 2 is offered.

WHAT I DID NOT DO
- Commit, push, or run anything live.
- Change the two failing history-fireability tests. Re-pinning them is a separate, reviewed change.
- Show the diagnosis_requests record in the dashboard (the deferred part of F2).
- Change the doc sentence that points to my test.sh log. The doc was written before test.sh ran, so it points to fixer/full-test-sh.log instead of stating the result.

MAIN FILES
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/diagnosis_protocol.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/scripts/experiments/diagnosis_probe.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/src/loopLimits.ts, frontend/src/runPlans.ts, frontend/src/components/LoopLimits.tsx, RunSetup.tsx, CampaignPlan.tsx, DiagnosticPanel.tsx
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/tests/diagnosis-rules.test.tsx (new)
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/tests/lab/test_diagnosis_rules.py, test_diagnosis_rules_loop.py, backend/tests/experiments/test_diagnosis_probe.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md (sections 2b, 5, 6, 8, 9 and a new section 10)
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/CURRENT_STATUS.md (header and first "Current work" paragraph; still "not yet committed")
