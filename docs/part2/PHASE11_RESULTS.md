# Phase 11 results — September 21, 2026

Protocol fixed and the design adversarially selected before any paid call:
[PHASE11_EXPERIMENT.md](PHASE11_EXPERIMENT.md). Progress: [PHASE11_TASKS.md](PHASE11_TASKS.md).

Phase 10 established that the validation gate accepted a provably working repair **0 times
in 13**, and that the dominant cause was the Actor corrupting 32-character hex evidence
identifiers it had to transcribe. Phase 11 removed the transcription and measured what
changed.

## The declared primary read-out did not reach significance

| | passes | Fisher vs Phase 10's 0 of 13 |
|---|---|---|
| **Stage B (the declared read-out)** | **2 of 6** | **p = 0.088 — not significant** |
| Stage A (validity check, 1 replay) | 1 of 1 | — |
| Pooled, by the rule fixed before Stage B ran | 3 of 7 | p = 0.031 |

The declared primary is **2 of 6 and it does not clear 0.05.** The pooled figure does, and
the pooling rule was written into the protocol *before* Stage B executed precisely so it
could not be reached for afterwards — but a result that depends on which of two
pre-declared figures you quote is not a conclusive result, and is not presented as one.

## What is conclusive is the mechanism, and the failure it removed

**370 episodes ran under `faultlab-actor-context/v4-indexed-evidence`. Zero contained a
fabricated evidence identifier.**

| | v1 (Phase 10, 828 episodes) | v4 (Phase 11, 370 episodes) |
|---|---:|---:|
| episodes citing a non-existent identifier | 3.43% | **0 of 368** |
| the ≥12-citation regime | 30% corrupted | **0 of 14** |
| **C1–C8 violation rate** | **6%** | **0%** |

And the read-out that tracks what the change actually targets:

> **Replays rejected on policy quality: 8 of 13 under v1, 0 of 7 under v4.
> Fisher's exact, two-sided: p = 0.015.**

Not one Phase 11 replay was rejected because the policy looked bad. Every non-pass was
`INCOMPLETE` — a scheduled fault failing to trigger somewhere in the 42 episodes — which is
batch fragility, not a citation failure, and is the same harness weakness that consumed 5
of Phase 10's 13 scored replays.

## The Phase 4 regression guard passes

Phase 4 is the precedent for an Actor-context change that fixed one thing and silently broke
another, so the same guard was applied per case to the candidate arm:

| case | target | v1 hit | v4 hit | v1 violations | v4 violations |
|---|---|---:|---:|---:|---:|
| healthy | COMPLETED | 99% | 97% | 0 | 0 |
| notification-1 | COMPLETED | 96% | 90% | 1 | 0 |
| notification-2 | COMPLETED | 87% | **100%** | 7 | **0** |
| notification-3 | COMPLETED | 89% | **100%** | 5 | **0** |
| **notification-18** | SAFE_UNRESOLVED | 66% | **92%** | **12** | **0** |
| lost-notification-response | COMPLETED | 93% | **100%** | 1 | **0** |
| terminal-upgrade-rejection | CORRECTLY_REJECTED | 100% | 100% | 0 | 0 |

**No case lost its target outcome. No case gained a violation.** The two cases that dipped
are within noise (`healthy` p = 0.51, `notification-1` p = 0.36) and their non-target
outcomes are truthful `SAFE_UNRESOLVED`, not violations.

Separately checked for the obvious ways this change could have broken something else:

- **Fault triggering is unchanged**: 97.5% under v1, 97.4% under v4, no case worse. The
  higher `INCOMPLETE` rate in Stage B is small-sample noise, not a consequence of v4.
- **The Actor behaves the same**: 5.42 → 5.14 actor calls, 6.00 → 5.92 HTTP attempts per
  episode; COMPLETED outcomes identical at 59%. v4 changed what the Actor *cites*, not what
  it *does*.

## A prediction that came out backwards, recorded as such

Three of the five design judges argued that cheap labels would make blanket citation nearly
free and erode C6's practical strictness. **The opposite happened.** Citation breadth —
cited observations over delivered observations — *fell*:

| | v1 | v4 |
|---|---:|---:|
| mean breadth | 0.887 | **0.735** |
| episodes citing 100% of their observations | 72.0% | **42.1%** |

The Actor became **more selective**, not less. That is the harder direction: C6's sub-clauses
require the *supporting* receipt to be among the cited set, so citing less makes C6 harder
to satisfy, not easier. Fewer citations with zero violations means the Actor is citing more
precisely. The judges' concern was reasonable and it was measured rather than argued; it did
not materialise, and the effect ran the other way.

## What changed in the code

`faultlab-actor-context/v4-indexed-evidence`: each delivered observation is shown under its
1-based journal position (`obs-1`, `obs-2`) instead of its `evidence-<32 hex>` identifier.
Every observation and every other field is retained; only the name changes. No opaque
identifier reaches the Actor, so there is nothing to mistype.

Cited labels are decoded to real evidence IDs before scoring. The decode is **total**,
**exact-match only**, and **passes unmatched tokens through verbatim** so they still fail C6.

Verified rather than asserted:

- **`scorer_hash` unchanged.** `checks.py` was never opened.
- `actor_prompt_hash`, `adapter_hash`, `interpreter_hash`, `contract_hash`,
  `capability_hash`, `dependency_lock_hash` all identical to Phase 10.
- The frozen descriptor hashes of protocols **v1, v2 and v3 are byte-identical** to those
  already in the store — the Phase 4 descriptor-stability rule holds.
- Through the real scorer: labels decode to an identical verdict, while `obs-99`, a
  fabricated hex identifier, an empty citation list and a near-miss `obs-1extremely` all
  still produce `VIOLATION`.
- 566 backend tests, 124 frontend tests, build and 3 browser fixtures green.

The design was chosen from five independent proposals, each scored by three judging lenses.
It tied highest at 8.0 with 3 of 3 ship votes and, unlike the runner-up, does not move
`scorer_hash`.

## A plan this phase abandoned before spending

The obvious vehicle was a two-arm **context study**. It cannot measure this change, and that
was established from retained data at zero cost:

- All 120 Phase 4 context-study episodes contained **zero** corrupted citations.
- The maximum citations in any context-study episode is **8**; corruption lives at **≥ 12**.
- Long citation lists only appear when a **policy** is executing, because policy reads,
  waits and retries add observations. A context study runs `policy-v0` in both arms.

It would have cost ~$8 to compare 0% with 0%, and that null would have been easy to misread
as "the fix does not matter". Recorded here rather than quietly dropped.

## Cost

Stage A $4.45170 + Stage B $35.32100 = **$39.77270**, 13 attempts, 370 live episodes.
Across Phases 2–11: **$234.85182 charged, $765.14818 remaining.**

## What this establishes, and what it does not

**Establishes.** The gate's inability to certify a working repair was substantially an
artifact of Actor transcription. Removing the transcription removed every citation failure
in 370 episodes, took the C1–C8 violation rate from 6% to 0%, and took quality rejections
from 8 of 13 to 0 of 7 — without losing a single target outcome or changing what the Actor
does.

**Does not establish.** A reliable gate pass rate. The declared read-out is 2 of 6 and the
binding constraint has moved again: **every remaining non-pass is batch fragility**, not
policy quality. Nor does any of this say the Mechanic can generate repairs reliably — that
is still 3 of 14 first proposals from Phase 9, untouched by this phase.

**No policy was accepted.** The replayed policy is still `REJECTED` and `policy-v0` remains
the incumbent everywhere.

## What should happen next

**Batch fragility is now the only thing standing between a working repair and a certified
one**, and it has two distinct causes, both measured:

1. **One `LAB_ERROR` aborts a 42-episode batch.** A transient provider `REQUEST_TIMEOUT` or
   `CONNECTION_ERROR` makes one episode a lab error; the evidence gateway refuses it as
   ineligible and the whole study dies. 6 of 12 Stage B attempts and 13 of 26 Phase 10
   attempts went this way. The Phase 6 retain-and-continue fix covers untriggered trials but
   not lab errors.
2. **One untriggered fault makes a batch `INCOMPLETE`.** At a 97.4% per-episode trigger rate
   across ~23 fault-bearing episodes, roughly 46% of batches contain at least one. This is
   a property of the fault injector's reliability, not of any policy.

These are separate changes and should be declared separately. Neither is a gate change.
