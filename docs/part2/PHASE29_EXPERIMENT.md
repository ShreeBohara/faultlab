# Phase 29 protocol — Mechanic slot 2 with the prior candidate hidden (replay, non-scoring)

**Status: NOT yet reviewed. Declared before any paid call; no provider call has been made for this phase.**
Built on 2026-09-25 under the Phases 28–31 program (`EXPERIMENT_PROGRAM_PHASES_28-31.md`, which the owner
approved in direction: "go ahead with whatever u recommend"). That program-level approval is **not** the owner's
answer to §18 question 1, and the harness refuses it as one (§11). **Review rounds 1 and 2 have run** (round 1:
statistics and run safety, 12 findings; round 2, on the round-1 changes: 2 major and 3 minor findings), and every
finding of both rounds is applied (Review log). The review is **not closed**: a round 3 on the round-2 changes is
recommended (the round-2 reviewer asked for one on its finding 2), the owner has not answered §18 question 1, and no
review record exists. The harness refuses to send anything until this status block no longer carries the
review-pending phrase, this file carries the bare "Reviewed for launch" line with both pins, the Review log's closing
entry carries the owner's own answer on its dedicated line, and `artifacts/phase29-2026-09-25/review.json` repeats the
pins with this file's sha256 and the phase cap, says it is approved, names the approver and holds the same answer
(§11, §12 step 3). No paid, model or W&B call has been made, and nothing under `backend/app` was edited. Every number
below comes from a $0 dry run or a saved $0 computation.

Pins of this draft, after the round-2 changes (the live gate requires both strings in this file): harness
b162a7da92bcbae0fdb67b7fbf143c3251c4d4404a83d57492635a982e493a90 plan
2b4bc80ca217bcc5f15e1ccf269d2f9f72a6ab417292f3835193e90095cd4466

- **Program:** `docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md`, Phase 29 (cap about $15).
- **Harness:** `scripts/experiments/slot2_hidden_probe.py`. **Tests:**
  `backend/tests/experiments/test_slot2_hidden_probe.py`.
- **Imported, never edited:** Phase 25's `scripts/experiments/slot2_probe.py` (sha `28b998ac…`).

## 1. The question, and why it is asked

A completion study asks the Mechanic for a policy twice. In most studies slot 2 returns slot 1's policy, so a
study gets one real draw, not two (pitfall 70; Phase 23: slot 2 repeated slot 1 in 16 of the 21 studies that
reached it).

**Why this hypothesis exists.** Phase 25 re-sent the 26 stored slot-2 requests of Phases 17 and 23. Its
descriptive reference arm N, the slot-2 request with `candidate_history = []`, never wrote slot 1's policy: **0 of
26**, one draw per prompt, against 57 of 78 duplicates for the unchanged request (C). Its declared arms missed their
bars (`PHASE25_RESULTS.md`). N was a reference, not a test: it decided nothing, it had one draw per prompt, and
its working rate was 1 of 26.

**No double-dipping.** Phase 25's N draws suggested this phase; they are **not evidence** in it:
- no Phase 25 draw is pooled with, compared against or counted in any declared read-out of this phase;
- Phase 25's C and N **requests** (their hashes, not their outputs) are read only to check that this phase sends
  exactly the same requests (§6);
- Phase 25's N **outputs** are read for one descriptive figure: how many Phase 29 hidden-arm draws re-draw
  the policy Phase 25's N wrote for the same prompt (`phase25_dependence`, §8.5). It decides nothing. It says how
  far this phase re-measures the draws that suggested it, and a fixed wording rule (§8.5) turns it into what the
  results must say;
- Phase 25's figures are used below as **planning inputs** (the expected rates in §9 and the reason for the
  temperature in §6), and every such use is labelled. Since review round 1 two more are computed by the harness
  from Phase 25's pinned run (`phase25_planning_inputs`, printed in the dry summary only, never in the hashed plan
  or any read-out): the policy concentration of Phase 25's arms (§5; counted against the plan's already-proposed set
  since review round 2) and its determinism figures, the basis of the predicted dependence (§9.3).

**The question.** As declared arms with repeats, against a concurrent control:
1. **Duplicates cut:** does hiding the prior candidate from slot 2 move its proposals off slot 1's policy,
   reliably across prompts, **without raising invalid output**?
2. **Yield gain:** does it raise the share of **WORKING** proposals (distinct from slot 1, the retry step present
   and able to fire after a transient failure, no declared harmful side rule), **without a harmful excess**?

A second treated arm hides the prior candidate **and** uses a moderate temperature (NT).

This is a **replay probe**. It re-sends stored development Mechanic requests and reads the policies that come
back. It runs no episode, scores nothing, and creates no campaign, study, trial, world, policy or store row. A
positive result is a recommendation for a later loop's own declaration only (§13, §16).

**Where this protocol departs from, or makes exact, the program.**
- **WORKING is stricter** than the program's gloss ("step present and can fire"): it also requires no declared
  harmful side rule (§7). Distinct firing draws, harmful or not, are reported beside it.
- **"Without raising invalid output" is made exact** as two conditions: Phase 25's 10-point margin, and a new
  exact sign test that refuses a raise shown across prompts even below the margin (§8.2).
- **A harm guard is added** that the program does not name (§8.4), because a firing repair with a premature
  defer loses terminal rejection in validation (pitfall 78).
- **"A moderate temperature" is made exact** as 0.4, declared before any data (§6).
- **The two questions are declared as separate part-verdicts** (`duplicates_cut`, `yield_gain`) beside the
  overall decision, so a partial answer is reported as declared, not framed afterwards (§8.5).
- **The ~$15 cap is a hard phase cap**, across every run of this phase that delivered nothing (§10).

## 2. What is fixed

**Setup.**
- Mechanic model `deepseek-ai/DeepSeek-V4-Pro-0813`, called directly through the runtime's own `RuntimeProvider`
  (W&B Inference), with no Weave tracing.
- Frozen request settings: temperature 0 as built by the runtime (the arm's temperature is applied afterwards by
  Phase 25's `RequestSender`, §10), 2,000 output tokens, `response_format` `json_object`, thinking disabled,
  20 s timeout, no provider retry.
- The Phase 17 settings file on the Phase 22 code. **No file under `backend/app` changes.**
- Development data only. heldout-2 is spent and is never read, listed or used. No held-out partition or seed,
  promotion record or final-audit file is read.
- **`checks.py` is never read by a person or an agent.** As in every configuration recompute since Phase 13, the
  fingerprint code hashes the `backend/app` tree, which includes it as a source file.
- No result is shown to any model, enters any study, or tunes anything.

**Pins.**

| item | value |
|---|---|
| harness `scripts/experiments/slot2_hidden_probe.py` sha256 (after round 2) | `b162a7da92bcbae0fdb67b7fbf143c3251c4d4404a83d57492635a982e493a90` |
| plan hash (`content_hash(plan)`, after round 2) | `2b4bc80ca217bcc5f15e1ccf269d2f9f72a6ab417292f3835193e90095cd4466` |
| `artifacts/phase29-2026-09-25/dry-plan-r2/plan.json` sha256 | `f37a3c65375826e1bcdae96da78a291abed07e073c4a44f3debdfc8aea6f469a` |
| after round 1 (superseded, kept as evidence) | harness `b4153f91…`, plan `5b5ef67d…`, `dry-plan-r1/plan.json` `3dcb7c1a…`, `protocol-numbers-r1/…out.json` `18cdcd29…`, tests `56b46038…` |
| before round 1 (superseded, kept as evidence) | harness `d42ae0a4…`, plan `91d4b8e0…`, `dry-plan/plan.json` `e55c3664…`, `protocol-numbers/…out.json` `972895c0…` |
| Phase 25 harness `scripts/experiments/slot2_probe.py` (imported, never edited) sha256 | `28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0` |
| `configuration_hash` (Phase 17 settings on the Phase 22 code), recomputed with `.env` unread | `2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba` |
| settings `artifacts/phase16-2026-09-22/settings-phase17.json` sha256 | `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| Phase 22 freeze `artifacts/phase22-2026-09-24/gate-freeze-after.json` sha256 | `8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1` |
| Phase 25 live plan `artifacts/phase25-2026-09-24/live/plan.json` sha256 | `ce5cb3ffb6823c1f1eb201de6a998ae462c9c3a414cd11401ad26f064fab186d` |
| Phase 25 live responses `artifacts/phase25-2026-09-24/live/responses.jsonl` sha256 | `2e3b9235507118d77378b0f697eacb6d3fb22d77588da7969a8c5f6f86020af9` |
| census run manifests (pinned inside the Phase 25 harness) | Phase 17 `f9060540…`, Phase 23 `aac41711…` |
| store cutoff (Phase 25's) | `2026-09-24T05:50:00Z` |
| per-request dollar bound | $0.04984 (32,000 input × $1.31/M + 2,000 output × $3.96/M; frozen Mechanic pricing) |
| protocol-numbers output `artifacts/phase29-2026-09-25/protocol-numbers-r2/protocol_numbers.out.json` sha256 | `47696e6641d257d052e783cae62262fdf7d835a55f7d8c6e4c40b2bcc6df247d` (not pinned by the harness; the test checks it records the current harness sha256) |
| test file `backend/tests/experiments/test_slot2_hidden_probe.py` sha256 (after round 2) | `c46c8dc0295e73755dadafb294da184d10dfc7f0a48cbe03343dd2ec1e7b71f8` (not pinned by the harness) |
| this document | its sha256 is typed by the operator (`--expect-protocol-sha256`) and repeated in the review record; the harness never pins it |

- **The Phase 25 harness is imported, not copied.** It is loaded unchanged under a private module name. Since
  review round 1 its bytes are read once and hashed **before any of them run**, and the import system then runs
  exactly those bytes (a loader that serves the checked bytes, never the file again), so the code that ran is the
  pinned code; a changed file refuses at import with nothing of it run (a test shows the changed code never runs).
  The file on disk is checked again before any plan is built and before any send.
- **The freeze is checked without running `gate_freeze.py`** (it hashes held-out and audit files): Phase 25's
  `check_freeze` compares the freeze file's sha256, its five fingerprints and its recorded hashes of
  `completion.md`, `mechanic.py`, `diagnosis.py`, `completion_study.py` and `policies.py`. The plan also records
  the sha256 of nine source files the rebuild depends on; any change moves the plan hash.
- **The dry run never reads `.env`** (a test checks this). A live run reads it once, through the runtime's own
  loader, after every offline check. Both API keys are scrubbed from every file the run writes.

## 3. What is imported from Phase 25, unchanged

From `slot2_probe.py` (sha `28b998ac…`, reviewed in three rounds, run once):
- **the request rebuild and its twelve verification checks** (`survey`, `verify_slot`, `mechanic_messages`,
  `request_body`, `request_digest`, `without_prior_candidate`): no Mechanic request hash is stored anywhere, so a
  prompt is used only if the immutable input record, its recomputed evidence and outcomes, the configuration, the
  historical output and the provider's own token count all check (`PHASE25_EXPERIMENT.md` §4);
- **the census rule** and its cross-check against the pinned Phase 17 and 23 run manifests;
- **the static auditor and the study's classification rules** (`classify_response`, `audit_policy`), validated
  against what stored v4 candidates did (40 of 40 agree on "fires"; recomputed in this plan);
- **the statistics** (`arm_summary`, `paired_sign`, `working_share`, `sign_test_greater`, `wilson`, `newcombe`,
  `clustered_sign`, `determinism_readout`);
- **the live loop** (`run_requests`: blind retry, waits, stop rule, re-send pass) and **`RequestSender`**, which
  checks every request's digest against the plan before sending it;
- **the round-1 fallback rule** (`fallback_permitted`, `run_end_of`);
- **the token-based paid-run process rule** (`live_experiment_processes`, `paid_run_command`), which excludes this
  process, its ancestors and its descendants, including its own `caffeinate` helper.

What is new here: the arms (§6), the declared read-outs and bars (§8), the simulation that set the working-share
minimums (§9), this phase's harm model inputs, and this phase's output, claim, review and paid-run guards (§10,
§11).

## 4. Rebuild and verification (dry run, $0)

`./.venv/bin/python scripts/experiments/slot2_hidden_probe.py` (output saved as `dry-plan-r2/dry-run.out.txt`; the
runs in `dry-plan/` and `dry-plan-r1/` gave the same figures, and all three plans hold the same 234 requests):
- **52 of 52 slots verify** (26 studies × 2 slots), 0 failures; the census is Phase 17's 5 and Phase 23's 21
  studies; 13 v4 studies that never reached slot 2 are excluded in scope; 166 studies of other configurations are
  outside scope (dry summary only, never in the hashed plan).
- **Auditor validation, recomputed:** 40 of 40 candidates agree (10 predicted to fire and fired every time, 30
  predicted silent and never fired); 35 distinct v4 policies, 4 harmful, 11 with the step, 2 with a dead step.

## 5. Population

**The same 26 slot-2 prompts as Phase 25** (the census: every v4-era full-loop study that asked for slot 2). No
other slot-2 prompt exists: no full loop has run since Phase 23.

- **This is a limit, stated now.** The prompts that suggested the hypothesis are the prompts that test it. Phase
  29's draws are fresh, repeated and concurrent with a control, so this phase answers "does it hold with repeats,
  against a concurrent control, on these prompts?". It does not answer "does it hold on new studies"; only a later
  loop can (§14).
- **Two prompts' slot-1 policies already fire** (studies `completion-study-78ed33a7…` and
  `completion-study-f3a9c0a1…`); the working share leaves them out, so 24 prompts are eligible for it (§8.3).
- **One source case; every census slot 1 ran on it and did not qualify** (review round 1; `census_facts` in the
  hashed plan, counted from the read-only store at $0). All 26 prompts ask about the same source fault spec (content
  hash `c585d162…`: F4, two transient failures of `send_confirmation`). Every census slot 1 ran on it and none
  source-qualified: slot 1's decision is `NO_CHANGE` in 23 studies and `INCOMPLETE` in 3 (so "did not qualify", not
  "failed", for 3 of them).
- **"Already proposed" is every policy the in-scope v4 studies proposed** (review round 2; `already_proposed` in the
  hashed plan, counted from the read-only store at $0). A study reaches slot 2 only after slot 1 did not qualify, so
  the census slot-1 policies (round 1's set) leave out, by construction, every slot-1 policy that qualified, all four
  certified repairs among them, and every historical slot-2 policy. The set is therefore every candidate policy hash
  proposed, **in either slot**, by the **39** in-scope v4 studies of Phases 17 and 23 (the 26 census studies and the
  13 that never reached slot 2): **35 policies**, from 33 slot-1 and 26 slot-2 proposals; all 33 studies that
  proposed anything were asked about the same source fault spec `c585d162…`. It holds the **four certified
  completion repairs** (`dd62c857…`, Phase 17 attempt 9; `711bddb6…`, `5735a918…` and `d4bc993e…`, Phase 23
  attempts 2, 21 and 24), read from the pinned run manifests and checked against the harness's declared four. A
  hidden-arm draw of any of the 35 is **already proposed**, not new; the rest are **novel**; a re-draw of a certified
  policy is reported on its own line. In a real loop the study's DUPLICATE rule would not catch such a re-proposal,
  because it compares only within one study (the `seen` set, `completion_study.py` lines 391, 422 and 425), so it
  would be run again.
- **"Distinct" is not "new".** DISTINCT means only "not this study's own slot-1 policy" (§7). Planning input from
  Phase 25's pinned run (review rounds 1 and 2; `phase25_planning_inputs`, dry summary only, never evidence here):
  - Phase 25's N wrote **25 distinct draws in only 14 policies**; one policy covered **7 of the 26 prompts**;
  - **15 of those 25** (6 policies) are a policy an in-scope v4 study had already proposed: **14** (5 policies) a
    census slot-1 policy, none of which fires, and **1** the certified `5735a918…` (slot 1 of Phase 23 attempt 21, a
    study outside the census), which is N's only WORKING draw;
  - **10 are novel** (8 policies), and **0 of them is WORKING** (1 fires and is harmful). Round 1's census-only set
    called 11 novel and 1 novel WORKING; that WORKING draw was the certified re-draw;
  - for comparison, novel draws of the distinct ones: C 10 of 20 (round 1: 19; the round-2 reviewer found 9 of the
    other 10 to be the study's own historical slot-2 policy), T 46 of 49, H 14 of 14.

  With the prior candidate hidden, the Mechanic mostly fell back on a few standard policies that other studies had
  already proposed on this source case (14 of the 15 ran there as a census slot 1 and did not qualify; the 15th is
  a certified repair). This is why §8.5 reports the novel and certified figures beside DISTINCT, and why §13 reads a
  `duplicates_cut` of SHOWN narrowly. At temperature 0, N is expected to re-draw Phase 25's N policy for most prompts
  (§9.3), so N's WORKING draws are expected to include re-draws of `5735a918…`, which the certified line reports and
  the novel figures exclude.
- **Prompts are not fully independent.** 26 studies share 22 slot-1 policies (counted in the dry plan), and one
  hidden-arm policy can supply many prompts (7 of 26 above). The distinct sign test (D3) is also reported with
  prompts collapsed by slot-1 policy, and every per-draw rate gets clustered intervals (§8.5), both descriptive.

## 6. Arms (exact)

Every request is the `chat.completions.create()` call `RuntimeProvider.complete` makes for the Mechanic role:
the completion prompt as the system message, and `canonical_json({**context, "output_schema": ...})` as the user
message; `max_tokens=2000`, `response_format={"type": "json_object"}`, `stream=False`,
`extra_body={"chat_template_kwargs": {"enable_thinking": False}}`, and the arm's temperature.

| arm | `context` | temperature | draws per prompt | requests |
|---|---|---|---|---|
| **C** (concurrent control) | the verified stored slot-2 context, unchanged | 0 | 3 | 78 |
| **N** (prior candidate hidden) | the slot-2 context with **`candidate_history = []`**; `development_evidence` and `observed_outcomes`, which carry slot 1's six source episodes, stay | 0 | 3 | 78 |
| **NT** (hidden, moderate temperature) | the same bytes as N | **0.4** | 3 | 78 |
| **total** | **52 distinct prompts** (26 stored, 26 hidden; N and NT share theirs) | | | **234** |

- **N is exactly Phase 25's reference request N**, byte for byte, and C is exactly Phase 25's C. The $0 pre-check
  compares every request digest with Phase 25's live plan.
- **Why 0.4 for NT (declared before any Phase 29 data; a planning choice, not tuned).** Phase 25's T raised the
  temperature to 0.7 with the prior in view: more distinct and more working draws (6 of 78 against 0), but 9 of 78
  invalid, failing its invalid bar. 0.4 is a round value between 0 and 0.7, chosen to keep part of the diversity at
  less cost in validity. No data can inform it without spending, and another value would be another phase.
- **Why these arms and not others.** The program names them. A later loop adopting N changes one line of
  `completion_study.py` (§16); NT also needs a per-slot Mechanic temperature.

**Order.** Three rounds (`r0001`–`r0078`, `r0079`–`r0156`, `r0157`–`r0234`). In each round the 26 prompts come in
seeded sha256 rank order (seed `faultlab-phase29-2026-09-25`), each prompt's C, N and NT back to back in ranked
order; each round is ranked afresh. A run that stops after round 1 therefore has a complete round 1.

**The $0 pre-check passed** (`precheck` in the plan). Nothing may be sent if it fails.

| check | result |
|---|---|
| N with `candidate_history` restored equals C's context; same system message and settings | 26 of 26 |
| N's user message has an empty `candidate_history` and holds neither slot 1's raw text nor its policy hash | 26 of 26 |
| NT differs from N only in `temperature` (0.4 against 0, and C at 0) | 26 of 26 |
| C's messages hash and request digest equal Phase 25's C request for the same prompt | 26 of 26 |
| N's messages hash and request digest equal Phase 25's N request for the same prompt | 26 of 26 |

A test also checks, for all 26 prompts, that the hidden prompt equals what the real `Mechanic.propose_completion`
sends for the slot-2 context with an empty `candidate_history` (captured with a fake provider).

## 7. Classes and WORKING (Phase 25's auditor, imported)

- Each returned text is judged as the study would: `INVALID` (fails `MechanicOutput`, `CandidatePolicy`, or is
  empty), `NO_CHANGE`, `STALE_PARENT`, or `CANDIDATE`. A candidate is **DUPLICATE** if its policy hash equals slot
  1's (the study's DUPLICATE rule), else **DISTINCT**. No format-repair turn is sent: one request is one draw.
- **DISTINCT is not "new"** (review rounds 1 and 2). It means only "not this study's own slot-1 policy". A
  DISTINCT draw may be a policy another in-scope v4 study already proposed, in either slot, on this source case,
  including a certified repair (§5); §8.5 splits DISTINCT draws into those **already proposed** and the **novel**
  ones, with re-draws of a certified policy on their own line.
- **Step present:** a notifications `retry_original_request` at `after_notification_response`.
- **Step fires:** an abstract run of the policy interpreter on the source path (upgrade succeeded; first send
  proposed; the send failed transiently, status `UNKNOWN`, never `PENDING`, pitfall 77) executes the retry, and
  nothing earlier closed business, blocked the send or exhausted a bound.
- **Harmful:** a premature defer (pitfall 78) or a rule that stops the first confirmation.
- **WORKING = DISTINCT, the step fires, and not harmful.**

**Where this is stricter than the program's wording.** The program glosses working as "step present and can fire
after a transient failure". Phase 25's round-1 review showed that counting distinct firing draws as working counts
premature-defer policies, which then lose terminal rejection in validation (Phase 17 attempt 4). So WORKING also
requires no declared harmful side rule, and harm is guarded separately (§8.4). Distinct firing draws, harmful or
not, are reported beside it.

## 8. Declared read-outs, tests and adoption bars (stated before any data)

For each treated arm **X ∈ {N, NT}, against C**, on Phase 29's draws only.
**Complete:** an arm received at least 95% of its planned draws (75 of 78; 25 of 26 in round 1).

**Missing draws.** Where a condition's denominator is the planned draws (D1, D2, W1, W2), a missing draw counts
against X: a missing X draw is not DISTINCT or WORKING, and a missing C draw counts as DISTINCT (D2) or as
WORKING (W1, W2). The distinct and invalid sign tests (D3, I2) and the invalid rates (I1) use received draws only;
a prompt with no received draw in either arm drops out of a sign test. Completeness bounds how much this can
matter.

**Multiplicity.** Two treated arms share one control. Each positive claim (duplicates cut, yield gain) uses
**α = 0.025 per arm** (Bonferroni over N and NT), and the working-share minimum is calibrated to a false-alarm
rate of **0.025 per arm** (§9). So, **within the calibrated range (a common firing rate of at most 0.10, §9.2)**,
the chance of any false positive claim of each kind across the two arms is at most 0.05. Outside that range the
working claim's false-alarm rate per arm rises (0.041 at a common firing rate of 0.15 and 0.070 at 0.20, §9.2),
and whether C is inside the range is read from C's own draws, which are few and clustered; §8.5 reads it from C
alone, two ways (review round 2), and fixes what the results must say. Guard tests use **α = 0.05 per arm** with no correction, which is the
stricter direction for adoption.

**What the bars are** (review round 1). D1, D2, I1, W1 and H1 are bars on the rates **observed in this run**; they
are not tests of true rates. The exact tests (D3, W2, and the guards' I2 and H2) guard only against "no
difference". So a `duplicates_cut` of SHOWN does not show a true gain of 0.30: a $0 re-check with the harness's
own code (`artifacts/phase29-2026-09-25/review-r1/dup_margin_check.out.json`) finds it SHOWN 24–33% of the time at
a true gain of 0.25 (D_X 0.80 or 0.75 against D_C 0.55 or 0.50), and 34–36% at exactly the bars (0.70 against
0.40). Results quote D_X and D_X − D_C as what this run observed.

### 8.1 Duplicates cut, part 1: distinct (a positive claim)

| # | condition | name |
|---|---|---|
| D1 | D_X = X's DISTINCT draws / 78 planned ≥ **0.70** | `distinct_at_least_0.70` |
| D2 | D_X − D_C ≥ **0.30**, where D_C = (C's DISTINCT + C's missing) / 78 | `distinct_gain_at_least_0.30` |
| D3 | **exact** one-sided sign test over prompts on each prompt's DISTINCT mean over its received draws, X above C (ties and prompts without draws in both arms dropped): p < **0.025** | `distinct_sign_test_p_below_0.025` |

Distinct, not "not duplicate": a drop in duplicates bought with invalid or `NO_CHANGE` output does not count.

### 8.2 Duplicates cut, part 2: invalid (a guard)

Invalid = (`INVALID` + `STALE_PARENT`) / received draws.

| # | condition | name |
|---|---|---|
| I1 | invalid_X − invalid_C ≤ **0.10** (Phase 25's bar) | `invalid_at_most_C_plus_0.10` |
| I2 | **not** (exact one-sided sign test over prompts on each prompt's invalid mean, X above C, p < **0.05**) | `invalid_not_shown_above_C_at_0.05` |

- **I2 is new and stricter than Phase 25.** The program asks for "without raising invalid output". A raise shown
  across prompts at p < 0.05 is a raise even below 10 points (for example 6 prompts of 26 with an invalid X draw
  and none for C). Its cost is in §9.4. `NO_CHANGE` is not invalid; it lowers D_X instead.
- **I1 and I2 measure first attempts, so they overstate what adoption would see** (review round 1). A real study
  would partly repair them: `Mechanic._generate` sends a `MechanicOutput` (schema) failure back once for a format
  repair (`propose_completion` keeps it on), while an empty response (the runtime raises `EMPTY_FINAL_RESPONSE`), a
  candidate the study's policy check rejects, and a stale parent are not repaired (`completion_study.py` line 419,
  "Invalid or stale policy"). The probe sends no repair (§7). §8.5 therefore reports invalid draws in these two
  groups, descriptive, and an invalid-guard FAIL does **not** show that adoption would raise invalid output; the
  split says how much of any excess a study would not repair. The guard itself is unchanged (the owner decides
  §18 question 2 with this on the page).

### 8.3 Yield gain, part 1: working (a positive claim)

Only the **24 prompts whose slot-1 policy's step does not fire** are eligible. On each, X's share is its WORKING
draws / its planned draws (a missing X draw is not WORKING), and C's share is its WORKING **or missing** draws /
its planned draws (Phase 25's `working_share`). Each prompt adds between −1 and +1.

| # | condition | name |
|---|---|---|
| W1 | the sum over eligible prompts of X's share minus C's share ≥ **3** (with 3 draws per prompt: at least 9 more WORKING draws in X than WORKING-or-missing draws in C, of 72 eligible draws each) | `working_share_gain_at_least_3.00` |
| W2 | **exact** one-sided sign test over the eligible prompts on those per-prompt differences, X above C: p < **0.025** | `working_sign_test_p_below_0.025` |

- **Why both.** The sign test alone is not a valid test of "equal per-draw WORKING rates" when the arms cluster
  differently within a prompt: C at temperature 0 tends to repeat itself, and an arm whose draws vary more wins
  more prompts at the same per-draw rate (Phase 25 review round 2, "breadth is not yield"). Alone, at p < 0.025, it
  reaches a false-alarm rate of **0.075** in the worst simulated case (§9.2). The minimum gain W1 bounds that.
- **Why 3.** It is the smallest multiple of 1/3 whose worst simulated false-alarm probability for W1 and W2
  together, under the yield null, is at most 0.025 (§9.2): 8/3 gives 0.029, 3 gives 0.0185. It was chosen by the
  harness's own `--protocol-numbers` run, whose output records `harness_minimum_is_the_chosen_one: true`.

### 8.4 Yield gain, part 2: harmful (a guard)

| # | condition | name |
|---|---|---|
| H1 | at most **half** of X's distinct firing draws carry a declared harmful side rule (Phase 25's bar) | `harmful_share_of_firing_at_most_0.50` |
| H2 | **not** (exact one-sided Fisher test on harmful against not harmful among distinct firing draws, X above C, p < **0.05**) | `harmful_not_shown_above_C_at_0.05` |

- **H1 is a cap within X, not a contrast.** A contrast of harmful draws per planned draw was tried in Phase 25 and
  dropped before any data, because harm tracks firing (3 of the 9 v4 policies whose step fires are harmful) and it
  refused the arms that fire most. H1 holds when X has no distinct firing draw; W1 cannot then hold.
- **H2 is the contrast against C,** on the share of firing draws that are harmful, so it does not penalise an arm
  for firing more. It is **not computable, and does not fail, when either arm has no distinct firing draw.** Since
  C rarely fires (Phase 25: 3 of 78, all harmful), H2 will often be not computable or unable to fail. Its reach is
  small, and that is stated here, not discovered later.
- H2 treats draws as independent; clustering makes it fail more easily, which is the conservative direction.

### 8.5 Decision

| declared result (per arm) | when |
|---|---|
| **`RECOMMEND_FOR_A_LATER_LOOP`** | X and C complete, and D1–D3, I1–I2, W1–W2 and H1–H2 all hold |
| **`INCOMPLETE`** | X or C is not complete (then §8.6) |
| **`NOT_RECOMMENDED`** | otherwise; every failed condition is listed |

Two part-verdicts are **declared on their own** (`SHOWN` / `NOT_SHOWN` / `INCOMPLETE`), so a partial answer can be
reported as declared, not framed afterwards:
- **`duplicates_cut`** = D1–D3 and I1–I2 (question 1);
- **`yield_gain`** = W1–W2 and H1–H2 (question 2).

If both arms are recommended, this phase prefers neither; their comparison is descriptive (below). The statement
in `readouts.json` lists each arm's decision, both part-verdicts and every failed condition.

**Descriptive only (never a decision input):**
- per arm: classes, distinct, duplicate, byte- and rules-text-identical rates, invalid and `NO_CHANGE` counts,
  distinct firing (harmful or not), working, step present, dead steps, every side-rule flag, `orders_retry`
  (relevant to Phase 28), distinct and working policy counts, Wilson intervals over draws (they understate
  uncertainty, because draws cluster by prompt), how draws arrived (blind retries, re-sends, timeouts, missing);
- **duplicates of slot 1 with the prior hidden** (the Phase 25 lead's measure, now with repeats): draws and prompts
  with at least one duplicate, per arm;
- **N against NT** (Newcombe intervals for distinct, working and invalid; the sign test and working share of NT
  over N): never a decision;
- **dependence on Phase 25:** for N and NT, the received draws whose policy (and whose bytes) equal what Phase 25's
  single N draw wrote for the same prompt, and that share;
- **C's firing rate** (distinct firing draws over received draws) and whether it is inside the calibrated range
  (≤ 0.10; §9.2), **read from C alone** since review round 2 (`calibrated_range`: `within`, `not_confirmed` or
  `outside`): C's point rate (`outside` above 0.10) and C's Wilson 95% upper bound (`not_confirmed` when only it is
  above 0.10). The calibration is about the null, where both arms share C's rate, so X's rate has no place in it:
  the pooled X-and-C rate is reported beside it (`pooled_rate_descriptive`) and drives no wording, because X's own
  gain inflates it on every SHOWN working claim (round 1 read it as a third leg, which fired on 90% of simulated
  SHOWN claims with C inside the range, §9.2). Round 1's point-only flag
  (`C_within_the_calibrated_firing_range_descriptive`) is dropped, so no second flag can disagree with the reading;
- Newcombe intervals over received draws for the distinct and WORKING differences; the distinct sign test with
  prompts collapsed by slot-1 policy; the working share's breadth count (Phase 25's, never a decision); the served
  model; tokens; determinism of C, N and NT (repeat pairs byte- and policy-identical; C also against its historical
  output).

**Added in review rounds 1 and 2** (declared before any Phase 29 data; descriptive, never a decision input):
- **policy concentration**, per arm (`policy_concentration`): the number of distinct policies among the DISTINCT
  draws, the prompt and draw count of the largest one, and how many policies appear on more than one prompt;
- **already proposed against novel**, per arm: the DISTINCT, distinct-firing and WORKING draws (and policies) whose
  policy is **already proposed** (review round 2: any of the 35 policies the 39 in-scope v4 studies proposed in
  either slot, `populations.already_proposed` in the hashed plan, §5), against the **novel** ones; beside them, on
  **their own line, re-draws of a certified policy** (`certified_policy_redraws`: draws, policies, firing and
  WORKING), and, for comparison only, round 1's narrower count of census slot-1 re-draws
  (`census_slot1_policy_redraws_round1_set`);
- **WORKING draws per distinct WORKING policy**, per arm, with the largest WORKING policy's draws and prompts;
- **per-draw rates with clustered intervals**, per arm, for DISTINCT, novel DISTINCT, WORKING and novel WORKING
  (`per_draw_rates_with_clustered_intervals`): beside the Wilson interval over draws, a **Wilson interval that counts
  each linked prompt group once** (prompts that share a slot-1 policy or any policy drawn in that arm, joined
  transitively), and percentile bootstraps (2,000 resamples, fixed seeds) over prompts and over linked prompt groups.
  **A cost model uses the Wilson interval that counts each linked group once**, never the Wilson interval over draws
  (one policy can supply many prompts) and never a bootstrap: since review round 2 a bootstrap over fewer than **10**
  clusters is withheld (null, flagged in `bootstrap_withheld`, with a note), because it is falsely precise at few
  groups (zero width at one group), and the groups can be few (Phase 25's N formed 6 linked groups, sizes 15, 4, 3,
  2, 1 and 1, with one draw per prompt; three draws per prompt can only merge more). The group Wilson interval
  stays informative when nothing succeeded, where a percentile bootstrap collapses to [0, 0];
- **invalid draws by what a study would do** (`invalid_by_what_a_study_would_do`), per arm: schema failures (a study
  would send them back once for a format repair) against empty responses, candidates the study's policy check would
  reject, and stale parents (not repaired), with the not-repaired rate and, for N and NT, its excess over C (§8.2).

**Fixed wording rules** (review round 1; printed in the statement, never a change to a decision):
- **Re-measurement.** If at least **half** of a hidden arm's received draws re-draw the policy Phase 25's N wrote for
  the same prompt (`same_prompt_re_measurement`), the statement, and the results, call that arm's duplicates-cut
  result **a same-prompt re-measurement of Phase 25's N draws, not an independent confirmation**. §9.3 predicts
  this for N.
- **Calibrated range** (read from C alone since review round 2). When an arm's working claim is SHOWN and C's point
  rate is above 0.10, the claim is **outside** its calibrated range; when only C's own 95% upper bound is above 0.10,
  the range is **not confirmed**. Either is quoted beside the claim. The pooled rate never changes the wording.
- **Distinct is not new.** The statement always carries "DISTINCT means only 'not this study's own slot 1', not
  'new'" and says that novel means none of the 35 policies the in-scope v4 studies proposed and that a re-draw of a
  certified policy is not new; each arm's line gives its DISTINCT, novel and already-proposed counts, its WORKING
  draws (and novel WORKING draws) and policies, and, on its own, its re-draws of a certified policy and how many of
  them are WORKING.

### 8.6 Round-1 fallback (Phase 25's rule, imported)

- **When:** an arm's all-rounds decision is `INCOMPLETE` **and** the run ended by a stop the operator does not
  choose (`completed`, `spend_guard`, `consecutive_errors`, or a crash recorded with its traceback) with **no stop
  signal** recorded.
- **What:** the same rule on round 1 alone (26 planned draws per arm, complete at 25), with the working minimum
  **1** (chosen the same way, §9.2); labelled `round_1_only`, with every all-rounds figure beside it.
- **Never after an operator stop:** any SIGINT or SIGTERM, whoever sent it, or a process closed by
  `--finalize-abandoned`, leaves an `INCOMPLETE` decision `INCOMPLETE`. So stopping once round 1 has arrived can
  never choose which rule decides.
- A live response line carries no classification, and `--readouts` refuses until the run's manifest is final. The
  operator does not open `responses.jsonl` and does not cause a stop.

## 9. False alarms, power and boundaries (computed, $0)

From `artifacts/phase29-2026-09-25/protocol-numbers-r2/protocol_numbers.out.json` (recomputed after review rounds 1
and 2; every figure equals the `protocol-numbers/` and `protocol-numbers-r1/` outputs), written by
`slot2_hidden_probe.py --protocol-numbers` with the harness's own decision code (seed
`faultlab-phase29-protocol-numbers`; 4,000 simulations per yield-null cell, 2,000 per power cell).

**Models (stated, not measured).** 26 prompts, 2 with a slot-1 policy whose step fires; 3 draws per arm per prompt;
each draw invalid with probability 0.03 unless stated; otherwise distinct at the arm's rate d and firing at its
unconditional rate w; a firing draw harmful with probability 3/9 and a distinct non-firing draw 1/26 (the store's
rates, Phase 25), so WORKING ≈ 2w/3; per-prompt clustering by a Beta model (ρ) or Phase 25's repeat model (each
later repeat copies the prompt's first draw with probability q), chosen per arm; and a shared-effect model.

### 9.1 Count boundaries at full receipt (78 planned draws per arm)

- **Complete:** 75 received (25 of 26 in round 1).
- **D1:** at least 55 distinct X draws. **D2:** C's distinct plus missing at most 54 when X is fully distinct.
- **I1:** at most 7 more invalid X draws than C's.
- **Sign test at p < 0.025** needs, of n untied prompts: 6 of 6, 7 of 7, 8 of 8, 8 of 9, 9 of 10, 10 of 12, 12 of
  15, 13 of 17, 15 of 20, 18 of 24. **At p < 0.05:** 5 of 5, 6 of 6, 7 of 8, 9 of 10.
- **H1:** harmful firing draws at most 0 of 1, 1 of 2 or 3, 2 of 4, 3 of 6, 4 of 9, 6 of 12.
- **Round-1 fallback** (26 planned draws per arm): complete at 25; D1 at least 19 distinct X draws; D2 C's distinct
  plus missing at most 18 when X is fully distinct; I1 at most 2 more invalid X draws than C's at full receipt.

### 9.2 The yield null and the working minimum

**Yield null:** X far more distinct than C (d_X 0.80 or 0.95 against 0.30), with the same firing rate (0.04 or
0.10). Twelve clustering scenarios (Phase 25's, including every repeat scenario of its round 3) and the
shared-effect model.

| working minimum W1 (with W2) | 2 | 7/3 | 8/3 | **3** | 10/3 | 4 |
|---|---|---|---|---|---|---|
| worst P(yield claim), all cells | 0.069 | 0.046 | 0.029 | **0.0185** | 0.009 | 0.002 |

- **The sign test alone (no W1) reaches 0.075** in the worst cell: C repeating its draws (q 1.0) while X's draws
  are independent (ρ 0), common firing 0.10, D_X 0.80. This is the breadth effect.
- **At 3, the worst cell is 0.0185** (C repeats at q 1.0, X ρ 0.2, common firing 0.10, D_X 0.80; the same scenario
  at D_X 0.95 gives 0.0107); every other scenario is at most 0.0097.
- **Outside the grid, descriptive:** at a common firing rate of 0.15 the same rule's worst cell is **0.041**, and
  at 0.20 it is **0.070** (both in the scenario C q 1.0, X ρ 0.2). The grid stops at 0.10 because C's measured
  rate is far below it (Phase 25: 3 of 78 distinct firing draws, a planning input). The read-out flags whether
  the concurrent C's firing rate is ≤ 0.10. If it is not, the results must say that the working claim's
  false-alarm rate is not calibrated at that rate (up to about 0.07 at 0.20). The declared verdict is not changed.
  Since review round 2 the flag reads C's rate **from C alone**, two ways (§8.5): its point estimate (`outside`
  above 0.10) and its Wilson 95% upper bound (`not_confirmed` when only it is above 0.10, which happens from 3
  firing draws of 78 upward), because C's 78 draws are few and clustered. The calibration is about the null, where
  both arms share C's rate; round 1 also read the pooled X-and-C rate, which X's own gain inflates on every SHOWN
  claim, so that leg mostly restated the claim. A $0 re-simulation with the harness's own code (C at a true firing
  rate of 0.02, inside the range; the round-2 reviewer's four power scenarios, X at 0.16, 0.20 and 0.30, 400
  simulations per cell, the same seed; `review-r2/range_reading_r2.out.json`): among SHOWN working claims the
  reading is not `within` in **507 of 2,169 (23%)**, against **1,945 of 2,169 (90%)** under round 1's three-way
  reading; at C's true rate 0.04 it is 920 of 1,836 (50%). So `not_confirmed` is still **expected on about a quarter
  of SHOWN claims even when C is at 0.02**: it says C's own 78 draws cannot confirm the range, nothing more.
- **Round-1 fallback:** minimum 1; worst cell 0.002 (the sign test at p < 0.025 already needs 6 of 6).

### 9.3 Power

P(`RECOMMEND_FOR_A_LATER_LOOP`), C at distinct 0.30 and firing 0.02, X at distinct 0.95, by X's firing rate
(WORKING per draw ≈ 2/3 of it); 3% invalid in both arms. In every cell P(`yield_gain` SHOWN) is at most 0.030 above
it, and P(working shown, W1 and W2) at most 0.049 above it: that gap is what the other conditions cost.

| X firing w (WORKING ≈) | N-like: both at temperature 0, both repeat (q 0.9) | N-like, X varies more (C q 0.9, X ρ 0.5) | NT-like: C repeats (q 0.9), X ρ 0.2 | independent |
|---|---|---|---|---|
| 0.04 (0.027) | 0.000 | 0.002 | 0.001 | 0.000 |
| 0.08 (0.053) | 0.003 | 0.022 | 0.013 | 0.009 |
| 0.12 (0.080) | 0.018 | 0.092 | 0.096 | 0.067 |
| 0.16 (0.107) | 0.048 | 0.230 | 0.279 | 0.246 |
| 0.20 (0.133) | 0.122 | 0.437 | 0.478 | 0.486 |
| 0.25 (0.167) | 0.251 | 0.627 | 0.714 | 0.756 |
| 0.30 (0.200) | 0.382 | 0.788 | 0.841 | 0.883 |
| 0.40 (0.267) | 0.644 | 0.928 | 0.940 | 0.965 |

- **Duplicates cut:** P(`duplicates_cut` SHOWN) is **0.96–0.99** in every cell above (X at 0.95 distinct). By X's
  distinct rate, against C at 0.30: 0.95 → 0.99; 0.80 → 0.86–0.97; 0.70 → 0.46–0.51; 0.60 → 0.03–0.13.
- **Round-1 fallback** (one draw per prompt): 0.066 at w 0.20, 0.283 at 0.30, 0.542 at 0.40.
- **What this means, plainly.** This phase can show that hiding cuts duplicates, almost surely if Phase 25's lead
  is real. It can show a yield gain only if hiding raises the per-draw WORKING rate to roughly **0.13–0.20 or
  more** (0.44–0.49 at 0.13 and 0.63–0.76 at 0.17 in three of the four scenarios), and it has the least power in
  the case most like N (both arms at temperature 0 repeating themselves: 0.12 at 0.13, 0.38 at 0.20).
  **A `yield_gain` of `NOT_SHOWN` is not evidence of no gain.** The per-draw WORKING rate of each arm is reported
  either way, with the **clustered** intervals of §8.5 beside the Wilson interval over draws. A later loop's cost
  model uses the **novel** DISTINCT and **novel** WORKING rates (review round 2: novel against all 35 policies the
  in-scope v4 studies proposed; a re-draw of a certified policy is reported on its own line and is not a new
  repair), with the **Wilson interval that counts each linked prompt group once**; never D_X, never the Wilson
  interval over draws alone, and never a bootstrap (withheld below 10 groups, §8.5): the draws of one prompt tend to
  repeat one policy, and one policy can supply many prompts (Phase 25's N: 7 of 26; 6 linked groups), so a Wilson
  interval over 78 draws would be overconfident and a bootstrap over a few groups falsely precise.
- **The expectation, stated before data (planning inputs from Phase 25, never evidence):** Phase 25's N wrote a
  distinct policy 25 of 26 times and a WORKING one 1 of 26 (firing 2 of 26, about 0.08); that WORKING draw re-drew
  the certified `5735a918…`, so N's **novel** WORKING count was 0 of 26 (review round 2, §5). If that holds, N's
  likely result is **`duplicates_cut` SHOWN and `yield_gain` NOT_SHOWN** (P(yield) about 0.003–0.02 at firing 0.08),
  and N's WORKING draws are likely to be mostly re-draws of `5735a918…` on its one prompt (§9.3's dependence). NT
  is unknown: Phase 25's T at 0.7, with the prior in view, fired 7 of 78 and wrote 6 WORKING draws, but 4 of those
  6 were on the two prompts whose slot-1 policy already fires, so its working-share gain on the eligible prompts
  was 2/3, far below 3.
- **The predicted dependence on Phase 25, stated before data (planning input, review round 1).** N sends Phase 25's
  N requests byte for byte, at temperature 0. In Phase 25 the same temperature-0 request returned the same policy in
  **0.73–0.82** of re-sends (C against its historical output 57 of 78; C repeat pairs 59 of 78; H repeat pairs 64 of
  78; computed by `phase25_planning_inputs`). So about **0.73–0.82 of N's received draws are expected to re-draw
  Phase 25's N policy for the same prompt**, which is above the wording rule's 1/2 (§8.5). If that holds, N's
  `duplicates_cut` result largely re-measures, on the same prompts, the draw that suggested the hypothesis: its
  0.96–0.99 chance of SHOWN is closer to a replication probability than to the power of an independent test, and
  the results must say so. N's three repeats per prompt also add little policy information at temperature 0
  (roughly one prompt's worth each, since most repeat pairs return one policy). **This phase's new information
  therefore comes mainly from NT and from the novel WORKING estimates of both arms** (§18 question 1).

### 9.4 The guards' operating characteristics

**Invalid guard FAIL** (I1 or I2), by X's per-draw invalid rate, X at distinct 0.95 and firing 0.04, C at
distinct 0.30 and firing 0.02:

| X invalid | C at 0 (Phase 25's C: 0 of 78) | C at 0.03 |
|---|---|---|
| 0.03 | 0.04–0.08 | 0.005–0.04 |
| 0.05 | 0.12–0.30 | 0.04–0.14 |
| 0.08 | 0.33–0.73 | 0.21–0.41 |
| 0.115 (Phase 25's T at 0.7) | 0.59–0.94 | 0.42–0.70 |
| 0.15 | 0.76–0.99 | 0.61–0.86 |

(ranges over three scenarios: independent, both repeating at q 0.9, and C repeating with X at ρ 0.2). At equal
invalid rates of 0.03 the guard fails 0.7–3.9% of the time (power table). These are **first-attempt** rates (§8.2): a
study would send schema failures back once for a format repair, so an invalid-guard FAIL overstates what adoption
would see; §8.5's split says how much of an excess a study would not repair.

**Harmful guard FAIL** (H1 or H2), C at distinct 0.30 and firing 0.04 with the store's harm rate (3 of 9 firing
draws harmful), X at distinct 0.95 and firing 0.10 or 0.20; ranges over those two firing rates and two scenarios
(independent, both repeating at q 0.9):

| X's true harmful share of firing draws | FAIL | H2 (Fisher) alone |
|---|---|---|
| 1/3 (the store's rate) | 0.06–0.24 | 0.002–0.049 |
| 1/2 | 0.41–0.51 | 0.02–0.12 |
| 2/3 | 0.65–0.89 | 0.09–0.21 |
| all | 0.96–1.00 | 0.37–0.61 |

The false FAIL at the store's rate comes from small counts of firing draws. It matters little where a yield gain is
shown, because W1 then implies at least 9 more WORKING draws; that is why P(`RECOMMEND`) stays close to P(working
shown) in §9.3.

### 9.5 What the probe cannot see

- Anything about episodes, qualification, validation or certification: no episode runs (pitfall 71).
- Harm outside the two declared patterns, and policies of a shape outside the auditor's validation.
- Whether the effect holds on new studies (§5).

## 10. Bounds, spend cap, waits and stop rule

| | value |
|---|---|
| planned requests | **234** (52 distinct prompts; C 78, N 78, NT 78) |
| per-request bound | **$0.04984** |
| planned bound | **$11.66** ($11.66256) |
| hard spend cap | **$15.00 for the whole phase**: 300 attempts, leaving **66 for blind retries and re-sends** |
| token-priced estimate | about **$4.99** (local token counts + 24 framing tokens, and the historical median slot-2 output, 463.5 tokens); at most **$6.42** with every output at 2,000 tokens. Unverified; the ledger carries the bound |
| input tokens (median, range) | C 15,703.5 (14,828–16,777); N and NT 14,357 (13,453–15,376); the runtime refuses above 32,000 |
| budget before this phase | $652.90 charged, $347.10 remaining (after Phase 27); reconcile first if Phase 28 or 30 has spent since |

- **Spend guard** (Phase 25's, checked against this harness's cap): every attempt, including a retry or a re-send,
  is charged at the bound in whole micro-dollars; the attempt that would pass the cap is refused and the run stops
  with `spend_guard`. The plan is refused before any call if it cannot fit.
- **The cap is a phase cap.** A live run's cap is the smaller of `--spend-cap` and $15.00 minus the
  `charged_upper_bound` of every earlier Phase 29 run that delivered nothing.
- **Retries, waits, re-send pass, request digest and stop rule:** exactly Phase 25's (`PHASE25_EXPERIMENT.md` §10),
  imported. A blind retry, at most once and after 10 s, only for a transport failure that delivered no generation
  (`CONNECTION_ERROR`, `REQUEST_TIMEOUT`); an empty final response is recorded as received and never retried;
  waits of 30 s, 2 min, 5 min, 5 min after errored requests; a fifth errored request in a row stops the run; after the main pass, each request
  that errored with nothing delivered is re-sent once; a delivered generation is never re-rolled (pitfall 49).
  Before every send, `RequestSender` checks that the runtime built temperature 0, applies the arm's temperature,
  and forwards only if the request digest equals the plan's.
- **Stop reasons:** `completed`, `spend_guard`, `consecutive_errors`, `operator_stop` (any SIGINT or SIGTERM,
  recorded with where it arrived), `another_paid_run_after_claim` ($0), `ABORTED` with a traceback, and
  `abandoned` (closed at $0 by `--finalize-abandoned`).
- **No resume, and one run that delivers anything.** Each run needs a new directory, exactly
  `artifacts/phase29-<date>/<name>`. An earlier run that is not final, or that delivered any generation, refuses
  every later run: a second draw would be repeat-until-lucky.
- **Atomic claim:** `artifacts/phase29-live-claims/claim-NN.json`, written in full and hard-linked (never deleted),
  after the output directory is created exclusively. **Progressive records:** `slot2-hidden-probe-manifest.json`
  is rewritten after every request, and `responses.jsonl` is appended and fsynced per request, before the manifest
  that counts it.

## 11. One paid run at a time, and the live gate

**The harness refuses to launch** while any of these hold. It checks them before building the plan, again at the
start of the live path, again after the credential read, and once more right after the claim (then this run ends
at $0 with `another_paid_run_after_claim`):
- a run manifest of another phase is not final: Phase 20 (`dev-probe-manifest.json`), 21
  (`lapse-probe-manifest.json`), 23 (`full-loop-manifest.json`), 25 (`slot2-probe-manifest.json`), 26
  (`gap-probe-manifest.json`), 27 (`report-word-probe-manifest.json`), each at its exact depth; or **any**
  `*manifest*.json` directly under `phase28-*`, `phase30-*` or `phase31-*` or one directory below it, because those
  phases are being built beside this one and their manifest names are not known here. A manifest counts as final
  only with an end time and no running status; an unreadable one counts as running. This fails closed: a sibling
  file that is not a run manifest but carries "manifest" in its name also blocks, until it is cleared by name
  with `--ignore-manifest` (below);
- a claim in `phase20`, `21`, `23`, `25`, `26`, `27`, `28`, `30` or `31-live-claims` names a directory with no
  final manifest, **or names anything other than exactly `artifacts/phaseNN-<x>/<name>`**. A claim into
  `phase22-*` (the heldout-2 seal) or `phase24-*` (its held-out check) is never followed; it is a blocker, and
  nothing it names is read. A file named `heldout-manifest.json` is skipped wherever manifests are read;
- **another process was launched as a paid experiment run**, by Phase 25's token rule: a Python executable
  running any `experiments/<name>.py` with `--execute-live` or any prefix of it from `--e`. **This process, its
  ancestors and its descendants are excluded**, so the runbook's own `caffeinate -is` helper (Python's child, with
  the launch arguments on its command line) does not block its own run; another run launched the same way is still
  caught through its Python process. A process list that cannot be read is itself a blocker;
- the lab backend's read-only status (`GET http://127.0.0.1:8000/api/config/status`) shows an active campaign, or
  cannot be read. A refused connection means the backend is down, so no backend-driven run can be active.

Phase 29's own manifests and claims are not "another run": they are covered by the one-delivering-run rule
(§10). `--ignore-manifest <exact path>` clears a crashed manifest or claim, or a sibling file that is not a run
manifest, never a process or the backend; each use is recorded in the run manifest (`ignored_manifests`), and
the operator states why in the results.

**The live gate.** The provider is called only if all of these hold:
- `--execute-live`, `--out`, `--confirm-entity`, `--expect-plan-hash`, `--expect-harness-sha256` and
  `--expect-protocol-sha256` are all given (checked before any plan is built);
- the Phase 25 harness is the pinned one (checked at import before any of it runs, and on disk again here);
- the output directory is new and exactly `artifacts/phase29-<date>/<name>`; every earlier live run is final and
  delivered nothing; no other paid run is in progress;
- the harness sha256 matches; this file exists and its sha256 matches; the recomputed plan hash matches, and this
  file contains the harness sha256 and the plan hash;
- **the review is enforced:** this file's status block (everything before its first `## ` heading) no longer
  carries the review-pending phrase in any case; this file has a bare line reading exactly
  `Reviewed for launch: harness <sha256> plan <hash>`; and `artifacts/phase29-2026-09-25/review.json` names this
  file's sha256 as `protocol_sha256`, the same `harness_sha256` and `plan_hash`, and `phase_cap` 15.0. Any edit to
  this file after the record is written makes the gate refuse;
- **the owner's approval is enforced** (review round 1, as Phase 30; made strict in review round 2): the record's
  `status` is exactly `"approved"`, `approved_by` is a non-empty name, and `owner_answer` holds non-empty
  `question`, `verbatim`, `given_by` and `date`: the owner's answer to §18 question 1 (that the phase is worth its
  bound). Since review round 2:
  - `question` is exactly `§18 question 1`;
  - `verbatim` is **one line** with no leading or trailing space, **at least 20 characters** long;
  - `verbatim` is **not words the status block or the program document already hold**: its letters and digits (case,
    spaces and punctuation ignored) must not occur in this file's status block or in
    `docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md`. So the program-level approval ("go ahead with whatever u
    recommend", which the status block quotes and which a workflow may relay) is never taken as the answer, however
    it is punctuated; a program document that cannot be read refuses;
  - this file's **Review log closing entry** (after the last `## Review log` heading, the last heading under it that
    starts `### Review log — closing`, up to the next heading) carries, **exactly once and on one bare line**, the
    line `Owner's answer to §18 question 1 (<given_by>, <date>): "<verbatim>"` with the record's three values. The
    line is never wrapped, however long, and carries no list marker, bold or backticks.

  Round 1's check was a plain substring test over the whole file, which the status block's program-level quote and
  a one-letter "answer" both passed (Review log, round 2, finding 1). Each missing or wrong field refuses before the
  credential read and before any claim, and the run manifest records the approval (`review`, with all four
  fields). So a record with the three hashes and the cap alone no longer launches;
- every planned request has a prompt whose hash and request digest match the plan;
- the run's cap is positive and the plan fits under it;
- after the only credential read: the entity matches `--confirm-entity`, the project is
  `shreetbohara-quinstreet/Faultlab`, the configuration hash is `2cf63e93…` with the frozen Mechanic settings, and
  the Mechanic role resolves to `deepseek-ai/DeepSeek-V4-Pro-0813`;
- the stop handlers are installed; a stop that has already arrived refuses before the claim; the list of earlier
  runs is unchanged since the offline checks.

**Tests.** `backend/tests/experiments/test_slot2_hidden_probe.py` covers each refusal above, each stop, the
read-out rules and their boundaries, the imported parts this phase depends on, and the Phase 25 identity of C and
N (§17 for the count). Round 1's run-safety lens ran a mutation check (46 mutants, 35 killed); every survivor
that was not equivalent now has a test, and the check was re-run after the round-1 fixes with new mutants of the
round-1 code (Review log, round 1). Review round 2's fixes got their own mutation check (30 mutants of the round-2
code, all killed after two tests were added; Review log, round 2), and one test runs the owner's-answer gate on
this file's real text.

## 12. Runbook

This probe drives neither the lab backend nor the simulator; it calls W&B Inference directly from one process.

| check (origin) | here |
|---|---|
| `check_ingestion_health.py` (Phase 12) | not required: no Weave traces. Harmless to run |
| `start-simulator.sh`, dashboard closed, `loop_latency.py` (Phase 19) | not applicable: no worlds, no lab requests beyond the read-only status GET |
| "restart both services deliberately" | not applicable; **do not** stop or restart :8000, :8001 or :5173 |
| configuration hash `2cf63e93…` | enforced by the harness, at plan time and after the credential read |
| code freeze `8994e962…` | enforced in part (§2); `gate_freeze.py` is not run |
| `check_clock_drift.py` afterwards | not applicable: no world, no tick |
| one paid run at a time | enforced (§11); also confirm by hand that no Phase 28 or 30 run is live and no other agent is working in the repository |
| mains power and no OS stop | as Phase 25 §12: `pmset -g batt` must show `Now drawing from 'AC Power'` (`caffeinate -s` prevents sleep only on mains power); `pmset -g sched` lists no shutdown, restart or sleep in the next three hours; automatic macOS update installation off or none pending; the command typed in a terminal window the operator keeps open (any SIGTERM is an operator stop and forfeits the round-1 fallback) |
| budget | reconcile `memory/context/runtime-and-evidence.md` before launch |
| launch order (review round 1) | **launch before any `backend/app` change**, in particular Phase 28's build (`PHASE28_DESIGN.md` plans Phases 29 and 30 first). After such a change the configuration pin `2cf63e93…` refuses at plan time, and this phase needs new pins and a new review |

**Steps.**
1. **Review.** Rounds 1 and 2 have run (Review log) and every finding of both is applied. A **round 3 on the
   round-2 changes alone** is recommended before closing (pitfall 74: a fix can create the next failure mode; the
   round-2 reviewer asked for one on its finding 2, the already-proposed set). The owner decides whether the phase is
   worth its bound given §9.3's power and predicted dependence (§18 question 1), and answers it in the owner's own
   words (step 3).
2. **If the harness changes,** its sha256 and the plan hash change. Then, from the repository root: write a new dry
   plan to a new directory (round 1 used `--write-plan artifacts/phase29-2026-09-25/dry-plan-r1`, round 2
   `dry-plan-r2`; a later round uses `dry-plan-r3`, and so on); re-run `--protocol-numbers` into a new directory
   (round 2: `protocol-numbers-r2`) and check `harness_minimum_is_the_chosen_one` (point the test's `SAVED_NUMBERS`
   at it; the test also checks that the numbers record the current harness sha256); re-run the tests; update the pins
   in the status block and §2, and every figure that moved.
3. **Close the review in writing** (only after the owner answers §18 question 1 in the owner's own words):
   - **The owner's answer.** It must be the owner's own answer to §18 question 1, at least 20 characters, and not
     words the status block or the program document already hold (§11): the program-level approval "go ahead with
     whatever u recommend", or any general approval a workflow relays, is **not** an answer and the gate refuses it.
   - **The closing entry.** Add, as the last entry under `## Review log`, a heading that starts exactly
     `### Review log — closing` (a suffix such as a date may follow), and in it, on **one line of its own**, however
     long (never wrapped at the file's usual width; no list marker, bold or backticks):
     `Owner's answer to §18 question 1 (<given_by>, <date>): "<verbatim>"`, with exactly the record's `given_by`,
     `date` and `verbatim` (straight apostrophe and straight double quotes). Quote the answer nowhere in the status
     block.
   - **The status block.** Replace it so it no longer carries the review-pending phrase in any case; add the bare line
     `Reviewed for launch: harness <sha256> plan <hash>` with the final pins and nothing around it.
   - **The record.** Record `shasum -a 256 docs/part2/PHASE29_EXPERIMENT.md`; write
     `artifacts/phase29-2026-09-25/review.json` with `phase` (29), `status` ("approved"), `approved_by`,
     `owner_answer` (`question` exactly "§18 question 1", `verbatim`, `given_by`, `date`), `protocol_sha256`,
     `harness_sha256`, `plan_hash`, `phase_cap` (15.0), `reviewers` and `approved_at` (UTC).
   - The gate compares the three hashes and the cap, requires `status` "approved" and a non-empty `approved_by`, and
     checks the owner's answer as §11 says. Do not edit this file afterwards.
4. **Re-check the dry plan at $0:** `./.venv/bin/python scripts/experiments/slot2_hidden_probe.py` must print the
   plan hash in §2, `"slots_verified": 52` and `"passed": true`.
5. **Re-run the tests** from `backend/`, with the skip report:
   `../.venv/bin/python -m pytest -q -rs -p no:cacheprovider tests/experiments/test_slot2_hidden_probe.py`.
   It must print **`136 passed` with nothing skipped** (update the count if tests are added). Sixteen
   tests, including every live-path safety test, skip without failing when the store is missing or the tree is
   not configuration `2cf63e93…` (counted with a scratch copy pointed at a missing store: 120 passed, 16
   skipped); a run with any skip is not a pass for launch.
6. **Run once,** from the repository root, after the checks above and
   `ps -axww -o pid=,command= | grep -- --execute-live | grep -v grep` listing nothing:
   ```
   cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
   nohup caffeinate -is ./.venv/bin/python scripts/experiments/slot2_hidden_probe.py --execute-live \
     --confirm-entity shreetbohara-quinstreet --out artifacts/phase29-2026-09-25/live \
     --expect-plan-hash <plan hash from §2> \
     --expect-harness-sha256 <harness sha256 from §2> \
     --expect-protocol-sha256 <sha256 from step 3> \
     >> artifacts/phase29-2026-09-25/live-runner.log 2>&1 &
   ```
   Stop only with `kill -TERM <pid from the claim>`; either kind of stop is an operator stop (§8.6). Do not open
   `responses.jsonl` or run `--readouts` before the run has ended. Requests run one at a time; the worst case is
   300 attempts × 20 s ≈ 100 minutes, plus waits.
7. **Afterwards:** `--readouts artifacts/phase29-2026-09-25/live` must equal `readouts.json` when the run ended
   normally; add `charged_upper_bound` to the ledger; write `PHASE29_RESULTS.md` from `readouts.json` only, quoting
   both arms' decisions and part-verdicts with their basis and failed conditions, D_X and D_C, the working-share
   gain and both sign tests, the invalid and harmful figures, each arm's per-draw WORKING rate with its interval,
   C's firing rate and the calibrated-range flag, the dependence on Phase 25, the determinism read-out, the
   per-arm arrival counts and `run_end`. Beside any round-1 decision, quote the all-rounds partial contrast. If a
   claim was closed with `--finalize-abandoned`, tell the Phase 28 and 30 operators. Since review rounds 1 and 2,
   also quote, per arm: the novel and already-proposed DISTINCT counts (against the plan's 35 policies) and the
   policy concentration; the re-draws of a certified policy, on their own line; the WORKING and novel WORKING rates
   with the Wilson interval that counts each linked group once beside the Wilson interval over draws (and any
   bootstrap reported, saying which were withheld below 10 groups); WORKING draws per WORKING policy; the invalid
   split by what a study would repair; the calibrated-range reading from C alone (C's point rate and upper bound,
   with the pooled rate only as a descriptive figure); and every wording rule the statement printed, verbatim.

## 13. What each result would and would not mean

**`RECOMMEND_FOR_A_LATER_LOOP` for N.**
- **It would mean:** on these 26 stored slot-2 requests, with the prior candidate hidden, at temperature 0, **in
  this run** the Mechanic's proposal differed from **this study's own** slot-1 policy in at least 70% of draws and
  at least 30 points more often than the unchanged request's (observed rates, D1 and D2; not a shown true gain of
  0.30, §8), more often across prompts (D3); its first-attempt invalid output was not shown to rise; its share of
  WORKING draws exceeded C's by at least 3 over the 24 eligible prompts, across prompts at p < 0.025; and at most
  half of its firing proposals carried a declared harmful side rule, not more often than C's.
- **It would not mean:** a higher certification yield (no episode ran; the source gate and validation are
  single-shot stages, pitfall 71); that the new policies qualify, pass validation or are safe; anything about new
  studies (§5); anything held-out, ACCEPTED or certified.

**The same for NT,** with "at temperature 0.4" added. It would also make a per-slot Mechanic temperature a
candidate change.

**Both arms recommended.** This phase prefers neither. The N-against-NT figures are descriptive; a later loop that
wants one of them chooses in its own declaration and says why.

**`duplicates_cut` SHOWN, `yield_gain` NOT_SHOWN** (the expected result for N if Phase 25's single draws are
representative, §9.3). It reads, narrowly: **with the prior hidden, slot 2's proposal differs from this study's own
slot 1** on these prompts, more often than the unchanged request's, without a shown rise in first-attempt invalid
output. It does **not** say slot 2 is a new or a second real draw (review round 1). DISTINCT excludes only this
study's slot 1; in Phase 25, 15 of N's 25 distinct draws were a policy **another** in-scope v4 study had already
proposed on this same source case (14 a census slot 1 that ran there and did not qualify; 1 the certified
`5735a918…`), and a real loop's DUPLICATE rule would not catch them (§5). So:
- **any cost-model use rests on the novel DISTINCT and the novel WORKING figures** (§8.5; novel against the 35
  policies the in-scope v4 studies proposed, review round 2), with the Wilson interval that counts each linked
  prompt group once: slot 2 counts as a second draw only at the novel DISTINCT rate, and as a second chance at a
  **new** working repair only at the novel WORKING rate, never at D_X. A WORKING draw that re-draws a certified
  policy (reported on its own line) is not a new repair: a loop would re-run a policy it already certified;
- a gain in WORKING proposals large enough for this size to see was not shown. That is not "no gain": the arm's
  WORKING and novel WORKING rates and their group Wilson intervals say how large a gain remains possible;
- if the re-measurement rule fired (§8.5, predicted for N in §9.3), the result is a same-prompt re-measurement of
  Phase 25's N draws, not an independent confirmation, and the results say so in those words.

It is not a recommendation: the decision stays `NOT_RECOMMENDED`.

**`duplicates_cut` NOT_SHOWN.** The failed conditions say which: D1–D3 (with repeats, the hidden arm does not
reliably leave slot 1's policy, so Phase 25's 0 of 26 did not hold up), or I1–I2 (it does, but by trading
duplicates for invalid output). An I1–I2 failure is on **first attempts** (§8.2): the invalid split says how much of
the excess a study would not repair, and the results quote it beside the failure; it does not by itself show that
adoption would raise invalid output.

**N and NT differ.** For example, NT's `duplicates_cut` NOT_SHOWN on I1–I2 while N's is SHOWN would mean that 0.4
still trades validity for diversity on these prompts, as 0.7 did in Phase 25. It would not show that 0.4 is worse
than N in general: the N-against-NT contrast is descriptive, with no declared test.

**`yield_gain` SHOWN on W1–W2 but the harm guard FAILs.** Hiding the prior raises firing proposals, and too many of
them carry a declared harmful side rule for adoption. A later loop would then need to deal with the side rule
first; this phase does not say how.

**`INCOMPLETE`** (after the fallback too, or after an operator stop). No evidence either way for that arm.

**A round-1 decision** (`basis: round_1_only`). The same rule on one draw per prompt, with the minimums of §9.1
and §9.2 for that size. Its yield power is lower still (§9.3), and the all-rounds partial figures are quoted beside
it.

**The dependence figure** (a fixed rule since review round 1, §8.5). If at least half of a hidden arm's received
draws re-draw Phase 25's N policy for the same prompt, that arm's duplicates-cut result is **a same-prompt
re-measurement of Phase 25's N draws, not an independent confirmation**, and the results use those words. §9.3
predicts 0.73–0.82 for N. Below half, the draws are fresh even though the prompts are not.

**C's firing rate above 0.10.** The working claim's false-alarm rate is then outside its calibrated range (up to
about 0.07 at 0.20, §9.2), and any `yield_gain` SHOWN must be quoted with that caveat. If only C's own 95% upper
bound is above 0.10, the range is **not confirmed**, and that is quoted instead (§8.5; read from C alone since review
round 2, and expected on about a quarter of SHOWN claims even with C's true rate at 0.02, §9.2). The pooled X-and-C
rate is descriptive and never changes the wording. The declared verdict stands.

## 14. Limits

- **The hypothesis-generating prompts are the test prompts** (§5). Fresh, repeated draws against a concurrent
  control are a real test of "on these prompts", not of new studies.
- **Development data only,** from two runs of one configuration. Nothing here bears on held-out safety.
- **A replay of one proposal step.** No episode runs.
- **26 prompts, 3 draws each, and fewer independent prompts than that** (22 slot-1 policies, and one hidden-arm
  policy can supply many prompts: 7 of 26 in Phase 25). The sign tests treat prompts as independent; the clustered
  sign test beside the distinct one is descriptive. Wilson and Newcombe intervals over draws understate
  uncertainty; the Wilson interval that counts each linked prompt group once (§8.5) is the one a cost model uses.
  Linked groups can be few (Phase 25's N: 6), so the percentile bootstraps are withheld below 10 clusters.
- **"Distinct" is not "new"** (review rounds 1 and 2, §5). A distinct draw may be a policy another in-scope v4
  study already proposed, in either slot, on the one source case all 26 prompts share: a census slot 1 that ran
  there and did not qualify, a historical slot 2, or a certified repair. The novel split in §8.5, against all 35
  such policies, is the read, with certified re-draws on their own line. "Novel" still means only "not proposed by
  an in-scope v4 study"; a policy proposed elsewhere in the store (another configuration) can count as novel here.
- **A likely re-measurement for N** (§9.3): at temperature 0, most N draws are expected to repeat Phase 25's N
  policy for the same prompt.
- **Power for yield is low** (§9.3). At a per-draw WORKING rate near Phase 25's single-draw estimate for N, the
  yield claim is nearly unreachable.
- **The calibration covers its stated models.** Its grid stops at a common firing rate of 0.10; outside it the
  worst false-alarm rate is about 0.07 (§9.2), and the read-out flags a C outside that range, from C's own draws.
- **"Distinct" is by policy hash:** a trivially different policy counts. WORKING is the yield-relevant read.
- **The harm model in the simulations is the store's**; a new arm may write harmful policies at another rate. The
  auditor sees two harm patterns only.
- **One temperature for NT** (0.4), declared, not tuned.
- **No format repair:** the invalid rate is the first-attempt rate; the study's final rate would be lower. I1 and
  I2 therefore overstate what adoption would see; the split in §8.5 says by how much at most (§8.2).
- **A study whose slot 1 never ran is outside the population** (review round 1). If slot 1 produced no candidate
  that ran (an invalid model proposal, `completion_study.py` line 412, or an invalid or stale policy, line 419),
  the study goes on with no feedback rows (only line 431 adds them), and with `candidate_history = []` slot 2's
  request would be **byte-identical** to slot 1's, which at temperature 0 tends to return the same output. Every
  census study's slot 1 ran on the source case (`census_facts`: 26 of 26), so this probe cannot see that case;
  §16 says how an adoption must handle it.
- **Provider nondeterminism and time** are not controlled; the served model is recorded, not enforced.
- **The dollar figures are conservative bounds.**

## 15. No tuning, no leakage, and what must not happen

- Results are written only under `artifacts/phase29-*`. They never enter a study and are never shown to any model.
- **The arms, NT's temperature (0.4), every threshold, both working minimums (3 and 1), both α levels and the
  fallback rule are fixed now.** Another value chosen after seeing these results is a new, declared phase that
  reports this one beside it.
- No edit to `backend/app`, the Phase 25 harness, this harness, or this file after the review record is written.
- No file named `slot2-hidden-probe-manifest.json` or `claim-*.json` saved under `artifacts/` except by the
  harness.
- No re-run after a run that delivered anything; no resumption or continuation; no change to the read-outs once
  data exists.
- Phase 25's draws are never pooled with this phase's.
- Nothing is called ACCEPTED, certified, REJECTED or promoted.

## 16. What adopting an arm would change in `backend/app` (described, not made)

This phase changes nothing under `backend/app`. A later loop that adopts an arm would need, each under its own
declaration, a new configuration, a new freeze and its own review:
- **N:** in `completion_study._execute`, slot 2's proposal context sets `candidate_history` to `[]` instead of
  `deepcopy(record['candidates'])` (line 405 today), **but only when slot 1's candidate actually ran on the source
  case, i.e. when `feedback_rows` is not empty** (review round 1). When slot 1 produced no candidate that ran (an
  invalid model proposal, line 412, or an invalid or stale policy, line 419), no feedback rows are added (only line
  431 adds them), so hiding the history would make slot 2's request byte-identical to slot 1's, which at
  temperature 0 tends to return the same output (Phase 25's C matched its historical policy in 57 of 78 re-sends);
  today slot 2 at least sees the rejected attempt. In that case the adoption keeps the history. This probe cannot
  measure that case (§14: every census slot 1 ran). The study's DUPLICATE rule is unaffected: it compares policy
  hashes through its own `seen` set, not through `candidate_history`; it also means a slot 2 that re-proposes a
  policy **another** study already proposed (one that ran and did not qualify, or a certified repair) would be run
  again (§5). The stored `completion_proposal_inputs` record
  would then carry the empty history, which keeps Phase 25's verification checks meaningful.
- **NT:** also a per-slot Mechanic temperature. Today `RuntimeProvider.complete` sends
  `MODEL_REQUEST_SETTINGS["temperature"]` (0) for every role (`runtime.py` line 154), and the configuration records
  `model_settings_by_role`; a slot-2 temperature would change both, and therefore the configuration hash.
- **Transfer check ($0):** the later loop's slot-2 request must be byte-identical to this probe's arm request on
  these 26 prompts, checked with this harness's rebuild. If it is not, this phase's result does not apply. The
  check also covers the case this probe cannot see (review round 1): for a study whose slot 1 did not run (a
  constructed or stored example with no feedback rows), the adopted code must send slot 2 **with** the history, so
  that slot 2's request is not byte-identical to slot 1's.
- Nothing here touches `assess_pairs`, C1–C8 or any threshold.

## 17. Evidence files (all $0)

- `artifacts/phase29-2026-09-25/dry-plan-r2/`: `plan.json` (with `census_facts` and, since review round 2,
  `populations.already_proposed`), `dry-summary.json` (with the labelled Phase 25 planning inputs), `dry-run.out.txt`.
  **Current.**
- `artifacts/phase29-2026-09-25/protocol-numbers-r2/protocol_numbers.out.json`: boundaries, the yield null and the
  choice of both working minimums (with the cells outside the grid), power under four clustering scenarios and in
  the round-1 fallback, and the invalid, harm and duplicates-cut operating characteristics. It records the harness
  sha256 it ran with and `harness_minimum_is_the_chosen_one`. **Current.** Every figure equals the round-1 and
  pre-round-1 outputs; only the recorded harness sha256 and the added threshold keys differ (Review log, rounds 1
  and 2).
- `artifacts/phase29-2026-09-25/review-r2/`: the round-2 $0 evidence: the mutation check of the round-2 code
  (`mutate_r2.py`, `mutation-r2-results.json`, `mutation-r2-run.out.txt`), the launch rehearsal
  (`launch_rehearsal_r2.py` and its output), the calibrated-range re-simulation (`range_reading_r2.*`), the read-out
  fuzz (`readout_fuzz_r2.*`) and the linked-group check (`linked_groups_r2.*`); and, in `reviewer/`, the round-2
  reviewer's own $0 evidence, copied unchanged from its scratch folder (its launch rehearsal, the novel checks, the
  range simulation, the linked-group check, the read-out fuzz, its dry rehearsal, test re-run and guard-state
  reading).
- `artifacts/phase29-2026-09-25/tests-slot2_hidden_probe-r2.txt`: the test run after the last edit of round 2:
  **136 passed, nothing skipped** (test file sha256 `c46c8dc0…`).
- After round 1 (superseded, kept): `dry-plan-r1/`, `protocol-numbers-r1/`, `review-r1/` (round 1's
  `dup_margin_check.py` and mutation check) and `tests-slot2_hidden_probe-r1.txt` (106 passed, test file
  `56b46038…`).
- Before round 1 (superseded, kept): `dry-plan/`, `protocol-numbers/` and `tests-slot2_hidden_probe.txt` (76
  passed, test file `18651db5…`).

## 18. Questions for the review

1. **Is the phase worth its bound?** The planned bound is $11.66 under a $15 cap. The expected result for N is
   `duplicates_cut` SHOWN and `yield_gain` NOT_SHOWN (§9.3). Since review round 1 that reads only "slot 2 differs
   from this study's slot 1 on these prompts", not "slot 2 becomes a second real draw" (§13), and N's result is
   predicted to be largely a same-prompt re-measurement of Phase 25's N (0.73–0.82 of its draws, §9.3). Since review
   round 2, "novel" means none of the 35 policies the in-scope v4 studies proposed: counted that way, Phase 25's N
   had **0 novel WORKING draws of 26** (its one WORKING draw re-drew the certified `5735a918…`, §5). **The phase's
   new information therefore comes mainly from NT and from the novel WORKING estimates of both arms**, with the
   Wilson interval that counts each linked prompt group once. Is that answer worth buying before Phase 28's loop, or
   should the money go to Phase 28? **The owner answers in the owner's own words**, at least 20 characters; the
   program-level "go ahead with whatever u recommend" (or any general approval a workflow relays) is not an answer
   to this question, and the gate refuses it (§11). The answer is recorded verbatim in the review record and stands
   on its own line in the Review log's closing entry (§12 step 3).
2. **The invalid guard's new sign test (I2).** At an X invalid rate of 0.03 against C at 0 (Phase 25's C), the guard
   fails 4–8% of the time, and 12–30% at 0.05 (§9.4). Both I1 and I2 count first attempts, which a study would
   partly repair (§8.2), so a FAIL overstates what adoption would see; the invalid split is reported beside it. Keep
   I2, or keep only Phase 25's margin?
3. **The harm contrast (H2)** will often be not computable, because C rarely fires (§8.4). Keep it as a guard with
   small reach, or drop it and rely on H1?
4. **A mutation check.** Answered in round 1: the run-safety lens ran 46 mutants of this harness's run-safety code
   (35 killed); this pass added tests for every non-equivalent survivor and re-ran the check, with new mutants for
   the round-1 code (§11, Review log). Round 2's code got 30 mutants of its own, all killed (Review log, round 2).
   The read-out code (`arm_decision`, `invalid_sign`, `fisher_greater`) was checked by the statistics lens against
   §8 and by its own $0 re-simulations; no mutant was run on it.
5. **The prompts that suggested the hypothesis test it** (§5). No other slot-2 prompt exists. Is "fresh, repeated
   draws on the same prompts, against a concurrent control" an acceptable test, with the dependence figure beside
   it?
6. **NT's temperature (0.4)** is a round value chosen without data (§6). Accept it, or drop NT and keep the phase
   to one treated arm (which would also remove the Bonferroni split)?

## 19. Build note (2026-09-25, before any review)

The first draft of §9.3 quoted a power table from a scratch run made while the harness still carried a placeholder
working minimum (2/3), before the calibration chose 3. The yield-null, round-1, guard and duplicates-cut tables of
that run are identical to the saved output (they do not depend on the minimum); the power table is not, and it
overstated power by up to 0.18. §9.3 now quotes the saved output only.

A consistency pass against the harness, the dry plan and the saved protocol numbers (before any review) corrected
the wording of: how missing draws enter each condition (§8); which contrast carries the clustered sign test (§5,
§8.5, §14); the study ids of the two prompts whose slot-1 policy fires (§5); the worst yield-null cell for the sign
test alone, and the cells outside the grid (§9.2); and the simulation settings behind the guard tables (§9.4). No
threshold, arm, pin or computed figure changed.

## Review log

### Review log — round 1 (2026-09-25): two lenses, both "run with changes"

Reviewers: statistics, and run safety. They reviewed harness `d42ae0a4…`, plan `91d4b8e0…`, tests `18651db5…` and
this file at `57d4ea5d…`. Both returned RUN_WITH_CHANGES: 2 major and 10 minor findings. Neither edited a repository
file, made a paid, provider, model or W&B call, or read `.env`, `checks.py`, heldout-2 or any audit file; the store
was read only in read-only mode. **Every finding was applied; none was declined.** The fixes changed the harness, so
its sha256, the plan hash and the protocol numbers were recomputed (§2), and a round 2 on these changes alone is
recommended before the review is closed (pitfall 74). The owner has not yet answered §18 question 1, so the review
is **not closed**: no review record exists, and the status block still carries the review-pending phrase.

**Statistics lens**

| # | severity | finding | disposition |
|---|---|---|---|
| S1 | major | "Distinct" means only "not this study's slot-1 policy", not "new". In Phase 25, N's 25 distinct draws were only 14 policies (one on 7 of 26 prompts), and 14 of them equal another census study's slot-1 policy, already proposed and failed on the same source case; yet §13 said a `duplicates_cut` of SHOWN "would support counting slot 2 as a second real draw" in a cost model (pitfall 70 one level up). §5 understated the prompts' dependence, and §9.3 offered a Wilson interval over draws to cost models | **Fixed.** New descriptive read-outs, declared before any Phase 29 data (§8.5): per arm, the policy concentration of DISTINCT draws; the DISTINCT, firing and WORKING draws that equal any census slot-1 policy against the novel ones; WORKING draws per WORKING policy; and clustered intervals (bootstrap by prompt and by linked prompt group, and a Wilson interval counting each linked group once) beside the Wilson interval, for DISTINCT, novel DISTINCT, WORKING and novel WORKING. The statement prints each arm's novel and already-proposed counts and "DISTINCT means only 'not this study's own slot 1', not 'new'". §13 rewritten: SHOWN reads "slot 2 differs from this study's slot 1", and any cost-model use rests on the novel and WORKING figures. §5 carries the census facts (one source fault spec, content hash `c585d162…`; slot 1 `NO_CHANGE` 23, `INCOMPLETE` 3, none qualified; in the hashed plan as `census_facts`) and Phase 25's concentration as a labelled planning input, computed by the harness's own code (`phase25_planning_inputs`, dry summary only) and reproducing the reviewer's figures exactly (N 25 draws, 14 policies, largest 7 prompts, 14 already proposed, none firing; C 1 of 20, T 2 of 49, H 0 of 14). The reviewer's spec hash `1b1b3529…` uses another hash convention; both count one spec across 26 prompts. The DUPLICATE rule's lines are 391, 422 and 425 (the finding said 421–423). Tests: `test_policy_concentration_separates_policies_already_proposed_as_slot1_from_novel_ones`, `test_clustered_intervals_are_wider_than_the_wilson_interval_when_draws_cluster_and_are_deterministic`, `test_the_phase25_planning_inputs_reproduce_the_figures_the_protocol_quotes`, and the census facts in `test_the_plan_is_phase25s_census_with_three_arms_and_every_slot_verifies` |
| S2 | minor | At $0 one can predict that most N draws will repeat Phase 25's N draws (temperature 0: 0.73–0.82 of re-sends return the same policy), so N's duplicates-cut test largely re-measures the draw that suggested it, yet the reading was left open; N's repeats add little | **Fixed.** §9.3 states the predicted dependence, 0.73–0.82, as a planning input (computed by `phase25_planning_inputs`: 57 of 78, 59 of 78, 64 of 78). A fixed wording rule (§8.5): at a dependence share of at least 1/2, the statement and the results call that arm's duplicates-cut result "a same-prompt re-measurement of Phase 25's N draws, not an independent confirmation". §18 question 1 now says the phase's new information comes mainly from NT and the WORKING estimates. Test: `test_the_re_measurement_wording_rule_fires_at_half_of_the_received_draws` (39 of 78 fires, 36 of 78 does not; the decisions are unchanged by it) |
| S3 | minor | If slot 1 produced no candidate that ran, no feedback rows are added, so adopting N would make slot 2's request byte-identical to slot 1's; the probe cannot see this case | **Fixed (described; no `backend/app` change here).** §14 states the case is outside the population (every census slot 1 ran: `census_facts` 26 of 26). §16: an adoption hides the history only when `feedback_rows` is not empty, else keeps it; the $0 transfer check covers that case. The harness's `adoption` rule text says the same |
| S4 | minor | I1 and I2 count first attempts that a study would partly repair (one format repair for schema failures), so a guard FAIL does not show adoption would raise invalid output; I2 is new and strict | **Fixed.** Invalid draws are reported in two groups per arm (`invalid_by_what_a_study_would_do`): schema failures (sent back once for a format repair) and empty responses, candidates the study's policy check rejects, and stale parents (not repaired), with the not-repaired rate and its excess over C. §8.2, §9.4, §13 and §14 say I1 and I2 measure first attempts and overstate what adoption would see; §18 question 2 carries it. The guard itself is unchanged. Test: `test_invalid_draws_are_split_by_what_a_study_would_do` |
| S5 | minor | §8 claimed any false positive "at most 0.05" without the calibrated-range condition, and the range flag rests on C's point estimate over 78 clustered draws; §13 read D1 and D2 as facts about true rates | **Fixed.** §8's sentence is qualified "within the calibrated range (a common firing rate of at most 0.10)", with the rates outside it. The range flag now reads C three ways (point, Wilson 95% upper bound, pooled X-and-C rate; `calibrated_range`: within, not_confirmed, outside), and the statement quotes the caveat beside any SHOWN working claim. §8 ("What the bars are") and §13 describe D1 and D2 as observed rates; a $0 re-check with the harness's own code (`review-r1/dup_margin_check.out.json`) confirms the reviewer's figures: SHOWN 24–33% at a true gain of 0.25 and 34–36% at exactly the bars. Tests: `test_the_calibrated_range_is_read_three_ways` |
| S6 | minor | The pinned Phase 25 harness ran at import before its hash was checked, and the later check hashed the file on disk, not the bytes that ran | **Fixed.** The bytes are read once and hashed before any of them run; a loader that serves exactly those bytes (never the file again, never a bytecode cache) runs them; a mismatch refuses at import with nothing run. `phase25_harness_problem` still re-checks the file on disk before any plan or send. Test: `test_the_code_that_ran_is_the_pinned_code_and_a_changed_file_refuses_at_import` (a changed copy refuses and its code never runs; an unchanged copy loads; a file edited after import is caught) |

**Run-safety lens**

| # | severity | finding | disposition |
|---|---|---|---|
| R1 | major | The live gate did not check the owner's approval: `check_review` compared only the three hashes and the cap, so a bare record could launch without the owner answering §18 question 1 (Phase 27 and Phase 30 enforce the owner's answer) | **Fixed, as Phase 30.** `check_review` also requires `status` exactly "approved", a non-empty `approved_by`, and `owner_answer` with non-empty `verbatim`, `given_by` and `date` whose `verbatim` words the protocol quotes; each refuses before the credential read and any claim, and the run manifest records the approval (`review`). §11 and §12 step 3 updated. Tests: `test_the_review_record_must_say_approved_name_the_approver_and_carry_the_owners_words` (14 refusals, one per field and form), `test_the_owners_words_must_be_quoted_in_the_protocol_and_a_complete_record_passes` (the reviewer's bare record now refuses), and the end-to-end test's manifest check |
| R2 | minor | Mutants S1 (the run's guard at $15, not the phase remainder) and S5 (an unreadable earlier charge read as $0) survived | **Fixed.** The reviewer's tests added: `test_the_spend_guard_during_a_run_uses_the_phase_remainder` ($0.35 left: 7 attempts, `spend_guard`), `test_an_earlier_run_without_a_readable_charge_blocks` (missing, null, text, negative and NaN) |
| R3 | minor | Mutants R3 (an unknown delivered count passes), R5 (`mkdir` accepts an existing directory), R6 (the claim written with `os.replace`) and I6 (a `ps` failure read as "dead") survived | **Fixed.** Tests: `test_an_earlier_run_whose_delivered_count_is_unknown_blocks`, `test_an_output_directory_that_appears_during_the_launch_checks_refuses_before_the_claim`, `test_a_claim_name_a_racing_launch_took_is_never_overwritten`, `test_a_claim_process_whose_command_cannot_be_read_counts_as_alive` |
| R4 | minor | No test showed that another paid run started from the same shell is seen (mutant O12; Phase 26 round 3, row 3a) | **Fixed.** `test_a_paid_run_started_from_the_same_shell_is_seen` (shell, this process, its caffeinate child, a sibling paid run: only the sibling is reported) |
| R5 | minor | `claimed_output` accepted `..` as a run name (Phase 25's refuses `.` and `..`), so a hand-written claim could lead `--finalize-abandoned` outside a run directory | **Fixed.** `claimed_output` refuses `.` and `..`. Test: `test_a_claim_never_names_dot_or_dot_dot` |
| R6 | minor | 13 of 76 tests, including every live-path safety test, skip silently without the store or on another tree; step 5 did not require "nothing skipped"; the runbook did not say to launch before Phase 28's `backend/app` change | **Fixed.** §12 step 5 runs with `-rs` and requires the full count passed with nothing skipped (now 106; without the store 15 of them skip); the runbook table adds the launch-order line (launch before any `backend/app` change, or re-pin and re-review) |

**Mutation check, re-run after the fixes** (`review-r1/mutation-r1-results.json`: the reviewer's 46 mutants, 44 in
its main list and its two extra process-guard mutants, plus 12 new mutants of the round-1 code, each run against
the full test file beside the network-blocking conftest): **58 mutants, 54 killed, 4 survived.** Of the reviewer's
46, 42 are now killed (35 before), including all seven survivors that were not equivalent (S1, S5, R3, R5, R6, I6
and O12); and all 12 new mutants of the round-1 code are killed (each
approval check, the `..` refusal, the re-measurement threshold, the census set, the invalid split, the range
reading and its caveat, the linked prompt groups, and the manifest's approval record). The 4 survivors are the ones
the reviewer judged equivalent or harmless: S7 (`run_live` re-checks the budget itself), G6 and G7
(`s2.check_pins` already refuses a wrong configuration hash or Mechanic model before those later checks are
reached), and O10b (ancestors only: harmless under the token rule, because the caffeinate helper's first token is
not python). The unmutated copy passed 105 with 1 skip, the protocol-numbers test, whose file was written after
the run.

**Also noted, not a harness defect:** the run-safety reviewer found the Mac on battery ("Battery Power", 95%) during
the review, so the runbook's AC-power check would have failed then. It is checked at launch (§12).

**Round 1 fix pins:** harness `b4153f914375969fb093808b03f1eb485969e89bf58728e94349c0fad15778f6`, plan
`5b5ef67d0e360cadf75b8a66ab4f8dd5073794ebd374930bcfb7ca23778280e7`, tests `56b46038212d220e9624305c5f9b1fc8f6b3cd9f844361d4bbdb36bc8e566be4`. Tests after the last
edit: **106 passed, nothing skipped** (`artifacts/phase29-2026-09-25/tests-slot2_hidden_probe-r1.txt`). The
protocol numbers were recomputed with the new harness (`protocol-numbers-r1`); every figure equals the pre-round-1 output (`protocol-numbers/`); only the recorded harness sha256 and three added
threshold keys (`re_measurement_share_min`, `bootstrap_resamples`, `bootstrap_seed`) differ, so no figure in §9
moved. The 234 planned requests are identical to the pre-round-1 plan's; the plan hash moved only because the
harness sha256, the rule texts, the thresholds and `census_facts` are part of the plan.

### Review log — round 2 (2026-09-25): the round-1 changes, "run with changes"

One reviewer, on the round-1 changes alone (pitfall 74). It reviewed harness `b4153f91…`, plan `5b5ef67d…`, tests
`56b46038…` and this file at `335c5b12…`, and returned **RUN_WITH_CHANGES: 2 major and 3 minor findings**. It edited
no repository file, made no paid, provider, model or W&B call, never passed `--execute-live`, and never read `.env`,
`checks.py`, heldout-2 or any audit file; the store was read only in read-only mode, with no bytecode written. Its
$0 evidence is copied, unchanged, into `artifacts/phase29-2026-09-25/review-r2/reviewer/`. **Every finding was
applied; none was declined.** The fixes changed the harness, so its sha256, the plan hash and the protocol numbers
were recomputed (§2). **A round 3 on these changes alone is recommended before the review is closed** (the reviewer
asked for one on finding 2). The owner has not yet answered §18 question 1, so the review is **not closed**: no
review record exists, and the status block still carries the review-pending phrase.

| # | severity | finding | disposition |
|---|---|---|---|
| 1 | major | Round 1's fix R1 could be passed with no answer at all. `check_review` tested only that the record's `verbatim` occurs **somewhere** in this file, and the status block already quotes the program-level approval "go ahead with whatever u recommend", the very words the tests used as the owner's answer (and the words the workflow relays as the user's request). The reviewer's $0 launch rehearsal on the real plan, harness and protocol text passed every offline gate with that phrase as the answer and **no closing entry**, and also with the one-letter "answer" `N`. §11 and §12 step 3 said "in the Review log's closing entry", but the code never checked where. Round 1's mutant A4 (the quote check removed) was killed only because the test's synthetic protocol lacked the phrase | **Fixed.** `owner_answer` now also holds `question`, exactly `§18 question 1`. `verbatim` must be one line with no leading or trailing space, at least **20 characters**, and not words the status block or `EXPERIMENT_PROGRAM_PHASES_28-31.md` already hold (compared on letters and digits only, so punctuation, case and spacing cannot slip the program phrase through; an unreadable program document refuses). The words must stand **exactly once, on one bare line, in the Review log's closing entry** (after the last `## Review log`, the last heading under it starting `### Review log — closing`, up to the next heading), reading `Owner's answer to §18 question 1 (<given_by>, <date>): "<verbatim>"`. §11, §12 step 3 and §18 question 1 say so. Tests: the owner's quote in the tests is no longer the program phrase; `test_the_review_record_must_say_approved_name_the_approver_and_carry_the_owners_words` (21 cases, 9 new), `test_the_owners_words_must_stand_on_one_bare_line_of_the_closing_entry` (12 placements), `test_the_owners_words_must_not_be_in_the_status_block_or_the_program`, `test_a_complete_record_and_closing_entry_pass_and_a_bare_record_does_not`, and **`test_the_owners_answer_gate_on_the_real_protocol_text`**, which runs the gate on this file's real text closed as step 3 says: the reviewer's cases A (program phrase, no closing entry) and B (`N`) refuse, the program phrase on a proper closing line refuses (by the status block, and with the status block's quote removed, by the program document), the owner's words outside a closing entry refuse, a wrapped answer refuses, and a proper close passes. Round 1's substring check, restored as a mutant, now fails 22 tests including that one |
| 2 | major | The "novel" split counted a draw as already proposed only if it equalled a **census slot-1** policy. A study reaches slot 2 only after slot 1 did not qualify, so that set leaves out, by construction, every slot-1 policy that qualified (all four certified repairs) and every historical slot-2 policy. Re-draws of known policies, even certified ones, were labelled novel and novel WORKING, and §9.3 and §13 named exactly those figures for a later cost model. Phase 25's N: its only "novel WORKING" draw was `5735a918…`, the policy Phase 23 certified (slot 1 of study `f6a6612a…`, outside the census); against all 35 policies the 39 in-scope v4 studies proposed, N has 10 novel draws, not 11, and 0 novel WORKING, not 1; C 10 novel, not 19. §13's "already failed" also overstated: 3 of the 26 census slot 1s ended INCOMPLETE | **Fixed.** "Already proposed" is now every candidate policy hash proposed, in either slot, by the in-scope v4 studies: **39 studies, 35 policies** (33 slot-1 and 26 slot-2 proposals; the 33 studies that proposed were all asked about source spec `c585d162…`). The set, its counts, the source-spec count and the **four certified policies** (read from the pinned Phase 17 and 23 run manifests, checked against the harness's declared four, and required to be in the set) are in the hashed plan (`populations.already_proposed`). The read-outs take the set from the plan (`compute_readouts(..., already_proposed=...)`, which refuses a missing or malformed record, so no read-out is ever computed against an empty set); the novel split, the novel clustered rates and the statement use it; **re-draws of a certified policy are reported on their own line** (`certified_policy_redraws`, and in each arm's statement line); round 1's census-only count stays beside it for comparison. The harness reproduces the reviewer's figures exactly (§5): N 15 already proposed (14 census slot-1, 1 certified), 10 novel in 8 policies, 0 novel WORKING; C 10 of 20 novel; T 46 of 49; H 14 of 14. §5, §7, §8.5, §9.3, §13, §14, §16 and §18 corrected ("did not qualify", not "failed"). Tests: the planning-input test (now on the real plan: 15, 10, 0 and 1), `test_policy_concentration_separates_policies_already_proposed_from_novel_ones` (a policy proposed outside the census is not novel), the census test (39, 33, 35, 4, one spec), `test_the_read_outs_refuse_a_missing_or_malformed_already_proposed_record` (6 cases), `test_the_certified_policies_come_from_the_pinned_run_manifests`, `test_the_already_proposed_record_holds_both_slots_of_every_study_and_every_certified_policy`, and the statement test (27 WORKING draws, 0 novel, 27 certified re-draws when the fake WORKING policy is a certified one; the decisions do not move). **A round-3 review of this change is recommended**, as the reviewer asked |
| 3 | minor | The gate could refuse a correctly approved launch: this file is hard-wrapped at about 118 characters, and a long answer wrapped across two lines no longer matched (the reviewer's case D, a 170-character answer); step 3 did not warn about it | **Fixed** by finding 1's rule: the answer stands on one line of its own, however long, and step 3 says so in those words. A wrapped answer still refuses (fail closed), now with a message that names the line and says "never wrapped". Tests: the wrapped case in the placement test and in the real-text test; a 181-character answer on one line passes |
| 4 | minor | The three-way calibrated-range reading used the pooled X-and-C firing rate. The calibration is about the null, where both arms share C's rate; when the working claim is SHOWN, X's own gain inflates the pooled rate, so the caveat mostly restated the claim (not confirmed on 64 of 113 to 367 of 367 SHOWN claims with C at 0.02, inside the range). Round 1's point-only flag was still reported and could disagree with the reading | **Fixed.** The range is read **from C alone**: `outside` when C's point rate is above 0.10, `not_confirmed` when only C's Wilson 95% upper bound is; the pooled rate is reported as `pooled_rate_descriptive` and drives no wording; the old flag `C_within_the_calibrated_firing_range_descriptive` is dropped. A $0 re-simulation with the reviewer's cells and seed (`review-r2/range_reading_r2.out.json`): with C at a true 0.02, not `within` on **507 of 2,169** SHOWN claims (23%), against 1,945 of 2,169 (90%) under round 1's reading; at 0.04, 920 of 1,836 (50%). §8.5, §9.2 and §13 say that `not_confirmed` is still expected on about a quarter of SHOWN claims at 0.02, because C's upper bound passes 0.10 from 3 of 78. Tests: `test_the_calibrated_range_is_read_from_c_alone` (the pooled rate alone no longer moves the reading; SHOWN claims with C at 0 of 78, 3 of 78 and 9 of 78 read `within`, `not_confirmed` and `outside`, with the exact statement text) and the working-share test (the old flag is gone) |
| 5 | minor | Prompts linked transitively through any drawn policy can merge into very few groups (Phase 25's N: 6 groups, sizes 15, 4, 3, 2, 1, 1), and a percentile bootstrap over G clusters has zero width at G = 1 (`cluster_bootstrap([(10, 26)])` returned [0.3846, 0.3846]) yet was offered to cost models | **Fixed.** A percentile bootstrap over fewer than **10** clusters is withheld (null), flagged in `bootstrap_withheld` with a note; cost models are pointed to the **Wilson interval that counts each linked group once** (§8.5, §9.3, §13, §14, the rule texts and the statement's basis). On Phase 25's N the linked-group bootstrap is now withheld and the group Wilson interval is [0.565, 0.998] (`review-r2/linked_groups_r2.out.json`). Tests: `test_a_bootstrap_over_fewer_than_ten_clusters_is_withheld` (G = 1: withheld, the group Wilson interval is wide and never [1, 1]; 9 against 10 clusters; 5 prompts withhold both) and the clustered-interval test |

**Mutation check of the round-2 code** (`review-r2/mutate_r2.py`, `mutation-r2-results.json`; each mutant a copy of
the harness with one change, run against the full test file beside the network-blocking conftest, as round 1): **30
mutants**, covering every new check of the owner's answer (placement removed, at least once instead of exactly once,
substring instead of a bare line, closing heading not required, first Review log instead of the last, entry running
to the end, status-block refusal, program refusal, unreadable program passing, length check removed or set to 2,
question not checked or not required, one-line check removed, no normalisation, and round 1's substring check
restored), the already-proposed set (certified-subset checks, a missing record accepted, novel against the census
only, clustered novel ignoring the set, certified line using the whole set, slot 1 only, census studies only, the
manifests not compared with the declared four, a certified policy not required in the set, the live path's
read-outs without the record), the range reading (pooled leg restored, upper bound ignored) and the bootstrap
minimum (removed, off by one). The first run killed 28; the two survivors (N8, N9: the certified-set guards had no
failing-input test) got `test_the_already_proposed_record_holds_both_slots_of_every_study_and_every_certified_policy`
and a declared-set check in the certified test, and the re-run killed **all 30** (the unmutated copy: 135 passed, 1
skipped, the protocol-numbers test, whose file did not exist yet).

**Other $0 checks of the round-2 code** (`artifacts/phase29-2026-09-25/review-r2/`, all on the round-2 harness):
- **Launch rehearsal** (`launch_rehearsal_r2.py`, the reviewer's rehearsal on the real plan, harness and protocol
  text in a scratch tree, the credential read replaced by a sentinel): the program phrase reused with no closing
  entry, on a proper closing line, and on a closing line with the status block's quote removed all refuse; `yes`,
  `N` and `N` on a closing line refuse; round 1's style of quote (not the owner line), a record without `question`
  and a wrapped answer refuse; a proper close passes every offline gate and stops at the credential read, with or
  without the program quote in the status block, as does a long answer on one line; no claim or output directory
  is ever created.
- **Read-out fuzz** (`readout_fuzz_r2.py`, the reviewer's 1,800 partial or odd runs, with the plan's set): 0
  crashes, JSON-clean under `allow_nan=False`, deterministic; so `--readouts` can always reproduce `readouts.json`.
- **The plan:** the 234 requests are identical, id for id, to the round-1 and pre-round-1 plans; the plan hash moved
  only because the harness sha256, `populations.already_proposed`, the census facts' note, three rule texts and one
  threshold key (`min_bootstrap_clusters`) are part of it. No decision rule, threshold of §8, arm or request changed.

**Also noted.** The reviewer found the Mac on battery (68%, discharging) and a dashboard polling the backend; neither
is a harness defect (the runbook's AC-power check is made at launch, and this probe sends no lab requests). Phase
30's harness (`report_narrow_probe.py`) carries the same whole-file substring check of the owner's words that this
round replaced here; it is outside this phase and was not edited.

**Round 2 fix pins:** harness `b162a7da92bcbae0fdb67b7fbf143c3251c4d4404a83d57492635a982e493a90`, plan
`2b4bc80ca217bcc5f15e1ccf269d2f9f72a6ab417292f3835193e90095cd4466`, `dry-plan-r2/plan.json`
`f37a3c65375826e1bcdae96da78a291abed07e073c4a44f3debdfc8aea6f469a`, protocol numbers
`47696e6641d257d052e783cae62262fdf7d835a55f7d8c6e4c40b2bcc6df247d`, tests `c46c8dc0295e73755dadafb294da184d10dfc7f0a48cbe03343dd2ec1e7b71f8`. Tests after the last edit: **136 passed, nothing skipped**
(`artifacts/phase29-2026-09-25/tests-slot2_hidden_probe-r2.txt`). The
protocol numbers were recomputed with the round-2 harness (`protocol-numbers-r2`); every figure equals the round-1
output (`protocol-numbers-r1/`); only the recorded harness sha256 and one added threshold key
(`min_bootstrap_clusters`) differ, and `harness_minimum_is_the_chosen_one` is true for both minimums, so no figure in
§9 moved.

## Cancellation (2026-09-25; Claude as PM, delegated by the project owner)

**Phase 29 is cancelled before any paid call.**
- **Why:** this protocol's own analysis (§9.3, §18 question 1):
  - N's expected result is largely a re-measurement of Phase 25's N;
  - Phase 25's N had **0 novel WORKING draws of 26**;
  - the phase's new information would come mainly from NT, while `yield_gain` is predicted
    NOT_SHOWN.
- **The trade-off:** the phase's $11.66 bound is better spent on Phase 28, which tests whether
  the loop can learn the upgrade-side repair.
- **What stays:** the harness, tests and reviews are kept as built, unrun. The owner-answer gate
  was never exercised.
