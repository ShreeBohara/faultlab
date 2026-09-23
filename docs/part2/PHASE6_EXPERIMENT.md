# Phase 6 protocol — why won't the Mechanic emit the retry?

Written **before** any paid call, after Phase 5 closed with 0 of 4 proposals containing the
one step that completes the task. This is the predeclared plan. Results go in
`PHASE6_RESULTS.md`; progress in `PHASE6_TASKS.md`.

Phase 5 established *that* two models never propose `retry_original_request` for
notifications. This phase asks *why*, in two parts: a cheap non-scoring probe that
discriminates the hypotheses, and then **one** declared single-variable study chosen by a
rule fixed here, before the probe runs.

## The tension being tested

The runtime contract supplied to the Mechanic says, verbatim:

> `retry_original_request`: "Replay an already attempted write for the supplied service
> using its persisted original bytes and identity. **No first write** and no retry after a
> matching FAILED receipt. **Notification retries are permitted only at
> `after_notification_response`.**"

The brief, `completion.md`, says in its list of prohibitions:

> "No code, scripts, URLs, literal task/order/fault IDs, hidden evaluation information, new
> tools or **first writes from a recovery hook**."

A replay of an already-dispatched write is not a first write, and the contract says so. But
Phase 5's V4 proposal volunteered, unprompted, that its policy "never performs first writes
**or retries**, preserving operation identities and authorization" — presenting non-retry
as a *safety* property. That is exactly what the brief's sentence produces if the qualifier
"first" is dropped.

Three hypotheses, from Phase 5:

- **H1 — belief:** the model believes a recovery hook may not replay a write.
- **H2 — visibility:** the model cannot see the failure mode, because
  `summarize_evidence` interns repeated rows and `TRANSIENT_UNAVAILABLE` appears literally
  twice in ~24,000 bytes of proposal input.
- **H3 — mapping:** the model knows and believes it is allowed, but does not map the
  concept onto the grammar. Phase 5's V3.1 described "retrying the original
  `send_confirmation` request" in prose and emitted a policy without it.

## Part A — comprehension probe (non-scoring)

A measurement, not an intervention. **No campaign, no study, no trial, no world, no policy,
no gate.** Its outputs are written to `artifacts/phase6-2026-09-20/` and are **never** fed
into any study, proposal context or evidence bundle.

Each probe request replays the **exact** saved Phase 5 proposal context
(`completion_proposal_inputs`, first slot: `…889f75d6…-1` for V4, `…122d93e0…-1` for
V3.1) as the user message, under a short probe system prompt that asks for an answer and
explicitly forbids proposing a policy. Two questions per request:

- **Q1 (open, does not mention retries or notifications):** list every op in the supplied
  `output_schema` that can cause the service to record a new operation, effect or receipt,
  and for each, the hooks where the supplied `runtime_contract` permits it.
- **Q2 (direct):** is a policy permitted to replay a write the actor already dispatched in
  this episode? Quote the supplied text that settles it.

**Design: 2 models × 2 conditions × 2 repeats = 8 requests.** The conditions are the probe
context **with** the `completion.md` brief appended and **without** it. That contrast is
the whole point: it isolates the brief from everything else.

Q1 is deliberately open. Q2 is deliberately leading — it names the behaviour — which is
precisely why the probe can only report what the model *knows and believes*, never what it
would *choose* to propose. Nothing in Part A is evidence about capability to solve the
task.

### Predeclared read-out for Part A

For each of the 8 responses, three mechanical facts:

1. Does the Q1 answer name `retry_original_request`?
2. Does the Q2 answer say replaying a dispatched write is **permitted**, **forbidden** or
   is unclear?
3. Does the response quote the contract's "Notification retries are permitted only at
   `after_notification_response`" sentence, or the brief's "first writes" sentence?

### Predeclared selection rule for Part B

Fixed here, before the probe runs, so the choice is not made on a hunch after seeing
results:

- If **any** response in the **with-brief** condition says replaying is forbidden or omits
  `retry_original_request` from Q1, **while** the matching **without-brief** response says
  permitted or names it → **H1 selected.** Part B runs the brief-clarification arm.
- Else if responses name the op and call it permitted in **both** conditions → the model
  knows and believes it is allowed, so the brief is not the blocker → **H2 selected.**
  Part B runs the evidence-inlining arm.
- Else (the op is missing or called forbidden in **both** conditions) → **H3/H1-as-belief,
  brief-independent.** Part B still runs the brief-clarification arm, because it is the
  only one of the two that addresses a belief, and the result is reported as a test of that
  belief rather than of the brief's wording.

## Part B — one single-variable study pair

Whichever arm the rule selects, Part B is **two completion studies**, one per Mechanic
model, identical to Phase 5 in every other respect: same nine-case manifest, three trials
per case, two proposal slots, the unchanged `policy-v0`, the preserved
`faultlab-actor-context/v1` Actor context, the unchanged C1–C8 scorer, unchanged episode
limits, and **no change to `assess_pairs` or any acceptance gate**. Phase 5's two studies
are the matched controls; they ran on the immediately preceding source.

### If H1 is selected — the exact change

One clause appended to the existing prohibition in `completion.md`, clarifying the scope of
a restriction that is already there:

> "…new tools or first writes from a recovery hook; replaying a write already dispatched in
> this episode, with its original bytes and identity, is not a first write."

It names no tool, no service, no fault, no failure mode and no desired behaviour, and it
restates language that already appears verbatim in the supplied runtime contract. **It is
still prompt engineering and it still raises the salience of one op.** A gain would show
the brief was ambiguous. It would **not** show the model can find the repair unaided, and
this document forbids reporting it that way.

### If H2 is selected — the exact change

`summarize_evidence` stops interning observation result rows and inlines them, so every
delivered `error_code` appears in full at every occurrence. No field is added, removed or
reworded; only the compression changes. Input size grows and must be re-checked against the
32,000-token admission bound before dispatch.

### Read-outs, fixed before execution

- **Primary, mechanical:** of the proposals generated, how many contain a step with
  `op == "retry_original_request"` and `service == "notifications"`? Directly comparable to
  Phase 5's 0 of 4.
- **Secondary:** each study's own decision under its unchanged rule. `SOURCE_QUALIFIED`
  still requires 3 of 3 candidate completions against 0 of 3 baseline on exact valid pairs;
  `OBSERVED_IMPROVEMENT` still requires the frozen seven-case validation batch.
- **Tertiary:** controls assessment, per-case counts, retained invalid trials, charged
  calls, and every raw proposal including invalid and duplicate ones.

**Interpretation fixed in advance.** `OBSERVED_IMPROVEMENT` in a completion study is not
policy acceptance, does not invoke the invariant-repair gates, does not activate anything,
and leaves `policy-v0` active. If a candidate qualifies it will be reported as the first
generated rule in this project to do so *under a clarified brief* — with the clarification
named in the same sentence, every time.

## Limits

- Part A: 8 probe requests, no trials. Part B: two studies, two proposal slots each.
- **No second Part B.** Whichever arm the rule selects is the only one run in this phase,
  whatever it shows. The other hypothesis stays open for a separately declared phase.
- No resampling, no replacement trial, no post-hoc change to any threshold or read-out, no
  edit to the policy grammar, the interpreter, the scorer, the manifest, the Actor prompt
  or any acceptance gate.
- Every attempted trial, probe response, invalid proposal and duplicate is retained.
- Stop conditions as in Phase 5: operator stop, configuration or manifest drift mid-run, a
  trial not matching its predeclared slot, a reused world identity, or unavailable verified
  evidence.

## Budget

Part A: 8 requests, worst case about **$0.40**. Part B: 2 × 484 reserved, worst case about
**$22**. Total worst case **$22.40** against $959.01024 remaining. Admission needs
(1064 + 484) × $0.04984 = $77.15 of the $400 campaign cap.
