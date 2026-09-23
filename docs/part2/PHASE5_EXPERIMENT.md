# Phase 5 protocol — does a generated rule actually repair the task?

Written **before** any paid call, after Phase 4 closed with two REGRESSION results and an
adversarial review of that work. This is the predeclared plan. Results go in
`PHASE5_RESULTS.md`; progress in `PHASE5_TASKS.md`.

This is the product promise, and it has never been properly tested. Phase 3 B asked the
DeepSeek V3.1 Mechanic twice and got two rules that polled instead of re-sending. Phase 3
B2 was configured with the V4 Mechanic and **died during Actor controls, on its sixth of
sixty trials, without making a single Mechanic call.** Nothing is known about V4 here.

## What is already established

Four things are settled by saved evidence and were re-verified for this protocol.

**The failure is real and reproducible.** On the declared source case
(`F4 send_confirmation failure_count=2`) the baseline Actor made exactly one
`send_confirmation` call and never a second in 18 of 18 Phase 3 episodes, completing 0 of
18 with 7–10 of its 18 HTTP attempts still free. Phase 4 re-measured the same behaviour
across 60 fresh control episodes.

**A correct rule is expressible and the engine executes it.** One rule is enough:

```json
{"hook": "after_notification_response",
 "when": "notification_outcome_uncertain",
 "steps": [{"op": "retry_original_request", "service": "notifications", "only_if": "always"}]}
```

Every element is legal at that hook under the policy grammar, and the identical runtime
path is already proven live: the handwritten B1 reference actor calls the same
`broker.retry_original(..., hook='after_notification_response')`, and **9 of 9** of its
`notification-2` trials in the database completed with one notification effect. The rule
is also inert on the other cases — `notification-1` resolves inside the adapter's own
retry, `notification-18` exhausts the HTTP budget and stays safely unresolved,
`lost-notification-response` already holds a receipt, and `terminal-upgrade-rejection`
never attempts a notification, so `notification_outcome_uncertain` is false there.

**The Mechanic had what it needed and still missed it.** Both Phase 3 B proposals used the
*right condition* (`notification_outcome_uncertain`) with the *wrong steps* (`wait_ticks`
+ `read_notification_operation`). The delivered `runtime_contract` spelled out that
`retry_original_request` "replays an already attempted write" and that a status read "does
not submit a confirmation"; the second proposal also received the first candidate's
`completed: 0` assessment and still described it as "showing potential". Separately, in
the older invariant-repair campaigns the same model *did* propose
`retry_original_request` for notifications at the correct hook — in three of those
policies gated on `notification_operation_pending`, a condition that is provably false
after a pre-acceptance rejection (status is `UNKNOWN`, not `PENDING`; verified directly
against `PolicyState`). The model has produced each half of the correct rule in different
runs and never both together under this objective.

**No reasoning trace exists.** `mechanic_outputs` stores only the returned content, and
the provider layer never retains reasoning, so *why* V3.1 chose polling is unknowable from
the record. This protocol does not speculate about it.

## One blocking fix, made before this protocol was finalised

`completion_study.py` aborted the whole batch on the first trial whose scheduled fault did
not trigger. That is exactly what killed Phase 3 B2, and it is not a rare event: on the
source case the measured untriggered rate is 2/27 across every baseline trial in the
database and 1/6 in Phase 4's control arm, giving a **20–42% chance of losing the run
during the six controls alone** and roughly **70–80% across a full study**.

The fix retains such a trial, never replaces it and never resamples, and lets the declared
assessment decide. **No acceptance gate moved.** `assess_pairs` still demands an exact set
of valid, triggered, correctly-bound pairs, so a stage containing an invalid trial can
only fail to qualify a candidate — never qualify one. A new test asserts exactly that. The
only rule that changed is the controls gate, which decides whether to *pay* for a
proposal, and it is now stated as: at least two valid source controls with zero
completions among them, and at least two valid healthy controls all completing. An
untriggered source trial can never be a completion, so excluding it cannot hide one.

## The experiment

Two studies. The **only** declared difference between them is the Mechanic model.

| Study | Mechanic | Actor | Everything else |
|---|---|---|---|
| **5A** | `deepseek-ai/DeepSeek-V4-Pro-0813` | `deepseek-ai/DeepSeek-V3.1` | identical |
| **5B** | `deepseek-ai/DeepSeek-V3.1` | `deepseek-ai/DeepSeek-V3.1` | identical |

5B is a matched control run under the current code. Phase 3 B is *not* a matched control —
it predates this phase's source — so its result is treated as a historical prior, not as
5B's substitute.

Unchanged from Phase 3 B and not to be touched: `completion.md`, the
`proposal_context` construction, `summarize_evidence`'s interning, the runtime contract,
the Actor prompt and model, the four tools, the C1–C8 scorer, the episode limits, the
nine-case manifest, three trials per case, and **two proposal slots per study**. Keeping
two slots is deliberate: changing the number would make Phase 3 B incomparable.

Each study runs its own fresh live baseline campaign with the unchanged `policy-v0`, on
the public development manifest only. The Actor runs the preserved
`faultlab-actor-context/v1` context in both — Phase 4's `attempted_writes` block is **not**
used here and cannot leak in, because `completion_study` never passes a protocol.

## Predeclared read-outs, fixed before execution

**Primary, mechanical:** of the proposals each study generates (at most two), how many
contain a step with `op == "retry_original_request"` and `service == "notifications"`?
Reported as a count out of the proposals actually made, per study. This is a syntactic
property of the saved proposal and involves no judgement.

**Secondary:** the study's own decision under its unchanged rule —
`SOURCE_QUALIFIED` for a candidate requires 3 of 3 fresh candidate completions against 0
of 3 baseline completions on exact valid pairs; `OBSERVED_IMPROVEMENT` additionally
requires the frozen seven-case validation batch to show a strict completion gain with no
case regression and no candidate violation.

**Tertiary, descriptive:** the controls assessment, the per-case counts, every retained
invalid trial, the charged calls, and the raw model output of every proposal including
invalid and duplicate ones.

**Interpretation fixed in advance.** `OBSERVED_IMPROVEMENT` in a completion study is
**not** policy acceptance. It does not invoke the invariant-repair gates, does not
activate a policy, does not satisfy the final-audit or transfer gates, and leaves
`policy-v0` active everywhere. If a candidate qualifies, that is the first generated rule
in this project's history to do so, and it will be reported as exactly that and nothing
more.

## Limits

- **Two studies. Two proposal slots each. No third model, no extra slot, no rerun,
  whatever the outcome.** If both fail, that is the result.
- No resampling, no replacement trial, no post-hoc change to any threshold or read-out.
- Every attempted trial, invalid proposal, duplicate proposal and rejected candidate is
  retained.
- Nothing here may edit the Actor prompt, the policy grammar, the interpreter, the scorer,
  the manifest or any acceptance gate.
- Stop conditions: operator stop, configuration or manifest drift mid-run, a returned
  trial that does not match its predeclared slot, a reused world identity, or unavailable
  verified evidence. All attempted effects are retained; nothing is replayed.

## Budget

Each study reserves 484 model calls (60 slots × 8 Actor calls + 2 proposal slots × 2
Mechanic attempts). Two studies: **968 reserved**, worst case about **$22** conservative
at the frozen rates, inside a remaining allowance of $962.53752. Admission needs
(1064 + 484) × $0.04984 = $77.15 of the $400 campaign cap, which fits.

## A follow-up this protocol deliberately does NOT authorize

The review found that `summarize_evidence` interns repeated observation rows, so
`TRANSIENT_UNAVAILABLE` appears as a literal string **twice in 23,901 bytes** of the real
Phase 3 B proposal input, reachable only by dereferencing a table index. That is a
plausible reason the failure mode was missed, and testing it — inlining the error codes
rather than interning them — is a defensible experiment. **It is a second variable and
must be declared and run on its own.** Folding it into this comparison would confound "a
stronger model proposes the retry" with "better-presented evidence reveals the failure".
