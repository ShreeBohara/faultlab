# Diagnosis probe 1: result (2026-09-30, request-only, pre-registered)

- **Declaration:** `DECLARATION.json` (sha `2be35bf2…`). Harness `b1eb7cda…`, plan `91ca47e4…`.
- **Calls:** 140 answers delivered, 0 failed, 142 charged (2 transport retries). The model was DeepSeek-V4-Pro-0813 at
  the product's frozen temperature 0.
- **Cost:** **$7.08 conservative** ($7.07728 bound); about **$1.89** at token prices. Ledger: $930.61.
- **Repeats:** 0 of 14 request keys gave a single distinct answer, so the 10 samples per key are real variation.
- **Person marks:** three independent Claude markers, blind to arm and to checker output, applied the frozen rubric
  (`RUBRIC.json`, sha `0fbe2556…`) to all 100 first-turn rows. The majority vote is recorded; there were no ties.
  - Unanimity was 96/100 for citation blame, 100/100 for C3 and 98/100 for C5.
  - The markers are not human. The owner may re-mark `review-marked.csv`.

## Pre-registered outcomes

| | CONTROL | GUIDE | status |
|---|---|---|---|
| **P1** citation-blaming dev-5 hypotheses | confirmed (checker match and person Y): **13/40**; person Y without checker match: 15 | **0/40**; person Y without match: 0 | **UNINFORMATIVE** (the premise needed CONTROL confirmed ≥ 20/40) |
| **P2** dev-5 first-attempt validity / over 600 characters | 29/40 valid, 11 over | **40/40 valid, 0 over** | **PASS** |
| **P3** (no bar) valid requested; names C3; names C5 inconsistency | 17/40; 8/40; 5/40 | **40/40; 40/40; 22/40** | one-sided Fisher p: 1.3e-9; 3.5e-15; 5.4e-5 |
| **P3** dev-6 names C4 / blames o3 | 2/10 / 4/10 | **10/10 / 0/10** | p = 0.00036 for naming C4 |
| **P4** repair valid within 600 with the Rule 1 message | v2f 10/10, v2g **6/10** (today's message: 7/10 and 9/10) | | **FAIL** on its own bar; totals equal (16/20 vs 16/20), so "not worse" |

## Decision under the declared rule

- **Rule 1 ships.** P4 does not show the Rule 1 message is worse.
  - Its record part is certain value on its own.
  - Its repair message did not help on balance: better for v2f, worse for v2g.
- **Rule 2 does not ship on this probe.** P1 is UNINFORMATIVE, not PASS.
  - The cause is the instrument. The checker's phrase list confirmed only 13 of the 28 CONTROL hypotheses that all
    three blind markers flagged as blaming citations.
  - So the premise (at least 20 confirmed) failed even though the markers found the pattern in 28 of 40.
  - The other measures favour GUIDE strongly, but they are secondary or have no pass bar, so they do not override the
    rule.

## Next

A second, separately declared probe tests Rule 2 again on **new** samples. Its primary measure (P1b) uses the blind
person-majority marks in both arms, defined before any new data. No result of probe 1 is re-scored or re-labelled.
