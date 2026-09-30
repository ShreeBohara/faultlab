_Saved by the PM from the agents' returned text; content unedited._

INVESTIGATION A: WHAT THE MECHANIC SAW IN THE FIVE NATIVE-V2 DIAGNOSES ($0, offline, read-only)

Summary
- I rebuilt all 5 diagnosis requests offline with the product's own code. The rebuilt requests match the sent requests in token count. Each rebuilt first turn counts exactly 136 tokens more than the provider reported, and each rebuilt repair turn exactly 167 more. The offsets are constant, so they are fixed overhead and the content lengths agree.
- The recorded record overstates the Mechanic's role in the split. v2g's dev-5 diagnosis is recorded as proposed INCONCLUSIVE with no intervention, but that is not what the Mechanic said:
  - Both of its answers proposed CONTRACT_EVIDENCE_GAP and requested the intervention (`intervention-828103e0598f48f8675994a5`). The records are `mechanic-ec2f80bf4d9b4543adf0b5ac3473f69c` (attempt 0) and `mechanic-5bb12477f42d43afb96d991b3e865001` (attempt 1).
  - Both answers were rejected because the hypothesis was 614 characters, over the 600-character limit (`models.py:24`, `Text` max_length=600). The error was `string_too_long`.
  - The format-repair answer was byte-identical to the first one.
  - With no valid proposal, `diagnosis.py:135` ran no intervention and `diagnosis.py:149` recorded the fallback `proposed_kind='INCONCLUSIVE'`.
  - So `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md:393` is wrong ("the Mechanic itself proposed INCONCLUSIVE and requested no intervention"). Lines 418-419 of the same doc, and the task brief, repeat the error.
- The exports do not contain these rejected answers. An export only lists a Mechanic output that an intervention's proposal_ref points to. v2e's answer and v2g's two rejected dev-5 answers exist only in the store.
- Corrected tally across the four dev-5 raw answers:
  - The Mechanic requested the intervention in 3 of 4 (v2d, v2f, v2g).
  - It proposed CONTRACT_EVIDENCE_GAP in 4 of 4.
  - The two INCONCLUSIVE results had two different causes: v2e was a model choice (null request); v2g was a format failure.
  - v2f nearly failed the same way: its first answer (`mechanic-36a16b375d5240b1983dbece2944f1eb`) had a 743-character hypothesis and was repaired to 428 characters (`mechanic-cf9b2b6da60d4f609cb2a2c9c3a7c063`).

1. Rebuild method and how close it is
- Script: `inv-a/rebuild_diagnosis_requests.py`, run from faultlab/backend with the project .venv.
  - It uses a copy of the store read with mode=ro&immutable=1, saved to /Users/shree/FaultLab_Scratch/inv-a/rebuild and deleted afterwards.
  - The store's sha256 was `8aa9aa27…fcb` before and after.
  - The fixer guard refused 0 outbound connections.
- How it rebuilds each request:
  - It reads the learning loop's inputs to Diagnostician.run from saved records: counterexample, retained recipe, reproduction trials, source and reproduction evidence bundles.
  - It rebuilds the reduction summary with `diagnosis.reduction_context`, using the reducer's trial order: the 3 original trials, then each attempt's trial_ids.
  - It wraps a capture Mechanic exactly as `learning.py:243-244` does for each campaign's saved plan:
    - v2d: plain Mechanic.
    - v2e: BoundedMechanic.
    - v2f and v2g: CitationStatusMechanic around BoundedMechanic.
  - It builds the messages as `mechanic.py:21-22` does, and the repair turn as `mechanic.py:65-73` does.
- Fidelity evidence:
  - Rebuilt admission count vs provider input_tokens:
    - v2d: 8,990 vs 8,854
    - v2e: 9,088 vs 8,952
    - v2f: 9,639 vs 9,503
    - v2g-dev5: 9,794 vs 9,658
    - v2g-dev6: 9,352 vs 9,216
    - That is exactly +136 on all five.
  - Repair turns: v2f 10,030 vs 9,863 and v2g-dev5 10,153 vs 9,986, exactly +167 on both.
  - The files that build the request are identical at the backup commits 814a6e3 (v2d), 884de24 (v2e), 47b8f69 (v2f) and 661e2d0 (v2g) and today: `diagnosis.py`, `mechanic.py`, `prompts/diagnosis.md`, `external_agent_v2.py`, `models.py`, `tokens.py`, `reducer.py`, plus `citation_status.py` (at 47b8f69/661e2d0) and `loop_limits.py` (at 884de24 onward). I compared git blobs read-only.
  - `learning.py` differs only in the plan-gated wrappers and the fireability code.
- No compaction happened: every request is about 9-10k tokens against the 32,000 limit, and there are no `mechanic_diagnosis` records in mechanic_context_records.

2. What each Mechanic answer said
- v2d-dev5 (`mechanic-01188b04304645d8ab752f717411daa9`, valid):
  - Proposed CONTRACT_EVIDENCE_GAP and requested `intervention-7b8a13a6ed07a7ba054e44e8`. Hypothesis: 443 characters.
  - Quote: "cites evidence labels that were never shown to it under the v2.1 shown-order labeling contract … tokens that cannot be decoded to delivered evidence IDs"
  - Result: intervention SUPPORTED (3 pairs), recorded POLICY_GAP (`diagnostic-57fa14bc…`).
- v2e-dev5 (`mechanic-ed993d65639949d7a6faf49021b31620`, valid):
  - Proposed CONTRACT_EVIDENCE_GAP and requested nothing (null). Hypothesis: 405 characters.
  - Quote: "cites evidence IDs that were never shown to it as labels … The fixed intervention removing the F2 primitive eliminates the target violation, but the supplied observations do not establish whether the report's evidence citations were valid under the shown-order label contract."
  - Result: INCONCLUSIVE (`diagnostic-b0eeb89d…`).
- v2f-dev5:
  - Attempt 0: 743 characters, rejected with `string_too_long`.
  - Attempt 1 (`mechanic-cf9b2b6d…`): proposed CONTRACT_EVIDENCE_GAP and requested `intervention-eb9f974e4d0e1b0e60ab2070`. It makes no citation claim; it describes the real failure but ends "which the scorer treats as inconsistent …" and "rather than a missing capability".
  - Result: SUPPORTED, POLICY_GAP (`diagnostic-dddc1a1b…`).
- v2g-dev5:
  - Both attempts were identical: CONTRACT_EVIDENCE_GAP, requested `intervention-828103e0598f48f8675994a5`, 614 characters. Both were rejected with `string_too_long`.
  - Quote: "the report's evidence_ids omit the unshown first write attempt".
  - The same answer also says the report "cites only delivered observations" and that "C6 passes".
  - Result: recorded proposed_kind INCONCLUSIVE and kind INCONCLUSIVE (`diagnostic-a0dd0c48…`).
- v2g-dev6, the C4 source (`mechanic-6804f09abb3b421ab7782f6784a3924e`, valid):
  - Proposed CONTRACT_EVIDENCE_GAP and requested `intervention-1fa1cf42ff627b60cfa631dd`.
  - Quote: "omits the transient send_confirmation error observation … the contract's evidence-labeling/citation rules create a gap".
  - Result: SUPPORTED, POLICY_GAP (`diagnostic-dc19567f…`).
- Full answers, validation errors and the diagnostic records are in `inv-a/mechanic-outputs.json`.

3. Field-by-field comparison: POLICY_GAP cases vs INCONCLUSIVE cases (`inv-a/comparison.json`; IDs normalised before comparing)
- Identical in all four dev-5 requests:
  - system prompt (sha `5488c7f5…`, 344 tokens)
  - output_schema (223 tokens)
  - target C3, reproduction_counts 3/3/3
  - control_fault_spec: one F2 UPGRADE_REJECTED fault, 1-tick delay
  - intervention_ids and the interventions block
  - observed_control_trials (3 fresh, 3 valid, 3 target violations)
  - every runtime_contract subfield except actor_contract.memory
- Intervention options: exactly one in every dev-5 request, `remove_primitive:0`. Its treatment has no faults, and `observed_treatment_trials` already shows 3 valid trials with 0 target violations from reduction. The wording is identical in all four.
- Differs by build, not by outcome:
  - v2d and v2e have the plain V2_MEMORY (206 tokens) and no citation block.
  - v2f and v2g have V2_MEMORY plus the pointer sentence (253 tokens) and the native_citation_status block (285-291 tokens).
  - The block rows all show cited==decoded and undecoded [] (v2f: 6/6, 5/5, 6/6, 6/6; v2g: 6/6, 7/7, 5/5, 5/5).
  - So v2d (POLICY_GAP) and v2e (INCONCLUSIVE) were shown the same fixed text. v2f (POLICY_GAP) and v2g-dev5 (INCONCLUSIVE) were also shown the same fixed text.
- Differs only through agent-run noise:
  - Evidence rows: 4 episodes each, same behaviour in every one. The agent reads the order, requests the upgrade (PENDING), polls PENDING then FAILED (UPGRADE_REJECTED), sends the confirmation (SUCCEEDED), and reports `{overall: CORRECTLY_REJECTED, upgrade_outcome: FAILED, notification_outcome: SUCCEEDED}`, failing C3 and C5.
  - Episodes have 5, 6 or 7 rows. v2f and v2g each have one episode with an extra get_operation_status UNKNOWN row.
  - evidence_ids: 22/22/23/23. reduction group splits vary slightly.
- Sizes of the user message in content tokens:
  - v2d 8,484; v2e 8,582; v2f 9,133; v2g 9,288; v2g-dev6 8,846.
  - observations: 3,336 / 3,353 / 3,603 / 3,815. runtime_contract: 2,780 / 2,780 / 2,827 / 2,827. reduction: about 1.1-1.3k.
  - Size does not separate the outcomes: POLICY_GAP at 8,484 and 9,133; INCONCLUSIVE at 8,582 and 9,288.
- One possible pattern, too small to rely on: the only two answers over the 600-character limit (v2f and v2g) came from the two builds with the citation block. The two builds without it produced 443 and 405 characters. That is 2 samples each, so I cannot attribute the overflow to the block.

4. What in the request plausibly steers the Mechanic to CONTRACT_EVIDENCE_GAP
- (a) The kinds are never defined.
  - `diagnosis.md:1` only lists them: "Output exactly {proposed_kind:\"POLICY_GAP\"|\"CONTRACT_EVIDENCE_GAP\"|\"INCONCLUSIVE\",…}".
  - The only guidance about kinds is "Unavailable evidence or nondiscriminating experiments warrant INCONCLUSIVE."
  - The output_schema has no descriptions.
  - In code, CONTRACT_EVIDENCE_GAP means something narrow: `referee/diagnostics.py:84-102` `validate_gap` uses the fixed evidence_gap_v1 profile, "Terminal upgrade evidence was unavailable through all declared paths". The Mechanic never sees this.
  - On this path, proposed_kind has no effect on the verdict. `classify_policy_gap` (`diagnostics.py:76-81`) decides the kind only from reproduction and interventions, and only stores proposed_kind.
- (b) The only agent-specific story in the request is about citations and evidence IDs. Its three sources are:
  - Memory text, `diagnosis.py:19-27`, which contains three key quotes:
    - "a token kept as written is one the agent was never shown as a label, and it fails the evidence check"
    - "an observation it was never shown (for example the first attempt of a write the broker retried inside one tool call …) gets no label"
    - "that numbering counts every recorded observation, including ones the agent never saw, so it can differ from the agent's obs-N"
  - The adapter protocol, `external_agent_v2.py:89-108`, about 556 tokens:
    - "any other token passes through verbatim and is scored as written"
    - "unshown_observations": "never labelled: … the first attempt of a write the broker retried inside one tool call are not in any tool result"
  - The citation block, from v2f on, about 290 tokens.
  - Together these are about 760-1,100 tokens of label and citation text. The word "evidence" appears 104-113 times in each user message.
- (c) The Mechanic's wording tracks these passages closely:
  - "never shown" (v2d, v2e) matches "never shown as a label".
  - "cannot be decoded" (v2d) matches "decoded back … kept exactly as written".
  - "shown-order label(ing) contract" (v2d, v2e) matches the protocol name "v2.1-shown-order-labels".
  - "omit the unshown first write attempt" (v2g-dev5) matches the retried-write example.
  - "evidence-labeling/citation rules create a gap" (v2g-dev6).
  - The name CONTRACT_EVIDENCE_GAP matches word for word the loudest theme of the request: the runtime *contract*'s text about *evidence*.
- (d) The same request contains counter-evidence the Mechanic did not use:
  - Every episode's check row has `C6 delivered_cited_evidence passed: true`.
  - Every report citation maps to a delivered row, shown as contiguous o1..oN. `summarize_evidence` only rewrites IDs present in the bundle (`diagnosis.py:175,181`).
  - The store's report_submitted events confirm this for every dev-5 episode: every row was labelled, and every cited label decoded to a delivered observation (`inv-a/report-submitted-citation-facts.json`).
  - In the dev-6 episodes one row (o3) really was never labelled, and the reports cite o1, o2, o4, o5, o6. This is exactly the gap the memory text describes, and the Mechanic turned it into its causal story.
- (e) Information about the real failure is missing:
  - The plan's task text ("Upgrade the authorized order to express shipping, then record one truthful confirmation.") is not in the request: "express" occurs 0 times.
  - Nothing states that a confirmation requires a SUCCEEDED upgrade, and nothing says what CORRECTLY_REJECTED means (it appears only as an enum value).
  - Nothing says why C5 failed. Check rows carry only check_id, category (for example "truthful_report" and "upgrade_before_confirmation"), passed, evidence_ids and event_ids.
  - `diagnosis.md:3` points the Mechanic at the contract: "Compare the original report … and delivered terminal receipts with the supplied runtime contract".
  - That contract describes only the report schema and the label mechanics, so the only thing the report can be compared against is its citations.
- (f) The only intervention cannot test a citation theory, and the prompt tells a citation believer not to request it.
  - Removing the fault removes the rejection and the confirm-after-rejection together.
  - `diagnosis.md:1` says "Request one controlled intervention that distinguishes your hypothesis … nondiscriminating experiments warrant INCONCLUSIVE."
  - v2e followed this literally: its hypothesis says the intervention "eliminates the target violation, but … do[es] not establish whether the report's evidence citations were valid", and it requested null.
  - So the citation misreading can directly produce the null request. v2d, v2f and v2g requested the intervention anyway.
  - Nothing in the request says that requesting the intervention is the only path to a candidate (`learning.py:250`), or that proposed_kind is not used.
- (g) The repair turn can block the fix it needs.
  - The repair message (`mechanic.py:73`) gives only `{"location":["hypothesis"],"type":"string_too_long"}` plus "Correct formatting only … Do not add authority, a new hypothesis, or a replacement canned solution."
  - It does not restate the 600-character limit, and it discourages rewriting the text.
  - v2g answered with the identical 614-character text; v2f shortened its answer.

Conclusion
- In these four dev-5 diagnoses, the POLICY_GAP / INCONCLUSIVE split does not follow from any difference in what the Mechanic was shown.
- It follows from one sampled null request (v2e) and one length-limit failure (v2g).
- The constant CONTRACT_EVIDENCE_GAP label and the repeated citation theories line up with request text that is heavy on citations, has no kind definitions, and never states the task or the reason for C5.

Files written, all under `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/analysis-diagnosis-2026-09-30/inv-a/`:
- `rebuild_diagnosis_requests.py` and `compare_requests.py`
- `{v2d-dev5,v2e-dev5,v2f-dev5,v2g-dev5,v2g-dev6}-diagnosis-request.json`: the exact messages, including the repair turns for v2f and v2g-dev5
- `*-diagnosis-context.json`: pretty-printed user content
- `rebuild-index.json`, `comparison.json`, `mechanic-outputs.json`, `report-submitted-citation-facts.json`, and the stdout/stderr logs

The scratch copy was deleted.

## Key facts

- v2g-dev5 was not a Mechanic INCONCLUSIVE. Both answers (mechanic-ec2f80bf4d9b4543adf0b5ac3473f69c and mechanic-5bb12477f42d43afb96d991b3e865001) proposed CONTRACT_EVIDENCE_GAP and requested intervention-828103e0598f48f8675994a5. Both were rejected with string_too_long (hypothesis 614 characters, limit 600 at models.py:24), and the repair answer was byte-identical. diagnosis.py:135 then ran no intervention and diagnosis.py:149 recorded proposed_kind INCONCLUSIVE. docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md:393 says otherwise and is wrong.
- The Mechanic requested the declared intervention in 3 of 4 dev-5 raw answers (v2d, v2f, v2g). Only v2e (mechanic-ed993d65639949d7a6faf49021b31620) chose null. It proposed CONTRACT_EVIDENCE_GAP in 4 of 4.
- v2f's first answer (mechanic-36a16b375d5240b1983dbece2944f1eb, 743 characters) also failed string_too_long. It was repaired to 428 characters (mechanic-cf9b2b6da60d4f609cb2a2c9c3a7c063).
- The rebuilt requests match what was sent in token count. The frozen-tokenizer count minus the provider's input_tokens is exactly 136 on all 5 first turns and exactly 167 on both repair turns. The request-building files are identical at backup commits 814a6e3, 884de24, 47b8f69 and 661e2d0.
- In all four dev-5 requests these fields are identical after replacing IDs: system prompt (sha 5488c7f5), output_schema, control spec, the single intervention remove_primitive:0 (already observed 3 valid / 0 violations), observed_control_trials 3/3/3, and every runtime_contract subfield except the memory text. v2d and v2e share one fixed text, and v2f and v2g share another.
- Neither kind definitions nor size separate the outcomes: the diagnosis prompt never defines the three kinds (diagnosis.md:1), and user-message sizes of 8,484 / 8,582 / 9,133 / 9,288 tokens do not line up with POLICY_GAP vs INCONCLUSIVE.
- proposed_kind never affects the verdict (referee/diagnostics.py:76-81). What CONTRACT_EVIDENCE_GAP means in code (validate_gap, diagnostics.py:84-102) is never shown to the Mechanic.
- The only agent-specific story in the request is about citations: V2_MEMORY (diagnosis.py:19-27), adapter_protocol evidence_labels (external_agent_v2.py:89-108) and, from v2f on, the citation block. Together that is about 760-1,100 tokens. The Mechanic's phrases 'never shown', 'cannot be decoded', 'shown-order label contract' and 'unshown first write attempt' echo those passages.
- Every request also shows counter-evidence: C6 delivered_cited_evidence passed:true in every episode, and report citations that all map to delivered rows. report_submitted events confirm every dev-5 row was labelled and every cited label decoded; only the dev-6 episodes had a never-labelled row (o3).
- Missing from every request: the plan's task text ('Upgrade the authorized order to express shipping, then record one truthful confirmation.'; 'express' occurs 0 times), what CORRECTLY_REJECTED means, and any reason why C5 failed. Check rows carry only id, category, passed flag and evidence ids.
- The only intervention offered (remove the fault) cannot test a citation hypothesis, and diagnosis.md:1 says nondiscriminating experiments warrant INCONCLUSIVE. v2e's null request follows that rule for its own citation hypothesis.
- The exports omit Mechanic diagnosis answers that no intervention references: v2e's answer and v2g-dev5's two rejected answers exist only in the store.

## Unknowns

- I could not prove byte-identity with what was sent: the product never stores the sent Mechanic request (mechanic_outputs keeps only the raw answer, request_id and usage, and the trace span inputs keep only evidence_ids, mechanic.py:30). The fidelity evidence is the constant token offset plus unchanged source files.
- Why v2e chose null when v2d, on near-identical fixed text, requested the intervention. There is one sample per run, sampling settings were not examined, and no model was re-queried ($0 rule).
- Whether the citation block causes over-length hypotheses. Both over-limit answers came from the builds with the block (v2f, v2g), but that is n=2 per build.
- Whether defining the kinds, adding the task text or a C5 reason, or cutting the label text would change the Mechanic's output. This was not tested because it needs paid calls.
- The actual reason C5 or C4 failed in the scorer. checks.py was not opened as instructed, and I relied only on the check category names the Mechanic saw.
- Whether a valid v2g-dev5 answer would have reached POLICY_GAP. It is likely, since reduction already showed 3/3 control and 0/3 treatment violations, but the intervention was never run.
