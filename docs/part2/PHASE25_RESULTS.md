# Phase 25 results: Mechanic slot-2 replay probe. September 25, 2026

- **Protocol:** `PHASE25_EXPERIMENT.md`. Reviewed in rounds 1–3, with the round-3 fixes checked.
  Approved by Claude as PM, delegated by the project owner (`artifacts/phase25-2026-09-24/review.json`).
- **Harness:** `slot2_probe.py`, sha `28b998ac…`, plan `5db5c880…`.
- **Run:**
  - **260 of 260 requests delivered**, 0 missing, 0 retries;
  - all served by `DeepSeek-V4-Pro-0813`;
  - **$12.96 conservatively charged** against the $15 cap.
- **Read-outs:** recomputed by the pinned harness, and identical.
- **Scope:** non-scoring. These are replays of 26 stored slot-2 Mechanic requests from Phases
  17 and 23. Nothing entered a study.
- **Launch conditions:** AC power; automatic macOS updates off; no other paid run.

## Declared outcome: **no arm recommended; the copying mechanism NOT_SHOWN**

The runner's statement:

> no arm is recommended: T NOT_RECOMMENDED (distinct_at_least_0.70, working_share_gain_at_least_3.33, invalid_at_most_C_plus_0.10); H NOT_RECOMMENDED (distinct_at_least_0.70, distinct_gain_at_least_0.30, sign_test_p_below_0.05, working_share_gain_at_least_3.33)

**The arms** (78 draws each for C, T and H; N is 26 single draws):

| arm | what changed | distinct proposals | duplicates of slot 1 | invalid | working repairs (step present and fires) |
|---|---|---|---|---|---|
| **C** | nothing (the exact slot-2 request) | 20 (26%) | 57 (73%); 51 have rules identical to slot 1 | 0 | **0** |
| **T** | temperature raised | **49 (63%)** | 12 (15%) | **9 (11.5%)** | **6** |
| **H** | the prior candidate shown differently | 14 (18%) | 63 (81%) | 1 | 0 |
| **N** (reference; decides nothing) | no prior candidate in view | 25 of 26 | **0 of 26** | 1 | 1 |

**What each decision rests on:**
- **T: NOT_RECOMMENDED.**
  - **Beat C clearly:** distinct 63% against 26% (sign test p = 0.0013), and working 6 of 78
    against 0.
  - **Missed three declared bars:**
    - distinct ≥ 70% (it reached 63%);
    - a working-share gain of at least 10/3 (it reached 2/3);
    - invalid at most C + 10 points (it had 11.5%, against C's 0%).
  - **Also noted:** 4 of its distinct policies were flagged harmful.
- **H: NOT_RECOMMENDED.** Changing how the prior candidate appears did not reduce copying (81%
  against 73%).
- **Mechanism: NOT_SHOWN.** The declared test (C against H) found no drop in duplicates. So the
  planning review's claim, that the duplicates come from the prior candidate's presentation in
  `candidate_history`, is not supported.

## Descriptive (decides nothing)

- **The copying is semantic, not byte-level.** C's duplicates repeat slot 1's **rules** (51 of 78)
  but are rarely byte-identical (3 of 78).
- **With no prior candidate in view (N), the Mechanic never rewrote slot 1's policy:** 0 of 26
  (upper 95% bound 12.9%). With the prior candidate in view (C and H), it did so 73–81% of the
  time.
  - This points to **the prior candidate being in view at all** as what drives the copying,
    not how it is shown.
  - N is a descriptive reference with one draw per prompt, so this is a lead, not a finding.
- **Temperature trades validity for diversity.** More varied proposals, and more working ones
  (6 against 0), but also more invalid ones (9 against 0) and some harmful ones.

## What this establishes, and what it does not

**Establishes:**
- Neither declared change meets its declared bar.
- Raising the temperature makes slot 2 far more varied and yields some working repairs (6 of 78,
  against 0 of 78 for the unchanged request), at a measured cost in invalid output.
- Re-presenting the prior candidate does nothing.

**Does not establish:**
- **That removing the prior candidate from slot 2's view would help.** N is descriptive, and
  with one draw per prompt its working rate is 1 of 26.
- **Any end-to-end effect** on how often the loop certifies a repair.

**Next, if pursued:** a declared arm that hides the prior candidate entirely (N as a proper arm,
several draws per prompt), perhaps combined with a moderate temperature. Its own declaration
and review come first.

## Budget

$600.65 + $12.96 = **$613.61 conservatively charged, $386.39 remaining** of the shared $1,000.
