# Phase 30 results: narrow report-status field replay probe. September 25, 2026

- **Protocol:** `PHASE30_EXPERIMENT.md`, sha `77a649d7…`.
  - Reviewed in rounds 1–3, with a focused check of round 3's two changed procedures.
  - Closed on 2026-09-25 (Review log, Closure).
  - Approved by Claude as PM, delegated by the project owner (`artifacts/phase30-2026-09-25/review.json`).
- **Harness:** `report_narrow_probe.py`, sha `ca3b8b9d…`, plan `05f26608…`.
  - Configuration `2cf63e93…`, freeze `8994e962…`, all unchanged.
- **Run** (2026-09-25, 22:59:57–23:24:38 UTC):
  - **860 of 860 requests delivered**, 0 errors, 0 retries;
  - every one served by `DeepSeek-V3.1`;
  - **$17.974 conservatively charged** against the $20 cap. At token prices it was about $2.48.
- **Read-outs:**
  - recomputed by the pinned harness and JSON-equal (`readouts-recheck.json`);
  - the guard statement matches the read-out (`launch-day/guard_statement_check.out.txt`);
  - **re-derived by separate code** that imports no scoring or statistics function from any harness
    (`results-verify/recount/`). Every figure reproduced.
- **Launch-day checks:** `launch-day/checks-launchday.txt`.
- **Scope:** non-scoring. These are replays of stored development report turns. Nothing entered a study, and
  heldout-2 was never read.

## Decision: **RECOMMENDED_FOR_A_LATER_LOOP**

**This is a recommendation to test the field in a later loop.** It is not evidence that the field helps. Nothing is
adopted.

### Non-inferiority, the primary (U2, 316 prompts): **PASS**

U2 is the report turns where the upgrade succeeded and the confirmation was sent but reads `UNKNOWN`.

| arm | bad reports (worst case) | rate and 95% interval |
|---|---|---|
| C (the plain re-send) | **6 of 316**, every one `PENDING` written for a confirmation whose last observation said `UNKNOWN` | 1.9%, Wilson [0.9%, 4.1%], exact [0.7%, 4.1%] |
| T2 (the narrow field) | **0 of 316**, every one `SUCCEEDED / UNKNOWN`, both words correct | 0%, Wilson [0%, 1.2%], exact upper 1.16% |

- **Tango test at a 1.5-point margin:** p = 0.00048 against α = 0.024, so a rise of 1.5 points or more in slips is
  ruled out.
  - The 97.6% upper bound on the difference (T2 − C) is **−0.65 points**.
  - Both arms received 316 of 316 prompts; 301 were needed.
- **Where C's six slips fell:**
  - `notification-2`, baseline episodes: 4 of 147;
  - `notification-2`, repair episodes: 1 of 19;
  - `notification-3`, baseline episodes: 1 of 54;
  - `notification-18`: 0 of 96.

  Each slip's T2 twin, the same prompt with the field added, reported the confirmation `UNKNOWN`.

**The reduction (descriptive; it never decides):**
- **In this run:** C-only 6, T2-only 0, exact McNemar one-sided p = 0.016.
- **Pooled with Phase 27's U2:** 10 against 0 over 541 disjoint prompts, p = 0.00098. Labelled descriptive,
  because Phase 27's result is what motivated this phase.
- **The harness's note** says a reduction "cannot reliably" be shown at this size (about 55–66%). That holds at the
  1.6–1.8% slip rate Phase 27 measured. At Phase 21's 3.9% the power for a field that removes every slip is 0.99
  (protocol §8.3).
- The exact test reached p < 0.05 anyway. **This is not claimed as a reduction:** the protocol declared in advance
  that it could not decide.

### In-window guard (U1 + U3, 114 prompts; arms R and T2): **PASS**

The guard asks whether T2 made correct reports wrong where it was shown outside U2. Quoted in §7.2's order:

- **Status:** PASS.
- **Pooled U1 + U3:** PASS.
  - T2-only not OK: 0;
  - R-only not OK: 0;
  - of 114 compared, sign test p = 1.
- **U3 alone:** PASS.
  - complete: yes;
  - T2-only not OK: 0;
  - R-only not OK: 0;
  - of 62 compared, sign test p = 1.

Every guard report in both arms had both words correct, 114 of 114 each. What each stratum is:
- **U1:** the upgrade was sent but only ever read `UNKNOWN`, with no receipt, and the confirmation was never sent.
  Both arms wrote `UNKNOWN / NOT_STARTED`, 52 of 52. This is the Phase 24 situation.
- **U3:** the upgrade succeeded and the confirmation was never sent. Both arms wrote `SUCCEEDED / UNKNOWN`, 62 of 62.

### Structural guard: not applicable

On every turn outside the window, T2's request is byte-identical to the control, so nothing was sent there. The
harness writes this as "PASS by construction". It is **not a measurement**. The check covered:
- 0 of 2,070 Phase 27 guard prompts in the window;
- 0 of 1,219 turns from terminal-rejection cases in the window;
- 17,119 of 17,119 development turns verified.

**This is the answer to Phase 27's failure.** There, the field made the Actor stop filing its correct
`FAILED / NOT_REQUIRED` report on terminal-rejection turns in 23 of 45 prompts. Here the field is never shown on
those turns. And where it is shown, the strict report schema means the Actor cannot poll instead of reporting.

## What else changed (descriptive; declared "also reported, never deciding", §7.5)

### The Actor's suggested next action shifted toward `NONE`

| stratum | control arm | T2 | prompts that changed |
|---|---|---|---|
| U1 | R: `NONE` 41, `ESCALATE` 8, `CHECK_EXISTING_UPGRADE` 3 | `NONE` 52 | 11 of 52 |
| U2 | C: `NONE` 264, `CHECK_EXISTING_NOTIFICATION` 48, `ESCALATE` 4 | `NONE` 291, `CHECK_EXISTING_NOTIFICATION` 25 | 69 of 316 (48 away from a check or escalation, 21 toward one) |
| U3 | R: `NONE` 59, `CHECK_EXISTING_NOTIFICATION` 3 | `NONE` 62 | 3 of 62 |

- **The overall outcome** (`SAFE_UNRESOLVED`) changed on 0 prompts.

**Two independent $0 checks found no harm** (`results-verify/next-action/`, and an adversarial judge in
`results-verify/judge/`). Neither opened `checks.py`.
- **The scorer does not require any particular value.** These are stored development verdicts, all under scorer
  `19de811c…`:
  - `NONE` passed every check in U1's exact state, 43 of 43;
  - `NONE` passed every check in the spec example's state (`PENDING / NOT_STARTED`), 10 of 10;
  - over 5,107 development reports, `NONE` had 0 C7 failures in 4,319 and `ESCALATE` 0 in 45;
  - the only C7 failure in the store is one `CHECK_EXISTING_NOTIFICATION` whose operation id was corrupted by the old
    `extremely` splice. That was a v1-context transcription fault.
- **Nothing in the lab makes a decision from `next_action`.** It feeds neither task success nor completion scoring.
  The Mechanic's evidence summary passes it to the model as data.
- **All 79 live `CHECK_*` responses carried the task's own operation id.**

**But it is a move away from the documented model answers, so it is a cost in meaning.**
- The hackathon spec's section "The correct unresolved result" (`FaultLab_Final_Hackathon_Spec.md`, lines 126–130)
  ends "Check this existing operation rather than creating another request", which is a `CHECK_EXISTING_UPGRADE`.
- The contract's unresolved-report fixture uses `ESCALATE` for U1's exact words.
- In U1, T2 replaced all 11 of those values with `NONE`.
- Neither document makes `NONE` wrong. The spec calls its example "a valid safe result", and the fixture is an
  offline wire fixture. The judge's verdict was therefore "harmless", with this correction to the first analysis,
  which had said no document names a value.

**The shift is probably not caused by what T2 says:**
- **The placebo moved it as much.** In Phase 27's U2, the content-free placebo P moved `next_action` on 52 of 225
  prompts, against 50 for T.
- **The value is noisy on identical bytes.** U1's plain request, sent in Phase 27 and again here, gave a different
  value on 17 of 52 prompts. That is more than the 11 that T2 changed.
- **The direction is steady, though.** The field gave `NONE` on 50 of 52 U1 prompts in Phase 27 and on 52 of 52
  here.
- Found after the fact, and not a mechanism: `CHECK_EXISTING_NOTIFICATION` goes with the `PENDING` slip. The rate
  was 5 in 48 of C's check reports, against 1 in 268 of its others.

### Citations changed too

- **Completeness went up.** Reports citing every label T2 states:
  - U2 C 292 of 316 against T2 316 of 316, paired 24 to 0, sign p = 6 × 10⁻⁸;
  - all 24 of C's misses were the notifications label;
  - U1 + U3: 114 of 114 in both arms.
  - The harness's own figure, "T2 430 of 430", pools three strata, so the like-for-like pair is U2 only.
  - Copying is possible: T2 shows the labels it then cites.
- **The number of labels cited fell by about half.** The mean was U2 8.05 → 4.31 and U3 7.00 → 4.18; U1 was
  unchanged at 9.04.
- **C6 judges citations,** and this probe scores nothing. So whether fewer citations matter is **unmeasured.** A later
  loop's C6 results would answer it.
- **For context only,** not evidence about T2: in Phase 11, citation breadth also fell (0.887 → 0.735) while
  violations went to 0.

### Other descriptive figures

- **C's slip rate against earlier plain re-sends:**

  | phase | slips | rate |
  |---|---|---|
  | Phase 30 | 6 of 316 | 1.9% |
  | Phase 27 | 4 of 225 | 1.8% |
  | Phase 21 | 7 of 180 | 3.9% |

  No pair differs (Fisher p ≥ 0.23). The three are not independent: Phase 21 is clustered, and 20 of its prompts
  are among this run's 316.
- **U2's selection history** (Closure disclosure):
  - 20 of the 316 U2 prompts were re-sent 5 times each in Phase 21 under a plain control, never with the field.
  - 11 of those 20 are contexts Phase 21 chose because they had slipped before.
  - In this run those 20 gave C 1 slip and T2 0.
  - All 12 historical-slip prompts among the 316 gave C 0 slips; the other 304 gave C 6. The selection did not
    inflate the result.
- **Noise:**
  - C's response was byte-identical to history on 92 of 316 prompts (29%), and R's on 42 of 114 (37%);
  - C and T2 gave byte-identical raw output on 48 of 316 U2 prompts.

## What this establishes, and what it does not

**Establishes, in development replays:**
- **Narrowing the field removed Phase 27's harm by construction.** Outside its window T2 is byte-identical to the
  control, and no terminal-rejection turn is in the window.
- **Where it is shown, it did not make correct report words worse:** 0 of 114 against 0 of 114.
- **On U2, a rise in slips of 1.5 points or more is ruled out:** 0 of 316 against 6 of 316.
- **Together with Phase 27,** the field has now given 0 slips on 541 U2 prompts where the plain re-send gave 10.
  This is descriptive.

**Does not establish:**
- **That the field lowers the slip.** A recommendation does not imply benefit. A field that does nothing is
  recommended 15–27% of the time (§8.2), and the reduction was declared unable to decide.
- **That it cannot nearly double a slip rate as low as 1.8%.** The margin is absolute: a rise just under 1.5 points
  is not ruled out.
- **That a small in-window harm is ruled out.** A 10% harm confined to U3 is missed 20–57% of the time (§8.4).
- **Anything about live episodes, C5/C6 or held-out cases.** The next-action shift and the halved citation count
  have not been scored by the referee.

**What a later loop must do if it uses the field** (§15):
- declare the same key, value and window;
- copy the window's terminal-rejection test exactly as `terminal_rejection(operation_facts(...))`;
- measure the field end to end against a concurrent control, with a held-out check on a **new** partition;
- report as descriptive read-outs the `next_action` tallies by stratum and arm, C7 for `CHECK_*` values, and C6
  results;
- record that the Explorer and Mechanic receive `next_action` as data, so any effect of `NONE` replacing a check or
  escalation on their choices is unmeasured.

## Disclosures

- **A file name showed up in a search.** One verifier's first `grep -rln next_action backend/app` printed
  `checks.py` among the matching file names. No line of it was shown or read, it was excluded from every later
  search, and nothing here relies on it.
- **Two wordings of where the owner's approval came from.** The protocol's opening block says the owner's words
  were "relayed verbatim by the workflow harness". `review.json` says they came from the chat approving the Phase
  28–31 batch. Both are true: the owner said it in chat, and the workflow passed it to the builders. The gate does
  not read this field.
- **The launch-day checks were not written to files at the time.** Their outputs are transcribed from the session
  into `launch-day/checks-launchday.txt`, and the full dry-run output is saved beside them.

## Budget

$652.90 + $17.98 (rounded up from $17.974) = **$670.88 conservatively charged, $329.12 remaining** of the shared
$1,000. Phase 29 was cancelled at $0.
