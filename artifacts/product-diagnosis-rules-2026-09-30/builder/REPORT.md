_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

Diagnosis rules: builder report (September 30, 2026). Cost $0; everything ran offline.

SHORT VERSION
- Rule 1 (faultlab-mechanic-diagnosis/v1-repair-and-record) is built and tested. Every new Learn plan now includes it, for every agent, and run options offer it.
- Rule 2 (faultlab-diagnosis-guide/v1-kinds-and-checks) is built and tested but not offered. The switch DIAGNOSIS_GUIDE_OFFERED = False controls that. Per the PM, the interpretive C6 sentence is dropped.
- The probe harness is built. It was run only as a dry run and with a scripted fake provider, never live.
- Nothing was committed, reviewed or run live. There were no provider, model, W&B, Weave or network calls; the network guard counted 0 refused outbound connections.
- I never opened checks.py, the .env file, artifacts/heldout2/, audit/promotion.json or audit/final-audit*.json. Gate freeze ran with those two audit files left out, so they were never read.
- git: HEAD is still cbbf957 on branch main, there is no stash, and the index was not touched. The only changes to the working tree are the files listed.

1. FILE-BY-FILE CHANGES

backend/app/lab/diagnosis_protocol.py (NEW; Rule 1)
- Constants: MECHANIC_DIAGNOSIS_V1, the plan key mechanic_diagnosis, RECORD_KIND diagnosis_requests, the statuses VALID_REQUESTED / VALID_NO_REQUEST / INVALID_OUTPUT, the kind sources model / code_default, REPAIR_SENTENCE (the memo's exact sentence), REPAIR_INSTRUCTION (today's instruction plus a space plus that sentence), and RULE.
- Functions:
  - declaration(), semantics_hash(), campaign_rule().
  - repair_errors(error): today's {location, type}; a string_too_long error also gets max_characters (from pydantic's own limit) and your_characters (the field's length).
  - repair_message(errors).
  - RecordingDiagnosisMechanic: the outermost wrapper. It keeps the Diagnostician's own options (id, change string, observed treatment trials), the returned ref, proposal and raw answers, and the real Mechanic's last_diagnosis.
  - build_record() / record(): writes an immutable diagnosis_requests/<diagnostic_id> record.
  - campaign_records(): used by the export; embeds every attempt's mechanic_outputs record by its id.
- What the record holds:
  - protocol, campaign_id, counterexample_id, diagnostic_id, target_invariant, request_id;
  - first_turn_hash (the sha256 of the first-turn messages, since the product does not store the sent request);
  - attempts (each with output_ref and validation_errors), output_refs;
  - proposal_status, recorded_proposed_kind and recorded_proposed_kind_source;
  - last_raw_unvalidated (validated: false);
  - options, requested_intervention_id, requested_change, intervention_ran, interventions, fresh_intervention_trials, verdict;
  - one plain-English statement.
- The record fails loudly instead of saving something false: if the wrapper's state does not describe this diagnosis, it raises and writes nothing.

backend/app/lab/diagnosis_guide.py (NEW; Rule 2)
- DIAGNOSIS_GUIDE_OFFERED = False is the one switch someone reviews and flips later.
- The block contains: protocol, meaning, task (the campaign's own task text), kinds (the minimal design's wording), checks (PUBLIC_INVARIANTS word for word; the plan freezes its content hash), contract_note, use and hypothesis_length.
- No checks_note. I dropped the whole draft checks_note, not just its C6 sentence: the spec's include-list does not name it, and the PM decision reads "Drop the interpretive C6 sentence (checks_note)". No fixed sentence of the block names a check.
- Also provides declaration(), campaign_rule(), block(), attach() and DiagnosisGuideMechanic.

backend/app/agents/mechanic.py (the only shared file touched; changes are behind the switch)
- Added the constant FORMAT_REPAIR_INSTRUCTION (text identical to today's).
- Added self.diagnosis_protocol = None and self.last_diagnosis = None.
- Only when the switch is set and the prompt is diagnosis.md:
  - last_diagnosis keeps request_id, first_turn_hash, output_refs and per-attempt validation_errors;
  - errors come from diagnosis_protocol.repair_errors;
  - the repair turn uses diagnosis_protocol.repair_message.
- The original flag-off lines are kept word for word, including the literal repair line. A test checks that line against 626bae4, and an older Phase 28a test pins it too.

backend/app/lab/learning.py (a few lines; the gate line is untouched)
- Imports both modules.
- Next to the citation-status rule: diagnosis_rule = diagnosis_protocol.campaign_rule(...); mechanic.diagnosis_protocol = diagnosis_rule; guide_rule = diagnosis_guide.campaign_rule(...).
- Wrapper order after the citation wrapper: the guide (with current.task_text) sits outside citation status, which sits outside the size rule; the recorder is outermost.
- diagnosis_protocol.record(...) is called right after Diagnostician.run returns, before evidence_for and before the unchanged line "if diagnostic.kind!='POLICY_GAP': continue".

backend/app/lab/run_plans.py
- New plan models:
  - MechanicDiagnosisPlan: exact-text validators; first_turn_changed, model_text_edited, reads_scoring and verdict_code_changed must be False; record_written_before_gate must be True; semantics_hash must match.
  - DiagnosisGuidePlan: exact fixed text; checks is C1..C8 with checks_hash = content_hash(checks); reads_episodes, reads_scoring, compacted, system_prompt_changed, verdict_code_changed and interprets_checks must be False.
- Both are optional fields on SavedRunPlan and are added to the "omit if absent" list.
- build_run_options lists learn.mechanic_diagnosis; diagnosis_guide appears only if DIAGNOSIS_GUIDE_OFFERED.
- prepare_run_plan freezes mechanic_diagnosis into every Learn plan; the guide only if offered.
- _bindings refuses either rule outside Learn.
- validate_run_plan (Start) refuses a declared rule that is not exactly the installed one. For the guide that includes the frozen C1-C8 text and its hash.

backend/app/lab/exports.py
- Only for a plan that declares mechanic_diagnosis: a top-level diagnosis_requests list that embeds every attempt by id, including a rejected first attempt such as v2f's.

scripts/experiments/diagnosis_probe.py (NEW; section 7): see part 3.

Tests (NEW)
- backend/tests/lab/test_diagnosis_rules.py: 60 tests.
- backend/tests/lab/test_diagnosis_rules_loop.py: 3 tests.
- backend/tests/experiments/test_diagnosis_probe.py: 20 tests.

Tests edited
- backend/tests/lab/test_evidence_wait.py (its harness is also used by test_evidence_retry_v3.py) and test_discovery_v4_review_fixes.py.
- Each harness now switches Rule 1 off in one commented monkeypatch.
- Why: their Diagnostician is a stand-in that never calls the Mechanic, so there are no attempts to record. With the rule on, the record correctly refused to write anything false, and the campaign ended ERROR. That caused 14 failures before the change.

Docs
- NEW docs/PRODUCT_DIAGNOSIS_RULES_2026-09-30.md.
- CURRENT_STATUS.md: new header entry and a new first "Current work" paragraph, marked "not yet committed, not reviewed, not run live; the probe has not been run".
- The previous build's paragraph was stale ("not yet committed, not run live"). It now says it was committed as 661e2d0 and run live once (v2g).

2. TESTS (memo T1-T9, adapted so Rule 2 is not offered)
- T1 (plans):
  - New Learn plans for reference, smolagents and smolagents-v2 carry Rule 1 and not Rule 2. Run options offer Rule 1 only. Baseline plans carry neither.
  - Altered text fails the exact validators (13 changes tried for Rule 1, 12 for Rule 2).
  - Non-Learn plans are refused.
  - Start refuses a different installed Rule 1, and a guide whose frozen C1-C8 text or hash differs, including after PUBLIC_INVARIANTS is edited.
  - A synthetic plan that declares the exact guide starts, and the loop applies it.
  - A plan saved before the rules keeps its bytes and starts.
  - All native-v2b saved plans re-read with the same plan_hash and no new key (store copy).
  - Flipping the switch is the only way the guide gets offered.
- T2: the real Mechanic, fed each saved context and the saved answers, sends exactly the bytes of inv-a's saved requests: first turns 8,990 / 9,088 / 9,639 / 9,794 / 9,352 tokens, repair turns 10,030 / 10,153. With the rule on, the first turn is identical. The mechanic_outputs records have the same fields and values either way.
- T3:
  - Exactly one key is added and every other key stays byte-identical.
  - Every first turn grows by +569 tokens, not the memo's +631, because the dropped checks_note was 62 tokens.
  - The citation block and the V2 memory pointer are unchanged.
  - Wrapper order is checked inside the real loop.
  - A synthetic request just under 32,000 tokens without the guide goes over the limit with it; the size rule compacts it to 28,000 or fewer and keeps the guide byte for byte.
- T4:
  - v2g's 614-character answer and v2f's 743-character answer get max_characters 600, your_characters 614 / 743, and the appended sentence (+47 tokens).
  - With the switch off, the repair turn is today's exact bytes.
  - A 601-character hypothesis fails in both modes and is stored word for word; a 600-character one passes.
  - Other errors keep today's form; candidate requests are unchanged.
- T5:
  - Valid request gives VALID_REQUESTED.
  - Null gives VALID_NO_REQUEST and INCONCLUSIVE.
  - Invalid twice gives INVALID_OUTPUT, code_default, with both ids in order.
  - Invalid then valid gives VALID_REQUESTED with both attempts.
  - Option change strings equal the request's (for example remove_primitive:0).
  - The DiagnosticResult is identical to the switch-off run.
  - The record is immutable, and an inconsistent state writes no record.
- T6 (the full 24-cell matrix):
  - {reproduction valid, invalid} × {null, valid request, invalid output} × {SUPPORTED, INCONCLUSIVE, CONTRADICTED, PREFLIGHT_REJECTED}.
  - Kinds, intervention records, ledger reservation and charge sequences, and trials are identical with the switch off and on.
  - Pinned sha256 values are unchanged for referee/diagnostics.py, reducer.py, lab/diagnosis.py, prompts/diagnosis.md, contracts/models.py and citation_status.py. PROTOCOL_HASH is still bfefe69b….
  - The gate line appears once, and the record call comes before it.
- T7: with the rule, every attempt appears in the export by id, including v2f's first attempt. Without it, the export has exactly today's keys and the rule's code never runs. Store copy: all 6 recordings are byte-identical under the old exports.py (from git show 626bae4) and the new one.
- T8: the offline_fixture scripted Learn campaign (real localhost simulator), run without and with Rule 1, gives the same state, episode counts, scripted calls, record counts and ledger calls, plus exactly one diagnosis_requests record (VALID_REQUESTED, model, intervention ran, POLICY_GAP).
- T9: the minimal design's prototype still reproduces its saved block and declaration hashes and +631 tokens on all 5 requests; the product's block is exactly that minus checks_note. The integrity prototype's saved statuses, kind sources and repair messages equal what the product now records and sends.
- Negative controls (builder/mutation-checks.log; scratch copy, deleted afterwards): 14 of 14 mutations were caught, and the unmutated copy passed 83 of 83.
- Saved-store check (builder/saved-store-check.json; original store opened read-only, sha256 8aa9aa27… before and after, copy deleted):
  - 6/6 plans read and re-serialize byte for byte.
  - 6/6 exports are identical under the old and new exports.py.
  - The 5 diagnosis requests, rebuilt from the store with inv-a's own code and run through the real Mechanic with the rule off, equal inv-a's saved requests turn for turn.
  - With the rule on, the records say v2d VALID_REQUESTED; v2e VALID_NO_REQUEST; v2f VALID_REQUESTED (attempt 0 rejected at 743); v2g dev-5 INVALID_OUTPUT / code_default; v2g dev-6 VALID_REQUESTED. That is exactly what the memo predicted.
- Gate freeze: 124 values compared, 8 changed. All 8 are either mechanic.py (the file, or its Mechanic class) or the source/runtime fingerprints.

3. PROBE HARNESS (not run live)
- Inputs:
  - The 5 inv-a requests, copied to artifacts/product-diagnosis-rules-2026-09-30/probe-inputs/ with SHA256SUMS: v2d 7cb9ac8c…, v2e 905228fb…, v2f 4ab16a7e…, v2g-dev5 098c2cda…, v2g-dev6 d76f2e4a….
  - Each run's saved export, for its task text.
  - The v2g saved plan and configuration (campaign d8d1e8cc…, plan 60899c53…), which give the model deepseek-ai/DeepSeek-V4-Pro-0813, the frozen request settings (temperature 0, 2,000 output tokens, 20 s, json_object, thinking disabled) and the per-call bound of $0.04984. The harness checks that the installed product's settings equal these.
  - The misreading checker v2, pinned at sha 11920882….
- Every call goes through RuntimeProvider and a CampaignLedger saved in the output folder. The call is admitted and charged before it is sent, with the 140 calls reserved up front. The product's one blind retry is charged only from the rest of the cap. The hard cap is $8.
- --execute-live refuses unless the declaration's sha256 matches, and the declaration names the harness sha, the plan hash, the model, a cap of $8 or less, an approver, P1-P4 and the decision rule, confirmed preconditions, and exactly the --out folder (which must be new or empty).
- Outputs are written only under --out: plan.json, requests.json, answers.jsonl (answers stored word for word), probe-ledger.sqlite3, manifest.json, scoring.json, review-blinded.csv (no arm column) and review-key.json.
- Scoring:
  - P1: a checker-v2 match that a person confirms with Y in the review file.
  - P2: counts of valid answers and of over-600 answers.
  - P3: counts plus one-sided Fisher tests, with columns for a person to score against the rubric.
  - P4: repair answers that are valid and 600 characters or shorter.

DRY-RUN OUTPUT (builder/probe-dry-run.txt; 0 refused connections)
- Plan hash 9d5d3bd6f4351b4dcaa2840e1546b323d20bc3f0b93ffe1305d942a5f6466cc5; harness sha256 fb73a584466bb543e2684a1739fadccd5208e3d4a6696da231833704a46fe2c3.
- Calls: 100 first-turn + 40 repair = 140; 10 per request key, across 14 keys.

| Request | CONTROL | GUIDE | REPAIR_TODAY | REPAIR_RULE1 |
|---|---|---|---|---|
| v2d-dev5 | 8,990 | 9,559 | – | – |
| v2e-dev5 | 9,088 | 9,657 | – | – |
| v2f-dev5 | 9,639 | 10,208 | 10,030 | 10,077 |
| v2g-dev5 | 9,794 | 10,363 | 10,153 | 10,200 |
| v2g-dev6 | 9,352 | 9,921 | – | – |

- Maximum charge: 140 × $0.04984 = $6.9776 (hard cap $8.00).
- Tighter bound (these inputs, with 2,000 output tokens per call): $2.9039.
- Network calls: 0.
- Tested offline with a scripted provider:
  - A live run charged 140 calls = $6.9776 and wrote only under --out.
  - When every call fails, 20 retries fit and the charge is 160 × $0.04984 = $7.9744, which is $8 or less.
  - The run is refused without a declaration and on any mismatch (no provider is ever built); caps above $8 or below the planned calls are refused.

4. IDENTITIES (builder/identity-before.json, identity-after.json, identity-compare.txt)
- Runtime: 49958e716f0b08aacb9db5d6ddf99620451f949a901aa35cca979918c1df6b6e → e3551ead0715fbbb65e24d1756f181b93acf237c9bdbe7849d266a1dc023a5a9.
- Algorithm: 7a56afed… → e4c47b4e….
- Reference Actor source hash: 7f78de28… → eaffac74…, because mechanic.py is in the agents tree. The example native configuration hashes changed with it. Register every agent again before any live run.
- New values: Rule 1 declaration 729441f0…, semantics 577b0c80…; Rule 2 declaration 36ca790f… (offered False); PUBLIC_INVARIANTS hash e792e8f0….
- Unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, native v2.1 prompt fff397c9, native v1 and v2 adapter and prompt hashes, and PROTOCOL_HASH. 30 of 41 identity values are unchanged.

5. DECISIONS AND LIMITS THE PM SHOULD KNOW
- (a) Temperature. The frozen sampling setting from the saved plan is temperature 0. Ten repeats of the same request may come back nearly identical. If they do, each request-and-arm cell is effectively one sample, and the 4-of-40 and 5-of-40 bars would say much less than they appear to. The harness uses the frozen settings as the spec asks; please decide this before declaring the probe.
- (b) Start accepts a plan that declares the exact Rule 2 even while it is not offered, so that such a plan can be handled and tested. The only way to create one is a code change or flipping the switch.
- (c) The Rule 1 record fails loudly (the campaign ends ERROR) instead of saving a false record. In the product this cannot happen, because the Diagnostician always calls the Mechanic.
- (d) A source whose diagnosis request the size rule refuses gets no diagnosis and no record. Its size-rule record (mechanic_context_records) already says why.
- (e) Not changed:
  - the dashboard (DiagnosticPanel still shows the code-default proposed_kind; the frontend plan check accepts the new key);
  - the experiments API;
  - the diagnostics.py:72 defect.
  All three are follow-ups.
- (f) Compare plans were not created in the tests, because that needs an accepted policy. They go through the same non-Learn path as baseline plans, which is tested.
- (g) Someone allowed to open checks.py should confirm that the C1-C8 public meanings match it before Rule 2 is offered.

6. EVIDENCE: artifacts/product-diagnosis-rules-2026-09-30/
- builder/: full-test-sh.log/.start/.end, probe-dry-run.txt, identity files, gate_freeze/, saved_store_check.py + .json, mutation_checks.py + .log, the pre-existing-failure log, protected-file and saved-store sha256 files, git status diff.
- probe-inputs/ and probe-plan/.
- The scratch trees under /Users/shree/FaultLab_Scratch/ were deleted. The inv-a folder there was already present before this stage.
- backend/.pytest_cache (git-ignored) was created or updated by pytest during test.sh.
