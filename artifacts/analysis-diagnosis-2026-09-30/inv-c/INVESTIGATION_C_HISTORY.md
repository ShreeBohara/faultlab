# Investigation C: every live diagnosis FaultLab has recorded (read-only, $0)

Stage: inv-c. Date: 2026-09-30. No provider, W&B, Weave or network calls. Every store was opened as
`file:PATH?mode=ro&immutable=1` (every `-wal` file was 0 bytes, so nothing was missed). No repo file was changed
except the files in this folder. `referee/checks.py`, `artifacts/heldout2/` and `audit/` were not opened.

Files here:
- `diagnoses_table.csv` / `.json`: one row per live diagnosis (30 rows), with store record ids.
- `rates.json`: the rates below, the post-hoc Fisher tests, and the same-source chains.
- `store_inventory.json`: every store that holds a diagnosis and how it was classed (live, copy, offline).
- `scripts/`: the read-only scripts that produced all of this.

## 1. What was found

483 store files scanned; 76 hold diagnosis records; 74 distinct diagnostic ids.
- **30 are live**:
  - 19 reference-agent diagnoses (DeepSeek-V3.1 Actor), 2026-09-13 and 2026-09-20, all in `artifacts/lab.sqlite3`.
    The `phase*/before|after.sqlite3` stores are copies of these same ids.
  - 5 native v1 (smolagents adapter v1): the `native-learn` and `native-learn-v3` stores, 2026-09-29.
  - 6 native v2 (adapter v2 / v2.1):
    - 1 in `FaultLab_Runs/2026-09-30/native-v2`, campaign b05ac280;
    - 5 in `native-v2b`: v2d, v2e, v2f and two in v2g.
- **44 are offline.** They come from the scripted product-loop fixtures, onboarding tests and product-retry e2e probes.
  Every one is a scripted POLICY_GAP → POLICY_GAP (their summaries say `provider_calls: 0`), so they are excluded.
- 8 more ids appear only in offline review evidence files. They are excluded too.

## 2. The table (short form; the full one is `diagnoses_table.csv`)

Legend: Mech = Mechanic model (V3.1 or V4-Pro-0813). Kind = the Mechanic's final raw `proposed_kind` (CEG =
CONTRACT_EVIDENCE_GAP, PG = POLICY_GAP, INC = INCONCLUSIVE). Req = requested an intervention in its raw output. Path =
what the product did with it. Intervention = control and treatment target-violation counts.

| diag | run | agent | inv | Mech | Kind | Req | Path | Intervention | Verdict | Candidate |
|---|---|---|---|---|---|---|---|---|---|---|
| 93da89fe | 09-13 86d3e202 | ref | C5 | V3.1 | INC (1st try CEG) | 1st yes, final no | REJECTED: corrupted evidence ids ("极" inside hex), both tries | – | INC | – |
| 352d30ca | 09-13 e6ac7b05 | ref | C5 | V3.1 | PG | yes | ran | INC (ctrl 2/3) | INC | – |
| 55ee968b | 09-13 e6ac7b05 | ref | C5 | V3.1 | CEG | yes | ran | INC (ctrl 2/3) | INC | – |
| 7fe4d06b | 09-13 e6ac7b05 | ref | C5 | V3.1 | PG | yes | ran | INC (trt 1/3) | INC | – |
| ffd281b9 | 09-13 e6ac7b05 | ref | C5 | V3.1 | PG | yes | ran | INC (trt 1/3) | INC | – |
| 2b06444a | 09-13 44085f54 | ref | C5 | V3.1 | PG | yes | ran | INC (trt 1/3) | INC | – |
| 4c3a41b4 | 09-13 44085f54 | ref | C5 | V3.1 | PG | yes | ran | INC (ctrl 1/3) | INC | – |
| 5d606f16 | 09-13 44085f54 | ref | C5 | V3.1 | CEG | yes | ran | INC (ctrl 0/3) | INC | – |
| b2a7dda4 | 09-13 44085f54 | ref | C5 | V3.1 | PG | yes | ran | SUPPORTED | **PG** | 3 cands; 1 passed SV → challenge COUNTEREXAMPLE |
| a3397fd8 | 09-13 aa790230 | ref | C5 | V4-Pro | CEG | yes | ran | SUPPORTED | **PG** | 4 cands, all failed SV |
| 0af91fe7 | 09-13 eb1bcf7e | ref | C5 | V4-Pro | CEG | yes | ran | SUPPORTED | **PG** | 2 cands, failed SV |
| 112bdd98 | 09-13 eb1bcf7e | ref | C5 | V4-Pro | CEG | yes | ran (after repair of a 627-char hypothesis) | SUPPORTED | **PG** | 1 cand, failed SV |
| d96bd046 | 09-13 eb1bcf7e | ref | C5 | V4-Pro | CEG | yes | ran (after repair, 627 chars) | INC (ctrl 1/3) | INC | – |
| d6f22b2a | 09-20 2fdef056 | ref | C5 | V4-Pro | CEG | yes | ran | SUPPORTED | **PG** | 1 cand CANDIDATE_FAILED + 3 duplicates |
| 52616f56 | 09-20 9e7f10cd | ref | C5 | V3.1 | PG | yes | ran | INC (ctrl 1/3) | INC | – |
| 53ba2834 | 09-20 9e7f10cd | ref | C5 | V3.1 | PG | yes | ran | INC (ctrl 2/3) | INC | – |
| dc1a11d2 | 09-20 9e7f10cd | ref | C5 | V3.1 | CEG | yes | ran | INC (trt 1/3) | INC | – |
| e0a68956 | 09-20 9e7f10cd | ref | C5 | V3.1 | PG | yes | ran | SUPPORTED | **PG** | none: campaign ended "Complete batch exceeds frozen dollar reservation" |
| 6cb0e8ab | 09-20 5a0af912 | ref | C5 | V3.1 | PG | yes | ran | SUPPORTED | **PG** | 1 cand CANDIDATE_FAILED + 3 duplicates |
| bdf0f68d | 09-29 7ee35abe | nat v1 | C5 | V4-Pro | CEG | yes | ran | INC (ctrl 1/3) | INC | – |
| eac3d243 | 09-29 7ee35abe | nat v1 | C5 | V4-Pro | INC | **no** | DECLINED (valid) | – | INC | – |
| a4c8395a | 09-29 a2fbffe3 | nat v1 | C5 | V4-Pro | CEG | yes | ran | SUPPORTED | **PG** | 2 cands; 1 PASSED SV → challenge COUNTEREXAMPLE |
| b4c25b59 | 09-29 a2fbffe3 | nat v1 | C5 | V4-Pro | CEG | yes | ran | INC (NO_FAULT treatment 1/3) | INC | – |
| da825066 | 09-29 a2fbffe3 | nat v1 | C5 | V4-Pro | CEG | yes | ran | INC (ctrl 1/3) | INC | – |
| 723354f7 | 09-29 b05ac280 | nat v2 | C4 | V4-Pro | CEG | **no** | DECLINED (valid) | – | INC | – |
| 57fa14bc | v2d | nat v2 | C3 | V4-Pro | CEG | yes | ran | SUPPORTED | **PG** | 1 cand PASSED SV → challenge INC, 0 failed checks |
| b0eeb89d | v2e | nat v2 | C3 | V4-Pro | CEG | **no** | DECLINED (valid) | – | INC | – |
| dddc1a1b | v2f | nat v2 | C3 | V4-Pro | CEG | yes | ran (after repair, 743 chars) | SUPPORTED | **PG** | 2 cands PASSED SV → 2 challenges INC, 0 failed checks |
| a0dd0c48 | v2g | nat v2 | C3 | V4-Pro | CEG | **yes** | **REJECTED: 614-char hypothesis, both tries** | – | INC | – |
| dc19567f | v2g | nat v2 | C4 | V4-Pro | CEG | yes | ran | SUPPORTED | **PG** | 1 cand SOURCE_FLAKY |

## 3. Rates

| group | n | CEG (final) | requested (raw) | declined | output rejected | intervention ran | SUPPORTED when ran | POLICY_GAP | candidate followed a PG |
|---|---|---|---|---|---|---|---|---|---|
| reference | 19 | 8/19 (42%) | 18/19 | 0/19 | 1/19 | 18/19 | 7/18 | 7/19 (37%) | 6/7 |
| native v1 | 5 | 4/5 | 4/5 | 1/5 | 0/5 | 4/5 | 1/4 | 1/5 | 1/1 |
| native v2 | 6 | 6/6 | 4/6 | 2/6 | 1/6 | 3/6 | 3/3 | 3/6 | 3/3 |
| all | 30 | 18/30 | 26/30 | 3/30 | 2/30 | 25/30 | 11/25 | 11/30 | 10/11 |
| Mechanic V3.1 (all reference) | 14 | 3/14 | 13/14 | 0/14 | 1/14 | 13/14 | 3/13 | 3/14 | 2/3 |
| Mechanic V4-Pro, reference | 5 | **5/5** | 5/5 | 0/5 | 0/5 | 5/5 | 4/5 | 4/5 | 4/4 |
| Mechanic V4-Pro, native | 11 | **10/11** | 8/11 | 3/11 | 1/11 | 7/11 | 4/7 | 4/11 | 4/4 |

Candidates that passed source validation:
- reference: 1 of 12;
- native v1: 1 of 2;
- native v2: 3 of 4.

Post-hoc two-sided Fisher tests. These are descriptive only: nothing was declared in advance, and the runs differ
in code version.
- CEG, V4-Pro vs V3.1 Mechanic: 15/16 vs 3/14, p = 0.00009.
- CEG within V4-Pro, reference vs native: 5/5 vs 10/11, p = 1.0.
- Declined, native vs reference: 3/11 vs 0/19, p = 0.04. Within V4-Pro only: 3/11 vs 0/5, p = 0.51.
- Citation-blaming hypothesis (analyst's reading), native v2 vs everyone else: 5/6 vs 1/24, p = 0.0002.
- POLICY_GAP verdict when the Mechanic said CEG vs when it said PG: 8/18 vs 3/10, p = 0.69.

## 4. Answers

**Is CONTRACT_EVIDENCE_GAP common for the reference agent too? Yes. It is not native-specific.**
- The reference agent drew CEG in 8 of 19 diagnoses (9 of 19 first attempts).
- CEG tracks the **Mechanic model**, not the agent:
  - the DeepSeek-V4-Pro Mechanic proposed CEG in 15 of 16 diagnoses: 5 of 5 for the reference agent, 10 of 11 for
    native agents;
  - the V3.1 Mechanic proposed CEG in 3 of 14.
- Every native diagnosis used the V4-Pro Mechanic, so "native agents get CEG" is confounded with "V4-Pro says CEG".
- The diagnosis prompt text has not changed since git commit f21b970 (2026-09-13 19:11 UTC).
- The label also does not decide the verdict. `classify_policy_gap` (referee/diagnostics.py:76-81) reads only the
  reproduction trials and the intervention result; the proposed kind is stored and nothing else
  (lab/diagnosis.py:149).
  - CEG proposals ended POLICY_GAP 8 of 18 times.
  - PG proposals ended POLICY_GAP 3 of 10 times.
- What *is* native-specific (native v2 specifically) is the hypothesis content. 5 of 6 native v2 hypotheses blame
  citations or labels. So do 1 of 19 reference and 0 of 5 native v1 hypotheses. Under V4-Pro, reference and native v1
  CEG hypotheses blame receipt timing instead. This is my manual reading of the 30 hypotheses (column
  `hypothesis_theme_analyst`).

**Is declining the intervention common? No: 3 of 30, all native, none for the reference agent.**
- eac3d243 (native v1): the decline was justified. In reduction, every one of its 4 options, including removing the
  fault, had already shown 1/3 target violations. The prompt calls that non-discriminating.
- 723354f7 (native v2, C4) and b0eeb89d (v2e): discriminating options existed and had been observed at 0/3 in
  reduction (for v2e, the only option). The Mechanic declined anyway, with a citation theory.
- A second route to "no intervention" is output that fails validation twice. This happened 2 of 30 times:
  - 93da89fe: the V3.1 Mechanic corrupted evidence ids;
  - a0dd0c48, v2g: a 614-character hypothesis against the 600 limit, repeated word for word in the format-repair turn.
- Overlong first attempts are a V4-Pro habit: 4 of 16, repaired 3 of 4.

**Correction to the v2g write-up.** `docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md:393` says "the Mechanic itself proposed
INCONCLUSIVE and requested no intervention". The store shows otherwise:
- In both tries the Mechanic proposed CONTRACT_EVIDENCE_GAP and requested intervention-828103e0598f48f8675994a5. That is
  remove_primitive:0, the only option, observed at 0/3 in reduction. The two tries are mechanic-ec2f80bf… (attempt 0) and
  mechanic-5bb12477… (attempt 1), request mechanic-request-e93fda59….
- Both tries failed `hypothesis: string_too_long`: 614 characters against `Text` max_length=600 (contracts/models.py:24
  and 369).
- So `Mechanic.diagnose` returned None (agents/mechanic.py:65-74), and diagnosis.py:149 recorded
  proposed_kind='INCONCLUSIVE'.

So across v2d–v2g, the dev-5 Mechanic *requested* the intervention 3 of 4 times. It declined once (v2e). The product
accepted 2 of 4. The diagnostic record cannot tell "declined" from "invalid output": it keeps no proposal ref when no
intervention ran. That is an observability gap.

**Did an INCONCLUSIVE diagnosis later turn out POLICY_GAP on another run of the same source? Yes, once, exactly.**
- The native v2 dev-5 replay (identical source recipe f0f2cb22… and retained recipe 193add68…) went:
  - v2d POLICY_GAP;
  - v2e INCONCLUSIVE (declined);
  - v2f POLICY_GAP;
  - v2g INCONCLUSIVE (rejected output).
- The only other exact repeats are both reference:
  - source 27db91e9… (F2 delay 5, seed 42): INCONCLUSIVE 3 of 3;
  - source beebb28a…: POLICY_GAP 2 of 2.
- At the looser level of "same fault shape, different seed", INCONCLUSIVE and POLICY_GAP mix freely for the reference
  agent:
  - F2 delay-5: 5 PG of 10;
  - delay-4: 2 of 7;
  - delay-3: 0 of 2.

**Where the binding step sits differs by agent.**
- Reference and native v1 (C5 slow-upgrade sources): the Mechanic nearly always requested an intervention (22 of 24).
  What failed was the fresh intervention itself:
  - 9 of 14 INCONCLUSIVE interventions had a control that did not reproduce 3/3;
  - 5 of 14 had a treatment that still violated, once with no fault at all (b4c25b59, native v1).
- Native v2 (dev-5 C3, dev-6 C4): every intervention that ran was SUPPORTED (3 of 3). All 3 misses came from the
  Mechanic's output: 2 declines and 1 over-length rejection. This agrees with the doc's "diagnosis Mechanic is the
  binding step" for native v2 only.

## 5. What I could not determine

- The exact prompt and context the V3.1-Mechanic campaigns of 2026-09-13 16:16–17:51 UTC saw. They predate the
  f21b970 commit, and the stores do not hash the prompt.
- Reference-era intervention option ids cannot be recomputed with today's code (the hash inputs changed). For those rows
  I used the fact that the intervention ran as proof that the id was accepted. The recomputation check is valid only
  for the native rows.
- Hypothesis themes are one analyst's manual reading, not a product classification.
- Whether the V4-Pro vs V3.1 difference is the model itself or other changes made alongside it. Runtime contract text,
  evidence summaries and the native adapter's V2_MEMORY text all differ between eras.
- Old-era source-validation outcomes were recomputed from evaluation trials (incumbent 3/3 and candidate 0 failures =
  passed), because `source_validation_results` records did not exist then.
