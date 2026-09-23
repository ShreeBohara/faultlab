# Phase 8 progress

Protocol: [PHASE8_EXPERIMENT.md](PHASE8_EXPERIMENT.md). Results: [PHASE8_RESULTS.md](PHASE8_RESULTS.md).
Checked means done and verified, not planned.

## Before any paid call

- [x] Closed Phase 7 honestly first: recorded that the declared H2 arm was **not run**, why, and that a new phase was declared in the open rather than substituted quietly. Wrote the missing `PHASE7_TASKS.md`.
- [x] Verified the premise the whole design rests on: the adjudicated outcome is **already** in the Mechanic's context. The saved Phase 5 proposal input carries `observed_outcomes` with `outcome: SAFE_UNRESOLVED` for the three failing B0 episodes, while every episode row carries only `check_row`/`report_row` and every check row is all-passed.
- [x] Declared the change, both read-outs, the classification rule, the uninformative-stop rule and the limits in `PHASE8_EXPERIMENT.md` before spending anything.

## The change

- [x] `summarize_evidence` gained an optional `outcomes` argument. With it: `task_outcome` per episode, format `faultlab-compact-evidence/v2-task-outcome`, one structural legend clause. Without it: byte-identical `…/v1`.
- [x] `completion_study.py` supplies the map from trials it already holds. **No other call site passes it**, so the Explorer, Diagnostician and learning-loop contexts are untouched.
- [x] Four new tests: default output unchanged, outcomes bound per episode with every other structure identical and the legend a strict prefix extension, and a missing outcome recorded as explicit `None` rather than an absent key.
- [x] Extended the real-runner completion-study test to assert the live proposal context carries `task_outcome` matching each trial's actual outcome and that those values are a subset of what `observed_outcomes` already grouped.
- [x] Full suite green on the frozen source: **552 backend**, 121 frontend, production build, 3 browser fixtures.

## Freeze and verification

- [x] Byte-level diff against the Phase 6 freeze: exactly **two files changed**, `backend/app/lab/completion_study.py` and `backend/app/lab/diagnosis.py`. No prompt, scorer, contract, adapter, interpreter or dependency file moved.
- [x] Hash comparison against the stored Phase 6 configuration: only `algorithm_hash` and the derived `runtime_hash` moved. `source_hash`, `actor_prompt_hash`, `adapter_hash`, `interpreter_hash`, `scorer_hash`, `contract_hash`, `capability_hash`, `dependency_lock_hash` and `service_hash` are **identical**.
- [x] Snapshotted the database before any study: 36,420 records, 1,064 episodes, `artifacts/phase8-2026-09-20/before.sqlite3`.
- [x] Confirmed nothing was running before restarting the backend — the only non-terminal study in the database is the closed Phase 3 B2 `INCOMPLETE`.
- [x] Settings files copied unchanged from Phase 6, so the only difference between the phases is the two source files.
- [x] Built `scripts/experiments/summarize_completion_study.py`, a read-only read-out that makes no model call, and validated it against Phases 5 and 6 — it reproduces their published 0-of-2 results and their 12/12 verified counts exactly.

## Studies

- [x] Study 8A `completion-study-ba0a7595769542e899b0bcf3d9e42ff6` (V4 Mechanic), campaign `campaign-cdb43a228401458b91b77a85c87815e8`: **NO_CHANGE**, 12 trials, 74 calls, 12/12 verified. Controls passed on the minimum the gate allows — one source control was untriggered and retained as invalid, leaving 2 valid source (0 completions) and 3 valid healthy (3 completions). **2 of 2 proposals contain `retry_original_request` for notifications** — the first time in the project.
- [x] Confirmed mechanically that the step executed, rather than only appearing in the policy text: `policy_steps=4` in every candidate episode against 0 in every baseline, two `TRANSIENT_UNAVAILABLE` attempts at ticks 3–4, two `UNKNOWN` reads at ticks 5 and 7, and a third `send_confirmation` at tick 8 returning **SUCCEEDED**.
- [x] Recorded that the gate rejected it anyway and was right to: `L completed` was 2 of 3 with a C6 violation in the third, and a **baseline** episode in the same batch independently failed C5 and C6.
- [x] Recorded that 8A's second proposal is byte-identical to the first while claiming to remove a rule, so V4 produced **one distinct policy**, not two.
- [x] Study 8B `completion-study-fe0e1bde846144d6bc93b6a094898e26` (V3.1 Mechanic), campaign `campaign-20bd66acb8244a92b6747ee4032f7183`: **INCOMPLETE**, 14 trials, 101 calls, 13/13 verified. Controls clean at 3 valid source (0 completions) and 3 valid healthy (3 completions). **0 of 2**; its first proposal is byte-identical to the one V3.1 produced in Phase 5.
- [x] 8B ended on a provider `CONNECTION_ERROR` at candidate-2, retained as `LAB_ERROR` without retry, 4 slots left unattempted.
- [x] Applied the uninformative-stop rule as written: neither study stopped at the controls gate, both produced proposals, so **no repeat was run**. Two of the four permitted studies were used.
- [x] No resampling, no replacement trial, no second arm, no threshold or read-out changed after the fact.

## Findings recorded

- [x] Primary read-out **2 of 4**, all of it in one model, against 0 of 6 in Phases 5–6 and 0 of 4 in the Phase 7 probes.
- [x] Secondary read-out classified against the predeclared rule with the exact quote behind each call, including one flagged as borderline rather than rounded up.
- [x] The Phase 7 "no failing episodes" reading did **not** recur in any output.
- [x] Stated plainly in the results that one distinct policy from one model is evidence, not proof, and that V3.1 did not move by a single byte.
- [x] Re-verified after both studies: frozen source unmoved, 552 backend tests, 121 frontend tests, build and 3 browser fixtures green, all three services reachable.
- [x] Reconciled cost: 175 requests, $3.71538 conservative; running total 2,232 requests, $47.69064, **$952.30936 remaining**.
