_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

INTEGRITY REVIEW: DIAGNOSIS RULES BUILD (September 30, 2026). Cost $0, all offline.

Scope: the builder's changes against backup/part2-2026-09-22 (626bae4). HEAD is still cbbf957 on main. The index is untouched (0 lines of cached diff) and there is no stash.

Evidence I produced: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-diagnosis-rules-2026-09-30/review-integrity/
- rerun-new-tests.log
- probe_adversarial.py and probe-adversarial-output.txt
- record_edge_cases.py and record-edge-cases.json
- run_gate_freeze.py and gate-freeze-now.json
- identity-now.json
- saved-stores-sha256-start.txt and saved-stores-sha256-end.txt
- reviewed-files-sha256.txt
- git-state.txt

WHAT CHANGED
I compared every file tracked in 626bae4 (2,787 files) with the working tree using git blob hashes. Only 7 tracked files differ:
- CURRENT_STATUS.md
- backend/app/agents/mechanic.py
- backend/app/lab/exports.py
- backend/app/lab/learning.py
- backend/app/lab/run_plans.py
- backend/tests/lab/test_evidence_wait.py
- backend/tests/lab/test_discovery_v4_review_fixes.py

Plus 7 new files:
- backend/app/lab/diagnosis_protocol.py
- backend/app/lab/diagnosis_guide.py
- scripts/experiments/diagnosis_probe.py
- backend/tests/lab/test_diagnosis_rules.py
- backend/tests/lab/test_diagnosis_rules_loop.py
- backend/tests/experiments/test_diagnosis_probe.py
- docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md

Nothing else under referee/ (including checks.py, diagnostics.py and reducer.py), the simulator, contracts/models.py, lab/diagnosis.py, prompts/diagnosis.md, promotion.py, challenge.py, evaluation.py, citation_status.py, the Actor or prompts/actor.md differs from 626bae4 by a single byte.

(1) NO VERDICT PATH CHANGED: CONFIRMED
- learning.py adds four things and nothing else:
  - two imports;
  - reading the two rules, and setting mechanic.diagnosis_protocol;
  - two optional wrappers;
  - one record() call placed after Diagnostician.run and before the gate.
- The gate line "if diagnostic.kind!='POLICY_GAP': continue" is unchanged and appears once.
- classify_policy_gap, run_interventions and the Diagnostician are untouched.
- I re-ran the 83 new tests plus tests/agents/test_roles.py: 93 passed (rerun-new-tests.log). That includes the 24-cell T6 matrix, which compares kinds, intervention records, ledger logs, runner calls and trials with the rule off and on.
- I re-ran gate_freeze.py (its own code, with the two audit files left out) on the current tree. It is identical to the builder's after.json.
  - Against the builder's before.json, only 8 values differ: mechanic.py (the file and its Mechanic class) and the algorithm, runtime, source and tree_lab fingerprints.
  - tree_referee, the scorer, service, contract and interpreter values are unchanged.
  - I also checked that before.json's file hashes equal 626bae4's blobs.
- I recomputed identity with the product's functions. It is byte-identical to builder/identity-after.json:
  - runtime e3551ead…; service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c and native v2.1 prompt fff397c9 are all unchanged.
  - The reference Actor source hash changed, because agents/mechanic.py is in that tree. The builder disclosed this. The Actor's code and prompt are unchanged, but every agent must be registered again.

(2) PART 1a NEVER CUTS OR EDITS MODEL TEXT; THE 600 LIMIT STILL BINDS: CONFIRMED
- repair_errors only adds max_characters (pydantic's limit) and your_characters (the field's length) to string_too_long errors. Every other error keeps today's {location, type}.
- The raw answer is stored and replayed exactly as received.
- REPAIR_INSTRUCTION is today's sentence, unchanged, plus the memo's sentence word for word.
- The rule applies only when the rule is set and the prompt is diagnosis.md.
- The code path with the rule off keeps today's exact line. The T2 golden-byte test matches all 5 of investigation A's rebuilt requests.
- In the tests, a 601-character hypothesis fails in both modes and a 600-character one passes.
- models.py (Text max_length=600) is byte-identical to 626bae4.

(3) THE RECORD IS TRUTHFUL AND EXPORTS KEEP EVERY ATTEMPT: CONFIRMED, WITH ONE MEDIUM ISSUE
- The status is derived from the proposal that was actually returned:
  - None gives INVALID_OUTPUT and code_default. It also requires the last attempt to have errors and proposed_kind to be INCONCLUSIVE.
  - Otherwise the source is model, and it requires no errors and the model's own proposed_kind.
- A code default cannot be labelled as the model's. A mutation check caught exactly that change.
- If the state does not match, the record raises and nothing false is saved.
- In the export, every attempt is embedded by its mechanic_outputs id, including v2f's rejected attempt 0. Plans that do not declare the rule keep exactly today's keys. The builder's store copy shows 6 of 6 recordings byte-identical under the old and new exports.py.
- MEDIUM-1: intervention_ran is true when the intervention was rejected by preflight, or stopped, with 0 fresh trials. I reproduced both cases (record-edge-cases.json).

(4) RULE 2 IS NOT OFFERED AND NOT FROZEN: CONFIRMED
- DIAGNOSIS_GUIDE_OFFERED=False gates both run options and prepare_run_plan.
- Plans are created only through prepare_run_plan (api.py), so a client cannot inject the key.
- Start validates a declared guide exactly, including the frozen C1-C8 text and its hash.
- The block contains only:
  - fixed text: meaning, kinds, contract_note, use, hypothesis_length;
  - PUBLIC_INVARIANTS verbatim, hash e792e8f0;
  - the campaign's task_text.
- The whole checks_note is dropped, which is a defensible reading of the PM decision. No fixed sentence names a check.
- It reads nothing from episodes or scoring.
- It is the design-minimal draft's block minus checks_note, with the same kinds wording.

(5) PROBE HARNESS: CONFIRMED, WITH TWO MEDIUM ISSUES ABOUT THE PROBE'S DESIGN
I ran probe_adversarial.py under a stricter guard than the builder's. It refuses any .env open, creating any AF_INET or AF_INET6 socket, getaddrinfo, gethostbyname and create_connection. Guard violations: 0.
- Dry run, both with no flags and with --dry-run: exit 0, nothing written, no provider built, no network.
- 16 refusal cases all exit 2, with no provider built and no output folder created:
  - no declaration; no --out; wrong sha256; a sha256 without a file;
  - caps of $9, $6, true and "8";
  - a different harness, plan or model;
  - no approver; a precondition set to false; missing outcomes; a different folder; a non-empty output folder.
- Scripted runs:
  - All answers OK: 140 calls charged at $6.9776.
  - Every call failing with a connection error: 160 provider calls, $7.9744 charged, still at most $8.
  - A declared cap of $7: 0 retries allowed, 140 calls charged.
  - A different served model: stops after 1 call.
  - An unexpected exception: ABORTED after 1 charged call.
- Every call is charged on the ledger before it is sent. CampaignLedger enforces the dollar cap in consume_call, and retries come only from unreserved capacity.
- Files are written only under --out. No repository file changed, and the scratch folders were deleted.
- The inputs are byte copies of investigation A's requests (all 5 sha256 values match). The harness's sha256 is fb73a584…, as reported.
- MEDIUM-2 (P1 scoring rule) and MEDIUM-3 (temperature) concern whether the probe can answer its question. They do not affect its safety.

(6) GATE FREEZE, NETWORK AND .ENV: CONFIRMED
- The gate-freeze and identity checks are described in (1).
- The tests run under conftest's network and .env guards; my scripts added their own stricter guards, with 0 violations.
- No .env was opened.
- All 624 saved-store files under /Users/shree/FaultLab_Runs have the same sha256 before and after my review, compared in sorted order.
- No bytecode was written.
- /Users/shree/FaultLab_Scratch/product-diagnosis-rules/review-product/ (empty, created 11:32) belongs to a concurrent reviewer, not to the builder or to me.

OTHER OBSERVATIONS
- The builder's report does not say that scripts/test.sh exited 1: the backend stage had 2 failed, 3119 passed and 180 skipped (LOW-1).
  - The two failures are in test_history_fireability.py, a file unchanged from 626bae4. Its assertions (36==30, 14==8) count history in the saved store, not anything about diagnosis. So I accept that the failures were there before this build, but I did not re-run them on 626bae4 code.
  - CURRENT_STATUS.md and the new doc do mention them.
- The CURRENT_STATUS edit that says the previous build was committed as 661e2d0 and run live once (v2g) is accurate: 661e2d0 and a7a6ab9 are on the backup branch.
- The pytest saved-store test copies the store to pytest's tmp_path. That is outside the Desktop and read-only, but not /Users/shree/FaultLab_Scratch as the stage rule says. This is a minor deviation that follows an existing helper.
- Rule 1 is already frozen into every new Learn plan, before P4 is measured. That is what the spec asked for. If P4 later shows the new message is worse, a withdrawal or a v2 will be needed.

MY OWN DEVIATION (disclosed)
To compare the working tree with 626bae4, I ran `git hash-object --stdin-paths` over every tracked path. Those paths include backend/app/referee/checks.py, audit/promotion.json and audit/final-audit.json.
- git read those three files' bytes to compute hashes. I never printed, opened or examined their contents.
- I used only the equality result: all three are unchanged from 626bae4.
- This goes beyond the letter of "hash checks.py only via the repo's identity/gate-freeze code" and "never read audit/promotion.json or final-audit*.json". The user should know.
- artifacts/heldout2/ is not tracked and was not touched.

NOT DONE
- No live call, no commit, and I did not re-run scripts/test.sh.
- I did not run the two fireability failures on 626bae4 code.

## Findings (structured)

- **MEDIUM-1 (MEDIUM)** `backend/app/lab/diagnosis_protocol.py`: The record says intervention_ran: true when the requested intervention never ran a single fresh trial: when preflight rejected the treatment recipe, or when a Stop arrived before any trial. Its plain-English statement then says only 'Intervention result: <id> INCONCLUSIVE'. The purpose of Rule 1b is to stop exactly this kind of misreadable summary; the v2g run-doc error came from trusting one. Evidence: review-integrity/record-edge-cases.json, built with the builder's own helpers (real Mechanic, Diagnostician and classify_policy_gap). PREFLIGHT_REJECTED gives intervention_ran true, fresh_intervention_trials 0, trial_pairs 0, limitations ['PREFLIGHT_REJECTED']. A Stop before any trial gives the same values with limitations ['STOPPED']. build_record sets 'intervention_ran': bool(run.experiments). The builder's T6 test asserts intervention_ran is True in the PREFLIGHT_REJECTED cells (test_diagnosis_rules.py, T6). Fix: Before any plan freezes this rule, define intervention_ran as 'at least one fresh intervention trial ran' (for example any(e.trial_pairs for e in run.experiments), or run.trials non-empty). If needed, keep a separate intervention_experiment_recorded. Make the statement name the limitation, such as 'rejected by preflight before any trial' or 'stopped before any trial'. Update RULE and semantics_hash, and T6. Nothing has been committed or run live, so this costs nothing now.
- **MEDIUM-2 (MEDIUM)** `scripts/experiments/diagnosis_probe.py`: P1 counts a hypothesis as blaming citations or labels only if checker v2 matches it automatically AND a person marks Y. A hypothesis that only the person flags is reported but does not count. Checker v2 is a narrow phrase list ('undelivered', 'never shown', 'undecodable', ...), not a detector of 'blames citations, labels or evidence ids'; phrases the memo itself quotes, such as 'shown-order label contract', do not match. The guide's CONTRACT_EVIDENCE_GAP definition names 'the adapter's evidence labels', so the GUIDE arm may reword its citation blame in ways the checker misses. That tilts the pre-registered bar (GUIDE at most 4 of 40) toward PASS. This follows the spec's wording literally; it is a design choice the PM must settle before the declaration is hashed. Evidence: _p1: confirmed = matched rows with human 'Y'; person_only is 'descriptive'. The CLAIM regex is in check_evidence_gap_misreading_v2.py lines 57-65. RECOMMENDATION.md 1.4 quotes 'shown-order label contract' and 'unshown first write attempt' as the Mechanic's wording. Fix: Before declaring, decide and pre-register: score P1 from the person's Y on every delivered dev-5 row (review-blinded.csv already has that column for all rows), and report checker matches separately as an aid. Or keep 'both' but also report, and count against the GUIDE bar, person-only flags. Consider removing the auto_claim columns from the blinded CSV so they cannot steer the person.
- **MEDIUM-3 (MEDIUM)** `docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md`: The builder correctly flagged that the frozen temperature is 0, so 10 repeats of the same request may be near-identical. But the doc and CURRENT_STATUS say the choice of 'a different temperature for the probe only' can be made in the declaration. It cannot. RuntimeProvider.complete always sends temperature=MODEL_REQUEST_SETTINGS['temperature'] (0), and neither the harness nor the declaration has a temperature field. A different temperature needs a harness code change, which changes the harness sha and the plan hash, and it would no longer be the product's exact request path. At temperature 0 the 40-call cells may hold about 4 distinct answers, so the P1/P2/P4 bars and Fisher tests, which assume independent samples, could mean far less than they appear to. Evidence: backend/app/providers/runtime.py:19-21 (MODEL_REQUEST_SETTINGS temperature 0) and the complete() call passing temperature=MODEL_REQUEST_SETTINGS['temperature']. declaration_template has no temperature field. Doc section 5: 'whether to keep that, or declare a different temperature for the probe only, is a PM decision to make in the declaration'. Fix: Correct the sentence. Before declaring, the PM should either (a) accept temperature 0 and pre-register reporting of distinct answers per request-arm cell, treating the cell rather than the call as the unit when interpreting P1-P4, or (b) order a reviewed harness change that sends a declared temperature and is re-verified offline.
- **LOW-1 (LOW)** `artifacts/product-diagnosis-rules-2026-09-30/builder/full-test-sh.log`: The builder's report does not state that the one scripts/test.sh run exited 1: the backend stage FAILED with 2 failed, 3119 passed and 180 skipped. It lists only 'the pre-existing-failure log' among its evidence. CURRENT_STATUS.md and the new doc do mention the two failures. Evidence: full-test-sh.log: 'FAILED backend (exit 1, 1164 s)'; test_history_fireability.py::test_a_new_v4_plan_on_the_saved_store_refuses_the_lone_status_read_target (36==30) and ::test_the_saved_stores_status_read_picks_are_refused_and_its_other_picks_are_allowed (14==8). The test file is unchanged from 626bae4, and its assertions count saved-store history that grew with v2g. Fix: State the exit status plainly in the report and the evidence index. Optionally repair or re-pin those two saved-store tests in a separate, reviewed change.
- **LOW-2 (LOW)** `frontend/src/components/RunSetup.tsx`: Rule 1 is frozen into every new Learn plan and listed in the backend's run options, but the dashboard does not show it before Start: neither RunSetup nor CampaignPlan renders mechanic_diagnosis. Earlier rules (mechanic_context, mechanic_evidence) are shown to the operator before Start. The builder listed only DiagnosticPanel as a follow-up. Evidence: RunSetup.tsx:76 and CampaignPlan.tsx:25 pass only mechanicContext, challengeSelection and mechanicEvidence. The frontend validator in runPlans.ts ignores unknown keys, so the new key is silently accepted. Fix: Add Rule 1 to the offered-rules and plan-facts views (a follow-up; no gate impact), or record explicitly that it is not shown.
- **LOW-3 (LOW)** `scripts/experiments/diagnosis_probe.py`: The probe charges only its own CampaignLedger (probe-ledger.sqlite3 in --out). Its spend is not visible in any product campaign ledger or dashboard total, so the running ledger figure ($923.53) must be updated by hand. answers.jsonl's 'served_model' is the configured model that RuntimeProvider echoes, not a model the provider reported. The declaration's preconditions omit check_clock_drift.py (memo section 6), which matters less for a request-only probe. Evidence: execute(): LabStore(out/'probe-ledger.sqlite3'). RuntimeProvider.complete returns RuntimeGeneration(model_id=model), where model is self.role_model(role). verify_declaration checks only ledger_checked, dashboard_closed and no_other_paid_run. Fix: In the declaration and the post-run write-up, require adding manifest.estimated_actual_dollars_from_reported_tokens and the charged upper bound to the project ledger. Rename served_model to requested_model, or note what it means. Decide whether a clock-drift precondition applies.
- **LOW-4 (LOW)** `backend/tests/lab/test_evidence_wait.py`: Rule 1 adds a new hard-failure path: build_record raises RuntimeError, and the campaign ends ERROR, when the recorder's state does not describe the diagnosis. To keep them passing, two existing loop harnesses (evidence wait / evidence retry v3, and the discovery v4 review fixes) now switch Rule 1 off. As a result, Rule 1 is never exercised together with evidence waits or the v4 replay paths; only the offline_fixture campaign and the native loop test cover it inside the loop. In today's product the Diagnostician always calls the Mechanic, so no live path is known to trigger it. Evidence: The diffs of test_evidence_wait.py and test_discovery_v4_review_fixes.py each add monkeypatch.setattr(diagnosis_protocol, 'campaign_rule', lambda store, campaign: None). The builder's report (c) says the campaign ends ERROR without that patch (14 failures). Fix: Add one loop test with the real Diagnostician and Mechanic, Rule 1 declared, and an evidence wait or retry after the diagnosis, asserting exactly one record per diagnostic and no ERROR. Optionally make the RuntimeError message name the diagnostic id so an operator can act on it.
