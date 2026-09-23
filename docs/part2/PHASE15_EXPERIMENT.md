# Phase 15 protocol — September 22, 2026

**Declared before any paid call, and revised before any paid call** after a four-lens
adversarial review returned `RUN_WITH_CHANGES` on every lens. The first draft of this
document contained a false integrity claim, an undeclared change to episode execution, a
read-out that mostly measures a nuisance parameter, an undeclared stronger figure, no power
calculation, an optimistic yield, and a circuit breaker that would have killed the run. All
are corrected below. The review's findings are the reason this phase is worth quoting.

## What is unchanged from Phase 13

| | value |
|---|---|
| policy under replay | `policy-d2b12ec1325742f5ac1428ec28f19639` |
| actor | `deepseek-ai/DeepSeek-V3.1` |
| actor context protocol | `faultlab-actor-context/v4-indexed-evidence` |
| mode | replay only — no Mechanic call, no proposal, nothing can be accepted |
| pass verdict | `OBSERVED_IMPROVEMENT` |
| validation batch | the frozen 7-case × 3-trial × 2-arm, 42 episodes |
| `scorer_hash` | `19de811c…` — **verified identical to all 36 stored configurations** |
| `actor_prompt_hash` | `12eabe7f…` — **verified identical to the store** |

## Integrity: what actually moved, stated correctly

The first draft claimed "`algorithm_hash` … is unchanged." **That was false, and it was the
claim offered as proof that no acceptance logic moved.** Measured against the store:

| hash | status |
|---|---|
| `scorer_hash` | **unchanged** (`checks.py` never opened) |
| `actor_prompt_hash` | **unchanged** |
| `algorithm_hash` | **CHANGED** — it covers `backend/app/lab` + `backend/app/referee`, and Phases 13–14 edited `lab/budgets.py`, `lab/completion_study.py`, `lab/runner.py` |
| `runtime_hash` | **CHANGED** |
| `configuration_hash` | **CHANGED** |

`assess_pairs` — the gate function — lives in `completion_study.py`, one of the changed
files. **Its own text was not edited**: the two edits to that file are the import at line 11
and the exception handler at lines 415–418, while `assess_pairs` begins at line 102. I record
its source hash now, `783e8e58f91992f36066a2c6a152c4fbd242bd7e`, so a future phase can
compare. **I cannot prove it byte-for-byte against Phase 13**, because the file is untracked
and no source freeze was taken for that phase. That is stated rather than glossed.

**Phase 15 is therefore not the byte-identical configuration Phase 13 ran under.** Any
comparison to Phase 10 or Phase 13 carries that caveat.

## What changed since Phase 13, including a change to episode execution

1. **Connection lifetime (Phase 14).** `keepalive_expiry=2.0` client-side and
   `--timeout-keep-alive 75` server-side. Touches only TCP connection lifetime.
2. **Bounded jittered retry of `create()` (Phase 14).** World creation only.
3. **Actor transport retry (Phase 13) — this one can affect episodes and must be declared.**
   `EpisodeMeter.transport_retry` plus its call site in `agents/actor.py` lets a transport
   failure be retried without spending an actor turn. In Phase 13 there were 5 actor
   transport failures in 849 episodes, so roughly **1 batch in 5** contains one, and in
   Phase 13's data it decided whether an episode survived. It applies symmetrically to both
   arms. **Pre-registered:** the results will report how many scored Phase 15 batches
   contained an `actor_transport_retry` event, so the size of this contamination is visible.

## The primary read-out, and what it actually measures

**Primary: of the SCORED replays, how many return `OBSERVED_IMPROVEMENT`?** Target **20
scored**. Single named contrast: **Phase 15 passes of 20 vs Phase 10's 0 of 13, Fisher
two-sided.** Phase 13's 5 of 13 is a reference point, not a second adjudicating comparison.

**Significance threshold and power, declared in advance:**

| passes of 20 | Fisher p vs 0/13 |
|---:|---:|
| 6 | 0.060 |
| **7** | **0.027 — first significant** |
| 8 | 0.012 |

| true pass rate | power to reach ≥7 |
|---|---:|
| 0.385 (Phase 13 observed) | **0.70** |
| 0.367 (untriggered-channel prediction) | 0.64 |
| 0.23 (if the untriggered rate drifts to 4%/episode) | **0.16** |

**A count of 4–6 passes will be reported as consistent with Phase 13 and underpowered
against Phase 10 — not as a refutation of either.** This is fixed now, before the result is
seen.

### The nuisance parameter this read-out is dominated by

Since Phase 11 removed citation corruption, the gate has stopped rejecting this policy on
quality. Verified in the store: Phase 13's 13 scored replays decomposed as 5
`OBSERVED_IMPROVEMENT` + 8 `INCOMPLETE` + **0 `NO_CHANGE`**, and every invalid trial in them
is the same shape — `lifecycle=COMPLETED, outcome=SAFE_UNRESOLVED, fault_scheduled=True,
fault_triggered=False`. So a pass now means, in practice, *all 36 fault-bearing episodes
triggered their fault*.

| | untriggered / trials | P(all 36 trigger) | observed passes |
|---|---:|---:|---:|
| Phase 10 | 7/546 = **1.28%** | 0.628 | 0 of 13 |
| Phase 13 | 15/546 = **2.75%** | 0.367 | 5 of 13 = 0.385 |

Phase 13's pass rate is almost exactly what the untriggered channel alone predicts. Phase 10
fell far below its own prediction because it was losing 8 of 13 to quality rejection. **The
nuisance rate has already moved 2.1× between the two phases being compared**, and on its own
swings the expected headline from 0.63 to 0.37 with the gate completely unchanged.

**Therefore, pre-declared and mandatory in every report of the primary:**

- **(a)** passes of scored — the headline;
- **(b)** the per-episode untriggered-fault rate over all validation episodes run, with a
  Wilson 95% interval, quoted **alongside** the headline every time, against the references
  1.28% (Phase 10) and 2.75% (Phase 13);
- **(c)** the count of scored replays with zero invalid trials, and passes among those — the
  figure that isolates the gate from the nuisance.

The headline is read conditional on (b). A drift in (b) must be visible, not absorbable.

## Secondaries, declared now so none is selected afterwards

**S1 — quality rejection, the gate-relevant contrast.** `NO_CHANGE` count among scored.
Phase 10: 8 of 13. Phase 11+13 pooled: 0 of 20, Fisher **p = 0.000093**. This figure is
stronger than the primary and *will* be produced by this run, so it is declared now rather
than quoted afterwards. **Pooling Phase 15 with Phase 13 against Phase 10 is permitted only
for S1, and the unpooled Phase 15 figure must be given beside it.**

**S2 — the Phase 14 fix, as a rate with its comparison fixed in advance.** Create-caused
aborts **per attempt** against Phase 13's 11/30, and **per episode** against 11/849, Fisher
two-sided, evaluated at whatever attempt count the run reaches.
**Prediction: 0 or 1 of ~34 attempts.** If create-caused aborts remain near 11 of 30, the
Phase 14 fix failed and this document requires me to say so plainly.

**S3 — yield.** Scored per attempt against Phase 13's 0.433 and the all-prior 0.513.
**Expected 0.68–0.74**, not the 0.8 the first draft claimed: 6 of Phase 13's 30 attempts died
in the evidence channel, but 11 were truncated early by the `ReadError` and never fully
exposed to it, so dividing 6 by 30 understates the per-attempt hazard. The evidence channel
is untouched by Phase 14, so **a clean 34 of 34 is not predicted and would be suspicious.**

## Bounds

| | value | why |
|---|---|---|
| scored replays targeted | 20 | unchanged |
| **attempt cap** | **34** | at yield 0.68–0.74, P(≥20 scored) = 0.92–0.98, against 0.66–0.87 at a cap of 30 |
| spend guard | $140 | worst case ~$125 at 34 full attempts |
| **circuit breaker** | **6 consecutive unscored** | the default of 4 would have aborted Phase 13 at attempt 22. At the predicted yield, 4-in-a-row occurs by chance ~3.4% of the time and 6-in-a-row ~0.6%. Recorded in the manifest |
| expected cost | **~$100–115** | revised from the first draft's ~$95–105 |

Budget before this run: **$339.40 charged, $660.60 remaining** of the shared $1,000.

## Read-out integrity: how the counts are computed

Two latent runner defects were found by review and **fixed before this run**; both could
silently delete a replay the gate had already judged, and both were biased toward discarding
*scorable* replays:

- reading the campaign's dollar figure was an argument to the update that saved the verdict,
  so a failed budget GET discarded the verdict with it. Spend is now recorded in its own
  step, after the verdict is saved.
- a single dropped poll GET abandoned the attempt without re-reading the study record, which
  may already hold the decision. The record is now re-read once and scored normally if
  present. The bias ran one way: the studies that poll longest are the ones that complete all
  42 episodes.

Additionally, an abort or Ctrl-C previously left the study running and charging, with that
spend missing from the ledger; the runner now stops the campaign and waits for it to settle
before reading total spend.

**Pre-declared:** the reported counts are computed by reconciling
`artifacts/phase15-2026-09-22/replay-manifest.json` against the `completion_studies` records
in the store, and any discrepancy is reported rather than silently resolved in either
direction. A runner log is retained at `artifacts/phase15-2026-09-22/runner.log`.

## What must not happen

No gate change, no `checks.py` edit, no threshold move, no per-case exclusion, no resumption
of a stopped study, no re-declaration of any read-out after seeing results, no quoting of the
primary without (b) and without the shortfall if one occurs, and no quoting of S1 pooled
without the unpooled Phase 15 figure beside it.
