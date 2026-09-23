# Phase 10 protocol — how often does the gate reject a working repair?

Written **before** any paid call. Results go in `PHASE10_RESULTS.md`; progress in
`PHASE10_TASKS.md`.

Phase 9 produced the first generated policy ever to pass this project's source gate, and
then watched it lose validation to a single episode in which **the Actor hallucinated an
evidence ID**. That raises a question the project has never asked and cannot answer from
the data it has:

> When a repair actually works, how often does the validation gate reject it anyway,
> for reasons that have nothing to do with the repair?

One validation batch has ever run. It contained 21 candidate-arm episodes and 1 violation.
If that ~4.8% per-episode rate is real, a batch of 21 passes only `0.952²¹ ≈ 36%` of the
time — meaning **roughly two out of three working repairs would be rejected by Actor noise
alone**. That estimate rests on a single observation. This phase measures it properly.

## What this phase is not

**It is not an attempt to get T15's policy accepted.** That policy is saved as `REJECTED`
and stays `REJECTED`; Phase 9's decision is final and is not revised by anything here. A
completion study cannot accept or activate a policy, and replay mode cannot either.

**It is not resampling.** Phase 9's result is a fixed, reported fact. These replays measure
a property of the *gate* — its false-rejection rate under a policy already demonstrated to
work — which is a different quantity from the one Phase 9 estimated. The distinction is
that no replay can change any earlier verdict, promote anything, or be reported as
evidence that T15 "really" passed.

## The mechanism: replay mode in the completion study

Rather than a parallel harness that could silently drift from the real gate,
`queue_completion_study` gains a declared `replay_policy_version`. When supplied it:

- loads that saved policy and **makes no Mechanic call at all** — no proposal, no
  candidate creation, no controls gate;
- runs **only** the `validation` stage slots, the frozen seven-case × three-trial paired
  batch, through the unchanged `execute_slots`;
- applies the unchanged `assess_pairs(..., validation=True)`;
- records `replay_of` on the study and never writes an accepted policy.

Reusing `execute_slots` and `assess_pairs` verbatim is the point: the number this phase
reports is produced by the same code that rejected T15, not by a reimplementation of it.

## Design

**Twenty scored replays of T15's policy** (`policy-d2b12ec1325742f5ac1428ec28f19639`, hash
`ec1acaf76e74fbd5…`) through the frozen validation batch. 42 episodes each — 21 candidate,
21 baseline, paired on identical cases — for **840 episodes total**.

Everything else is unchanged: same manifest, same scorer, same episode limits, same
`policy-v0` incumbent, same Actor (V3.1), preserved `faultlab-actor-context/v1`, and **no
change to `assess_pairs` or any acceptance gate.**

### Primary read-out, fixed here

**Of the twenty scored replays, how many return `OBSERVED_IMPROVEMENT`** — the gate's own
pass verdict, computed by the unchanged `assess_pairs`?

A replay is **scored** when it produced a validation assessment. A replay that produced
none — a lab error, an evidence failure, a timeout — **observed nothing about the gate**
and is therefore neither a pass nor a rejection. It is retained, reported, and replaced,
up to an attempt cap of 26. Counting such a replay as a rejection would blame the gate for
an infrastructure failure; silently dropping it without replacement would shrink the
denominator in the favourable direction. Both are avoided by declaring the rule here.

Reported as a count out of twenty with a Wilson 95% interval, whatever it is.

### Secondary read-outs, fixed here

- **Per-episode violation rate, candidate arm versus baseline arm**, on 210 paired episodes
  each. Phase 9 measured 22% in the candidate arm on source stages against ~3% baseline,
  but only 4.8% in the one validation batch. This settles which number is real, on the
  seven-case mix the gate actually uses.
- **Per-case completion and violation rates**, both arms. Directly answers whether
  `notification-18` fails reproducibly or whether Phase 9's failure there was a one-off.
- **Cause of every violation**, classified by reading the saved report against the saved
  observations: a cited evidence ID that exists nowhere (hallucination), an unsupported
  status claim, or something else. Counts reported per class.
- **How often the baseline arm violates on the same case in the same replay**, which
  separates "this case is hard for the Actor" from "the policy makes it hard".

### Declared interpretation, set by what the interval can actually exclude

n was chosen so that both conclusions are reachable. At n = 20 the Wilson 95% interval
excludes a 50% pass rate only at 15 or more, or 5 or fewer:

| observed | Wilson 95% | supports |
|---|---|---|
| **≥ 15 of 20** | lower bound > 0.50 | the gate passes a working repair most of the time |
| **≤ 5 of 20** | upper bound < 0.50 | the gate rejects a working repair most of the time |
| 6–14 of 20 | interval spans 0.50 | **neither**; report the estimate and its width |

An earlier draft of this protocol declared these bands at n = 10, where they are
**unreachable**: at 8 of 10 the Wilson lower bound is 0.49, which supports nothing. The
adversarial review caught that before any money was spent, and n was raised rather than the
claims weakened.

No result licenses changing a threshold. If the gate turns out to be a coin flip, that is
reported as a measured limitation of the design.

## Limits

- **Twenty scored replays**, attempt cap **26**, declared here. No twenty-first scored
  replay, whatever the count reaches, and no attempt past the cap.
- No change to the grammar, interpreter, scorer, manifest, Actor prompt, proposal slots or
  any acceptance gate. Replay mode adds a path that runs fewer stages; it changes none.
- Every replay, trial, violation and lab error is retained and reported, including replays
  that end INCOMPLETE.
- T15's policy record stays `REJECTED`. No replay writes an acceptance.
- Source frozen and the database snapshotted first; only `algorithm_hash` and the derived
  `runtime_hash` may move.
- The protocol and the replay implementation are adversarially reviewed before the first
  paid call, as in Phase 9.

## Budget

42 episodes per replay at Phase 9's measured $0.14 per episode ≈ **$5.90 per replay**,
**~$118 for twenty** and at most **~$154** if every replacement attempt is used, against
**$898.74** remaining. A spend guard aborts the phase at $220.

## A prior from retained data, computed before the run

`scripts/experiments/analyze_citations.py` (read-only, no model call) classified every
citation in the 466 completion-study episodes that filed a report. **15 of them — 3.22% —
cite at least one evidence ID that is not an observation of that episode.** What those
citations are is the interesting part:

| kind | count |
|---|---|
| well-formed but nonexistent | 7 |
| malformed: word fragment spliced into the hex | 3 |
| malformed: characters dropped | 3 |
| malformed: other | 2 |

Examples: `evidence-1aac6983a3814424ac**extremely**b22b5f588d4`,
`evidence-41f8e866e3cc4a558288655**ylation**14e8d1`, and three IDs with 30–31 hex
characters where a real one has 32. These are **transcription failures, not reasoning
failures** — the Actor is asked to copy 32-character opaque identifiers and intermittently
drops characters or splices in a token.

C6 fails an episode on a single bad citation, so at 3.22% per episode a 21-episode
candidate arm passes only ≈ 50% of the time **from citation corruption alone**. That is
the prior this phase tests end-to-end, and it is recorded here, before the run, so the
result cannot be read as having been fitted to it.

## Stated limits on what this phase can conclude

- **One policy.** Every replay uses T15's policy, the only one that has ever qualified. A
  pass rate measured on it is a property of *that policy under this Actor*, and generalises
  to "a working repair" only as far as that policy is representative. It is the only
  instance available, and the limitation is real.
- **Sequential, not simultaneous.** The replays run one after another against one backend
  over several hours. Provider drift within that window is not controlled for, unlike
  Phase 9 where two arms were interleaved. There is no second arm here to interleave with;
  the mitigation is that the baseline arm inside every replay is contemporaneous with its
  candidate arm, so the *paired* per-case comparison is drift-free even if the absolute
  pass rate is not.
- **The Actor is pinned and verified** (`deepseek-ai/DeepSeek-V3.1`) before every replay,
  because replay makes no Mechanic call and the Actor produces all 840 episodes.

## This protocol was adversarially reviewed before any paid call

Five lenses raised 41 findings; a refutation pass confirmed 22. The ones that changed the
science or would have voided the run:

- **The declared interpretation bands were unreachable at n = 10.** Raised to 20.
- **The read-out denominator disagreed between the protocol and the runner**, and a failed
  replay shrank it in the favourable direction. The scored/replaced rule above is the fix.
- **The runner pinned the Mechanic model, which replay never calls, and never pinned the
  Actor, which produces every episode.**
- **The dashboard rejected every replay study record as malformed**, so the phase could not
  have been watched or inspected while 840 paid episodes ran.
- **A campaign created whose study then failed to start escaped the spend guard** — the
  same defect class the Phase 9 review found, reintroduced by adapting that runner.
- **Nothing verified that the study the runner started was actually a replay.** It now
  aborts unless the backend echoes `replay_of`.

