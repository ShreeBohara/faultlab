# Phase 10 results — September 21, 2026

Protocol fixed, adversarially reviewed and corrected before any paid call:
[PHASE10_EXPERIMENT.md](PHASE10_EXPERIMENT.md). Progress: [PHASE10_TASKS.md](PHASE10_TASKS.md).

## The gate accepted a working repair zero times in thirteen attempts

| | |
|---|---|
| **Primary read-out** | **0 of 13 scored replays returned `OBSERVED_IMPROVEMENT`** |
| Wilson 95% interval | **[0.000, 0.228]** — the upper bound excludes 50% |
| Attempts | 26 (declared cap), 13 scored, 13 unscored and replaced |
| Episodes | 828 live episodes, 414 candidate-arm and 414 baseline-arm |
| Cost | **$93.82010** |

The declared band was "≤ 5 of 20 → the gate rejects a working repair most of the time".
The run reached its attempt cap at 13 scored rather than the targeted 20 — reported here
rather than extended — and 0 of 13 clears that band with room to spare.

**T15's policy remains `REJECTED`.** No replay accepted, activated or rewrote anything,
and `policy-v0` is still the incumbent in every campaign.

## Why: the Actor, not the policy

This is the finding, and it is not what the project assumed for ten phases.

| arm | violations | episodes | rate |
|---|---:|---:|---:|
| **L** (candidate policy) | 26 | 414 | **6.3%** |
| **B0** (empty baseline) | 21 | 414 | **5.1%** |

**The two arms violate at nearly the same rate.** Running the repair policy barely changes
how often an episode fails a check. Phase 9's 16–28% candidate-arm figure was measured on
the source case alone and did not generalise; on the seven-case mix the gate actually uses,
the excess attributable to the policy is about **1.2 percentage points**.

And the violations are overwhelmingly one thing: **62% of the 47 violating episodes (29 of
them) cited an evidence ID that does not exist.**

### The mechanism is transcription, not reasoning

C6 requires every cited `evidence_id` to be a real delivered observation of that episode.
The Actor is asked to copy 32-character opaque hex identifiers, and it intermittently
corrupts one. Phase 10 produced more instances of the same signature Phase 9 found:

```
evidence-d3739dcd82174ad1ac extremely a3d49e81eb8
evidence-b7361a76ad9347df835905 extremely 9f59892
```

The literal token **"extremely" has now been spliced into a hex identifier four separate
times** across Phases 8–10, alongside identifiers with 30 or 31 hex characters where a real
one has 32. This is a decoding artifact of the Actor model, reproducible and specific.

### The pre-registered prior replicated

Before the run, `analyze_citations.py` measured the corruption rate at **3.22%** on the 466
reports then in the store. After the run, on **1,284** reports — nearly three times the
sample, including 828 new episodes — it measures **3.43%**:

| kind | pre-run (466) | post-run (1,284) |
|---|---:|---:|
| well-formed but nonexistent | 7 | 35 |
| word fragment spliced into the hex | 3 | **19** |
| characters dropped | 3 | 7 |
| other | 2 | 3 |
| **rate** | **3.22%** | **3.43%** |

The prior was declared in the protocol before spending and predicted a ~50% single-arm pass
rate from citation corruption alone. The measured rate held; the pass rate came in lower
still because C5 unsupported-claim failures add to it.

### It concentrates where there is most to transcribe

| case | L violations / episodes | B0 violations / episodes |
|---|---:|---:|
| **notification-18** | **12 / 50** | 7 / 50 |
| notification-2 | 7 / 75 | 6 / 73 |
| notification-3 | 5 / 64 | 7 / 64 |
| notification-1 | 1 / 69 | 1 / 69 |
| lost-notification-response | 1 / 42 | 0 / 42 |
| healthy | 0 / 75 | 0 / 76 |
| terminal-upgrade-rejection | 0 / 39 | 0 / 40 |

`notification-18` — eighteen consecutive transient failures — generates the longest
observation history, and its episodes cite 13–14 of 15 observations. It is the worst case in
**both arms**. The failure scales with the number of identifiers the Actor must copy, not
with the difficulty of the recovery.

**This answers the question that started the phase.** `notification-18` does not fail
occasionally; it failed in every scored replay that reached a verdict on it, and the
baseline fails it too.

## The arithmetic checks out

The observed 6.3% per-episode candidate violation rate implies a 21-episode arm is
violation-free `0.937²¹ ≈ 25.6%` of the time. Among scored replays, 8 of 13 had exact valid
pairs. So the predicted pass rate is `0.256 × 0.615 ≈ 16%`, and `P(0 passes in 13) ≈ 11%`.

**0 of 13 is not a fluke of this policy. It is what a gate of this shape does on top of an
Actor that mis-cites about one episode in sixteen.** The gate is working exactly as
designed; the input it is judging is noisy in a way nobody had measured.

## A second, expensive limitation: half of all attempts were unusable

Of 26 attempts, **13 produced no validation assessment at all** and were retained, reported
and replaced under the declared rule. The cause is a single point of failure:

> A transient provider `REQUEST_TIMEOUT` or `CONNECTION_ERROR` makes one episode a
> `LAB_ERROR`. The evidence gateway then refuses that episode as ineligible, raising
> `EvidenceDenied`, which aborts the **entire 42-episode batch**.

One failed network call out of 42 destroys the whole replay. A further 5 of the 13 scored
replays returned `INCOMPLETE` — "exact valid triggered pairs are incomplete" — so only **8
of 26 attempts (31%)** produced a clean quality verdict. That is a property of the harness
worth as much attention as the read-out.

## Discipline

- The read-out, the scored/replaced rule, the interpretation bands and the attempt cap were
  all declared before the first paid call, and none was changed afterwards.
- The run stopped at its declared cap with fewer scored replays than targeted. The shortfall
  is reported; the cap was not raised to reach the number.
- Every attempt, error, lab error and incomplete batch is retained in
  `artifacts/phase10-2026-09-21/replay-manifest.json`.
- Replay mode reuses the unchanged `execute_slots` and `assess_pairs`, so these verdicts
  come from the same code that rejected T15 in Phase 9, not a reimplementation.
- Only `algorithm_hash` and the derived `runtime_hash` moved. The scorer, contract,
  capability, Actor prompt, adapter, interpreter, lock and service hashes are identical to
  Phase 9.
- Store grew from 53,131 to 83,180 records; 2,300 episodes.

## Cost

Phase 10: **$93.82010**. Across Phases 2–10: **$195.07912 charged, $804.92088 remaining.**

## What this changes

**For ten phases the project has been measuring the wrong thing.** "No generated policy has
been accepted" was read as evidence about the Mechanic's ability to generate a repair. Phase
9 showed the Mechanic can generate one. Phase 10 shows that **even a repair that provably
works is accepted 0 times in 13** — and that the rejections are driven by an Actor
transcription fault that affects the baseline almost as much as the candidate.

The honest restatement of the project's headline result is now:

> FaultLab has generated a recovery policy that completes the task, and its acceptance gate
> cannot currently certify one, because the gate's unit of evidence is an Actor-transcribed
> identifier that is corrupted about 6% of the time.

**The gate is not loosened.** It is doing what it was built to do. What must change is the
reliability of the evidence it judges.

## What should happen next

1. **Bound the citation surface.** The Actor should not be transcribing 32-character hex
   identifiers from memory at all. Referring to observations by a small index the engine
   assigns — the compact evidence format already does this internally with `oN` aliases —
   would remove the dominant failure mode outright. This is an Actor-contract change, so it
   must be measured against the frozen batch with the Phase 4 regression guard, and declared
   as its own single variable.
2. **Make one lab error not destroy a 42-episode batch.** The retain-and-continue fix that
   saved untriggered trials in Phase 6 does not cover `LAB_ERROR` episodes, which still
   abort through the evidence gateway. Half of this phase's attempts died that way.
3. Only after those: return to the Mechanic and ask whether a qualifying candidate can be
   produced reliably.

Neither of the first two is a gate change, and neither should be folded into the other.
