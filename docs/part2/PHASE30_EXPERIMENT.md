# Phase 30 protocol — narrow report-status field replay probe (non-scoring)

**Status: declared before any paid call; NOT yet reviewed.** No paid, model or W&B call has been made for this
phase, and nothing under `backend/app` was edited. Every number below comes from a $0 dry run or a saved $0
computation. The harness sends nothing until the review is closed as §12 step 2 describes; §10 lists everything
its live gate checks. Review rounds 1, 2 and 3 ran on 2026-09-25; every finding is applied (Review log). Round 1's
fixes changed the harness, and round 2 checked them (pitfall 74). Round 2's three findings and round 3's four (the
fidelity lens named in §12 step 1) changed only this file, so no pin moved. All three lenses have reported. The
review is not closed; §12 step 2 says how it closes.

Pins of this draft, after round 3 (round 1's, unchanged; the live gate requires both strings in this file): harness
ca3b8b9d0df0960b4fff4f6ae8369f5cc6677815e9ee94b73f9c40e106681317 plan
05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34

- **Program:** `docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md`, Phase 30 (cap about $20).
- **Harness:** `scripts/experiments/report_narrow_probe.py`. **Tests:**
  `backend/tests/experiments/test_report_narrow_probe.py`.
- **Imported, never edited:** Phase 27's `report_word_probe.py` (which imports Phase 21's `lapse_probe.py`) and
  Phase 26's `run_gap_probe.py` (its process rule only). All three are pinned by sha256 (§3).
- **Evidence folder:** `artifacts/phase30-2026-09-25/` (§17).
- **The owner's approval of the program:** "go ahead with whatever u recommend" (Shree Bohara, project owner,
  2026-09-25; the owner's request that started this build, relayed verbatim by the workflow harness). It covers
  the program's direction and this phase's $20 cap. It does not replace this phase's own review and approval. The
  review record must quote the same words (§10 item 6).
- **Departures:** §2 lists every place this protocol departs from the program or from the build brief.

## 1. The question

Phase 27 found two things (`PHASE27_RESULTS.md`):
- **The field works where it is aimed.** On report-required turns where the confirmation was sent but reads
  `UNKNOWN` (stratum U2), a field that restates each operation's last observed status (T) removed the `PENDING`
  slip: 0 of 225 against 4 of 225 for a plain re-send (C).
- **The field does harm where it is not aimed.** On terminal-rejection turns (stratum G4) the same field said
  `FAILED / null`, and the Actor stopped filing its correct `FAILED / NOT_REQUIRED` report in 23 of 45 prompts. It
  polled the order's status again instead.

**This phase asks:** if the same field is shown **only** on report-required turns where the field would state
`UNKNOWN` for some operation, and **never** on a terminal-rejection turn or anywhere else, does it
1. leave every other context untouched, and
2. not make the report words worse where it is shown, measured as non-inferiority against a plain re-send?

**Why the narrow window should remove Phase 27's harm.** It works on two levels:
- **G4 is never in the window.** Every G4 turn is voluntary, and none has an `UNKNOWN` status (§5.3).
- **The Actor cannot poll where T2 is shown.** A report-required turn is sent with the strict final-report JSON
  schema (`response_format_for(response_contract='actor_final_report')`), which admits only a report. The harm
  Phase 27 saw was a delay (poll instead of report), and a response to these turns cannot be a poll. Only the words
  can change, and the in-window guard (§7.2) watches the words.

**The Phase 24 situation is inside the window.** Phase 24's failing episode used all 8 turns, and its report came
on the reserved last turn with the upgrade reading `UNKNOWN` (`PHASE24_RESULTS.md`, a published summary). That is
a report-required turn with an `UNKNOWN` status, so T2 would have been shown. heldout-2 is still never read, and
it can never judge T2 (§11).

This is a **replay probe**:
- it re-sends frozen historical development prompts and reads one response from each;
- it scores nothing (no C1–C8, no referee, no gate);
- its best outcome is **a recommendation for a later loop**. Nothing is adopted here.

**What it cannot show, said plainly:** that the field **lowers** the slip. The live re-send slip rate on U2 has
measured between about 1.8% (Phase 27: 4 of 225) and 3.9% (Phase 21: 7 of 180), about 42 hours apart (§4). Even a
field that removed every slip would reach p < 0.05 on an exact test only about 55–99% of the time at this size,
depending on that rate: 0.55–0.66 at 1.6–1.8%, and 0.99 at the historical cell rates (about 3.7%) or at a flat
3.9% (§8.3). So a reduction cannot be reliably shown. It is reported, and it never decides anything.

## 2. Where this protocol departs from the program or the build brief

| # | program or brief | this protocol | why |
|---|---|---|---|
| 1 | the guard: "the guard populations are the same as Phase 27's"; the brief: send arms C, R and T2 on them | **the guard on Phase 27's guard strata is structural and costs $0.** On all **2,070** development prompts of G1–G5 (not only Phase 27's 95), and on every other turn outside the window, T2's request is **byte-identical** to the control's. The plan refuses to exist otherwise (§5.3) | T2's window needs an `UNKNOWN` status, and no G-stratum prompt has one. Sending C, R and T2 there would send **the same request three times**. That measures nothing, and Phase 27's word test (no tolerance, p < 0.05) could still block a harmless field by chance. An identical request has the same response distribution, so the expected excess over R is exactly zero and Phase 27's tolerances (pooled 0.05, terminal rejection 0.10, word test p < 0.05) hold in expectation. Terminal rejection is never in the window: 0 of 1,219 turns of the terminal-rejection episodes, and 0 of 286 G4 prompts |
| 2 | "shown ONLY when an operation's latest status is `UNKNOWN`" on report turns | **report turn = a report-required turn** (`final_report_required` is true) | the lab knows a report-required turn before it sends it. It cannot know which voluntary turn will carry a report (pitfall 18). **The cost:** voluntary `UNKNOWN` reports (U4: 13 of the 38 historical `UNKNOWN`-context slips) are not addressed. U2's 25 are |
| 3 | "a narrower report-status field" | **T2's value is exactly Phase 27's T value** on the same turn: the same key, note and content. Only the window differs | one change at a time. On every U2 prompt, T2's request is what Phase 27 sent for T |
| 4 | the brief: R, "the re-send reference for the guard, as Phase 27" | **R is the re-send reference where T2 is actually shown besides U2:** the in-window non-target strata U1 and U3, with arms R and T2 and a **variant of Phase 27's word test** (exact one-sided sign test, p < 0.05) that counts a received non-report as not OK. It is run twice: pooled over U1 + U3, and on U3 alone (round 1) | these are the only contexts, besides U2, that T2 touches in development data. There the test compares T2 with an exchangeable plain re-send, as Phase 27's word test compared T with R. Phase 27's test counted only prompts where both R and T reported, with a floor of 20; this one counts every prompt where both were received. U3 is also tested alone because U1's requests repeat Phase 27's (§6), so U3 is the only context besides U2 never sent with the field, and a harm there must not be diluted by U1 (§8.4) |
| 5 | "non-inferiority on slips" (declare the margin) | **U2, Tango's score test for paired proportions, margin 1.5 percentage points, one-sided α 0.024**, on Phase 27's worst case for T2 (round 1; round 0 declared 2 points at 0.025) | §7.3 and §8. Against Phase 27's re-send slip rate of about 1.8%, 2 points is nearly a doubling (against Phase 21's 3.9%, about half as much again). 1.5 points costs nothing for a field like Phase 27's T and halves the chance of recommending a field 1 point worse than C (§8.2). α 0.024 rather than the usual 0.025, because at 1.5 points the exact size at 0.025 slightly exceeds 0.025 (0.0256 at a C-only rate of 3%). At 0.024 the exact size at the margin is at most 0.0243 on a 0.1-point grid of C-only rates from 0 to 12% |
| 6 | "does the field keep the slip at or near 0" | **answered descriptively:** T2's worst-case bad count on U2, with its Wilson interval (§7.3). The decision uses non-inferiority | "at or near 0" names no test. At about 1.8% for the re-send (Phase 27; Phase 21 measured 3.9%, §4), nothing at this size can separate 0 from a small rate (§8.3) |
| 7 | the same guard populations as Phase 27 | **U2 prompts that Phase 27 sent are not sent again** (225 excluded, 442 left, 316 sampled). **U1 is re-sent in full** (Phase 27 sent all 52, and there is no other U1 prompt) | T2 was designed after seeing Phase 27's responses on those U2 prompts. Fresh prompts keep the new result independent of the data that motivated it. U1 has no fresh prompt, so it is re-sent and labelled as such. **"Fresh" means not sent in Phase 27** (round 3, fidelity F2): 20 of the 316 were among Phase 21's re-sent U2 contexts. Each of those 20 was re-sent 5 times in Phase 21 with a request byte-identical to this phase's C, and 5 of the 100 re-sends slipped (5.0%, one on each of 5 prompts). None was ever sent with the field, and each new send is still a fresh draw (§6) |
| 8 | (Phase 27 used a placebo P) | **no placebo** | non-inferiority claims no reduction, so nothing has to be attributed to the field's content. The budget goes to U2 |

## 3. What is fixed

**Setup** (as Phase 27, checked by the imported code):
- **Actor:** `deepseek-ai/DeepSeek-V3.1` at temperature 0, with 2,000 output tokens and a 20 s timeout.
- **Response format:** the stored contract. All 860 requests are report-required, so every one uses the strict
  final-report JSON schema (`actor_final_report`).
- **Actor context:** only `faultlab-actor-context/v4-indexed-evidence` episodes are rebuilt.
- **Settings:** `artifacts/phase16-2026-09-22/settings-phase17.json`. The dry run reads no `.env`.
- **What does not run:** no Mechanic, no Explorer, no lab backend, no simulator, no Weave tracing. Nothing creates
  a campaign, study, trial, world, policy or store row. Both stores are opened read-only.
- **Code:** nothing under `backend/app` changes. T2 exists only in the harness.

**Pins:**

| item | value |
|---|---|
| harness `scripts/experiments/report_narrow_probe.py` sha256 (round 1; unchanged by rounds 2 and 3) | `ca3b8b9d0df0960b4fff4f6ae8369f5cc6677815e9ee94b73f9c40e106681317` |
| dry plan hash (`content_hash(plan)`, round 1; unchanged by rounds 2 and 3) | `05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34` |
| dry plan file `artifacts/phase30-2026-09-25/dry-plan-r1/plan.json` sha256 | `3931f0c6d2d38ec1649cf48cb62e97098d948d751d86c563dfeb572e21cb472b` |
| round 0, superseded (kept) | harness `cbc57db1…`, plan `575df1dc…`, `dry-plan/plan.json` `ba56660c…` |
| Phase 27 harness `report_word_probe.py` (imported unchanged) sha256 | `f057ef2a1123f01bf50c61c5637cbba463f01d16593e8ee9d6d27f4f47869519` |
| Phase 21 harness `lapse_probe.py` (imported by Phase 27's, unchanged) sha256 | `f701ba148f716dd8416b603e387cdbec7772e513453f1207d307cb1927e7ebfd` |
| Phase 26 runner `run_gap_probe.py` (its process rule imported unchanged) sha256 | `5d8e16901feda8ec4f6c9ecc3d2c410e549e52e982b66c646d9812f2b271589b` |
| Phase 27 sent plan `artifacts/phase27-2026-09-24/live/plan.json` sha256 / plan hash | `2f26cd34a494610b0ca4bb9ce77b2ee35eb616aa591dcb9bf4f5406cb6b5ddb6` / `cd3b7bc805cd4a337bbaaf783ade5d9bb2c222b048cd16f1af12db0cba5e9682` |
| Phase 27 read-outs `artifacts/phase27-2026-09-24/live/readouts.json` sha256 | `c58d162a7324f4276466017dc995d3d58626b197cfe4a06ce471faa9f710593e` |
| `configuration_hash` (Phase 17 settings on the Phase 22 code), recomputed without reading `.env` | `2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba` |
| gate freeze record `artifacts/phase22-2026-09-24/gate-freeze-after.json` sha256 (the file's hash; the freeze is never re-taken) | `8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1` |
| settings file sha256 | `1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d` |
| Phase 20 store / plan sha256 | `8d78f09938f514e225cc914df33a20732fcc9ce3d09b180192e802d4284a4487` / `549a9eb18eaecfcbde88e60a4d258490b4a9e6b14ac32b237c239de6c3617426` |
| main store cutoff | episodes started before `2026-09-24T05:50:00Z` (Phase 27's; before heldout-2's first episode) |
| sample seed | `faultlab-phase30-2026-09-25` |
| per-request bound; hard phase cap; the program's cap | $0.0209; **$20.00**; $20.00 (the harness refuses to plan with a cap above the program's) |
| this document | its sha256 is typed as `--expect-protocol-sha256` and written into the review record. The plan does not include it, so editing this file changes neither pin above |
| tests `backend/tests/experiments/test_report_narrow_probe.py` sha256 (not pinned by the harness; round 1; unchanged by rounds 2 and 3) | `edf5c0867873f5e155ad2ab5d8bd6a49ef2875cb06de9542ad5dbcec9118d936` (round 0: `7b199f3a…`) |

**What moves the pins.** The plan records the harness sha256 and the sha256 of the nine files the rebuild and the
word rule depend on: `actor.py`, `progress.py`, `prompts/actor.md`, `reference.py`, `runtime.py`,
`contracts/models.py`, `policy_state.py`, `lapse_probe.py` and `report_word_probe.py`. So **any** edit to the
harness, or to any of those files, changes the plan hash, and then the live gate refuses until the pins here are
updated and reviewed. Round 1's dry run (`dry-plan-r1/`, 2026-09-25) produced the plan hash above, with
`"passed": true`. Its 860 requests equal round 0's request for request (id, prompt, arm, stratum and request
hash; `review-r1/plan_facts_r1.out.json`): round 1 changed read-out rules and thresholds, not what is sent.
Rounds 2 and 3 edited only this file, so the harness, the plan, the dry plan file and the tests keep round 1's
hashes (Review log, rounds 2 and 3).

## 4. Why, and the base rates (development evidence, $0)

**Historical words, every verified v4 development report turn, Phase 27's word rule** (re-derived by this
harness's survey: `protocol-facts/stated_by_stratum.out.json` and `protocol-facts/t2_window_survey.out.json`):

| stratum | what it is | reports | unsupported | in T2's window? |
|---|---|---|---|---|
| U1 | report-required; upgrade written, only ever `UNKNOWN`, no receipt (the Phase 24 situation) | 52 | 0 | **yes** (all 52) |
| U2 | report-required; upgrade `SUCCEEDED`; confirmation written, reads `UNKNOWN` | 667 | **25 (3.7%)** | **yes** (all 667) |
| U3 | report-required; upgrade `SUCCEEDED`; confirmation reads `UNKNOWN`, never written (the lapse reports) | 62 | 0 | **yes** (all 62) |
| U4 | voluntary; some operation `UNKNOWN` | 351 | 13 (3.7%) | no: voluntary |
| G1–G5 | Phase 27's guard strata: no `UNKNOWN` status (G4 = terminal rejection, 286) | 2,070 | 0 | no: never |

All 3,202 development report turns are in one of these rows (809 report-required, 2,393 voluntary).

**Live re-sends in Phase 27** (the same model and settings; `artifacts/phase27-2026-09-24/live/readouts.json`):

| where | C (plain re-send) | T (T2's value) | P (placebo) |
|---|---|---|---|
| U2, 225 prompts | 4 slips (1.8%) | **0** | 3 (1.3%) |
| U1, 52 prompts (descriptive there) | 1 slip: `PENDING / NOT_STARTED`, the Phase 24 upgrade-word slip; 51 of 52 correct | **0**; 52 of 52 correct | not sent |
| G4, 45 prompts (voluntary turns) | — | changed the outcome on 28 (R: 6); 23 polled instead of reporting | not sent |

- **Phase 21's plain re-sends of U2 contexts** (the same model and settings; round 3, fidelity F2): 36 contexts,
  each re-sent 5 times on its report-required turn, slipped on **7 of 180 (3.9%, Wilson 95% [1.9%, 7.8%])**
  (`artifacts/phase21-2026-09-23/live/`, re-derived in `review-r3/fidelity_fix_checks_r3.out.json`). Phase 27's own
  protocol quoted this figure (`PHASE27_EXPERIMENT.md` §2 row 1 and §4). Each context slipped 0 or 1 times in its 5
  re-sends, none twice.
- **So the live re-send slip rate on U2 has measured between about 1.8% and 3.9%, about 42 hours apart:** Phase
  27's C slipped on 4 of 225 (1.8%, [0.7%, 4.5%]; C and P together 7 of 450, 1.6%) on 2026-09-25, and Phase 21's
  re-sends on 7 of 180 on 2026-09-23 (UTC). The two intervals overlap. The historical rate is 3.7%. The power
  figures (§8) use 1.6%, 1.8% and the historical cell rates (model A, about 3.7%). Model A roughly brackets Phase
  21's rate: at a flat 3.9%, every §8.2 and §8.3 figure is within 0.04 of model A's, and the chance of PASS for a
  field like T, a field that does nothing and a field 0.5 to 2 points worse than C is within 0.004 (§8, model D).
- **20 of this phase's 316 U2 prompts are among Phase 21's 36 contexts** (§2 row 7, §6): 5 of their 100 re-sends
  slipped.
- **U3:** 0 historical slips. Phase 21 re-sent 51 of these 62 prompts under its plain control C, once each, and
  all 51 came back correct (`SUCCEEDED / UNKNOWN`; `review-r1/plan_facts_r1.out.json`, from
  `artifacts/phase21-2026-09-23/live/`). So R's error rate on U3 is measured: 0 of 51 (Wilson 95% upper bound
  7.0%). U3 has never been sent with the field.
- **U1:** R's error rate is 1 of 52 (Phase 27's C), and T was correct on 52 of 52.
- **Where T's harm came from:** G4 turns, where T stated `FAILED / null`. T2 is never shown on a G4 turn.

## 5. The field, the window and the $0 structural check

### 5.1 The window (declared; `t2_window` in the harness)

T2 is added to a turn's user message **if and only if** all three hold:
1. **the turn is report-required:** `final_report_required` is exactly `true` (the reserved last turn, or every
   turn after business closure: `EpisodeMeter.final_turn`);
2. **the field would state `UNKNOWN` for at least one operation:** the latest delivered observation that matches
   the operation under the runtime's binding (`app.agents.progress._matching_operation_data`) reports `UNKNOWN`;
3. **the turn is not a terminal rejection:** no delivered observation of the upgrade operation, and no upgrade
   receipt, shows `FAILED`. Any earlier observation counts, not only the latest: an upgrade shown `FAILED` and
   read `UNKNOWN` afterwards is still outside the window (`terminal_rejection`; §15 says what a later loop must
   copy).

On every other turn, every arm is **byte-identical** to the stored request.

**What condition 3 does in development data:** it removes no turn. No report-required turn with an `UNKNOWN`
status also shows the upgrade `FAILED` (the survey counts none). It is there for contexts development data lacks.

### 5.2 The field (exact text)

When T2 is shown, it is **exactly Phase 27's T** on that turn: the key `last_observed_status`, the same note, and
for each operation the latest delivered matching status, verbatim, with its `obs-k` label, or `null`. It sorts
second in the turn message (keys are in canonical order), right after `final_report_required`. Two examples, from
the plan's `arms.shape`:

```
U2: "last_observed_status":{"note":"Copied from the most recent delivered observation that reports a status for each operation, with that observation's label; null means no delivered observation has reported one.","notifications":{"evidence":"obs-6","status":"UNKNOWN"},"orders":{"evidence":"obs-3","status":"SUCCEEDED"}}
U1: "last_observed_status":{"note":"…the same note…","notifications":null,"orders":{"evidence":"obs-4","status":"UNKNOWN"}}
```

What T2 states, and the reference words, on every in-window prompt (`protocol-facts/stated_by_stratum.out.json`):

| stratum | T2 states (orders / notifications) | reference words | prompts |
|---|---|---|---|
| U1 | `UNKNOWN` / null | `UNKNOWN` / `NOT_STARTED` (`UNKNOWN` for the confirmation is also correct: the allowed pair) | 52 |
| U2 | `SUCCEEDED` / `UNKNOWN` | `SUCCEEDED` / `UNKNOWN` | 667 |
| U3 | `SUCCEEDED` / `UNKNOWN` | `SUCCEEDED` / `UNKNOWN` (`NOT_STARTED` also correct: the allowed pair) | 62 |

T2 never names a report word to use, and it never states anything that contradicts the reference words.

### 5.3 The $0 pre-check (the structural guard)

`survey` runs over **every** verified development v4 turn before any plan exists, and the plan is refused if any
must-be-zero line is not zero. From the dry plan (`dry-plan-r1/dry-summary.json`; round 1 did not change the
survey, and its counts equal round 0's). Two cross-checks, of different strength:
- **the window from raw observations:** the harness's own `independent_t2_window` recomputes the window from the
  raw observation dicts, by code separate from the runtime's (the row "the window computed from raw observations"
  below);
- **the window rule only:** `protocol-facts/t2_window_survey.py` imports only Phase 27's harness and re-applies
  the window rule. It reuses Phase 27's computed field (`context['stated']`), so it checks the rule, not how the
  field is computed.

| check | result | kind |
|---|---|---|
| turns verified (both stored hashes match) | **17,119 of 17,119** (3,066 main-store and 138 Phase 20 episodes) | measured |
| turns in T2's window | **781**: U1 52, U2 667, U3 62 | measured |
| in-window turns whose historical response was not a report | **0**: every in-window turn is a report turn | measured |
| in-window turns that follow an earlier in-window turn of the same episode | **0**, so each replayed history is exactly what a later loop would have sent | measured |
| turns of terminal-rejection episodes in the window | **0 of 1,219** | measured |
| the harness's window against the window computed from raw observations by separate code (`independent_t2_window`) | 0 disagreements | measured |
| report-required turns where the field's `UNKNOWN` differs from the runtime's `PolicyState` `UNKNOWN` | 0 of 809 | measured |
| control differs from the stored request | 0 | measured (the rebuild is exact) |
| turns outside the window where T2 differs from the stored request | **0 of 16,338** | by construction |
| Phase 27 guard prompts (G1 18, G2 7, G3 3, G4 286, G5 1,756) in the window | **0 of 2,070**; all 2,070 byte-identical to the control | by construction, given the measured 0 of 809 above |
| in-window turns that are not report-required, or show the upgrade `FAILED` | 0, 0 | by definition of the window (code checks only) |
| in-window turns where T2 differs from Phase 27's T construction | 0 | code check |

**Read it honestly (pitfall 72).** Outside its window T2 *is* the control, so "0 differ" is true by construction.
What the pre-check measures is that the rebuild reproduces every stored request, that the harness's window agrees
with separate code, and that the window reaches only the 781 report turns. **So in development data, T2 can change
the Actor's input on 781 report turns and on nothing else,** and the live money goes to those turns only (§6).
It says nothing about contexts that development data does not contain (§14).

## 6. Populations and arms (exact counts)

**Sampling rule.** A stratum marked "all" sends every prompt. U2 first drops the 225 prompts Phase 27 sent. Its 316
prompts are then allocated across (source, case, episode arm) cells in proportion to what each cell holds, by
Phase 27's Webster rule (house-monotone). Within a cell the harness sends the first prompts ranked by
`sha256("faultlab-phase30-2026-09-25:<stratum>:<source>:<episode>:<turn>")`. Declared once, never redrawn.

| population | stratum | available | sent | arms | requests |
|---|---|---|---|---|---|
| **primary (non-inferiority)** | U2, not sent in Phase 27 | 442 | **316** | C, T2 | 632 |
| **in-window guard** | U1 (all; re-sent) | 52 | 52 | R, T2 | 104 |
| | U3 (all 62; 51 were re-sent under C in Phase 21, all correct; never sent with the field) | 62 | 62 | R, T2 | 124 |
| **structural guard** | G1–G5 and every other turn outside the window | 16,338 turns | 0 | — ($0, §5.3) | 0 |
| **total** | | | **430 prompts** | **860 distinct request bodies** | **860** |

- **U2 composition** (sent of available): `notification-2`/B0 147 of 205, `notification-2`/L 19 of 26,
  `notification-18`/B0 51 of 72, `notification-18`/L 45 of 63, `notification-3`/B0 54 of 76. Each cell is within
  one prompt of its proportional share. Expected C slips: 11.8 at the historical cell rates, 5.6 at Phase 27's live
  1.8%, 4.9 at 1.6%, and 12.3 at Phase 21's 3.9%. (12 of the 316 prompts carried a historical slip; each re-send is
  a fresh draw.)
- **20 of the 316 U2 prompts were re-sent before** (round 3, fidelity F2): they are among the 36 U2 contexts that
  Phase 21 re-sent 5 times each under its plain control, and each of those 100 Phase 21 requests is byte-identical
  to this phase's C request for its prompt. 5 of the 100 slipped (5.0%, Wilson 95% [2.2%, 11.2%]), one on each of 5
  prompts (`review-r3/fidelity_fix_checks_r3.out.json`). None of the 20 was ever sent with the field. They are
  "fresh" only in the sense of §2 row 7 (not sent in Phase 27), and each send here is still a fresh draw.
- **U1:** all from Phase 20's store: the transient-upgrade cases `A-c2`, `A-c3` and `A-c4`, replicas r1–r3, 5 or
  6 prompts each. Its R request is Phase 27's C request there, and its T2 request is Phase 27's T request there. So
  U1 **repeats** Phase 27's descriptive U1 comparison, where C was correct on 51 of 52 and T on 52 of 52.
- **U3:** all from the main store: `notification-2` 18, `healthy` 14, `notification-1` 13, `notification-3` 9,
  `lost-notification-response` 6, `notification-18` 2. Phase 21 re-sent 51 of them under its plain control (all
  correct); none has been sent with the field. So U3 is the only in-window context besides U2 that is fresh for
  the field, and the in-window guard also tests it alone (§7.2).
- **One prompt per episode:** each of the 430 prompts comes from a different (source, episode). No fresh U2 prompt
  shares an episode with any Phase 27 prompt (`review-r1/plan_facts_r1.out.json`).
- **Send order:** primary `r0001`–`r0632`, then guard `r0633`–`r0860`. Within a population, prompts go in a seeded
  order, and the two arms of a prompt are sent back to back in a seeded order.
- **Size:** the largest prompt is bounded at 7,603 input tokens.

## 7. Declared read-outs

**Received** means a generation arrived: status `ok` or `empty_response`. The word rule is Phase 27's, imported
(`report_word_probe.judge`). Each of a report's two words is a match, an allowed pair (`UNKNOWN` ↔ `NOT_STARTED`
for an operation never written and never shown other than `UNKNOWN`), unsupported, or another mismatch. A report
is **correct** when both words are a match or the allowed pair. C5 and C6 are not scored, and `checks.py` is never
opened.

### 7.1 Structural guard ($0)

The §5.3 pre-check, copied from the plan into the read-outs. **PASS in any plan that exists, by construction,**
because a failed pre-check refuses the plan before anything can be sent. It is not a measurement: T2 is
byte-identical to the control there and nothing is sent. The harness's statement says "by construction, not a
measurement", and the results must write it as "not applicable: T2 is byte-identical to the control there;
nothing was sent" (§11).

### 7.2 In-window guard (U1 + U3, 114 prompts; arms R and T2; two parts)

- **OK** = a received report whose two words are both correct. A received non-report counts as not OK, in either
  arm.
- **Compared** = prompts where R and T2 were both received.
- **The test, in each part:** the exact one-sided sign test on (T2 not OK and R OK) against (R not OK and T2 OK).
  No tolerance. It is a **variant** of Phase 27's terminal-rejection word test: Phase 27 counted only prompts
  where both R and T reported, with a floor of 20; here a received non-report counts as not OK, and completeness
  is counted on prompts where both were received.
- **Part 1, pooled:** U1 + U3, 114 prompts. **INCOMPLETE** unless at least 95% were compared (109); else **FAIL**
  if p < 0.05; else PASS.
- **Part 2, U3 alone** (round 1): the 62 U3 prompts. **INCOMPLETE** unless at least 95% were compared (59); else
  **FAIL** if p < 0.05; else PASS. **Why:** U1's R and T2 requests are byte-identical to Phase 27's C and T
  requests (52 of 52 each; T was correct on 52 of 52, C on 51 of 52). U3 is the only in-window context besides U2
  that has never been sent with the field. In the pooled test, a harm confined to U3 is diluted by U1's 52 prompts,
  and U1's R-only errors raise the fail boundary (§8.4).
- **The guard:** **FAIL** if either part fails; else **INCOMPLETE** if either part is incomplete; else **PASS**. A
  part fails only when its own completeness holds, and a failed part is reported ahead of an incomplete one.
- **How the read-out is quoted (round 2).** In `readouts.json` (`in_window_guard`), the top-level `status` combines
  both parts. The top-level `complete`, `planned_prompts`, `compared`, `t2_only_not_ok`, `r_only_not_ok` and
  `sign_test_one_sided_p` belong to the **pooled part only**, and the U3 part is under `alone`. So `complete: true`
  can stand beside `status: INCOMPLETE`: with 4 U3 R responses missing, the pooled part compares 110 of 114 and is
  complete, while U3 compares 58 of 62 and is not. `PHASE30_RESULTS.md` quotes, in this order:
  1. the guard's `status`;
  2. `pooled_status`, with the top-level counts and p;
  3. `alone.status`, `alone.complete`, `alone.compared` (of `alone.planned_prompts`), `alone.t2_only_not_ok`,
     `alone.r_only_not_ok` and `alone.sign_test_one_sided_p`.

  The top-level `complete` is never quoted as the guard's completeness; it is the pooled part's. §12 step 7 checks
  the statement's pooled and U3 figures against these fields, because no test checks the U3 p in the statement
  (round 2's mutant N06, §10).
- **What it takes to fail,** in each part (T2-only failures needed, by R-only failures): 0 → 5; 1 → 7; 2 → 9;
  3 → 10; 4 → 12; 5 → 13.
- **Per stratum (U1, U3), descriptive:** reports, word classes and R-to-T2 transitions.

### 7.3 Non-inferiority, the primary (U2, 316 prompts; arms C and T2)

- **Worst case for T2 (Phase 27's rule):** a T2 response is **bad unless it is a received report with both words
  correct.** So an unsupported word, any other mismatch, a non-report, and an empty, errored or missing T2 response
  all count against it. A C response is bad **only** when it is a received report with an unsupported word.
- **Counts:** b = prompts with T2 bad and C not; c = prompts with C bad and T2 not; n = 316, the planned prompts
  (every planned prompt counts, received or not).
- **Test:** Tango's (1998) score test for the difference of paired proportions. H0: P(T2 bad) − P(C bad) ≥ **0.015**
  (1.5 percentage points), against H1: < 0.015. The restricted maximum-likelihood estimate q of P(C bad, T2 not)
  solves `2n q² + (−(b + c) + δ(2n − b + c)) q − c δ (1 − δ) = 0`, with δ = 0.015. The statistic is
  `z = (b − c − n δ) / sqrt(n (2q + δ(1 − δ)))`, and p = Φ(z). A test checks the closed form against a numerical
  maximum-likelihood fit. Round 0 declared δ = 0.02 at 0.025; round 1 changed both (§2 row 5, §8).
- **PASS** if and only if **p < 0.024**. **INCOMPLETE** unless C and T2 each received at least 95% of the 316
  (301). Otherwise FAIL.
- **What it takes to pass** (the most T2-only bad prompts that still pass, by C-only bad prompts):

  | C-only bad (c) | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 10 |
  |---|---|---|---|---|---|---|---|---|---|---|
  | most T2-only bad that passes (b) | 0 | 0 | 1 | 2 | 2 | 3 | 3 | 4 | 5 | 6 |

  For example, with no discordant prompt at all p is 0.014 (PASS); b = c = 1 gives p 0.0241 (FAIL, just); b = 2,
  c = 3 passes (p 0.022), and b = c = 3 does not (p 0.052).
- **One T2 miss can decide it when C has almost no slips.** Every T2 failure counts, including an errored or
  missing response. So when C has at most one slip (c ≤ 1), a single bad T2 response fails the test. At C's
  measured rates (1.6–1.8%, with T2 near 0), c ≤ 1 happens about 2–4% of the time; at Phase 21's 3.9%, about
  0.005% of the time (`review-r3/phase21_rate_numbers_r3.out.json`).
- **Also reported, never deciding:**
  - per arm: the bad count and rate with a Wilson interval (this answers the program's "at or near 0",
    descriptively), reports, unsupported and not-correct among them, non-reports, word pairs and word classes;
    per cell;
  - the one-sided 97.6% upper bound on the difference (1 − α), by inverting the same test;
  - unsupported words where both arms reported (not a separate test).

### 7.4 The reduction (descriptive, never deciding)

- The exact one-sided McNemar test of T2 < C on (c, b), at p < 0.05.
- The same test with Phase 27's U2 discordance added: C-only 4, T-only 0, on 225 disjoint prompts, where T is T2
  on every U2 prompt. It is copied into the plan from Phase 27's pinned read-outs.
- The pooled figure is declared here, before this phase's data but after Phase 27's, whose result motivated this
  phase. So it is **descriptive only**.

### 7.5 Decision

| structural guard | in-window guard | non-inferiority | decision |
|---|---|---|---|
| PASS | PASS | PASS | **`RECOMMENDED_FOR_A_LATER_LOOP`** |
| anything else | | | **`NOT_RECOMMENDED`** |

**The statement** (written by the harness): the non-inferiority result with T2's and C's counts and Tango's p (a
PASS says "this does not show a benefit"); then the in-window guard's status, with each part's counts and p
(pooled U1 + U3, and U3 alone); then the structural guard, "PASS by construction, not a measurement (0 of 2,070
Phase 27 guard prompts in the window: T2 is byte-identical to the control there, and nothing was sent)"; then "a
reduction is not claimed", with whether the exact test reached p < 0.05. When recommended, the harness appends:
"Recommended for a later loop only: that loop must declare the same key, value and window and measure it end to
end against a concurrent control, with a held-out check on a new partition."

**Also reported, never deciding:** `overall` and `next_action` tallies per stratum and arm; reports citing every
label T2 states; C and R responses byte-identical to history; what served each request.

## 8. Power, size and boundaries (exact, $0)

**Source:** `artifacts/phase30-2026-09-25/protocol-numbers-r1/protocol_numbers_r1.py` and `.out.json` (round 1),
run on the round-1 harness with its own `noninferiority` and `mcnemar_greater`. It imports round 0's helpers
(`protocol-numbers/protocol_numbers.py`, whose output is kept for the round-0 design). Every figure is an **exact
enumeration**, not Monte Carlo; the mass lost beyond the enumeration grid is below 5 × 10⁻¹². The statistics
reviewer reproduced the round-0 figures and the 1.5-point and union-guard figures with independent code
(`review-r1/stats/`).

**The model:**
- prompts are independent;
- within a prompt the two arms are independent draws (Phase 21: each re-sent U2 context slipped 0 or 1 times in
  5, none twice; 7 slips in 180 re-sends, 3.9%, §4);
- every request is received (INCOMPLETE is not modelled).

**C's slip rate:**
- **A:** each prompt's cell historical rate (expected 11.8 C slips);
- **B:** a flat 1.8% (Phase 27's live C; expected 5.6);
- **C:** a flat 1.6% (Phase 27's live C and P; expected 4.9);
- **D (round 3, a check beside the declared models):** a flat 3.9% (Phase 21's 7 of 180; expected 12.3). Computed
  exactly with the same helpers (`review-r3/phase21_rate_numbers_r3.py` and `.out.json`), which reproduce the
  model B and C columns of §8.2 and §8.3. Every model-D figure there is within 0.04 of model A's; the chance of PASS
  on the rows a decision rests on (a field like T, no effect, and C + 0.5 to C + 2 points) is within 0.004. Model D
  is quoted where it matters (§1, §7.3, §8.3); the tables keep A, B and C.

### 8.1 Size of the non-inferiority test at the margin

With T2 exactly 1.5 points worse than C (the declared margin, α 0.024), the test passes:
- at most **0.0243** of the time on a 0.1-point grid of C-only rates from 0 to 12% (the largest at 6.7%); no grid
  point exceeds 0.025;
- **0.020–0.022** at the plausible C-only rates of 1–2%;
- 0.008 at a C-only rate of 0.

For comparison, round 0's 2 points at 0.025 reaches 0.02499 at 8% and exceeds 0.025 slightly above 8% (at most
0.0253, at 11.2%), far above any measured rate. At 1.5 points and α 0.025 the size is 0.0256 at 3%, which is why
α is 0.024.

### 8.2 Chance of PASS (non-inferiority), by what T2 really does

| T2's bad rate (worst case) | declared: 1.5 points, α 0.024 (A / B / C) | round 0: 2 points, α 0.025 (A / B / C) |
|---|---|---|
| **0 (as Phase 27's T was on U2: 0 of 225)** | **1.00 / 1.00 / 1.00** | 1.00 / 1.00 / 1.00 |
| flat 0.5% | 0.99 / 0.87 / 0.83 | 1.00 / 0.96 / 0.94 |
| flat 1% | 0.95 / 0.61 / 0.54 | 0.98 / 0.77 / 0.71 |
| flat 2% | 0.65 / 0.18 / 0.14 | 0.78 / 0.30 / 0.24 |
| **no effect (T2 = C per prompt)** | **0.15 / 0.25 / 0.27** | 0.24 / 0.38 / 0.42 |
| T2 = C + 0.5 points | 0.08 / 0.12 / 0.13 | 0.14 / 0.21 / 0.22 |
| **T2 = C + 1 point** | **0.045 / 0.053 / 0.054** | 0.08 / 0.10 / 0.11 |
| T2 = C + 1.5 points (the declared margin) | 0.023 / 0.022 / 0.022 | 0.045 / 0.047 / 0.048 |
| T2 = C + 2 points | 0.011 / 0.009 / 0.008 | 0.023 / 0.020 / 0.020 |
| T2 = C + 4 points | 0.000 / 0.000 / 0.000 | 0.001 / 0.000 / 0.000 |

- **A field that behaves like Phase 27's T passes with certainty in this model,** at either margin.
- **A field that does nothing is recommended 15–27% of the time** (24–42% at round 0's margin). **A recommendation
  does not imply benefit.**
- **A harmful field:** 1 point above C passes about 5% of the time (8–11% at round 0's margin); 1.5 points or more
  above C, at most 2.3%. A field just under 1.5 points worse, nearly a doubling of a 1.8% slip rate (about 40% more
  at 3.9%), is not ruled
  out by a PASS (§13).
- **What the tighter margin costs:** a field better than C but not perfect passes less often. A flat 1% bad rate
  passes 0.54–0.95 against 0.71–0.98 at round 0's margin; a flat 0.5% rate 0.83–0.99 against 0.94–1.00.
- **Why round 1 chose it** (review round 1, S2): it costs nothing for a field like T and halves the chance of
  recommending a field 1 point worse than C. Round 2 re-derived every figure for it and recommends keeping it
  (§16 question 2). **Going back to 2 points at α 0.025 is not a choice the closure can make:** `NI_MARGIN` and
  `NI_ALPHA` are constants in the harness and are written into the plan's `thresholds`, so it would move both the
  harness and the plan pins and need §12 step 1 in full, with another review round.

### 8.3 The reduction (descriptive): why it cannot decide

| T2's bad rate | A | B | C | pooled with Phase 27 (A / B / C) |
|---|---|---|---|---|
| 0 | 0.99 | **0.66** | **0.55** | 1.00 / 1.00 / 0.99 |
| 0.5% | 0.87 | 0.28 | 0.21 | 0.99 / 0.76 / 0.69 |
| no effect | 0.03 | 0.02 | 0.02 | 0.13 / 0.17 / 0.18 |

- **The reduction's power is about 55–99%, depending on a rate that has measured between about 1.8% and 3.9%
  (§4)** (round 3, fidelity F2). At Phase 27's live rates (B, C), even a perfect field shows a reduction on this
  phase's data only about 55–66% of the time. At the historical cell rates (A) it is 0.99, and at a flat 3.9%
  (Phase 21's rate, model D) also 0.99 (0.89 for a 0.5% bad rate, 0.03 for no effect).
- The historical rate (A, about 3.7%) is above Phase 27's live 1.6–1.8% and close to Phase 21's live 3.9%. Round
  2's text said A was "higher than any live re-send has shown"; that was true of Phase 27's re-sends only.
- **The harness quotes the lower anchor only.** Its docstring (`report_narrow_probe.py` line 62), its plan's
  read-out rule text (line 682) and its read-out note (line 1471) say "the measured ~1.6-1.8% re-send slip rate",
  and the margin's comment (line 220) says "about 1.8%". Those are Phase 27's figures. The harness is pinned, so
  they stay as they are; read them with Phase 21's 3.9% beside them.
- **So this phase does not claim a reduction either way.** The pooled figure looks stronger, but it leans on Phase
  27's own data, which motivated this phase. It stays descriptive. (The margin does not enter this test; round 1
  reproduced these figures.)

### 8.4 The in-window guard (U1 52 + U3 62 prompts; pooled OR U3 alone)

**R's error rate w is measured in both strata:** on U1, Phase 27's C was wrong on 1 of 52 (1.9%); on U3, Phase
21's plain re-sends were wrong on 0 of 51 (Wilson 95% upper bound 7.0%). The rows below use those anchors, with U3
also at 2%, 5% and its Wilson upper bound, and a row with 5% in both. A harm h makes a share h of T2's otherwise
correct reports incorrect. The harm is either **spread evenly** over U1 and U3, or **confined to U3**: U1's T2
requests are Phase 27's T requests (correct 52 of 52), so the realistic place for an unseen harm is U3.

**Chance the guard FAILs, round-1 rule** (FAIL if the pooled test or the U3-alone test gives p < 0.05):

| w: U1 / U3 | false block (h = 0) | spread 2% | spread 5% | spread 10% | U3 only 3% | U3 only 5% | U3 only 10% | U3 only 15% | U3 only 20% |
|---|---|---|---|---|---|---|---|---|---|
| **1/52 / 0 (measured)** | **0.001** | 0.11 | 0.56 | 0.96 | 0.09 | **0.28** | **0.80** | 0.97 | 1.00 |
| 1/52 / 2% | 0.011 | 0.11 | 0.45 | 0.90 | 0.11 | 0.23 | 0.62 | 0.87 | 0.97 |
| 1/52 / 5% | 0.026 | 0.11 | 0.37 | 0.81 | 0.10 | 0.19 | 0.48 | 0.76 | 0.91 |
| 1/52 / 7% (U3's Wilson upper bound) | 0.031 | 0.10 | 0.33 | 0.76 | 0.10 | 0.17 | 0.43 | 0.69 | 0.87 |
| 5% / 5% | 0.033 | 0.11 | 0.34 | 0.76 | 0.11 | 0.20 | 0.49 | 0.76 | 0.91 |

**Round 0's rule (the pooled test alone) against a harm confined to U3, for comparison:**

| w: U1 / U3 | U3 only 5% | U3 only 10% | U3 only 15% | U3 only 20% |
|---|---|---|---|---|
| 1/52 / 0 (measured) | 0.19 | 0.60 | 0.87 | 0.97 |
| 1/52 / 2% | 0.17 | 0.49 | 0.78 | 0.93 |
| 1/52 / 7% | 0.13 | 0.35 | 0.61 | 0.81 |

- **Phase 27's G4 harm was about 50%** (23 of 45). A harm that size anywhere in the window is caught with
  certainty.
- **The U3-alone part is what catches a harm confined to U3.** At the measured rates a 10% U3 harm is caught 0.80
  of the time, against 0.60 under round 0's pooled test; a 5% one 0.28 against 0.19.
- **Said plainly: a harm of 10% confined to U3 is still missed 20–57% of the time** across these anchors, one of
  5% is missed 72–83% of the time, and smaller ones more often. A spread harm of 5% is caught 0.33–0.56. A recommendation does not
  rule out a small in-window harm (§13).
- **The price is small:** the union blocks a harmless field 0.1% of the time at the measured rates, and at most
  3.3% up to w = 5–7%.
- **Completeness:** the pooled part needs 109 of 114 prompts compared, the U3 part 59 of 62.

### 8.5 The joint chance of a recommendation

If T2 behaves like Phase 27's T on U2 and does no harm in the window: **0.97–1.00**, for the anchors above (0.999
at the measured rates, 0.969 with U3 at its Wilson upper bound), in every C model.

## 9. Spend cap, bounds, waits and stop rules

| | value |
|---|---|
| planned requests | **860** (860 distinct request bodies) |
| per-request bound | **$0.0209** (32,000 input tokens × $0.55/M + 2,000 output tokens × $1.65/M) |
| planned bound | **$17.974** |
| hard spend cap | **$20.00 for the whole phase** (the program's cap). It admits 956 attempts, leaving **96 attempts ($2.01)** for retries. Phase 27 used 0 retries in 1,064 requests |
| token-priced ceiling | at most about $6.43 (7,603 input and 2,000 output tokens on every request). Unmeasured; the ledger carries the bound |
| budget before this run | $652.90 charged, **$347.10 remaining** after Phase 27. Reconcile any Phase 28a and 28 charges first (Phase 29 is cancelled) |

**The spend guard** is Phase 21's code with this harness's own cap check (`SpendGuard`):
- it charges every attempt, retries included, at the bound, in whole micro-dollars;
- it refuses the attempt that would pass the cap;
- a plan that cannot fit is refused before any call.

**The cap is a phase cap.** A later run is allowed only after runs that delivered nothing, and it gets $20.00
minus their charged bounds.

**Retries, waits and stops** are Phase 21's and Phase 27's, unchanged:
- **retry:** one blind retry of a transport failure that delivered nothing (`CONNECTION_ERROR`,
  `REQUEST_TIMEOUT`), charged, after 10 s. A delivered generation is never re-rolled: `EMPTY_FINAL_RESPONSE` is
  received and never retried;
- **waits:** 30 s, 2 min, 5 min and 5 min after the first to fourth errored request in a row;
- **the run stops at the first of:**
  - all 860 done (`COMPLETED`);
  - another paid run seen after the claim (`STOPPED` / `other_paid_run`, 0 attempts);
  - the spend guard (`spend_guard`);
  - the 5th errored request in a row (`consecutive_errors`);
  - SIGINT or SIGTERM (`operator_stop`);
  - any other exception (`ABORTED`, with a scrubbed traceback);
  - a dead process closed at $0 by `--finalize-abandoned` (`ABORTED` / `abandoned`). This charges the recorded
    attempts plus up to two unrecorded in-flight ones. A cut-off last line of `responses.jsonl` counts as delivered
    (round 1): the loop counts a delivery before it saves the manifest, so a run killed while writing its first
    response could otherwise be closed as having delivered nothing and be followed by a second run.
- After any stop, the read-outs are computed on what arrived.

**No resume, and only one run may deliver anything.**
- The output directory must be new and exactly `artifacts/phase30-<date>/<name>`.
- It is created exclusively before an atomic claim `artifacts/phase30-live-claims/claim-NN.json` (a private file,
  then a hard link; never deleted; it records the pid).
- A later run is refused while any earlier Phase 30 run is not final, has delivered anything, or has a claim with
  no manifest.
- A second draw after a delivering run would be repeat-until-lucky, and it would need its own declared phase.

## 10. The live gate

The harness refuses to call the provider unless all of these hold. Everything except the credential-dependent
items is checked before the one credential read.

1. **Flags:** `--execute-live`, `--out`, `--confirm-entity`, `--expect-plan-hash`, `--expect-harness-sha256` and
   `--expect-protocol-sha256`, all present before any plan is built.
2. **Output:** a new directory, exactly `artifacts/phase30-<date>/<name>` (letters, digits, `.`, `_`, `-`); every
   earlier Phase 30 run final and undelivered.
3. **One paid run at a time.** This is checked four times: before the plan is built (run records and processes
   only, not the backend), then at the start of the live path, after the credential read, and after the claim
   (all three kinds each of those three times):
   - **run records:** no run manifest (a JSON object with `started_at`) without an end marker, and no unreadable
     `*manifest*.json`, under any directory of Phases 20, 21, 23, 25–29 or 31–39; and no launch claim of those
     phases whose run directory holds no finished run manifest. **This check never lists Phases 22 and 24 and
     opens none of their files.** (The pin check in item 4 hashes one Phase 22 file, the freeze record; §12.) A
     claim is followed only to a run directory of a listed phase. A crashed record can be named with
     `--ignore-manifest <exact path>`;
   - **the run-record check does not see Phase 28a** (round 3, fidelity F1). A listed directory's name must be
     `phase`, two digits and then `-` (`OTHER_RUN_DIR`, `OTHER_CLAIM_DIR`, `OTHER_CLAIMED_RUN`), so
     `artifacts/phase28a-<date>/` and `artifacts/phase28a-live-claims/` are never read. Measured at $0 through
     `other_run_files` on a temporary tree: a RUNNING Phase 28a run manifest and an open Phase 28a claim were both
     ignored, while a RUNNING `phase28-…` manifest beside them was found (`review-r3/fidelity_fix_checks_r3.out.json`).
     Phase 28a is the one paid run that the approved sequencing puts in Phase 30's window (`PHASE28_DESIGN.md` §9,
     §19). **Only the process check below covers it,** and only while a 28a process is alive. A crashed 28a run
     that was never finalized, or an open 28a claim, is caught only by §12 step 3's manual check. The harness is
     not changed for this: its pins would move and §12 step 1 would apply in full. If the harness changes for
     another reason, widen the three patterns to `phase(?:2[01356789]|3[1-9])[a-z]?-…`, with a test for a `phase28a`
     manifest and claim;
   - **processes (by tokens):** no other `python … experiments/<name>.py --execute-live` process, by Phase 26's
     reviewed rule, imported (`run_gap_probe.live_experiment_processes`). This process, its ancestors and its
     **descendants** are excluded, so its own `caffeinate -is` helper is never counted. A process list that cannot
     be read, or a Phase 26 runner that is not the pinned file, blocks. Processes are never set aside by
     `--ignore-manifest`;
   - **the backend** (not in the first check): a read-only `GET http://127.0.0.1:8000/api/config/status` shows
     `active_campaign_id: null`, or the connection is refused. Any other failure to read it blocks.
4. **The plan:** rebuilt from scratch at $0 (every pin in §3, every prompt re-verified, the §5.3 pre-check re-run).
5. **Pins:** the harness sha256 equals `--expect-harness-sha256`; this file exists and its sha256 equals
   `--expect-protocol-sha256`; the plan hash equals `--expect-plan-hash`; this file contains both strings.
6. **The review:**
   - this file's opening block (everything before the first `## ` heading) no longer contains the phrase "NOT yet
     reviewed", matched in any case;
   - a bare line reads exactly `Reviewed for launch: harness <sha256> plan <hash>` with the pins (no backticks, list
     marker or bold);
   - `artifacts/phase30-2026-09-25/review.json` names this file's sha256, the harness sha256 and the plan hash;
     `phase_cap` equal to $20.00; a non-empty `approved_by`; and `owner_answer` with non-empty `verbatim`,
     `given_by` and `date`, whose `verbatim` appears in this file word for word.
7. **Budget:** the run's cap is the smaller of `--spend-cap` and what the phase cap leaves; the plan fits under it.
8. **After the one credential read** (the runtime's own loader): the entity equals `--confirm-entity`; the project
   is `shreetbohara-quinstreet/Faultlab`; the configuration pins hold again; the Actor role resolves to
   `deepseek-ai/DeepSeek-V3.1`; the one-paid-run check (item 3) passes again.
9. **Launch:** SIGINT and SIGTERM handlers are installed first; the output directory is created exclusively; the
   claim is taken (refused if the earlier runs changed since the offline checks); the `STARTING` manifest is
   written (it carries the owner's answer), then `plan.json` and `prompts.jsonl`.
10. **The last check, after the claim:** item 3 runs once more, right before the first provider call. If anything
    is active, the run ends `STOPPED` / `other_paid_run` with 0 attempts, and a later launch is allowed.

**Tests** (`test_report_narrow_probe.py`: 67 test functions, 93 tests with their parameters, after round 1):
- every refusal above and every read-out rule has a test that fails when it is removed or weakened, **as far as the
  listed mutants reach**;
- the $0 mutation check (`review-prep/mutate.py`) applies one weakening per scratch copy of the harness and runs
  the test file against each:
  - **round 0:** 55 weakenings, all caught; the unmutated copy passed 82 of 82 (`review-prep/mutation-results.txt`,
    with the list kept in `review-prep/mutate-r0.py`). But round 1's run-safety review found 11 more weakenings
    (R01–R11) that all 82 tests let through: the process check's default source and its fail-closed branch, the
    cap a later run's guard enforces, the RUNNING save before the first call, and six fail-closed branches of
    the one-run guard (`review-r1/runsafety/mutation-runsafety.txt`). So round 0's "every refusal has a test" was
    not true;
  - **round 1:** 72 weakenings (round 0's 55, plus S14 and G01–G04 for round 1's read-out changes, and R01–R12),
    **all 72 caught; the unmutated copy passes 93 of 93** (`review-r1/mutation-results-r1.txt`);
  - **round 2:** the reviewer aimed 5 more weakenings at round 1's changes (`review-r2/reviewer/mutate_r2.py`,
    `mutation-r2-results.txt`; the unmutated copy passes 93 of 93). N01 (the U3 part's planned count taken from
    the pool), N02 (the U3 part using the pooled counts) and N07 (the upper bound at α 0.025) were caught. N08 (a
    cut-off line counted only when the manifest says RUNNING) survived, but it is equivalent: no response line can
    exist before the RUNNING save. **N06 survived:** a statement that quotes the pooled p for U3 passes all 93
    tests, because no test checks the U3 p in the statement. The harness is correct, and it was not changed for
    this (that would move both pins and need another fix check, pitfall 74). §7.2 fixes how the results quote the
    guard, and §12 step 7 checks the statement's figures against the read-out. If the harness changes for another
    reason, add a test for the U3 p in the statement;
  - a mutation list samples weakenings; it cannot prove the claim for every possible one;
- **known gap:** `build_requests`' own refusals (a control that is not the stored request, a T2 identical to the
  control) are reachable only through the pre-check, which checks the same things on the same turns first;
- **the dry run reads no `.env`** (`env_path=os.devnull`) and builds no provider client; a test checks both.

**At drafting time** (2026-09-25, $0, through the harness's own functions, in the drafter's scratch folder and not
saved as evidence): no other run record, no other experiment process, no Phase 30 claim or run, the backend up with
`active_campaign_id` null, and no `review.json`; the gate refused this file for its status phrase. §12 step 2,
applied to a scratch copy of this file with a scratch review record, passed `check_review`; the same copy was
refused without the bare line, and with the phrase put back in the status line. The machine was on battery power.

**At review round 1** (2026-09-25, $0, saved in `review-r1/`): the run-safety reviewer read the same guard state
(`runsafety/guard_reading.out.json`) and measured the process rule under a real `caffeinate -is` process tree
through this harness's own wrapper: its own helper and parent shell were excluded and a sibling was found
(`runsafety/caffeinate_wrapper.out.json`). The round-1 fix repeated the guard reading with the round-1 harness
(`guard_reading_r1.out.json`: no other run record or experiment process, no Phase 30 claim or run, the backend up
with `active_campaign_id` null, no `review.json`, and the gate refusing this file for its status phrase). It also
rehearsed §12 step 2 on a scratch copy with the round-1 pins (`closure_rehearsal_r1.out.json`): the closed copy
passed `check_review`, and was refused without the bare line and with the phrase back in the status line. The
machine was on battery power at every reading (`power_r1.out.txt`), so a launch must wait for mains power (§12
step 3). Repeat the rehearsal with the final pins if a later round changes them.

**At review round 2** (2026-09-25, $0, saved in `review-r2/`): the reviewer rehearsed the whole offline live gate
with the final pins. It called the harness's own `run_live` on the real plan with a scratch copy of this file,
closed as §12 step 2 says, and a scratch review record. The credential read, `take_claim` and the provider client
were replaced by sentinels, and the flag was never passed to `main`. Every offline gate passed up to the `.env`
read, and seven closure mistakes were each refused (`reviewer/launch_rehearsal_r2.out.json`); no live directory and
no claims directory were created. The reviewer also measured the runbook's process ids under `nohup caffeinate -i`,
with a stand-in Python script (`reviewer/sleeper.py`): `echo $!` prints the Python process, SIGTERM sent to it
reaches Python's handler, and after `kill -9` of Python the `caffeinate` helper exits
(`reviewer/caff_pid_probe.out.txt`, `reviewer/caff_kill9_probe.out.txt`). The guard
reading (`reviewer/guard_reading_r2.out.json`) found no other run record or experiment process, the backend up with
`active_campaign_id` null, no Phase 30 claim, run or `review.json`, and the gate refusing this file for its status
phrase. The machine was on battery power (71%, discharging), so §12 step 3's power check still fails. After round
2's edits to this file, the fix repeated the closure rehearsal on a scratch copy of the edited file
(`closure_rehearsal_r2.out.json`), the paid-run guard reading (`guard_reading_r2_fix.out.json`) and the power
reading (`power_r2.out.txt`).

**At review round 3** (2026-09-25, $0, saved in `review-r3/`): the fidelity reviewer re-ran the dry plan (plan
`05f26608…`, `"passed": true`) and the §12 step 3 tests (206 passed), and showed on a temporary tree, through
`other_run_files`, that the run-record check ignores Phase 28a's folders (finding F1; `reviewer/`). After round 3's
edits to this file, the fix rehearsed §12 step 3's new Phase 28a check, exactly as printed there, on nine
temporary trees and on the repository (`fidelity_fix_checks_r3.out.json`). It also repeated the closure rehearsal
with §12 step 2's new wording (`closure_rehearsal_r3.out.json`), the paid-run guard reading
(`guard_reading_r3.out.json`) and the power reading (`power_r3.out.txt`).

## 11. No tuning, no leakage, and what must not happen

- **Results stay under `artifacts/phase30-*`.** They never enter a study and are never shown to any model.
- **Only development prompts are replayed,** each exactly as the Actor already received it, plus T2 in its window.
- **heldout-2 is never read.** Phase 24's published summary motivated Phase 27, and Phase 27's results motivated
  this phase, so heldout-2 can never judge T2. Any later held-out check of an Actor carrying T2 needs a **new**
  partition.
- **T2's key, value and window are fixed now.** Another wording or window tried on these prompts would be a new,
  declared phase, reported beside this one.
- **Must not happen:**
  - a second draw after a run that delivered anything;
  - re-declaring a read-out after seeing data;
  - quoting the reduction, or the pooled figure, as the result;
  - quoting the structural guard as a measured pass. `PHASE30_RESULTS.md` writes it as "not applicable: T2 is
    byte-identical to the control there; nothing was sent";
  - quoting the in-window guard's top-level `complete` (or its top-level counts and p) as the whole guard's. They
    are the pooled part's; the U3 part is under `alone` (§7.2);
  - writing a recommendation as evidence of benefit (a field that does nothing is recommended 15–27% of the time,
    §8.2);
  - any edit under `backend/app`;
  - opening `checks.py`, `artifacts/heldout2/`, `audit/promotion.json` or any final-audit file;
  - reading `.env` outside the one credential read;
  - using any result to tune a Mechanic, Explorer or Actor input.

## 12. Runbook

This probe drives neither the lab backend nor the simulator. It calls W&B Inference directly, from one process,
with no Weave tracing. The program's runbook items apply as follows:

| runbook item | here |
|---|---|
| `check_ingestion_health.py` | not required: no Weave traces and no evidence verification. It is harmless to run |
| `start-simulator.sh`, dashboard closed, `loop_latency.py` (Phase 19) | not applicable: no worlds and no lab requests |
| `check_clock_drift.py` afterwards (Phase 19) | not applicable: no worlds |
| configuration hash `2cf63e93…` (Phase 22) | **enforced:** recomputed at the dry run, at launch and after the credential read. Any `backend/app` change breaks it |
| freeze `8994e962…` (Phase 22) | **enforced:** the record file's sha256. The freeze is never re-taken |
| heldout-2 never read (Phase 22) | **enforced** by the development-only selection and the cutoff. No heldout-2, audit or Phase 24 file is opened. Of Phase 22's files, only the freeze record `artifacts/phase22-2026-09-24/gate-freeze-after.json` is read, to hash it (§3); the other-run check opens none |
| one paid run at a time | **enforced** (§10 items 3, 8 and 10), **except for Phase 28a's run records and claims**, which this harness cannot see (§10 item 3; round 3, fidelity F1). Phase 29 is cancelled (`PHASE29_EXPERIMENT.md`, Cancellation), so the paid run that shares Phase 30's window is **Phase 28a** (`PHASE28_DESIGN.md` §9, §19). This harness sees a live 28a process (by tokens), but not a crashed or unfinalized 28a run or an open 28a claim, so §12 step 3 checks those by hand. **The 28a harness, when built, must watch `artifacts/phase30-*` and `artifacts/phase30-live-claims`.** Run Phase 28a and Phase 30 one after the other, never together |
| services on ports 8000, 8001 and 5173 | leave them as they are. Do not start, stop or restart anything for this probe |

**Steps.** Every command starts from the repository root, `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`,
unless it says otherwise.

0. **Now:** nothing is run and nothing is spent.
1. **Review** in rounds, with three lenses: statistics; build and live safety; fidelity to the program, Phase 27
   and the runtime. Then a focused check of any fix (pitfall 74).
   - Answer every question in §16 in writing.
   - Save the reviewers' $0 re-checks (the dry run, the paid-run guard reading, a closure rehearsal on a scratch
     copy of this file) under `artifacts/phase30-2026-09-25/review-r<N>/`.
   - **If a round changes the harness:** write a new dry plan to a new directory (for example `dry-plan-r1/`),
     update the pins in this file (the opening block, §3, the commands below), re-run the protocol numbers (round
     1: `protocol-numbers-r1/protocol_numbers_r1.py`), the tests and `review-prep/mutate.py`, and have the fix
     checked. Round 1 did all of this (Review log).
   - **If a round changes only this file** (rounds 2 and 3), no pin moves: re-run the tests and the dry run after
     the last edit, check that every pin in §3 still equals its file, and repeat the closure rehearsal on a scratch
     copy of the edited file.
   - **The review cannot close** until the fidelity lens has reported and its findings are applied. It reported in
     round 3, and its four findings are applied, all as edits to this file (Review log, round 3). A fix that changes
     the harness later brings back all of the first bullet.
2. **Close the review in writing,** in this order:
   - add a closing entry at the end of the Review log, headed `### Closure (<YYYY-MM-DD>)`. It names each round's
     reviewers and verdicts, gives the final answer to each §16 question in a table, repeats the owner's words
     "go ahead with whatever u recommend" with who gave them (Shree Bohara, project owner) and the date
     (2026-09-25), and names the approver;
   - **replace lines 3–13 of this file, and nothing else in the opening block** (round 3, fidelity F4): the status
     paragraph (from `**Status: declared before any paid call; NOT yet reviewed.**` to the first blank line), that
     blank line, and the pins paragraph (it begins `Pins of this draft,`). Put exactly the text below in their
     place, with its `<…>` placeholders filled (the rounds, the closing date twice, the approver and the final
     pins) and without this code block's fences. Round 2's instruction changed only line 3, which would have left
     the draft's round and pins wording beside a closed status:
     ```
     **Status: declared before any paid call; reviewed in rounds <…>; closed <YYYY-MM-DD>; approved by <approver>.**
     No paid, model or W&B call had been made for this phase when the review closed, and nothing under
     `backend/app` was edited. Every number below comes from a $0 dry run or a saved $0 computation. Review rounds
     1 (statistics; build and live safety), 2 (the check of round 1's fixes) and 3 (fidelity to the program, Phase
     27 and the runtime) ran on 2026-09-25, and every finding is applied (Review log). The review closed on
     <YYYY-MM-DD> (Review log, Closure). §10 lists everything the live gate checks.

     Pins at closure (the live gate requires both strings in this file): harness <sha256> plan <hash>
     ```
     If another round runs before closure, name it in both lists of rounds. The quotation of the old status
     sentence in this step may stay, because it is below the first heading;
   - check: `grep -n -i "not yet reviewed" docs/part2/PHASE30_EXPERIMENT.md` must print only lines below the first
     `## ` heading, and this must print nothing (no draft wording left in the opening block):
     `sed -n '1,/^## /p' docs/part2/PHASE30_EXPERIMENT.md | grep -n -i -e 'not yet' -e 'has not reported' -e 'not closed' -e 'of this draft'`;
   - end the closing entry with the bare line, with the final pins and no backticks, list marker, bold or table:
     `Reviewed for launch: harness <sha256> plan <hash>`;
   - record `shasum -a 256 docs/part2/PHASE30_EXPERIMENT.md`. **Do not edit this file afterwards;**
   - write `artifacts/phase30-2026-09-25/review.json`:
     ```
     {
       "protocol_sha256": "<the sha256 just recorded>",
       "harness_sha256": "ca3b8b9d0df0960b4fff4f6ae8369f5cc6677815e9ee94b73f9c40e106681317",
       "plan_hash": "05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34",
       "phase_cap": 20.0,
       "approved_by": "<who approved>",
       "owner_answer": {
         "verbatim": "go ahead with whatever u recommend",
         "given_by": "Shree Bohara, project owner",
         "date": "2026-09-25",
         "channel": "the owner's request that started the Phase 30 build, relayed verbatim by the workflow harness"
       },
       "reviewers": ["<round 1>", "<round 2>", "..."],
       "closed_at": "<YYYY-MM-DD>"
     }
     ```
     (with the final pins, if step 1 changed them);
   - rehearse the gate at $0 (it reads only this file and `review.json`, never `.env`):
     ```
     ./.venv/bin/python -B - <<'EOF'
     import importlib.util
     spec = importlib.util.spec_from_file_location('rnp', 'scripts/experiments/report_narrow_probe.py')
     m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
     print(m.check_review(m.PROTOCOL.read_text(), m.sha256_file(m.PROTOCOL), m.sha256_file(m.__file__),
                          '05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34'))
     EOF
     ```
     It must print the owner's answer, not `PlanningError`.
3. **Check before launch, at $0,** right before step 4:
   - **Power:** `pmset -g batt` must print `Now drawing from 'AC Power'`. Keep the lid open for the whole run. On
     battery, `caffeinate -s` does nothing, and a flat battery or a closed lid after the first generation ends the
     run for good: it could only be closed with `--finalize-abandoned`, and the probe could not be run again.
   - **Budget:** reconcile the ledger (`memory/context/runtime-and-evidence.md`) with any Phase 28a and 28 charges
     (Phase 29 is cancelled). Confirm the remaining budget covers the $20 cap.
   - **No other paid run:**
     - `curl -s http://127.0.0.1:8000/api/config/status` must show `"active_campaign_id":null`. If the request is
       refused, `lsof -nP -iTCP:8000 -sTCP:LISTEN` must show nothing listening;
     - `ps -ax -o pid,command | grep -- '--execute-live' | grep -v grep` must print nothing. The harness makes its
       own token-based check, which never counts its own `caffeinate` helper. This manual check can also match a
       shell that only mentions the flag; that is not a paid run, but wait until it has ended. It also covers a
       live Phase 28a process;
     - **Phase 28a's records** (round 3, fidelity F1; the harness never reads 28a's folders, §10 item 3). Every
       `*manifest*.json` under `artifacts/phase28a-*` must be final (an `ended_at`, and no status or stop reason
       saying RUNNING or STARTING), and every claim in `artifacts/phase28a-live-claims/` must name a run directory
       `artifacts/phase28a-<date>/<name>` that holds a final run manifest. Check both with this $0 command, which
       loads the harness, points its own run-record rule at Phase 28a's folders in memory (the file is not edited),
       and adds every non-final `*manifest*.json` there, with or without `started_at`:
       ```
       ./.venv/bin/python -B - <<'EOF'
       import importlib.util, json, re
       spec = importlib.util.spec_from_file_location('rnp', 'scripts/experiments/report_narrow_probe.py')
       m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
       m.OTHER_RUN_DIR = re.compile(r'phase28a-[A-Za-z0-9._-]+')
       m.OTHER_CLAIM_DIR = re.compile(r'phase28a-live-claims')
       m.OTHER_CLAIMED_RUN = re.compile(r'artifacts/phase28a-[A-Za-z0-9._-]+/[A-Za-z0-9._-]+')
       found = m.other_run_files()
       for path in sorted((m.ROOT / 'artifacts').glob('phase28a-*/**/*manifest*.json')):
           try:
               final = m._manifest_final_marker(json.loads(path.read_text()))
           except (OSError, ValueError):
               final = False
           name = str(path.relative_to(m.ROOT))
           if not final and name not in found:
               found.append(name)
       print(found or 'no open Phase 28a run record or claim')
       EOF
       ```
       It must print `no open Phase 28a run record or claim`. If it names anything, do not launch: wait until that
       28a run has ended or has been closed by 28a's own procedure. If a named file is not a run manifest at all,
       write down why before going on. Rehearsed at $0 on nine temporary trees and on the repository
       (`review-r3/fidelity_fix_checks_r3.out.json`);
   - **The dry plan:** `./.venv/bin/python -B scripts/experiments/report_narrow_probe.py` must print
     `"plan_hash": "05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34"` and `"passed": true`.
   - **The tests,** from `backend/`:
     `cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend && ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/experiments/test_report_narrow_probe.py tests/experiments/test_report_word_probe.py`.
     Everything must pass.
4. **Run once,** on mains power:
   ```
   cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
   nohup caffeinate -is ./.venv/bin/python scripts/experiments/report_narrow_probe.py --execute-live \
     --confirm-entity shreetbohara-quinstreet --out artifacts/phase30-2026-09-25/live \
     --expect-plan-hash 05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34 \
     --expect-harness-sha256 ca3b8b9d0df0960b4fff4f6ae8369f5cc6677815e9ee94b73f9c40e106681317 \
     --expect-protocol-sha256 <sha256 from step 2> \
     >> artifacts/phase30-2026-09-25/live-runner.log 2>&1 &
   echo $!
   ```
   - **The pins** in this command are round 1's, which rounds 2 and 3 left unchanged. Use the final pins if a later round
     changes them.
   - **The folder** is `artifacts/phase30-2026-09-25/` whatever day the run starts, so the review record, the log
     and the run's outputs sit together.
   - **The process id** is what `echo $!` prints (the Python process). The claim records it as well.
   - **The log** is appended to, and it sits outside the output directory, which must not exist beforehand.
   - **Timing:** Phase 27's 1,064 requests took 28 minutes (2026-09-25, 17:20–17:48 UTC). At that pace these 860
     take about 23 minutes. Each errored request adds its declared wait.
   - **If the gate names a crashed run record** of another phase: confirm that nothing is running before passing
     `--ignore-manifest <exact path>`.
5. **To stop:** use `kill -TERM <pid>`. Use `kill -9` only if the process has ignored SIGTERM for more than a
   minute. After a hard kill, close the claim with
   `./.venv/bin/python scripts/experiments/report_narrow_probe.py --finalize-abandoned artifacts/phase30-live-claims/claim-NN.json`
   before anything else.
6. **Outputs** in the output directory: `plan.json` and `prompts.jsonl`; `responses.jsonl`;
   `report-narrow-probe-manifest.json`; `readouts.json` (missing only after a hard kill).
7. **Afterwards:**
   - recompute the read-outs and compare their JSON content (not their text) with `readouts.json`. `--readouts`
     refuses unless the harness and the plan are the run's own and both imported harnesses are still the pinned
     files:
     ```
     ./.venv/bin/python -B scripts/experiments/report_narrow_probe.py --readouts artifacts/phase30-2026-09-25/live > artifacts/phase30-2026-09-25/readouts-recheck.json
     ./.venv/bin/python -c "import json; assert json.load(open('artifacts/phase30-2026-09-25/readouts-recheck.json')) == json.load(open('artifacts/phase30-2026-09-25/live/readouts.json')); print('equal')"
     ```
     It must print `equal`;
   - check the statement's in-window guard figures against the read-out's fields (round 2; no test checks the U3
     p in the statement, §10). It rebuilds that part of the statement from `status`, `pooled_status` with the
     top-level counts and p, and `alone`:
     ```
     ./.venv/bin/python -B - <<'EOF'
     import json
     r = json.load(open('artifacts/phase30-2026-09-25/live/readouts.json'))
     g = r['in_window_guard']; a = g['alone']
     quoted = (f"in-window guard {g['status']} (pooled U1 + U3 {g['pooled_status']}: T2-only not OK {g['t2_only_not_ok']}, "
               f"R-only not OK {g['r_only_not_ok']} of {g['compared']} compared, sign test p {g['sign_test_one_sided_p']:.4g}; "
               f"{a['stratum']} alone {a['status']}: T2-only not OK {a['t2_only_not_ok']}, R-only not OK {a['r_only_not_ok']} "
               f"of {a['compared']} compared, sign test p {a['sign_test_one_sided_p']:.4g})")
     assert quoted in r['statement'], 'the statement does not match the guard read-out'
     print('guard statement matches the read-out')
     EOF
     ```
     It must print `guard statement matches the read-out`. It was rehearsed at $0 on the real dry plan
     (`review-r2/statement_recheck_r2.out.json`): it passes on the harness's own read-outs, and it refuses a
     statement that quotes the pooled p for U3;
   - add the manifest's `charged_upper_bound` to the ledger;
   - write `PHASE30_RESULTS.md` against these read-outs only, quoting the worst-case figures first. Quote the
     in-window guard in §7.2's order: its `status`, then `pooled_status` with the top-level counts and p, then
     `alone.status`, `alone.complete`, `alone.compared`, `alone.t2_only_not_ok`, `alone.r_only_not_ok` and
     `alone.sign_test_one_sided_p`. Never quote the top-level `complete` as the guard's completeness;
   - **if the run delivered nothing** (for example `STOPPED` / `other_paid_run`), a new run is allowed in a new
     directory (for example `.../live-2`) under the rest of the phase cap. Record both runs.

## 13. What each result would mean — and would not

**`RECOMMENDED_FOR_A_LATER_LOOP`**
- **It would mean,** in development replays:
  - T2 left every context outside its window byte for byte unchanged;
  - where it was shown besides U2 (U1 + U3 pooled, and U3 alone), it did not make correct reports incorrect beyond
    a plain re-send's noise, at the sign tests' power;
  - on U2, the 97.6% upper bound on the rise in the worst-case bad rate is below 1.5 points.
- **It would not mean** any of these:
  - that T2 lowers the slip, or helps at all. That is not tested as a decision (§8.3), and a field that does
    nothing is recommended 15–27% of the time (§8.2). **A recommendation does not imply benefit;**
  - that T2 cannot nearly double the slip. The margin is absolute: a PASS rules out a rise of 1.5 points or more,
    not a smaller one, and against a re-send rate of about 1.8% a rise of just under 1.5 points is close to a
    doubling (against Phase 21's 3.9%, about 40% more). A field 1 point worse than C is recommended about 5% of the time (§8.2);
  - that T2 is safe on held-out cases, or on contexts that do not exist in development data (§14);
  - that a small in-window harm is ruled out (§8.4). **A harm of 10% confined to U3 is missed 20–57% of the time,
    and one of 5% 72–83% of the time;** a harm of 5% spread over U1 and U3 is missed 44–67% of the time;
  - that T2 fixes voluntary `UNKNOWN` reports (U4), which it never touches;
  - fewer C5/C6 failures in live episodes, or anything certified, accepted or held out.

**`NOT_RECOMMENDED`, non-inferiority FAIL:** a rise of 1.5 points or more is not ruled out. With a field that does
nothing, this happens 73–85% of the time (§8.2), and a field with a flat 1% bad rate, better than C, fails 5–47%
of the time. So a FAIL is not by itself evidence of harm. The counts and the upper bound say which it is.

**`NOT_RECOMMENDED`, in-window guard FAIL:** where it is shown (U1 + U3 pooled, or U3 alone), T2 made correct
reports incorrect more often than a plain re-send, at p < 0.05. That would be a real harm, and the transitions
show which words moved. A harmless field is blocked this way 0.1% of the time at the measured rates, and at most
3.3% at the rates checked (§8.4).

**`NOT_RECOMMENDED` with an INCOMPLETE read-out:** an arm, or one of the guard's two comparisons, received fewer
than 95% of its prompts. That is no evidence either way.

**The reduction, whatever it shows:** descriptive. A p < 0.05 there is quoted beside the decision, never as the
result. The pooled figure is quoted only with its label (§7.4).

## 14. Limits

- **Development only; a replay; one response deep.** Each prompt is a frozen v4 history. A live episode would
  diverge after it.
- **The structural guard is true by construction** (§5.3). It shows that T2 cannot reach any development turn
  outside its 781, not that it is safe on contexts development data lacks. Those include:
  - a report-required turn with the upgrade `PENDING` and the confirmation `UNKNOWN` (stratum `U_other`: none in
    development data);
  - a report-required turn after a blocked or invalid report, whose history would already carry T2. Development
    data has no in-window turn after another (§5.3), so the replay cannot see it;
  - a report-required turn where the runtime reads an operation as `UNKNOWN` but no observation shows it. The
    field's `UNKNOWN` matched the runtime's on all 809 report-required development turns. On voluntary turns they
    differ 797 times (`t2_window_survey.out.json`); that does not matter here, because voluntary turns are outside
    the window.
- **U4 is untouched.** 13 of the 38 historical `UNKNOWN`-context slips were voluntary reports, and T2 is never
  shown on those turns.
- **The margin is absolute** (1.5 points against a base measured between about 1.8% and 3.9%, §4), and the
  worst-case accounting is
  asymmetric: T2 is bad for any wrong or missing report, C only for an unsupported word. The asymmetry errs against
  T2.
- **The in-window guard is weak against small harms:** it misses most harms of 5% or less, and a 10% harm confined
  to U3 20–57% of the time (§8.4). Its reference rate w is measured, but on few prompts: 0 of 51 on U3 (Phase 21's
  plain re-sends; Wilson 95% upper bound 7.0%) and 1 of 52 on U1 (Phase 27's C).
- **U1 is not fresh.** It repeats Phase 27's U1 requests (§6), where C was correct on 51 of 52 and T on 52 of 52.
- **Provider nondeterminism.** Only 36% of repeat pairs were byte-identical in Phase 21. The arms of a prompt are
  sent back to back, but drift across the run is not controlled. The served model is recorded, not enforced.
- **Prompts are not fully independent.** They share cases and episode arms, but not episodes: each of the 430
  prompts comes from a different episode (`review-r1/plan_facts_r1.out.json`). The exact figures treat them as
  independent; clustering by case was not modelled.
- **The word rule is not C5.** `checks.py` is never opened. The allowed `UNKNOWN`/`NOT_STARTED` pair is Phase 27's.
- **The dollar figures are conservative bounds.** The token-priced cost is unmeasured.
- **The owner's-answer gate checks the record against this file, not against the owner.** Whether the owner said
  the words is the closure's to confirm.

## 15. What a later loop would need (described, not made)

Nothing under `backend/app` changes in this phase. If T2 is recommended, a later loop needs, as its own declared
and reviewed change:
- **a new Actor context protocol id** (for example `faultlab-actor-context/v6-narrow-status`) in
  `backend/app/agents/progress.py`, registered in `ACTOR_CONTEXT_PROTOCOLS` and in `INDEXED_EVIDENCE_PROTOCOLS`
  (so evidence keeps its `obs-k` labels);
- **`turn_message` for that protocol** adding `last_observed_status` only inside the window. The value is
  `report_word_probe.status_field`'s: computed from the journal's delivered observations with
  `_matching_operation_data`. The Actor already passes `journal=broker.journal` on every turn
  (`backend/app/agents/actor.py`), so the call site needs no new argument;
- **the window's `FAILED` check exactly as tested** (round 3, fidelity F3): this harness's
  `terminal_rejection(operation_facts(...))` for the upgrade. The turn is out of the window when the `PolicyState`
  status is `FAILED`, **or** a `FAILED` receipt exists, **or any** delivered observation of the upgrade operation has
  result status `FAILED`. `PolicyState` and the receipt alone are not enough: with no receipt,
  `PolicyState.status` returns the status of the latest delivered observation of the operation
  (`backend/app/lab/policy_state.py:21-29`), so a turn where the upgrade was shown `FAILED` without a receipt and
  then read `UNKNOWN` would get the field. That turn is outside the tested window. Built from real observation
  models at $0, it gives `PolicyState` status `UNKNOWN`, no receipt, `seen` `FAILED` and `UNKNOWN`: the declared
  window is closed and the PolicyState-or-receipt reading is open. No development turn has that shape: on all
  17,119 actor turns of the 3,204 development v4 episodes, the two readings agree, and all 325 terminal-rejection
  turns carry a `FAILED` receipt (`review-r3/fidelity_fix_checks_r3.out.json`);
- **the descriptor** (`actor_context_protocol`) gaining the new field and its window rule, so the new protocol's
  descriptor hash differs from v4's and v4's stays unchanged;
- **a runner that passes the new protocol explicitly** (pitfall 69: never through a default);
- **a new configuration hash and a new code freeze,** because `progress.py` changes. Every earlier pin (`2cf63e93…`,
  `8994e962…`) then refers to the old code;
- **tests** that the field appears only in the window, including the case of an upgrade shown `FAILED` and read
  `UNKNOWN` afterwards (no field; this harness's own test pins it, `test_report_narrow_probe.py:300-301`, "FAILED
  seen earlier"), and that v1–v4 messages and descriptor hashes are unchanged;
- **a concurrent control** (v4 against v6) measured end to end, including reports after a blocked or invalid first
  report, and **a new held-out partition** for any held-out check.

## 16. Questions for the review

1. **The structural guard (§2 item 1).** Is a $0 byte-identity check on all 2,070 Phase 27 guard prompts an
   acceptable replacement for re-sending C, R and T2 on Phase 27's 95? The alternative costs about $6 (285
   requests), would take U2 down to about 180 prompts under the $20 cap, and can only measure noise.
2. **The margin and α (§7.3, §8.2).** Round 0 declared 2 points at one-sided 0.025. **Round 1 changed it to 1.5
   points at 0.024** (review round 1, S2), on the statistics reviewer's recommendation, under the owner's
   delegation ("go ahead with whatever u recommend").
   - The trade (§8.2): the chance of PASS stays 1.00 for a field like T; a field 1 point worse than C is
     recommended about 5% of the time instead of 8–11%, and a field that does nothing 15–27% instead of 24–42%.
     The cost: a field better than C but not perfect passes less often (a flat 1% bad rate: 0.54–0.95 instead of
     0.71–0.98), and when C has at most one slip, one bad T2 response fails the test (§7.3).
   - At 1.5 points, α 0.025 has an exact size of 0.0256 at a C-only rate of 3%; α 0.024 keeps it at most 0.0243
     (§8.1).
   - Keep 1.5 points at 0.024, or return to 2 points at 0.025? Both rows are in §8.2.
   - **Returning to 2 points is a harness change, not a closure choice** (round 2): `NI_MARGIN` and `NI_ALPHA` are
     constants in the harness and are written into the plan's `thresholds`, so it would change the harness sha256
     and the plan hash and would need §12 step 1 in full and another review round. Round 2 recommends keeping 1.5
     points at 0.024; it re-derived every figure for it independently.
3. **Fresh U2 prompts (§2 item 7).** Excluding Phase 27's 225 U2 prompts keeps the result independent of the data
   that motivated T2. The cost is nothing at this size (442 remain). (Round 3: 20 of the 316 were re-sent 5 times
   each in Phase 21 under a plain control, never with the field; disclosed in §2 row 7 and §6.)
4. **U1 re-sent.** All 52 U1 prompts were sent in Phase 27 (T was correct on all 52). Round 1 kept them (U1 is the
   Phase 24 situation) and added the U3-alone test, so U1 cannot dilute a harm in U3, the only fresh in-window
   context (§7.2, §8.4). Is the union rule's cost acceptable: a harmless field blocked 0.1% of the time at the
   measured rates, at most 3.3% at the rates checked?
5. **The window's report-required rule (§2 item 2)** leaves voluntary `UNKNOWN` reports (U4) untouched. Is that the
   right trade for a window whose whole reach can be replayed exactly, and where the strict schema rules out
   Phase 27's kind of harm?
6. **"At or near 0" (§2 item 6).** The program asked whether the field keeps the slip at or near 0. This protocol
   answers that descriptively (T2's count and Wilson interval) and decides on non-inferiority. Is that the right
   reading of the program? (Round 1: yes. An exact Clopper–Pearson upper bound may be quoted beside the Wilson
   interval in the results, labelled descriptive; the harness does not compute it.)

## 17. Evidence files (all $0)

In `artifacts/phase30-2026-09-25/`:
- **Round 0** (written by the builder on 2026-09-25; superseded by round 1 where noted, and kept):
  - **`dry-plan/`:** `plan.json` (sha256 `ba56660c…`, plan `575df1dc…`, harness `cbc57db1…`) and
    `dry-summary.json`; the run's output is `dry-plan-stdout.txt`. Superseded by `dry-plan-r1/`;
  - **`protocol-numbers/`:** `protocol_numbers.py` and `protocol_numbers.out.json`: the round-0 design's U2 cell
    rates, non-inferiority size, power and boundaries at 2 points, the reduction's power, the pooled guard's
    boundaries and power, and the joint chance of a recommendation. Superseded by `protocol-numbers-r1/`, which
    imports its helpers;
  - **`protocol-facts/`:** `t2_window_survey.py` and `.out.json` (the window rule re-applied by separate code over
    every verified turn, §5.3); `stated_by_stratum.py` and `.out.json` (what T2 states, the reference words, the
    historical words and the cases, per in-window stratum, §4, §5.2). Round 1 did not change the survey, so these
    stand (their outputs record the round-0 harness sha256);
  - **`review-prep/`:** `mutate.py` (extended in round 1), `mutate-r0.py` (the round-0 list, unchanged), and
    `mutation-results.txt` and `.json` (round 0's 55 mutants).
- **Round 1** (2026-09-25):
  - **`dry-plan-r1/`:** `plan.json` (sha256 `3931f0c6…`, plan `05f26608…`, harness `ca3b8b9d…`) and
    `dry-summary.json`; the run's output is `dry-plan-r1-stdout.txt`;
  - **`protocol-numbers-r1/`:** `protocol_numbers_r1.py` and `.out.json`: size on a fine grid, power and
    boundaries at both margins, and the in-window guard under the union rule with the harm spread or confined to
    U3 (§8);
  - **`review-r1/`:** the two reviewers' saved re-checks (`stats/`, `runsafety/`), `plan_facts_r1.py` and `.out.json`,
    `mutation-results-r1.txt` and `.json`, and the checks after the round-1 fix's last edit (`tests-r1.txt`,
    `dry-rerun-r1.out.txt`, `guard_reading_r1.out.json`). `review-r1/README.md` lists them.
- **Round 2** (2026-09-25; round 2 wrote no new dry plan or protocol numbers, because no pin moved):
  - **`review-r2/reviewer/`:** the round-2 reviewer's re-checks, copied unchanged from the session scratchpad:
    independent statistics (`indep_stats_r2.*`, `indep_power_exact_rates.*`), the round-0-to-round-1 harness diff
    (`r0_to_r1.diff`), the extra mutants (`mutate_r2.py`, `mutation-r2-results.txt` and `.json`), the guard's
    `complete` field case (`guard_complete_field.out.txt`), the launch rehearsal (`launch_rehearsal_r2.*`), the
    caffeinate probes, the guard reading and the reviewer's test run and dry re-run;
  - **the checks after the round-2 fix's last edit:** `statement_recheck_r2.py` and `.out.json` (§12 step 7's new
    recheck, rehearsed), `closure_rehearsal_r2.py` and `.out.json`, `guard_reading_r2_fix.py` and `.out.json`,
    `power_r2.out.txt`, `tests-r2.txt`, `dry-rerun-r2.out.txt` and `pins-r2.out.json` (every pin in §3 against its
    file). `review-r2/README.md` lists them.
- **Round 3** (2026-09-25; the fidelity lens; no new dry plan or protocol numbers, because no pin moved):
  - **`review-r3/reviewer/`:** the fidelity reviewer's re-checks, copied unchanged from the session scratchpad:
    `fidelity_checks.py`, `.out.json` and `.err.txt`, its dry re-run and its two test runs. Its temporary tree of
    fake Phase 28 and 28a run manifests was **not** copied, so that no paid-run guard watching `phase30-*` folders
    can ever read it as an open run;
  - **the checks after the round-3 fix's last edit:** `fidelity_fix_checks_r3.py` and `.out.json` (every figure
    the four fixes rest on, re-derived by separate code, and §12 step 3's Phase 28a check rehearsed);
    `phase21_rate_numbers_r3.py` and `.out.json` (§8's figures at Phase 21's 3.9%, model D);
    `closure_rehearsal_r3.py` and `.out.json` (§12 step 2's new wording on a scratch copy);
    `guard_reading_r3.py` and `.out.json`, `power_r3.out.txt`, `tests-r3.txt`, `dry-rerun-r3.out.txt`, and
    `pins_r3.py` with `pins-r3.out.json`. `review-r3/README.md` lists them.

The checks made while drafting round 0 (the dry run reproduced plan `575df1dc…` with `"passed": true`; the
paid-run guard reading; the gate refusing this file; the closure rehearsal of §12 step 2) were run in the
drafter's scratch folder and are not saved here. Round 1's are saved in `review-r1/`, round 2's in `review-r2/`, and
round 3's in `review-r3/`.

## Review log

### Review log — round 1 (2026-09-25): two lenses, both "run with changes"

**Reviewers:** statistics; build and live safety. They reviewed harness `cbc57db1…`, plan `575df1dc…`, tests
`7b199f3a…` and this file at `3988ff67…`, all at $0, with no repository edit, no paid, model or W&B call, no
`.env` read and no `--execute-live`. Both returned **RUN_WITH_CHANGES**. Their evidence is copied unchanged into
`review-r1/stats/` and `review-r1/runsafety/`.
- **Every finding was applied; none was declined.** Where a finding offered two fixes, the table names the one
  taken.
- **The fixes changed the harness** (the in-window guard, the margin and α, the statement, and
  `finalize_abandoned`), so a round-2 check of the fixes is required before the review can close (pitfall 74).
- **The third lens named in §12 step 1** (fidelity to the program, Phase 27 and the runtime) is not among round 1's
  reports. Round 2 should cover it.
- Every reviewer figure was re-derived by the fix before it was used here: the union guard, the 1.5-point margin
  and the fine size grid by `protocol-numbers-r1/`; the U3 re-sends, the one-prompt-per-episode fact and U1's
  identity with Phase 27 by `review-r1/plan_facts_r1.py`; the surviving mutants by `review-r1/mutation-results-r1.txt`
  (all now caught). All of them held.

**Statistics lens**

| # | severity | finding | disposition |
|---|---|---|---|
| S1 | major | The in-window guard pooled U1 and U3 into one sign test, and §8.4 stated its power only for a harm spread over all 114 prompts. U1's R and T2 requests are Phase 27's C and T requests, where T was already correct 52 of 52, so U3 (62 prompts) is the only context besides U2 where T2 is shown and untested. A harm confined to U3 is diluted by U1: at R error 2% on U1 and 0 on U3, a 10% U3 harm was caught 0.59 by the pooled test, 0.76 by U3 alone | **Fixed in the harness, as proposed.** A U3-alone exact one-sided sign test is a second failing part with its own 95% completeness (59 of 62). The guard is FAIL if either part fails while its completeness holds, else INCOMPLETE if either is incomplete, else PASS (`GUARD_ALONE_STRATUM`, `combined_guard_status`, `guard_readout`). §2 row 4, §7.2, §8.4, §8.5, §13 and §16 Q4 restated; §8.4 now has rows for a harm confined to U3 and says plainly that a 10% U3 harm is missed 20–57% of the time. At the measured rates the union catches a 10% U3 harm 0.80 (pooled alone 0.60) and blocks a harmless field 0.1%; at most 3.3% at the rates checked. Tests: `test_the_in_window_guard_also_tests_u3_alone_so_a_u3_harm_is_not_diluted_by_u1`, `test_each_guard_part_needs_its_own_completeness_and_a_failure_is_reported_first`; mutants G01–G04 caught |
| S2 | minor | §8.2 had no row for a harm below the margin; "a useless field is not recommended" was wrong (a no-effect field passes 24–42%); the 1.5-point option was dismissed on its size at α 0.025, which a slightly lower α fixes. Recommendation: 1.5 points at α 0.024 | **Fixed, and the recommendation adopted** under the owner's delegation ("go ahead with whatever u recommend"): `NI_MARGIN = 3/200`, `NI_ALPHA = 0.024`. §8.2 now shows both margins with rows for C + 0.5, + 1, + 1.5, + 2 and + 4 points; the sentence is replaced by "a field that does nothing is recommended 15–27% of the time; a recommendation does not imply benefit" (§8.2, §11, §13), and the harness's PASS statement says "this does not show a benefit". Exact size at the margin at most 0.0243 on a 0.1-point grid from 0 to 12% (§8.1). The cost is stated (§7.3, §8.2): imperfect but beneficial fields pass less often, and with c ≤ 1 one bad T2 response fails. §16 Q2 puts the choice to the closure. Test: `test_non_inferiority_boundaries_at_the_declared_size` (new boundaries 0, 0, 1, 2, 2, 3, 3) |
| S3 | minor | U3 was called "never sent before" and R's error rate on U3 "unmeasured", but Phase 21 re-sent 51 of the 62 U3 prompts under a plain control, all correct; §4 already cited "0 of 51" | **Fixed.** Re-derived (`review-r1/plan_facts_r1.out.json`: 51 of 62 re-sent once each, 51 of 51 `SUCCEEDED / UNKNOWN`, correct). §4, §6 (table and bullet), §8.4 and §14 now say "never sent with the field; 51 re-sent under C in Phase 21, all correct", and §8.4 anchors w at 0 of 51 for U3 (Wilson upper 7.0%, also a row) and 1 of 52 for U1. The harness docstring and `STRATUM_RULES` say the same |
| S4 | minor | Five statements did not match the code or the evidence: (a) prompts "share … episodes"; (b) "all three kinds each time"; (c) "no Phase 22 file is opened"; (d) the guard called "Phase 27's terminal-rejection word test"; (e) `t2_window_survey.py` presented as separate code for the whole window | **Fixed.** (a) §14: prompts share cases and episode arms, not episodes; each of the 430 comes from a different episode, and no fresh U2 episode is shared with Phase 27 (re-derived, `plan_facts_r1.out.json`; §6 bullet added). (b) §10 item 3: the first check covers run records and processes only; the other three cover all three kinds. (c) §12 table and §10 item 3: the other-run check opens no Phase 22 or 24 file; the pin check hashes one Phase 22 file, the freeze record. (d) §2 row 4 and §7.2: a variant of Phase 27's word test that counts a received non-report as not OK (Phase 27 counted only prompts both reported, floor 20). (e) §5.3: `t2_window_survey.py` checks the window rule only (it reuses `context['stated']`); the raw-observation check is the harness's `independent_t2_window` |
| S5 | minor | The statement printed "structural guard PASS (0 of 2070 …)" beside the measured gates, although that PASS is true by construction (pitfall 72) | **Fixed in the harness and the protocol.** The statement now reads "structural guard PASS by construction, not a measurement (0 of 2070 Phase 27 guard prompts in the window: T2 is byte-identical to the control there, and nothing was sent)"; the read-out carries `by_construction: true` and the rule text says never to quote it as measured. §11 adds "quoting the structural guard as a measured pass" to what must not happen and requires the results to write "not applicable: T2 is byte-identical to the control there; nothing was sent" (§7.1 too). Test: `test_a_clean_narrow_field_is_recommended`; mutant S14 caught |

**Build and live-safety lens**

| # | severity | finding | disposition |
|---|---|---|---|
| B1 | major | No test checked how the harness's own process check is wired to the real process table, or its fail-closed branch: `experiment_processes` returning `[]` (R08) or swallowing a runner error (R07) passed 82 of 82. The code itself was correct (measured under a real `caffeinate -is` tree) | **Fixed as proposed.** The reviewer's two tests added: `test_r1_default_process_source_is_the_real_table_minus_own_tree` (no `processes=` injection; own caffeinate child skipped, sibling found, through `experiment_processes`, `other_paid_runs` and `check_other_runs`) and `test_r1_process_check_fails_closed_when_the_runner_breaks` (also through `check_other_runs`). R07 and R08 added to `review-prep/mutate.py`; both caught |
| B2 | minor | Two spend-accounting rules were untested: the cap a later run's `SpendGuard` enforces (R01, R02 survived; the phase could have spent $20 plus an earlier run's charge), and RUNNING saved before the first provider call (R06; a hard kill would then charge no in-flight attempts) | **Fixed as proposed.** `test_r1_a_later_runs_guard_gets_only_what_the_phase_cap_leaves` ($3 earlier → the guard gets $17) and `test_r1_the_manifest_says_running_before_the_first_provider_call`. R01, R02 and R06 caught |
| B3 | minor | A hard kill while the first delivered response was being written left a cut-off line and a manifest saying 0 delivered; `finalize_abandoned` skipped the line, recorded 0 delivered, and a second full run was allowed (reproduced at $0, `runsafety/partial_line_sim.out.json`) | **Fixed as proposed (fail closed).** `finalize_abandoned` now counts every cut-off line as delivered (`delivered = … + partial`), and its rule text says so; §9 states it. The same logic in Phases 21 and 27's harnesses is not edited (they are pinned and closed). Tests: `test_r1_a_cut_off_first_response_line_counts_as_delivered` (the simulation, through `main`: `a_new_run_is_allowed` is false) and the existing finalize test, whose count rises from 2 to 3. Mutant R12 caught |
| B4 | minor | Six fail-closed branches of the one-run and no-resume guard could be weakened with no failing test: R03 (unknown delivery count), R04 (missing charge counted as $0), R05 (final without `ended_at`), R09 (claim not exclusive), R10 (another phase's manifest with `ended_at` but status RUNNING), R11 (`..` in a claim's path) | **Fixed: one tmp-tree test per branch, none left as a known gap.** `test_r1_an_unknown_delivery_count_a_missing_charge_or_no_end_time_refuses_a_new_run` (R03–R05), `test_r1_a_claim_is_exclusive_and_never_overwrites_another` (R09: a raced claim-01 is refused and left unchanged), `test_r1_another_phases_manifest_that_says_running_is_open_even_with_an_end_time` (R10), `test_r1_a_claim_that_names_a_dot_dot_path_is_refused` (R11). All six added to `review-prep/mutate.py`; all caught |

**Round 1's answers to §16** (the closure gives the final answers):

| question | round 1 |
|---|---|
| 1. structural guard for $0 | agreed: on G1–G5 T2's request is the control's, so re-sending measures only noise and adds false-block risk |
| 2. margin and α | 1.5 points at α 0.024 recommended and adopted in round 1 (S2); 2 points "defensible if the rows are shown". Both rows are in §8.2 |
| 3. fresh U2 prompts | agreed |
| 4. U1 re-sent | keep U1 (the Phase 24 situation), but do not let it dilute U3: done (S1) |
| 5. the report-required window | the trade is sound and disclosed |
| 6. "at or near 0" | descriptive is fine; an exact Clopper–Pearson upper bound could be quoted beside the Wilson interval (noted in §16 Q6; not computed by the harness) |

**Also checked sound by round 1** (not findings): every pin and the reuse of Phase 27's verified rebuild; the dry
re-run reproduced plan `575df1dc…`; the Tango restricted MLE, its variance, the boundary table and the size curve,
by independent code; every §8 figure against `protocol_numbers.out.json`; the populations (316 fresh U2 prompts
disjoint from Phase 27's at prompt and episode level; 860 report-required requests, all with the strict schema);
the spend cap, the per-attempt bound and `max_retries=0`; the live-gate order; the four one-paid-run checks; the
claim and signal order; the Phase 22/24 exclusion; the Phase 29 cross-watch; the review record's fields.

**Operational:** the machine was on battery power at every round-1 reading (95%, 83% and 78%, discharging), so
§12 step 3's AC-power check fails today. A launch must wait for mains power.

**Round 1 fix pins:** harness `ca3b8b9d0df0960b4fff4f6ae8369f5cc6677815e9ee94b73f9c40e106681317`, plan
`05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34`, dry plan file
`3931f0c6d2d38ec1649cf48cb62e97098d948d751d86c563dfeb572e21cb472b`, tests
`edf5c0867873f5e155ad2ab5d8bd6a49ef2875cb06de9542ad5dbcec9118d936`. The round-1 plan sends exactly round 0's 860
requests. After the fix's last edit: `test_report_narrow_probe.py` 93 passed; the §12 step 3 command
(`test_report_narrow_probe.py` with `test_report_word_probe.py`) 206 passed (`review-r1/tests-r1.txt`); the dry
run reproduced plan `05f26608…` with `"passed": true` (`review-r1/dry-rerun-r1.out.txt`); the mutation check caught
72 of 72 with the unmutated copy at 93 of 93 (`review-r1/mutation-results-r1.txt`); the paid-run guard reading and
the closure rehearsal are `review-r1/guard_reading_r1.out.json` and `closure_rehearsal_r1.out.json`. An interim
round-1 harness (`268e93fb…`) differed from the final one only in one docstring sentence (the no-effect pass
rate, made exact); every round-1 output (dry plan, protocol numbers, plan facts, mutation check) was regenerated
with the final harness, and the protocol numbers were identical.

### Review log — round 2 (2026-09-25): the check of round 1's fixes, "run with changes"

**Reviewer:** one combined report on statistics and on build and live safety. It is the focused check of round
1's fixes that pitfall 74 requires. It reviewed harness `ca3b8b9d…`, plan `05f26608…`, tests `edf5c086…` and this
file at `015a3149…`, all at $0, with no repository edit, no paid, model or W&B call, no `.env` read and no
`--execute-live`. It returned **RUN_WITH_CHANGES** with three minor findings. Its evidence is copied unchanged
into `review-r2/reviewer/` (scratch mutant copies were not kept).
- **Every finding was applied; none was declined.** Each fix is an edit to this file only, as each finding asked.
  The harness, the plan, the dry plan file and the tests keep round 1's hashes, so no pin moved and no code fix
  needs another check.
- **The fidelity lens** (fidelity to the program, Phase 27 and the runtime; §12 step 1) has still not reported.
  The review cannot close until it has.
- Every figure the fixes rely on was re-read from saved files: 0.91479 from `protocol_numbers_r1.out.json`, the
  harness constants and the plan's `thresholds`, and the guard's field layout from `guard_readout`.

| # | severity | finding | disposition |
|---|---|---|---|
| R2-1 | minor | §8.4, first table, row "5% / 5%", column "U3 only 20%": 0.92 was copied wrong. The saved computation gives 0.915 (`protocol_numbers_r1.out.json`, `in_window_guard.p_fail['w 0.05 on both']['harm confined to U3']['h 0.2'].union_round1` = 0.91479), and the reviewer's independent code gives 0.913. Every other §7 and §8 figure matched its independent re-derivation | **Fixed as proposed:** 0.92 became 0.91. The fix re-read 0.91479 from the saved file. Only this file changed |
| R2-2 | minor | The U3-alone part can be misreported, although the code is correct. The guard's top-level `complete`, `compared` and `sign_test_one_sided_p` belong to the pooled part, while the top-level `status` combines both parts, so `complete: true` can stand beside `status: INCOMPLETE`. With 4 U3 R responses missing: pooled 110 compared, PASS; U3 58 of 62, INCOMPLETE. Mutant N06 (the statement quoting the pooled p for U3) passed all 93 tests | **Fixed in this file, as proposed. The harness and the tests were not edited,** because that would move the pins and need another fix check (pitfall 74). The changes: §7.2 says which fields belong to which part and fixes the order in which `PHASE30_RESULTS.md` quotes them; §11 adds quoting the top-level `complete` as the guard's to what must not happen; §12 step 7 adds a recheck that rebuilds the statement's guard figures from `status`, `pooled_status` with the top-level counts and p, and `alone`, and requires the statement to contain them; §10 records N06 and the other round-2 mutants. The recheck was rehearsed at $0 on the real dry plan through the harness's own `compute_readouts` (`review-r2/statement_recheck_r2.out.json`). It passes on four sets of read-outs: nothing received; everything correct; the reviewer's case of 4 U3 R responses missing (reproduced: top-level `complete` true, guard INCOMPLETE, U3 58 of 62); and a U3-only harm beside U1 R-only noise (pooled p 0.2266, U3 p 0.03125). It refuses the last statement with the pooled p put in for U3. No test for the U3 p was added: the finding asks for one only if the harness changes for another reason |
| R2-3 | minor | §16 question 2, and §8.2's pointer to it, presented going back to 2 points at α 0.025 as a choice made at closure. It is a harness change: `NI_MARGIN` and `NI_ALPHA` are harness constants (lines 223 and 227) written into the plan's `thresholds`. Round 0's and round 1's plans have all 860 request dicts equal and differ only in `harness_sha256`, `readout_rules`, the `STRATUM_RULES` text in `sampling`, and `thresholds` (`ni_margin` 1/50 → 3/200, `ni_alpha` 0.025 → 0.024, `guard_alone_stratum` added); the plan hash moved from `575df1dc…` to `05f26608…`. A closer who changed them during closure would skip the fix check | **Fixed as proposed:** 1.5 points at α 0.024 is kept. §16 question 2 now says that the 2-point option would change the harness and the plan hash and would need §12 step 1 in full and another review round. §8.2's last bullet, which the finding calls "§8.6's pointer", says the same instead of "§16 question 2 puts the choice to the review's closure". §12 step 1 adds what a round that changes only this file must re-run, and that the review cannot close before the fidelity lens |

**Round 2's answers to §16** (the closure gives the final answers):

| question | round 2 |
|---|---|
| 1. structural guard for $0 | no new answer (round 1 agreed) |
| 2. margin and α | keep 1.5 points at α 0.024; every figure for it re-derived independently. Going back to 2 points is a harness change (R2-3) |
| 3. fresh U2 prompts | no new answer (round 1 agreed) |
| 4. U1 re-sent, and the union rule's cost | the cost is acceptable: the union blocks a harmless field 0.12% of the time at the measured rates, and at most 3.35% at the rates checked |
| 5. the report-required window | no new answer (round 1: sound and disclosed). The reviewer's premise check supports §1: in Phase 27, 838 of 838 report-required responses under the strict schema were reports |
| 6. "at or near 0" | no new answer (round 1: descriptive is fine) |

**Also checked sound by round 2** (not findings):
- **Pins:** harness `ca3b8b9d…`, tests `edf5c086…`, this file `015a3149…` (before round 2's edits), the dry plan file
  `3931f0c6…`, Phase 27 `f057ef2a…`, Phase 21 `f701ba14…`, Phase 26 `5d8e1690…`, the freeze record `8994e962…`,
  the settings `1e2002d3…`, and Phase 27's plan and read-outs all match. `slot2_probe.py` is `28b998ac…`, as
  Phase 26's code records.
- **What round 1 changed:** the reviewer rebuilt the round-0 harness exactly (`cbc57db1…`) and diffed it against
  round 1 (`reviewer/r0_to_r1.diff`). The changes touch only the docstring and `STRATUM_RULES`; `NI_MARGIN`,
  `NI_ALPHA` and `GUARD_ALONE_STRATUM`; `readout_rules` and `thresholds`; `finalize_abandoned` (the partial line);
  `combined_guard_status` and `guard_readout`; the structural `by_construction`; and the statement strings.
  Nothing changed in the spend guard, the caps, the claim, the other-run checks, the live gate, the survey, the
  sampling or the request building.
- **The five risks:** no new way to overspend ($17.974 planned; the cap admits 956 attempts, 96 spare for
  retries), to leak or to lose data. Every read-out change is stricter (a tighter margin, a lower α, one more part
  that can fail), and none makes a recommendation easier. All 860 request dicts equal round 0's.
- **B3's fix** is correct and fits Phase 21's loop order: a delivery is counted, then its line is written with
  fsync, then the manifest is saved. One window is left: a SIGKILL after a response arrives but before its line is
  written leaves no line. Nothing was recorded, so nothing can be selected on, and the two in-flight attempts are
  still charged. Mutant N08 survived, but it is equivalent.
- **Tests and dry run:** the §12 step 3 test command passed 206 of 206; the dry run gave plan `05f26608…` with
  `"passed": true`, identical to round 1's re-run. The pre-check lines are all zero: 17,119 of 17,119 turns
  verified, 781 in the window, 0 of 2,070 guard prompts in the window.
- **The read-outs on the real plan:** no results give INCOMPLETE and NOT_RECOMMENDED, without a crash; correct
  words everywhere give RECOMMENDED (b = c = 0, p 0.0141); 5 T2-only errors in U3 give FAIL, pooled and alone (p
  0.0312 each). One prompt per episode (430 of 430), no fresh U2 episode shared with Phase 27, and U1's R and T2
  equal to Phase 27's C and T (104 of 104) were re-derived. No Tango p is within 10⁻⁶ of 0.024 for any b and c
  below 80.
- **The launch rehearsal, the caffeinate process ids and the guard reading** are described in §10 ("At review
  round 2").

**Operational:**
- At 12:54 PDT the laptop was on battery (71%, discharging). The launch must wait for mains power (§12 step 3).
- The reviewer saw a client polling the lab backend at about 20 requests a second (`backend.log` grew by 99 lines
  in 5 s). The status GET still returned in about 2 ms, so Phase 30, which never drives the lab, is unaffected.
  Close that client before any phase that drives the lab (Phase 19's runbook). This fix did not re-measure it and
  touched no service.

**Round 2 fix pins** (all round 1's, unchanged): harness
`ca3b8b9d0df0960b4fff4f6ae8369f5cc6677815e9ee94b73f9c40e106681317`, plan
`05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34`, dry plan file
`3931f0c6d2d38ec1649cf48cb62e97098d948d751d86c563dfeb572e21cb472b`, tests
`edf5c0867873f5e155ad2ab5d8bd6a49ef2875cb06de9542ad5dbcec9118d936`. Round 2 edited only this file, whose sha256
is recorded at closure (§12 step 2). After the fix's last edit to this file: the §12 step 3 test command passed
206 of 206 (`review-r2/tests-r2.txt`); the dry run reproduced plan `05f26608…` with `"passed": true`
(`review-r2/dry-rerun-r2.out.txt`); every pin in §3 equals its file (`review-r2/pins-r2.out.json`); the closure
rehearsal on a scratch copy of the edited file passed `check_review` and was refused without the bare line and
with the phrase back in the status line (`review-r2/closure_rehearsal_r2.out.json`); and the paid-run guard
reading and the power reading are `review-r2/guard_reading_r2_fix.out.json` and `power_r2.out.txt`.

### Review log — round 3 (2026-09-25): the fidelity lens, "run with changes"

**Reviewer:** fidelity to the program, Phase 27 and the runtime: the third lens named in §12 step 1, which rounds 1
and 2 did not cover. It reviewed harness `ca3b8b9d…`, plan `05f26608…`, tests `edf5c086…` and this file at
`3d0c3c78…` (after round 2's fixes), all at $0, with no repository edit, no paid, model or W&B call, no `.env`
read, no `--execute-live` and no forbidden file opened. It returned **RUN_WITH_CHANGES** with four minor findings.
Its evidence is copied unchanged into `review-r3/reviewer/`, except its temporary tree of fake Phase 28 and 28a run
manifests (§17).
- **Every finding was applied; none was declined.** Each finding asked for a fix to this file only, and each fix is
  an edit to this file only. The harness, the plan, the dry plan file and the tests keep round 1's hashes, so no pin
  moved.
- **Every figure the fixes rely on was re-derived by code separate from the reviewer's** (`review-r3/`): Phase 21's
  re-sends were matched to this plan by request hash rather than by prompt id, and their words were judged against
  facts recomputed from the store rather than taken from the plan; §15's claim was checked on every development
  actor turn rather than on observation shapes; the model-D figures were computed exactly. All of the reviewer's
  figures held.
- **The fixes change no code, but they change two procedures:** the closure edit (§12 step 2) and a new manual
  check with a $0 command (§12 step 3). Both were rehearsed at $0 on the edited file. Whether they need a focused
  check before closure (pitfall 74) is the closer's decision.
- **Beyond the places each finding named**, the same fixes were carried to sentences that repeated the same
  statement: §2 rows 5 and 6, §7.3, §8.2, §13 and §14 now name Phase 21's 3.9% beside Phase 27's 1.8%; §5.1's
  condition 3 says an earlier `FAILED` counts; §9 and §12 step 3's budget lines say Phase 29 is cancelled; §16
  question 3 notes the 20 prompts.

| # | severity | finding | disposition |
|---|---|---|---|
| F1 | minor | The run-record layer of the one-paid-run guard cannot see Phase 28a, the one paid run that the approved sequencing puts in Phase 30's window (`PHASE28_DESIGN.md` §9, §17 A4, §19). The three patterns need a `-` right after the two digits, so `phase28a-…` and `phase28a-live-claims` never match. §10 item 3 read as if 28a were covered, and §12 sequenced around a cross-watch with the cancelled Phase 29. The process layer still catches a live 28a `--execute-live` process; a crashed, unfinalized 28a run or an open 28a claim is missed | **Fixed in this file, as proposed; the harness is not changed** (its pins would move). (1) §10 item 3 says the run-record check never reads `phase28a-*` or `phase28a-live-claims`, that only the process check covers 28a, and that a later harness change should widen the three patterns to `phase(?:2[01356789]\|3[1-9])[a-z]?-…` with a test. (2) §12's table replaces the Phase 29 cross-watch with Phase 28a and **requires the 28a harness, when built, to watch `artifacts/phase30-*` and `artifacts/phase30-live-claims`**. (3) §12 step 3 adds a manual $0 check: every `*manifest*.json` under `artifacts/phase28a-*` must be final with an `ended_at`, and every 28a claim must name a 28a run directory holding a final run manifest; the `ps` check covers a live 28a process. The command loads the harness and points its own run-record rule at 28a's folders in memory only, and it also names any non-final manifest without `started_at`. **Re-derived:** the harness's `other_run_files`, on a temporary tree with an open 28a run, an open 28a claim and an open `phase28-…` run, returned only the `phase28-…` manifest. **Rehearsed** exactly as printed in §12 step 3, on nine temporary trees: it named the open record in each of the six open cases (a RUNNING manifest; one two levels down without `started_at`; a claim with no manifest; `ended_at` with status RUNNING; an unreadable manifest; a 28a claim naming a Phase 30 directory), and printed the pass line for no 28a folder, for a closed 28a run with its claim, and for open runs of other phases only. On the repository it printed the pass line. At that reading `artifacts/phase28a-2026-09-25/` existed (Phase 28a's build in progress; its contents are listed in `fidelity_fix_checks_r3.out.json`), with no `*manifest*.json` under it and no `phase28a-live-claims` |
| F2 | minor | The protocol called 1.6–1.8% "the measured re-send slip rate" on U2 and dropped Phase 21's plain re-sends of U2 contexts: 7 of 180 (3.9%, Wilson [1.9%, 7.8%]), which Phase 27's protocol quoted. 20 of the 316 "fresh" U2 prompts are among those contexts, re-sent 5 times each with a request byte-identical to this phase's C, and 5 of 100 slipped; §2 row 7 and §6 did not say so. No decision effect, but "a reduction reaches p < 0.05 only about 55–66% of the time" holds only under models B and C (0.99 under A) | **Fixed in this file, as proposed.** §4 adds Phase 21's 7 of 180 beside Phase 27's 4 of 225 and says the live rate has measured between about 1.8% and 3.9%, about 42 hours apart (Phase 21 ran 2026-09-23 23:24 UTC, Phase 27 2026-09-25 17:20 UTC). §2 row 7 and §6 disclose the 20 prompts and their 5 of 100, and say each new send is still a fresh draw. §1 and §8.3 give the reduction's power as about 55–99%, depending on the rate. §8.3 notes that the harness's strings (lines 62, 682 and 1471, and the comment at 220) quote Phase 27's lower anchor only; they are pinned and stay. **Re-derived:** 180 report-required re-sends of 36 contexts (5 each), all U2-shaped by facts recomputed from the store, 7 unsupported (all `PENDING` for the confirmation), no context twice; matched by request hash, 100 of them equal this plan's C requests on 20 U2 prompts, 5 unsupported, one on each of 5 prompts; the recomputed facts equal the plan's on all 100. **Checked by exact computation** (model D, a flat 3.9%; `phase21_rate_numbers_r3.out.json`): it reproduces §8.2's B and C columns; every model-D figure is within 0.04 of model A's, and the chance of PASS on the rows a decision rests on within 0.004; the reduction's power for a perfect field is 0.99; the size at the margin at a C-only rate of 3.9% is 0.0235 (within §8.1's bound); c ≤ 1 has chance 0.005% |
| F3 | minor | §15's recipe for a later loop took the `FAILED` check "from `PolicyState` and the upgrade receipt". The tested window also excludes any delivered observation of the upgrade showing `FAILED`, and `PolicyState.status` returns the latest observation's status when there is no receipt (`policy_state.py:21-29`). So a turn where the upgrade was shown `FAILED` without a receipt and then read `UNKNOWN` is outside the tested window but would get the field under §15. No development turn is affected | **Fixed in this file, as proposed.** §15 now requires the later loop's check to be exactly `terminal_rejection(operation_facts(...))` (the `PolicyState` status `FAILED`, or a `FAILED` receipt, or any delivered observation of the upgrade with result status `FAILED`), says why `PolicyState` and the receipt alone are not enough, and asks for a test of the FAILED-then-UNKNOWN case (this harness's own test already pins it, `test_report_narrow_probe.py:300-301`). §5.1 condition 3 says the same. **Re-derived with real observation models:** a stored `FAILED` status observation with its receipt removed, followed by the same observation reading `UNKNOWN`, gives `PolicyState` status `UNKNOWN`, no receipt and `seen` `FAILED`/`UNKNOWN`; the declared window is closed, the PolicyState-or-receipt reading open. **On every development actor turn** (17,119 turns of 3,204 v4 episodes) the two readings agree: all 325 terminal-rejection turns have status and receipt `FAILED` (seen `FAILED`/`PENDING`) |
| F4 | minor | A round-2 regression (pitfall 74). §12 step 2 changed only line 3 and then said "do not edit this file afterwards", so the launch-pinned file would keep "Review rounds 1 and 2 ran … The fidelity lens … has not reported yet, and the review cannot close before it does" and "Pins of this draft, after round 2" beside a closed status. `check_review` looks only for "NOT yet reviewed", so the gate would pass; round 2's rehearsal asserted `closed_existing_lines_that_changed: [3]`, making the stale text the expected result | **Fixed in this file, as proposed.** §12 step 2 now replaces lines 3–13 (the status paragraph, the blank line and the pins paragraph) with an exact closed-state text, printed in the step, that names every round, this fidelity round included, with the final pins. A second check prints any draft wording left in the opening block (`not yet`, `has not reported`, `not closed`, `of this draft`). The opening block of this draft was rewritten for round 3. **Rehearsed** (`closure_rehearsal_r3.out.json`), taking the closed-state text from §12 step 2 itself on a scratch copy: exactly lines 3–13 were replaced, every other line is unchanged apart from the appended closing entry, the closed opening block has no draft wording and both of §12 step 2's shell checks pass, and `check_review` passes; it refuses the copy without the bare line, with the phrase back in the status line and with the bare line in backticks. Round 2's instruction applied to this draft leaves the draft wording, as the finding said, and the new check catches it |

**Round 3 and §16** (the closure gives the final answers): the fidelity lens gave no new answer to questions 1, 2, 4,
5 and 6. On question 3, fresh U2 prompts are kept; the 20 prompts that Phase 21 re-sent (never with the field) are
disclosed (F2).

**Also checked sound by round 3** (the reviewer's findings of no defect; not findings):
- **Pins and the dry run:** every pin in §3 equals its file, and the dry re-run reproduced plan `05f26608…` with
  `"passed": true`, configuration `2cf63e93…`, 17,119 of 17,119 turns verified and every must-be-zero pre-check
  line at 0.
- **Fidelity to the runtime:** `actor.py` sets the `actor_final_report` contract exactly when the turn is
  report-required, and all 860 planned requests are report-required, in the window and under that contract; the v4
  turn message's keys are `observations`, `final_report_required` and `remaining_actor_calls`, so
  `last_observed_status` sorts second, as §5.2 says; the `obs-k` labels match the runtime's; the provider settings
  (2,000 output tokens, 20 s, temperature 0, V3.1) match the Actor's. The configuration pin forces Phase 30 to run
  before the Phase 28 backend change, as `PHASE28_DESIGN.md` §9 and §19 require.
- **Fidelity to Phase 27:** the word rule, strata, status field, Webster allocation, worst-case rule, `RECEIVED` and
  the 95% completeness bar are imported unchanged; the guard-stratum counts equal Phase 27's plan (2,070); the
  quoted tolerances and every quoted Phase 27 figure match its read-outs; U1's R and T2 are Phase 27's C and T (104
  of 104); Phase 21's 51 U3 re-sends are byte-identical to this phase's R and all correct.
- **Never on a terminal-rejection turn:** 0 of 1,219 terminal-rejection-case turns and 0 of 286 G4 prompts are in
  the window; no planned request has `FAILED` in the upgrade's `seen`; in the terminal-rejection episodes the
  upgrade reads `PENDING`, never `UNKNOWN`, until `FAILED` arrives with a receipt.
- **The program and Phase 24:** Phase 24's failing turn is inside the window; the departures are declared in §2;
  the $20 cap equals the program's.
- **Round 2's changes:** only this file changed; §12 step 7's recheck matches the harness's statement; no
  `review.json` and no `phase30-live-claims` exist. After its last write, the §12 step 3 test command passed 206
  of 206.

**Operational:** round 3 did not touch any service. The paid-run guard reading and the power reading after the
fix's last edit are `review-r3/guard_reading_r3.out.json` and `power_r3.out.txt`; §12 step 3's power check must
still pass on the day of the launch.

**Round 3 fix pins** (all round 1's, unchanged): harness
`ca3b8b9d0df0960b4fff4f6ae8369f5cc6677815e9ee94b73f9c40e106681317`, plan
`05f266082d4bd7fe3ea5e62b859eb061df15a07a377282de2375d06b3979fd34`, dry plan file
`3931f0c6d2d38ec1649cf48cb62e97098d948d751d86c563dfeb572e21cb472b`, tests
`edf5c0867873f5e155ad2ab5d8bd6a49ef2875cb06de9542ad5dbcec9118d936`. Round 3 edited only this file, whose sha256 is
recorded at closure (§12 step 2). After the fix's last edit to this file: the §12 step 3 test command passed 206
of 206 (`review-r3/tests-r3.txt`); the dry run reproduced plan `05f26608…` with `"passed": true`
(`review-r3/dry-rerun-r3.out.txt`); every pin in §3 equals its file (`review-r3/pins-r3.out.json`); the closure
rehearsal and the Phase 28a check passed as described under F4 and F1; and every re-derived figure is in
`review-r3/fidelity_fix_checks_r3.out.json` and `phase21_rate_numbers_r3.out.json`.
