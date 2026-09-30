_Saved by the PM from the agents' returned text; content unedited._

# Diagnosis step: state the length limit on retry, record why no intervention ran, test a definitions block before it ships, and do not auto-run the intervention

The dev-5 split (2 POLICY_GAP, 2 INCONCLUSIVE) came from one declined request (v2e) and one 14-character length overrun (v2g), not from any difference in what the Mechanic was shown. Recommendation: ship a plan-gated repair message that states the 600-character limit, plus a record of why no intervention ran. Test a fixed definitions block with a request-only probe of about $3 before shipping it. Do not let fixed code run the intervention for the Mechanic.

RECOMMENDATION MEMO: WHY NATIVE-V2 DIAGNOSIS SPLITS, AND WHAT TO CHANGE
Date: 2026-09-30. Everything behind this memo was read-only and cost $0. No model, provider, W&B, Weave or network calls were made. checks.py was not opened.
Evidence folders, all under faultlab/artifacts/analysis-diagnosis-2026-09-30/:
- inv-a/ (rebuilt requests)
- investigation-b-protocol/ (protocol reading)
- inv-c/ (all 30 live diagnoses)
- designer-integrity/, designer-effectiveness/, design-minimal/ (design prototypes)

====================================================================
0. THE DECISION IN SHORT
====================================================================
1. Approve now ($0 to build and test). Build one new plan rule, protocol faultlab-mechanic-diagnosis/v1-repair-and-record, frozen into new Learn plans only. It has two parts:
   (a) When the Mechanic's hypothesis is too long, the repair message states the limit and how long the answer was, for example "max 600, yours 614".
   (b) A new record after every diagnosis that says plainly whether the Mechanic requested an intervention, declined, or gave no valid answer, and lists every attempt by id.
   No verdict code and no gate changes.
2. Approve a small paid probe (about 140 Mechanic-only calls, capped at $8, likely $2-3). It tests a second rule, faultlab-diagnosis-guide/v1-kinds-and-checks: a fixed block giving the Mechanic the kind definitions, the public meaning of C1-C8 and the task text. The probe also measures part (a). Ship the block only if it meets the pre-registered bar in section 7.
3. Reject for now the "fixed default" design, where fixed code runs the intervention when the Mechanic names none. It would lift dev-5 to about 4 of 4 POLICY_GAP, but only by making the diagnosis gate easier. Section 4 gives the reasons.
4. Correct the run doc now. It misstates what happened in v2g (section 1.5).

====================================================================
1. WHAT THE INVESTIGATIONS ESTABLISHED
====================================================================
1.1 The split is not explained by what the Mechanic saw.
- Investigation A rebuilt all five diagnosis requests offline with the product's own code (dev-5 in v2d, v2e, v2f and v2g, plus v2g dev-6).
  - Rebuilt token counts are exactly 136 higher than the provider's input_tokens on all five first turns, and exactly 167 higher on both repair turns. Constant offsets mean the content lengths agree.
  - The request-building files are byte-identical at the backup commits for each run (814a6e3, 884de24, 47b8f69, 661e2d0) and today.
- Across the four dev-5 requests, after normalising ids, these fields are identical:
  - the system prompt (sha 5488c7f5)
  - the output schema
  - the control fault spec
  - the single offered intervention, remove_primitive:0
  - observed control 3 valid / 3 violations and observed treatment 3 valid / 0 violations
  - every runtime_contract field except the memory text
- The fixed text also pairs up across outcomes:
  - v2d (POLICY_GAP) and v2e (INCONCLUSIVE) received the same fixed text.
  - v2f (POLICY_GAP) and v2g (INCONCLUSIVE) received the same fixed text.
  - Request size does not separate outcomes either: 8,484 / 8,582 / 9,133 / 9,288 content tokens.
- Evidence: inv-a/comparison.json and inv-a/*-diagnosis-request.json.

1.2 The two losses had two different causes.
- v2e was a model choice.
  - The Mechanic (mechanic-ed993d65639949d7a6faf49021b31620) proposed CONTRACT_EVIDENCE_GAP and requested null.
  - Its own text says the intervention "eliminates the target violation, but ... do[es] not establish whether the report's evidence citations were valid".
  - It declined because it held a citation theory the one offered experiment could not test. The prompt tells it to do that: "nondiscriminating experiments warrant INCONCLUSIVE" (prompts/diagnosis.md:1).
- v2g was a formatting failure, not a decline.
  - Both answers (mechanic-ec2f80bf4d9b4543adf0b5ac3473f69c and mechanic-5bb12477f42d43afb96d991b3e865001) requested the right intervention, intervention-828103e0598f48f8675994a5.
  - Both had a 614-character hypothesis against a 600-character limit (contracts/models.py:24), so both failed with string_too_long.
  - The repair answer was byte-identical to the first.
  - The repair message (agents/mechanic.py:72-73) does not state the limit. It says "Correct formatting only ... Do not add authority, a new hypothesis, or a replacement canned solution." I confirmed that text in the file.
  - With no valid answer, diagnosis.py:134-135 ran nothing, and diagnosis.py:149 wrote proposed_kind='INCONCLUSIVE' as a code default.
- Corrected tally for dev-5:
  - The Mechanic requested the intervention in 3 of 4 raw answers (v2d, v2f, v2g) and proposed CONTRACT_EVIDENCE_GAP in 4 of 4.
  - The product accepted 2 of 4.
- v2f nearly failed the same way. Its first answer (mechanic-36a16b375d5240b1983dbece2944f1eb) was 743 characters, and the repair shortened it to 428 (mechanic-cf9b2b6da60d4f609cb2a2c9c3a7c063).
- Overall, 3 of 7 raw native-v2 diagnosis answers were over the limit. The V4-Pro Mechanic overran on its first try in 4 of 16 diagnoses (inv-c).

1.3 How fixed code actually decides (checked against the code).
- classify_policy_gap (referee/diagnostics.py:76-81) returns only POLICY_GAP or INCONCLUSIVE.
  - POLICY_GAP needs a valid 3/3 reproduction, plus one requested intervention that is SUPPORTED on fresh trials (control 3/3, treatment 0/3), with nothing CONTRADICTED.
- CONTRACT_EVIDENCE_GAP can never be the verdict in the Learn loop. Only validate_gap (diagnostics.py:84-102) returns it, and only tests call it.
- The Mechanic's proposed_kind, hypothesis and cited evidence have no effect on the verdict (diagnostics.py:81 only stores proposed_kind).
- The candidate gate is `if diagnostic.kind!='POLICY_GAP': continue` (learning.py:250).
- So the Mechanic affects the verdict in only two ways: whether it returns a valid answer within two tries, and whether that answer names an offered option. Its reasoning does not count.
- For dev-5 the reducer left exactly one option. Reduction had already observed it at control 3/3 and treatment 0/3, so the diagnosis experiment largely repeats reduction.

1.4 Why the Mechanic keeps telling a citation story.
- The request never defines the three kinds; the prompt only lists them (diagnosis.md:1), and the schema has no descriptions.
- It never says what C1-C8 mean. PUBLIC_INVARIANTS (agents/explorer.py:21-30) goes only to the Explorer (explorer.py:284).
- It never gives the task text: "express" occurs 0 times in all five requests.
- It never says why C5 failed. Check rows carry only id, category word and passed flag (models.py:433-438).
- The only agent-specific text is about evidence labels and citations, roughly 760-1,100 tokens:
  - V2_MEMORY (diagnosis.py:19-27)
  - the adapter's label protocol (external_agent_v2.py:89-108)
  - from v2f on, the citation-status block
- The Mechanic's wording echoes those passages: "never shown", "cannot be decoded", "shown-order label contract", "unshown first write attempt".
- The request also contains counter-evidence that the Mechanic did not use:
  - C6 (delivered_cited_evidence) passed in every dev-5 episode.
  - The report_submitted events show every dev-5 citation decoded to a delivered observation (inv-a/report-submitted-citation-facts.json).
  - Only the dev-6 episodes had a genuinely unlabelled row (o3).
- The label is driven by the Mechanic model, not by native agents (inv-c):
  - The V4-Pro Mechanic proposed CONTRACT_EVIDENCE_GAP in 15 of 16 diagnoses (5 of 5 for the reference agent too). The V3.1 Mechanic did so in 3 of 14. That comparison is post hoc (Fisher p=0.00009) and confounded by other changes made at the same time.
  - The citation content of the hypotheses is specific to native v2: 5 of 6 there, against 1 of 24 elsewhere, by one analyst's manual reading.

1.5 Record errors found (fix these regardless of design).
- docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md:393 says the v2g Mechanic "itself proposed INCONCLUSIVE and requested no intervention". That is wrong:
  - It proposed CONTRACT_EVIDENCE_GAP and requested intervention-828103e0598f48f8675994a5, twice.
  - Both answers failed the length check at 614 of 600 characters.
  - The recorded INCONCLUSIVE is a code default (diagnosis.py:149).
- Lines 415-419 of the same doc say CONTRACT_EVIDENCE_GAP "(or INCONCLUSIVE)" and "requested 2 of 4". They should say CONTRACT_EVIDENCE_GAP 4 of 4, requested 3 of 4, accepted 2 of 4.
- The task brief says every POLICY_GAP candidate passed source validation. The v2g dev-6 candidate was SOURCE_FLAKY (doc line 394, which I read). Across native v2, 3 of 4 candidates passed.
- Investigation A said the exports leave out v2e's answer and v2g's rejected answers. That is wrong. I checked:
  - native-v2e-run/export.json contains v2e's hypothesis text.
  - native-v2g-run/export.json contains the "unshown first write attempt" text twice.
  - Both appear without their record ids and with no link to the diagnostic.
  - What exports do drop is v2f's first attempt, mechanic-36a16b375d5240b1983dbece2944f1eb. exports.py:60-61 omits an unreferenced output when its request_id matches a referenced one.
- The diagnostic record cannot tell "declined" from "invalid output" from "code default". That gap is what produced the wrong doc line.
- A small defect: InterventionExperiment.change stores the prediction ('removes_violation') instead of the change string (diagnostics.py:72).

1.6 What remains unknown.
- Whether telling the Mechanic the kind definitions, check meanings and task text changes its choices. v2g's own answer already said "C6 passes" and still blamed citations. Only paid calls can answer this.
- Whether stating the limit in the repair turn makes V4-Pro shorten. v2f shortened without it once; v2g resent identical text once. n=1 each.
- Why v2e declined when v2d, on the same fixed text, requested. It is one sample per run, and sampling settings were not examined.
- Byte-identity with what was sent cannot be proven, because the product never stores the sent Mechanic request. The evidence is the constant token offsets plus unchanged source files.
- Whether the public meaning of C6 matches what checks.py implements. checks.py was not opened. Someone authorised should confirm this before any text that relies on it is frozen.
- Whether today's diagnosis could ever catch a real evidence-gap source. It cannot distinguish one: every option only weakens or removes the fault, and validate_gap is not wired into the loop.
- Housekeeping: investigation C saw two empty git objects appear at 09:42:17, one in a clone it never touched. It ran only read-only git commands. The cause is unexplained; another concurrent process is the likely source.

====================================================================
2. RECOMMENDED DESIGN
====================================================================
Two separately declared rules. This combines the strongest parts of the integrity-first and minimal designs. It leaves out the fixed-default design (section 4).

RULE 1: faultlab-mechanic-diagnosis/v1-repair-and-record (plan key mechanic_diagnosis). Ship once the offline tests pass.

Part 1a: the repair turn states the limit.
- In agents/mechanic.py add self.diagnosis_protocol=None, following the lab_retry pattern (mechanic.py:17-19). learning.py sets it from the plan.
- Only when it is set and prompt=='diagnosis.md':
  - each string_too_long error in the repair message also carries max_characters (from pydantic's ctx) and your_characters. For v2g the repair would have said: [{location:[hypothesis], type:string_too_long, max_characters:600, your_characters:614}].
  - today's instruction sentence is kept exactly, and this sentence is appended: "A string_too_long error gives max_characters and your_characters: rewrite that same field in at most max_characters characters, keeping its meaning and adding no new claim."
- The model's text is never truncated or edited. The 600 limit is unchanged.
- Cost: +47 tokens on a repair turn only.

Part 1b: a record of why an intervention did or did not run.
- mechanic.py (same gate) keeps last_diagnosis: {request_id, output_refs in attempt order, per-attempt validation_errors, first_turn_hash}.
- A thin outermost wrapper captures the options it passed through.
- learning.py writes an immutable diagnosis_requests/<diagnostic_id> record right after Diagnostician.run returns and before the gate at learning.py:250, so INCONCLUSIVE diagnoses get one too. Fields:
  - protocol, campaign_id, counterexample_id, diagnostic_id, request_id
  - output_refs and validation_errors per attempt
  - proposal_status: VALID_REQUESTED, VALID_NO_REQUEST or INVALID_OUTPUT
  - recorded_proposed_kind_source: model or code_default
  - last_raw_unvalidated (the parsed proposed_kind and requested id, marked unvalidated)
  - options: [{intervention_id, change, observed_treatment_trials}]. This also works around the diagnostics.py:72 defect without editing that file.
  - requested_intervention_id, intervention_ran
- exports.py: only for plans that declare the rule, add a top-level diagnosis_requests list that embeds every attempt by id, including same-request attempts such as v2f's first one.
- Replayed on the five saved diagnoses, the record would have said:
  - v2d: VALID_REQUESTED
  - v2e: VALID_NO_REQUEST
  - v2f: VALID_REQUESTED, with attempt 0 rejected at 743 characters
  - v2g dev-5: INVALID_OUTPUT, code_default
  - v2g dev-6: VALID_REQUESTED
  The wrong doc line could not have been written.

RULE 2: faultlab-diagnosis-guide/v1-kinds-and-checks (plan key diagnosis_guide). Ship only if the probe in section 7 passes.
- A new module, backend/app/lab/diagnosis_guide.py. The full draft is at design-minimal/proposed_diagnosis_guide.py.
- A DiagnosisGuideMechanic wrapper adds one key, diagnosis_guide, to the diagnosis request. It is applied after learning.py:244, outermost, so the size rule counts it, in the same pattern as CitationStatusMechanic.
- The block is fixed text plus the campaign's own task_text, and reads nothing else:
  - task: e.g. "Upgrade the authorized order to express shipping, then record one truthful confirmation."
  - kinds, restating docs/demo-guide.md:471-473 and the evidence_gap_v1 witness:
    - POLICY_GAP: the delivered observations were enough; a different recovery policy could plausibly prevent the violation.
    - CONTRACT_EVIDENCE_GAP: through every declared public tool and status path, the terminal evidence could not be delivered within the episode limits. "Contract here means the public service API ... not the report schema or the adapter's evidence labels."
    - INCONCLUSIVE: the observations and offered interventions cannot distinguish the explanations.
  - checks: PUBLIC_INVARIANTS C1-C8, verbatim from explorer.py:21-30, with a content hash frozen in the plan.
  - checks_note: C6 is the citation check; where C6 passed, that report's citations met it; explain each failed check from its own meaning.
  - contract_note: runtime_contract describes how things work and is not a list of pass/fail rules.
  - use: fixed code runs only the requested intervention as three fresh pairs; null, or output still invalid after one repair, means no experiment and INCONCLUSIVE.
  - hypothesis_length: at most 600 characters, about 90 words; shortening is the correction for string_too_long.
- It contains no dev-5 or other worked example.
- It deliberately leaves out the integrity-first design's sentences "Requesting an intervention is not a claim that it will be SUPPORTED" and "proposed_kind ... not scored". Both push the model toward requesting for reasons other than understanding the failure, and leaving them out keeps any measured change attributable to the definitions.
- Cost: +631 tokens per first turn (measured). The largest request becomes 10,784 tokens against a 28,000 compaction target and a 32,000 limit, about +$0.0008 per call.

Common to both rules:
- Each rule is frozen only into new Learn plans. It is absent (not null) from all earlier plans and all baseline and compare plans, so their bytes and plan_hash are unchanged.
- _bindings refuses either rule outside Learn.
- Start refuses a plan whose frozen text or hash differs from the installed constants, as mechanic_evidence does at run_plans.py:996.
- Scope is every agent. If the owner prefers to keep the reference-agent path frozen, it becomes a one-line smolagents-v2 gate, as citation_status.AGENTS does.

Explicitly unchanged:
- referee/diagnostics.py, so checker_hash and PROTOCOL_HASH are unchanged
- referee/checks.py and C1-C8
- referee/reducer.py
- lab/diagnosis.py: options, context, V2_MEMORY, the hard-coded prediction, the null path and the code default
- prompts/diagnosis.md
- contracts/models.py: the 600-character Text, DiagnosticProposal, DiagnosticResult
- lab/citation_status.py
- the learning.py:250 gate
- reproduction, reduction, assess_pairs, source validation, challenge and promotion

INTEGRITY ARGUMENT
- The verdict still comes only from classify_policy_gap, fed by fresh trials, and that file is not edited. Nothing about SUPPORTED (fresh 3/3 vs 0/3, every trial valid) or POLICY_GAP (a valid 3/3 reproduction) changes.
- No gate becomes easier:
  - the 600 limit stays
  - no text is truncated
  - null and invalid output still mean no intervention and INCONCLUSIVE
  - no default run is added
  - no new option kinds and no retains_violation route are added
  - proposed_kind stays without authority
- No new information about any episode reaches the model:
  - the task text is already bound to the plan (runner.py:87) and already sent to the agent (external_agent.py:315)
  - the C1-C8 meanings are public text already sent to the Explorer
  - nothing comes from checks.py
  - candidate requests get neither block, and the diagnostic record passed to candidates has no hypothesis (learning.py:259)
- The record becomes more truthful: a code default can no longer pass for a model proposal, and every attempt is kept with its id.
- Both independent judges scored the parts used here 8 to 8.5 out of 10 on integrity, with no blocking concerns.
- Honest limit: this design does not fix the existing weakness that the diagnosis experiment mostly repeats reduction and is never checked against the stated hypothesis (experiment-protocol.md:90-91). As the Mechanic follows the fixed rule more faithfully, that weakness becomes easier to see. Tightening it is a separate, gate-changing decision.

EXPECTED EFFECT
- Certain (Rule 1b): every new diagnosis says in plain terms requested, declined or invalid, where proposed_kind came from, and which attempts exist. Exports stop dropping same-request attempts.
- Likely but unmeasured (Rule 1a): fewer v2g-type losses. v2f shows the model can shorten when repairing, and v2g resent identical text under a message that never named the limit. This affects roughly 1 in 16 V4-Pro diagnoses historically, but it was 1 of the 2 dev-5 losses.
- Uncertain (Rule 2): it may reduce v2e-type declines built on a citation theory, and should make stored hypotheses stop blaming citations that C6 already passed. The prompt already told the Mechanic to request the zero-violation option (diagnosis.md:5), and v2g still blamed citations after writing "C6 passes", so information alone may not be enough. Hence the probe.
- Best case on dev-5: POLICY_GAP goes from 2 of 4 to 4 of 4, and every additional POLICY_GAP is still decided by fresh trials. A realistic expectation without the probe: about 3 of 4.
- The Mechanic keeps its veto. If the probe shows declines do not move, the remaining lever is a gate-level decision for the owner (section 4).
- Not success measures: the POLICY_GAP rate, which rises mechanically when more answers are valid requests and is not better diagnosis, and proposed_kind, whose meaning shifts under Rule 2.

RISKS
- The null-means-INCONCLUSIVE sentence in Rule 2 may still nudge the model toward requesting. It is kept because it is literally true and milder than the alternatives.
- The kind definitions and the "contract means the public API" sentence were written after seeing the failure. The POLICY_GAP definition could tilt labels, which is why labels are not a success measure.
- About 631 extra tokens could lengthen hypotheses. The probe checks the first-attempt over-length rate as a guard.
- agents/mechanic.py is shared by every plan. A bug in the gated branch could change requests for old plans. A golden byte-identity test with the flag off is a hard precondition (T2).
- Freezing the C1-C8 hash means any later edit to PUBLIC_INVARIANTS blocks Start for plans carrying Rule 2 until a v2 of the rule is declared. This is intended, but it may surprise someone.
- The C6 sentence rests on the public meaning of C6. Confirm it against checks.py (by someone allowed to open it) before freezing.
- DiagnosticPanel.tsx:9 will keep showing the code-default proposed_kind until it reads the new record. That is a follow-up.
- Tests that pin run-option or plan keys (test_run_plans.py, test_loop_limits_plans.py) need their expectations updated.

====================================================================
3. FILES TO CHANGE
====================================================================
- NEW backend/app/lab/diagnosis_protocol.py (Rule 1):
  - PROTOCOL, REPAIR_SENTENCE and RULE constants
  - declaration(), campaign_rule(store, campaign), semantics_hash()
  - RecordingDiagnosisMechanic (outermost wrapper; captures options and the returned ref, proposal and raws)
  - record(store, campaign, counter, diagnostic, run, wrapper)
- NEW backend/app/lab/diagnosis_guide.py (Rule 2), per design-minimal/proposed_diagnosis_guide.py: declaration(), campaign_rule(), block(task_text), attach(), DiagnosisGuideMechanic.
- backend/app/agents/mechanic.py: Part 1a and last_diagnosis only, behind self.diagnosis_protocol.
- backend/app/lab/learning.py, about 6 lines:
  - read both rules next to :164 and set mechanic.diagnosis_protocol
  - after :244, wrap in this order: guide outside citation status, which sits outside the size rule; the recorder outermost
  - call record() after Diagnostician.run and before :250
  - :250 itself untouched
- backend/app/lab/run_plans.py:
  - MechanicDiagnosisPlan and DiagnosisGuidePlan (StrictModel, Literal protocol, exact-text validators; reads_scoring and verdict_code_changed Literal False)
  - add both to the omit-absent tuple (:481-487)
  - freeze in the learn branch (:766-776)
  - refuse outside Learn (:824-827)
  - Start hash check (:996)
  - show in build_run_options (:628-630)
- backend/app/lab/exports.py: the plan-gated diagnosis_requests key.
- Docs:
  - correct PRODUCT_NATIVE_V2_RUN_2026-09-29.md :393 and :415-419, and the task-brief claim about source validation
  - add both rules to CURRENT_STATUS.md
- Follow-ups, separate and not in this change:
  - DiagnosticPanel reads the new record and labels hypotheses "unverified model proposal"
  - the diagnostics.py:72 defect, fixed only as a declared protocol-hash bump
  - a reviewed gate-tightening design (section 4)

====================================================================
4. WHAT NOT TO DO, AND WHY
====================================================================
1. Do not ship "fixed default" (fixed code runs the declared intervention when the Mechanic names none). It scored 9/10 on effectiveness but 4/10 on integrity, with blocking concerns:
   - It makes the diagnosis gate easier. After a locally minimal reduction, the default is the neighbour already seen at 0/3, so POLICY_GAP becomes nearly automatic and diagnosis becomes a repeat of reduction.
   - It removes the only path by which a real evidence-gap source avoids a POLICY_GAP label. Removing the fault clears evidence-gap violations too, and validate_gap is test-only.
   - It would store a false sentence. The unchanged classify_policy_gap writes "Fresh reproduction and the declared controlled intervention support a bounded policy hypothesis" (diagnostics.py:81, confirmed), while the fixed hypothesis claims no explanation.
   - It requires amending the written protocol (experiment-protocol.md:82-83 and the design line at diagnosis.py:1).
   - Its stated benefit is raising a gate's pass rate on a known source.
   Revisit only if the owner accepts the amendment, it is paired with a gate that tests something reduction did not, and the explanation text is fixed under a new protocol hash.
2. Do not raise the 600 limit or truncate model text. Text is shared with stored experiment hypotheses, and model answers must stay verbatim (mechanic.py:1).
3. Do not let proposed_kind or the hypothesis affect the verdict. That would give the model verdict authority.
4. Do not remove the citation and label text (V2_MEMORY, adapter labels, citation block) yet:
   - it is accurate, and it is the only explanation of C6 if C6 ever fails
   - removing it changes runtime_contract bytes shared with candidate requests
   - it breaks citation_status._with_pointer, which requires memory==V2_MEMORY
   It is the next step only if the probe shows definitions are not enough.
5. Do not add retains_violation predictions or options tailored to the hypothesis. They would create new routes to SUPPORTED.
6. Do not edit referee/diagnostics.py in place, even for the :72 defect. That changes checker_hash for every new diagnostic.
7. Do not judge success by POLICY_GAP rate, by proposed_kind, or by pooling new-plan rates with old ones.
8. Do not buy more live dev-5 replays as the next experiment. One live run costs about $7 (v2g: 305 calls, $6.73) and yields one diagnosis sample. The request-only probe yields about 140 samples for about $3. Probe before you spend.

====================================================================
5. OFFLINE TEST PLAN ($0)
====================================================================
Ground rules:
- Run with the network guard and assert 0 outbound connections.
- Run python -B so no bytecode lands in the repo.
- Copy saved stores read-only (mode=ro&immutable=1) to /Users/shree/FaultLab_Scratch/<stage>/, record the sha256 before and after, and delete the copy.
- Put durable evidence under faultlab/artifacts/<topic>-<date>/, not /tmp, which is wiped on restart.

Tests:
- T1 Plan freezing:
  - new Learn plans for reference, smolagents and smolagents-v2 carry both declarations
  - baseline and compare plans do not
  - altered text fails the exact validator
  - non-Learn plans are refused
  - Start refuses on a hash mismatch
  - saved native-v2b plans re-serialize with an unchanged plan_hash and no new keys
- T2 Flag off, byte for byte:
  - run the inv-a rebuild through the real Mechanic with a capture provider
  - first and repair turns must equal inv-a/*-diagnosis-request.json byte for byte (8,990 / 9,088 / 9,639 / 9,794 / 9,352 tokens; repairs 10,030 / 10,153)
  - mechanic_outputs fields unchanged
- T3 Rule 2 is additive:
  - every existing key is byte-identical
  - exactly one key is added
  - +631 tokens on every first turn
  - wrapper order: guide outside citation status outside size rule
  - the size rule counts the block and never compacts it (synthetic request near 28,000 tokens)
  - the citation block and the V2_MEMORY pointer are unchanged
- T4 Repair turn:
  - feed v2g's saved 614-character answer at attempt 0
  - flag on: the repair errors carry max_characters 600 and your_characters 614, plus the appended sentence (+47 tokens)
  - flag off: today's exact bytes
  - a 601-character hypothesis still fails in both modes; a 600-character one passes in both
- T5 Record, with scripted answers:
  - valid request gives VALID_REQUESTED
  - null gives VALID_NO_REQUEST and INCONCLUSIVE
  - invalid twice gives INVALID_OUTPUT with code_default and both output refs in order
  - invalid then valid (the v2f case) gives VALID_REQUESTED with both attempts
  - the option change strings equal the request's list
  - DiagnosticResult is identical to a flag-off run
- T6 Gate invariance:
  - matrix: {reproduction valid, invalid} x {null, valid request, invalid output} x {SUPPORTED, INCONCLUSIVE, CONTRADICTED, PREFLIGHT_REJECTED}
  - flag off and flag on must give identical kinds, intervention records, ledger reservations and trial counts
  - pinned sha256 of referee/diagnostics.py, reducer.py, lab/diagnosis.py and prompts/diagnosis.md, and PROTOCOL_HASH, all unchanged
  - a source assertion that the learning.py:250 gate line is still present
- T7 Export:
  - flag on: every attempt appears with its id, including v2f-style attempt 0
  - flag off: the export is byte-identical to one from the same scratch store before the change
- T8 End to end: the offline_fixture scripted Learn campaign follows the same path and counts as before, plus one diagnosis_requests record per diagnosis.
- T9 Replay: the prototypes reproduce their saved outputs (designer-integrity/prototype-results.json statuses; design-minimal/guide-measurement.json +631).
- Then the full backend suite with the network blocked, and the frontend type-check.

====================================================================
6. BEFORE ANY PAID STEP
====================================================================
- Check the ledger. The last recorded figure is $923.53 after v2g, per the run doc. I did not re-read the live ledger.
- Close the dashboard and run check_clock_drift.py.
- Never run two agents at once.
- Quote heredocs when writing declarations that contain $ figures, and re-read the dollar figures before hashing.

====================================================================
7. PRE-REGISTERED REQUEST-ONLY PROBE (paid; needs owner approval)
====================================================================
Purpose: measure whether Rule 2 and Part 1a change the Mechanic's answers, before any live episodes are spent. No episodes are run and no verdicts are produced.

Setup:
- Model: deepseek-ai/DeepSeek-V4-Pro-0813, with the product's frozen sampling settings read from the saved plan.
- Inputs: the five rebuilt requests from inv-a, exact bytes.
- Arms:
  - CONTROL: the requests as sent
  - GUIDE: the same requests plus the Rule 2 block
  - K=10 per request per arm, interleaved: 100 first-turn calls
- Repair sub-probe:
  - replay v2g's 614-character answer and v2f's 743-character answer as the assistant turn
  - then either today's repair message or the Part 1a message
  - K=10 each: 40 calls
- Total 140 calls. Cap $8 (140 x $0.0498 per-call bound = $6.97). Expected about $2-3.

Pre-registered outcomes, written down before running:
- P1, Rule 2 primary: on the four dev-5 requests, the share of hypotheses that blame citations, labels or evidence ids. Scored by misreading checker v2 claim matches plus human confirmation, blind to arm where possible.
  - Pass: GUIDE at most 10% (4 of 40) AND CONTROL at least 50% (if CONTROL is below 50%, the premise failed and the result is reported as uninformative).
- P2, Rule 2 guard: first-attempt schema validity in GUIDE is not lower than CONTROL by more than 5 of 40, and the over-600 rate is not higher by more than 5 of 40.
- P3, Rule 2 secondary, reported with counts and a one-sided Fisher test, no pass bar:
  - non-null request rate on dev-5, GUIDE vs CONTROL
  - share of hypotheses naming confirmation-after-FAILED (C3) and the report inconsistency (C5), by a written rubric
  - for dev-6, naming C4 rather than the unlabelled o3
- P4, Part 1a: share of repair turns returning a valid hypothesis of 600 characters or fewer.
  - Pass: at least 9 of 10 on each setup with the new message.
  - Today's message is measured alongside as the baseline.
- proposed_kind is reported descriptively only.

Decision rule:
- Rule 1 ships after the offline tests pass, unless P4 shows the new message is worse than today's.
- Rule 2 ships only if P1 and P2 pass.
- If P1 fails, the next design is trimming the label text from diagnosis requests only.
- If P1 passes but P3 shows declines unchanged, record that the Mechanic's veto persists and bring the gate question to the owner as a separate decision.

====================================================================
8. DECLARED LIVE READ-OUT FOR THE NEXT RUN
====================================================================
Run: one live Learn campaign with native adapter v2.1 and the DeepSeek-V3.1 Actor.
- Same setup as v2g: the V4-Pro Mechanic, history replay of dev-5 and dev-6, the fireability rule, evidence-retry v3.
- The only additions: mechanic_diagnosis v1, plus diagnosis_guide v1 if the probe passed.
- Expected cost is about $7.

Declared before the run:
- Q1 (Part 1a): Did any diagnosis end INVALID_OUTPUT? For every first attempt over 600, did the repair come back at 600 or fewer?
- Q2 (Rule 2, if shipped): Does the dev-5 hypothesis blame citations or labels (checker v2 plus a person)? Did the Mechanic request the offered intervention (VALID_REQUESTED)?
- Q3 (Part 1b): Does every diagnosis have a diagnosis_requests record whose status, attempt ids and proposed_kind source agree with mechanic_outputs? Does the export contain every attempt with its id?
- Guardrails:
  - 0 clock drift
  - all worlds VALID
  - diagnostics.py hash and PROTOCOL_HASH unchanged
  - every diagnosis request under the input limit
  - no MechanicContextUnfit refusals
- Not success measures: the POLICY_GAP count, proposed_kind, and anything after diagnosis (candidates, source validation, challenge). Those are reported, not credited to this change.
- Interpretation: this is n=1 per source. The run can falsify:
  - INVALID_OUTPUT after a limit-stating repair
  - a citation-based null request under the guide
  - a missing or inconsistent record
  It cannot confirm effect sizes; those come from the probe.
- Report every diagnosis as a row: proposal_status, attempts, first-attempt length, repair outcome, requested id, intervention result and verdict.

====================================================================
9. ONE-PARAGRAPH SUMMARY
====================================================================
The dev-5 source is reliable: it reproduced and reduced 4 of 4 times, and every native-v2 intervention that ran was SUPPORTED. What decides the verdict is not the Mechanic's reasoning, which fixed code ignores. It is whether the Mechanic returns a valid answer that names the one offered option. It lost once by declining, on a citation theory the recorded data refute, and once by overrunning the length limit by 14 characters. The recommended rules:
- state the limit on retry
- record honestly why no intervention ran
- if a cheap request-only probe shows it helps, give the Mechanic the public definitions, check meanings and task text it never had
None of this touches a gate. The faster fix, letting fixed code run the intervention itself, would lift dev-5 to about 4 of 4, but only by making diagnosis a rubber stamp of reduction. That is a gate decision for the owner, not a bug fix.

## PM decision (2026-09-30, Claude as PM, delegated by the owner)

- Approve Rule 1 (repair message states the limit; record why no intervention ran).
- Build Rule 2 (definitions block) but offer it only if the pre-registered probe (section 7) passes. Drop the interpretive C6 sentence (checks_note): it cannot be verified without opening checks.py; the C1-C8 public meanings are included verbatim only.
- Approve the pre-registered request-only probe (140 calls, cap $8), to be declared before it runs.
- Reject the fixed-default design.
- Correct the run doc (done, commit b5d0008).
