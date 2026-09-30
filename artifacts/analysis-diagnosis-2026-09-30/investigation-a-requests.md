_Saved by the PM from the agents' returned text; content unedited._

INVESTIGATION B: THE DIAGNOSIS PROTOCOL (read-only, $0)

Scope and method. I read backend/app/agents/prompts/diagnosis.md, backend/app/lab/diagnosis.py, backend/app/referee/diagnostics.py, backend/app/agents/mechanic.py, backend/app/referee/reducer.py, backend/app/lab/citation_status.py, backend/app/lab/loop_limits.py, the gate at backend/app/lab/learning.py:236-250, and the design docs. I did not open referee/checks.py. These four files are byte-identical at every commit from before v2d (7f5d4f6~1) through 1384267 (after v2g) and in the working tree: diagnosis.md fd1640cf, diagnosis.py 6a9779b8, diagnostics.py 9ffa3b83, mechanic.py dd4ce44e. So the code below is exactly what ran. I also opened the saved store read-only (immutable URI) and recomputed each run's intervention options and schema checks locally, with no network. The script and its output are in faultlab/artifacts/analysis-diagnosis-2026-09-30/investigation-b-protocol/.

1. What the Mechanic is asked for, and how the kinds are defined for it
- The system prompt (diagnosis.md:1) asks for exactly {proposed_kind: "POLICY_GAP"|"CONTRACT_EVIDENCE_GAP"|"INCONCLUSIVE", hypothesis: string<=600, evidence_ids: [1..36 supplied IDs], requested_intervention_id: one supplied choice ID or null}. The schema appended to the request (mechanic.py:21) has only the bare enum and maxLength 600, with no descriptions (TypeAdapter(DiagnosticProposal), models.py:367-371).
- None of the three kinds is defined anywhere the Mechanic can read. The only hints in the prompt are:
  - "A present status endpoint suffering an outage is not a missing endpoint."
  - "Unavailable evidence or nondiscriminating experiments warrant INCONCLUSIVE." (diagnosis.md:1)
  - "Compare the original report ... and delivered terminal receipts with the supplied runtime contract." (diagnosis.md:3)
- The real definitions live only in human-facing documents:
  - Policy gap: "the available evidence is sufficient, but the Actor needs better recovery behavior."
  - Contract evidence gap: "the available public API evidence cannot distinguish important underlying outcomes within the tested deadline." (docs/demo-guide.md:471-473)
  - See also FaultLab_Specs/specs/001-faultlab-loop/experiment-protocol.md:90-124.
- With no definition, "CONTRACT_EVIDENCE_GAP" is open to a literal reading: a gap between the contract and the evidence.
  - Every one of the 7 raw diagnosis outputs chose CONTRACT_EVIDENCE_GAP, including v2f's (mechanic-cf9b2b6da60d4f609cb2a2c9c3a7c063), whose own text says the cause is "the delayed FAILED upgrade receipt rather than a missing capability".
  - The only agent-specific text in the request is V2_MEMORY (diagnosis.py:19-27, sent as runtime_contract.actor_contract.memory, diagnosis.py:51). It is almost entirely about evidence labels. It says an uncited or undecoded token "fails the evidence check" and gives the example "the first attempt of a write the broker retried".
  - v2g's dev-5 hypothesis (mechanic-ec2f80bf4d9b4543adf0b5ac3473f69c) blames "the unshown first write attempt", which echoes that example.
  - The task contract's only check-like rule is also about citations: "Cite only delivered evidence IDs" (integrations/external_agent.py:32).

2. How fixed code assigns the verdict
- In the Learn loop the verdict comes from classify_policy_gap alone (diagnostics.py:76-81, called at diagnosis.py:149).
  - reproduced (diagnostics.py:78) needs exactly 3 reproduction trials: distinct worlds and episodes, indices {0,1,2}, one scenario hash and one policy hash, each COMPLETED, VIOLATION, with the target check failed and the fault fired.
  - supported (diagnostics.py:79) needs reproduced, at least one intervention SUPPORTED with 3 trial pairs for this counterexample, and no intervention CONTRADICTED.
  - kind is POLICY_GAP if supported, otherwise INCONCLUSIVE (diagnostics.py:80).
- The possible verdicts here are only POLICY_GAP or INCONCLUSIVE. CONTRACT_EVIDENCE_GAP can never be the verdict in the Learn loop.
  - Only validate_gap (diagnostics.py:84-102) can return it. That function checks a separate evidence_gap_v1 witness: two worlds (one committed, one not), 10 fixed probes, horizon 10.
  - Its only callers are tests (backend/tests/referee/test_diagnostics.py, backend/tests/integration/test_diagnostic_evidence.py, backend/tests/simulator/test_faults_http.py). execute_witness (diagnostics.py:105) is likewise test-only.
  - The spec intends this: the fixture is separate and "Runtime models cannot switch profiles" (experiment-protocol.md:100-124; research.md:186-201).
- What makes an intervention SUPPORTED (diagnostics.py:41-73):
  - The one requested variant runs 3 fresh pairs, alternating arm order (diagnostics.py:56).
  - Every trial must be valid (reducer.valid_trial, reducer.py:42-43). An empty-fault treatment counts as valid without firing.
  - SUPPORTED means control shows the target violation 3/3 and treatment 0/3. CONTRADICTED means treatment 3/3. Anything else is INCONCLUSIVE (diagnostics.py:68-71).
- The prediction is hard-coded to 'removes_violation' (diagnosis.py:138).
  - The Mechanic cannot choose 'retains_violation', even though run_interventions supports it (diagnostics.py:46,69).
  - The protocol's own worked example is a retains-violation test (experiment-protocol.md:83).
- proposed_kind is written into the record (diagnostics.py:81) and read nowhere else in the backend.
  - The only other readers are display code: frontend/src/components/DiagnosticPanel.tsx:9 and RunSummary.tsx:59.
  - The hypothesis is copied into InterventionExperiment.hypothesis (diagnostics.py:72) and never evaluated.
  - The cited evidence_ids are only checked for membership and then dropped (DiagnosticResult evidence_ids=[], diagnostics.py:81).

3. When the Mechanic requests no intervention, or its output is invalid
- If requested_intervention_id is null (or the proposal is None), variants stays empty (diagnosis.py:134-135).
  - run becomes InterventionRun([],[]) (diagnosis.py:145), with no ledger reservation and no trials.
  - supported is False, so the verdict is INCONCLUSIVE. The diagnostic is saved with intervention_ids [].
  - learning.py:250 (`if diagnostic.kind!='POLICY_GAP': continue`) then drops the source for good. There is no second diagnosis request, no default run of the declared option, and no candidate.
- An invalid output takes the same path. After two failed attempts (mechanic.py:26,65-74), proposal is None, and diagnosis.py:149 records proposed_kind='INCONCLUSIVE'. That value is a code default, not what the model said.
- The single format-repair turn (mechanic.py:72-73) sends only {location:['hypothesis'], type:'string_too_long'}; with include_context=False, the 600 limit is dropped. Its instruction talks only about copying IDs ("Correct formatting only. Copy cited IDs exactly..."). It never says to shorten the hypothesis.
- The Mechanic is never told any of these consequences:
  - that null ends the source;
  - that only a SUPPORTED fixed-code result allows a repair;
  - that its proposed_kind has no effect;
  - that CONTRACT_EVIDENCE_GAP cannot be established in this loop;
  - that trials already observed during reduction do not count, because the fixed rule needs fresh trials of the option it requests.

4. How the intervention options are generated and described
- Options come from neighbors() of the retained (reduced) recipe (diagnosis.py:125-130; the recipe is passed at learning.py:236,246).
  - neighbors (reducer.py:25-39) lists, in order: remove_primitive:i; lower_occurrence:i:v; lower_parameter:i:key:v. F1 values come from (3000,2500,2000,1500); other kinds step down from their current value.
  - The first 4 are kept. Each ID is 'intervention-'+content_hash({counterexample_id, control, treatment})[:24] (diagnosis.py:129).
  - I recomputed the IDs, and they match the recorded ones: intervention-7b8a13a6ed07a7ba054e44e8 (v2d), intervention-eb9f974e4d0e1b0e60ab2070 (v2f), intervention-1fa1cf42ff627b60cfa631dd (v2g dev-6).
- Each option is shown to the Mechanic as {id, change (e.g. "remove_primitive:0"), treatment_fault_spec, prediction:'removes_violation', expected_result:'3/3 control target violations and zero treatment target violations', observed_treatment_trials}. The request also carries control_fault_spec and observed_control_trials (diagnosis.py:132).
  - The observed counts come from the reduction's own trials (observed_outcomes, diagnosis.py:110-120).
  - They were added on 2026-09-13 to stop the Mechanic from picking a treatment that still produces the violation (auto-memory faultlab-repair-demo-state.md:15). diagnosis.md:5 then tells it to "Request the intervention whose treatment removes the suspected cause and is expected to show zero target violations".
- Every option only weakens or removes the fault. None changes whether evidence is available, the policy, or the agent. So no option can tell a policy gap from an evidence gap: both explanations predict "no fault, no violation".
- After a LOCALLY_MINIMAL reduction, every option is a neighbor the reducer already tried and rejected (reducer.py:77-100). The "experiment" repeats the reducer's own result.
- All five diagnosed sources show this (recomputed_diagnosis_inputs.json):
  - dev-5 (v2d, v2e, v2f, v2g): retained recipe F2 delay 1, occurrence 1. There is exactly ONE option, remove_primitive:0. The Mechanic saw control 3 valid / 3 violations and treatment 3 valid / 0 violations before choosing.
  - dev-6 (v2g): two options, remove F4 and failure_count 1. Both had already shown 0/3 treatment violations, against control 3/3.
- Minor record defect: InterventionExperiment.change stores variant.prediction ('removes_violation') instead of the change string (diagnostics.py:72). The saved intervention records do not say which change ran; only the hashes do.

5. Can a CONTRACT_EVIDENCE_GAP proposal lead to a candidate? Yes, and it has happened three times.
- The gate reads only diagnostic.kind (learning.py:250), and kind ignores proposed_kind. The three cases, each with proposed CONTRACT_EVIDENCE_GAP and verdict POLICY_GAP:
  - diagnostic-57fa14bc65e941bfa5d55c392d325b7c (v2d), with intervention-7b8a13a6… SUPPORTED;
  - diagnostic-dddc1a1b692147cf9bb9aa15d0a80ca0 (v2f), with intervention-eb9f974e… SUPPORTED;
  - diagnostic-dc19567fb237465cac75b2caa63e7cea (v2g dev-6), with intervention-1fa1cf42… SUPPORTED.
- v2d's SUPPORTED experiment is stored with the hypothesis "cites evidence labels that were never shown to it". Nothing checked that claim, and the dashboard shows it next to a SUPPORTED badge (DiagnosticPanel.tsx:9).
- The repair Mechanic then receives the diagnostic record, which carries the kind, proposed_kind and a fixed explanation but no hypothesis (learning.py:259).

6. Is the Mechanic told the failed checks' names and meanings? Names yes, meanings no.
- What it gets:
  - target_invariant "C3" (diagnosis.py:132);
  - reduction.trial_outcomes, whose failed_checks lists read ["C3","C5"] (diagnosis.py:96-98);
  - a per-episode checks table in the observations summary (diagnosis.py:190-191) with check_id, passed, and a short category label such as upgrade_before_confirmation, truthful_report or delivered_cited_evidence (CheckResult, models.py:433-438; seen in the stored evidence for episode-183b78c814f44c26af8030a16b0ede05).
- What it does not get:
  - the definitions of C1-C8. PUBLIC_INVARIANTS (agents/explorer.py:21-30, e.g. C3 "The upgrade effect must occur before any confirmation effect") goes only to the Explorer (explorer.py:284);
  - any reason a check failed.
- The citation-status block (citation_status.py) adds per-episode cited/decoded counts in v2f and v2g only. It explicitly says nothing about why a check failed (citation_status.py:21).
- The context-size rule did not touch any diagnosis request. They were about 9-10k input tokens, and loop_limits.fit_request returns a request under the limit unchanged (loop_limits.py:326-327). The only mechanic_context_records are three v2f candidate requests.

7. Every place the verdict depends on the Mechanic's free choice
- (a) Producing a valid output within 2 tries (mechanic.py:26,65-74,76-85). Requirements: the exact enum; hypothesis at most 600 characters; 1-36 evidence IDs, all from evidence_ids[:36] (the first 36 observations of source plus reproductions, diagnosis.py:131-132); requested ID in the option list, or null. A failure gives INCONCLUSIVE.
- (b) Requesting a non-null intervention (diagnosis.py:135). Null gives INCONCLUSIVE.
- (c) Which option it picks when there are 2-4 (diagnosis.py:135-138). dev-5 had only one option; dev-6 had two, and both were predicted SUPPORTED.
- Nothing else the Mechanic writes matters. proposed_kind, the hypothesis text and the cited evidence all have zero effect (diagnostics.py:79-81).
- The rest is fixed or chance:
  - the reproduction must hold 3/3 (diagnostics.py:78);
  - the fresh control/treatment arms must repeat 3/3 and 0/3 (diagnostics.py:53-71);
  - stop and ledger limits (diagnosis.py:140-147).
- In practice, for dev-5: POLICY_GAP was near-certain whenever the Mechanic returned a valid output that picked the one offered option. The model's reasoning cannot change the verdict. Its format compliance and its willingness to request the option do.

8. Correction to the recorded story (v2g dev-5)
- docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md:393 says "the Mechanic itself proposed INCONCLUSIVE and requested no intervention". Lines 415-416 say its kind was "CONTRACT_EVIDENCE_GAP (or INCONCLUSIVE)" and that it requested the intervention "2 of 4". The task context repeats "INCONCLUSIVE (v2g)".
- The saved records say otherwise.
  - Both v2g dev-5 outputs, mechanic-ec2f80bf4d9b4543adf0b5ac3473f69c (attempt 0) and mechanic-5bb12477f42d43afb96d991b3e865001 (format repair), under request mechanic-request-e93fda592ce146e49dadeae69be4651e, proposed CONTRACT_EVIDENCE_GAP. Both requested intervention-828103e0598f48f8675994a5, which is the one option actually offered.
  - Both had an identical 614-character hypothesis, over the 600 limit, so both failed the schema.
  - diagnosis.py:149 then wrote proposed_kind='INCONCLUSIVE' into diagnostic-a0dd0c487cff41ddb5ec546c8dc14131, with no intervention run.
- v2f's first output (mechanic-36a16b375d5240b1983dbece2944f1eb) was 743 characters and was saved only by the repair turn (428 characters).
- Across dev-5 the Mechanic did request the single option in 3 of 4 runs (v2d, v2f, v2g). v2g was lost to the length limit. Only v2e (mechanic-ed993d65639949d7a6faf49021b31620) requested null.
  - v2e's hypothesis says the removal "eliminates the target violation, but ... do[es] not establish whether the report's evidence citations were valid". So it declined an experiment that could not test its citation theory. That is consistent with "Request one controlled intervention that distinguishes your hypothesis" and "nondiscriminating experiments warrant INCONCLUSIVE" (diagnosis.md:1).
- Of the two INCONCLUSIVE dev-5 diagnoses, one came from a 14-character overrun, not from any scientific judgement.
- Across all diagnosis requests, 3 of 7 raw outputs broke the 600 limit.

9. What diagnosis is for, according to the docs, and where the mechanism falls short
- Stated purpose:
  - "Model hypotheses select reviewed interventions; fixed code assigns verdicts." (diagnosis.py:1)
  - "Fixed bounded intervention and evidence-gap validation; explanations are proposals." (diagnostics.py:1)
  - "Diagnosis can identify missing API evidence instead of fabricating a prompt fix." (FaultLab_Specs/specs/001-faultlab-loop/spec.md:19)
  - FR-039: store Mechanic hypotheses separately from intervention results, and "distinguish observed associations from experimentally supported explanations". FR-040: classify POLICY_GAP / CONTRACT_EVIDENCE_GAP / INCONCLUSIVE. (spec.md:312-316)
  - "POLICY_GAP requires a reproducible target invariant plus a completed controlled intervention supporting the stated recovery hypothesis ... The fixed validator assigns the diagnostic kind; the model's proposed kind and explanation are nonauthoritative. Narration alone is never causal evidence." (experiment-protocol.md:90-96)
  - Evidence gaps are diagnosed only by the separate fixture (experiment-protocol.md:98-124; research.md:186-201 R10; .specify/memory/constitution.md:38-40).
  - The demo guide's question: "Is this failure fixable by a recovery policy, or is the necessary evidence unavailable?" and "Only a supported policy gap should lead to a recovery-policy proposal." (docs/demo-guide.md:465-477)
  - "A supported hypothesis permits a candidate proposal, never promotion" (diagnostics.py:81).
- Where the mechanism falls short:
  - The purpose is to separate "fixable by policy" from "evidence unavailable". The mechanism tests only whether removing or weakening the fault removes the violation. Both kinds of gap pass that test, and the evidence-gap test is not connected to the loop.
  - The protocol says the intervention must support "the stated recovery hypothesis". The code never relates the experiment to the hypothesis: a refuted citation theory (v2d) was recorded as SUPPORTED.
  - The design line "hypotheses select interventions" holds only in a thin sense. When the only choice is "click the one option or don't", the Mechanic's choice effectively is the verdict, while its reasoning is ignored.
  - For dev-5 the correct class was in fact a policy gap: the agent sent the confirmation after a FAILED upgrade receipt. The fixed code got that right twice only because it ignores the Mechanic's (always wrong) proposed_kind.

## Key facts

- The prompt's allowed kinds are bare enum names with no definitions (diagnosis.md:1; schema from models.py:367-371 has only the enum and maxLength 600). The definitions exist only in docs/demo-guide.md:471-473 and FaultLab_Specs experiment-protocol.md:90-124.
- Fixed code (classify_policy_gap, diagnostics.py:76-81) can only return POLICY_GAP or INCONCLUSIVE. POLICY_GAP needs a valid 3/3 reproduction plus one requested intervention that comes back SUPPORTED (fresh control 3/3, treatment 0/3), with nothing CONTRADICTED.
- CONTRACT_EVIDENCE_GAP is unreachable as a Learn-loop verdict: only validate_gap (diagnostics.py:84-102) returns it, and its only callers are tests (backend/tests/referee/test_diagnostics.py, backend/tests/integration/test_diagnostic_evidence.py, backend/tests/simulator/test_faults_http.py).
- proposed_kind, the hypothesis and the cited evidence_ids have zero effect on the verdict; proposed_kind is only recorded (diagnostics.py:81). The gate to a candidate is diagnostic.kind=='POLICY_GAP' (learning.py:250), so CONTRACT_EVIDENCE_GAP proposals led to candidates 3 times: diagnostic-57fa14bc (v2d), diagnostic-dddc1a1b (v2f), diagnostic-dc19567f (v2g dev-6).
- A null requested_intervention_id, or an output invalid twice, gives an empty InterventionRun and INCONCLUSIVE (diagnosis.py:135,145,149). learning.py:250 then drops the source: no retry, no default run of the declared option, no candidate. The Mechanic is never told these consequences.
- Prediction is hard-coded to 'removes_violation' (diagnosis.py:138); the Mechanic cannot choose 'retains_violation' although run_interventions supports it (diagnostics.py:46,69).
- Options are neighbors() of the retained recipe (reducer.py:25-39), first 4 (diagnosis.py:125-130), shown with change, treatment spec, a fixed prediction/expected_result text and the reduction's observed counts (diagnosis.py:132). Every option weakens or removes the fault, so none can tell a policy gap from an evidence gap.
- For all 4 dev-5 diagnoses, the retained recipe (F2 delay 1, occurrence 1) has exactly ONE option (remove_primitive:0). Before choosing, the Mechanic already saw control 3/3 and treatment 0/3 from reduction, so the 'experiment' repeats the reducer's own result. Recomputed IDs match the records (e.g. intervention-7b8a13a6ed07a7ba054e44e8, intervention-eb9f974e4d0e1b0e60ab2070).
- v2g dev-5 correction: both raw outputs (mechanic-ec2f80bf4d9b4543adf0b5ac3473f69c, mechanic-5bb12477f42d43afb96d991b3e865001) proposed CONTRACT_EVIDENCE_GAP and requested the one valid option intervention-828103e0598f48f8675994a5, but each had a 614-character hypothesis, over the 600 limit. diagnosis.py:149 then recorded proposed_kind INCONCLUSIVE (diagnostic-a0dd0c487cff41ddb5ec546c8dc14131). docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md:393 and :415-416 misstate this.
- The Mechanic requested the single dev-5 option in 3 of 4 runs (v2d, v2f, v2g); only v2e (mechanic-ed993d65639949d7a6faf49021b31620) chose null, while noting that the removal eliminates the violation but does not test its citation theory. 3 of 7 raw diagnosis outputs exceeded 600 characters (v2f attempt 0 at 743 was rescued by the repair turn).
- The format-repair turn (mechanic.py:69-73) passes only {location:['hypothesis'], type:'string_too_long'}, without the limit, and an instruction about copying IDs; it never says to shorten.
- The Mechanic sees failed-check IDs and short category labels (e.g. upgrade_before_confirmation, truthful_report) in the evidence summary (diagnosis.py:190-191; models.py:433-438), but no definitions: PUBLIC_INVARIANTS (explorer.py:21-30) is sent only to the Explorer (explorer.py:284), and no failure reasons are given.
- The only agent-specific text the Mechanic gets (V2_MEMORY, diagnosis.py:19-27) is about evidence labels and 'fails the evidence check', including the example 'first attempt of a write the broker retried'; v2g's hypothesis blames 'the unshown first write attempt'.
- The Mechanic in these runs was deepseek-ai/DeepSeek-V4-Pro-0813 (the model_id on every mechanic_outputs record); the dev-5 target invariant was C3 (counterexample records), with C5 failing alongside.
- The gate files (diagnosis.md, diagnosis.py, diagnostics.py, mechanic.py, reducer.py) are byte-identical from 7f5d4f6~1 through 1384267 and in the working tree, so the analysed code is what ran in v2d-v2g.
- Stated purpose: diagnosis.py:1; diagnostics.py:1; spec.md:19 and FR-039/FR-040 (spec.md:312-316); experiment-protocol.md:80-124; research.md:186-201; constitution.md:38-40; demo-guide.md:465-477. The design intends to separate 'fixable by policy' from 'evidence unavailable' and to require an intervention supporting the stated hypothesis, but the code tests neither.
- Minor record defect: InterventionExperiment.change stores the prediction ('removes_violation') instead of the change string (diagnostics.py:72).
- Evidence files written: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/analysis-diagnosis-2026-09-30/investigation-b-protocol/recompute_diagnosis_inputs.py and recomputed_diagnosis_inputs.json in the same folder (read-only store, $0).

## Unknowns

- I did not rebuild each run's full diagnosis request byte for byte (full summarize_evidence tables, runtime_contract text, citation block). What the Mechanic saw is inferred from byte-identical code plus the recomputed options and observed counts.
- I cannot say why v2e chose null beyond its own hypothesis text, or why the v2g repair turn resubmitted the identical 614-character text; model intent is not recorded.
- I did not re-verify the report_submitted citation records that refute the Mechanic's citation theories; that belongs to another investigation. I relied on the run doc and citation_status.py's description.
- I did not open referee/checks.py, so the exact C3/C5 logic is known only from the PUBLIC_INVARIANTS text (explorer.py:21-30) and the category labels.
- It is untested whether giving the Mechanic kind definitions, check meanings, a stated length budget, or telling it that null ends the source would change its choices; no experiment has been run.
- When reduction ends REDUCED, CAPPED or NO_REDUCTION rather than LOCALLY_MINIMAL, some options could lack reduction trials. That did not happen in these 5 diagnoses, so its behaviour here is unobserved.
- Whether the 48-call intervention reservation or the stop and ledger limits ever affected a diagnosis in these runs was not checked; the three interventions that ran each completed 3 pairs.
