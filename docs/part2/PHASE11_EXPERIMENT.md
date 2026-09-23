# Phase 11 protocol — does removing transcription let the gate certify a working repair?

Written **before** any paid call. Results go in `PHASE11_RESULTS.md`; progress in
`PHASE11_TASKS.md`.

Phase 10 established that the validation gate accepted a provably working repair **0 times
in 13**, and that the dominant cause is the Actor corrupting 32-character hex evidence
identifiers it must transcribe. This phase removes the transcription and measures whether
the gate's behaviour changes.

## The change: `faultlab-actor-context/v4-indexed-evidence`

Each delivered observation is shown to the Actor under its 1-based journal position —
`obs-1`, `obs-2` — instead of its `evidence-<32 hex>` identifier. Every observation and
every other field is retained; only the name changes. **No opaque identifier reaches the
Actor at all**, so there is nothing to mistype.

The labels the Actor cites are decoded back to real evidence IDs before scoring. The decode
is **total** (every token yields one token, in order, nothing dropped, added, merged or
deduplicated), **exact-match only** (no case folding, no trimming, no nearest-label), and
**passes unmatched tokens through verbatim** so they still fail C6 exactly as today.

**`checks.py` is never opened.** `scorer_hash`, `actor_prompt_hash`, `adapter_hash`,
`interpreter_hash`, `contract_hash` and `capability_hash` are all verified identical to
Phase 10; only `source_hash` and the derived `algorithm_hash`/`runtime_hash` move. The
frozen descriptor hashes of protocols v1, v2 and v3 are byte-identical to those already in
the store.

The design was selected from five independent proposals scored by three judging lenses
each. It tied highest at 8.0 with 3 of 3 ship votes, and unlike the runner-up it does not
move `scorer_hash`.

## A plan this protocol explicitly abandoned, and why

The obvious vehicle was a two-arm **context study** — the Phase 4 harness that A/Bs Actor
protocols across 10 cases with a regression guard. **It cannot measure this change**, and
that was established from retained data before spending:

- Across all 120 Phase 4 context-study episodes there were **zero** corrupted citations.
- The maximum citations in any context-study episode is **8**. Corruption lives at **≥ 12**,
  where it runs at 30% against ~2.5% below.
- The reason: long citation lists only appear when a **policy** is executing, because policy
  reads, waits and retries add observations. A context study runs `policy-v0` in both arms,
  so its `notification-18` episodes produce ~6 citations rather than the 13–14 they produce
  inside a validation batch.

Running it would have cost about $8 to compare 0% with 0%, and a null there would have been
easy to misread as "the fix does not matter". It is recorded here rather than quietly
dropped.

A second reason not to lean on that harness: its decision rule returns `REGRESSION` if the
changed arm has **any** C1–C8 violation in 30 episodes. At the 3.3% per-episode baseline
violation rate measured on those very cases, that fires **~64% of the time regardless of
the change**.

## The measurement: gate replays under v4, against the Phase 10 baseline

The failure only manifests where a policy is running on the hard case, which is exactly the
frozen 42-episode validation batch. So Phase 11 replays the same Phase 9 qualifying policy
through the same unchanged gate, with the Actor running v4 instead of v1.

**Phase 10 is the control and is not re-run**: 0 passes of 13 scored replays, under
`faultlab-actor-context/v1`, same policy, same batch, same gate code, measured yesterday.

### Stage A — mechanism check, one replay

One live replay (42 episodes, ~$7, ~10 minutes), reported before any further spending.
It answers three yes/no questions:

1. Do `notification-18` episodes cite labels (`obs-N`) rather than hex identifiers?
2. Does every cited label resolve to a delivered observation of that episode?
3. Does the decoded report still score, and do the per-case outcomes look sane?

**If any answer is no, the phase stops here and reports why.** Stage A is a validity check,
not a measurement: one replay cannot establish a pass rate and will not be reported as one.

**Pooling rule, fixed before Stage B runs.** Stage A used the identical configuration, so
discarding its result would waste a paid observation and reporting only the pooled figure
would hide that one replay was run first and looked at. Both numbers are therefore
reported: Stage B's 6 scored replays as the declared primary read-out, and the pooled 7
alongside it, each with its own Fisher test against Phase 10's 0 of 13. Neither is
presented without the other.

### Stage B — the comparison, 6 scored replays

Primary read-out, fixed here: **of the scored replays, how many return
`OBSERVED_IMPROVEMENT`**, compared against Phase 10's 0 of 13 with **Fisher's exact,
two-sided**.

A replay is *scored* when it produced a validation assessment. One that produced none
observed nothing about the gate; it is retained, reported and replaced, up to an attempt
cap. Same rule as Phase 10.

**Why 6:** against a 0-of-13 control, 4 of 6 gives p = 0.0039 and even 3 of 8 gives
p = 0.042. Six scored replays is decisive **if the effect is large**, which is the only
effect worth acting on here. It is **not** powered to detect a small improvement, and a
null at n = 6 will be reported as "no large effect", never as "no effect".

At the ~50% attempt yield measured in Phase 10, 6 scored replays needs ~12 attempts:
**~$45 and ~2 hours.** Attempt cap **16**, spend guard **$90**.

### Secondary read-outs, fixed here

- **Citation corruption rate**, v4 arm versus the Phase 10 v1 arm, per episode and
  restricted to `notification-18`. This is the mechanism; the primary read-out is the
  consequence.
- **Per-episode violation rate, candidate and baseline arms.** Phase 10 measured 6.3% and
  5.1%. Note that the **baseline arm also runs v4** in these replays, so both arms should
  improve if the mechanism is real — that is a feature, not a confound, because the
  comparison is against Phase 10's absolute numbers, not between arms within a replay.
- **Citation breadth** — cited real observations over delivered observations. Three judges
  argued that cheap labels make blanket citation nearly free and erode C6's discriminating
  power. Measured baseline: **75.4%** of episodes already cite 100% of their observations,
  so blanket citation is already dominant. If breadth rises materially above that, it is
  reported as a real erosion of C6's practical strictness, whatever the primary read-out
  says.
- **Any unresolved label** appearing in a scored report, which would mean the Actor invented
  a label — a new failure mode this change could introduce.

## Limits

- No change to the grammar, interpreter, scorer, manifest, proposal slots, Actor prompt or
  any acceptance gate. `checks.py` is not opened.
- Phase 10's result is the control and is **not** re-run or revised.
- The replayed policy stays `REJECTED`. No replay can accept or activate anything.
- Every attempt, lab error and incomplete batch is retained and reported.
- Stop at the declared attempt cap and report a shortfall rather than extending it.
- Source frozen and the database snapshotted first.

## Honest statement of what a positive result would and would not mean

A jump from 0 of 13 to, say, 4 of 6 would show that **the gate's inability to certify a
working repair was substantially an artifact of Actor transcription** — which is a finding
about this lab's measurement apparatus, not a demonstration that the Mechanic can generate
repairs reliably. That remains 3 of 14 first proposals from Phase 9, unchanged by anything
here.

It would also not mean a policy has been accepted. A replay cannot accept.
