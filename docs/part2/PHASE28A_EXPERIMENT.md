# Phase 28a protocol — upgrade-side Mechanic probe (non-scoring go/no-go)

**Status: declared before any paid call; reviewed in rounds 1, 2, 3 and 4; closed 2026-09-26; approved by Claude (Opus 5.5) as PM, delegated by the project owner.**
No paid, provider, model or W&B call had been made for this phase when the review closed, and nothing under
`backend/app` was edited. Every number below comes from a $0 dry run or a saved $0 computation. Rounds 1 (two
lenses, 9 findings), 2 (one reviewer, 4 findings) and 3 (two reviewers, 9 findings, 8 distinct) each applied every
finding; round 3 changed one line of the harness, and round 4 (the focused check of that change, pitfall 74) found
no new problem (Review log). §12 lists everything the live gate checks.

Pins at closure (the live gate requires both strings in this file): harness
3dacdbeda2c670936e99e41dd50f1c2aade70fdb7b54247f922c9bfd108938a0 plan
a04d931938be880365dc3a0261d24ab9d050297520b9f63fef4ef9db505d9a8c

Reviewed for launch: harness 3dacdbeda2c670936e99e41dd50f1c2aade70fdb7b54247f922c9bfd108938a0 plan a04d931938be880365dc3a0261d24ab9d050297520b9f63fef4ef9db505d9a8c

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
> orders re-send (`retry_original_request` with `service: orders`), at any hook and under any gate?

- **GO** (at least one of 30 draws is a valid policy with an orders re-send): the Phase 28 build may start.
- **NO_GO** (none of 30, all delivered): Phase 28 closes with this probe as its result, and the backend change is
  never built.

This is the design's "present" predicate (design §6.0, approved in §19 decision 4), the same predicate as Phase 28's
futility look. Whether a re-send can fire after a transient upgrade failure is reported beside it, as a description
(§8); it never decides. Round 1 restored this rule (Review log, finding 1).

It does **not** ask whether a re-send works, whether the loop would certify a repair, whether a repair is safe, or
anything about held-out cases.

## 2. Where this protocol departs from the design, the build brief or an earlier phase's launch rule

| # | design (§6.0, §8.4, §17), brief or earlier rule | this protocol | why |
|---|---|---|---|
| 1 | design §8.4/§17: `mechanic_upgrade_probe.py`, `test_mechanic_upgrade_probe.py` | `upgrade_mechanic_probe.py`, `test_upgrade_mechanic_probe.py` | the build brief assigned these names; no file with the design's names exists |
| 2 | design §6.0: **GO** if a draw contains an orders re-send at **any** hook under **any** `only_if` (the "present" predicate, the same as the loop's futility look); the "can fire" label is descriptive | **no departure (restored in round 1).** GO is the design's "present" predicate; the static check's label, `fires_at` and reasons are descriptive (§8, §9). `R_draw` is the design's (present ÷ 30); the firing rate is the separate, descriptive `R_fire_draw` | the round-0 draft had taken the build brief's stricter "can FIRE" wording as the decision. That was not an approver decision, and it was not coherent (it counted a `before_final_report`-only re-send that cannot complete the task). Round 1, finding 1 |
| 3 | design §8.4 lists a short import list from `slot2_probe` | the exact list of names read from `slot2_probe` and `run_full_loop` is pinned by a test (AST scan). It adds the request digest, the classifier, the abstract interpreter (`run_hook`, `_service`), the freeze check, the request sender, the recorder, `wilson` and `before_cutoff`. It also imports `case_manifest` and `planned_slots` from `backend/app/lab/completion_study.py` (read-only) for the control spec and the controls order | reuse the reviewed code instead of copying it |
| 4 | design §6.0: positive control over the main-store **healthy** episodes used | over **all 174** rebuilt Phase 23 controls episodes. Also a byte-for-byte check of the context builder against **all 26** stored Phase 23 slot-1 inputs; the design put that check in the tests. Any difference refuses the plan (§7) | a stronger check at the same cost |
| 5 | design §6.0: "cannot fire" when gated only on PENDING; "can fire" or "unclear" otherwise | a concrete rule: Phase 25's abstract interpreter runs the policy through the two hooks the stored source path reaches (§8). Checked at $0 against stored behaviour on **1 informative policy** (the manual reference: `CAN_FIRE` at `after_upgrade_response`, fired 18 of 18); the **2 other stored policies have no orders re-send and cannot disagree**. `CAN_FIRE` at `before_final_report`, `CANNOT_FIRE` and `UNCLEAR` have **no dynamic validation**. The label is descriptive only | the design's label needed a runnable definition. Round 1, finding 2 corrected the earlier "3 of 3 agree" |
| 6 | design §6.0 declared difference 3: "Seeds do not appear in the bundles" | true of the bundles, but `observed_outcomes` groups trials by `scenario_hash`, which **is** shown. Added as declared difference 3 with its counts (§6) | found while building |
| 7 | design §6.0, declared difference 4: "`campaign_id`, `study_id` and `parent_version` are named probe values" | loop-shaped ids derived from the seed (§5); no word in the input names the probe. **`parent_version` is the loop's own `policy-v0`, not a probe value**, so design difference 4 applies to the two ids only; the stored Phase 23 slot-1 inputs read `policy-v0` too (the context rebuild is byte-equal to 26 of 26, §7) | a word like "probe" in the input could change the answer; the loop's `parent_version` is closer to the loop than a probe value. Round 3 (fidelity F6) declared the `parent_version` part |
| 8 | design silent | an **empty** first output, or one that arrived but could not be read, is a delivered **INVALID** draw. So is a format repair that comes back empty or unreadable, or that the input bound refuses (`INPUT_LIMIT`, `REQUEST_LIMIT`). None is repaired or re-sent (pitfall 49). **This is not what the loop records.** There, `Mechanic._generate` raises (`mechanic.py:28-31`; `validate_model_input` raises for the input bound, `tokens.py:86-89`); `_execute`'s handler makes the study INCOMPLETE with no candidate attempt (`completion_study.py:449-457`), an infrastructure death (design §7.2). The read-outs therefore count these draws separately (`not_a_loop_proposal`), and every statement says how many of the 30 they were (§9) | a generation arrived, so it is delivered under the design's INCOMPLETE rule, and it can never be re-sent. Counting it as "not a draw" would turn one empty reply into an INCOMPLETE that could be completed only by re-sending a delivered answer. The convention can move a run from INCOMPLETE to NO_GO, never to GO. Round 1, finding 3 corrected the earlier "fidelity" justification |
| 9 | design §6.0: "after one blind re-send of each transport failure" | each attempt that fails with `CONNECTION_ERROR`, `REQUEST_TIMEOUT`, `HTTP_ERROR` or `PROVIDER_ERROR` **and shows no sign of a delivered generation** is re-sent once, after 10 s. There is no second pass (§11) | the design's wording, made exact |
| 10 | design §6.0: completing an INCOMPLETE run "sends exactly the missing request ids, once" with the owner's approval | the harness has **no completion mode**. It refuses any second run once a run delivered anything. Completing needs the owner's approval **and** a separately reviewed harness change | a completion path is a second chance and should be reviewed on its own. INCOMPLETE is unlikely (§11) |
| 11 | design §6.0: healthy pool "3 in Phase 20 and 2 in Phase 26, plus Phase 23's controls-stage healthy episodes" | exactly 84 of Phase 23's 87 (3 were `SAFE_UNRESOLVED`) | the declared rule applied |
| 12 | design §6.0: the review record repeats the three hashes | it also repeats the configuration pin and the $5 phase cap, says `status: approved` and names the approver | the Phase 29/30 record rules |
| 13 | design §6.0: completing an INCOMPLETE run needs the user's approval and sends the missing ids "once" | **no departure (restored in round 2).** After runs that **delivered nothing**, every request id is missing, and another launch sends all 30, once. The harness admits it only with `--relaunch-approval`, naming the owner's record `artifacts/phase28a-<date>/relaunch-approval-NN.json` for **exactly that launch** (`RELAUNCH_RULE`, §11): `status: approved`, `approved_by`, `approved_at`, the earlier runs exactly as the harness lists them, the new `--out`, the plan hash and the harness sha256. One record admits one launch: once that launch has run, the list of earlier runs has grown and the record no longer matches. "Once" is read as one launch per owner approval. With no earlier run, the argument must be absent. The $5 phase cap still applies, so it admits 4 to 41 launches in all (the first one plus approved relaunches), depending on what each earlier run was charged; runs that sent nothing are charged $0 and never use it up (§11) | round 1 had let a zero-delivery run be followed by launches **with no approval**, as long as the phase cap covered the plan. That was a departure from design §6.0 declared by the builder, with no approver record, the thing round 1's own finding 1 ruled out. Round 2, finding 2, option (b) |
| 14 | Phase 25, review round 3 (finding 2): the run is "not run from an agent's or tool's shell: a tool that cleans up its process group would send the run a SIGTERM" | **Claude as the operator launches the run from its own Bash tool shell**, detached under `nohup` (§13 step 4), and keeps that Claude session open until the manifest is final | measured in round 2 (`review-r2/reviewer/launch_rehearsal_r2.*`) with a stand-in launched exactly as step 4: `$!` is the Python process; `caffeinate` is its child; Python survives the tool call's return (parent becomes pid 1, SIGHUP ignored, heartbeats continue, no signal received); `kill -TERM <pid>` reaches the handler, which stops within 0.2 s, and `caffeinate` exits too. **But** Python stays in the tool shell's process group and session (pgid = sid = the tool shell's pid), and `set -m` cannot move it out ("can't change option: -m"). So any cleanup of that process group, for example when the launching Claude session ends, would send a SIGTERM, which is an operator stop (§11). A `start_new_session` wrapper was not adopted: it would need its own rehearsal against the paid-run token rule, which relies on the Python process being the one that carries `--execute-live`. Round 2, finding 4. **The launching session must outlive the run** (round 3, fix-check FC3): the owner's interactive main session, or a subagent that polls until the manifest is final before it returns and has no step timeout, or one of at least 3 hours; never a workflow step that returns right after the launch. A workflow subagent is its own short-lived `claude` process (round 3 measured the tool shell leading its own process group under that process); whether that process cleans up the group when it exits is unmeasured |

## 3. What is fixed

| item | value |
|---|---|
| harness (this draft, after round 3) | `upgrade_mechanic_probe.py` sha256 `3dacdbeda2c670936e99e41dd50f1c2aade70fdb7b54247f922c9bfd108938a0` (round 2: `613b66bd…`; round 1: `6c24121c…`; round 0: `45314eea…`) |
| plan (this draft, after round 3) | `a04d931938be880365dc3a0261d24ab9d050297520b9f63fef4ef9db505d9a8c` (`artifacts/phase28a-2026-09-25/dry-plan-r3/plan.json`; round 2: `56b16211…` in `dry-plan-r2/`; round 1: `8f753a2c…` in `dry-plan-r1/`; round 0: `e667a13b…` in `dry-plan/`). The 30 requests, their prompts and the draws are byte-identical to rounds 0, 1 and 2; round 2 added the relaunch rule, and round 3 changed only the harness sha |
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

**The configurations the episodes ran on (added in round 1).** Each pool entry in the plan records its
`configuration_hash`, and `plan.pool_configurations` compares the stored configuration records.
- **Phase 20's 11 episodes** (8 `upgrade-3`, 3 healthy) ran on configuration `0a33aa51…` (Phase 20, before the
  Phase 22 freeze), not `2cf63e93…`.
- **The Phase 26 and main-store episodes** (11 `upgrade-3`, 86 healthy) ran on `2cf63e93…`.
- **The two stored configuration records differ only in `algorithm_hash`** (`047a4812…` against `f2f71c59…`) **and
  `runtime_hash`** (`96d3d616…` against `67e6d968…`). The Actor prompt, adapter, interpreter, scorer, contract,
  service and source hashes, the models and the budgets are identical. The impact is expected to be low; it is
  declared difference 5 (§6).

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

Each item gives a **likely direction (unmeasured)**, added in round 3 (fidelity F4), because NO_GO closes Phase 28
for good and the reader needs to know which way the differences plausibly push. The directions are reasoning from
the inputs (checked at $0 on `prompts.jsonl`), not measurements.

1. Every evidence row reads `source: local_only`. A loop's rows read `weave_verified`. The healthy rows are rebuilt
   too, so the label is uniform. *Likely direction:* the Mechanic's system message calls the evidence "verified
   public development evidence", yet all 180 row labels in the 30 contexts read `local_only` (0 read
   `weave_verified`), and `completion.md` explains neither label. Any effect plausibly favours caution
   (`NO_CHANGE`), which points **toward NO_GO**.
2. The six controls come from different campaigns and stores (Phases 20, 26 and 23), not one study's controls, and
   they keep their stored episode ids. *Likely direction:* none expected; the context carries no store, campaign or
   configuration field.
3. The source episodes ran under their own seeds, not 703. `source_fault_spec` shows seed 703, and
   `observed_outcomes` groups trials by `scenario_hash`. So the three source controls carry **3 different scenario
   hashes in 21 contexts and 2 in 9**, where a loop's three share one; none equals `content_hash(source_fault_spec)`.
   The Phase 20/26 healthy episodes also carry their own hash. *Likely direction:* the three uncompleted source
   trials appear as 2–3 groups of 1–2 trials, none under the shown spec's hash, where a loop shows one group of 3
   uncompleted trials under it. That weakens the "the same scenario went uncompleted 3 of 3" signal; if anything
   toward `NO_CHANGE`, so **toward NO_GO**.
4. `campaign_id` and `study_id` follow a declared rule (§5), not a real study. `parent_version` is the loop's value,
   `policy-v0` (§2 row 7). *Likely direction:* none expected; the ids are opaque and loop-shaped.
5. The Phase 20 episodes (8 `upgrade-3`, 3 healthy) ran on configuration `0a33aa51…`, not `2cf63e93…`. The two
   configuration records differ only in `algorithm_hash` and `runtime_hash` (§4). A loop's controls all run on one
   configuration. (Added in round 1, finding 4.) *Likely direction:* low, direction unknown. No configuration,
   algorithm, runtime, contract, scorer or policy hash appears in any context, so this difference reaches the
   Mechanic only through how the episodes behaved.

**The differences with a plausible direction (1 and 3) both lean toward NO_GO, the irreversible result.** A NO_GO
here is therefore a statement about this format, with these labels and these scenario groups (§14).

These are why the probe decides only GO or NO_GO, and why Phase 28 keeps its own futility look.

## 7. The $0 positive controls (any failure refuses the plan)

| control | result (dry plan) |
|---|---|
| bundle rebuild: every main-store Phase 23 controls episode, local rebuild against its stored `weave_verified` bundle, on `episode_id`, `policy_hash`, `contract_hash`, `scorer_hash`, `observations`, `report`, `findings` | **174 of 174 equal**. One controls episode is not eligible evidence and is never used |
| context rebuild: each Phase 23 study with a stored slot-1 input, rebuilt from its own ids, specs and locally rebuilt control bundles | **26 of 26 byte-equal** to the stored input once each row's source label reads `weave_verified` |
| static check against stored behaviour (§8) | **1 informative policy** agrees: the manual reference, `CAN_FIRE` at `after_upgrade_response`, fired 18 of 18. The **2 other policies have no orders re-send, so they cannot disagree**; they are recorded, never counted as validations. The gate needs every row to agree **and** the informative row to be present and firing (round 1 replaced a "3 or more rows" count that the two vacuous rows satisfied). `CAN_FIRE` at `before_final_report`, `CANNOT_FIRE` and `UNCLEAR` are not validated (`plan.positive_controls.auditor_validation_scope`) |
| hook reach on the source path | 19 of 19 pool episodes filed a report; 0 of 19 sent a confirmation |
| source spec | equals the design's mirror; content hash `c4decdb9…` |
| control spec | equals the healthy spec in every Phase 23 manifest |

## 8. The static check: "can fire after a transient upgrade failure" (pitfall 77; descriptive, never decides)

**Its role.** The decision counts **present** re-sends (§9). This check only describes each one: whether, on the
stored source path, it would run, where, and why not. Pitfall 77 is why it is reported: a present step is not a step
that fires.

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

| policy | static | dynamic | informative? |
|---|---|---|---|
| manual reference `b8d18218…` (Phase 26) | `CAN_FIRE` at `after_upgrade_response` | fired in 18 of 18 | **yes**: it validates this one label |
| certified `dd62c857…` (Phase 20) | no orders re-send | fired in 0 of 27 | no: a policy with no re-send cannot disagree |
| certified `711bddb6…` (Phase 26) | no orders re-send | fired in 0 of 18 | no: the same |

**What is validated, and what is not.** One label has a dynamic check: `CAN_FIRE` at `after_upgrade_response`, on
one policy. **`CAN_FIRE` at `before_final_report`, `CANNOT_FIRE` and `UNCLEAR` have no dynamic validation on the
upgrade side.** The only indirect support for the PENDING branch is pitfall 77 on the notification side, through the
same pinned `condition()`. This is acceptable only because the label never decides.

**What the check does not model:** HTTP and tick budgets, and what the Actor would do differently after a policy's
reads or waits. A re-send that fires only at `before_final_report` runs after the Actor has already proposed its
report. It cannot lead to a confirmation, and the report may no longer match the world. It is labelled `CAN_FIRE`
with `fires_at: before_final_report`, and the GO statement names it separately.

## 9. Declared read-outs and the decision (computed by the harness, never re-declared)

**A draw** is one of the 30 contexts. Its output is the first response if that validates; otherwise it is the
format-repair response. Classes (Phase 25's `classify_response`, which applies the study's rules):
- `CANDIDATE`: a valid policy.
- `NO_CHANGE`.
- `INVALID`: fails `MechanicOutput` after the repair; empty or unreadable; a stale parent; or a `CandidatePolicy`
  failure.
- `UNDELIVERED`: the output the loop would use never arrived.

**Not a loop proposal (round 1, finding 3).** An `INVALID` draw whose first output was empty or unreadable, or whose
repair came back empty or unreadable or was refused by the input bound, is one the loop would have recorded as an
infrastructure death, with no proposal (§2 row 8). It stays a delivered draw here, because a generation arrived and
is never re-sent. The read-outs count these draws (`not_a_loop_proposal`, by cause), and every statement says how
many there were.

**The decision** (design §6.0, approved in §19 decision 4; restored in round 1):
- **GO** iff at least one draw is a `CANDIDATE` containing `retry_original_request` with `service: orders`, at any
  hook and under any `when`/`only_if` (the "present" predicate, the same as Phase 28's futility look).
- **NO_GO** iff all 30 draws were delivered and none is. The Wilson 95% upper bound for 0 of 30 is **11.4%**.
- **INCOMPLETE** iff fewer than 30 were delivered and none so far is.
- A `NO_CHANGE` or `INVALID` draw is a draw without the step (the Phase 9 rule).
- The static check's label (`CAN_FIRE`, `CANNOT_FIRE`, `UNCLEAR`), `fires_at` and its reasons **never decide**.

**Pre-fixed wording** (the harness writes it; *e* is the number of draws that are not a loop proposal; every form ends
with the scope sentence):
- GO: "GO: *k* of 30 first proposals (Wilson 95% [*lo*, *hi*]) contain an orders re-send (retry_original_request,
  service orders) at some hook under some gate. Descriptive, from the static check of the declared transient-failure
  path: *f* can fire (*j* at after_upgrade_response, where a re-send can complete the task, and *f − j* only at
  before_final_report, after the Actor has proposed its report), *c* cannot fire and *u* are unclear. *e* of the 30
  draws were empty or unreadable outputs, which the loop would have recorded as an infrastructure death, not a
  proposal. This decides only that the Phase 28 build may start; it does not mean that a re-send works or that the
  loop will certify a repair."
- NO_GO: "NO_GO: none of the 30 draws contains an orders re-send at any hook under any gate (Wilson 95% upper bound
  0.114). *e* of the 30 draws were empty or unreadable outputs, which the loop would have recorded as an
  infrastructure death, not a proposal; over the other 30 − *e* the upper bound is *b*. Phase 28 closes; the backend
  change is not built." (*b* is the Wilson upper bound for 0 of 30 − *e*, or "undefined" when *e* = 30.)
- INCOMPLETE, when a generation may have arrived (round 2): "INCOMPLETE: *d* of 30 draws delivered (*e* of them empty
  or unreadable, which the loop would have recorded as an infrastructure death), none so far with an orders re-send;
  completing the missing draws needs the owner's approval and a separately reviewed harness change (this harness has
  no completion mode)."
- INCOMPLETE, when no generation arrived (round 2, finding 2): "INCOMPLETE: 0 of 30 draws delivered and no generation
  arrived, so nothing was observed. Another launch within the $5 phase cap sends all 30 draws and needs the owner's
  relaunch approval (design §6.0; protocol §11)." "No generation arrived" means: the manifest's delivered count is
  0, no response line shows that a generation may have arrived, and no cut-off line was skipped. The one-run rule
  reads the manifest's count only. The two tests agree on every manifest the harness writes: the running harness
  counts every line that shows a generation, and since round 3 `--finalize-abandoned` also counts a trailing line cut
  off by a hard stop as delivered (round 3, fix-check FC1). Before round 3 it skipped such a line, so a run whose
  first delivered line was cut off could be finalized as "0 delivered" and admitted to a relaunch after part of a
  draw could be read. Where the two tests could differ (a file edited by hand), the statement's test is the
  stricter. So this wording never appears after a run that delivered anything. **It does not check the phase cap**
  (round 3, FC2 and fidelity F1). After the last launch the cap admits (the 5th at ten attempts per run, the 4th at
  twelve, the 41st at one), the wording still appears, but the harness refuses any further launch at $0, even with
  an approval, and names the cap (§11). The phase then ends INCOMPLETE, a hard no-go for Phase 28 (design §18).
- Scope sentence: "Development evidence only, rebuilt locally (every evidence row reads local_only), from episodes
  of several campaigns and stores; one draw per context at temperature 0; contexts share episodes, so the intervals
  understate the uncertainty."

**Descriptive, never deciding:**
- **R_draw** (the design's): draws with an orders re-send (any hook, any gate) ÷ 30. **R_valid:** the same count ÷
  `CANDIDATE` draws. Both with Wilson intervals.
- **R_fire_draw:** draws whose orders re-send the static check labels `CAN_FIRE` ÷ 30. **R_fire_valid:** the same
  count ÷ `CANDIDATE` draws. Both with Wilson intervals. The labels behind them are validated only for `CAN_FIRE` at
  `after_upgrade_response` (§8).
- For each re-send: its label, `fires_at`, reason, hook, `when`, `only_if`, and the number of orders re-send steps.
- NO_CHANGE and INVALID shares (Wilson), with INVALID split by cause, and the draws that are not a loop proposal.
- Format repairs needed and their results.
- Distinct policies (content hash); distinct policies with a present re-send and with a firing one; re-draws of the
  four certified policies.
- The Phase 9 notification step (`run_full_loop.contains_step`); both-sides policies; the Phase 17 attempt-4 pattern
  (a premature defer, Phase 25's audit).
- Per-episode exposure (contexts, draws with a present re-send, draws with a firing one); served model and tokens.

**Uses.**
- The decision only. No tuning: N, the cap, the look, the certification rule and the case set of Phase 28 are fixed
  by its design and do not change with this result.
- No pooling with the loop's S1.
- The result is never shown to any model.

## 10. Operating characteristics ($0; `plan.operating_characteristics`)

P(NO_GO) if all 30 draws are delivered and independent. *s* is the per-draw rate of a **working** upgrade re-send.
The decision counts **present** re-sends, so P(NO_GO) = (1 − *r*)^30, where *r* is the per-draw rate of a present
one. The design's column (§6.0) takes *r* = *s* / 0.75: a present step works 3 times in 4, as in Phases 17 and 23. The
second column takes *r* = *s* (every present re-send works), which gives the largest P(NO_GO) for a given *s*.
Correlated draws make NO_GO **more** likely than both columns say.

| *s* | *r* = *s* / 0.75 | P(NO_GO), design (*r* = *s* / 0.75) | P(NO_GO) if *r* = *s* |
|---:|---:|---:|---:|
| 0 | 0 | 1.000 | 1.000 |
| 0.01 | 0.013 | 0.669 | 0.740 |
| 0.02 | 0.027 | 0.444 | 0.545 |
| 0.03 | 0.040 | 0.294 | 0.401 |
| 0.05 | 0.067 | 0.126 | 0.215 |
| 0.10 | 0.133 | 0.014 | 0.042 |
| 0.15 | 0.200 | 0.001 | 0.008 |
| 0.20 | 0.267 | 0.000 | 0.001 |

At *s* = 0.05 the chance of a NO_GO is about 13% under the design's assumption, and at most about 21%. At *s* = 0.10
it is about 1%, and at most about 4%. (Round 0's stricter "can fire" rule was costed with the second column; round 1
withdrew that rule.) The figures are rounded from the exact values, not from the plan's four-decimal ones; round 0's
table showed 0.445 and 0.546 at *s* = 0.02, a double-rounding slip (exact: 0.44448 and 0.54548).

## 11. Spend cap, bounds, retries and stop rules

- **Planned:** 30 first requests + at most 30 format repairs = 60 calls × $0.04984 = **$2.99**.
- **Hard phase cap $5** = 100 attempts, charged at the bound in whole micro-dollars. Every attempt is charged,
  including blind re-sends. A run that ends having delivered nothing still counts against the phase cap for a later
  run.
- **Every admitted attempt is in the final manifest (round 2, finding 1).** The manifest's counts are normally
  updated when a send returns. When an exception escapes the run while a request is in flight (the cancellation
  that `RuntimeProvider` re-raises from inside the call), round 1 made the manifest final with the counts of the last
  finished send: the attempt in flight, and during a blind re-send the errored first attempt too, were never
  charged, and `--finalize-abandoned` then refused ("already final"). Now, whenever the run ends through the
  harness's own handlers (a normal end, a stop, an `Exception` or a `BaseException`; a hard kill does not, §13 step
  7), `attempts` and `charged_upper_bound` are set to everything the spend guard admitted, and
  `unrecorded_attempts_charged` says how many of those had no count yet (0 on every normal path). The in-flight
  attempt's response line is not written to `responses.jsonl`; it is charged in the manifest only. The same holds
  for an errored first attempt when the exception escapes during the 10 s wait before its blind re-send: a request's
  line is written only after its last attempt, so that attempt has no line either, and it is counted in
  `unrecorded_attempts_charged` (round 3, a fix-check wording note; its test A2). A stop by signal during that wait
  is different: the line is written with its one attempt, and no re-send is sent.
- **Blind re-send (pitfall 49):** one re-send, after 10 s, of an attempt that failed with `CONNECTION_ERROR`,
  `REQUEST_TIMEOUT`, `HTTP_ERROR` or `PROVIDER_ERROR` and shows no sign of a delivered generation. A delivered
  generation is never re-sent.
- **Stops:**
  - the spend guard, which refuses an attempt that would pass the cap;
  - five errored draws in a row, after waits of 30, 120, 300 and 300 s;
  - an operator stop (SIGINT or SIGTERM, whoever sent it), recorded with where it arrived. The call in flight
    finishes (20 s at most); then no repair and no retry is sent, and a draw whose repair was not sent stays
    `UNDELIVERED`, so a stop can never produce a NO_GO. The only sanctioned stop is `kill -TERM <pid>` (§13 step 5);
  - a crash, recorded with its traceback. Since round 1 this includes a cancellation or exit that escapes the run
    (a `BaseException`): the manifest is written `ABORTED` and final, charging every admitted attempt (round 2), then
    the exception goes on.
- **SIGHUP is not handled.** A closed terminal would kill a foreground run outright and leave its manifest `RUNNING`.
  The runbook therefore launches the run detached under `nohup` (§13 step 4), never in the foreground.
- **Any stop after one delivered generation ends the phase for good.** A run that delivered anything is never
  resumed or repeated, and there is no completion mode (§2 row 10); an interrupted run is INCOMPLETE, which design
  §18 treats as a hard no-go for Phase 28 unless the owner approves its completion.
- **One run, and a relaunch only with the owner's approval (round 2, finding 2, option (b); design §6.0).**
  - A second run is refused once any run delivered a generation, or while an earlier run is not final. A trailing
    `responses.jsonl` line cut off by a hard stop counts as a delivered generation when `--finalize-abandoned` closes
    the run (round 3, fix-check FC1), whatever its readable part says, so such a run is never followed by a relaunch.
  - After runs that all **delivered nothing**, the phase is INCOMPLETE, and completing it is the owner's decision
    (design §6.0 and §18). Another launch sends all 30 draws, once, and the harness admits it only with
    `--relaunch-approval artifacts/phase28a-<date>/relaunch-approval-NN.json`: the owner's record with
    `status: "approved"`, a non-empty `approved_by` and `approved_at`, and exactly this launch:
    `earlier_undelivered_runs` as the harness lists them, `out` (the new `--out`), `plan_hash` and `harness_sha256`.
    Without it, the harness refuses before any credential read or claim, and the refusal prints the exact
    `earlier_undelivered_runs` and `out` the record must name. The claim and the manifest record the approval's path,
    sha256, `approved_by` and `approved_at`.
  - One record admits one launch. Once that launch has run, the list of earlier runs has grown, so the record no
    longer matches. With no earlier run, `--relaunch-approval` must be absent.
  - Each such launch is blind, because nothing was observed. Round 1 had allowed them with no approval, a departure
    from design §6.0 that no approver had decided; it is withdrawn.
  - **The phase cap still limits them.** A launch is admitted only while the rest of the $5 covers the 60 planned
    calls ($2.99), so earlier zero-delivery runs may have been charged at most 40 attempts in all. That admits 41
    launches in all at one attempt per earlier run, 21 at two, 5 at ten (the most a finished zero-delivery run can be
    charged: five errored draws, each with a blind re-send) and 4 at twelve (a run closed by `--finalize-abandoned`,
    which adds 2 in-flight attempts). Runs that sent nothing are charged $0 and never use up the cap; the owner's
    approval is then the only limit. Tests pin this
    (`test_the_phase_cap_admits_between_4_and_41_launches_after_runs_that_delivered_nothing`,
    `test_runs_that_sent_nothing_are_charged_nothing_and_never_use_up_the_cap`,
    `test_a_launch_after_runs_that_delivered_nothing_needs_the_owners_relaunch_approval`).
- **Budget** (updated in round 3, fidelity F2). Phase 30 has ended: its manifest
  (`artifacts/phase30-2026-09-25/live/report-narrow-probe-manifest.json`) is `COMPLETED` at 2026-09-25T23:24:38Z
  with `charged_upper_bound` $17.974, carried in the ledger as $17.98. `PHASE30_RESULTS.md` records $670.88
  conservatively charged and **$329.12 remaining** of the shared $1,000, and the ledger
  (`memory/context/runtime-and-evidence.md`) states the same $329.12 remaining (its "Shared total" row still reads
  $652.90, the figure before Phase 30). That covers this phase's $5 cap. The operator reconciles any charge made
  since (§13 step 3) and adds this run's `charged_upper_bound` afterwards.

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
5. This file's status block (the lines before the first `## `) no longer says "NOT yet reviewed" in any case. **A line
   of this file**, with surrounding whitespace removed, is exactly `Reviewed for launch: harness S plan H`: no
   backticks, list marker or bold. The gate checks every line of the file, not only the status block, and an indented
   line counts (Phase 25's rule; corrected in round 1, finding R2-5). The runbook still puts the line in the status
   block (§13 step 2); P and `review.json` bind the exact file either way.
6. `artifacts/phase28a-2026-09-25/review.json` has `status: "approved"`, a non-empty `approved_by`,
   `protocol_sha256` P, `harness_sha256` S, `plan_hash` H, `configuration_hash` `2cf63e93…` and `phase_cap` 5.0.
7. Every request's prompt hashes to its plan entry. After earlier runs that delivered nothing, `--relaunch-approval`
   names the owner's record for exactly this launch; with no earlier run, it must be absent (round 2, §11). The rest
   of the $5 phase cap covers the 60 planned calls.
8. **Only then** does the runtime's own loader read the credentials. The entity must match `--confirm-entity`, the
   project and the Mechanic model must be the declared ones, and the configuration pin is recomputed.
9. The paid-run check runs again. A stop signal that arrived meanwhile refuses. The atomic claim is taken
   (`artifacts/phase28a-live-claims/claim-NN.json`, never deleted); it refuses if the earlier runs changed since item
   7, so a relaunch approval binds this one claim. The paid-run check runs once more after the claim; a blocker then
   ends the run at $0.

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
     `remaining_budget_at_approval` states the reconciled ledger figure of step 3 ($329.12 after Phase 30, unless
     something was charged since).
   - **Rehearse the review gate at $0** (round 3, fidelity F3; Phase 30 did the same): load the harness as a module
     and call `check_review(PROTOCOL.read_text(), sha256_file(PROTOCOL), S, H)`. It must return the record, not raise
     `PlanningError`.
   - **Commit and freeze** (design §9 F11; round 3, fidelity F5). Commit the closed protocol, the harness and its
     tests to `backup/part2-2026-09-22`, as Phase 30 did in `6ed4fa0`, without checking that branch out in this
     working tree (a checkout here could replace the working files with the branch's older copies). `artifacts/` is
     git-ignored and stays local. A commit does not change the files' bytes, so P, S and H still hold; check
     afterwards that `shasum -a 256` still prints P for the protocol and S for the harness. From here until the run
     ends, nothing edits these files. The command (round 4, from the repository root):
     `artifacts/phase22-2026-09-24/prep/commit_to_backup.sh "Phase 28a review closed <date> (protocol <first 8 hex of P>)" docs/part2/PHASE28A_EXPERIMENT.md scripts/experiments/upgrade_mechanic_probe.py backend/tests/experiments/test_upgrade_mechanic_probe.py`.
3. **Before launch,** at $0, right before step 4:
   - Phase 30 has ended, with no run of it live: its manifest is `COMPLETED` (ended 2026-09-25T23:24:38Z, $17.974),
     and its `claim-01` names that run directory. Round 3's guard reading found no blocker (no other open run file,
     no `--execute-live` process, no Phase 28a run or claim; `review-r3/fidelity-lens/guard_reading_r3.out.json`).
     The Phase 28 backend change has **not** landed; the configuration pin enforces this.
   - **Budget** (round 3, fidelity F2): reconcile the ledger (`memory/context/runtime-and-evidence.md`): $329.12
     remaining after Phase 30's $17.974, unless something was charged since. Confirm it covers the $5 cap.
     `review.json`'s `remaining_budget_at_approval` states the same figure.
   - A dry run prints plan hash H.
   - **Power** (round 2, finding 4; the Phase 27 and 30 check): `pmset -g batt` must print
     `Now drawing from 'AC Power'`. Keep the lid open for the whole run. On battery, `caffeinate -s` does nothing
     (Phase 27, R2-L2), and a flat battery or a closed lid after the first generation ends the phase for good. The
     machine was on battery at round 2's review (75%, discharging), on AC power when round 2 was applied
     (`review-r2/fixer/os_stop_checks_r2_fix.out.txt`) and on AC power (100%) at both round-3 reviews
     (`review-r3/*/os_checks_r3.out.txt`); check again at launch.
   - **No stop from the OS** (Phase 25, round 3): `pmset -g sched` lists no shutdown, restart or sleep in the next
     three hours (wakes are harmless), and automatic installation of macOS updates is off
     (`defaults read /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates` prints `0`) or
     the operator has confirmed that no update is pending (`softwareupdate --list`). Both read clean in round 2 and
     again in round 3: wakes only, and `0`.
   - **No other paid run** (rewritten in round 3, fidelity F3; Phase 30's exact checks). This probe calls the
     provider directly and needs neither the simulator nor the lab backend, but:
     - `curl -s http://127.0.0.1:8000/api/config/status` must show `"active_campaign_id":null`. If the connection is
       refused, `lsof -nP -iTCP:8000 -sTCP:LISTEN` must show nothing listening. Any other failure to read it blocks;
       the harness reads the same URL (Phase 25's `backend_status`) and refuses on an active or unreadable status;
     - `ps -ax -o pid,command | grep -- '--execute-live' | grep -v grep` must print nothing. The harness makes its
       own token-based check (§12 item 3). This manual check can also match a shell that only mentions the flag;
       that is not a paid run, but wait until it has ended.
4. **Launch once, detached** (rewritten in round 1, finding R2-1; the Phase 25, 27 and 30 form), on mains power:
   ```
   cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
   nohup caffeinate -is ./.venv/bin/python scripts/experiments/upgrade_mechanic_probe.py --execute-live \
     --confirm-entity <entity> --out artifacts/phase28a-2026-09-25/live \
     --expect-plan-hash H --expect-harness-sha256 S --expect-protocol-sha256 P \
     >> artifacts/phase28a-2026-09-25/live-runner.log 2>&1 &
   echo $!
   ```
   - **A relaunch** (only after runs that all delivered nothing, and only with the owner's approval, §11) uses a new
     `--out` (for example `artifacts/phase28a-2026-09-25/live-2`) and adds
     `--relaunch-approval artifacts/phase28a-2026-09-25/relaunch-approval-NN.json`.
   - **Never in the foreground.** The harness handles SIGINT and SIGTERM, not SIGHUP: a closed terminal would kill
     a foreground run and leave its manifest `RUNNING`. A Ctrl-C, or a foreground tool call that times out, stops
     the run. After one delivered generation, any such interruption makes Phase 28a INCOMPLETE for good (§11).
   - **Claude as the operator** launches it from its own Bash tool shell, exactly as above, never as a foreground
     tool call (§2 row 14 declares this departure from Phase 25's rule). Measured in round 2 with a stand-in launched
     this way: the process survives the tool call's return, ignores SIGHUP, and stops cleanly on `kill -TERM <pid>`.
     It stays in the tool shell's process group and session, though, so **the launching Claude session must stay
     open until the manifest is final.** Ending or closing that session may clean up the process group and send the
     run a SIGTERM. That is an operator stop, whoever sent it (§11), and after one delivered generation it ends the
     phase for good.
   - **The launcher must be a session that will outlive the run** (round 3, fix-check FC3). That means the owner's
     interactive main session, or a subagent that polls until the manifest is final before it returns and has no
     step timeout, or one of at least 3 hours (the worst run lengths below reach about 117 minutes). It must **never** be a
     workflow step that returns right after the launch (`echo $!`): each workflow subagent is its own short-lived
     `claude` process that ends when it returns its result or when a step timeout stops it, and its tool shell leads
     its own process group under that process (`review-r3/fixcheck-reviewer/tool_shell_process_facts.out.txt`;
     whether that process cleans up the group on exit is unmeasured). With this rule, keeping the launching session
     open is the guard (§17, round 3's answer to question 4); no `start_new_session` wrapper is built.
   - **Timing** (corrected in round 2, finding 3). Phase 25's calls came about 2.3 s apart (260 calls in 10.2
     minutes), so 30–60 calls take about 1–2.5 minutes. Five errored draws in a row stop the run after about 17
     minutes of declared waits (30 + 120 + 300 + 300 s of back-off, plus up to 10 attempts of 20 s and 5 blind-retry
     waits of 10 s). **That is not the longest run.** Errors in runs of four never trip the five-in-a-row stop, and
     each run of four pays the whole back-off ladder. When draws 1–4 of every 5 fail on both attempts, the run takes
     about **95 minutes, 54 calls and $2.69** (the reviewer's measurement on the harness's own `run_draws`). With a
     delivered-then-failed pattern it can use all 100 attempts the guard allows and take about **109–117 minutes
     ($4.98)** (`review-r2/fixer/worst_wallclock_r2.out.json`). All of this is inside the declared waits and the
     spend guard. Every one of these lengths is beyond a foreground tool call (2 minutes by default, 10 at most).
   - **Polling: slow is not hung** (round 2, finding 3). Poll every few minutes with `ps -p <pid> -o pid=,etime=`
     and by reading the manifest (`artifacts/phase28a-2026-09-25/live/upgrade-mechanic-probe-manifest.json`) until
     its status is final.
     - The run is alive while its pid exists and the manifest's `last_request`, `backoff_waits` or `attempts` keep
       changing. The longest the harness can go without saving the manifest is about **350 s**: a 300 s back-off,
       then a 20 s timeout, the 10 s blind-retry wait and a second 20 s timeout (measured,
       `review-r2/fixer/worst_wallclock_r2.out.json`).
     - **Never stop the run for being slow**, however long it takes.
     - If the pid exists and the manifest has not changed for more than 15 minutes, no declared path explains it.
       Write down what `ps` and the log show and tell the owner. Do not stop it on your own.
     - `kill -TERM` is only for a real reason: the owner's decision, or a paid-run conflict the harness cannot see.
       After any delivered generation it ends the phase for good (INCOMPLETE, a hard no-go for Phase 28 in design
       §18).
   - **The process id** is what `echo $!` prints: the Python process (under `nohup caffeinate -is`, `caffeinate` is
     its child, as Phases 25, 27 and 30 and this phase's round 2 measured). The claim records it as well.
   - **The log** is appended to, and it sits outside the output directory, which must not exist beforehand.
5. **To stop:** only `kill -TERM <pid>`, with the pid from step 4, and only for a real reason (step 4's polling
   rule; never for slowness). Never Ctrl-C and never a foreground tool call. Use `kill -9` only if the process has
   ignored SIGTERM for more than a minute; after a hard kill, close the claim with `--finalize-abandoned` (step 7)
   before anything else.
6. **After.**
   - `--readouts artifacts/phase28a-2026-09-25/live` reproduces `readouts.json`.
   - Add `charged_upper_bound` to the ledger.
   - Write `PHASE28A_RESULTS.md` with the statement, the §9 descriptive figures and every limit in §15.
   - On GO, the Phase 28 build may start (design §9 step 2). On NO_GO, Phase 28 closes.
7. **If the process dies.**
   - `--finalize-abandoned artifacts/phase28a-live-claims/claim-NN.json` closes it at $0 and charges what was
     recorded, plus 2 attempts that may have been in flight. It refuses a manifest that is already final; since round
     2, a final manifest already charges every attempt the guard admitted (§11).
   - **If `--finalize-abandoned` prints a traceback** instead of its FINALIZED or REJECTED line (round 4: a hard stop
     that cuts a line inside a multi-byte UTF-8 character raises a raw `UnicodeDecodeError`), treat the run as
     delivered, never relaunch, and tell the owner. The manifest stays `RUNNING`, so every later launch is refused
     (it fails closed).
   - A trailing `responses.jsonl` line cut off by the hard stop counts as a delivered generation (round 3, fix-check
     FC1). The finalized manifest then shows `finalized_abandoned.partial_lines_skipped` above 0 and
     `generations_delivered` of at least 1, and the harness refuses any relaunch. The owner must not approve one
     either: part of a draw may already have been read.
   - An INCOMPLETE run that delivered anything is completed only with the owner's approval and a separately reviewed
     change (§2 row 10).
   - After runs that all delivered nothing, another launch needs the owner's relaunch approval for exactly that launch
     (§11, §2 row 13). The record states the owner's decision; nobody writes it without one. A launch without it is
     refused at $0, and the refusal prints the earlier runs and the `out` the record must name.

## 14. What each result would and would not mean

- **GO.**
  - *Would mean:* the Mechanic sometimes writes an upgrade re-send, at some hook under some gate, when shown
    upgrade-side evidence in this format.
  - *Would not mean:* that the re-send can fire (read the labels: a PENDING-gated re-send cannot, pitfall 77, and only
    one label is validated, §8); that it completes the task (read `fires_at`: a `before_final_report` re-send
    cannot); that the loop will certify a repair; that it is safe; anything about held-out cases. Phase 28's own
    futility look and its gates remain the check.
- **NO_GO.**
  - *Would mean:* none of 30 draws in this format contains any orders re-send (upper bound 11.4%, and wider in truth
    because the draws are correlated; read how many draws were empty or unreadable and would not have been loop
    proposals). Phase 28 closes, and no backend change is made.
  - *Would not mean:* that the Mechanic cannot with another brief, temperature or model, or with `weave_verified`
    rows, or with one study's controls under one scenario hash. The two input differences with a plausible
    direction both lean toward NO_GO (§6).
- **INCOMPLETE.** Not a finding about the Mechanic. After runs that delivered nothing, the owner may approve one more
  launch at a time (§11), while the rest of the $5 covers the 60 planned calls; after a run that delivered anything
  (a cut-off response line counts, §11), completion needs the owner's approval and a separately reviewed harness
  change (§2 row 10). Otherwise it is a hard no-go for Phase 28 (design §18).
- **Never:** ACCEPTED, certified, a policy, or a change to anything. The probe creates no campaign, study, trial,
  world, policy or store row.

## 15. Limits

- The inputs differ from a loop's in five declared ways (§6). Their effect is unmeasured; the two with a plausible
  direction (the `local_only` labels and the split scenario hashes) both lean toward NO_GO.
- Only 19 source episodes exist. They fill 90 slots, so the 30 draws are correlated.
- One draw per context at temperature 0. Temperature 0 is not deterministic (Phase 21: 36% of repeat pairs were
  byte-identical), so a re-run would differ. That is why there is one run.
- Slot 1 only. Slot 2, the source gate and validation are not modelled.
- GO counts a **present** re-send, including one that cannot fire (PENDING-gated), one that is unclear (only at a hook
  the source path never reaches) and one that fires only at `before_final_report` and cannot complete the task. The
  statement names each kind; Phase 28's futility look uses the same predicate.
- The static check is abstract (§8) and descriptive. Only `CAN_FIRE` at `after_upgrade_response` is checked against
  stored behaviour, on one policy.
- Empty or unreadable outputs are counted as delivered draws, although the loop would have recorded no proposal
  (§2 row 8). Each statement gives their number.
- The brief (`completion.md`), the model and the settings are the loop's. The result speaks only to them.
- Development data only. No held-out partition is read, and none can follow for Phase 28 (design §10, decision 7).
- When an exception escapes the run while a request is in flight, that attempt is charged in the manifest but has no
  line in `responses.jsonl` (§11). Nothing it might have returned was observed. The same holds for an errored first
  attempt whose blind-retry wait the exception interrupted (§11).

## 16. What must not happen

- No edit under `backend/app`, to the pinned harnesses, to `completion.md`, to the settings or to the gate. The
  scorer is never opened.
- No `private_*` record, no heldout-2 file, no promotion or final-audit partition, and no `.env` read by the dry
  plan.
- No second run once a run delivered anything (a cut-off response line counts); no relaunch after runs that
  delivered nothing without the owner's relaunch approval for exactly that launch; no re-send of a delivered
  generation; no re-declared read-out; no change to Phase 28's N, cap, look, certification rule or case set after
  this result.
- No launch from a session that may end before the run does (§13 step 4).
- No stop of a live run for being slow (§13 step 4).
- No result shown to any model or entered into a study; nothing called ACCEPTED.
- No launch beside another paid run, or after the Phase 28 backend change lands.

## 17. Questions for the review

Round 1 answered round 0's questions 1–3: the decision is the design's "present" predicate, as the approver took it
(design §19 decision 4), and `before_final_report` and `UNCLEAR` re-sends count toward GO like any present re-send,
with their labels reported (Review log, finding 1). A stricter rule would need an explicit approver decision recorded
in `review.json` and this Review log before the review closes, a coherent definition (only `after_upgrade_response`
`CAN_FIRE`) and a recomputed §10 table.

Round 2 answered round 1's questions (Review log, round 2):
- question 1 (the restored rule): sound, as implemented and tested;
- question 3 (zero-delivery launches with no approval): not acceptable without an approver record. Option (b) was
  taken: a relaunch needs the owner's approval (§2 row 13, §11);
- question 4 (the `BaseException` handler): it kept every ended run final, but under-charged an attempt in flight
  (finding 1, fixed);
- questions 2, 5, 6 and 7 drew no finding; the current answers stand (§2 rows 8 and 10, §4).

For round 3 (round 2 changed the harness, pitfall 74):
1. **The in-flight charge** (§11). Does the final manifest now charge every attempt the spend guard admitted on every
   path that ends the run (normal end, stop, `Exception`, `BaseException`), with `unrecorded_attempts_charged` 0 on
   every normal path, and does `--finalize-abandoned` still add its 2 in-flight attempts only to a manifest that is
   not final?
2. **The relaunch gate** (`RELAUNCH_RULE`, `check_relaunch_approval`, §11, §12 item 7). Is it bound tightly enough
   (the earlier runs, `--out`, plan hash, harness sha; re-checked at the claim), placed before any credential read
   or claim, and refused when passed with no earlier run? Is "once" rightly read as one launch per approval?
3. **The two INCOMPLETE statements** (§9). Is "no generation arrived" exactly the one-run rule's test (the
   manifest's count, every line, and cut-off lines), so the relaunch wording never appears after a run the harness
   refuses to follow?
4. **The launch from Claude's tool shell** (§2 row 14, §13 step 4). Is keeping the launching session open an
   adequate guard against a process-group cleanup, or should a `start_new_session` wrapper be built and rehearsed
   against the paid-run token rule?
5. **The poll rule** (§13 step 4). Is 350 s the true longest gap between manifest saves, and is "more than 15
   minutes unchanged: tell the owner, never stop on your own" the right threshold and action?

Round 3 answered round 2's questions (Review log, round 3):
- question 1 (the in-flight charge): sound on every path tried (cancellation during the blind-retry wait, during a
  back-off, during a format repair, while the provider closes; `SystemExit` and `KeyboardInterrupt` in flight;
  every normal ending), and `--finalize-abandoned` still adds its 2 attempts only to a manifest that is not final;
- question 2 (the relaunch gate): sound (order of the earlier runs, the spelling of `out`, a symlinked record, one
  record per launch, a run that ends between the check and the claim, the check before the credential read);
- question 3 (the two INCOMPLETE statements): **not exactly**. A trailing line cut off by a hard stop was not counted
  by `--finalize-abandoned` (finding FC1, fixed in the harness), and the relaunch wording does not check the phase
  cap (FC2 and F1, text);
- question 4 (the launch from Claude's tool shell): adequate, with the added rule that the launcher must be a session
  that outlives the run (FC3, text); no `start_new_session` wrapper;
- question 5 (the poll rule): 350 s reproduced as the longest gap between manifest saves, and 95–117 minutes as the
  worst run lengths; the 15-minute threshold has room.

For round 4 (round 3 changed the harness, pitfall 74):
1. **The cut-off line** (§9, §11, §13 step 7). Does `--finalize-abandoned` now count a trailing line cut off by a
   hard stop as a delivered generation, so that the one-run rule refuses a relaunch and the statement and the rule
   agree? Is counting such a line as delivered whatever its readable part says (an errored line too, the
   conservative side) acceptable?
2. **The harness diff** (`review-r3/fixer/harness_r2_vs_r3.diff`). Is `finalize_abandoned` the only function whose
   code changed (the rest is docstrings and comments), with the requests, draws and `prompts.jsonl` byte-identical?
3. **The text-only changes**: §6's likely directions, §9's corrected account of the relaunch wording, §11's budget,
   §13 steps 2–4 (the gate rehearsal, the commit, the ledger, the backend and process checks, the launcher that
   outlives the run), §2 rows 7 and 14. Accurate and sufficient?

## 18. Evidence files (all $0)

- `artifacts/phase28a-2026-09-25/dry-plan-r3/`: **the current plan** after round 3: `plan.json` (the hashed plan:
  pins, pools with their configurations, `pool_configurations`, exclusions, positive controls with
  `auditor_validation_scope`, draws, requests, rules including `relaunch_rule`), `dry-summary.json`,
  `prompts.jsonl` (the 30 exact message lists, `807a141c…`, byte-identical to rounds 0, 1 and 2).
- `artifacts/phase28a-2026-09-25/dry-plan-r3-stdout.txt`: that dry run's output.
- `artifacts/phase28a-2026-09-25/dry-plan-r3-check-stdout.txt`: a plain dry run after the last edit of round 3, which
  must print plan hash H.
- `artifacts/phase28a-2026-09-25/dry-plan-r2/`, `dry-plan-r2-stdout.txt` and `dry-plan-r2-check-stdout.txt`: round
  2's plan (`56b16211…`), kept. `dry-plan-r1/` and its two stdout files: round 1's plan (`8f753a2c…`), kept.
  `dry-plan/` and `dry-plan-stdout.txt`: round 0's plan (`e667a13b…`), kept.
- `artifacts/phase28a-2026-09-25/prep/`: the pre-build checks with their outputs, and labelled copies of the
  design's scratch (see its `README.md`).
- `artifacts/phase28a-2026-09-25/review-r1/`, `review-r2/` and `review-r3/`: each round's evidence, from the
  reviewers' and the fixers' scratch (see each `README.md`).
- `artifacts/phase28a-2026-09-25/tests-upgrade_mechanic_probe-r3.txt`: the test run after the last edit of round 3.
  `tests-upgrade_mechanic_probe-r2.txt` (round 2, 74 passed), `tests-upgrade_mechanic_probe-r1.txt` (round 1, 67
  passed) and `tests-upgrade_mechanic_probe.txt` (round 0, 48 passed) are kept.
- Not yet written: `review.json` (the approver writes it at §13 step 2) and the live run folder.

## Review log

### Review log — round 1 (2026-09-25, $0)

**Lenses.** Two reviewers, working read-only: statistics and design (§1, §2, §8–§10, the tests of the decision), and
run safety and launch (§11–§13, the live loop, the claims, the stop paths). Both returned **RUN_WITH_CHANGES**, with 9
findings: 2 major and 7 minor. Neither edited a repository file, opened `.env`, `checks.py`, heldout-2, promotion or
final-audit files, or made a provider, model or W&B call. Their scratch is copied, labelled, to
`artifacts/phase28a-2026-09-25/review-r1/`.

**What both found sound** (not repeated below): the request is the loop's slot-1 request; the positive controls (174
of 174 bundles, 26 of 26 contexts); the messages and the format repair; the request digest check; the classification;
the four declared input differences in `prompts.jsonl`; the source-path premise (150 UNKNOWN reads and 0 PENDING in
the 30 contexts' results tables); the static check's logic; the populations, re-derived by an independent stdlib
script; no stop at success; the OC arithmetic; the spend cap (100 attempts under $5; the worst case of 120 attempts is
stopped by the guard); the live-gate order; one run and no resume; the interruption handling; the other-paid-run
guard. **No reviewer claim proved wrong**: every finding below was checked against the code or the store and held.

**Every finding and its disposition:**

| # | severity | finding | disposition |
|---|---|---|---|
| 1 | **major** | **The GO/NO_GO predicate was not the approved one.** Design §6.0, approved in §19 decision 4, decides GO on the "present" predicate (an orders re-send at any hook under any gate), the same as Phase 28's futility look; the "can fire" label is descriptive. Round 0 decided on `CAN_FIRE`, citing the build brief, not an approver decision. The rule was also incoherent: it excluded PENDING-gated and `before_confirmation` re-sends but counted a `before_final_report`-only one, which cannot complete the task. It redefined the design's `R_draw`, so 28a's headline no longer matched the loop's S1u/R. Because NO_GO is irreversible, it could close Phase 28 where the approved rule says GO. Evidence: the harness's own `compute_readouts` on 30 synthetic draws gave NO_GO for a PENDING-gated and for a `before_confirmation` re-send, and GO for a `before_final_report`-only one; round 0's test asserted NO_GO with 15 present PENDING-gated re-sends; §10 put P(NO_GO) at 0.215 against 0.126 at *s* = 0.05 | **Applied: the approved rule is restored.** `DECISION_RULE` and `decide()` now use the present predicate; `CAN_FIRE`, `fires_at`, `UNCLEAR` and the reasons are descriptive. `R_draw` and `R_valid` are the design's (present ÷ 30, ÷ `CANDIDATE`); the firing rates are the separate, descriptive `R_fire_draw` and `R_fire_valid`. The GO statement gives the present count with its interval, then the labels (*f* can fire, split by hook; *c* cannot; *u* unclear); NO_GO says "none of the 30 draws contains an orders re-send at any hook under any gate". Updated: the harness docstring, `readout_rules`, `operating_characteristics` (now the design's column plus the *r* = *s* upper case), §1, §2 row 2, §8, §9, §10, §14, §15, §17. **No stricter rule was adopted**, so none needs an approver record. Tests: the NO_GO case now uses policies with no orders re-send; `test_any_present_orders_re_send_is_go_whatever_its_label` replays the reviewer's three cases (PENDING-gated, `before_confirmation`, `before_final_report`-only), each GO with its label reported; the classification test checks `R_draw` 3 and `R_fire_draw` 2. **Mutation check** (`review-r1/fixer/mutation_check.out.txt`): round 0's `decide()` fails the new test for the PENDING-gated and `UNCLEAR` cases; it passes the `CAN_FIRE` case, where both rules agree. The reviewer's own demonstration, re-run on the round-1 harness, gives GO for all three (`review-r1/fixer/decide_demo_r1.out.txt`) |
| 2 | minor | **"3 of 3 agree" overstated the static check's validation.** Two of the three stored policies (`dd62c857…`, `711bddb6…`) have no orders re-send, so their rows "agree" whenever the policy never re-sent, which cannot fail. Only the manual reference tests a label, and only `CAN_FIRE` at `after_upgrade_response`. `positive_controls_pass`'s "3 or more rows" count was met only because of the two vacuous rows | **Applied.** §2 row 5, §7 and §8 now say: 1 informative policy (`CAN_FIRE` at `after_upgrade_response`, fired 18 of 18); 2 policies with no orders re-send, which cannot disagree; `CAN_FIRE` at `before_final_report`, `CANNOT_FIRE` and `UNCLEAR` are not validated. Each validation row now carries `informative`, and the plan records `auditor_validation_scope` (policies, informative policies, labels validated and not validated). `positive_controls_pass` no longer counts rows: it needs every row to agree **and** an informative row with `CAN_FIRE` at `after_upgrade_response` that fired. Three new refusal cases (no informative row; the informative row never fired; its label moved) are tests; round 0's count fails two of them (`mutation_check.out.txt`). Because the label is now descriptive (finding 1), this is a wording and record fix, not a change to what decides |
| 3 | minor | **Empty or unreadable outputs counted as delivered INVALID draws** (an empty or unreadable first output; a repair that is empty, unreadable or refused by `INPUT_LIMIT`/`REQUEST_LIMIT`), justified as "fidelity to `Mechanic._generate`". In the loop `_generate` re-raises (`mechanic.py:28-31`; `tokens.py:86-89`), the study goes to `_execute`'s handler, becomes INCOMPLETE and records no candidate attempt (`completion_study.py:449-457`): an infrastructure death, not a draw (design §7.2). The probe therefore moves such runs from INCOMPLETE to NO_GO; it cannot make a false GO | **Applied, the reviewer's second option.** The Phase 25 convention stays: a generation arrived, so under the design's INCOMPLETE rule the draw is delivered, and it can never be re-sent (pitfall 49). Treating it as "not a draw" would turn one empty reply into an INCOMPLETE that only a re-send of a delivered answer could complete. §2 row 8's justification is corrected: the loop would record no proposal. Each draw now carries `not_a_loop_proposal` (`first_empty`, `first_unreadable`, `repair_empty`, `repair_unreadable`, `repair_input_limit`); the read-outs count them by cause; **every statement says how many of the 30 they were**, and NO_GO also gives the upper bound over the other 30 − *e*. §9, §14 and §15 say so. Tests: the classification test (empty first output, unreadable first output) and `test_an_empty_or_unreadable_or_refused_repair_is_counted_as_not_a_loop_proposal` |
| 4 | minor | **Phase 20's episodes ran on another configuration, undeclared.** 8 of the 19 source episodes and 3 healthy ones ran on `0a33aa51…` (Phase 20, before the Phase 22 freeze), not `2cf63e93…`; the pool entries did not record a configuration. The reviewer's read-only comparison found the two stored records identical except `algorithm_hash` (`047a4812…` against `f2f71c59…`) and `runtime_hash` (`96d3d616…` against `67e6d968…`), so the impact is low | **Applied.** Re-checked independently at $0 (read-only, `immutable=1`): the only differing fields are `algorithm_hash` and `runtime_hash`. Every pool entry now records `configuration_hash`, and the plan carries `pool_configurations`, computed from the stored records: `0a33aa51…` 8 `upgrade-3` + 3 healthy, all Phase 20, differing in exactly those two fields; `2cf63e93…` 11 + 86, none differing. §4 and §6 (declared difference 5) say so, and the plan's `declared_input_differences` has the same line. A test pins all of it |
| R2-1 | **major** | **The runbook launched the probe in the foreground**, with no `nohup`, where Phases 25 and 27 used `nohup`. The harness handles SIGINT and SIGTERM only, so a closed terminal (SIGHUP) kills it and leaves the manifest RUNNING, and a Ctrl-C or a foreground tool-call timeout stops it. After one delivered generation, any interruption makes Phase 28a INCOMPLETE for good (no completion mode; design §18's hard no-go). The run takes about 1–2.5 minutes with no errors and up to about 17 minutes with the declared waits, beyond a foreground tool call's limits. The reviewer's scratch test E2 (SIGINT during the first call) gave STOPPED, INCOMPLETE, and a refused second launch | **Applied, text only (no harness change needed).** §13 step 4 is rewritten in the Phase 27/30 form: `nohup caffeinate -is ./.venv/bin/python … >> artifacts/phase28a-2026-09-25/live-runner.log 2>&1 &`, then `echo $!` (the Python process). It says never to launch in the foreground, and that a Claude operator launches it detached and polls the manifest. The new step 5 makes `kill -TERM <pid>` the only sanctioned stop, never Ctrl-C or a foreground tool call. §11 states that SIGHUP is not handled, and that any stop after one delivered generation ends the phase |
| R2-2 | minor | **No test covered an interruption after the claim.** The `_run` helper's `stop` argument was never used. Unpinned: a stop between an invalid first output and its repair must leave the draw UNDELIVERED, never INVALID (else a stop could make a NO_GO); a stop during the blind-retry wait; a real SIGINT during a provider call. The code was already correct (reviewer's E1b, E1c, E2) | **Applied: E1b, E1c and E2 are tests** (`test_a_stop_between_an_invalid_first_output_and_its_repair_leaves_the_draw_undelivered`, `test_a_stop_during_the_blind_retry_wait_sends_no_retry`, `test_a_sigint_during_a_provider_call_stops_the_run_and_the_one_run_rule_holds`). Fakes only, $0 |
| R2-3 | minor | **Several fail-closed paths were unpinned:** the crash path (ABORTED with a traceback, the one-run rule holding); a `BaseException` escaping the run, which left the manifest `RUNNING` with `ended_at` set, so `--finalize-abandoned` then charged 2 in-flight attempts never sent; refusing an existing `--out` (the only guard against a resume); the atomic-claim race; the gates after the credential read (entity, project, configuration pin). The reviewer suggested also catching `BaseException` in `run_live` in a later reviewed revision | **Applied, tests and the suggested harness fix.** Tests: E3 (`test_a_crash_after_a_delivery_is_aborted_final_and_ends_the_phase`), E4 (`test_a_base_exception_escaping_the_run_is_recorded_aborted_and_final`), E7 (`test_an_existing_output_is_never_resumed_and_a_racing_claim_is_refused`) and E10 (`test_the_gates_after_the_credential_read_refuse_without_claiming`, four cases: entity, project, configuration hash and, added here, the Mechanic model). **Harness:** because round 1 changes the harness anyway and round 2 reviews it, `run_live`'s inner handler now also catches `BaseException`: it writes `ABORTED` with the traceback, the `finally` block makes the manifest final, and the exception is re-raised. The E4 test shows the manifest final, the handlers restored, a second launch refused ("repeat-until-lucky", one generation was delivered) and `--finalize-abandoned` refusing ("already final"). Round 2 question 4 asks for this to be checked |
| R2-4 | minor | **§11's "may be followed by one more" did not match the code.** The harness allows zero-delivery reruns with no approval until the $5 phase cap can no longer cover the 60 planned calls; the reviewer's E5 allowed 5 and refused the 6th ($2.51 left). Design §6.0 says completing an INCOMPLETE run needs approval and happens once. No selection risk (nothing observed) and total spend stays at or below $5, but after about 5 failed launches the phase can never run | **Applied, the reviewer's first option: the text now states what the code does.** §11 and a new §2 row 13 declare it as a departure from design §6.0: each further zero-delivery launch is blind, needs no approval, and is allowed while the remaining cap covers $2.99; at the worst charge five fit, then the phase ends INCOMPLETE. A test pins the count (`test_runs_that_delivered_nothing_may_follow_within_the_phase_cap_until_it_cannot_cover_the_plan`). Round 2 question 3 asks whether the departure is acceptable |
| R2-5 | minor | **§12 item 5 said the bare line must be in the status block, but the gate accepts it on any line**, stripped (so an indented, code-block line also counts). The test fixture relies on that: it puts the line under `## Pins`. Low risk, since P and `review.json` bind the exact file | **Applied, text only** (the reviewer's first option, and Phase 25's rule, which the code copies). §12 item 5 now says "a line of this file, with surrounding whitespace removed", checked over every line, an indented line included. §13 step 2 still puts the line in the status block |

**Found while applying round 1 (not a reviewer finding).** Round 0's §10 table showed 0.445 and 0.546 at *s* = 0.02,
rounded from the plan's four-decimal values; the exact values are 0.44448 and 0.54548, so 0.444 and 0.545. Corrected
in §10. No decision or rule depends on these figures.

**What round 1 changed, and the new pins.**
- **Harness** (`upgrade_mechanic_probe.py`): `45314eea…` → **`6c24121cc3062147a3f35e5d1003e72beba12adc316a9e88581fd8ef93043a17`**.
  Changed: the decision (finding 1), the static-check records and the positive-control gate (2), the
  `not_a_loop_proposal` count and statements (3), the configuration records (4), the `BaseException` handler (R2-3),
  and the docstrings and rules that describe them.
- **Plan:** `e667a13b…` → **`8f753a2c3c355ed9d4ff995f4c515adb7ec2eece74a75d77f502a1c24e7abb74`**
  (`dry-plan-r1/`). The 30 requests, the prompts and the draws are byte-identical to round 0's
  (`review-r1/fixer/plan_r0_vs_r1.out.txt`); the plan differs only in the rules, the static-check records, the
  configuration fields and the harness sha.
- **Tests** (`test_upgrade_mechanic_probe.py`): 48 → **67**, all passing after the last edit
  (`tests-upgrade_mechanic_probe-r1.txt`). The new tests are named above.
- **Protocol:** this file (its sha is taken only when the review closes, §13 step 2).
- Unchanged: `slot2_probe.py` (`28b998ac…`), `run_full_loop.py` (`07dcaa93…`), everything under `backend/app`, the
  configuration pin `2cf63e93…`.

**Next.** Round 1 changed the harness, so **round 2 must run** on the changed code (pitfall 74), with the questions in
§17. The review is not closed; no `review.json` exists.

### Review log — round 2 (2026-09-25, $0)

**Lens.** One reviewer, working read-only (scratch `p28a-r2-broke-launch`), on the round-1 harness `6c24121c…`,
protocol `00716a2a…` and tests `5f56ef19…`. Verdict **RUN_WITH_CHANGES**, with 4 minor findings. It edited no
repository file, opened none of `.env`, `checks.py`, heldout-2, promotion or final-audit files, passed no
`--execute-live`, and made no provider, model or W&B call. Its scratch is copied, labelled, to
`artifacts/phase28a-2026-09-25/review-r2/reviewer/`.

**What it found sound** (not repeated below):
- **Pins:** unchanged through the review. A plain dry run printed plan `8f753a2c…`, harness `6c24121c…` and
  configuration `2cf63e93…`. `slot2_probe.py` `28b998ac…`, `run_full_loop.py` `07dcaa93…`.
- **Tests:** 67 passed (69 with its 2 scratch tests).
- **The restored rule (round 1's question 1):**
  - `decide()` and `compute_readouts` implement design §6.0's "present" predicate;
  - `ServiceStep.service` is required, so the `service == 'orders'` test cannot miss a re-send;
  - `propose_completion` validates only `MechanicOutput`, so the harness's repair trigger matches the loop's;
  - the new tests are substantive;
  - NO_GO with *e* = 30 prints "undefined", as declared.
- **Numbers:** §10's table was recomputed by hand, and every row matches; the 0-of-30 upper bound is 0.1135. §4 and
  §7 match `dry-plan-r1`. `prompts.jsonl` is byte-identical between rounds 0 and 1.
- **Closure and live-gate rehearsal:** a scratch copy of this file, closed as §13 step 2 says, passed every offline
  gate of the real `run_live` up to a stand-in for the credential read, with nothing claimed or created. Eleven
  closure mistakes were each refused. An indented line is accepted, as §12 item 5 declares. The status block holds
  exactly one "NOT yet reviewed".
- **Guard reading on the real machine** at review time: no blockers, backend idle, no Phase 28a run or claim, no
  `review.json`, and no Phase 30 run or claim yet.
- **Signals:** round 1's `BaseException` handler changes no signal path; the harness's own SIGINT and SIGTERM
  handlers stay in charge (Python 3.12's `asyncio.run` installs its SIGINT handler only over the default one). The
  real-SIGINT test E2 passes. The only defect it found there is finding 1.
- **Round 0 copy:** commit `6dbcb82`'s harness copy is a mid-fix snapshot (one docstring from round 1), so the
  reviewer reviewed the current code directly.

**Who applied it.** Two sessions. A first fixer session (scratch `p28a-r2-fix`) made the harness and test changes
for findings 1 and 2 and ran the wall-clock and mutation scripts. It stopped before editing this file: its last
write was at 15:12 local time, and the second session began at 15:55. Its edits were left on disk (harness
`641fd319…`, tests `da0b11a6…`). The second session (scratch `p28a-r2-apply`) checked each of those edits against the
finding texts and the code, and kept them. It then added one consistency change and fixed one non-hermetic test
(below), wrote this file's changes, the new plan and the evidence, and ran every check after the last edit. Both
sessions' scratch is copied to `review-r2/fixer/`.

**Every finding and its disposition:**

| # | severity | finding | disposition |
|---|---|---|---|
| 1 | minor | **Round 1's `BaseException` handler under-charged an attempt in flight.** The manifest's `attempts` and `charged_upper_bound` are updated only after `provider.complete` returns, and `RuntimeProvider` re-raises `asyncio.CancelledError` from inside the call. A cancellation there made the manifest final (ABORTED) with the counts of the last finished send, so the admitted and sent attempt was never charged, and `--finalize-abandoned` then refused ("already final"). Before round 1, that manifest stayed non-final and finalize added 2 in-flight attempts. A zero-delivery run aborted this way was charged $0, so the next launch got the whole $5 cap again. Test E4 missed it because it raised the cancellation after the send's counts were saved. Evidence: cancelled during r0001's first call, attempts 0, $0; cancelled during r0002's blind re-send, attempts 1 of 3 sent | **Applied, as proposed.** `run_live`'s `finally` block now sets `attempts` to the larger of the recorded count and `guard.attempts`, and `charged_upper_bound` to `guard.charged`, before the last save. It also records `unrecorded_attempts_charged`, which is 0 on every normal path (each finished send already copies the guard's count). The optional part, writing the in-flight attempt's partial line, was not taken: the attempt is charged in the manifest only (§11, §15). **Test:** `test_a_cancellation_while_a_request_is_in_flight_charges_every_admitted_attempt`, the reviewer's two cases, with `FakeOpenAI.create` raising `asyncio.CancelledError` while the request is in flight. Case 1: attempts 1, $0.04984, 1 unrecorded. Case 2: attempts 3, $0.14952, 2 unrecorded, 1 delivered. `--finalize-abandoned` refuses both, which is now correct. E4 also asserts 0 unrecorded. **The reviewer's own scratch test,** re-run on the round-2 harness, now prints attempts 1 and 3 and fails its round-1 assertions, as it should (`review-r2/fixer/reviewer_inflight_on_r2_harness.out.txt`). Mutant M1 (round 1's `finally` block) fails both cases |
| 2 | minor | **Zero-delivery relaunches with no approval were a builder's departure from the approved design, with no approver record.** Round 1's own finding-1 disposition says such a departure needs an explicit approver decision. The harness also contradicted §2 row 13: for a run that delivered nothing, its INCOMPLETE statement said "completing the missing draws needs the owner's approval". And row 13's "five such runs fit" was only the fewest the cap allows: 41 at one charged attempt per run, and no limit at all at the $0 charge finding 1 produced. The reviewer offered (a) keep row 13 with an approver decision and a branched statement, or (b) require an explicit approval argument for any relaunch, as design §6.0 says | **Applied, option (b).** It restores design §6.0 in the harness, so there is no departure left to approve; option (a) would have needed an approver decision in `review.json`, which only the approver writes. **Harness:** `RELAUNCH_RULE` (in the plan as `relaunch_rule`) and `check_relaunch_approval`. After runs that all delivered nothing, a launch needs `--relaunch-approval` naming `artifacts/phase28a-<date>/relaunch-approval-NN.json`: status approved, `approved_by`, `approved_at`, and exactly this launch (the earlier runs as the harness lists them, `out`, plan hash, harness sha). It is checked before any credential read or claim, and the claim re-checks the earlier runs, so one record admits one launch. With no earlier run, the argument must be absent. The claim and the manifest record the approval's path, sha256, approver and time (§2 row 13, §11, §12 items 7 and 9). **Statements:** INCOMPLETE has two forms (§9). When no generation arrived, it says another launch needs the owner's relaunch approval. Otherwise it says completion needs the owner's approval and a separately reviewed harness change. The read-outs carry `any_generation_arrived`. **Arithmetic:** 4 to 41 launches in all fit the cap. That is the reviewer's 5 to 41, plus 4 when earlier runs were closed by `--finalize-abandoned` with its 2 in-flight attempts (12 attempts; the reviewer's own table has this row). Runs that sent nothing are charged $0 and never use up the cap; the owner's approval is then the only limit (§11). **Tests:** `test_a_launch_after_runs_that_delivered_nothing_needs_the_owners_relaunch_approval` (the refusals, the record's place, a matching record reaching the credential read with nothing claimed, and the same record refused after one more run); `test_the_phase_cap_admits_between_4_and_41_launches_after_runs_that_delivered_nothing` (12, 10, 2 and 1 attempts per run: 4, 5, 21 and 41 launches), which replaces round 1's `test_runs_that_delivered_nothing_may_follow_within_the_phase_cap_until_it_cannot_cover_the_plan`; `test_runs_that_sent_nothing_are_charged_nothing_and_never_use_up_the_cap`; the in-flight test's case 1 (refused without approval, then an approved relaunch completes with the rest of the cap, and the claim and manifest record the approval); and new statement cases in `test_go_no_go_and_incomplete` and the five-errors test. Mutants M2 (no approval gate) and M3 (round 1's single statement) each fail two tests |
| 3 | minor | **The runbook's timing covered only the five-in-a-row stop.** Errors in runs of four never trip it, and each run pays the whole 30 + 120 + 300 + 300 s back-off, so a run can last about 95 minutes within the $5 guard (54 calls, $2.69, measured on the harness's own `run_draws`). Nothing told a polling operator how to tell slow from hung, and a SIGTERM sent after one delivery because the run "seems stuck" makes Phase 28a INCOMPLETE for good, a hard no-go for Phase 28 (design §18) | **Applied, text only.** §13 step 4 now states the worst cases: about 95 minutes, 54 calls and $2.69 for the reviewer's pattern, and about 109–117 minutes at the guard's 100 attempts ($4.98) for the harder patterns the first fixer measured. All are inside the declared waits and the guard. **Poll rule:** the run is alive while its pid exists and the manifest's `last_request`, `backoff_waits` or `attempts` keep changing. The longest the harness can go without saving the manifest is about 350 s (measured). Never stop it for being slow. After more than 15 minutes with no manifest change while the pid exists, write down what `ps` and the log show, tell the owner, and do not stop it alone. `kill -TERM` is only for a real reason, and after any delivery it ends the phase (§13 steps 4 and 5, §16). Evidence: `review-r2/reviewer/worst_wallclock.*`; `review-r2/fixer/worst_wallclock_r2.out.json` (four patterns at 2.3 s and 20 s answers, re-run on the round-2 harness and plan) |
| 4 | minor | **The runbook has Claude launch the run from its own tool shell**, the opposite of Phase 25's round-3 rule, and §2 did not declare the reversal. Measured with a stand-in launched exactly as step 4: the run survives the tool call's return, but it stays in that shell's process group and session, so a group-level cleanup (for example when the session ends) would send a SIGTERM, an operator stop. Step 3 also lacked the concrete power check of Phases 27 and 30 (`pmset -g batt` must print "Now drawing from 'AC Power'"; on battery `caffeinate -s` does nothing), and Phase 25's `pmset -g sched` and automatic-update checks. The machine was on battery at review | **Applied, text only.** New §2 row 14 declares the departure and cites the measurement: `$!` is Python, `caffeinate` is its child, Python survives the tool call (parent pid 1, SIGHUP ignored), `kill -TERM` reaches the handler and both processes exit, and it stays in the tool shell's process group and session. `set -m` is refused in the tool's zsh. §13 step 4 says the launching Claude session must stay open until the manifest is final. §13 step 3 adds the power check and Phase 25's schedule and automatic-update checks. They were read again at $0 when round 2 was applied: AC power (75%, charging), wakes only, `AutomaticallyInstallMacOSUpdates` 0 (`review-r2/fixer/os_stop_checks_r2_fix.out.txt`). The optional `start_new_session` wrapper was not adopted: it would need its own rehearsal against the paid-run token rule. Round 3 question 4 asks about it |

**Found while applying round 2 (not reviewer findings).**
1. **The "no generation arrived" test now also reads the manifest's own count.** The first fixer's statement branch
   looked only at the response lines. The one-run rule (`live_run_records`) decides on the manifest's count
   (`delivered_generations`). The two could disagree if a generation arrived on an attempt whose line shows no sign
   of it; no such line is known. `compute_readouts` now takes `manifest_delivered`, which `run_live` and
   `--readouts` pass from the run's manifest; an unreadable count (None) counts as arrived. So the relaunch wording
   uses the rule's own test. Test: two cases in `test_go_no_go_and_incomplete` (a counted generation, an unreadable
   count). Mutant M4 fails it.
2. **A test read the real repository's artifacts.**
   `test_the_process_guard_ignores_this_runs_caffeinate_child_and_sees_a_foreign_run` called `other_paid_runs`
   without pointing the harness at a test tree. It failed in this session because **a real Phase 30 run went live**
   at 2026-09-25T22:59:57Z (`artifacts/phase30-2026-09-25/live`, Python pid 10776). The guard correctly saw that
   run's open manifest and claim, and the test expected only its fake process. The test now uses an empty test tree,
   like every other guard test. No harness change. The harness is right: a Phase 28a launch would be refused while
   Phase 30 runs (§12 item 3), and §13 step 3 requires Phase 30 to have ended. Nothing in this session touched the
   Phase 30 run or its files.

**What round 2 changed, and the new pins.**
- **Harness** (`upgrade_mechanic_probe.py`): `6c24121c…` →
  **`613b66bdb7cbcca40af45d14d787cc45ba7f34b1a95ea9ccbe1be2f1400863cc`**. Changed:
  - the `finally` block (finding 1);
  - `RELAUNCH_RULE`, `RELAUNCH_APPROVAL_NAME`, `check_relaunch_approval`, `--relaunch-approval`, and the claim's
    and manifest's `relaunch_approval` (finding 2);
  - the two INCOMPLETE statements and `any_generation_arrived` (finding 2);
  - `compute_readouts`' `manifest_delivered` (found item 1);
  - the module docstring and `--finalize-abandoned`'s note.
- **Plan:** `8f753a2c…` → **`56b16211c2a3a4fcf028cc4e8de0f6517bbf1520b692fb3358132ee8cfb6e3b1`**
  (`dry-plan-r2/`). Only `harness_sha256` changed and `relaunch_rule` was added. The requests, the draws and
  `prompts.jsonl` (`807a141c…`) are byte-identical to round 1's (`review-r2/fixer/plan_r1_vs_r2.out.txt`). A plain
  dry run after the last edit prints the same plan hash (`dry-plan-r2-check-stdout.txt`).
- **Tests** (`test_upgrade_mechanic_probe.py`): 67 → **74**, all passing after the last edit
  (`tests-upgrade_mechanic_probe-r2.txt`). New or replaced tests are named above. Also changed:
  `test_go_no_go_and_incomplete`, the five-errors test, E4, `FakeOpenAI` (it can now raise a cancellation in flight,
  or a scripted client exception) and the process-guard test.
- **Mutation check** (`review-r2/fixer/mutation_check_r2.out.txt`). Each mutant is the round-2 harness with one
  round-2 change taken out, loaded in memory; the file on disk is never changed:
  - M1: round 1's `finally` block;
  - M2: no relaunch gate;
  - M3: round 1's single INCOMPLETE statement;
  - M4: the arrival test without the manifest's count.

  Each is caught by the tests named above, and the round-2 harness passes all of them.
- **Protocol:** the status block and pins; §2 (its heading, rows 13 and 14); §3; §9; §11; §12 items 7 and 9; §13
  steps 3–5 and 7; §14–§18; this log. Its sha is taken only when the review closes (§13 step 2).
- **Unchanged:** `slot2_probe.py` (`28b998ac…`), `run_full_loop.py` (`07dcaa93…`), everything under `backend/app`,
  and the configuration pin `2cf63e93…`.

**Next.** Round 2 changed the harness, so **round 3 must run** on the changed code (pitfall 74), with the questions
in §17. The review is not closed, and no `review.json` exists. Phase 30 was live while round 2 was applied. Phase
28a may launch only after Phase 30 has ended and round 3 has closed.

### Review log — round 3 (2026-09-25, $0)

**Lenses.** Two reviewers, working read-only on the round-2 harness `613b66bd…`, plan `56b16211…`, protocol
`711a328c…` and tests `f3393eda…`. Both returned **RUN_WITH_CHANGES**, with 9 minor findings; FC2 and F1 are the same
finding, so 8 are distinct.
- **Fix-check** (scratch copied to `review-r3/fixcheck-reviewer/`): round 2's three fixes, attacked with 21
  fake-only tests (`test_r3_fixcheck.py`, all passing on round 2's harness). Findings FC1–FC3. Its file sha256s
  before and after match (`shas-before.txt`, `shas-after.txt`).
- **Fidelity** (`review-r3/fidelity-lens/`): the protocol against the design, the harness and the stores, with
  every count re-derived by its own scripts. Findings F1–F6. It did not query the backend on port 8000.

Neither edited a repository file, opened `.env`, `checks.py`, heldout-2, promotion or final-audit files, passed
`--execute-live`, or made a provider, model or W&B call. No `review.json`, claim or live folder existed.

**What they found sound** (not repeated below):
- **Pins and tests:** plain dry runs printed plan `56b16211…`, harness `613b66bd…` and configuration `2cf63e93…`,
  byte for byte as round 2's check. `slot2_probe.py` `28b998ac…`, `run_full_loop.py` `07dcaa93…`,
  `completion_study.py` `c3fc2234…`. 74 of 74 tests passed before and after each review.
- **Round 2's fix 1 (every admitted attempt charged):** a cancellation during the blind-retry wait (A2: 1 attempt, 1
  unrecorded, no line), during a back-off (A3), during a format repair in flight (A4: 1 delivered, a second run
  refused), `SystemExit` and `KeyboardInterrupt` in flight (A5, the handlers restored), and while the provider closes
  (A6); every normal ending records 0 unrecorded (C1–C3); `--finalize-abandoned` adds its 2 attempts only to a
  manifest that is not final.
- **SIGTERM with the harness's real handler:** during a back-off the run stops before the next request (B1); sent
  from another thread during a real asyncio back-off it ended the run 0.503 s later (B3); during the blind-retry wait
  no re-send is sent (B2).
- **Round 2's fix 2 (the relaunch gate):** refused for the earlier runs in another order, an `out` spelled
  differently from the refusal's, and a symlinked record pointing outside `artifacts/` (D1–D3); one record admits one
  launch, even one that claimed and ended at $0 (D4); a record survives a refusal before its claim (D5); an earlier
  run that ends between the check and the claim is caught by the claim, with nothing claimed (D6); the check runs
  before the credential read.
- **Normal paths:** `run_draws`, `decide`, `DECISION_RULE`, `classify_draw`, `upgrade_audit`, `SpendGuard`,
  `live_run_records`, `finalize_abandoned`, `check_output`, `check_review`, `collect_inputs` and every constant are
  AST-identical to round 1. Plan r1 against r2: only `harness_sha256` and the added `relaunch_rule`.
  `prompts.jsonl` is `807a141c…` in every round.
- **Fidelity:** the requests are the loop's slot-1 first proposals (`candidate_history` [], `policy-v0`, the loop's
  objective; Phase 25's messages and body, digest-checked); the context builder matches `completion_study.py`
  lines 394–403, confirmed by the 26-of-26 control; the format repair matches `Mechanic._generate`; the source spec
  hashes to `c4decdb9…` by an independent stdlib hash. Every count in §4, §5 and §7 was re-derived from `dry-plan-r2`
  and matches. The decision is the design's "present" predicate. §10's table and the Wilson bound 0.1135 match a
  recomputation. The cost bound is $0.04984 ($2.9904 for 60 calls; 100 attempts under $5). The live-gate order in
  §12 matches `run_live` and `main()`.
- **Runbook and machine:** the wall-clock script re-run on round 2's harness reproduced 95.2–116.7 minutes, $2.69–
  $4.98 and a longest gap of 350 s between manifest saves. The machine read AC power (100%), wakes only, and
  `AutomaticallyInstallMacOSUpdates` 0. The guard reading found no other open run file, no `--execute-live` process
  and no Phase 28a run or claim; Phase 30's manifest is `COMPLETED` at $17.974.

**Who applied it.** One fixer session (scratch `review-r3/fixer/`). It saved verified reference copies of the round-2
harness, tests and protocol first (`orig-round2/`, sha256s `613b66bd…`, `f3393eda…`, `711a328c…`), and ran every
check after the last edit.

**Every finding and its disposition:**

| # | severity | finding | disposition |
|---|---|---|---|
| FC1 | minor | **A line cut off by a hard stop was not counted as delivered, so the one-run rule could admit a relaunch after part of a draw was readable.** The one-run rule reads only the manifest's count. `--finalize-abandoned` counted deliveries from complete response lines only, and skipped a trailing line cut off by a hard stop. If that line held the run's first delivered generation, the finalized manifest said 0 delivered, the harness treated the run as one that "ended having delivered nothing" and admitted a relaunch with the owner's record, while the same run's read-out said a generation may have arrived. An approved relaunch would then have been a second draw after one was partly seen (pitfall 49). §9 had claimed the two tests were equal, and the test comment in `test_go_no_go_and_incomplete` said the harness refuses a relaunch for a cut-off line. Evidence: the reviewer's E1 (a RUNNING manifest at 0 delivered, a claim, and `responses.jsonl` ending in half of a FIRING line: finalized as 0 delivered with 1 partial line skipped; the relaunch refusal asked for an approval; the read-out said "no completion mode"; the word `candidate` readable in the cut line). Realistically only a power loss or a kernel panic during the write of the first delivered line causes it, since each line is one write and fsync | **Applied, the recommended harness fix.** `finalize_abandoned` now counts a skipped cut-off line as a delivered generation: `delivered = sum(entry_delivered(r) for r in results) + partial`, with a comment and a docstring sentence. `load_results` skips at most one line, the trailing one. A cut-off line counts whatever its readable part says, an errored one too: the conservative side, since a relaunch after a partly seen draw is the failure to avoid. The one-run rule then refuses a second run ("repeat-until-lucky"), and the statement and the rule agree. **Test:** `test_a_line_cut_off_by_a_hard_stop_counts_as_delivered_and_no_relaunch_is_offered`, the reviewer's E1 with its assertion inverted, in three cases: a cut-off FIRING line and a cut-off errored line are each finalized as 1 delivered (2 in-flight attempts charged), refused by `earlier_live_runs` and `check_output`, and read out with `any_generation_arrived` and "no completion mode"; the contrast, a complete errored line with no cut, is finalized as 0 delivered (4 attempts), a launch needs the owner's relaunch approval, and the read-out gives the relaunch wording. The test comment is corrected. **Mutation check:** M5 (round 2's line) fails both cut cases and passes the contrast; the round-3 harness passes all three (`review-r3/fixer/mutation_check_r3.out.txt`). **Text:** §9 now states what each test reads and why they agree; §11, §13 step 7, §14 and §16 say a cut-off line counts as delivered and that the owner must not approve a relaunch after one. The text-only alternative was not taken, because it would leave the harness admitting a relaunch the protocol forbids |
| FC2 = F1 | minor | **The relaunch wording does not check the phase cap.** `compute_readouts` cannot see earlier runs or the rest of the $5. After the last launch the cap admits, the run's statement still says "Another launch within the $5 phase cap sends all 30 draws and needs the owner's relaunch approval", although the harness then refuses every further launch on the cap alone. §9 claimed the wording appears only "while the phase cap covers the plan" and "never after a run the harness would refuse to follow", and the `compute_readouts` comment said it "never offers a relaunch the harness would refuse". Wording only: no money or decision is affected. Evidence: the fix-check's E2 (four runs at 12 attempts; `check_budget` refuses; the statement still offers a relaunch) and the fidelity lens's `relaunch_wording_vs_cap.*` (at 10, 12 and 1 attempts per run: 5, 4 and 41 launches admitted, then refused at $2.51, $2.61 and $2.96) | **Applied, text only, and the harness comment corrected in the same edit as FC1.** §9 now says the wording never appears after a run that delivered anything, does not check the phase cap, and after the last launch the cap admits (the 5th at ten attempts per run, the 4th at twelve, the 41st at one) still appears while the harness refuses any further launch at $0, even with an approval, and names the cap; the phase then ends INCOMPLETE, a hard no-go for Phase 28 (design §18). §14's INCOMPLETE bullet adds "while the rest of the $5 covers the 60 planned calls". The `compute_readouts` docstring and comment now say the same. **Not taken:** the optional change passing the remaining cap into the statement. The statement's "within the $5 phase cap" already reads as a condition, the harness's refusal names the cap, and keeping round 3's code change to FC1's one line keeps round 4 small |
| FC3 | minor | **The runbook did not say that a workflow subagent is a short-lived session.** Each workflow subagent is its own `claude` process that ends when it returns its result or when a step timeout stops it. A subagent that launches the run and returns after `echo $!` exposes the run to the process-group cleanup §2 row 14 warns about, for a run that can last about 95–117 minutes; after one delivered generation the SIGTERM would end the phase for good. Evidence: `tool_shell_process_facts.out.txt` (the reviewer's tool shell leads its own process group under its `claude --output-format stream-json` process; whether that process cleans up the group on exit is unmeasured) | **Applied, text only.** §13 step 4 adds that the launcher must be a session that will outlive the run: the owner's interactive main session, or a subagent that polls until the manifest is final before it returns and has no step timeout under about 2 hours; never a workflow step that returns right after the launch. §2 row 14 and §16 say the same. With this rule, keeping the launching session open answers round 3's question 4; no `start_new_session` wrapper is built |
| F2 | minor | **The budget text was stale, and the runbook had no ledger check at launch.** §11 still said "$652.90 charged and $347.10 remaining… (Phase 30 may have spent since)", although Phase 30 has ended and its charge is known; §13 step 3 had no step reconciling the ledger against the $5 cap, which Phase 30's runbook had. Evidence: Phase 30's manifest `COMPLETED` at 23:24:38Z, $17.974; `PHASE30_RESULTS.md` line 213 ($670.88 charged, $329.12 remaining) and the ledger's $329.12 | **Applied, text only.** §11's Budget cites Phase 30's final manifest, $17.974 carried as $17.98, $670.88 charged and $329.12 remaining, which covers the $5 cap. It also notes that the ledger's "Shared total" row still reads $652.90, the figure before Phase 30, while its remaining line reads $329.12 (checked here; the ledger was not edited). §13 step 3 adds a Budget bullet, and step 2 says `remaining_budget_at_approval` states that figure. The "Phase 30 has ended" bullet now cites the final manifest, its claim and round 3's guard reading. Re-read by this fixer at $0 without querying the backend: no other open run file, no `--execute-live` process, no Phase 28a run or claim, Phase 30 `COMPLETED` (`review-r3/fixer/guard_reading_r3_fix.out.json`) |
| F3 | minor | **The backend check was not Phase 30's exact check.** §13 step 3 said only "If the backend is up, it must show no active campaign", without the command, the expected string, what to do when the connection is refused, or Phase 30's manual `ps` check; nor Phase 30's $0 `check_review` rehearsal. The harness does read the same URL and fails closed, so this is a runbook-fidelity gap, not a safety hole | **Applied, text only.** §13 step 3's bullet is now Phase 30's: `curl -s http://127.0.0.1:8000/api/config/status` must show `"active_campaign_id":null`; if refused, `lsof -nP -iTCP:8000 -sTCP:LISTEN` must show nothing listening; any other failure blocks; `ps -ax -o pid,command | grep -- '--execute-live' | grep -v grep` must print nothing (with Phase 30's caveat about a shell that only mentions the flag). The optional rehearsal is added to §13 step 2: call `check_review(PROTOCOL.read_text(), sha256_file(PROTOCOL), S, H)`, which must return the record |
| F4 | minor | **§6 gave no likely direction for the input differences.** NO_GO closes Phase 28 for good, so the reader needs to know which way the differences plausibly push. Two have a plausible direction, both toward NO_GO: the system message says "verified public development evidence" while every row reads `local_only` (180 labels, 0 `weave_verified`, neither explained in `completion.md`), and the source trials are split across 2–3 scenario hashes, none the shown spec's | **Applied, text only.** Each §6 item now gives a likely direction, marked unmeasured: (1) toward NO_GO; (2) none expected; (3) toward NO_GO; (4) none expected; (5) low, direction unknown (no configuration, algorithm, runtime, contract, scorer or policy hash appears in any context). One sentence says the two with a plausible direction lean toward NO_GO, the irreversible result. §14's NO_GO "would not mean" adds "or with one study's controls under one scenario hash", and §15 repeats the lean. Re-checked here at $0 on `prompts.jsonl`: the phrase is in all 30 system messages (one distinct system message), 180 `local_only` and 0 `weave_verified`, none of the six hash names in any context, and `backend/app/agents/prompts/completion.md` mentions neither label. The plan's `declared_input_differences` list (in the harness) is unchanged; the directions are protocol text |
| F5 | minor | **The design's F11 commit step was missing and undeclared.** Design §9 says Phase 28a follows the F-step pattern on its own files (no F4–F6), and F11 commits the protocol, runner and prep outputs to the backup branch, then freezes. The runbook's step 2 ended with `review.json` and never committed; Phase 30 committed its closed protocol (`6ed4fa0`). The only commit of the Phase 28a files is `6dbcb82`, a mid-build snapshot; on `main` they are untracked | **Applied, the step (not the alternative of declaring the omission).** §13 step 2 adds "Commit and freeze": commit the closed protocol, the harness and its tests to `backup/part2-2026-09-22`, as Phase 30 did in `6ed4fa0`, without checking that branch out in this working tree (the branch holds `6dbcb82`'s older copies of these files, and `main` is at `cbbf957` with them untracked). `artifacts/` is git-ignored and stays local. A commit does not change the bytes, so P, S and H hold; `shasum -a 256` confirms it afterwards; from then until the run ends nothing edits the files. This fixer made no commit |
| F6 | minor | **The `parent_version` departure was not declared.** Design §6.0's difference 4 names three probe values: `campaign_id`, `study_id` and `parent_version`. The protocol uses the loop's own `policy-v0`, so difference 4 shrinks to the two ids. That is better fidelity, but §2 claims to list every departure | **Applied, text only.** §2 row 7 quotes the design's three names and says `parent_version` is the loop's `policy-v0`, not a probe value, so the difference applies to the two ids only; the stored Phase 23 slot-1 inputs read `policy-v0` too (26 of 26 byte-equal). §6 item 4 says the same |
| note | none requested | **A wording nit (fix-check):** §11 and §15 said only the in-flight attempt has no response line. A2 shows that an errored first attempt whose blind-retry wait was interrupted by an exception has no line either; it is still counted in `unrecorded_attempts_charged` | **Applied as wording**, since the paragraph was being edited: §11 and §15 now name that case, and say that a stop by signal during the wait is different (the line is written with its one attempt, and no re-send is sent; B2) |

**What round 3 changed, and the new pins.**
- **Harness** (`upgrade_mechanic_probe.py`): `613b66bd…` →
  **`3dacdbeda2c670936e99e41dd50f1c2aade70fdb7b54247f922c9bfd108938a0`**. Changed: one line of
  `finalize_abandoned` and its docstring (FC1); the `compute_readouts` docstring and one comment (FC1, FC2). An AST
  comparison with docstrings removed finds `finalize_abandoned` the only function whose code differs, and no
  module-level assignment differs (`review-r3/fixer/harness_r2_vs_r3.out.txt` and `.diff`).
- **Plan:** `56b16211…` → **`a04d931938be880365dc3a0261d24ab9d050297520b9f63fef4ef9db505d9a8c`**
  (`dry-plan-r3/`). Only `harness_sha256` changed. The requests, the draws and `prompts.jsonl` (`807a141c…`) are
  byte-identical to round 2's (`review-r3/fixer/plan_r2_vs_r3.out.txt`); no finding required otherwise. A plain dry
  run after the last edit prints the same plan hash (`dry-plan-r3-check-stdout.txt`).
- **Tests** (`test_upgrade_mechanic_probe.py`): 74 → **77** (the new test has three cases), all passing after the
  last edit (`tests-upgrade_mechanic_probe-r3.txt`). The comment in `test_go_no_go_and_incomplete` is corrected.
- **The fix-check reviewer's own tests, re-run on the round-3 harness:** 18 pass and 3 fail, each as expected: its
  pin of the round-2 sha; D2, which passes the round-2 sha as the approval's harness; and E1, whose round-2
  assertion (`generations_delivered == 0`) is the defect FC1 fixed (`review-r3/fixer/reviewer_fixcheck_tests_on_r3_harness.out.txt`).
- **Protocol:** the status block and pins; §2 rows 7 and 14; §3; §6; §9; §11; §13 steps 2, 3, 4 and 7; §14–§18; this
  log. Its sha is taken only when the review closes (§13 step 2).
- **Unchanged:** `slot2_probe.py` (`28b998ac…`), `run_full_loop.py` (`07dcaa93…`), everything under `backend/app`,
  and the configuration pin `2cf63e93…`.

**Next.** Round 3 changed the harness, so **round 4 must run** on the changed code (pitfall 74), with the questions
in §17. The review is not closed, and no `review.json` exists. Phase 30 has ended (`COMPLETED`, $17.974), and no other
paid run was seen when round 3 was applied.

### Review log — round 4 (2026-09-26, $0): the focused check of round 3's fix

**Reviewer:** an independent $0 verifier, run after round 3's last edit (evidence in
`artifacts/phase28a-2026-09-25/review-r3/verifier/`). No paid, provider, model or W&B call; no `--execute-live` on the
real harness; no `.env`, `checks.py`, heldout-2, promotion or final-audit file read; no repository edit. It returned
**launch-ready apart from closure**, with no new finding needing a fix and three optional wording nits.

**Round 4's answers to §17's round-4 questions:**
1. **The cut-off line: sound.** A cut firing line, a cut errored line and a NUL-filled tail with no newline are each
   finalized as delivered, and the one-run rule refuses a second run; a second cut line after a delivered first line
   counts both; a second finalize refuses; a well-formed owner relaunch record cannot get past it (the refusal comes
   before the record is read, and nothing is claimed). The contrasts still need an approval: a run that sent nothing,
   and a complete errored line missing only its newline. Mutation check: with round 2's line put back, the new repo
   test fails in both cut-off cases and the contrast still passes. Counting an errored cut line as delivered is
   accepted as the cautious side.
2. **The harness diff: confirmed.** An AST comparison against the verified round-2 copy (`613b66bd…`) finds exactly
   one changed statement, in `finalize_abandoned`; the rest is docstrings and comments; no function added or removed;
   no module-level assignment changed. The plan differs from round 2's only in `harness_sha256`; the requests, the
   draws and `prompts.jsonl` (`807a141c…`) are byte-identical in rounds 0 to 3.
3. **The text-only changes: accurate.** FC2/F1 (the relaunch wording and the cap; the last launch the cap admits is
   the 41st at one attempt per earlier run, the 21st at two, the 5th at ten and the 4th at twelve), FC3, F2 (Phase 30
   `COMPLETED`, $17.974; $329.12 remaining), F3, F4 (re-derived from `prompts.jsonl`), F5 (the commit script,
   rehearsed in a scratch clone with the branch ref unchanged) and F6 (all 30 contexts read `policy-v0`).

**Also verified:** 77 of 77 repo tests before and after, plus the verifier's own 40 fake-only tests; the dry run
prints plan `a04d9319…`, harness `3dacdbed…`, configuration `2cf63e93…`, byte-identical to round 3's output; all 37
pins equal their files; a closure rehearsal on a scratch copy passes every offline gate up to the credential read and
refuses 32 closure mistakes; the paid-run guard excludes its own process, its `caffeinate` child and a shell that only
mentions the flag, and lists a foreign stand-in.

| # | kind | nit | disposition |
|---|---|---|---|
| N1 | wording | §13 step 2's "Commit and freeze" named no command | **Applied:** the Phase 22 script line is given |
| N2 | wording | "no step timeout under about 2 hours" left about 3 minutes over the 116.7-minute worst case | **Applied** in §2 row 14 and §13 step 4: "no step timeout, or one of at least 3 hours" |
| N3 | wording (pre-existing) | a hard stop that cuts a line inside a multi-byte UTF-8 character makes `--finalize-abandoned` raise a raw `UnicodeDecodeError`; the run stays `RUNNING` and every launch is refused (fails closed) | **Applied** in §13 step 7: a traceback means treat the run as delivered, never relaunch, and tell the owner |

All three are text only; the harness, plan and tests keep round 3's pins, so no further round is needed.

### Closure (2026-09-26)

**Approver:** Claude (Opus 5.5) as PM, delegated by the project owner. The owner's direction for the program: "go ahead with whatever u recommend" (Shree Bohara,
2026-09-25, approving the Phase 28–31 batch in chat), restated on 2026-09-25 evening as "ok go ahead.. i am homw
now.. pluggedn in alls et....". It is the delegation under which this approval is given.

| round | reviewers | verdict | harness changed |
|---|---|---|---|
| 1 | statistics and design; harness, fidelity and live safety | RUN_WITH_CHANGES (9 findings) | yes |
| 2 | one combined reviewer | RUN_WITH_CHANGES (4 findings) | yes |
| 3 | focused check of round 2's fixes; fidelity to the design and the runtime | RUN_WITH_CHANGES (9 findings, 8 distinct) | yes (one line) |
| 4 | focused check of round 3's fix | launch-ready; 3 wording nits, applied | no |

- **Decision rule:** the approved design's "present" predicate (design §19 decision 4): GO if at least one valid
  policy contains an orders `retry_original_request` at any hook under any gate; fire labels descriptive only.
- **No stricter rule, no relaunch without the owner's record, no held-out check** (design §19 decision 7).
- **Launch path:** the owner's interactive Terminal panel shell, as Phase 30 was launched, detached under
  `nohup caffeinate -is`; the approving Claude session stays open and polls until the manifest is final. That shell
  outlives any workflow step (§13 step 4).
- **Budget at approval:** $329.12 remaining after Phase 30, which covers the $5 cap.

Reviewed for launch: harness 3dacdbeda2c670936e99e41dd50f1c2aade70fdb7b54247f922c9bfd108938a0 plan a04d931938be880365dc3a0261d24ab9d050297520b9f63fef4ef9db505d9a8c
