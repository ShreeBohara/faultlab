# Phase 6 results — September 20, 2026

Protocol fixed before any paid call: [PHASE6_EXPERIMENT.md](PHASE6_EXPERIMENT.md).
Progress: [PHASE6_TASKS.md](PHASE6_TASKS.md). Same $1,000 ceiling as Phases 2–5.

## Part A — comprehension probe: the hypothesis I picked is not supported

Eight non-scoring requests, two models × two conditions × two repeats, replaying the exact
saved Phase 5 proposal context. No campaign, no study, no trial, no policy. Outputs are in
`artifacts/phase6-2026-09-20/` and are fed into nothing.

| Model | Brief present | Repeat | Q1 names `retry_original_request` | Q2 verdict |
|---|---|---|---|---|
| V3.1 | yes | 0 | **yes** | PERMITTED |
| V3.1 | yes | 1 | **yes** | PERMITTED |
| V3.1 | no | 0 | no | UNCLEAR |
| V3.1 | no | 1 | no | UNCLEAR |
| V4-Pro | yes | 0 | no | PERMITTED |
| V4-Pro | yes | 1 | **yes** | PERMITTED |
| V4-Pro | no | 0 | no | PERMITTED |
| V4-Pro | no | 1 | no | PERMITTED |

**No response, in any condition, said replaying a dispatched write is forbidden.** Six of
eight said PERMITTED and quoted the contract sentence that settles it. The two UNCLEAR
answers are V3.1's, and they are a *retrieval* failure, not a belief — "the supplied
material does not contain text that explicitly permits or forbids" — in the condition
**without** the brief. The brief did not suppress the permission; for V3.1 it appears to
have helped locate it.

So **H1 is not supported.** The models do not believe the brief forbids a replay.

The open question is where the failure shows. Only 3 of 8 responses named
`retry_original_request` when asked, without prompting, which ops can cause the service to
record a new operation, effect or receipt. Worse, in both of V4's no-brief answers the op
list was `update_order` and `send_confirmation` — **the Actor's business tools, which are
not policy ops at all.** The model reached for the wrong vocabulary entirely.

That is the same signature as Phase 5's sharpest artifact, where V3.1 wrote "retrying the
original `send_confirmation` request" in prose and emitted a policy containing no retry
step. Two independent observations now point the same way: **the models know the op is
permitted when asked about it directly, and do not retrieve it when generating.** That is
H3, the mapping hypothesis.

Probe cost: 8 requests, 61,596 input and 2,536 output tokens, **$0.28296** conservative,
$0.06381 known-token estimate.

## The selection rule, and where it broke

The rule fixed in the protocol reads, in its first branch:

> If **any** response in the **with-brief** condition says replaying is forbidden **or
> omits `retry_original_request` from Q1**, **while** the matching **without-brief**
> response says permitted or names it → **H1 selected.**

Read literally, that branch fires: V4's with-brief repeat 0 omits the op from Q1, and its
matching no-brief response says PERMITTED. But the inference the branch exists to draw —
*the brief is what blocks it* — is not available, because the omission appears in **both**
conditions. The rule was written to detect a with/without contrast, and there is no such
contrast to detect. I am recording that the predeclared rule was satisfied by a degenerate
reading rather than quietly re-deriving a different one.

**Decision, recorded before Part B was run.** Part B runs the brief-clarification arm, the
same intervention and the exact wording already fixed in the protocol. What changes is the
reason and therefore the reading:

- It is **not** run to test whether the models believe retries are forbidden. Part A
  refuted that.
- It is run to test whether the blocker is **salience at generation time** — whether
  putting the permission in the *instruction* channel, where the model is being told what
  to do, changes behaviour when the same permission in the *reference* channel does not.
- The intervention is unchanged from what was declared, so nothing was selected to suit the
  data. Only the interpretation narrows, and it narrows in the direction that makes a
  positive result mean **less**, not more.

A gain here would show the proposal is sensitive to where a permission is stated. It would
still be prompt engineering, and it would still not show that a model finds the repair
unaided.

## Part B — the clarified brief changed nothing

One clause was appended to the existing prohibition in `completion.md`, exactly as the
protocol fixed it, and nothing else was touched (114 characters; `actor_prompt_hash`,
`scorer_hash`, `contract_hash`, `capability_hash`, `interpreter_hash` and `adapter_hash`
all identical to Phase 5, only `source_hash` moved):

> "…new tools or first writes from a recovery hook**; replaying a write already dispatched
> in this episode, with its original bytes and identity, is not a first write.**"

| Study | Mechanic | Proposals | Containing a notification retry | Decision |
|---|---|---|---:|---|
| 6A | `deepseek-ai/DeepSeek-V4-Pro-0813` | 2 | **0** | NO_CHANGE |
| 6B | `deepseek-ai/DeepSeek-V3.1` | 0 | — | NO_CHANGE (stopped at controls) |

6A: campaign `campaign-8f57ac087b48435aa40739f3633dc838`, study
`completion-study-7aea25bfc3e34ac797b42e7d5128b110`, 12 episodes, 12/12 verified, 77 calls.
6B: campaign `campaign-528752ed7c4642e9b7ef967ccab53f1f`, study
`completion-study-387f536ab6a84e64b444719ff8fd557a`, 6 episodes, 6/6 verified, 36 calls.

**V4 still never proposed the retry.** It added a `wait_ticks` and a second status read at
the notification hook — polling harder — and for the third study running its second
proposal was **byte-identical** to its first (`1673dabdb4f4` twice) while asserting "This
materially different policy adds a bounded wait-and-reread cycle". The one language shift
worth noting is that its explanation no longer says "never performs first writes *or
retries*"; it now says "without first writes", which is the qualified term. The belief
moved; the behaviour did not.

Combined with Phase 5, across two models and two versions of the brief:
**0 of 6 generated proposals contain the step that completes the task.**

## Two things this phase found by accident, both worth more than the arm itself

**The retain-and-continue fix earned its keep on its first live outing.** 6A's
candidate-1 stage hit an untriggered trial — `notification-2`, arm B0, trial 2, the same
signature that killed Phase 3 B2. The trial was retained, the stage was correctly assessed
`INCOMPLETE` rather than qualifying anything, and the study ran on to its second proposal.
Under the pre-Phase-6 code this run would have aborted and produced nothing.

**The source gap is 95.6%, not 100%.** 6B stopped at its controls because one of three
baseline trials completed the task, so the declared gap did not reproduce and no proposal
was requested. That is the controls rule working, and it exposed a structural fact nobody
had measured: across **45 valid, triggered, baseline-policy episodes** of the source case
in the whole database, the Actor completes it **2 times — 4.4%**.

The consequence matters for every future completion study. The controls gate requires
*zero* completions among three baseline trials, so it stops by chance about **13%** of the
time. `assess_pairs` requires `B0 completed == 0` on the candidate pairs too, so a perfect
candidate also fails about 13% of the time through baseline variance alone. That is a
power problem, not a correctness problem, and **it must not be fixed by loosening the gate
after seeing this result.** It is recorded here for a separately declared phase to address
prospectively — by declaring more control trials, not by weakening the threshold.

## What Phase 6 establishes

- **H1 is dead.** The models do not believe a replay is forbidden: 6 of 8 probe responses
  said PERMITTED and quoted the contract; none said forbidden. Clarifying the brief did not
  change a single proposal.
- **H3 is the live hypothesis.** The op is named in only 3 of 8 open-question answers, V4
  twice answered with the Actor's business tools instead of policy ops, and V3.1 has
  described the correct repair in prose while emitting a policy without it. The models know
  the op when pointed at it and do not reach for it when generating.
- **H2 is untouched** and is now the obvious next single-variable arm: inline the delivered
  error codes instead of interning them, so `TRANSIENT_UNAVAILABLE` appears in full at
  every occurrence rather than twice in ~24,000 bytes behind a table index.

Nothing was adopted. `policy-v0` is active in both campaigns, no policy record is
ACCEPTED, and the clarified brief is a declared source change that stays in place and is
recorded in the configuration identity.

## Cost

| Part | Requests | Conservative charge bound |
|---|---:|---:|
| A — comprehension probe (8 requests, non-scoring) | 8 | $0.28296 |
| B — study 6A (V4 Mechanic) | 77 | $1.66718 |
| B — study 6B (V3.1 Mechanic) | 36 | $0.75240 |
| Phase 6 total | 121 | **$2.70254** |

Part B tokens: 394,964 input and 7,482 output, zero unknown-usage requests; known-token
estimate $0.22957550. Part A: 61,596 input and 2,536 output, $0.06381.

Across Phases 2–6: **2,049 requests, $43.69230 conservatively charged, $956.30770
remaining.** Actual billed dollars unavailable. No deployment, paid overage or Aria call.

## What should happen next

Run the H2 arm — inlined evidence — as its own declared phase, with two changes to the
design this phase paid to learn:

1. **Declare more than three control trials**, prospectively, so a 4.4% baseline completion
   rate does not stop one study in eight before it asks anything. The `trial_index` bound
   of 0–2 means this needs a contract change, declared in advance.
2. **Expect the candidate stage to fail by chance too**, and say so in the protocol before
   running, so a single `B0 completed == 1` is read as variance rather than as evidence
   about the candidate.

Neither is authorized by this document, and neither may loosen an acceptance threshold.

