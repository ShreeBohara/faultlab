# Phase 21 results: Actor replay probe of the confirmation lapse. September 23, 2026

- **Protocol:** `PHASE21_EXPERIMENT.md`. Review rounds 1 and 2 were applied, and it was
  approved by Claude as PM, delegated by the project owner (review record
  `artifacts/phase21-2026-09-23/review.json`).
- **Harness:** `scripts/experiments/lapse_probe.py`, sha `f701ba14…`, plan `6d9182b4…`.
- **Evidence:** `artifacts/phase21-2026-09-23/live/`: plan, prompts, every raw response,
  manifest and `readouts.json`.
- **Run:** **1,063 of 1,063 requests delivered**, 0 missing, 0 retries needed. Every request
  was served by `deepseek-ai/DeepSeek-V3.1`, as requested. **$22.2167 conservatively charged**
  against the $25 cap.
- **Read-outs:** recomputed from the saved responses by the pinned harness, and identical.
- **Scope:** non-scoring. These are replays of stored development prompts; nothing entered a
  study.

## Decision: **V5_NOT_ADOPTED**, as declared

The run's statement: *"the lapse is not fixed by stating the missing state; the untriggered
channel stays fatal."*

| read-out | result | status |
|---|---|---|
| **Primary: turn 4**, the prompt right after the Actor read `UNKNOWN` for a confirmation it never sent (65 lapse episodes per arm) | sent the confirmation: **C 0 of 65, T (v5) 3 of 65, P (placebo) 0 of 65**. T 4.6% [1.6%, 12.7%]; T − P = 0.05; Fisher p = 0.12 | **FAIL** (needed T ≥ 0.8 and T − P ≥ 0.5 at p < 0.01) |
| **R3: v5 must not disturb ordinary turns** (100 non-lapse prompts) | T agrees with C's action on 99 of 100, with 0 reports | PASS |
| **R4: report wording** (T on 14 voluntary report prompts) | T **filed no report** on any of the 14; it asked for status instead | PASS, **but vacuous: 0 of 14 T reports**. R4 carries no information here, as the protocol's round-2 caveat warned |

**In plain words:** telling the Actor "no confirmation has been requested yet" does not get it
out of the lapse. Once it has polled a confirmation it never sent and read `UNKNOWN`, it keeps
polling: 65 of 65 times without the field, and 62 of 65 with it.

## Descriptive findings (declared as descriptive; they explain the failure)

**1. The lapse is mostly a chance event on the turn before, and it is sticky once it happens.**
- **Turn 3 re-sent unchanged (C):** on the turn where the historical episodes lapsed (they
  polled instead of sending), the same prompt now **sends the confirmation 54 of 65 times
  (83%)**. Only 5 of 65 responses match the historical one byte for byte.
- **So the historical lapse was usually a low-probability draw,** not a decision the Actor
  makes reliably from that input.
- **Turn 4 is absorbing:** once the draw has gone wrong, recovery is 0 of 65.

**2. At turn 3, any extra field raised sending to about 100%, regardless of what it said.**
- **Rates:** T 65 of 65, placebo 63 of 65, C 54 of 65. T − P is 3% (p = 0.25).
- **Reading:** the lift comes from perturbing the prompt, not from what v5 says. It is
  descriptive and was never a decision input.

**3. Temperature 0 is far from deterministic on this provider.**
- **Byte-identical output:** only **36% of pairs** of repeats of the same context (202 of
  560).
- **Word disagreement:** the notification word differs between repeats of one context 8% of
  the time [5.6%, 11.1%], within one session.
- **Match with history:** only 15% of repeats equal the stored historical answer (confounded
  with any provider change since).
- **Old PENDING contexts:** they now answer PENDING about 7% of the time, the same as old
  UNKNOWN contexts (7% vs 7%). The historical PENDING answers were not reproducible.

## What this establishes, and what it does not

**Establishes:**
- The declared fix for the lapse behind every untriggered fault **does not work** at the point
  of lapse, on the exact prompts that failed.
- The lapse is best described as a **low-probability, provider-nondeterministic draw on turn
  3** that becomes **self-sustaining** once the Actor has polled and read `UNKNOWN`.
- Temperature-0 runs on this provider are not reproducible **byte-for-byte**, even within one
  session.

**Does not establish:**
- That no fix exists. A change that acts **before** the poll (turn 3), or that breaks the
  absorbing state some other way, was not tested.
- Any end-to-end yield effect. This is a replay probe.
- Anything about the original historical conditions: the provider may have changed since.

## Consequences for the program

- **Phase 22:** v5 does **not** enter the change set.
- **Phase 25:** falls back to its declared alternative, 12 v4 replays capped at $60, run
  only after Phase 24 and only if the reserve is healthy.
- **The untriggered-fault channel stays fatal.** It remains the main yield loss of every paid
  gate run.
- **A candidate for later work, not in this program:**
  - Since the lapse is a turn-3 chance event and turn 4 is absorbing, the natural place for a
    fix is the lab or policy layer: for example, a hook that sends an unsent confirmation
    rather than letting the Actor poll it.
  - That would be a declared change to what the lab does, measured end to end, not a prompt
    tweak.

## Budget

$484.01 + $22.22 = **$506.23 conservatively charged, $493.77 remaining** of the shared
$1,000.
