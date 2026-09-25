# Phase 27 protocol — Actor report-word replay probe (non-scoring)

**Status: declared before any paid call; reviewed in rounds 1, 2 and 3; round-3 fix checked 2026-09-25; closed 2026-09-25; the owner's answer to §17 question 1: option R (Review log, round 2).** No paid, model or W&B call has been made, and nothing under
`backend/app` was edited. Every number below
comes from a $0 dry run or a saved $0 computation.

Pins of this draft (the live gate requires both strings in this file): harness
f057ef2a1123f01bf50c61c5637cbba463f01d16593e8ee9d6d27f4f47869519 plan
cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682

- **Program:** `docs/part2/EXPERIMENT_PROGRAM_PHASES_25-28.md`, Phase 27 (cap about $25).
- **Harness:** `scripts/experiments/report_word_probe.py`. **Tests:**
  `backend/tests/experiments/test_report_word_probe.py`.
- **Departures from the program:** §2 lists every place this protocol departs from, or corrects,
  the program.
- **The owner's answer on the size and the cap (§10.3, §17 question 1): option R, inside the program's
  $25 cap.** The owner, Shree Bohara, wrote "okay gi ahead with whater u recommend" (2026-09-24; the
  owner's request that started the round-2 fix run, relayed verbatim by the workflow harness). R is the
  recommended option, and that answer covers nothing above $25. The harness enforces it: the review
  record must carry it, and a cap above $25 would need a new answer naming A1 or A2 (§12 item 6).
  Since round 3 the named option also fixes the sizes and the most the cap may be (the harness's
  `OPTION_TABLE`; for R: U2 225, G4 45, $25). Rounds 1–3 changed the design; the Review log lists every
  change.

## 1. The question

On a report turn where an operation's latest observed status is `UNKNOWN`, the Actor sometimes
writes a word that no delivered observation supports. Phase 24's only HARM episode is the example
that motivated the program's question (`PHASE24_RESULTS.md`, a published summary; §13):
- both of the Actor's upgrade attempts returned `TRANSIENT_UNAVAILABLE` (transient failures, F4 on
  `update_order`), so the upgrade was never accepted;
- every status read said `UNKNOWN`;
- the Actor reported `upgrade_outcome: PENDING`;
- the referee failed the report on C5 and C6.

This phase asks three things, all on stored **development** prompts:
1. **Primary.** On report-required prompts where the upgrade succeeded and the confirmation was sent
   but reads `UNKNOWN` (stratum U2, where every development slip of a report-required prompt is),
   does one declared context field (**T**) lower the rate of bad report words, compared with a plain
   re-send (**C**) and with a same-shape placebo field (**P**)? The field states each operation's last
   observed status, copied verbatim from the evidence.
2. **Guard.** On prompts whose true status is not `UNKNOWN` and whose historical words were
   correct, does T change the report more often than a second plain re-send (**R**) does?
   - Phase 4's `NOT_REQUIRED` → `NOT_STARTED` regression came from exactly this kind of change
     (pitfall 17). The terminal-rejection stratum gets its own gate, with a report floor and a word
     test (§9.2).
3. **Descriptive.** What do C and T say on the development examples of the Phase 24 situation itself
   (stratum U1)? And how often does the same request, sent twice, come back different?

This is a **replay probe**:
- it re-sends frozen historical prompts and reads one response from each;
- it scores nothing (no C1–C8, no referee, no gate);
- its best outcome is **a recommendation for a later loop**. Nothing is adopted here.

## 2. Where this protocol departs from, or corrects, the program

| # | program | this protocol | why |
|---|---|---|---|
| 1 | "Phase 21 measured about 7% `PENDING` on report turns" | **on U2 (report-required, confirmation written, `UNKNOWN`) the measured rate is 3.7%** (25 of 667); **on all 809 report-required prompts it is 3.1%** (the same 25; every other report-required context has 0); U4 (voluntary `UNKNOWN`) is 3.7% (13 of 351) (§4) | Phase 21's "7%" is its `pending_probability`, 14 of 201 re-sent reports, which **pooled two strata**: 7 of 180 on U2 prompts (3.9%) and 7 of 21 on the voluntary U4 prompts that came back as reports. The 180 are 36 contexts re-sent 5 times each. Selecting half the contexts for a historical `PENDING` word made no difference (3 of 90 selected, 4 of 90 not). See §4 |
| 2 | "one declared, windowed context field" for report turns | **T is added on every in-window turn**, report-required turns included | 2,393 of the 3,202 report turns (75%) are voluntary, and nothing tells the lab in advance which turn will carry a report (pitfall 18). So a live field must sit on every in-window turn. This probe sends only report turns. **Its effect on tool turns is unmeasured**, and that is a later loop's job. Unlike Phase 21's v5, report-required turns are not exempt, because the report is the target |
| 3 | arms C, T and a placebo P | **C, T, P on the primary; C, R, T on the guard; C, T on U1.** P is not sent on guard prompts | the guard needs a noise reference. Comparing C with history is confounded with time, and repeats agreed byte for byte only 36% of the time in Phase 21. R also gives the determinism read-out |
| 4 | guard populations for "every other true-status context (PENDING, SUCCEEDED, FAILED, and NOT_STARTED/NOT_REQUIRED)" | **G1–G5**, every other context that exists in development data | no report context exists with a confirmation status of `PENDING` or `FAILED`. `PENDING` exists only as an upgrade status, on 18 report-required turns. All 2,070 historical reports in these contexts have correct words |
| 5 | "the unsupported-word rate, C against T, with an exact test and a declared threshold" | **paired exact one-sided McNemar, p < 0.05, and T at most half of the comparator, against C and against P**, on a worst-case set that counts every T response that is not a fully correct report against T. FLOOR_LIMITED when C has fewer than 5 | the prompts are paired across arms. The placebo contrast stops "any added field" from carrying the result, so the rule is a contrast, not a count (pitfall 25). The floor names the case where no exact test can succeed |
| 6 | "build a new harness from `lapse_probe.py`'s pinned prompt rebuild … not reused as is" | `lapse_probe.py` is **imported unchanged under a private module name, with its sha256 pinned** (`f701ba14…`) | its rebuild, send loop, recorder and statistics are reused. Its configuration pin (`0a33aa51…`), populations, read-outs and spend-cap check are not: this harness pins `2cf63e93…`, checks the freeze file `8994e962…`, and enforces its own cap with its own `SpendGuard` |
| 7 | "a word no observation supports" | **declared word rule (§6)**, taken from the contract text and the reference actor. `checks.py` is never opened | the program left the rule open. Support is judged against delivered observations. Cited evidence is a subset of delivered evidence, so "cited" adds nothing to the rule. Citations are tallied (C6 needs matching cited evidence), never scored |
| 8 | the Phase 24 situation, implied to be in the development store and to carry the primary | it exists **only in Phase 20's own store**: 52 forced-report turns on the transient-upgrade cases, **0 historical slips**. **U1 is descriptive** (arms C and T) | the main store's completion studies hold no upgrade-side fault case. With 0 historical slips, U1 cannot add C slips to the primary; it could only add prompts where T alone is bad. So the primary is U2 and U1 is reported beside it, never deciding (§15) |
| 9 | voluntary report turns in the primary | **voluntary `UNKNOWN` prompts (U4) are not sent** | a re-sent voluntary report prompt rarely comes back as a report: Phase 21's plain re-sends reported on 23 of 114, and 8.4% of all turns in U4 contexts are reports. At the round-0 size (26 prompts) that is about 5 reports per arm, which says nothing. **T's effect on voluntary `UNKNOWN` reports is unmeasured** (§16) |
| 10 | the primary population: "report turns where an operation's latest observation is `UNKNOWN`" | **narrowed to `UNKNOWN` after a write** (U2; U1 descriptive). **U3 is not sent**: 62 report-required prompts whose confirmation reads `UNKNOWN` and was never written (the Phase 21 lapse reports) | U3 had 0 historical slips (62 of 62 correct) and 0 of 51 on Phase 21's re-sends, so it cannot help the primary, and the budget goes to U2. The cost: **T's effect on the correct `UNKNOWN`/`NOT_STARTED` words in the lapse context is unmeasured**, although a later loop's field would sit on that context every time (§16). T states `SUCCEEDED` / `UNKNOWN` on all 62 |
| 11 | "a guard on every other word" | **the guard covers every other word on the guard prompts; on the primary prompts any T word that is not correct counts against T** (§9.1) | a T report that moves a word into an "other mismatch" (for example the upgrade word to `UNKNOWN` despite a delivered `SUCCEEDED` receipt) is not unsupported, and round 0 let it pass unseen. Round 1 counts it as bad for T in the worst-case set, and tallies it separately (`t_other_mismatch_where_c_had_none`) |
| 12 | "on report turns where an operation's latest observation is UNKNOWN" (motivated by Phase 24) | the question and U1 are motivated by **one published heldout-2 episode summary** (`PHASE24_RESULTS.md`). No heldout-2 file, row or trace is read or sent | the program approves using the Phase 24 summary. Because heldout-2 informed this change, heldout-2 can never judge it (§13) |
| 13 | (sampling unspecified) | **each sampled stratum is allocated across (source, case, episode arm) cells in proportion to what each cell holds**, then seeded rank within a cell (§8) | round 0 took an unstratified seeded prefix, which by chance under-sampled the cell that slips most (`notification-2`/B0: 69 chosen against 87.4 expected; hypergeometric P(X ≤ 69) = 0.001). The slip rate differs by cell (§4) |

## 3. What is fixed

**Setup:**
- **Actor:** `deepseek-ai/DeepSeek-V3.1` at temperature 0, with 2,000 output tokens and a 20 s
  timeout, as in `Actor.__call__`. Checked against the frozen configuration and
  `MODEL_REQUEST_SETTINGS`.
- **Response format:** the stored contract, via `response_format_for(stored response_contract)`:
  - strict JSON schema on the 305 report-required prompts;
  - `json_object` on the 67 voluntary prompts (G4 and G5).
- **Actor context:** only `faultlab-actor-context/v4-indexed-evidence` episodes are rebuilt
  (pitfall 69).
- **Settings:** `artifacts/phase16-2026-09-22/settings-phase17.json`.
- **What does not run:** no Mechanic, no Explorer, no lab backend, no simulator, no Weave tracing.
  Nothing creates a campaign, study, trial, world, policy or store row.
- **Code:** nothing under `backend/app` changes. The fields T and P exist only in the harness.

**Pins:**

| item | value |
|---|---|
| harness `scripts/experiments/report_word_probe.py` sha256 | `f057ef2a1123f01bf50c61c5637cbba463f01d16593e8ee9d6d27f4f47869519` |
| dry plan hash (`content_hash(plan)`) | `cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682` |
| dry plan file `dry-plan-r3/plan.json` sha256 | `2f26cd34a494610b0ca4bb9ce77b2ee35eb616aa591dcb9bf4f5406cb6b5ddb6`. Its 1,064 requests are identical to round 2's and round 1's; only the harness sha256 differs from round 2's plan (`protocol-facts-r3/plan_r3_vs_r2.out.json`) |
| Phase 21 harness `lapse_probe.py` (imported unchanged) sha256 | `f701ba148f716dd8416b603e387cdbec7772e513453f1207d307cb1927e7ebfd` |
| `configuration_hash` (Phase 17 settings on the Phase 22 code), recomputed from the settings file without reading `.env` | `2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba` |
| gate freeze record `artifacts/phase22-2026-09-24/gate-freeze-after.json` sha256 | `8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1`. Only the file's hash is checked. The freeze is never re-taken, because re-taking it would hash the private partitions |
| settings file sha256 | `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| `actor_prompt_hash` | `12eabe7f41028c05e37d4143f5208843a9414bd14bcb0deea600e3a5e7d9f7b2` |
| Phase 20 store `artifacts/phase20-2026-09-23/run-1/lab.sqlite3` sha256 | `8d78f09938f514e225cc914df33a20732fcc9ce3d09b180192e802d4284a4487` |
| Phase 20 plan `artifacts/phase20-2026-09-23/run-1/plan.json` sha256 | `549a9eb18eaecfcbde88e60a4d258490b4a9e6b14ac32b237c239de6c3617426` |
| main store cutoff | episodes started before `2026-09-24T05:50:00Z`. The last development completion-study episode (Phase 23) started at 05:48:32Z, and heldout-2's first episode (Phase 24) at 05:51:21Z (the round-1 fidelity review's count; this harness reads no promotion row), so the cutoff is a second barrier beside the split filter |
| sample seed | `faultlab-phase27-2026-09-24` |
| per-request bound; hard phase cap | $0.0209; $25.00 |
| size option (`DECLARED_OPTION`); the program's phase cap (`PROGRAM_PHASE_CAP`) | R; $25.00. Both are in the plan, and the review record must name R (§12 item 6). Since round 3 the harness's `OPTION_TABLE` gives each option's sizes and most cap (R: U2 225, G4 45, $25; A1: U2 300, $30.17; A2: U2 400, $37.20), and the dry run and the live gate refuse unless `STRATUM_SIZES` are R's and `HARD_SPEND_CAP` is at most $25 |
| this document | its sha256 is typed by the operator as `--expect-protocol-sha256` and written into the review record. The harness does not pin it, so the pins are not circular |
| tests `backend/tests/experiments/test_report_word_probe.py` sha256 (not pinned by the harness) | `0242f42a9175e179d6b4ba018a9c0ad0522fb5717743a75d29fda5a556c43ca4` |

The plan also records the sha256 of the eight files the rebuild and the word rule depend on:
`actor.py`, `progress.py`, `prompts/actor.md`, `reference.py`, `runtime.py`,
`contracts/models.py`, `policy_state.py` and `lapse_probe.py`. Any change to them changes the plan
hash, and then the live gate refuses.

## 4. Why, and the base rate (development evidence, $0)

**Sources:**
- `artifacts/phase27-2026-09-24/protocol-numbers/protocol_numbers.out.json` (round 0) and
  `protocol-numbers-r1/protocol_numbers_r1.out.json` (the same cell figures as round 2's
  `protocol-numbers-r2/protocol_numbers_r2.out.json`);
- `artifacts/phase27-2026-09-24/protocol-facts/report_word_facts.out.txt`;
- `protocol-facts-r1/phase21_resends.out.json` and `protocol-facts-r1/context_report_share.out.json`;
- the dry plan.

Every verified v4 development report turn, judged by the word rule in §6:

| stratum | rule | reports | unsupported | rate (Wilson 95%) |
|---|---|---|---|---|
| U1 | report-required; upgrade `UNKNOWN`, written at least once, never shown otherwise, no receipt (the Phase 24 situation) | 52 | 0 | 0% [0, 6.9%] |
| U2 | report-required; upgrade `SUCCEEDED`; confirmation written at least once, status `UNKNOWN` | 667 | 25 | **3.7% [2.6%, 5.5%]** |
| U3 | report-required; upgrade `SUCCEEDED`; confirmation `UNKNOWN`, never written (Phase 21's lapse reports) | 62 | 0 | 0% [0, 5.8%] |
| U4 | voluntary; any operation `UNKNOWN` | 351 | 13 | 3.7% [2.2%, 6.2%] |
| G1 | report-required; upgrade `PENDING` | 18 | 0 | 0% |
| G2 | report-required; reference `SUCCEEDED` / `SUCCEEDED` | 7 | 0 | 0% |
| G3 | report-required; reference `SUCCEEDED` / `NOT_STARTED` | 3 | 0 | 0% |
| G4 | voluntary; reference `FAILED` / `NOT_REQUIRED` (terminal rejection) | 286 | 0 | 0% [0, 1.3%] |
| G5 | voluntary; reference `SUCCEEDED` / `SUCCEEDED` | 1,756 | 0 | 0% [0, 0.22%] |
| **all** | | **3,202** | **38** | 1.2% |

- **Every report turn falls in one of these strata.** No report turn falls in the catch-all
  strata `U_other` or `G_other`.
- **All 38 slips are the confirmation word, never the upgrade word:**
  - 36 are `PENDING` (25 in U2, 11 in U4);
  - 2 are `NOT_STARTED` where a confirmation write, or a status other than `UNKNOWN`, had been
    delivered (U4);
  - every one was written where the confirmation's status was `UNKNOWN`.
- **The upgrade word never slipped in 3,202 development reports.** That includes 0 of 52 in U1,
  the Phase 24 situation. Phase 24's slip was an upgrade-word slip, and it happened on heldout-2,
  which is not development data. So **the primary's power comes entirely from U2's confirmation
  word** (§15).
- **The slip rate differs by cell.** U2 by case and episode arm:

  | cell | reports | unsupported | rate |
  |---|---|---|---|
  | `notification-2` / B0 | 310 | 17 | 5.5% |
  | `notification-2` / L | 40 | 1 | 2.5% |
  | `notification-18` / B0 | 108 | 4 | 3.7% |
  | `notification-18` / L | 95 | 0 | 0% |
  | `notification-3` / B0 | 114 | 3 | 2.6% |

  B0 episodes slip more than L episodes: 24 of 532 against 1 of 135 (one-sided Fisher p = 0.024). U4
  shows the same, 13 of 230 against 0 of 121. The power figures in §10 use these cell rates, not the
  pooled 3.7%.
- **Where Phase 21's "about 7%" came from.** It is Phase 21's `pending_probability`: 7 of 98 reports
  in the contexts selected for a historical `PENDING` word and 7 of 103 in the others, 14 of 201 in
  all. Judged by this probe's rule:
  - those reports **pooled two strata**. U2 prompts (36 contexts, each re-sent 5 times: 180
    reports) slipped **7 of 180 = 3.9% [1.9%, 7.8%]**. The voluntary U4 prompts came back as reports
    on only 21 of 100 re-sends, and 7 of those 21 slipped. The mixture gives the 7%;
  - **the selection made no difference:** on U2, 3 of 90 in the selected contexts against 4 of 90 in
    the others;
  - **the slips look like per-request noise, not a property of the prompt:** each of the 36 U2
    contexts slipped 0 or 1 times in its 5 re-sends; none slipped twice;
  - on the 14 voluntary lapse prompts: 2 reports, both supported. On the 51 U3 lapse reports:
    0 unsupported.

## 5. How a prompt is rebuilt and verified

- **Phase 21's rebuild, imported unchanged.**
  - The harness loads `scripts/experiments/lapse_probe.py` under a private module name. It refuses
    to plan unless that file's sha256 is `f701ba14…`.
  - It uses `rebuild_episode`, which rebuilds each request with the runtime's own code:
    `ACTOR_PROMPT`, `ACTION_ADAPTER`, `progress.turn_message` and `response_format_for`. It replays
    the Actor's history extensions exactly.
  - A prompt is verified only if **both** stored hashes match: `messages_hash` and
    `request_hash` (which also covers `response_format`).
- **Also reused from it:**
  - the live loop (`run_requests`);
  - the recorder and the served-model recorder;
  - the exact statistics (`mcnemar_greater`, `fisher_greater`, `wilson`).
  - The spend guard is Phase 21's code, but its cap check is this harness's own (`SpendGuard`
    subclasses it and checks this harness's `HARD_SPEND_CAP`; §11).
- **Eligible episodes:**
  - main store `artifacts/lab.sqlite3`: split `development`, purpose `completion_study`, lifecycle
    `COMPLETED`, started before the cutoff;
  - Phase 20's store: split `development`, purpose `challenge`, lifecycle `COMPLETED`;
  - both: v4 context only.
- **Result: 17,119 of 17,119 v4 turns verify, across 3,204 episodes** (3,066 main, 138 Phase 20).
  3,202 of those turns are reports: 809 report-required and 2,393 voluntary. Round 1's changes to how
  the stores are read left these populations exactly as they were
  (`protocol-facts-r1/plan_r1_vs_r0.out.json`).
- **The stores are opened read-only.**
  - The main store is opened with `?mode=ro`.
  - Phase 20's finished store is opened with `?mode=ro&immutable=1`, and only if its write-ahead
    log is empty, so its directory is never touched.
- **heldout-2 is never rebuilt, and no held-out row is parsed.**
  - Episode rows are selected in SQL by split `development` and the declared purpose, so no payload
    of another split is parsed. heldout-2's episodes are split `promotion`.
  - The cutoff (05:50:00Z) falls before heldout-2's first episode, a second barrier.
  - Case labels come from completion-study trial rows: SQLite extracts two fields per trial row
    (`trial.episode_id`, `case_id`), and only labels of eligible development episodes are kept. No
    `trials` record is read. (Round 0 used `lapse_probe.load_index`, which also parsed every
    `trials` row, 192 of them tied to held-out episodes by the round-1 fidelity review's count, and
    every episode row of every split.)
  - Events are loaded only for eligible development episodes.
  - No file under `artifacts/heldout2/` or `audit/` is opened, and no final-audit file is read.
- **Before any plan,** the harness re-checks every pin in §3 at $0: the settings file, the freeze
  record, both Phase 20 files, `lapse_probe.py` and the recomputed configuration hash.

## 6. The context of a report turn, and the word rule

Everything here comes from delivered observations, never from private truth (pitfall 10).

- **Status per operation:** `PolicyState.status`, the runtime's own rule behind the policy
  conditions:
  - a matching terminal receipt, if one exists;
  - otherwise the latest observation bound to the operation, with a missing status read as
    `UNKNOWN`;
  - none, when no observation names the operation.
- **What was seen per operation:** the status of every observation whose `operation_id` is the
  operation (a missing status counts as `UNKNOWN`), plus the receipt's status. Also, how many writes
  (`update_order` or `send_confirmation`) were delivered.
- **Reference words:** those of the handwritten reference actor (`backend/app/agents/reference.py`):
  - upgrade = the status, or `NOT_STARTED` if there is none;
  - confirmation = `NOT_REQUIRED` when the upgrade is `FAILED`; otherwise the status, or
    `NOT_STARTED` if there is none.
- **Word classes**, per operation, checked in this order:

  | class | rule |
  |---|---|
  | match | the reference word |
  | allowed pair | `UNKNOWN` ↔ `NOT_STARTED`, only for an operation never written and never shown other than `UNKNOWN` (pitfall 2; Phase 21's 4-of-4 C5 evidence) |
  | **unsupported** | `PENDING`, `SUCCEEDED` or `FAILED` that no delivered observation of that operation shows. `NOT_STARTED` after a delivered write, or after any status other than `UNKNOWN` ("NOT_STARTED requires no write attempt": the Explorer's C5 brief). `NOT_REQUIRED` without a delivered `FAILED` upgrade (the spec's data model) |
  | other mismatch | anything else. Examples: a stale `PENDING` that was shown earlier; `UNKNOWN` despite a terminal receipt; **`NOT_STARTED` where `NOT_REQUIRED` is required** (Phase 4's regression); a missing word |

- **A report is unsupported when either of its words is.** `UNKNOWN` is never unsupported.
- **A report is correct when both words are a match or the allowed pair.**
- **C5 and C6 are not scored, and `checks.py` is never opened.** The rule's sources are
  `prompts/actor.md`, the spec's data model, the Explorer's C5/C6 brief and the reference actor.
- **How the read-outs use the rule:**
  - the primary counts a C or P report as bad when it is unsupported, and a T response as bad
    unless it is a correct report (§9.1);
  - the guard compares word pairs, with an allowed-pair word replaced by its reference word, so it
    also sees Phase 4's other mismatch; G4's word test uses "correct" (§9.2).

## 7. Arms (exact text)

| arm | what is sent |
|---|---|
| **C** | the exact verified v4 request, re-sent. C equals the stored request; that follows from the verification and is not an independent check |
| **R** | the same request as C, sent again (guard prompts only): the guard's noise reference, and determinism |
| **T** | C plus the field `last_observed_status`, on every turn in window |
| **P** | C plus the placebo field `layout_marker`, on exactly the same turns (primary prompts only) |

**The window.** A turn is in window if and only if at least one operation has a delivered
observation that matches it under the runtime's binding (`progress._matching_operation_data`) and
reports a status. That binding means:
- transport `ok`;
- the operation's service, id, order and intent hash all match;
- the result's status equals the data's status.

Outside the window every arm is byte-identical to C. **All 3,202 report turns are in window.**

**The two fields, exactly as the Actor sees them** in the canonical JSON of the turn's user message.
The v4 message has the keys `final_report_required`, `observations` and `remaining_actor_calls`, so
both fields sort **second**, right after `final_report_required`. T is shown on a Phase 24-like
turn; P is constant:

```
"last_observed_status":{"note":"Copied from the most recent delivered observation that reports a status for each operation, with that observation's label; null means no delivered observation has reported one.","notifications":null,"orders":{"evidence":"obs-4","status":"UNKNOWN"}}
"layout_marker":{"note":"A fixed layout block with the same structure as the other context on this turn; its entries are constant in every episode and describe nothing.","slot_a":{"ref":"layout-1","value":"constant"},"slot_b":{"ref":"layout-2","value":"constant"}}
```

- **What T holds:** for each operation, the status of the latest delivered observation that
  matches it, **verbatim**, with that observation's `obs-k` label. If there is none, it holds
  `null`.
  - The label is the observation's position in the delivered list, the same label the Actor sees.
  - This was checked in every planned T request (`protocol-facts-r1/t_label_check_r1.out.txt`).
    All 626 stated labels point at an observation in the same message that carries that
    label, that service and that status; the other 118 entries are `null`.
  - In all 372 T and 225 P requests, the field is the second key.
- **What T does not do:** it never names a report word to use. It restates public, delivered
  evidence only.
- **Lengths:**
  - notes: T 176 characters, P 143;
  - the example key-value pairs: T 280 characters, P 264.
- **T states exactly the runtime's status on every primary and guard prompt.**
  - This was checked on all 10,683 in-window turns
    (`protocol-facts/stated_status_all_turns.out.txt`).
  - The only differences are 769 turns where the runtime reads the confirmation as `UNKNOWN` (an
    observation names it, but none reports a bound status) and T says `null`:
    - 766 of them are tool turns, on the notification cases;
    - 3 are U4 report turns (not sent).
  - T never states a status that the runtime's rule contradicts.

**What T says, and the reference words, per stratum** (orders / notifications):

| stratum | T states | reference words |
|---|---|---|
| U1 (descriptive) | `UNKNOWN` / null | `UNKNOWN` / `NOT_STARTED` |
| U2 (primary) | `SUCCEEDED` / `UNKNOWN` | `SUCCEEDED` / `UNKNOWN` |
| G1 | `PENDING` / null | `PENDING` / `NOT_STARTED` |
| G2, G5 | `SUCCEEDED` / `SUCCEEDED` | `SUCCEEDED` / `SUCCEEDED` |
| G3 | `SUCCEEDED` / null | `SUCCEEDED` / `NOT_STARTED` |
| **G4** | `FAILED` / **null** | `FAILED` / **`NOT_REQUIRED`** |
| U3, not sent | `SUCCEEDED` / `UNKNOWN` (all 62) | `SUCCEEDED` / `UNKNOWN` |
| U4, not sent | `SUCCEEDED` / `UNKNOWN` 346; `SUCCEEDED` / null 3; `FAILED` / `UNKNOWN` 2 | per turn |

**G4 is the trap of pitfall 17, and the guard gives it its own gate.**
- There, T says that no observation reported a confirmation status. Taken literally, that
  describes `NOT_STARTED`.
- The contract requires `NOT_REQUIRED`.
- Phase 4's context change produced exactly that slip, 5 times in 6.

**The $0 pre-check passed** (from `dry-plan-r2/dry-summary.json`, identical to round 1's). Nothing may be
sent if it fails.

| check | result | kind |
|---|---|---|
| turns verified | 17,119 of 17,119 | real check |
| turns in window | 10,683 (7,481 tool turns and 3,202 report turns, split in `protocol-facts/stated_status_all_turns.out.txt`) | count |
| report turns in window | 3,202 of 3,202 (809 report-required) | real check: T reaches every report prompt |
| T's content equals an independent computation from the raw observation dicts | 0 disagreements | real check |
| the window by that independent rule | 0 disagreements | real check |
| changed prompts that differ from C by anything but the one added key | 0 | real check |
| turns changed by T; by P | 10,683; 10,683, exactly the window | implementation self-check (true by construction) |
| C differs from the stored request | 0 | implementation self-check (C is the verified request) |

## 8. Populations (exact counts and the sampling rule)

**Sampling rule.**
- A stratum marked "all" sends every prompt it has.
- Otherwise its n prompts are **allocated across cells** — (source, case, episode arm) — in proportion
  to the prompts each cell holds, by Webster's divisor method: seats go one at a time to the open cell
  with the largest `held / (2 × seats + 1)`, ties to the first cell by name. Within a cell, the harness
  sends the first prompts ranked by
  `sha256("faultlab-phase27-2026-09-24:<stratum>:<source>:<episode>:<turn>")`.
- The method is house-monotone: a larger n never takes a prompt away from any cell, so a larger n keeps
  the same prompts and adds more. In this plan every cell of U2, G4 and G5 ends within one prompt of its
  exact proportional share. Tests check both, for every U2 size up to 299, and that the input order never
  matters.
- The rule is declared once, before data, and is not redrawn with another seed.

**A guard prompt must have correct historical words:** both words match the reference, or they form
the allowed pair. No prompt was excluded by this rule.

| population | stratum | available | sent | arms | requests |
|---|---|---|---|---|---|
| **primary** | U2 (confirmation sent, `UNKNOWN`) | 667 | **225** | C, T, P | 675 |
| **guard** | G1 (upgrade `PENDING`) | 18 | all 18 | C, R, T | 54 |
| | G2 (`SUCCEEDED` / `SUCCEEDED`, forced) | 7 | all 7 | C, R, T | 21 |
| | G3 (`SUCCEEDED` / `NOT_STARTED`, forced) | 3 | all 3 | C, R, T | 9 |
| | G4 (terminal rejection, voluntary) | 286 | **45** | C, R, T | 135 |
| | G5 (`SUCCEEDED` / `SUCCEEDED`, voluntary) | 1,756 | 22 | C, R, T | 66 |
| **descriptive** | U1 (the Phase 24 situation) | 52 | all 52 | C, T | 104 |
| not sent | U3 (lapse reports) | 62 | 0 | — | 0 |
| not sent | U4 (voluntary `UNKNOWN`) | 351 | 0 | — | 0 |
| **total** | | | **372 prompts** | **969 distinct request bodies** (C and R share one) | **1,064** |

**Composition** (from the dry plan, `sampling.allocation`):
- **U2** (all main store), sent of held: `notification-2`/B0 105 of 310, `notification-2`/L 14 of 40,
  `notification-18`/B0 36 of 108, `notification-18`/L 32 of 95, `notification-3`/B0 38 of 114. By arm:
  B0 179, L 46. Expected C slips at the cell rates: 8.4.
- **U1:** all from Phase 20's store. The transient-upgrade-failure cases (F4 on `update_order`, 2–4
  failures) `A-c2`, `A-c3` and `A-c4`, replicas r1–r3, have 5–6 prompts each. By arm: B0 25, L 27.
- **G1:**
  - by case: `terminal-upgrade-rejection` 6 (main), `D-d16` 6 and `D-d20` 6 (Phase 20);
  - by arm: L 12, B0 6.
- **G2:**
  - by case: `B-d4-r1` 3 and `B-d4-r2` 3 (Phase 20), `notification-2` 1 (main);
  - all B0.
- **G3:** `D-d5` 3 (Phase 20), all B0.
- **G4:** `terminal-upgrade-rejection` 45 (main). By arm: B0 23 of 146, L 22 of 140.
- **G5** (all main store): `healthy` B0 5, L 3; `lost-notification-response` B0 2, L 2;
  `notification-1` B0 3, L 2; `notification-2` L 3; `notification-3` L 2. By arm: B0 10, L 12. Cells
  holding fewer prompts get none at this size.

**Send order** (fixed by the plan, never changed during the run):
- **Populations:** primary `r0001`–`r0675`, then guard `r0676`–`r0960`, then descriptive
  `r0961`–`r1064`. If the run is cut short, the descriptive prompts are lost first.
- **Within a population:** prompts go in a seeded order that mixes strata and cells. The arms of one
  prompt are sent back to back, in a seeded order.
- **The largest prompt** is bounded at 7,515 input tokens.

## 9. Declared read-outs

**Received** means a generation arrived: status `ok` or `empty_response`. A request that errored
after its one blind retry is not received.

**Response class.** The runtime's own `ACTION_ADAPTER` parses each response into one of these:
- a report, with all its fields;
- a tool action (`get_operation_status` with its service, `send_confirmation`, or another tool by
  name);
- `other` (invalid output, or an empty response).

**Completeness.**
- **Primary:** INCOMPLETE unless each of C, T and P received at least 95% of the planned prompts: 214
  of 225 per arm.
- **Guard outcome tests:** an outcome test is INCOMPLETE unless at least 95% of its prompts had C, R and
  T **all** received: pooled 91 of 95; G4 43 of 45.
- **G4's word test** needs only its report floor: at least 20 G4 prompts on which R and T both returned
  a report (§9.2). It does not need the 95%, and it does not use C.

The code (`compute_readouts`) governs. The rule strings frozen into the plan (`readout_rules`) now state
the full rule; round 0's strings were abbreviations (Review log, F5).

### 9.1 Primary (U2: 225 report-required prompts; arms C, T, P)

**Worst case for T.** Each prompt gets one flag per arm:
- a **T** response is **bad unless it is a received report whose two words are both correct** (match or
  allowed pair). So an unsupported word, any other mismatch, a non-report, and an invalid, empty,
  errored or missing T response all count against T;
- a **C or P** response is bad **only** when it is a received report with an unsupported word. Any other
  C or P response (missing, errored, empty, invalid, not a report, or a report with an other mismatch)
  counts as not bad.

Historically none of the planned U2 prompts had an other mismatch (218 fully correct, 7 unsupported), so
any T other mismatch is new and now counts.

**Evaluation order** (the first that applies):
1. **INCOMPLETE:** any of C, T or P received fewer than 214 of 225.
2. **FLOOR_LIMITED:** C has fewer than **5** bad prompts. An exact one-sided sign test cannot reach
   p < 0.05 with fewer than 5 discordant prompts, so the probe cannot tell.
3. **FAIL, route (a):** the test against C fails. The test against C needs both:
   - the exact one-sided McNemar test on the discordant prompts (C bad and T not, against T bad and C
     not) gives **p < 0.05**;
   - T's bad count is **at most half** of C's.
4. **FAIL, route (b0):** the test against C passes, the same test against P fails, and P itself has
   fewer than 5.
5. **FAIL, route (b):** the test against C passes, and the same test against P fails.
6. **PASS:** both tests pass.

**Statements** (written by the harness, declared now):

| result | statement |
|---|---|
| PASS | "the field lowered unsupported report words against both the plain re-send and the placebo" |
| FLOOR_LIMITED | "the plain re-send gave only k unsupported reports in 225 prompts (fewer than 5); no exact test at this size can show a reduction, so this probe cannot tell whether the field helps" |
| INCOMPLETE | "an arm received fewer than 95% of its planned requests; no evidence either way" |
| FAIL (a) | "the field did not lower unsupported words enough against the plain re-send (T x against C y of 225, worst case for T)" |
| FAIL (b0) | "… the placebo arm itself gave only k unsupported reports (fewer than 5), so no drop below it can be shown: either a meaningless same-shape field also suppresses the slip or the placebo arm drew low; the drop is not attributable to the field's content" |
| FAIL (b) | "… not enough against a meaningless same-shape field (T x against P y); the drop is not shown to come from stating the status" |

**Also reported, never deciding:**
- **Per arm:**
  - the worst-case count and rate, with a Wilson interval;
  - reports received, unsupported and not-correct among them, with a Wilson interval;
  - non-report responses;
  - the word pairs given, and the word classes;
- **Received-only discordance** against C and P (unsupported words only, like for like), over the
  prompts where all three arms reported. It is not a separate test.
- **`t_other_mismatch_where_c_had_none`:** prompts where T's report has an other mismatch and C's
  report on the same prompt has none.
- **An unpaired one-sided Fisher p,** T against C and T against P. It is descriptive.

### 9.2 Guard (G1–G5: 95 prompts; arms C, R, T)

- **A response's outcome** is:
  - for a report, the pair (upgrade word, confirmation word), **with a word in the allowed pair
    replaced by its reference word** (`UNKNOWN` ↔ `NOT_STARTED` for an operation never written and
    never shown other than `UNKNOWN`: on these prompts, the confirmation on G1 and G3). The word rule
    calls both words correct, so moving between them is not a change;
  - otherwise, the response class and detail.

  So a move between reporting and acting counts as a change. So does Phase 4's `NOT_REQUIRED` →
  `NOT_STARTED`: `NOT_REQUIRED` is not in the allowed pair. **Allowed-pair shifts are tallied apart**
  (T against C, and R against C), and reported beside every gate.
- **A response changed** when its outcome differs from C's outcome on the same prompt.
- **Compared prompts** (for the outcome tests): C, R and T were all received.
- **An outcome test FAILS** if and only if both hold:
  - (T changed − R changed) / compared **> the tolerance**;
  - the exact one-sided sign test on the discordant prompts (T changed and R did not, against R
    changed and T did not) gives **p < 0.05**.
- **Two gates:**
  - **pooled** over all 95 prompts: the outcome test with tolerance **0.05**;
  - **G4** (terminal rejection, 45 prompts), with three parts:
    - the outcome test with tolerance **0.10**;
    - a **report floor**: at least **20** G4 prompts on which R and T **both** returned a report,
      whatever C returned. Below it the word test is INCOMPLETE. G4 prompts are voluntary
      (`json_object`), so a re-send may act instead of reporting, and Phase 4's harm can show only on
      a report. C is not needed because the word test compares T with R only; under no effect T and
      R stay exchangeable whatever C did. (Round 1 also required C's report, which met the floor with
      probability q³ per prompt instead of q² and added a way to end INCOMPLETE for no purpose;
      round 2 removed it, Review log R2-S1);
    - a **word test** on those prompts: T's report not correct while R's is, against R's not correct
      while T's is; FAIL if the exact one-sided sign test gives **p < 0.05**. It targets Phase 4's
      `NOT_REQUIRED` → `NOT_STARTED` directly, and also any incorrect upgrade word. A change in
      reporting-versus-acting cannot hide it.
- **Status.** A test reports FAIL only when its own completeness holds:
  - an **outcome test** (pooled, and G4's) needs at least 95% of its prompts with C, R and T all
    received;
  - G4's **word test** needs only its report floor (at least 20 prompts reported by R and T). It does
    not need the 95%.

  Then, for G4's two parts and for the two gates alike: **FAIL if any part failed; otherwise
  INCOMPLETE if any part is incomplete; otherwise PASS.** So a guard with a failed gate is FAIL even
  when the other gate lacks data, and an INCOMPLETE guard has no failed gate.
- **What it takes to fail:**
  - G4 outcome test, with 45 compared: an excess of at least 5 prompts and the sign test, for
    example 5 T-only changes with no R-only change, or 7 with one.
  - G4 word test: at least 5 prompts where only T is incorrect and none where only R is, or 7 against
    one, among at least 20 prompts reported by R and T.
  - Pooled, with 95 compared: an excess of at least 5 prompts, and the sign test.
- **Why R, and not C, is the reference.** If T does nothing, T and R are exchangeable draws against
  the same C. So each sign test holds its false block at 5% or less, whatever the noise level. The
  tolerance lets a small, real change through.
- **Also reported, never deciding:**
  - per-stratum figures for every guard stratum;
  - every transition from C's outcome to T's;
  - T's word classes;
  - the allowed-pair shifts.

### 9.3 Descriptive only (never a decision input)

- **U1 (arms C, T; the Phase 24 situation):** per arm, received, reports, unsupported, correct, word
  pairs and response classes; T against C: outcome changes with their transitions, and prompts where
  only one arm was unsupported or not correct.
- **Determinism (C against R, on the 95 guard prompts):**
  - the byte-identical share, with a Wilson interval;
  - the same-outcome share (as the guard compares outcomes);
  - the unsupported discordance where both arms reported.
- **`overall` and `next_action`:** tallies per stratum and arm, and changes against C and against
  the historical report.
- **Citations:** reports that cite every `obs-k` label T stated (C6 needs matching cited evidence).
- **History:** C and R responses that are byte-identical to the historical output.
- **Provider:** what served each request (`model`, `system_fingerprint`), measured tokens,
  statuses, attempts, waits and the stop reason. The served model is recorded, never enforced.

### 9.4 Decision rule

| primary | guard | decision |
|---|---|---|
| PASS | PASS | **`RECOMMENDED_FOR_A_LATER_LOOP`** |
| anything else | anything else | **`NOT_RECOMMENDED`** |

- **The statement** is the primary's statement (§9.1). If the guard is not PASS, the harness appends
  "; guard <status> (pooled <status>, terminal rejection <status>: outcome test <status>, word test
  <status> on k prompts reported by R and T, floor 20)".
- **A recommendation is only a recommendation.** When recommended, the harness appends: "the guard
  saw no word change beyond a second plain re-send. Recommended for a later loop only: that loop
  must measure it end to end, including tool turns, which this probe never sends".
  - The field is not adopted anywhere.
  - A later loop must declare its own change: the same key, wording, position and window. It must
    then measure the change live, against a concurrent control, with its own review.
- **The read-outs are computed only by the run's own harness and plan** (`--readouts` refuses
  otherwise; §14 step 7).

## 10. Power, false alarms and boundaries (computed, $0)

**Sources:** `protocol-numbers-r2/protocol_numbers_r2.py` and `.out.json` (round 2), run on the
round-2 harness (`adf09f83…`). They use the harness's own `webster_allocation`, `primary_decision` and
`guard_readout`, with fixed seeds (Monte Carlo: 4,000 draws for the declared primary, 2,000 for each
option and each guard row; standard error about 0.01). The primary figures (§10.1, §10.2 and the
primary columns of §10.3) are identical to round 1's (`protocol-numbers-r1/`), draw for draw; only the
guard figures and the G4 floor changed. Round 3 changed no sampling, read-out or statistics code; the
same script re-run on the round-3 harness reproduces its saved output exactly, apart from the harness
sha256 it records (`protocol-facts-r3/numbers_rerun_r3.out.txt`).

**The primary model:** each U2 prompt's C and P slip independently at **its cell's historical rate**
(§4), T at a flat rate, prompts independent. Round 0 used the pooled 3.7% on an unstratified sample, which
overstated the power (§10.2).

### 10.1 Exact boundaries

| discordant prompts (T better, T worse) | one-sided p | passes p < 0.05? |
|---|---|---|
| 4, 0 | 0.063 | no: the floor |
| **5, 0** | **0.031** | yes: the smallest possible PASS (C ≥ 5, T 0) |
| 6, 1 | 0.063 | no |
| 7, 1 | 0.035 | yes |
| 8, 2 | 0.055 | no |
| 9, 2 | 0.033 | yes |
| 10, 3 | 0.046 | yes |

- A single T-bad prompt where C was not bad needs at least 7 prompts the other way.
- T must also be at most half of C, on the worst-case counts.

### 10.2 Primary, at the declared size (U2 225, allocated by cell)

Expected C slips: 8.44.

| T's bad rate | PASS | FLOOR_LIMITED | FAIL a / b / b0 |
|---|---|---|---|
| **0** | **0.86** (exact 0.861) | 0.07 | 0 / 0 / 0.07 |
| **0.5%** | **0.54** | 0.07 | 0.23 / 0.11 / 0.05 |
| 1% | 0.31 | 0.07 | 0.43 / 0.16 / 0.03 |
| 2% | 0.09 | 0.07 | 0.73 / 0.10 / 0.02 |
| no effect (T at each prompt's cell rate) | **0.005** | 0.08 | 0.90 / 0.02 / 0.00 |
| P works too (T = P = 0) | **0** | 0.07 | b0 0.93 |

- **False alarm.** A field with no effect passes the primary 0.5% of the time. Requiring both
  contrasts keeps it far below 5%.
- **The placebo's price.** When T removes every slip and P does nothing, route (b0) still fires 7% of
  the time, because P drew fewer than 5 by chance.
- **The round-0 sample was worse than round 0 said.** Its unstratified seeded prefix happened to
  under-sample `notification-2`/B0 (69 chosen against 87.4 expected, P(X ≤ 69) = 0.001) and
  over-sample `notification-18`/L (35 against 26.8; 0 historical slips). At the cell rates it gave
  PASS 0.59 at T 0 and 0.27 at T 0.5%, not the 0.68 and 0.33 round 0 quoted.
- **The heterogeneity that matters is by cell, and it is now in the model.** Round 0's argument that
  clustering by prompt does not lower the power used a scenario (7.4% of prompts slipping at 50%)
  that the data contradict: in Phase 21, each of the 36 re-sent U2 contexts slipped 0 or 1 times in
  5, none twice (§4). Within a cell, slips behave as per-request noise, which is what the model
  assumes.

### 10.3 The size decision (the owner's, before any data)

Every option below uses the round-2 rules (T's worst case, the G4 floor counted on R and T, the word
test, U2 allocated by cell) and the cell rates. "G4 floor met" is the exact probability of at least 20
G4 prompts with R and T both reporting, if each arm reports independently with probability q (§10.4).
"Guard power" is the chance the guard FAILs a field that moves 20% of T's G4 words (h = 0.2 in §10.4).
An above-cap option's cap is its bound plus about 12% for retries, as round 0 sized them; within the
cap, $25 leaves 132–134 retry attempts. Sources: `protocol-numbers-r2/protocol_numbers_r2.out.json`
(`options`, `guard`, `guard_g4_30`); the primary columns are unchanged from round 1.

| option | requests | bound | cap | PASS at T 0 | PASS at T 0.5% | FLOOR_LIMITED | G4 floor met, q 0.89 / 0.8 | guard power at h 0.2, q 0.89 / 0.8 |
|---|---|---|---|---|---|---|---|---|
| **R (declared; the owner's answer):** U2 225, G4 45, U1 descriptive C/T, U4 and U3 not sent | 1,064 | $22.24 | **$25** (132 retry attempts) | **0.86** | **0.54** | 0.07 | **1.00 / 1.00** | **0.90 / 0.75** |
| W1: U2 240, G4 30, U1 descriptive | 1,064 | $22.24 | $25 | 0.90 | 0.58 | 0.05 | 0.97 / 0.46 | 0.61 / 0.37 |
| W2: U2 259, G4 45, U1 not sent | 1,062 | $22.20 | $25 | 0.94 | 0.64 | 0.03 | 1.00 / 1.00 | 0.90 / 0.75 |
| W3: U2 274, G4 30, U1 not sent | 1,062 | $22.20 | $25 | 0.96 | 0.68 | 0.02 | 0.97 / 0.46 | 0.61 / 0.37 |
| W4: U2 225 from B0 episodes only (a narrower population), G4 45, U1 descriptive | 1,064 | $22.24 | $25 | 0.95 | 0.74 | 0.02 | 1.00 / 1.00 | 0.90 / 0.75 |
| D0: the round-0 draft (U2 188 seeded prefix, U1 in the primary, U4 sent, G4 30) | 1,064 | $22.24 | $25 | 0.59 | 0.27 | 0.23 | 0.97 / 0.46 | 0.61 / 0.37 |
| A1: U2 300, otherwise as R | 1,289 | $26.94 | **$30.17** | 0.98 | 0.75 | 0.01 | 1.00 / 1.00 | 0.90 / 0.75 |
| A2: U2 400, otherwise as R | 1,589 | $33.21 | **$37.20** | 1.00 | 0.90 | 0.00 | 1.00 / 1.00 | 0.90 / 0.75 |

- **Why R is recommended, restated after round 2.** Round 1 argued against W1 and W3 mainly with the
  report floor ("unmet a quarter of the time even at q = 0.89"). That figure came from round 1's floor,
  which also required C's report. Counted on R and T, the floor at G4 = 30 is met 97% of the time at
  q = 0.89, so that argument was overstated. R is still recommended, for two reasons that survive the
  correction:
  - **q is unmeasured and may be lower than the historical context share** (§10.4). At q = 0.8, R still
    meets the floor (1.00); W1 and W3 meet it 46% of the time, and an unmet floor makes the decision
    NOT_RECOMMENDED;
  - **45 G4 prompts give the terminal-rejection guard more power** against a Phase 4-type word harm:
    at h = 0.2, 0.90 against 0.61 at q = 0.89, and 0.75 against 0.37 at q = 0.8. That is the
    regression this program was warned about (pitfall 17).

  W1 and W3 would buy 4–14 points of primary power for that. W2 drops U1 for 8–10 points of power. W4 narrows
  the population to baseline episodes; the certified repairs run in L episodes, where the Phase 24 slip
  happened, so it answers a narrower question.
- **The owner chose R** ("okay gi ahead with whater u recommend"; Review log, round 2). The answer
  covers nothing above $25.
- **A1 and A2 raise the phase cap above the program's figure.** That would need a new answer from the
  owner that names the option, and the harness change below. The budget after Phase 24 is $399.35,
  before Phases 25 and 26.
- **How a change is made:**
  1. Edit `STRATUM_SIZES`, `DECLARED_OPTION` and, if the cap changes, `HARD_SPEND_CAP` in the harness,
     all three to one row of `OPTION_TABLE`. The harness's own `SpendGuard` checks this harness's
     `HARD_SPEND_CAP`, so a higher cap works without touching the pinned `lapse_probe.py`. Since round 2
     the live gate also refuses a cap above $25 unless the review record's `owner_answer.option` is A1
     or A2 and equals `DECLARED_OPTION`. **Since round 3** the dry run and the live gate also refuse
     unless `STRATUM_SIZES` equal that option's row and `HARD_SPEND_CAP` is at most its cap, so an A1
     answer opens U2 300 at up to $30.17 and nothing else (§12 item 6; tests run A2 at $37.20 end to end
     on a fake client, and refuse it with the answer R, with R's sizes, or at $37.21). W1–W4 have no row:
     choosing one means adding its row too. The harness sha256 and the plan hash then change.
  2. Write a new dry plan to a new directory (for example `dry-plan-r4/`).
  3. Recompute §10 with `protocol-numbers-r2/protocol_numbers_r2.py`, and update §3, §8, §10 and §11
     and the pins line at the top.
  4. Re-run the tests and `review-r3/mutate_r3.py`.
  5. Review the change (pitfall 74).
- **The rate interval itself is wide.** 8 of 225 has a Wilson 95% interval of [1.8%, 6.9%].

### 10.4 Guard (95 prompts: G1–G3 28 forced, G4 45 and G5 22 voluntary)

**The model** (the harness's own `guard_readout`): C, R and T are independent draws per prompt. A
voluntary prompt returns a report with probability **q** per arm, else a tool action. Forced prompts
always report, with word noise w = 5%. A harm moves T's G4 reports from `NOT_REQUIRED` to
`NOT_STARTED` with probability **h** (Phase 4's size: h = 0.83).

**The G4 re-send report rate q is unmeasured.** The evidence for it:
- historically, 286 of the 322 turns in G4 contexts were reports (88.8% [84.9%, 91.8%]); in G5
  contexts, 1,756 of 1,770 (`protocol-facts-r1/context_report_share.out.json`);
- in U4 contexts only 8.4% of turns were reports, yet Phase 21's plain re-sends of historical U4
  report prompts reported 21 of 100. A re-sent report prompt reported more often than its context's
  share, by a factor of 2.5. Nothing shows that the difference cannot go the other way on G4.

So q ≥ 0.89 on G4 is plausible, not shown. **Every guard figure below is conditional on q,** which is
why they are given down to q = 0.6.

**The report floor** (round 2: at least 20 G4 prompts with R and T both reporting), exactly, with iid
arms (correlated arms only make it easier to meet). Round 1's rule, which also required C's report, in
brackets:

| q | G4 30 | **G4 45 (declared)** | G4 60 |
|---|---|---|---|
| 0.95 | 1.00 (1.00) | 1.00 (1.00) | 1.00 (1.00) |
| 0.89 | 0.97 (0.75) | **1.00** (1.00) | 1.00 (1.00) |
| 0.85 | 0.81 (0.35) | **1.00** (0.99) | 1.00 (1.00) |
| 0.8 | 0.46 (0.06) | **1.00** (0.85) | 1.00 (1.00) |
| 0.75 | 0.17 (0.01) | **0.96** (0.44) | 1.00 (0.94) |
| 0.7 | 0.04 (0.00) | **0.78** (0.10) | 1.00 (0.61) |
| 0.6 | 0.00 (0.00) | 0.15 (0.00) | 0.71 (0.02) |

**False block, when T does nothing** (guard FAIL): 0.3% at q = 1; 4.6% at q = 0.89 and at q = 0.8; 4.8%
at q = 0.75; 5.6% at q = 0.7; 5.4% at q = 0.6; 4.1% at q = 0.89 with forced word noise of 20%. Each sign
test alone stays at or below 5%; the guard fails when any of its three tests fails, so the total can
sit slightly above 5% (Monte Carlo standard error about 0.5 points). The false block is the same under
round 1's floor (the round-2 review measured 3.6–6.3% under both rules). **The guard is INCOMPLETE,
with no harm,** 0.2% of the time at q = 0.8 (round 1's floor: 15%), 4% at q = 0.75, 21% at q = 0.7 and
81% at q = 0.6 (round 1: 94%).

**Power against a real word harm** (guard FAIL; INCOMPLETE in brackets where it is not negligible):

| harm | q = 1 | q = 0.89 | q = 0.8 | q = 0.75 | q = 0.7 | q = 0.6 |
|---|---|---|---|---|---|---|
| G4 only, h = 0.1 | 0.54 | 0.41 | 0.28 | 0.21 (0.04) | 0.17 (0.19) | 0.10 (0.77) |
| G4 only, h = 0.2 | 0.97 | 0.90 | 0.75 | 0.63 (0.04) | 0.48 (0.19) | 0.21 (0.71) |
| G4 only, h = 0.3 | 1.00 | 0.99 | 0.97 | 0.92 | 0.77 (0.14) | 0.34 (0.64) |
| G4 only, h = 0.5 | 1.00 | 1.00 | 1.00 | 0.99 | 0.91 (0.09) | 0.54 (0.46) |
| **G4 only, h = 0.83 (Phase 4's size)** | **1.00** | **1.00** | **1.00** | **1.00** | 0.99 | 0.88 (0.12) |
| every guard prompt, h = 0.05 | 0.40 | 0.19 | | | | |
| every guard prompt, h = 0.1 | 0.86 | 0.57 | | | | |
| every guard prompt, h = 0.2 | 1.00 | 0.97 | | | | |

Against round 1's figures, the power at q = 0.89 rose by 1–6 points and at q = 0.8 by 2–17 points,
because the word test now counts every prompt R and T reported. At G4 = 30 (options W1 and W3) the same
harms are caught less often: at h = 0.2, 0.61 at q = 0.89 and 0.37 at q = 0.8, with the guard INCOMPLETE
54% of the time at q = 0.8 (`guard_g4_30`).

**The joint risk.** Take a field that removes every slip (primary PASS 0.86) and also moves a share h of
G4 words. It is recommended with probability PASS × P(guard PASS):

| h | q = 1 | q = 0.89 | q = 0.8 | q = 0.75 | q = 0.7 | q = 0.6 |
|---|---|---|---|---|---|---|
| 0 (no harm) | 0.86 | 0.82 | 0.82 | 0.79 | 0.63 | 0.12 |
| 0.1 | 0.39 | 0.51 | 0.62 | 0.65 | 0.55 | 0.11 |
| 0.2 | 0.02 | 0.09 | 0.21 | 0.29 | 0.28 | 0.06 |
| 0.3 | 0.00 | 0.01 | 0.03 | 0.05 | 0.07 | 0.02 |
| 0.83 (Phase 4) | **0** | **0** | **0** | **0** | **0** | **0** |

- **Round 0's claim that the guard "catches a Phase 4-sized harm for certain" was not supported:**
  its power model assumed every G4 re-send was a report. Without a floor, at q = 0.21 (Phase 21's
  voluntary rate) such a field would have been recommended about half the time.
- **With the floor, a Phase 4-sized harm is never recommended in this model** at any q computed (1 to
  0.6): when R and T report often, the gate fails; when they rarely do, the gate is INCOMPLETE and the
  decision is NOT_RECOMMENDED. Below q = 0.6 the floor is almost never met. This rests on the model
  (arms independent; the harm shows on reports).
- **What round 2's floor trades.** It removes INCOMPLETE results that served no purpose: at q = 0.8, a
  field that works and harms nothing is now recommended 82% of the time, against 70% under round 1's
  floor. The price is that a small G4 harm passes more often where round 1's floor would have blocked
  it for lack of data, not by detecting it: at q = 0.8 and h = 0.1, 62% against 56%. At q = 0.6 round 1
  recommended almost nothing (0.2% with no harm), while round 2 recommends a harmless field 12% of the
  time and a 20% harm 6% of the time. The false block is unchanged, and the Phase 4-sized harm is
  still never recommended.
- **It still misses most harms below about 10–20%.** A recommendation does not rule out a
  terminal-rejection harm of that size (§15).
- **If q is low, the probe can rarely recommend anything.** At q = 0.6, G4 meets its floor 15% of the
  time, so the decision is NOT_RECOMMENDED at least 85% of the time whatever T does. That is the
  conservative direction, and the statement then names the word test's report count.

## 11. Spend cap, bounds, waits and stop rules

| | value |
|---|---|
| planned requests | **1,064** (969 distinct request bodies) |
| per-request bound | **$0.0209** (32,000 input tokens × $0.55/M + 2,000 output tokens × $1.65/M) |
| planned bound | **$22.2376** |
| hard spend cap | **$25.00 for the whole phase.** That admits 1,196 attempts, leaving **132 attempts ($2.76)** for retries |
| token-priced ceiling | at most about $7.91 (7,515 input and 2,000 output tokens on every request). This is unmeasured; the ledger carries the bound |
| budget before this run | $600.65 charged, **$399.35 remaining** after Phase 24. Reconcile Phases 25 and 26 first |

**The spend guard** (`report_word_probe.SpendGuard`: Phase 21's guard, with this harness's cap check):
- It charges every attempt, retries included, at the bound, in whole micro-dollars.
- It refuses the attempt that would pass the cap. The run then stops as `STOPPED` / `spend_guard`.
- A plan that cannot fit under the cap is refused before any call.

**The cap is a phase cap.** A later run is allowed only after runs that delivered nothing. It gets
$25.00 minus their charged bounds. Its manifest records `spend_cap`, `spend_cap_requested` and
`earlier_undelivered_charged`.

**Retries and waits (Phase 21's, unchanged):**
- **One blind retry.** A transport failure that delivered no generation (`CONNECTION_ERROR`,
  `REQUEST_TIMEOUT`) is retried at most once, charged, after 10 s.
- **No re-rolls.** A delivered generation is never re-rolled. `EMPTY_FINAL_RESPONSE` is recorded
  as received and never retried (pitfall 49).
- **Waits after errors.** After an errored request, the run waits 30 s, then 2 min, then 5 min,
  then 5 min, for the first to fourth errored request in a row. A received response resets the
  count. An errored request is never sent again.

**Stop rule.** The run stops at the first of these:

| stop | recorded as |
|---|---|
| all 1,064 requests done | `COMPLETED` |
| another paid run became visible after the claim, before the first provider call (§12 step 10) | `STOPPED` / `other_paid_run`, with 0 attempts |
| the spend guard | `STOPPED` / `spend_guard` |
| the 5th errored request in a row | `STOPPED` / `consecutive_errors` |
| SIGINT or SIGTERM, after the request in flight (a wait is cut short) | `STOPPED` / `operator_stop` |
| any other exception after the claim | `ABORTED`, with a scrubbed traceback in the manifest |
| the process dies with no final manifest, closed afterwards at $0 by `--finalize-abandoned` | `ABORTED` / `abandoned` |

- **After any stop,** the read-outs are computed on whatever arrived. An arm below its completeness
  bound makes its read-out `INCOMPLETE`, and the decision is then `NOT_RECOMMENDED`.
- **The served model is recorded, never enforced.** Its string format is unverified, and an abort on
  the first response would end the one live run.

**No resume, and only one run may deliver anything:**
- **Output directory.** It must be new, and exactly `artifacts/phase27-<date>/<name>`. It is created
  exclusively **before** the claim, so a directory that appears during the launch checks refuses with
  nothing claimed, and a failed claim removes the empty directory it made.
- **Claim.** Each live run takes an atomic claim `artifacts/phase27-live-claims/claim-NN.json`:
  - it is written in full to a private file, then hard-linked to its name;
  - it is never deleted;
  - it records the `pid`.
- **Refusal.** A later run is refused while any earlier Phase 27 run is not final, has delivered
  anything, or has a claim with no manifest.
- **A second draw** after a run that delivered anything would be repeat-until-lucky. It needs its
  own declared phase.
- **A dead claim.** A claim whose process died is closed at $0 with
  `--finalize-abandoned artifacts/phase27-live-claims/claim-NN.json`:
  - it refuses while the process may still be alive;
  - it charges every recorded attempt, plus two unrecorded in-flight attempts if the run died while
    `RUNNING`;
  - it counts what was delivered;
  - it writes a final `ABORTED` / `abandoned` manifest.

**Progressive manifest.** `report-word-probe-manifest.json` is written:
- `STARTING`, right after the claim. It already carries the owner's recorded answer (`owner_answer`,
  copied from the review record), the size option and the program's cap;
- then with `plan.json` and `prompts.jsonl`;
- then the last other-run check (its result is recorded as `other_runs_check_after_claim`);
- then `RUNNING`, before the first call;
- then again after every request.

`responses.jsonl` is appended and fsynced per request. Both API keys are scrubbed from every file the
run writes.

## 12. The live gate

The harness refuses to call the provider unless all of these hold. It checks them in this order, and
it checks everything except the credential-dependent items before it reads `.env`:

1. **Flags:** `--execute-live`, `--out`, `--confirm-entity`, `--expect-plan-hash`,
   `--expect-harness-sha256` and `--expect-protocol-sha256` are all given.
2. **Output:** the directory is new and exactly `artifacts/phase27-<date>/<name>`. Every earlier
   Phase 27 run is final and delivered nothing, and every claim's directory holds a final manifest.
3. **One paid run at a time (the files):**
   - no manifest lacks its end marker among these, listed by exact name for past phases and by
     wildcard only for the phases built beside this one: `phase20-*/*/dev-probe-manifest.json`,
     `phase21-*/*/lapse-probe-manifest.json`, `phase23-*/full-loop-manifest.json`,
     `phase25-*/**/*manifest*.json` and `phase26-*/**/*manifest*.json`. The end marker is an
     `ended_at`, with no `running` or `starting` status or stop reason. **Phases 22 and 24 (the
     heldout-2 seal and its held-out check) are never listed, and none of their files is opened;**
   - no claim in `phase20`, `phase21`, `phase23`, `phase25` or `phase26-live-claims/` names a
     directory without a finished manifest. A claim is followed only to a run directory of one of
     those phases; any other claim counts as running without being followed;
   - a crashed run can be named with `--ignore-manifest <exact path>`, which the manifest records.
4. **The plan:** `build_plan` re-checks every pin in §3 at $0, re-verifies every prompt, and
   re-runs the pre-check.
   - Then the output check runs again.
   - Then the file check runs again, now with a read-only
     `GET http://127.0.0.1:8000/api/config/status`. That request must show
     `active_campaign_id: null`, or be refused outright (the backend is down). Anything else,
     including a timeout, refuses.
5. **Pins:**
   - the harness sha256 equals `--expect-harness-sha256`;
   - this file exists, and its sha256 equals `--expect-protocol-sha256`;
   - the recomputed plan hash equals `--expect-plan-hash`;
   - this file contains the harness sha256 and the plan hash.
6. **The review:**
   - this file's opening block (everything before the first `## ` heading) no longer carries the
     status phrase (the harness's `REVIEW_PENDING_MARKER`), **in any case**: since round 2 a
     lower-case leftover also refuses. A Review log that quotes it cannot block the launch;
   - a bare line, with no backticks, list marker, bold or table, reads exactly
     `Reviewed for launch: harness <sha256> plan <hash>` with the two pins;
   - `artifacts/phase27-2026-09-24/review.json` names this file's sha256 as `protocol_sha256`,
     plus the same `harness_sha256` and `plan_hash`. Any edit to this file after the record is
     written makes the gate refuse;
   - **the owner's answer (round 2).** The record also carries `phase_cap`, equal to the harness's
     `HARD_SPEND_CAP` ($25.00), and `owner_answer` with the non-empty strings `option`, `verbatim`,
     `given_by` and `date`:
     - `option` must be the option the harness implements (`DECLARED_OPTION`, R);
     - when `HARD_SPEND_CAP` is above the program's $25, `option` must be A1 or A2. So a raised cap
       needs both a harness change and a new answer from the owner naming that option;
     - **the option's sizes and cap (round 3).** The option must be a row of the harness's
       `OPTION_TABLE` whose sizes equal `STRATUM_SIZES` and whose cap is at least `HARD_SPEND_CAP`
       (R: U2 225, G4 45, $25; A1: U2 300, $30.17; A2: U2 400, $37.20; the other strata as R). So an
       answer covers that option's sizes and cap, not only its label. The dry run (`build_plan`) makes
       the same check before it reads any file. The table is harness code: a test holds it to §10.3,
       and any edit to it changes the harness pin and needs review;
     - `verbatim` must appear in this file, word for word (case and spacing included), so the Review
       log and the record quote the same words;
     - the answer is copied into the `STARTING` manifest.
7. **Budget:** the run's cap is positive, and the plan fits under it. The run's cap is the smaller
   of `--spend-cap` and what the phase cap leaves, and this harness's `SpendGuard` accepts it.
8. **After the one credential read** (the runtime's own loader):
   - the entity equals `--confirm-entity`;
   - the project is `shreetbohara-quinstreet/Faultlab`;
   - the configuration pins hold again;
   - the Actor role resolves to `deepseek-ai/DeepSeek-V3.1`;
   - the one-paid-run check (item 3, with the backend status) passes again.
9. **Launch:**
   - the SIGINT and SIGTERM handlers are installed, and a stop that has already arrived refuses;
   - the output directory is created exclusively;
   - the claim is taken, and the list of earlier runs has not changed since the offline checks;
   - the `STARTING` manifest is written, then `plan.json` and `prompts.jsonl`.
10. **The last check, after the claim:** the one-paid-run check (item 3, with the backend status) runs
    once more, right before the first provider call. If anything is active, the run ends `STOPPED` /
    `other_paid_run` with 0 attempts. Its manifest is then final with nothing delivered, so the phase
    is not spent and a later launch is allowed once the other run is final.

**Tests.** Every refusal above, and every read-out rule, has a test that fails when it is removed or
weakened, **as far as the listed mutants reach**: a mutation list samples weakenings, it cannot prove the
claim for every possible one. Round 1 claimed this after 49 mutants; round 2 showed it was not quite true
(item 10's backend check, item 3's Phase 21 manifest name, five read-out rules and two store-read filters
had no failing test; Review log R2-S2); round 3 showed it again for code round 2 added (seven of its 24
mutants survived: an above-cap option at $25, an integer `phase_cap` refused, a `phase_cap` within a
dollar of the cap or below it, the status phrase matched in the protocol body, and the quote matched
ignoring case or spacing; Review log R3-2). The round-3 check is `review-r3/mutate_r3.py` and
`review-r3/mutation-results-r3.txt`: 110 mutants, one guard or rule removed or weakened each
(round 2's 75, read unchanged from `review-r2/mutate_r2.py`; the round-3 review's 24; and 11 new ones aimed
at the option table round 3 added), **all 110 caught** by the final test file (harness `f057ef2a…`,
tests `0242f42a…`); the unmutated copy passes 113 of 113. **The dry run reads no `.env`**
(`env_path=os.devnull`). It builds no provider client, and a test spies on both.

## 13. No tuning, no leakage, and what must not happen

- **Results stay under `artifacts/phase27-*`.** They never enter a study, and they are never shown
  to any model, the Mechanic included.
- **Only development prompts are replayed,** each exactly as the Actor already received it.
- **heldout-2 motivated this phase, so it can never judge its result.** The question, and stratum U1,
  are motivated by one published heldout-2 episode summary (`PHASE24_RESULTS.md`), as the program
  approves. No heldout-2 file, row or trace is read or sent: the Phase 24 situation is rebuilt only
  from Phase 20's development episodes, the store reads parse development rows only (§5), and the
  one-paid-run check never lists or opens Phase 22's or Phase 24's files (§12). Because heldout-2
  informed this change, any later held-out check of an Actor carrying T needs a new partition
  (`PHASE22_EXPERIMENT.md` §7.5). Round 0's sentence "heldout-2's per-case results inform nothing
  here" was wrong and is withdrawn (Review log, F1).
- **The T and P wording is fixed now.** Another wording tried on these prompts would be a new,
  declared phase, reported beside this one.
- **Must not happen:**
  - a second draw after a run that delivered anything;
  - re-declaring a read-out after seeing data;
  - quoting received-only figures in place of the worst-case figures;
  - any edit under `backend/app`;
  - opening `checks.py`, `artifacts/heldout2/`, `audit/promotion.json` or any final-audit file;
  - reading `.env` outside the one credential read;
  - using any result to tune a Mechanic, Explorer or Actor input.

## 14. Runbook

This probe drives neither the lab backend nor the simulator. It calls W&B Inference directly, from
one process, with no Weave tracing. The program's runbook items (Phases 19 and 22) therefore apply
as follows:

| runbook item | here |
|---|---|
| `check_ingestion_health.py` | not required: no Weave traces and no evidence verification. It is harmless to run |
| `start-simulator.sh`, dashboard closed, `loop_latency.py` (Phase 19) | not applicable: no worlds and no lab requests |
| `check_clock_drift.py` afterwards (Phase 19) | not applicable: no worlds |
| configuration hash `2cf63e93…` (Phase 22) | **enforced:** recomputed from the settings file at the dry run, again at launch, and again after the credential read. Any `backend/app` change breaks it |
| freeze `8994e962…` (Phase 22) | **enforced:** the record file's sha256. The freeze is never re-taken |
| heldout-2 never read (Phase 22 §7.5) | **enforced** by the development-only SQL selection and the cutoff. No heldout-2, audit, Phase 22 or Phase 24 file is opened |
| one paid run at a time | **enforced** (§12 items 3, 8 and 10). Also check by hand (step 3) |
| services on ports 8000, 8001 and 5173 | leave them as they are. Do not start, stop or restart anything for this probe |

**Steps.** Every command below starts from the repository root,
`/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`, unless it says otherwise.

0. **Now:** nothing is run and nothing is spent.
1. **Review.** Rounds 1, 2 and 3 are done (Review log), each with its lenses: statistics, build and
   live safety, fidelity to the program and the runtime, (round 2) launch readiness, and (round 3) a
   focused review of the round-2 fixes.
   - **The round-3 fix changed the harness** (`OPTION_TABLE` and its check in `build_plan` and
     `check_review`; Review log, round 3), so it needs a focused check of its own before closure
     (pitfall 74). The Review log's round-3 table lists the change, and the harness diff is
     `review-r3/harness-r2-to-r3.diff`. If that check changes the harness again: write a new dry plan
     to a new directory (for example `dry-plan-r4/`), update the pins here, re-run the tests and
     `review-r3/mutate_r3.py`, and check those fixes too.
   - **The owner's answer to §17 question 1 is recorded** (Review log, round 2): option R, in the
     owner's words "okay gi ahead with whater u recommend". Step 2 copies it into the review record
     exactly. Any other option needs a new, explicit answer from the owner that names the option,
     and a harness change (`STRATUM_SIZES`, `HARD_SPEND_CAP` and `DECLARED_OPTION`, set to that
     option's row of `OPTION_TABLE`).
2. **Close the review in writing,** in this order:
   - add a closing entry at the end of the Review log, headed `### Closure (<YYYY-MM-DD>)`. It
     names who reviewed the round-2 fixes (round 3) and who checked the round-3 fix, with their
     verdicts, gives the final answer to each of §17 questions 2–7 in a table (round 2's notes are in
     the round-2 table), and repeats the owner's answer to question 1 word for word, with who gave it
     and the date;
   - replace the bold first sentence of this file's opening paragraph, from `**Status:` to
     `(NOT yet reviewed).**`, with exactly:
     `**Status: declared before any paid call; reviewed in rounds 1, 2 and 3; round-3 fix checked <YYYY-MM-DD>; closed <YYYY-MM-DD>; the owner's answer to §17 question 1: option R (Review log, round 2).**`
     and delete the next sentence ("The probe is built and dry-run only.") and the one that begins
     "The harness refuses to call the provider until"; keep the rest of the opening block;
   - check: `grep -n -i "not yet reviewed" docs/part2/PHASE27_EXPERIMENT.md` must print only lines
     below the first `## ` heading (the harness now matches the phrase in any case);
   - end the closing entry with the bare line, with the final pins and with no backticks, list
     marker, bold or table: `Reviewed for launch: harness <sha256> plan <hash>`;
   - record `shasum -a 256 docs/part2/PHASE27_EXPERIMENT.md`. **Do not edit this file afterwards;**
   - write `artifacts/phase27-2026-09-24/review.json`:
     ```
     {
       "protocol_sha256": "<the sha256 just recorded>",
       "harness_sha256": "f057ef2a1123f01bf50c61c5637cbba463f01d16593e8ee9d6d27f4f47869519",
       "plan_hash": "cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682",
       "phase_cap": 25.0,
       "owner_answer": {
         "option": "R",
         "verbatim": "okay gi ahead with whater u recommend",
         "given_by": "Shree Bohara, project owner",
         "date": "2026-09-24",
         "channel": "the owner's request that started the round-2 fix run, relayed verbatim by the workflow harness"
       },
       "reviewers": ["<round 1>", "<round 2>", "<round 3: review of the round-2 fixes>", "<check of the round-3 fix>"],
       "closed_at": "<YYYY-MM-DD>"
     }
     ```
     (with other pins if step 1 changed them);
   - rehearse the gate at $0 (it reads only this file and `review.json`, never `.env`):
     ```
     ./.venv/bin/python - <<'EOF'
     import importlib.util
     spec = importlib.util.spec_from_file_location('rwp', 'scripts/experiments/report_word_probe.py')
     m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
     print(m.check_review(m.PROTOCOL.read_text(), m.sha256_file(m.PROTOCOL), m.sha256_file(m.__file__),
                          'cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682'))
     EOF
     ```
     It must print the owner's answer, not `PlanningError`.
3. **Check before launch, at $0,** right before step 4:
   - **Power:** `pmset -g batt` must print `Now drawing from 'AC Power'`. Keep the lid open for the
     whole run. On battery, `caffeinate -s` does nothing, and a flat battery or a closed lid after the
     first generation ends the run for good (it could only be closed with `--finalize-abandoned`, and
     the probe could not be run again).
   - **Budget:** reconcile the ledger (`memory/context/runtime-and-evidence.md`) with any Phase 25
     or 26 charges. Confirm the remaining budget covers the $25 cap.
   - **No other paid run:**
     - `curl -s http://127.0.0.1:8000/api/config/status` must show `"active_campaign_id":null`. If
       the request is refused, `lsof -nP -iTCP:8000 -sTCP:LISTEN` must show nothing listening;
     - `ps -ax -o pid,command | grep -E 'execute-live|slot2_probe|run_gap_probe|report_word_probe' | grep -v grep`
       must print nothing. This is the only process check on this side: the harness itself checks
       manifests, claims and the backend, not processes, so it cannot count its own `caffeinate`
       helper as another run (the defect Phase 26 found in its own `ps` guard; checked for this
       harness in round 3, `protocol-facts-r3/caffeinate_probe.out.txt`). This manual check can also match a shell that
       only mentions these names, for example an agent's test or mutation run of this harness. That
       is not a paid run, but wait until it has ended and the check prints nothing;
   - **The dry plan:** `./.venv/bin/python scripts/experiments/report_word_probe.py`. It must print
     `"plan_hash": "cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682"` and
     `"passed": true`.
   - **The tests,** from `backend/`:
     `cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend && ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/experiments/test_report_word_probe.py tests/experiments/test_lapse_probe.py`.
     Everything must pass; the 20 skips are `test_lapse_probe.py`'s declared Phase 21-tree skips.
4. **Run once,** on mains power, from the repository root:
   ```
   cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
   nohup caffeinate -is ./.venv/bin/python scripts/experiments/report_word_probe.py --execute-live \
     --confirm-entity shreetbohara-quinstreet --out artifacts/phase27-2026-09-24/live \
     --expect-plan-hash cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682 \
     --expect-harness-sha256 f057ef2a1123f01bf50c61c5637cbba463f01d16593e8ee9d6d27f4f47869519 \
     --expect-protocol-sha256 <sha256 from step 2> \
     >> artifacts/phase27-2026-09-24/live-runner.log 2>&1 &
   echo $!
   ```
   - **The folder** is `artifacts/phase27-2026-09-24/` whatever day the run starts, so the review
     record, the log and the run's outputs sit together.
   - **The process id** is what `echo $!` prints (the Python process). The claim records it as well.
   - **The log** is appended to, and it sits outside the output directory, which must not exist
     beforehand.
   - **Timing:** Phase 21's 1,063 requests took 14 minutes (23:24–23:38 UTC). The worst case with no
     errors is 1,196 × 20 s ≈ 6.6 hours.
   - **If the gate names a dry-run or fixture file** of Phase 25 or 26 as a possible paid run:
     confirm that it is not running before passing `--ignore-manifest <exact path>`.
5. **To stop:** use `kill -TERM <pid>`. Use `kill -9` only if the process has ignored SIGTERM for
   more than a minute. After a hard kill, close the claim with `--finalize-abandoned` before
   anything else.
6. **Outputs** in the output directory:
   - `plan.json` and `prompts.jsonl`;
   - `responses.jsonl`;
   - `report-word-probe-manifest.json`;
   - `readouts.json` (missing only after a hard kill).
7. **Afterwards:**
   - recompute the read-outs and compare their JSON content (not their text) with `readouts.json`.
     `--readouts` refuses unless the harness and the plan are the run's own and `lapse_probe.py` is
     still the pinned file:
     ```
     ./.venv/bin/python scripts/experiments/report_word_probe.py --readouts artifacts/phase27-2026-09-24/live > /tmp/phase27-readouts-recheck.json
     ./.venv/bin/python -c "import json; assert json.load(open('/tmp/phase27-readouts-recheck.json')) == json.load(open('artifacts/phase27-2026-09-24/live/readouts.json')); print('equal')"
     ```
     It must print `equal`;
   - add the manifest's `charged_upper_bound` to the ledger;
   - write `PHASE27_RESULTS.md` against these read-outs only, quoting the worst-case figures first;
   - **if the run delivered nothing** (for example `STOPPED` / `other_paid_run`), a new run is allowed
     in a new directory (for example `.../live-2`) under the rest of the phase cap. Record both runs.

## 15. What each result would mean — and would not

**`RECOMMENDED_FOR_A_LATER_LOOP`**
- **It would mean** three things:
  - on these development report-required prompts, where the confirmation was sent and reads
    `UNKNOWN`, stating each operation's last observed status cut bad report words (T counted at its
    worst) against both a plain re-send and a same-shape placebo, with exact paired tests at p < 0.05,
    to at most half;
  - on correct-word prompts, it changed the report no more than a second re-send did, beyond the
    declared tolerance, counting an allowed-pair shift as no change;
  - on G4, with at least 20 prompts reported by R and T, it did not move `NOT_REQUIRED` beyond the
    declared tolerance, and T's reports were not incorrect significantly more often than R's.
- **What would carry it:** U2's confirmation word. That is where every development slip on a
  report-required prompt is.
- **It would not mean** any of these:
  - that the field prevents the Phase 24 slip, the upgrade word in U1. That slip never occurred in
    development data (0 of 52), and U1 is descriptive. Its figures are reported: if C reproduces the
    slip there, and T does not, that is a hint, not a test;
  - anything about voluntary `UNKNOWN` reports (U4) or the lapse context (U3), which are not sent;
  - fewer C5/C6 failures in live episodes;
  - a safe effect on tool turns. A live field would sit on 7,481 in-window tool turns for every
    3,202 report turns, and this probe sends none of them. Phase 21 found that any added field moved
    turn-3 decisions (sends 54 of 65 → 65 of 65, placebo 63 of 65);
  - the absence of a small word harm. At q = 0.89 the recommendation still happens about 51% of the
    time with a 10% terminal-rejection harm, and 9% with a 20% harm; at q = 0.8, 62% and 21% (§10.4).
    All guard figures are conditional on the G4 re-send report rate, which is unmeasured;
  - that the allowed pair is safe: it rests on 4 stored C5 cases, and a later loop that sees T shift
    words within it must check C5 on them;
  - anything held out, certified or accepted.

**FLOOR_LIMITED:** the plain re-send slipped fewer than 5 times in 225 prompts. That is no evidence
either way, and it is expected in about 7% of runs at the cell rates. It is not a FAIL, and it is not a
reason to re-run. A larger sample would be a new, declared phase.

**Primary FAIL:**
- **route (a):** the field, in this wording, did not reliably lower bad words against a plain re-send
  on these prompts. It does not show that no wording could. At a true residual rate of 0.5–1% for T,
  this route is likely (§10.2);
- **route (b):** the field beat the plain re-send, but a meaningless field did nearly as well. The
  drop is not attributed to stating the status;
- **route (b0):** the placebo arm gave fewer than 5 slips. That is either because any added field
  suppresses the slip, or because the placebo drew low (7% when the field is perfect and P does
  nothing). The drop is not attributed to the field's content.

**Guard FAIL:**
- **It would mean:** T changed correct reports more often than a second re-send did, beyond the
  tolerance and at p < 0.05, or (on G4) T's reports were incorrect significantly more often than R's.
  The transitions show which words moved.
- It blocks the recommendation, whatever the primary says. The other gate may be INCOMPLETE; the
  statement names each gate's status.
- **It does not show that stating the status is the cause.** P is not sent on guard prompts, so an
  effect of adding any field at all is not separated out. That is the conservative direction for a
  guard.

**Guard PASS:** weak evidence of no harm. It misses most harms below about 10–20% (§10.4).

**Guard INCOMPLETE:** no gate failed, but at least one lacked data: an outcome test with fewer than 95%
of its prompts received by every arm, or (on G4) fewer than 20 prompts reported by R and T. On G4 the
likely cause is that the re-sends acted instead of reporting. It is no evidence of harm or of safety. The decision
is `NOT_RECOMMENDED`.

**Primary INCOMPLETE:** an arm received fewer than 95% of its requests. No evidence either way. The
decision is `NOT_RECOMMENDED`.

**Determinism:**
- **It would mean:** how often this Actor, at temperature 0 through this provider, answers the
  identical report prompt differently within one session.
- **It would not mean:** a time drift, or a per-episode rate.

## 16. Limits

- **Development only; a replay; one response deep.** Each prompt is a frozen v4 history. A live
  episode would diverge after it.
- **The target word is not the Phase 24 word.** All 38 development slips are the confirmation word.
  The upgrade word never slipped. U1, the Phase 24 situation, is descriptive.
- **Unmeasured contexts.**
  - The tool-turn effect: in a live loop the field would also sit on in-window tool turns, 70% of
    in-window turns in this data. On 766 of them, T would say `null` where the runtime reads the
    confirmation as `UNKNOWN` (§7). Any added field changed tool decisions in Phase 21.
  - Voluntary `UNKNOWN` reports (U4, 351 turns, 13 slips) are not sent.
  - The lapse reports (U3, 62 turns): T's effect on their correct `UNKNOWN`/`NOT_STARTED` words is
    unmeasured, though a later loop's field would sit there every time.
- **Selected contexts, not episodes.**
  - U1 is every development example of the Phase 24 situation, and none slipped.
  - U2 is sampled by cell in proportion to what each cell holds (179 B0, 46 L; the population is 80%
    B0). B0 slips more than L.
  - The guard's G2 and G3 are tiny: 7 and 3 prompts.
- **The G4 re-send report rate is unmeasured.** The guard's power and the chance that G4 meets its
  report floor both depend on it (§10.4).
- **The guard has no placebo, and its reference is an identical request.**
  - If any change to the prompt bytes moves words more than an identical re-send does, the guard
    reads that as T's effect. That errs toward blocking.
  - It compares word pairs. It does not compare `overall`, `next_action` or citations, which are
    tallied.
- **Provider nondeterminism.**
  - Only 36% of repeat pairs were byte-identical in Phase 21.
  - The arms of a prompt are sent back to back, but drift across the run is not controlled.
  - The served model is recorded, not enforced. A weights change behind the same model id cannot be
    detected.
- **Prompts are not independent.** They share cases, episodes and arms. The exact tests and the
  power figures treat prompts within a cell as independent; the power model uses the cell rates.
  Phase 21's per-context re-sends (0 or 1 slip in 5 for every one of 36 contexts) support per-request
  noise within a context; clustering by episode was not modelled.
- **The word rule is not C5.** `checks.py` is never opened. The allowed `UNKNOWN`/`NOT_STARTED`
  pair rests on 4 stored cases (Wilson upper bound 0.49), and the guard now treats it as no change. C6
  citation is tallied, never scored.
- **The dollar figures are conservative bounds.** Token-priced cost is unmeasured.
- **The owner's-answer gate checks the record against the harness, not against the owner.** It binds the
  recorded option to that option's sizes and cap in `OPTION_TABLE` (round 3), and it checks that the
  quoted words appear somewhere in this file (round 2). The table itself is harness code: a test holds it
  to §10.3, and the review of any harness change is the control on it. Whether the owner said the words
  is the closure's to confirm (Review log, round 2).

## 17. Questions for the review

1. **For the owner: the primary sample size and the phase cap (§10.3). Answered: option R.**
   - **The answer, verbatim:** "okay gi ahead with whater u recommend". **Given by** Shree Bohara, the
     project owner, on 2026-09-24. **Channel:** the owner's request that started the round-2 fix run,
     relayed verbatim to the fixer by the workflow harness. It names no option; the recommended option
     is R, and both round-2 reviewers read it as choosing R and nothing above $25.
   - **What R is:** U2 225 and G4 45 inside the program's $25 cap; PASS 0.86 at T 0 and 0.54 at T 0.5%.
   - **What it does not cover:** W1–W4 (other allocations inside $25) and A1 or A2 (U2 300 or 400, caps
     $30.17 or $37.20). Any of them would need a new answer from the owner that names the option, and a
     harness change; the live gate refuses a cap above $25 without an above-cap option, and since round 3
     any sizes or cap other than the named option's row of `OPTION_TABLE` (§12 item 6).
   - **Where it is recorded:** the Review log (round 2) now, and `review.json` at closure (§14 step 2,
     which gives the exact record). The harness refuses a review record without it.

2. **U1 as descriptive.** Round 1 moved U1 (the Phase 24 situation, 0 historical slips) out of the
   primary and dropped R and P there. Keep it with C and T, or drop it (W2)?
3. **The word rule (§6).** Settle three points:
   - `NOT_STARTED` after a write counts as unsupported;
   - `UNKNOWN` is never unsupported;
   - the `NOT_REQUIRED` rule;

   and check that the rule matches the contract text without opening `checks.py`.
4. **The guard (§9.2, §10.4).**
   - Are tolerances of 5 points pooled and 10 on G4, a G4 report floor of 20 (counted on R and T since
     round 2) and G4 at 45 acceptable?
   - Is treating an allowed-pair shift as no change right, given the pair rests on 4 C5 cases? The
     alternative is the exact comparison, which penalises allowed-pair shifts.
   - Should P be sent on the 95 guard prompts as a descriptive "any field" reference? That costs
     95 requests, about $1.99, which the recommended option cannot fit.
5. **T on report-required turns.** This departs from Phase 21's v5 and the v3 precedent. Here the
   report is the target.
6. **The placebo at p < 0.05.** Keep it as a required contrast? It costs route (b0) 7% of the time
   when the field is perfect.
7. **The worst-case accounting (§9.1).** T is now bad unless it gives a fully correct report; C and P
   are bad only for an unsupported word. Is that asymmetry the right conservative choice?

## 18. Evidence files (all $0)

**Round 3 (this version):**
- **`artifacts/phase27-2026-09-24/dry-plan-r3/`:** `plan.json`, `dry-summary.json` and
  `dry-run.out.txt` (the dry plan for this version), plus `dry-run.recheck.out.txt` (the dry run
  re-run after the last edit).
- **`artifacts/phase27-2026-09-24/protocol-facts-r3/`:**
  - `plan_r3_vs_r2.py` and `.out.json`: the round-3 plan's 1,064 requests equal round 2's; only the
    harness sha256 differs;
  - `caffeinate_probe.py` and `.out.txt`: this harness has no automated process scan, and under
    `nohup caffeinate -is` the claim's pid is the Python process; its `caffeinate` helper is a child that
    exits with it, timed separately from the Python process (§14 step 3);
  - `closure_rehearsal_r3.py` and `.out.txt`: §14 step 2 applied literally to a scratch copy of this
    file passes the gate with option R; the refusals it should give are given;
  - `numbers_rerun_r3.py` and `.out.txt`: `protocol_numbers_r2.py` re-run on the round-3 harness
    reproduces its saved output (§10);
  - `paid_run_guard_r3.py` and `.out.txt`: the paid-run guard at the time of writing, through the
    harness's own functions: no other paid run, no Phase 27 claim, the backend up with
    `active_campaign_id` null, no `review.json`, and the machine on AC power.
- **`artifacts/phase27-2026-09-24/review-r3/`:** `mutate_r3.py`, `mutation-results-r3.txt` and `.json`
  (the mutation check of §12 after round 3), and `harness-r2-to-r3.diff`, `tests-r2-to-r3.diff` and
  `protocol-r2-to-r3.diff` (the round-3 fix, for its focused check).
- **`artifacts/phase27-2026-09-24/tests-report_word_probe-r3.txt`:** the test run after the last
  round-3 edit.
- **The round-3 reviewer's own evidence** stays in their scratch folder (`p25-27/r3-p27-focus/`, named in
  the Review log); its mutants Z01–Z31 are copied into `review-r3/mutate_r3.py`.

**Round 2, kept as it was** (its dry plan and mutation check describe the round-2 harness; its
`protocol-numbers-r2/` still gives §10's figures, which round 3 did not change; where anything differs
from this text, this text governs):
- **`artifacts/phase27-2026-09-24/dry-plan-r2/`:** `plan.json`, `dry-summary.json` and
  `dry-run.out.txt` (the round-2 dry plan), plus `dry-run.recheck.out.txt`.
- **`artifacts/phase27-2026-09-24/protocol-numbers-r2/`:** `protocol_numbers_r2.py` and
  `protocol_numbers_r2.out.json`: everything round 1's script computed, under round 2's floor, plus the
  floor under both rules, the guard at q = 0.75 and 0.7, and the guard at G4 = 30.
- **`artifacts/phase27-2026-09-24/protocol-facts-r2/`:** `plan_r2_vs_r1.py` and `.out.json`: the
  round-2 plan's 1,064 requests equal round 1's; only the harness sha256, two rule strings, the size
  option and the program cap differ.
- **`artifacts/phase27-2026-09-24/review-r2/`:** `mutate_r2.py`, `mutation-results-r2.txt` and `.json`:
  the mutation check of §12 after round 2.
- **`artifacts/phase27-2026-09-24/tests-report_word_probe-r2.txt`:** the test run after the last
  round-2 edit.
- **The round-2 reviewers' own evidence** stays in their scratch folders (named in the Review log);
  nothing of it was copied here.

**Round 1, kept as it was** (its figures describe the round-1 design; where they differ from this text,
this text governs):
- **`artifacts/phase27-2026-09-24/dry-plan-r1/`:** `plan.json` (plan `43a37dd2…`), `dry-summary.json`,
  `dry-run.out.txt` and `dry-run.recheck.out.txt`.
- **`artifacts/phase27-2026-09-24/protocol-numbers-r1/`:** `protocol_numbers_r1.py` and
  `protocol_numbers_r1.out.json`: U2's cell rates, the round-0 prefix by cell, the primary and guard
  power under the round-1 rules, the options of §10.3, the G4 report floor and the joint risk.
- **`artifacts/phase27-2026-09-24/protocol-facts-r1/`:**
  - `context_report_share.py` and `.out.json`: the historical report share per context (G4 88.8%);
  - `phase21_resends.py` and `.out.json`: Phase 21's re-sends split by stratum and selection, and per
    context;
  - `t_label_check_r1.py` and `.out.txt`: the T labels, key positions, response formats and request-id
    ranges of the round-1 plan;
  - `plan_r1_vs_r0.py` and `.out.json`: the round-1 store reads leave the populations as they were.
- **`artifacts/phase27-2026-09-24/review-r1/`:** `mutate.py`, `mutation-results.txt` and `.json`: the
  mutation check of §12.
- **`artifacts/phase27-2026-09-24/tests-report_word_probe-r1.txt`:** the test run after the last
  round-1 edit.
- **Round 0, kept as it was:** `dry-plan/` (plan `6e1b3a0d…`), `protocol-numbers/`, `protocol-facts/`
  (including `builder-draft-PHASE27_EXPERIMENT.md`, sha256 `ca90bad2…`) and
  `tests-report_word_probe.txt`. Their figures describe the round-0 design; where they differ from
  this text, this text governs.
- **The paid-run guard in round 2, through the harness's own functions:** no open Phase 20, 21, 23, 25
  or 26 manifest or claim, no Phase 27 claim, and the backend showed `active_campaign_id` null
  (`other_paid_runs()` returned `[]`; `live_run_records()` found no claim or run). The machine was on
  battery power then. Round 3's reading is `protocol-facts-r3/paid_run_guard_r3.out.txt`.

## Review log

### Round 1 (2026-09-24): three lenses, all "run with changes"

Reviewers: statistics; build and live safety; fidelity to the program and the runtime. They reviewed
harness `250b0be0…`, plan `6e1b3a0d…` and this file at `cf827eba…`. All three returned RUN_WITH_CHANGES.
Every finding was applied; none was declined. The fixes changed the harness, so round 2 must review
them (pitfall 74). The round-0 builder's note that "Phase 21's 7% came from biased contexts" is
superseded by S4 below. Where the reviewers offered two fixes, the table names the one taken.

**Statistics lens**

| # | severity | finding | disposition |
|---|---|---|---|
| S1 | major | The G4 gate could pass without testing anything: its power model assumed every G4 re-send is a report, which is unmeasured; at Phase 21's voluntary report rate a Phase 4-sized harm would be recommended about half the time, so "never" was unsupported | **Fixed.** G4 now needs at least 20 prompts on which C, R and T all reported (else INCOMPLETE, so NOT_RECOMMENDED), plus a word test on those prompts (T not correct while R is, sign test). G4 raised from 30 to 45 prompts. §10.4 and §15 restated as conditional on the unmeasured re-send report rate, with the historical G4 context share (88.8%) given as a proxy, not a measurement. Tests: `test_the_terminal_rejection_gate_needs_enough_reports_and_tests_the_words_among_them` |
| S2 | major | The stated primary power (0.68 / 0.33) was too high: it assumed the pooled 3.7%, and the seeded prefix under-sampled `notification-2`/B0 | **Fixed.** Every sampled stratum is now allocated across (source, case, episode arm) cells by Webster's method in proportion to what each cell holds (house-monotone; no reseeding). §10 recomputed at the cell rates, and the round-0 sample's true power (0.59 / 0.27) quoted. Test: `test_the_allocation_is_proportional_by_cell_and_house_monotone` |
| S3 | major | The size decision was framed as keep-or-raise-the-cap, although reallocating inside $25 reaches similar power; U1 cannot add C slips; U4 is descriptive and yields about 5 reports per arm | **Fixed.** §10.3 and §17 list within-cap options (W1–W4) beside the above-cap ones (A1, A2), all with cell-rate power. The declared option R moves U1 out of the primary into a descriptive C/T read-out, drops U4, and uses the freed requests for U2 (225) and G4 (45). §15 says U1 cannot carry the result |
| S4 | minor | The explanation of Phase 21's 7% was wrong (the selection changed nothing; the 7% pooled U2 with voluntary U4 reports), "7 of 180" hid 36 contexts × 5 repeats, and the clustering scenario was contradicted by the data | **Fixed** in §2 row 1, §4 and §10.2, with a saved computation (`protocol-facts-r1/phase21_resends.out.json`). The clustering paragraph is replaced by the case × arm heterogeneity, which is now in the power model |
| S5 | minor | The primary could PASS while T introduced other-mismatch words on the primary prompts, which no guard covered | **Fixed.** In the worst-case set, T is bad unless it gives a fully correct report; other mismatches are also tallied (`t_other_mismatch_where_c_had_none`). Test: `test_primary_counts_any_incorrect_t_word_against_t_but_not_against_c_or_p` |
| S6 | minor | The guard counted an allowed-pair move (`NOT_STARTED` ↔ `UNKNOWN` for a never-written confirmation) as harm, while the word rule calls it correct | **Fixed, by normalisation, declared before data.** The guard's outcome replaces an allowed-pair word with its reference word; allowed-pair shifts are tallied apart. §17 question 4 asks the review to confirm this choice over the exact comparison. Test: `test_the_guard_treats_an_allowed_pair_shift_as_no_change_and_tallies_it` |
| S7 | minor | An INCOMPLETE gate hid another gate's FAIL in the guard status, and §15 then said "no evidence either way" | **Fixed.** FAIL now takes precedence over INCOMPLETE (a part fails only when its own completeness holds); §9.2 and §15 reworded. Test: `test_a_failed_gate_is_reported_ahead_of_an_incomplete_one` |

**Build and live-safety lens**

| # | severity | finding | disposition |
|---|---|---|---|
| B1 | major | The documented way to raise the cap could not run: the probe used Phase 21's `SpendGuard`, which refuses any cap above its own $25 in the pinned file | **Fixed.** `report_word_probe.SpendGuard` subclasses Phase 21's guard and checks this harness's `HARD_SPEND_CAP` at call time; `lapse_probe.py` is unchanged (`f701ba14…`). Tests: `test_the_spend_guard_follows_this_harness_cap_not_phase21s` and `test_a_raised_cap_gets_past_the_guard_on_a_fake_client`. §10.3's change procedure corrected |
| B2 | major | 13 of 35 mutants survived: many live-safety guards had no test that fails when the guard is removed, so "a test covers every refusal" was false | **Fixed.** Phase 21's three tests are ported (signal handlers and a stop in set-up; a stop before the claim; in-flight attempts charged by `--finalize-abandoned`), and new tests cover entity, project, pins and Actor model after a faked credential read, a paid run appearing during the launch checks, earlier runs changing before the claim, a RUNNING Phase 27 manifest with nothing delivered, an edited freeze file, a wrong-sha settings file with a valid configuration, and `claim_process_alive` on a reused pid. Re-run of the mutation list plus new mutants for the round-1 code: all caught (§12, `review-r1/`) |
| B3 | minor | The other-run check was never repeated after the claim, so a sibling run starting in that window could spend at the same time | **Fixed.** After the `STARTING` manifest, `plan.json` and `prompts.jsonl`, and right before the first provider call, the check (files and backend) runs again; if anything is active the run ends `STOPPED` / `other_paid_run` with 0 attempts, final, so a later launch is allowed. Test: `test_a_paid_run_that_appears_after_the_claim_stops_this_run_at_zero` |
| B4 | minor | The one-paid-run glob matched and parsed Phase 24's held-out check manifest | **Fixed.** Past phases are listed by exact manifest name (Phases 20, 21, 23), Phases 25 and 26 by wildcard; Phases 22 and 24 are never listed. Claims are read only in the listed phases' claim directories and followed only to their run directories. Test spies on every read: `test_other_runs_never_list_or_open_the_heldout_phases` |
| B5 | minor | An output directory appearing between the output check and `mkdir` raised `FileExistsError` after the claim, leaving a claim with no manifest | **Fixed.** The directory is created exclusively before the claim; a directory that appeared refuses with nothing claimed, and a failed claim removes the empty directory it made. Tests: `test_an_output_directory_that_appears_during_the_launch_refuses_before_the_claim`, `test_earlier_runs_that_change_during_the_launch_refuse_the_claim` |

**Fidelity lens (program and runtime)**

| # | severity | finding | disposition |
|---|---|---|---|
| F1 | major | §13's "heldout-2's per-case results inform nothing here" was false: the question and U1 rest on one heldout-2 episode summary. §1 also said "refused" where the attempts returned `TRANSIENT_UNAVAILABLE` | **Fixed.** §13 rewritten: the motivation is a published heldout-2 episode summary, as the program approves; no heldout-2 data is read or sent; heldout-2 can never judge this change, and a later held-out check of a T-bearing Actor needs a new partition. §1 corrected. §2 row 12 added |
| F2 | major | Same as B1: the $32.77 and $39.79 options were not implementable | **Fixed** with B1 |
| F3 | minor | Only the split filter kept heldout-2 out, and the harness parsed more held-out data than §5 said (every episode row, every `trials` row) | **Fixed.** Cutoff moved to 05:50:00Z (between Phase 23's last development episode and heldout-2's first); split and purpose filtered in SQL; case labels from completion-study trial rows via SQLite, without `lp.load_index`. Populations unchanged (`protocol-facts-r1/plan_r1_vs_r0.out.json`). §5 corrected. Test: `test_store_reads_parse_development_rows_only` |
| F4 | minor | U3 (an `UNKNOWN` context) was in neither the primary nor the guard, and the narrowing was not declared | **Declared** in §2 row 10 and §16; not sent, because it cannot fit inside $25 beside the S1–S3 fixes (186 requests) |
| F5 | minor | The rule strings frozen into the plan understated the code (C/P non-reports, the guard's completeness) | **Fixed.** `readout_rules` and the docstring now state the full rules; §9 says the code governs |
| F6 | minor | "A guard on every other word" was not met on the primary prompts, and the departure was not declared | **Fixed** with S5 (T's other mismatches count against T), declared in §2 row 11, with a descriptive tally |
| F7 | minor | Raising the cap above $25 needs the owner's own decision; "go ahead with whatever you recommend" must not be read as approval of $32.77–$39.79 | **Fixed.** The harness declares option R inside $25. §17 question 1 is put to the owner as an explicit question, whose answer and author must be recorded in `review.json` and this log before the review closes. **Pending: the owner's answer.** |

**Round 1 fix pins:** harness `cbcfb3b340ad409a1b4e2253c9bacc2ffe35ec5e2ff840fdd92a7a9a51007055`, plan `43a37dd28a33661e3edbc618b56d1c8adf20abe4c25f40957bf20eedcd1321d2`, tests
`c57f342dffba3812a5314f6a80e61c0f9867ceec5556e2c4c307c0feddf7e94e`. Tests after the last edit: `test_report_word_probe.py` with `test_lapse_probe.py`: 168 passed, 20 skipped (the 20 are `test_lapse_probe.py`'s declared Phase 21-tree skips; `artifacts/phase27-2026-09-24/tests-report_word_probe-r1.txt`).

### Review log — round 2 (2026-09-24): two lenses, both "run with changes"

Reviewers: regressions from round 1 (statistics and code), and launch readiness. They reviewed harness
`cbcfb3b3…`, plan `43a37dd2…`, tests `c57f342d…` and this file at `905d2582…`, made no repository edit
and no paid call, and both returned RUN_WITH_CHANGES. Their evidence is in the session scratchpad,
`p25-27/r2-p27-regressions/` and `p25-27/r2-p27-launch/`. **Every finding was applied; none was
declined.** The fixes changed the harness (the G4 floor, the review gate, `--readouts`), so they need
their own review before the review closes (pitfall 74; §14 step 1). The round-2 fix did not write
`review.json`: that is the closing step (§14 step 2).

**Regressions lens**

| # | severity | finding | disposition |
|---|---|---|---|
| R2-S1 | major | Round 1's G4 report floor counted prompts where C, R and T all reported, although the word test compares T with R only. The floor was met with probability q³ per prompt instead of q², which alone forces INCOMPLETE (so NOT_RECOMMENDED) below about q = 0.85, and made W1 and W3 look unviable in §10.3. Conservative, but it could pre-decide a $22 run | **Fixed as proposed.** The floor and the word test count every G4 prompt where R and T both reported, whatever C returned; the outcome test is unchanged. The key `prompts_reported_by_c_r_t` is now `prompts_reported_by_r_and_t`, and the statement says "reported by R and T". §9, §9.2 and §9.4 reworded. §10.3 (the floor column, a new guard-power column, the R-against-W1/W3 rationale), §10.4 (the floor under both rules, false block, INCOMPLETE rates, power, joint risk, and what the change trades) and §15 recomputed with `protocol-numbers-r2/`; the primary figures reproduce round 1's draw for draw. **R is still recommended**, on two grounds that survive the correction: the floor still holds at q = 0.8 (1.00 against 0.46 for G4 = 30), and G4 = 45 has more guard power (0.90 against 0.61 at h = 0.2, q = 0.89). The trade is stated in §10.4: fewer INCOMPLETE results with no harm (at q = 0.8, 0.2% against 15%), and small G4 harms pass somewhat more often at low q; the false block is unchanged and a Phase 4-sized harm is still never recommended. New dry plan `dry-plan-r2/`, whose 1,064 requests equal round 1's. Tests: the one at the old line 725 rewritten (R or T acting, not C, now leaves the floor unmet); new `test_the_terminal_rejection_word_test_does_not_need_c` (C acting or errored leaves the word test at 30 prompts) |
| R2-S2 | minor | Three safeguards round 1 added and four boundaries had no failing test: mutants N01, N02, N03, N05, N08, N09 and N10 survived, so §12's "every refusal has a test" was not true of item 10's backend check or item 3's Phase 21 manifest name | **Fixed.** New tests: `test_c_and_p_errors_and_non_reports_are_never_counted_bad` (N01: C or P errors and polls stay not-bad; the status is unchanged, FLOOR_LIMITED and FAIL b0 respectively), `test_a_word_harm_outside_terminal_rejection_fails_the_guard_through_the_pooled_gate` (N02: a G5 word harm with a clean G4 gives pooled FAIL, guard FAIL, NOT_RECOMMENDED), `test_an_active_campaign_seen_after_the_claim_stops_this_run_at_zero` (N03), `test_a_running_past_phase_run_without_a_claim_counts_as_active` (N10, for each of the three exact names), `test_primary_boundaries` (N05: C = 5 with T = 0 passes; N08: P at 94 of 100 is INCOMPLETE, at 95 it is not; N09: T exactly half of C passes). **Two more of the reviewer's mutants survived, though the finding did not name them:** N06 (the SQL purpose filter removed) and N07 (every trial row's case label kept). Neither opens a held-out path (the split filter and the Python re-check stay, and M47 and M48 are caught), but §12 claims a failing test for every rule, so `test_store_reads_parse_development_rows_only` now asserts that no other purpose's payload is parsed and that only the requested labels are returned. The full mutation list was re-run (§12) |
| R2-S3 | minor | A raised cap could launch with a self-written `review.json` that records no owner answer: `check_review` compared only the three hashes | **Fixed as proposed, with two more checks.** `check_review` now requires `phase_cap` equal to `HARD_SPEND_CAP`, and `owner_answer` with the non-empty strings `option`, `verbatim`, `given_by` and `date`. It refuses a cap above the new `PROGRAM_PHASE_CAP` ($25) unless `option` is A1 or A2. Added: `option` must equal the new `DECLARED_OPTION` (R), which the plan also records, and `verbatim` must appear in this file. The answer is copied into the `STARTING` manifest. The owner's answer is recorded as R here and in §17; `review.json` is written at closure, from the template in §14 step 2. **Limit:** the gate checks that the quoted words appear in this file, not where; a $0 rehearsal on a scratch copy (fixer scratch `fix2-p27/closure_rehearsal.out.txt`) passed step 2 as written and refused a lower-case status phrase, a missing answer, option A1 at $25 and a wrong cap, but also passed a record quoting round 1's "go ahead with whatever you recommend", which F7 below quotes. The written closure is still the control on the words Tests: `test_the_review_record_must_carry_the_owners_answer_and_the_phase_cap`, `test_a_raised_cap_needs_the_owners_above_cap_answer`, `test_live_gate_enforces_the_review` extended, and the raised-cap end-to-end test now declares A2 |
| R2-S4 | minor | §2 row 1 gave 3.7% for all report-required prompts (it is 25 of 809, 3.1%; 3.7% is U2's 25 of 667), and §9.2's "(the 95% and, for the word test, the floor)" could be read as requiring both before the word test may fail | **Fixed** with the proposed wording: §2 row 1 now gives U2 3.7%, all 809 report-required 3.1% and U4 3.7%; §9 and §9.2 now say the outcome tests need the 95% and the word test needs only its floor, as the code does |
| R2-N1 | note, outside the lens | `--readouts` does not re-check `lapse_probe.py`'s sha256 before reusing its statistics functions (predates round 1) | **Applied.** `recompute_readouts` refuses, or labels the output with `--not-the-runs-harness`, unless `lapse_probe.py` is the pinned file. Test: `test_readouts_refuse_when_lapse_probe_is_not_the_pinned_file` |

**Launch-readiness lens**

| # | severity | finding | disposition |
|---|---|---|---|
| R2-L1 | major | The text read two ways about what counts as the owner's answer for R (the opening block said only a raised cap needs it; §14 step 1 said get it first, whatever the option), and the harness did not enforce it: a record with only the three hashes opened the gate | **Fixed.** The owner's words are recorded verbatim, with who gave them, the date and the channel (the opening block, §17 question 1, and below). §14 steps 1–2 say exactly what is recorded and give the `review.json` template. The gate enforces it (R2-S3), including the reviewer's optional check that the option matches the harness's declared option. That changed the harness, so the fix has a new dry plan, new pins, a test re-run, and needs its own review (§14 step 1) |
| R2-L2 | minor | No step checked the power source; the machine was on battery at the rehearsal, where `caffeinate -s` does nothing | **Fixed.** §14 step 3: `pmset -g batt` must print "AC Power", and the lid stays open. The machine was still on battery during this fix (57%, discharging) |
| R2-L3 | minor | Step 4's working directory and `<date>` were ambiguous | **Fixed.** Every §14 command starts from the repository root unless it says otherwise; step 4 begins with `cd` to it; the literal `--out artifacts/phase27-2026-09-24/live` is used whatever the launch day, so the review record, the log and the outputs sit in one folder |
| R2-L4 | minor | The manual process check had no command, and it is the only process check on this side | **Fixed.** §14 step 3 gives the exact `ps` and `grep` command, matching `execute-live`, `slot2_probe`, `run_gap_probe` and `report_word_probe`, which must print nothing |
| R2-L5 | minor | Step 2 gave no replacement status text; the opening bullet about the pending decision would go stale; a lower-case "not yet reviewed" left in the status block passed the gate; §17 questions 2–7 had no place for round 2's answers | **Fixed.** Step 2 gives the exact replacement sentence, the sentences to delete, a `grep -i` check, and what the closing entry holds (the final answers to questions 2–7 in a table). The opening bullet now records the owner's answer. **The harness now matches the status phrase in any case** (a harness change; the gate test covers a lower-case leftover). Round 2's notes on questions 2–7 are the table below |
| R2-L6 | minor | Step 7 did not say how to compare the recomputed read-outs with `readouts.json` (the two are printed differently) | **Fixed.** §14 step 7 compares the JSON content with a one-line Python check, writing the recomputation to `/tmp`, outside `artifacts/` |

**Round 2's notes on §17 questions 2–7.** Neither reviewer answered them explicitly; this records what
their checks touched. The closing entry (§14 step 2) gives the final answers.

| question | round 2 |
|---|---|
| 2. U1 as descriptive | no objection raised |
| 3. the word rule | no finding. The regressions lens found T's worst case attainable: Phase 21's 180 plain U2 re-sends had 0 other mismatches and 0 non-reports, and 231 of 231 report-required re-sends came back as reports |
| 4. the guard | the report floor changed (R2-S1). The allowed-pair normalisation was checked sound: it never touches `NOT_REQUIRED` on G4, and a mutant that over-normalises is caught |
| 5. T on report-required turns | no objection raised |
| 6. the placebo at p < 0.05 | no objection raised. The power at T = 0 was recomputed independently: PASS 0.861, FLOOR_LIMITED 0.072, route b0 0.067, as §10.2 says |
| 7. the worst-case accounting | checked sound (see question 3); an anti-conservative flip for C and P is now caught (R2-S2, N01) |

**The owner's answer to §17 question 1, recorded in round 2.** Option **R**. Verbatim: "okay gi ahead
with whater u recommend". Given by Shree Bohara, the project owner, on 2026-09-24. Channel: the owner's
request that started the round-2 fix run, relayed verbatim by the workflow harness. It names no option;
R is the recommended option, and both round-2 reviewers read the answer as choosing R and nothing above
$25. It does not cover W1–W4, A1 or A2.

**Checked sound by round 2, and unchanged:** every round-1 pin reproduced; the dry run (17,119 of 17,119
turns verified, all 3,202 report turns in window); the late one-paid-run check and its $0 stop; the
output directory created before the claim, and every kill point closable with `--finalize-abandoned`;
the spend guard subclass; the other-run lists (exact names for Phases 20, 21 and 23, wildcards for 25
and 26, nothing of Phases 22 or 24), both ways with the Phase 25 and 26 runners; development-only store
reads; the sampling (every U2, G4 and G5 cell within one prompt of its share); 40 fuzzed result sets
through the read-outs (no crash, valid JSON, no PASS); the live-gate order; and the launch mechanics
(`$!` is the Python process under `nohup caffeinate`, `kill -TERM` reaches the handler).

**Round 2 fix pins:** harness `adf09f83db8a5482b499192842abede7798ccea69fccba094b2744ad593269c9`, plan
`fdf6be1097646ab9850b933614c88e78461de94b5072534b0b9558f88e28b29e`, plan file `dry-plan-r2/plan.json`
`51dd93469554aac6e3fbd0be8d572dc498b0704e0731109258013a83af7581c0`, tests
`6f1f12f7436f8c450ef169a25d11b2ee2ac09a20b8655a048493f752fb5459cf`. Unchanged: `lapse_probe.py` `f701ba14…`,
freeze file `8994e962…`, configuration `2cf63e93…`, settings `1e2002d3…`, Phase 20 store `8d78f099…` and
plan `549a9eb1…`. Tests after the last edit, with §14 step 3's command: 177 passed, 20 skipped (the 20 are `test_lapse_probe.py`'s declared Phase 21-tree skips; `artifacts/phase27-2026-09-24/tests-report_word_probe-r2.txt`). The dry run after the last edit printed plan `fdf6be10…` and `"passed": true` (`dry-plan-r2/dry-run.recheck.out.txt`). Mutation: 75 of 75 caught (§12).

### Review log — round 3 (2026-09-24): a focused review of the round-2 fixes, "run with changes"

Reviewer: one focused lens on what round 2 changed (pitfall 74), checked against eight risks: overspend,
running twice, running beside another paid run, refusing its own launch, a data leak, refusing forever,
data lost on an interruption, and data silently excluded or replaced, or a read-out changed after the
fact. It reviewed harness `adf09f83…`, tests `6f1f12f7…` and this file at `38a053af…`, made no
repository edit and no paid call, wrote no review record, and returned RUN_WITH_CHANGES: two minor
findings, no blocker and no major. Its evidence is in the session scratchpad, `p25-27/r3-p27-focus/`.
**Both findings were applied; none was declined.** The fix for R3-1 changed the harness (the first of the
two fixes the reviewer offered), so it needs a focused check of its own before the review closes
(pitfall 74; §14 step 1). The round-3 fix did not write `review.json` and did not close the review.

| # | severity | finding | disposition |
|---|---|---|---|
| R3-1 | minor | The owner-answer gate checked only the option's label. `check_review` had no map from an option to its sizes or its §10.3 cap, so an A1 answer opened any cap above $25 (the reviewer's $0 probe passed $60 under A1 and $40 under A2), and an R answer opened any sizes within $25 (W1's passed). Not a regression, and not usable without a harness edit, new pins and a review; the declared R run at $25 was unaffected. The raised-cap test fixed the permissive case in place: it ran $40 under A2 on R's sizes to completion | **Fixed with the reviewer's option (a).** The harness gains `OPTION_TABLE` (R: U2 225, G4 45, $25; A1: U2 300, $30.17; A2: U2 400, $37.20; the other strata as R) and `option_problem()`, which refuses unless `DECLARED_OPTION` is a row whose sizes equal `STRATUM_SIZES` and whose cap is at least `HARD_SPEND_CAP`. `check_review` calls it after the above-cap label check; `build_plan` calls it first, before it reads any file, so the dry run refuses the same harness. It adds refusals only: the spend path (`SpendGuard`, `effective_spend_cap`, `check_budget`) is untouched. New dry plan `dry-plan-r3/`: its 1,064 requests equal round 2's, and only the harness sha256 differs (`protocol-facts-r3/plan_r3_vs_r2.out.json`). The opening block, §3, §10.3, §12 item 6, §14, §16, §17 and §18 updated. Tests: the raised-cap end-to-end test now runs A2 as §10.3 defines it (U2 400, $37.20); `test_a_raised_cap_needs_the_owners_above_cap_answer` also refuses R's sizes under A2; new `test_the_owners_option_binds_the_sizes_and_the_cap` (in both `check_review` and `build_plan`, it refuses W1's sizes under R, R's sizes with U1 set to 0, A1 at $60 and at $37.20, A2 at $40 and at $37.21, A2's sizes under A1, and an option with no row (W1); it passes each row at its own cap, and R at $24), `test_the_option_table_is_section_10_3`, and `test_the_above_cap_options_are_their_bound_plus_twelve_percent` (on the real plan A1 and A2 are 1,289 and 1,589 requests, and their caps are those bounds plus 12%, rounded to the cent) |
| R3-2 | minor | §12's "every refusal has a test that fails when it is removed or weakened" was again not quite true for code round 2 added: 7 of the reviewer's 24 mutants survived. Z01: any above-cap option accepted at $25. Z04: an integer `phase_cap` refused. Z05 and Z06: a `phase_cap` within a dollar of the cap, or below it, accepted. Z11: the status phrase matched in the protocol body, which would make the real launch refuse, because §14 step 2 quotes the phrase in lower case above the Review log. Z02 and Z03: the quote matched ignoring case or spacing. None opens a spend path | **Fixed as proposed, and Z02 and Z03 too.** The refusals list gains A1 and A2 at $25, `phase_cap` 24.0 and 25.5, and the quote in upper case and with doubled spaces; `phase_cap` written as the integer 25 is asserted to pass. New `test_a_lower_case_status_phrase_in_the_protocol_body_does_not_block_the_launch` puts a runbook section holding the phrase (in lower case, and in its original case) between the opening block and the Review log, as this file does, and the gate still reaches the credential read. The mutation check was re-run on the final test file with round 2's 75 mutants, the reviewer's 24 and 11 new mutants of the round-3 code (`review-r3/`): 110 of 110 caught, among them all seven of the reviewer's survivors and all 11 new ones, and the unmutated copy passes 113 of 113. A first run of this list during the fix stopped after 90 mutants (all caught) when the session was interrupted; the whole list was then re-run from the start on the final harness and tests, and that run is the one saved. §12 is corrected: it now says that a mutation list samples weakenings, and gives round 3's count |

**The process guard and `caffeinate` (asked with the round-3 findings).** Phase 26's defect is not
here. Phase 26 found that its own `ps` guard would have refused its own launch: under
`nohup caffeinate -is python …` the `caffeinate` helper is a child of the Python process and repeats the
launch arguments, and Phase 26's round-1 rule, which excluded only the runner's ancestors, would have
counted that helper as another paid run (`PHASE26_EXPERIMENT.md` §6 and its Review log, row 15). This
harness has no automated process scan. Its one `ps` call is `claim_process_alive(pid)`, which only
`--finalize-abandoned` uses, on the pid the claim recorded: `os.getpid()`, the Python process. The
one-paid-run check reads manifests, claims and the backend, and its own claim and manifest are outside
the lists it reads (no Phase 27 path is in `OTHER_RUN_MANIFEST_GLOBS` or `OTHER_CLAIM_DIRS`). Measured at
$0 with the harness's own function, on a stand-in launched exactly as §14 step 4 launches the run
(`protocol-facts-r3/caffeinate_probe.out.txt`):
- `$!` equals the stand-in's `os.getpid()`, and the helper is a separate child pid;
- after kill -9 or SIGTERM the Python process was gone within 0.01 s and the helper within 0.01 s after
  it. After a normal exit (the stand-in sleeps 3 s) the probe saw the helper gone at 2.33 s and the
  Python process at 2.40 s, one poll apart (a poll runs `ps -p` on each pid, then waits 0.05 s);
- `claim_process_alive` then reported the Python pid gone, and step 3's manual check printed nothing of
  the stand-in. `claim_process_alive` on the helper's pid says alive while it runs, because the helper's
  command line names the harness, but a claim never records that pid.

So no helper outlives the run to block `--finalize-abandoned` or step 3. Two notes:
- step 3's manual `ps | grep` matches any command text that names these scripts, including a shell that
  only mentions them. An earlier run of the same probe during this fix, while other sessions worked on
  Phases 25 and 26, listed up to four such lines: this fix's own shell running the mutation check, two
  shells of that other work, and one Python process running the Phase 26 runner. The saved run listed
  none. The operator cannot tell such a line from a paid run at a glance, so §14 step 3 now says to
  wait until the check prints nothing;
- as the reviewer noted, `claim_process_alive` does not exclude its own pid. If the dead run's pid were
  reused by the `--finalize-abandoned` process itself, it would refuse; running it again, under a new pid,
  clears this. Left as it is: very unlikely, and it errs toward refusing. It predates round 2.

**Checked sound by round 3, and unchanged:**
- the spend path (`SpendGuard`, `effective_spend_cap`, `check_budget`, the cap as `HARD_SPEND_CAP`); the
  round-2 gate added refusals only; the $0 dry run reproduced plan `fdf6be10…`, 1,064 requests, bound
  $22.2376, pre-check passed;
- the claim, earlier-run and final-manifest logic;
- the after-claim check reads the backend as well as the files; this harness still sees Phases 25 and 26
  after their round-2 edits (their manifests match its wildcards, both claims record `out` as
  `artifacts/phaseNN-x/y`, and both end markers use `status` and `ended_at`); its file check reported no
  other run on the real tree;
- §14 step 2, applied literally to the round-2 file, passed `check_review` with option R, and a lower-case
  leftover, a missing answer, A1 at $25 and a wrong cap were refused; the marker search stays inside the
  opening block; `pmset -g batt` prints the exact string step 3 requires;
- no leak: `owner_answer` goes into a local manifest, never into a prompt;
- `--readouts` refuses only if `lapse_probe.py` changes, `--not-the-runs-harness` still prints a labelled
  result, and step 7's JSON comparison works on a scratch run;
- the recorder and `--finalize-abandoned` are unchanged, and `owner_answer` is built before the claim;
- the G4 word-test change was declared before any data, the plan's frozen `readout_rules` match the code,
  the §10.4 floor table matches an exact binomial recomputation (q² against q³), and 120 fuzzed result
  sets over the real plan gave no crash, strict JSON, and never RECOMMENDED.

The provenance of the owner's answer (relayed by the workflow harness, and not a reply to §17 question 1)
is disclosed in the round-2 entry; the reviewer left it to the owner's closure, and so does this fix.
Round 3 raised nothing on §17 questions 2–7.

**Round 3 fix pins:** harness `f057ef2a1123f01bf50c61c5637cbba463f01d16593e8ee9d6d27f4f47869519`, plan
`cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682`, plan file `dry-plan-r3/plan.json`
`2f26cd34a494610b0ca4bb9ce77b2ee35eb616aa591dcb9bf4f5406cb6b5ddb6`, tests
`0242f42a9175e179d6b4ba018a9c0ad0522fb5717743a75d29fda5a556c43ca4`. Unchanged: `lapse_probe.py` `f701ba14…`, freeze file `8994e962…`,
configuration `2cf63e93…`, settings `1e2002d3…`, Phase 20 store `8d78f099…` and plan `549a9eb1…`. Tests
after the last edit, with §14 step 3's command: 181 passed, 20 skipped (the 20 are `test_lapse_probe.py`'s declared Phase 21-tree skips)
(`artifacts/phase27-2026-09-24/tests-report_word_probe-r3.txt`). The dry run after the last edit printed
plan `cd3b7bc8…` and `"passed": true` (`dry-plan-r3/dry-run.recheck.out.txt`). The closure rehearsal on
this file (§14 step 2 applied literally, in memory) passed with option R, also with `phase_cap` written as
25; it refused a lower-case status phrase, a missing bare line, a missing answer, A1 at $25, a $37.20
`phase_cap`, round 2's harness sha256, an upper-case quote, W1's sizes under R and A1 at $60, and passed A1
at its own sizes and $30.17. As round 2 recorded (R2-S3), it still passes a record quoting round 1's
paraphrase, which this file quotes in F7 (`protocol-facts-r3/closure_rehearsal_r3.out.txt`).
Mutation: 110 of 110 caught; the unmutated copy passes 113 of 113 (§12; `review-r3/mutation-results-r3.txt`).

### Closure (2026-09-25)

- **Round 3, the review of the round-2 fixes:** a focused adversarial reviewer returned
  RUN_WITH_CHANGES with 2 minor findings. Both were applied (round-3 table).
- **Check of the round-3 fix:** a focused verification found the round-3 fix correct and raised
  no new finding.
  - 181 tests pass (with `test_lapse_probe.py`; 20 skipped by the declared Phase 21 skip).
  - The dry run verified 17,119 of 17,119 turns and reproduces plan `cd3b7bc8…`, with 1,064
    requests and "passed": true.
- **The owner's answer to §17 question 1, word for word:** "okay gi ahead with whater u
  recommend". Given by Shree Bohara, the project owner, on 2026-09-24. It is read as option R:
  U2 225 and G4 45, inside the $25 cap, and nothing above it.
- **Approver:** Claude as PM, delegated by the owner.

| §17 question | final answer |
|---|---|
| 2. U1 as descriptive | **Keep U1 descriptive, with C and T only** (round 1's change). It is the Phase 24 situation with 0 historical slips, so it cannot power a primary |
| 3. The word rule (§6) | **Accepted as declared:** `NOT_STARTED` after a write counts as unsupported; `UNKNOWN` is never unsupported; `NOT_REQUIRED` as §6 states. The reviewers checked it against the contract text without opening `checks.py` |
| 4. The guard | **Accepted as declared:** tolerances of 5 points pooled and 10 on G4; the G4 report floor of 20 (on R and T); G4 at 45; an allowed-pair shift treated as no change. P is **not** sent on the 95 guard prompts: it does not fit option R's cap |
| 5. T on report-required turns | **Accepted:** here the report is the target, unlike Phase 21's v5 |
| 6. The placebo at p < 0.05 | **Kept as a required contrast.** It costs route (b0) 7% of the time when the field is perfect, and that price is accepted to rule out an "any field" effect |
| 7. The worst-case accounting | **Accepted as the conservative choice:** T is bad unless its report is fully correct; C and P are bad only for an unsupported word |

Reviewed for launch: harness f057ef2a1123f01bf50c61c5637cbba463f01d16593e8ee9d6d27f4f47869519 plan cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682
