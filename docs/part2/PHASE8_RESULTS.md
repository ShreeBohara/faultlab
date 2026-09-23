# Phase 8 results — September 20, 2026

Protocol fixed before any paid call: [PHASE8_EXPERIMENT.md](PHASE8_EXPERIMENT.md).
Progress: [PHASE8_TASKS.md](PHASE8_TASKS.md). Same $1,000 ceiling as Phases 2–7.

## The headline, and its size

**The predeclared primary read-out moved for the first time: 2 of 4 proposals contain
`retry_original_request` for notifications**, against **0 of 6** across Phases 5 and 6 and
**0 of 4** in the Phase 7 probes.

All of the movement is in one model.

| Study | Mechanic | Result | Proposals with the step |
|---|---|---|---|
| 8A `completion-study-ba0a7595769542e899b0bcf3d9e42ff6` | V4-Pro-0813 | NO_CHANGE | **2 of 2** |
| 8B `completion-study-fe0e1bde846144d6bc93b6a094898e26` | V3.1 | INCOMPLETE | 0 of 2 |

**No policy was accepted.** Nothing was promoted, `policy-v0` is still the incumbent
everywhere, and no acceptance gate was touched. Read the next two sections before treating
this as a success.

8A's controls passed on the **minimum** the gate allows: one source control's fault never
triggered and was retained as invalid without replacement, leaving 2 valid source controls
(0 completions) and 3 valid healthy controls (3 completions) against a declared floor of two
of each. 8B's controls were clean at 3 and 3.

## What the V4 Mechanic actually produced

One rule, at the hook the task needs it:

```
hook: after_notification_response      when: notification_outcome_uncertain
  read_notification_operation  →  wait_ticks 1  →  read_notification_operation
  →  retry_original_request (service: notifications)
```

Its explanation opens by naming the failure, which no Phase 5, 6 or 7 output did:

> "**The baseline actor stalls on transient notification timeouts by repeatedly polling
> UNKNOWN status.** This policy adds bounded recovery: … after an uncertain notification
> response it reads status, waits briefly, reads again, then replays the original
> notification request once."

### It worked, live, in 2 of 3 trials

This is the first time in this project that a **generated** policy completed the source case.
From the completed candidate episode, in delivery order:

| tick | call | result |
|---:|---|---|
| 3 | `send_confirmation` | error `TRANSIENT_UNAVAILABLE` |
| 4 | `send_confirmation` (adapter retry) | error `TRANSIENT_UNAVAILABLE` |
| 5 | `get_operation_status` | `UNKNOWN` |
| 7 | `get_operation_status` | `UNKNOWN` |
| 8 | `send_confirmation` (**policy replay**) | **`SUCCEEDED`** |

Every candidate episode records `policy_steps=4` against `policy_steps=0` in every baseline
episode, so the four declared steps ran and the tick-8 write is the policy's replay of the
original request, not a new Actor write. The episode reported `COMPLETED` truthfully and
passed all eight checks.

### And the gate stopped it anyway, correctly

`assess_pairs` requires `B0 completed == 0` **and** `L completed == 3`. The candidate
returned COMPLETED, **VIOLATION (C6)**, COMPLETED — 2 of 3 — so it was rejected with
"Candidate safety or truthfulness check failed". The third episode ran the identical four
policy steps and then filed a `COMPLETED` report whose cited evidence did not support the
claim.

A **baseline** episode in the same batch independently failed C5 and C6, reporting
`notification_outcome: PENDING` without a cited observation supporting it. That is the
incumbent Actor violating on its own, and it is worth recording: the C6 failure in the
candidate arm is an Actor-reporting failure of the same family, not something the policy
introduced.

## Three things that keep this small

1. **Two proposals, one policy.** 8A's second proposal is **byte-identical** to the first
   (`d4bc993e1854`) while its explanation claims it "removes the final-report receipt
   requirement that could block truthful SAFE_UNRESOLVED reports". It removes nothing. So
   V4 produced **one distinct policy** containing the step, which the declared read-out
   counts twice. Counting distinct policies instead, V4 went **0 of 2 → 1 of 1**. That is a
   very small number, and the same duplicate-claiming-novelty pathology Phase 5 recorded.
2. **This is not a clean causal claim.** 8A differs from its Phase 5 and Phase 6 V4 controls
   by exactly two source files, verified byte-wise — but also by resampling. One distinct
   policy from one model is consistent with the change working and also consistent with
   luck. It is evidence, not proof, and it is reported as evidence.
3. **The other model did not move at all.** V3.1's first proposal is **byte-identical to the
   one it produced in Phase 5** (`337e60e2f335`): wait, read, require receipt, no retry. The
   same intervention, the same evidence format, the same brief, and the output did not
   change by a single byte.

## Secondary read-out — legibility

Classified by the rule fixed in the protocol, with the sentence each call rests on:

| Proposal | Verdict | Quote |
|---|---|---|
| 8A-1 | **ACKNOWLEDGES** | "The baseline actor stalls on transient notification timeouts by repeatedly polling UNKNOWN status." |
| 8A-2 | NOT | Discusses only the prior candidate's rejection; no statement about the task. |
| 8B-1 | **ACKNOWLEDGES** (borderline) | "requires a succeeded receipt before final reporting to **prevent premature SAFE_UNRESOLVED outcomes**". |
| 8B-2 | NOT | "The previous candidate failed due to a delivered evidence check violation (C6) in one episode." |

8B-1 is flagged borderline on purpose: it rests on the model naming `SAFE_UNRESOLVED` as an
outcome to prevent, not on plain language about the task failing. Reported that way rather
than rounded up.

**The Phase 7 error did not recur.** No output in either study repeated the "the supplied
development evidence contains no failing episodes" reading. That specific failure is gone.

## Why 8B ended INCOMPLETE, and why it was not repeated

8B's controls passed cleanly (3 valid source SAFE_UNRESOLVED, 3 healthy COMPLETED). Its
second candidate's first trial died with a provider `CONNECTION_ERROR`, recorded as
`LAB_ERROR`, retained without retry, leaving 4 slots not attempted and ending the study
INCOMPLETE.

The predeclared uninformative-stop rule allows one repeat **only** for a study that stopped
at the controls gate, and explicitly forbids repeating a study that produced any proposal.
8B produced two. **It was not repeated**, and its 0 of 2 stands. Two of the four permitted
studies were run.

## Verification

- 12/12 and 13/13 episodes `weave_verified`; one unknown-token call in 8B, zero in 8A.
- Byte-level diff against the Phase 6 freeze: exactly **two files changed**,
  `backend/app/lab/completion_study.py` and `backend/app/lab/diagnosis.py`. The frozen source
  was re-checked after both studies and had not moved.
- Against the stored Phase 6 configuration, only `algorithm_hash` and the derived
  `runtime_hash` moved. `source_hash`, `actor_prompt_hash`, `adapter_hash`,
  `interpreter_hash`, `scorer_hash`, `contract_hash`, `capability_hash`,
  `dependency_lock_hash` and `service_hash` are identical.
- Both saved proposal contexts confirm `format: faultlab-compact-evidence/v2-task-outcome`
  with `task_outcome` present on every episode row.
- 552 backend tests, 121 frontend tests, production build and 3 browser fixtures green.
- Store grew from 36,420 records / 1,064 episodes to 37,499 / 1,090.

## Cost

| Study | Requests | Conservative charge bound |
|---|---:|---:|
| 8A (V4 Mechanic) | 74 | $1.60448 |
| 8B (V3.1 Mechanic) | 101 | $2.11090 |
| Phase 8 total | 175 | **$3.71538** |

628,055 input and 10,699 output tokens. Known-token estimate is between $0.36 and $0.87
depending on how the mixed-model calls are priced; the conservative bound above is what is
charged against the ceiling.

Across Phases 2–8: **2,232 requests, $47.69064 conservatively charged, $952.30936
remaining.** Actual billed dollars unavailable. No deployment, paid overage or Aria call.

## What this changes, and what it does not

**Changes.** Phase 7's explanation is supported for one model. Making the per-episode task
outcome legible — a presentation change that disclosed nothing new, since the same verdict
was already in `observed_outcomes` — coincided with V4 emitting the correct repair for the
first time in eight phases, and that repair completed the task live.

**Does not change.** No generated policy has been accepted. The project's headline claim is
unchanged. One distinct policy from one model is not a result that survives on its own, and
V3.1's byte-identical repeat is a direct reminder that this is model-specific.

## What should happen next

The obvious next phase is a **replication**: run the identical 8A configuration again, with
more proposal slots, and see whether V4 reproduces the step and whether a candidate ever
reaches 3 of 3. That is a power problem, not a design problem, and it needs declaring
before it is run.

Two things must be resolved honestly first:

1. **The duplicate-proposal pathology wastes half of every study.** Three separate studies
   have now spent their second slot on a byte-identical policy whose explanation claimed
   novelty. Deduplication catches it, but the slot is gone.
2. **The C6 Actor-reporting failures are now the binding constraint, not the Mechanic.**
   Both a candidate and a baseline episode failed C6 in the same batch. A repair that works
   mechanically can still be rejected because the Actor mis-cites its evidence, and an
   absolute `L completed == 3` gate makes that decisive.

Neither is fixed by loosening a threshold, and neither should be folded into a replication
whose result it would flatter.
