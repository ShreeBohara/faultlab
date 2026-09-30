_Saved by the PM from the agents' returned text; content unedited._

FaultLab has recorded 30 live diagnoses. CONTRACT_EVIDENCE_GAP is not specific to native agents: it follows the Mechanic model. The DeepSeek-V4-Pro Mechanic proposed it in 15 of 16 diagnoses (5 of 5 for the reference agent, 10 of 11 for native agents). The V3.1 Mechanic proposed it in 3 of 14. Declining the intervention is rare: 3 of 30, all native. An INCONCLUSIVE diagnosis did later turn POLICY_GAP on the identical source, once: native v2 dev-5, v2e then v2f. I also found that the v2g write-up misdescribes its dev-5 diagnosis (details under "Correction").

Everything was read-only and cost $0. Output folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/analysis-diagnosis-2026-09-30/inv-c/
- INVESTIGATION_C_HISTORY.md: the full write-up; its content is summarised here in case the file is refused.
- diagnoses_table.csv and diagnoses_table.json: 30 rows with store record ids.
- rates.json: the rates, post-hoc Fisher tests and same-source chains.
- store_inventory.json: every store holding a diagnosis and how it was classed.
- scripts/ and intermediate/: the read-only scripts and their derived data.

## What was scanned
- 483 SQLite stores were opened as file:PATH?mode=ro&immutable=1. All -wal files were 0 bytes, so nothing was missed.
- 76 stores hold diagnosis records, 74 distinct diagnostic ids in all.
- **Live: 30.**
  - 19 reference agent (V3.1 Actor), 2026-09-13 and 09-20, in artifacts/lab.sqlite3. The phase before/after stores are copies of the same ids.
  - 5 native v1: FaultLab_Runs/2026-09-29/native-learn and native-learn-v3.
  - 6 native v2: 1 in FaultLab_Runs/2026-09-30/native-v2 (campaign b05ac280); 5 in native-v2b (v2d, v2e, v2f, and two in v2g).
- **Excluded as offline: 44.** They come from scripted fixtures and tests (product-loop attempts, onboarding tests, product-retry probes). All are scripted POLICY_GAP to POLICY_GAP with provider_calls 0.
- 8 further ids appear only in offline review evidence files; also excluded.

## How each diagnosis was traced
- The diagnostic record does not store the Mechanic output when no intervention ran. So I linked each diagnostic to its diagnosis.md mechanic_outputs by insertion order.
- Where an intervention exists, its proposal_ref confirms the link.
- I re-checked every Mechanic output against the repo's DiagnosticProposal schema with bytecode writes disabled.
- For native rows I also recomputed the intervention options using today's code.

## Rates
| group | CEG (final) | requested intervention (raw) | declined | output rejected | intervention SUPPORTED when run | POLICY_GAP | candidate after a POLICY_GAP |
|---|---|---|---|---|---|---|---|
| reference (19) | 8/19 | 18/19 | 0/19 | 1/19 | 7/18 | 7/19 | 6/7 |
| native v1 (5) | 4/5 | 4/5 | 1/5 | 0/5 | 1/4 | 1/5 | 1/1 |
| native v2 (6) | 6/6 | 4/6 | 2/6 | 1/6 | 3/3 | 3/6 | 3/3 |

Candidates that passed source validation: reference 1 of 12, native v1 1 of 2, native v2 3 of 4.

## Is CONTRACT_EVIDENCE_GAP specific to native agents?
No.
- It tracks the Mechanic model (Fisher p=0.00009, post hoc). Every native diagnosis used V4-Pro, so "native agents get CEG" is confounded with "V4-Pro says CEG".
- The diagnosis prompt has not changed since commit f21b970 (2026-09-13 19:11 UTC).
- The label does not affect the verdict. classify_policy_gap (referee/diagnostics.py:76-81) uses only the reproduction trials and the intervention result; lab/diagnosis.py:149 just stores the proposed kind.
  - Diagnoses where the Mechanic said CEG ended POLICY_GAP 8 of 18 times.
  - Diagnoses where it said POLICY_GAP ended POLICY_GAP 3 of 10 times.
- What is native-v2-specific is the hypothesis content. By my manual reading, it blames citations or labels in 5 of 6 native v2 hypotheses, against 1 of 24 elsewhere. Reference and native v1 CEG hypotheses blame receipt timing instead.

## Is declining the intervention common?
No: 3 of 30.
- eac3d243 (native v1): the decline was justified. All 4 options, including removing the fault, had already shown 1/3 violations in reduction.
- 723354f7 (native v2, C4) and b0eeb89d (v2e): discriminating options had been observed at 0/3, yet the Mechanic declined, with a citation theory.
- A second route to "no intervention" is output that fails validation twice (2 of 30):
  - 93da89fe: the V3.1 Mechanic wrote corrupted evidence ids (a CJK character inside the hex).
  - a0dd0c48 (v2g): the hypothesis was too long.
- V4-Pro wrote an over-length hypothesis on the first try in 4 of 16 diagnoses; the format repair fixed 3 of the 4.

## Correction to the v2g write-up
docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md:393 says the Mechanic "itself proposed INCONCLUSIVE and requested no intervention". The store shows otherwise.
- In both attempts the Mechanic proposed CONTRACT_EVIDENCE_GAP and requested intervention-828103e0598f48f8675994a5.
  - That is remove_primitive:0, the only option, which reduction had observed at 0/3.
  - The attempts are mechanic-ec2f80bf4d9b4543adf0b5ac3473f69c and mechanic-5bb12477f42d43afb96d991b3e865001.
- Both failed "hypothesis: string_too_long": 614 characters against the 600 limit (contracts/models.py:24, 369). The repair turn repeated the same text.
- So Mechanic.diagnose returned None (agents/mechanic.py:65-74), and diagnosis.py:149 recorded proposed_kind INCONCLUSIVE.
- Across v2d to v2g, the Mechanic requested the intervention for dev-5 in 3 of 4 runs and declined once (v2e). The product accepted 2 of 4.
- The diagnostic record cannot tell "declined" from "invalid output". That is an observability gap in the product.

## INCONCLUSIVE later POLICY_GAP on the same source?
Yes, once, on an exact match. The dev-5 source (source recipe f0f2cb22…, reduced recipe 193add68…) went:
- v2d POLICY_GAP (57fa14bc)
- v2e INCONCLUSIVE (b0eeb89d, declined)
- v2f POLICY_GAP (dddc1a1b)
- v2g INCONCLUSIVE (a0dd0c48, over-length)

The other two exact repeats are both reference sources:
- 27db91e9… (F2 delay 5, seed 42): INCONCLUSIVE 3 of 3 (93da89fe, 7fe4d06b, 5d606f16).
- beebb28a…: POLICY_GAP 2 of 2 (a3397fd8 on 09-13, 6cb0e8ab on 09-20).

Grouping by the same fault shape with different seeds, the reference agent's results mix freely: delay 5 gave 5 POLICY_GAP of 10, delay 4 gave 2 of 7, delay 3 gave 0 of 2.

## Where the bottleneck sits
- **Reference and native v1:** the Mechanic almost always asked for an intervention (22 of 24). The fresh intervention itself was what failed. Of 14 INCONCLUSIVE interventions, 9 had a control that did not reproduce 3/3, and 5 had a treatment that still violated. One of those (b4c25b59) violated with no fault at all.
- **Native v2:** every intervention that ran was SUPPORTED (3 of 3). All 3 misses came from the Mechanic's output: 2 declines and 1 length rejection.

## Key facts

- 30 live diagnoses: 19 reference (V3.1 Actor, 2026-09-13/20), 5 native v1, 6 native v2; 44 more are offline scripted fixtures and are excluded
- CONTRACT_EVIDENCE_GAP (final raw proposal): reference 8/19, native v1 4/5, native v2 6/6. By Mechanic model: V4-Pro 15/16 (reference 5/5, native 10/11) vs V3.1 3/14 (post-hoc Fisher p=0.00009)
- The proposed kind does not affect the verdict (referee/diagnostics.py:76-81; lab/diagnosis.py:149): CEG proposals ended POLICY_GAP 8/18, POLICY_GAP proposals 3/10
- Declined the intervention with a valid proposal: 3/30, all native (eac3d243 native v1, justified; 723354f7 native v2 C4; b0eeb89d v2e); reference 0/19
- Output rejected after format repair: 2/30. 93da89fe had corrupted evidence ids from the V3.1 Mechanic; a0dd0c48 (v2g) had a 614-char hypothesis against the 600 limit in both attempts
- The v2g doc line (docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md:393) is wrong: the Mechanic proposed CEG and requested intervention-828103e0598f48f8675994a5 in both attempts (mechanic-ec2f80bf…, mechanic-5bb12477…). The product recorded INCONCLUSIVE because both failed the length check
- Across v2d-v2g the dev-5 Mechanic requested the intervention in 3 of 4 runs and declined once (v2e); the product accepted 2 of 4
- Exact-source repeat: native v2 dev-5 (source recipe f0f2cb22…, reduced recipe 193add68…) went POLICY_GAP (v2d), INCONCLUSIVE (v2e), POLICY_GAP (v2f), INCONCLUSIVE (v2g). This is the only case of INCONCLUSIVE later becoming POLICY_GAP on an identical source
- Reference exact repeats: 27db91e9… INCONCLUSIVE 3/3; beebb28a… POLICY_GAP 2/2. Same fault shape with different seeds: delay 5 gave 5 POLICY_GAP of 10, delay 4 gave 2 of 7
- Intervention SUPPORTED when run: reference 7/18, native v1 1/4, native v2 3/3. Of 14 INCONCLUSIVE interventions, 9 had a control that did not reproduce 3/3 and 5 had a treatment that still violated
- A candidate followed 10 of 11 POLICY_GAP diagnoses; e0a68956 got none because its campaign hit the dollar reservation. Candidates passing source validation: reference 1/12, native v1 1/2, native v2 3/4
- By my manual reading, citation-blaming hypotheses appear in native v2 5/6 vs 1/24 elsewhere
- Outputs are in /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/analysis-diagnosis-2026-09-30/inv-c/ (INVESTIGATION_C_HISTORY.md, diagnoses_table.csv/.json, rates.json, store_inventory.json, scripts/, intermediate/)

## Unknowns

- The exact diagnosis prompt and context seen by the earliest V3.1-Mechanic campaigns (2026-09-13 16:16-17:51 UTC). They predate commit f21b970, and the stores do not hash the prompt
- Reference-era intervention option ids cannot be recomputed with today's code because the hash inputs changed; for those rows, the intervention having run is taken as proof the id was accepted
- Whether the V4-Pro vs V3.1 CEG difference comes from the model itself or from other changes made at the same time (runtime contract text, evidence summaries, the native V2_MEMORY text)
- The hypothesis themes are one analyst's manual reading, not a product classification
- The two diagnostic records (a0dd0c48, 93da89fe) do not store validation errors; the rejection reasons were reconstructed by re-running today's schema on the saved raw outputs
- The Fisher tests are post hoc on small, non-concurrent samples with different code versions; they are descriptive only
- Two empty-blob git objects appeared at 09:42:17, one in artifacts/product-dependability-2026-09-29/clone/.git, which I never touched. I ran only read-only git commands (log, show, status, diff --stat) and believe another concurrent process made them, but I cannot prove it
