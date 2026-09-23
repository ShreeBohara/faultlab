# Phase 15 results — September 22, 2026

Protocol frozen and then revised before any paid call:
[PHASE15_EXPERIMENT.md](PHASE15_EXPERIMENT.md). Evidence:
`artifacts/phase15-2026-09-22/` (manifest, runner log, service logs).
**28 attempts, 914 episodes, $97.33.**

## The declared target was reached for the first time

Phases 11 and 13 both declared 20 scored replays and reached 6 and 13. **Phase 15 reached
20, at attempt 28 of a cap of 34.**

| | scored | accepted | rate | Wilson 95% |
|---|---:|---:|---:|---|
| Phase 10 (`v1` citations) | 13 | 0 | 0.00 | [0.000, 0.228] |
| Phase 13 (`v4`) | 13 | 5 | 0.38 | [0.177, 0.645] |
| **Phase 15 (`v4`, control path fixed)** | **20** | **9** | **0.45** | **[0.258, 0.658]** |

**Primary: 9 of 20, Fisher two-sided p = 0.005 against Phase 10's 0 of 13.** The
pre-declared significance threshold was ≥7 of 20; it is met. Against Phase 13's 5 of 13 —
declared as a reference, not an adjudicating comparison — p = 1.00, i.e. **a clean
replication**.

Manifest and store reconcile exactly: 28 attempts, 20 scored, **0 discrepancies**.

## The mandatory decomposition, and the number that actually matters

The protocol required the untriggered-fault rate to be quoted alongside the headline,
because since Phase 11 the gate has essentially stopped rejecting this policy on quality, so
a "pass" largely means *all 36 fault-bearing episodes fired*.

| | untriggered rate | P(all 36 trigger) | observed pass rate |
|---|---:|---:|---:|
| Phase 10 | 1.28% | 0.628 | 0.00 |
| Phase 13 | 2.75% | 0.367 | 0.385 |
| **Phase 15** | **2.02%**, Wilson [1.27%, 3.22%] | **0.479** | **0.450** |

Phase 15's rate sits between the two, consistent with both, and its predicted pass rate
(0.479) again lands almost exactly on the observed one (0.450). The headline is doing what
the protocol warned it would.

**The conditional read-out is the cleanest result this project has produced:**

| scored replays | n | accepted |
|---|---:|---:|
| with **zero** invalid trials | 10 | **9 (0.90)** |
| with at least one invalid trial | 10 | **0** |

**When every fault in the batch triggers, the gate certifies this repair 9 times out of 10.
When one does not, it never does.** The separation is total. That, not 0.45, is the honest
statement of what the gate does with a working policy, and it is only quotable because the
decomposition was declared before the run.

## Full decomposition of all 28 attempts

| outcome | n | share |
|---|---:|---:|
| accepted (`OBSERVED_IMPROVEMENT`) | 9 | 32% |
| scored, clean batch, quality-rejected (`NO_CHANGE`) | 1 | 4% |
| scored, but a fault failed to trigger (`INCOMPLETE`) | 10 | 36% |
| died in the evidence channel | 8 | 29% |
| **died in the lab control path** | **0** | **0%** |

## S1 — quality rejection, with the honest wrinkle

**Phase 15 unpooled: 1 `NO_CHANGE` of 20 scored**, against Phase 10's 8 of 13.
Fisher **p = 0.000529**. Pooled across Phases 11+13+15: 1 of 40, **p = 0.0000118**. Both are
given, as the protocol requires.

**This breaks the "zero quality rejections" streak, and that is reported rather than
buried.** Phase 11 and Phase 13 had 0 of 20 between them; Phase 15 has 1. Its reason is
`Expected outcome regressed within a validation case` — a genuine quality judgement on a
clean batch, not batch fragility. It is the first since Phase 10. One in 40 is still a
collapse from 8 in 13, but "zero" is no longer the correct word and should not be used
again without this footnote.

## S2 — the Phase 14 fix, tested against a pre-registered prediction

**Prediction: 0 or 1 create-caused aborts of ~34 attempts. Result: 0 of 28.**

| | create-caused aborts | Fisher two-sided |
|---|---:|---|
| per attempt | **0 of 28** vs Phase 13's 11 of 30 | **p = 0.000334** |
| per episode | **0 of 914** vs Phase 13's 11 of 849 | **p = 0.000312** |

Not one `ReadError`. The `control_operation` field that Phase 14 added to name a failing
control call was never written, because no control call failed. The channel that destroyed
37% of Phase 13's attempts is closed.

**All 8 unscored attempts were the evidence channel** — 7 `WaitingEvidence`, 1
`EvidenceDenied` — which is exactly the channel Phase 14 does not touch, and exactly what
the protocol predicted would remain. A clean 28 of 28 was pre-declared as *not* expected and
would have been suspicious.

## S3 — yield

**20 scored of 28 attempts = 0.714**, inside the declared 0.68–0.74 band, against Phase 13's
0.433 and the all-prior 0.513. Phase 12's original objective — raising yield — is met two
phases after it was set, by fixing a channel Phase 12 never identified.

Spend **$97.33** against a $140 guard, slightly below the declared $100–115 because the run
finished at 28 attempts rather than the 34 it was authorised for.

## Declared contamination check

The protocol required reporting how many scored batches contained an `actor_transport_retry`
event, since that Phase 13 change touches episode execution. **7 of 20 scored batches (35%),
7 events across 914 episodes.** That is higher than the ~20% the protocol estimated from
Phase 13's data, and it is reported as measured. The retry applies symmetrically to both
arms, but a third of the scored batches contained one, so it is a real and non-trivial
difference from the Phase 10 configuration.

## Integrity

- `scorer_hash` **unchanged** and verified identical to all 36 stored configurations.
  `checks.py` was never opened.
- `actor_prompt_hash` **unchanged**.
- `algorithm_hash`, `runtime_hash` and `configuration_hash` **changed** — stated in the
  protocol before the run, not discovered afterwards. `assess_pairs`'s own source text was
  not edited (hash `783e8e58…` recorded for future comparison), but no byte-for-byte proof
  against Phase 13 is possible because the file is untracked and that phase took no source
  freeze.
- **Nothing was promoted.** Replay mode runs validation only and cannot accept a policy.
  Every campaign still has `policy-v0` active and no policy record is `ACCEPTED`.

## What this establishes, and what it does not

**Establishes:**
1. The declared 20-scored read-out, reached for the first time: **9 of 20, p = 0.005**.
2. **When a batch is clean, the gate accepts this repair 9 times in 10; when a fault fails
   to trigger, never.** The two channels are cleanly separated.
3. The Phase 14 control-path fix works: **0 of 28** against 11 of 30, p = 0.0003.
4. Yield 0.714, meeting Phase 12's objective.
5. Quality rejection remains near-eliminated — 1 of 40 pooled against 8 of 13 — but is no
   longer zero.

**Does not establish:**
- That the headline 0.45 measures the gate. It substantially measures the untriggered-fault
  rate, which is why the conditional figure is given.
- Anything about promotion. No policy is accepted anywhere.
- That the evidence channel is fixed — it is now the **only** remaining loss channel at 29%
  of attempts, and nothing in Phases 13–15 addressed it.
- That the one `NO_CHANGE` is noise. At n=20 a single event cannot be distinguished from a
  real residual quality failure.
