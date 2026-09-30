_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

PRODUCT REVIEW: diagnosis rules (September 30, 2026). Cost $0, everything offline. I changed no product file. Evidence is in faultlab/artifacts/product-diagnosis-rules-2026-09-30/review-product/.

SHORT VERSION
- The builder's main claims hold up. I checked each one independently:
  - Rule 1's repair turn states the limit.
  - Every diagnosis gets a truthful record, written before the POLICY_GAP gate.
  - The five saved diagnoses replay to exactly the statuses the memo predicted.
  - The Rule 2 block is the draft with checks_note removed (+569 tokens), and it is not offered.
  - The probe's dry run gives 140 calls with a maximum charge of $6.9776 against the $8 cap, and it refuses clearly without a matching declaration.
  - The identity values match the builder's.
- No HIGH findings. There are 2 MEDIUM and 4 LOW. Details are in the findings list.
- My guard counted 0 refused outbound connections or DNS lookups in every script. HEAD is still cbbf957, the index equals HEAD and there is no stash. No new files exist outside review-product/. The saved stores have the same sha256 before and after (native-v2b 8aa9aa27…, native-v2 5ccb1842…), and the scratch copies are deleted. /Users/shree/FaultLab_Scratch/inv-a was already there and is untouched.

WHAT I CHECKED, AND WHAT I FOUND

(1) A scripted Learn campaign with Rule 1
Files: checks/test_r1_scripted_learn_campaign.py and checks/test_r1b_planned_export_api.py; results in loop-evidence/*.json.

1A. The real loop (original_loop_fixture: real coordinator, real localhost simulator, real Mechanic and Diagnostician). The Mechanic's first diagnosis answer had a 614-character hypothesis that requested the offered intervention.
- With Rule 1, the repair turn was exactly {"validation_errors":[{"location":["hypothesis"],"max_characters":600,"type":"string_too_long","your_characters":614}], "instruction": today's text + one space + the memo's sentence}.
- When the scripted repair fit (428 characters):
  - The intervention ran: 6 episodes, SUPPORTED, POLICY_GAP, and the campaign COMPLETED.
  - The record said VALID_REQUESTED, source model, with two attempts (614/600, then no errors) that match mechanic_outputs by id.
  - requested_change was 'remove_primitive:0', not 'removes_violation'.
- Without Rule 1, the same answers got today's repair message and no record was written.
- When the model repeated the 614-character text (exactly what happened in v2g), the record said INVALID_OUTPUT with a code_default source. No intervention ran, the verdict was INCONCLUSIVE, and the statement names "614 of at most 600 characters".
- As in the builder's T8, the fixture campaign has no saved plan, so Rule 1 had to be switched on by patching campaign_rule.

1B. A real saved Learn plan created with prepare_run_plan and create. It froze mechanic_diagnosis and no diagnosis_guide. I ran the diagnosis step the way learning.py does: rules read from the plan, wrappers in the same order, record() before the gate.
- The first answer was 743 characters, v2f-style, and the record said VALID_REQUESTED.
- Store: the diagnosis_requests record is saved and immutable.
- API/export: GET /api/campaigns/{id}/recording returned 200 with a diagnosis_requests row. Its attempt_outputs holds the rejected attempt 0 word for word, which today's mechanic_outputs list still leaves out.
- The record does NOT appear in /api/campaigns/{id}/matrix, in /api/diagnostics/{id}, or anywhere in the frontend: no frontend file mentions diagnosis_requests or proposal_status. The run setup and saved-plan panels do not show the new rule either (finding F2).
- Old plans: a Learn plan saved without the key gets today's repair message, no record and no export key.
- Across all 11 saved stores (21 plans):
  - every plan_hash recomputes;
  - no plan declares either rule;
  - every development recording is byte-identical under this build's exports.py and 626bae4's.
- 13 older plans re-read with extra null keys (evidence_retry, transport_retry and similar). They do exactly the same under 626bae4's reader, so this is not caused by this build (old-vs-new-plan-reader.json: 21/21 identical).

(2) Replaying the five saved diagnoses
File: review_replay_saved_diagnoses.py; results in replay-saved-diagnoses.json.
- Method: each diagnosis context was taken straight from the pinned request files. These are byte copies of inv-a's files, and I did not rebuild them again. Every answer, diagnostic and intervention came from a read-only scratch copy of the v2b store.
- Results:

| Diagnosis | Status | Source | Attempts |
|---|---|---|---|
| v2d | VALID_REQUESTED | model | 1 |
| v2e | VALID_NO_REQUEST | model | 1 |
| v2f | VALID_REQUESTED | model | 2 (attempt 0 at 743/600) |
| v2g dev-5 | INVALID_OUTPUT | code_default | 2 (614/600 twice) |
| v2g dev-6 | VALID_REQUESTED | model | 1 |

- All five match the memo.
- With the rule off and on, first turns equal the saved bytes. With the rule off, repair turns equal the saved bytes. With the rule on, only the last user message changes.
- first_turn_hash equals the hash of the saved first turn.
- v2g's two saved answers are byte-identical.
- The record's options give the real change strings: remove_primitive:0, plus lower_parameter:0:failure_count:1 for dev-6. The saved intervention records' change field still says 'removes_violation' (the known defect at diagnostics.py:72).

(3) The Rule 2 block
File: review_guide_block.py; results in guide-block-check.json.
- The block's keys are protocol, meaning, task, kinds, checks, contract_note, use and hypothesis_length. It equals the memo's draft block with checks_note removed, and every kept text is word for word the draft's.
- checks equals PUBLIC_INVARIANTS word for word, and checks_hash e792e8f0… is frozen and matches.
- The draft still reproduces its saved hash and +631 tokens. The product adds +569 tokens on all five requests, and the removed checks_note is exactly 62 tokens. The largest guided first turn is 10,363 tokens.
- No fixed sentence names a check. Two fixed sentences mention evidence labels: contract_note, and the CONTRACT_EVIDENCE_GAP definition. Both come from the memo.
- The task text in the plan equals the campaign's task text in all four runs.
- DIAGNOSIS_GUIDE_OFFERED is False.
- The builder dropped all three sentences of checks_note, not only the C6 one (finding F4).

(4) The probe harness
Evidence: probe-dry-run.txt, probe-refusals.txt, checks/test_r4_probe_harness.py.
- Dry run under my guard: plan 9d5d3bd6…, harness fb73a584…, output identical to the builder's.
  - 140 calls: 100 first-turn and 40 repair, 10 for each of 14 request keys.
  - Tokens: CONTROL 8,990 / 9,088 / 9,639 / 9,794 / 9,352; GUIDE is +569 on each. Today's repair turns are 10,030 / 10,153 and the Rule 1 repair turns are +47.
  - Maximum charge 140 × $0.04984 = $6.9776, against the $8 cap. The per-call bound equals exactly 32,000 input tokens at $1.31/M plus 2,000 output tokens at $3.96/M. The tighter bound for these requests is $2.9039.
- Refusals: I tried 10 bad inputs through the command line. Every one exited 2 with a clear REFUSED message:
  - no --out;
  - no declaration;
  - the unfilled template;
  - a wrong sha256;
  - a $9 cap;
  - a wrong plan hash;
  - no approver;
  - the dashboard not confirmed closed;
  - a $6 cap;
  - a different output folder.
  In every case no output folder was created and .env was never read.
- Scripted "live" runs, with a fake provider and a temporary folder:
  - the provider received exactly the planned messages, in schedule order;
  - 140 × $0.04984 was charged before sending;
  - nothing was written outside --out;
  - a different served model stopped the run after 1 call;
  - a $6.98 cap admitted the 140 planned calls and no retries.
- Every request is either the saved bytes or exactly one declared change.
- The Rule 1 repair request equals what the real Mechanic sent in check (2).

(5) Identity
File: identity-review.json.
- I ran the builder's snapshot script unchanged, under my own guard. Every shared value equals builder/identity-after.json.
- Runtime is e3551ead…, the algorithm hash is e4c47b4e…, and the reference source hash is eaffac74….
- Unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, v2.1 prompt fff397c9, and PROTOCOL_HASH bfefe69b.
- Protected files at backend/app match builder/protected-sha256-end.txt. Only learning.py and mechanic.py differ from the builder's start, as declared.

(6) Tests
- I ran the builder's new tests plus the related suites: diagnosis rules, the loop tests, the probe tests, the native v1 golden test, citation status, evidence wait and retry v3, discovery-v4 fixes, the loop-limit and run-plan tests, and the run-plan API. 228 passed.
- My 14 review checks passed (pytest-review-checks.log).
- The builder's scripts/test.sh run exited 1: the backend stage had 2 failed, 3119 passed and 180 skipped. Both failures are test_history_fireability saved-store tests, which pin the store's verified-episode count at 30; it is 36 since v2g. CURRENT_STATUS says so; the builder's summary does not.
- I could not re-run them on a 626bae4 export, because those tests need audit/promotion.json, which I may not copy. They touch no diagnosis code.

(7) Docs
- docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md and CURRENT_STATUS are accurate on everything I checked: the numbers, the placement, the record fields and "not yet committed". They are dense but readable.
- Four gaps:
  - The output list leaves out requests.json.
  - "implements section 7 exactly" overstates it; the harness makes its own counting choices (F5).
  - The doc does not say test.sh failed.
  - It says the PM can "declare a different temperature … in the declaration", which the harness cannot do.

NOTES THE PM SHOULD KNOW
- Recording fails loudly. If the wrapper's state does not describe the diagnosis, no record is saved and the campaign ends ERROR, after the interventions have already been paid for. Today's Diagnostician always calls the Mechanic, so this cannot happen in the product.
- Because of that, three test harnesses whose Diagnostician is a stand-in (evidence wait, evidence retry v3, discovery-v4 fixes) now run with Rule 1 switched off.
- If the size rule refuses the repair turn (MechanicContextUnfit), the source gets no diagnosis and no diagnosis_requests record, even though a first answer was charged. Its mechanic_context_records entry names that answer.
- Because mechanic.py changed, the reference Actor's source hash changed. Every agent has to be registered again before any live run.

WHAT I DID THAT TOUCHES THE HARD RULES
- At the start, to list the changed files, I ran git hash-object over every tracked file. That read checks.py's bytes to hash them; nothing was displayed, and its hash equals 626bae4's. No heldout2, audit/promotion.json or audit/final-audit file is tracked, so none was hashed.
- The product code under test loads its own audit manifests, just as scripts/test.sh and the builder's T8 do. I never opened, printed or copied audit/promotion.json or final-audit*.json.

Main files:
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/diagnosis_protocol.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/diagnosis_guide.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/agents/mechanic.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/learning.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/run_plans.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend/app/lab/exports.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/scripts/experiments/diagnosis_probe.py
- /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md
- Review evidence: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-diagnosis-rules-2026-09-30/review-product/

## Findings (structured)

- **F1 (MEDIUM)** `scripts/experiments/diagnosis_probe.py`: The probe runs at the frozen temperature of 0. At temperature 0, the 10 repeats of a byte-identical request may all return the same answer, so each request-and-arm cell could really be one sample. The P1, P2 and P4 bars (at most 4 of 40, at least 20 of 40, at least 9 of 10) would then rest on 4 dev-5 samples per arm and 1 per repair setup. scoring.json never reports how many different answers each cell got, so a pass would look much stronger than it is. The doc also says the PM can choose a different temperature in the declaration, but the declaration has no temperature field, and RuntimeProvider always uses temperature 0. Evidence: I ran a scripted run in which every repeat gave the same bytes (checks/test_r4_probe_harness.py::test_a_scripted_live_run...). All 14 cells had exactly 1 distinct hypothesis, P2 and P4 still reported PASS, and no scoring field mentions distinct answers. probe-plan/plan.json has request_settings.temperature = 0. backend/app/providers/runtime.py:187 sends temperature=MODEL_REQUEST_SETTINGS["temperature"], which is 0 (runtime.py:18-20). declaration_template (diagnosis_probe.py:349-363) has no temperature field. docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md section 5 says to decide the temperature "in the declaration". Fix: Add a count of distinct raw answers and distinct hypotheses for each request key to scoring.json and to the printed summary, and say in the declaration how repeated answers will be read. The PM should decide the temperature before declaring. Keeping 0 is faithful to the product. Any other value needs a harness change (which gives a new harness sha and plan hash) and a note that it departs from the product's request path. Correct the doc sentence.
- **F2 (MEDIUM)** `frontend/src/components/LoopLimits.tsx`: The dashboard does not show Rule 1 anywhere. Every earlier plan rule (mechanic_context, challenge_selection, mechanic_evidence, explorer_selection) is checked in runPlans.ts and shown in Run setup ("Every new Learn plan also freezes this rule") and in the saved-plan panel. mechanic_diagnosis is neither checked nor shown, so an operator approving a Learn plan cannot see that it freezes a rule that changes Mechanic requests. The new diagnosis_requests record is not in the dashboard, the matrix API or the diagnostic API; only the recording export has it. DiagnosticPanel still labels the code-default proposed_kind as "Model proposed kind", which is the same misreading Rule 1 was built to prevent. Evidence: loop-evidence/planned-export-api.json: recording_has_diagnosis_requests true; matrix_mentions_diagnosis_requests false; the diagnostic endpoint mentions proposal_status false; frontend files mentioning diagnosis_requests or proposal_status: none. frontend/src/runPlans.ts checks the other four rule keys (lines around 266-270 and 309-320) but not mechanic_diagnosis. LoopLimits.tsx OfferedLoopLimits and LoopLimitFacts list only the other rules. DiagnosticPanel.tsx shows <Field name="Model proposed kind">{d.proposed_kind}</Field>. The builder disclosed DiagnosticPanel as a follow-up but not the missing plan and run-setup display. Fix: Add a mechanic_diagnosis check and display to runPlans.ts, OfferedLoopLimits and LoopLimitFacts. Plan the DiagnosticPanel follow-up to read diagnosis_requests, showing proposal_status and the proposed_kind source. At least state in the doc and in CURRENT_STATUS that the dashboard does not show the rule or its record.
- **F3 (LOW)** `backend/app/lab/diagnosis_protocol.py`: intervention_ran is set from bool(run.experiments). An experiment is recorded even when no fresh trial ran: an operator Stop before the first trial, a callback error, or a preflight rejection. The record then says intervention_ran true with 0 trials. Its statement reads "Intervention result: <id> INCONCLUSIVE" without saying why, so a reader can take a diagnosis that was stopped for a real one. Evidence: checks/test_r5_record_edge_cases.py::test_zero_fresh_trials_is_still_recorded_as_intervention_ran[stop|callback_error]: intervention_ran True, fresh_intervention_trials 0, trial_pairs 0, limitations ['STOPPED'] or ['CALLBACK_ERROR:RuntimeError'], and the statement does not mention them. The builder's own T6 asserts intervention_ran True with 0 runner calls in the PREFLIGHT_REJECTED case. Code: build_record, 'intervention_ran': bool(run.experiments) (line 215), and _statement (lines 173-175). Fix: Set intervention_ran from whether any fresh trial ran (fresh_intervention_trials > 0). If 'an experiment was recorded' is still needed, keep it as a separate field. Add the experiment's limitation (STOPPED, CALLBACK_ERROR, and so on) to the statement.
- **F4 (LOW)** `backend/app/lab/diagnosis_guide.py`: The builder removed the whole draft checks_note, not only the interpretive C6 sentence. Two sentences that do not depend on checks.py went with it: "Each episode's checks row gives the fixed checks by check_id and category; the checks field gives each check's public meaning." and "Explain each failed check from its own meaning." The spec says to drop "the interpretive checks_note sentence about C6", which is singular, while its list of what to include leaves checks_note out, so both readings are possible. The probe binds this exact block through its plan hash, so the choice affects what P1 and P3 measure. Evidence: guide-block-check.json: product_block_equals_draft_minus_checks_note true; dropped_checks_note_text is all three sentences; the draft adds 631 tokens and the product adds 569 (checks_note = 62). fixed_text_naming_a_check is empty. The builder's report and doc give the reason: the include-list does not name checks_note. Fix: Have the PM confirm the scope before the probe is declared. If the two neutral sentences should stay, add them back (they name no check). Then update GUIDE_TOKENS and the T3/T9 expectations and rebuild the probe plan.
- **F5 (LOW)** `scripts/experiments/diagnosis_probe.py`: Parts of the pre-registration are defined only in code and not in the declaration that gets hashed. (a) P4's "new message worse than today's" is computed as the total valid-within-600 count across both setups being strictly lower; the declaration does not say this. (b) The declaration template's decision_rule leaves out two of the memo's clauses: if P1 fails, trim the label text; if declines are unchanged, raise the gate question with the owner. scoring.json does include them. (c) P1 counts only answers that the checker flags AND a person confirms. Answers a person flags without a checker match are reported separately and not counted, so a GUIDE answer that blames citations in words checker v2 misses still counts toward a pass. Evidence: diagnosis_probe.py: declaration_template at lines 349-363; _p1 at lines 643-665 (confirmed = matched with a person's Y; person_only is descriptive); _p4 at line 728 ('rule1_worse_than_today_in_total' is a comparison of sums). probe-plan/DECLARATION.template.json decision_rule reads: "Rule 1 ships unless P4 shows the new message is worse than today's; Rule 2 ships only if P1 and P2 pass." Fix: Before hashing a declaration, write into it the definition of 'worse' for P4, the full decision rule, and how rows flagged by a person but not the checker are treated. The careful choice is to count them against GUIDE.
- **F6 (LOW)** `docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md`: The doc and the builder's report have small accuracy gaps. The section 5 list of outputs leaves out requests.json, which the harness writes. "Implements RECOMMENDATION.md section 7 exactly" overstates it (see F5). Section 6 says "All pass" for the new tests but never says that the one scripts/test.sh run exited 1 (backend: 2 failed, 3119 passed, 180 skipped); CURRENT_STATUS does say so. The builder's summary also leaves out the test.sh result. The claim that the 2 failures existed before this change could not be checked independently without copying audit/promotion.json. Evidence: builder/full-test-sh.log line 265: '2 failed, 3119 passed, 180 skipped'; line 336: 'FAILED backend'; full-test-sh.end: 'exit 1'. The docstring at diagnosis_probe.py:43 lists requests.json. review-product/preexisting-fireability-on-626bae4-export.log records the attempt that could not be completed. Fix: Add requests.json to the doc's output list. Change "exactly" to name the counting choices. State the test.sh result and the two failing test names in the doc's section 6 and in the builder's summary.
