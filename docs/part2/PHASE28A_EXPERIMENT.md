# Phase 28a protocol — upgrade-side Mechanic probe (non-scoring go/no-go)

**Status: declared before any paid call; NOT yet reviewed.** No paid, provider, model or W&B call has been made for
this phase, and nothing under `backend/app` was edited. Every number below comes from a $0 dry run or a saved $0
computation. The harness sends nothing until the review is closed as §13 step 2 describes; §12 lists everything its
live gate checks. No review round has run yet (Review log).

Pins of this draft (the live gate requires both strings in this file): harness
45314eea8a082b062c9bdb93d22e9f1720a9052fb02be23fd0ebc436b768bba5 plan
e667a13bafa41cbebe57c165403f9bb6b6cc73748a01302a9af0095922a22e97

- **Program:** `docs/part2/EXPERIMENT_PROGRAM_PHASES_28-31.md`, Phase 28.
- **Design:** `docs/part2/PHASE28_DESIGN.md` §6.0 (the probe) and §8.4 (the harness); approver decisions §19 (all
  seven recommendations taken; decision 4 is "Phase 28a first, as a declared go/no-go"). Phase 29 is cancelled.
- **Harness:** `scripts/experiments/upgrade_mechanic_probe.py`. **Tests:**
  `backend/tests/experiments/test_upgrade_mechanic_probe.py`.
- **Imported, never edited, pinned by sha256 before any of their code runs:** Phase 25's `slot2_probe.py` and Phase
  17's `run_full_loop.py` (§3).
- **Evidence folder:** `artifacts/phase28a-2026-09-25/` (§18).
- **The owner's direction for the program:** "go ahead with whatever u recommend" (Shree Bohara, 2026-09-25, relayed
  by the workflow harness). It is context only. It is not this phase's approval, which is given in the review record
  after the review closes (§13).
- **Departures:** §2 lists every place this protocol departs from the design or from the build brief.

## 1. The question

Phase 26 found a second completion gap. When the **upgrade** call fails a few times in a row, the baseline Actor
usually gives up. A simple rule, "wait, then re-send the upgrade" (`retry_original_request` with `service: orders`),
completed those cases every time (36 of 36). The loop's Mechanic has never written that step: 0 of 59 stored v4
proposals re-send the upgrade. It has only ever been shown notification-side evidence, though.

Phase 28 would point the whole loop at an upgrade-side source. That needs a backend change and could spend $35–150.
This phase asks the cheap question first, for at most $5:

> Shown upgrade-side evidence in exactly the loop's own first-proposal format, does the Mechanic ever write an
> orders re-send that can fire after a transient upgrade failure?

- **GO** (at least one of 30): the Phase 28 build may start.
- **NO_GO** (none of 30, all delivered): Phase 28 closes with this probe as its result, and the backend change is
  never built.

It does **not** ask whether the loop would certify a repair, whether a repair is safe, or anything about held-out
cases.

## 2. Where this protocol departs from the design or the build brief

| # | design (§6.0, §8.4, §17) or brief | this protocol | why |
|---|---|---|---|
| 1 | design §8.4/§17: `mechanic_upgrade_probe.py`, `test_mechanic_upgrade_probe.py` | `upgrade_mechanic_probe.py`, `test_upgrade_mechanic_probe.py` | the build brief assigned these names; no file with the design's names exists |
| 2 | design §6.0: **GO** if a draw contains an orders re-send at **any** hook under **any** `only_if` (the "present" predicate, the same as the loop's futility look); the "can fire" label is descriptive | **GO** needs an orders re-send that the static check labels **CAN_FIRE** after a transient upgrade failure (§8). The design's "present" count is reported beside it, descriptive | the build brief states the decision this way ("that can FIRE after a transient failure (static gate check, pitfall 77)"). The rule is stricter than the design's, so NO_GO is more likely (§10). **Review question 1** |
| 3 | design §8.4 lists a short import list from `slot2_probe` | the exact list of names read from `slot2_probe` and `run_full_loop` is pinned by a test (AST scan). It adds the request digest, the classifier, the abstract interpreter (`run_hook`, `_service`), the freeze check, the request sender, the recorder, `wilson` and `before_cutoff`. It also imports `case_manifest` and `planned_slots` from `backend/app/lab/completion_study.py` (read-only) for the control spec and the controls order | reuse the reviewed code instead of copying it |
| 4 | design §6.0: positive control over the main-store **healthy** episodes used | over **all 174** rebuilt Phase 23 controls episodes. Also a byte-for-byte check of the context builder against **all 26** stored Phase 23 slot-1 inputs; the design put that check in the tests. Any difference refuses the plan (§7) | a stronger check at the same cost |
| 5 | design §6.0: "cannot fire" when gated only on PENDING; "can fire" or "unclear" otherwise | a concrete rule: Phase 25's abstract interpreter runs the policy through the two hooks the stored source path reaches, and the rule is validated at $0 against three stored policies (§8) | the design's label needed a runnable definition |
| 6 | design §6.0 declared difference 3: "Seeds do not appear in the bundles" | true of the bundles, but `observed_outcomes` groups trials by `scenario_hash`, which **is** shown. Added as declared difference 3 with its counts (§6) | found while building |
| 7 | design §6.0: `campaign_id` and `study_id` are "named probe values" | loop-shaped ids derived from the seed (§5); no word in the input names the probe | a word like "probe" in the input could change the answer |
| 8 | design silent | an **empty** first output, or one that arrived but could not be read, is a delivered **INVALID** draw. It gets no format repair, because the loop's Mechanic would raise there, and it is never re-sent (pitfall 49) | fidelity to `Mechanic._generate` |
| 9 | design §6.0: "after one blind re-send of each transport failure" | each attempt that fails with `CONNECTION_ERROR`, `REQUEST_TIMEOUT`, `HTTP_ERROR` or `PROVIDER_ERROR` **and shows no sign of a delivered generation** is re-sent once, after 10 s. There is no second pass (§11) | the design's wording, made exact |
| 10 | design §6.0: completing an INCOMPLETE run "sends exactly the missing request ids, once" with the owner's approval | the harness has **no completion mode**. It refuses any second run once a run delivered anything. Completing needs the owner's approval **and** a separately reviewed harness change | a completion path is a second chance and should be reviewed on its own. INCOMPLETE is unlikely (§11) |
| 11 | design §6.0: healthy pool "3 in Phase 20 and 2 in Phase 26, plus Phase 23's controls-stage healthy episodes" | exactly 84 of Phase 23's 87 (3 were `SAFE_UNRESOLVED`) | the declared rule applied |
| 12 | design §6.0: the review record repeats the three hashes | it also repeats the configuration pin and the $5 phase cap, says `status: approved` and names the approver | the Phase 29/30 record rules |

## 3. What is fixed

| item | value |
|---|---|
| harness (this draft) | `upgrade_mechanic_probe.py` sha256 `45314eea8a082b062c9bdb93d22e9f1720a9052fb02be23fd0ebc436b768bba5` |
| plan (this draft) | `e667a13bafa41cbebe57c165403f9bb6b6cc73748a01302a9af0095922a22e97` (`artifacts/phase28a-2026-09-25/dry-plan/plan.json`) |
| imported | `slot2_probe.py` `28b998ac9d66fc03287dd518afb3ed64df5191d711f95a981cfd86c18a1155d0`; `run_full_loop.py` `07dcaa93fd2e2d62ea22209bc78981fd011d025f839d0143dca157f6208f2342`. Each file's bytes are read once and checked **before** any of it runs |
| configuration | `2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba`, recomputed from the code on disk with the Phase 17 settings (`artifacts/phase16-2026-09-22/settings-phase17.json`, `1e2002d3…`). **Any Phase 28 backend change moves it, and the harness then refuses** |
| freeze | Phase 22 `gate-freeze-after.json` `8994e962…`: fingerprints `source_hash` `da80ac6f…`, `runtime_hash` `67e6d968…`, `contract_hash` `6f9d7783…`, `algorithm_hash` `f2f71c59…`, `interpreter_hash` `d64cac7a…`; file sha256s of `completion.md`, `mechanic.py`, `diagnosis.py`, `completion_study.py`, `policies.py`, `evidence.py`, `reproduction.py`, `progress.py`, `actor.py`, `prompts/actor.md`, `manifests.py` and `audit/development.json`. The scorer and the private partitions listed in that freeze are never opened |
| stores | main `artifacts/lab.sqlite3` (read-only; Phase 23 studies created before `2026-09-24T05:50:00Z`, which must equal the pinned Phase 23 run manifest's studies, `aac41711…`); Phase 20 `run-1/lab.sqlite3` `8d78f099…` with plan `549a9eb1…`; Phase 26 `run-1/lab.sqlite3` `d1f8e741…` with plan `0a9dfbdc…` (both `immutable=1`, no WAL) |
| record kinds read | `episodes`, `trials`, `observations`, `configurations`, `evidence`, `completion_studies`, `completion_proposal_inputs`; the `events` table. **No `private_*` kind**; a test records every statement and its parameters |
| model and request | `deepseek-ai/DeepSeek-V4-Pro-0813`, temperature 0, 2,000 output tokens, 20 s timeout, the frozen response format, no thinking (the loop's Mechanic settings) |
| source spec | F4 `update_order`/`orders`, occurrence 1, `failure_count: 3`, seed 703; content hash `c4decdb93f69db9bce758e4bdb9951a40025ff40c2dd4b6bb73df68465f57c76`, equal to the design's stdlib mirror (§4.1 row 2) |
| control spec | `case_manifest()`'s `healthy` (dev-1, seed 101, no primitives), equal to the one in every Phase 23 manifest |
| design | K = 30 contexts, one draw each; seed `faultlab-phase28a-2026-09-25` |
| money | $0.04984 per request (the conservative bound), 60 planned calls ($2.99), **hard phase cap $5** |

## 4. The episodes (development data only, baseline B0 only)

**How a schedule is recognised.** Each finished store's pinned plan lists its cases with their public fault
specs. The harness checks that each spec hashes to its `scenario_hash`, and matches episodes by that hash. No
private recipe is read.

**The `upgrade-3` pool: 19 episodes.**
- Phase 20: 8, from cases `A-c3-r1/r2/r3`. Phase 26: 11, the B0 arm of `MR-c3-r1/r2` and `L-c3-r1/r2`.
- Rule: v4 Actor context (the first `actor_output` event), DeepSeek-V3.1, `challenge` purpose, arm B0 with the
  baseline policy `bafdc14f…`, a valid trial, and **not completed**. A loop context exists only when the valid source
  controls show 0 completions, so the 2 completing episodes (1 per store) are excluded.
- All 19 are `SAFE_UNRESOLVED` with 0 check failures. **Each one used all 8 Actor turns and 8 HTTP attempts**: the
  baseline Actor polled UNKNOWN until its reserved report turn and never re-sent. There are 7 distinct scenario
  hashes among them.
- L and manual-reference episodes are excluded (Phase 20: 9; Phase 26: 12).

**The `healthy` pool: 89 episodes.**
- Phase 20: 3. Phase 26: 2 (1 more was `SAFE_UNRESOLVED` and is excluded).
- Main store: 84 of Phase 23's 87 controls-stage healthy episodes (3 were `SAFE_UNRESOLVED`). All are valid,
  COMPLETED, B0, DeepSeek-V3.1, v4.

**The draws (`DRAW_RULE`).**
- For each pool, every 3-episode combination is ranked by sha256 of the seed, the pool and the sorted ids. The
  harness takes combinations in rank order and skips any that would use an episode more than
  cap = ceil(90 / pool size) times: **5** for `upgrade-3`, **2** for `healthy`. It stops at 30.
- Context *k* takes the *k*-th triple of each pool. Within a triple the episodes are ordered by a second seeded rank.
- The six controls are interleaved in `planned_slots` order: `upgrade-3`, `healthy`, `upgrade-3`, `healthy`,
  `upgrade-3`, `healthy`.
- **Result:** 30 distinct `upgrade-3` triples and 30 distinct healthy triples.
  - Source episode uses: 16 episodes 5 times, 2 episodes 4 times, 1 episode twice.
  - Healthy: 57 episodes used (33 twice, 24 once).
  - Stores in each source triple: Phase 20 + Phase 26 + Phase 26 in 13 contexts, Phase 20 × 2 + Phase 26 in 12,
    Phase 26 × 3 in 4, Phase 20 × 3 in 1.
  - 5 of 30 contexts include a Phase 20 or 26 healthy episode.
- **The draws are correlated.** 19 source episodes fill 90 slots, and the model sees similar evidence many times.
  Intervals are Wilson intervals over the 30 draws, and they **understate** the uncertainty.

## 5. The request (exactly the loop's slot-1 request)

Each context is `completion_study._execute`'s slot-1 `proposal_context` (lines 394–403):

- `campaign_id` = `campaign-` + the first 32 hex of sha256(`<seed>:campaign:<k>`); `study_id` =
  `completion-study-` + the first 32 hex of sha256(`<seed>:study:<k>`). These are the loop's id shapes.
- `objective` `faultlab-completion-study/v1`; `parent_version` `policy-v0`.
- `source_fault_spec`: the `upgrade-3` spec (§3). `control_fault_spec`: the healthy spec (§3).
- `runtime_contract()`; `development_evidence = summarize_evidence(bundles, outcomes={episode: adjudicated
  outcome})` (the v2 task-outcome protocol); `observed_outcomes = trial_outcomes(trials)`; `candidate_history = []`.
- **Bundles are rebuilt locally**, exactly as `EvidenceGateway.get(require_remote=False)` builds them: the stored
  observations in store order, the episode's report, and the verdict's checks as findings; `source: local_only`,
  no call ids, `retrieved_at: null`. The gateway's eligibility rules apply, except its cross-context check.
- **Messages:** Phase 25's `mechanic_messages(context)`, which is `Mechanic._generate`'s request byte for byte. A
  test runs the real `Mechanic.propose_completion` with a fake provider and compares.
- **Body:** Phase 25's `request_body(messages, 0)`. Every send is digest-checked against the plan before it leaves
  (Phase 25's `RequestSender`).
- **Size:** input bounds are 8,323–9,708 tokens against the frozen 32,000.

**Format repair (as the loop).** When the first output fails `MechanicOutput` validation, the harness sends one
follow-up: the first messages, then the output as the assistant message, then
`canonical_json({validation_errors, instruction})`. The instruction is `_generate`'s, verbatim ("Your response
failed output_schema or its supplied evidence/choice bindings. Correct formatting only. …"). A test reads it from
`mechanic.py` and checks the whole follow-up against the real Mechanic's. Its request digest is computed from the
saved first output and checked before sending. A first output that validates gets no repair, and neither does an
empty or unreadable one (§2 row 8).

## 6. Declared input differences from a loop context (their effect is unmeasured)

1. Every evidence row reads `source: local_only`. A loop's rows read `weave_verified`. The healthy rows are rebuilt
   too, so the label is uniform.
2. The six controls come from different campaigns and stores (Phases 20, 26 and 23), not one study's controls, and
   they keep their stored episode ids.
3. The source episodes ran under their own seeds, not 703. `source_fault_spec` shows seed 703, and
   `observed_outcomes` groups trials by `scenario_hash`. So the three source controls carry **3 different scenario
   hashes in 21 contexts and 2 in 9**, where a loop's three share one; none equals `content_hash(source_fault_spec)`.
   The Phase 20/26 healthy episodes also carry their own hash.
4. `campaign_id` and `study_id` follow a declared rule (§5), not a real study.

These are why the probe decides only GO or NO_GO, and why Phase 28 keeps its own futility look.

## 7. The $0 positive controls (any failure refuses the plan)

| control | result (dry plan) |
|---|---|
| bundle rebuild: every main-store Phase 23 controls episode, local rebuild against its stored `weave_verified` bundle, on `episode_id`, `policy_hash`, `contract_hash`, `scorer_hash`, `observations`, `report`, `findings` | **174 of 174 equal**. One controls episode is not eligible evidence and is never used |
| context rebuild: each Phase 23 study with a stored slot-1 input, rebuilt from its own ids, specs and locally rebuilt control bundles | **26 of 26 byte-equal** to the stored input once each row's source label reads `weave_verified` |
| static check against stored behaviour (§8) | **3 of 3 agree** |
| hook reach on the source path | 19 of 19 pool episodes filed a report; 0 of 19 sent a confirmation |
| source spec | equals the design's mirror; content hash `c4decdb9…` |
| control spec | equals the healthy spec in every Phase 23 manifest |

## 8. The static check: "can fire after a transient upgrade failure" (pitfall 77)

**The declared source path.** The Actor's `update_order` exhausts its adapter retries with `TRANSIENT_UNAVAILABLE`.
The upgrade is then attempted, has no receipt, and reads **UNKNOWN**, never PENDING, because the write was never
accepted. The stored pool episodes show exactly this: status reads after the failure return UNKNOWN. On that path
two hooks run:
- `after_upgrade_response`, right after the failed call;
- `before_final_report`, when the Actor proposes its report. In all 19 pool episodes the Actor filed a report and
  never sent a confirmation.

**The check.** Phase 25's reviewed abstract interpreter (`run_hook`, whose conditions a Phase 25 test pins to the
runtime's) runs the policy through `after_upgrade_response` and then, unless a step closed business or exhausted a
bound, `before_final_report`, sharing one policy-step budget. Status reads deliver UNKNOWN. The labels:

| label | meaning |
|---|---|
| `CAN_FIRE` | the orders re-send executes at `after_upgrade_response` or at `before_final_report` (`fires_at` says which) |
| `CANNOT_FIRE` | it executes at neither: gated on `current_operation_pending` (UNKNOWN is never PENDING), gated on a receipt the failure never delivers, closed by an earlier `defer_unresolved`, or a bound exhausted |
| `UNCLEAR` | it would execute only at `before_confirmation` or `after_notification_response`, which the stored source path never reaches |

**Validation against stored behaviour ($0).** "Fired" means the policy itself dispatched `update_order` in a valid L
trial on F4 counts 2–4:

| policy | static | dynamic |
|---|---|---|
| manual reference `b8d18218…` (Phase 26) | `CAN_FIRE` at `after_upgrade_response` | fired in 18 of 18 |
| certified `dd62c857…` (Phase 20) | no orders re-send | fired in 0 of 27 |
| certified `711bddb6…` (Phase 26) | no orders re-send | fired in 0 of 18 |

**What the check does not model:** HTTP and tick budgets, and what the Actor would do differently after a policy's
reads or waits. A re-send that fires only at `before_final_report` runs after the Actor has already proposed its
report. It cannot lead to a confirmation, and the report may no longer match the world. It still counts as
`CAN_FIRE`, and the statement names it separately (review question 2).

## 9. Declared read-outs and the decision (computed by the harness, never re-declared)

**A draw** is one of the 30 contexts. Its output is the first response if that validates; otherwise it is the
format-repair response. Classes (Phase 25's `classify_response`, which applies the study's rules):
- `CANDIDATE`: a valid policy.
- `NO_CHANGE`.
- `INVALID`: fails `MechanicOutput` after the repair; empty or unreadable; a stale parent; or a `CandidatePolicy`
  failure.
- `UNDELIVERED`: the output the loop would use never arrived.

**The decision:**
- **GO** iff at least one draw is a `CANDIDATE` whose orders re-send is `CAN_FIRE`.
- **NO_GO** iff all 30 draws were delivered and none is. The Wilson 95% upper bound for 0 of 30 is **11.4%**.
- **INCOMPLETE** iff fewer than 30 were delivered and none so far is.
- A `NO_CHANGE` or `INVALID` draw is a draw without the step (the Phase 9 rule).

**Pre-fixed wording** (the harness writes it; every form ends with the scope sentence):
- GO: "GO: *k* of 30 first proposals (Wilson 95% [*lo*, *hi*]) contain an orders re-send … that the static check
  says can fire after a transient upgrade failure: *j* at after_upgrade_response, where a re-send can complete the
  task, and *k − j* only at before_final_report, after the Actor has proposed its report. This decides only that the
  Phase 28 build may start; it does not mean the loop will certify a repair."
- NO_GO: "NO_GO: 0 of 30 first proposals contain an orders re-send that can fire after a transient upgrade failure
  (Wilson 95% upper bound 0.114); *p* contain one that cannot or may not fire. Phase 28 closes; the backend change is
  not built."
- INCOMPLETE: "INCOMPLETE: *d* of 30 draws delivered, none so far with an orders re-send that can fire; completing
  the missing draws needs the owner's approval."
- Scope sentence: "Development evidence only, rebuilt locally (every evidence row reads local_only), from episodes
  of several campaigns and stores; one draw per context at temperature 0; contexts share episodes, so the intervals
  understate the uncertainty."

**Descriptive, never deciding:**
- **R_draw:** firing re-sends ÷ 30. **R_valid:** firing re-sends ÷ CANDIDATE draws. Both with Wilson intervals.
- **The design's "present" predicate** (an orders re-send at any hook, under any gate), ÷ 30 and ÷ CANDIDATE.
- For each re-send: its label, `fires_at`, reason, hook, `when`, `only_if`, and the number of orders re-send steps.
- NO_CHANGE and INVALID shares (Wilson), with INVALID split by cause.
- Format repairs needed and their results.
- Distinct policies (content hash); distinct policies with a present re-send and with a firing one; re-draws of the
  four certified policies.
- The Phase 9 notification step (`run_full_loop.contains_step`); both-sides policies; the Phase 17 attempt-4 pattern
  (a premature defer, Phase 25's audit).
- Per-episode exposure (contexts and firing draws); served model and tokens.

**Uses.**
- The decision only. No tuning: N, the cap, the look, the certification rule and the case set of Phase 28 are fixed
  by its design and do not change with this result.
- No pooling with the loop's S1.
- The result is never shown to any model.

## 10. Operating characteristics ($0; `plan.operating_characteristics`)

P(NO_GO) if all 30 draws are delivered and independent. *s* is the per-draw rate of a working upgrade re-send; this
rule takes the rate of a firing one to equal *s*. The design's column (the "present" rule, *r* = *s* / 0.75) is
reproduced for comparison. Correlated draws make NO_GO **more** likely than both columns say.

| *s* | P(NO_GO), this rule | P(NO_GO), design's "present" rule |
|---:|---:|---:|
| 0 | 1.000 | 1.000 |
| 0.01 | 0.740 | 0.669 |
| 0.02 | 0.546 | 0.445 |
| 0.03 | 0.401 | 0.294 |
| 0.05 | 0.215 | 0.126 |
| 0.10 | 0.042 | 0.014 |
| 0.15 | 0.008 | 0.001 |
| 0.20 | 0.001 | 0.000 |

At *s* = 0.05 the stricter rule raises the chance of a NO_GO from about 13% to about 21%. At *s* = 0.10 it raises it
from about 1% to about 4%.

## 11. Spend cap, bounds, retries and stop rules

- **Planned:** 30 first requests + at most 30 format repairs = 60 calls × $0.04984 = **$2.99**.
- **Hard phase cap $5** = 100 attempts, charged at the bound in whole micro-dollars. Every attempt is charged,
  including blind re-sends. A run that ends having delivered nothing still counts against the phase cap for a later
  run.
- **Blind re-send (pitfall 49):** one re-send, after 10 s, of an attempt that failed with `CONNECTION_ERROR`,
  `REQUEST_TIMEOUT`, `HTTP_ERROR` or `PROVIDER_ERROR` and shows no sign of a delivered generation. A delivered
  generation is never re-sent.
- **Stops:**
  - the spend guard, which refuses an attempt that would pass the cap;
  - five errored draws in a row, after waits of 30, 120, 300 and 300 s;
  - an operator stop (SIGINT or SIGTERM), recorded with where it arrived;
  - a crash, recorded with its traceback.
- **One run.** A second run is refused once any run delivered a generation. A run that delivered nothing may be
  followed by one more within the remaining phase cap.
- **Budget.** The program document records $652.90 charged and $347.10 remaining. The operator reconciles the
  ledger (Phase 30 may have spent since) and adds this run's `charged_upper_bound` afterwards.

## 12. The live gate (in the order the harness checks it)

1. `--execute-live` needs `--out`, `--confirm-entity`, `--expect-plan-hash`, `--expect-harness-sha256` and
   `--expect-protocol-sha256`.
2. `--out` is a new directory exactly `artifacts/phase28a-<date>/<name>`. No earlier Phase 28a run may be unfinished
   or have delivered anything.
3. **One paid run at a time.** No other phase's run manifest may be open, and no other phase's claim may lack a final
   manifest. The directories read are Phases 20, 21, 23, 25–29 and 30+; Phases 22 and 24 are never read, and
   `phase28-` (the loop) is included. No other `--execute-live` experiment process may exist, by Phase 25's token
   rule, which excludes this process, its ancestors and its descendants such as its own `caffeinate -is` helper. The
   lab backend, if up, must show no active campaign; an unreadable status blocks.
4. The pinned imports are unchanged on disk; sha256(this harness) = S; sha256(protocol) = P; the recomputed plan
   hash = H; this file contains S and H.
5. This file's status block (the lines before the first `## `) no longer says "NOT yet reviewed" in any case. It
   carries the **bare** line `Reviewed for launch: harness S plan H`, without backticks, a list marker or bold.
6. `artifacts/phase28a-2026-09-25/review.json` has `status: "approved"`, a non-empty `approved_by`,
   `protocol_sha256` P, `harness_sha256` S, `plan_hash` H, `configuration_hash` `2cf63e93…` and `phase_cap` 5.0.
7. Every request's prompt hashes to its plan entry. The spend cap covers the 60 planned calls.
8. **Only then** does the runtime's own loader read the credentials. The entity must match `--confirm-entity`, the
   project and the Mechanic model must be the declared ones, and the configuration pin is recomputed.
9. The paid-run check runs again. A stop signal that arrived meanwhile refuses. The atomic claim is taken
   (`artifacts/phase28a-live-claims/claim-NN.json`, never deleted). The paid-run check runs once more after the
   claim; a blocker then ends the run at $0.

The plan holds no protocol sha and no review-record sha, so there is no hash cycle. A test shows the plan hash does
not change when the protocol does, and changes when the seed or the cap changes.

## 13. Runbook

1. **Review (at least two adversarial rounds, design §11).** Lenses: statistics and design (§9–§10 and the
   departures); harness and fidelity (§5–§8, the tests); integrity and launch (§3, §12, sequencing). A round that
   changes the harness is followed by another (pitfall 74). After any fix:
   - re-run the tests from `backend/` after the last edit (pitfall 75);
   - write a new dry plan to a new directory (`--write-plan artifacts/phase28a-2026-09-25/dry-plan-rN`);
   - update this file's "Pins of this draft";
   - record every finding and its disposition in the Review log.
2. **Close the review (the approver, not the builder).**
   - Change this file's status line so it no longer says "NOT yet reviewed".
   - Add the bare line `Reviewed for launch: harness S plan H` to the status block.
   - **Then** take P = `shasum -a 256 docs/part2/PHASE28A_EXPERIMENT.md`. Nothing edits this file afterwards.
   - Write `artifacts/phase28a-2026-09-25/review.json` with `status`, `approved_by`, `approved_at`,
     `protocol_sha256` P, `harness_sha256` S, `plan_hash` H, `configuration_hash`, `phase_cap: 5.0`, the review
     rounds, `remaining_budget_at_approval`, and `approval_basis` (the owner's program direction, as context only).
3. **Before launch.**
   - Phase 30 has ended, with no run of it live. The Phase 28 backend change has **not** landed; the configuration
     pin enforces this.
   - A dry run prints plan hash H.
   - AC power, lid open.
   - This probe calls the provider directly and needs neither the simulator nor the lab backend. If the backend is
     up, it must show no active campaign.
4. **Launch** (from the repository root):
   `caffeinate -is ./.venv/bin/python scripts/experiments/upgrade_mechanic_probe.py --execute-live --confirm-entity
   <entity> --out artifacts/phase28a-2026-09-25/live --expect-plan-hash H --expect-harness-sha256 S
   --expect-protocol-sha256 P`
5. **After.**
   - `--readouts artifacts/phase28a-2026-09-25/live` reproduces `readouts.json`.
   - Add `charged_upper_bound` to the ledger.
   - Write `PHASE28A_RESULTS.md` with the statement, the §9 descriptive figures and every limit in §15.
   - On GO, the Phase 28 build may start (design §9 step 2). On NO_GO, Phase 28 closes.
6. **If the process dies.** `--finalize-abandoned artifacts/phase28a-live-claims/claim-NN.json` closes it at $0 and
   charges what was recorded. An INCOMPLETE run is completed only with the owner's approval and a separately
   reviewed change (§2 row 10).

## 14. What each result would and would not mean

- **GO.**
  - *Would mean:* the Mechanic sometimes writes an upgrade re-send that can fire, when shown upgrade-side evidence in
    this format.
  - *Would not mean:* that the loop will certify a repair; that the re-send completes the task (read `fires_at`: a
    `before_final_report` re-send cannot); that it is safe; anything about held-out cases.
- **NO_GO.**
  - *Would mean:* 0 of 30 in this format (upper bound 11.4%, and wider in truth because the draws are correlated).
    Phase 28 closes, and no backend change is made.
  - *Would not mean:* that the Mechanic cannot with another brief, temperature or model, or with `weave_verified`
    rows. It also would not mean it never writes a re-send: read the "present" count.
- **INCOMPLETE.** Not a finding about the Mechanic.
- **Never:** ACCEPTED, certified, a policy, or a change to anything. The probe creates no campaign, study, trial,
  world, policy or store row.

## 15. Limits

- The inputs differ from a loop's in four declared ways (§6). Their effect is unmeasured.
- Only 19 source episodes exist. They fill 90 slots, so the 30 draws are correlated.
- One draw per context at temperature 0. Temperature 0 is not deterministic (Phase 21: 36% of repeat pairs were
  byte-identical), so a re-run would differ. That is why there is one run.
- Slot 1 only. Slot 2, the source gate and validation are not modelled.
- The static check is abstract (§8). `UNCLEAR` re-sends do not count toward GO. `before_final_report` re-sends do
  count, although they cannot complete the task.
- The brief (`completion.md`), the model and the settings are the loop's. The result speaks only to them.
- Development data only. No held-out partition is read, and none can follow for Phase 28 (design §10, decision 7).

## 16. What must not happen

- No edit under `backend/app`, to the pinned harnesses, to `completion.md`, to the settings or to the gate. The
  scorer is never opened.
- No `private_*` record, no heldout-2 file, no promotion or final-audit partition, and no `.env` read by the dry
  plan.
- No second run once a run delivered anything; no re-send of a delivered generation; no re-declared read-out; no
  change to Phase 28's N, cap, look, certification rule or case set after this result.
- No result shown to any model or entered into a study; nothing called ACCEPTED.
- No launch beside another paid run, or after the Phase 28 backend change lands.

## 17. Questions for the review

1. **The decision predicate.** The build brief's "an orders re-send that can fire" (built) or the design's
   "present" (reported)? The stricter rule costs about 9 points of P(GO) at *s* = 0.05 (0.874 against 0.785, §10). The loop's futility
   look still counts present steps either way.
2. **`before_final_report` re-sends** fire after the Actor's report proposal, so they cannot complete the task and
   may leave the report stale. Should GO count only `after_upgrade_response`?
3. **`UNCLEAR`** re-sends (only at hooks the source path never reaches) do not count. Is that right?
4. **Correlation.** 16 of 19 source episodes appear in 5 contexts each. Is 30 draws over 19 episodes acceptable for
   a go/no-go, given the upper bound is stated as understated?
5. **The healthy mix.** 84 of 89 healthy episodes come from Phase 23's main-store controls, and 5 contexts include a
   Phase 20/26 healthy episode with its own scenario hash. Acceptable?
6. **No completion mode** for INCOMPLETE (§2 row 10). Acceptable, or should one be built and reviewed now?

## 18. Evidence files (all $0)

- `artifacts/phase28a-2026-09-25/dry-plan/`: `plan.json` (the hashed plan: pins, pools, exclusions, positive
  controls, draws, requests, rules), `dry-summary.json`, `prompts.jsonl` (the 30 exact message lists).
- `artifacts/phase28a-2026-09-25/dry-plan-stdout.txt`: the dry run's output.
- `artifacts/phase28a-2026-09-25/prep/`: the pre-build checks with their outputs, and labelled copies of the
  design's scratch (see its `README.md`).
- `artifacts/phase28a-2026-09-25/tests-upgrade_mechanic_probe.txt`: the test run after the last edit.
- Not yet written: `review.json` (the approver writes it at §13 step 2) and the live run folder.

## Review log

No review round has run yet.
