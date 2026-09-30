# Diagnosis probe 2: result (2026-09-30). **INCOMPLETE, no decision**

- **Declaration:** `DECLARATION.json` (sha `bd5688c2…`). Harness `b1eb7cda…`, plan `91ca47e4…`. Declared primary P1b:
  `probe2_score.declared.py` (sha `470fedf7…`).
- **Why it is incomplete:**
  - From **22:38:46 UTC every provider call returned HTTP 402 "Payment Required"** (W&B Inference).
  - Rounds 0–5 were delivered; rounds 6–9 failed.
  - 88 of 140 answers were delivered and 52 failed (48 with 402 only; the rest with connection errors followed by
    402).
- **Cost:** **$7.38 conservative** (148 charged calls, including the failed ones) and about **$1.19** at token prices.
  Ledger: **$937.99**.
- **Marking:** the same three blind Claude markers applied the same frozen rubric to the 64 delivered first-turn rows.
  There were no ties.
- **Scorer bug, disclosed:** the declared scorer crashed on undelivered rows (no marks). The fix only skips rows that
  have no marks, and the rule is unchanged (`probe2_score.py`, diff against `probe2_score.declared.py`).

| | CONTROL | GUIDE | status |
|---|---|---|---|
| **P1b** (declared primary) dev-5 rows the markers flagged as blaming citations | **21/27** delivered | **0/25** delivered | **not evaluable**: the rule is stated "of 40" and only 27 and 25 were delivered |
| harness P1 (checker-confirmed) | 11/27 (+10 marker-only) | 0/25 | INCOMPLETE |
| P2 validity / over 600 characters | 21/27 valid, 6 over | **25/25 valid, 0 over** | INCOMPLETE |
| P3 valid requested / names C3 / names C5 | 16/27 / 7/27 / 1/27 | **25/25 / 25/25 / 10/25** | descriptive |
| P3 dev-6 names C4 | 1/6 | **6/6** | descriptive |
| P4 repair valid within 600 characters | Rule 1: v2f 5/6, v2g 3/6; today: 4/6, 4/6 | | INCOMPLETE |

**Reading:**
- Probe 2 gives no decision, so Rule 2 stays **not offered**.
- Descriptively it agrees with probe 1 in every measure. Across both probes, the markers flagged citation blame in
  **49 of 67** CONTROL dev-5 answers and **0 of 65** GUIDE answers.
- The next step, once the provider account accepts calls again, is a fresh declared probe (or the missing rounds)
  under the same P1b rule.
