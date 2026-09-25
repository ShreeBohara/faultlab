# Phase 27 results: Actor report-word replay probe. September 25, 2026

- **Protocol:** `PHASE27_EXPERIMENT.md`. Reviewed in rounds 1–3, with the round-3 fix checked.
  The owner's answer to §17 question 1 was option R. Approved by Claude as PM, delegated by the
  project owner (`artifacts/phase27-2026-09-24/review.json`).
- **Harness:** `report_word_probe.py`, sha `f057ef2a…`, plan `cd3b7bc8…`.
- **Run:**
  - **1,064 of 1,064 requests delivered**, 0 missing;
  - all served by `DeepSeek-V3.1`;
  - **$22.24 conservatively charged** against the $25 cap.
- **Read-outs:** recomputed by the pinned harness, and equal.
- **Scope:** non-scoring. These are replays of stored development report turns. Nothing
  entered a study.

## Decision: **NOT_RECOMMENDED**

The runner's statement:

> the plain re-send gave only 4 unsupported reports in 225 prompts (fewer than 5); no exact test at this size can show a reduction, so this probe cannot tell whether the field helps; guard FAIL (pooled FAIL, terminal rejection FAIL: outcome test FAIL, word test INCOMPLETE on 17 prompts reported by R and T, floor 20)

**Primary: FLOOR_LIMITED.** These are the report turns where the upgrade succeeded and the
confirmation's latest status is `UNKNOWN`, 225 prompts per arm:

| arm | unsupported report word (`PENDING` where the evidence says `UNKNOWN`) |
|---|---|
| C (the plain re-send) | **4 of 225 (1.8%)** [0.7%, 4.5%] |
| T (a field stating each operation's last observed status) | **0 of 225** [0%, 1.7%] |
| P (placebo) | 3 of 225 (1.3%) |

- **The direction favours T,** but with 4 baseline events no exact test can show a reduction
  (McNemar against C, p = 0.0625).
- **The slip is rarer here than Phase 21 suggested:** 1.8% on these turns under C.

**Guard: FAIL.** T changed what the Actor does in other contexts:
- **Terminal-rejection turns** (the upgrade FAILED): T changed the Actor's action in **28 of
  45** prompts, against 6 for the re-send reference R. That is an excess of 49 points against a
  tolerance of 10, p ≈ 1 × 10⁻⁵.
  - In **23 of those 45**, the Actor **stopped filing its correct `FAILED / NOT_REQUIRED`
    report** and polled the order's status again instead.
- **Pooled over every guard context:** T changed 30 of 95 actions, against R's 7.
- **Wording:** where T did report, its words were correct (68 of 68 match/match). The harm is
  **delay**: fewer reports, more polling. It is not wrong words.
- **The same kind of regression as Phase 4:** a context field meant to fix one report
  disturbed correct refusal handling. The guard caught it.

## What this establishes, and what it does not

**Establishes:**
- **Where Phase 24's HARM came from:** on the report turns where it happened, the `PENDING`
  slip happens about 2% of the time (4 of 225).
- **The field removes the slip there,** 0 of 225. But it **does not pass the guard.** On
  terminal-rejection turns it makes the Actor put off its correct report in about half the
  prompts. So it is not adopted.

**Does not establish:**
- That the field helps, which is floor-limited.
- That a narrower field would not work: for example, one shown only when an operation is
  `UNKNOWN`, never on terminal rejections. That would need its own declaration and review.

## Budget

$630.66 + $22.24 = **$652.90 conservatively charged, $347.10 remaining** of the shared $1,000.
